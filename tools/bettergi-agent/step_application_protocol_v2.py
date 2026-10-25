"""Strict queued native-50 wire grammar; selection requires a confirmed v2 channel.

No controller, scheduling, input or model operation lives here. The unchanged v1
coverage predicate checks the common application fields only after this module
has checked the exact v2 envelope and queue binding. No received wire version is
guessed, rewritten in place, or admitted through the v1 transport path.
"""
import hashlib
import math

import step_application_protocol as v1

VERSION = 2
MODE = 'native-single-50ms-queued-v2'
LINK_FIELDS = ('requestId', 'applicationSequence', 'submissionSha256')
BINDING_FIELDS = ('identity', 'requestId', 'submissionSha256', 'model',
                  'intervalCount', 'stepIndex', 'step', 'queueAfter')
REQUEST_FIELDS = {'version', 'command', 'sessionId', 'ownerEpoch', 'goalVersion',
                  'requestId', 'frameId', 'observedAtMs', 'expiresAtMs', 'modelId',
                  'steps', 'startBeforeMs', 'queueAfter'}
EXTENSIONS = {'stepApplication', 'stepApplicationsAck'}


def same(left, right):
    """Compare finite detached JSON with exact scalar types, including numeric tokens."""
    return v1.canonical(left) == v1.canonical(right)


def elapsed(value):
    """Validate a session-relative elapsed sample without converting it to QPC."""
    v1.require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
               'v2_elapsed')


def link(value, *, nullable=False):
    """A predecessor link is explicit null or the exact retained application identity."""
    if value is None and nullable:
        return
    v1.fields(value, LINK_FIELDS)
    v1.text(value['requestId'])
    v1.integer(value['applicationSequence'], 1, v1.OUTBOX_RECORDS)
    v1.digest(value['submissionSha256'])


def application_link(record):
    """Return detached public linkage, never a native token or a history-commit claim."""
    return dict(requestId=record['binding']['requestId'],
                applicationSequence=record['sequence'],
                submissionSha256=record['binding']['submissionSha256'])


def configuration(value):
    """Validate exact v2 mode before reusing the unchanged common v1 lease grammar."""
    v1.require(type(value) is dict and type(value.get('version')) is int
               and value['version'] == VERSION and value.get('mode') == MODE, 'v2_mode')
    common = dict(value, version=v1.VERSION, mode=v1.MODE)
    v1.configuration(common)
    return v1.canonical(value, 4096)


def _common_binding(value):
    """Project only the already-validated version extension for common coverage checks."""
    return {name: value[name] for name in BINDING_FIELDS if name != 'queueAfter'}


def binding(value, config):
    """Keep all original identity/profile/step checks and the explicit typed queue link."""
    configuration(config)
    v1.fields(value, BINDING_FIELDS)
    link(value['queueAfter'], nullable=True)
    v1.binding(_common_binding(value), config)
    v1.canonical(value, 3072)


def validate_submission(request):
    """Require the original fixed interval, mandatory source deadline and explicit queueAfter."""
    v1.fields(request, REQUEST_FIELDS)
    v1.require(type(request['version']) is int and request['version'] == 1
               and request['command'] == 'action', 'submission_command')
    for name in ('sessionId', 'ownerEpoch', 'requestId', 'modelId'):
        v1.text(request[name])
    for name in ('goalVersion', 'frameId'):
        v1.integer(request[name])
    for name in ('observedAtMs', 'expiresAtMs', 'startBeforeMs'):
        elapsed(request[name])
    link(request['queueAfter'], nullable=True)
    v1.require(type(request['steps']) is list and len(request['steps']) == 1, 'single_interval')
    v1.step(request['steps'][0])
    v1.require(not set(request['steps'][0]['keys']) & {'SHIFT', 'CONTROL', 'ESC'}, 'alias_authority')
    return v1.canonical(request, 16384)


def make_binding(decision, request, proposal_steps, model_contract):
    """Hash the actual canonical action including queueAfter; preserve original step bytes."""
    validate_submission(request)
    common = v1.decode(v1.make_binding(decision, request, proposal_steps, model_contract), 3072)
    common['queueAfter'] = request['queueAfter']
    return v1.canonical(common, 3072)


