const test=require('node:test');
const assert=require('node:assert/strict');
const tower=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/gate-tower-combat.js');
const native=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-native-combat.js');
const [distant,approach,first,measured]=require('./fixtures/r77-gate-watchtower.json');
const [kaeyaAtGate,switching,amber1,amber2,amber3]=require('./fixtures/r77-gate-amber-switch.json');
const [atGate,shotBefore,flash,damaged,settling]=require('./fixtures/r77-gate-ranged-impact.json');
const [missStart,missBefore,missAfter]=require('./fixtures/r77-gate-missed-shot.json');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const original=o=>o.ocr.some(r=>r.x>1600&&r.y>1020&&r.text.includes('693306810'));
const ctx=o=>({now:()=>o.timestamp,session:o.session,original});

test('real gate frames retain one high tower bar; the ordinary melee filter stays unchanged',()=>{
 assert.equal(tower.candidate(distant,ctx(distant)),false);
 assert.equal(tower.candidate(approach,ctx(approach)),false);assert.ok(native.targets(approach).length);
 for(const o of [first,measured])assert.equal(tower.candidate(o,ctx(o)),true);
 assert.equal(native.targets(measured).length,0);assert.equal(tower.scan(measured,'threat',1),true);
 const req={step:'actTwoFieldCombat',entryScene:'world',session:measured.session,expectedFrameId:103,
  expectedUid:'693306810',createdAt:measured.hud.captureStamp.capturedAt-1};
 assert.equal(native.worldEntry(measured,req,measured.timestamp,original),false);
 assert.equal(native.worldEntry(measured,req,measured.timestamp,original,o=>tower.candidate(o,ctx(o))),true);
});
test('stale, unidentified, ungrounded, weak or wrongly faced parties cannot enter',()=>{
 for(const edit of [o=>o.hud.health.current=2700,o=>o.hud.groundControls=false,o=>o.hud.climbing=true,
  o=>o.ocr=o.ocr.filter(r=>r.text!=='Amber'),o=>o.ocr=o.ocr.filter(r=>!r.text.includes('693306810')),
  o=>o.hud.enemyBars.push({...o.hud.enemyBars[0]}),o=>o.map.cameraAngle=110,o=>o.map.x+=10,
  o=>o.hud.captureStamp.capturedAt-=3000]){
  const o=structuredClone(measured);edit(o);assert.equal(tower.candidate(o,ctx(o)),false);
 }
});
// Only the pre-switch Kaeya frames are recorded game data. Simulate post-switch state transitions
// to test the software contract without invoking BetterGI, the game or any actual keyboard/device.
function next(n,avatar){
 const o=structuredClone(measured),delta=(n-measured.frameId)*650;
 o.frameId=n;o.timestamp+=delta;o.hud.captureStamp.frameId=n;o.hud.captureStamp.capturedAt+=delta;
 o.hud.enemyBarObservation.frameId=n;o.hud.enemyBarObservation.capturedAt+=delta;
 if(avatar==='Amber'){
  o.ocr=o.ocr.filter(r=>r.text!=='2');o.ocr.push({text:'3',x:1855,y:447});o.hud.health={current:1675,max:1733};
 }
 return o;
}
function harness(mutateImpact,mutateAmber){
 const start=next(110,'Kaeya'),inputs=[],snapshots=[next(111,'Kaeya'),next(112,'Amber'),
  next(113,'Amber'),next(114,'Amber'),next(115,'Amber'),next(116,'Amber'),next(117,'Kaeya')];
 if(mutateAmber)for(const o of snapshots.slice(1,-1))mutateAmber(o);
 for(const o of snapshots.slice(2,-1))mutateImpact(o);
 let now=start.timestamp,active='Kaeya';
 return {start,inputs,api:{session:start.session,original,now:()=>now,deadline:now+30000,checkStop(){},sleep:async()=>{},
  observe:async()=>{let o=snapshots.shift();if(active==='Kaeya'&&o.frameId>111)o=next(o.frameId,'Kaeya');now=o.timestamp;return o;},
  actionId:i=>'a:'+i,rewards:native.rewardFeedback,key:async k=>{inputs.push(k);active=k==='VK_2'?'Amber':'Kaeya';},
  fire:async o=>{assert.equal(tower.party(o,'Amber'),true);inputs.push('native-arrow');return {nativeReturned:true};}}};
}
test('a single native bow command requires a fresh matching Amber frame and true red-fill loss',async()=>{
 const h=harness(o=>{o.hud.enemyBars[0].width-=14;o.hud.enemyBars[0].x-=7;});
 const r=await tower.run(h.start,0,h.api);assert.deepEqual(h.inputs,['VK_2','native-arrow','VK_3']);
 assert.equal(r.result.assessment,'damage');assert.equal(r.result.restored,true);assert.equal(r.turns.length,1);
});
test('incoming player damage, observed jitter, moving targets and disappearance alone never credit a shot',async()=>{
 for(const edit of [o=>{o.hud.health.current-=13;o.hud.enemyBars[0].width-=2;},
  o=>{o.hud.enemyBars[0].width-=13;o.hud.enemyBars[0].x+=35;},
  o=>{o.hud.enemyBars=[];o.hud.enemyBarDiagnostic.fieldCandidates=[];Object.assign(o.hud.enemyBarObservation,{state:'clear',candidateCount:0,acceptedCount:0});}]){
  const h=harness(edit),r=await tower.run(h.start,0,h.api);
  assert.equal(r.result.assessment,'unconfirmed');assert.equal(r.turns.length,1);assert.equal(r.result.restored,true);
 }
});
test('post-switch Amber identity, actual measured health, and repeated full scan all gate the shot',async()=>{
 for(const edit of [o=>{o.hud.health.current=900;},o=>{o.ocr=o.ocr.filter(r=>r.text!=='3');},
  o=>{o.hud.enemyBarObservation.state='ambiguous';},o=>{o.hud.enemyBars[0].x+=145;}]){
  const h=harness(()=>{},edit);await tower.run(h.start,0,h.api);assert.equal(h.inputs.includes('native-arrow'),false);
 }
});
test('a new Character EXP row plus independently clear ground can confirm the isolated defeat',async()=>{
 const h=harness(o=>{o.ocr.push({text:'Character EXP × 12',x:100,y:526});o.hud.enemyBars=[];o.hud.enemyBarDiagnostic.fieldCandidates=[];
  Object.assign(o.hud.enemyBarObservation,{state:'clear',candidateCount:0,acceptedCount:0});});
 const r=await tower.run(h.start,0,h.api);assert.equal(r.result.assessment,'defeat');assert.equal(r.result.restored,true);
});
test('ordinary field sequence hands off on the recorded elevated frame without another melee approach',async()=>{
 const h=harness(()=>{});let handoffs=0;
 const result=await native.fieldSequence(h.start,{now:h.api.now,checkStop(){},encounterDeadline:h.api.deadline,
  eligible:o=>tower.candidate(o,h.api),towerCandidate:o=>tower.candidate(o,h.api),
  runTower:(o,i)=>{handoffs++;return tower.run(o,i,h.api);}});
 assert.equal(handoffs,1);assert.equal(result.towerResult.assessment,'unconfirmed');
 assert.equal(result.approachBudget.steps,0);assert.equal(result.turns.length,1);
});
test('frames acquired before switch/shot completion cannot attest to a later action',async()=>{
 const h=harness(()=>{},o=>{o.hud.captureStamp.capturedAt-=350;});
 const r=await tower.run(h.start,0,h.api);assert.equal(h.inputs.includes('native-arrow'),false);assert.match(r.result.error,/New tower observation/);
});
test('a depleted survivor requires the native level-one rail or the same capture’s local level glyph',()=>{
 const o=structuredClone(measured),tip={...o.hud.enemyBars[0],width:7};o.hud.enemyBars=[tip];
 assert.equal(tower.bar(o),null);
 const level={text:'Lv.1',x:tip.x-5,y:tip.y-28,width:21,height:14};o.ocr.push(level);assert.equal(tower.bar(o).width,7);
 o.ocr.pop();o.hud.enemyBars=[{...measured.hud.enemyBars[0],depletedRail:{remainingRed:tip,level}}];
 assert.equal(tower.bar(o).width,7);level.text='Lv.6';assert.equal(tower.bar(o),null);
});
test('recorded pre-switch, transitional and selected rows distinguish the actual Amber with 1809 HP',()=>{
 assert.equal(tower.party(kaeyaAtGate,'Kaeya'),true);assert.equal(tower.party(kaeyaAtGate,'Amber'),false);
 assert.equal(tower.candidate(switching,ctx(switching)),false);
 for(const o of [amber1,amber2,amber3]){
  assert.equal(tower.candidate(o,ctx(o)),true);assert.equal(tower.party(o,'Amber'),true);assert.equal(tower.party(o,'Kaeya'),false);
 }
 for(const edit of [o=>o.ocr.find(r=>r.text==='Kaeya').x-=25,o=>o.ocr.find(r=>r.text==='Amber').y-=8,
  o=>o.ocr.push({text:'2',x:1856,y:351}),o=>o.hud.health.max=1733]){
  const o=structuredClone(amber1);edit(o);assert.equal(tower.party(o,'Amber'),false);
 }
});
test('starting as verified Amber takes a second independent threat frame, never switches to slot 2, and verifies Kaeya afterward',async()=>{
 const o=structuredClone(amber1),inputs=[];let now=o.timestamp,sequence=[amber2,amber3];
 // The start, repeat and no-impact samples above are actual captures. The successful return
 // to Kaeya below is synthetic and tests the routing contract only.
 function from(record,id){
  const v=structuredClone(record),delta=amber3.timestamp+900*(id-13)-v.timestamp;v.timestamp+=delta;v.frameId=id;
  v.hud.captureStamp.frameId=id;v.hud.captureStamp.capturedAt+=delta;
  v.hud.enemyBarObservation.frameId=id;v.hud.enemyBarObservation.capturedAt+=delta;return v;
 }
 sequence.push(from(amber3,14),from(amber3,15),from(amber3,16),from(amber3,17),from(kaeyaAtGate,18));
 const api={...ctx(o),now:()=>now,deadline:now+30000,checkStop(){},sleep:async()=>{},
  observe:async()=>{const v=sequence.shift();now=v.timestamp;return v;},rewards:native.rewardFeedback,
  key:async k=>{inputs.push(k);},actionId:()=> 'arrow',fire:async()=>{inputs.push('native-arrow');return {nativeReturned:true};}};
 const res=await tower.run(o,0,api);assert.deepEqual(inputs,['native-arrow','VK_3']);
 assert.equal(res.result.startedAs,'Amber');assert.equal(res.result.switched,false);assert.equal(res.result.restored,true);
 assert.equal(res.result.assessment,'unconfirmed');
});
test('ambiguous named rows in the second captured Amber scene never shoot or change character',async()=>{
 const o=structuredClone(amber2);o.ocr.find(r=>r.text==='Amber').x+=28;
 let now=amber1.timestamp;const api={...ctx(amber1),now:()=>now,deadline:now+30000,checkStop(){},sleep:async()=>{},
   observe:async()=>{now=o.timestamp;return o;},key:async()=>assert.fail(),fire:async()=>assert.fail()};
 const res=await tower.run(amber1,0,api);assert.equal(res.turns.length,0);assert.equal(res.result.restored,false);
});
// Replay the same narrow gold mask against lossless native RGB pixels immediately to the
// right of the red bar. The real frame 10 contains an uninterrupted rectangle, 17 by 4.
function measuredTail(o,id){
 const c=o.rawRailCrop,buf=Buffer.from(c.rgb24,'base64');let x0=c.width,x1=-1,y0=c.height,y1=-1,n=0;
 for(let y=0;y<c.height;y++)for(let x=0;x<c.width;x++){
  const k=(y*c.width+x)*3;
  if(buf[k]<249||buf[k+1]<204||buf[k+1]>214||buf[k+2]<120||buf[k+2]>132)continue;
  x0=Math.min(x0,x);x1=Math.max(x1,x);y0=Math.min(y0,y);y1=Math.max(y1,y);n++;
 }
 const width=x1-x0+1,height=y1-y0+1;
 if(width<16||height<3||n!==width*height)return null;
 return {actionId:id,x:c.x+x0+width/2,y:c.y+y0+height/2,width,height,rectangularity:1};
}
test('real native shot follows the turning camera and proves a red-to-gold fill transition; the earlier body flash alone cannot',()=>{
 const o=structuredClone(damaged),id='one:rotation:0',api={...ctx(o),rewards:native.rewardFeedback};
 assert.equal(measuredTail(shotBefore,id),null);assert.equal(measuredTail(flash,id),null);assert.equal(measuredTail(settling,id),null);
 const g=measuredTail(o,id);assert.deepEqual([g.width,g.height],[17,4]);o.hud.enemyBars[0].towerDamageTail=g;
 assert.equal(tower.feedback(shotBefore,flash,{...ctx(flash),rewards:native.rewardFeedback},id),'unconfirmed');
 assert.equal(tower.feedback(shotBefore,o,api,id),'damage');assert.equal(tower.candidate(o,ctx(o)),true);
 for(const edit of [v=>{delete v.hud.enemyBars[0].towerDamageTail;},v=>v.hud.enemyBars[0].towerDamageTail.actionId='old-shot',
  v=>v.hud.enemyBars[0].towerDamageTail.x+=6,v=>v.hud.enemyBars[0].x-=45,v=>v.hud.enemyBars[0].towerDamageTail.y+=6,
  v=>v.map.x+=3,v=>v.map.cameraAngle=250,v=>v.hud.enemyBarObservation.acceptedCount=2]){
  const v=structuredClone(o);edit(v);assert.equal(tower.feedback(shotBefore,v,api,id),'unconfirmed');
 }
});
test('re-entry refuses another bearing even with the same coordinates, health and red pixels',()=>{
 for(const edit of [v=>v.map.cameraAngle=260,v=>v.hud.enemyBars[0].x=850]){
  const v=structuredClone(damaged);edit(v);assert.equal(tower.candidate(v,ctx(v)),false);
 }
});
test('the native shot waits through the verified moving-camera impact, then re-observes ambiguous roster without pressing a key',async()=>{
 const id='one:rotation:0',hit=structuredClone(damaged);hit.hud.enemyBars[0].towerDamageTail=measuredTail(hit,id);
 function later(record,n){
  const v=structuredClone(record),delta=settling.timestamp+900*(n-11)-v.timestamp;v.frameId=n;v.timestamp+=delta;
  v.session=atGate.session;v.hud.captureStamp.session=v.session;v.hud.enemyBarObservation.session=v.session;
  v.hud.captureStamp.frameId=n;v.hud.captureStamp.capturedAt+=delta;v.hud.enemyBarObservation.frameId=n;
  v.hud.enemyBarObservation.capturedAt+=delta;return v;
 }
 const kaeya=later(kaeyaAtGate,13);kaeya.map=structuredClone(hit.map);
 const sequence=[shotBefore,flash,hit,settling,later(hit,12),kaeya],inputs=[];let now=atGate.timestamp;
 const api={...ctx(atGate),now:()=>now,deadline:now+30000,checkStop(){},sleep:async()=>{},
  observe:async()=>{const v=sequence.shift();now=v.timestamp;return v;},rewards:native.rewardFeedback,
  key:async(k,v)=>{inputs.push([k,v.frameId]);},actionId:()=>id,fire:async v=>{inputs.push(['shot',v.frameId]);return {nativeReturned:true};}};
 const res=await tower.run(atGate,0,api);
 assert.deepEqual(inputs,[['shot',8],['VK_3',12]]);assert.equal(res.result.assessment,'damage');assert.equal(res.result.restored,true);
 assert.equal(res.turns[0].assessment.evidence,'tracked_red_fill_and_adjacent_gold_tail');assert.equal(res.result.impactFrameId,10);
});
test('the recorded successful shot is inside the accepted firing projection; the recorded miss needs a camera turn',()=>{
 assert.equal(tower.aligned(shotBefore),true);assert.equal(tower.aligned(missBefore),false);
 assert.equal(tower.candidate(missBefore,ctx(missBefore)),true);
 assert.equal(mission.navigationTurnPixels(missBefore.map.cameraAngle-292.5),120);
 assert.equal(tower.feedback(missBefore,missAfter,{...ctx(missAfter),rewards:native.rewardFeedback},'one'),'unconfirmed');
});
function alignReplay(bad){
 const id='r:0',events=[],later=(n,kaeya=false)=>{
  const v=structuredClone(kaeya?kaeyaAtGate:missBefore),delta=missBefore.timestamp+1000*(n-8)-v.timestamp;
  v.frameId=n;v.timestamp+=delta;v.session=missBefore.session;v.map=structuredClone(missBefore.map);v.map.cameraAngle=292.5;
  v.hud.captureStamp.frameId=n;v.hud.captureStamp.capturedAt+=delta;v.hud.captureStamp.session=v.session;
  v.hud.enemyBarObservation.frameId=n;v.hud.enemyBarObservation.capturedAt+=delta;v.hud.enemyBarObservation.session=v.session;
  v.hud.enemyBars[0].x=1004+v.hud.enemyBars[0].width/2;return v;
 };
 const observations=[missBefore,later(9),later(10),later(11),later(12),later(13),later(14),later(15,true)];
 if(bad)bad(observations);
 let now=missStart.timestamp;
 return {events,api:{...ctx(missStart),now:()=>now,deadline:now+30000,checkStop(){},sleep:async()=>{},
  observe:async()=>{const v=observations.shift();now=v.timestamp;return v;},rewards:native.rewardFeedback,
  key:async(k,v)=>events.push([k,v.frameId]),actionId:()=>id,
  turn:async(error,v)=>{const dx=mission.navigationTurnPixels(error);events.push(['camera',v.frameId,dx]);return dx;},
  fire:async v=>{events.push(['shot',v.frameId]);return {nativeReturned:true};}}};
}
test('a camera-only native heading correction and two independently aligned threat frames precede the next arrow',async()=>{
 const h=alignReplay(),r=await tower.run(missStart,0,h.api);
 assert.deepEqual(h.events,[['camera',8,120],['shot',10],['VK_3',14]]);
 assert.equal(r.result.alignment.length,1);assert.equal(r.result.alignment[0].afterFrameId,9);
 assert.equal(r.result.assessment,'unconfirmed');assert.equal(r.result.restored,true);
});
test('unhelpful turn, changed target, conflicting identity or a lost second sight generates no shot',async()=>{
 for(const edit of [s=>{s[1]=structuredClone(s[1]);s[1].map.cameraAngle=277.5;s[1].hud.enemyBars[0].x=1203;},
  s=>s[1].map.x+=4,s=>s[1].hud.enemyBars[0].width+=15,s=>s[2].ocr=s[2].ocr.filter(r=>r.text!=='Amber'),
  s=>s[2].hud.enemyBarObservation.state='ambiguous']){
  const h=alignReplay(edit),r=await tower.run(missStart,0,h.api);
  assert.equal(h.events.filter(e=>e[0]==='camera').length,1);assert.equal(h.events.some(e=>e[0]==='shot'),false);
  assert.ok(r.result.error);
 }
});

