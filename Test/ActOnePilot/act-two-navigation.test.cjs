const test=require('node:test'),assert=require('node:assert/strict');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('Guild navigation rejects unbounded travel and requires local pause protection',async()=>{
 const request={objective:'Talk to Katheryne for more details',deadlineMs:30000,waypoints:[{map:'Teyvat',x:0,y:0}]};
 const observation={hud:{}};
 assert.equal((await mission.runNavigation(request,observation,{},()=>{})).status,'stopped');
 let wrapped=0;
 const api={runActTwoNavigationWithPause:async(initial,observe,callback)=>{wrapped++;assert.equal(initial,observation);assert.equal(typeof callback,'function');return {pauseVerified:true};}};
 assert.equal((await mission.runNavigation({...request,deadlineMs:90000},observation,api,()=>{})).status,'stopped');
 assert.equal(wrapped,0);
 assert.deepEqual(await mission.runNavigation(request,observation,api,()=>{}),{pauseVerified:true});
 assert.equal(wrapped,1);
});
