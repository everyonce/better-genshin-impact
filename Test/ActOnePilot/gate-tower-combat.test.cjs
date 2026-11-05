const test=require('node:test');
const assert=require('node:assert/strict');
const tower=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/gate-tower-combat.js');
const native=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-native-combat.js');
const [distant,approach,first,measured]=require('./fixtures/r77-gate-watchtower.json');
const original=o=>o.ocr.some(r=>r.x>1600&&r.y>1020&&r.text.includes('693306810'));
const ctx=o=>({now:()=>o.timestamp,session:o.session,original});

test('real gate frames retain one high tower bar; the ordinary melee filter stays unchanged',()=>{
 assert.equal(tower.candidate(distant,ctx(distant)),false);
 for(const o of [approach,first,measured])assert.equal(tower.candidate(o,ctx(o)),true);
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
