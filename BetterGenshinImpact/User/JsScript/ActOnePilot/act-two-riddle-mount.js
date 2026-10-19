(function(root){
 'use strict';
 const action={type:'key',key:'VK_W',ms:600};
 const review={kind:'windmill-stone-first-contact',target:'bare exterior stone course left of wooden windmill door',surveySession:'mvem4kp5-lc0ysohhra',scene:[
  {frameId:503,sha256:'64628523dbe4021c3a026d010eb4a174c28cefe1f9b21084e3aa806ddfc56b72'},
  {frameId:515,sha256:'3e0083439551207cdd174deb297683ec396c1ab7e902cfc3a996e7a739ff0f3a'},
  {frameId:520,sha256:'91fada337fe47ba1d48a377f13cedb427c72c4d9ad2e5211d92ac5c23945f5e0'}],expectedClimbFrame:19574};
 const angle=(a,b)=>Math.abs((a-b+540)%360-180);
 const height=o=>{const rows=(o&&o.hud&&o.hud.objectives)||[];const match=rows.map(v=>String(v).trim()).filter(v=>/^Higher \d+m$/.test(v));return match.length===1?Number(match[0].match(/\d+/)[0]):null;};
 function common(o,session,now){const h=o&&o.hud,m=o&&o.map,p=h&&h.health;return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&m.map==='Teyvat'&&Math.hypot(m.x+842.865234375,m.y-2209.41796875)<=.45&&h&&h.world===true&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&p&&p.current===4015&&p.max===4015&&h.enemyBarDiagnostic&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).includes('Look for the location in the riddle')&&(o.ocr||[]).some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(String(r.text).trim())));}
 function entry(o,session,now){return common(o,session,now)&&o.hud.groundControls===true&&o.hud.climbing===false&&height(o)===27&&angle(o.map.cameraAngle,314.5)<=4&&Math.hypot(o.map.x+842.92578125,o.map.y-2209.25390625)<=.12;}
 function attached(o,session,now){return common(o,session,now)&&o.hud.climbing===true&&o.hud.groundControls===false&&height(o)>=25&&height(o)<=28&&angle(o.map.cameraAngle,314.5)<=12;}
 function stamina(o){const s=o&&o.hud&&o.hud.climbStamina,b=s&&s.boxes;return !!(s&&s.source==='same-frame-yellow-arc'&&Number.isFinite(s.pixels)&&s.pixels>=180&&Array.isArray(b)&&b.length&&b.every(v=>[v.x,v.y,v.width,v.height].every(Number.isFinite)&&v.width>0&&v.height>0)&&Math.max(...b.map(v=>v.y+v.height))-Math.min(...b.map(v=>v.y))>=45);}
 function safeGround(o,session,now){return common(o,session,now)&&o.hud.groundControls===true&&o.hud.climbing===false&&height(o)>=26&&height(o)<=28;}
 function safeLedge(a,b,session,now){const good=o=>{const h=o&&o.hud,m=o&&o.map,p=h&&h.health;return !!(o&&o.session===session&&m&&m.map==='Teyvat'&&Math.hypot(m.x+843.27734375,m.y-2209.9892578125)<=.65&&h&&h.world&&h.groundControls&&!h.climbing&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&p&&p.current===4015&&p.max===4015&&h.enemyBarDiagnostic&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).includes('Look for the location in the riddle')&&height(o)>=8&&height(o)<=11);};return !!(good(a)&&good(b)&&b.frameId>a.frameId&&b.timestamp>=a.timestamp&&now>=b.timestamp&&now-b.timestamp<=1000&&Math.hypot(a.map.x-b.map.x,a.map.y-b.map.y)<=.2);}
 function plan(){return {mode:'actions',actions:[action],mountReview:review};}
 function permit(p,request,inventory,witness,now){return !!(p&&request&&inventory&&witness&&request.step==='actTwoRiddleMount'&&!p.usedAt&&p.session===request.session&&p.frameId===request.expectedFrameId&&p.witnessFrameId===520&&p.witnessSession===review.surveySession&&Number.isFinite(p.createdAt)&&now>=p.createdAt&&now-p.createdAt<=120000&&inventory.session===request.session&&Number.isInteger(inventory.frameId)&&inventory.frameId>=request.expectedFrameId&&inventory.frameId<=request.expectedFrameId+1&&witness.session===review.surveySession&&witness.frameId===520&&entry(witness,review.surveySession,witness.timestamp)&&JSON.stringify(p.mountReview)===JSON.stringify(review));}
 function progressReason(history,progress,w){if(!progress||typeof progress.rejection!=='function')return 'Progress guard unavailable';return progress.rejection(history,plan(),w);}
 async function run(initial,history,progress,api){
  let current=initial,inputs=0,reads=0,uncertain=false;const session=initial&&initial.session,started=api.now(),result={status:'stopped',step:'actTwoRiddleMount',inputs:0,mounted:false,climbingObserved:false,staminaVerified:false};
  const deadline=()=>{if(api.now()-started>10000)throw Error('Mount local deadline reached');};
  const check=()=>{api.check();deadline();if(!entry(current,session,api.now()))throw Error('Fresh grounded windmill entry changed');};
  const observe=async()=>{deadline();const before=current;current=await api.observe();reads++;deadline();if(!current||current.session!==session||current.frameId<=before.frameId||current.timestamp<before.timestamp||api.now()-current.timestamp>1000)throw Error('Mount observation continuity failed');};
  try{
   check();const refusal=progressReason(history,progress,current);if(refusal){result.reason=refusal;return result;}
   api.check();deadline();uncertain=true;await api.key('VK_W',600,current);inputs++;await api.release();await api.sleep(250);await observe();uncertain=false;
   if(!attached(current,session,api.now())){result.reason=safeGround(current,session,api.now())?'Mount did not attach; safe ground verified':'Mount outcome requires visual review';return result;}
   result.climbingObserved=true;
   if(!stamina(current)){await api.sleep(150);await observe();if(!attached(current,session,api.now())||!stamina(current)){result.reason='Climb attached, but fresh positive stamina is unverified';return result;}}
   result.mounted=true;result.staminaVerified=true;result.reason='First wall foothold verified; stop for ledge review';return result;
  }catch(e){result.reason=String(e&&e.message||e);result.uncertainInput=uncertain;return result;}
  finally{await api.release();result.inputs=inputs;result.reads=reads;result.frameId=current&&current.frameId;result.health=current&&current.hud&&current.hud.health;}
 }
 root.ActTwoRiddleMount={entry,attached,stamina,safeGround,safeLedge,plan,permit,progressReason,run};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoRiddleMount;
})(typeof globalThis!=='undefined'?globalThis:this);
