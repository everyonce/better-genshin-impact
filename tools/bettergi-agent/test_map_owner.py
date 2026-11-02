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

    def test_r59_handoff_replays_original_and_protected_game(self):
        first,second,res,game = self.create_successor()
        # No R57 payload exists in this fixture; source identity is reconstructed from the original audit.
        lineage = owner.replacement(first,second)
        self.assertEqual(lineage['protectedGame'],game)
        receipt = second/'map-owner-lineage.json'
        write(receipt,lineage)
        self.assertEqual(owner.load_map_owner(receipt)['child'],owner.identity(res['child']))
        self.assertEqual(owner.load_map_owner(first),self.new_owner)
        # A stale R58 discovery cannot authorize a subsequent R59 replacement.
        with self.assertRaises(ValueError):
            owner.preflight(receipt,second/'before.json')

    def create_next_handoff(self, prior, previous, game, number):
        """Build a complete successor candidate, including an unsupported later release when a test needs one."""
        folder=prior.parent.parent/f'r{number}'
        write(folder/'before.json',dict(instances=[previous['root'],previous['child']],unavailable=[]))
        write(folder/'game-before.json',game)
        target=owner.ARTIFACTS/f'release-r{number}/BetterGI-English-win-x64'
        target.mkdir(parents=True)
        selected=dict(targetDirectory=str(target))
        for ext in ('exe','dll'):
            data=(ext+f' R{number}').encode()
            (target/f'BetterGI.{ext}').write_bytes(data)
            selected[ext+'Sha256']=hashlib.sha256(data).hexdigest()
        write(target.parent/'build-manifest.json',dict(self.build,**selected))
        result=deepcopy(previous)
        old=previous['child']
        result['child'].update(processId=number*100,instanceNonce=f'{number:032x}',
                               appDirectory=str(target),assemblySha256=selected['dllSha256'])
        result.update(selectedPackage=selected,previousProcessId=old['processId'])
        result['replacementEvidence'].update(previousProcessId=old['processId'],previousNonce=old['instanceNonce'],
            replacementProcessId=result['child']['processId'],replacementNonce=result['child']['instanceNonce'],
            targetDirectory=str(target))
        write(folder/'ensure-child.json',result)
        write(folder/'preflight.json',dict(source=owner.load_map_owner(prior),protectedGame=game,
            targetConfigSha256=result['replacementEvidence']['existingTargetConfigSha256'],**selected))
        return folder,result

    def create_r60_successor(self):
        """Seal the R59 predecessor before constructing the existing R60 handoff."""
        first,second,previous,game=self.create_successor()
        prior=second/'map-owner-lineage.json'
        write(prior,owner.replacement(first,second))
        folder,result=self.create_next_handoff(prior,previous,game,60)
        return prior,folder,result,game

    def create_r61_successor(self):
        """Keep the complete original chain intact before preparing the one newly admitted transition."""
        previous,folder,result,game=self.create_r60_successor()
        prior=folder/'map-owner-lineage.json'
        write(prior,owner.replacement(previous,folder))
        folder,result=self.create_next_handoff(prior,result,game,61)
        return prior,folder,result,game

    def create_r62_successor(self):
        """Seal the complete R61 chain before constructing only the next R62 candidate."""
        previous,folder,result,game=self.create_r61_successor()
        prior=folder/'map-owner-lineage.json'
        write(prior,owner.replacement(previous,folder))
        folder,result=self.create_next_handoff(prior,result,game,62)
        return prior,folder,result,game

    def create_r63_successor(self):
        """Seal the complete R62 chain before preparing its explicitly supported successor."""
        previous,folder,result,game=self.create_r62_successor()
        prior=folder/'map-owner-lineage.json'
        write(prior,owner.replacement(previous,folder))
        folder,result=self.create_next_handoff(prior,result,game,63)
        return prior,folder,result,game

    def create_r64_successor(self):
        """Seal R63 before preparing the one next package that carries the ground-control guard."""
        previous,folder,result,game=self.create_r63_successor()
        prior=folder/'map-owner-lineage.json'
        write(prior,owner.replacement(previous,folder))
        folder,result=self.create_next_handoff(prior,result,game,64)
        return prior,folder,result,game

    def create_r65_successor(self):
        """Seal the original R64 owner before preparing only its explicitly supported R65 successor."""
        previous,folder,result,game=self.create_r64_successor()
        prior=folder/'map-owner-lineage.json'
        write(prior,owner.replacement(previous,folder))
        folder,result=self.create_next_handoff(prior,result,game,65)
        return prior,folder,result,game

    def create_r66_successor(self):
        """Retain the complete R65 chain and give only the new endpoints explicit idle/config evidence."""
        previous,folder,result,game=self.create_r65_successor()
        prior=folder/'map-owner-lineage.json'
        write(prior,owner.replacement(previous,folder))
        folder,result=self.create_next_handoff(prior,result,game,66)
        before=json.loads((folder/'before.json').read_bytes())
        for status in (*before['instances'],result['root'],result['child']):
            status.update(taskRunning=False,agentStreamRunning=False,serviceOwnsPilot=False)
        build,_=owner.target_package(66)
        write(Path(build['targetDirectory'])/'User/config.json',owner.R62_CLEAN_CAPTURE)
        digest=owner.check_clean_target(build)
        preflight=json.loads((folder/'preflight.json').read_bytes())
        preflight['targetConfigSha256']=digest
        result['replacementEvidence']['existingTargetConfigSha256']=digest
        write(folder/'before.json',before)
        write(folder/'preflight.json',preflight)
        write(folder/'ensure-child.json',result)
        return prior,folder,result,game

    def create_r67_successor(self):
        """Seal R66 and prepare exactly its next fresh English, explicitly released successor."""
        previous,folder,result,game=self.create_r66_successor()
        prior=folder/'map-owner-lineage.json'
        write(prior,owner.replacement(previous,folder))
        folder,result=self.create_next_handoff(prior,result,game,67)
        build,_=owner.target_package(67)
        write(Path(build['targetDirectory'])/'User/config.json',owner.R62_CLEAN_CAPTURE)
        digest=owner.check_clean_target(build)
        preflight=json.loads((folder/'preflight.json').read_bytes())
        preflight['targetConfigSha256']=digest
        result['replacementEvidence']['existingTargetConfigSha256']=digest
        write(folder/'preflight.json',preflight)
        write(folder/'ensure-child.json',result)
        return prior,folder,result,game

    def test_r67_replays_exact_original_root_and_game(self):
        """Only one new finite handoff is permitted, even with a fabricated later package present."""
        prior,folder,result,game=self.create_r67_successor()
        receipt=owner.replacement(prior,folder);path=folder/'map-owner-lineage.json'
        write(path,receipt)
        self.assertEqual(owner.load_map_owner(path),dict(root=self.ids['root'],child=owner.identity(result['child'])))
        self.assertEqual(receipt['protectedGame'],game)
        self.assertEqual(receipt['priorLineageSha256'],hashlib.sha256(prior.read_bytes()).hexdigest())

    def assert_r67_retains(self,regression):
        """Replay an unchanged adversarial contract on the actual additional predecessor depth."""
        fixture=self.create_r67_successor()
        with patch.object(self,'create_r66_successor',return_value=fixture):regression()

    def test_r67_rejects_changed_or_missing_game_lifetime(self):
        """Coherently changed reports still cannot replace the original Genshin lifetime."""
        self.assert_r67_retains(self.test_r66_rejects_coherently_changed_or_missing_game_lifetime)

    def test_r67_rejects_changed_root_stale_source_or_reused_destination(self):
        """The source and destination must retain distinct exact authenticated identities."""
        self.assert_r67_retains(self.test_r66_rejects_changed_root_stale_source_or_reused_destination)

    def test_r67_requires_explicit_idle_at_both_endpoints(self):
        """Missing, active and non-boolean ownership cannot qualify either owner."""
        self.assert_r67_retains(self.test_r66_requires_explicitly_released_root_and_child_at_both_endpoints)

    def test_r67_rejects_skipped_circular_or_rewritten_predecessors(self):
        """The one extra hop must still replay each exact original immutable report."""
        self.assert_r67_retains(self.test_r66_rejects_skipped_circular_or_rewritten_predecessors)

    def test_r67_clean_target_requires_fresh_english_defaults(self):
        """Only the same clean capture and English schema may enter the new child."""
        _,_,result,_=self.create_r67_successor();build,_=owner.target_package(67)
        config=Path(result['selectedPackage']['targetDirectory'])/'User/config.json'
        self.assertEqual(owner.check_clean_target(build),hashlib.sha256(config.read_bytes()).hexdigest())
        for changed in (owner.CLEAN_CAPTURE,dict(owner.R62_CLEAN_CAPTURE,extra=True),
                dict(owner.R62_CLEAN_CAPTURE,otherConfig={'uiCultureInfoName':'en','gameCultureInfoName':'zh-Hans'}),
                dict(owner.R62_CLEAN_CAPTURE,wgcV2ReadbackMode='nonblocking')):
            write(config,changed)
            with self.subTest(config=changed),self.assertRaisesRegex(ValueError,'Unexpected target capture settings'):
                owner.check_clean_target(build)

    def test_r67_source_and_target_witnesses_preserve_replay(self):
        """Removed complete runtimes retain identity evidence; damaged live or witness bytes still refuse."""
        prior,folder,result,_=self.create_r67_successor()
        self.check_source_and_target_witnesses(prior,folder,result,(66,67))

    def create_r68_successor(self):
        """Seal R67 and prepare exactly its next fresh English, explicitly released successor."""
        previous,folder,result,game=self.create_r67_successor()
        prior=folder/'map-owner-lineage.json'
        write(prior,owner.replacement(previous,folder))
        folder,result=self.create_next_handoff(prior,result,game,68)
        build,_=owner.target_package(68)
        write(Path(build['targetDirectory'])/'User/config.json',owner.R62_CLEAN_CAPTURE)
        digest=owner.check_clean_target(build)
        preflight=json.loads((folder/'preflight.json').read_bytes())
        preflight['targetConfigSha256']=digest
        result['replacementEvidence']['existingTargetConfigSha256']=digest
        write(folder/'preflight.json',preflight)
        write(folder/'ensure-child.json',result)
        return prior,folder,result,game

    def test_r68_replays_exact_original_root_and_game(self):
        """Only one new finite handoff is permitted, even with a fabricated later package present."""
        prior,folder,result,game=self.create_r68_successor()
        receipt=owner.replacement(prior,folder);path=folder/'map-owner-lineage.json'
        write(path,receipt)
        self.assertEqual(owner.load_map_owner(path),dict(root=self.ids['root'],child=owner.identity(result['child'])))
        self.assertEqual(receipt['protectedGame'],game)
        self.assertEqual(receipt['priorLineageSha256'],hashlib.sha256(prior.read_bytes()).hexdigest())

    def assert_r68_retains(self,regression):
        """Replay an unchanged adversarial contract on the actual additional predecessor depth."""
        fixture=self.create_r68_successor()
        with patch.object(self,'create_r66_successor',return_value=fixture):regression()

    def test_r68_rejects_changed_or_missing_game_lifetime(self):
        """Coherently changed reports still cannot replace the original Genshin lifetime."""
        self.assert_r68_retains(self.test_r66_rejects_coherently_changed_or_missing_game_lifetime)

    def test_r68_rejects_changed_root_stale_source_or_reused_destination(self):
        """The source and destination must retain distinct exact authenticated identities."""
        self.assert_r68_retains(self.test_r66_rejects_changed_root_stale_source_or_reused_destination)

    def test_r68_requires_explicit_idle_at_both_endpoints(self):
        """Missing, active and non-boolean ownership cannot qualify either owner."""
        self.assert_r68_retains(self.test_r66_requires_explicitly_released_root_and_child_at_both_endpoints)

    def test_r68_rejects_skipped_circular_or_rewritten_predecessors(self):
        """The one extra hop must still replay each exact original immutable report."""
        self.assert_r68_retains(self.test_r66_rejects_skipped_circular_or_rewritten_predecessors)

    def test_r68_clean_target_requires_fresh_english_defaults(self):
        """Only the same clean capture and English schema may enter the new child."""
        _,_,result,_=self.create_r68_successor();build,_=owner.target_package(68)
        config=Path(result['selectedPackage']['targetDirectory'])/'User/config.json'
        self.assertEqual(owner.check_clean_target(build),hashlib.sha256(config.read_bytes()).hexdigest())
        for changed in (owner.CLEAN_CAPTURE,dict(owner.R62_CLEAN_CAPTURE,extra=True),
                dict(owner.R62_CLEAN_CAPTURE,otherConfig={'uiCultureInfoName':'en','gameCultureInfoName':'zh-Hans'}),
                dict(owner.R62_CLEAN_CAPTURE,wgcV2ReadbackMode='nonblocking')):
            write(config,changed)
            with self.subTest(config=changed),self.assertRaisesRegex(ValueError,'Unexpected target capture settings'):
                owner.check_clean_target(build)

    def test_r68_source_and_target_witnesses_preserve_replay(self):
        """Removed complete runtimes retain identity evidence; damaged live or witness bytes still refuse."""
        prior,folder,result,_=self.create_r68_successor()
        self.check_source_and_target_witnesses(prior,folder,result,(67,68))

    def create_r69_successor(self):
        """Seal R68 and prepare exactly its next fresh English, explicitly released successor."""
        previous,folder,result,game=self.create_r68_successor()
        prior=folder/'map-owner-lineage.json'
        write(prior,owner.replacement(previous,folder))
        folder,result=self.create_next_handoff(prior,result,game,69)
        build,_=owner.target_package(69)
        write(Path(build['targetDirectory'])/'User/config.json',owner.R62_CLEAN_CAPTURE)
        digest=owner.check_clean_target(build)
        preflight=json.loads((folder/'preflight.json').read_bytes())
        preflight['targetConfigSha256']=digest
        result['replacementEvidence']['existingTargetConfigSha256']=digest
        write(folder/'preflight.json',preflight)
        write(folder/'ensure-child.json',result)
        return prior,folder,result,game

    def test_r69_replays_exact_original_root_and_game(self):
        """Historical R69 keeps its exact original root and game when R70 becomes supported."""
        prior,folder,result,game=self.create_r69_successor()
        receipt=owner.replacement(prior,folder);path=folder/'map-owner-lineage.json'
        write(path,receipt)
        self.assertEqual(owner.load_map_owner(path),dict(root=self.ids['root'],child=owner.identity(result['child'])))
        self.assertEqual(receipt['protectedGame'],game)
        self.assertEqual(receipt['priorLineageSha256'],hashlib.sha256(prior.read_bytes()).hexdigest())

    def assert_r69_retains(self,regression):
        """Replay an unchanged adversarial contract on the actual additional predecessor depth."""
        fixture=self.create_r69_successor()
        with patch.object(self,'create_r66_successor',return_value=fixture):regression()

    def test_r69_rejects_changed_or_missing_game_lifetime(self):
        """Coherently changed reports still cannot replace the original Genshin lifetime."""
        self.assert_r69_retains(self.test_r66_rejects_coherently_changed_or_missing_game_lifetime)

    def test_r69_rejects_changed_root_stale_source_or_reused_destination(self):
        """The source and destination must retain distinct exact authenticated identities."""
        self.assert_r69_retains(self.test_r66_rejects_changed_root_stale_source_or_reused_destination)

    def test_r69_requires_explicit_idle_at_both_endpoints(self):
        """Missing, active and non-boolean ownership cannot qualify either owner."""
        self.assert_r69_retains(self.test_r66_requires_explicitly_released_root_and_child_at_both_endpoints)

    def test_r69_rejects_skipped_circular_or_rewritten_predecessors(self):
        """The one extra hop must still replay each exact original immutable report."""
        self.assert_r69_retains(self.test_r66_rejects_skipped_circular_or_rewritten_predecessors)

    def test_r69_clean_target_requires_fresh_english_defaults(self):
        """Only the same clean capture and English schema may enter the new child."""
        _,_,result,_=self.create_r69_successor();build,_=owner.target_package(69)
        config=Path(result['selectedPackage']['targetDirectory'])/'User/config.json'
        self.assertEqual(owner.check_clean_target(build),hashlib.sha256(config.read_bytes()).hexdigest())
        for changed in (owner.CLEAN_CAPTURE,dict(owner.R62_CLEAN_CAPTURE,extra=True),
                dict(owner.R62_CLEAN_CAPTURE,otherConfig={'uiCultureInfoName':'en','gameCultureInfoName':'zh-Hans'}),
                dict(owner.R62_CLEAN_CAPTURE,wgcV2ReadbackMode='nonblocking')):
            write(config,changed)
            with self.subTest(config=changed),self.assertRaisesRegex(ValueError,'Unexpected target capture settings'):
                owner.check_clean_target(build)

    def test_r69_source_and_target_witnesses_preserve_replay(self):
        """Removed complete runtimes retain identity evidence; damaged live or witness bytes still refuse."""
        prior,folder,result,_=self.create_r69_successor()
        self.check_source_and_target_witnesses(prior,folder,result,(68,69))

    def create_r70_successor(self):
        """Seal R69 and prepare exactly its next fresh English, explicitly released successor."""
        previous,folder,result,game=self.create_r69_successor()
        prior=folder/'map-owner-lineage.json'
        write(prior,owner.replacement(previous,folder))
        folder,result=self.create_next_handoff(prior,result,game,70)
        build,_=owner.target_package(70)
        write(Path(build['targetDirectory'])/'User/config.json',owner.R62_CLEAN_CAPTURE)
        digest=owner.check_clean_target(build)
        preflight=json.loads((folder/'preflight.json').read_bytes())
        preflight['targetConfigSha256']=digest
        result['replacementEvidence']['existingTargetConfigSha256']=digest
        write(folder/'preflight.json',preflight)
        write(folder/'ensure-child.json',result)
        return prior,folder,result,game

    def test_r70_replays_exact_original_root_and_game(self):
        """Historical R70 keeps its exact original root and game when R71 becomes supported."""
        prior,folder,result,game=self.create_r70_successor()
        receipt=owner.replacement(prior,folder);path=folder/'map-owner-lineage.json'
        write(path,receipt)
        self.assertEqual(owner.load_map_owner(path),dict(root=self.ids['root'],child=owner.identity(result['child'])))
        self.assertEqual(receipt['protectedGame'],game)
        self.assertEqual(receipt['priorLineageSha256'],hashlib.sha256(prior.read_bytes()).hexdigest())

    def assert_r70_retains(self,regression):
        """Replay an unchanged adversarial contract on the actual additional predecessor depth."""
        fixture=self.create_r70_successor()
        with patch.object(self,'create_r66_successor',return_value=fixture):regression()

    def test_r70_rejects_changed_or_missing_game_lifetime(self):
        """Coherently changed reports still cannot replace the original Genshin lifetime."""
        self.assert_r70_retains(self.test_r66_rejects_coherently_changed_or_missing_game_lifetime)

    def test_r70_rejects_changed_root_stale_source_or_reused_destination(self):
        """The source and destination must retain distinct exact authenticated identities."""
        self.assert_r70_retains(self.test_r66_rejects_changed_root_stale_source_or_reused_destination)

    def test_r70_requires_explicit_idle_at_both_endpoints(self):
        """Missing, active and non-boolean ownership cannot qualify either owner."""
        self.assert_r70_retains(self.test_r66_requires_explicitly_released_root_and_child_at_both_endpoints)

    def test_r70_rejects_skipped_circular_or_rewritten_predecessors(self):
        """The one extra hop must still replay each exact original immutable report."""
        self.assert_r70_retains(self.test_r66_rejects_skipped_circular_or_rewritten_predecessors)

    def test_r70_clean_target_requires_fresh_english_defaults(self):
        """Only the same clean capture and English schema may enter the new child."""
        _,_,result,_=self.create_r70_successor();build,_=owner.target_package(70)
        config=Path(result['selectedPackage']['targetDirectory'])/'User/config.json'
        self.assertEqual(owner.check_clean_target(build),hashlib.sha256(config.read_bytes()).hexdigest())
        for changed in (owner.CLEAN_CAPTURE,dict(owner.R62_CLEAN_CAPTURE,extra=True),
                dict(owner.R62_CLEAN_CAPTURE,otherConfig={'uiCultureInfoName':'en','gameCultureInfoName':'zh-Hans'}),
                dict(owner.R62_CLEAN_CAPTURE,wgcV2ReadbackMode='nonblocking')):
            write(config,changed)
            with self.subTest(config=changed),self.assertRaisesRegex(ValueError,'Unexpected target capture settings'):
                owner.check_clean_target(build)

    def test_r70_source_and_target_witnesses_preserve_replay(self):
        """Removed complete runtimes retain identity evidence; damaged live or witness bytes still refuse."""
        prior,folder,result,_=self.create_r70_successor()
        self.check_source_and_target_witnesses(prior,folder,result,(69,70))

    def test_r60_handoff_keeps_the_same_game_and_rejects_stale_source(self):
        """The newly allowed successor still cannot reuse the discovery from before the R60 replacement."""
        prior,folder,result,game=self.create_r60_successor()
        receipt=owner.replacement(prior,folder)
        path=folder/'map-owner-lineage.json'
        write(path,receipt)
        self.assertEqual(owner.load_map_owner(path)['child'],owner.identity(result['child']))
        with self.assertRaises(ValueError):owner.preflight(path,folder/'before.json')
        result['protectedGame']=dict(game,startedFileTime=1)
        write(folder/'ensure-child.json',result)
        with self.assertRaisesRegex(ValueError,'game lifetime'):owner.load_map_owner(path)

    def test_r61_replays_original_root_and_game(self):
        """The historical R61 receipt retains the same original root and sealed game."""
        prior,folder,result,game=self.create_r61_successor()
        receipt=owner.replacement(prior,folder)
        path=folder/'map-owner-lineage.json'
        write(path,receipt)
        self.assertEqual(owner.load_map_owner(path),dict(root=self.ids['root'],child=owner.identity(result['child'])))
        self.assertEqual(receipt['protectedGame'],game)
        self.assertEqual(owner.load_map_owner(prior)['root'],self.ids['root'])
    def test_r62_replays_original_root_and_game(self):
        """The historical R62 receipt remains independently replayable after the next extension."""
        prior,folder,result,game=self.create_r62_successor()
        receipt=owner.replacement(prior,folder)
        path=folder/'map-owner-lineage.json'
        write(path,receipt)
        self.assertEqual(owner.load_map_owner(path),dict(root=self.ids['root'],child=owner.identity(result['child'])))
        self.assertEqual(receipt['protectedGame'],game)
        self.assertEqual(receipt['priorLineageSha256'],hashlib.sha256(prior.read_bytes()).hexdigest())
        self.assertEqual(owner.load_map_owner(prior)['root'],self.ids['root'])

    def test_r63_replays_original_root_and_game(self):
        """The historical R63 receipt remains independently replayable after the next extension."""
        prior,folder,result,game=self.create_r63_successor()
        receipt=owner.replacement(prior,folder)
        path=folder/'map-owner-lineage.json'
        write(path,receipt)
        self.assertEqual(owner.load_map_owner(path),dict(root=self.ids['root'],child=owner.identity(result['child'])))
        self.assertEqual(receipt['protectedGame'],game)
        self.assertEqual(receipt['priorLineageSha256'],hashlib.sha256(prior.read_bytes()).hexdigest())
    def test_r64_replays_original_root_and_game(self):
        """The historical R64 receipt remains independently replayable after the finite next extension."""
        prior,folder,result,game=self.create_r64_successor()
        receipt=owner.replacement(prior,folder)
        path=folder/'map-owner-lineage.json'
        write(path,receipt)
        self.assertEqual(owner.load_map_owner(path),dict(root=self.ids['root'],child=owner.identity(result['child'])))
        self.assertEqual(receipt['protectedGame'],game)
        self.assertEqual(receipt['priorLineageSha256'],hashlib.sha256(prior.read_bytes()).hexdigest())

    def test_r65_replays_original_root_and_game(self):
        """Historical R65 remains replayable without requiring new endpoint flags in old receipts."""
        prior,folder,result,game=self.create_r65_successor()
        receipt=owner.replacement(prior,folder);path=folder/'map-owner-lineage.json'
        write(path,receipt)
        self.assertEqual(owner.load_map_owner(path),dict(root=self.ids['root'],child=owner.identity(result['child'])))
        self.assertEqual(receipt['protectedGame'],game)
        self.assertEqual(receipt['priorLineageSha256'],hashlib.sha256(prior.read_bytes()).hexdigest())
        self.assertEqual(owner.load_map_owner(prior)['root'],self.ids['root'])

    def test_r66_replays_exact_original_root_and_game(self):
        """The historical R66 transition keeps its original exact root and game identity."""
        prior,folder,result,game=self.create_r66_successor()
        receipt=owner.replacement(prior,folder)
        path=folder/'map-owner-lineage.json'
        write(path,receipt)
        self.assertEqual(owner.load_map_owner(path),dict(root=self.ids['root'],child=owner.identity(result['child'])))
        self.assertEqual(receipt['protectedGame'],game)
        self.assertEqual(receipt['priorLineageSha256'],hashlib.sha256(prior.read_bytes()).hexdigest())
        self.assertEqual(owner.load_map_owner(prior)['root'],self.ids['root'])

    def test_r66_rejects_coherently_changed_or_missing_game_lifetime(self):
        """Fresh reports cannot replace the game already sealed by R65 and its original ancestors."""
        prior,folder,result,game=self.create_r66_successor()
        preflight=json.loads((folder/'preflight.json').read_bytes())
        for field,value in (('startedFileTime',1),('processId',888),('executable','YuanShen.exe'),('windowsSessionId',4)):
            changed=dict(game,**{field:value})
            write(folder/'game-before.json',changed)
            write(folder/'preflight.json',dict(preflight,protectedGame=changed))
            write(folder/'ensure-child.json',dict(result,protectedGame=changed))
            with self.subTest(field=field),self.assertRaises(ValueError):
                owner.replacement(prior,folder)
        write(folder/'game-before.json',game)
        write(folder/'preflight.json',preflight)
        write(folder/'ensure-child.json',dict(result,protectedGame=dict(game,startedFileTime=1)))
        with self.assertRaisesRegex(ValueError,'game lifetime'):owner.replacement(prior,folder)
        write(folder/'ensure-child.json',result)
        (folder/'game-before.json').unlink()
        with self.assertRaises(FileNotFoundError):owner.replacement(prior,folder)

    def test_r66_rejects_changed_root_stale_source_or_reused_destination(self):
        """A coherent new root, stale predecessor or reused child identity cannot inherit this handoff."""
        prior,folder,result,_=self.create_r66_successor()
        before=json.loads((folder/'before.json').read_bytes())
        preflight=json.loads((folder/'preflight.json').read_bytes())
        changed_before,changed_result,changed_preflight=deepcopy(before),deepcopy(result),deepcopy(preflight)
        for root in (changed_before['instances'][0],changed_result['root']):
            root.update(processId=10125,instanceNonce='e'*32)
        for child in (changed_before['instances'][1],changed_result['child']):
            child['rootProcessId']=10125
        changed_preflight['source']['root']=owner.identity(changed_result['root'])
        write(folder/'before.json',changed_before)
        write(folder/'preflight.json',changed_preflight)
        write(folder/'ensure-child.json',changed_result)
        with self.assertRaisesRegex(ValueError,'Original child occupant changed'):owner.replacement(prior,folder)
        write(folder/'preflight.json',preflight)
        write(folder/'ensure-child.json',result)
        for fields in (dict(processId=999),dict(instanceNonce='f'*32)):
            changed=deepcopy(before);changed['instances'][1].update(fields)
            write(folder/'before.json',changed)
            with self.subTest(source=fields),self.assertRaisesRegex(ValueError,'Original child occupant changed'):
                owner.replacement(prior,folder)
        write(folder/'before.json',before)
        old=before['instances'][1]
        for field in ('processId','instanceNonce'):
            changed=deepcopy(result)
            changed['child'][field]=old[field]
            evidence_key='replacementProcessId' if field=='processId' else 'replacementNonce'
            changed['replacementEvidence'][evidence_key]=old[field]
            write(folder/'ensure-child.json',changed)
            with self.subTest(destination=field),self.assertRaisesRegex(ValueError,'old and new authenticated owners'):
                owner.replacement(prior,folder)

    def test_r66_requires_explicitly_released_root_and_child_at_both_endpoints(self):
        """Busy, missing or non-boolean ownership flags cannot qualify either side of the new handoff."""
        prior,folder,result,game=self.create_r66_successor()
        before=json.loads((folder/'before.json').read_bytes())
        missing=object()
        for document,original in (('before.json',before),('ensure-child.json',result)):
            for role in ('root','child'):
                for field in ('taskRunning','agentStreamRunning','serviceOwnsPilot'):
                    for value in (True,missing):
                        changed=deepcopy(original)
                        status=changed['instances'][0 if role=='root' else 1] if document=='before.json' else changed[role]
                        if value is missing:status.pop(field)
                        else:status[field]=value
                        write(folder/document,changed)
                        with self.subTest(document=document,role=role,field=field,value=value):
                            with self.assertRaisesRegex(ValueError,'explicitly released'):
                                owner.replacement(prior,folder)
                write(folder/document,original)
        for role,field,value in (('root','serviceOwnsPilot',0),('child','taskRunning','false')):
            changed=deepcopy(result);changed[role][field]=value
            write(folder/'ensure-child.json',changed)
            with self.subTest(role=role,value=value),self.assertRaisesRegex(ValueError,'explicitly released'):
                owner.replacement(prior,folder)
        write(folder/'ensure-child.json',result)
        self.assertEqual(owner.replacement(prior,folder)['protectedGame'],game)

    def test_r66_rejects_skipped_circular_or_rewritten_predecessors(self):
        """The added depth remains finite and every immediate predecessor is independently replayed."""
        prior,folder,_,game=self.create_r66_successor()
        receipt=json.loads(prior.read_bytes())
        parent=Path(receipt['prior'])
        parent_receipt=json.loads(parent.read_bytes())
        write(prior,dict(receipt,prior=str(prior)))
        with self.assertRaisesRegex(ValueError,'bounded'):owner.replacement(prior,folder)
        write(prior,receipt)
        write(parent,dict(parent_receipt,prior=str(prior)))
        with self.assertRaisesRegex(ValueError,'bounded'):owner.replacement(prior,folder)
        write(parent,parent_receipt)
        write(prior,dict(receipt,prior=parent_receipt['prior']))
        with self.assertRaises(ValueError):owner.replacement(prior,folder)
        write(prior,receipt)
        with self.assertRaises(ValueError):owner.replacement(parent,folder)
        write(parent,dict(parent_receipt,buildSha256='f'*64))
        with self.assertRaisesRegex(ValueError,'lineage receipt'):owner.replacement(prior,folder)
        write(parent,parent_receipt)
        self.assertEqual(owner.replacement(prior,folder)['protectedGame'],game)

    def test_r66_clean_target_requires_only_fresh_english_and_capture_defaults(self):
        """R66 cannot carry old profile data or substitute language, source retention or readback settings."""
        _,_,result,_=self.create_r66_successor()
        build,_=owner.target_package(66)
        config=Path(result['selectedPackage']['targetDirectory'])/'User/config.json'
        self.assertEqual(owner.check_clean_target(build),hashlib.sha256(config.read_bytes()).hexdigest())
        cases=[owner.CLEAN_CAPTURE,dict(owner.R62_CLEAN_CAPTURE,extra=True),
            dict(owner.R62_CLEAN_CAPTURE,otherConfig={'uiCultureInfoName':'en'}),
            dict(owner.R62_CLEAN_CAPTURE,otherConfig={'uiCultureInfoName':'zh-CN','gameCultureInfoName':'en'}),
            dict(owner.R62_CLEAN_CAPTURE,otherConfig={'uiCultureInfoName':'en','gameCultureInfoName':'zh-Hans'})]
        for field,value in (('captureMode','BitBlt'),('wgcV2ReadbackMode','nonblocking'),
                ('wgcV2SourceRetention','release-before-readback'),('wgcV2UseCpuConvert',False)):
            cases.append(dict(owner.R62_CLEAN_CAPTURE,**{field:value}))
        for changed in cases:
            write(config,changed)
            with self.subTest(config=changed),self.assertRaisesRegex(ValueError,'Unexpected target capture settings'):
                owner.check_clean_target(build)

    def test_r66_source_and_target_witnesses_retain_exact_package_identity(self):
        """Retiring R65/R66 assets preserves replay but cannot hide changed live, partial or witness bytes."""
        prior,folder,result,_=self.create_r66_successor()
        self.check_source_and_target_witnesses(prior,folder,result,(65,66))

    def test_r65_rejects_changed_game_busy_owner_circular_or_substituted_parent(self):
        """Neither a matching new report nor the additional release can replace the original lifetime or source pins."""
        prior,folder,result,game=self.create_r65_successor()
        before=json.loads((folder/'before.json').read_bytes())
        original_receipt=json.loads(prior.read_bytes())
        for field,value in (('startedFileTime',1),('processId',888),('executable','YuanShen.exe')):
            write(folder/'game-before.json',dict(game,**{field:value}))
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'sealed R64 game lifetime'):
                owner.replacement(prior,folder)
        write(folder/'game-before.json',game)
        for mutation in (dict(serviceOwnsPilot=True),dict(taskRunning=True),dict(agentStreamRunning=True),
                         dict(instanceNonce='f'*32),dict(processId=999)):
            changed=deepcopy(before);changed['instances'][1].update(mutation)
            write(folder/'before.json',changed)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):owner.replacement(prior,folder)
        write(folder/'before.json',before)
        for mutation in (dict(prior=str(prior)),dict(buildSha256='f'*64),dict(priorLineageSha256='e'*64)):
            write(prior,dict(original_receipt,**mutation))
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):owner.replacement(prior,folder)
        write(prior,original_receipt)
        self.assertEqual(owner.replacement(prior,folder)['protectedGame'],game)

    def test_r65_clean_target_preserves_exact_english_capture_defaults(self):
        """The new package cannot import mutable old settings or change either English culture."""
        _,_,result,_=self.create_r65_successor();build,_=owner.target_package(65)
        config=Path(result['selectedPackage']['targetDirectory'])/'User/config.json'
        write(config,owner.R62_CLEAN_CAPTURE)
        self.assertEqual(owner.check_clean_target(build),hashlib.sha256(config.read_bytes()).hexdigest())
        for changed in (owner.CLEAN_CAPTURE,dict(owner.R62_CLEAN_CAPTURE,extra=True),
                        dict(owner.R62_CLEAN_CAPTURE,otherConfig=dict(uiCultureInfoName='en',gameCultureInfoName='zh-Hans'))):
            write(config,changed)
            with self.assertRaisesRegex(ValueError,'Unexpected target capture settings'):owner.check_clean_target(build)

    def test_r64_retains_the_sealed_game_and_rejects_busy_or_circular_predecessors(self):
        """The added transition cannot replace a different game, an active child or its own predecessor."""
        prior,folder,_,game=self.create_r64_successor()
        before=json.loads((folder/'before.json').read_bytes())
        for field,value in (('startedFileTime',1),('processId',888),('executable','YuanShen.exe')):
            write(folder/'game-before.json',dict(game,**{field:value}))
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'sealed R63 game lifetime'):
                owner.replacement(prior,folder)
        write(folder/'game-before.json',game)
        changed=deepcopy(before)
        changed['instances'][1]['serviceOwnsPilot']=True
        write(folder/'before.json',changed)
        with self.assertRaises(ValueError):owner.replacement(prior,folder)
        write(folder/'before.json',before)
        receipt=json.loads(prior.read_bytes())
        write(prior,dict(receipt,prior=str(prior)))
        with self.assertRaisesRegex(ValueError,'bounded'):owner.replacement(prior,folder)

    def test_r64_clean_target_preserves_exact_english_capture_defaults(self):
        """R64 accepts only the same public capture and fresh English settings as R62/R63."""
        _,_,result,_=self.create_r64_successor()
        build,_=owner.target_package(64)
        config=Path(result['selectedPackage']['targetDirectory'])/'User/config.json'
        write(config,owner.R62_CLEAN_CAPTURE)
        self.assertEqual(owner.check_clean_target(build),hashlib.sha256(config.read_bytes()).hexdigest())
        changed=deepcopy(owner.R62_CLEAN_CAPTURE)
        changed['otherConfig']['uiCultureInfoName']='zh-CN'
        write(config,changed)
        with self.assertRaisesRegex(ValueError,'Unexpected target capture settings'):owner.check_clean_target(build)

    def test_r63_rejects_substituted_game_and_stale_or_busy_owners(self):
        """Matching new evidence cannot substitute the protected game or reuse another controller owner."""
        prior,folder,result,game=self.create_r63_successor()
        preflight=json.loads((folder/'preflight.json').read_bytes())
        before=json.loads((folder/'before.json').read_bytes())
        for field,value in (('startedFileTime',1),('processId',888),('executable','YuanShen.exe')):
            changed=dict(game,**{field:value})
            write(folder/'game-before.json',changed)
            write(folder/'preflight.json',dict(preflight,protectedGame=changed))
            write(folder/'ensure-child.json',dict(result,protectedGame=changed))
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'sealed R62 game lifetime'):
                owner.replacement(prior,folder)
        write(folder/'game-before.json',game)
        write(folder/'preflight.json',preflight)
        write(folder/'ensure-child.json',result)
        for index,fields in ((0,dict(instanceNonce='e'*32)),(1,dict(processId=6000)),
                             (1,dict(instanceNonce='f'*32)),(1,dict(serviceOwnsPilot=True))):
            changed=deepcopy(before)
            changed['instances'][index].update(fields)
            write(folder/'before.json',changed)
            with self.subTest(index=index,fields=fields),self.assertRaises(ValueError):owner.replacement(prior,folder)

    def test_r63_rejects_circular_or_rewritten_predecessors(self):
        """The extra supported depth remains finite and independently validates the complete original chain."""
        prior,folder,_,_=self.create_r63_successor()
        receipt=json.loads(prior.read_bytes())
        parent=Path(receipt['prior'])
        parent_receipt=json.loads(parent.read_bytes())
        write(prior,dict(receipt,prior=str(prior)))
        with self.assertRaisesRegex(ValueError,'bounded'):owner.replacement(prior,folder)
        write(prior,receipt)
        write(parent,dict(parent_receipt,buildSha256='f'*64))
        with self.assertRaisesRegex(ValueError,'lineage receipt'):owner.replacement(prior,folder)

    def test_r63_faulted_source_requires_explicit_release_of_every_owner(self):
        """A retired script fault is compatible with replacement; any active or unknown owner still refuses."""
        prior,folder,result,_=self.create_r63_successor()
        before=json.loads((folder/'before.json').read_bytes())
        for child in (before['instances'][1],result['child']):
            child.update(pilotState='faulted',serviceOwnsPilot=False)
        write(folder/'before.json',before)
        write(folder/'ensure-child.json',result)
        self.assertEqual(owner.replacement(prior,folder)['identity']['child'],owner.identity(result['child']))
        missing=object()
        for document,original in (('before.json',before),('ensure-child.json',result)):
            for field in ('taskRunning','agentStreamRunning','serviceOwnsPilot'):
                for value in (missing,True,None,0,'false'):
                    changed=deepcopy(original)
                    child=changed['instances'][1] if document=='before.json' else changed['child']
                    if value is missing:child.pop(field)
                    else:child[field]=value
                    write(folder/document,changed)
                    with self.subTest(document=document,field=field,value=value),self.assertRaises((ValueError,KeyError)):
                        owner.replacement(prior,folder)
            write(folder/document,original)

    def test_r62_stopped_source_and_target_require_explicit_release(self):
        """Both ends may report stopped only with exact false task, stream and service ownership."""
        prior,folder,result,_=self.create_r62_successor()
        before=json.loads((folder/'before.json').read_bytes())
        for child in (before['instances'][1],result['child']):
            child.update(pilotState='stopped',serviceOwnsPilot=False)
        write(folder/'before.json',before)
        write(folder/'ensure-child.json',result)
        self.assertEqual(owner.replacement(prior,folder)['identity']['child'],owner.identity(result['child']))
        missing=object()
        for document,original in (('before.json',before),('ensure-child.json',result)):
            for field in ('taskRunning','agentStreamRunning','serviceOwnsPilot'):
                for value in (missing,True,None,0,'false'):
                    changed=deepcopy(original)
                    child=changed['instances'][1] if document=='before.json' else changed['child']
                    if value is missing:child.pop(field)
                    else:child[field]=value
                    write(folder/document,changed)
                    with self.subTest(document=document,field=field,value=value),self.assertRaises((ValueError,KeyError)):
                        owner.replacement(prior,folder)
            write(folder/document,original)

    def test_r62_rejects_changed_game_even_with_coherent_new_reports(self):
        """Agreement among fresh reports cannot replace the game sealed by R61 and its ancestors."""
        prior,folder,result,game=self.create_r62_successor()
        preflight=json.loads((folder/'preflight.json').read_bytes())
        for field,value in (('startedFileTime',1),('processId',888),('executable','YuanShen.exe')):
            changed=dict(game,**{field:value})
            write(folder/'game-before.json',changed)
            write(folder/'preflight.json',dict(preflight,protectedGame=changed))
            write(folder/'ensure-child.json',dict(result,protectedGame=changed))
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'sealed R61 game lifetime'):
                owner.replacement(prior,folder)
        write(folder/'game-before.json',game)
        write(folder/'preflight.json',preflight)
        write(folder/'ensure-child.json',dict(result,protectedGame=dict(game,startedFileTime=1)))
        with self.assertRaisesRegex(ValueError,'game lifetime'):owner.replacement(prior,folder)
        write(folder/'ensure-child.json',result)
        (folder/'game-before.json').unlink()
        with self.assertRaises(FileNotFoundError):owner.replacement(prior,folder)

    def test_r62_rejects_changed_root_or_stale_source_owner(self):
        """The next transition remains bound to the original root and exact immediate predecessor."""
        prior,folder,result,_=self.create_r62_successor()
        before=json.loads((folder/'before.json').read_bytes())
        for index,fields in ((0,dict(instanceNonce='e'*32)),(1,dict(processId=6000)),
                             (1,dict(instanceNonce='f'*32)),(1,dict(serviceOwnsPilot=True))):
            changed=deepcopy(before)
            changed['instances'][index].update(fields)
            write(folder/'before.json',changed)
            with self.subTest(index=index,fields=fields),self.assertRaises(ValueError):owner.replacement(prior,folder)
        write(folder/'before.json',before)
        changed=deepcopy(result)
        changed['root'].update(processId=10125,instanceNonce='e'*32)
        changed['child']['rootProcessId']=10125
        write(folder/'ensure-child.json',changed)
        with self.assertRaisesRegex(ValueError,'old and new authenticated owners'):owner.replacement(prior,folder)

    def test_r62_rejects_circular_skipped_or_rewritten_parent_lineage(self):
        """The added depth remains bounded and every original parent receipt is independently replayed."""
        prior,folder,_,_=self.create_r62_successor()
        receipt=json.loads(prior.read_bytes())
        parent=Path(receipt['prior'])
        parent_receipt=json.loads(parent.read_bytes())
        write(prior,dict(receipt,prior=str(prior)))
        with self.assertRaisesRegex(ValueError,'bounded'):owner.replacement(prior,folder)
        write(prior,receipt)
        write(parent,dict(parent_receipt,prior=str(prior)))
        with self.assertRaisesRegex(ValueError,'bounded'):owner.replacement(prior,folder)
        write(parent,parent_receipt)
        write(prior,dict(receipt,prior=parent_receipt['prior']))
        with self.assertRaises(ValueError):owner.replacement(prior,folder)
        write(prior,receipt)
        write(parent,dict(parent_receipt,buildSha256='f'*64))
        with self.assertRaisesRegex(ValueError,'lineage receipt'):owner.replacement(prior,folder)

    def test_r61_rejects_coherent_or_partial_game_replacement(self):
        """Matching new reports cannot substitute a different game for the one already sealed by R60."""
        prior,folder,result,game=self.create_r61_successor()
        preflight=json.loads((folder/'preflight.json').read_bytes())
        for field,value in (('startedFileTime',1),('processId',888),('executable','YuanShen.exe')):
            changed=dict(game,**{field:value})
            write(folder/'game-before.json',changed)
            write(folder/'preflight.json',dict(preflight,protectedGame=changed))
            write(folder/'ensure-child.json',dict(result,protectedGame=changed))
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'sealed R60 game lifetime'):
                owner.replacement(prior,folder)
        write(folder/'game-before.json',game)
        write(folder/'preflight.json',preflight)
        write(folder/'ensure-child.json',dict(result,protectedGame=dict(game,startedFileTime=1)))
        with self.assertRaisesRegex(ValueError,'game lifetime'):owner.replacement(prior,folder)
        write(folder/'ensure-child.json',result)
        (folder/'game-before.json').unlink()
        with self.assertRaises(FileNotFoundError):owner.replacement(prior,folder)

    def test_r61_rejects_coherent_root_replacement(self):
        """A replacement primary cannot inherit the original root's lineage even if its child agrees."""
        prior,folder,result,_=self.create_r61_successor()
        before=json.loads((folder/'before.json').read_bytes())
        for root in (before['instances'][0],result['root']):
            root.update(processId=10125,instanceNonce='e'*32)
        for child in (before['instances'][1],result['child']):
            child['rootProcessId']=10125
        write(folder/'before.json',before)
        write(folder/'ensure-child.json',result)
        with self.assertRaisesRegex(ValueError,'Original child occupant changed'):
            owner.replacement(prior,folder)

    def test_r61_rejects_circular_or_skipped_predecessors(self):
        """Bounded inspection must reject cycles before recursive replay and still validate every ancestor."""
        prior,folder,_,_=self.create_r61_successor()
        receipt=json.loads(prior.read_bytes())
        parent=Path(receipt['prior'])
        parent_receipt=json.loads(parent.read_bytes())
        write(prior,dict(receipt,prior=str(prior)))
        with self.assertRaisesRegex(ValueError,'bounded'):owner.replacement(prior,folder)
        write(prior,receipt)
        write(parent,dict(parent_receipt,prior=str(prior)))
        with self.assertRaisesRegex(ValueError,'bounded'):owner.replacement(prior,folder)
        write(parent,parent_receipt)
        write(prior,dict(receipt,prior=parent_receipt['prior']))
        with self.assertRaises(ValueError):owner.replacement(prior,folder)
        write(prior,receipt)
        write(parent,dict(parent_receipt,buildSha256='f'*64))
        with self.assertRaisesRegex(ValueError,'lineage receipt'):owner.replacement(prior,folder)

    def test_r61_source_and_target_witnesses_retain_exact_package_identity(self):
        """Retirement remains replayable without allowing changed live bytes, changed witnesses, or partial releases."""
        prior,folder,result,_=self.create_r61_successor()
        self.check_source_and_target_witnesses(prior,folder,result,(60,61))

    def test_r62_source_and_target_witnesses_retain_exact_package_identity(self):
        """The new handoff cannot hide a substituted R61 source or R62 target behind retained witnesses."""
        prior,folder,result,_=self.create_r62_successor()
        self.check_source_and_target_witnesses(prior,folder,result,(61,62))

    def check_source_and_target_witnesses(self,prior,folder,result,numbers):
        """Replay exact live and retained package bytes for each explicitly selected handoff endpoint."""
        path=folder/'map-owner-lineage.json'
        write(path,owner.replacement(prior,folder))
        witnesses={}
        for number in numbers:
            original=owner.ARTIFACTS/f'release-r{number}'
            dll=original/'BetterGI-English-win-x64/BetterGI.dll'
            data=dll.read_bytes()
            dll.write_bytes(b'changed-live-file')
            with self.subTest(live=number),self.assertRaisesRegex(ValueError,f'Changed R{number} binary'):
                owner.load_map_owner(path)
            dll.write_bytes(data)
            witnesses[number]=Path(owner.preserve_package_witness(number)['witnessDirectory'])
            retired=owner.ARTIFACTS/f'retired-fixture-r{number}'
            # Both directory moves remain within this test's private temporary artifact root.
            self.assertEqual(original.parent.resolve(),owner.ARTIFACTS.resolve())
            self.assertEqual(retired.parent.resolve(),owner.ARTIFACTS.resolve())
            original.rename(retired)
        self.assertEqual(owner.load_map_owner(path)['child'],owner.identity(result['child']))
        for number,witness in witnesses.items():
            dll=witness/'BetterGI-English-win-x64/BetterGI.dll'
            data=dll.read_bytes()
            dll.write_bytes(b'changed-witness')
            with self.subTest(witness=number),self.assertRaisesRegex(ValueError,f'Changed R{number} binary'):
                owner.load_map_owner(path)
            dll.write_bytes(data)
            original=owner.ARTIFACTS/f'release-r{number}'
            original.mkdir()
            with self.subTest(partial=number),self.assertRaises(FileNotFoundError):owner.load_map_owner(path)
            original.rmdir()

    def test_small_identity_witness_survives_retirement_but_never_hides_changed_live_bytes(self):
        witness=Path(owner.preserve_package_witness(58)['witnessDirectory'])
        original=owner.ARTIFACTS/'release-r58'
        retired=owner.ARTIFACTS/'retired-fixture-r58'
        # Both paths belong to this test's private temporary artifact root.
        self.assertEqual(original.parent.resolve(),owner.ARTIFACTS.resolve())
        self.assertEqual(retired.parent.resolve(),owner.ARTIFACTS.resolve())
        dll=self.target/'BetterGI.dll'
        prior=dll.read_bytes()
        dll.write_bytes(b'changed-live-file')
        with self.assertRaises(ValueError):owner.target_package(58)
        dll.write_bytes(prior)
        original.rename(retired)
        self.assertEqual(owner.target_package(58)[0],self.build)
        self.assertEqual(owner.replacement(self.prior,self.folder)['identity'],self.new_owner)
        (witness/'BetterGI-English-win-x64/BetterGI.dll').write_bytes(b'changed-witness')
        with self.assertRaises(ValueError):owner.target_package(58)

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

    def test_r62_and_r63_clean_targets_retain_exact_fresh_english_defaults(self):
        """Both releases preserve the published English settings and hash the original config bytes."""
        expected={**owner.CLEAN_CAPTURE,'otherConfig':{'uiCultureInfoName':'en','gameCultureInfoName':'en'}}
        self.assertEqual(owner.R62_CLEAN_CAPTURE,expected)
        for number in (62,63):
            target=owner.ARTIFACTS/f'release-r{number}/BetterGI-English-win-x64'
            path=target/'User/config.json'
            build=dict(self.build,targetDirectory=str(target))
            write(path,expected)
            with self.subTest(release=number):
                self.assertEqual(owner.check_clean_target(build),hashlib.sha256(path.read_bytes()).hexdigest())

    def test_r62_and_r63_reject_missing_extra_or_substituted_language_settings(self):
        """Capture-only defaults would reintroduce Chinese game text; unrelated copied profile data also fails."""
        cases=[owner.CLEAN_CAPTURE,dict(owner.R62_CLEAN_CAPTURE,unexpectedProfileData='refuse'),
               dict(owner.R62_CLEAN_CAPTURE,otherConfig=None)]
        for other in ({'uiCultureInfoName':'en'}, {'gameCultureInfoName':'en'},
                      {'uiCultureInfoName':'zh-Hans','gameCultureInfoName':'en'},
                      {'uiCultureInfoName':'en','gameCultureInfoName':'zh-Hans'},
                      {'uiCultureInfoName':'en','gameCultureInfoName':'en','unrelated':True}):
            cases.append(dict(owner.CLEAN_CAPTURE,otherConfig=other))
        for number in (62,63):
            target=owner.ARTIFACTS/f'release-r{number}/BetterGI-English-win-x64'
            path=target/'User/config.json'
            build=dict(self.build,targetDirectory=str(target))
            for config in cases:
                write(path,config)
                with self.subTest(release=number,config=config),self.assertRaisesRegex(ValueError,'Unexpected target capture settings'):
                    owner.check_clean_target(build)

    def test_older_clean_target_contract_does_not_gain_r62_settings(self):
        """Each previously supported release keeps its original four-field configuration contract."""
        for number in (58,59,60,61):
            target=owner.ARTIFACTS/f'release-r{number}/BetterGI-English-win-x64'
            path=target/'User/config.json'
            build=dict(self.build,targetDirectory=str(target))
            write(path,owner.CLEAN_CAPTURE)
            self.assertEqual(owner.check_clean_target(build),hashlib.sha256(path.read_bytes()).hexdigest())
            write(path,owner.R62_CLEAN_CAPTURE)
            with self.subTest(release=number),self.assertRaisesRegex(ValueError,'Unexpected target capture settings'):
                owner.check_clean_target(build)


    def create_r71_successor(self):
        """Seal R70 and prepare exactly its next fresh English, explicitly released successor."""
        previous,folder,result,game=self.create_r70_successor()
        prior=folder/'map-owner-lineage.json'
        write(prior,owner.replacement(previous,folder))
        folder,result=self.create_next_handoff(prior,result,game,71)
        build,_=owner.target_package(71)
        write(Path(build['targetDirectory'])/'User/config.json',owner.R62_CLEAN_CAPTURE)
        digest=owner.check_clean_target(build)
        preflight=json.loads((folder/'preflight.json').read_bytes())
        preflight['targetConfigSha256']=digest
        result['replacementEvidence']['existingTargetConfigSha256']=digest
        write(folder/'preflight.json',preflight)
        write(folder/'ensure-child.json',result)
        return prior,folder,result,game


    def assert_r71_retains(self,regression):
        """Replay an unchanged adversarial contract on the actual additional predecessor depth."""
        fixture=self.create_r71_successor()
        with patch.object(self,'create_r66_successor',return_value=fixture):regression()


    def test_r71_replays_exact_original_root_and_game(self):
        """Historical R71 retains the exact original root and game when R72 becomes supported."""
        prior,folder,result,game=self.create_r71_successor()
        receipt=owner.replacement(prior,folder);path=folder/'map-owner-lineage.json'
        write(path,receipt)
        self.assertEqual(owner.load_map_owner(path),dict(root=self.ids['root'],child=owner.identity(result['child'])))
        self.assertEqual(receipt['protectedGame'],game)
        self.assertEqual(receipt['priorLineageSha256'],hashlib.sha256(prior.read_bytes()).hexdigest())


    def test_r71_rejects_changed_or_missing_game_lifetime(self):
        """Coherently changed reports still cannot replace the original Genshin lifetime."""
        self.assert_r71_retains(self.test_r66_rejects_coherently_changed_or_missing_game_lifetime)


    def test_r71_rejects_changed_root_stale_source_or_reused_destination(self):
        """The source and destination must retain distinct exact authenticated identities."""
        self.assert_r71_retains(self.test_r66_rejects_changed_root_stale_source_or_reused_destination)


    def test_r71_requires_explicit_idle_at_both_endpoints(self):
        """Missing, active and non-boolean ownership cannot qualify either owner."""
        self.assert_r71_retains(self.test_r66_requires_explicitly_released_root_and_child_at_both_endpoints)


    def test_r71_rejects_skipped_circular_or_rewritten_predecessors(self):
        """The one extra hop must still replay each exact original immutable report."""
        self.assert_r71_retains(self.test_r66_rejects_skipped_circular_or_rewritten_predecessors)


    def test_r71_clean_target_requires_fresh_english_defaults(self):
        """Only the same clean capture and English schema may enter the new child."""
        _,_,result,_=self.create_r71_successor();build,_=owner.target_package(71)
        config=Path(result['selectedPackage']['targetDirectory'])/'User/config.json'
        self.assertEqual(owner.check_clean_target(build),hashlib.sha256(config.read_bytes()).hexdigest())
        for changed in (owner.CLEAN_CAPTURE,dict(owner.R62_CLEAN_CAPTURE,extra=True),
                dict(owner.R62_CLEAN_CAPTURE,otherConfig={'uiCultureInfoName':'en','gameCultureInfoName':'zh-Hans'}),
                dict(owner.R62_CLEAN_CAPTURE,wgcV2ReadbackMode='nonblocking')):
            write(config,changed)
            with self.subTest(config=changed),self.assertRaisesRegex(ValueError,'Unexpected target capture settings'):
                owner.check_clean_target(build)


    def test_r71_source_and_target_witnesses_preserve_replay(self):
        """Removed complete runtimes retain identity evidence; damaged live or witness bytes still refuse."""
        prior,folder,result,_=self.create_r71_successor()
        self.check_source_and_target_witnesses(prior,folder,result,(70,71))


    def create_r72_successor(self):
        """Seal R71 and prepare exactly its next fresh English, explicitly released successor."""
        previous,folder,result,game=self.create_r71_successor()
        prior=folder/'map-owner-lineage.json'
        write(prior,owner.replacement(previous,folder))
        folder,result=self.create_next_handoff(prior,result,game,72)
        build,_=owner.target_package(72)
        write(Path(build['targetDirectory'])/'User/config.json',owner.R62_CLEAN_CAPTURE)
        digest=owner.check_clean_target(build)
        preflight=json.loads((folder/'preflight.json').read_bytes())
        preflight['targetConfigSha256']=digest
        result['replacementEvidence']['existingTargetConfigSha256']=digest
        write(folder/'preflight.json',preflight)
        write(folder/'ensure-child.json',result)
        return prior,folder,result,game


    def assert_r72_retains(self,regression):
        """Replay an unchanged adversarial contract on the actual additional predecessor depth."""
        fixture=self.create_r72_successor()
        with patch.object(self,'create_r66_successor',return_value=fixture):regression()


    def test_r72_replays_exact_original_root_and_game(self):
        """Historical R72 retains the exact original root and game when R73 becomes supported."""
        prior,folder,result,game=self.create_r72_successor()
        receipt=owner.replacement(prior,folder);path=folder/'map-owner-lineage.json'
        write(path,receipt)
        self.assertEqual(owner.load_map_owner(path),dict(root=self.ids['root'],child=owner.identity(result['child'])))
        self.assertEqual(receipt['protectedGame'],game)
        self.assertEqual(receipt['priorLineageSha256'],hashlib.sha256(prior.read_bytes()).hexdigest())


    def test_r72_rejects_changed_or_missing_game_lifetime(self):
        """Coherently changed reports still cannot replace the original Genshin lifetime."""
        self.assert_r72_retains(self.test_r66_rejects_coherently_changed_or_missing_game_lifetime)


    def test_r72_rejects_changed_root_stale_source_or_reused_destination(self):
        """The source and destination must retain distinct exact authenticated identities."""
        self.assert_r72_retains(self.test_r66_rejects_changed_root_stale_source_or_reused_destination)


    def test_r72_requires_explicit_idle_at_both_endpoints(self):
        """Missing, active and non-boolean ownership cannot qualify either owner."""
        self.assert_r72_retains(self.test_r66_requires_explicitly_released_root_and_child_at_both_endpoints)


    def test_r72_rejects_skipped_circular_or_rewritten_predecessors(self):
        """The one extra hop must still replay each exact original immutable report."""
        self.assert_r72_retains(self.test_r66_rejects_skipped_circular_or_rewritten_predecessors)


    def test_r72_clean_target_requires_fresh_english_defaults(self):
        """Only the same clean capture and English schema may enter the new child."""
        _,_,result,_=self.create_r72_successor();build,_=owner.target_package(72)
        config=Path(result['selectedPackage']['targetDirectory'])/'User/config.json'
        self.assertEqual(owner.check_clean_target(build),hashlib.sha256(config.read_bytes()).hexdigest())
        for changed in (owner.CLEAN_CAPTURE,dict(owner.R62_CLEAN_CAPTURE,extra=True),
                dict(owner.R62_CLEAN_CAPTURE,otherConfig={'uiCultureInfoName':'en','gameCultureInfoName':'zh-Hans'}),
                dict(owner.R62_CLEAN_CAPTURE,wgcV2ReadbackMode='nonblocking')):
            write(config,changed)
            with self.subTest(config=changed),self.assertRaisesRegex(ValueError,'Unexpected target capture settings'):
                owner.check_clean_target(build)


    def test_r72_source_and_target_witnesses_preserve_replay(self):
        """Removed complete runtimes retain identity evidence; damaged live or witness bytes still refuse."""
        prior,folder,result,_=self.create_r72_successor()
        self.check_source_and_target_witnesses(prior,folder,result,(71,72))


    def create_r73_successor(self):
        """Seal R72 and prepare exactly its next fresh English, explicitly released successor."""
        previous,folder,result,game=self.create_r72_successor()
        prior=folder/'map-owner-lineage.json'
        write(prior,owner.replacement(previous,folder))
        folder,result=self.create_next_handoff(prior,result,game,73)
        result['child'].update(configuredTriggerPolicyVersion=1, configuredTriggersSuppressed=True)
        build,_=owner.target_package(73)
        write(Path(build['targetDirectory'])/'User/config.json',owner.R62_CLEAN_CAPTURE)
        digest=owner.check_clean_target(build)
        preflight=json.loads((folder/'preflight.json').read_bytes())
        preflight['targetConfigSha256']=digest
        result['replacementEvidence']['existingTargetConfigSha256']=digest
        write(folder/'preflight.json',preflight)
        write(folder/'ensure-child.json',result)
        return prior,folder,result,game


    def test_r73_requires_exact_child_configured_trigger_policy(self):
        """An idle child needs its own typed startup-policy proof; a root claim cannot substitute."""
        prior,folder,result,_=self.create_r73_successor()
        build,_=owner.target_package(73)
        package=Path(build['targetDirectory']).resolve()
        original=deepcopy(result['child'])
        mutations=[{}, {'configuredTriggerPolicyVersion':1}, {'configuredTriggersSuppressed':True},
                   {'configuredTriggerPolicyVersion':1,'configuredTriggersSuppressed':False},
                   {'configuredTriggerPolicyVersion':True,'configuredTriggersSuppressed':True},
                   {'configuredTriggerPolicyVersion':1.0,'configuredTriggersSuppressed':True},
                   {'configuredTriggerPolicyVersion':2,'configuredTriggersSuppressed':True},
                   {'configuredTriggerPolicyVersion':1,'configuredTriggersSuppressed':1},
                   {'configuredTriggerPolicyVersion':1,'configuredTriggersSuppressed':'true'}]
        for fields in mutations:
            child={k:v for k,v in original.items() if k not in ('configuredTriggerPolicyVersion','configuredTriggersSuppressed')}
            child.update(fields)
            root=dict(result['root'],configuredTriggerPolicyVersion=1,configuredTriggersSuppressed=True)
            with self.subTest(fields=fields),self.assertRaisesRegex(ValueError,'configured automatic triggers'):
                owner.checked_pair(root,child,package,build['dllSha256'],strict_release=True)
        # The sealed replacement path must enforce the same policy, not merely the direct helper.
        result['child']['configuredTriggersSuppressed']=False
        write(folder/'ensure-child.json',result)
        with self.assertRaisesRegex(ValueError,'configured automatic triggers'):
            owner.replacement(prior,folder)

    def test_r73_trigger_policy_survives_explicitly_retired_child_states(self):
        """The policy is required after completed/faulted/stopped ownership release as well as idle."""
        _,_,result,_=self.create_r73_successor()
        build,_=owner.target_package(73);package=Path(build['targetDirectory']).resolve()
        for state in ('idle','completed','faulted','stopped'):
            child=dict(result['child'],pilotState=state,serviceOwnsPilot=False)
            with self.subTest(state=state):
                self.assertEqual(owner.checked_pair(result['root'],child,package,build['dllSha256'],strict_release=True)['child'],owner.identity(child))
                child['configuredTriggersSuppressed']=False
                with self.assertRaisesRegex(ValueError,'configured automatic triggers'):
                    owner.checked_pair(result['root'],child,package,build['dllSha256'],strict_release=True)

    def test_r72_historical_status_needs_no_new_trigger_fields(self):
        """The R73 policy neither backfills nor rejects the historical R72 endpoint."""
        prior,folder,result,game=self.create_r72_successor()
        self.assertNotIn('configuredTriggerPolicyVersion',result['child'])
        self.assertNotIn('configuredTriggersSuppressed',result['child'])
        receipt=owner.replacement(prior,folder)
        self.assertEqual(receipt['protectedGame'],game)
        self.assertEqual(receipt['identity']['child'],owner.identity(result['child']))


    def assert_r73_retains(self,regression):
        """Replay an unchanged adversarial contract on the actual additional predecessor depth."""
        fixture=self.create_r73_successor()
        with patch.object(self,'create_r66_successor',return_value=fixture):regression()


    def test_r73_replays_exact_original_root_and_game_but_rejects_r74(self):
        """Only one new finite handoff is permitted, even with a fabricated later package present."""
        prior,folder,result,game=self.create_r73_successor()
        receipt=owner.replacement(prior,folder);path=folder/'map-owner-lineage.json'
        write(path,receipt)
        self.assertEqual(owner.load_map_owner(path),dict(root=self.ids['root'],child=owner.identity(result['child'])))
        self.assertEqual(receipt['protectedGame'],game)
        self.assertEqual(receipt['priorLineageSha256'],hashlib.sha256(prior.read_bytes()).hexdigest())
        later,_=self.create_next_handoff(path,result,game,74)
        with self.assertRaisesRegex(ValueError,'bounded'):owner.replacement(path,later)
        with self.assertRaisesRegex(ValueError,'Unsupported map release'):owner.target_package(74)


    def test_r73_rejects_changed_or_missing_game_lifetime(self):
        """Coherently changed reports still cannot replace the original Genshin lifetime."""
        self.assert_r73_retains(self.test_r66_rejects_coherently_changed_or_missing_game_lifetime)


    def test_r73_rejects_changed_root_stale_source_or_reused_destination(self):
        """The source and destination must retain distinct exact authenticated identities."""
        self.assert_r73_retains(self.test_r66_rejects_changed_root_stale_source_or_reused_destination)


    def test_r73_requires_explicit_idle_at_both_endpoints(self):
        """Missing, active and non-boolean ownership cannot qualify either owner."""
        self.assert_r73_retains(self.test_r66_requires_explicitly_released_root_and_child_at_both_endpoints)


    def test_r73_rejects_skipped_circular_or_rewritten_predecessors(self):
        """The one extra hop must still replay each exact original immutable report."""
        self.assert_r73_retains(self.test_r66_rejects_skipped_circular_or_rewritten_predecessors)


    def test_r73_clean_target_requires_fresh_english_defaults(self):
        """Only the same clean capture and English schema may enter the new child."""
        _,_,result,_=self.create_r73_successor();build,_=owner.target_package(73)
        config=Path(result['selectedPackage']['targetDirectory'])/'User/config.json'
        self.assertEqual(owner.check_clean_target(build),hashlib.sha256(config.read_bytes()).hexdigest())
        for changed in (owner.CLEAN_CAPTURE,dict(owner.R62_CLEAN_CAPTURE,extra=True),
                dict(owner.R62_CLEAN_CAPTURE,otherConfig={'uiCultureInfoName':'en','gameCultureInfoName':'zh-Hans'}),
                dict(owner.R62_CLEAN_CAPTURE,wgcV2ReadbackMode='nonblocking')):
            write(config,changed)
            with self.subTest(config=changed),self.assertRaisesRegex(ValueError,'Unexpected target capture settings'):
                owner.check_clean_target(build)


    def test_r73_source_and_target_witnesses_preserve_replay(self):
        """Removed complete runtimes retain identity evidence; damaged live or witness bytes still refuse."""
        prior,folder,result,_=self.create_r73_successor()
        self.check_source_and_target_witnesses(prior,folder,result,(72,73))





