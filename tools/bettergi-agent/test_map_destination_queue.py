"""Exercise map and automatic-queue admission and result sealing without starting a live lease."""
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import destination_batch_sender as sender
import map_owner
import run_destination_batches as batches
import run_rdp_patrol as patrol
import run_warm_photo_requests as warm


class MapQueueTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.owner = self.root/'warm-launcher.json'
        self.lineage = self.root/'map-owner-lineage.json'
        self.pair = {role:dict(windowsSessionId=session,processId=session*100,instanceNonce=str(session)*32)
                     for role,session in [('root',1),('child',3)]}
        self.game = dict(processId=600,windowsSessionId=3,startedFileTime=1234,executable='GenshinImpact.exe')
        self.receipt = dict(prior='prior-lineage.json',priorLineageSha256='a'*64,identity=self.pair,protectedGame=self.game)
        self.flags = ['--batches','12','--leg-limit','96','--seconds','400','--target-gameplay-seconds','210',
                      '--open-queue','--owner-from',str(self.owner),'--start-station','sidewalk-junction',
                      '--destination','lamp','west-lamp','--destination','return','sidewalk-junction',
                      '--inspect-junction-map','--map-owner-from',str(self.lineage),'--landmark-shadow','g4',
                      '--photo-qualification','qualification']
        self.owner.write_text(json.dumps(dict(status='completed',identity=self.pair)),encoding='utf-8')
        self.folder = self.root/'queue'
        (self.folder/'batches').mkdir(parents=True)

    def test_flags_require_paired_automatic_queue_and_exact_initial_plan(self):
        args = batches.launch_options(self.flags)
        self.assertEqual((args.batches,args.destination_legs,args.seconds,args.target_gameplay_seconds),(12,96,400,210))
        for omit,extra in [(['--inspect-junction-map'],[]),(['--map-owner-from',str(self.lineage)],[]),
                           (['--target-gameplay-seconds','210'],['--manual']),([],['--stop-in-batch','2']),
                           (['--open-queue','--owner-from',str(self.owner),'--target-gameplay-seconds','210'],[]),
                           ([],['--destination','third','stair-front']),([],['--recover-junction-map']),
                           ([],['--start-station','west-lamp'])]:
            flags=[flag for flag in self.flags if flag not in omit]+extra
            with self.subTest(omit=omit,extra=extra),redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                batches.launch_options(flags)

    def launch(self, args, *, receipt=None, expected=None, side_effect=None):
        actual = self.receipt if receipt is None else receipt
        with patch.object(map_owner,'evidence',return_value=(actual,'f'*64)), \
                patch.object(map_owner,'replacement',return_value=actual if expected is None else expected), \
                patch.object(warm.socket,'gethostname',return_value='SIREN'), \
                patch.object(patrol,'run',side_effect=side_effect) as job:
            self.job = job
            return warm.run(args,self.folder,guard_type=batches.BatchGuard)

    def test_wrong_owner_r58_or_modified_lineage_never_submits(self):
        args = batches.launch_options(self.flags)
        for reason,receipt,expected in [('R58',dict(prior='older',identity=self.pair),None),
                                       ('modified',self.receipt,dict(self.receipt,prior='different')),
                                       ('owner',self.receipt,None)]:
            self.folder=self.root/reason
            self.folder.mkdir()
            if reason=='owner':
                other=dict(self.pair,child=dict(self.pair['child'],processId=999))
                self.owner.write_text(json.dumps(dict(status='completed',identity=other)),encoding='utf-8')
            with self.subTest(reason=reason),self.assertRaises(ValueError):
                self.launch(args,receipt=receipt,expected=expected)
            self.job.assert_not_called()

    def test_single_job_and_both_audits_are_required(self):
        args=batches.launch_options(self.flags)
        successor=sender.create_plan('sidewalk-junction',[('east','stair-front'),('end','sidewalk-junction')])
        plans=[args.plan,successor]
        requests=[r for plan in plans for r in plan['requests']]
        handoffs=[dict(oldRequestId=a['id'],newRequestId=b['id'],dispatchGapMs=400) for a,b in zip(requests,requests[1:])]
        def job(args,folder,*,series):
            self.assertEqual(series.required_identity,self.pair)
            self.assertEqual(json.loads((folder/'map-required-game.json').read_bytes()),self.game)
            self.assertEqual((folder/'required-owner.json').read_bytes(),self.owner.read_bytes())
            command=patrol.patrol_argv(args,3,folder)
            for flag in ('--inspect-junction-map','--warm-open-queue','--warm-batch-count=12'):
                self.assertIn(flag,command)
            series.identity=self.pair
        for mode in ('passed','queue-failed','map-failed'):
            self.folder=self.root/mode
            self.folder.mkdir()
            def queue(args,folder,guard):
                if mode=='queue-failed':
                    raise RuntimeError('queue failure')
                proof=dict(passed=True,status='runtime-target-achieved',openQueue=dict(outcome='gameplayTargetReached'),handoffs=handoffs)
                patrol.atomic_json(folder/'handoff-audit.json',proof)
                return proof
            def map_replay(folder,*_):
                summary=json.loads((folder/'warm-launcher.json').read_bytes())
                self.assertEqual((summary['status'],summary['identity']),('auditingMap',self.pair))
                self.assertTrue((folder/'handoff-audit.json').exists())
                return dict(passed=mode=='passed')
            audit=Mock(side_effect=map_replay)
            with self.subTest(mode=mode),patch.dict('sys.modules',{'audit_map_inspection':SimpleNamespace(audit_map=audit)}), \
                    patch.object(warm,'audit_result',side_effect=queue),patch.object(sender,'admitted_plans',return_value=plans):
                result=self.launch(args,side_effect=job)
                self.job.assert_called_once()
                self.assertEqual(audit.call_count,int(mode!='queue-failed'))
                self.assertEqual(result['status'],'completed' if mode=='passed' else 'stopped')
                self.assertEqual(result.get('mapInspectionVerified',False),mode=='passed')
                self.assertEqual((self.folder/'map-audit.json').is_file(),mode=='passed')
                self.assertEqual(json.loads((self.folder/'warm-launcher.json').read_bytes()),result)


if __name__=='__main__':
    unittest.main()
