const test=require('node:test'),assert=require('node:assert/strict'),m=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const field={timestamp:1000,map:{map:'Teyvat',x:-1427.426,y:1661.825,cameraAngle:18},hud:{world:true,groundControls:true,health:{current:2313,max:2313},enemyBars:[],objectives:[]},ocr:[]};
async function run(f,seen){let moves=0,keys=[];const api={now:()=>1000,runActTwoNavigationWithPause:async(a,b,cb)=>cb(f),forward:async ms=>{assert.equal(ms,600);moves++;},sleep:async()=>{},keyPress:async k=>keys.push(k)};const result=await m.runQuestStep('actTwoLionInspect',f,api,async()=>seen||f);return {moves,keys,result};}
test('Lion inspection has a three-move ceiling and stops on danger',async()=>{
 assert.equal((await run(field)).moves,3);
 for(const f of [{...field,map:{...field.map,x:-1500}},{...field,timestamp:-1},{...field,hud:{...field.hud,climbing:true}},{...field,hud:{...field.hud,enemyBars:[{}]}},{...field,hud:{...field.hud,health:{current:1500,max:2313}}}])assert.equal((await run(f)).moves,0);
 const r=await run(field,{...field,hud:{...field.hud,enemyBars:[{}]}});assert.equal(r.moves,1);assert.deepEqual(r.keys,[]);
});
test('Lion inspection opens only the exactly selected entrance and never starts a trial',async()=>{
 const f={...field,ocr:[{text:'Temple of the Lion',x:1250,y:520,height:30},{text:'F',x:1120,y:520,height:30}]};
 const r=await run(f);assert.equal(r.moves,0);assert.deepEqual(r.keys,['VK_F']);assert.equal(r.result.entranceOpened,true);
 const bad=await run({...f,hud:{...f.hud,interact:true},ocr:[f.ocr[0],{...f.ocr[1],y:580}]});assert.deepEqual(bad.keys,[]);assert.equal(bad.moves,0);
});

test('locked trial close requires its exact menu and restores pause',async()=>{
 let keys=[];const o={timestamp:1000,ocr:[{text:'Domain Entrance'},{text:'Domain unlocks at Adventure Rank 16'},{text:'Elemental Trial: Vaporize'},{text:'Elemental Trial: Vaporize'}]},api={now:()=>1000,keyPress:async k=>keys.push(k),sleep:async()=>{},finishActTwoDialogue:async(a,b,r)=>({...r,pauseVerified:true})};
 assert.equal((await m.runQuestStep('actTwoLionInspectClose',o,api,async()=>({frameId:2}))).pauseVerified,true);assert.deepEqual(keys,['VK_ESCAPE']);keys=[];await m.runQuestStep('actTwoLionInspectClose',{...o,ocr:o.ocr.slice(1)},api,async()=>({}));assert.deepEqual(keys,[]);
});
test('southern prerequisite corridor stays bounded and requires protected navigation',async()=>{
 let calls=0;const api={runActTwoNavigationWithPause:async()=>{calls++;return {wrapped:true};}},req={objective:'Explore for Adventure Rank',deadlineMs:25000,waypoints:[{map:'Teyvat',x:-1430,y:1465}]};
 assert.equal((await m.runNavigation(req,{hud:{}},api,()=>{})).wrapped,true);assert.equal(calls,1);
 for(const pos of [{x:-1600,y:1500},{x:-1430,y:1399},{x:-1200,y:1465}])assert.equal((await m.runNavigation({...req,waypoints:[{map:'Teyvat',...pos}]},{hud:{}},api,()=>{})).status,'stopped');assert.equal(calls,1);
});
