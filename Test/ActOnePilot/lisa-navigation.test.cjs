const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const objective = 'Meet Lisa at the temple';
function world({x=0,angle=180,groundControls=true,climbing=false,enemyBars=[]}={}) {
  return {map:{map:'Teyvat',x,y:0,cameraAngle:angle},hud:{world:true,groundControls,climbing,
    lowHealth:false,health:{current:900,max:1000},objectives:[objective],enemyBars}};
}
function api(){let now=1000;const calls=[];return {calls,now:()=>now,sleep:async ms=>{now+=ms;},checkStop(){},
  rotate:async ms=>calls.push(['rotate',ms]),forward:async ms=>{calls.push(['forward',ms]);now+=ms;},
  keyPress:async key=>calls.push(['key',key]),releaseClimb:async()=>calls.push(['releaseClimb'])};}
const request={objective,deadlineMs:90000,waypoints:[{map:'Teyvat',x:30,y:0}]};

test('Lisa dispatch requires the verified-pause wrapper and invokes its callback in protected mode',async()=>{
  const a=api();let calls=0,wrappedResult;
  a.runLisaNavigationWithPause=async(initial,observe,run)=>{
    calls++;wrappedResult=await run(initial);return {status:'completed',navigationStatus:wrappedResult.status,
      destinationReached:wrappedResult.status==='arrived',questComplete:false,fieldFrameId:initial.frameId||1,pauseProof:{verified:true}};
  };
  const initial={...world(),frameId:1};
  const wrapped=await mission.runNavigation(request,initial,a,async()=>initial);
  assert.equal(calls,1);assert.equal(wrapped.status,'completed');assert.equal(wrapped.navigationStatus,'stopped');
  assert.equal(wrapped.destinationReached,false);assert.equal(wrapped.questComplete,false);assert.ok(a.calls.every(c=>c[0]==='forward'&&c[1]<=800));
  const invalid=api();const unbounded=await mission.runNavigation({...request,deadlineMs:90001},world(),invalid,async()=>world());
  assert.equal(unbounded.status,'stopped');assert.match(unbounded.reason,/within 90 seconds/);assert.deepEqual(invalid.calls,[]);
  const noWrapper=api();const stopped=await mission.runNavigation(request,world(),noWrapper,async()=>world());
  assert.equal(stopped.status,'stopped');assert.match(stopped.reason,/pause wrapper unavailable/);assert.deepEqual(noWrapper.calls,[]);
});

test('an enemy bar in the current frame stops Lisa navigation before any turn or forward pulse',async()=>{
  const a=api();const o=world({enemyBars:[{x:900}]});
  const result=await mission.runNavigation(request,o,a,async()=>o,true);
  assert.equal(result.status,'stopped');assert.match(result.reason,/Enemy bar/);assert.deepEqual(a.calls,[]);
});

test('an enemy bar observed after a turn stops before the next forward pulse',async()=>{
  const a=api();let n=0;
  const result=await mission.runNavigation(request,world({angle:90}),a,async()=>{
    n++;return world({angle:90,enemyBars:n===1?[{x:900}]:[]});
  },true);
  assert.equal(result.status,'stopped');assert.match(result.reason,/Enemy bar/);
  assert.equal(a.calls.filter(c=>c[0]==='rotate').length,1);assert.equal(a.calls.filter(c=>c[0]==='forward').length,0);
});

test('explicit bounded escape permits movement past an enemy but expiration stops the next input',async()=>{
  const a=api();let allowed=true;
  a.lisaNavigationEnemyAllowed=()=>allowed;
  const o=world({enemyBars:[{x:900}]});
  const result=await mission.runNavigation(request,o,a,async()=>{allowed=false;return o;},true);
  assert.equal(result.status,'stopped');assert.match(result.reason,/Enemy bar/);
  assert.equal(a.calls.filter(c=>c[0]==='forward').length,1);
});

test('Lisa movement requires grounded controls and refuses climbing before input',async()=>{
  for(const patch of [{groundControls:false},{climbing:true}]){
    const a=api(),o=world(patch);const result=await mission.runNavigation(request,o,a,async()=>o,true);
    assert.equal(result.status,'stopped');assert.match(result.reason,/requires confirmed ground|refuses climbing/);assert.deepEqual(a.calls,[]);
  }
});

test('Lisa navigation never uses jump or climb recovery after repeated stationary movement',async()=>{
  const a=api();let n=0;const result=await mission.runNavigation(request,world(),a,async()=>{n++;return world();},true);
  assert.equal(result.status,'stopped');assert.match(result.reason,/jump recovery/);
  assert.equal(a.calls.filter(c=>c[0]==='key'&&c[1]==='VK_SPACE').length,0);
  assert.equal(a.calls.filter(c=>c[0]==='releaseClimb').length,0);
  assert.equal(a.calls.filter(c=>c[0]==='forward').length,3);
});
