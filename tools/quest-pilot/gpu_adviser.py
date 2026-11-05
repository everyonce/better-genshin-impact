"""Read the public BetterGI quest frame pipe and publish expiring P2P steering suggestions."""
import argparse
from collections import Counter, deque
from contextlib import ExitStack
import ctypes
import json
import math
import multiprocessing
import os
from pathlib import Path
import re
import struct
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[2]
PROFILE = 'p2p-native-hamming-192-v1'
SOURCE_KINDS = {'wgc-source', 'desktopdc-host', 'capture-request'}
FRAME_BYTES = 192 * 192 * 3
GET_FRAME = b'{"command":"getFrame"}'
REQUEST = struct.pack('<I', len(GET_FRAME)) + GET_FRAME


def unix_ms():
    return time.time_ns() // 1_000_000


def owner(args):
    return dict(session=args.session, processId=args.process_id, windowsSessionId=args.windows_session_id,
                gameProcessId=args.game_process_id)


def sharing_violation(exc):
    """Windows reports a file in use as access denied, sharing violation, or lock violation."""
    return isinstance(exc,PermissionError) or getattr(exc,'winerror',None) in (5,32,33)


def publish(path, value, *, retry_seconds=0):
    """Publish a complete record. A Windows sharing violation drops this sample unless it is a receipt."""
    pending = path.with_name(f'{path.name}.{os.getpid()}.pending')
    encoded = json.dumps(value, separators=(',', ':'), allow_nan=False).encode('utf-8')
    deadline = time.monotonic() + retry_seconds
    while True:
        try:
            pending.write_bytes(encoded)
            os.replace(pending, path)
            return True
        except OSError as exc:
            if not sharing_violation(exc):
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if retry_seconds:
                    raise TimeoutError(f'Could not publish {path.name} before the sharing timeout') from exc
                return False
            time.sleep(min(.025,remaining))
        finally:
            # A busy orphan of this PID is overwritten on the next publication.
            try:
                pending.unlink(missing_ok=True)
            except OSError as exc:
                if not sharing_violation(exc):
                    raise


def read_exact(pipe, count):
    data = bytearray()
    while len(data) < count:
        part = pipe.read(count - len(data))
        if not part:
            raise EOFError('Quest frame pipe closed')
        data.extend(part)
    return bytes(data)


def get_frame(pipe, lock):
    """Send the fixed read request and bound both parts of the reply before allocating."""
    with pipe.transaction(lock):
        offset = 0
        while offset < len(REQUEST):
            count = pipe.write(REQUEST[offset:])
            if not count:
                raise EOFError('Quest frame pipe closed during request')
            offset += count
        size, = struct.unpack('<I', read_exact(pipe, 4))
        if not 0 < size <= 16384:
            raise ValueError('Invalid quest frame header size')
        header = json.loads(read_exact(pipe, size))
        if not isinstance(header, dict):
            raise ValueError('Invalid quest frame header')
        length = header.get('payloadBytes')
        if type(length) is not int or (header.get('type'), length) not in (('frame',FRAME_BYTES), ('unavailable',0)):
            raise ValueError('Invalid quest frame payload declaration')
        return header, read_exact(pipe, length)


def verify_server(pipe, expected):
    """Check the kernel-reported pipe owner before taking model input from its replies."""
    import msvcrt
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    server = wintypes.ULONG()
    lookup = kernel.GetNamedPipeServerProcessId
    lookup.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
    lookup.restype = wintypes.BOOL
    if not lookup(msvcrt.get_osfhandle(pipe.fileno()), ctypes.byref(server)):
        raise ctypes.WinError(ctypes.get_last_error())
    session = wintypes.DWORD()
    session_for = kernel.ProcessIdToSessionId
    session_for.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    session_for.restype = wintypes.BOOL
    if not session_for(server.value, ctypes.byref(session)):
        raise ctypes.WinError(ctypes.get_last_error())
    if server.value != expected['processId'] or session.value != expected['windowsSessionId']:
        raise ValueError('Native quest pipe server owner changed')


