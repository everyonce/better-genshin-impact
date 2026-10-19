"""Install only the reviewed riddle-mount snippets into the retained R18 pilot.

The R18 dispatcher has other live changes, so copying source bgi.js is unsafe.
This script is deliberately single-use and retains a byte-exact rollback.
"""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = root / 'BetterGenshinImpact/User/JsScript/ActOnePilot'
runtime = root / 'artifacts/release-r18/BetterGI-English-win-x64/User/JsScript/ActOnePilot'
rollback = root / 'artifacts/release-r18/rollback-riddle-mount'
rollback.mkdir(parents=True, exist_ok=True)

def one(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f'Expected exactly one dispatcher anchor: {old[:90]!r}')
    return text.replace(old, new, 1)

src_bgi = (source / 'bgi.js').read_text(encoding='utf-8')
start = src_bgi.index('        runActTwoRiddleMount: async function(initial,observe){')
end = src_bgi.index('        runActTwoLowerClimb: async function(initial,observe){', start)
adapter = src_bgi[start:end]
bgi_path = runtime / 'bgi.js'
bgi = bgi_path.read_text(encoding='utf-8')
if 'runActTwoRiddleMount:' in bgi:
    raise RuntimeError('Riddle mount already installed; refusing to repeat deployment')
bgi = one(bgi, '        runActTwoLowerClimb: async function(initial,observe){', adapter + '        runActTwoLowerClimb: async function(initial,observe){')
old = "if(value.mission==='questStep'&&value.step==='actTwoLowerClimb')names.push('act-two-lower-climb.js','act-two-field.js','climb-stamina.js','world-inventory.js','local-pause.js');"
new = old + "\n            if(value.mission==='questStep'&&value.step==='actTwoRiddleMount')names.push('act-two-riddle-mount.js','field-progress.js','climb-stamina.js','world-inventory.js','local-pause.js');"
bgi = one(bgi, old, new)
bgi = one(bgi, "['actTwoField','actTwoLowerClimb','actTwoBoundedMount'].indexOf(request.step)>=0&&climbing", "['actTwoField','actTwoLowerClimb','actTwoBoundedMount','actTwoRiddleMount'].indexOf(request.step)>=0&&climbing")
mission_path = runtime / 'mission.js'
mission = mission_path.read_text(encoding='utf-8')
old = "        if(name==='actTwoLowerClimb')return api.runActTwoLowerClimb(observation,observe);"
mission = one(mission, old, old + "\n        if(name==='actTwoRiddleMount')return api.runActTwoRiddleMount(observation,observe);")

outputs = {'bgi.js': bgi.encode(), 'mission.js': mission.encode()}
for name in ('field-progress.js', 'act-two-riddle-mount.js'):
    outputs[name] = (source / name).read_bytes()
manifest = {'files': []}
for name, data in outputs.items():
    path = runtime / name
    if path.exists():
        original = path.read_bytes()
        (rollback / name).write_bytes(original)
        manifest['files'].append({'path': str(path), 'previousSha256': hashlib.sha256(original).hexdigest(), 'newSha256': hashlib.sha256(data).hexdigest()})
    else:
        manifest['files'].append({'path': str(path), 'previousSha256': None, 'newSha256': hashlib.sha256(data).hexdigest()})
(rollback / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
for name, data in outputs.items():
    (runtime / name).write_bytes(data)
print(json.dumps(manifest))
