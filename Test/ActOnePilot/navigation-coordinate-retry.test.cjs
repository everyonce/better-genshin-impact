const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const objective = 'Keep heading towards Mondstadt';
const request = { objective, deadlineMs: 5000, waypoints: [{ map: 'Teyvat', x: 20, y: 0 }] };
function frame(x, { objectives = [objective], health = { current: 900, max: 1000 }, ...patch } = {}) {
  return { frameId: 1, map: { map: 'Teyvat', x, y: 0, cameraAngle: 180 }, hud: {
    world: true, health, lowHealth: false, objectives, objectiveChanged: false, dialogueReady: false, choice: false,
    journal: false, bigMap: false, climbing: false, tutorialStep: null, ...patch,
  } };
}
function harness(initial, next) {
  let now = 0, latest = initial, observations = 0;
  const actions = [];
  const api = { now: () => now, sleep: async ms => { now += ms; }, checkStop: () => {},
    rotate: async ms => { actions.push(['rotate', ms]); now += 20; },
    forward: async ms => { actions.push(['forward', ms]); now += ms; latest = { ...latest, map: { ...latest.map, x: 20 } }; },
    keyPress: async key => actions.push(['keyPress', key]),
  };
  async function observe() {
    observations++;
    if (next) latest = next(observations, latest, actions);
    return { ...latest, frameId: observations + 1 };
  }
  return { actions, api, get observations() { return observations; }, observe };
}

test('transient implausible coordinates are retried before any input, then navigation continues', async () => {
  const bad = frame(4918.1777);
  const recovered = frame(0);
  const h = harness(bad, (count, latest, actions) => {
    if (count === 1) { assert.deepEqual(actions, [], 'no input before a fresh map retry'); return recovered; }
    return latest;
  });
  const result = await mission.runNavigation(request, bad, h.api, h.observe);
  assert.equal(result.status, 'arrived');
  assert.equal(h.observations, 2);
  assert.deepEqual(h.actions.map(a => a[0]), ['forward']);
});

test('persistent implausible coordinates stop after two fresh retries with no input', async () => {
  const bad = frame(4918.1777);
  const h = harness(bad, () => bad);
  const result = await mission.runNavigation(request, bad, h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'Waypoint farther than the allowed local segment');
  assert.equal(h.observations, 2);
  assert.deepEqual(h.actions, []);
});

test('objective change or unsafe health on a coordinate retry stops without input', async () => {
  const bad = frame(4918.1777);
  const unsafe = [
    frame(0, { objectives: ['Another objective'], objectiveChanged: true }),
    frame(0, { health: { current: 590, max: 1000 } }),
  ];
  for (const next of unsafe) {
    const h = harness(bad, () => next);
    const result = await mission.runNavigation(request, bad, h.api, h.observe);
    assert.equal(result.status, 'stopped');
    assert.deepEqual(h.actions, []);
  }
});
