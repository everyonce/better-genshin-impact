"""Hotload only the one-use W200 low-wall probe, retaining byte-exact rollback."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = root / 'BetterGenshinImpact/User/JsScript/ActOnePilot'
runtime = root / 'artifacts/release-r18/BetterGI-English-win-x64/User/JsScript/ActOnePilot'
rollback = root / 'artifacts/release-r18/rollback-wall-micro-ascent'


def once(value, old, new):
    if value.count(old) != 1:
        raise RuntimeError(f'Expected exactly one anchor: {old[:100]}')
    return value.replace(old, new, 1)


src = (source / 'bgi.js').read_text(encoding='utf-8')
marker = '        runActTwoWallMicroAscent: async function(initial,observe){'
next_marker = '        runActTwoRiddleMount: async function(initial,observe){'
method = src[src.index(marker):src.index(next_marker, src.index(marker))]
bgi = (runtime / 'bgi.js').read_text(encoding='utf-8')
if marker in bgi:
    raise RuntimeError('Attachment probe already deployed')
bgi = once(bgi, next_marker, method + next_marker)
old = "if(value.mission==='questStep'&&value.step==='actTwoWallAttachmentTiming')names.push('act-two-wall-attachment-timing.js','climb-stamina.js','world-inventory.js','local-pause.js');"
bgi = once(bgi, old, old + "\n            if(value.mission==='questStep'&&value.step==='actTwoWallMicroAscent')names.push('act-two-wall-micro-ascent.js','climb-stamina.js','world-inventory.js','local-pause.js');")
bgi = once(bgi, "'actTwoWallStaminaTiming','actTwoWallAttachmentTiming'].indexOf(request.step)>=0&&climbing", "'actTwoWallStaminaTiming','actTwoWallAttachmentTiming','actTwoWallMicroAscent'].indexOf(request.step)>=0&&climbing")
bgi = once(bgi, "'actTwoWallAttachmentTiming','actTwoMapClose'", "'actTwoWallAttachmentTiming','actTwoWallMicroAscent','actTwoMapClose'")
mission = (runtime / 'mission.js').read_text(encoding='utf-8')
old = "        if(name==='actTwoWallAttachmentTiming')return api.runActTwoWallAttachmentTiming(observation,observe);"
mission = once(mission, old, old + "\n        if(name==='actTwoWallMicroAscent')return api.runActTwoWallMicroAscent(observation,observe);")
outputs = {'bgi.js': bgi.encode(), 'mission.js': mission.encode(), 'act-two-wall-micro-ascent.js': (source / 'act-two-wall-micro-ascent.js').read_bytes()}
rollback.mkdir(parents=True, exist_ok=True)
manifest = {'files': []}
for name, data in outputs.items():
    target = runtime / name
    old_bytes = target.read_bytes() if target.exists() else None
    if old_bytes is not None:
        (rollback / name).write_bytes(old_bytes)
    manifest['files'].append({'path': str(target), 'previousSha256': hashlib.sha256(old_bytes).hexdigest() if old_bytes is not None else None, 'newSha256': hashlib.sha256(data).hexdigest()})
(rollback / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
for name, data in outputs.items():
    (runtime / name).write_bytes(data)
print(json.dumps(manifest))
