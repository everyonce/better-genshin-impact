(function(root){'use strict';
 const sourceSession='mvf4mx8b-ocb3bio5j5p',sourceFrame=13;
 const angle=(a,b)=>Math.abs((a-b+540)%360-180);
 const height=o=>{const matches=(o&&o.hud&&o.hud.objectives||[]).map(t=>/^\s*Higher\s*(\d+)m$/.exec(String(t))).filter(Boolean);return matches.length===1?Number(matches[0][1]):null;};
 function common(o,session,now){const h=o&&o.hud,m=o&&o.map,p=h&&h.health;return !!(o&&o.session===session&&Number.isInteger(o.frameId)&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&m.map==='Teyvat'&&Math.hypot(m.x+842.42578125,m.y-2210.25390625)<=.5&&angle(m.cameraAngle,322)<=9&&h&&h.world===true&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&p&&p.max===4015&&p.current===4015&&h.enemyBarDiagnostic&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Lookforthelocationintheriddle')&&(o.ocr||[]).some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(String(r.text).trim())));}
 function entry(o,session,now){return common(o,session,now)&&o.hud.groundControls===true&&o.hud.climbing===false&&height(o)===27&&Math.hypot(o.map.x+842.42578125,o.map.y-2210.25390625)<=.18&&angle(o.map.cameraAngle,322)<=5;}
 function attached(o,session,now){return common(o,session,now)&&o.hud.climbing===true&&o.hud.groundControls===false&&[25,26,27].includes(height(o))&&(o.ocr||[]).some(r=>r.text==='X'&&r.x>1550&&r.y>980);}
 function grounded(o,session,now){return common(o,session,now)&&o.hud.groundControls===true&&o.hud.climbing===false&&height(o)>=26&&height(o)<=28;}
 function permit(p,r,inventory,gate,now){return !!(p&&r&&r.step==='actTwoWallStaminaTiming'&&!p.usedAt&&p.session===r.session&&p.frameId===r.expectedFrameId&&p.sourceSession===sourceSession&&p.sourceFrame===sourceFrame&&typeof p.sha256==='string'&&/^[a-f0-9]{64}$/.test(p.sha256)&&Number.isFinite(p.createdAt)&&now>=p.createdAt&&now-p.createdAt<=120000&&gate(inventory,now,r.session));}
 async function run(initial,api){let current=initial,reads=0,inputs=0,held=false;const session=initial.session,start=api.now(),r={status:'stopped',step:'actTwoWallStaminaTiming',inputs:0,fastSamples:[],groundRecovered:false,staminaVerified:false};
  const check=()=>{api.check();if(api.now()-start>10000)throw Error('Timing probe local deadline reached');};
  const observe=async()=>{check();const before=current;current=await api.observe();reads++;check();if(!current||current.session!==session||current.frameId<=before.frameId||current.timestamp<before.timestamp||api.now()-current.timestamp>1000)throw Error('Timing probe observation continuity failed');};
  async function sample(label,downAt){check();const s=await api.sample(label,downAt);check();if(!s||s.valid!==true||!Number.isFinite(s.capturedAt)||s.capturedAt<downAt||s.capturedAt-api.now()>0)throw Error('Fast stamina sample invalid');r.fastSamples.push({...s,label,relativeHoldMs:s.capturedAt-downAt});}
  try{check();if(!entry(current,session,api.now()))throw Error('Fresh reviewed ground pose changed; no W input');
   const downAt=api.now();await api.down(current);inputs++;held=true;
   await api.sleep(80);await sample('held-early',downAt);
   if(api.now()-downAt<210){await api.sleep(210-(api.now()-downAt));await sample('held-late',downAt);}
   await api.release();held=false;r.forwardHoldMs=api.now()-downAt;
   r.holdOverBudget=r.forwardHoldMs>500;
   if(!r.holdOverBudget)await sample('after-forward-release',downAt);
   await api.sleep(250);await observe();
   if(attached(current,session,api.now())){
    r.climbingObserved=true;r.lowHeight=height(current);r.heightBoundKept=r.lowHeight>=26;
    r.releaseAttempted=true;await api.key('VK_X',60,current);inputs++;await api.release();await api.sleep(300);await observe();
    for(let i=0;i<2&&!grounded(current,session,api.now())&&common(current,session,api.now())&&!current.hud.climbing;i++){await api.sleep(200);await observe();}
   }
   r.groundRecovered=grounded(current,session,api.now());r.staminaCandidate=r.fastSamples.some(s=>s.stamina&&s.stamina.kind==='usable'&&s.stamina.pixels>=180);
   r.reason=r.groundRecovered?(r.holdOverBudget?'Forward hold exceeded budget but release reached verified ground':'One timing probe ended on verified ground'):'Timing probe landing unverified; pause protection required';return r;
  }catch(e){r.reason=String(e&&e.message||e);
   try{await api.release();if(inputs>0&&!r.releaseAttempted){if(!attached(current,session,api.now()))await observe();if(attached(current,session,api.now())){r.climbingObserved=true;r.lowHeight=height(current);r.heightBoundKept=r.lowHeight>=26;r.releaseAttempted=true;await api.key('VK_X',60,current);inputs++;await api.release();await api.sleep(300);await observe();r.groundRecovered=grounded(current,session,api.now());r.recoveredAfterFailure=true;}}}catch(recoveryError){r.recoveryError=String(recoveryError&&recoveryError.message||recoveryError);}
   return r;}
  finally{await api.release();held=false;r.inputs=inputs;r.reads=reads;r.frameId=current&&current.frameId;r.health=current&&current.hud&&current.hud.health;r.map=current&&current.map;r.climbAfterRelease=current&&current.hud&&current.hud.climbing;}
 }
 root.ActTwoWallStaminaTiming={sourceSession,sourceFrame,entry,attached,grounded,permit,run};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoWallStaminaTiming;
})(typeof globalThis!=='undefined'?globalThis:this);
