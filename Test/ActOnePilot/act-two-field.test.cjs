const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js');
const o={session:'s',timestamp:1000,frameId:1,map:{map:'Teyvat',x:-1354,y:1973},ocr:[{text:'UID: 693306810',x:1680,y:1050}],hud:{world:true,groundControls:true,health:{current:1640,max:1700},enemyBars:[{}],enemyBarDiagnostic:{level:4},objectives:['Lv.','4']}};
test('Field plans reject stale, replayed, wrong-session and excessive inputs',()=>{
 const p={reviewed:true,session:'s',frameId:2,witnessFrameId:1,createdAt:1000,mode:'combat',actions:[{type:'look',dx:-750,dy:0},{type:'key',key:'VK_W',ms:800}]},r={session:'s',expectedFrameId:2};assert.equal(g.plan(p,r,1001),true);
 for(const bad of [{usedAt:1001},{session:'x'},{witnessFrameId:2},{createdAt:-121000},{mode:'other'},{actions:[{type:'key',key:'VK_F',ms:800}]},{actions:[{type:'key',key:'VK_W',ms:801}]},{actions:Array(4).fill({type:'key',key:'VK_W',ms:800})}])assert.equal(g.plan({...p,...bad},r,1001),false);
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
test('Field interaction requires the exact selected loot label and rejects cooking',()=>{
 const rows=[{text:'F',x:1100,y:520,height:30},{text:'Exquisite Chest',x:1200,y:520,height:30}];assert.equal(g.interaction({ocr:rows},'Exquisite Chest'),true);
 assert.equal(g.interaction({ocr:rows.map(r=>r.text==='Exquisite Chest'?{...r,y:580}:r)},'Exquisite Chest'),false);
 assert.equal(g.interaction({ocr:rows.map(r=>r.text==='Exquisite Chest'?{...r,text:'Cook'}:r)},'Cook'),false);
 assert.equal(g.interaction({ocr:[{text:'F',x:1100,y:485,height:32},{text:"Adventurer's Tail",x:1220,y:472,height:29},{text:'Feather',x:1216,y:498,height:35}]},"Adventurer's Tail Feather"),true);
 assert.equal(g.interaction({ocr:[{text:'F',x:1094,y:518,height:41},{text:"Adventurer's",x:1218,y:510,height:27},{text:'2 Experience',x:1189,y:535,height:38}]},"Adventurer's Experience"),true);
 assert.equal(g.interaction({ocr:[{text:'F',x:1099,y:519,height:36},{text:"Adventurer's",x:1218,y:510,height:27},{text:'2Experience',x:1192,y:535,height:37}]},"Adventurer's Experience"),true);
});
