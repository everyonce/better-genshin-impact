const test=require('node:test'),assert=require('node:assert/strict');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),o=require('./act-two-hideout-riddle-camera.fixture.json');
test('recorded riddle city surface permits camera only with original safeguards',()=>{
 assert(g.ready(o,o,o.timestamp,o.session,false,false,true));
 assert.equal(g.ready(o,o,o.timestamp,o.session,false,false,false),false);
 for(const mutate of [v=>v.hud.health.current--,v=>v.hud.enemyBars.push({x:500,y:300,width:50}),v=>v.hud.objectives=['different quest'],v=>v.map.x=-1000,v=>v.hud.climbing=true,v=>v.hud.world=false,v=>v.hud.groundControls=false]){const v=structuredClone(o);mutate(v);assert.equal(g.ready(v,v,v.timestamp,v.session,false,false,true),false);}
});
