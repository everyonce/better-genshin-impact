const test=require('node:test'),assert=require('node:assert/strict');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-handbook.js');
const base=[{text:'Chapter 1',x:1350,y:185},{text:'Experience',x:230,y:228},{text:'Investigation Progress',x:414,y:269}];
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
