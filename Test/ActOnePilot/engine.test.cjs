const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const engine = require(path.join(root, 'engine.js'));
const mission = require(path.join(root, 'mission.js'));
function world(x = 0, angle = 180) {
  return { map: { x, y: 0, map: 'Teyvat', cameraAngle: angle }, hud: { world: true, lowHealth: false, health: { current: 800, max: 987 }, healthPct: 800/987, objectives: ['Go to Mondstadt'] } };
}
function fixture(observations = [world()]) {
  let time = 100000, index = 0; const calls = [], writes = [];
  const api = { now: () => time, sleep: async ms => { time += ms; },
    beginMission: () => {}, events: () => calls, checkStop: () => {}, requireInputReady: () => {},
    observe: async (_, n) => ({ timestamp: time, screenshotPath: 'frame-'+n+'.png', ...observations[Math.min(index++, observations.length-1)] }),
    write: (p, v) => writes.push([p, JSON.parse(v)]), release: () => calls.push(['release']),
    keyPress: async key => calls.push(['key', key]), rotate: async dx => calls.push(['rotate', dx]), forward: async ms => { calls.push(['forward', ms]); time += ms; } };
  const runner = engine.create(api, { session:'a', enableInput:true });
  const request = (kind, args={}) => ({session:'a',id:'id-'+Math.random().toString(36).slice(2),createdAt:time,expectedFrameId:runner.getFrame(),mission:kind,...args});
  return { api, runner, request, calls, writes, advance: ms => time += ms };
}
const route = (x=10) => ({waypoints:[{map:'Teyvat',x,y:0}],deadlineMs:90000,objective:'Go to Mondstadt'});
test('actual OCR variants tolerate at most one character, without accepting different objectives',()=>{
  for(const text of ['Go toMondstadt','Go to Mondstad','GoftoMondstadt','Go to Mondstadi']) assert.equal(mission.objectiveMatches(text,'Go to Mondstadt'),true);
  for(const text of ['Go to Liyue','Enter the city','Go to Monsta','Mondstadt']) assert.equal(mission.objectiveMatches(text,'Go to Mondstadt'),false);
});
test('strict schema rejects stale requests, unsupported maps, unbounded input, and missing objective', () => {
  const base = {session:'a',id:'x',createdAt:100000,expectedFrameId:1,mission:'navigation',...route()};
  assert.equal(engine.validate(base,'a',1,{},100000),null);
  for (const r of [{...base,session:'b'},{...base,createdAt:0},{...base,expectedFrameId:0},{...base,objective:undefined},{...base,deadlineMs:90001},{...base,waypoints:[{x:1,y:1,map:'Unknown'}]},{...base,extra:'code'}]) assert.ok(engine.validate(r,'a',1,{},100000));
});
test('look accepts only one nonzero bounded integer delta and no unrelated fields',()=>{
 const base={session:'a',id:'look',createdAt:100000,expectedFrameId:1,mission:'look',dx:125};
 assert.equal(engine.validate(base,'a',1,{},100000),null);
 for(const bad of [{...base,dx:0},{...base,dx:251},{...base,dx:-251},{...base,dx:1.5},{...base,dx:'125'},{...base,dx:50,key:'VK_J'}]) assert.ok(engine.validate(bad,'a',1,{},100000));
});
test('look rejects stale and wrong-session requests without observing or rotating',async()=>{
 for(const [session,frameId] of [['other',1],['a',0]]) {
  const f=fixture();await f.runner.observe();
  const r={session,id:'bad-look-'+session+frameId,createdAt:100000,expectedFrameId:frameId,mission:'look',dx:-100};
  assert.equal(await f.runner.process(r,()=>mission),'rejected');
  assert.equal(f.runner.getFrame(),1);assert.equal(f.calls.some(c=>c[0]==='rotate'),false);
 }
});
test('look requires safe world HUD and numeric HP before rotating',async()=>{
 for(const patch of [
  {world:false},{journal:true},{bigMap:true},{tutorialStep:'trackQuest'},{climbing:true},
  {lowHealth:true},{health:{current:590,max:1000}},{dialogueReady:true},{choice:true},
 ]) {
  const f=fixture([world(),{...world(),hud:{...world().hud,...patch}}]);await f.runner.observe();
  await assert.rejects(f.runner.process(f.request('look',{dx:80}),()=>mission),/Look requires fresh safe world HUD/);
  assert.equal(f.calls.some(c=>c[0]==='rotate'),false);
 }
});
test('valid look rotates once, waits, and records a fresh safe observation',async()=>{
 const f=fixture();await f.runner.observe();
 let readyChecks=0;f.api.requireInputReady=()=>readyChecks++;
 const result=await f.runner.process(f.request('look',{dx:-120}),()=>mission);
 assert.equal(result,'completed');
 assert.deepEqual(f.calls.filter(c=>c[0]==='rotate'),[['rotate',-120]]);
 const receipt=f.writes.filter(([p])=>p==='receipt.json').at(-1)[1];
 assert.equal(receipt.status,'completed');assert.equal(receipt.frameId,4);
 assert.equal(receipt.details.result.frameId,3);
 assert.equal(receipt.details.result.timestamp,100180,'post-look observation follows the required 180 ms settle');
 assert.equal(receipt.details.result.hud.world,true);
 assert.equal(readyChecks,1);
});
test('publishes current observation and terminal receipt; duplicate rejected', async () => {
  const f=fixture(); await f.runner.observe(); const r=f.request('observe'); await f.runner.process(r,()=>mission);
  assert.ok(f.writes.some(([p])=>p==='observation.json'));
  assert.equal(f.writes.filter(([p])=>p==='receipt.json').at(-1)[1].status,'completed');
  assert.equal(await f.runner.process({...r,expectedFrameId:f.runner.getFrame()},()=>mission),'rejected');
});
test('journal Escape allowed but world F without interaction rejected', async () => {
  const f=fixture([{map:null,hud:{journal:true}}]); await f.runner.observe(); await f.runner.process(f.request('keyPress',{key:'VK_ESCAPE'}),()=>mission);
  assert.ok(f.calls.some(c=>c[1]==='VK_ESCAPE'));
  const g=fixture(); await g.runner.observe(); await assert.rejects(g.runner.process(g.request('keyPress',{key:'VK_F'}),()=>mission),/recognized screen/);
  assert.ok(!g.calls.some(c=>c[0]==='key'));
});
test('stop ends the controller; idle time does not', async () => {
  const f=fixture(); await f.runner.observe(); await f.runner.process(f.request('stop'),()=>mission); assert.equal(f.runner.stopped(),true);
  const g=fixture(); g.advance(600001); assert.equal(g.runner.stopped(),false);
});
test('world coordinate bearings match inverted map axes', () => {
  assert.equal(mission.bearing({x:0,y:0},{x:10,y:0}),180);
  assert.equal(mission.bearing({x:0,y:0},{x:0,y:10}),270);
});
test('turns are reobserved before any forward input; stationary turns do not count as stalled walking', async () => {
  const f=fixture(); let n=0;
  const result=await mission.runNavigation(route(),world(0,0),f.api,async()=> ++n<5 ? world(0,90) : n===5 ? world(0,180) : world(10,180));
  assert.equal(result.status,'arrived'); assert.equal(f.calls.filter(c=>c[0]==='rotate').length,5);
  assert.deepEqual(f.calls.at(-1),['forward',800]);
});
test('movement stops on HP drop, changed objective, missing HUD, and three stalled moves', async () => {
  for(const next of [{...world(1),hud:{...world().hud,health:{current:650,max:987}}},{...world(1),hud:{...world().hud,objectives:['New quest']}},{...world(1),hud:{...world().hud,world:false}}]) {
    const f=fixture(); const result=await mission.runNavigation(route(100),world(),f.api,async()=>next);
    assert.equal(result.status,'stopped'); assert.equal(f.calls.filter(c=>c[0]==='forward').length,1);
  }
  const f=fixture(); const result=await mission.runNavigation(route(100),world(),f.api,async()=>world());
  assert.match(result.reason,/stalled/); assert.equal(f.calls.filter(c=>c[0]==='forward').length,3);
});
test('dialogue emits no Space for choices or unrecognized screens',async()=>{
  for(const hud of [{choice:true},{dialogueReady:false}]) {
    const f=fixture(); const result=await mission.runDialogue(f.api,async()=>({hud})); assert.equal(result.status,'stopped'); assert.equal(f.calls.length,0);
  }
});
test('adapter releases held key when focus lost during movement', async()=>{
  const calls=[]; const ctx={genshin:{isRemoteDesktopSession:true,windowsSessionId:5,isGameForeground:true},file:{isExists:()=>false},keyDown:k=>calls.push(['down',k]),keyUp:k=>calls.push(['up',k]),sleep:async()=>{ctx.genshin.isGameForeground=false;}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),ctx); const a=ctx.createActOneAdapter(5);
  await assert.rejects(a.forward(800),/foreground/); assert.deepEqual(calls,[['down','VK_W'],['up','VK_W']]);
});
test('default observe-only controller refuses input', async()=>{
  const f=fixture(); const runner=engine.create(f.api,{session:'a',enableInput:false}); await runner.observe();
  await assert.rejects(runner.process({session:'a',id:'disabled',createdAt:100000,expectedFrameId:1,mission:'keyPress',key:'VK_J'},()=>mission),/disabled/);
  assert.ok(!f.calls.some(c=>c[0]==='key'));
});
test('scoped crystal ledge recovery jumps once, then stops if still stalled',async()=>{
  const f=fixture(); const o=world(0,180); o.hud.worldMarker={x:960,y:345}; o.hud.objectives=['Investigate what Paimon has found','Higher 5m'];
  const result=await mission.runNavigation({...route(7),objective:'Investigate what Paimon has found'},o,f.api,async()=>o);
  assert.equal(result.status,'stopped'); assert.equal(result.jumpRecoveries,1);
  assert.equal(f.calls.filter(c=>c[0]==='key'&&c[1]==='VK_SPACE').length,1);
});
test('key hold uses elapsed time rather than accumulating sleep overshoot',async()=>{
  let clock=0; const calls=[];
  const ctx={Date:{now:()=>clock},genshin:{isRemoteDesktopSession:true,windowsSessionId:5,isGameForeground:true},file:{isExists:()=>false},keyDown:k=>calls.push(['down',clock]),keyUp:k=>calls.push(['up',clock]),sleep:async ms=>{clock+=ms+12;}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),ctx); const a=ctx.createActOneAdapter(5);
  await a.forward(800); assert.ok(clock>=800&&clock<=850); assert.equal(calls.at(-1)[0],'up');
});

