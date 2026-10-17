(function(root){
 'use strict';
 function plan(p){return !!(p&&['inspect','fire'].includes(p.thornPyro)&&p.mode==='actions'&&p.visualPositionReviewed===true&&Number.isInteger(p.regionMapFrameId)&&p.actions&&p.actions.length===0&&p.thornReviewed===true&&p.aimOffset&&Number.isInteger(p.aimOffset.dx)&&Math.abs(p.aimOffset.dx)<=200&&Number.isInteger(p.aimOffset.dy)&&Math.abs(p.aimOffset.dy)<=200);}
 function base(o,now,session){const h=o&&o.hud,r=o&&o.ocr||[],hp=h&&h.health;return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&h&&!h.climbing&&!h.auto&&!h.journal&&!h.bigMap&&!h.dialogueReady&&!h.choice&&hp&&Number.isFinite(hp.current)&&hp.current>0&&hp.current<=hp.max&&Array.isArray(h.enemyBars)&&Array.isArray(h.objectives)&&h.objectives.every(t=>String(t).replace(/[^A-Za-z]/g,'').length<=5)&&r.some(x=>/^(?:UID)?[: ]*693306810$/.test(String(x.text).trim())&&x.x>1600&&x.y>1020)&&r.filter(x=>/^(Lumina|Amber|Kaeya|Lisa)$/.test(x.text)&&x.x>=1650&&x.y>=240&&x.y<=580).length>=2);}
 function slot(o,name,y){return(o.ocr||[]).some(r=>r.text===name&&r.x>=1650&&r.y>=y&&r.y<=y+65);}
 function ground(o,now,session,max,safe){return base(o,now,session)&&o.hud.groundControls&&o.hud.health.max===max&&(!safe||o.hud.health.current>=max*.85&&!o.hud.enemyBars.length);}
 function aim(o,now,session,safe){return base(o,now,session)&&!o.hud.groundControls&&o.hud.health.max===1186&&(o.ocr||[]).some(r=>r.text==='R'&&r.x>1680&&r.x<1770&&r.y>1010&&r.y<1055)&&(!safe||o.hud.health.current>=1186*.85&&!o.hud.enemyBars.length);}
 async function run(initial,p,api){
  if(!plan(p)||!ground(initial,api.now(),initial.session,4015,true)||!slot(initial,'Amber',330))throw Error('Reviewed thorn and healthy regional Kaeya required');
  let o=initial;const result={status:'stopped',thornPyro:p.thornPyro,shots:0,selectedAmber:false,returnedKaeya:false};
  try{
   await api.key('VK_2',60,o);result.selectedAmber=true;await api.sleep(350);o=await api.observe();result.amberFrameId=o.frameId;
   if(!ground(o,api.now(),initial.session,1186,true))throw Error('Fresh healthy Amber ground evidence required');
   await api.key('VK_R',60,o);await api.sleep(350);o=await api.observe();result.aimFrameId=o.frameId;
   if(!aim(o,api.now(),initial.session,true))throw Error('Fresh healthy Amber aim evidence required');
   if(p.aimOffset.dx||p.aimOffset.dy){await api.look(p.aimOffset,o);await api.sleep(200);o=await api.observe();result.adjustedFrameId=o.frameId;}
   if(p.thornPyro==='fire'){
    if(!aim(o,api.now(),initial.session,true))throw Error('Aim changed before charge');
    await api.sleep(1800);o=await api.observe();result.chargedFrameId=o.frameId;
    if(!aim(o,api.now(),initial.session,true))throw Error('Aim health or threats changed during charge');
    await api.key('VK_LBUTTON',60,o);result.shots=1;await api.sleep(600);o=await api.observe();result.impactFrameId=o.frameId;
   }
  }catch(e){result.reason=String(e.message||e);}
  finally{
   await api.release();o=await api.observe();
   if(aim(o,api.now(),initial.session,false)){await api.key('VK_R',60,o);await api.sleep(250);o=await api.observe();}
   if(ground(o,api.now(),initial.session,1186,false)&&slot(o,'Kaeya',420)){await api.key('VK_3',60,o);await api.sleep(350);o=await api.observe();result.returnedKaeya=ground(o,api.now(),initial.session,4015,false);}
   await api.release();
  }
  result.fieldFrameId=o.frameId;result.health=o.hud&&o.hud.health;result.reason=result.reason||(p.thornPyro==='inspect'?'Aim inspection ended without firing':'One Pyro arrow fired; inspect actual barrier effect');return result;
 }
 root.ActTwoThornPyro={plan,base,ground,aim,run};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoThornPyro;
})(typeof globalThis!=='undefined'?globalThis:this);
