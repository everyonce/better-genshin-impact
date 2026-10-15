const test=require('node:test'),assert=require('node:assert/strict');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-handbook.js');
const base=[{text:'Chapter 1',x:1350,y:185},{text:'Experience',x:230,y:228},{text:'Investigation Progress',x:414,y:269}];
test('inspect next page only from the reviewed chapter one chest state',()=>{
 const o={timestamp:1000,map:null,hud:{world:false},ocr:[...base,{text:'Open 15 chests',x:880,y:300},{text:'13/15',x:890,y:335}]};
 assert.deepEqual(gate.target(o,1000,null,true),{action:'next',x:1548,y:203});
 assert.equal(gate.target(o,2001,null,true),null);
 assert.equal(gate.target({...o,map:{x:1}},1000,null,true),null);
 assert.equal(gate.target({...o,ocr:o.ocr.map(r=>r.text==='Chapter 1'?{...r,text:'Chapter 2'}:r)},1000,null,true),null);
 assert.equal(gate.target({...o,ocr:o.ocr.filter(r=>r.text!=='13/15')},1000,null,true),null);
});
test('Statue upgrade claim requires completed level two and matching reward context',()=>{
 const o={timestamp:1000,map:null,hud:{world:false},ocr:[...base,{text:'Upgrade the Statues of The',x:878,y:280},{text:'Seven in Mondstadt to Lv. 2',x:880,y:310},{text:'1/1',x:882,y:334},{text:'Claim',x:1468,y:310,width:81,height:30}]};
 assert.equal(gate.target(o,1000).action,'claim');
 o.ocr[5].text='0/1';assert.equal(gate.target(o,1000),null);
 const reward={timestamp:1000,session:'s',frameId:2,map:null,hud:{},ocr:[['Obtained',870,276],['100',868,560],['Adventure',827,588],['EXP',866,617],["Lucky Dog's",964,594],['Hourglass',976,619],['Click anywhere in the blank area to continue',684,735]].map(([text,x,y])=>({text,x,y}))};
 assert.equal(gate.target(reward,1000),null);assert.equal(gate.target(reward,1000,{session:'s',frameId:1,createdAt:900}).action,'continue');
});
test('recorded Handbook row reorder keeps claims tied to completed objective',()=>{
 const o={timestamp:1000,map:null,hud:{world:false},ocr:[...base,{text:'Activate 3 Teleport',x:874,y:282},{text:'Waypoints',x:872,y:308},{text:'3/3',x:882,y:339},{text:'Claim',x:1474,y:310,width:81,height:30}]};
 assert.deepEqual(gate.target(o,1000),{action:'claim',objective:'Activate 3 Teleport Waypoints',x:1515,y:325});
 assert.equal(gate.target(o,2001),null);
 assert.equal(gate.target({...o,ocr:o.ocr.map(r=>r.text==='3/3'?{...r,text:'2/3'}:r)},1000),null);
 assert.equal(gate.target({...o,ocr:o.ocr.map(r=>r.text==='3/3'?{...r,y:600}:r)},1000),null);
});
test('Handbook earned-reward continuation requires matching fresh claim context',()=>{
 const rows=[['Obtained',874,276],['Adventure',827,588],['EXP',864,617],['100',868,560],['5000',998,554],['Click anywhere in the blank area to continue',684,735]].map(([text,x,y])=>({text,x,y}));
 const o={timestamp:1000,session:'s',frameId:69,map:null,hud:{world:false},ocr:rows},context={session:'s',frameId:67,createdAt:900};
 assert.equal(gate.target(o,1000),null);assert.equal(gate.target(o,1000,{...context,session:'other'}),null);
 assert.deepEqual(gate.target(o,1000,context),{action:'continue',x:960,y:800});
});
test('chapter two claims require exact completed weapon or waypoint objectives',()=>{
 const o={timestamp:1000,map:null,hud:{world:false},ocr:[...base.map(r=>r.text==='Chapter 1'?{...r,text:'Chapter 2'}:r),{text:'Enhance a weapon to Lv. 10',x:880,y:300},{text:'1/1',x:890,y:335},{text:'Claim',x:1470,y:310,width:80,height:30}]};
 assert.equal(gate.target(o,1000).rewardExp,200);
 const cooking={...o,ocr:o.ocr.map(r=>({...r,text:({'Enhance a weapon to Lv. 10':'Cook 5 dishes','1/1':'5/5'})[r.text]||r.text}))};
 assert.equal(gate.target(cooking,1000).objective,'Cook 5 dishes');
 assert.equal(gate.target({...cooking,ocr:cooking.ocr.map(r=>r.text==='5/5'?{...r,text:'4/5'}:r)},1000),null);
 assert.equal(gate.target({...o,ocr:o.ocr.map(r=>r.text==='1/1'?{...r,text:'0/1'}:r)},1000),null);
 const waypoint={...o,ocr:[...o.ocr.slice(0,3),{text:'Activate 6 Teleport',x:880,y:410},{text:'Waypoints',x:880,y:440},{text:'6/6',x:890,y:470},{text:'Claim',x:1470,y:440,width:80,height:30}]};
 assert.equal(gate.target(waypoint,1000).objective,'Activate 6 Teleport Waypoints');
 const equipment={...waypoint,ocr:waypoint.ocr.map(q=>({...q,text:({'Activate 6 Teleport':'Equip 4 artifacts on a single',Waypoints:'character','6/6':'1/1'})[q.text]||q.text}))};
 assert.equal(gate.target(equipment,1000).objective,'Equip 4 artifacts on a single character');
 assert.equal(gate.target({...equipment,ocr:equipment.ocr.map(q=>q.text==='1/1'?{...q,text:'0/1'}:q)},1000),null);
 assert.equal(gate.target({...waypoint,ocr:waypoint.ocr.map(r=>r.text==='6/6'?{...r,text:'5/6'}:r)},1000),null);
 const reward={timestamp:1000,session:'s',frameId:2,map:null,hud:{},ocr:[['Obtained',870,276],['200',868,560],['Adventure',827,588],['EXP',866,617],['Click anywhere in the blank area to continue',684,735]].map(([text,x,y])=>({text,x,y}))};
 assert.equal(gate.target(reward,1000),null);
 assert.equal(gate.target(reward,1000,{session:'s',frameId:1,createdAt:900,rewardExp:100}),null);
 assert.equal(gate.target(reward,1000,{session:'s',frameId:1,createdAt:900,rewardExp:200}).action,'continue');
});
