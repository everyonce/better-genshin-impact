const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

const objective = 'Meet Amber at the temple';
function frame({ map = null, world = true, health = { current: 900, max: 1000 }, objectives = [objective], ...patch } = {}) {
  return { frameId: 12, map, hud: { world, health, lowHealth: false, objectives, journal: false, bigMap: false,
    dialogueReady: false, choice: false, climbing: false, tutorialStep: null, objectiveChanged: false, ...patch } };
}
function harness(observations, teleportDuration = 0) {
  let now = 1000, index = 0; const calls = [];
  const api = { now: () => now, sleep: async ms => { calls.push(['sleep', ms]); now += ms; }, checkStop: () => calls.push(['checkStop']),
    teleportFalconWaypoint: async (...args) => { calls.push(['teleport', ...args]); now += teleportDuration; } };
  const observe = async () => { const o = observations[Math.min(index++, observations.length - 1)]; calls.push(['observe', o.frameId]); return o; };
  return { calls, api, run: initial => mission.runQuestStep('falconWaypoint', initial, api, observe) };
}

test('falcon waypoint uses the fixed native destination and verifies arrival within 25m', async () => {
  assert.deepEqual(bgi.falconWaypointTarget(), { x: -1122.173, y: 2197.455 });
  const initial = frame({ map: { map: 'Teyvat', x: 8473, y: 7673 } });
  const arrived = frame({ map: { map: 'Teyvat', x: -1100, y: 2207 } });
  const h = harness([arrived]);
  const result = await h.run(initial);
  assert.equal(result.status, 'completed');
  assert.equal(result.reason, 'Falcon waypoint arrival verified');
  assert.deepEqual(h.calls.filter(c => c[0] === 'teleport'), [['teleport']]);
  assert.equal(h.calls.filter(c => c[0] === 'observe').length, 1, 'arrival must use a post-teleport capture');
  assert.equal(result.nativeTeleportMs, 0);
  assert.equal(result.polls, 1);
});

test('post-teleport verification gets its full 15 seconds even when native teleport takes longer', async () => {
  const arrived = frame({ map: { map: 'Teyvat', x: -1122.173, y: 2197.455 } });
  const h = harness([arrived], 20000);
  const result = await h.run(frame());
  assert.equal(result.status, 'completed');
  assert.equal(result.nativeTeleportMs, 20000);
  assert.equal(result.polls, 1);
});

test('pre-teleport coordinates at the destination cannot validate arrival', async () => {
  const staleAtTarget = frame({ map: { map: 'Teyvat', x: -1122.173, y: 2197.455 } });
  const afterTeleportLoading = frame({ world: false, map: null, health: null, lowHealth: true, objectives: [] });
  const h = harness([afterTeleportLoading]);
  const result = await h.run(staleAtTarget);
  assert.equal(result.status, 'stopped');
  assert.match(result.reason, /timed out/);
  assert.equal(result.frameId, afterTeleportLoading.frameId);
  assert.equal(result.polls, 44);
});

test('unsafe initial evidence never invokes native teleport', async () => {
  const unsafe = [
    frame({ objectives: ['Meet Amber at the temples'] }),
    frame({ health: { current: 590, max: 1000 } }),
    frame({ journal: true }), frame({ dialogueReady: true }), frame({ choice: true }),
    frame({ climbing: true }), frame({ tutorialStep: 'glideOpen' }), frame({ objectiveChanged: true }),
    frame({ world: false }),
  ];
  for (const observation of unsafe) {
    const h = harness([]), result = await h.run(observation);
    assert.equal(result.status, 'stopped');
    assert.equal(h.calls.some(c => c[0] === 'teleport'), false);
  }
});

test('loading observations are tolerated until exact verified arrival', async () => {
  const loading = frame({ world: false, map: null, health: null, lowHealth: true, objectives: [] });
  const arrived = frame({ map: { map: 'Teyvat', x: -1122.173, y: 2197.455 } });
  const h = harness([loading, arrived]);
  const result = await h.run(frame());
  assert.equal(result.status, 'completed');
  assert.equal(result.polls, 2);
  const changed = harness([frame({ objectives: ['A different quest'] })]);
  const stopped = await changed.run(frame());
  assert.equal(stopped.status, 'stopped');
  assert.match(stopped.reason, /Objective changed/);
});

