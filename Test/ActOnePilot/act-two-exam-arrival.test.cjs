const test=require('node:test'),assert=require('node:assert/strict');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('wilderness Amber arrival uses bounded pause wrapper',async()=>{
 let calls=0;
 const api={runActTwoNavigationWithPause:async()=>{calls++;return {pauseVerified:true};}};
 const route={objective:'Talk to Amber',deadlineMs:25000,waypoints:[{map:'Teyvat',x:-1311,y:1711}]};
 assert.equal((await mission.runNavigation(route,{hud:{}},api,()=>{})).pauseVerified,true);
 for(const patch of [{deadlineMs:45001},{deadlineMs:0},{waypoints:Array(5).fill(route.waypoints[0])}])assert.equal((await mission.runNavigation({...route,...patch},{hud:{}},api,()=>{})).status,'stopped');
 assert.equal(calls,1);
});
