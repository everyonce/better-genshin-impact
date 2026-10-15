(function(root){
 'use strict';
 // A short native rotation owns combat inputs. Quest code owns entry and pause.
 const strategy='凯亚 e(fast), attack(1)';
 const ambushStrategy='当前角色 e, attack(1)';
 const groupStrategy='凯亚 e(fast), q, attack(1)';
 function field(o,now,session,original){
  const h=o&&o.hud,p=o&&o.map,hp=h&&h.health;
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&original(o)&&h&&h.world===true&&h.groundControls===true&&!h.climbing&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.bigMap&&!h.journal&&!h.tutorialStep&&hp&&[2313,2635].includes(hp.max)&&hp.current>=hp.max*0.85&&hp.current<=hp.max&&p&&p.map==='Teyvat'&&p.x>=-1600&&p.x<=-700&&p.y>=1450&&p.y<=2700);
 }
 function deadlineProbe(o,now,session,original){return field(o,now,session,original)&&o.hud.health.current===o.hud.health.max&&(o.hud.enemyBars||[]).length===0&&Math.hypot(o.map.x+1265.917,o.map.y-1928.381)<=8;}
 function targets(o){
  // Exact level OCR is deliberately unnecessary. Require a substantial,
  // rectangular enemy health segment in the central combat view instead.
  return (o&&o.hud&&o.hud.enemyBars||[]).filter(b=>[b.x,b.y,b.width,b.height,b.rectangularity].every(Number.isFinite)&&b.x>=350&&b.x<=1600&&b.y>=200&&b.y<=850&&b.width>=16&&b.width<=300&&b.height>=3&&b.height<=20&&b.width/b.height>=3.5&&b.rectangularity>=0.8&&b.rectangularity<=1.05);
 }
 function thirdCamp(m){return !!m&&Math.hypot(m.x+1220,m.y-2315)<=35;}
 function cyrusArea(m){return !!m&&(Math.hypot(m.x+1125,m.y-2230)<=50||Math.hypot(m.x+1415,m.y-2395)<=40||thirdCamp(m));}
 function encounter(o,now,session,original,group){
  if(!field(o,now,session,original))return false;
  const n=targets(o).length,h=o.hud;
  if(!group)return n===1;
  const ambush=thirdCamp(o.map)&&(h.objectives||[]).includes('Defeat the attacking monsters');
  const maxTargets=thirdCamp(o.map)&&((h.objectives||[]).includes('(2/3)')||ambush)?5:3;
  return h.health.current>=h.health.max*0.9&&n>=1&&n<=maxTargets&&(h.enemyBars||[]).length<=maxTargets&&cyrusArea(o.map)&&(ambush||(h.objectives||[]).some(t=>/^\([0-2]\/3\)$/.test(t))&&(h.objectives||[]).some(t=>String(t).replace(/[^A-Za-z]/g,'')==='Questareareached'));
 }
 function finish(o,w,receipt,p,r,now,original){
  const v=receipt&&receipt.details&&receipt.details.result;
  return !!(p&&p.reviewed===true&&!p.usedAt&&p.session===r.session&&p.frameId===r.expectedFrameId&&now>=p.createdAt&&now-p.createdAt<=120000&&receipt.id===p.priorId&&receipt.session===r.session&&receipt.frameId===p.frameId&&receipt.status==='stopped'&&v&&v.nativeGroup===true&&v.nativeReturned===true&&v.pauseVerified===true&&v.beforeBars&&v.beforeBars.length>0&&v.afterBars&&v.afterBars.length===0&&w&&w.frameId===v.afterFrameId&&w.session===r.session&&now>=w.timestamp&&now-w.timestamp<=600000&&original(w)&&field(o,now,r.session,original)&&o.hud.health.current>=o.hud.health.max*.9&&w.map&&Math.hypot(o.map.x-w.map.x,o.map.y-w.map.y)<=6&&cyrusArea(o.map)&&(o.hud.objectives||[]).some(t=>/^\([0-2]\/3\)$/.test(t)));
 }
 async function chunk(native,checkStop,options){
  const {now,sleep}=options,timeoutMs=options.timeoutMs||4000;
  checkStop();
  const cts=native.createCancellation();
  let done=false,fight,monitor,cancelled=false;
  const cancel=()=>{if(!cancelled){cancelled=true;cts.Cancel();}};
  try{
   // The native executor can synchronously occupy the JS engine. Arm its .NET
   // timer as well, so a character-switch retry cannot starve the JS monitor.
   if(native.armDeadline)native.armDeadline(cts,timeoutMs);
   else if(typeof cts.CancelAfter==='function')cts.CancelAfter(timeoutMs);
   const start=now();
   fight=Promise.resolve().then(()=>{checkStop();return native.run(options.strategy||strategy,cts.Token);});
   monitor=(async()=>{while(!done){await sleep(50);if(done)return;checkStop();if(now()-start>=timeoutMs)throw new Error('Native rotation cooperative deadline reached');}})();
   await Promise.race([fight,monitor]);
   if(cts.IsCancellationRequested===true)throw new Error('Native rotation cooperative deadline reached');
   checkStop();
   return {nativeReturned:true,nativeMs:now()-start,damageConfirmed:false,defeatConfirmed:false};
  }finally{
   done=true;
   try{cancel();}finally{
    try{if(fight)await fight.catch(()=>{});if(monitor)await monitor.catch(()=>{});}
    finally{try{native.release();}finally{cts.Dispose();}}
   }
  }
 }
 function progress(before,after){
  const count=o=>{const t=(o.hud.objectives||[]).find(t=>/^\([0-3]\/3\)$/.test(t));return t?Number(t[1]):-1;};
  if(count(after)>count(before))return 'quest_increment';
  const rewards=o=>(o.ocr||[]).filter(r=>/Character EXP|Mora/.test(r.text)&&r.x<650&&r.y>300&&r.y<850).map(r=>r.text).join('|');
  if(rewards(after)&&rewards(after)!==rewards(before))return 'new_reward';
  const a=targets(before),b=targets(after);
  // Conservative comparable-bar witness; a vanished target alone is not a kill.
  if(a.length===1&&b.length===1&&Math.abs(a[0].x-b[0].x)<180&&Math.abs(a[0].y-b[0].y)<100&&Math.abs(a[0].height-b[0].height)<=2&&b[0].width/b[0].height<a[0].width/a[0].height*.85)return 'bar_reduced';
  return null;
 }
 async function sequence(initial,api){
  let current=initial;const started=api.now(),turns=[];
  for(let i=0;i<4;i++){
   if(api.now()-started>=15000)return {current,turns,reason:'sequence_deadline'};
   if(!api.eligible(current))return {current,turns,reason:'encounter_or_health_guard'};
   const before=current,result=await api.run(current,i);await api.sleep(150);current=await api.observe();
   const evidence=progress(before,current);turns.push({beforeFrameId:before.frameId,afterFrameId:current.frameId,beforeHealth:before.hud.health,afterHealth:current.hud.health,evidence,...result});
   if(evidence==='quest_increment')return {current,turns,reason:evidence};
   if(!api.eligible(current))return {current,turns,reason:'encounter_or_health_guard'};
   if(!evidence)return {current,turns,reason:'no_damage_progress'};
  }
  return {current,turns,reason:'chunk_limit'};
 }
 root.ActTwoNativeCombat={strategy,groupStrategy,ambushStrategy,deadlineProbe,field,targets,encounter,finish,chunk,progress,sequence};
 if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoNativeCombat;
})(typeof globalThis!=='undefined'?globalThis:this);
