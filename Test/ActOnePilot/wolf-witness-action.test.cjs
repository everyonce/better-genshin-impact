const test = require('node:test');
const assert = require('node:assert/strict');
const runner = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/wolf-witness-action.js');

function frame(id, now, opts = {}) {
  return { session: opts.session || 's1', frameId: id, timestamp: now, focused: opts.focused !== false,
    active: opts.active !== false, paused: opts.paused === true, canPause: opts.canPause === true,
    hud: { health: { current: opts.hp === undefined ? 800 : opts.hp, max: 1000 } } };
}
function harness(opts = {}) {
  let now = 10000, id = 1, phase = 'paused', reads = 0, actionCalls = 0, released = 0;
  const calls = [], initial = frame(id, now, { paused: true });
  let sleepCount = 0;
  if (opts.initialHealthMissing) initial.hud.health = null;
  const api = { now: () => now, checkStop() { if (opts.cancel) throw new Error('cancelled'); },
    sleep: async ms => { calls.push(['sleep', ms]); sleepCount++; now += ms;
      if (opts.extraDelayAt === sleepCount) now += opts.extraDelay || 0; },
    wolfWitnessContinueReady: o => o.paused === true,
    ...(opts.baselineHealth === undefined ? {} : { wolfWitnessBaselineHealth: () => opts.baselineHealth }),
    wolfWitnessContinue: async () => { calls.push('continue'); phase = 'active'; reads = 0; },
    wolfWitnessActiveReady: o => o.active === true && o.focused === true,
    wolfWitnessActionName: () => opts.actionName || 'jumpForward',
    wolfWitnessAction: async () => { actionCalls++; calls.push('action'); },
    wolfWitnessPauseReady: o => o.canPause === true,
    wolfWitnessEscape: async () => { calls.push('escape'); phase = 'pausedAgain'; reads = 0; },
    wolfWitnessPauseVerified: o => o.paused === true,
    release: async () => { released++; calls.push('release'); } };
  async function observe() {
    now += 2; id++; reads++;
    if (opts.throwObserve === reads) throw new Error('observe failed');
    let o;
    if (phase === 'active') o = frame(id, now, { active: opts.readyAtReads === undefined ? (opts.readyAfter === undefined || reads > opts.readyAfter) : reads >= opts.readyAtReads,
      focused: opts.focused !== false, canPause: true, hp: actionCalls > 0 ? (opts.hpAfter || 800) : (opts.pollHpDriftAt === reads ? 799 : 800) });
    else if (phase === 'pausedAgain') o = frame(id, now, { paused: true, canPause: false });
    else o = frame(id, now, { paused: true });
    if (opts.faultAt === reads) {
      if (opts.fault === 'stale') o.frameId = id - 1;
      if (opts.fault === 'session') o.session = 'other';
      if (opts.fault === 'old') o.timestamp = now - 1001;
      if (opts.fault === 'focus') o.focused = false;
    }
    if (phase === 'active' && opts.nullHpAtReads && opts.nullHpAtReads.includes(reads)) o.hud.health = null;
    if (phase === 'active' && opts.enemyBarsAtReads === reads) o.enemyBars = [{ current: 50, max: 100 }];
    return o;
  }
  return { initial, api, observe, calls, get actionCalls() { return actionCalls; }, get released() { return released; } };
}

test('makes one permitted action, verifies unchanged health, then safely pauses and releases', async () => {
  const h = harness(), r = await runner.run(h.initial, h.api, h.observe);
  assert.equal(r.status, 'stopped'); assert.equal(r.step, 'wolfWitnessAction');
  assert.equal(r.action, 'jumpForward'); assert.equal(r.continueAttempts, 1); assert.equal(r.actionAttempts, 1);
  assert.equal(r.pauseAttempts, 1); assert.equal(r.pauseVerified, true); assert.deepEqual(r.healthAfter, r.healthBefore);
  assert.equal(r.rootDirected, true); assert.equal(r.questComplete, false); assert.equal(r.routeComplete, false);
  assert.equal(h.actionCalls, 1); assert.equal(h.released, 1);
});

