const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),o=require('./act-two-hq-waypoint.fixture.json');
const ready=x=>g.ready(x,x,x.timestamp,x.session,false,false,false);
test('tower sill permits exact selected waypoint interaction',()=>{assert.equal(ready(o),true);assert.equal(g.interaction(o,'Teleport Waypoint'),true);});
test('tower sill rejects missing interaction, changed height, location and enemies',()=>{for(const mutate of [x=>x.ocr=x.ocr.filter(r=>r.text!=='Teleport Waypoint'),x=>x.hud.objectives=['Follow the route and fly to the finish line in time','Lower 30m'],x=>x.map.x+=2,x=>x.hud.enemyBars=[{}]]){const x=structuredClone(o);mutate(x);assert.equal(ready(x),false);}});
