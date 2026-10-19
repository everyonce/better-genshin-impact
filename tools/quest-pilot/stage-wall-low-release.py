"""Stage only the tested low-release dispatcher changes over HEAD."""
import subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2]
base='BetterGenshinImpact/User/JsScript/ActOnePilot/'
def git(*args,data=None):
    return subprocess.run(['git',*args],cwd=root,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
def one(value,old,new):
    if value.count(old)!=1:raise RuntimeError(f'Expected one anchor: {old[:80]!r}')
    return value.replace(old,new,1)
staged=git('diff','--cached','--name-only').decode().splitlines()
if any(base+n in staged for n in ('bgi.js','mission.js')):raise RuntimeError('Dispatcher already staged; inspect first')
source=(root/base/'bgi.js').read_text(encoding='utf-8')
marker='        runActTwoWallLowRelease: async function(initial,observe){'
next_marker='        runActTwoRiddleMount: async function(initial,observe){'
method=source[source.index(marker):source.index(next_marker,source.index(marker))]
bgi_path=base+'bgi.js';bgi=git('show','HEAD:'+bgi_path).decode()
bgi=one(bgi,next_marker,method+next_marker)
old="if(value.mission==='questStep'&&value.step==='actTwoWallMount')names.push('act-two-riddle-wall-mount.js','field-progress.js','climb-stamina.js','world-inventory.js','local-pause.js');"
bgi=one(bgi,old,old+"\n            if(value.mission==='questStep'&&value.step==='actTwoWallLowRelease')names.push('act-two-wall-low-release.js','climb-stamina.js','world-inventory.js','local-pause.js');")
bgi=one(bgi,"'actTwoRiddleMount','actTwoWallMount'].indexOf(request.step)>=0&&climbing","'actTwoRiddleMount','actTwoWallMount','actTwoWallLowRelease'].indexOf(request.step)>=0&&climbing")
bgi=one(bgi,"'actTwoWallMount','actTwoMapClose'","'actTwoWallMount','actTwoWallLowRelease','actTwoMapClose'")
mission_path=base+'mission.js';mission=git('show','HEAD:'+mission_path).decode()
old="        if(name==='actTwoWallMount')return api.runActTwoWallMount(observation,observe);"
mission=one(mission,old,old+"\n        if(name==='actTwoWallLowRelease')return api.runActTwoWallLowRelease(observation,observe);")
for name,value in ((bgi_path,bgi),(mission_path,mission)):
    blob=git('hash-object','-w','--stdin',data=value.encode()).decode().strip()
    git('update-index','--cacheinfo',f'100644,{blob},{name}')
    if git('show',':'+name)!=value.encode():raise RuntimeError(f'Staged mismatch: {name}')
    print(f'{name} {blob}')
