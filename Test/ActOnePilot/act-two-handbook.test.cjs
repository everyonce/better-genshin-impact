const test=require('node:test'),assert=require('node:assert/strict');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-handbook.js');
const base=[{text:'Chapter 1',x:1350,y:185},{text:'Experience',x:230,y:228},{text:'Investigation Progress',x:414,y:269}];
test('recorded Enemies page permits only a bounded list scroll',()=>{
 const frame={timestamp:1000,map:null,hud:{world:false},ocr:[{text:'Enemies',x:238,y:427},{text:'All',x:400,y:187},{text:'Cancel',x:1412,y:812},{text:'Navigation',x:1386,y:840}]};
 assert.deepEqual(gate.target(frame,1000,null,'enemyScroll'),{action:'scrollEnemies',x:690,y:690,scroll:-8});
 assert.deepEqual(gate.target(frame,1000,null,'enemyCategory'),{action:'inspectEnemyCategory',x:695,y:204});
 for(const row of frame.ocr)assert.equal(gate.target({...frame,ocr:frame.ocr.filter(v=>v!==row)},1000,null,'enemyScroll'),null);
});
test('recorded enemy category popup permits only the Elite Enemies selection',()=>{
 const frame={timestamp:1000,map:null,hud:{world:false},ocr:[{text:'Enemies',x:238,y:427},{text:'All',x:402,y:187},{text:'Easy',x:401,y:294},{text:'Elite Enemies',x:402,y:353},{text:'Boss Enemies',x:399,y:407}]};
 assert.deepEqual(gate.target(frame,1000,null,'enemyCategory'),{action:'selectEliteEnemies',x:489,y:373});
 for(const row of frame.ocr)assert.equal(gate.target({...frame,ocr:frame.ocr.filter(v=>v!==row)},1000,null,'enemyCategory'),null);
 assert.equal(gate.target(frame,2001,null,'enemyCategory'),null);
});
test('Elite Enemies page permits bounded scrolling',()=>{
 const frame={timestamp:1000,map:null,hud:{world:false},ocr:[{text:'Enemies',x:238,y:427},{text:'Elite Enemies',x:404,y:189},{text:'Navigate',x:1387,y:822}]};
 assert.deepEqual(gate.target(frame,1000,null,'enemyScroll'),{action:'scrollEliteEnemies',x:690,y:690,scroll:-24});
 for(const row of frame.ocr)assert.equal(gate.target({...frame,ocr:frame.ocr.filter(v=>v!==row)},1000,null,'enemyScroll'),null);
});
test('mage location is restricted to the inspected incomplete chapter two row',()=>{
 const o={timestamp:1000,map:null,hud:{world:false},ocr:[{text:'Chapter 2',x:1350,y:185},...base.slice(1),{text:'4/8',x:520,y:370},{text:'Hunt down a Cryo Abyss',x:880,y:660},{text:'Mage',x:880,y:690},{text:'0/1',x:895,y:725},{text:'15/30',x:895,y:460}]};
 assert.deepEqual(gate.target(o,1000,null,'mage'),{action:'locate',objective:'Cryo Abyss Mage',x:1508,y:701});
 assert.deepEqual(gate.target({...o,ocr:o.ocr.map(r=>r.text==='15/30'?{...r,text:'18/30'}:r)},1000,null,'mage'),{action:'locate',objective:'Cryo Abyss Mage',x:1508,y:701});
 for(const row of o.ocr)assert.equal(gate.target({...o,ocr:o.ocr.filter(r=>r!==row)},1000,null,'mage'),null);
 assert.equal(gate.target(o,2001,null,'mage'),null);
});
test('Completed chapter one permits inspection of the next chapter',()=>{
 const o={timestamp:1000,map:null,hud:{world:false},ocr:[...base,{text:'4/4',x:520,y:370},{text:'Rewards claimed',x:485,y:844},{text:'Open 15 chests',x:880,y:550},{text:'15/15',x:890,y:590}]};
 assert.equal(gate.target(o,1000,null,true).action,'next');
 for(const label of ['4/4','Rewards claimed','15/15'])assert.equal(gate.target({...o,ocr:o.ocr.filter(r=>r.text!==label)},1000,null,true),null);
});
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
test('Fifteen-chest page navigation and claim require exact completed counters',()=>{
 const o={timestamp:1000,map:null,hud:{world:false},ocr:[...base.map(r=>r.text==='Chapter 1'?{...r,text:'Chapter 2'}:r),{text:'Open 30 chests',x:880,y:430},{text:'15/30',x:890,y:460}]};
 assert.equal(gate.target(o,1000,null,'previous').action,'previous');
 assert.equal(gate.target({...o,ocr:o.ocr.map(r=>r.text==='15/30'?{...r,text:'14/30'}:r)},1000,null,'previous'),null);
 const c={...o,ocr:[...base,{text:'Open 15 chests',x:880,y:300},{text:'15/15',x:890,y:335},{text:'Claim',x:1470,y:310,width:80,height:30}]};
 assert.equal(gate.target(c,1000).objective,'Open 15 chests');
 assert.equal(gate.target({...c,ocr:c.ocr.map(r=>r.text==='15/15'?{...r,text:'14/15'}:r)},1000),null);
});
test('Chapter one bundle requires all completed objectives and a matching reward context',()=>{
 const o={timestamp:1000,session:'s',frameId:2,map:null,hud:{world:false},ocr:[...base,...[['4/4',520,360],['Open 15 chests',880,550],['15/15',890,590],['10000',630,630],['50',430,740],['Claim',520,835]].map(([text,x,y])=>({text,x,y}))]};
 assert.equal(gate.target(o,1000).chapterReward,true);
 assert.notEqual(gate.target({...o,ocr:o.ocr.map(r=>r.text==='4/4'?{...r,text:'3/4'}:r)},1000)?.chapterReward,true);
 const reward={...o,ocr:[['Obtained',880,278],['Primogem',685,591],['50',730,560],['10000',854,558],['Mora',852,588],["Hero's Wit",970,591],["Lucky Dog's",1106,596],['Clover',1136,619],['Click anywhere in the blank area to continue',681,733]].map(([text,x,y])=>({text,x,y}))};
 const context={chapterReward:true,session:'s',frameId:1,createdAt:900};
 assert.equal(gate.target(reward,1000,context).action,'continue');
 assert.equal(gate.target(reward,1000,{...context,session:'other'}),null);
 assert.equal(gate.target({...reward,ocr:reward.ocr.filter(r=>r.text!=='10000')},1000,context),null);
});
test('Domains inspection requires the current Chapter2 Handbook and unique tab',()=>{
 const o={timestamp:1000,map:null,hud:{world:false},ocr:[{text:'Chapter 2',x:1350,y:190},{text:'Experience',x:230,y:230},{text:'Investigation Progress',x:410,y:270},{text:'Domains',x:235,y:332}]};
 const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-handbook.js');
 assert.equal(g.target(o,1000,null,'domains').action,'inspectDomains');
 for(let i=0;i<o.ocr.length;i++)assert.equal(g.target({...o,ocr:o.ocr.filter((_,j)=>i!==j)},1000,null,'domains'),null);
});

test('chapter three inspection is bounded to the reviewed chapter two state',()=>{
 const o={timestamp:1000,map:null,hud:{world:false},ocr:[{text:'Chapter 2',x:1350,y:185},...base.slice(1),{text:'4/8',x:520,y:370},{text:'Open 30 chests',x:880,y:430},{text:'15/30',x:890,y:460}]};
 assert.equal(gate.target(o,1000,null,true).action,'next');for(const row of o.ocr)assert.equal(gate.target({...o,ocr:o.ocr.filter(r=>r!==row)},1000,null,true),null);assert.equal(gate.target(o,2001,null,true),null);
});
