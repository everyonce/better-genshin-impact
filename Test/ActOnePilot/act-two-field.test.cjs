const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js');
const o={session:'s',timestamp:1000,frameId:1,map:{map:'Teyvat',x:-1354,y:1973},ocr:[{text:'UID: 693306810',x:1680,y:1050}],hud:{world:true,groundControls:true,health:{current:1640,max:1700},enemyBars:[{}],enemyBarDiagnostic:{level:4},objectives:['Lv.','4']}};
test('reviewed camp rock release allows one drop near the witnessed base despite the nearby enemy',()=>{
 const c={...o,map:{map:'Teyvat',x:-1235.4863,y:2302.3857},ocr:o.ocr.concat([{text:'X',x:1600,y:1020},{text:'Space',x:1700,y:1020}]),hud:{...o.hud,climbing:true,groundControls:false,health:{current:2449,max:2635},objectives:['Defeat the attacking monsters']}};
 assert.equal(g.ready(c,c,1000,'s',true,false,false,true),true);
 assert.equal(g.ready(c,c,1000,'s',true,false,false,false),false);
 for(const x of [{...c,map:{...c.map,x:-1240}},{...c,hud:{...c.hud,health:{current:2300,max:2635}}},{...c,hud:{...c.hud,objectives:['Other quest']}},{...c,hud:{...c.hud,enemyBars:[{},{},{}]}}])assert.equal(g.ready(x,c,1000,'s',true,false,false,true),false);
});
test('Amber city inspection permits only camera plans without broadening movement or quest scope',()=>{
 const f={...o,map:{map:'Teyvat',x:-705.8,y:2287.8},hud:{...o.hud,health:{current:2313,max:2313},enemyBars:[],objectives:['Talk to Amber','Lower 69m']}};
 assert.equal(g.cameraPlan({mode:'actions',actions:[{type:'look',dx:0,dy:500}]}),true);
 assert.equal(g.cameraPlan({mode:'actions',actions:[{type:'key',key:'VK_W',ms:60}]}),false);
 assert.equal(g.ready(f,f,1000,'s',false,false,true),true);assert.equal(g.ready(f,f,1000,'s'),false);
 assert.equal(g.ready({...f,map:{...f.map,x:-1000}},f,1000,'s',false,false,true),false);
 assert.equal(g.ready({...f,hud:{...f.hud,objectives:['Talk to Lisa']}},f,1000,'s',false,false,true),false);
});
test('Noncombat field observations retain all threat levels; combat scope is request bound',()=>{
 const r={session:'s',expectedFrameId:2},p={session:'s',frameId:2,mode:'combat',enemyLevel:5};assert.equal(g.enemyLevel(p,r),5);
 for(const patch of [{mode:'actions'},{mode:'climb'},{session:'other'},{frameId:1},{enemyLevel:6}])assert.equal(g.enemyLevel({...p,...patch},r),'any');
 assert.equal(g.enemyLevel({...p,enemyLevel:4},r),4);
});
test('Field health accepts verified artifact maximum while preserving percentage and within-batch invariants',async()=>{
 const upgraded={...o,hud:{...o.hud,health:{current:1617,max:1829}}};assert.equal(g.ready(upgraded,upgraded,1000,'s'),true);
 assert.equal(g.ready({...o,hud:{...o.hud,health:{current:2313,max:2313}}},o,1000,'s'),true);
 assert.equal(g.ready({...o,hud:{...o.hud,health:{current:1500,max:2313}}},o,1000,'s'),false);
 for(const hp of [{current:1200,max:1829},{current:2000,max:2000},{current:1900,max:1829}])assert.equal(g.ready({...upgraded,hud:{...upgraded.hud,health:hp}},upgraded,1000,'s'),false);
 let now=1000,keys=0;await g.run(o,o,{mode:'combat',actions:[]},{now:()=>now,checkStop:()=>{},sleep:async n=>now+=n,key:async()=>keys++,release:async()=>{}},async()=>({...upgraded,timestamp:now}));assert.equal(keys,1);
});
test('Reviewed climb batches exclude jumps, drops, attacks and long holds',()=>{
 const p={reviewed:true,session:'s',frameId:2,witnessFrameId:1,createdAt:1000,mode:'climb',actions:[{type:'key',key:'VK_W',ms:600}]},r={session:'s',expectedFrameId:2};
 assert.equal(g.plan(p,r,1001),true);
 for(const a of [{type:'key',key:'VK_SPACE',ms:60},{type:'key',key:'VK_X',ms:60},{type:'key',key:'VK_LBUTTON',ms:60,target:'Breakable rocks'},{type:'key',key:'VK_W',ms:601}])assert.equal(g.plan({...p,actions:[a]},r,1001),false);
});
test('Climb mode stops and releases when climbing ends or a threat appears',async()=>{
 const c={...o,ocr:o.ocr.concat([{text:'X',x:1600,y:1020},{text:'Space',x:1700,y:1020}]),hud:{...o.hud,climbing:true,groundControls:false,enemyBars:[]}};
 assert.equal(g.ready(c,c,1000,'s',true),true);assert.equal(g.ready(c,c,1000,'s'),false);
 assert.equal(g.ready({...c,hud:{...c.hud,enemyBars:[{}]}},c,1000,'s',true),false);
 let now=1000,actions=0,releases=0;
 await assert.rejects(g.run(c,c,{mode:'climb',actions:[{type:'key',key:'VK_W',ms:600},{type:'key',key:'VK_W',ms:600}]},{now:()=>now,checkStop:()=>{},sleep:async n=>now+=n,action:async()=>actions++,release:async()=>releases++},async()=>({...c,timestamp:now,hud:{...c.hud,climbing:false,groundControls:true}})),/evidence changed/);
 assert.equal(actions,1);assert.equal(releases,1);
});
test('Field plans reject stale, replayed, wrong-session and excessive inputs',()=>{
 const p={reviewed:true,session:'s',frameId:2,witnessFrameId:1,createdAt:1000,mode:'combat',actions:[{type:'look',dx:-750,dy:0},{type:'key',key:'VK_W',ms:800}]},r={session:'s',expectedFrameId:2};assert.equal(g.plan(p,r,1001),true);
 for(const bad of [{usedAt:1001},{session:'x'},{witnessFrameId:2},{createdAt:-121000},{mode:'other'},{actions:[{type:'key',key:'VK_F',ms:800}]},{actions:[{type:'key',key:'VK_W',ms:801}]},{actions:Array(4).fill({type:'key',key:'VK_W',ms:800})}])assert.equal(g.plan({...p,...bad},r,1001),false);
});
test('Obstacle strikes require an explicit reviewed rock target and a short press',()=>{
 const p={reviewed:true,session:'s',frameId:2,witnessFrameId:1,createdAt:1000,mode:'actions',actions:[{type:'key',key:'VK_LBUTTON',ms:60,target:'Breakable rocks'}]},r={session:'s',expectedFrameId:2};
 assert.equal(g.plan(p,r,1001),true);assert.equal(g.plan({...p,actions:[{...p.actions[0],target:undefined}]},r,1001),false);assert.equal(g.plan({...p,actions:[{...p.actions[0],ms:800}]},r,1001),false);
});
test('Rock actions use three spaced strikes per fresh observation and stop for threats',async()=>{
 let now=1000,actions=0;const field={...o,hud:{...o.hud,enemyBars:[]}},api={now:()=>now,checkStop:()=>{},sleep:async ms=>now+=ms,action:async()=>{actions++;now+=60;},release:async()=>{}};
 const result=await g.run(field,field,{mode:'actions',actions:[{type:'key',key:'VK_LBUTTON',ms:60,target:'Breakable rocks'}]},api,async()=>({...field,timestamp:now}));assert.equal(actions,3);assert.equal(result.obstacleStrikes,3);
 now=1000;await assert.rejects(g.run(o,o,{mode:'actions',actions:[{type:'key',key:'VK_LBUTTON',ms:60,target:'Breakable rocks'}]},api,async()=>o),/evidence changed/);assert.equal(actions,3);
});
test('Field combat rejects stale, low health, changed account, location and quest',()=>{
 assert.equal(g.ready(o,o,1001,'s'),true);
 for(const bad of [{timestamp:0},{session:'x'},{ocr:[{text:'UID: 111111111',x:1680,y:1050}]},{map:{...o.map,x:-1300}},{hud:{...o.hud,climbing:true}},{hud:{...o.hud,health:{current:1100,max:1700}}},{hud:{...o.hud,enemyBarDiagnostic:null}},{hud:{...o.hud,objectives:['Talk to someone']}}])assert.equal(g.ready({...o,...bad},o,1001,'s'),false);
});
test('Field combat releases inputs and stops immediately after a major health drop',async()=>{
 let now=1000,release=0;const keys=[];
 const result=await g.run(o,o,{mode:'combat',actions:[]},{now:()=>now,checkStop:()=>{},sleep:async ms=>now+=ms,key:async k=>keys.push(k),release:async()=>release++},async()=>({...o,timestamp:now,hud:{...o.hud,health:{current:1300,max:1700}}}));
 assert.deepEqual(keys,['VK_E']);assert.equal(release,1);assert.match(result.reason,/health/);
});
test('Field combat requires visible targets and always releases on input errors',async()=>{
 let now=1000,keys=0,released=0;const empty={...o,hud:{...o.hud,enemyBars:[]}},api={now:()=>now,checkStop:()=>{},sleep:async ms=>now+=ms,key:async()=>keys++,release:async()=>released++};
 await g.run(empty,empty,{mode:'combat',actions:[]},api,async()=>({...empty,timestamp:now}));assert.equal(keys,0);assert.equal(released,1);
 now=1000;await assert.rejects(g.run(o,o,{mode:'combat',actions:[]},{...api,key:async()=>{throw Error('focus lost');}},async()=>o),/focus lost/);assert.equal(released,2);
});
test('Unclassified outdoor bars cannot authorize attacks',async()=>{
 const unknown={...o,hud:{...o.hud,enemyBarDiagnostic:{level:'any'}}};let keys=0;
 await g.run(unknown,unknown,{mode:'combat',actions:[]},{now:()=>1000,checkStop:()=>{},key:async()=>keys++,release:async()=>{}},async()=>unknown);assert.equal(keys,0);
});
test('Explicit reviewed any-level combat requires a geometrically valid outdoor threat bar',async()=>{
 const bar={x:843,y:487.5,width:62,height:5,rectangularity:0.934},field={...o,hud:{...o.hud,enemyBars:[bar],enemyBarDiagnostic:{level:'any'}}},plan={mode:'combat',enemyLevel:'any',actions:[]};
 assert.equal(g.combatTargets(field,plan).length,1);
 for(const patch of [{rectangularity:undefined},{rectangularity:0.5},{x:1800},{y:1000},{width:400},{height:1}])assert.equal(g.combatTargets({...field,hud:{...field.hud,enemyBars:[{...bar,...patch}]}},plan).length,0);
 assert.equal(g.combatTargets(field,{mode:'combat'}).length,0);
 let now=1000,released=0,keys=[];
 const result=await g.run(field,field,plan,{now:()=>now,checkStop:()=>{},sleep:async ms=>now+=ms,key:async k=>keys.push(k),release:async()=>released++},async()=>({...field,timestamp:now,hud:{...field.hud,health:{current:1300,max:1700}}}));
 assert.deepEqual(keys,['VK_E']);assert.equal(released,1);assert.match(result.reason,/health/);
});
test('Field interaction requires the exact selected loot label and rejects cooking',()=>{
 const waypoint=[{text:'F',x:1100,y:520,height:30},{text:'Teleport Waypoint',x:1200,y:520,height:30}];assert.equal(g.interaction({ocr:waypoint},'Teleport Waypoint'),true);assert.equal(g.interaction({ocr:waypoint.map(r=>r.text==='Teleport Waypoint'?{...r,text:'Start Challenge'}:r)},'Start Challenge'),false);
 const rows=[{text:'F',x:1100,y:520,height:30},{text:'Exquisite Chest',x:1200,y:520,height:30}];assert.equal(g.interaction({ocr:rows},'Exquisite Chest'),true);
 assert.equal(g.interaction({ocr:rows.map(r=>r.text==='Exquisite Chest'?{...r,text:'Silver Sword'}:r)},'Silver Sword'),true);
 assert.equal(g.interaction({ocr:rows.map(r=>r.text==='Exquisite Chest'?{...r,y:580}:r)},'Exquisite Chest'),false);
 assert.equal(g.interaction({ocr:rows.map(r=>r.text==='Exquisite Chest'?{...r,text:'Cook'}:r)},'Cook'),false);
 assert.equal(g.interaction({ocr:[{text:'F',x:1100,y:485,height:32},{text:"Adventurer's Tail",x:1220,y:472,height:29},{text:'Feather',x:1216,y:498,height:35}]},"Adventurer's Tail Feather"),true);
 assert.equal(g.interaction({ocr:[{text:'F',x:1094,y:518,height:41},{text:"Adventurer's",x:1218,y:510,height:27},{text:'2 Experience',x:1189,y:535,height:38}]},"Adventurer's Experience"),true);
 assert.equal(g.interaction({ocr:[{text:'F',x:1099,y:519,height:36},{text:"Adventurer's",x:1218,y:510,height:27},{text:'2Experience',x:1192,y:535,height:37}]},"Adventurer's Experience"),true);
 assert.equal(g.interaction({ocr:[{text:'F',x:1100,y:452,height:32},{text:"Traveling Doctor's",x:1220,y:441,height:28},{text:'Handkerchief',x:1220,y:469,height:30}]},"Traveling Doctor's Handkerchief"),true);
 assert.equal(g.interaction({ocr:[{text:'F',x:1100,y:520,height:32},{text:'2 Enhancement Ore',x:1200,y:520,height:32}]},'Enhancement Ore'),true);
});
test('Explicit visual-position recovery preserves fresh identity, health and bounded witness requirements',()=>{
 const drift={...o,map:{map:'Teyvat',x:730,y:-1265}};
 assert.equal(g.ready(drift,o,1001,'s',false),false);
 assert.equal(g.ready(drift,o,1001,'s',false,true),true);
 for(const patch of [{timestamp:0},{session:'other'},{ocr:[]},{hud:{...o.hud,health:{current:100,max:1700}}},{hud:{...o.hud,climbing:true}}])assert.equal(g.ready({...drift,...patch},o,1001,'s',false,true),false);
 assert.equal(g.ready(drift,{...o,timestamp:-600000},1001,'s',false,true),false);
 assert.equal(g.ready(drift,{...o,map:{map:'Teyvat',x:730,y:-1265}},1001,'s',false,true),false);
});

