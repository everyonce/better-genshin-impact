const test=require('node:test'),assert=require('node:assert/strict'),mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const req={objective:'Explore for Adventure Rank',deadlineMs:30000,waypoints:[{map:'Teyvat',x:-1200,y:1900}]};
test('Rank exploration requires finite protected starter-region route',async()=>{
 let calls=0;const api={runActTwoNavigationWithPause:async()=>{calls++;return {pauseVerified:true};}};
 assert.equal((await mission.runNavigation(req,{hud:{}},api,()=>{})).pauseVerified,true);
 for(const r of [{...req,deadlineMs:45001},{...req,waypoints:[{map:'Teyvat',x:0,y:0}]},{...req,waypoints:Array(5).fill(req.waypoints[0])}])assert.equal((await mission.runNavigation(r,{hud:{}},api,()=>{})).status,'stopped');
 assert.equal(calls,1);
});
test('Exploration stops on threats or health loss',async()=>{
 for(const patch of [{enemyBars:[{}]},{health:{current:1400,max:1700}}]){
  let now=0;const field={map:{map:'Teyvat',x:-1200,y:1900,cameraAngle:0},hud:{world:true,groundControls:true,health:{current:1700,max:1700},objectives:[],enemyBars:[],...patch}};
  const api={now:()=>now,sleep:async n=>now+=n,checkStop:()=>{},runActTwoNavigationWithPause:async(o,observe,cb)=>cb(field)};
  assert.equal((await mission.runNavigation(req,{hud:{}},api,async()=>field)).status,'stopped');
 }
});
test('Explicit exploration does not depend on ambient or tracked objective text',async()=>{
 for(const objectives of [[],['33332','33232'],['Mikbail'],['Return to Mondstadt']]){
  let now=0;const field={map:{map:'Teyvat',x:-1200,y:1900,cameraAngle:0},hud:{world:true,groundControls:true,health:{current:1700,max:1700},objectives,enemyBars:[]}};
  const api={now:()=>now,sleep:async n=>now+=n,checkStop:()=>{},runActTwoNavigationWithPause:async(o,observe,cb)=>cb(field)};
  assert.equal((await mission.runNavigation(req,{hud:{}},api,async()=>field)).status,'arrived');
  assert.equal((await mission.runNavigation({...req,objective:'Talk to Amber'},{hud:{}},api,async()=>field)).status,'stopped');
 }
});
test('Boulder pickup refuses a changed location, health or active objective without jumping',async()=>{
 const base={map:{x:-1265.26,y:1974.11,cameraAngle:290},hud:{world:true,groundControls:true,health:{current:1700,max:1700},objectives:[]}};
 for(const field of [{...base,map:{...base.map,x:-1270}},{...base,hud:{...base.hud,health:{current:1600,max:1700}}},{...base,hud:{...base.hud,objectives:['Another objective']}}]){
  let inputs=0;const api={runActTwoNavigationWithPause:async(o,observe,cb)=>cb(field),keyPress:async()=>inputs++,forward:async()=>inputs++};
  assert.equal((await mission.runQuestStep('actTwoWindriseOculus',{},api,async()=>field)).status,'stopped');assert.equal(inputs,0);
 }
});
test('Boulder pickup emits only a short jump and forward hold, then observes',async()=>{
 const field={frameId:2,map:{x:-1265.26,y:1974.11,cameraAngle:290},hud:{world:true,groundControls:true,health:{current:1700,max:1700},objectives:[]}},inputs=[];
 const api={runActTwoNavigationWithPause:async(o,observe,cb)=>cb(field),keyPress:async k=>inputs.push(k),forward:async ms=>inputs.push(ms),sleep:async()=>{}};
 const result=await mission.runQuestStep('actTwoWindriseOculus',{},api,async()=>({...field,frameId:3}));
 assert.deepEqual(inputs,['VK_SPACE',650]);assert.equal(result.frameId,3);
});
