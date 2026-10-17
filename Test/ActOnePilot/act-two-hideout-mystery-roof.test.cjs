const test=require('node:test'),assert=require('node:assert/strict');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),o=require('./act-two-hideout-mystery-roof.fixture.json');
test('fresh full-health mystery roof permits camera inspection only',()=>{
 assert(g.ready(o,o,o.timestamp,o.session,false,false,true));
 assert.equal(g.ready(o,o,o.timestamp,o.session,false,false,false),false);
 for(const mutate of [v=>v.hud.health.current--,v=>v.hud.enemyBars.push({x:500,y:300,width:50}),v=>v.hud.objectives=['different quest'],v=>v.map.x=-1000]){const v=structuredClone(o);mutate(v);assert.equal(g.ready(v,v,v.timestamp,v.session,false,false,true),false);}
});
test('recorded headquarters chest permits exact selected interaction and rejects uncertain surroundings',()=>{
 const chest=require('./act-two-hideout-hq-chest.fixture.json');assert(g.ready(chest,chest,chest.timestamp,chest.session,false,false,false));assert(g.interaction(chest,'Common Chest'));
 for(const mutate of [v=>v.ocr=v.ocr.filter(r=>r.text!=='F'),v=>v.map.x+=8,v=>v.hud.health.current--,v=>v.hud.enemyBars.push({x:500,y:300,width:50}),v=>v.hud.objectives=['different quest']]){const v=structuredClone(chest);mutate(v);assert.equal(g.ready(v,v,v.timestamp,v.session,false,false,false),false);}
});
