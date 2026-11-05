const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),fs=require('node:fs'),vm=require('node:vm');
const w={session:'s',timestamp:1000,hud:{world:true,health:{current:1581,max:2313},objectives:['Check the suspicious location and eliminate any threats','(0/3)']}};
test('field diagnostics distinguish definitive health failure from stale or changed objective',()=>{
 assert.equal(g.failureReason(w,w,1000,'s'),'health_below_minimum');
 assert.equal(g.failureReason(w,w,2001,'s'),'stale_frame');
 assert.equal(g.failureReason(w,w,1000,'other'),'session_mismatch');
 const healthy={...w,hud:{...w.hud,health:{current:2313,max:2313}}};
 assert.equal(g.failureReason({...healthy,hud:{...healthy.hud,objectives:['Talk to Cyrus']}},w,1000,'s'),'objective_mismatch');
 assert.equal(g.failureReason(healthy,w,1000,'s'),'field_guards_not_met');
});
test('definitive low health aborts the resume polling loop immediately',async()=>{
 const source=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8');
 const body=source.slice(source.indexOf('runActTwoField: async'),source.indexOf('runActTwoWindriseSlime: async'));
 const loop=body.match(/for\(var poll=0;poll<5;poll\+\+\)\{.*\}/)[0];
 const fieldReady=body.match(/function fieldReady\(o\)\{[^\n]+/)[0];
 // Run the ordinary field branch in the adapter's own scope, including its production entry-settled helper.
 const run=vm.runInNewContext(source+`\n(async function(guard,witness,request,p,sleep,observe,Date,release){
   let current;
   const eyeDefense=null;
   ${fieldReady}
   ${loop}
 })`);
 let reads=0,releases=0;
 await assert.rejects(run(g,w,{session:'s'},{},async()=>{},async()=>{reads++;return w;},{now:()=>1000},()=>releases++),/health_below_minimum/);
 assert.equal(reads,1);
 assert.equal(releases,1);
});
