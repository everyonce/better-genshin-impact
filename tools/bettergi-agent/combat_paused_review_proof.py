"""Pure joins for a reviewed world image kept behind inventory pause until combat is ready.

This module performs no filesystem, process, model or game operations. Callers
must supply exact bytes and independently replay each native UI proof. Legacy
combat bindings and live-frame guards retain their existing meanings.
"""
import copy
import hashlib
import json
import re
from pathlib import Path

from combat_trial_guard import FOUR_SCOPE, bind_review, canonical, combat_scope, trial_policy, validated_trial_policy


# Distinct names prevent an old post-resume review from acquiring the new ordering.
CAPTURE_REQUEST_KIND = 'combat-paused-review-capture-request-v1'
CAPTURE_KIND = 'combat-paused-review-capture-v1'
PAUSE_KIND = 'combat-native-scene-paired-pause-v1'
PREPARATION_KIND = 'combat-trial-reviewed-paused-preparation-v1'
PLAN_KIND = 'combat-trial-paused-review-plan-v1'
LINK_KIND = 'paused-review-prepared-combat-authority-v1'
ARM_KIND = 'combat-paused-review-arm-v1'
PRECHECK_KIND = 'combat-paused-review-ready-to-resume-v1'
RESUME_KIND = 'combat-paused-review-final-resume-v1'
WRAPPER_KIND = 'combat-trial-reviewed-paused-wrapper-v1'
RECORD_NAMES = ('captureRequest', 'capture', 'pairedPause')
COMMON_PLAN_FIELDS = ('runId', 'directory', 'owner', 'ownerFile', 'ownerSha256', 'resources',
                      'checkpointSha256', 'checkpointStamp', 'sourceFiles', 'workerRuntime', 'modelConfiguration')
PRECHECK_METADATA_NAMES = ('preparation.json', 'prepared.json', 'plan.json', 'ARM-REQUESTED.json', 'ARM.json',
                          'ARM-CONSUMED.json', 'CONSUMED.json', 'WORKER-CONSUMED.json')


def require(value, message):
    """Refuse a missing or contradictory phase rather than inferring its occurrence."""
    if not value:
        raise ValueError(message)


def sha(raw):
    """Hash original bytes without normalizing a submitted record."""
    return hashlib.sha256(raw).hexdigest()


def document(raw):
    """Read only a bounded exact JSON object with no duplicate fields or nonfinite constants."""
    require(type(raw) is bytes and 0 < len(raw) <= 16 * 1024 * 1024, 'Invalid paused-review bytes')
    def pairs(rows):
        """Keep duplicate JSON keys from obscuring the phase that was actually declared."""
        value = {}
        for key, item in rows:
            require(key not in value, 'Duplicate paused-review field')
            value[key] = item
        return value
    def invalid(value):
        """Nonfinite JSON values cannot represent clocks or authority."""
        raise ValueError('Invalid paused-review JSON constant: ' + value)
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    require(isinstance(value, dict), 'Expected paused-review object')
    return value


def positive_clock(value):
    """Reject bools, floats, zero and negative phase clocks."""
    return type(value) is int and value > 0


def valid_sha(value):
    """Require a complete lowercase digest rather than a path-derived identity."""
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None


def version_one(*records):
    """A boolean must not be accepted as a version number in the separate new protocol."""
    return all(type(record.get('version')) is int and record['version'] == 1 for record in records)


def outer_health_policy():
    """Preserve the previously named original-baseline review policy exactly."""
    return dict(version=2, kind='paused-review-health-80pct-max2pp-loss-v2',
        minimumPausedHealthPercent=80, minimumReviewedHealthPercent=80,
        maximumPreReviewLossPercent=2, requireSameMaximum=True, allowHealthIncrease=False,
        combatBaseline='actualReviewedHealth')


def validate_baseline(health, maximum):
    """Use the inspected pause before capture, never the later paired pause's health."""
    require(type(health) is int and type(maximum) is int and 0 < health <= maximum
        and health * 100 >= maximum * 80, 'Original paused baseline must remain at least 80 percent')


