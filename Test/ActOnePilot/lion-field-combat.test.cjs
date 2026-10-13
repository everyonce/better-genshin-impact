'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const lionFight = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/lion-field-combat.js');

function field(patch = {}) {
  return { session: 's1', frameId: 10, timestamp: 1000, map: null,
    hud: { world: true, groundControls: true, climbing: false, journal: false, bigMap: false,
      dialogueReady: false, choice: false, auto: false, unknownHud: false, tutorialStep: null,
      health: { current: 1067, max: 1186 }, objectives: ['Meet Lisa at the temple'],
      enemyBars: [{ x: 900, y: 300, width: 100, height: 5 }] }, ...patch };
}
function inventory() {
  return { session: 's1', frameId: 9, timestamp: 1000, map: null, ocr: [{ text: 'Food', x: 150, y: 40 }],
    hud: { world: false, groundControls: false, journal: false, bigMap: false, dialogueReady: false, choice: false } };
}
function harness(opts = {}) {
  let clock = 1000, frame = 10;
  const calls = [];
  const api = {
    now: () => clock,
    checkStop() { calls.push('checkStop'); },
    async sleep(ms) { calls.push(['sleep', ms]); clock += ms; },
    async release() { calls.push('release'); },
    lionFieldInventoryReady(o, now) { return !!(o && o.map === null && Array.isArray(o.ocr) && o.ocr.some(r => r.text === 'Food') && now - o.timestamp <= 1000 && !o.ocr.some(r => r.text === 'Confirm')); },
    lionFieldProbeOnly() { return opts.probeOnly === true; },
    async lionFieldCloseInventory() { calls.push('close'); clock += 20; },
    lionFieldReady(o) { return o.hud.world && o.hud.partyReady !== false && o.hud.objectives.some(s => lionFight.compact(s) === 'meetlisaatthetemple') && !o.ocr?.some(r => r.text === 'Trial'); },
    async lionFieldSelectKaeya() { calls.push('select3'); clock += 10; },
    async lionFieldReturnAmber() { calls.push('returnAmber'); clock += 10; },
    async lionFieldFight() { calls.push('fight'); clock += 1200; if (opts.fightError) throw new Error('native timeout'); },
    async lionFieldPause() { calls.push('pause'); return opts.pauseResult !== false; },
  };
  const observe = async () => {
    calls.push('observe');
    clock += 10;
    frame++;
    const value = opts.observe ? opts.observe(frame, clock) : field({ frameId: frame, timestamp: clock });
    return value;
  };
  return { api, observe, calls, get clock() { return clock; } };
}

test('refuses wrong Lisa objective or trial party before selecting or fighting', async () => {
  for (const bad of [
    field({ hud: { ...field().hud, objectives: ['Meet Kaeya at the temple'] } }),
    field({ ocr: [{ text: 'Trial', x: 1700, y: 450 }] }),
  ]) {
    const h = harness({ observe(frame, clock) { return field({ frameId: frame, timestamp: clock, ...bad }); } });
    const result = await lionFight.run(inventory(), h.api, h.observe);
    assert.equal(result.status, 'stopped');
    assert.equal(result.kaeyaSelectAttempted, false);
    assert.equal(result.fightStarted, false);
    assert.equal(h.calls.includes('select3'), false);
    assert.equal(h.calls.includes('fight'), false);
  }
  const h = harness();
  const result = await lionFight.run(field({ ocr: [] }), h.api, h.observe);
  assert.equal(result.reason, 'Fresh recognized safe Food inventory required');
  assert.equal(h.calls.includes('close'), false);
});

test('normalizes exact Lisa objective punctuation but rejects other text, objective transitions, and impossible HP', () => {
  const now = 1100, base = field({ timestamp: 1050, frameId: 11 });
  assert.equal(lionFight.safeWorld({ ...base, hud: { ...base.hud, objectives: ['Meet.Lisa at the temple'] } }, now, 's1', field(), true), true);
  for (const patch of [
    { objectives: ['Meet Lisa in the temple'] },
    { objectives: ['Meet Lisa at the temple'], objectiveChanged: true },
    { objectives: ['Meet Lisa at the temple'], health: { current: 1200, max: 1186 } },
  ]) {
    const bad = { ...base, hud: { ...base.hud, ...patch } };
    assert.equal(lionFight.safeWorld(bad, now, 's1', field(), true), false);
  }
  const injured = { ...base, hud: { ...base.hud, health: { current: 500, max: 1186 } } };
  assert.equal(lionFight.knownWorld(injured, now, 's1', field()), true, 'positive health below 60% can still be paused safely');
  assert.equal(lionFight.knownWorld({ ...injured, hud: { ...injured.hud, health: { current: 1187, max: 1186 } } }, now, 's1', field()), false);
  assert.equal(lionFight.knownWorld({ ...injured, hud: { ...injured.hud, objectiveChanged: true } }, now, 's1', field()), false);
  assert.equal(lionFight.compact('Méet.Liša at the temple'), 'meetlisaatthetemple');
  assert.equal(lionFight.compact('Meet Liśa at the temple'), 'meetlisaatthetemple');
});

