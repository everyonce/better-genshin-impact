const test=require('node:test'),assert=require('node:assert/strict'),g=require(process.env.ACT_TWO_FIELD_MODULE||'../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),o=require('./act-two-southwest-clipped-map.fixture.json');
test('actual southwest map uses three consistent anchors when Whispering Woods is above viewport',()=>{
 assert(g.regionalMap(o,o.timestamp,o.session));
 for(const label of ['Mondstadt','Windrise','Elemental Trial'])assert(!g.regionalMap({...o,ocr:o.ocr.filter(r=>r.text!==label)},o.timestamp,o.session));
 assert(!g.regionalMap({...o,ocr:o.ocr.map(r=>r.text==='Windrise'?{...r,x:r.x+15}:r)},o.timestamp,o.session));
 assert(!g.regionalMap({...o,ocr:o.ocr.filter(r=>!r.text.includes('693306810'))},o.timestamp,o.session));
 assert(!g.regionalMap(o,o.timestamp+600001,o.session));assert(!g.regionalMap(o,o.timestamp,'wrong'));
});
