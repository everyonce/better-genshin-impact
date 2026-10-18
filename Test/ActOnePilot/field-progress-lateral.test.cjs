const test=require('node:test'),assert=require('node:assert/strict');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/field-progress.js');
test('recorded live sideways batch and stationary stamina observation permit the reviewed continuation',()=>{const f=require('./field-progress-lateral.fixture.json'),[a,b,w]=f.observations,p={mode:'climb',actions:Array.from({length:4},()=>({type:'key',key:'VK_D',ms:600})),progressReview:f.review},h=g.finish(g.begin({version:1,entries:[]},p,a,'recorded'),'recorded',b);assert.equal(g.rejection(h,p,w),null);p.actions[0].key='VK_W';assert.match(g.rejection(h,p,w),/passed entrance elevation/);});
function setup(){
 const a={session:'s',frameId:4874,timestamp:100,map:{map:'Teyvat',x:1,y:1,cameraAngle:50},hud:{world:true,climbing:true,groundControls:false,objectives:["Enter Raptor's Hideout",'Lower 27m']}};
 const b=structuredClone(a);b.frameId=4896;b.timestamp=200;b.map.cameraAngle=54;b.hud.objectives[1]='Lower 26m';
 const p={mode:'climb',actions:Array.from({length:4},()=>({type:'key',key:'VK_D',ms:600})),progressReview:{kind:'lateral-climb',fromFrame:4874,toFrame:4896,landmark:'Continuous rock face around the right-hand bulge',visibleContinuousWall:true}};
 const h=structuredClone(g.finish(g.begin({version:1,entries:[]},p,a,'side'),'side',b));return {a,b,p,h};
}
test('completed sideways hideout climb with closer same target permits reviewed same direction',()=>{const {b,p,h}=setup();assert.equal(g.rejection(h,p,b),null);});
test('fresh stationary reobservation must retain the completed endpoint distance',()=>{const s=setup(),b=structuredClone(s.b),{p,h}=s;b.frameId++;b.timestamp++;p.progressReview.toFrame=b.frameId;assert.equal(g.rejection(h,p,b),null);b.hud.objectives[1]='Lower 25m';assert.match(g.rejection(h,p,b),/unverified/);});
test('lateral evidence never permits upward, reversed, or uncertain movement',()=>{
 for(const key of ['VK_W','VK_A']){const {b,p,h}=setup();p.actions=[{type:'key',key,ms:600}];assert.match(g.rejection(h,p,b),/unverified|passed entrance elevation/);}
 const {b,p,h}=setup();h.entries[0].end=null;assert.match(g.rejection(h,p,b),/unverified/);
});
test('hideout Lower elevation blocks further ascent even outside old coordinate history',()=>{const {b,p,h}=setup();b.map.x+=500;p.actions=[{type:'key',key:'VK_W',ms:600}];assert.match(g.rejection(h,p,b),/passed entrance elevation/);});
test('lateral evidence rejects unchanged distance, different objective, camera drift, and missing review',()=>{
 for(const change of [s=>s.b.hud.objectives[1]='Lower 27m',s=>s.b.hud.objectives[0]='Other quest',s=>s.b.map.cameraAngle=70,s=>s.p.progressReview.visibleContinuousWall=false,s=>s.h.entries[0].actions[0].key='VK_W']){const s=setup();change(s);assert.match(g.rejection(s.h,s.p,s.b),/unverified/);}
});