test('confirmed low health stops transition polling immediately and pauses without a switch',async()=>{
  const h=harness({observe(frame,clock){return field({frameId:frame,timestamp:clock,hud:{...field().hud,health:{current:496,max:1057}}});}});
  const result=await lionFight.run(inventory(),h.api,h.observe);
  assert.equal(result.fieldPolls,1);assert.equal(result.kaeyaSelectAttempted,false);assert.equal(result.fightStarted,false);
  assert.ok(h.calls.includes('pause'));assert.match(result.reason,/Confirmed low health/);
});

test('waits through initial transition frames and accepts exact Lisa objective with diacritics', async () => {
  const h = harness({ observe(frame, clock) {
    if (frame < 16) return field({ frameId: frame, timestamp: clock, hud: { ...field().hud, objectives: ['Approach the temple'] } });
    return field({ frameId: frame, timestamp: clock, hud: { ...field().hud, objectives: ['Méet.Liša at the temple'] } });
  } });
  const result = await lionFight.run(inventory(), h.api, h.observe);
  assert.equal(result.fieldPolls, 6);
  assert.equal(result.kaeyaSelectAttempted, true);
  assert.equal(result.fightStarted, true);
  assert.equal(h.calls.filter(x => Array.isArray(x) && x[0] === 'sleep' && x[1] === 150).length, 5);
});

test('retries fresh post-selection party OCR and accepts recovered owned Kaeya slot 3 without another switch', async () => {
  const h = harness({ observe(frame, clock) {
    const partyReady = frame !== 12;
    return field({ frameId: frame, timestamp: clock, hud: { ...field().hud, partyReady } });
  } });
  const result = await lionFight.run(inventory(), h.api, h.observe);
  assert.equal(result.kaeyaSelectAttempted, true);
  assert.equal(result.postSelectionPolls, 2);
  assert.equal(result.fightStarted, true);
  assert.equal(h.calls.filter(x => x === 'select3').length, 1);
  assert.equal(h.calls.filter(x => x === 'fight').length, 1);
});

test('persistent unknown post-selection HUD never repeats switch or sends native fight, Amber, or pause input', async () => {
  const h = harness({ observe(frame, clock) {
    if (frame >= 12) return { ...field({ frameId: frame, timestamp: clock }), hud: { world: false, unknownHud: true } };
    return field({ frameId: frame, timestamp: clock });
  } });
  const result = await lionFight.run(inventory(), h.api, h.observe);
  assert.equal(result.kaeyaSelectAttempted, true);
  assert.equal(result.fightStarted, false);
  assert.equal(result.enemyClearVerified, false);
  assert.equal(h.calls.filter(x => x === 'select3').length, 1);
  assert.equal(h.calls.includes('fight'), false);
  assert.equal(h.calls.includes('returnAmber'), false);
  assert.equal(h.calls.includes('pause'), false);
});

test('probe mode returns field evidence without selection or combat and still pauses safely', async () => {
  const h = harness({ probeOnly: true, observe(frame, clock) {
    return field({ frameId: frame, timestamp: clock, map: null, hud: { ...field().hud, compassAngle: 42 } });
  } });
  const result = await lionFight.run(inventory(), h.api, h.observe);
  assert.equal(result.step, 'lionFieldProbe');
  assert.deepEqual(JSON.parse(JSON.stringify(result.fieldProbe)), {
    frameId: 11, health: { current: 1067, max: 1186 }, objectives: ['Meet Lisa at the temple'],
    enemyBars: [{ x: 900, y: 300, width: 100, height: 5 }], compassAngle: 42,
  });
  assert.equal(result.fightStarted, false);
  assert.equal(result.kaeyaSelectAttempted, false);
  assert.equal(result.enemyClearVerified, false);
  assert.equal(result.pauseVerified, true);
  assert.equal(h.calls.includes('select3'), false);
  assert.equal(h.calls.includes('fight'), false);
  assert.equal(h.calls.includes('returnAmber'), false);
  assert.equal(h.calls.filter(x => x === 'pause').length, 1);
});

test('probe capture error during cleanup retries observation and safely pauses without selection', async () => {
  let observations = 0;
  const h = harness({ probeOnly: true, observe(frame, clock) {
    observations++;
    if (observations === 2) throw new Error('temporary capture failure');
    return field({ frameId: frame, timestamp: clock });
  } });
  const result = await lionFight.run(inventory(), h.api, h.observe);
  assert.equal(result.step, 'lionFieldProbe');
  assert.equal(result.pauseVerified, true);
  assert.match(result.releaseError, /temporary capture failure/);
  assert.equal(h.calls.includes('select3'), false);
  assert.equal(h.calls.includes('fight'), false);
  assert.equal(h.calls.filter(x => x === 'pause').length, 1);
});

