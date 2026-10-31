(function(root){
 'use strict';
 const target={x:-1308,y:2544};
 function region(m,north){if(north)return !!(m&&m.map==='Teyvat'&&m.x>=-1322&&m.x<=-1295&&m.y>=2568&&m.y<=2592);return !!(m&&m.map==='Teyvat'&&m.x>=-1334&&m.x<=-1300&&m.y>=2538&&m.y<=2570);}
 function read(img,cv){let crop=null,rgb=null,mask=null;try{crop=img.deriveCrop(1819,1028,9,7);rgb=crop.srcMat.cvtColor(cv.ColorConversionCodes.BGR2RGB,0);mask=rgb.inRange(new cv.Scalar(242,223,39),new cv.Scalar(255,233,44));const pixels=Number(cv.Cv2.countNonZero(mask));return {source:'same-frame-swim-control',pixels,confirmed:pixels>=4};}finally{if(mask)mask.dispose();if(rgb)rgb.dispose();if(crop)crop.dispose();}}
 function base(o,now,session,north){const h=o&&o.hud,hp=h&&h.health;return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&region(o.map,north)&&Number.isFinite(o.map.cameraAngle)&&h&&h.world&&!h.climbing&&!h.auto&&!h.choice&&!h.dialogueReady&&!h.bigMap&&!h.journal&&hp&&hp.current===4015&&hp.max===4015&&h.enemyBarDiagnostic&&Array.isArray(h.enemyBars)&&!h.enemyBars.length&&Array.isArray(h.objectives)&&!h.objectives.length&&(h.groundControls||h.starfellSwim&&h.starfellSwim.source==='same-frame-swim-control'&&h.starfellSwim.confirmed===true)&&(o.ocr||[]).some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(r.text)));}
 function staminaHeight(pixels,boxes){
  if(!Number.isFinite(pixels)||pixels<80||pixels>800||!Array.isArray(boxes)||boxes.length<1||boxes.length>2)return null;
  if(boxes.some(b=>!b||!['x','y','width','height'].every(k=>Number.isFinite(b[k]))||b.x<0||b.y<0||b.width<1||b.width>25||b.height<1||b.x+b.width>80||b.y+b.height>180))return null;
  const sorted=boxes.slice().sort((a,b)=>b.height-a.height),main=sorted[0];
  if(main.height<25||main.height>130)return null;
  if(sorted.length===2){const tip=sorted[1],gap=main.y-tip.y-tip.height;if(tip.height>8||gap<0||gap>3||tip.x<main.x||tip.x+tip.width>main.x+main.width)return null;}
  return main.height; // Never add the detached tip to measured stamina.
 }
 function stamina(img,cv){let crop=null,hsv=null,mask=null;try{crop=img.deriveCrop(1060,560,80,180);hsv=crop.srcMat.cvtColor(cv.ColorConversionCodes.BGR2HSV,0);mask=hsv.inRange(new cv.Scalar(18,190,150),new cv.Scalar(28,255,255));const pixels=Number(cv.Cv2.countNonZero(mask)),contours=mask.findContoursAsArray(cv.RetrievalModes.External,cv.ContourApproximationModes.ApproxSimple),boxes=[];for(let i=0;i<contours.length;i++){const b=cv.Cv2.boundingRect(contours[i]);boxes.push({x:Number(b.x),y:Number(b.y),width:Number(b.width),height:Number(b.height)});}return {source:'same-frame-swim-stamina',pixels,boxes,height:staminaHeight(pixels,boxes)};}finally{if(mask)mask.dispose();if(hsv)hsv.dispose();if(crop)crop.dispose();}}
 function continuationPosition(m){const dx=m.x+1329.832,dy=m.y-2564.187,vx=21.832,vy=-20.187,l2=vx*vx+vy*vy,t=(dx*vx+dy*vy)/l2;return t>=.2&&t<=1.05&&Math.abs(dx*vy-dy*vx)/Math.sqrt(l2)<=2;}
 function unknownStamina(o){const s=o&&o.hud&&o.hud.swimStamina;return !s||s.source!=='same-frame-swim-stamina'||!Number.isFinite(s.height);}
 function northLane(m){const dx=m.x+1317.9043,dy=m.y-2573.0947,vx=17.9043,vy=11.9053,l2=vx*vx+vy*vy,t=(dx*vx+dy*vy)/l2;return t>=-.05&&t<=1.1&&Math.abs(dx*vy-dy*vx)/Math.sqrt(l2)<=2;}
 function start(o,now,session,continuation,north){if(north)return base(o,now,session,true)&&o.hud.starfellSwim&&o.hud.starfellSwim.confirmed===true&&o.hud.swimStamina&&o.hud.swimStamina.height>=40&&northLane(o.map);return base(o,now,session)&&(continuation===true?o.hud.starfellSwim.confirmed&&o.hud.swimStamina&&o.hud.swimStamina.source==='same-frame-swim-stamina'&&o.hud.swimStamina.height>=40&&continuationPosition(o.map):o.hud.groundControls&&!o.hud.starfellSwim.confirmed&&Math.hypot(o.map.x+1329.832,o.map.y-2564.187)<=3);}
 // Camera inspection has no movement authority; crossing still requires measured stamina.
 function cameraReady(o,now,session){return base(o,now,session)&&Number.isInteger(o.frameId)&&o.frameId>0&&o.hud.groundControls===false&&o.hud.starfellSwim&&o.hud.starfellSwim.source==='same-frame-swim-control'&&o.hud.starfellSwim.confirmed===true&&continuationPosition(o.map);}
 // A single camera call must be followed by a newer healthy stationary swimming frame.
 async function inspectCamera(o,api){
  const result={status:'stopped',actions:0,inputMs:0,cameraAdjustments:0,cameraDy:500,sourceFrameId:o&&o.frameId,fieldFrameId:o&&o.frameId,stationaryVerified:false};
  let current=o;
  try{
   if(!cameraReady(current,api.now(),api.session)){result.reason='Fresh full-health southern-lane swimming required for camera inspection';return result;}
   result.health=current.hud.health;result.swimStamina=current.hud.swimStamina;
   await api.pitch(500,current);result.cameraAdjustments=1;
   await api.sleep(350);current=await api.observe();
   result.fieldFrameId=current&&current.frameId;result.health=current&&current.hud&&current.hud.health;result.swimStamina=current&&current.hud&&current.hud.swimStamina;
   if(!cameraReady(current,api.now(),api.session)||current.frameId<=o.frameId||current.timestamp<=o.timestamp){result.reason='Post-camera fresh scoped swimming or full health was not verified';return result;}
   result.positionDelta=Math.hypot(current.map.x-o.map.x,current.map.y-o.map.y);
   if(result.positionDelta>0.5){result.reason='Position changed beyond stationary camera inspection bound';return result;}
   result.stationaryVerified=true;result.reason='One stationary shore camera inspection; inspect stamina before continuation';return result;
  }catch(error){const failure=error instanceof Error?error:new Error(String(error&&error.message||error));failure.fieldResult=result;throw failure;}finally{api.release();}
 }
 function distance(o,t){return Math.hypot(o.map.x-t.x,o.map.y-t.y);}
 const shoreExit={x:-1313.8046875,y:2547.23046875};
 // This exit is limited to the old southern lane and six units around the historical grounded landmark.
 function exitScope(o,now,session){return base(o,now,session)&&Number.isInteger(o.frameId)&&o.frameId>0&&Number.isFinite(o.map.x)&&Number.isFinite(o.map.y)&&continuationPosition(o.map)&&distance(o,shoreExit)<=6;}
 // The separate exit admits a measured 35-pixel reserve, retaining the 25-pixel movement floor.
 function exitReady(o,now,session,continuing){const h=o&&o.hud,s=h&&h.swimStamina;return exitScope(o,now,session)&&h.groundControls===false&&h.starfellSwim&&h.starfellSwim.source==='same-frame-swim-control'&&h.starfellSwim.confirmed===true&&s&&s.source==='same-frame-swim-stamina'&&Number.isFinite(s.height)&&s.height>=(continuing===true?25:35);}
 // A fresh explicit exit request gets at most six holds; no stamina reread or pitch is authorized.
 async function runExit(o,api){
  let current=o,stalls=0;const result={status:'stopped',actions:0,inputMs:0,turns:0,pitchAdjustments:0,positions:[],sourceFrameId:o&&o.frameId,target:{x:shoreExit.x,y:shoreExit.y},swimmingObserved:false};
  // Retain the last observation even when it makes the exit inadmissible.
  function retain(){result.fieldFrameId=current&&current.frameId;result.health=current&&current.hud&&current.hud.health;result.staminaEvidence=current&&current.hud&&current.hud.swimStamina;}
  function stop(reason){result.reason=reason;return result;}
  function landed(){result.status='completed';return stop('Ground controls regained after verified swim');}
  // Each turn or hold must produce a newer source before another action can be considered.
  async function next(){const previous=current;current=await api.observe();retain();if(!current||!Number.isInteger(current.frameId)||current.frameId<=previous.frameId||!Number.isFinite(current.timestamp)||current.timestamp<=previous.timestamp)throw Error('Near-shore exit requires a newer field observation');}
  try{
   retain();if(!exitReady(current,api.now(),api.session,false))return stop('Fresh near-shore swimming with at least 35 measured stamina required');
   result.swimmingObserved=true;
   for(let n=0;n<6;n++){
    for(let turn=0;turn<=3;turn++){
     if(!exitScope(current,api.now(),api.session))return stop('Near-shore identity, health, threat, lane or distance changed');
     if(current.hud.groundControls)return landed();
     if(!exitReady(current,api.now(),api.session,true))return stop('Near-shore swimming or measured stamina floor unavailable');
     const heading=(Math.atan2(current.map.y-shoreExit.y,current.map.x-shoreExit.x)*180/Math.PI+360)%360,diff=(heading-current.map.cameraAngle+540)%360-180;
     if(Math.abs(diff)<=15)break;if(turn===3)return stop('Near-shore heading did not settle');
     await api.look(Math.max(-600,Math.min(600,Math.round(diff*8))),current);result.turns++;await api.sleep(180);await next();
    }
    if(!exitReady(current,api.now(),api.session,true))return stop('Fresh near-shore movement permission expired');
    const before=distance(current,shoreExit);await api.key('VK_W',600,current);result.actions++;result.inputMs+=600;await api.sleep(180);await next();
    if(!exitScope(current,api.now(),api.session))return stop('Post-step near-shore identity, health, threat, lane or distance changed');
    const after=distance(current,shoreExit);result.positions.push({frameId:current.frameId,x:current.map.x,y:current.map.y,distance:after,swimming:!!current.hud.starfellSwim.confirmed});
    if(current.hud.groundControls)return landed();
    if(!exitReady(current,api.now(),api.session,true))return stop('Near-shore swimming or measured stamina floor unavailable');
    if(after>before+1)return stop('Near-shore distance increased');stalls=before-after<.25?stalls+1:0;if(stalls>=2)return stop('Two near-shore steps made no progress');
   }
   return stop('Bounded near-shore exit ended; inspect ground before continuing');
  }catch(error){const failure=error instanceof Error?error:new Error(String(error&&error.message||error));failure.fieldResult=result;throw failure;}finally{api.release();}
 }
 async function run(o,api){const destination=api.north?{x:-1300,y:2585}:target;let current=o,swam=api.continuation===true,stalls=0;const result={status:'stopped',actions:0,inputMs:0,turns:0,positions:[]};try{
  if(api.continuation&&base(current,api.now(),api.session,api.north)&&current.hud.starfellSwim.confirmed&&(api.north?northLane(current.map):continuationPosition(current.map))&&unknownStamina(current)){await api.sleep(800);current=await api.observe();result.staminaRereads=1;}
  if(!start(current,api.now(),api.session,api.continuation,api.north)){result.reason='Fresh Starfell spawn or measured continuation required';result.staminaEvidence=current.hud&&current.hud.swimStamina||null;result.fieldFrameId=current.frameId;return result;}
  if(!api.continuation&&typeof api.pitch==='function'){for(let view=0;view<2;view++){if(!start(current,api.now(),api.session,false)){result.reason='Dry spawn changed during camera preparation';return result;}await api.pitch(500,current);result.pitchAdjustments=(result.pitchAdjustments||0)+1;await api.sleep(180);current=await api.observe();}}
  // Recover any stamina used before teleport while standing safely at the Statue.
  if(!api.continuation){await api.sleep(1500);current=await api.observe();}
  for(let n=0;n<(api.continuation?10:12);n++){
   if(!base(current,api.now(),api.session,api.north)){result.reason='Shore field identity, threat, health or control changed';break;}
   if(current.hud.starfellSwim&&current.hud.starfellSwim.confirmed)swam=true;
   if(swam&&current.hud.groundControls){result.status='completed';result.reason='Ground controls regained after verified swim';break;}
   if(swam&&unknownStamina(current)&&!result.staminaRereads){await api.sleep(800);current=await api.observe();result.staminaRereads=1;if(!base(current,api.now(),api.session,api.north)){result.reason='Stationary stamina reread lost scoped field evidence';break;}if(current.hud.groundControls){result.status='completed';result.reason='Ground controls regained after verified swim';break;}}
   if(swam&&(!current.hud.swimStamina||current.hud.swimStamina.source!=='same-frame-swim-stamina'||!Number.isFinite(current.hud.swimStamina.height)||current.hud.swimStamina.height<25)){result.staminaEvidence=current.hud.swimStamina||null;result.reason=!current.hud.swimStamina||current.hud.swimStamina.source!=='same-frame-swim-stamina'||!Number.isFinite(current.hud.swimStamina.height)?'Fresh swim stamina unknown; no valid measured arc':'Measured swim stamina below continuation floor';break;}
   let diff=0;
   for(let turn=0;turn<3;turn++){
    const heading=(Math.atan2(current.map.y-destination.y,current.map.x-destination.x)*180/Math.PI+360)%360;diff=(heading-current.map.cameraAngle+540)%360-180;
    if(Math.abs(diff)<=15)break;
    if(!base(current,api.now(),api.session,api.north))throw Error('Fresh shore camera state required');
    await api.look(Math.max(-600,Math.min(600,Math.round(diff*8))),current);result.turns++;await api.sleep(180);current=await api.observe();
   }
   if(Math.abs(diff)>15){result.reason='Shore heading did not settle';break;}
   if(!base(current,api.now(),api.session,api.north))break;
   const before=distance(current,destination);await api.key('VK_W',600,current);result.actions++;result.inputMs+=600;await api.sleep(180);current=await api.observe();
   if(!base(current,api.now(),api.session,api.north)){result.reason='Post-step field guard';break;}
   const after=distance(current,destination);result.positions.push({frameId:current.frameId,x:current.map.x,y:current.map.y,distance:after,swimming:!!current.hud.starfellSwim.confirmed});
   if(after>before+1){result.reason='Shore distance increased';break;}stalls=before-after<.25?stalls+1:0;if(stalls>=2){result.reason='Two shore steps made no progress';break;}
  }
  result.fieldFrameId=current.frameId;result.swimmingObserved=swam;if(!result.reason)result.reason='Bounded crossing ended; inspect ground before continuing';return result;
 }finally{api.release();}}
 const api={region,read,stamina,staminaHeight,base,start,cameraReady,inspectCamera,exitReady,runExit,run};root.ActTwoStarfellShore=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
