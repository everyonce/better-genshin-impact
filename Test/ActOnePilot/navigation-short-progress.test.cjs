const test=require('node:test'),assert=require('node:assert/strict'),mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
async function simulate(speed,points){
 let clock=0,x=-750,y=2280,angle=180,holds=[];
 const observe=async()=>({map:{map:'Teyvat',x,y,cameraAngle:angle},hud:{world:true,groundControls:true,climbing:false,enemyBars:[],health:{current:3953,max:4015},lowHealth:false,objectives:['Go to the door of Mondstadt Cathedral']},ocr:[]});
 const api={now:()=>clock,checkStop(){},sleep:async ms=>clock+=ms,rotate:async dx=>{angle=(angle+dx/8+360)%360;},forward:async ms=>{holds.push(ms);x-=Math.cos(angle*Math.PI/180)*speed*ms/1000;y-=Math.sin(angle*Math.PI/180)*speed*ms/1000;clock+=ms;},runActTwoNavigationWithPause:async(o,obs,fn)=>fn(o)};
 const result=await mission.runNavigation({objective:'Explore for Adventure Rank',deadlineMs:20000,waypoints:points.map(x=>({map:'Teyvat',x,y:2280}))},await observe(),api,observe);
 return {result,holds,x};
}
test('recorded stair-speed short holds do not accumulate a false stall across arrival',async()=>{
 const {result,holds}=await simulate(3,[-747,-740]);assert.equal(result.status,'arrived');assert.ok(holds.filter(ms=>ms<=166).length>=3);assert.ok(holds.every(ms=>ms<=800));
});
test('unchanged coordinates still stop after three bounded movement attempts',async()=>{
 const {result,holds}=await simulate(0,[-747]);assert.equal(result.reason,'Map coordinates stalled');assert.equal(holds.length,3);
});
test('tiny localization jitter is not accepted as short-hold progress',async()=>{
 const {result,holds}=await simulate(.05,[-747]);assert.equal(result.reason,'Map coordinates stalled');assert.equal(holds.length,3);
});
