const test=require('node:test'),assert=require('node:assert/strict'),gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-map.js');
const p={session:'s',frameId:58,createdAt:1000,reviewed:true,action:'mondstadtGateWaypoint'},r={session:'s',expectedFrameId:58};
const o={timestamp:1000,hud:{bigMap:true},ocr:[{text:'Mondstadt',x:834,y:397},{text:'Windrise',x:1137,y:674},{text:'Cider Lake',x:852,y:230}]};
test('reviewed waypoint refuses panned maps, stale frames and reused plans',()=>{
 assert.deepEqual(gate.target(o,1000,p,r),{x:1099,y:560});
 assert.equal(gate.target({...o,ocr:o.ocr.slice(1)},1000,p,r),null);
 assert.equal(gate.target(o,2001,p,r),null);assert.equal(gate.target(o,1000,{...p,consumed:true},r),null);
});
test('teleport requires exact unlocked waypoint panel and button',()=>{
 const t={...o,ocr:[{text:'Teleport Waypoint',x:1492,y:22},{text:' Starfell Valley, Mondstadt',x:1464,y:103},{text:'Teleport',x:1650,y:1000,width:150,height:30}]};
 assert.deepEqual(gate.target(t,1000,{...p,action:'teleport'},r),{x:1725,y:1015});
 assert.equal(gate.target({...t,ocr:[...t.ocr,{text:'Go to activate waypoint'}]},1000,{...p,action:'teleport'},r),null);
 assert.equal(gate.target(o,1000,{...p,action:'teleport'},r),null);
});
test('overlapping map markers select the waypoint row without choosing the domain',()=>{
 const popup={...o,ocr:[...o.ocr,{text:'Teleport Waypoint',x:1321,y:713,width:283,height:46},{text:'Temple of the Falcon',x:1319,y:786,width:315,height:44}]};
 assert.deepEqual(gate.target(popup,1000,{...p,action:'chooseWaypoint'},r),{x:1463,y:736});
});

test('recorded city waypoint, overlap and unlocked panel retain exact fresh layout guards',()=>{
 const fs=require('node:fs');
 function fixture(name){return JSON.parse(fs.readFileSync(__dirname+'/act-two-'+name+'.fixture.json','utf8'));}
 for(const [name,action] of [['city-map','cityWaypoint'],['city-map-overlap','chooseWaypoint'],['city-map-panel','teleport']]){
  const f=fixture(name),plan={...p,session:f.session,frameId:f.frameId,createdAt:f.timestamp,action},req={session:f.session,expectedFrameId:f.frameId};
  assert.ok(gate.target(f,f.timestamp,plan,req));
  assert.equal(gate.target(f,f.timestamp+1001,plan,req),null);
  assert.equal(gate.target(f,f.timestamp,{...plan,consumed:true},req),null);
 }
 const f=fixture('city-map-panel');f.ocr.push({text:'Go to activate waypoint'});
 assert.equal(gate.target(f,f.timestamp,{...p,session:f.session,frameId:f.frameId,createdAt:f.timestamp,action:'teleport'},{session:f.session,expectedFrameId:f.frameId}),null);
});

test('Cyrus marker inspection and close preserve exact map and quest evidence',()=>{
 const f={timestamp:1000,hud:{bigMap:true},ocr:[{text:'Starfell Lake',x:970,y:349},{text:'Whispering Woods',x:712,y:490},{text:'Mondstadt',x:414,y:544}]};
 assert.deepEqual(gate.target(f,1000,{...p,action:'inspectCyrusNearest'},r),{x:923,y:680});
 assert.equal(gate.target({...f,ocr:f.ocr.slice(1)},1000,{...p,action:'inspectCyrusNearest'},r),null);
 const panel={timestamp:1000,hud:{bigMap:false},ocr:[{text:'Not to be Missed',x:1486,y:20},{text:'Starfell Valley, Mondstadt',x:1480,y:103},{text:'Cancel Navigation',x:1553,y:989},{text:'X',x:1848,y:8}]};
 assert.deepEqual(gate.target(panel,1000,{...p,action:'closeCyrusPanel'},r),{x:1876,y:34});
 for(let i=0;i<panel.ocr.length;i++)assert.equal(gate.target({...panel,ocr:panel.ocr.filter((_,n)=>n!==i)},1000,{...p,action:'closeCyrusPanel'},r),null);
});
