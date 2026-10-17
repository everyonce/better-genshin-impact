const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),o=require('./act-two-hq-climb.fixture.json');
const ready=(f,probe=false)=>g.ready(f,f,f.timestamp,f.session,true,false,false,false,null,false,false,probe,false);
test('HQ low wall first pulse requires exact final-stage witness; further climbing requires visible stamina',()=>{
 assert.equal(ready(o,true),true);assert.equal(ready(o),false);
 const enough={...o,hud:{...o.hud,climbStamina:{source:'same-frame-yellow-arc',pixels:400,boxes:[{y:10,height:70}]}}};
 assert.equal(ready(enough),true);
 for(const f of [{...o,map:{...o.map,x:o.map.x+3}},{...o,hud:{...o.hud,enemyBars:[{}]}},{...o,hud:{...o.hud,health:{max:4015,current:3000}}},{...o,hud:{...o.hud,objectives:['Other quest']}}])assert.equal(ready(f,true),false);
 for(const stamina of [{source:'unknown',pixels:400,boxes:[{y:0,height:70}]},{source:'same-frame-yellow-arc',pixels:170,boxes:[{y:0,height:70}]},{source:'same-frame-yellow-arc',pixels:400,boxes:[]}])assert.equal(ready({...enough,hud:{...enough.hud,climbStamina:stamina}}),false);
});

test('standing HQ ledge can approach the visible wall only at its reviewed anchor',()=>{const f=require('./act-two-hq-ledge.fixture.json');assert.equal(g.ready(f,f,f.timestamp,f.session),true);assert.equal(g.ready({...f,map:{...f.map,x:f.map.x+1}},f,f.timestamp,f.session),false);assert.equal(g.ready({...f,hud:{...f.hud,enemyBars:[{}]}},f,f.timestamp,f.session),false);});