class PilotRetirementTest(unittest.TestCase):
    """Pure post-stop evidence checks; no process, pipe, native input, or mutable live file is accessed."""
    def setUp(self):
        self.ids = dict(root=dict(processId=10124, windowsSessionId=1, instanceNonce='a'*32),
                        child=dict(processId=25656, windowsSessionId=3, instanceNonce='b'*32))
        flags = dict(taskRunning=False, agentStreamRunning=False, serviceOwnsPilot=False)
        self.root = dict(self.ids['root'], **flags, childWindowMinimized=True, childConnectedState=1, childSessionId=3)
        self.child = dict(self.ids['child'], **flags, rootProcessId=10124, scriptSession='owned-session',
                          heartbeatFresh=True, pilotState='faulted')

    def ready(self, acknowledged=True):
        return owner.pilot_retirement_ready(self.root, self.child, self.ids, 'owned-session',
                                            stop_acknowledged=acknowledged)

    def test_exact_released_faulted_owner_is_ready_without_claiming_delivery(self):
        self.assertTrue(self.ready());self.assertTrue(self.ready(False))

    def test_known_owned_task_still_running_is_pending(self):
        for service, task in ((True,True),(True,False),(False,True)):
            self.child.update(serviceOwnsPilot=service,taskRunning=task)
            with self.subTest(service=service,task=task):self.assertFalse(self.ready())

    def test_missing_heartbeat_only_pending_after_ack_and_never_proves_release(self):
        self.child.update(scriptSession=None,heartbeatFresh=False)
        self.assertFalse(self.ready())
        with self.assertRaisesRegex(ValueError,'without acknowledged stop'):self.ready(False)
        self.child['heartbeatFresh']=True
        with self.assertRaisesRegex(ValueError,'without acknowledged stop'):self.ready()

    def test_nonempty_foreign_session_immediately_rejects_even_when_released(self):
        for value in ('foreign-session','',123,{'unexpected':'value'}):
            self.child['scriptSession']=value
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'Another pilot'):self.ready()

    def test_changed_owner_or_parent_or_minimization_rejects(self):
        changes=(('root','instanceNonce','c'*32),('child','processId',99),('child','windowsSessionId',4),
                 ('child','rootProcessId',99),('root','childWindowMinimized',False),
                 ('root','childConnectedState',0),('root','childSessionId',4))
        for role,key,value in changes:
            before=deepcopy(getattr(self,role));getattr(self,role)[key]=value
            with self.subTest(role=role,key=key),self.assertRaises(ValueError):self.ready()
            setattr(self,role,before)

    def test_missing_true_or_non_boolean_task_flags_cannot_prove_idle(self):
        for role,key,value in (('root','taskRunning',True),('root','serviceOwnsPilot',None),
                               ('root','agentStreamRunning',True),('child','agentStreamRunning',True),
                               ('child','serviceOwnsPilot',None),('child','taskRunning',0)):
            before=deepcopy(getattr(self,role));getattr(self,role)[key]=value
            with self.subTest(role=role,key=key),self.assertRaises(ValueError):self.ready()
            setattr(self,role,before)

    def test_invalid_ack_or_absent_owned_session_rejects(self):
        for acknowledged,session in ((None,'owned-session'),(1,'owned-session'),(True,None),(True,'')):
            with self.subTest(ack=acknowledged,session=session),self.assertRaises(ValueError):
                owner.pilot_retirement_ready(self.root,self.child,self.ids,session,stop_acknowledged=acknowledged)

    def test_bounded_snapshot_preserves_first_latest_and_rejecting_values(self):
        report={}
        for i in range(70):
            self.child['scriptSession']='foreign' if i==69 else 'owned-session'
            owner.retain_pilot_identity_snapshot(report,self.root,self.child,'post-stop',i)
        rows=report['pilotIdentityChecks']
        self.assertEqual((len(rows),rows[0]['checkedAtUnixNs'],rows[-1]['checkedAtUnixNs']),(64,0,69))
        self.assertEqual(report['pilotIdentityChecksOmitted'],6)
        with self.assertRaisesRegex(ValueError,'Another pilot'):self.ready()
        self.assertEqual(rows[-1]['child']['scriptSession'],'foreign')

    def test_snapshot_is_detached_even_for_malformed_mutable_field(self):
        report={};self.child['scriptSession']={'unexpected':['retained']}
        owner.retain_pilot_identity_snapshot(report,self.root,self.child,'post-stop',1)
        self.child['scriptSession']['unexpected'].clear()
        self.assertEqual(report['pilotIdentityChecks'][0]['child']['scriptSession'],{'unexpected':['retained']})
