const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const engine = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/engine.js');
const recovery = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/recovery.js');
const source = fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'), 'utf8');

// Captured Blessing OCR, including the actual slash-as-seven reserve and Kaeya card.
function panel() {
  return { map: null, hud: { world: false, journal: false, bigMap: false, choice: false,
    dialogueReady: false, auto: false, climbing: false, health: null }, ocr: [
    { text: ' Click on the character portrait to restore HP', x: 213, y: 32, width: 567, height: 37 },
    { text: "Statue's Blessing", x: 1517, y: 25, width: 252, height: 48 },
    { text: 'Lv. 20', x: 440, y: 226, width: 79, height: 29 },
    { text: 'Restorative Power: 9196 710000', x: 1397, y: 597, width: 492, height: 29 },
    { text: 'UID: 693306810', x: 1684, y: 1050, width: 220, height: 20 },
  ] };
}

// Run the real engine, recovery branch and adapter gates with inert native boundaries.
function fixture(change = () => {}, options = {}) {
  let time = 100000, scene = 'panel', captures = 0, readyChecks = 0;
  const calls = [], writes = [], context = { Date: { now: () => time }, lastObservation: null,
    request: null, events: [], checkStop() { if (options.stop) throw Error('operator stop'); },
    click(x, y) { calls.push(['click', x, y]); if (options.expireAfterClick) time += 1001; },
    sleep: async ms => { time += ms; } };
  vm.runInNewContext(source, context);
  function method(name, async = false) {
    const label = name + ': ', start = source.lastIndexOf(label + (async ? 'async ' : '') + 'function (');
    const end = source.indexOf('\n        },', start);
    assert.ok(start > 0 && end > start, name);
    return vm.runInContext('(' + source.slice(start + label.length, end + '\n        }'.length) + ')', context);
  }
  const actualReady = method('statuePanelRecoveryReady');
  const api = {
    now: () => time, checkStop: context.checkStop, sleep: context.sleep,
    requireInputReady() {}, pinObservation() {}, release() { calls.push(['release']); },
    beginMission(request) { context.request = request; context.events = []; }, events: () => context.events,
    write(path, value) { writes.push([path, JSON.parse(value)]); },
    observe: async (session, frameId) => {
      time++; captures++;
      const o = { ...panel(), session, frameId, timestamp: time, screenshotPath: 'frame-' + frameId + '.png' };
      if (scene === 'world') { o.map = { map: 'Teyvat', x: -1323, y: 2566 }; Object.assign(o.hud,
        { world: true, groundControls: true, health: { current: options.finalHealth || 4015, max: 4015 } }); }
      if (scene === 'journal') o.hud.journal = true;
      change(o, frameId, calls);
      context.lastObservation = o;
      return o;
    },
    statuePanelRecoveryReady(o) {
      readyChecks++;
      if (options.changeAfterEngineCheck && readyChecks === 2) context.lastObservation = { ...o, frameId: o.frameId + 1 };
      return actualReady(o);
    },
    statuePanelRecoveryWorldReady: method('statuePanelRecoveryWorldReady'),
    statuePanelRecoveryPauseReady: method('statuePanelRecoveryPauseReady'),
    healTravelerAtStatue: method('healTravelerAtStatue', true),
    keyPress: async key => { calls.push(['key', key]); context.events.push({ type: 'key', key }); scene = 'world'; time += 60; },
    pauseCombat: async () => { calls.push(['key', 'VK_J']); context.events.push({ type: 'key', key: 'VK_J' }); scene = 'journal'; time += 60; return true; },
    // These input-producing fallbacks must stay unreachable from the scoped branch.
    forward() { throw Error('forbidden forward'); }, rotate() { throw Error('forbidden rotate'); },
    chooseStatueBlessing() { throw Error('forbidden Blessing choice'); },
    teleportToStarfell() { throw Error('forbidden teleport'); },
    wolfClosingCharacterRecoveryReady() { throw Error('generic pre-branch reached'); },
  };
  const runner = engine.create(api, { session: 'panel-test', enableInput: true });
  const request = (extra = {}) => ({ id: 'once', session: 'panel-test', expectedFrameId: runner.getFrame(),
    createdAt: time, mission: 'recover', statuePanelOnly: true, ...extra });
  const policy = { recover: recovery.run, recoverStatuePanel: recovery.runStatuePanel };
  return { api, runner, request, calls, writes, context, policy, captures: () => captures };
}

