const test = require('node:test');
const assert = require('node:assert/strict');
const combat = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/combat.js');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const engine = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/engine.js');

const OBJECTIVE = 'Stormterror aerial encounter';
const labels = [
  { text: 'Stormterror', x: 878, y: 22, width: 150, height: 24 },
  { text: 'Howling Hurricane of Mondstadt', x: 797, y: 53, width: 340, height: 24 },
];
function aerial(fraction = 0.9, current = 1138, extra = {}) {
  return { map: null, hud: { world: false, health: { current, max: 1138 }, lowHealth: false,
    journal: false, bigMap: false, dialogueReady: false, choice: false, objectiveChanged: false,
    aerialBossVisible: true, aerialBoss: { barFraction: fraction }, ...extra } };
}
function harness(next = () => aerial()) {
  let now = 1000; const calls = [];
  const api = {
    now: () => now,
    sleep: async ms => { calls.push(['sleep', ms]); now += ms; },
    checkStop: () => calls.push(['checkStop']),
    fireAerial: async ms => { calls.push(['fireAerial', ms]); now += ms; },
    pauseCombat: async () => { calls.push(['pause']); return true; },
  };
  return { api, calls, observe: async () => { calls.push(['observe']); return next(); }, advance: ms => { now += ms; } };
}

test('recorded Stormterror labels require the encounter HUD, null map, HP, and same-frame red bar', () => {
  const hp = { current: 1138, max: 1138 };
  const screen = { journal: false, bigMap: false, dialogueReady: false, choice: false, objectiveChanged: false };
  assert.equal(bgi.aerialBossLabels(labels), true);
  assert.equal(bgi.aerialBossState(labels, null, hp, screen, 0.99), true);
  for (const [rows, map, health, flags, bar] of [
    [[{ ...labels[0], text: 'Stormterror?' }, labels[1]], null, hp, screen, 0.99],
    [[labels[0], { ...labels[1], text: 'Howling Hurricane' }], null, hp, screen, 0.99],
    [labels, { map: 'Teyvat', x: 0, y: 0 }, hp, screen, 0.99],
    [labels, null, null, screen, 0.99],
    [labels, null, { current: 590, max: 1138 }, screen, 0.99],
    [labels, null, hp, { ...screen, bigMap: true }, 0.99],
    [labels, null, hp, { ...screen, journal: true }, 0.99],
    [labels, null, hp, { ...screen, dialogueReady: true }, 0.99],
    [labels, null, hp, { ...screen, choice: true }, 0.99],
    [labels, null, hp, screen, null],
  ]) assert.equal(bgi.aerialBossState(rows, map, health, flags, bar), false);
});

test('stationary fire bursts stop after eight with no boss-bar progress', async () => {
  const f = harness(() => aerial(0.9));
  const result = await combat.runAerial({ objective: OBJECTIVE, deadlineMs: 60000 }, aerial(), f.api, f.observe);
  assert.equal(result.status, 'stopped');
  assert.match(result.reason, /no progress after eight bursts/);
  assert.equal(result.bursts, 8);
  assert.equal(result.attacks, 0);
  assert.equal(f.calls.filter(c => c[0] === 'fireAerial').length, 8);
  assert.ok(f.calls.filter(c => c[0] === 'fireAerial').every(c => c[1] === 800));
  assert.equal(f.calls.some(c => c[0] === 'pause'), false);
});

test('aerial burst loop is bounded at sixty even when boss bar continues to fall', async () => {
  let fraction = 0.99;
  const f = harness(() => aerial(fraction = Math.max(0.01, fraction - 0.015)));
  const result = await combat.runAerial({ objective: OBJECTIVE, deadlineMs: 60000 }, aerial(), f.api, f.observe);
  assert.equal(result.reason, 'Aerial burst limit reached');
  assert.equal(result.status, 'stopped');
  assert.equal(result.bursts, 60);
});

test('a one-frame missing boss signal is polled before the next burst and resumes when it returns', async () => {
  let index = 0;
  const missing = aerial(0.9, 1138, { aerialBossVisible: false, aerialBoss: null });
  const returning = aerial(0.85);
  const f = harness(() => index++ === 0 ? missing : returning);
  const result = await combat.runAerial({ objective: OBJECTIVE, deadlineMs: 60000 }, aerial(), f.api, f.observe);
  assert.match(result.reason, /no progress after eight bursts/);
  assert.equal(result.bursts, 9, 'the observed bar return permits further bursts');
  const firstFire = f.calls.findIndex(c => c[0] === 'fireAerial');
  const missingObserve = f.calls.findIndex((c,i) => i > firstFire && c[0] === 'observe');
  const retryWait = f.calls.findIndex((c,i) => i > missingObserve && c[0] === 'sleep' && c[1] === 180);
  const retryObserve = f.calls.findIndex((c,i) => i > retryWait && c[0] === 'observe');
  const nextFire = f.calls.findIndex((c,i) => i > retryObserve && c[0] === 'fireAerial');
  assert.ok(firstFire < missingObserve && missingObserve < retryWait && retryWait < retryObserve && retryObserve < nextFire);
});

