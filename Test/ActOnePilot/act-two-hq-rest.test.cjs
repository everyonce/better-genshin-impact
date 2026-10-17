const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),o=require('./act-two-hq-rest.fixture.json');
const ready=(f,reviewed=true)=>g.ready(f,f,f.timestamp,f.session,true,false,false,true,null,false,false,false,reviewed);
test('HQ visible second brace release requires exact reviewed landing, full health and height cue',()=>{
 assert.equal(ready(o),true);assert.equal(ready(o,false),false);
 for(const f of [{...o,map:{...o.map,x:o.map.x+1}},{...o,hud:{...o.hud,enemyBars:[{}]}},{...o,hud:{...o.hud,health:{current:4000,max:4015}}},{...o,hud:{...o.hud,objectives:['Follow the route and fly to the finish line in time','Higher 30m']}}])assert.equal(ready(f),false);
});
test('settled second brace allows guarded regrip only at its matching height and location',()=>{const f=require('./act-two-hq-rested.fixture.json');assert.equal(g.ready(f,f,f.timestamp,f.session),true);assert.equal(g.ready({...f,hud:{...f.hud,objectives:['Follow the route and fly to the finish line in time','Higher 25m']}},f,f.timestamp,f.session),false);});
