const test=require('node:test'),assert=require('node:assert/strict');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js');
const f=require('./act-two-south-road-field.fixture.json');
test('recorded southern exam road allows grounded recovery while retaining boundary and health guards',()=>{
 assert.equal(g.ready(f,f,f.timestamp,f.session),true);
 for(const patch of [{map:{...f.map,x:-1299}},{map:{...f.map,y:1449}},{hud:{...f.hud,climbing:true,groundControls:false}},{hud:{...f.hud,health:{current:2000,max:4015}}},{hud:{...f.hud,objectives:['Other quest']}}])assert.equal(g.ready({...f,...patch},f,f.timestamp,f.session),false);
 assert.equal(g.ready(f,f,f.timestamp+1001,f.session),false);
 assert.equal(g.ready(f,f,f.timestamp,'other'),false);
 assert.equal(g.ready(f,f,f.timestamp,f.session,true),false);
});
test('recorded cliff-base release permits only reviewed location health and no enemies',()=>{
 const c=require('./act-two-south-road-release.fixture.json');
 assert.equal(g.ready(c,c,c.timestamp,c.session,true,false,false,true),true);
 assert.equal(g.ready(c,c,c.timestamp,c.session,true),false);
 for(const patch of [{map:{...c.map,x:-1380}},{hud:{...c.hud,health:{current:3400,max:4015}}},{hud:{...c.hud,enemyBars:[{}]}},{hud:{...c.hud,objectives:['Other quest']}}])assert.equal(g.ready({...c,...patch},c,c.timestamp,c.session,true,false,false,true),false);
});
