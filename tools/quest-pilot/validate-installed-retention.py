"""Bounded, observation-only installed retention check. Never sends gameplay input."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import time
import uuid


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def submit_observation(path, request):
    pending = path.with_suffix('.pending.json')
    pending.write_text(json.dumps(request), encoding='utf-8')
    for attempt in range(6):
        try:
            os.replace(pending, path)
            return
        except OSError as error:
            if attempt == 5 or getattr(error, 'winerror', None) not in (5, 32, 33):
                raise
            time.sleep(.05)


def run(app, pid, windows_session, count, output):
    root = app / 'User/JsScript/ActOnePilot'
    command = load('retention_command', Path(__file__).with_name('act-one-command.py'))
    control = load('retention_control', Path(__file__).with_name('controller-control.py'))
    group = command.read(app / 'User/ScriptGroup/ActOneRun.json')
    if any(project.get('jsScriptSettingsObject', {}).get('enableInput') is not False for project in group['projects']):
        raise RuntimeError('Supervised gameplay input must be disabled before validation')
    status = control.run('status', pid, windows_session)
    if Path(status.get('appDirectory', '')).resolve() != app or status.get('captureStorageVersion') != 1:
        raise RuntimeError('Pinned installed native runtime identity differs')
    before_free = shutil.disk_usage(app).free
    peak_count = peak_bytes = 0
    samples = []
    started = time.time()
    try:
        for index in range(count):
            observation = command.read(root / 'observation.json')
            session, frame = observation['session'], observation['frameId']
            heartbeat = command.require_live_controller(root, session, frame, windows_session)
            if heartbeat['processId'] != pid:
                raise RuntimeError('Controller owner changed; validation stopped')
            words = [str(row.get('text', '')).strip().lower() for row in observation.get('ocr', [])]
            if 'food' not in words:
                raise RuntimeError('Food inventory boundary is no longer visible; no request sent')
            request = dict(session=session, expectedFrameId=frame, id='mission-' + uuid.uuid4().hex,
                           createdAt=int(time.time() * 1000), mission='observe')
            submit_observation(root / 'request.json', request)
            deadline = time.monotonic() + 20
            while True:
                time.sleep(.1)
                try:
                    receipt = command.read(command.request_receipt_path(root, session, request['id']))
                except (FileNotFoundError, json.JSONDecodeError):
                    receipt = None
                if receipt and receipt.get('status') not in ('started', 'running'):
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError('Observation timed out; no retry was sent')
            if receipt.get('status') != 'completed':
                raise RuntimeError('Read-only observation did not complete: ' + str(receipt.get('status')))
            immutable = command.read(command.observation_path(root, session, receipt['frameId']))
            command.validate_terminal_receipt(request, receipt, immutable)
            if any(event.get('type') != 'controllerRevision' for event in receipt.get('details', {}).get('inputEvents', [])):
                raise RuntimeError('Unexpected input evidence during observation-only validation')
            pngs = list((root / 'observations').rglob('*.png'))
            size = sum(path.stat().st_size for path in pngs)
            peak_count, peak_bytes = max(peak_count, len(pngs)), max(peak_bytes, size)
            if len(pngs) > 288 or size > 576 * 1024 * 1024:
                raise RuntimeError('Installed screenshot retention exceeded its advertised cap')
            if (index + 1) % 32 == 0 or index + 1 == count:
                sample = dict(observations=index + 1, frameId=immutable['frameId'], pngFiles=len(pngs), pngBytes=size)
                samples.append(sample)
                print(json.dumps(sample), flush=True)
            # Give the controller's request-finally/heartbeat boundary time to settle.
            time.sleep(.25)
        latest = command.read(root / 'observation.json')
        unique = {}
        for path in (root / 'observations').rglob('*.png'):
            stat = path.stat()
            if not stat.st_ino:
                raise RuntimeError('Filesystem file IDs unavailable for deduplication verification')
            unique[(stat.st_dev, stat.st_ino)] = stat.st_size
        report = dict(verified=True, utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                      processId=pid, windowsSessionId=windows_session, appDirectory=str(app),
                      observations=count, peakPngFiles=peak_count, peakPngBytes=peak_bytes,
                      uniquePngFiles=len(unique), uniquePngContentBytes=sum(unique.values()),
                      freeBefore=before_free, freeAfter=shutil.disk_usage(app).free,
                      elapsedSeconds=round(time.time()-started, 2), latestSession=latest['session'],
                      latestFrameId=latest['frameId'], latestScreenshot=str(root/latest['screenshotPath']),
                      screenshotTimestamp=latest['timestamp'], gameplayInputEnabled=False, samples=samples)
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)
    except Exception as error:
        # Only this explicitly pinned, supervised validation controller is stopped.
        stop_error = None
        try:
            if control.run('status', pid, windows_session).get('serviceOwnsPilot') is True:
                control.run('stopPilot', pid, windows_session)
        except Exception as cleanup_error:
            stop_error = str(cleanup_error)
        output.write_text(json.dumps(dict(verified=False, error=str(error), stopError=stop_error,
                          processId=pid, windowsSessionId=windows_session, samples=samples,
                          peakPngFiles=peak_count, peakPngBytes=peak_bytes), indent=2), encoding='utf-8')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-directory', type=Path, required=True)
    parser.add_argument('--process-id', type=int, required=True)
    parser.add_argument('--windows-session-id', type=int, required=True)
    parser.add_argument('--observations', type=int, default=320)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.observations <= 400:
        raise SystemExit('Validation must be bounded to 1..400 observations')
    run(args.app_directory.resolve(strict=True), args.process_id, args.windows_session_id,
        args.observations, args.output)