test('two missing boss observations stop without firing while evidence is absent', async () => {
  const missing = aerial(0.9, 1138, { aerialBossVisible: false, aerialBoss: null });
  const f = harness(() => missing);
  const result = await combat.runAerial({ objective: OBJECTIVE, deadlineMs: 60000 }, aerial(), f.api, f.observe);
  assert.equal(result.reason, 'Encounter transition: Stormterror indicators disappeared');
  assert.equal(result.bursts, 1);
  assert.equal(f.calls.filter(c => c[0] === 'fireAerial').length, 1);
  assert.equal(f.calls.filter(c => c[0] === 'sleep' && c[1] === 180).length, 2);
});

test('unsafe HP on an observation retry aborts before another aerial burst', async () => {
  const missing = aerial(0.9, 1138, { aerialBossVisible: false, aerialBoss: null });
  const unsafe = aerial(0.85, 590);
  let index = 0;
  const f = harness(() => index++ === 0 ? missing : unsafe);
  const result = await combat.runAerial({ objective: OBJECTIVE, deadlineMs: 60000 }, aerial(), f.api, f.observe);
  assert.equal(result.reason, 'Aerial player health below 60%');
  assert.equal(result.bursts, 1);
  assert.equal(f.calls.filter(c => c[0] === 'fireAerial').length, 1);
  assert.equal(f.calls.filter(c => c[0] === 'sleep' && c[1] === 180).length, 1);
});

test('low HP, excessive health loss, and boss disappearance stop without completion', async () => {
  for (const [next, reason] of [
    [() => aerial(0.85, 680), 'Aerial player health below 60%'],
    [() => aerial(0.85, 1000), 'Aerial player health dropped more than 10% of maximum'],
    [() => aerial(0.85, 1138, { aerialBossVisible: false, aerialBoss: null }), 'Encounter transition: Stormterror indicators disappeared'],
    [() => aerial(0.85, 1138, { aerialBoss: null }), 'Aerial boss health bar evidence unavailable'],
    [() => ({ ...aerial(), map: { map: 'Teyvat', x: 0, y: 0 } }), 'Aerial encounter screen changed'],
  ]) {
    const f = harness(next);
    const result = await combat.runAerial({ objective: OBJECTIVE, deadlineMs: 60000 }, aerial(), f.api, f.observe);
    assert.equal(result.status, 'stopped');
    assert.equal(result.reason, reason);
    assert.equal(result.questCompleted, false);
    assert.equal(result.bursts, 1);
  }
});

test('only the supported aerial request objective is admitted by the engine schema', () => {
  const request = { session: 's', id: 'aerial', createdAt: 1000, expectedFrameId: 4,
    mission: 'combat', objective: OBJECTIVE, deadlineMs: 60000 };
  assert.equal(engine.validate(request, 's', 4, {}, 1000), null);
  assert.equal(engine.validate({ ...request, objective: 'Stormterror' }, 's', 4, {}, 1000), 'Unsupported combat objective');
});

test('engine preserves an aerial encounter transition as a stopped receipt', async () => {
  let now = 1000, frameId = 0, fired = 0; const writes = [];
  function data(state) { return { timestamp: now, screenshotPath: 'frame.png', ocr: labels, map: null, hud: state.hud }; }
  const api = {
    now: () => now, sleep: async ms => { now += ms; }, beginMission: () => {}, events: () => [],
    checkStop: () => {}, release: () => {}, write: (path, content) => writes.push([path, JSON.parse(content)]),
    observe: async () => { frameId++; return data(fired ? aerial(0.8, 1138, { aerialBossVisible: false, aerialBoss: null }) : aerial()); },
    fireAerial: async ms => { assert.equal(ms, 800); fired++; now += ms; },
  };
  const runner = engine.create(api, { session: 's', enableInput: true });
  await runner.observe();
  const request = { session: 's', id: 'stop-transition', createdAt: now, expectedFrameId: runner.getFrame(),
    mission: 'combat', objective: OBJECTIVE, deadlineMs: 60000 };
  const result = await runner.process(request, () => ({ run: combat.run }));
  assert.equal(result, 'stopped');
  const receipt = writes.filter(([path]) => path === 'receipt.json').at(-1)[1];
  assert.equal(receipt.status, 'stopped');
  assert.equal(receipt.details.result.reason, 'Encounter transition: Stormterror indicators disappeared');
  assert.equal(receipt.details.result.questCompleted, false);
});
