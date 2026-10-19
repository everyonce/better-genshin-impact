(function(root){'use strict';
 const witnessSession='mvf6vzeh-wwsokrqjsai',witnessFrame=15,witnessHash='db3a588d3b8e79d50e307e1bd13e62c9fc3dfdc96c76edc1761e29fe561cd2b9';
 const angle=(a,b)=>Math.abs((a-b+540)%360-180);
 const height=o=>{const rows=(o&&o.hud&&o.hud.objectives||[]).map(s=>/^\s*Higher\s*(\d+)m$/.exec(String(s))).filter(Boolean);return rows.length===1?Number(rows[0][1]):null;};
 function base(o,session,now){const h=o&&o.hud,m=o&&o.map,p=h&&h.health;return !!(o&&o.session===session&&Number.isInteger(o.frameId)&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&m.map==='Teyvat'&&Math.hypot(m.x+842.42578125,m.y-2210.2568359375)<=.35&&angle(m.cameraAngle,321.5)<=8&&h&&h.world===true&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&p&&p.max===4015&&p.current===4015&&h.enemyBarDiagnostic&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Lookforthelocationintheriddle')&&(o.ocr||[]).some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(String(r.text).trim())));}
 function groundPose(o,session,now){return base(o,session,now)&&o.hud.groundControls===true&&o.hud.climbing===false&&Math.hypot(o.map.x+842.42578125,o.map.y-2210.2568359375)<=.08&&angle(o.map.cameraAngle,321.5)<=2;}
 function entry(o,session,now){return groundPose(o,session,now)&&height(o)===27;}
 function attached(o,session,now){return base(o,session,now)&&o.hud.climbing===true&&o.hud.groundControls===false&&[26,27].includes(height(o))&&(o.ocr||[]).some(r=>r.text==='X'&&r.x>1550&&r.y>980);}
 function releaseReady(o,session,now){return base(o,session,now)&&o.hud.climbing===true&&o.hud.groundControls===false&&(height(o)===null||height(o)>=24&&height(o)<=27)&&(o.ocr||[]).some(r=>r.text==='X'&&r.x>1550&&r.y>980);}
 function grounded(o,session,now){return base(o,session,now)&&o.hud.groundControls===true&&o.hud.climbing===false&&[26,27,28].includes(height(o));}
 function permit(p,r,inventory,gate,now){return !!(p&&r&&r.step==='actTwoWallMicroAscent'&&!p.usedAt&&p.session===r.session&&p.frameId===r.expectedFrameId&&p.sourceSession===witnessSession&&p.sourceFrame===witnessFrame&&p.sha256===witnessHash&&Number.isFinite(p.createdAt)&&now>=p.createdAt&&now-p.createdAt<=120000&&gate(inventory,now,r.session));}
 async function run(initial,api){let current=initial,reads=0,inputs=0,mountAttempted=false,ascentAttempted=false,releaseAttempted=false;const session=initial.session,start=api.now(),r={status:'stopped',step:'actTwoWallMicroAscent',inputs:0,mountVerified:false,ascentObserved:false,groundRecovered:false,staminaVerified:false};
  const check=()=>{api.check();if(api.now()-start>11000)throw Error('Micro-ascent local deadline reached');};
  const observe=async()=>{check();const before=current;current=await api.observe();reads++;check();if(!current||current.session!==session||current.frameId<=before.frameId||current.timestamp<before.timestamp||api.now()-current.timestamp>1000)throw Error('Micro-ascent observation continuity failed');};
  async function releaseLow(){if(releaseAttempted||!releaseReady(current,session,api.now()))return;releaseAttempted=true;r.releaseAttempted=true;await api.key('VK_X',60,current);inputs++;await api.release();await api.sleep(300);await observe();r.groundRecovered=grounded(current,session,api.now());}
  try{check();if(!entry(current,session,api.now())&&groundPose(current,session,api.now())&&height(current)===null){await api.sleep(250);await observe();}
   if(!entry(current,session,api.now()))throw Error('Fresh low wall entry missing; no W input');
   mountAttempted=true;await api.key('VK_W',600,current);inputs++;await api.release();await api.sleep(250);await observe();
   if(!attached(current,session,api.now())){r.groundRecovered=grounded(current,session,api.now());r.reason=r.groundRecovered?'Mount did not attach; ground verified':'Mount outcome unverified';return r;}
   r.mountVerified=true;r.mountHeight=height(current);
   check();ascentAttempted=true;await api.key('VK_W',200,current);inputs++;await api.release();r.totalForwardBudgetMs=800;
   r.fastSample=await api.sample();check();await api.sleep(180);await observe();
   r.ascentObserved=releaseReady(current,session,api.now());r.afterAscentHeight=height(current);r.heightBoundKept=r.afterAscentHeight!==null&&r.afterAscentHeight>=25;
   r.staminaVerified=!!(r.fastSample&&r.fastSample.stamina&&r.fastSample.stamina.kind==='usable'&&current.hud.climbStamina&&Number.isFinite(current.hud.climbStamina.pixels)&&current.hud.climbStamina.pixels>=180);
   await releaseLow();r.reason=r.groundRecovered?'Micro-ascent ended on verified ground':'Landing unverified; pause protection required';return r;
  }catch(e){r.reason=String(e&&e.message||e);
   try{await api.release();if(mountAttempted&&!releaseAttempted){if(!releaseReady(current,session,api.now()))await observe();await releaseLow();r.recoveredAfterFailure=r.groundRecovered;}}catch(recoveryError){r.recoveryError=String(recoveryError&&recoveryError.message||recoveryError);}
   return r;}
  finally{await api.release();r.inputs=inputs;r.reads=reads;r.mountAttempted=mountAttempted;r.ascentAttempted=ascentAttempted;r.frameId=current&&current.frameId;r.health=current&&current.hud&&current.hud.health;r.map=current&&current.map;r.climbAfterRelease=current&&current.hud&&current.hud.climbing;}
 }
 root.ActTwoWallMicroAscent={witnessSession,witnessFrame,witnessHash,height,base,entry,attached,releaseReady,grounded,permit,run};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoWallMicroAscent;
})(typeof globalThis!=='undefined'?globalThis:this);