def admit(header, expected, previous_id, previous_time, now, max_age):
    """Validate provenance and reject duplicates, clock regressions, stale images and unsupported encodings."""
    for key, value in expected.items():
        if type(header.get(key)) is not type(value) or header[key] != value:
            raise ValueError(f'Native frame owner mismatch: {key}')
    if (type(header.get('protocolVersion')) is not int or header['protocolVersion'] != 1
            or header.get('sourceKind') not in SOURCE_KINDS or header.get('pixelFormat') != 'rgb24'
            or not isinstance(header.get('sourceEpoch'), str) or not re.fullmatch(r'[0-9a-f]{32}',header['sourceEpoch'])
            or header.get('observationProfile') != PROFILE or header.get('width') != 192 or header.get('height') != 192
            or any(type(header.get(k)) is not int or header[k] <= 0
                   for k in ('width','height','sourceWidth','sourceHeight','frameId','capturedAtUnixMs'))):
        raise ValueError('Unsupported native quest frame')
    if header['frameId'] <= previous_id or header['capturedAtUnixMs'] <= previous_time:
        return 'duplicate'
    if not 0 <= now - header['capturedAtUnixMs'] <= max_age:
        return 'stale'
    return 'accepted'


def read_context(path, session, captured):
    """Bind a suggestion only to public navigation that was already observed when its image was taken."""
    try:
        with path.open('rb') as stream:
            raw = stream.read(16385)
        if len(raw)>16384:
            return None
        data = json.loads(raw)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    point = data.get('waypoint')
    if (data.get('session') != session or type(data.get('frameId')) is not int or data['frameId'] < 1
            or type(data.get('observedAtUnixMs')) is not int or not 0 <= captured-data['observedAtUnixMs'] <= 1000
            or not isinstance(data.get('expectedUid'), str) or not re.fullmatch(r'[0-9]{9,10}',data['expectedUid'])
            or not isinstance(data.get('requestId'), str) or not data['requestId']
            or not isinstance(data.get('objective'), str) or not data['objective']
            or not isinstance(point, dict) or point.get('map') != 'Teyvat'
            or any(type(point.get(k)) not in (float,int) or not math.isfinite(point[k]) for k in ('x','y'))):
        return None
    return {k:data[k] for k in ('session','frameId','observedAtUnixMs','requestId','expectedUid','objective','waypoint')}


def steering(prediction):
    """Expose only a short, forward-only suggestion; all other model output abstains."""
    steps = prediction.get('steps')
    if prediction.get('parseValid') is True and isinstance(steps,list) and len(steps) == 1:
        step = steps[0]
        if (isinstance(step,dict) and step.get('keys') == ['W']
                and all(type(step.get(k)) in (int,float) and math.isfinite(step[k]) and abs(step[k]) <= 32
                        for k in ('mouseDx','mouseDy'))
                and type(step.get('durationMs')) is int and 1 <= step['durationMs'] <= 250):
            return dict(forward=True, holdMs=step['durationMs'])
    return dict(forward=False, holdMs=0)


def suggestion(header, predicted, first_context, current_context, published, max_age, inference_ms):
    captured = header['capturedAtUnixMs']
    if not 0 <= published-captured <= max_age:
        return None
    keys = ('session','processId','windowsSessionId','gameProcessId','frameId','capturedAtUnixMs',
            'sourceKind','sourceEpoch','sourceWidth','sourceHeight','observationProfile')
    return dict({k:header[k] for k in keys}, protocolVersion=1,type='steeringSuggestion',model='open-p2p-150M',
                publishedAtUnixMs=published,validUntilUnixMs=captured+max_age,inferenceMs=round(inference_ms,3),
                context=first_context if first_context==current_context else None,steering=steering(predicted))