test('aimed bow tracks the head below a wounded HP rail independent of the remaining fill',()=>{
 const frame=structuredClone(missBefore);
 frame.hud.bowAimBars=[{left:927,y:485,width:13,height:4}];
 frame.ocr=[{text:'Lv. 1',x:938,y:455,width:44,height:25}];
 const target=tower.aimTarget(frame,66);
 assert.equal(target.x,960);assert.equal(target.y,540);assert.equal(target.width,13);
 frame.ocr=[];assert.equal(tower.aimTarget(frame,66).x,960);
 frame.hud.bowAimBars.push({left:992,y:487,width:20,height:4});
 assert.equal(tower.aimTarget(frame,66),null);
});

test('the aimed volley corrects pitch and yaw before firing, then releases aim on a verified empty sight',async()=>{
 const source=structuredClone(missBefore),ground=source.hud.captureStamp.capturedAt;
 let now=source.timestamp,frameId=source.frameId,shots=0,dx=110,dy=-150;const keys=[],looks=[];
 const out=await tower.aimedVolley(source,{now:()=>now,deadline:now+20000,session:source.session,original:()=>true,
  checkStop(){},sleep:async(ms)=>{now+=ms;},key:async(k)=>keys.push(k),
  look:(x,y)=>{looks.push([x,y]);dx-=x*1.6;dy-=y*.6;},shoot:async()=>{assert.ok(Math.abs(dx)<=12&&Math.abs(dy)<=14);shots++;},
  observe:async()=>{
   const f=structuredClone(source);f.frameId=++frameId;f.timestamp=++now;f.hud.groundControls=false;
   f.hud.captureStamp={...f.hud.captureStamp,frameId,capturedAt:ground+now-source.timestamp};
   f.ocr=[{text:'R',x:1720,y:1020,width:18,height:20}];
   f.hud.bowAimBars=shots?[]:[{left:927+dx,y:485+dy,width:41,height:4}];return f;
  }});
 assert.equal(out.nativeReturned,true);assert.equal(shots,1);assert.ok(looks.some(([x,y])=>x>0&&y<0));assert.deepEqual(keys,['VK_R','VK_R']);
});
