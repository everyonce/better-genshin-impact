const test=require('node:test'),assert=require('node:assert/strict');
const map=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-map.js');
const recorded=require('./act-two-hideout-map-split.fixture.json');
function target(o){return map.target(o,o.timestamp,{reviewed:true,session:o.session,frameId:o.frameId,createdAt:o.timestamp,action:'chooseWaypoint'},{session:o.session,expectedFrameId:o.frameId});}
test('recorded split Guild menu selects exact waypoint',()=>assert.deepEqual(target(recorded),{x:1460,y:734}));
test('recorded tracked mystery overlap selects the exact headquarters waypoint',()=>{
 const o=require('./act-two-hideout-map-mystery.fixture.json');assert.deepEqual(target(o),{x:1464,y:809});
 const wrong=structuredClone(o);wrong.ocr.find(x=>x.text==='Teleport Waypoint').y=730;assert.equal(target(wrong),null);
});
test('split Guild rejects distant, duplicate, missing and misaligned tokens',()=>{
 for(const mutate of [o=>o.ocr.find(x=>x.text==='Guild').x+=40,o=>o.ocr.find(x=>x.text==='Guild').y+=20,o=>o.ocr.push({...o.ocr.find(x=>x.text==='Guild')}),o=>o.ocr=o.ocr.filter(x=>x.text!=='Guild')]){
  const o=structuredClone(recorded);mutate(o);assert.equal(target(o),null);
 }
});