def validate_review_health(baseline, maximum, health, reviewed_maximum):
    """Allow the unchanged two-point loss only from original baseline to actual reviewed pixels."""
    validate_baseline(baseline, maximum)
    require(type(health) is int and type(reviewed_maximum) is int and reviewed_maximum == maximum
        and 0 < health <= baseline and health * 100 >= maximum * 80
        and (baseline - health) * 100 <= maximum * 2, 'Paused-review original-baseline health changed')


def validate_capture(request_raw, captured_raw, scene_blobs, owner):
    """Bind a real nativeScene and its source clock to the pre-capture baseline request."""
    request, captured = document(request_raw), document(captured_raw)
    require(set(scene_blobs) == {'plan', 'scene', 'sidecar', 'image'}, 'Incomplete native scene bytes')
    plan, scene, sidecar = (document(scene_blobs[name]) for name in ('plan', 'scene', 'sidecar'))
    require(version_one(request, captured)
        and request.get('kind') == CAPTURE_REQUEST_KIND and captured.get('kind') == CAPTURE_KIND
        and isinstance(request.get('captureId'), str) and re.fullmatch('[a-f0-9]{32}', request['captureId'])
        and captured.get('captureId') == request['captureId'] and captured.get('captureRequestSha256') == sha(request_raw)
        and request.get('owner') == captured.get('owner') == owner
        and request.get('sceneDirectory') == captured.get('sceneDirectory'), 'Native capture phase identity changed')
    require(canonical(request.get('outerHealthPolicy')) == canonical(outer_health_policy()), 'Outer review health policy changed')
    validate_baseline(request.get('baselineHealth'), request.get('maximumHealth'))
    require(plan.get('owner') == owner and plan.get('enableInput') is False and plan.get('modelLoaded') is False
        and scene.get('status') == 'completed' and scene.get('inputEnabled') is False and scene.get('modelLoaded') is False
        and scene.get('ownerIdleMinimizedAfter') is True, 'Capture is not an input-disabled retired nativeScene')
    references = captured.get('evidence')
    require(isinstance(references, dict) and set(references) == set(scene_blobs)
        and all(isinstance(references[name], dict) and references[name].get('sha256') == sha(raw)
                and isinstance(references[name].get('path'), str) for name, raw in scene_blobs.items()),
        'Captured native bytes changed')
    image_name = captured.get('imageName')
    directory = Path(request['sceneDirectory'])
    require(isinstance(image_name, str) and image_name == Path(image_name).name and image_name.endswith('.png')
        and all(references[name]['path'] == str(directory / filename) for name, filename in
                dict(plan='plan.json', scene='result.json', image=image_name,
                     sidecar=str(Path(image_name).with_suffix('.json'))).items()), 'Capture paths changed their native scene namespace')
    require(sidecar.get('frameId') == scene.get('qualifiedImageFrameId') == captured.get('frameId')
        and type(captured.get('frameId')) is int and captured['frameId'] > 0
        and sha(scene_blobs['image']) == sidecar.get('imageSha256') == scene.get('selectedImageSha256')
        and scene.get('selectedImageName') == captured.get('imageName')
        and sidecar.get('sourceFrame') == captured.get('sourceFrame')
        and sidecar.get('sourceTimestampKind') == 'wgc_reported_compositor_qpc', 'Captured image/source join changed')
    source = (captured.get('sourceFrame') or {}).get('timestamp100ns')
    require(all(positive_clock(value) for value in (source, request.get('createdAtUnixNs'), request.get('createdAtClientNs'),
        captured.get('completedAtUnixNs'), captured.get('completedAtClientNs')))
        and request['createdAtClientNs'] <= source * 100 <= captured['completedAtClientNs']
        and request['createdAtUnixNs'] <= captured['completedAtUnixNs'], 'Native capture clock preceded its baseline phase')
    return request, captured