test('Exam field combat is restricted to witnessed approach region and ground controls',()=>{
 const f={...o,map:{map:'Teyvat',x:-1392,y:1660},hud:{...o.hud,health:{current:2313,max:2313},objectives:['Go to the exam point']}};
 assert.equal(g.ready(f,f,1000,'s'),true);
 for(const patch of [{map:{...f.map,x:-1199}},{map:{...f.map,y:1599}},{hud:{...f.hud,objectives:['Unrelated quest']}},{hud:{...f.hud,climbing:true}},{hud:{...f.hud,health:{current:1000,max:2313}}}])assert.equal(g.ready({...f,...patch},f,1000,'s'),false);
});
test('Exam cliff climb requires the exact witnessed face and full upgraded Kaeya health',()=>{
 const f={...o,map:{map:'Teyvat',x:-1342.426,y:1691.34},ocr:o.ocr.concat([{text:'X',x:1600,y:1020},{text:'Space',x:1700,y:1020}]),hud:{...o.hud,climbing:true,groundControls:false,health:{current:2313,max:2313},enemyBars:[],objectives:['Go to the exam point']}};
 assert.equal(g.ready(f,f,1000,'s',true),true);
 for(const patch of [{map:{...f.map,x:-1352}},{hud:{...f.hud,health:{current:2312,max:2313}}},{hud:{...f.hud,enemyBars:[{}]}}])assert.equal(g.ready({...f,...patch},f,1000,'s',true),false);
});
test('Low exam rock release is one X press at the reviewed full-health witness',async()=>{
 const p={reviewed:true,session:'s',frameId:2,witnessFrameId:1,createdAt:1000,mode:'releaseClimb',actions:[{type:'key',key:'VK_X',ms:60}]},r={session:'s',expectedFrameId:2};
 assert.equal(g.plan(p,r,1000),true);
 for(const patch of [{mode:'actions'},{actions:[{type:'key',key:'VK_W',ms:60}]},{actions:[...p.actions,...p.actions]}])assert.equal(g.plan({...p,...patch},r,1000),false);
 const f={...o,map:{map:'Teyvat',x:-1207.2227,y:1660.873},ocr:o.ocr.concat([{text:'X',x:1600,y:1020},{text:'Space',x:1700,y:1020}]),hud:{...o.hud,climbing:true,groundControls:false,health:{current:2313,max:2313},enemyBars:[],objectives:['Go to the exam point']}};
 assert.equal(g.ready(f,f,1000,'s',true,false,false,true),true);
 assert.equal(g.ready({...f,map:{map:'Teyvat',x:-1300,y:2000},hud:{...f.hud,objectives:[]}},{...f,map:{map:'Teyvat',x:-1300,y:2000}},1000,'s',true,false,false,true),false);
 assert.equal(g.ready(f,f,1000,'s',true),false);
 for(const patch of [{map:{...f.map,x:-1212}},{hud:{...f.hud,health:{current:2312,max:2313}}},{hud:{...f.hud,enemyBars:[{}]}}])assert.equal(g.ready({...f,...patch},f,1000,'s',true,false,false,true),false);
 let now=1000,actions=0,released=0;
 await g.run(f,f,p,{now:()=>now,checkStop:()=>{},action:async a=>{assert.equal(a.key,'VK_X');actions++;},sleep:async n=>now+=n,release:async()=>released++},async()=>({...f,timestamp:now,hud:{...f.hud,climbing:false,groundControls:true}}));
 assert.equal(actions,1);assert.equal(released,1);
});
test('Finite ordinary-loot loop follows exact selected labels and stops at interaction changes',async()=>{
 const p={reviewed:true,session:'s',frameId:2,witnessFrameId:1,createdAt:1000,mode:'loot',actions:[]},r={session:'s',expectedFrameId:2};assert.equal(g.plan(p,r,1000),true);assert.equal(g.plan({...p,actions:[{type:'key',key:'VK_W',ms:60}]},r,1000),false);
 const frame=name=>({...o,hud:{...o.hud,enemyBars:[]},ocr:o.ocr.concat([{text:'F',x:1100,y:520,height:30},{text:name,x:1200,y:520,height:30}])});
 let now=1000,keys=0,releases=0;const api={now:()=>now,checkStop:()=>{},key:async k=>{assert.equal(k,'VK_F');keys++;},sleep:async n=>now+=n,release:async()=>releases++};
 const result=await g.run(frame('Fine Enhancement Ore'),o,p,api,async()=>({...frame(keys===1?"Adventurer's Experience":'Cook'),timestamp:now}));assert.equal(keys,2);assert.equal(releases,1);assert.deepEqual(result.lootTargets,['Fine Enhancement Ore',"Adventurer's Experience"]);
 keys=0;now=1000;await g.run(frame('Exquisite Chest'),o,p,api,async()=>o);assert.equal(keys,0);
 now=1000;await g.run(frame('Fine Enhancement Ore'),o,p,api,async()=>({...frame('Fine Enhancement Ore'),timestamp:now}));assert.equal(keys,8);
});

