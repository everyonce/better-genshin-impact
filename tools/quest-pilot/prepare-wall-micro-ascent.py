"""Add a one-use low wall micro-ascent dispatcher without touching other draft changes."""
from pathlib import Path

root=Path(__file__).resolve().parents[2]
source=root/'BetterGenshinImpact/User/JsScript/ActOnePilot'


def once(value,old,new):
    if value.count(old)!=1:raise RuntimeError(f'Expected one anchor: {old[:100]}')
    return value.replace(old,new,1)


method="""        runActTwoWallMicroAscent: async function(initial,observe){
            var gate=eval(file.readTextSync('world-inventory.js')+'\\nactOneWorldInventoryClosePermission;');
            var chain=eval(file.readTextSync('act-two-wall-micro-ascent.js')+'\\nActTwoWallMicroAscent;');
            var staminaReader=eval(file.readTextSync('climb-stamina.js')+'\\nActTwoClimbStamina;');
            var p=JSON.parse(file.readTextSync('act-two-wall-micro-ascent-request.json'));
            if(!chain.permit(p,request,initial,gate,Date.now())||!actTwoOriginalAccount(initial.ocr))throw Error('Fresh one-use micro-ascent plan required');
            var witness=JSON.parse(file.readTextSync('observations/'+p.sourceSession+'/frame-0015.json'));
            if(!chain.entry(witness,p.sourceSession,witness.timestamp))throw Error('Reviewed low wall witness changed');
            var path='observations/'+p.sourceSession+'/frame-0015.png',line=file.readTextSync('capture-retention.tsv').split('\\n').find(v=>v.indexOf(path+'\\t')===0);
            if(!line||line.toLowerCase().indexOf(p.sha256)<0)throw Error('Reviewed landing image hash missing');
            p.usedAt=Date.now();p.requestId=request.id;var consumed=JSON.stringify(p);
            if(!file.writeTextSync('act-two-wall-micro-ascent-request.json',consumed)||file.readTextSync('act-two-wall-micro-ascent-request.json')!==consumed)throw Error('Micro-ascent plan consumption failed');
            var current=initial,result={status:'stopped',step:'actTwoWallMicroAscent',inputs:0},error=null,sampleImage=null,unpauseAt=null,mountUsed=false,microUsed=false,xUsed=false;
            function check(){checkStop();ready();}
            try{check();unpauseAt=Date.now();await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(500);current=await observe();
                result=await chain.run(current,{now:Date.now,check:check,sleep:sleep,release:async function(){release();},observe:observe,
                    key:async function(k,ms,o){check();var now=Date.now();
                        if(k==='VK_W'&&ms===600&&!mountUsed&&!microUsed&&chain.entry(o,request.session,now)){mountUsed=true;}
                        else if(k==='VK_W'&&ms===200&&mountUsed&&!microUsed&&chain.attached(o,request.session,now)){microUsed=true;}
                        else if(k==='VK_X'&&ms===60&&mountUsed&&!xUsed&&chain.releaseReady(o,request.session,now)){xUsed=true;}
                        else throw Error('Fixed low mount, single W200 ascent or guarded X release required');
                        events.push({type:'actTwoWallMicroInput',key:k,ms:ms,frameId:o.frameId,startedAt:now});await boundedKey(k,ms,o.frameId);},
                    sample:async function(){check();var at=Date.now(),img=captureGameRegion();try{if(Number(img.width)!==1920||Number(img.height)!==1080)throw Error('Micro-ascent capture dimensions changed');var raw=staminaReader.read(img,OpenCvSharp.OpenCvSharp),classified=staminaReader.classify(raw),measured={valid:true,capturedAt:at,captureAndRecognitionMs:Date.now()-at,stamina:classified,rawPixels:raw.rawPixels,boxes:raw.boxes};sampleImage=img;img=null;check();return measured;}finally{dispose(img);}}});
            }catch(e){error=String(e&&e.message||e);result.reason=error;}finally{release();}
            result.unpauseAt=unpauseAt;result.localActionFinishedAt=Date.now();
            try{var paused=await finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error,lastObservation&&lastObservation.hud.world&&Date.now()-lastObservation.timestamp<=1000?lastObservation:null);
                paused.pauseVerifiedAt=Date.now();paused.exposureMs=unpauseAt?paused.pauseVerifiedAt-unpauseAt:null;
                if(sampleImage){var filePath='observations/'+request.session+'/frame-'+String(270000000+initial.frameId)+'.png';if(!file.writeImageSync(filePath,sampleImage.srcMat))throw Error('Micro-ascent image storage refused');paused.sampleImagePath=filePath;}
                return paused;
            }finally{dispose(sampleImage);}
        },
"""

bgi_path=source/'bgi.js';bgi=bgi_path.read_text(encoding='utf-8')
marker='        runActTwoRiddleMount: async function(initial,observe){'
bgi=once(bgi,marker,method+marker)
old="if(value.mission==='questStep'&&value.step==='actTwoWallAttachmentTiming')names.push('act-two-wall-attachment-timing.js','climb-stamina.js','world-inventory.js','local-pause.js');"
bgi=once(bgi,old,old+"\n            if(value.mission==='questStep'&&value.step==='actTwoWallMicroAscent')names.push('act-two-wall-micro-ascent.js','climb-stamina.js','world-inventory.js','local-pause.js');")
bgi=once(bgi,"'actTwoWallStaminaTiming','actTwoWallAttachmentTiming'].indexOf(request.step)>=0&&climbing","'actTwoWallStaminaTiming','actTwoWallAttachmentTiming','actTwoWallMicroAscent'].indexOf(request.step)>=0&&climbing")
bgi=once(bgi,"'actTwoWallAttachmentTiming','actTwoMapClose'","'actTwoWallAttachmentTiming','actTwoWallMicroAscent','actTwoMapClose'")
bgi_path.write_text(bgi,encoding='utf-8')
mission_path=source/'mission.js';mission=mission_path.read_text(encoding='utf-8')
old="        if(name==='actTwoWallAttachmentTiming')return api.runActTwoWallAttachmentTiming(observation,observe);"
mission=once(mission,old,old+"\n        if(name==='actTwoWallMicroAscent')return api.runActTwoWallMicroAscent(observation,observe);")
mission_path.write_text(mission,encoding='utf-8')
print('Added one-use low-wall W200 micro-ascent dispatch')
