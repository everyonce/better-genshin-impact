(function(root){
 'use strict';
 function permit(o,w,p,r,prior,now,inventory){
  const h=w&&w.hud,hp=h&&h.health,v=prior&&prior.details&&prior.details.result,proof=v&&v.pauseProof;
  return !!(inventory&&o&&w&&p&&r&&prior&&o.session===r.session&&w.session===r.session&&p.session===r.session&&now>=o.timestamp&&now-o.timestamp<=1000&&now>=w.timestamp&&now-w.timestamp<=600000&&p.eyeDodgeProbe===true&&p.windSealCombat===true&&p.mode==='combat'&&p.enemyLevel===9&&p.nativeAvatar==='Amber'&&p.nativeWindows===1&&p.dodgeDirection==='VK_A'&&typeof p.escapeLandmark==='string'&&p.escapeLandmark.trim().length>=30&&p.escapeWitnessFrameId===w.frameId&&p.witnessFrameId===w.frameId&&p.frameId===r.expectedFrameId&&h&&h.world&&h.groundControls&&!h.climbing&&hp&&hp.current===1733&&hp.max===1733&&h.windSealBoss&&h.windSealBoss.level===9&&h.windSealThreat&&h.windSealThreat.nearBodyWarning===true&&!h.windSealThreat.ambiguous&&prior.id===p.pauseTerminalId&&prior.session===r.session&&prior.frameId===r.expectedFrameId&&v.pauseVerified===true&&proof&&proof.verified&&proof.kind==='inventory'&&proof.sourceFrameId===w.frameId&&(w.ocr||[]).some(t=>t.text.trim()==='Eye of the Storm'&&t.x>=800&&t.x<=900&&t.y<=45)&&(w.ocr||[]).some(t=>/693306810$/.test(t.text.trim())&&t.x>1600&&t.y>1020));
 }
 async function run(o,api){
  const started=api.now();let heldAt=null;
  try{
   api.check();await api.key('VK_ESCAPE',60,o);await api.sleep(100);api.check();heldAt=api.now();api.down('VK_A');
   await api.sleep(60);api.check();if(api.now()-heldAt>400)throw Error('Directional dodge budget expired');await api.key('VK_SHIFT',60,o);
   await api.sleep(90);api.check();if(api.now()-heldAt>400)throw Error('Directional dodge budget expired');api.up('VK_A');
   await api.sleep(150);api.check();
   return {defensiveProbe:true,direction:'VK_A',directionHoldBudgetMs:400,plannedDirectionHoldMs:210,directionOverlapsDash:true,unpauseToDirectionDelayMs:160,unpauseToDashDelayMs:220,elapsedMs:api.now()-started,phaseReact:false,escapeVerified:false};
  }finally{api.up('VK_SHIFT');api.up('VK_A');api.release();}
 }

 root.ActTwoEyeDefense={permit,run};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoEyeDefense;
})(typeof globalThis!=='undefined'?globalThis:this);