test('Level 13 crop recognition is limited to the reviewed combat request',()=>{
 const r={session:'s',expectedFrameId:2},p={session:'s',frameId:2,mode:'combat',enemyLevel:13};
 assert.equal(g.enemyLevel(p,r),13);
 assert.equal(g.enemyLevel({...p,mode:'actions'},r),'any');
 assert.equal(g.enemyLevel({...p,frameId:1},r),'any');
 const bar={x:1216,y:317,width:12,height:7},field={hud:{enemyBars:[bar],enemyBarDiagnostic:{level:13}}};
 assert.deepEqual(g.combatTargets(field,p),[bar]);
 assert.deepEqual(g.combatTargets(field,{...p,enemyLevel:5}),[]);
});

test('Four-row ordinary loot menus keep the selected top row and wrapped artifact names',()=>{
 const rows=[{text:'F',x:1100,y:413,height:35},{text:'Firm Arrowhead',x:1215,y:411,height:38},{text:"Traveling Doctor's",x:1219,y:467,height:38},{text:'Pocket Watch',x:1216,y:500,height:29}];
 assert.equal(g.interaction({ocr:rows},'Firm Arrowhead'),true);
 assert.equal(g.interaction({ocr:rows},"Traveling Doctor's Pocket Watch"),false);
 assert.equal(g.interaction({ocr:[{...rows[0],y:487},...rows.slice(1)]},"Traveling Doctor's Pocket Watch"),true);
 assert.equal(g.interaction({ocr:[{...rows[0],y:300},...rows.slice(1)]},'Firm Arrowhead'),false);
});
test('Reviewed crossroads combat supports only its exact requested level',()=>{
 const r={session:'s',expectedFrameId:2};
 for(const level of [11,14]){
  const p={session:'s',frameId:2,mode:'combat',enemyLevel:level},bar={x:1000,y:500,width:12,height:7};
  assert.equal(g.enemyLevel(p,r),level);
  assert.deepEqual(g.combatTargets({hud:{enemyBars:[bar],enemyBarDiagnostic:{level}}},p),[bar]);
  assert.deepEqual(g.combatTargets({hud:{enemyBars:[bar],enemyBarDiagnostic:{level:4}}},p),[]);
 }
});
test('Reviewed regional map permits only fresh safe visual ground batches at the fog boundary',()=>{
 const region={session:'s',timestamp:1000,frameId:1,hud:{bigMap:true,world:false},ocr:[{text:'Mondstadt',x:708,y:165,width:151},{text:'Whispering Woods',x:964,y:115,width:251},{text:'Windrise',x:1131,y:553,width:126},{text:'UID: 693306810',x:1680,y:1048}]};
 const field={...o,map:{map:'Teyvat',x:2300,y:4200},hud:{...o.hud,enemyBars:[],health:{current:1700,max:1700}}};
 assert.equal(g.regionalMap(region,1001,'s'),true);
 assert.equal(g.regionalMap({...region,ocr:region.ocr.map(r=>r.text==='Mondstadt'?{...r,y:r.y-7}:r)},1001,'s'),true);
 assert.equal(g.regionalMap({...region,ocr:region.ocr.map(r=>r.text==='Mondstadt'?{...r,y:r.y-9}:r)},1001,'s'),false);
 assert.equal(g.regionalMap({...region,ocr:region.ocr.map(r=>r.text==='Whispering Woods'?{...r,text:'WhisperingWoods'}:r)},1001,'s'),true);
 assert.equal(g.regionalMap({...region,ocr:region.ocr.map(r=>r.text==='Whispering Woods'?{...r,text:'WhisperingWood'}:r)},1001,'s'),false);
 assert.equal(g.ready(field,field,1001,'s',false,true,false,false,region),true);
 const historic={...field,hud:{...field.hud,enemyBarDiagnostic:null}};assert.equal(g.ready(historic,historic,1001,'s',false,true,false,false,region),false);assert.equal(g.ready(historic,historic,1001,'s',false,true,false,false,region,true),true);
 for(const patch of [{session:'other'},{timestamp:-600000},{hud:{bigMap:false}},{ocr:region.ocr.slice(1)},{ocr:region.ocr.map(r=>r.text==='Windrise'?{...r,x:1400}:r)}])assert.equal(g.regionalMap({...region,...patch},1001,'s'),false);
 for(const patch of [{hud:{...field.hud,enemyBars:[{}]}},{hud:{...field.hud,health:{current:1400,max:1700}}},{timestamp:0},{session:'other'}])assert.equal(g.ready({...field,...patch},field,1001,'s',false,true,false,false,region),false);
 const p={reviewed:true,session:'s',frameId:3,witnessFrameId:2,regionMapFrameId:1,visualPositionReviewed:true,createdAt:1000,mode:'actions',actions:[{type:'key',key:'VK_W',ms:800}]},r={session:'s',expectedFrameId:3};
 assert.equal(g.plan(p,r,1000),true);
 for(const patch of [{mode:'combat'},{visualPositionReviewed:false},{regionMapFrameId:3},{actions:[{type:'key',key:'VK_SPACE',ms:60}]}])assert.equal(g.plan({...p,...patch},r,1000),false);
 const road={...p,actions:Array.from({length:8},()=>({type:'key',key:'VK_W',ms:800}))};
 assert.equal(g.plan(road,r,1000),true);
 assert.equal(g.plan({...road,regionMapFrameId:undefined},r,1000),false);
 assert.equal(g.plan({...road,actions:road.actions.concat(road.actions[0])},r,1000),false);
 assert.equal(g.plan({...road,actions:[{type:'key',key:'VK_W',ms:801}]},r,1000),false);
});
test('Regional travel releases inputs immediately when the next local observation detects a threat',async()=>{
 const region={session:'s',timestamp:1000,frameId:1,hud:{bigMap:true,world:false},ocr:[{text:'Mondstadt',x:708,y:165,width:151},{text:'Whispering Woods',x:964,y:115,width:251},{text:'Windrise',x:1131,y:553,width:126},{text:'UID: 693306810',x:1680,y:1048}]};
 const field={...o,hud:{...o.hud,enemyBars:[],objectives:[],health:{current:1700,max:1700}}};
 let now=1000,actions=0,released=0;
 const p={mode:'actions',visualPositionReviewed:true,regionWitness:region,actions:Array.from({length:8},()=>({type:'key',key:'VK_W',ms:800}))};
 await assert.rejects(g.run(field,field,p,{now:()=>now,checkStop:()=>{},action:async()=>actions++,sleep:async n=>now+=n,release:async()=>released++},async()=>({...field,timestamp:now,hud:{...field.hud,enemyBars:[{}]}})),/evidence changed/);
 assert.equal(actions,1);assert.equal(released,1);
});

