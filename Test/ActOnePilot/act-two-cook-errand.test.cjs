const test=require('node:test'),assert=require('node:assert/strict'),m=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('Good Hunter cook opening needs known location, health and selected Cook label',async()=>{
 const base={frameId:2,map:{map:'Teyvat',x:-886.7,y:2240.3},hud:{health:{current:2136,max:2313},objectives:[]},ocr:[{text:'Cook',x:1210,y:500,width:80,height:30},{text:'F',x:1100,y:500,width:40,height:30}]};
 for(const [patch,ok] of [[{},true],[{map:{map:'Teyvat',x:-800,y:2240}},false],[{hud:{health:{current:1500,max:2313},objectives:[]}},false],[{ocr:[]},false]]){
  const o={...base,...patch};let presses=0;const api={runActTwoNavigationWithPause:async(_a,_b,cb)=>cb(o),selectActTwoCook:async()=>{},sleep:async()=>{},keyPress:async()=>presses++};
  const result=await m.runQuestStep('actTwoCookOpen',{},api,async()=>o);
  assert.equal(presses,ok?1:0);assert.equal(!!result.cookingOpened,ok);
 }
});
test('mastered cooking back action rejects field, incomplete and unrelated panels',async()=>{
 const o={map:null,hud:{world:false},ocr:[['Cook',140,35],['Auto Cook',715,1000],['Cooking ingredients required',77,410],['Amber',1730,300]].map(([text,x,y])=>({text,x,y}))};
 for(const [p,ok] of [[o,true],[{...o,map:{x:1}},false],[{...o,hud:{world:true}},false],[{...o,ocr:o.ocr.filter(r=>r.text!=='Auto Cook')},false]]){
  let keys=[];const api={keyPress:async k=>keys.push(k),sleep:async()=>{}};
  await m.runQuestStep('actTwoCookBack',p,api,async()=>({...p,frameId:5}));
  assert.deepEqual(keys,ok?['VK_ESCAPE']:[]);
 }
});
