const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js');
const o={session:'s',timestamp:1000,frameId:1,map:{map:'Teyvat',x:-1354,y:1973},ocr:[{text:'UID: 693306810',x:1680,y:1050}],hud:{world:true,groundControls:true,health:{current:1640,max:1700},enemyBars:[{}],enemyBarDiagnostic:{level:4},objectives:['Lv.','4']}};
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
