const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-mage.js');
test('mage burst needs close level13 enemy and selected healthy Amber',()=>{
 const o={session:'s',timestamp:1000,map:{map:'Teyvat',x:-1562.52,y:2233.04},hud:{world:true,groundControls:true,health:{current:1186,max:1186},enemyBarDiagnostic:{level:13},enemyBars:[{}]},ocr:[{text:'Amber',x:1662,y:350},{text:'Lv. 13',x:300,y:390}]};
 assert.equal(g.burst(o,1000,'s'),true);
 for(const b of [{timestamp:-2000},{session:'x'},{map:{...o.map,x:-1540}},{hud:{...o.hud,enemyBars:[]}},{hud:{...o.hud,health:{current:711,max:1186}}},{ocr:o.ocr.slice(1)},{hud:{...o.hud,enemyBarDiagnostic:{level:'any'}}}])assert.equal(g.burst({...o,...b},1000,'s'),false);
});
test('Amber field profile stays near the witnessed mage and requires selected party label',()=>{
 const f=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),o={session:'s',timestamp:1000,map:{map:'Teyvat',x:-1540,y:2240},hud:{world:true,groundControls:true,health:{current:1186,max:1186},enemyBarDiagnostic:{},enemyBars:[],objectives:[]},ocr:[{text:'Amber',x:1662,y:350},{text:'R',x:1600,y:1030},{text:'UID:693306810',x:1680,y:1048}]};
 assert.equal(f.ready(o,o,1000,'s'),true);
 assert.equal(f.ready({...o,ocr:o.ocr.filter(r=>r.text!=='Amber')},o,1000,'s'),false);
 const far={...o,map:{...o.map,x:-1400}};assert.equal(f.ready(far,far,1000,'s'),false);
});
test('mage preparation selects only observed Amber slot from healthy safe approach',()=>{
 const o={session:'s',timestamp:1000,map:{map:'Teyvat',x:-1550,y:2250},hud:{world:true,groundControls:true,health:{current:2313,max:2313},enemyBarDiagnostic:{},enemyBars:[],objectives:[]},ocr:[{text:'Amber',x:1700,y:350},{text:'2',x:1860,y:350}]};
 assert.equal(g.preparation(o,1000,'s'),true);
 for(const b of [{session:'x'},{timestamp:-2000},{map:{...o.map,x:-1300}},{hud:{...o.hud,enemyBars:[{}]}},{hud:{...o.hud,climbing:true}},{hud:{...o.hud,health:{current:1000,max:2313}}},{ocr:o.ocr.slice(1)}])assert.equal(g.preparation({...o,...b},1000,'s'),false);
});


test('mage follow-up switches only the witnessed Amber to observed Kaeya slot',()=>{
 const o={session:'s',timestamp:1000,map:{map:'Teyvat',x:-1563,y:2233},hud:{world:true,groundControls:true,health:{current:984,max:1186}},ocr:[{text:'Amber',x:1662,y:350},{text:'Kaeya',x:1688,y:440},{text:'3',x:1852,y:441}]};
 assert.equal(g.switchToKaeya(o,1000,'s'),true);
 for(const b of [{session:'x'},{timestamp:-1},{map:{...o.map,x:-1600}},{hud:{...o.hud,climbing:true}},{hud:{...o.hud,health:{current:0,max:1186}}},{ocr:o.ocr.slice(0,2)}])assert.equal(g.switchToKaeya({...o,...b},1000,'s'),false);
});
test('Amber food modal is recognized as a safe boundary without authorizing Kaeya feeding',()=>{
 const b=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),o={timestamp:1000,map:null,hud:{world:false},ocr:[{text:'Food',x:140,y:30},{text:'Sweet Madame',x:1350,y:140},{text:'Amber',x:890,y:270},{text:'Amount to use',x:640,y:620},{text:'Confirm',x:1120,y:750},{text:'Cancel',x:700,y:750}]};
 assert.equal(b.knownSafeFoodBoundary(o,1000),true);
 assert.equal(b.wolfFeedKaeyaTarget(o,1000),null);
 assert.equal(b.knownSafeFoodBoundary({...o,ocr:o.ocr.filter(r=>r.text!=='Amount to use')},1000),false);
});
