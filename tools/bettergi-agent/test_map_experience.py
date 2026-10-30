"""Keep native UI pulses distinct, completely qualified, and tied to their original source images."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from map_experience import collect_map_experience,map_pulse_rows


class MapExperienceTests(unittest.TestCase):
    """Mock only the existing full map auditor; exercise actual source joins and mutation detection."""
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo=Path(temp.name).resolve()
        self.folder=self.repo/'artifacts/live/episode'
        self.directory=self.folder/'map-inspection'
        self.directory.mkdir(parents=True)
        self.owner=self.repo/'artifacts/live/map-owner-lineage.json'
        self.owner.write_bytes(b'{}')
        self.warm=dict(status='completed',mapInspectionVerified=True)
        self.write('warm-launcher.json',self.warm)
        self.write('map-required-owner.json',{})
        self.write('map-owner-source.json',dict(path=str(self.owner),sha256=hashlib.sha256(b'{}').hexdigest()))
        self.proof=dict(passed=True,requestId='operation',runId='run')
        self.write('map-audit.json',self.proof)
        frames=[]
        for number in (7,19):
            raw=f'original-png-{number}'.encode()
            (self.directory/f'native-{number}.png').write_bytes(raw)
            frames.append(dict(frameId=number,width=1920,height=1080,sha256=hashlib.sha256(raw).hexdigest()))
        pulses=[dict(action=action,key=key,frameId=frame['frameId'],requestedTicks=100,releasedTicks=160,outcome='released')
            for frame,action,key in zip(frames,('openMap','closeMap'),('M','ESCAPE'))]
        self.tx=dict(mode='inspection',status='returnedToJunction',runId='run',requestId='operation',
            inspection=dict(requestId='operation',inputs=pulses,before=[frames[0]],map=[frames[1]],originTicks=0,frequency=1000,
                sessionId='lease',ownerEpoch='owner'))
        self.write('map-inspection/transaction.json',self.tx)
        auditor=patch('audit_map_inspection.audit_map',return_value=self.proof)
        self.audit=auditor.start()
        self.addCleanup(auditor.stop)

    def write(self,name,value):
        """Write only this inert fixture's JSON."""
        (self.folder/name).write_text(json.dumps(value),encoding='utf-8')

    def collect(self):
        """Use fixed inert observer arguments without contacting any native endpoint."""
        return collect_map_experience(self.folder,self.repo,(self.repo/'model.json',self.repo/'qualified.json'))

    def test_two_real_pulses_keep_the_operation_id_and_distinct_original_pngs(self):
        result=self.collect()
        self.assertTrue(result['passed'])
        self.assertEqual([row['action']['key'] for row in result['actions']],['M','ESCAPE'])
        self.assertEqual([row['pulseOrdinal'] for row in result['actions']],[1,2])
        for row in result['actions']:
            self.assertEqual(row['nativeOperationId'],'operation')
            self.assertNotIn('requestId',row)
            self.assertEqual(row['actor'],'native-ui-controller')
            self.assertFalse(row['humanExpertDemonstration'])
            self.assertFalse(row['physicalExecutionProven'])
            self.assertEqual(row['sourceFrame']['frameId'],row['action']['frameId'])
        self.assertEqual(len(result['sourceFiles']),7)

    def test_mismatched_source_key_or_terminal_outcome_is_rejected(self):
        for change in ({'frameId':8},{'key':'W'},{'outcome':'pending'},{'releasedTicks':99}):
            with self.subTest(change=change):
                tx=copy.deepcopy(self.tx)
                tx['inspection']['inputs'][0].update(change)
                with self.assertRaisesRegex(ValueError,'source or terminal'):
                    map_pulse_rows(tx,self.directory,self.repo)

    def test_changed_original_png_is_rejected(self):
        (self.directory/'native-7.png').write_bytes(b'different pixels')
        with self.assertRaisesRegex(ValueError,'source PNG changed'):self.collect()

    def test_missing_or_changed_owner_binding_is_rejected_before_replay(self):
        self.owner.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'owner source changed'):self.collect()
        self.audit.assert_not_called()
        (self.folder/'map-owner-source.json').unlink()
        with self.assertRaisesRegex(ValueError,'owner-source binding'):self.collect()

    def test_changed_evidence_during_replay_is_rejected(self):
        def change(*args):
            self.write('map-required-owner.json',{'changed':True})
            return self.proof
        self.audit.side_effect=change
        with self.assertRaisesRegex(ValueError,'evidence changed during'):self.collect()

    def test_unfinished_recovery_or_different_independent_audit_cannot_be_exported(self):
        self.write('warm-launcher.json',dict(self.warm,mapRecoveryVerified=True))
        with self.assertRaisesRegex(ValueError,'completed inspection'):self.collect()
        self.write('warm-launcher.json',self.warm)
        self.audit.return_value=dict(self.proof,passed=False)
        with self.assertRaisesRegex(ValueError,'Independent map replay'):self.collect()

    def test_plain_walking_episode_has_no_ui_transition(self):
        plain=self.repo/'artifacts/live/plain'
        plain.mkdir()
        (plain/'warm-launcher.json').write_text(json.dumps(dict(status='completed')))
        self.assertIsNone(collect_map_experience(plain,self.repo,(None,None)))
        self.audit.assert_not_called()
