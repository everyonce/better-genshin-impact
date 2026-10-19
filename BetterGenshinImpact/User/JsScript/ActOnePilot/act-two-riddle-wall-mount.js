(function(root){'use strict';
 const review={kind:'windmill-broad-wall-first-contact',target:'flat exterior stone left of jamb',sourceSession:'mvf3dvpn-3vemzlvktui',scene:[
  {frameId:17,sha256:'ba8f81a4ae5dac3c6f5c1a32987a71763389809580781a380fa6a6c3a4ec8208'},
  {frameId:18,sha256:'94b1797821fce24de5b6216def6cffcf448627a8b9402ee9266abfea872c3f7f'}]};
 const angle=(a,b)=>Math.abs((a-b+540)%360-180);
 const height=o=>{const matches=(o&&o.hud&&o.hud.objectives||[]).map(s=>/^\s*Higher\s*(\d+)m$/.exec(String(s))).filter(Boolean);return matches.length===1?Number(matches[0][1]):null;};
 function common(o,session,now){const h=o&&o.hud,m=o&&o.map,p=h&&h.health;return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&m.map==='Teyvat'&&Math.hypot(m.x+842.529296875,m.y-2210.306640625)<=1.3&&h&&h.world&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&p&&p.current===4015&&p.max===4015&&h.enemyBarDiagnostic&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Lookforthelocationintheriddle')&&(o.ocr||[]).some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(String(r.text).trim())));}
 function entry(o,session,now){return common(o,session,now)&&o.hud.groundControls===true&&o.hud.climbing===false&&height(o)===27&&Math.hypot(o.map.x+842.529296875,o.map.y-2210.306640625)<=.12&&angle(o.map.cameraAngle,316)<=4;}
 function attached(o,session,now){return common(o,session,now)&&o.hud.climbing===true&&o.hud.groundControls===false&&[26,27].includes(height(o))&&angle(o.map.cameraAngle,316)<=12;}
 function ground(o,session,now){return common(o,session,now)&&o.hud.groundControls===true&&o.hud.climbing===false&&height(o)>=26&&height(o)<=28;}
 function stamina(o){const s=o&&o.hud&&o.hud.climbStamina,b=s&&s.boxes;return !!(s&&s.source==='same-frame-yellow-arc'&&Number.isFinite(s.pixels)&&s.pixels>=180&&Array.isArray(b)&&b.length&&b.every(v=>[v.x,v.y,v.width,v.height].every(Number.isFinite)&&v.width>0&&v.height>0)&&Math.max(...b.map(v=>v.y+v.height))-Math.min(...b.map(v=>v.y))>=45);}
 function plan(){return {mode:'actions',actions:[{type:'key',key:'VK_W',ms:600}],progressReview:review};}
 function permit(p,r,inventory,witness,now){return !!(p&&r&&inventory&&witness&&r.step==='actTwoWallMount'&&!p.usedAt&&p.session===r.session&&p.frameId===r.expectedFrameId&&p.witnessSession===review.sourceSession&&p.witnessFrameId===18&&Number.isFinite(p.createdAt)&&now>=p.createdAt&&now-p.createdAt<=120000&&inventory.session===r.session&&Number.isInteger(inventory.frameId)&&inventory.frameId>=r.expectedFrameId&&inventory.frameId<=r.expectedFrameId+1&&witness.session===review.sourceSession&&witness.frameId===18&&entry(witness,review.sourceSession,witness.timestamp)&&JSON.stringify(p.progressReview)===JSON.stringify(review));}
 async function run(initial,history,progress,api){
  let current=initial,inputs=0,reads=0,uncertain=false;const session=initial&&initial.session,started=api.now(),result={status:'stopped',step:'actTwoWallMount',inputs:0,climbingObserved:false,staminaVerified:false,footholdVerified:false,groundRecovered:false};
  const deadline=()=>{if(api.now()-started>10000)throw Error('Wall mount local deadline reached');};
  const observe=async()=>{deadline();const before=current;current=await api.observe();reads++;deadline();if(!current||current.session!==session||current.frameId<=before.frameId||current.timestamp<before.timestamp||api.now()-current.timestamp>1000)throw Error('Wall mount observation continuity failed');};
  try{
   api.check();deadline();if(!entry(current,session,api.now()))throw Error('Fresh broad-wall entry changed');
   const refusal=progress&&progress.rejection(history,plan(),current);if(refusal)throw Error(refusal||'Progress guard unavailable');
   uncertain=true;await api.key('VK_W',600,current);inputs++;await api.release();await api.sleep(250);await observe();uncertain=false;
   if(!attached(current,session,api.now())){result.reason=ground(current,session,api.now())?'Broad wall did not attach; safe ground verified':'Wall contact outcome requires visual review';return result;}
   result.climbingObserved=true;
   if(!stamina(current)){await api.sleep(150);await observe();}
   result.staminaVerified=attached(current,session,api.now())&&stamina(current);
   if(!attached(current,session,api.now())){result.reason='Climb state changed before safe release';return result;}
   api.check();deadline();uncertain=true;await api.key('VK_X',60,current);inputs++;await api.release();await api.sleep(350);await observe();uncertain=false;
   result.groundRecovered=ground(current,session,api.now());result.footholdVerified=result.staminaVerified&&result.groundRecovered;
   result.reason=result.footholdVerified?'Positive first foothold verified; released to safe ground':result.groundRecovered?'Climb observed but positive stamina unverified; released to safe ground':'Safe ground after climb release unverified';return result;
  }catch(e){result.reason=String(e&&e.message||e);result.uncertainInput=uncertain;return result;}
  finally{await api.release();result.inputs=inputs;result.reads=reads;result.frameId=current&&current.frameId;result.health=current&&current.hud&&current.hud.health;result.map=current&&current.map;result.stamina=current&&current.hud&&current.hud.climbStamina;}
 }
 root.ActTwoRiddleWallMount={entry,attached,ground,stamina,plan,permit,run};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoRiddleWallMount;
})(typeof globalThis!=='undefined'?globalThis:this);