def bind_pause_chain(record_blobs, scene_blobs, owner, baseline_proof, pause_proof, review_bytes=None):
    """Join original baseline, actual capture, later positive pause and an optional real human review."""
    require(set(record_blobs) == set(RECORD_NAMES), 'Incomplete capture/pause chain')
    request, captured = validate_capture(record_blobs['captureRequest'], record_blobs['capture'], scene_blobs, owner)
    paired = document(record_blobs['pairedPause'])
    require(version_one(paired) and paired.get('kind') == PAUSE_KIND
        and paired.get('captureId') == request['captureId'] and paired.get('owner') == owner
        and paired.get('captureRequestSha256') == sha(record_blobs['captureRequest'])
        and paired.get('captureSha256') == sha(record_blobs['capture'])
        and (request.get('baselinePause') or {}).get('proof') == baseline_proof
        and (paired.get('pause') or {}).get('proof') == pause_proof
        and request['baselinePause']['directory'] != paired['pause']['directory'], 'Original baseline and paired pause were substituted')
    require(baseline_proof.get('operation') == pause_proof.get('operation') == 'pause'
        and baseline_proof.get('owner') == pause_proof.get('owner') == owner
        and baseline_proof.get('sourceFiles') == pause_proof.get('sourceFiles'), 'Paired pause changed native owner or source')
    require(all(positive_clock(value) for value in (baseline_proof.get('cleanupAcknowledgedAtUnixNs'),
        pause_proof.get('cleanupAcknowledgedAtUnixNs'), paired.get('pausedAtUnixNs'), paired.get('pausedAtClientNs')))
        and baseline_proof['cleanupAcknowledgedAtUnixNs'] <= request['createdAtUnixNs']
        and captured['completedAtUnixNs'] <= pause_proof['transition']['requestCreatedAtUnixMs'] * 1_000_000
        and pause_proof['cleanupAcknowledgedAtUnixNs'] <= paired['pausedAtUnixNs']
        and captured['completedAtClientNs'] < paired['pausedAtClientNs'], 'Capture was not followed by this positive pause')
    if review_bytes is not None:
        review = document(review_bytes)
        require(positive_clock(review.get('reviewedAtUnixNs')) and review['reviewedAtUnixNs'] >= paired['pausedAtUnixNs'],
                'Actual review preceded the completed paired pause')
        validate_review_health(request['baselineHealth'], request['maximumHealth'],
                               review.get('inspectedHealth'), review.get('inspectedMaximumHealth'))
    result = dict(captureId=request['captureId'], baselineHealth=request['baselineHealth'], maximumHealth=request['maximumHealth'],
        originalSceneDeadlineClientNs=captured['sourceFrame']['timestamp100ns'] * 100 + 120_000_000_000,
        sourceFrame=copy.deepcopy(captured['sourceFrame']), pairedPausedAtUnixNs=paired['pausedAtUnixNs'],
        outerHealthPolicy=outer_health_policy(), recordSha256={name: sha(raw) for name, raw in record_blobs.items()})
    if review_bytes is not None:
        result['reviewedAtUnixNs'] = review['reviewedAtUnixNs']
    return result


def bind_reviewed_pause(evidence_blobs, record_blobs, owner, baseline_proof, pause_proof):
    """Keep the existing nativeScene binder and add only the new explicit paused chronology."""
    names = ('review', 'plan', 'scene', 'sidecar', 'image', 'goal')
    require(set(evidence_blobs) == set(names), 'Incomplete paused combat review')
    binding = bind_review(*(evidence_blobs[name] for name in names))
    require(combat_scope(binding) == FOUR_SCOPE and binding['owner'] == owner, 'Paused combat scope or owner changed')
    chain = bind_pause_chain(record_blobs, {name: evidence_blobs[name] for name in ('plan', 'scene', 'sidecar', 'image')},
                             owner, baseline_proof, pause_proof, evidence_blobs['review'])
    require(binding['reviewedFrame']['sourceFrame'] == chain['sourceFrame'], 'Reviewed source differs from the paused capture')
    return binding, chain


def validate_review_paths(evidence, record_blobs):
    """Retain the actual native capture originals, not detached replacements with copied bytes."""
    captured = document(record_blobs['capture'])
    require(all(evidence[name]['path'] == captured['evidence'][name]['path']
        and evidence[name]['sha256'] == captured['evidence'][name]['sha256']
        for name in ('plan', 'scene', 'sidecar', 'image')), 'Reviewed originals differ from the paired native capture')