test('southern temple road field recovery stays in the bounded ground corridor',()=>{
 const f={...o,map:{map:'Teyvat',x:-1401,y:1604},hud:{...o.hud,objectives:[]}};assert.equal(g.ready(f,f,1000,'s'),true);
 for(const p of [{x:-1550,y:1604},{x:-1401,y:1400},{x:-1200,y:1604}])assert.equal(g.ready({...f,map:{map:'Teyvat',...p}},f,1000,'s'),false);
 const c={...f,ocr:f.ocr.concat([{text:'X',x:1600,y:1020},{text:'Space',x:1700,y:1020}]),hud:{...f.hud,climbing:true,groundControls:false,enemyBars:[]}};assert.equal(g.ready(c,c,1000,'s',true),false);
});

test('low plaza tree release is restricted to its witnessed full-health base',()=>{
 const f={...o,map:{map:'Teyvat',x:-929.096,y:2222.957},ocr:o.ocr.concat([{text:'X',x:1600,y:1020},{text:'Space',x:1700,y:1020}]),hud:{...o.hud,climbing:true,groundControls:false,health:{current:2313,max:2313},enemyBars:[],objectives:[]}};
 assert.equal(g.ready(f,f,1000,'s',true,false,false,true),true);
 for(const p of [{map:{...f.map,x:-940}},{hud:{...f.hud,health:{current:2000,max:2313}}},{hud:{...f.hud,enemyBars:[{}]}}])assert.equal(g.ready({...f,...p},f,1000,'s',true,false,false,true),false);
});
test('Southern Windrise regional map accepts consistent translation and rejects scale drift',()=>{
 const region={session:'s',timestamp:1000,hud:{bigMap:true,world:false},ocr:[{text:'Windrise',x:937,y:444,width:139},{text:'Thousand Winds',x:1394,y:89,width:239},{text:'Falcon Coast',x:1522,y:674,width:194},{...o.ocr[0],x:1676,y:1046}]};
 assert.equal(g.regionalMap(region,1001,'s'),true);
 for(const delta of [{x:20},{width:155}])assert.equal(g.regionalMap({...region,ocr:region.ocr.map((r,i)=>i===0?{...r,...delta}:r)},1001,'s'),false);
 assert.equal(g.regionalMap({...region,ocr:region.ocr.slice(0,3)},1001,'s'),false);
});
test('Regional Lv4 defense permits no movement and retains health, identity and target checks',()=>{
 const region={session:'s',timestamp:900,frameId:1,hud:{bigMap:true,world:false},ocr:[{text:'Windrise',x:937,y:444,width:139},{text:'Thousand Winds',x:1394,y:89,width:239},{text:'Falcon Coast',x:1522,y:674,width:194},{...o.ocr[0],x:1676,y:1046}]};
 const p={reviewed:true,session:'s',frameId:3,witnessFrameId:2,regionMapFrameId:1,visualPositionReviewed:true,createdAt:1000,mode:'combat',enemyLevel:4,actions:[]},r={session:'s',expectedFrameId:3};
 assert.equal(g.plan(p,r,1000),true);
 for(const patch of [{enemyLevel:5},{enemyLevel:13},{actions:[{type:'key',key:'VK_W',ms:800}]}])assert.equal(g.plan({...p,...patch},r,1000),false);
 const f={...o,map:{map:'Teyvat',x:979,y:-710},hud:{...o.hud,health:{current:2217,max:2313},objectives:[]}};
 assert.equal(g.ready(f,f,1000,'s',false,true,false,false,region,false,true),true);
 for(const patch of [{health:{current:1600,max:2313}},{enemyBarDiagnostic:{level:13}},{climbing:true},{objectives:['Unrelated objective']}])assert.equal(g.ready({...f,hud:{...f.hud,...patch}},f,1000,'s',false,true,false,false,region,false,true),false);
});

