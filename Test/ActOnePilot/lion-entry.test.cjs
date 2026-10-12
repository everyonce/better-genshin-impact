'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const lion = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/lion-entry.js');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const row = (text, x, y, width = 100, height = 30) => ({ text, x, y, width, height });
function startScreen(patch = {}) {
  return { timestamp: 1000, session: 's1', map: null, ocr: [
    row('Domain Entrance', 137, 30), row('Temple of the Lion', 55, 120),
    row('Deep Within the Temple of the Lion', 52, 157, 390, 30),
    row('Deep Within the Temple of the Lion', 1274, 149, 469, 29), row('Start', 1688, 999, 85, 36),
  ], hud: { world: false, journal: false, bigMap: false, dialogueReady: false, choice: false, climbing: false, auto: false, tutorialStep: null }, ...patch };
}
function partyScreen(patch = {}) {
  return { timestamp: 1000, session: 's1', map: null, ocr: [
    row('Party Setup', 75, 30), row('Lumina', 410, 320), row('Amber', 760, 350),
    row('Team Standing By', 80, 1010, 280, 35), row('Start', 1688, 999, 85, 36),
  ], hud: { world: false, journal: false, bigMap: false, dialogueReady: false, choice: false, climbing: false, auto: false, tutorialStep: null }, ...patch };
}
const startReceipt = { id: 'r1', session: 's1', mission: 'questStep', status: 'completed', timestamp: 1100,
  details: { result: { step: 'lionStart', label: 'Deep Within the Temple of the Lion' }, inputEvents: [
    { type: 'lionDomainStart', label: 'Deep Within the Temple of the Lion', startedAt: 1050, frameId: 1, x: 1731, y: 1017 },
    { type: 'observation', startedAt: 1101 },
  ] } };
test('Lion start target needs fresh, exact and unique domain labels and named Start button', () => {
  assert.deepEqual(lion.startTarget(startScreen(), 1500), { x: 1731, y: 1017, label: 'Deep Within the Temple of the Lion' });
  const o = startScreen();
  for (const bad of [
    { ...o, timestamp: 499 }, { ...o, timestamp: 1501 }, { ...o, map: { map: 'Teyvat' } },
    { ...o, hud: { ...o.hud, world: true } },
    { ...o, ocr: o.ocr.filter(r => r.text !== 'Domain Entrance') },
    { ...o, ocr: o.ocr.map(r => r.text === 'Temple of the Lion' ? { ...r, text: 'Temple of the Wolf' } : r) },
    { ...o, ocr: [...o.ocr, row('Start', 1680, 999)] },
    { ...o, ocr: [...o.ocr, { text: 'Start', x: NaN, y: 999, width: 80, height: 30 }] },
    { ...o, ocr: o.ocr.map(r => r.text === 'Deep Within the Temple of the Lion' && r.x > 900 ? { ...r, text: 'Deep Within the Temple of the Wolf' } : r) },
    { ...o, hud: { ...o.hud, journal: true } },
  ]) assert.equal(lion.startTarget(bad, 1500), null);
  assert.equal(lion.startTarget({ ...startScreen(), ocr: startScreen().ocr.map(r => r.text === 'Deep Within the Temple of the Lion' ? { ...r, text: 'Deep Within the Temple of the Wolf' } : r) }, 1500), null);
});
test('Lion party target needs safe fresh party OCR and one same-session labelled terminal receipt', () => {
  const o = partyScreen({ timestamp: 1200 });
  o.ocr.splice(3, 0, row('Kaeya', 1110, 350)); // The verified starter party can include Kaeya as a third member.
  assert.deepEqual(lion.partyTarget(o, 1500, [startReceipt], 's1'), { x: 1731, y: 1017 });
  assert.equal(lion.entryProof([startReceipt], 's1', o), true);
  assert.equal(lion.partyTarget(o, 1500, [], 's1'), null);
  assert.equal(lion.partyTarget({ ...o, session: 's2' }, 1500, [startReceipt], 's1'), null);
  for (const bad of [
    { ...o, timestamp: 499 }, { ...o, timestamp: 1501 }, { ...o, map: { map: 'Teyvat' } },
    { ...o, hud: { ...o.hud, world: true } },
    { ...o, ocr: o.ocr.filter(r => r.text !== 'Amber') },
    { ...o, ocr: [...o.ocr, row('Start', 1688, 999)] },
    { ...o, ocr: [...o.ocr, row('Trial', 1400, 500)] },
    { ...o, ocr: [...o.ocr, row('Start', 1688, 999)] },
  ]) assert.equal(lion.partyTarget(bad, 1500, [startReceipt], 's1'), null);
});
test('Lion entry proof rejects unknown labels, duplicates, future receipts and intervening game inputs', () => {
  const o = partyScreen({ timestamp: 1200 });
  const changed = fn => { const copy = structuredClone(startReceipt); fn(copy); return copy; };
  for (const bad of [
    changed(r => { r.details.result.label = 'Temple of the Lion'; }),
    changed(r => { r.details.inputEvents[0].label = 'Temple of the Wolf'; }),
    changed(r => { r.details.inputEvents.push({ type: 'click', startedAt: 1120 }); }),
    changed(r => { r.timestamp = 1300; }),
    changed(r => { r.details.inputEvents[0].x = 2000; }),
  ]) assert.equal(lion.entryProof([bad], 's1', o), false);
  assert.equal(lion.entryProof([startReceipt, structuredClone(startReceipt)], 's1', o), false);
  assert.equal(lion.entryProof([startReceipt, { session: 's1', mission: 'questStep', status: 'completed', timestamp: 1150 }], 's1', o), false);
});

test('Lion helper evaluates without CommonJS globals for ClearScript loading', () => {
  const context = {};
  vm.runInNewContext(fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/lion-entry.js'), 'utf8'), context);
  assert.equal(typeof context.ActOneLionEntry.startTarget, 'function');
  assert.deepEqual(JSON.parse(JSON.stringify(context.ActOneLionEntry.startTarget(startScreen(), 1500))),
    { x: 1731, y: 1017, label: 'Deep Within the Temple of the Lion' });
});

test('Lion mission hooks refuse uncertain screens and send exactly one bounded click when ready', async () => {
  for (const [step, readyName, clickName] of [
    ['lionStart', 'lionStartReady', 'startLionDomain'],
    ['lionPartyStart', 'lionPartyReady', 'startLionParty'],
  ]) {
    let clicks = 0, waits = 0;
    const observation = step === 'lionStart' ? startScreen() : partyScreen({ timestamp: 1200 });
    const api = { now: () => 1500, checkStop() {}, sleep: async ms => { assert.equal(ms, 800); waits++; },
      [readyName]: () => false, [clickName]: () => { clicks++; } };
    const refused = await mission.runQuestStep(step, observation, api, async () => observation);
    assert.equal(refused.status, 'stopped'); assert.equal(clicks, 0); assert.equal(waits, 0);
    api[readyName] = () => true;
    const result = await mission.runQuestStep(step, observation, api, async () => ({ ...observation, frameId: 9 }));
    assert.equal(result.status, 'completed'); assert.equal(result.clicks, 1); assert.equal(clicks, 1);
    assert.equal(waits, 1); assert.equal(result.label, 'Deep Within the Temple of the Lion'); assert.equal(result.frameId, 9);
  }
});