test('dialogue acknowledges only recognized character acquisition, then reobserves',async()=>{
 const f=fixture();let count=0;const seen=[{hud:{characterAcquired:'Amber'}},world()];
 f.api.continueCharacter=async()=>count++;
 const result=await mission.runDialogue(f.api,async()=>seen.shift());
 assert.equal(count,1);assert.equal(result.reason,'world_returned');assert.equal(result.presses,1);
});

test('combat request accepts only verified objective and a bounded duration',()=>{
 const r={session:'a',id:'combat',createdAt:100000,expectedFrameId:1,mission:'combat',objective:'Defeat the nearby hilichurls',deadlineMs:20000};
 assert.equal(engine.validate(r,'a',1,{},100000),null);
 for(const bad of [{...r,objective:'Fight anything'},{...r,deadlineMs:60001},{...r,deadlineMs:0},{...r,key:'VK_E'}]) assert.ok(engine.validate(bad,'a',1,{},100000));
});

test('enemy acquisition hands navigation directly to combat within the same request',async()=>{
 const f=fixture(); await f.runner.observe(); let fought=0;
 const local={runNavigation:async()=>({status:'stopped',reason:'Enemy acquired'}),run:async(r)=>{fought++;assert.equal(r.deadlineMs,20000);return {status:'completed'};}};
 await f.runner.process(f.request('navigation',{...route(),objective:'Defeat the nearby hilichurls'}),()=>local);
 assert.equal(fought,1);
 const receipt=f.writes.filter(([p])=>p==='receipt.json').at(-1)[1];
 assert.equal(receipt.details.result.localHandoff,true);
});

