(function(root){
 'use strict';
 const radius=3; // At least the starter exploration arrival tolerance.
 function position(p){return !!(p&&p.map==='Teyvat'&&Number.isFinite(p.x)&&Number.isFinite(p.y)&&p.x>=-1700&&p.x<=-500&&p.y>=1400&&p.y<=2850);}
 function distance(a,b){return Math.hypot(a.x-b.x,a.y-b.y);}
 function hazard(w){return !!(w&&w.hud&&((w.hud.enemyBars||[]).length||(w.hud.objectives||[]).some(t=>/^Defeatallopponents\d+\/\d+$/.test(String(t).replace(/\s/g,'')))));}
 function inspect(w,route,now,session){
  if(!w||w.session!==session||!Number.isInteger(w.frameId)||w.fastSample||w.mapPositionInherited||!position(w.map)||!w.hud||!w.hud.world||!w.hud.groundControls||w.hud.climbing||!Number.isFinite(w.timestamp)||now<w.timestamp||now-w.timestamp>600000||!(w.ocr||[]).some(r=>/^(?:UID)?[: ]*693306810$/.test(String(r.text).trim())&&r.x>1600&&r.y>1020))return 'Fresh original-account grounded navigation witness required';
  if(!route||!Array.isArray(route.waypoints)||!route.waypoints.length||!route.waypoints.every(position))return 'Finite navigation destinations required';
  if(hazard(w)&&route.waypoints.every(p=>distance(w.map,p)<=radius))return 'Hazard-side zero-motion navigation refused before unpause';
  const e=route.escape;
  if(e!==undefined){
   if(!e||!position(e.hazard)||!Number.isFinite(e.minimumSeparationGain)||e.minimumSeparationGain<6||e.minimumSeparationGain>30||!Number.isFinite(e.minimumMovement)||e.minimumMovement<4||e.minimumMovement>30)return 'Escape requires reviewed hazard, movement and separation bounds';
   const end=route.waypoints[route.waypoints.length-1];
   if(distance(w.map,end)<e.minimumMovement+radius||distance(end,e.hazard)<distance(w.map,e.hazard)+e.minimumSeparationGain+radius)return 'Escape destination cannot provide separation outside arrival tolerance';
  }
  return null;
 }
 function plan(p,r,w,now){return !!(p&&p.reviewed===true&&!p.usedAt&&p.requestId===r.id&&p.session===r.session&&p.frameId===r.expectedFrameId&&p.witnessFrameId===w.frameId&&w.frameId<p.frameId&&now>=p.createdAt&&now-p.createdAt<=120000&&p.route&&p.route.objective===r.objective&&JSON.stringify(p.route.waypoints)===JSON.stringify(r.waypoints)&&!inspect(w,p.route,now,r.session));}
 function arrival(p,w,current,movements){
  if(!p||!p.route.escape)return null;
  const e=p.route.escape;
  if(!current||current.session!==w.session||!position(current.map)||current.mapPositionInherited||!current.hud||!current.hud.groundControls||current.hud.climbing||!(movements>0)||distance(w.map,current.map)<e.minimumMovement||distance(current.map,e.hazard)<distance(w.map,e.hazard)+e.minimumSeparationGain)return 'Escape arrival lacks actual movement and hazard separation';
  return null;
 }
 root.NavigationSafety={inspect,plan,arrival,hazard,radius};if(typeof module!=='undefined'&&module.exports)module.exports=root.NavigationSafety;
})(typeof globalThis!=='undefined'?globalThis:this);