test('recognized New Quest toast waits without input until exact objective and arrival return', async () => {
  const toast = frame({ map: { map: 'Teyvat', x: -1100, y: 2200 }, objectives: ['New Quest', 'Sharpening the Axe Won\'t Hinder the Work'] });
  const arrived = frame({ map: { map: 'Teyvat', x: -1120.639, y: 2190.842 } });
  const h = harness([toast, arrived]);
  const result = await h.run(frame());
  assert.equal(result.status, 'completed');
  assert.equal(result.polls, 2, 'one initial toast capture and one fresh arrival capture');
  assert.deepEqual(h.calls.filter(c => c[0] === 'sleep'), [['sleep', 350]]);
  assert.equal(h.calls.some(c => c[0] === 'forward'), false);
});

test('New Quest toast resolving to a different objective stops without movement', async () => {
  const toast = frame({ map: { map: 'Teyvat', x: -1100, y: 2200 }, objectives: ['New Quest', 'Sharpening the Axe Won\'t Hinder the Work'] });
  const changed = frame({ map: { map: 'Teyvat', x: -1100, y: 2200 }, objectives: ['Sharpening the Axe Won\'t Hinder the Work'] });
  const h = harness([toast, changed]);
  const result = await h.run(frame());
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'Falcon New Quest toast cleared with unrelated objective');
  assert.equal(result.polls, 2);
  assert.equal(h.calls.some(c => c[0] === 'forward'), false);
});

test('persistent loading stops at 15 seconds without movement or repeat teleport', async () => {
  const loading = frame({ world: false, map: null, health: null, lowHealth: true, objectives: [] });
  const h = harness([loading]);
  const result = await h.run(frame());
  assert.equal(result.status, 'stopped');
  assert.match(result.reason, /timed out/);
  assert.equal(result.polls, 44);
  assert.equal(h.calls.filter(c => c[0] === 'teleport').length, 1);
  assert.equal(h.calls.some(c => c[0] === 'forward'), false);
});

test('bgi teleport gate requires a fresh exact objective, safe HP, world and clear HUD', () => {
  const safe = { ...frame(), timestamp: 1000, frameId: 25 };
  assert.equal(bgi.falconWaypointReady(safe, 2000), true);
  for (const changed of [
    { ...safe, timestamp: 999 }, { ...safe, timestamp: 0 },
    { ...safe, hud: { ...safe.hud, world: false } },
    { ...safe, hud: { ...safe.hud, objectives: ['Meet Amber at the temples'] } },
    { ...safe, hud: { ...safe.hud, health: { current: 599, max: 1000 } } },
    { ...safe, hud: { ...safe.hud, journal: true } },
    { ...safe, hud: { ...safe.hud, bigMap: true } },
    { ...safe, hud: { ...safe.hud, climbing: true } },
    { ...safe, hud: { ...safe.hud, tutorialStep: 'glideOpen' } },
    { ...safe, hud: { ...safe.hud, objectiveChanged: true } },
  ]) assert.equal(bgi.falconWaypointReady(changed, 2000), false);
});

test('full-map OCR recognition uses the footer, resin counter and multiple geographic labels', () => {
  const rows = [
    { text: 'Teyvat', x: 1691, y: 983 }, { text: '200/200', x: 1624, y: 32 },
    { text: 'Mondstadt', x: 925, y: 325 }, { text: 'Cider Lake', x: 956, y: 60 },
    { text: 'Whispering Woods', x: 1226, y: 274 }, { text: 'Starfell Lake', x: 1480, y: 129 },
  ];
  assert.equal(bgi.fullMapState(rows), true);
  for (const bad of [rows.slice(0, 3), rows.map(r => r.text === 'Teyvat' ? { ...r, y: 500 } : r),
    rows.map(r => r.text === '200/200' ? { ...r, x: 1200 } : r),
    [...rows, { text: 'Teyvat', x: 1690, y: 982 }]]) assert.equal(bgi.fullMapState(bad), false);
});