test('known first Cyrus camp accepts fresh area and progress markers when the long title is missed',()=>{
 const f={...o,map:{map:'Teyvat',x:-1126.2,y:2245.16},hud:{...o.hud,health:{current:2302,max:2313},objectives:['(0/3)','Quest area reached'],enemyBarDiagnostic:{level:'any'}}};
 assert.equal(g.ready(f,f,1000,'s'),true);
 assert.equal(g.ready({...f,hud:{...f.hud,objectives:['(0/3)']}},f,1000,'s'),true);
 const outside={...f,map:{...f.map,x:-1250}};assert.equal(g.ready(outside,outside,1000,'s'),false);
 assert.equal(g.ready({...f,hud:{...f.hud,objectives:['Quest area reached']}},f,1000,'s'),false);
});
test('Cyrus low ledge recovery requires exact witnessed location, full upgraded HP and quest counter',()=>{
 const f={...o,map:{map:'Teyvat',x:-1123.295,y:2302.307},ocr:[...o.ocr,{text:'X',x:1600,y:1010},{text:'Space',x:1700,y:1010}],hud:{...o.hud,groundControls:false,climbing:true,health:{current:2635,max:2635},enemyBars:[],objectives:['Check the suspicious location and eliminate any threats','(1/3)']}};
 assert.equal(g.ready(f,f,1000,'s',true),true);
 for(const patch of [{health:{current:2600,max:2635}},{enemyBars:[{}]},{objectives:['Check the suspicious location and eliminate any threats','(2/3)']}])assert.equal(g.ready({...f,hud:{...f.hud,...patch}},f,1000,'s',true),false);
 assert.equal(g.ready({...f,map:{...f.map,x:-1140}},f,1000,'s',true),false);
});

