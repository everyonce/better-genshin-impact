const test=require('node:test'),assert=require('node:assert/strict'),m=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('recorded close Statue position advances inside interaction radius instead of declaring arrival at1.6m',async()=>{
 const o=structuredClone(require('./act-two-statue-close-approach.fixture.json')),target={map:'Teyvat',x:-1265.917,y:1928.381};o.map.cameraAngle=m.bearing(o.map,target);let now=0,moves=0;
 const api={now:()=>now,checkStop(){},sleep:async ms=>now+=ms,forward:async ms=>{assert(ms<=250);moves++;now+=ms;},rotate:async()=>assert.fail('already aligned')};
 const r=await m.runNavigation({objective:'Explore for Adventure Rank',deadlineMs:10000,waypoints:[target]},o,api,async()=>({...o,map:{...target,cameraAngle:o.map.cameraAngle}}),true);
 assert.equal(r.status,'arrived');assert.equal(moves,1);
});