def load_policy(goal):
    """Create one real CUDA policy; warm its graph and reset synthetic history before exposing readiness."""
    if str(ROOT/'tools/bettergi-agent') not in sys.path:
        sys.path.insert(0,str(ROOT/'tools/bettergi-agent'))
    from model_adapters import make_adapter
    from PIL import Image
    base = ROOT/'artifacts/agent'
    policy = make_adapter('open-p2p',checkpoint=base/'models/open-p2p-150M/150M/checkpoint-step=00500000.ckpt',
                          source=base/'sources/open-p2p',cache_root=base/'compatibility',history=41,dtype='float16',
                          cuda_graph=True,fast_start=True,goal_embedding=str(goal),observation_profile=PROFILE)
    policy.predict(Image.new('RGB',(192,192)),(1920,1080),observation_profile=PROFILE)
    policy.reset()
    return policy


def quantiles(values):
    ordered = sorted(values)
    if not ordered:
        return {}
    return {label:round(ordered[math.ceil(len(ordered)*p)-1],3) for label,p in (('p50',.50),('p95',.95))}


def worker(args, stop):
    """A single outstanding getFrame fetches the latest view; inference and file I/O run outside BetterGI."""
    expected = owner(args)
    stats = Counter()
    latency, age = deque(maxlen=2048), deque(maxlen=2048)
    pipe, model_loaded, error = None, False, None
    last_id, last_seen_id, last_time, last_source = 0, 0, 0, None
    # Keep volatile single-record mailboxes outside the bounded durable reports tree.
    context_path = args.pilot_dir/'quest-adviser-context.json'
    result_path = args.pilot_dir/'quest-adviser-latest.json'
    native_name = f'BetterGI.QuestFrames.{args.process_id}.{args.session}'
    def status():
        return dict(**expected,modelLoaded=model_loaded,validNativeFrameSeen=stats['accepted']>0,counts=dict(stats),
                    lastFrameId=last_id,inferenceMs=quantiles(latency),captureToPublicationMs=quantiles(age))
    try:
        if stop.is_set():
            return
        model = load_policy(args.goal_embedding)
        model_loaded = True
        if stop.is_set():
            return
        from windows_pipe_transport import WindowsPipe
        from PIL import Image
        publish(args.output/'ready.json',dict(status(),ready=True,model='open-p2p-150M',goalEmbedding=str(args.goal_embedding)),
                retry_seconds=2)
        lock = threading.Lock()
        fresh_frame_deadline=time.monotonic()+args.first_frame_timeout
        next_stats = time.monotonic()+1
        while not stop.is_set():
            tick = time.monotonic()
            if tick>=fresh_frame_deadline:
                raise TimeoutError('The quest pipe stopped producing fresh native frames' if stats['accepted']
                                   else 'The quest pipe produced no valid native frame before the first-frame deadline')
            if tick >= next_stats:
                if not publish(args.output/'stats.json',status()):
                    stats['busyStats']+=1
                next_stats=tick+1
            if pipe is None:
                try:
                    pipe=WindowsPipe(native_name,timeout=1)
                except OSError as exc:
                    if getattr(exc,'winerror',None) not in (2, 3, 121, 231):
                        raise
                    stats['waitingForPipe']+=1
                    stop.wait(.1)
                    continue
                verify_server(pipe,expected)
            try:
                head,pixels=get_frame(pipe,lock)
            except (EOFError,OSError,TimeoutError):
                pipe.close()
                pipe=None
                stats['disconnects']+=1
                stop.wait(.1)
                continue
            if head['type']=='unavailable':
                stats['unavailable']+=1
            else:
                verdict=admit(head,expected,last_seen_id,last_time,unix_ms(),args.max_age_ms)
                last_seen_id=max(last_seen_id,head['frameId'])
                stats[verdict]+=1
                if verdict=='accepted' and not stop.is_set():
                    fresh_frame_deadline=tick+args.disconnect_timeout
                    source=(head['sourceKind'],head['sourceEpoch'])
                    if last_source and (source!=last_source or head['capturedAtUnixMs']-last_time>1000):
                        model.reset()
                        stats['historyResets']+=1
                    last_id,last_time,last_source=head['frameId'],head['capturedAtUnixMs'],source
                    before=read_context(context_path,args.session,last_time)
                    image=Image.frombytes('RGB',(192,192),pixels)
                    started=time.perf_counter_ns()
                    pred=model.predict(image,(head['sourceWidth'],head['sourceHeight']),observation_profile=PROFILE)
                    measured=(time.perf_counter_ns()-started)/1e6
                    latency.append(measured)
                    now_context=read_context(context_path,args.session,last_time)
                    advice=suggestion(head,pred,before,now_context,unix_ms(),args.max_age_ms,measured)
                    if advice is None:
                        stats['expiredDuringInference']+=1
                    elif not stop.is_set():
                        if not publish(result_path,advice):
                            stats['busyOutput']+=1
                        else:
                            stats['published']+=1
                            stats['withContext']+=int(advice['context'] is not None)
                            stats['forward']+=int(advice['steering']['forward'])
                            age.append(unix_ms()-last_time)
            stop.wait(max(0.,1/30-(time.monotonic()-tick)))
    except Exception as exc:
        error=f'{type(exc).__name__}: {exc}'
    finally:
        if pipe is not None:
            pipe.close()
        publish(args.output/'terminal.json',dict(status(),status='failed' if error else 'stopped',error=error),
                retry_seconds=2)
    if error:
        raise SystemExit(1)


