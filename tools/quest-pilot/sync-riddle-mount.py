"""Sync reviewed mount code after the first scoped R18 installation."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = root / 'BetterGenshinImpact/User/JsScript/ActOnePilot'
runtime = root / 'artifacts/release-r18/BetterGI-English-win-x64/User/JsScript/ActOnePilot'
rollback = root / 'artifacts/release-r18/rollback-riddle-mount'
if not (rollback / 'manifest.json').exists():
    raise RuntimeError('Initial byte-exact R18 rollback is missing')
marker = '        runActTwoRiddleMount: async function(initial,observe){'
end = '        runActTwoLowerClimb: async function(initial,observe){'
src = (source / 'bgi.js').read_text(encoding='utf-8')
dst = (runtime / 'bgi.js').read_text(encoding='utf-8')
if src.count(marker) != 1 or dst.count(marker) != 1 or src.count(end) != 1 or dst.count(end) != 1:
    raise RuntimeError('Unique mount adapter bounds not found')
new = src[src.index(marker):src.index(end, src.index(marker))]
old = dst[dst.index(marker):dst.index(end, dst.index(marker))]
dst = dst.replace(old, new, 1)
(runtime / 'bgi.js').write_text(dst, encoding='utf-8')
for name in ('act-two-riddle-mount.js', 'field-progress.js'):
    (runtime / name).write_bytes((source / name).read_bytes())
print(json.dumps({'synced': ['bgi.js adapter', 'act-two-riddle-mount.js', 'field-progress.js'], 'bgiSha256': hashlib.sha256((runtime / 'bgi.js').read_bytes()).hexdigest()}))
