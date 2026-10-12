const test = require('node:test');
const assert = require('node:assert/strict');
const runner = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/windrise-reveal.js');

function frame(id, now, hp = 1186, patch = {}) {
  return { session: 'windrise-session', frameId: id, timestamp: now, capture: { width: 1920, height: 1080 },
    map: null, ocr: [{ text: 'Amber', x: 1600, y: 400 }, { text: 'Kaeya', x: 1600, y: 450 }],
    hud: { world: true, groundControls: true, climbing: false, auto: false, dialogueReady: false, choice: false,
      journal: false, bigMap: false, tutorialStep: null, enemyBars: [],
      objectives: ['Meet Lisa at the temple'], health: { current: hp, max: 1186 } }, ...patch };
}
function harness({ plan = { action: 'forward', holds: 6 }, hpAfter = null, ready = true, permit = true, cancelAtAction = false,
  pause = true, badHud = false, statue = false, postInteractionPatch = {}, statueApiReady = true, enemyBars = [],
  enemyBarsAfterActionAt = Infinity, persistentBigMap = false, postActionGroundFalse = false, groundFalseObservations = 0 } = {}) {
  let now = 1000, id = 1, calls = [], actionCount = 0, observeCount = 0, released = 0;
  const initial = frame(id, now, 1186, badHud ? { hud: { ...frame(1, 1000).hud, bigMap: true } } : {});
  initial.hud.enemyBars = enemyBars;
  if (statue) initial.ocr.push({ text: 'Statue   of The Seven', x: 1200, y: 515, width: 270, height: 30 },
    { text: 'F', x: 1120, y: 540, width: 30, height: 30 });
  const nextFrame = () => { id++; const n = frame(id, now, hpAfter !== null && actionCount > 0 ? hpAfter : 1186);
    if (persistentBigMap) n.hud.bigMap = true;
    if (postActionGroundFalse && actionCount === 1 && id === 2 && plan.action !== 'interact') n.hud.groundControls = false;
    if (actionCount >= enemyBarsAfterActionAt) n.hud.enemyBars = [{ text: 'Lv. 3 Hydro Slime' }];
    return actionCount > 0 && plan.action === 'interact' ? { ...n, ...postInteractionPatch,
      hud: { ...n.hud, ...(postInteractionPatch.hud || {}) }, ocr: postInteractionPatch.ocr || n.ocr } : n; };
  const api = { now: () => now, checkStop: () => { if (cancelAtAction && actionCount) throw new Error('cancelled'); },
    windriseRevealReady: o => ready && o.hud.bigMap === false && o.hud.groundControls === true && (plan.action === 'retreat' || o.hud.enemyBars.length === 0),
    windriseRevealPlan: () => plan,
    windriseRevealStatueReady: () => statueApiReady,
    windriseRevealConsumePermit: () => { calls.push('permit'); return permit; },
    windriseRevealAction: async (action, amount) => { calls.push([action, amount]); actionCount++; now += action === 'forward' ? 500 : action === 'interact' ? 60 : 20; },
    sleep: async ms => { calls.push(['sleep', ms]); now += ms; },
    windriseRevealPause: async o => { calls.push(['pause', o.frameId]); return pause; },
    release: () => { released++; calls.push('release'); } };
  const observe = async () => { calls.push('observe'); now += 1; const o = nextFrame(); observeCount++;
    if (observeCount <= groundFalseObservations) o.hud.groundControls = false; return o; };
  return { initial, api, observe, calls, get released() { return released; }, run: () => runner.run(initial, api, observe) };
}

test('safe completion stays within six 500ms holds and pauses from a fresh field frame', async () => {
  const h = harness(), r = await h.run();
  assert.equal(r.rootDirected, true); assert.equal(r.moves, 6); assert.equal(r.turns, 0);
  assert.equal(r.pausedInventory, true); assert.equal(r.frameId, 8); assert.equal(r.inputMs, 3000);
  assert.match(r.reason, /not verified/); assert.equal(r.questComplete, false); assert.equal(h.released, 1);
});