test('other combat navigation stops pause without starting combat',async()=>{
 const f=fixture(); await f.runner.observe(); let paused=0;
 f.api.pauseCombat=async()=>paused++;
 const local={runNavigation:async()=>({status:'stopped',reason:'Health dropped'}),run:async()=>assert.fail('unexpected combat')};
 await assert.rejects(f.runner.process(f.request('navigation',{...route(),objective:'Defeat the nearby hilichurls'}),()=>local),/Health dropped/);
 assert.equal(paused,1);
});

test('the observed forest ledge permits one jump; another stalled location does not',async()=>{
 for(const offset of [0,20]) {
  const f=fixture(),o=world();o.map={map:'Teyvat',x:-1161+offset,y:2400,cameraAngle:84.56};
  o.hud.objectives=['Defeat the nearby hilichurls'];
  const r={objective:'Defeat the nearby hilichurls',deadlineMs:90000,waypoints:[{map:'Teyvat',x:-1163+offset,y:2379}]};
  const result=await mission.runNavigation(r,o,f.api,async()=>o);
  assert.equal(result.status,'stopped');
  assert.equal(f.calls.filter(c=>c[0]==='key'&&c[1]==='VK_SPACE').length,offset===0?1:0);
 }
});

test('unknown climbing receives six bounded holds then stops without dropping',async()=>{
 const f=fixture(),o=world();o.hud.climbing=true;
 const result=await mission.runNavigation(route(),o,f.api,async()=>o);
 assert.match(result.reason,/Bounded ledge climb/);
 assert.equal(result.climbSteps,6);
 assert.equal(f.calls.filter(c=>c[0]==='forward').length,6);
 assert.equal(f.calls.some(c=>c[0]==='releaseClimb'),false);
});

