(function(root){
 'use strict';
 function plan(p,r,now){
  if(!p||p.reviewed!==true||p.usedAt||p.session!==r.session||p.frameId!==r.expectedFrameId||!Number.isInteger(p.witnessFrameId)||p.witnessFrameId>=p.frameId||!Number.isFinite(p.createdAt)||now<p.createdAt||now-p.createdAt>120000||!Number.isInteger(p.timeoutMs)||p.timeoutMs<1000||p.timeoutMs>15000)return false;
  const points=p.route&&p.route.positions;
  return !!(Array.isArray(points)&&points.length>0&&points.length<=5&&points.every((v,i)=>v&&Number.isFinite(v.x)&&Number.isFinite(v.y)&&v.x>=-880&&v.x<=-700&&v.y>=2180&&v.y<=2320&&['path','target'].includes(v.type)&&v.move_mode==='walk'&&!v.action&&!v.action_params&&(!i||Math.hypot(v.x-points[i-1].x,v.y-points[i-1].y)<=50)));
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
 root.ActTwoNativeRoute={plan,run};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoNativeRoute;
})(typeof globalThis!=='undefined'?globalThis:this);