def validate_envelope(request):
    """Require an explicitly versioned v2 extension and byte-identical canonical action."""
    v1.require(type(request) is dict and 'stepApplication' in request, 'submission_extension')
    ext = request['stepApplication']
    v1.fields(ext, ('version', 'submissionJson', 'binding'))
    v1.require(type(ext['version']) is int and ext['version'] == VERSION, 'extension_version')
    v1.require(type(ext['submissionJson']) is str and ext['submissionJson'].isascii(), 'submission_ascii')
    raw = ext['submissionJson'].encode('ascii')
    original = v1.decode(raw, 16384)
    v1.require(validate_submission(original) == raw, 'submission_not_canonical')
    actual = {name: value for name, value in request.items() if name not in EXTENSIONS}
    v1.require(validate_submission(actual) == raw, 'submission_wire_mismatch')
    v1.fields(ext['binding'], BINDING_FIELDS)
    v1.require(same(ext['binding']['queueAfter'], original['queueAfter']), 'submission_queue_mismatch')
    v1.require(ext['binding']['submissionSha256'] == hashlib.sha256(raw).hexdigest(), 'submission_digest')
    return raw


def validate_record(value, config):
    """Reuse exact stock call/held/backend coverage after checking all v2-only authority."""
    configuration(config)
    v1.require(type(value) is dict and type(value.get('version')) is int
               and value['version'] == VERSION, 'record_version')
    binding(value['binding'], config)
    v1.integer(value['sequence'], 1, v1.OUTBOX_RECORDS)
    # validate_record retains its exact field census; no unknown common field is dropped.
    common = dict(value, version=v1.VERSION, binding=_common_binding(value['binding']))
    v1.validate_record(common, config)
    return v1.canonical(value, v1.RECORD_BYTES)


def admission(value, config, bound):
    """Validate one detached schedule; predecessor and actual request joins occur in the ledger."""
    v1.fields(value, ('version', 'channelId', 'requestId', 'state', 'queueAfter',
                     'admittedAtMs', 'scheduledStartMs', 'scheduledEndMs'))
    v1.require(type(value['version']) is int and value['version'] == VERSION
               and value['channelId'] == config['channelId']
               and value['requestId'] == bound['requestId'], 'v2_admission_identity')
    v1.require(value['state'] in ('active', 'queued'), 'v2_admission_state')
    link(value['queueAfter'], nullable=True)
    v1.require(same(value['queueAfter'], bound['queueAfter']), 'v2_admission_link')
    for name in ('admittedAtMs', 'scheduledStartMs', 'scheduledEndMs'):
        elapsed(value[name])
    v1.require(same(value['scheduledEndMs'], value['scheduledStartMs'] + 50), 'v2_fixed_end')
    if bound['queueAfter'] is None:
        v1.require(value['state'] == 'active' and same(value['admittedAtMs'], value['scheduledStartMs']),
                   'v2_initial_schedule')
    else:
        v1.require(value['state'] == 'queued' and value['admittedAtMs'] < value['scheduledStartMs'],
                   'v2_queued_schedule')
    return v1.canonical(value, 2048)


def validate_terminal(value, config):
    """A no-release terminal is exclusively the explicit v2 successor handoff grammar."""
    v1.fields(value, ('version', 'channelId', 'binding', 'applicationSequences', 'status',
                     'reason', 'publicationTicks', 'legacyEndedAtMs', 'releaseOutcome', 'transition'))
    v1.require(type(value['version']) is int and value['version'] == VERSION, 'terminal_version')
    binding(value['binding'], config)
    common = {name: item for name, item in value.items() if name != 'transition'}
    common.update(version=v1.VERSION, binding=_common_binding(value['binding']))
    v1.validate_terminal(common, config)
    for sequence in value['applicationSequences']:
        v1.integer(sequence, 1, v1.OUTBOX_RECORDS)
    transition = value['transition']
    if transition is None:
        v1.require(value['reason'] != 'horizon_handoff', 'handoff_transition_missing')
    else:
        v1.require(value['status'] == 'completed' and value['reason'] == 'horizon_handoff'
                   and value['releaseOutcome'] == 'not_requested'
                   and len(value['applicationSequences']) == 1, 'handoff_terminal_kind')
        v1.fields(transition, ('successor', 'boundaryMs', 'successorScheduledEndMs',
                              'dispatchCheckedAtMs', 'successorCallsReturnedTicks'))
        link(transition['successor'])
        for name in ('boundaryMs', 'successorScheduledEndMs', 'dispatchCheckedAtMs'):
            elapsed(transition[name])
        v1.integer(transition['successorCallsReturnedTicks'], config['sessionOriginTicks'])
    return v1.canonical(value, 4096)


def reservation_byte_bound(bound, config, before, sequence):
    """The existing conservative application witness includes the full v2 binding unchanged."""
    binding(bound, config)
    v1.integer(sequence, 1, v1.OUTBOX_RECORDS)
    return v1.reservation_byte_bound(bound, config, before, sequence)