test('accepts the corrected forwardFine action name', async () => {
  const h = harness({ actionName: 'forwardFine' }), r = await runner.run(h.initial, h.api, h.observe);
  assert.equal(r.action, 'forwardFine'); assert.equal(r.actionAttempts, 1); assert.equal(h.actionCalls, 1);
});

test('uses adapter health fallback only when pause HUD health is absent and still matches active health', async () => {
  const valid = harness({ initialHealthMissing: true, baselineHealth: { current: 800, max: 1000 } });
  const a = await runner.run(valid.initial, valid.api, valid.observe);
  assert.deepEqual(a.healthBefore, { current: 800, max: 1000 }); assert.equal(a.actionAttempts, 1);
  const missing = harness({ initialHealthMissing: true }), b = await runner.run(missing.initial, missing.api, missing.observe);
  assert.match(b.reason, /health baseline required/); assert.equal(b.continueAttempts, 0); assert.equal(b.actionAttempts, 0);
  const invalidValues = [null, { current: 0, max: 1000 }, { current: 1001, max: 1000 },
    { current: 100, max: 0 }, { current: NaN, max: 1000 }];
  for (const baselineHealth of invalidValues) {
    const h = harness({ initialHealthMissing: true, baselineHealth }), r = await runner.run(h.initial, h.api, h.observe);
    assert.match(r.reason, /health baseline required/); assert.equal(r.continueAttempts, 0); assert.equal(h.actionCalls, 0);
  }
});

test('rejects noncanonical entry, unknown action, and changed health before input', async () => {
  const entry = harness(); entry.initial.paused = false;
  const a = await runner.run(entry.initial, entry.api, entry.observe);
  assert.equal(a.continueAttempts, 0); assert.equal(entry.actionCalls, 0); assert.equal(entry.released, 1);
  const malformed = harness(); malformed.initial.timestamp = malformed.api.now() - 1001;
  const m = await runner.run(malformed.initial, malformed.api, malformed.observe);
  assert.match(m.reason, /Canonical paused entry/); assert.equal(m.continueAttempts, 0); assert.equal(malformed.released, 1);
  const unknown = harness({ actionName: 'forward' }), b = await runner.run(unknown.initial, unknown.api, unknown.observe);
  assert.match(b.reason, /Unknown/); assert.equal(b.actionAttempts, 0); assert.equal(unknown.actionCalls, 0);
  const changed = harness({ hpAfter: 799 }), c = await runner.run(changed.initial, changed.api, changed.observe);
  assert.match(c.reason, /Health changed after/); assert.equal(c.actionAttempts, 1); assert.equal(changed.actionCalls, 1);
});

test('deadline expiry prevents action and cleanup Escape while still releasing', async () => {
  const h = harness({ extraDelayAt: 1, extraDelay: 15000 }), r = await runner.run(h.initial, h.api, h.observe);
  assert.match(r.reason, /15-second/); assert.equal(r.actionAttempts, 0); assert.equal(h.actionCalls, 0);
  assert.equal(r.pauseAttempts, 0); assert.equal(h.calls.includes('escape'), false); assert.equal(h.released, 1);
});

test('identity faults stop without action and a foreign or stale frame cannot authorize pause', async () => {
  for (const fault of ['stale', 'session', 'old']) {
    const h = harness({ faultAt: 1, fault }), r = await runner.run(h.initial, h.api, h.observe);
    assert.match(r.reason, /Fresh distinct same-session/); assert.equal(r.actionAttempts, 0, fault);
    assert.ok(r.pauseAttempts <= 1, fault); if (r.pauseVerified) assert.equal(r.pauseAttempts, 1, fault);
    assert.equal(h.actionCalls, 0, fault);
  }
});