test('health loss over five percent stops before another hold but still permits a fresh field pause', async () => {
  const h = harness({ hpAfter: 1100 }), r = await h.run();
  assert.equal(r.moves, 1); assert.equal(h.calls.filter(x => Array.isArray(x) && x[0] === 'forward').length, 1);
  assert.equal(r.pausedInventory, true); assert.match(r.reason, /Health dropped more than 5%/); assert.equal(h.released, 1);
});

test('unsafe HUD and failed permit cause zero game input', async () => {
  for (const opt of [{ badHud: true }, { permit: false }]) {
    const h = harness(opt), r = await h.run();
    assert.equal(r.moves, 0); assert.equal(r.turns, 0); assert.equal(r.inputMs, 0); assert.equal(r.pausedInventory, false);
    assert.equal(h.calls.some(x => Array.isArray(x) && ['forward', 'look', 'pause'].includes(x[0])), false);
    assert.equal(h.released, 1);
  }
});

test('pause failure is reported honestly and one look is bounded to 250', async () => {
  const failed = harness({ pause: false }), a = await failed.run();
  assert.equal(a.pausedInventory, false); assert.equal(a.moves, 6); assert.match(a.reason, /pause was not verified/);
  const looked = harness({ plan: { action: 'look', dx: -250 } }), b = await looked.run();
  assert.equal(b.turns, 1); assert.equal(b.moves, 0); assert.deepEqual(looked.calls.find(x => Array.isArray(x) && x[0] === 'look'), ['look', -250]);
});

test('invalid plan, focus loss, and cancellation release without unsafe retries', async () => {
  const bad = harness({ plan: { action: 'forward', holds: 25 } }), a = await bad.run();
  assert.equal(a.moves, 0); assert.equal(bad.released, 1);
  const overLimit = harness({ plan: { action: 'forward', holds: 25 } }), over = await overLimit.run();
  assert.equal(over.moves, 0); assert.match(over.reason, /1 to 24/); assert.equal(overLimit.calls.filter(x => x === 'permit').length, 0);
  const focus = harness({ ready: false }), b = await focus.run();
  assert.equal(b.moves, 0); assert.equal(focus.released, 1);
  const cancelled = harness({ cancelAtAction: true, plan: { action: 'forward', holds: 2 } }), c = await cancelled.run();
  assert.equal(c.moves, 1); assert.match(c.reason, /cancelled/); assert.equal(cancelled.released, 1);
});

test('field readiness enforces freshness, health, HUD, quest and required roster evidence', () => {
  const good = frame(12, 1000);
  assert.equal(runner.fieldReady(good, 1100, 'windrise-session'), true);
  assert.equal(runner.fieldReady({ ...good, timestamp: 0 }, 1100, 'windrise-session'), false);
  assert.equal(runner.fieldReady(frame(12, 1000, 700), 1100, 'windrise-session'), false);
  for (const patch of [
    { ocr: [...good.ocr, { text: 'Trial', x: 900, y: 500 }] }, { hud: { ...good.hud, enemyBars: [{}] } },
    { hud: { ...good.hud, objectives: ['Meet Lisa at the temple', 'Meet Lisa at the temple'] } },
    { ocr: [{ text: 'Amber', x: 1600, y: 400 }] }, { capture: { width: 1280, height: 720 } },
  ]) assert.equal(runner.fieldReady({ ...good, ...patch }, 1100, 'windrise-session'), false);
  assert.equal(runner.fieldPauseReady(frame(13, 1000, 100), 1100, 'windrise-session'), true);
});

test('Lisa objective readiness normalizes OCR diacritics without accepting different words', () => {
  const good = frame(12, 1000);
  for (const objective of ['Méet Lisa at the temple', 'Meet Liša at the temple', 'Meet Liśa at the temple', 'Mèet Liśa at the temple']) {
    const observed = { ...good, hud: { ...good.hud, objectives: [objective] } };
    assert.equal(runner.fieldReady(observed, 1100, 'windrise-session'), true, objective);
  }
  const wrong = { ...good, hud: { ...good.hud, objectives: ['Meet Lysa at the temple'] } };
  assert.equal(runner.fieldReady(wrong, 1100, 'windrise-session'), false);
});

