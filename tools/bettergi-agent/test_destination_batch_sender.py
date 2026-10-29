"""Exercise external publication and the automatic benchmark without any live broker or GPU."""
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import destination_batch_sender as sender
from hybrid_routes import PATROL_STATIONS, itinerary_legs
from run_destination_batches import launch_options, verify_manual_lease
import run_rdp_patrol as patrol


class SenderTests(unittest.TestCase):
    def setUp(self):
        """Supply an inert addressed control channel and the unmodified first destination plan."""
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.folder = Path(scratch.name)
        (self.folder/'batches').mkdir()
        (self.folder/'station-photos').mkdir()
        self.first = sender.create_plan('stair-front',[('initial-b','sidewalk-junction'),('initial-c','west-lamp')])
        self.path = self.folder/'photo-requests.json'
        self.path.write_bytes(sender.encode(self.first))
        self.summary = dict(status='running',computer='SIREN',batchCount=2,maxLegs=4)
        (self.folder/'warm-launcher.json').write_bytes(sender.encode(self.summary))
        self.run_id = 'e'*32
        self.warm = dict(version=1,runId=self.run_id,sessionId='a'*32,ownerEpoch='b'*32,batchOrdinal=1,
                         batchSha256=hashlib.sha256(self.path.read_bytes()).hexdigest(),activeOrdinal=1,
                         complete=False,activeRequestId=self.first['requests'][0]['id'],
                         activeFirstAppliedRequestId=None,activeFirstAppliedFrameId=None)
        self.status = self.folder/'station-photos'/'warm-status.json'
        self.status.write_bytes(sender.encode(self.warm))
        (self.folder/'patrol.json.status.json').write_bytes(sender.encode(dict(version=1,state='running',runId=self.run_id)))
        (self.folder/'patrol.json.control.json').write_bytes(sender.encode(dict(version=1,runId=self.run_id,command='run')))
        self.goals = [('custom-b','sidewalk-junction'),('custom-a','stair-front')]

    def witnessed(self):
        """Simulate a positive original receipt on the first active goal."""
        self.warm.update(activeFirstAppliedRequestId='c'*32,activeFirstAppliedFrameId=8)
        self.status.write_bytes(sender.encode(self.warm))

    def test_manual_publication_waits_for_witness_and_cannot_replace_evidence(self):
        with patch.object(sender,'create_plan',side_effect=AssertionError('future payload generated early')):
            self.assertIsNone(sender.submit(self.folder,2,self.goals))
        self.assertEqual(list((self.folder/'batches').iterdir()),[])
        self.witnessed()
        with patch.object(patrol,'native_qpc_sample',side_effect=[(1000,41),(1000,42)]):
            proof = sender.submit(self.folder,2,self.goals)
        base = self.folder/'batches'
        envelope = (base/'00002.json').read_bytes()
        intent = sender.read_json(base/'00002.intent.json')
        ack = sender.read_json(base/'00002.publication.json')
        self.assertEqual(hashlib.sha256(envelope).hexdigest(),proof['batchSha256'])
        self.assertEqual(intent['plan'],json.loads(envelope)['plan'])
        self.assertEqual(intent['previousSha256'],self.warm['batchSha256'])
        self.assertEqual((ack['publicationQpc']['beforeTicks'],ack['publicationQpc']['afterTicks']), (41,42))
        self.assertEqual(ack['witness'],dict(batchOrdinal=1,requestId=self.warm['activeRequestId'],
                                            nativeRequestId='c'*32,frameId=8))
        with self.assertRaises(ValueError):
            sender.submit(self.folder,2,self.goals)
        self.assertEqual((base/'00002.json').read_bytes(),envelope)
        with self.assertRaises(FileExistsError):
            sender.exclusive_bytes(base/'00002.json',b'other')

    def test_unbound_stale_capped_or_stopped_submissions_fail_closed(self):
        self.witnessed()
        for bad in (dict(batchSha256='0'*64),dict(runId='f'*32),dict(activeFirstAppliedFrameId=0)):
            self.status.write_bytes(sender.encode(dict(self.warm,**bad)))
            with self.assertRaises(ValueError):
                sender.submit(self.folder,2,self.goals)
        self.status.write_bytes(sender.encode(self.warm))
        with self.assertRaises(ValueError):
            sender.submit(self.folder,2,[('uses-four','stair-front'),('more','west-lamp')])
        (self.folder/'STOP').touch()
        with self.assertRaises(ValueError):
            sender.submit(self.folder,2,self.goals)
        self.assertEqual(list((self.folder/'batches').iterdir()),[])

    def test_seven_legs_per_generated_batch_and_one_bounded_resident(self):
        for start in PATROL_STATIONS:
            for witness in (8,9):
                goals = sender.qualification_goals(start,2,witness)
                self.assertEqual(len(itinerary_legs(start,[station for _,station in goals])),7)
        args = launch_options(['--batches','9','--leg-limit','63','--start-station','west-lamp',
                               '--landmark-shadow','model','--photo-qualification','qualification'])
        args.warm_photo_plan = self.path
        command = patrol.patrol_argv(args,3,self.folder)
        self.assertIn('--warm-batch-count=9',command)
        self.assertIn('--record-max-mib=160',command)
        self.assertEqual(command.count('--resident'),1)
        self.assertLessEqual(len(command)+1,65)

    def test_manual_authority_joins_live_status_to_separate_windows_session_manifest(self):
        root = dict(processId=11,instanceNonce='a'*32,childWindowMinimized=True)
        child = dict(processId=22,instanceNonce='b'*32,windowsSessionId=3,agentStreamRunning=True,runtimeRunning=True)
        binding = f"11:{root['instanceNonce']}:22:{child['instanceNonce']}:{time.monotonic_ns()+10_000_000_000}"
        (self.folder/'jobs').mkdir()
        (self.folder/'jobs'/'one.job.json').write_bytes(sender.encode(dict(windowsSessionId=3,
            argv=['stream_client.py','--output',str(self.folder/'patrol.json'),'--patrol-series-binding='+binding])))
        manifest = dict(version=1,runId=self.run_id,windowsSessionId=3,status='running',mode='resident-rdp',
                        inputRequested=True,modelLoads=1,controlFile=str(self.folder/'patrol.json.control.json'))
        path = self.folder/'patrol.json'
        path.write_bytes(sender.encode(manifest))
        # ResidentControl writes this shape during gameplay, without windowsSessionId.
        progress = dict(version=1,runId=self.run_id,state='running',childProcessId=22,childReplaced=False,
                        command='run',requestedCommand='run',controlError=None,updatedAtUnixMs=int(time.time()*1000))
        current = self.folder/'patrol.json.status.json'
        current.write_bytes(sender.encode(progress))
        api = Mock()
        api.discover.return_value = dict(unavailable=[],instances=[root,child])
        with patch.object(patrol,'control_module',return_value=api):
            verify_manual_lease(self.folder,self.warm)
            for bad in (dict(childProcessId=24),dict(childReplaced=True),dict(state='completed'),
                        dict(command='pause'),dict(updatedAtUnixMs=1)):
                current.write_bytes(sender.encode(dict(progress,**bad)))
                with self.assertRaises(ValueError):
                    verify_manual_lease(self.folder,self.warm)
            current.write_bytes(sender.encode(progress))
            path.write_bytes(sender.encode(dict(manifest,windowsSessionId=4)))
            with self.assertRaises(ValueError):
                verify_manual_lease(self.folder,self.warm)
