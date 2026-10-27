"""Keep one local GPU policy resident across authenticated RDP bridge leases."""
import copy
import ctypes
import importlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import uuid

from navigation_idle_recovery import GOAL_INTENTS
from stream_segments import EvidencePublicationError
from bridge_transport import is_transport_failure


def atomic_json(path, value):
    """Replace a local report/command atomically so readers never see partial JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
    try:
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                # Windows readers/scanners can briefly hold a file without delete sharing.
                if attempt == 5:
                    raise
                time.sleep(.02)
    finally:
        temporary.unlink(missing_ok=True)


def read_control_document(path, run_id):
    """Read one bounded run-bound command, including an optional immutable goal request."""
    try:
        with Path(path).open('rb') as stream:
            payload = stream.read(2049)
        if len(payload) > 2048:
            raise ValueError('Control file exceeds 2048 bytes')
        command = json.loads(payload)
        if (not isinstance(command, dict) or command.get('version') != 1
                or command.get('runId') != run_id or command.get('command') not in ('run', 'pause', 'stop')):
            raise ValueError('Expected this run ID and command run, pause, or stop')
        if 'goalRequestId' in command or 'goalEmbedding' in command or 'goalIntent' in command:
            request_id, embedding = command.get('goalRequestId'), command.get('goalEmbedding')
            if (not isinstance(request_id, str) or not re.fullmatch('[0-9a-f]{32}', request_id)
                    or not isinstance(embedding, str) or not embedding or '\0' in embedding
                    or not Path(embedding).is_absolute() or embedding.startswith('\\\\')):
                raise ValueError('A goal requires a unique 32-character request ID and an absolute local embedding path')
            if command.get('goalIntent', 'unspecified') not in GOAL_INTENTS:
                raise ValueError('Goal intent must be unspecified, stationary, or ground-navigation')
        return command, None
    except (OSError, ValueError, TypeError) as error:
        return None, str(error)


def read_command(path, run_id):
    """Keep the existing run/pause/stop reader compatible; invalid authority pauses."""
    document, error = read_control_document(path, run_id)
    return document['command'] if document else 'pause', error


class ResidentControl:
    """Poll local commands and write progress away from capture and inference threads."""
    def __init__(self, path, status_path, run_id):
        self.path, self.status_path, self.run_id = Path(path), Path(status_path), run_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents an old run's resume command from authorizing this run.
        with self.path.open('x', encoding='utf-8') as stream:
            json.dump({'version': 1, 'runId': run_id, 'command': 'run'}, stream)
        self._lock = threading.Lock()
        self._command, self._error = 'run', None
        self._epoch = 0
        self._goal_request = None
        self._goal_status, self._goal_error = None, None
        self._seen_goals = {}
        self._goal_version = 0
        self._applied_goal_id = None
        self._goal_metadata = None
        self._goal_intent = 'unspecified'
        # Only the serial policy thread owns this recovery latch across bridge leases.
        self.navigation_idle_recovery = None
        self._goal_events = []
        self._progress = {}
        self._closing = threading.Event()
        self.worker = threading.Thread(target=self._monitor, name='BetterGI-resident-control', daemon=True)
        self.worker.start()

    def snapshot(self):
        """Read an in-memory control state without filesystem work on the policy thread."""
        with self._lock:
            return self._effective_command(), self._goal_error or self._error

    def _effective_command(self):
        """A pending or failed goal cannot authorize the old policy, even after run."""
        if self._command == 'stop':
            return 'stop'
        return 'pause' if self._goal_status in ('pending', 'applying', 'failed') else self._command

    def goal_state(self):
        """Return immutable attribution and acknowledgement metadata without file IO."""
        with self._lock:
            return self._goal_state_locked()

    def goal_identity(self):
        """Read small per-tick attribution without copying embedding provenance or validation metadata."""
        with self._lock:
            return {'policyGoalVersion': self._goal_version, 'appliedGoalRequestId': self._applied_goal_id,
                    'goalIntent': self._goal_intent}

    def _goal_state_locked(self):
        """Keep acknowledgements and command state consistent in one status snapshot."""
        return {'controlEpoch': self._epoch, 'policyGoalVersion': self._goal_version,
                'appliedGoalRequestId': self._applied_goal_id,
                'goalRequestId': self._goal_request['requestId'] if self._goal_request else None,
                'goalRequestStatus': self._goal_status, 'goalError': self._goal_error,
                'goalMetadata': copy.deepcopy(self._goal_metadata), 'goalIntent': self._goal_intent}

    def set_initial_goal(self, metadata, intent='unspecified'):
        """Name the startup policy goal as version zero before any live goal is applied."""
        if intent not in GOAL_INTENTS:
            raise ValueError('Unknown initial goal intent')
        with self._lock:
            if self._goal_version == 0:
                self._goal_metadata = copy.deepcopy(metadata)
                self._goal_intent = intent

    def prediction_token(self):
        """Bind a prediction to the observed control generation and applied policy goal."""
        with self._lock:
            return self._epoch, self._goal_version, self._applied_goal_id, self._effective_command()

    def guarded_submit(self, expected_token, submit):
        """Check authority and perform only the supplied submission under the control lock.

        The callback must not call control methods: this is the existing plain
        Lock. It may retain request evidence and invoke its owned bridge only.
        A changed or paused token returns a proven pre-write refusal. Exceptions
        propagate after releasing the lock; reply interpretation stays outside.
        """
        with self._lock:
            current = self._epoch, self._goal_version, self._applied_goal_id, self._effective_command()
            if current != expected_token or current[3] != 'run':
                return False, None
            return True, submit()

    def begin_goal(self):
        """Claim a goal only on the serial policy thread, never in the monitor."""
        with self._lock:
            if self._command == 'stop' or self._goal_status != 'pending':
                return None
            self._goal_status = 'applying'
            return dict(self._goal_request)

    def finish_goal(self, request, metadata=None, error=None):
        """Acknowledge the exact request; newer requests and terminal stop retain priority."""
        with self._lock:
            if error is None:
                self._goal_version += 1
                self._applied_goal_id = request['requestId']
                self._goal_metadata = copy.deepcopy(metadata)
                self._goal_intent = request.get('goalIntent', 'unspecified')
            current = (self._goal_request and self._goal_request['requestId'] == request['requestId']
                       and self._goal_status == 'applying')
            if current:
                self._goal_status = 'failed' if error else 'applied'
                self._goal_error = str(error) if error else None
            event = dict(type='policyGoalChange', runId=self.run_id, requestId=request['requestId'],
                         goalEmbedding=request['embeddingPath'], policyGoalVersion=self._goal_version,
                         appliedGoalRequestId=self._applied_goal_id, status='failed' if error else 'applied',
                         goalIntent=request.get('goalIntent', 'unspecified'),
                         superseded=not current, error=str(error) if error else None,
                         goalMetadata=copy.deepcopy(metadata), clientTimeNs=time.perf_counter_ns())
            self._goal_events.append(event)
            return copy.deepcopy(event)

    def goal_events(self):
        """Copy sparse goal events for the final resident report."""
        with self._lock:
            return copy.deepcopy(self._goal_events)

    def _observe(self, document, error):
        """Reconcile one monitor read; each interruption invalidates older predictions."""
        with self._lock:
            if self._command == 'stop':
                return
            command = document['command'] if document else 'pause'
            if (command, error) != (self._command, self._error):
                self._epoch += 1
            self._command, self._error = command, error
            if command == 'stop' or not document or 'goalRequestId' not in document:
                return
            request_id, path = document['goalRequestId'], document['goalEmbedding']
            intent = document.get('goalIntent', 'unspecified')
            if self._goal_request and request_id == self._goal_request['requestId']:
                if path != self._goal_request['embeddingPath']:
                    if self._goal_error != 'A goal request ID cannot change its embedding path':
                        self._epoch += 1
                    self._goal_status, self._goal_error = 'failed', 'A goal request ID cannot change its embedding path'
                elif intent != self._goal_request['goalIntent']:
                    if self._goal_error != 'A goal request ID cannot change its intent':
                        self._epoch += 1
                    self._goal_status, self._goal_error = 'failed', 'A goal request ID cannot change its intent'
                return
            self._epoch += 1
            self._goal_request = {'requestId': request_id, 'embeddingPath': path, 'goalIntent': intent}
            if request_id in self._seen_goals:
                self._goal_status, self._goal_error = 'failed', 'A previous goal request ID cannot be replayed'
            else:
                self._seen_goals[request_id] = path
                self._goal_status, self._goal_error = 'pending', None

    def publish(self, **values):
        """Publish small progress metadata for the asynchronous status writer."""
        with self._lock:
            self._progress.update(values)

    def _monitor(self):
        while not self._closing.is_set():
            document, error = read_control_document(self.path, self.run_id)
            self._observe(document, error)
            with self._lock:
                status = dict(self._progress, version=1, runId=self.run_id,
                              command=self._effective_command(), requestedCommand=self._command,
                              controlError=self._goal_error or self._error, **self._goal_state_locked(),
                              updatedAtUnixMs=int(time.time()*1000))
            try:
                atomic_json(self.status_path, status)
            except OSError as error:
                with self._lock:
                    # A status-write failure must never undo the terminal stop latch.
                    if self._command != 'stop':
                        self._epoch += 1
                        self._command, self._error = 'pause', 'Cannot write status: ' + str(error)
            self._closing.wait(.1)

    def close(self):
        self._closing.set()
        self.worker.join(timeout=2)


def apply_pending_goal(control, policy, before_change):
    """Apply on the policy thread only after the caller releases its current input lease."""
    request = control.begin_goal()
    if request is None:
        return None
    # Release failures terminate the episode; continuing would leave input ownership uncertain.
    try:
        before_change()
    except Exception as error:
        control.finish_goal(request, error=error)
        raise
    try:
        if policy is None or not callable(getattr(policy, 'set_goal', None)):
            raise ValueError('The selected policy does not support live goal embeddings')
        policy.set_goal(request['embeddingPath'])
        return control.finish_goal(request, metadata=copy.deepcopy(policy.metadata.get('goal')))
    except Exception as error:
        # The old tensor may remain loaded, but run cannot authorize it after this failure.
        return control.finish_goal(request, error=error)


def control_module():
    """Reuse the existing PID/session/SID-authenticated RDP lifecycle client."""
    directory = str(Path(__file__).resolve().parents[1] / 'rdp-automation')
    if directory not in sys.path:
        sys.path.insert(0, directory)
    return importlib.import_module('rdp_control')


def require_current_rdp(session_id):
    """Refuse resident control on the console or in a different Windows session."""
    if os.name != 'nt':
        raise RuntimeError('Resident gameplay requires a Windows RDP process')
    actual = ctypes.c_ulong()
    if not ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(actual)):
        raise ctypes.WinError()
    if actual.value != session_id or not ctypes.windll.user32.GetSystemMetrics(0x1000):
        raise RuntimeError('Launch this client inside the exact requested RDP session')


def select_child(instances, session_id):
    """Select exactly one enabled RDP child, never an available console instance."""
    choices = [entry for entry in instances if entry.get('windowsSessionId') == session_id
               and entry.get('instanceType') == 'ChildSession' and entry.get('remoteDesktop') is True
               and entry.get('automationEnabled') is True]
    if len(choices) > 1:
        raise RuntimeError('Multiple enabled BetterGI children occupy the requested RDP session')
    return choices[0] if choices else None


def verify_bridge_identity(handle, process_id, session_id):
    """Authenticate the streaming pipe against the lifecycle instance just selected."""
    import msvcrt
    api = control_module().transport.WinPipeApi()
    native = msvcrt.get_osfhandle(handle.fileno())
    if api.server_pid(native) != process_id or api.server_session(native) != session_id:
        raise RuntimeError('Agent pipe does not belong to the selected RDP BetterGI process')
    api.verify_same_user(native)


def run_resident(args, load_policy, run_episode):
    """Own one bounded run, retaining weights/graphs through pause and bridge replacement."""
    require_current_rdp(args.rdp_session_id)
    from observation_profiles import LEGACY, validate_model_profile
    observation_profile = validate_model_profile(getattr(args, 'observation_profile', LEGACY), args.model)
    lifecycle = control_module()
    output = Path(args.output)
    run_id = uuid.uuid4().hex
    control = ResidentControl(args.control_file or str(output)+'.control.json', str(output)+'.status.json', run_id)
    summary = {'version': 1, 'runId': run_id, 'mode': 'resident-rdp', 'status': 'loading',
               'observationProfile': observation_profile,
               'controlFile': str(control.path.resolve()), 'windowsSessionId': args.rdp_session_id,
               'inputRequested': args.enable_input, 'modelLoads': 0, 'segments': [], 'acceptedInputActions': 0,
               'recordedBytes': 0, 'recordingBudgetExhausted': False, 'connectionErrors': [],
               'evidenceComplete': True, 'failedLeases': 0}
    episodes = output.with_name(output.stem + '-segments')
    unavailable_since = None
    previous_identity = None
    pending_start_identity = None
    try:
        control.publish(state='loading', inputRequested=args.enable_input)
        loading_started = time.monotonic()
        policy = load_policy(args)
        control.set_initial_goal(getattr(policy, 'metadata', {}).get('goal'), getattr(args, 'goal_intent', 'unspecified'))
        summary['modelLoadSeconds'] = time.monotonic()-loading_started
        summary['modelLoads'] = int(policy is not None)
        deadline = time.monotonic() + args.seconds
        summary['status'] = 'running'
        atomic_json(output, summary)
        while time.monotonic() < deadline:
            # Between actual bridge leases there is no held input; ordinary file
            # rollover remains inside run_episode and never reaches this loop.
            # This also applies queued goals while paused before the first connection.
            apply_pending_goal(control, policy, lambda: None)
            command, control_error = control.snapshot()
            if command == 'stop':
                summary['endReason'] = 'userStop'
                break
            if command == 'pause':
                control.publish(state='paused', reason=control_error or 'userPause')
                time.sleep(.1)
                continue
            child = select_child(lifecycle.discover()['instances'], args.rdp_session_id)
            if unavailable_since is not None and time.monotonic()-unavailable_since >= args.reconnect_timeout:
                raise RuntimeError('RDP bridge did not become available before reconnect timeout')
            current_identity = (child['processId'], child['instanceNonce']) if child else None
            # Reconcile a lost start acknowledgement through read-only identity/state.
            # A listening, unconnected stream may be joined; an active owner is never displaced.
            pending_listener = bool(child and current_identity == pending_start_identity
                                    and child.get('agentStreamState') == 'listening'
                                    and child.get('agentStreamRunning') is True
                                    and child.get('agentInputEnabled') is args.enable_input
                                    and child.get('agentObservationProfile', LEGACY) == observation_profile)
            if (child is None or child.get('runtimeRunning') is not True
                    or child.get('automationState') != 'game_ready'
                    or child.get('taskRunning') is True and not pending_listener):
                unavailable_since = unavailable_since or time.monotonic()
                if time.monotonic()-unavailable_since >= args.reconnect_timeout:
                    raise RuntimeError('RDP bridge did not become available before reconnect timeout')
                control.publish(state='waitingForBridge', reason='missingChildOrBusyRuntime')
                time.sleep(.5)
                continue
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                break
            # A fresh pipe/owner never inherits actions or temporal history from a prior lease.
            if policy is not None:
                policy.reset()
            if not pending_listener:
                try:
                    child = lifecycle.start_agent(child, min(15, max(1, remaining)), enable_input=args.enable_input,
                                                  observation_profile=observation_profile)
                except lifecycle.ControlError as error:
                    pending_start_identity = current_identity
                    unavailable_since = unavailable_since or time.monotonic()
                    summary['connectionErrors'] = (summary['connectionErrors'] + [str(error)])[-128:]
                    control.publish(state='waitingForBridge', reason='startOutcomeNeedsReconciliation')
                    time.sleep(.5)
                    continue
            pending_start_identity = None
            segment_args = copy.copy(args)
            segment_args.pipe = child['agentPipeName']
            segment_args.expected_process_id = child['processId']
            segment_args.expected_session_id = args.rdp_session_id
            segment_args.seconds = max(.01, deadline-time.monotonic())
            segment_args.lease_deadline = deadline
            number = len(summary['segments'])+1
            segment_args.segment_start_index = number
            segment_args.output = str(episodes / f'{number:05d}.json')
            segment_args.lease_output = str(episodes / f'lease-{number:05d}.json')
            segment_args.record_dir = str(Path(args.record_dir) / f'{number:05d}') if args.record_dir else None
            if segment_args.record_dir:
                remaining_mib = args.record_max_mib-summary['recordedBytes']/(2**20)
                if remaining_mib < 1:
                    segment_args.record_dir = None
                    summary['recordingBudgetExhausted'] = True
                else:
                    segment_args.record_max_mib = max(1, int(remaining_mib))
            if args.max_input_actions is not None:
                segment_args.max_input_actions = args.max_input_actions-summary['acceptedInputActions']
            control.publish(state='connecting', childProcessId=child['processId'], segment=number,
                            childReplaced=previous_identity is not None and previous_identity != current_identity)
            previous_identity = current_identity
            segment = {'number': number, 'processId': child['processId'], 'instanceNonce': child['instanceNonce'],
                       'report': segment_args.output}
            lease = None
            episode_error = None
            try:
                segment['exitCode'] = run_episode(segment_args, policy, control)
            except EvidencePublicationError as error:
                # Keep every accepted action/byte and unknown outcome from the
                # unpublished manifest. Never fall back to just the first part.
                lease = error.manifest
                episode_error = error
                segment.update(error=str(error), exitCode=1)
            except Exception as error:
                # Account the failed lease before deciding whether this exact failure permits retry.
                episode_error = error
                segment['error'] = str(error)
                segment['exitCode'] = 1
            if lease is None and Path(segment_args.lease_output).exists():
                lease = json.loads(Path(segment_args.lease_output).read_text(encoding='utf-8'))
            if lease is not None:
                for part in lease['segments']:
                    summary['segments'].append(dict(part, processId=child['processId'], instanceNonce=child['instanceNonce']))
                summary['acceptedInputActions'] += lease['acceptedInputActions']
                summary['recordedBytes'] += lease['recordedBytes']
                summary['recordingBudgetExhausted'] |= lease['recordingBudgetExhausted']
                if (lease.get('status') == 'failed' or segment['exitCode']
                        or any(part.get('exitCode') for part in lease['segments'])):
                    summary.update(evidenceComplete=False, failedLeases=summary['failedLeases']+1)
                segment['endReason'] = lease['endReason']
                if lease.get('unacknowledgedAction'):
                    summary['unacknowledgedAction'] = lease['unacknowledgedAction']
                if lease['framesReceived']:
                    unavailable_since = None
                if lease.get('evidenceError'):
                    raise RuntimeError('Resident evidence archive incomplete: ' + lease['evidenceError'])
                if lease.get('unacknowledgedAction'):
                    raise RuntimeError('Agent action acknowledgement was lost; run stopped without replay: '
                                       + lease['unacknowledgedAction'])
            elif Path(segment_args.output).exists():
                report = json.loads(Path(segment_args.output).read_text(encoding='utf-8'))
                segment.update(endReason=report.get('endReason'), framesReceived=report.get('framesReceived'),
                               acceptedInputActions=report.get('acceptedInputActions', 0))
                summary['acceptedInputActions'] += segment['acceptedInputActions']
                if segment.get('framesReceived', 0):
                    unavailable_since = None
            if lease is None:
                summary['segments'].append(segment)
                if segment['exitCode']:
                    summary.update(evidenceComplete=False, failedLeases=summary['failedLeases']+1)
            if lease is None and segment_args.record_dir and Path(segment_args.record_dir).exists():
                summary['recordedBytes'] += sum(path.stat().st_size for path in Path(segment_args.record_dir).iterdir()
                                                if path.is_file())
            atomic_json(output, summary)
            if episode_error is not None and not is_transport_failure(episode_error):
                raise episode_error
            lease_failed = (segment['exitCode'] or (lease is not None and
                (lease.get('status') == 'failed' or any(part.get('exitCode') for part in lease['segments']))))
            if lease_failed and episode_error is None:
                # A generic failed result is not evidence of a recoverable pipe disconnect.
                summary['endReason'] = segment.get('endReason') or 'error'
                break
            if args.max_input_actions is not None and summary['acceptedInputActions'] >= args.max_input_actions:
                summary['endReason'] = 'maxInputActions'
                break
            if segment.get('endReason') in ('userStop', 'hybridLegLimit'):
                summary['endReason'] = segment['endReason']
                break
            # Allow the previous TaskRunner owner to finish before rediscovery/start.
            time.sleep(.1)
        summary.setdefault('endReason', 'durationElapsed')
        summary['status'] = 'completed' if summary['evidenceComplete'] else 'failed'
        if not summary['evidenceComplete']:
            summary['error'] = 'One or more bridge leases or evidence segments failed; see segments'
    except Exception as error:
        summary.update(status='failed', error=str(error), endReason='error')
        raise
    finally:
        summary.update(control.goal_state(), goalChanges=control.goal_events())
        if summary['goalError']:
            summary.update(status='failed', error=summary['goalError'])
        control.publish(state=summary['status'], reason=summary.get('endReason'))
        try:
            atomic_json(output, summary)
        finally:
            control.close()
        atomic_json(str(output)+'.status.json', dict(summary, state=summary['status']))
    return 1 if summary['status'] == 'failed' else 0