test('fresh unique statue and F evidence permits exactly one bounded interaction and observes post-action frame', async () => {
  const h = harness({ plan: { action: 'interact' }, statue: true, postInteractionPatch: { hud: { groundControls: false, world: false } } });
  const r = await h.run();
  assert.deepEqual(h.calls.filter(x => Array.isArray(x) && ['interact', 'forward', 'look'].includes(x[0])), [['interact', 60]]);
  assert.equal(r.interactions, 1); assert.equal(r.moves, 0); assert.equal(r.turns, 0); assert.equal(r.frameId, 2);
  assert.equal(r.pausedInventory, false); assert.match(r.reason, /unlock animation observed/); assert.equal(r.questComplete, false);
  assert.equal(h.calls.filter(x => Array.isArray(x) && x[0] === 'pause').length, 0);
});

test('statue interaction rejects wrong, missing, duplicate, malformed prompt, overlay, stale and low-HP evidence', async () => {
  const variants = [
    { rows: [{ text: 'Statue of The Seven', x: 1200, y: 515, width: 270, height: 30 }, { text: 'F', x: 1120, y: 540, width: 30, height: 30 }], statueApiReady: false },
    { rows: [{ text: 'Wrong Statue', x: 1200, y: 515, width: 270, height: 30 }, { text: 'F', x: 1120, y: 540, width: 30, height: 30 }] },
    { rows: [{ text: 'Statue of the Seven', x: 1200, y: 515, width: 270, height: 30 }, { text: 'F', x: 1120, y: 540, width: 30, height: 30 }] },
    { rows: [{ text: 'Statue of The Seven', x: 1200, y: 515, width: 270, height: 30 }] },
    { rows: [{ text: 'Statue of The Seven', x: 1200, y: 515, width: 270, height: 30 }, { text: 'F', x: 1120, y: 540, width: 30, height: 30 },
      { text: 'Statue of The Seven', x: 1205, y: 515, width: 270, height: 30 }] },
    { rows: [{ text: 'Statue of The Seven', x: 1200, y: 515, width: 270, height: 30 }, { text: 'F', x: 1120, y: 540, width: 30, height: 30 }, { text: 'F', x: 1140, y: 540, width: 30, height: 30 }] },
    { rows: [{ text: 'Statue of The Seven', x: 1200, y: 515, width: 270, height: 30 }, { text: 'F', x: 1300, y: 540, width: 30, height: 30 }] },
    { rows: [{ text: 'Statue of The Seven', x: 1200, y: 515, width: 270, height: 30 }, { text: 'F', x: 1120, y: 540, width: 61, height: 30 }] },
  ];
  for (const variant of variants) {
    const h = harness({ plan: { action: 'interact' }, statue: true });
    h.initial.ocr = [...h.initial.ocr.filter(r => r.text !== 'Statue   of The Seven' && r.text !== 'F'), ...variant.rows];
    if (variant.statueApiReady === false) h.api.windriseRevealStatueReady = () => false;
    const r = await h.run(); assert.equal(r.interactions, 0); assert.equal(r.inputMs, 0);
    assert.equal(h.calls.some(x => Array.isArray(x) && ['interact', 'forward', 'look', 'pause'].includes(x[0])), false);
  }
  const stale = harness({ plan: { action: 'interact' }, statue: true }); stale.initial.timestamp -= 1001;
  const staleResult = await stale.run(); assert.equal(staleResult.interactions, 0);
  for (const patch of [{ hud: { bigMap: true } }, { hud: { health: { current: 700, max: 1186 } } }]) {
    const h = harness({ plan: { action: 'interact' }, statue: true }); Object.assign(h.initial.hud, patch.hud);
    const r = await h.run(); assert.equal(r.interactions, 0);
  }
  const staleAfter = harness({ plan: { action: 'interact' }, statue: true, postInteractionPatch: { timestamp: 1000 } });
  const staleAfterResult = await staleAfter.run(); assert.equal(staleAfterResult.interactions, 1);
  assert.match(staleAfterResult.reason, /post-interaction frame/); assert.equal(staleAfterResult.pausedInventory, false);
  assert.equal(staleAfter.calls.filter(x => Array.isArray(x) && x[0] === 'pause').length, 0);
  const hpAfter = harness({ plan: { action: 'interact' }, statue: true,
    postInteractionPatch: { hud: { health: null, groundControls: false, dialogueReady: true } } });
  const hpAfterResult = await hpAfter.run(); assert.equal(hpAfterResult.interactions, 1);
  assert.match(hpAfterResult.reason, /unlock animation observed/); assert.equal(hpAfterResult.pausedInventory, false);
});