test('attempts Kaeya once, fights once only with fresh enemy bar, releases, and verifies pause without party recovery', async () => {
  const h = harness();
  const result = await lionFight.run(inventory(), h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.equal(result.kaeyaSelectAttempted, true);
  assert.equal(result.fightStarted, true);
  assert.equal(result.enemyClearVerified, false);
  assert.equal(result.pauseVerified, true);
  assert.equal(result.amberReturnAttempted, false);
  assert.equal(h.calls.filter(x => x === 'select3').length, 1);
  assert.equal(h.calls.filter(x => x === 'fight').length, 1);
  assert.equal(h.calls.includes('returnAmber'), false);
  assert.equal(h.calls.filter(x => x === 'pause').length, 1);
  assert.deepEqual(h.calls.slice(-2), ['observe', 'pause']);
  assert.equal(h.calls.at(-1), 'pause');
  assert.ok(h.calls.includes('release'));
});

test('does not fight when the post-selection frame is stale, hurt, or has no enemy bar', async () => {
  for (const change of [
    (o) => ({ ...o, timestamp: 0 }),
    (o) => ({ ...o, hud: { ...o.hud, health: { current: 700, max: 1186 } } }),
    (o) => ({ ...o, hud: { ...o.hud, enemyBars: [] } }),
  ]) {
    const h = harness({ observe(frame, clock) { return frame === 11 ? field({ frameId: frame, timestamp: clock }) : change(field({ frameId: frame, timestamp: clock })); } });
    const result = await lionFight.run(inventory(), h.api, h.observe);
    assert.equal(result.fightStarted, false);
    assert.equal(h.calls.includes('fight'), false);
    assert.ok(h.calls.includes('release'));
  }
});

test('native failure still releases and requests a single safe pause without claiming a clear', async () => {
  const h = harness({ fightError: true });
  const result = await lionFight.run(inventory(), h.api, h.observe);
  assert.match(result.reason, /native timeout/);
  assert.equal(result.fightStarted, true);
  assert.equal(result.enemyClearVerified, false);
  assert.equal(result.amberReturnAttempted, false);
  assert.equal(result.nativeFightMs, 1200);
  assert.ok(h.calls.includes('release'));
  assert.equal(h.calls.includes('returnAmber'), false);
  assert.equal(h.calls.filter(x => x === 'pause').length, 1);
});

test('low-health native failure captures known field and pauses without party input after the error', async () => {
  const h = harness({ fightError: true, observe(frame, clock) {
    return field({ frameId: frame, timestamp: clock, hud: { ...field().hud,
      health: frame >= 14 ? { current: 500, max: 1186 } : { current: 1067, max: 1186 } } });
  } });
  const result = await lionFight.run(inventory(), h.api, h.observe);
  assert.match(result.reason, /native timeout/);
  assert.equal(result.pauseVerified, true);
  assert.equal(result.amberReturnAttempted, false);
  assert.equal(h.calls.filter(x => x === 'pause').length, 1);
  const failureIndex = h.calls.indexOf('fight');
  assert.equal(h.calls.slice(failureIndex + 1).some(x => x === 'returnAmber' || x === 'select3'), false);
  assert.deepEqual(h.calls.slice(-2), ['observe', 'pause']);
});

test('unknown screen after fight receives no blind pause input', async () => {
  const h = harness({ observe(frame, clock) {
    return frame > 12 ? { ...field({ frameId: frame, timestamp: clock }), hud: { world: false, unknownHud: true } } : field({ frameId: frame, timestamp: clock });
  } });
  const result = await lionFight.run(inventory(), h.api, h.observe);
  assert.equal(result.pauseVerified, false);
  assert.equal(result.amberReturnAttempted, false);
  assert.equal(h.calls.includes('pause'), false);
  assert.equal(h.calls.includes('returnAmber'), false);
  assert.ok(h.calls.includes('release'));
});

test('retries capture-only cleanup through transient unknown frames, then pauses once', async () => {
  const h = harness({ observe(frame, clock) {
    if (frame === 13 || frame === 14) return { ...field({ frameId: frame, timestamp: clock }), hud: { world: false, unknownHud: true } };
    return field({ frameId: frame, timestamp: clock });
  } });
  const result = await lionFight.run(inventory(), h.api, h.observe);
  assert.equal(result.amberReturnAttempted, false);
  assert.equal(result.pauseVerified, true);
  assert.equal(h.calls.includes('returnAmber'), false);
  assert.equal(h.calls.filter(x => x === 'pause').length, 1);
});

test('module loads without CommonJS globals for ClearScript', () => {
  const context = {};
  vm.runInNewContext(fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/lion-field-combat.js'), 'utf8'), context);
  assert.equal(typeof context.ActOneLionFieldCombat.run, 'function');
  assert.equal(context.ActOneLionFieldCombat.objective, 'Meet Lisa at the temple');
});
