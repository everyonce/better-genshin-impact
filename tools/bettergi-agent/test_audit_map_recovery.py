"""Replay bounded recovery evidence without starting the game, bridge or model."""
import copy
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

import audit_map_recovery as recover
from test_audit_map_inspection import fixture,tick


SHA='e'*64
REPO=Path(__file__).resolve().parents[2]
SEALED=REPO/'artifacts/live/2026-10-29-map-inspection'
FAILURE=SEALED/'live/warm-20261029T180711Z-9e347a5c89dc'
PASSIVE=SEALED/'r58-after-attempt'
OWNER=SEALED/'lineage/map-owner-lineage.json'


def single_fixture():
    """Initialize an explicit release and one synthetic Escape, with no hidden prior or normal actions."""
    n,h=fixture()
    h['mapInspection'].update(recoveryVersion=1,inputChannel='original-game-hwnd',wgcOnly=True,gameProcessId=22,gameWindowHandle=31)
    n.update(gameProcessId=22,gameWindowHandle=31,priorEvidenceSha256=SHA,mode='recovery',before=[],inputs=n['inputs'][1:])
    events=n['finalExecutionContext']['events']
    initial=copy.deepcopy(events[4:6])
    for i,e in enumerate(initial,1):
        e.update(sequence=i,atMs=i+1)
    n['initialExecutionContext'].update(events=initial,lastSequence=2,lastInputEvent=initial[-1])
    remaining=events[6:]
    for i,e in enumerate(remaining,3):
        e['sequence']=i
    n['finalExecutionContext'].update(events=initial+remaining,lastSequence=2+len(remaining),lastInputEvent=remaining[-1])
    return n,h


class RecoveryEvidenceTests(unittest.TestCase):
    def test_correct_recovery_uses_no_open_input(self):
        n,h=single_fixture()
        self.assertEqual(len(recover.validate_native_recovery(n,h,SHA)),5)
        recover.verify_return_position(n['returned'][0]['navigationPose'],n['returned'])

    def test_substitutions_missing_authority_and_early_or_extra_calls_are_rejected(self):
        cases=[
            ('wrong prior',lambda n,h:n.update(priorEvidenceSha256='c'*64)),
            ('wrong mode',lambda n,h:n.update(mode='inspection')),
            ('wrong HWND',lambda n,h:n.update(gameWindowHandle=30)),
            ('wrong process',lambda n,h:h['mapInspection'].update(gameProcessId=33)),
            ('disconnected lease',lambda n,h:n.update(ownerEpoch='different')),
            ('stop',lambda n,h:n.update(phase='failed')),
            ('no map',lambda n,h:n['map'].clear()),
            ('single map',lambda n,h:n['map'].pop()),
            ('crossed epoch',lambda n,h:n['map'][0].update(captureEpoch='restarted')),
            ('bad map',lambda n,h:n['map'][1].update(knownMap=False)),
            ('added source',lambda n,h:n['before'].append(n['map'][0])),
            ('missing release',lambda n,h:n['inputs'][0].update(outcome='timeout')),
            ('M rather than escape',lambda n,h:n['inputs'][0].update(action='openMap',key='M')),
            ('second press',lambda n,h:n['inputs'].append(n['inputs'][0])),
            ('wrong trigger',lambda n,h:n['inputs'][0].update(frameId=100)),
            ('stale source',lambda n,h:n['inputs'][0].update(requestedTicks=tick(666),releasedTicks=tick(721))),
            ('stale HUD',lambda n,h:n['returned'][0]['worldReadiness'].update(ready=False)),
            ('early HUD',lambda n,h:n['inputs'][0].update(releasedTicks=tick(605))),
            ('foreign event',lambda n,h:n['finalExecutionContext']['events'][3].update(origin='dispatch')),
            ('earlier hidden input',lambda n,h:n['initialExecutionContext']['events'][0]['call'].update(operation='keyDown')),
            ('ordinary proposal',lambda n,h:n.update(ordinaryRequestsWhileFenced=1)),
            ('pending movement',lambda n,h:n.update(pendingActions=1)),
            ('missing terminal release',lambda n,h:n['finalExecutionContext']['trackedState'].update(heldKeys=['W'])),
            ('late terminal',lambda n,h:n.update(finalReleaseAtMs=12_100)),
        ]
        for label,change in cases:
            with self.subTest(label):
                n,h=single_fixture()
                change(n,h)
                with self.assertRaises(ValueError): recover.validate_native_recovery(n,h,SHA)

    def test_different_original_junction_pose_cannot_arm_walking(self):
        n,_=single_fixture()
        for changes in (dict(layerId='Other'),dict(x=0),dict(yawDegrees=98)):
            with self.subTest(changes),self.assertRaises(ValueError):
                recover.verify_return_position(dict(n['returned'][0]['navigationPose'],**changes),n['returned'])

    @unittest.skipUnless((PASSIVE/'original-map.png').is_file(),'Local R58 recording unavailable')
    def test_sealed_r58_origin_and_its_failed_alternatives(self):
        value=recover.verify_failed_map_origin(FAILURE,PASSIVE,OWNER,REPO)
        self.assertEqual(value['mapPngSha256'],'7ae2747095e498400b96dd9ad2f31fa98b6d01b30b53a9cc2b0c3a07ffc2f164')
        self.assertFalse(value['fullMapVisit'])
        self.assertGreater(value['mapCapturedTicks'],value['openReleasedTicks'])
        self.assertEqual(len(hashlib.sha256(recover.canonical_origin(value)).hexdigest()),64)
        original_read=recover.read
        for label in ('wrong window','extra escape','ordinary proposal','missing stop release','wrong passive digest'):
            def altered(path):
                data=original_read(path)
                if Path(path)==FAILURE/'map-inspection/transaction.json':
                    if label=='extra escape': data['inspection']['inputs'].append(dict(action='closeMap'))
                    if label=='ordinary proposal': data['inspection']['ordinaryRequestsWhileFenced']=1
                    if label=='missing stop release': data['abort']['executionContext']['trackedState']['heldKeys']=['M']
                if Path(path)==PASSIVE/'original-map-source.json':
                    if label=='wrong passive digest': data['imageSha256']='0'*64
                    if label=='wrong window':
                        data['sourceFrame']['captureEpoch']='a'*32
                        data['worldReadiness']['sourceFrame']['captureEpoch']='a'*32
                return data
            with self.subTest(label),patch.object(recover,'read',side_effect=altered),self.assertRaises(ValueError):
                recover.verify_failed_map_origin(FAILURE,PASSIVE,OWNER,REPO)


if __name__=='__main__':
    unittest.main()
