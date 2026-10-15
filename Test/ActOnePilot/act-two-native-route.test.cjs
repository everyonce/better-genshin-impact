const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-native-route.js');
const p={reviewed:true,session:'s',frameId:4,witnessFrameId:3,createdAt:1000,timeoutMs:15000,route:{positions:[{x:-850,y:2280,type:'target',move_mode:'walk'}]}},r={session:'s',expectedFrameId:4};
test('native town plan forbids replay, stale plans, excessive time and route side effects',()=>{
 assert.equal(g.plan(p,r,1001),true);
 for(const bad of [{usedAt:1000},{session:'other'},{frameId:5},{createdAt:-120000},{timeoutMs:15001},{timeoutMs:0},{witnessFrameId:4}])assert.equal(g.plan({...p,...bad},r,1001),false);
 for(const bad of [{x:-900},{y:2400},{type:'teleport'},{move_mode:'fly'},{action:'combat_script'},{action_params:'w(999)'}])assert.equal(g.plan({...p,route:{positions:[{...p.route.positions[0],...bad}]}},r,1001),false);
});
test('focus loss cancels and drains native task before disposing token',async()=>{
 let cancel,finished=false,disposed=false,checks=0;
 const native={createCancellation:()=>({Token:{},Cancel:()=>cancel?.(),Dispose:()=>{assert.equal(finished,true);disposed=true;}}),run:()=>new Promise((resolve,reject)=>{cancel=()=>{finished=true;reject(Error('cancelled'));};})};
 await assert.rejects(g.run(native,()=>{if(++checks>1)throw Error('focus lost');},()=>new Promise(resolve=>setImmediate(resolve)),{},15000),/focus lost/);
 assert.equal(disposed,true);
});
test('native success also releases cancellation resources',async()=>{
 let disposed=false;
 await g.run({createCancellation:()=>({Token:{},Cancel(){},Dispose(){disposed=true;}}),run:async()=>{}},()=>{},()=>new Promise(resolve=>setImmediate(resolve)),{},1000);
 assert.equal(disposed,true);
});

test('Windrise route keeps explicit region and fresh full-health empty-threat checks',()=>{
 const o={session:'s',timestamp:1000,map:{map:'Teyvat',x:-1266,y:1934},hud:{world:true,groundControls:true,health:{current:2313,max:2313},enemyBarDiagnostic:{},enemyBars:[],objectives:['Solve the mystery (Go to Kaeya at the Knights of Favonius','HQ for a hint)']}};
 assert.equal(g.field(o,o,1001,'s','windrise'),true);
 assert.equal(g.field({...o,hud:{...o.hud,objectives:[]}},o,1001,'s','windrise'),true);
 assert.equal(g.field({...o,hud:{...o.hud,objectives:['Unrelated quest']}},o,1001,'s','windrise'),false);
 for(const h of [{health:{current:2312,max:2313}},{enemyBars:[{}]},{climbing:true},{groundControls:false}])assert.equal(g.field({...o,hud:{...o.hud,...h}},o,1001,'s','windrise'),false);
 assert.equal(g.field(o,o,2001,'s','windrise'),false);assert.equal(g.field(o,o,1001,'s',undefined),false);
 const route={positions:[{x:-1245,y:1934,type:'target',move_mode:'walk'}]};assert.equal(g.plan({...p,region:'windrise',route},r,1001),true);assert.equal(g.plan({...p,region:'unknown',route},r,1001),false);
});
test('Travel receipts reject impossible fog matches and label plausible distance as an estimate',()=>{
 const a={frameId:1,map:{map:'Teyvat',x:-1266,y:1934}},b={frameId:2,map:{map:'Teyvat',x:-1223,y:1934}};
 const good=g.telemetry(a,b,'windrise',8000,13000);assert.equal(good.minimapDisplacementEstimate,43);assert.equal(good.wallMs,13000);assert.equal(good.displacementVerified,false);
 const bad=g.telemetry(b,{frameId:3,map:{map:'Teyvat',x:979,y:-710}},'windrise',12142,17519);assert.equal(bad.minimapDisplacementEstimate,null);assert.equal(bad.positionEstimatePlausible,false);
});
