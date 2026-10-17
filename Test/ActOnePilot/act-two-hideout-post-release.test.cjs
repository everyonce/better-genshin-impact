const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js');
test('untracked regional low post release requires reviewed landing, full health and fresh climb controls',()=>{
 const o=require('./act-two-hideout-post-release.fixture.json'),m={...require('./act-two-hideout-blossom-map.fixture.json'),timestamp:o.timestamp,session:o.session};
 const ready=(x=o,landing=true,map=m,now=o.timestamp)=>g.ready(x,o,now,o.session,true,true,false,true,map,false,false,false,landing);
 assert(ready());assert(!ready(o,false));assert(!ready(o,true,null));assert(!ready(o,true,m,o.timestamp+1001));
 for(const hud of [{health:{current:4014,max:4015}},{climbing:false},{enemyBars:[{x:800,y:300,width:100,height:8}]},{bigMap:true},{journal:true},{choice:true}])assert(!ready({...o,hud:{...o.hud,...hud}}));
 assert(!ready({...o,ocr:o.ocr.filter(r=>r.text!=='X')}));assert(!ready({...o,session:'other'}));
});
