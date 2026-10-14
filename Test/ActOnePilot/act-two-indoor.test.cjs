const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const o=JSON.parse(fs.readFileSync(__dirname+'/act-two-hq-interior.fixture.json','utf8'));
test('indoor movement uses fresh HUD evidence without indoor GPS',()=>{
 assert.equal(bgi.indoorSafe({...o,map:null},o.timestamp,o.session),true);
 assert.equal(bgi.indoorSafe(o,o.timestamp+1001,o.session),false);
 assert.equal(bgi.indoorSafe(o,o.timestamp-1,o.session),false);
 assert.equal(bgi.indoorSafe(o,o.timestamp,'other'),false);
 for(const patch of [{climbing:true},{groundControls:false},{dialogueReady:true},{enemyBars:[{}]},{health:{current:1500,max:1700}},{objectives:['Unrelated']}]){
  const copy={...o,hud:{...o.hud,...patch},ocr:o.ocr.filter(r=>r.text!=='Talk to Kaeya')};
  assert.equal(bgi.indoorSafe(copy,o.timestamp,o.session),false);
 }
});
test('exact full-frame quest OCR can corroborate an overlapping cropped objective',()=>{
 const f=JSON.parse(fs.readFileSync(__dirname+'/act-two-hq-objective-ocr.fixture.json','utf8'));
 assert.equal(bgi.indoorSafe(f,f.timestamp,f.session),true);
});
