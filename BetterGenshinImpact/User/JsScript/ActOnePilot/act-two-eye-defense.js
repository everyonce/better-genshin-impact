(function(root){
 'use strict';
 function permit(o,w,p,r,prior,now,inventory){
  const h=w&&w.hud,hp=h&&h.health,v=prior&&prior.details&&prior.details.result,proof=v&&v.pauseProof;
  return !!(inventory&&o&&w&&p&&r&&prior&&o.session===r.session&&w.session===r.session&&p.session===r.session&&now>=o.timestamp&&now-o.timestamp<=1000&&now>=w.timestamp&&now-w.timestamp<=600000&&p.eyeDodgeProbe===true&&p.windSealCombat===true&&p.mode==='combat'&&p.enemyLevel===9&&p.nativeAvatar==='Amber'&&p.nativeWindows===1&&p.dodgeDirection==='VK_A'&&typeof p.escapeLandmark==='string'&&p.escapeLandmark.trim().length>=30&&p.escapeWitnessFrameId===w.frameId&&p.witnessFrameId===w.frameId&&p.frameId===r.expectedFrameId&&h&&h.world&&h.groundControls&&!h.climbing&&hp&&hp.current===1733&&hp.max===1733&&h.windSealBoss&&h.windSealBoss.level===9&&h.windSealThreat&&h.windSealThreat.nearBodyWarning===true&&!h.windSealThreat.ambiguous&&prior.id===p.pauseTerminalId&&prior.session===r.session&&prior.frameId===r.expectedFrameId&&v.pauseVerified===true&&proof&&proof.verified&&proof.kind==='inventory'&&proof.sourceFrameId===w.frameId&&(w.ocr||[]).some(t=>String(t.text).replace(/\s/g,'')==='EyeoftheStorm'&&t.x>=800&&t.x<=900&&t.y<=45)&&(w.ocr||[]).some(t=>/693306810$/.test(t.text.trim())&&t.x>1600&&t.y>1020));
 }
 function permitCalibration(o,w,p,r,prior,now,inventory){
  const h=w&&w.hud,hp=h&&h.health,v=prior&&prior.details&&prior.details.result,proof=v&&v.pauseProof;
  return !!(inventory&&o&&w&&p&&r&&prior&&o.session===r.session&&w.session===r.session&&p.session===r.session&&now>=o.timestamp&&now-o.timestamp<=1000&&now>=w.timestamp&&now-w.timestamp<=600000&&p.safeDodgeCalibration===true&&p.visualPositionReviewed===true&&Number.isInteger(p.regionMapFrameId)&&p.regionMapFrameId<w.frameId&&p.mode==='actions'&&Array.isArray(p.actions)&&p.actions.length===0&&p.nativeAvatar==='Kaeya'&&p.dodgeDirection==='VK_D'&&typeof p.escapeLandmark==='string'&&p.escapeLandmark.trim().length>=30&&p.escapeWitnessFrameId===w.frameId&&p.witnessFrameId===w.frameId&&p.frameId===r.expectedFrameId&&h&&h.world&&h.groundControls&&!h.climbing&&!h.windSealBoss&&!(w.ocr||[]).some(t=>String(t.text).replace(/\s/g,'')==='EyeoftheStorm')&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&hp&&hp.current===4015&&hp.max===4015&&prior.id===p.pauseTerminalId&&prior.session===r.session&&prior.frameId===r.expectedFrameId&&v.pauseVerified===true&&proof&&proof.verified&&proof.kind==='inventory'&&proof.sourceFrameId===w.frameId&&(w.ocr||[]).some(t=>/693306810$/.test(t.text.trim())&&t.x>1600&&t.y>1020));
 }
 function observationFirstEyeEntry(p,w){
  const h=w&&w.hud,rows=w&&w.ocr||[];
  const eye=!!(h&&h.windSealBoss&&h.windSealBoss.level===9&&h.windSealBoss.barFraction>0&&
   rows.some(t=>String(t.text).replace(/\s/g,'')==='EyeoftheStorm'&&t.x>=800&&t.x<=900&&t.y<=45)&&
   rows.some(t=>String(t.text).trim()==='Restless Pure Elemental'&&t.x>=800&&t.x<=900&&t.y>=40&&t.y<=75));
  return !!(eye&&p&&p.eyeDodgeProbe!==true&&p.safeDodgeCalibration!==true);
 }
 async function run(o,api){
  const started=api.now(),direction=api.direction||'VK_A';let heldAt=null;
  if(!['VK_A','VK_D'].includes(direction))throw Error('Unreviewed dodge direction');
  try{
   api.check();await api.key('VK_ESCAPE',60,o);await api.sleep(100);api.check();heldAt=api.now();api.down(direction);
   await api.sleep(60);api.check();if(api.now()-heldAt>400)throw Error('Directional dodge budget expired');await api.key('VK_SHIFT',60,o);
   await api.sleep(90);api.check();if(api.now()-heldAt>400)throw Error('Directional dodge budget expired');api.up(direction);
   await api.sleep(150);api.check();
   return {defensiveProbe:true,direction,directionHoldBudgetMs:400,plannedDirectionHoldMs:210,directionOverlapsDash:true,unpauseToDirectionDelayMs:160,unpauseToDashDelayMs:220,elapsedMs:api.now()-started,phaseReact:false,escapeVerified:false};
  }finally{api.up('VK_SHIFT');api.up(direction);api.release();}
 }

 root.ActTwoEyeDefense={permit,permitCalibration,observationFirstEyeEntry,run};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoEyeDefense;
})(typeof globalThis!=='undefined'?globalThis:this);
