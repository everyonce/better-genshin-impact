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

