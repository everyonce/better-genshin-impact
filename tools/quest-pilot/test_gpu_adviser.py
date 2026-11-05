"""Contract tests for the read-only quest adviser. No game, named pipe or GPU is opened."""
from contextlib import nullcontext
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest import mock
import unittest

import gpu_adviser as adviser


def inert_resident(args,stop):
    """Exercise real Windows process ownership using an idle child without any model or pipe."""
    snapshot=dict(adviser.owner(args),modelLoaded=False,validNativeFrameSeen=False,counts={},testChildPid=os.getpid())
    adviser.publish(args.output/'ready.json',snapshot,retry_seconds=2)
    stop.wait(45)
    adviser.publish(args.output/'terminal.json',dict(snapshot,status='stopped'),retry_seconds=2)


def fixture_repo():
    """Locate the existing Windows job helper beside either a checked-in or staged test."""
    return next(p for p in Path(__file__).resolve().parents if (p/'tools/rdp-automation/child_runner.py').is_file())


class FragmentPipe:
    """Give the real packet reader short reads and writes."""
    def __init__(self, header, pixels=b''):
        body = json.dumps(header).encode()
        self.reply = bytearray(struct.pack('<I',len(body))+body+pixels)
        self.commands = bytearray()

    def read(self,size):
        length=min(size,341)
        chunk=self.reply[:length]
        del self.reply[:length]
        return chunk

    def write(self,data):
        part=data[:4]
        self.commands.extend(part)
        return len(part)

    def transaction(self,lock):
        return nullcontext()


