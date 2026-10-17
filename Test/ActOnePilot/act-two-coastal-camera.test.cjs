const test=require('node:test'),assert=require('node:assert/strict');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),o=require('./act-two-coastal-camera.fixture.json');
const ready=(v,camera=true,now=o.timestamp,session=o.session)=>g.ready(v,o,now,session,false,false,camera);
test('recorded coastal ground allows camera only, preserving movement rejection',()=>{assert(ready(o));assert(!ready(o,false));});
test('coastal camera rejects stale, identity, damage, threats, climbing and out-of-corridor state',()=>{for(const v of [{...o,timestamp:o.timestamp-1001},{...o,session:'wrong'},{...o,map:{...o.map,x:-1661}},{...o,map:{...o.map,y:2599}},{...o,hud:{...o.hud,health:{current:4014,max:4015}}},{...o,hud:{...o.hud,enemyBars:[{}]}},{...o,hud:{...o.hud,climbing:true}},{...o,hud:{...o.hud,objectives:['unrelated quest']}}])assert(!ready(v));});
