const test=require('node:test'),assert=require('node:assert/strict'),g=require(process.env.ACT_TWO_FIELD_MODULE||'../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),o=require('./act-two-windwail-vendor-map.fixture.json');
test('recorded vendor map accepts merged whitespace and centered Mondstadt OCR box',()=>{
 assert(g.regionalMap(o,o.timestamp,o.session));
 assert(!g.regionalMap(o,o.timestamp+600001,o.session));
 assert(!g.regionalMap(o,o.timestamp,'another-session'));
 for(const text of ['Mondstadt','WhisperingWoods','Windrise'])assert(!g.regionalMap({...o,ocr:o.ocr.filter(r=>r.text!==text)},o.timestamp,o.session));
 for(const mutation of [{x:1000},{width:160},{height:60}])assert(!g.regionalMap({...o,ocr:o.ocr.map(r=>r.text==='Mondstadt'?{...r,...mutation}:r)},o.timestamp,o.session));
 assert(!g.regionalMap({...o,hud:{...o.hud,bigMap:false}},o.timestamp,o.session));
});

test('recorded next road map retains consistent centers despite taller OCR boxes',()=>{const q=require('./act-two-windwail-gap-map.fixture.json');assert(g.regionalMap(q,q.timestamp,q.session));assert(!g.regionalMap({...q,ocr:q.ocr.map(r=>r.text==='Whispering Woods'?{...r,y:r.y+20}:r)},q.timestamp,q.session));});

test('canopy recovery map retains all three label centers with8px wider OCR box',()=>{const q=require('./act-two-windwail-canopy-map.fixture.json');assert(g.regionalMap(q,q.timestamp,q.session));assert(!g.regionalMap({...q,ocr:q.ocr.map(r=>r.text==='Whispering Woods'?{...r,width:r.width+20}:r)},q.timestamp,q.session));});
