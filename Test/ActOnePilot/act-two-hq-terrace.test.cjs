const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),o=require('./act-two-hq-terrace.fixture.json');
const ready=x=>g.ready(x,x,x.timestamp,x.session,false,false,false);
test('reviewed terrace ridge permits bounded healthy ground step',()=>assert.equal(ready(o),true));
test('recorded terrace lip permits one reviewed continuation',()=>assert.equal(ready(require('./act-two-hq-terrace-lip.fixture.json')),true));
test('recorded low parapet permits short step onto adjoining stone floor',()=>assert.equal(ready(require('./act-two-hq-terrace-parapet.fixture.json')),true));
test('terrace step rejects changed height, location, health or enemies',()=>{for(const change of [x=>x.map.x+=2,x=>x.hud.objectives=['Follow the route and fly to the finish line in time','Lower 20m'],x=>x.hud.health.current=3000,x=>x.hud.enemyBars=[{}]]){const x=structuredClone(o);change(x);assert.equal(ready(x),false);}});
