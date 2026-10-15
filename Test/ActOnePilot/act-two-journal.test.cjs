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
