"""Persist deduplicated controller receipts and observation timing before capture retention."""
import json
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / 'artifacts/release-r17/BetterGI-English-win-x64/User/JsScript/ActOnePilot'
LEDGER = REPO / 'artifacts/act-two-events.jsonl'

def main():
    seen = set()
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding='utf-8-sig').splitlines():
            event = json.loads(line)
            if event.get('key'):
                seen.add(event['key'])
    session = json.loads((ROOT / 'controller-status.json').read_text(encoding='utf-8-sig'))['session']
    written = 0
    with LEDGER.open('a', encoding='utf-8') as stream:
        for kind, folder in [('observation', 'observations'), ('receipt', 'receipts')]:
            for path in sorted((ROOT / folder / session).glob('*.json')):
                value = json.loads(path.read_text(encoding='utf-8-sig'))
                if kind == 'receipt' and value.get('status') in ('started', 'running'):
                    continue
                key = f'{kind}:{session}:{path.stem}'
                if key in seen:
                    continue
                if kind == 'observation':
                    value = {k: value.get(k) for k in ('frameId', 'timestamp', 'timings', 'map', 'hud')}
                event = {'key': key, 'type': kind, 'session': session,
                         'recordedUtc': datetime.now(timezone.utc).isoformat(), 'data': value}
                stream.write(json.dumps(event, separators=(',', ':')) + '\n')
                written += 1
    print(json.dumps({'session': session, 'newEvents': written, 'ledgerBytes': LEDGER.stat().st_size}))

if __name__ == '__main__':
    main()
