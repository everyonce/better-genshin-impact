(function(root){
 'use strict';
 async function run(initial,api,observe){
  let current=initial,attempted=false;
  function fresh(o){return !!o&&o.session===api.session&&api.original(o)&&api.now()>=o.timestamp&&api.now()-o.timestamp<=1000;}
  if(!fresh(current))throw new Error('Fresh original-account food modal required');
  if(!api.selected(current)){
   const target=api.selectTarget(current);if(!target)throw new Error('Recognized Sweet Madame character modal required');
   await api.click(target,current,'selectKaeya');await api.sleep(350);current=await observe();
  }
  const target=fresh(current)&&api.feedTarget(current);
  if(!target)throw new Error('Exact Kaeya and same-frame quantity one required');
  attempted=true;await api.click(target,current,'useOneSweetMadame');await api.sleep(500);current=await observe();
  return {status:'stopped',step:'actTwoHeal',foodUseAttempted:attempted,foodUseAttempts:1,healingVerified:false,frameId:current.frameId,pauseVerified:api.paused(current)};
 }
 root.ActTwoHeal={run};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoHeal;
})(typeof globalThis!=='undefined'?globalThis:this);
