"""Stage only the tested micro-ascent dispatcher additions over HEAD."""
import subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2];base='BetterGenshinImpact/User/JsScript/ActOnePilot/'
def git(*args,data=None):return subprocess.run(['git',*args],cwd=root,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
def one(text,old,new):
    if text.count(old)!=1:raise RuntimeError(f'Expected one anchor: {old[:70]!r}')
    return text.replace(old,new,1)
staged=git('diff','--cached','--name-only').decode().splitlines()
if any(base+n in staged for n in ('bgi.js','mission.js')):raise RuntimeError('Dispatcher already staged')
src=(root/base/'bgi.js').read_text(encoding='utf-8')
marker='        runActTwoWallMicroAscent: async function(initial,observe){';next_marker='        runActTwoRiddleMount: async function(initial,observe){'
method=src[src.index(marker):src.index(next_marker,src.index(marker))]
bgi_path=base+'bgi.js';bgi=git('show','HEAD:'+bgi_path).decode()
bgi=one(bgi,next_marker,method+next_marker)
old="if(value.mission==='questStep'&&value.step==='actTwoWallAttachmentTiming')names.push('act-two-wall-attachment-timing.js','climb-stamina.js','world-inventory.js','local-pause.js');"
bgi=one(bgi,old,old+"\n            if(value.mission==='questStep'&&value.step==='actTwoWallMicroAscent')names.push('act-two-wall-micro-ascent.js','climb-stamina.js','world-inventory.js','local-pause.js');")
bgi=one(bgi,"'actTwoWallStaminaTiming','actTwoWallAttachmentTiming'].indexOf(request.step)>=0&&climbing","'actTwoWallStaminaTiming','actTwoWallAttachmentTiming','actTwoWallMicroAscent'].indexOf(request.step)>=0&&climbing")
bgi=one(bgi,"'actTwoWallAttachmentTiming','actTwoMapClose'","'actTwoWallAttachmentTiming','actTwoWallMicroAscent','actTwoMapClose'")
mission_path=base+'mission.js';mission=git('show','HEAD:'+mission_path).decode()
old="        if(name==='actTwoWallAttachmentTiming')return api.runActTwoWallAttachmentTiming(observation,observe);"
mission=one(mission,old,old+"\n        if(name==='actTwoWallMicroAscent')return api.runActTwoWallMicroAscent(observation,observe);")
for name,value in ((bgi_path,bgi),(mission_path,mission)):
    blob=git('hash-object','-w','--stdin',data=value.encode()).decode().strip();git('update-index','--cacheinfo',f'100644,{blob},{name}')
    if git('show',':'+name)!=value.encode():raise RuntimeError(f'Staged mismatch: {name}')
    print(f'{name} {blob}')