test('scope schema is opt-in true on recover only; absent flag preserves generic schema', () => {
  const base = { id: 'a', session: 's', expectedFrameId: 1, createdAt: 1000, mission: 'recover' };
  assert.equal(engine.validate(base, 's', 1, {}, 1000), null);
  assert.equal(engine.validate({ ...base, statuePanelOnly: true }, 's', 1, {}, 1000), null);
  for (const value of [false, null, 1, 0, 'true', {}, []])
    assert.match(engine.validate({ ...base, statuePanelOnly: value }, 's', 1, {}, 1000), /statuePanelOnly/);
  for (const mission of ['observe', 'stop', 'keyPress', 'look', 'navigation', 'dialogue', 'combat', 'questStep'])
    assert.match(engine.validate({ ...base, mission, statuePanelOnly: true }, 's', 1, {}, 1000), /statuePanelOnly/);
});

test('actual panel follows only five existing portrait callbacks then Escape and J', async () => {
  const f = fixture(); await f.runner.observe();
  assert.equal(await f.runner.process(f.request(), () => f.policy), 'completed');
  assert.equal(f.calls.filter(row => row[0] === 'click').length, 15);
  assert.deepEqual(f.calls.filter(row => row[0] === 'key'), [['key', 'VK_ESCAPE'], ['key', 'VK_J']]);
  const receipt = f.writes.filter(([path]) => path === 'receipt.json').at(-1)[1];
  assert.equal(receipt.details.result.statuePanelOnly, true);
  assert.equal(receipt.details.result.health.current, 4015);
  assert.equal(receipt.details.result.paused, true);
  const heals = f.context.events.filter(row => row.type === 'healStarterParty');
  assert.equal(heals.length, 5);
  assert.ok(heals.every(row => row.statuePanelOnly === true && Number.isInteger(row.frameId)));
  assert.equal(await f.runner.process(f.request(), () => f.policy), 'rejected', 'request cannot replay');
});

test('combined party heading and healing instruction allow scoped Statue recovery', async () => {
  const f = fixture(o => {
    if (o.map !== null || !o.ocr[0]) return;
    o.ocr[0] = { text: ' In combat Click on the character portrait to restore HP', x: 28, y: 34, width: 749, height: 29 };
  });
  await f.runner.observe();
  assert.equal(await f.runner.process(f.request(), () => f.policy), 'completed');
  assert.ok(f.calls.some(call => call[0] === 'click'));
});

test('fresh engine entry rejects changed menu, stale source, different session/UID, depletion and ambiguous Kaeya', async () => {
  const mutations = [
    o => { o.hud.world = true; }, o => { o.timestamp -= 1001; },
    o => { o.session = 'other'; }, o => { o.ocr[4].text = 'UID: 123456789'; },
    o => { o.ocr[3].text = 'Restorative Power: 0 / 10000'; },
    o => { o.ocr[3].text = 'Restorative Power: 0 710000'; },
    o => { o.ocr.splice(0, 1); }, o => { o.ocr[2].text = 'Lv. 19'; },
    o => { o.ocr[0] = { text: 'In combat Click on the character portrait to restore HP', x: 1200, y: 34, width: 749, height: 29 }; },
    o => { o.ocr.push({ ...o.ocr[2], text: 'Lv. 30' }); },
    o => { o.ocr.push({ ...o.ocr[3] }); },
  ];
  for (const mutate of mutations) {
    const f = fixture((o, frame) => { if (frame === 2) mutate(o); }); await f.runner.observe();
    await assert.rejects(f.runner.process(f.request(), () => f.policy), /Fresh original-account/);
    assert.equal(f.captures(), 2, 'refused scene cannot be polled into generic recovery');
    assert.deepEqual(f.calls.filter(row => row[0] !== 'release'), [], mutate.toString());
  }
});

