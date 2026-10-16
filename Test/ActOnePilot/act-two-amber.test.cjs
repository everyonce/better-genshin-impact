const test=require('node:test'),assert=require('node:assert/strict');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const recovery=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-town-recovery.js');
test('Amber talk requires the selected matching NPC and objective',async()=>{
 const row=(text,x,y)=>({text,x,y,width:60,height:24}),field={hud:{interact:true,objectives:['Talk to Amber']},ocr:[row('Amber',1210,520),row('F',1100,520)]};let keys=[];
 const api={runActTwoNavigationWithPause:async(o,observe,fn)=>fn(field),keyPress:async k=>keys.push(k),sleep:async()=>{},now:()=>0,checkStop:()=>{}};
 await mission.runQuestStep('actTwoAmberTalk',{hud:{}},api,async()=>({hud:{world:true}}));assert.deepEqual(keys,['VK_F']);
 for(const patch of [{text:'Wagner'},{y:580}]){keys=[];const old=field.ocr[0];field.ocr[0]={...old,...patch};await mission.runQuestStep('actTwoAmberTalk',{hud:{}},api,()=>{});assert.deepEqual(keys,[]);field.ocr[0]=old;}
});
test('Low Amber stair release remains tied to exact witnessed location, health and climb controls',()=>{
 const o={session:'s',timestamp:1000,map:{map:'Teyvat',x:-809.506,y:2309.961},hud:{climbing:true,objectives:['Talk to Amber'],health:{current:2313,max:2313},enemyBars:[]},ocr:[{text:'X',x:1600,y:1000},{text:'Space',x:1700,y:1000}]};
 assert.equal(recovery.ready(o,1000,'s'),true);
 assert.equal(recovery.ready({...o,map:{map:'Teyvat',x:-775.756,y:2293.423}},1000,'s'),true);
 for(const patch of [{map:{...o.map,x:-800}},{hud:{...o.hud,health:{current:1800,max:2313}}},{hud:{...o.hud,objectives:['Talk to Kaeya']}},{hud:{...o.hud,enemyBars:[{}]}},{ocr:[]}])assert.equal(recovery.ready({...o,...patch},1000,'s'),false);
});
test('Amber stair mantle is limited to the verified railing vicinity',()=>{
 const o={session:'s',timestamp:1000,map:{map:'Teyvat',x:-756.959,y:2273.944},hud:{climbing:true,objectives:['Talk to Amber'],health:{current:2313,max:2313},enemyBars:[],enemyBarDiagnostic:{level:'any'}}};
 assert.equal(recovery.wallReady(o,1000,'s'),true);
 for(const [x,y] of [[-727.434,2277.426],[-708.416,2286.529]])assert.equal(recovery.wallReady({...o,map:{map:'Teyvat',x,y}},1000,'s'),true);
 for(const patch of [{map:{...o.map,x:-750}},{session:'other'},{hud:{...o.hud,health:{current:2312,max:2313}}},{hud:{...o.hud,objectives:['Talk to Kaeya']}},{hud:{...o.hud,enemyBars:[{}]}}])assert.equal(recovery.wallReady({...o,...patch},1000,'s'),false);
});

test('Amber retry interaction is restricted to healthy safe exam location and selected NPC',async()=>{const base={map:{map:'Teyvat',x:-1309.18,y:1721.85},hud:{interact:true,groundControls:true,climbing:false,health:{current:4015,max:4015},enemyBars:[],objectives:["Follow Amber's instructions and take the examagain"]},ocr:[{text:'Amber',x:1210,y:520,width:60,height:24},{text:'F',x:1100,y:520,width:20,height:24}]};for(const [patch,expected] of [[{},1],[{map:{map:'Teyvat',x:-698.99219,y:2347.92676}},1],[{map:{map:'Teyvat',x:-694,y:2347.92676}},0],[{hud:{...base.hud,health:{current:3953,max:4015}}},1],[{map:{...base.map,x:-1400}},0],[{hud:{...base.hud,health:{current:3000,max:4015}}},0],[{hud:{...base.hud,enemyBars:[{}]}},0],[{hud:{...base.hud,objectives:['Other quest']}},0],[{ocr:base.ocr.slice(1)},0]]){let keys=[];const api={runActTwoNavigationWithPause:async(o,observe,fn)=>fn({...base,...patch}),keyPress:async k=>keys.push(k),sleep:async()=>{},now:()=>0,checkStop:()=>{}};await mission.runQuestStep('actTwoAmberTalk',{hud:{}},api,async()=>({hud:{world:true}}));assert.equal(keys.length,expected);}});

test('recorded Amber prompt settles without input and still requires fresh F',async()=>{const first=require('./act-two-amber-prompt-9051.fixture.json'),ready=require('./act-two-amber-prompt-9052.fixture.json');for(const succeeds of [true,false]){let keys=[],reads=0;const api={runActTwoNavigationWithPause:async(o,observe,fn)=>fn(first),keyPress:async k=>keys.push(k),sleep:async()=>{},now:()=>0,checkStop:()=>{}};await mission.runQuestStep('actTwoAmberTalk',{hud:{}},api,async()=>++reads===1?(succeeds?ready:first):succeeds?{hud:{world:true}}:first);assert.equal(keys.length,succeeds?1:0);assert.ok(reads<=3);}});
