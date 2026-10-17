(function(root){
 'use strict';
 const target={x:-1308,y:2544};
 function region(m){return !!(m&&m.map==='Teyvat'&&m.x>=-1334&&m.x<=-1300&&m.y>=2538&&m.y<=2570);}
 function read(img,cv){let crop=null,rgb=null,mask=null;try{crop=img.deriveCrop(1819,1028,9,7);rgb=crop.srcMat.cvtColor(cv.ColorConversionCodes.BGR2RGB,0);mask=rgb.inRange(new cv.Scalar(242,223,39),new cv.Scalar(255,233,44));const pixels=Number(cv.Cv2.countNonZero(mask));return {source:'same-frame-swim-control',pixels,confirmed:pixels>=4};}finally{if(mask)mask.dispose();if(rgb)rgb.dispose();if(crop)crop.dispose();}}
 function base(o,now,session){const h=o&&o.hud,hp=h&&h.health;return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&region(o.map)&&Number.isFinite(o.map.cameraAngle)&&h&&h.world&&!h.climbing&&!h.auto&&!h.choice&&!h.dialogueReady&&!h.bigMap&&!h.journal&&hp&&hp.current===4015&&hp.max===4015&&h.enemyBarDiagnostic&&Array.isArray(h.enemyBars)&&!h.enemyBars.length&&Array.isArray(h.objectives)&&!h.objectives.length&&(h.groundControls||h.starfellSwim&&h.starfellSwim.source==='same-frame-swim-control'&&h.starfellSwim.confirmed===true)&&(o.ocr||[]).some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(r.text)));}
 function stamina(img,cv){let crop=null,hsv=null,mask=null;try{crop=img.deriveCrop(1060,560,80,180);hsv=crop.srcMat.cvtColor(cv.ColorConversionCodes.BGR2HSV,0);mask=hsv.inRange(new cv.Scalar(18,190,150),new cv.Scalar(28,255,255));const pixels=Number(cv.Cv2.countNonZero(mask)),contours=mask.findContoursAsArray(cv.RetrievalModes.External,cv.ContourApproximationModes.ApproxSimple),boxes=[];for(let i=0;i<contours.length;i++){const b=cv.Cv2.boundingRect(contours[i]);boxes.push({x:Number(b.x),y:Number(b.y),width:Number(b.width),height:Number(b.height)});}const valid=boxes.length===1&&pixels>=80&&pixels<=800&&boxes[0].width<=25&&boxes[0].height>=25&&boxes[0].height<=130;return {source:'same-frame-swim-stamina',pixels,boxes,height:valid?boxes[0].height:null};}finally{if(mask)mask.dispose();if(hsv)hsv.dispose();if(crop)crop.dispose();}}
 function start(o,now,session,continuation){return base(o,now,session)&&(continuation===true?o.hud.starfellSwim.confirmed&&o.hud.swimStamina&&o.hud.swimStamina.source==='same-frame-swim-stamina'&&o.hud.swimStamina.height>=40&&Math.hypot(o.map.x+1319.3574,o.map.y-2552.5801)<=2:o.hud.groundControls&&!o.hud.starfellSwim.confirmed&&Math.hypot(o.map.x+1329.832,o.map.y-2564.187)<=3);}
 function distance(o){return Math.hypot(o.map.x-target.x,o.map.y-target.y);}
 async function run(o,api){let current=o,swam=api.continuation===true,stalls=0;const result={status:'stopped',actions:0,inputMs:0,turns:0,positions:[]};try{
  if(!start(current,api.now(),api.session,api.continuation))throw Error('Fresh Starfell spawn or measured continuation required');
  // Recover any stamina used before teleport while standing safely at the Statue.
  if(!api.continuation){await api.sleep(1500);current=await api.observe();}
  for(let n=0;n<(api.continuation?10:12);n++){
   if(!base(current,api.now(),api.session)){result.reason='Shore field identity, threat, health or control changed';break;}
   if(current.hud.starfellSwim&&current.hud.starfellSwim.confirmed)swam=true;
   if(swam&&current.hud.groundControls){result.status='completed';result.reason='Ground controls regained after verified swim';break;}
   if(swam&&(!current.hud.swimStamina||current.hud.swimStamina.source!=='same-frame-swim-stamina'||!Number.isFinite(current.hud.swimStamina.height)||current.hud.swimStamina.height<25)){result.staminaEvidence=current.hud.swimStamina||null;result.reason=!current.hud.swimStamina||current.hud.swimStamina.source!=='same-frame-swim-stamina'||!Number.isFinite(current.hud.swimStamina.height)?'Fresh swim stamina unknown; no valid measured arc':'Measured swim stamina below continuation floor';break;}
   let diff=0;
   for(let turn=0;turn<3;turn++){
    const heading=(Math.atan2(current.map.y-target.y,current.map.x-target.x)*180/Math.PI+360)%360;diff=(heading-current.map.cameraAngle+540)%360-180;
    if(Math.abs(diff)<=15)break;
    if(!base(current,api.now(),api.session))throw Error('Fresh shore camera state required');
    await api.look(Math.max(-600,Math.min(600,Math.round(diff*8))),current);result.turns++;await api.sleep(180);current=await api.observe();
   }
   if(Math.abs(diff)>15){result.reason='Shore heading did not settle';break;}
   if(!base(current,api.now(),api.session))break;
   const before=distance(current);await api.key('VK_W',600,current);result.actions++;result.inputMs+=600;await api.sleep(180);current=await api.observe();
   if(!base(current,api.now(),api.session)){result.reason='Post-step field guard';break;}
   const after=distance(current);result.positions.push({frameId:current.frameId,x:current.map.x,y:current.map.y,distance:after,swimming:!!current.hud.starfellSwim.confirmed});
   if(after>before+1){result.reason='Shore distance increased';break;}stalls=before-after<.25?stalls+1:0;if(stalls>=2){result.reason='Two shore steps made no progress';break;}
  }
  result.fieldFrameId=current.frameId;result.swimmingObserved=swam;if(!result.reason)result.reason='Bounded crossing ended; inspect ground before continuing';return result;
 }finally{api.release();}}
 const api={region,read,stamina,base,start,run};root.ActTwoStarfellShore=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