test('a source substitution between engine admission and scoped entry sends no input', async () => {
  const f = fixture(() => {}, { changeAfterEngineCheck: true }); await f.runner.observe();
  await assert.rejects(f.runner.process(f.request(), () => f.policy), /Fresh original-account/);
  assert.deepEqual(f.calls.filter(row => row[0] !== 'release'), []);
  assert.equal(f.captures(), 2);
});

test('lost panel after one heal is terminal with no generic branch or further capture/input', async () => {
  const f = fixture((o, frame) => { if (frame >= 3) { o.ocr = []; o.hud.world = true; } });
  await f.runner.observe();
  await assert.rejects(f.runner.process(f.request(), () => f.policy), /panel did not return/);
  assert.equal(f.calls.filter(row => row[0] === 'click').length, 3);
  assert.equal(f.calls.filter(row => row[0] === 'key').length, 0);
  assert.equal(f.captures(), 3);
});

test('source expiry during a portrait callback stops remaining clicks and preserves failure', async () => {
  const f = fixture(() => {}, { expireAfterClick: true }); await f.runner.observe();
  await assert.rejects(f.runner.process(f.request(), () => f.policy), /source expired/);
  assert.equal(f.calls.filter(row => row[0] === 'click').length, 1);
  assert.equal(f.calls.filter(row => row[0] === 'key').length, 0);
  assert.equal(f.writes.filter(([path]) => path === 'receipt.json').at(-1)[1].status, 'failed');
});

test('partial health cannot be relabeled full Kaeya recovery', async () => {
  const f = fixture(() => {}, { finalHealth: 3900 }); await f.runner.observe();
  await assert.rejects(f.runner.process(f.request(), () => f.policy), /full original-account Kaeya/);
  assert.deepEqual(f.calls.filter(row => row[0] === 'key'), [['key', 'VK_ESCAPE']]);
});

test('full health waits passively for settled ground controls before the single journal key', async () => {
  let worldFrames = 0;
  const f = fixture(o => {
    if (o.hud.world && ++worldFrames <= 2) o.hud.groundControls = false;
  });
  await f.runner.observe();
  assert.equal(await f.runner.process(f.request(), () => f.policy), 'completed');
  assert.equal(worldFrames, 3);
  assert.equal(f.context.events.filter(row => row.type === 'healStarterParty').length, 5);
  assert.deepEqual(f.calls.filter(row => row[0] === 'key'), [['key', 'VK_ESCAPE'], ['key', 'VK_J']]);
});

test('missing ground controls exhaust the existing passive budget without another heal or pause key', async () => {
  let worldFrames = 0;
  const f = fixture(o => {
    if (o.hud.world) { worldFrames++; o.hud.groundControls = false; }
  });
  await f.runner.observe();
  await assert.rejects(f.runner.process(f.request(), () => f.policy), /full original-account Kaeya/);
  assert.equal(worldFrames, 7);
  assert.equal(f.context.events.filter(row => row.type === 'healStarterParty').length, 5);
  assert.deepEqual(f.calls.filter(row => row[0] === 'key'), [['key', 'VK_ESCAPE']]);
});

test('repeated source time and foreign-account journal cannot finish the scoped branch', async () => {
  for (const mutate of [
    (o, frame) => { if (frame === 3) o.timestamp = 100002; },
    o => { if (o.hud.journal) o.ocr[4].text = 'UID: 123456789'; },
  ]) {
    const f = fixture(mutate); await f.runner.observe();
    await assert.rejects(f.runner.process(f.request(), () => f.policy), /same-session source|original-account evidence/);
    assert.equal(f.writes.filter(([path]) => path === 'receipt.json').at(-1)[1].status, 'failed');
  }
});

test('the absent flag still dispatches exactly the original generic recovery function', async () => {
  const f = fixture(); await f.runner.observe();
  let generic = 0, scoped = 0;
  const request = f.request(); delete request.statuePanelOnly;
  assert.equal(await f.runner.process(request, () => ({
    recover: async () => { generic++; return { status: 'completed' }; },
    recoverStatuePanel: async () => { scoped++; throw Error('wrong branch'); },
  })), 'completed');
  assert.equal(generic, 1); assert.equal(scoped, 0);
});

module.exports = { fixture, panel };
