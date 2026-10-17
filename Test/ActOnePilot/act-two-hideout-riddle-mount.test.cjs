const test=require('node:test'),assert=require('node:assert/strict');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),o=require('./act-two-hideout-riddle-mount.fixture.json');
test('recorded exact windmill door permits bounded mount context only',()=>{
 assert(g.ready(o,o,o.timestamp,o.session,false,false,false));
 for(const mutate of [v=>v.hud.health.current--,v=>v.hud.enemyBars.push({x:500,y:300,width:50}),v=>v.hud.objectives=['different quest'],v=>v.map.x-=2,v=>v.hud.groundControls=false]){const v=structuredClone(o);mutate(v);assert.equal(g.ready(v,v,v.timestamp,v.session,false,false,false),false);}
});
test('windmill climb requires positive same-frame stamina and climbing controls; release stays refused',()=>{
 const v=structuredClone(o);v.hud.climbing=true;v.hud.groundControls=false;v.ocr.push({text:'X',x:1600,y:1020},{text:'Space',x:1750,y:1020});v.hud.climbStamina={source:'same-frame-yellow-arc',pixels:300,boxes:[{x:60,y:30,width:15,height:70}]};
 assert(g.ready(v,v,v.timestamp,v.session,true,false,false));
 assert.equal(g.ready(v,v,v.timestamp,v.session,true,false,false,true),false);
 for(const mutate of [v=>v.hud.climbStamina=null,v=>v.hud.climbStamina.pixels=179,v=>v.hud.climbStamina.boxes[0].height=20,v=>v.hud.climbing=false,v=>v.hud.health.current--,v=>v.map.x-=20]){const c=structuredClone(v);mutate(c);assert.equal(g.ready(c,c,c.timestamp,c.session,true,false,false),false);}
});
test('recorded low mount permits only exact short stamina probe when arc is absent',()=>{
 const m=require('./act-two-hideout-riddle-mounted.fixture.json');
 assert.equal(g.ready(m,m,m.timestamp,m.session,true,false,false),false);
 assert(g.ready(m,m,m.timestamp,m.session,true,false,false,false,undefined,false,false,true));
 for(const mutate of [v=>v.map.x+=1,v=>v.hud.objectives=['Look for the location in the riddle','Higher 20m'],v=>v.hud.climbStamina.rawPixels=50,v=>v.hud.health.current--]){const v=structuredClone(m);mutate(v);assert.equal(g.ready(v,v,v.timestamp,v.session,true,false,false,false,undefined,false,false,true),false);}
});
test('recorded settled mount normalizes whitespace without weakening numeric stamina checks',()=>{
 const v=require('./act-two-hideout-riddle-settled.fixture.json');
 assert(g.ready(v,v,v.timestamp,v.session,true,false,false,false,undefined,false,false,true));
 assert.equal(g.ready(v,v,v.timestamp,v.session,true,false,false),false);
});
test('reviewed stone corridor keeps a visible 32px reserve and refuses unrelated positions or releases',()=>{
 const v=require('./act-two-hideout-riddle-reserve.fixture.json');
 assert(g.ready(v,v,v.timestamp,v.session,true,false,false));
 for(const mutate of [v=>v.hud.climbStamina.boxes[0].height=31,v=>v.hud.climbStamina.pixels=179,v=>v.map.x-=2,v=>v.hud.objectives=['Look for the location in the riddle','Higher 20m'],v=>v.hud.health.current--]){const c=structuredClone(v);mutate(c);assert.equal(g.ready(c,c,c.timestamp,c.session,true,false,false),false);}
 assert.equal(g.ready(v,v,v.timestamp,v.session,true,false,false,true),false);
});
test('fresh reviewed balcony permits only exact release position and elevation',()=>{
 const v=require('./act-two-hideout-riddle-landing.fixture.json');
 const allow=v=>g.ready(v,v,v.timestamp,v.session,true,false,false,true,undefined,false,false,false,true);
 assert(allow(v));
 assert.equal(g.ready(v,v,v.timestamp,v.session,true,false,false,true),false);
 for(const mutate of [v=>v.map.x+=.5,v=>v.hud.objectives=['Look for the location in the riddle','Higher 14m'],v=>v.hud.health.current--,v=>v.hud.enemyBars.push({x:500})]){const c=structuredClone(v);mutate(c);assert.equal(allow(c),false);}
});
test('verified balcony ground requires the recorded elevation and ground controls',()=>{
 const v=require('./act-two-hideout-riddle-ground.fixture.json');
 assert(g.ready(v,v,v.timestamp,v.session,false,false,false));
 for(const mutate of [v=>v.hud.groundControls=false,v=>v.map.x+=20,v=>v.hud.objectives=['Look for the location in the riddle','Higher 25m']]){const c=structuredClone(v);mutate(c);assert.equal(g.ready(c,c,c.timestamp,c.session,false,false,false),false);}
});