test('retreat permits bounded holds through enemy bars while retaining field and HP guards', async () => {
  const plan = { action: 'retreat', holds: 3 };
  const h = harness({ plan, enemyBars: [{ text: 'Lv. 3 Hydro Slime' }] });
  const r = await h.run();
  assert.deepEqual(h.calls.filter(x => Array.isArray(x) && ['forward', 'retreat', 'look'].includes(x[0])),
    [['retreat', 500], ['retreat', 500], ['retreat', 500]]);
  assert.equal(r.retreats, 3); assert.equal(r.moves, 0); assert.equal(r.turns, 0); assert.equal(r.interactions, 0);
  assert.equal(r.pausedInventory, true); assert.equal(h.released, 1);
  assert.equal(runner.retreatReady(h.initial, 1000, 'windrise-session'), true);
  assert.equal(runner.fieldReady(h.initial, 1000, 'windrise-session'), false, 'enemy bars remain disallowed for forward movement');
});

test('retreat rejects low HP, stale and UI-blocked frames; forward remains blocked by enemies', async () => {
  const cases = [
    h => { h.initial.hud.health.current = 700; },
    h => { h.initial.timestamp = -1; },
    h => { h.initial.hud.journal = true; },
  ];
  for (const mutate of cases) {
    const h = harness({ plan: { action: 'retreat', holds: 2 }, enemyBars: [{}] }); mutate(h);
    const r = await h.run(); assert.equal(r.retreats, 0); assert.equal(r.inputMs, 0);
    assert.equal(h.calls.some(x => Array.isArray(x) && ['retreat', 'forward', 'look'].includes(x[0])), false);
  }
  const forward = harness({ plan: { action: 'forward', holds: 2 }, enemyBars: [{ text: 'Lv. 3 Hydro Slime' }] });
  const f = await forward.run(); assert.equal(f.moves, 0); assert.equal(f.retreats, 0);
  assert.equal(forward.calls.some(x => Array.isArray(x) && ['retreat', 'forward'].includes(x[0])), false);
  const damaged = harness({ plan: { action: 'retreat', holds: 2 }, enemyBars: [{}], hpAfter: 1100 });
  const d = await damaged.run(); assert.equal(d.retreats, 1); assert.equal(d.pausedInventory, true);
  assert.match(d.reason, /Health dropped more than 5%/);
});

test('enemy-blocked initial readiness may consume one pause-only permit and pause from a fresh field frame', async () => {
  for (const hp of [1186, 400]) {
    const h = harness({ ready: false, enemyBars: [{ text: 'Lv. 3 Hydro Slime' }] });
    h.initial.hud.health.current = hp;
    let pausePermitCalls = 0;
    h.api.windriseRevealConsumePausePermit = o => { pausePermitCalls++; return o === h.initial; };
    const r = await h.run();
    assert.equal(r.moves, 0); assert.equal(r.retreats, 0); assert.equal(r.turns, 0); assert.equal(r.interactions, 0);
    assert.equal(r.pausedInventory, true); assert.equal(pausePermitCalls, 1);
    assert.equal(h.calls.filter(x => x === 'permit').length, 0, 'movement permit is never requested');
    assert.equal(h.calls.filter(x => Array.isArray(x) && x[0] === 'pause').length, 1);
    assert.equal(h.released, 1);
  }
});

