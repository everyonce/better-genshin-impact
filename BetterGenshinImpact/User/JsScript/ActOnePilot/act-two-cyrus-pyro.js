(function(root){
 'use strict';
 function field(o,now,session,original){
  const h=o&&o.hud,m=o&&o.map,hp=h&&h.health;
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&original(o)&&h&&h.world&&h.groundControls&&!h.climbing&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.bigMap&&!h.journal&&m&&m.map==='Teyvat'&&Math.hypot(m.x+1220,m.y-2315)<=35&&hp&&hp.current>0&&hp.current<=hp.max&&(h.objectives||[]).some(t=>String(t).replace(/[^a-z]/gi,'').toLowerCase()==='defeattheattackingmonsters'));
 }
 function slot(o,name,key,y){const r=o.ocr||[];return r.some(x=>x.text===name&&x.x>=1650&&x.x<=1800&&x.y>=y&&x.y<=y+70)&&r.some(x=>x.text===key&&x.x>=1840&&x.x<=1900&&x.y>=y&&x.y<=y+70);}
 function preparation(o,now,session,original){return field(o,now,session,original)&&o.hud.health.max===2635&&o.hud.health.current>=2635*.9&&slot(o,'Amber','2',330);}
 function amber(o,now,session,original){return field(o,now,session,original)&&o.hud.health.max===1186&&o.hud.health.current>=1186*.9;}
 function returning(o,now,session,original){return field(o,now,session,original)&&o.hud.health.max===1186&&slot(o,'Kaeya','3',430);}
 async function run(initial,api){
  let current=initial;const result={status:'stopped',pyroSupport:true,selectedAmber:false,bursts:0,skills:0,returnedKaeya:false};
  if(!preparation(current,api.now(),api.session,api.original))throw new Error('Fresh healthy Kaeya and Amber slot required in Cyrus ambush');
  try{
   await api.key('VK_2',60,current);result.selectedAmber=true;await api.sleep(350);current=await api.observe();
   if(!amber(current,api.now(),api.session,api.original))throw new Error('Fresh healthy Amber required before Pyro support');
   result.amberHealth=current.hud.health;
   await api.key('VK_Q',60,current);result.bursts++;await api.sleep(650);current=await api.observe();
   if(amber(current,api.now(),api.session,api.original)){await api.key('VK_E',60,current);result.skills++;await api.sleep(200);current=await api.observe();}
  }catch(e){result.reason=String(e.message||e);}
  finally{
   await api.release();
   if(result.selectedAmber){
    current=await api.observe();
    if(returning(current,api.now(),api.session,api.original)){await api.key('VK_3',60,current);await api.sleep(350);current=await api.observe();result.returnedKaeya=current.hud.health&&current.hud.health.max===2635;}
   }
  }
  result.current=current;result.fieldHealth=current.hud.health;return result;
 }
 root.ActTwoCyrusPyro={field,preparation,amber,returning,run};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoCyrusPyro;
})(typeof globalThis!=='undefined'?globalThis:this);
