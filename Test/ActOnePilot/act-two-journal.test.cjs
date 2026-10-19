const test=require('node:test'),assert=require('node:assert/strict');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-journal.js');
const quest="Welcome to the Adventurers' Guild";
const o={timestamp:1000,hud:{journal:true},ocr:[{text:'In Progress',x:135,y:26,width:153,height:41},{text:' Archon Quests',x:148,y:113,width:233,height:41},{text:quest,x:177,y:889,width:438,height:29}]};
const p={session:'s',frameId:52,reviewed:true,createdAt:1000,action:'select',quest};const request={session:'s',expectedFrameId:52};
test('Available Amber prerequisite uses exact journal title and protected bounded navigation',async()=>{
 const name='Glide With the Wind',frame={...o,ocr:o.ocr.map(q=>q.text===quest?{...q,text:name}:q)};
 assert.ok(gate.target(frame,1000,{...p,quest:name},request));
 const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');let calls=0;
 const api={runActTwoNavigationWithPause:async()=>{calls++;return {pauseVerified:true};}},route={objective:'Talk to Amber',deadlineMs:45000,waypoints:[{map:'Teyvat',x:-854,y:2290}]};
 assert.equal((await mission.runNavigation(route,{hud:{}},api,()=>{})).pauseVerified,true);
 assert.equal((await mission.runNavigation({...route,deadlineMs:45001},{hud:{}},api,()=>{})).status,'stopped');assert.equal(calls,1);
});
test('journal permits only unique approved quest targets on fresh pinned screens',()=>{
 assert.deepEqual(gate.target(o,1000,p,request),{x:396,y:904});
 for(const patch of [{quest:'Unrelated quest'},{action:'spend'},{consumed:true},{reviewed:false},{session:'x'},{frameId:51},{createdAt:-60000}])assert.equal(gate.target(o,1000,{...p,...patch},request),null);
 assert.equal(gate.target(o,2001,p,request),null);assert.equal(gate.target({...o,ocr:[...o.ocr,o.ocr[2]]},1000,p,request),null);
});
test('Navigate requires the selected right-hand quest title',()=>{
 const n={...o,ocr:[...o.ocr,{text:'Navigate',x:1650,y:1000,width:150,height:35}]};
 assert.equal(gate.target(n,1000,{...p,action:'navigate'},request),null);
 n.ocr.push({text:quest,x:870,y:120,width:500,height:40});
 assert.deepEqual(gate.target(n,1000,{...p,action:'navigate'},request),{x:1725,y:1018});
});
test('Parking Amber exam cancels only exact tracked exam navigation',()=>{
 const frame={...o,ocr:[...o.ocr,{text:'License to Glide',x:872,y:119,width:279,height:41},{text:'Go to the exam point',x:924,y:254,width:265,height:29},{text:'Cancel',x:1626,y:989,width:93,height:30},{text:'Navigation',x:1597,y:1013,width:151,height:43}]},plan={...p,quest:'License to Glide',action:'cancelNavigation'};
 assert.deepEqual(gate.target(frame,1000,plan,request),{x:1673,y:1019});
 for(const word of ['License to Glide','Go to the exam point','Cancel','Navigation'])assert.equal(gate.target({...frame,ocr:frame.ocr.filter(r=>r.text!==word)},1000,plan,request),null);
 assert.equal(gate.target(frame,1000,{...plan,quest:'Glide With the Wind'},request),null);
});
test('Collector inspection works from the visible World Quests section without broadening other quests',()=>{
 const frame={...o,ocr:[o.ocr[0],{text:'World Quests',x:194,y:820,width:180,height:30},{text:'Collector of Anemo Sigils',x:177,y:880,width:400,height:30}]};
 const plan={...p,quest:'Collector of Anemo Sigils'};
 assert.deepEqual(gate.target(frame,1000,plan,request),{x:377,y:895});
 assert.equal(gate.target(frame,1000,p,request),null);
 assert.equal(gate.target({...frame,ocr:frame.ocr.slice(0,1).concat(frame.ocr.slice(2))},1000,plan,request),null);
});
test('Parking Mystery requires its exact selected title, objective and cancel control',()=>{
 const name='Mystery of the Arcadian Ruins',rows=[o.ocr[0],o.ocr[1],{text:name,x:874,y:121,width:521,height:41},{text:'Solve the mystery (Go to Kaeya at the Knights of Favonius HQ for a',x:922,y:246,width:843,height:35},{text:'hint)',x:922,y:272,width:71,height:39},{text:'Cancel',x:1624,y:989,width:97,height:30},{text:'Navigation',x:1598,y:1014,width:151,height:37}],frame={...o,ocr:rows},plan={...p,quest:name,action:'cancelNavigation'};
 assert.deepEqual(gate.target(frame,1000,plan,request),{x:1673,y:1019});
 for(const row of rows.slice(2))assert.equal(gate.target({...frame,ocr:rows.filter(r=>r!==row)},1000,plan,request),null);
});

