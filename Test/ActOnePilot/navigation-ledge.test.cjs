const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const objective = 'Keep heading towards Mondstadt';
const request = { objective, deadlineMs: 20000, waypoints: [{ map: 'Teyvat', x: 0, y: 0 }] };
function frame({ climbing = true, lowHealth = false, objectiveChanged = false, health = 900 } = {}) {
  return {
    map: { map: 'Teyvat', x: 0, y: 0, cameraAngle: 180 },
    hud: { world: true, climbing, dialogueReady: false, choice: false, objectiveChanged, lowHealth,
      health: { current: health, max: 1000 }, objectives: [objective] }
  };
}
function harness(frames) {
  let now = 0, index = 0;
  const inputs = [];
  return {
    inputs,
    api: { now: () => now, checkStop: () => {}, sleep: async ms => { now += ms; },
      forward: async ms => { inputs.push(['forward', ms]); now += ms; },
      rotate: async ms => { inputs.push(['rotate', ms]); now += 20; },
      keyPress: async key => { inputs.push(['keyPress', key]); } },
    observe: async () => frames[Math.min(index++, frames.length - 1)]
  };
}

test('unknown ledge climb stops after six bounded holds without continuing movement', async () => {
  const h = harness(Array(7).fill(frame()));
  const result = await mission.runNavigation(request, frame(), h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'Bounded ledge climb did not reach the top');
  assert.equal(result.climbSteps, 6);
  assert.deepEqual(h.inputs, Array(6).fill(['forward', 800]));
});

test('headquarters approach stops on an arch or hedge instead of climbing it', async () => {
  const objective='Go to the Knights of Favonius Headquarters';
  const current=frame(); current.hud.objectives=[objective];
  const h=harness([current]);
  const result=await mission.runNavigation({...request,objective},current,h.api,h.observe);
  assert.equal(result.reason,'Unexpected climbing on headquarters approach');
  assert.equal(result.climbSteps,0);
  assert.deepEqual(h.inputs,[]);
});

test('fresh world frame resets the per-ledge limit but request-wide climb cap stays at twelve', async () => {
  const h = harness([
    ...Array(5).fill(frame()),
    frame({ climbing: false }),
    ...Array(20).fill(frame()),
  ]);
  const twoLedgeRoute = { ...request, waypoints: [
    { map: 'Teyvat', x: 10, y: 0 },
    { map: 'Teyvat', x: 0, y: 0 },
  ] };
  const result = await mission.runNavigation(twoLedgeRoute, frame(), h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'Navigation-wide climb hold limit reached');
  assert.equal(result.climbSteps, 12);
  assert.equal(h.inputs.filter(input => input[0] === 'forward').length, 13, 'includes one guarded navigation move between ledges plus twelve climb holds');
});

test('missing HUD after the request-wide climb cap stops safely without dereferencing HUD', async () => {
  const missingHud = { map: null, hud: null };
  const h = harness([
    ...Array(5).fill(frame()),
    frame({ climbing: false }),
    frame(),
    ...Array(5).fill(frame()),
    missingHud,
  ]);
  const twoLedgeRoute = { ...request, waypoints: [
    { map: 'Teyvat', x: 10, y: 0 },
    { map: 'Teyvat', x: 0, y: 0 },
  ] };
  const result = await mission.runNavigation(twoLedgeRoute, frame(), h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.match(result.reason, /missing navigation evidence/);
  assert.equal(result.climbSteps, 12);
  assert.equal(h.inputs.filter(input => input[0] === 'forward').length, 13);
});

test('unknown climb continues navigation when two steps reach a fresh non-climbing frame', async () => {
  const h = harness([frame(), frame({ climbing: false })]);
  const result = await mission.runNavigation(request, frame(), h.api, h.observe);
  assert.equal(result.status, 'arrived');
  assert.equal(result.climbSteps, 2);
  assert.deepEqual(h.inputs, [['forward', 800], ['forward', 800]]);
});

test('low health on a fresh climb observation stops before another hold', async () => {
  const h = harness([frame({ lowHealth: true })]);
  const result = await mission.runNavigation(request, frame(), h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.match(result.reason, /low-health/);
  assert.equal(result.climbSteps, 1);
  assert.deepEqual(h.inputs, [['forward', 800]]);
});

test('objective change on a fresh climb observation stops before another hold', async () => {
  const h = harness([frame({ objectiveChanged: true })]);
  const result = await mission.runNavigation(request, frame(), h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.match(result.reason, /objective/);
  assert.equal(result.climbSteps, 1);
  assert.deepEqual(h.inputs, [['forward', 800]]);
});

test('ledge recovery does not start when less than one hold-and-observe interval remains', async () => {
  const h = harness([frame()]);
  const result = await mission.runNavigation({ ...request, deadlineMs: 999 }, frame(), h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'Navigation deadline reached before ledge recovery');
  assert.equal(result.climbSteps, 0);
  assert.deepEqual(h.inputs, []);
});

test('Talk to Amber permits one jump only at the verified grounded stone-base obstacle', async () => {
  const talk='Talk to Amber',anchor={x:-1159.818,y:2137.488},target={x:-1167.818,y:2137.488};
  function amberFrame(x,y,objective=talk,groundControls=true) {
    return {map:{map:'Teyvat',x,y,cameraAngle:0},hud:{world:true,climbing:false,groundControls,dialogueReady:false,choice:false,
      objectiveChanged:false,lowHealth:false,health:{current:1213,max:1213},objectives:[objective]}};
  }
  async function runFrom(start) {
    let now=0,current=start,jumped=false;const inputs=[];
    const api={now:()=>now,checkStop:()=>{},sleep:async ms=>{now+=ms;},rotate:async ms=>{inputs.push(['rotate',ms]);},
      keyPress:async key=>{inputs.push(['keyPress',key]);if(key==='VK_SPACE')jumped=true;},
      forward:async ms=>{inputs.push(['forward',ms]);now+=ms;if(jumped&&ms===500){current=amberFrame(target.x,target.y);jumped=false;}}};
    const observe=async()=>current;
    const result=await mission.runNavigation({objective:talk,deadlineMs:10000,waypoints:[{map:'Teyvat',...target}]},start,api,observe);
    return {result,inputs};
  }
  const safe=await runFrom(amberFrame(anchor.x,anchor.y));
  assert.equal(safe.result.status,'arrived');
  assert.equal(safe.result.jumpRecoveries,1);
  assert.equal(safe.inputs.filter(input=>input[0]==='keyPress'&&input[1]==='VK_SPACE').length,1);

  const wrong=await runFrom(amberFrame(anchor.x+3,anchor.y));
  assert.equal(wrong.result.status,'stopped');
  assert.equal(wrong.result.reason,'Map coordinates stalled');
  assert.equal(wrong.result.jumpRecoveries,0);
  assert.equal(wrong.inputs.some(input=>input[0]==='keyPress'&&input[1]==='VK_SPACE'),false);

  const noGround=await runFrom(amberFrame(anchor.x,anchor.y,talk,false));
  assert.equal(noGround.result.reason,'Map coordinates stalled');
  assert.equal(noGround.inputs.some(input=>input[0]==='keyPress'&&input[1]==='VK_SPACE'),false);
});