def owned_worker(args, stop, armed, target):
    """Wait for Windows job assignment before a child can load a checkpoint or issue a frame request."""
    if not armed.wait(5):
        raise SystemExit(1)
    if not stop.is_set():
        target(args,stop)


def lifetime_job():
    """Use the existing RDP runner's non-inheritable kill-on-close job."""
    runner=str(ROOT/'tools/rdp-automation')
    if runner not in sys.path:
        sys.path.insert(0,runner)
    from child_runner import CommandJob
    return CommandJob()


def bind_worker(job, child):
    """Assign the exact Windows process handle returned at spawn, while the GPU child is gated."""
    from ctypes import wintypes
    assign=job.kernel.AssignProcessToJobObject
    assign.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
    assign.restype=wintypes.BOOL
    if not assign(job.handle,child.sentinel):
        raise ctypes.WinError(ctypes.get_last_error())


def read_receipt(path,expected):
    """A stale or partially written record cannot supply evidence for a newly spawned run."""
    deadline=time.monotonic()+.5
    while True:
        try:
            snapshot=json.loads(path.read_bytes())
            break
        except ValueError:
            return {}
        except OSError as exc:
            if not sharing_violation(exc) or time.monotonic()>=deadline:
                return {}
            time.sleep(.025)
    if isinstance(snapshot,dict) and all(snapshot.get(k)==v for k,v in expected.items()):
        return snapshot
    return {}


