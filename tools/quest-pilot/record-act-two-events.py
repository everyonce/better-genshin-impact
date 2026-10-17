"""Persist deduplicated controller receipts and observation timing before capture retention."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(os.environ.get('BETTERGI_PILOT_APP_DIR', REPO / 'artifacts/release-r18/BetterGI-English-win-x64')) / 'User/JsScript/ActOnePilot'
LEDGER = REPO / 'artifacts/act-two-events.jsonl'

def main():
    seen = set()
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding='utf-8-sig').splitlines():
            event = json.loads(line)
            if event.get('key'):
                seen.add(event['key'])
    state = json.loads((ROOT / 'controller-status.json').read_text(encoding='utf-8-sig'))
    session = state['session']
    written = 0
    latest_field = None
    latest_receipt = None
    with LEDGER.open('a', encoding='utf-8') as stream:
        for kind, folder in [('observation', 'observations'), ('receipt', 'receipts')]:
            for path in sorted((ROOT / folder / session).glob('*.json')):
                value = json.loads(path.read_text(encoding='utf-8-sig'))
                if kind == 'observation' and (value.get('hud') or {}).get('world'):
                    if latest_field is None or value['frameId'] > latest_field['frameId']:
                        latest_field = value
                if kind == 'receipt' and value.get('status') in ('started', 'running'):
                    continue
                if kind == 'receipt' and (latest_receipt is None or value.get('timestamp', 0) > latest_receipt.get('timestamp', 0)):
                    latest_receipt = value
                key = f'{kind}:{session}:{path.stem}'
                if key in seen:
                    continue
                if kind == 'observation':
                    value = {k: value.get(k) for k in ('frameId', 'timestamp', 'timings', 'map', 'hud')}
                event = {'key': key, 'type': kind, 'session': session,
                         'recordedUtc': datetime.now(timezone.utc).isoformat(), 'data': value}
                stream.write(json.dumps(event, separators=(',', ':')) + '\n')
                written += 1
    checkpoint_path = REPO / 'artifacts/act-two-latest-checkpoint.json'
    checkpoint = json.loads(checkpoint_path.read_text(encoding='utf-8-sig')) if checkpoint_path.exists() else {}
    checkpoint.update(utc=datetime.now(timezone.utc).isoformat(), session=session, frame=state.get('frameId'),
                      controllerState=state.get('state'), activeRequestId=state.get('activeRequestId'),
                      childPid=state.get('processId'), rdpSession=state.get('windowsSessionId'))
    if latest_field:
        checkpoint['lastField'] = {key: latest_field.get(key) for key in ('frameId', 'timestamp', 'map', 'hud')}
    if latest_receipt:
        result = (latest_receipt.get('details') or {}).get('result') or {}
        checkpoint['lastTerminalRequest'] = {'id': latest_receipt.get('id'), 'status': latest_receipt.get('status'),
                                            'timestamp': latest_receipt.get('timestamp'), 'result': result}
        proof = result.get('pauseProof') or {}
        checkpoint['pauseCurrentlyVerified'] = bool(state.get('state') == 'idle' and result.get('pauseVerified') and
            latest_receipt.get('frameId') == state.get('frameId'))
        if proof.get('verified'):
            checkpoint['verifiedPauseFrame'] = proof.get('pauseFrameId')
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2), encoding='utf-8')
    print(json.dumps({'session': session, 'newEvents': written, 'ledgerBytes': LEDGER.stat().st_size}))

if __name__ == '__main__':
    main()
