const test=require('node:test'),assert=require('node:assert/strict'),m=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('statue recovery switches only a living Traveler in the verified safe location',async()=>{
 const o={map:{map:'Teyvat',x:-1265.917,y:1928.381},hud:{world:true,groundControls:true,health:{current:1363,max:1363},enemyBars:[],objectives:[]},ocr:[{text:'Kaeya',x:1690,y:440}]};
 for(const [p,ok] of [[{hud:{...o.hud,health:{current:2436,max:2764},objectives:['Defeat the ambush']}},true],[{hud:{...o.hud,health:{current:2451,max:2451}}},true],[{hud:{...o.hud,health:{current:1740,max:1740}}},true],[{},true],[{map:{map:'Teyvat',x:-1300,y:2300}},false],[{hud:{...o.hud,enemyBars:[{}]}},false],[{hud:{...o.hud,health:{current:600,max:1363}}},true],[{hud:{...o.hud,health:{current:0,max:1363}}},false],[{map:{map:"Teyvat",x:-1266.35,y:1934.03}},true],[{ocr:[]},false]]){
  let keys=[];const f={...o,...p},api={runActTwoNavigationWithPause:async(a,b,cb)=>cb(f),keyPress:async k=>keys.push(k),sleep:async()=>{}};
  await m.runQuestStep('actTwoStatueSelectKaeya',f,api,async()=>({...f,frameId:3}));assert.deepEqual(keys,ok?['VK_3']:[]);
 }
});

test('final glider recovery still requires the safe Statue and living Traveler',async()=>{
 const o={map:{map:'Teyvat',x:-1265.917,y:1928.381},hud:{world:true,groundControls:true,health:{current:2451,max:2451},enemyBars:[],objectives:['Follow the route and fly to the finish line in time']},ocr:[{text:'Kaeya',x:1690,y:440}]};
 for(const [change,ok] of [[{},true],[{map:{map:'Teyvat',x:0,y:0}},false],[{hud:{...o.hud,enemyBars:[{}]}},false],[{hud:{...o.hud,objectives:['Another quest']}},false]]){
  const f={...o,...change},keys=[];await m.runQuestStep('actTwoStatueSelectKaeya',f,{runActTwoNavigationWithPause:async(a,b,cb)=>cb(f),keyPress:async k=>keys.push(k),sleep:async()=>{}},async()=>({...f,frameId:3}));assert.deepEqual(keys,ok?['VK_3']:[]);
 }
});
