const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const expected = 'Keep heading towards Mondstadt';
const request = { objective: expected, deadlineMs: 12000, waypoints: [{ map: 'Teyvat', x: 20, y: 0 }] };
function observation(objectives, health = { current: 900, max: 1000 }, extra = {}) {
  return {
    map: { map: 'Teyvat', x: 0, y: 0, cameraAngle: 180 },
    hud: { world: true, dialogueReady: false, choice: false, objectiveChanged: false, lowHealth: false, health, objectives },
    ...extra
  };
}
function harness(initial, observeNext) {
  let now = 0, latest = initial;
  const actions = [];
  return {
    actions,
    get nowValue() { return now; },
    initial,
    api: {
      now: () => now,
      sleep: async ms => { now += ms; },
      checkStop: () => {},
      rotate: async ms => { actions.push(['rotate', ms]); now += 20; },
      forward: async ms => { actions.push(['forward', ms]); now += ms; latest = { ...latest, map: { ...latest.map, x: 20 } }; },
      keyPress: async key => { actions.push(['keyPress', key]); },
    },
    observe: async () => { latest = observeNext(latest); return latest; }
  };
}

test('waits through a recognized New Quest banner, then navigates only after the requested objective returns', async () => {
  let observed = 0;
  const toast = observation(['New Quest', 'The Art of Cooking']);
  const h = harness(toast, () => {
    observed++;
    return { ...observation([expected]), map: { map: 'Teyvat', x: observed > 1 ? 20 : 0, y: 0, cameraAngle: 180 } };
  });
  const result = await mission.runNavigation(request, toast, h.api, h.observe);
  assert.equal(observed, 2, 'one fresh observation clears the toast and one verifies arrival');
  assert.equal(result.status, 'arrived');
  assert.deepEqual(h.actions.map(a => a[0]), ['forward']);
});

test('a persistent New Quest banner stops within the eight-second observation-only bound', async () => {
  const toast = observation(['New Quest', 'The Art of Cooking']);
  const h = harness(toast, () => observation(['New Quest', 'The Art of Cooking']));
  const result = await mission.runNavigation(request, toast, h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'New Quest toast did not clear');
  assert.ok(h.nowValue <= 8000, `waited ${h.nowValue}ms`);
  assert.ok(h.nowValue >= 7600, `stopped too early at ${h.nowValue}ms`);
  assert.deepEqual(h.actions, []);
});

test('a transient frame missing health and objective evidence is retried without input', async () => {
  const base = observation([], null);
  const missing = { ...base, hud: { ...base.hud, world: false, lowHealth: true } };
  let count = 0;
  const h = harness(missing, () => {
    count++;
    if (count === 1) {
      assert.deepEqual(h.actions, [], 'no input before fresh evidence');
      return { ...observation([expected]), map: { map: 'Teyvat', x: 0, y: 0, cameraAngle: 180 } };
    }
    return { ...observation([expected]), map: { map: 'Teyvat', x: 20, y: 0, cameraAngle: 180 } };
  });
  const result = await mission.runNavigation(request, missing, h.api, h.observe);
  assert.equal(result.status, 'arrived');
  assert.equal(count, 2);
  assert.deepEqual(h.actions.map(a => a[0]), ['forward']);
});

test('persistently missing health and objective evidence stops after two observation-only retries', async () => {
  const base = observation([], null);
  const missing = { ...base, hud: { ...base.hud, world: false, lowHealth: true } };
  const h = harness(missing, () => missing);
  const result = await mission.runNavigation(request, missing, h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'Fresh health evidence unavailable');
  assert.equal(h.nowValue, 360);
  assert.deepEqual(h.actions, []);
});

test('an unrelated objective change without the recognized toast is a hard stop', async () => {
  const base = observation(['The Art of Cooking']);
  const changed = { ...base, hud: { ...base.hud, objectiveChanged: true } };
  const h = harness(changed, () => { throw new Error('unexpected observation'); });
  const result = await mission.runNavigation(request, changed, h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'Dialogue, objective, low-health, or missing navigation evidence');
  assert.deepEqual(h.actions, []);
});

test('a transient objective OCR miss retries observation before any input', async () => {
  const missing = observation([]);
  let count = 0;
  const h = harness(missing, () => {
    count++;
    if (count === 1) {
      assert.deepEqual(h.actions, []);
      return { ...observation([expected]), map: { map: 'Teyvat', x: 0, y: 0, cameraAngle: 180 } };
    }
    return { ...observation([expected]), map: { map: 'Teyvat', x: 20, y: 0, cameraAngle: 180 } };
  });
  const result = await mission.runNavigation(request, missing, h.api, h.observe);
  assert.equal(result.status, 'arrived');
  assert.equal(count, 2);
  assert.equal(h.nowValue, 1130);
});

test('unsafe health on the fresh frame that clears the toast prevents navigation', async () => {
  const toast = observation(['New Quest', 'The Art of Cooking']);
  const h = harness(toast, () => observation([expected], { current: 590, max: 1000 }));
  const result = await mission.runNavigation(request, toast, h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'Unsafe state while waiting for New Quest toast');
  assert.deepEqual(h.actions, []);
});

test('a New Quest toast that resolves to an unrelated objective stops immediately', async () => {
  const toast = observation(['New Quest', 'The Art of Cooking']);
  const h = harness(toast, () => observation(['The Art of Cooking']));
  const result = await mission.runNavigation(request, toast, h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'New Quest toast cleared with unrelated objective');
  assert.ok(h.nowValue <= 350);
  assert.deepEqual(h.actions, []);
});

