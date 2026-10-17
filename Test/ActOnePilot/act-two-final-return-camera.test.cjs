const test=require('node:test'),assert=require('node:assert/strict');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js');
const o=require('./act-two-final-return-camera.fixture.json');
test('final roof return camera stays in city and current quest and never authorizes movement',()=>{
 const ready=(f,c=true)=>g.ready(f,o,f.timestamp,o.session,false,false,c);
 assert.equal(ready(o),true);assert.equal(ready(o,false),false);
 const hq={...o,map:{...o.map,x:-747,y:2268}};assert.equal(g.ready(hq,hq,hq.timestamp,hq.session,false,false,true),true);assert.equal(ready(hq),false);
 for(const f of [{...o,hud:{...o.hud,enemyBars:[{}]}},{...o,map:{...o.map,x:-1000}},{...o,hud:{...o.hud,health:{current:3000,max:4015}}},{...o,hud:{...o.hud,objectives:['Other quest']}},{...o,hud:{...o.hud,climbing:true,groundControls:false}}])assert.equal(ready(f),false);
});