test('focus guard polls read-only at most eight times, then pauses without repeating action', async () => {
  const h = harness({ readyAfter: 99 }), r = await runner.run(h.initial, h.api, h.observe);
  assert.match(r.reason, /did not become ready/); assert.equal(r.readOnlyPolls, 8);
  assert.equal(r.actionAttempts, 0); assert.equal(h.actionCalls, 0); assert.equal(r.pauseAttempts, 1);
});

test('platform readiness recovery at poll four or six allows one guarded action across fading null HP', async () => {
  for (const readyAtReads of [5, 7]) {
    const h = harness({ readyAtReads, nullHpAtReads: [2, 3] }), r = await runner.run(h.initial, h.api, h.observe);
    assert.equal(r.actionAttempts, 1, `ready frame ${readyAtReads}`); assert.equal(h.actionCalls, 1);
    assert.equal(r.readOnlyPolls, readyAtReads - 1); assert.deepEqual(r.healthBefore, { current: 800, max: 1000 });
  }
});

test('health drift and enemy bars abort readiness polling on the first unsafe frame', async () => {
  const hp = harness({ readyAfter: 99, pollHpDriftAt: 2 }), a = await runner.run(hp.initial, hp.api, hp.observe);
  assert.match(a.reason, /Health changed during/); assert.equal(a.readOnlyPolls, 1); assert.equal(a.actionAttempts, 0);
  const enemies = harness({ readyAfter: 99, enemyBarsAtReads: 2 }), b = await runner.run(enemies.initial, enemies.api, enemies.observe);
  assert.match(b.reason, /Enemy bars appeared/); assert.equal(b.readOnlyPolls, 1); assert.equal(b.actionAttempts, 0);
});

test('readiness polling preserves at least 2500ms for cleanup and action requires 4000ms remaining', async () => {
  const pollBudget = harness({ readyAfter: 99, extraDelayAt: 2, extraDelay: 12000 }), a = await runner.run(pollBudget.initial, pollBudget.api, pollBudget.observe);
  assert.match(a.reason, /15-second/); assert.equal(a.actionAttempts, 0); assert.equal(pollBudget.calls.includes('escape'), false);
  const actionBudget = harness({ extraDelayAt: 1, extraDelay: 10600 }), b = await runner.run(actionBudget.initial, actionBudget.api, actionBudget.observe);
  assert.match(b.reason, /15-second/); assert.equal(b.actionAttempts, 0); assert.equal(actionBudget.calls.includes('escape'), true);
});

test('focus loss after the action and changed HP stop further actions while cleanup releases', async () => {
  const focus = harness({ faultAt: 2, fault: 'focus' }), a = await runner.run(focus.initial, focus.api, focus.observe);
  assert.match(a.reason, /focus guard failed after/); assert.equal(a.actionAttempts, 1); assert.equal(focus.actionCalls, 1);
  const hp = harness({ hpAfter: 790 }), b = await runner.run(hp.initial, hp.api, hp.observe);
  assert.match(b.reason, /Health changed after/); assert.equal(b.actionAttempts, 1); assert.equal(hp.actionCalls, 1);
  assert.equal(focus.released, 1); assert.equal(hp.released, 1);
});

test('adapter, observation, and cancellation errors never repeat the action and always release', async () => {
  const h = harness(); h.api.wolfWitnessAction = async () => { h.calls.push('action-failed'); throw new Error('input failed'); };
  const a = await runner.run(h.initial, h.api, h.observe);
  assert.match(a.reason, /input failed/); assert.equal(a.actionAttempts, 1); assert.equal(h.released, 1);
  const observed = harness({ throwObserve: 1 }), b = await runner.run(observed.initial, observed.api, observed.observe);
  assert.match(b.reason, /observe failed/); assert.equal(b.actionAttempts, 0); assert.equal(observed.released, 1);
  const cancelled = harness({ cancel: true }), c = await runner.run(cancelled.initial, cancelled.api, cancelled.observe);
  assert.match(c.reason, /cancelled/); assert.equal(c.actionAttempts, 0); assert.equal(cancelled.released, 1);
});
