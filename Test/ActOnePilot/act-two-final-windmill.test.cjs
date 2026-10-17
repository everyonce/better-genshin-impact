const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-exam.js'),o=require('./act-two-final-windmill.fixture.json');
test('recorded final windmill flight extends only the verified airborne final-trial corridor',()=>{
 assert.equal(g.state(o,1000,o.session).kind,'airborne');
 for(const bad of [{...o,hud:{...o.hud,groundControls:true}},{...o,map:{...o.map,y:2200}},{...o,ocr:o.ocr.filter(r=>r.text!=='Space')},{...o,hud:{...o.hud,health:{current:1000,max:4015}}},{...o,ocr:o.ocr.map(r=>({...r,text:r.text.replace('60 second','180 second')}))}])assert.equal(g.state(bad,1000,o.session),null);
 assert.equal(g.state(o,2001,o.session),null);assert.equal(g.state(o,1000,'wrong-session'),null);
});
