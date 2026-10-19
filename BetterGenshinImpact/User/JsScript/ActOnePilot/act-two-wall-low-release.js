(function(root){'use strict';
 const sourceSession='mvf3zqtu-3x4dcamyawp';
 const angle=(a,b)=>Math.abs((a-b+540)%360-180);
 const height=o=>{const hits=(o&&o.hud&&o.hud.objectives||[]).map(s=>/^\s*Higher\s*(\d+)m$/.exec(String(s))).filter(Boolean);return hits.length===1?Number(hits[0][1]):null;};
 function common(o,session,now){const h=o&&o.hud,m=o&&o.map,p=h&&h.health;return !!(o&&o.session===session&&Number.isInteger(o.frameId)&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&m.map==='Teyvat'&&Math.hypot(m.x+842.396484375,m.y-2210.2294921875)<=.25&&angle(m.cameraAngle,320)<=12&&h&&h.world===true&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&p&&p.current===4015&&p.max===4015&&h.enemyBarDiagnostic&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).some(s=>String(s).replace(/\s/g,'')==='Lookforthelocationintheriddle')&&(o.ocr||[]).some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(String(r.text).trim())));}
 function attached(o,session,now){return common(o,session,now)&&o.hud.climbing===true&&o.hud.groundControls===false&&[26,27].includes(height(o))&&(o.ocr||[]).some(r=>r.text==='X'&&r.x>1550&&r.y>980);}
 function grounded(o,session,now){return common(o,session,now)&&o.hud.groundControls===true&&o.hud.climbing===false&&height(o)>=26&&height(o)<=28;}
 function permit(p,r,initial,gate,now){return !!(p&&r&&initial&&r.step==='actTwoWallLowRelease'&&!p.usedAt&&p.session===r.session&&p.frameId===r.expectedFrameId&&p.sourceSession===sourceSession&&p.sourceFrames&&p.sourceFrames.length===2&&p.sourceFrames[0]===10&&p.sourceFrames[1]===11&&Number.isFinite(p.createdAt)&&now>=p.createdAt&&now-p.createdAt<=120000&&gate(initial,now,r.session));}
 async function run(initial,api){let current=initial,inputs=0,reads=0;const session=initial.session,started=api.now(),r={status:'stopped',step:'actTwoWallLowRelease',inputs:0,groundRecovered:false};
  const check=()=>{api.check();if(api.now()-started>9000)throw Error('Low-release local deadline reached');};
  const observe=async()=>{check();const prior=current;current=await api.observe();reads++;check();if(!current||current.session!==session||current.frameId<=prior.frameId||current.timestamp<prior.timestamp||api.now()-current.timestamp>1000)throw Error('Low-release observation continuity failed');};
  try{check();if(!attached(current,session,api.now()))throw Error('Fresh low wall attachment absent; no X input');
   await api.key('VK_X',60,current);inputs++;await api.release();await api.sleep(250);await observe();
   for(let i=0;i<3&&!grounded(current,session,api.now())&&common(current,session,api.now())&&!current.hud.climbing;i++){await api.sleep(200);await observe();}
   r.groundRecovered=grounded(current,session,api.now());r.reason=r.groundRecovered?'Low-height release reached verified ground':'Landing unverified; protect with pause';return r;
  }catch(e){r.reason=String(e&&e.message||e);return r;}
  finally{await api.release();r.inputs=inputs;r.reads=reads;r.frameId=current&&current.frameId;r.health=current&&current.hud&&current.hud.health;r.map=current&&current.map;}
 }
 root.ActTwoWallLowRelease={sourceSession,attached,grounded,permit,run};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoWallLowRelease;
})(typeof globalThis!=='undefined'?globalThis:this);
