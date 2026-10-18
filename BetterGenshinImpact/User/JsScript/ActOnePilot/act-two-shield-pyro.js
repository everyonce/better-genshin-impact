(function(root){
 'use strict';
 function original(o){return (o.ocr||[]).some(r=>/^(?:UID)?[: ]*693306810$/.test(String(r.text).trim())&&r.x>1600&&r.y>1020);}
 function event(o){return (o.hud.objectives||[]).some(t=>/^Defeatallopponents[0-8]\/9$/.test(String(t).replace(/[\s-]/g,'')));}
 function base(o,now,session){const h=o&&o.hud,hp=h&&h.health;return !!(o&&o.session===session&&now>=o.timestamp&&now-o.timestamp<=1000&&original(o)&&h&&!h.climbing&&!h.auto&&!h.bigMap&&!h.journal&&!h.dialogueReady&&!h.choice&&hp&&hp.current>0&&hp.current<=hp.max&&!o.ocr.some(r=>/Frozen|Cannot switch|Unable to switch/i.test(r.text)));}
 function scope(o,p){const m=o.map,h=o.hud;return !!(m&&m.map==='Teyvat'&&(p.mode==='practice'?Math.hypot(m.x+1265.917,m.y-1928.381)<=8&&!h.enemyBars.length&&(h.objectives||[]).every(t=>String(t).replace(/[^A-Za-z]/g,'').length<=5):Math.hypot(m.x+1476.6,m.y-2314.4)<=4&&event(o)));}
 function plan(p,r,now){return !!(p&&p.reviewed===true&&!p.usedAt&&p.session===r.session&&p.frameId===r.expectedFrameId&&now>=p.createdAt&&now-p.createdAt<=120000&&['practice','inspect','fire','replay','burst','recover'].includes(p.mode)&&(p.fast===undefined||p.fast===true)&&(p.mode!=='replay'||Array.isArray(p.replayFrameIds)&&p.replayFrameIds.length>0&&p.replayFrameIds.length<=3&&p.replayFrameIds.every(f=>Number.isInteger(f)&&f>0&&(f<p.frameId||p.replayPhaseReviewed===true&&f>=260000000)))&&p.offset&&Number.isInteger(p.offset.dx)&&Math.abs(p.offset.dx)<=200&&Number.isInteger(p.offset.dy)&&Math.abs(p.offset.dy)<=200&&(p.mode!=='fire'||p.vision===true&&p.woodenShieldReviewed===true&&Number.isInteger(p.aimWitnessFrameId)&&(p.aimWitnessFrameId<p.frameId||Number.isInteger(p.aimWitnessSourceFrameId)&&p.aimWitnessSourceFrameId<p.frameId))&&(p.mode!=='burst'||p.vision===true&&p.woodenShieldReviewed===true&&p.rangeAndFacingReviewed===true));}
 function ground(o,now,session,max){return base(o,now,session)&&o.hud.groundControls&&o.hud.health.max===max;}
 function aim(o,now,session){return base(o,now,session)&&!o.hud.groundControls&&o.hud.health.max===1733&&(o.ocr||[]).some(r=>r.text==='R'&&r.x>1680&&r.x<1770&&r.y>1010&&r.y<1055);}
 function slot(o,name,y){return (o.ocr||[]).some(r=>r.text===name&&r.x>=1650&&r.y>=y&&r.y<=y+65);}
 async function run(initial,p,api){
  const alreadyAmber=(p.mode==='practice'&&ground(initial,api.now(),initial.session,1733)||p.mode==='recover'&&(ground(initial,api.now(),initial.session,1733)||aim(initial,api.now(),initial.session)))&&initial.hud.health.current===1733;
  if(!alreadyAmber&&(!ground(initial,api.now(),initial.session,4015)||initial.hud.health.current<3814||!scope(initial,p)||!slot(initial,'Amber',330)))throw Error('Fresh healthy Kaeya at reviewed safe bank or Statue required');
  if(!scope(initial,p))throw Error('Reviewed shield or safe Statue scope required');
  let o=initial,start=api.now(),amberStart=null;const result={status:'stopped',mode:p.mode,shots:0,returnedKaeya:false,frames:[]};
  const healthy=()=>o.hud.health.current>=1647&&(!amberStart||amberStart-o.hud.health.current<=86);
  function budget(ms){if(api.checkAction)api.checkAction(ms||0);}
  async function sample(){o=await api.observe();budget();result.frames.push(o.frameId);if(api.now()-start>10000)throw Error('Pyro exposure deadline');return o;}
  try{
   if(p.mode==='recover'){throw Error('Recovery only; release aim and return to Kaeya');}
   budget(1500);if(!alreadyAmber){await api.key('VK_2',60,o);await api.sleep(p.primitive==='burst'||p.mode==='burst'?800:400);await sample();}
   if(!ground(o,api.now(),initial.session,1733)||!scope(o,p)||!healthy())throw Error('Fresh healthy upgraded Amber required');
   amberStart=o.hud.health.current;result.startHealth=amberStart;
   if(p.mode==='burst'||p.primitive==='burst'){
    result.burstReadiness=o.shieldVision&&o.shieldVision.amberBurstReady===true;
    if(p.mode==='practice'){result.reason='Burst readiness inspected without consuming energy';}
    else{
     budget(1800);result.policy=api.shieldDecision(initial,o,p);
     if(result.policy.action!=='apply-element'||result.policy.capability!=='Amber.Q')throw Error(result.policy.reason||'Shield policy refused burst');
     await api.key('VK_Q',60,o);result.bursts=1;await api.sleep(650);await sample();
     result.impactFrameId=o.frameId;result.reason='One ready Pyro burst attempted; shield effect requires separate verification';
    }
   }else{
   budget(1200);await api.key('VK_R',60,o);await api.sleep(350);await sample();
   if(!aim(o,api.now(),initial.session)||!healthy())throw Error('Fresh healthy Amber aim required');
   if(p.offset.dx||p.offset.dy){await api.look(p.offset,o);await api.sleep(300);await sample();}
   if(p.mode==='fire'&&p.vision===true){const d=api.centerShield(o);await api.look(d,o);await api.sleep(300);await sample();}
   const targetBefore=o;result.aimFrameId=o.frameId;
   if(p.mode==='fire'||p.mode==='practice'&&p.practiceFire===true){
    if(!aim(o,api.now(),initial.session)||!healthy())throw Error('Aim or health changed');
    budget(2600);await api.sleep(1800);await sample();result.chargedFrameId=o.frameId;
    if(!aim(o,api.now(),initial.session)||!healthy())throw Error('Stop before firing after health/aim change');
    if(p.mode==='fire'&&p.vision===true){result.policy=api.shieldFireDecision(targetBefore,o,p);if(result.policy.action!=='apply-element')throw Error(result.policy.reason||'Fresh centered shield required');}
    budget(500);await api.key('VK_LBUTTON',60,o);result.shots=1;await api.sleep(300);await sample();result.impactFrameId=o.frameId;
   }
   result.reason=result.shots===1?'One charged arrow fired; verify shield effect and defeat separately':'Aim inspected without firing';
   }
  }catch(e){result.reason=String(e.message||e);}
  finally{
   await api.release();
   // Recovery observations omit target vision but retain identity, health and freshness guards.
   const recoveryObserve=api.observeRecovery||api.observe;
   if(!base(o,api.now(),initial.session))o=await recoveryObserve();
   if(aim(o,api.now(),initial.session)){await api.key('VK_R',60,o);await api.sleep(350);o=await recoveryObserve();}
   if(ground(o,api.now(),initial.session,1733)&&!slot(o,'Kaeya',420)){await api.sleep(200);o=await recoveryObserve();}
   if(ground(o,api.now(),initial.session,1733)&&slot(o,'Kaeya',420)){await api.key('VK_3',60,o);await api.sleep(400);o=await recoveryObserve();result.returnedKaeya=ground(o,api.now(),initial.session,4015);}
   await api.release();
  }
  result.current=o;result.health=o.hud.health;result.exposureMs=api.now()-start;return result;
 }
 root.ActTwoShieldPyro={original,event,base,scope,plan,ground,aim,run};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoShieldPyro;
})(typeof globalThis!=='undefined'?globalThis:this);
