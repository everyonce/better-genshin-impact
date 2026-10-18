const test=require('node:test'),assert=require('node:assert/strict'),m=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('Good Hunter allows verified current party health profiles without relaxing location or selected prompt',async()=>{
 for(const [max,current,location,prompt,ok] of [[2764,2764,true,true,true],[4015,4015,true,true,true],[2764,2349,true,true,false],[2764,2765,true,true,false],[9999,9999,true,true,false],[2764,2764,false,true,false],[2764,2764,true,false,false]]){
  const o={map:{map:'Teyvat',x:location?-886.7:-800,y:2240.3},hud:{health:{max,current},objectives:["Enter Raptor's Hideout"]},ocr:prompt?[{text:'Cook',x:1210,y:520,width:80,height:24},{text:'F',x:1100,y:520,width:24,height:24}]:[]};let presses=0;
  const api={runActTwoNavigationWithPause:async(a,b,fn)=>fn(o),selectActTwoCook:async()=>{},sleep:async()=>{},keyPress:async()=>presses++};
  await m.runQuestStep('actTwoCookOpen',{},api,async()=>o);assert.equal(presses,ok?1:0);
 }
});
