const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-map.js'),o=require('./act-two-starfell-statue.fixture.json');
test('recorded Starfell Statue teleport needs its fresh exact panel and positive Teleport button',()=>{const p={reviewed:true,session:o.session,frameId:o.frameId,createdAt:o.timestamp,action:'teleport'},r={session:o.session,expectedFrameId:o.frameId};assert.deepEqual(g.target(o,o.timestamp,p,r),{x:1693,y:1007});for(const q of [{...o,timestamp:o.timestamp-1001},{...o,ocr:o.ocr.filter(v=>v.text!=='Teleport')},{...o,hud:{bigMap:false},ocr:o.ocr.map(v=>v.text==='Starfell Lake, Mondstadt'?{...v,text:'Unknown, Mondstadt'}:v)}])assert.equal(g.target(q,o.timestamp,p,r),null);});

test('both witnessed Starfell label positions retain exact panel and button guards',()=>{
 const p={reviewed:true,session:o.session,frameId:o.frameId,createdAt:o.timestamp,action:'teleport'},r={session:o.session,expectedFrameId:o.frameId};
 const withLocation=(x)=>({...o,ocr:o.ocr.map(v=>v.text==='Starfell Lake, Mondstadt'?{...v,x}:v)});
 for(const x of [1452,1460,1468,1470,1478,1486])assert.deepEqual(g.target(withLocation(x),o.timestamp,p,r),{x:1693,y:1007});
 for(const x of [1451,1487,1550])assert.equal(g.target(withLocation(x),o.timestamp,p,r),null);
 for(const text of ['Statues of The Seven –','Anemo','Starfell Lake, Mondstadt','Teleport']){
  const missing={...o,ocr:o.ocr.filter(v=>v.text!==text)};
  assert.equal(g.target(missing,o.timestamp,p,r),null,text);
 }
 for(const change of [v=>({...v,y:150}),v=>({...v,text:'Unknown, Mondstadt'}),v=>({...v,x:NaN}),v=>({...v,width:undefined}),v=>({...v,height:undefined}),v=>({...v,width:310}),v=>({...v,height:50})]){
  const wrong={...o,ocr:o.ocr.map(v=>v.text==='Starfell Lake, Mondstadt'?change(v):v)};
  assert.equal(g.target(wrong,o.timestamp,p,r),null);
 }
 const duplicate={...o,ocr:o.ocr.concat(o.ocr.find(v=>v.text==='Starfell Lake, Mondstadt'))};
 assert.equal(g.target(duplicate,o.timestamp,p,r),null);
 assert.equal(g.target(o,o.timestamp,{...p,reviewed:false},r),null);
 assert.equal(g.target(o,o.timestamp,{...p,consumed:true},r),null);
});