def validate_preparation(preparation, folder):
    """A reviewed preparation still cannot select input-enabled model loading."""
    require(version_one(preparation) and preparation.get('kind') == PREPARATION_KIND
        and preparation.get('directory') == str(folder) and combat_scope(preparation) == FOUR_SCOPE
        and isinstance(preparation.get('runId'), str) and re.fullmatch('[a-f0-9]{32}', preparation['runId'])
        and preparation.get('inputEnabled') is False and preparation.get('attacksAllowed') is False
        and 'binding' not in preparation and 'policy' not in preparation
        and preparation.get('maximumHostSeconds') == 90 and preparation.get('maximumReviewAgeSeconds') == 120
        and preparation.get('maximumPauseProofAgeSeconds') == 30
        and preparation.get('loadingPauseVerification') == 'native-input-disabled-inventory-probe-v1'
        and isinstance(preparation.get('workerRuntime'), dict) and isinstance(preparation.get('reviewedCombat'), dict)
        and isinstance(preparation.get('pausedReview'), dict)
        and positive_clock(preparation.get('createdAtUnixNs')) and positive_clock(preparation.get('createdAtClientNs')),
        'Invalid reviewed zero-input preparation')
    validated_trial_policy(preparation['reviewedCombat']['binding'])
    return preparation


def prepared_link(preparation_sha, prepared_sha, worker, request_id, chain):
    """Name only already-established authority; a future resume is never fabricated in ARM."""
    return dict(kind=LINK_KIND, preparationSha256=preparation_sha, preparedSha256=prepared_sha,
        worker=copy.deepcopy(worker), armRequestId=request_id,
        captureId=chain['captureId'], pausedReviewSha256=sha(canonical(chain)))


def validate_plan(plan, preparation, link):
    """Require exact preparation equality under a separately named pre-resume plan format."""
    require(version_one(plan) and plan.get('kind') == PLAN_KIND
        and combat_scope(plan) == FOUR_SCOPE and canonical(plan.get('policy')) == canonical(validated_trial_policy(plan.get('binding')))
        and plan.get('maximumHostSeconds') == 90 and plan.get('maximumReviewAgeSeconds') == 120
        and plan.get('recordingMaximumBytes') == 160 * 1024 * 1024
        and all(canonical(plan.get(name)) == canonical(preparation.get(name)) for name in COMMON_PLAN_FIELDS)
        and plan.get('binding') == preparation['reviewedCombat']['binding']
        and plan.get('evidence') == preparation['reviewedCombat']['evidence']
        and plan.get('preparedPolicy') == link and plan.get('pausedReview') == preparation['pausedReview'],
        'Paused-review combat plan changed its preparation or bounded authority')


def validate_precheck(prechecked, plan, plan_sha, preparation_sha, ready_sha, arm_sha, worker, claim):
    """Bind worker-authored readiness to the exact closed precheck and original lifetime."""
    require(version_one(prechecked) and prechecked.get('kind') == PRECHECK_KIND
        and prechecked.get('runId') == plan['runId'] and prechecked.get('planSha256') == plan_sha
        and prechecked.get('preparationSha256') == preparation_sha and prechecked.get('preparedSha256') == ready_sha
        and prechecked.get('armSha256') == arm_sha and prechecked.get('worker') == worker
        and prechecked.get('owner') == plan['owner'] and prechecked.get('hostClaim') == claim
        and prechecked.get('inputEnabled') is False and prechecked.get('listenerCreated') is False
        and prechecked.get('originalSceneDeadlineClientNs') == plan['pausedReview']['chain']['originalSceneDeadlineClientNs']
        and valid_sha(prechecked.get('verifiedInputsSha256'))
        and positive_clock(prechecked.get('checkedAtUnixNs')) and positive_clock(prechecked.get('checkedAtClientNs'))
        and positive_clock(claim.get('startedAtClientNs'))
        and claim['startedAtClientNs'] <= prechecked['checkedAtClientNs']
            < min(prechecked['originalSceneDeadlineClientNs'], claim['startedAtClientNs'] + 90_000_000_000),
        'Ready-to-resume record changed worker, inputs or original bounds')