test('verified cliff climb is capped at twelve observed holds without a drop',async()=>{
 const f=fixture(),o=world();o.map={map:'Teyvat',x:-1128.5,y:2217,cameraAngle:90};
 o.hud.climbing=true;o.hud.objectives=['Defeat the nearby hilichurls'];
 f.api.releaseClimb=async()=>assert.fail('verified cliff should not drop');
 const r={objective:'Defeat the nearby hilichurls',deadlineMs:45000,waypoints:[{map:'Teyvat',x:-1127,y:2193}]};
 const result=await mission.runNavigation(r,o,f.api,async()=>o);
 assert.match(result.reason,/Bounded cliff climb/);
 assert.equal(f.calls.filter(c=>c[0]==='forward').length,12);
});

test('low enemy HP remains a target when its red bar becomes short',()=>{
 const bar=require(path.join(root,'bgi.js')).enemyBarSize;
 assert.equal(bar(20,8),true);assert.equal(bar(6,6),true);
 assert.equal(bar(100,60),false);assert.equal(bar(2,8),true);assert.equal(bar(1,8),false);
});


test('observed city wall retreat drops only once for an outward route',async()=>{
 const f=fixture(),o=world();o.map={map:'Teyvat',x:-849.9,y:2285,cameraAngle:164.5};o.hud.climbing=true;
 o.hud.objectives=['Go to the location designated by Amber'];let releases=0;f.api.releaseClimb=async()=>releases++;
 const r={objective:o.hud.objectives[0],deadlineMs:30000,waypoints:[{map:'Teyvat',x:-870,y:2290}]};
 const result=await mission.runNavigation(r,o,f.api,async()=>o);
 assert.equal(releases,1);assert.equal(result.reason,'City wall retreat did not clear climbing');
 assert.equal(f.calls.filter(c=>c[0]==='forward').length,0);
});
