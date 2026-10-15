const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
// Replace account-specific fixture constants with a synthetic identity in this isolated test module.
const source=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),'utf8').replace(/\b\d{9}\b/g,'123456789');
const sandbox={module:{exports:{}}};vm.runInNewContext(source,sandbox);const g=sandbox.module.exports;
const bar={x:960,y:450,width:64,height:6,rectangularity:0.95};
const base={session:'s',timestamp:1000,frameId:1,map:{map:'Teyvat',x:-1168,y:1938},ocr:[{text:'UID: 123456789',x:1680,y:1050}],hud:{world:true,groundControls:true,health:{current:2263,max:2313},enemyBars:[bar],enemyBarDiagnostic:{level:4},objectives:[]}};
const plan={reviewed:true,session:'s',frameId:2,witnessFrameId:1,createdAt:1000,mode:'combat',enemyLevel:4,actions:[],singleTargetDiagnostic:true,targetAnchor:bar};
async function simulate(initial=base,next=()=>initial){
 let now=1000,frame=initial.frameId,release=0,reads=0;const inputs=[];
 const api={now:()=>now,checkStop:()=>{},sleep:async n=>now+=n,key:async(key,ms)=>{inputs.push({key,ms});now+=ms;},action:async a=>inputs.push(a),release:async()=>release++};
 const result=await g.run(initial,initial,plan,api,async()=>{now+=100;reads++;return {...next(reads),timestamp:now,frameId:++frame};});
 return {result,inputs,release,reads};
}
test('diagnostic plan is opt-in exact Lv4 with bounded anchor and no supplied actions',()=>{
 const request={session:'s',expectedFrameId:2};assert.equal(g.plan(plan,request,1000),true);
 for(const patch of [{enemyLevel:'any'},{enemyLevel:5},{mode:'actions'},{singleTargetDiagnostic:'true'},{targetAnchor:null},{targetAnchor:{...bar,x:1800}},{visualPositionReviewed:true},{actions:[{type:'key',key:'VK_W',ms:400}]}])assert.equal(g.plan({...plan,...patch},request,1000),false);
});
test('out of range makes at most four 400ms approaches and no attack',async()=>{
 const distant={...base,hud:{...base.hud,enemyBars:[{...bar,height:5}]}};const r=await simulate(distant);
 assert.equal(r.inputs.length,4);assert.ok(r.inputs.every(a=>a.key==='VK_W'&&a.ms===400));assert.equal(r.result.attacks,0);assert.match(r.result.reason,/range bound/);assert.equal(r.release,1);
});
test('approach requires fresh close range before the one burst',async()=>{
 const distant={...base,hud:{...base.hud,enemyBars:[{...bar,height:5}]}};const r=await simulate(distant,()=>base);
 assert.deepEqual(r.inputs.map(a=>a.key),['VK_W','VK_LBUTTON','VK_LBUTTON','VK_LBUTTON']);assert.equal(r.reads,4);assert.equal(r.result.attacks,3);
});
test('no damage ends after one burst and retains before after observations',async()=>{
 const r=await simulate();assert.equal(r.result.attacks,3);assert.equal(r.reads,3);assert.equal(r.result.damageConfirmed,false);assert.equal(r.result.defeatConfirmed,false);assert.ok(r.result.beforeBurstFrameId<r.result.afterBurstFrameId);assert.match(r.result.reason,/damage unconfirmed/);assert.equal(r.release,1);
});
test('exact-level detector output has geometry without optional any-level rectangularity',async()=>{
 const exactBar={x:960,y:444,width:63,height:6};
 const exact={...base,hud:{...base.hud,enemyBars:[exactBar]}};
 const r=await simulate(exact);assert.equal(r.result.attacks,3);assert.equal(r.result.damageConfirmed,false);
});
test('identity disappears after first strike: stop immediately and never claim defeat',async()=>{
 const r=await simulate(base,()=>({...base,hud:{...base.hud,enemyBars:[]}}));assert.equal(r.result.attacks,1);assert.equal(r.result.defeatConfirmed,false);assert.match(r.result.reason,/identity lost/);
});
test('changed level or multiple candidates cannot authorize another strike',async()=>{
 for(const hud of [{...base.hud,enemyBarDiagnostic:{level:5}},{...base.hud,enemyBars:[bar,{...bar,x:1050}]}]){
  const r=await simulate(base,()=>({...base,hud}));assert.equal(r.result.attacks,1);assert.match(r.result.reason,/identity/);
 }
});
test('any health loss stops before another strike or approach',async()=>{
 for(const height of [5,6]){const initial={...base,hud:{...base.hud,enemyBars:[{...bar,height}]}};const r=await simulate(initial,()=>({...initial,hud:{...initial.hud,health:{current:2262,max:2313}}}));assert.equal(r.inputs.length,1);assert.match(r.result.reason,/health/);assert.equal(r.release,1);}
});
test('range or spatial continuity loss stops before another strike',async()=>{
 for(const b of [{...bar,height:5},{...bar,x:1300}]){const r=await simulate(base,()=>({...base,hud:{...base.hud,enemyBars:[b]}}));assert.equal(r.result.attacks,1);assert.equal(r.result.damageConfirmed,false);}
});
test('red fill shrink with stable scale is retained but not asserted as damage',async()=>{
 const r=await simulate(base,()=>({...base,hud:{...base.hud,enemyBars:[{...bar,width:30}]}}));assert.equal(r.result.attacks,3);assert.equal(r.result.damageConfirmed,false);assert.equal(r.result.frames.at(-1).bars[0].width,30);
});
test('camera alignment is bounded and does not approach uncentered target',async()=>{
 const side={...base,hud:{...base.hud,enemyBars:[{...bar,x:1140,height:5}]}};const r=await simulate(side);assert.equal(r.inputs.length,2);assert.ok(r.inputs.every(a=>a.type==='look'&&Math.abs(a.dx)<=100));assert.equal(r.result.attacks,0);
});
test('focus/input exception releases keys and propagates to existing pause guardian',async()=>{
 let release=0;await assert.rejects(g.run(base,base,plan,{now:()=>1000,checkStop:()=>{},key:async()=>{throw Error('focus lost');},release:async()=>release++},async()=>base),/focus lost/);assert.equal(release,1);
});
