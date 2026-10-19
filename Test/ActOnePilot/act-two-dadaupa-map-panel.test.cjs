const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-map.js');
test('exact locked Dadaupa waypoint panel closes without navigation or teleport',()=>{
 const now=10000,session='map',o={session,timestamp:now,frameId:302,hud:{bigMap:false},ocr:[
  {text:'Teleport Waypoint',x:1492,y:22},{text:' Dadaupa Gorge, Mondstadt',x:1458,y:103},
  {text:'*Interact with the Teleport Waypoint to',x:1454,y:917},{text:'activate teleportation',x:1552,y:943},
  {text:'Navigate',x:1622,y:991},{text:'X',x:1850,y:6}]};
 const p={reviewed:true,session,frameId:303,createdAt:now,action:'closeInspectedDadaupaWaypoint'},r={session,expectedFrameId:303};
 assert.deepEqual(g.target(o,now,p,r),{x:1876,y:34});
 for(const text of ['Teleport Waypoint',' Dadaupa Gorge, Mondstadt','*Interact with the Teleport Waypoint to','activate teleportation','Navigate','X'])
  assert.equal(g.target({...o,ocr:o.ocr.filter(x=>x.text!==text)},now,p,r),null,text);
 assert.equal(g.target(o,now,{...p,action:'teleport'},r),null);
});
test('Ley Line and waypoint overlap selects only the reviewed Blossom row',()=>{
 const now=20000,session='map',o={session,timestamp:now,frameId:308,hud:{bigMap:true},ocr:[
  {text:'Ley Line Outcrop: Blossom of',x:1319,y:701},{text:'Revelation',x:1324,y:735},
  {text:'Teleport Waypoint',x:1326,y:792}]};
 const p={reviewed:true,session,frameId:309,createdAt:now,action:'chooseBlossom'},r={session,expectedFrameId:309};
 assert.deepEqual(g.target(o,now,p,r),{x:1490,y:734});
 for(const text of o.ocr.map(x=>x.text))assert.equal(g.target({...o,ocr:o.ocr.filter(x=>x.text!==text)},now,p,r),null,text);
 assert.equal(g.target(o,now,{...p,action:'teleport'},r),null);
});
test('tracked Starsnatch Blossom panel closes without cancelling navigation',()=>{
 const now=30000,session='map',o={session,timestamp:now,frameId:311,hud:{bigMap:false},ocr:[
  {text:'Ley Line Outcrop:',x:1492,y:6},{text:'Blossom of Revelation',x:1488,y:34},
  {text:' Starsnatch Cliff, Mondstadt',x:1459,y:101},{text:'Treasure Collection Cost 20',x:1452,y:413},
  {text:'Cancel Navigation',x:1556,y:991},{text:'X',x:1848,y:6}]};
 const p={reviewed:true,session,frameId:312,createdAt:now,action:'closeStarsnatchBlossomPanel'},r={session,expectedFrameId:312};
 assert.deepEqual(g.target(o,now,p,r),{x:1876,y:34});
 for(const text of o.ocr.map(x=>x.text))assert.equal(g.target({...o,ocr:o.ocr.filter(x=>x.text!==text)},now,p,r),null,text);
 assert.equal(g.target(o,now,{...p,action:'navigateBlossom'},r),null);
});
