const test=require('node:test'),assert=require('node:assert/strict'),b=require(process.env.BGI_MODULE||'../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),o=require('./act-two-wind-seal-missing-level.fixture.json'),good=require('./act-two-wind-seal-eye.fixture.json');
test('same-frame level crop is requested only for the exact Eye header and missing level',()=>{
 assert(b.windSealLevelCropNeeded(o.ocr));assert(!b.windSealLevelCropNeeded(good.ocr));
 assert(!b.windSealLevelCropNeeded(o.ocr.filter(r=>r.text!=='Eye of the Storm')));
 assert(!b.windSealLevelCropNeeded(o.ocr.concat({text:'Lv.10',x:700,y:75,width:45,height:17})));
});
test('synthetic crop merge maps coordinates once and never invents an absent level',()=>{
 const r=b.mergeWindSealLevel(o.ocr,[{text:'Lv.9',x:60,y:30,width:135,height:51}]);
 const found=r.find(r=>r.text==='Lv.9');assert.deepEqual(found,{text:'Lv.9',x:700,y:75,width:45,height:17});
 assert(!b.mergeWindSealLevel(o.ocr,[]).some(r=>r.text==='Lv.9'));
 assert(!b.mergeWindSealLevel(o.ocr,[{text:'noise',x:60,y:30,width:135,height:51}]).some(r=>r.text==='Lv.9'));
});

test('recorded full Amber requires exact Eye identity before additional same-frame party OCR',()=>{const a=require('./act-two-wind-seal-amber.fixture.json');assert(b.windSealAmberGround(a.ocr,a.hud));for(const patch of [{health:{current:1473,max:1733}},{climbing:true},{groundControls:false}])assert(!b.windSealAmberGround(a.ocr,{...a.hud,...patch}));assert(!b.windSealAmberGround(a.ocr.filter(r=>r.text!=='Eye of the Storm'),a.hud));});
