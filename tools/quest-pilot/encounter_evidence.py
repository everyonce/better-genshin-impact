"""Archive receipt-selected native encounter captures while an owned route leg is current."""
import hashlib
import json
from pathlib import Path
import tempfile
import zlib


MAX_FRAMES = 16
MAX_BYTES = 32 * 1024 * 1024
MAX_JSON = 1024 * 1024
MAX_ISSUES = 16


def _read_native(root, path, budget):
    """Read one immutable native file below the validated pilot root, within the byte budget."""
    if path.resolve(strict=True) != path or not path.is_relative_to(root) or not path.is_file():
        raise ValueError('unexpected native file location')
    expected_size = path.stat().st_size
    if expected_size <= 0 or expected_size > budget:
        raise ValueError('file is empty or exceeds the byte budget')
    with path.open('rb') as handle:
        content = handle.read(expected_size + 1)
    if len(content) != expected_size:
        raise ValueError('file size changed during capture')
    return content


def _is_png(picture):
    """Check PNG chunk lengths and CRCs before presenting an image as reproducible evidence."""
    if not picture.startswith(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'):
        return False
    view = memoryview(picture)
    pos = 8
    image_data = False
    while pos + 12 <= len(view):
        size = int.from_bytes(view[pos:pos + 4], 'big')
        end = pos + 8 + size
        if end + 4 > len(view) or zlib.crc32(view[pos + 4:end]) != int.from_bytes(view[end:end + 4], 'big'):
            return False
        kind = view[pos + 4:pos + 8]
        if kind == b'IDAT' and size:
            image_data = True
        if kind == b'IEND':
            return image_data and size == 0 and end + 4 == len(view)
        pos = end + 4
    return False


def _selected(request, receipt, rewards):
    """Select bounded combat action pairs, verified reward evidence and named dialogue transitions."""
    result = receipt['details']['result']
    if request['mission'] == 'dialogue':
        if result.get('talkTo', request['talkTo']) != request['talkTo']:
            raise ValueError('dialogue speaker differs from request')
        for role, key in [('npc-selected', 'interactionFrameId'), ('npc-greeting', 'greetingFrameId'),
                          ('npc-menu', 'menuFrameId'),
                          ('npc-world-return', 'worldFrameId')]:
            if result.get(key) is not None:
                yield role, result[key]
        farewell = result.get('farewell')
        if isinstance(farewell, dict) and farewell.get('frameId') is not None:
            yield 'npc-farewell', farewell['frameId']
        return
    if result.get('nativeAttempted') is not True:
        return
    # Save the overall pair and proven reward before spending space on individual rotations.
    for role, key in [('combat-before', 'beforeFrameId'), ('combat-after', 'afterFrameId')]:
        if result.get(key) is not None:
            yield role, result[key]
    for reward in rewards:
        if reward.get('requestId') == request['id']:
            if reward.get('attackFrameId') != result.get('beforeFrameId') or not isinstance(reward.get('rewardText'), str):
                raise ValueError('reward differs from the combat request')
            yield 'combat-reward', reward['rewardFrameId']
    for i, chunk in enumerate(result.get('chunks', [])[:8]):
        if chunk.get('nativeReturned') is True and chunk.get('actionId') == f"{request['id']}:rotation:{i}":
            for role, key in [('before', 'beforeFrameId'), ('after', 'afterFrameId')]:
                if chunk.get(key) is not None:
                    yield f'rotation-{i}-{role}', chunk[key]


class EncounterArchive:
    """Maintain one byte and frame budget across every leg of a launcher instance."""

    def __init__(self, pilot, output, command, save_manifest):
        self.pilot = pilot.resolve(strict=True)
        self.output = output.resolve(strict=True)
        self.command = command
        self.save_manifest = save_manifest
        self.revision = 0
        self.persisted = -1
        self.summary = dict(maxFrames=MAX_FRAMES, maxBytes=MAX_BYTES, bytes=0, frames=[], issues=[], skipped=0)
        self.saved = {}
        self.reviewed = {}
        self.last_snapshot = None

    def issue(self, leg, reason, request_id=None, frame_id=None):
        """Limit diagnostic size even when many retained files have already expired."""
        self.revision += 1
        self.summary['skipped'] += 1
        if len(self.summary['issues']) < MAX_ISSUES:
            self.summary['issues'].append(dict(leg=leg, requestId=request_id, frameId=frame_id, reason=str(reason)[:180]))

    def poll(self, progress, session, leg):
        """Sample only changes to this leg's progress, including its last publication before retirement."""
        try:
            info = progress.stat()
            snapshot = (leg, info.st_size, info.st_mtime_ns)
            if self.last_snapshot == snapshot:
                return
            if info.st_size > 32 * 1024 * 1024:
                raise ValueError('canonical progress exceeds evidence reader limit')
            with progress.open('rb') as handle:
                content = handle.read(info.st_size + 1)
            if len(content) != info.st_size:
                return
            report = json.loads(content)
            self.last_snapshot = snapshot
            self.capture_leg(report, session, leg)
            if self.revision != self.persisted:
                manifest = self.output / 'encounter-evidence.json'
                if any(p.resolve() != p for p in (manifest, manifest.with_name(manifest.name + '.tmp'))):
                    raise ValueError('unexpected evidence manifest location')
                self.save_manifest(manifest, self.summary)
                self.persisted = self.revision
        except FileNotFoundError:
            pass  # The controller has yet to publish its first progress file.
        except Exception as exc:
            self.issue(leg, exc)

    def capture_leg(self, report, session, leg):
        """Join only settled, scoped requests from this worker's own native session."""
        if report.get('session') != session:
            self.issue(leg, 'route session mismatch')
            return
        for record in report.get('records', []):
            rid = None
            try:
                req = record['request']
                if not (req.get('mission') == 'dialogue' and req.get('talkTo')
                        or req.get('mission') == 'questStep' and req.get('step') in ('actTwoFieldCombat', 'actTwoNativeCombat')):
                    continue
                if req.get('session') != session:
                    raise ValueError('request session differs from route session')
                receipt_path = self.command.request_receipt_path(self.pilot, session, req['id'])
                rid = req['id']  # Validated generated identifier; safe to include in diagnostics.
                rewards = [r for r in report.get('fieldCombatRewards', []) if r.get('requestId') == rid]
                reward_frames = tuple(r.get('rewardFrameId') for r in rewards)
                if self.reviewed.get((leg, rid)) == reward_frames:
                    continue
                self.reviewed[(leg, rid)] = reward_frames
                receipt = record['receipt']
                self.command.validate_terminal_receipt(req, receipt, record['observation'])
                if receipt['status'] == 'rejected':
                    continue
                raw = _read_native(self.pilot, receipt_path, MAX_JSON)
                if json.loads(raw) != receipt:
                    raise ValueError('immutable native receipt differs from route record')
                digest = hashlib.sha256(raw).hexdigest()
                for role, frame in _selected(req, receipt, rewards):
                    try:
                        if type(frame) is not int or type(req.get('expectedFrameId')) is not int or not (
                                req['expectedFrameId'] < frame <= receipt['frameId']):
                            raise ValueError('frame outside request and receipt interval')
                        context = dict(leg=leg, role=role, requestId=rid, receiptSha256=digest)
                        if role == 'combat-reward':
                            context['rewardText'] = next(r['rewardText'] for r in rewards if r['rewardFrameId'] == frame)
                        if req['mission'] == 'dialogue':
                            context['talkTo'] = req['talkTo']
                        self._capture(session, frame, context)
                    except (OSError, ValueError, RuntimeError, TypeError, KeyError) as exc:
                        self.issue(leg, exc, rid, frame if type(frame) is int else None)
            except (OSError, ValueError, RuntimeError, TypeError, KeyError, AttributeError) as exc:
                self.issue(leg, exc, rid)

    def _capture(self, session, frame, context):
        """Archive a verified original pair atomically and attach every role supported by that pair."""
        key = (session, frame)
        if key in self.saved:
            entry, reward_rows = self.saved[key]
            if 'rewardText' in context and context['rewardText'] not in reward_rows:
                raise ValueError('reward text missing from native observation')
            if context not in entry['uses']:
                entry['uses'].append(context)
                self.revision += 1
            return
        if len(self.saved) >= self.summary['maxFrames']:
            raise ValueError('launcher frame budget reached')
        source = self.command.observation_path(self.pilot, session, frame)
        budget = self.summary['maxBytes'] - self.summary['bytes']
        observation = _read_native(self.pilot, source, min(MAX_JSON, budget))
        data = json.loads(observation)
        image_source = source.with_suffix('.png')
        stamp = data['hud']['captureStamp']
        if (data.get('session') != session or type(data.get('frameId')) is not int or data['frameId'] != frame
                or data.get('screenshotPath') != image_source.relative_to(self.pilot).as_posix()
                or stamp.get('session') != session or type(stamp.get('frameId')) is not int
                or stamp['frameId'] != frame or stamp.get('source') != 'game-capture-start'):
            raise ValueError('native observation, capture stamp or screenshot path mismatch')
        reward_rows = {row['text'] for row in data.get('ocr', []) if 0 <= row.get('x', -1) < 650
                       and 300 < row.get('y', -1) < 850 and 'character exp' in row['text'].lower()}
        if 'rewardText' in context and context['rewardText'] not in reward_rows:
            raise ValueError('reward text missing from native observation')
        picture = _read_native(self.pilot, image_source, budget - len(observation))
        if not _is_png(picture):
            raise ValueError('native image has invalid PNG chunks')
        folder = self.output / 'encounters' / session / source.stem
        if folder.resolve() != folder:
            raise ValueError('unexpected archive location')
        folder.parent.mkdir(parents=True, exist_ok=True)
        # Publish both files as a single directory, or clean up the private temporary pair on failure.
        with tempfile.TemporaryDirectory(dir=folder.parent) as temporary:
            pair = Path(temporary) / 'pair'
            pair.mkdir()
            (pair / source.name).write_bytes(observation)
            (pair / image_source.name).write_bytes(picture)
            pair.rename(folder)
        entry = dict(session=session, frameId=frame, uses=[context],
                     json=(folder / source.name).relative_to(self.output).as_posix(),
                     png=(folder / image_source.name).relative_to(self.output).as_posix(),
                     jsonSha256=hashlib.sha256(observation).hexdigest(), pngSha256=hashlib.sha256(picture).hexdigest())
        self.summary['bytes'] += len(observation) + len(picture)
        self.summary['frames'].append(entry)
        self.saved[key] = (entry, reward_rows)
        self.revision += 1
