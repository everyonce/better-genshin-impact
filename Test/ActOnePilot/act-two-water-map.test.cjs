const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const s=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8');
const body=s.match(/function windriseMapEscape\(o\)\{([^\n]+)\}/)[1];
const check=new Function('o','request',body);
test('Windrise riverbank recovery permits only map opening with witnessed location and health',()=>{
 const o={map:{map:'Teyvat',x:-1243.71,y:1867.27},hud:{world:true,health:{current:1617,max:1829},objectives:[]}},r={step:'actTwoWorldMap'};
 assert.equal(check(o,r),true);
 for(const c of [{map:{...o.map,x:-1200}},{hud:{...o.hud,health:{current:10,max:1829}}},{hud:{...o.hud,choice:true}},{hud:{...o.hud,objectives:['Unrelated quest']}}])assert.equal(check({...o,...c},r),false);
 assert.equal(check(o,{step:'actTwoCharacter'}),false);
});
