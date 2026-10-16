const test=require('node:test'),assert=require('node:assert/strict');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),f=require('./act-two-climb-camera.fixture.json');
test('climbing camera inspection grants no movement ascent or drop permission',()=>{
 assert.equal(g.ready(f,f,f.timestamp,f.session,false,false,true),true);
 assert.equal(g.ready(f,f,f.timestamp,f.session),false);
 assert.equal(g.ready(f,f,f.timestamp,f.session,true),false);
 for(const patch of [{hud:{...f.hud,enemyBars:[{}]}},{hud:{...f.hud,health:{current:3000,max:4015}}},{hud:{...f.hud,objectives:['Other quest']}},{ocr:f.ocr.filter(r=>r.text!=='Space')}])assert.equal(g.ready({...f,...patch},f,f.timestamp,f.session,false,false,true),false);
 assert.equal(g.cameraPlan({mode:'actions',actions:[{type:'look',dx:0,dy:450}]}),true);
 assert.equal(g.cameraPlan({mode:'actions',actions:[{type:'key',key:'VK_W',ms:60}]}),false);
});