class AdviserTests(unittest.TestCase):
    def setUp(self):
        self.identity = dict(session='real-quest',processId=101,windowsSessionId=7,gameProcessId=202)
        self.header = dict(self.identity,protocolVersion=1,type='frame',frameId=12,capturedAtUnixMs=5000,
            width=192,height=192,sourceWidth=1920,sourceHeight=1080,sourceKind='wgc-source',sourceEpoch='c'*32,
            observationProfile=adviser.PROFILE,pixelFormat='rgb24',payloadBytes=adviser.FRAME_BYTES)
        self.prediction = dict(parseValid=True,steps=[dict(keys=['W'],mouseDx=2,mouseDy=0,durationMs=50)])
        self.context = dict(session='real-quest',frameId=88,observedAtUnixMs=4992,requestId='mission-42',
            expectedUid='693306810',objective='Explore for Adventure Rank',waypoint=dict(map='Teyvat',x=-1130,y=2200))

    def test_only_read_request_exact_framing_and_rgb_bytes(self):
        rgb=b'a'*adviser.FRAME_BYTES
        pipe=FragmentPipe(self.header,rgb)
        self.assertEqual(adviser.get_frame(pipe,None),(self.header,rgb))
        self.assertEqual(pipe.commands,adviser.REQUEST)
        size,=struct.unpack('<I',pipe.commands[:4])
        self.assertEqual(len(pipe.commands)-4,size)
        self.assertEqual(json.loads(pipe.commands[4:]),{'command':'getFrame'})

    def test_rejects_oversized_and_truncated_replies_and_accepts_unavailable(self):
        unavailable=dict(type='unavailable',payloadBytes=0,reason='no_frame')
        self.assertEqual(adviser.get_frame(FragmentPipe(unavailable),None),(unavailable,b''))
        for length in [0,adviser.FRAME_BYTES-1,2**31,True]:
            with self.assertRaises(ValueError):
                adviser.get_frame(FragmentPipe(dict(self.header,payloadBytes=length)),None)
        with self.assertRaises(EOFError):
            adviser.get_frame(FragmentPipe(self.header,b'short'),None)
        pipe=FragmentPipe(unavailable)
        pipe.reply[:4]=struct.pack('<I',16385)
        with self.assertRaises(ValueError):
            adviser.get_frame(pipe,None)

    def test_exact_owner_profile_timestamps_and_monotonic_frames(self):
        def check(**changed):
            return adviser.admit(dict(self.header,**changed),self.identity,11,4980,5100,250)
        self.assertEqual(check(),'accepted')
        self.assertEqual(check(frameId=11),'duplicate')
        self.assertEqual(check(capturedAtUnixMs=4980),'duplicate')
        self.assertEqual(adviser.admit(self.header,self.identity,0,0,5251,250),'stale')
        self.assertEqual(check(capturedAtUnixMs=5101),'stale')
        for key,value in [('session','foreign'),('processId',True),('windowsSessionId',3),('gameProcessId',777),
                          ('observationProfile','thumbnail'),('sourceKind','unknown'),('pixelFormat','bgra32'),
                          ('width',256),('protocolVersion',True),('sourceWidth',False),('sourceEpoch','unbound')]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                check(**{key:value})

    def test_steering_projects_only_one_pure_forward_step(self):
        self.assertEqual(adviser.steering(self.prediction),{'forward':True,'holdMs':50})
        step=self.prediction['steps'][0]
        for changed in [dict(keys=['W','LBUTTON']),dict(keys=['A']),dict(keys=['W','SPACE']),dict(mouseDx=33),
                        dict(mouseDy=float('nan')),dict(durationMs=0),dict(durationMs=251)]:
            self.assertEqual(adviser.steering(dict(parseValid=True,steps=[dict(step,**changed)])),
                             {'forward':False,'holdMs':0})
        self.assertFalse(adviser.steering(dict(parseValid=False,steps=[step]))['forward'])
        self.assertFalse(adviser.steering(dict(parseValid=True,steps=[step,step]))['forward'])

    def test_atomic_context_is_bound_to_public_frame_before_native_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'context.json'
            self.assertIsNone(adviser.read_context(path,'real-quest',5000))
            adviser.publish(path,self.context)
            self.assertEqual(adviser.read_context(path,'real-quest',5000),self.context)
            for changed in [dict(frameId=True),dict(observedAtUnixMs=5001),dict(observedAtUnixMs=3999),
                            dict(session='other'),dict(expectedUid='broken'),dict(waypoint={})]:
                adviser.publish(path,dict(self.context,**changed))
                self.assertIsNone(adviser.read_context(path,'real-quest',5000))

    def test_expiry_starts_at_capture_and_context_switches_revoke_advice(self):
        def pack(after,when):
            return adviser.suggestion(self.header,self.prediction,self.context,after,when,250,21.125)
        result=pack(self.context,5031)
        self.assertEqual(result['frameId'],12)
        self.assertEqual(result['context']['frameId'],88)
        self.assertEqual(result['validUntilUnixMs'],5250)
        self.assertEqual(result['inferenceMs'],21.125)
        self.assertIsNone(pack(self.context,5251))
        self.assertIsNone(pack(self.context,4999))
        self.assertIsNone(pack(dict(self.context,requestId='mission-other'),5031)['context'])

    def test_existing_stop_finishes_without_loading_model_or_opening_pipe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'reports').mkdir()
            output=root/'evidence'
            output.mkdir()
            (output/'STOP').touch()
            args=SimpleNamespace(output=output,pilot_dir=root,session='real-quest',process_id=101,
                                 windows_session_id=7,game_process_id=202)
            with mock.patch.object(adviser.multiprocessing,'get_context',side_effect=AssertionError('started child')):
                self.assertEqual(adviser.supervise(args),0)
            terminal=json.loads((output/'terminal.json').read_bytes())
            self.assertEqual({k:terminal[k] for k in self.identity},self.identity)
            self.assertFalse(terminal['validNativeFrameSeen'])
            self.assertFalse(terminal['modelLoaded'])
            self.assertFalse((output/'ready.json').exists())

    def test_worker_loads_once_drops_duplicate_resets_on_epoch_and_publishes_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'reports').mkdir()
            output=root/'audit'
            output.mkdir()
            adviser.publish(root/'reports/quest-adviser-context.json',self.context)
            args=SimpleNamespace(output=output,pilot_dir=root,session='real-quest',process_id=101,windows_session_id=7,
                                 game_process_id=202,goal_embedding=Path('test-goal'),first_frame_timeout=10,max_age_ms=250)
            args.disconnect_timeout=10
            stop=mock.Mock()
            stop.is_set.return_value=False
            headers=[self.header, self.header, dict(self.header,frameId=13,capturedAtUnixMs=5010,sourceEpoch='d'*32)]
            def wait(_):
                if not headers:
                    stop.is_set.return_value=True
            stop.wait.side_effect=wait
            transport=mock.Mock()
            model=mock.Mock()
            model.predict.return_value=self.prediction
            read=mock.Mock(side_effect=lambda *_:(headers.pop(0),bytes(adviser.FRAME_BYTES)))
            with mock.patch.dict(sys.modules,{'windows_pipe_transport':transport}), mock.patch.object(adviser,'verify_server'), \
                    mock.patch.object(adviser,'unix_ms',return_value=5040), mock.patch.object(adviser,'get_frame',read), \
                    mock.patch.object(adviser,'load_policy',return_value=model) as load:
                adviser.worker(args,stop)
            load.assert_called_once()
            self.assertEqual(model.predict.call_count,2)
            model.reset.assert_called_once()
            latest=json.loads((root/'reports/quest-adviser-latest.json').read_bytes())
            self.assertEqual(latest['context'],self.context)
            self.assertEqual(latest['sourceEpoch'],'d'*32)
            self.assertEqual(latest['frameId'],13)
            self.assertTrue(latest['steering']['forward'])
            self.assertEqual(latest['validUntilUnixMs'],5260)
            ready=json.loads((output/'ready.json').read_bytes())
            terminal=json.loads((output/'terminal.json').read_bytes())
            self.assertFalse(ready['validNativeFrameSeen'])
            self.assertTrue(ready['modelLoaded'])
            self.assertTrue(terminal['validNativeFrameSeen'])
            self.assertEqual(terminal['counts']['duplicate'],1)
            self.assertEqual(terminal['counts']['published'],2)
            for receipt in (ready,terminal):
                self.assertEqual({k:receipt[k] for k in self.identity},self.identity)

    def test_busy_publication_drops_immediate_samples_and_retries_durable_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'sample.json'
            adviser.publish(path,{'old':True})
            replace=os.replace
            calls=0
            def temporarily_busy(src,dst):
                nonlocal calls
                calls+=1
                if calls<3:
                    raise PermissionError('busy')
                return replace(src,dst)
            with mock.patch.object(adviser.os,'replace',side_effect=temporarily_busy):
                self.assertFalse(adviser.publish(path,{'dropped':True}))
                self.assertEqual(json.loads(path.read_bytes()),{'old':True})
                self.assertTrue(adviser.publish(path,{'durable':True},retry_seconds=.5))
            self.assertEqual(json.loads(path.read_bytes()),{'durable':True})
            with mock.patch.object(adviser.os,'replace',side_effect=PermissionError('busy')):
                with self.assertRaises(TimeoutError):
                    adviser.publish(path,{},retry_seconds=.03)

    def test_no_fresh_frame_deadline_applies_after_first_valid_frame_and_shared_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'reports').mkdir()
            output=root/'audit'
            output.mkdir()
            args=SimpleNamespace(output=output,pilot_dir=root,session='real-quest',process_id=101,windows_session_id=7,
                 game_process_id=202,goal_embedding=Path('test-goal'),first_frame_timeout=20,disconnect_timeout=4,max_age_ms=250)
            now=[20.]
            stop=mock.Mock()
            stop.is_set.return_value=False
            stop.wait.side_effect=lambda _:now.__setitem__(0,now[0]+1)
            model=mock.Mock()
            model.predict.return_value=self.prediction
            read=mock.Mock(side_effect=[(self.header,bytes(adviser.FRAME_BYTES)),EOFError(),
                       ({'type':'unavailable','payloadBytes':0},b''),(self.header,bytes(adviser.FRAME_BYTES))])
            replace=os.replace
            def busy_stats_and_latest(src,dst):
                if Path(dst).name in ('stats.json','quest-adviser-latest.json'):
                    raise PermissionError('held by a reader')
                return replace(src,dst)
            with mock.patch.dict(sys.modules,{'windows_pipe_transport':mock.Mock()}), mock.patch.object(adviser,'verify_server'), \
                    mock.patch.object(adviser,'unix_ms',return_value=5040), mock.patch.object(adviser,'get_frame',read), \
                    mock.patch.object(adviser.time,'monotonic',side_effect=lambda:now[0]), \
                    mock.patch.object(adviser.os,'replace',side_effect=busy_stats_and_latest), \
                    mock.patch.object(adviser,'load_policy',return_value=model):
                with self.assertRaises(SystemExit):
                    adviser.worker(args,stop)
            terminal=json.loads((output/'terminal.json').read_bytes())
            self.assertEqual(terminal['status'],'failed')
            self.assertIn('stopped producing fresh',terminal['error'])
            self.assertEqual(terminal['counts']['accepted'],1)
            self.assertEqual(terminal['counts']['disconnects'],1)
            self.assertEqual(terminal['counts']['busyOutput'],1)
            self.assertEqual(terminal['counts']['busyStats'],3)
            self.assertEqual(terminal['counts']['duplicate'],1)
            self.assertFalse((root/'reports/quest-adviser-latest.json').exists())

    def test_real_windows_job_honors_absolute_runtime_and_pinned_launcher_exit(self):
        repo=fixture_repo()
        for mode in ('runtime_timeout','launcher_exited'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                (root/'reports').mkdir()
                output=root/'audit'
                args=SimpleNamespace(output=output,pilot_dir=root,session='real-quest',process_id=101,windows_session_id=7,
                    game_process_id=202,startup_timeout=10,max_runtime_seconds=1 if mode=='runtime_timeout' else 10,
                    launcher_pid=None)
                launcher=watcher=None
                try:
                    if mode=='launcher_exited':
                        launcher=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(45)'])
                        args.launcher_pid=launcher.pid
                        def retire_on_ready():
                            deadline=time.monotonic()+5
                            while not (output/'ready.json').exists() and time.monotonic()<deadline:
                                time.sleep(.025)
                            launcher.terminate()
                        watcher=threading.Thread(target=retire_on_ready)
                        watcher.start()
                    with mock.patch.object(adviser,'ROOT',repo):
                        self.assertEqual(adviser.supervise(args,worker_target=inert_resident),1)
                finally:
                    if watcher: watcher.join(6)
                    if launcher:
                        if launcher.poll() is None: launcher.terminate()
                        launcher.wait(3)
                terminal=json.loads((output/'terminal.json').read_bytes())
                self.assertEqual(terminal.get('reason'),mode,terminal)
                self.assertEqual(terminal.get('status'),'failed')
                self.assertFalse(terminal['validNativeFrameSeen'])
                self.assertGreater(terminal['testChildPid'],0)

    def test_hard_supervisor_death_retires_the_exact_resident_worker(self):
        import _winapi
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'reports').mkdir()
            supervisor=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--inert-supervisor',str(root)])
            handle=None
            try:
                ready=root/'audit/ready.json'
                deadline=time.monotonic()+8
                while supervisor.poll() is None and not ready.exists() and time.monotonic()<deadline:
                    time.sleep(.025)
                self.assertTrue(ready.exists())
                pid=json.loads(ready.read_bytes())['testChildPid']
                handle=_winapi.OpenProcess(_winapi.SYNCHRONIZE | 0x0001,False,pid)  # PROCESS_TERMINATE for test cleanup
                self.assertEqual(_winapi.WaitForSingleObject(handle,0),_winapi.WAIT_TIMEOUT)
                supervisor.terminate()
                supervisor.wait(3)
                self.assertEqual(_winapi.WaitForSingleObject(handle,3000),0,'orphaned idle test worker')
            finally:
                if supervisor.poll() is None:
                    supervisor.terminate()
                supervisor.wait(3)
                if handle is not None:
                    if _winapi.WaitForSingleObject(handle,0)==_winapi.WAIT_TIMEOUT:
                        _winapi.TerminateProcess(handle,1)
                    _winapi.CloseHandle(handle)


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--inert-supervisor':
        root=Path(sys.argv[2])
        args=SimpleNamespace(output=root/'audit',pilot_dir=root,session='fixture',process_id=101,windows_session_id=7,
                             game_process_id=202,startup_timeout=10,max_runtime_seconds=20,launcher_pid=None)
        adviser.ROOT=fixture_repo()
        raise SystemExit(adviser.supervise(args,worker_target=inert_resident))
    unittest.main()
