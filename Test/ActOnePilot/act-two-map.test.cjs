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