test('Cyrus travel camera permits inspection only, with full health and no visible enemies',()=>{
 const f={...o,map:{map:'Teyvat',x:-1140,y:2243},hud:{...o.hud,health:{current:2635,max:2635},enemyBars:[],objectives:['Defeat the attacking monsters']}};
 assert.equal(g.ready(f,f,1000,'s',false,false,true),true);
 assert.equal(g.ready(f,f,1000,'s'),false);
 assert.equal(g.ready(f,f,1000,'s',true,false,true),false);
 for(const patch of [{health:{current:2634,max:2635}},{enemyBars:[{}]},{climbing:true},{groundControls:false},{objectives:['Talk to someone']},{world:false}])assert.equal(g.ready({...f,hud:{...f.hud,...patch}},f,1000,'s',false,false,true),false);
 for(const patch of [{session:'x'},{timestamp:0},{ocr:[]},{map:{...f.map,x:-1099}},{map:{...f.map,y:2189}},{map:{...f.map,map:'Other'}}])assert.equal(g.ready({...f,...patch},f,1001,'s',false,false,true),false);
 assert.equal(g.cameraPlan({mode:'actions',actions:[{type:'look',dx:-696,dy:0},{type:'key',key:'VK_W',ms:60}]}),false);
});

test('plateau route low tree release is one witnessed full-health X, never a climb permission',()=>{
 const f={...o,map:{map:'Teyvat',x:-1434.979,y:2375.973},ocr:[...o.ocr,{text:'X',x:1600,y:1020},{text:'Space',x:1700,y:1020}],hud:{...o.hud,climbing:true,groundControls:false,health:{current:2635,max:2635},enemyBars:[],objectives:['Defeat the attacking monsters']}};
 assert.equal(g.ready(f,f,1000,'s',true,false,false,true),true);
 assert.equal(g.ready(f,f,1000,'s',true),false);
 for(const hp of [{current:2634,max:2635},{current:2313,max:2313}])assert.equal(g.ready({...f,hud:{...f.hud,health:hp}},f,1000,'s',true,false,false,true),false);
 for(const patch of [{enemyBars:[{}]},{objectives:['Talk to someone']},{climbing:false}])assert.equal(g.ready({...f,hud:{...f.hud,...patch}},f,1000,'s',true,false,false,true),false);
 const far={...f,map:{...f.map,x:-1430}};assert.equal(g.ready(far,far,1000,'s',true,false,false,true),false);
});
