"""Patch only the reviewed broad-wall step into retained R18, with rollback."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[2]
source=root/'BetterGenshinImpact/User/JsScript/ActOnePilot'
runtime=root/'artifacts/release-r18/BetterGI-English-win-x64/User/JsScript/ActOnePilot'
rollback=root/'artifacts/release-r18/rollback-riddle-wall-mount'
rollback.mkdir(parents=True,exist_ok=True)

def one(text,old,new):
    if text.count(old)!=1:raise RuntimeError(f'Expected unique anchor: {old[:75]!r}')
    return text.replace(old,new,1)

src=(source/'bgi.js').read_text(encoding='utf-8')
marker='        runActTwoWallMount: async function(initial,observe){'
next_marker='        runActTwoRiddleMount: async function(initial,observe){'
method=src[src.index(marker):src.index(next_marker,src.index(marker))]
bgi=(runtime/'bgi.js').read_text(encoding='utf-8')
if marker in bgi:raise RuntimeError('Broad-wall dispatcher is already installed')
bgi=one(bgi,next_marker,method+next_marker)
old="if(value.mission==='questStep'&&value.step==='actTwoRiddleMount')names.push('act-two-riddle-mount.js','field-progress.js','climb-stamina.js','world-inventory.js','local-pause.js');"
bgi=one(bgi,old,old+"\n            if(value.mission==='questStep'&&value.step==='actTwoWallMount')names.push('act-two-riddle-wall-mount.js','field-progress.js','climb-stamina.js','world-inventory.js','local-pause.js');")
bgi=one(bgi,"'actTwoRiddleMount'].indexOf(request.step)>=0&&climbing","'actTwoRiddleMount','actTwoWallMount'].indexOf(request.step)>=0&&climbing")
bgi=one(bgi,"'actTwoRiddleMount','actTwoMapClose'","'actTwoRiddleMount','actTwoWallMount','actTwoMapClose'")
mission=(runtime/'mission.js').read_text(encoding='utf-8')
old="        if(name==='actTwoRiddleMount')return api.runActTwoRiddleMount(observation,observe);"
mission=one(mission,old,old+"\n        if(name==='actTwoWallMount')return api.runActTwoWallMount(observation,observe);")
outputs={'bgi.js':bgi.encode(),'mission.js':mission.encode()}
for name in ('field-progress.js','act-two-riddle-wall-mount.js'):outputs[name]=(source/name).read_bytes()
manifest={'files':[]}
for name,data in outputs.items():
    target=runtime/name
    old=target.read_bytes() if target.exists() else None
    if old is not None:(rollback/name).write_bytes(old)
    manifest['files'].append({'path':str(target),'previousSha256':hashlib.sha256(old).hexdigest() if old is not None else None,'newSha256':hashlib.sha256(data).hexdigest()})
(rollback/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
for name,data in outputs.items():(runtime/name).write_bytes(data)
print(json.dumps(manifest))