def validate_final_resume(resumed, resume_proof, prechecked, prechecked_sha, plan, preparation, worker, now_unix_ns=None, now_client_ns=None):
    """Accept exactly the qualified Escape after paused precheck, never an earlier resume."""
    require(version_one(resumed) and resumed.get('kind') == RESUME_KIND
        and resumed.get('runId') == plan['runId'] and resumed.get('precheckedSha256') == prechecked_sha
        and resumed.get('planSha256') == prechecked['planSha256'] and resumed.get('armSha256') == prechecked['armSha256']
        and resumed.get('worker') == worker and resumed.get('owner') == plan['owner']
        and resumed.get('inputEnabled') is False and resumed.get('originalSceneDeadlineClientNs') == prechecked['originalSceneDeadlineClientNs']
        and resumed.get('hostClaim') == prechecked['hostClaim']
        and (resumed.get('resume') or {}).get('proof') == resume_proof
        and resume_proof.get('operation') == 'resume' and resume_proof.get('owner') == plan['owner']
        and resume_proof.get('sourceFiles') == preparation['pause']['proof']['sourceFiles'],
        'Final resume changed its prechecked worker, native source or authority')
    require(all(positive_clock(value) for value in (resumed.get('resumedAtUnixNs'), resumed.get('resumedAtClientNs')))
        and resume_proof['transition']['requestCreatedAtUnixMs'] * 1_000_000 >= prechecked['checkedAtUnixNs']
        and resumed['resumedAtUnixNs'] >= resume_proof['cleanupAcknowledgedAtUnixNs']
        and resumed['resumedAtClientNs'] > prechecked['checkedAtClientNs']
        and resumed['resumedAtClientNs'] < min(prechecked['originalSceneDeadlineClientNs'],
            prechecked['hostClaim']['startedAtClientNs'] + 90_000_000_000), 'Final resume preceded readiness or expired original budget')
    if now_unix_ns is not None:
        require(0 <= now_unix_ns - resume_proof['terminalTimestampUnixMs'] * 1_000_000 <= 30_000_000_000
            and resumed['resumedAtUnixNs'] <= now_unix_ns, 'Final native resume is stale or future-dated')
    if now_client_ns is not None:
        require(resumed['resumedAtClientNs'] <= now_client_ns < prechecked['originalSceneDeadlineClientNs'],
                'Final resume source budget expired')


def prechecked_inputs(preparation, plan, model_preparation, metadata):
    """Describe the complete immutable census for both live rereads and archive-only replay."""
    require(set(metadata) == set(PRECHECK_METADATA_NAMES), 'Incomplete precheck metadata inventory')
    expected = {}
    def add(name, pin):
        """Refuse conflicting pins when independent proof phases share an original dependency."""
        require(isinstance(name, str) and name and valid_sha(pin)
            and (name not in expected or expected[name] == pin), 'Conflicting prechecked input hashes')
        expected[name] = pin
    for records in (plan['evidence'], preparation['pausedReview']['records']):
        for record in records.values():
            add(record['path'], record['sha256'])
            add(record['retained'], record['sha256'])
    for record in (preparation['pause'], preparation['pausedReview']['baselinePause'], model_preparation['inventoryProbe']):
        require(set(record['retained']) == set(record['proof']['files']), 'Incomplete prechecked native proof')
        for original, pin in record['proof']['files'].items():
            add(original, pin)
            add(record['retained'][original], pin)
    for record in metadata.values():
        require(set(record) == {'path', 'sha256'}, 'Unexpected precheck metadata record')
        add(record['path'], record['sha256'])
    return expected


class PrecheckedAdmission:
    """Keep actual worker-validated input digests in memory; disk readiness cannot construct authority."""
    def __init__(self, plan, prechecked, prechecked_sha, expected_inputs):
        """Retain detached results only after the caller finishes all paused validations."""
        require(isinstance(expected_inputs, dict) and expected_inputs
            and all(isinstance(name, str) and valid_sha(pin) for name, pin in expected_inputs.items())
            and sha(canonical(expected_inputs)) == prechecked.get('verifiedInputsSha256'), 'Incomplete private precheck inputs')
        self.plan = copy.deepcopy(plan)
        self.prechecked = copy.deepcopy(prechecked)
        self.prechecked_sha = prechecked_sha
        self.expected_inputs = copy.deepcopy(expected_inputs)
        self.consumed = False

    def compare(self, actual_inputs):
        """Require a fresh exact byte-hash census, never a path/mtime cache or boolean."""
        require(not self.consumed and actual_inputs == self.expected_inputs, 'Prechecked immutable inputs changed')

    def consume(self):
        """One final admission attempt retires this in-memory capability even if native start fails."""
        require(not self.consumed, 'Paused-review admission was already consumed')
        self.consumed = True
