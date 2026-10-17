const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),map=require('./act-two-raptor-regional-map.fixture.json'),o=require('./act-two-raptor-marks-low-rock.fixture.json');
const ready=(q,landing=true,release=true)=>g.ready(q,o,1000,o.session,true,true,false,release,{...map,session:o.session},false,false,false,landing);
test('recorded low Raptor rock permits one reviewed release with over90percent Kaeya health',()=>{
 assert.equal(o.hud.world,false);assert.equal(o.hud.climbing,true);assert(ready(o));
 assert(!ready(o,false));assert(!ready(o,true,false));
 for(const hud of [{health:{current:3600,max:4015}},{enemyBars:[{x:500,y:400}]},{objectives:['Unrelated quest']},{auto:true},{dialogueReady:true},{climbing:false}])assert(!ready({...o,hud:{...o.hud,...hud}}));
 assert(!ready({...o,ocr:o.ocr.filter(r=>r.text!=='X')}));
 assert(!ready({...o,session:'wrong'}));
});
