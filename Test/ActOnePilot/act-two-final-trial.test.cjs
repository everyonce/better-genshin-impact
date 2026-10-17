const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-final-trial.js');
const start=require('./act-two-final-city-start.fixture.json'),grip=require('./act-two-final-city-climb.fixture.json');
function harness(patch={}){
 let now=start.timestamp,reads=0,keys=[],looks=[],released=0,courses=0,launches=0;
 const ground={...start,map:{...start.map,cameraAngle:13}},top={...start,map:{map:'Teyvat',x:-777.04102,y:2241.99414,cameraAngle:13}};
 const frames=[ground,grip,top,{session:start.session,ocr:[],hud:{world:false,dialogueReady:true,health:null},map:null}];
 const api={now:()=>now,check(){},sleep:async ms=>{now+=ms;},release:()=>released++,look:async(...x)=>looks.push(x),key:async(k,ms)=>{keys.push([k,ms]);now+=ms;},observe:async()=>{const o=frames[Math.min(reads++,frames.length-1)];return {...o,timestamp:now};},launch:async()=>{launches++;return {opened:true,samples:[{timer:49}]};},course:async()=>{courses++;return {reason:'Flight or health proof lost'};},...patch};
 api.wallJump=async()=>{keys.push(['heldForwardJump',800]);now+=860;};
 return {api,keys,looks,run:o=>g.run(o||start,api),stats:()=>({released,courses,launches})};
}
test('one local operation derives heading, verifies grip and mantle, deploys and records phase transition',async()=>{
 const h=harness(),r=await h.run();assert.equal(r.reason,'Final trial phase changed');assert.equal(r.wallJumps,1);assert.equal(r.climbHolds,1);assert.equal(h.stats().launches,1);assert.equal(h.stats().courses,1);assert.equal(r.stages.find(s=>s.name==='deployment').timer,49);assert.equal(h.looks[0][0],180);assert.deepEqual(h.keys,[['heldForwardJump',800],['VK_W',600]]);assert(h.stats().released>0);
});
test('late timer, wrong geometry, damage and wrong session stop before any input',async()=>{
 for(const change of [{map:{...start.map,x:-770}},{hud:{...start.hud,health:{current:1000,max:4015}}},{ocr:start.ocr.map(r=>r.text==='00:58'?{...r,text:'00:12'}:r)}]){
  const h=harness(),r=await h.run({...start,...change});assert.equal(h.keys.length,0);assert.equal(h.stats().launches,0);assert.equal(r.status,'stopped');
 }
});
test('unproven deployment never starts a course and always releases inputs',async()=>{
 const h=harness({launch:async()=>({opened:false,samples:[]})}),r=await h.run();assert.match(r.reason,/not positively verified/);assert.equal(h.stats().courses,0);assert(h.stats().released>0);
});
test('known tower-side ground is insufficient to authorize the original takeoff point',async()=>{
 let reads=0;const h=harness({observe:async()=>{const o=reads++===0?start:reads===2?grip:{...start,map:{...start.map,x:-777.36,y:2240.94}};return o;}});const r=await h.run();assert.equal(h.stats().launches,0);assert.match(r.reason,/clearance|Fresh|Climb/);
});
test('reviewed top resumes directly, but nearby unreviewed geometry cannot launch',async()=>{
 const top={...start,map:{map:'Teyvat',x:-777.990234375,y:2240.7216796875,cameraAngle:351.5}};
 const h=harness({resume:true,observe:async()=>({...start,timestamp:start.timestamp+180,hud:{dialogueReady:true},ocr:[]})});
 const r=await h.run(top);assert.equal(h.stats().launches,1);assert.equal(r.wallJumps,0);assert.equal(r.climbHolds,0);assert.equal(r.stages[0].name,'resumeTop');
 const bad=harness({resume:true});await bad.run({...top,map:{...top.map,x:top.map.x+1}});assert.equal(bad.stats().launches,0);
});
test('runtime Space pulse preserves held forward and releases Space even on focus loss',async()=>{
 const fs=require('fs'),text=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8').replace(/\r\n/g,'\n');
 const chunk=text.slice(text.indexOf('            function fastApi(markers)'),text.indexOf('            try{\n                var outcome=await trial.run'));
 let held=new Set(['VK_W']),checks=0,fail=false;const events=[],lastObservation={frameId:1};
 const checked=()=>{if(fail&&++checks>1)throw Error('focus lost');},sleep=async()=>{},stopKeys=()=>held.clear(),forwardDown=()=>held.add('VK_W'),look=()=>{},sample=()=>{},keyDown=k=>held.add(k),keyUp=k=>held.delete(k);
 const factory=eval('('+chunk.trim().replace(/^function fastApi/,'function')+')');
 await factory(false).pressSpace();assert.deepEqual([...held],['VK_W']);assert.equal(events[0].key,'VK_SPACE');
 fail=true;await assert.rejects(factory(false).pressSpace(),/focus lost/);assert.deepEqual([...held],['VK_W']);
});

test('prepared parapet inspection stops before launch and all courses',async()=>{
 const h=harness({prepareOnly:true}),r=await h.run();assert.match(r.reason,/inspect standing or falling/);assert.equal(r.wallJumps,1);assert.equal(r.climbHolds,1);assert.equal(h.stats().launches,0);assert.equal(h.stats().courses,0);assert(h.stats().released>0);
});

test('runtime start-resume permit is exact, consumed once and only adds an inspection stop',()=>{
 const fs=require('fs'),source=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8'),code=source.slice(source.indexOf('        takeFinalTrialPlan:function'),source.indexOf('        runActTwoFinalTrial:'));
 const request={step:'actTwoFinalTrial',session:start.session,expectedFrameId:77,id:'test-request'},events=[];
 let plan={session:start.session,frameId:77,createdAt:start.timestamp,enabled:true,resumeStart:true,inspectBeforeLaunch:true};
 const file={readTextSync:n=>n==='act-two-final-trial.js'?fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-final-trial.js'),'utf8'):JSON.stringify(plan),writeTextSync:(n,s)=>{plan=JSON.parse(s);return true;}};
 const api=new Function('file','request','events','Date','return ({'+code+'});')(file,request,events,{now:()=>start.timestamp});
 assert.equal(api.takeFinalTrialPlan(start,true),'start');assert.equal(request.finalTrialPrepareOnly,true);assert.equal(plan.requestId,'test-request');assert.equal(api.takeFinalTrialPlan(start,true),false);
 plan={session:start.session,frameId:77,createdAt:start.timestamp,enabled:true,resumeStart:true};assert.throws(()=>api.takeFinalTrialPlan({...start,map:{...start.map,x:start.map.x+2}},true),/exact start/);
});

test('reviewed outer-edge step releases before the one-press recovery adapter',async()=>{
 const top={...start,map:{map:'Teyvat',x:-777.990234375,y:2240.9111328125,cameraAngle:10}};let keys=[],released=0,launches=0;
 const h=harness({resume:true,stepOff:true,key:async(k,ms)=>keys.push([k,ms]),release:()=>released++,launch:async()=>{assert(released>0);launches++;return {opened:false};}});const r=await h.run(top);assert.deepEqual(keys,[['VK_W',300]]);assert.equal(launches,1);assert.equal(r.stepOff,true);
 const bad=harness({resume:true,stepOff:true});await bad.run({...top,map:{...top.map,x:top.map.x+3}});assert.equal(bad.stats().launches,0);
});
