"""Install only the one-use low wall release into the validated R18 runtime."""
import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
source=root/'BetterGenshinImpact/User/JsScript/ActOnePilot'
runtime=root/'artifacts/release-r18/BetterGI-English-win-x64/User/JsScript/ActOnePilot'
rollback=root/'artifacts/release-r18/rollback-wall-low-release'

def one(text,old,new):
    if text.count(old)!=1:raise RuntimeError(f'Expected one anchor: {old[:65]!r}')
    return text.replace(old,new,1)

src=(source/'bgi.js').read_text(encoding='utf-8')
marker='        runActTwoWallLowRelease: async function(initial,observe){'
next_marker='        runActTwoRiddleMount: async function(initial,observe){'
method=src[src.index(marker):src.index(next_marker,src.index(marker))]
bgi=(runtime/'bgi.js').read_text(encoding='utf-8')
if marker in bgi:raise RuntimeError('Low-release method already deployed')
bgi=one(bgi,next_marker,method+next_marker)
old="if(value.mission==='questStep'&&value.step==='actTwoWallMount')names.push('act-two-riddle-wall-mount.js','field-progress.js','climb-stamina.js','world-inventory.js','local-pause.js');"
bgi=one(bgi,old,old+"\n            if(value.mission==='questStep'&&value.step==='actTwoWallLowRelease')names.push('act-two-wall-low-release.js','climb-stamina.js','world-inventory.js','local-pause.js');")
bgi=one(bgi,"'actTwoRiddleMount','actTwoWallMount'].indexOf(request.step)>=0&&climbing","'actTwoRiddleMount','actTwoWallMount','actTwoWallLowRelease'].indexOf(request.step)>=0&&climbing")
bgi=one(bgi,"'actTwoWallMount','actTwoMapClose'","'actTwoWallMount','actTwoWallLowRelease','actTwoMapClose'")
mission=(runtime/'mission.js').read_text(encoding='utf-8')
old="        if(name==='actTwoWallMount')return api.runActTwoWallMount(observation,observe);"
mission=one(mission,old,old+"\n        if(name==='actTwoWallLowRelease')return api.runActTwoWallLowRelease(observation,observe);")
outputs={'bgi.js':bgi.encode(),'mission.js':mission.encode()}
for name in ('act-two-wall-low-release.js','climb-stamina.js'):outputs[name]=(source/name).read_bytes()
rollback.mkdir(parents=True,exist_ok=True)
manifest={'files':[]}
for name,data in outputs.items():
    target=runtime/name;old=target.read_bytes() if target.exists() else None
    if old is not None:(rollback/name).write_bytes(old)
    manifest['files'].append({'path':str(target),'previousSha256':hashlib.sha256(old).hexdigest() if old is not None else None,'newSha256':hashlib.sha256(data).hexdigest()})
(rollback/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
for name,data in outputs.items():(runtime/name).write_bytes(data)
print(json.dumps(manifest))