test('invalid pause-only permit or invalid field frame produces no input and is never retried', async () => {
  const invalidPermit = harness({ ready: false, enemyBars: [{}] }); let calls = 0;
  invalidPermit.api.windriseRevealConsumePausePermit = () => { calls++; return false; };
  const a = await invalidPermit.run();
  assert.equal(a.moves + a.retreats + a.turns + a.interactions, 0); assert.equal(a.pausedInventory, false);
  assert.equal(calls, 1); assert.equal(invalidPermit.calls.filter(x => x === 'permit').length, 0);
  assert.equal(invalidPermit.calls.some(x => Array.isArray(x) && x[0] === 'pause'), false);

  const unsafe = harness({ ready: false, enemyBars: [{}], persistentBigMap: true }); calls = 0;
  unsafe.initial.hud.bigMap = true;
  unsafe.api.windriseRevealConsumePausePermit = () => { calls++; return true; };
  const b = await unsafe.run();
  assert.equal(b.moves + b.retreats + b.turns + b.interactions, 0); assert.equal(calls, 0);
  assert.equal(unsafe.calls.some(x => Array.isArray(x) && x[0] === 'pause'), false);
});

test('pause-only recovery retries transient initial ground loss and consumes permit only on a safe fresh capture', async () => {
  const h = harness({ ready: false, groundFalseObservations: 1 });
  h.initial.hud.groundControls = false;
  let permitFrames = [];
  h.api.windriseRevealConsumePausePermit = o => { permitFrames.push(o.frameId); return runner.fieldPauseReady(o, h.api.now(), 'windrise-session'); };
  const r = await h.run();
  assert.equal(r.moves + r.retreats + r.turns + r.interactions, 0); assert.equal(r.pausedInventory, true);
  assert.deepEqual(permitFrames, [3], 'first recovery capture is unsafe; permit is consumed only on the next field frame');
  assert.deepEqual(h.calls.filter(x => Array.isArray(x) && x[0] === 'sleep'), [['sleep', 200]]);
  assert.equal(h.calls.filter(x => Array.isArray(x) && x[0] === 'pause').length, 1); assert.equal(h.released, 1);
});

test('post-move stagger frame retries to a safe pause; persistent unknown UI never opens the journal', async () => {
  const stagger = harness({ plan: { action: 'forward', holds: 4 }, postActionGroundFalse: true, groundFalseObservations: 1 });
  const s = await stagger.run();
  assert.equal(s.moves, 1); assert.match(s.reason, /focus guard failed after movement/);
  assert.equal(s.pausedInventory, true); assert.equal(stagger.calls.filter(x => Array.isArray(x) && x[0] === 'pause').length, 1);
  assert.equal(stagger.released, 1);

  const unknown = harness({ ready: false, persistentBigMap: true }); unknown.initial.hud.bigMap = true;
  let permits = 0; unknown.api.windriseRevealConsumePausePermit = () => { permits++; return true; };
  const u = await unknown.run();
  assert.equal(u.pausedInventory, false); assert.equal(permits, 0);
  assert.equal(unknown.calls.filter(x => Array.isArray(x) && x[0] === 'pause').length, 0);
  assert.equal(unknown.calls.filter(x => x === 'observe').length, 3); assert.equal(unknown.released, 1);
});

test('twenty-four fixed holds remain bounded and finish within the thirty-five second capture budget', async () => {
  const h = harness({ plan: { action: 'forward', holds: 24 } }), r = await h.run();
  assert.equal(r.moves, 24); assert.equal(r.retreats, 0); assert.equal(r.inputMs, 12000);
  assert.equal(h.calls.filter(x => Array.isArray(x) && x[0] === 'forward').length, 24);
  assert.equal(h.calls.filter(x => x === 'observe').length, 25, 'fresh capture after each hold plus fresh pause capture');
  assert.equal(r.pausedInventory, true); assert.ok(r.elapsedMs < 35000); assert.equal(h.released, 1);
});

test('a new enemy or over-five-percent HP loss midway stops the longer route and pauses safely', async () => {
  const enemy = harness({ plan: { action: 'forward', holds: 24 }, enemyBarsAfterActionAt: 3 });
  const e = await enemy.run();
  assert.equal(e.moves, 3); assert.match(e.reason, /input focus guard failed after movement/);
  assert.equal(e.pausedInventory, true); assert.equal(enemy.released, 1);
  const hp = harness({ plan: { action: 'forward', holds: 24 }, hpAfter: 1100 });
  const h = await hp.run();
  assert.equal(h.moves, 1); assert.match(h.reason, /Health dropped more than 5%/);
  assert.equal(h.pausedInventory, true); assert.equal(hp.released, 1);
});
