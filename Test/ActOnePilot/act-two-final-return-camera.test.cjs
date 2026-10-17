const test=require('node:test'),assert=require('node:assert/strict');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js');
const o=require('./act-two-final-return-camera.fixture.json');
test('final roof return camera stays at witnessed plaza and never authorizes movement',()=>{
 const ready=(f,c=true)=>g.ready(f,o,f.timestamp,o.session,false,false,c);
 assert.equal(ready(o),true);assert.equal(ready(o,false),false);
 for(const f of [{...o,map:{...o.map,x:-770}},{...o,hud:{...o.hud,health:{current:3000,max:4015}}},{...o,hud:{...o.hud,objectives:['Other quest']}},{...o,hud:{...o.hud,climbing:true,groundControls:false}}])assert.equal(ready(f),false);
});