def supervise(args, worker_target=worker):
    """Own the GPU job, bound launcher and run lifetimes, and collect the last actual frame evidence."""
    import _winapi
    expected = owner(args)
    terminal=args.output/'terminal.json'
    ready=args.output/'ready.json'
    args.output.mkdir(parents=True,exist_ok=True)
    if terminal.exists() or ready.exists():
        raise ValueError('An adviser run requires a fresh output directory')
    if (args.output/'STOP').exists():
        publish(terminal,dict(expected,status='stopped',modelLoaded=False,validNativeFrameSeen=False,
                              reason='stop_before_start',counts={},lastFrameId=0,inferenceMs={},
                              captureToPublicationMs={}),retry_seconds=2)
        return 0
    reason=error=child=None
    forced=False
    started=time.monotonic()
    try:
        if not (args.pilot_dir/'reports').is_dir():
            raise ValueError('The ActOnePilot reports directory is missing')
        with ExitStack() as scope:
            launcher=None
            if args.launcher_pid is not None:
                launcher=_winapi.OpenProcess(_winapi.SYNCHRONIZE,False,args.launcher_pid)
                scope.callback(_winapi.CloseHandle,launcher)
                if _winapi.WaitForSingleObject(launcher,0)!=_winapi.WAIT_TIMEOUT:
                    raise RuntimeError('The launching process already exited')
            job=lifetime_job()
            scope.callback(job.close)
            mp=multiprocessing.get_context('spawn')
            stop,armed=mp.Event(),mp.Event()
            child=mp.Process(target=owned_worker,args=(args,stop,armed,worker_target))
            child.start()
            try:
                bind_worker(job,child)
                armed.set()
                while child.is_alive():
                    elapsed=time.monotonic()-started
                    if (args.output/'STOP').exists():
                        reason='stop_requested'
                    elif launcher is not None and _winapi.WaitForSingleObject(launcher,0)!=_winapi.WAIT_TIMEOUT:
                        reason='launcher_exited'
                    elif elapsed>=args.max_runtime_seconds:
                        reason='runtime_timeout'
                    elif elapsed>=args.startup_timeout and not ready.exists():
                        reason='startup_timeout'
                    if reason:
                        break
                    child.join(.05)
            finally:
                stop.set()
                child.join(3.5)
                forced=child.is_alive()
                if forced:
                    child.terminate()
                    child.join(1)
    except Exception as exc:
        error=f'{type(exc).__name__}: {exc}'
        reason='supervisor_failure'
    receipt=read_receipt(terminal,expected)
    failed=reason not in (None,'stop_requested') or receipt.get('status')=='failed'
    if not receipt and reason!='stop_requested':
        failed=True
        reason=reason or 'worker_exited_without_receipt'
    if receipt.get('status')=='stopped' and reason is None and child is not None and child.exitcode:
        failed=True
        reason='worker_exited_with_error'
    if not receipt or reason:
        snapshot=receipt or read_receipt(args.output/'stats.json',expected)
        counts=snapshot.get('counts',{})
        publish(terminal,dict(snapshot,**expected,status='failed' if failed else 'stopped',
            modelLoaded=ready.exists(),validNativeFrameSeen=counts.get('accepted',0)>0,counts=counts,
            lastFrameId=snapshot.get('lastFrameId',0),inferenceMs=snapshot.get('inferenceMs',{}),
            captureToPublicationMs=snapshot.get('captureToPublicationMs',{}),reason=reason,
            forcedWorkerExit=forced,error=error or snapshot.get('error')),retry_seconds=2)
    return int(failed)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot-dir',type=Path,required=True)
    parser.add_argument('--session',required=True)
    parser.add_argument('--process-id',type=int,required=True)
    parser.add_argument('--windows-session-id',type=int,required=True)
    parser.add_argument('--game-process-id',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-age-ms',type=int,default=250,choices=range(1,351),metavar='1..350')
    parser.add_argument('--startup-timeout',type=float,default=120)
    parser.add_argument('--first-frame-timeout',type=float,default=120)
    parser.add_argument('--disconnect-timeout',type=float,default=30)
    parser.add_argument('--max-runtime-seconds',type=float,default=1800)
    parser.add_argument('--launcher-pid',type=int)
    parser.add_argument('--goal-embedding',type=Path,default=ROOT/'artifacts/agent/goals/ground-street-walk.json')
    args=parser.parse_args()
    if (not re.fullmatch(r'[A-Za-z0-9_-]{1,96}',args.session)
            or min(args.process_id,args.game_process_id,args.windows_session_id)<1
            or not 0<args.startup_timeout<=600 or not 0<args.first_frame_timeout<=600
            or not 0<args.disconnect_timeout<=600 or not 1<=args.max_runtime_seconds<=86400
            or args.launcher_pid is not None and args.launcher_pid<=0):
        parser.error('Invalid session identity or startup timeout')
    return supervise(args)


if __name__=='__main__':
    raise SystemExit(main())