test('one bounded scroll exposes Cyrus below the verified World Quests header',()=>{
 const frame={...o,ocr:[o.ocr[0],{text:'World Quests',x:176,y:810,width:191,height:29},{text:'Collector of Anemo Sigils',x:171,y:856,width:327,height:37}]};
 const plan={...p,quest:'Not to be Missed',action:'scrollToCyrus'};
 assert.deepEqual(gate.target(frame,1000,plan,request),{x:500,y:800,scroll:-2});
 assert.equal(gate.target(frame,2001,plan,request),null);
 assert.equal(gate.target(frame,1000,{...plan,quest:'Mystery of the Arcadian Ruins'},request),null);
 frame.ocr.push({text:'Not to be Missed',x:175,y:945,width:250,height:28});
 assert.equal(gate.target(frame,1000,plan,request),null);
 frame.ocr[1].y=500;assert.ok(gate.target(frame,1000,{...plan,action:'select'},request));
});

test('reviewed World Quest tab inspection requires the exact recorded journal',()=>{
 const f=require('./act-two-journal-lower-list.fixture.json'),plan={...p,quest:'Shadow Over Mondstadt',action:'inspectWorldQuestTab',createdAt:f.timestamp};
 assert.deepEqual(gate.target(f,f.timestamp,plan,request),{x:1152,y:48});
 for(const title of ['Archon Quests','Shadow Over Mondstadt','License to Glide','Mystery of the Arcadian Ruins'])assert.equal(gate.target({...f,ocr:f.ocr.filter(r=>String(r.text).trim()!==title)},f.timestamp,plan,request),null);
 assert.equal(gate.target(f,f.timestamp+1001,plan,request),null);
 assert.equal(gate.target(f,f.timestamp,{...plan,consumed:true},request),null);
});
test('World Quest tab inspection accepts the later Kaeya-selected journal layout',()=>{
 const rows=[['In Progress',138,30],[' Archon Quests',152,93],['Shadow Over Mondstadt',194,242],['Story Quests',160,347],['Outrider Style',194,498],['Mystery of the Arcadian Ruins',187,706],['Mystery of the Arcadian Ruins',872,121],['Q',670,30],['E',1208,30]].map(([text,x,y])=>({text,x,y,width:200,height:35}));
 const frame={timestamp:1000,hud:{journal:true},ocr:rows},plan={...p,quest:'Shadow Over Mondstadt',action:'inspectWorldQuestTab'};
 assert.deepEqual(gate.target(frame,1000,plan,request),{x:1152,y:48});
 for(const index of [1,2,3,4,5,6,7,8])assert.equal(gate.target({...frame,ocr:rows.filter((_,i)=>i!==index)},1000,plan,request),null);
});

test('exact World Quest tab returns to all quests despite absent generic journal classifier',()=>{
 const f=require('./act-two-world-quests-tab.fixture.json'),plan={...p,quest:'Collector of Anemo Sigils',action:'returnAllQuests',createdAt:f.timestamp};
 assert.deepEqual(gate.target(f,f.timestamp,plan,request),{x:768,y:48});
 assert.deepEqual(gate.target({...f,ocr:f.ocr.map((r,i)=>i===5?{...r,text:'\uff01World Quests'}:r)},f.timestamp,plan,request),{x:768,y:48});
 for(const i of [2,3,4,5,6,7])assert.equal(gate.target({...f,ocr:f.ocr.filter((r,n)=>n!==i)},f.timestamp,plan,request),null);
 assert.equal(gate.target(f,f.timestamp+1001,plan,request),null);
 assert.equal(gate.target(f,f.timestamp,{...plan,action:'select'},request),null);
});
test('recorded empty World Quests tab permits only a reviewed return to In Progress',()=>{
 const f=require('./act-two-empty-world-journal-tab.fixture.json');
 const plan={...p,session:f.session,frameId:f.frameId+1,createdAt:f.timestamp,quest:'Mystery of the Arcadian Ruins',action:'inspectInProgressTab'};
 const req={session:f.session,expectedFrameId:plan.frameId};
 assert.deepEqual(gate.target(f,f.timestamp,plan,req),{x:768,y:48});
 for(const word of ['World Quests','No active quests','Check another tab','Q','E'])
  assert.equal(gate.target({...f,ocr:f.ocr.filter(r=>r.text!==word)},f.timestamp,plan,req),null);
 for(const patch of [{quest:'Shadow Over Mondstadt'},{action:'select'},{reviewed:false},{consumed:true},{session:'other'}])
  assert.equal(gate.target(f,f.timestamp,{...plan,...patch},req),null);
 assert.equal(gate.target(f,f.timestamp+1001,plan,req),null);
});
test('recorded Mystery journal navigates from selected riddle despite scrolled Archon heading',()=>{
 const f=require('./act-two-mystery-near-journal.fixture.json');
 const plan={...p,session:f.session,frameId:f.frameId+1,createdAt:f.timestamp,quest:'Mystery of the Arcadian Ruins',action:'navigate'};
 const req={session:f.session,expectedFrameId:plan.frameId};
 assert.deepEqual(gate.target(f,f.timestamp,plan,req),{x:1672,y:1021});
 for(const word of ['For a Tomorrow Without Tears','Prologue: Act II','Story Quests','Look for the location in the riddle','Navigate'])
  assert.equal(gate.target({...f,ocr:f.ocr.filter(r=>String(r.text).trim()!==word)},f.timestamp,plan,req),null);
 assert.equal(gate.target(f,f.timestamp,{...plan,action:'select'},req),null);
 assert.equal(gate.target(f,f.timestamp+1001,plan,req),null);
});
