"""Offline lineage regressions for sealed warm runs and the managed map-test child replacement."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import map_owner as owner


def write(path, obj):
    """Create a standalone JSON fixture without accessing any live session or user settings."""
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj),encoding='utf-8')


class MapOwnerTest(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve() / 'artifacts'
        self.patch = patch.object(owner,'ARTIFACTS',root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.prior = root / 'live/walk/warm-launcher.json'
        self.folder = root / 'live/map/lineage'
        package = lambda release: root / f'release-r{release}' / 'BetterGI-English-win-x64'
        host = dict(instanceType='Primary',instanceNonce='1'*32,processId=10124,windowsSessionId=1,
                    remoteDesktop=False,automationEnabled=True,uiStatus='current',childWindowMinimized=True,
                    childSessionId=3,childConnectedState=1,appDirectory=str(package(56)),assemblySha256=owner.ROOT_DLL)
        child = dict(instanceType='ChildSession',instanceNonce='2'*32,processId=21240,windowsSessionId=3,
                     remoteDesktop=True,automationEnabled=True,uiStatus='current',automationState='game_ready',
                     runtimeRunning=True,pilotState='idle',taskRunning=False,agentStreamRunning=False,
                     rootProcessId=10124,appDirectory=str(package(57)),assemblySha256=owner.OLD_DLL,idleRestartVersion=2)
        self.ids = dict(root=owner.identity(host),child=owner.identity(child))
        self.warm = dict(computer='SIREN',status='completed',auditStatus='runtime-target-achieved',identity=self.ids)
        self.audit = dict(status='runtime-target-achieved',passed=True,stopVerified=False,rootPid=10124,
                          childPid=21240,windowsSessionId=3,rdpJob=dict(windowsSessionId=3,rootNonce='1'*32,childNonce='2'*32))
        write(self.prior,self.warm)
        write(self.prior.with_name('handoff-audit.json'),self.audit)
        self.before = dict(instances=[host,child],unavailable=[])
        write(self.folder/'before.json',self.before)
        self.target = package(58)
        self.target.mkdir(parents=True)
        selected = dict(targetDirectory=str(self.target))
        for ext in ('exe','dll'):
            data = (ext+' fixture').encode()
            (self.target/f'BetterGI.{ext}').write_bytes(data)
            selected[ext+'Sha256'] = hashlib.sha256(data).hexdigest()
        self.build = dict(selected,version=1,validationConfiguration='Debug',publishConfiguration='Release',
                          runtimeIdentifier='win-x64',selfContained=True)
        write(self.target.parent/'build-manifest.json',self.build)
        digest = hashlib.sha256(json.dumps(owner.CLEAN_CAPTURE).encode()).hexdigest()
        write(self.folder/'preflight.json',dict(source=self.ids,targetConfigSha256=digest,**selected))
        new_child = dict(child,instanceNonce='3'*32,processId=333,appDirectory=str(self.target),assemblySha256=selected['dllSha256'])
        self.new_owner = dict(root=owner.identity(host),child=owner.identity(new_child))
        self.result = dict(success=True,rootReady=True,childReady=True,gameReady=True,childReplaced=True,
            childStartDispatched=False,readinessScope='game_runtime',previousProcessId=21240,
            root=host,child=new_child,selectedPackage=selected,replacementEvidence=dict(phase='replacement_ready',
                restartRequestAttempted=True,restartAcknowledged=True,readinessPolls=2,previousProcessId=21240,
                previousNonce='2'*32,replacementProcessId=333,replacementNonce='3'*32,targetDirectory=str(self.target),
                existingTargetConfigSha256=digest))
        write(self.folder/'ensure-child.json',self.result)

    def test_original_seal_and_replacement_replay(self):
        self.assertEqual(owner.load_map_owner(self.prior),self.ids)
        receipt = owner.replacement(self.prior,self.folder)
        path = self.folder/'map-owner-lineage.json'
        write(path,receipt)
        self.assertEqual(owner.load_map_owner(path),self.new_owner)
        write(self.folder/'ensure-child.json',dict(self.result,extra='changed original report'))
        with self.assertRaises(ValueError):
            owner.load_map_owner(path)

    def test_prior_seal_requires_real_terminal_audit_and_broker(self):
        for fields in (dict(status='running'),dict(computer='LAPTOP'),dict(auditStatus='unknown')):
            write(self.prior,dict(self.warm,**fields))
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                owner.load_map_owner(self.prior)
        write(self.prior,self.warm)
        for fields in (dict(passed=False),dict(rootPid=5),dict(rdpJob=dict(self.audit['rdpJob'],childNonce='9'*32))):
            write(self.prior.with_name('handoff-audit.json'),dict(self.audit,**fields))
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                owner.load_map_owner(self.prior)

    def test_stale_source_and_busy_original_rejected(self):
        for index,fields in ((0,dict(instanceNonce='4'*32)),(1,dict(instanceNonce='8'*32)),(1,dict(taskRunning=True)),
                             (1,dict(agentStreamRunning=True)),(1,dict(rootProcessId=87)),(1,dict(assemblySha256='a'*64))):
            before = deepcopy(self.before)
            before['instances'][index].update(fields)
            write(self.folder/'before.json',before)
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                owner.replacement(self.prior,self.folder)

    def test_incomplete_restart_and_swapped_target_rejected(self):
        for key,fields in (('root',dict(instanceNonce='4'*32)),('child',dict(taskRunning=True)),
                           ('selectedPackage',dict(dllSha256='a'*64)),('selectedPackage',dict(exeSha256='a'*64)),
                           ('child',dict(assemblySha256='a'*64)),('child',dict(instanceNonce='4'*32)),
                           ('replacementEvidence',dict(previousNonce='9'*32)),('replacementEvidence',dict(restartAcknowledged=False)),
                           ('replacementEvidence',dict(phase='restart_request')),('replacementEvidence',dict(readinessPolls=0)),
                           ('replacementEvidence',dict(existingTargetConfigSha256='a'*64))):
            result = deepcopy(self.result)
            result[key].update(fields)
            write(self.folder/'ensure-child.json',result)
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                owner.replacement(self.prior,self.folder)
        write(self.folder/'ensure-child.json',{k:v for k,v in self.result.items() if k!='replacementEvidence'})
        with self.assertRaises(KeyError):
            owner.replacement(self.prior,self.folder)

    def test_actual_target_binary_changed_after_publication(self):
        (self.target/'BetterGI.dll').write_bytes(b'swapped after manifest')
        with self.assertRaisesRegex(ValueError,'Changed R58 binary'):
            owner.replacement(self.prior,self.folder)

    def create_successor(self):
        """Retain the complete R58 receipt and create a distinct R59 build and actual-style acknowledged handoff."""
        first = self.folder/'map-owner-lineage.json'
        write(first,owner.replacement(self.prior,self.folder))
        second = self.folder.parent/'r59'
        game = dict(processId=777,windowsSessionId=3,startedFileTime=1234567890,executable='GenshinImpact.exe')
        write(second/'game-before.json',game)
        write(second/'before.json',dict(instances=[self.result['root'],self.result['child']],unavailable=[]))
        target = owner.ARTIFACTS/'release-r59/BetterGI-English-win-x64'
        target.mkdir(parents=True)
        selected = dict(targetDirectory=str(target))
        for ext in ('exe','dll'):
            data = (ext+' R59').encode()
            (target/f'BetterGI.{ext}').write_bytes(data)
            selected[ext+'Sha256'] = hashlib.sha256(data).hexdigest()
        write(target.parent/'build-manifest.json',dict(self.build,**selected))
        res = deepcopy(self.result)
        old = self.result['child']
        res['child'].update(processId=999,instanceNonce='9'*32,appDirectory=str(target),assemblySha256=selected['dllSha256'])
        res.update(selectedPackage=selected,previousProcessId=old['processId'],protectedGame=game)
        res['replacementEvidence'].update(previousProcessId=old['processId'],previousNonce=old['instanceNonce'],
            replacementProcessId=999,replacementNonce='9'*32,targetDirectory=str(target))
        write(second/'ensure-child.json',res)
        write(second/'preflight.json',dict(source=self.new_owner,protectedGame=game,
            targetConfigSha256=res['replacementEvidence']['existingTargetConfigSha256'],**selected))
        return first,second,res,game

    def test_only_one_additional_handoff_replays_original_and_protected_game(self):
        first,second,res,game = self.create_successor()
        # No R57 payload exists in this fixture; source identity is reconstructed from the original audit.
        lineage = owner.replacement(first,second)
        self.assertEqual(lineage['protectedGame'],game)
        receipt = second/'map-owner-lineage.json'
        write(receipt,lineage)
        self.assertEqual(owner.load_map_owner(receipt)['child'],owner.identity(res['child']))
        self.assertEqual(owner.load_map_owner(first),self.new_owner)
        with self.assertRaisesRegex(ValueError,'direct R57 to R58'):
            owner.preflight(receipt,second/'before.json')

    def test_r59_rejects_missing_or_substituted_game_lifetime(self):
        first,second,res,game = self.create_successor()
        for field,value in (('startedFileTime',1),('windowsSessionId',4),('processId',654),('executable','other.exe')):
            write(second/'ensure-child.json',dict(res,protectedGame=dict(game,**{field:value})))
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'game lifetime'):
                owner.replacement(first,second)
        write(second/'ensure-child.json',res)
        (second/'game-before.json').unlink()
        with self.assertRaises(FileNotFoundError):
            owner.replacement(first,second)

    def test_r59_rejects_changed_prior_lineage_or_source_package(self):
        first,second,_,_ = self.create_successor()
        receipt = json.loads(first.read_bytes())
        write(first,dict(receipt,buildSha256='a'*64))
        with self.assertRaisesRegex(ValueError,'lineage receipt'):
            owner.replacement(first,second)
        write(first,receipt)
        (self.target/'BetterGI.exe').write_bytes(b'changed original R58')
        with self.assertRaisesRegex(ValueError,'Changed R58 binary'):
            owner.replacement(first,second)

    def test_clean_capture_settings_before_upgrade(self):
        path = self.target/'User/config.json'
        with self.assertRaises((ValueError,OSError)):
            owner.check_clean_target(self.build)
        write(path,dict(owner.CLEAN_CAPTURE,unexpectedProfileData='refuse'))
        with self.assertRaises(ValueError):
            owner.check_clean_target(self.build)
        write(path,owner.CLEAN_CAPTURE)
        owner.check_clean_target(self.build)
