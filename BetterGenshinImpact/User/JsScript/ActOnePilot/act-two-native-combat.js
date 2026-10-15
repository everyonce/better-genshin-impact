(function(root){
 'use strict';
 // A short native rotation owns combat inputs. Quest code owns entry and pause.
 const strategy='凯亚 e(fast), attack(1)';
 function field(o,now,session,original){
  const h=o&&o.hud,p=o&&o.map,hp=h&&h.health;
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&original(o)&&h&&h.world===true&&h.groundControls===true&&!h.climbing&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.bigMap&&!h.journal&&!h.tutorialStep&&hp&&[2313,2635].includes(hp.max)&&hp.current>=hp.max*0.85&&hp.current<=hp.max&&p&&p.map==='Teyvat'&&p.x>=-1600&&p.x<=-700&&p.y>=1450&&p.y<=2700);
 }
 function targets(o){
  // Exact level OCR is deliberately unnecessary. Require a substantial,
  // rectangular enemy health segment in the central combat view instead.
  return (o&&o.hud&&o.hud.enemyBars||[]).filter(b=>[b.x,b.y,b.width,b.height,b.rectangularity].every(Number.isFinite)&&b.x>=650&&b.x<=1270&&b.y>=200&&b.y<=850&&b.width>=16&&b.width<=300&&b.height>=3&&b.height<=20&&b.width/b.height>=3.5&&b.rectangularity>=0.8&&b.rectangularity<=1.05);
 }
 function encounter(o,now,session,original,group){
  if(!field(o,now,session,original))return false;
  const n=targets(o).length,h=o.hud;
  if(!group)return n===1;
  return h.health.current>=h.health.max*0.9&&n>=1&&n<=3&&(h.enemyBars||[]).length<=3&&Math.hypot(o.map.x+1125,o.map.y-2230)<=50&&(h.objectives||[]).some(t=>/^\([0-2]\/3\)$/.test(t))&&(h.objectives||[]).some(t=>String(t).replace(/[^A-Za-z]/g,'')==='Questareareached');
 }
 function finish(o,w,receipt,p,r,now,original){
  const v=receipt&&receipt.details&&receipt.details.result;
  return !!(p&&p.reviewed===true&&!p.usedAt&&p.session===r.session&&p.frameId===r.expectedFrameId&&now>=p.createdAt&&now-p.createdAt<=120000&&receipt.id===p.priorId&&receipt.session===r.session&&receipt.frameId===p.frameId&&receipt.status==='stopped'&&v&&v.nativeGroup===true&&v.nativeReturned===true&&v.pauseVerified===true&&v.beforeBars&&v.beforeBars.length>0&&v.afterBars&&v.afterBars.length===0&&w&&w.frameId===v.afterFrameId&&w.session===r.session&&now>=w.timestamp&&now-w.timestamp<=600000&&original(w)&&field(o,now,r.session,original)&&o.hud.health.current>=o.hud.health.max*.9&&w.map&&Math.hypot(o.map.x-w.map.x,o.map.y-w.map.y)<=6&&Math.hypot(o.map.x+1125,o.map.y-2230)<=50&&(o.hud.objectives||[]).some(t=>/^\([0-2]\/3\)$/.test(t)));
 }
 async function chunk(native,checkStop,options){
  const {now,sleep}=options,timeoutMs=options.timeoutMs||4000;
  checkStop();
  const cts=native.createCancellation();
  let done=false,fight,monitor,cancelled=false;
  const cancel=()=>{if(!cancelled){cancelled=true;cts.Cancel();}};
  try{
   const start=now();
   fight=Promise.resolve().then(()=>{checkStop();return native.run(strategy,cts.Token);});
   monitor=(async()=>{while(!done){await sleep(50);if(done)return;checkStop();if(now()-start>=timeoutMs)throw new Error('Native rotation cooperative deadline reached');}})();
   await Promise.race([fight,monitor]);
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
 root.ActTwoNativeCombat={strategy,field,targets,encounter,finish,chunk};
 if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoNativeCombat;
})(typeof globalThis!=='undefined'?globalThis:this);
