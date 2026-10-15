(function(root){
 'use strict';
 function plan(p,r,now){
  if(!p||p.reviewed!==true||p.usedAt||p.session!==r.session||p.frameId!==r.expectedFrameId||!Number.isInteger(p.witnessFrameId)||p.witnessFrameId>=p.frameId||!Number.isFinite(p.createdAt)||now<p.createdAt||now-p.createdAt>120000||!Number.isInteger(p.timeoutMs)||p.timeoutMs<1000||p.timeoutMs>15000)return false;
  const points=p.route&&p.route.positions;
  return !!(Array.isArray(points)&&points.length>0&&points.length<=5&&points.every((v,i)=>v&&Number.isFinite(v.x)&&Number.isFinite(v.y)&&region(v,p.region)&&['path','target'].includes(v.type)&&v.move_mode==='walk'&&!v.action&&!v.action_params&&(!i||Math.hypot(v.x-points[i-1].x,v.y-points[i-1].y)<=50)));
 }
 function region(m,name){return name==='windrise'?m.x>=-1300&&m.x<=-650&&m.y>=1750&&m.y<=2050:!name&&m.x>=-880&&m.x<=-700&&m.y>=2180&&m.y<=2320;}
 function field(o,w,now,session,name){
  const h=o&&o.hud,m=o&&o.map,wm=w&&w.map,hp=h&&h.health;
  const objective=h&&(h.objectives||[]).slice(0,2).join('').normalize('NFD').replace(/[^A-Za-z]/g,'');
  return !!(o&&o.session===session&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&wm&&m.map==='Teyvat'&&wm.map==='Teyvat'&&region(m,name)&&Math.hypot(m.x-wm.x,m.y-wm.y)<=8&&h.world&&h.groundControls&&!h.climbing&&!h.auto&&!h.choice&&!h.dialogueReady&&!h.bigMap&&!h.journal&&hp&&hp.max===2313&&hp.current===2313&&h.enemyBarDiagnostic&&!(h.enemyBars||[]).length&&(objective==='SolvethemysteryGotoKaeyaattheKnightsofFavoniusHQforahint'||name==='windrise'&&!objective));
 }
 async function run(native,check,sleep,route,timeoutMs){
  check();const cts=native.createCancellation();let task,monitor,done=false;
  try{
   task=Promise.resolve().then(()=>native.run(JSON.stringify(route),timeoutMs,cts.Token));
   monitor=(async()=>{while(!done){await sleep(100);if(!done)check();}})();
   return await Promise.race([task,monitor]);
  }finally{
   done=true;
   try{cts.Cancel();}finally{try{if(task)await task.catch(()=>{});if(monitor)await monitor.catch(()=>{});}finally{cts.Dispose();}}
  }
 }
 function telemetry(start,end,regionName,executionMs,wallMs){
  const a=start&&start.map,b=end&&end.map,d=a&&b?Math.hypot(b.x-a.x,b.y-a.y):NaN;
  const plausible=!!(a&&b&&a.map==='Teyvat'&&b.map==='Teyvat'&&region(a,regionName)&&region(b,regionName)&&Number.isFinite(d)&&d<=executionMs/1000*10+10);
  return {startFrameId:start&&start.frameId,endFrameId:end&&end.frameId,startPosition:a||null,endPosition:b||null,nativeExecutionMs:executionMs,wallMs,positionEstimatePlausible:plausible,minimapDisplacementEstimate:plausible?Math.round(d*100)/100:null,displacementVerified:false,positionWarning:plausible?'Minimap estimate; inspect terrain and map before treating as verified progress':'Endpoint failed region or speed plausibility; do not use for travel'};
 }
 root.ActTwoNativeRoute={plan,field,run,telemetry};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoNativeRoute;
})(typeof globalThis!=='undefined'?globalThis:this);
