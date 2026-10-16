const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const recovery = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/recovery.js');
const bgiPath = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const source = fs.readFileSync(bgiPath, 'utf8');
const session = 'wolf-closing-test';
const strikeId = 'mission-' + 'a'.repeat(32);
const row = (text, x, y, width = 140, height = 28) => ({ text, x, y, width, height });

function closingRows(speaker = 'Kaeya', extra = []) {
  return [row('Auto', 30, 24), row(speaker, 800, 850), row('The trial is over. You did well.', 500, 930, 520, 30), ...extra];
}
function entryReport() {
  return { id: 'entry-1', session, mission: 'questStep', status: 'completed', details: {
    result: { step: 'wolfPartyStart', label: 'Deep Within the Temple of the Wolf' },
    inputEvents: [{ type: 'wolfPartyStart', label: 'Deep Within the Temple of the Wolf', startedAt: 7000 }]
  }};
}
function proofFixture() {
  const strike = { type: 'wolfWitnessAction', action: 'strike', rootDirected: true, frameId: 8, startedAt: 8000, finishedAt: 8100 };
  const key = { type: 'key', key: 'VK_LBUTTON', durationMs: 60, frameId: 8, startedAt: 8010, finishedAt: 8090 };
  const receipt = { id: strikeId, session, mission: 'questStep', status: 'completed', details: { result: { step: 'wolfWitnessAction', action: 'strike', actionAttempts: 1 }, inputEvents: [strike, key] } };
  const witness = { session, frameId: 10, timestamp: 8200, map: null, ocr: [...closingRows(), row('Bravo! What a performance!', 500, 940, 500, 30)], hud: {
    world: false, auto: true, dialogueReady: true, choice: false, health: null, journal: false,
    bigMap: false, tutorialStep: null, enemyBars: []
  }};
  const report = { id: strikeId, session, mission: 'recover', status: receipt.status, details: JSON.parse(JSON.stringify(receipt.details)) };
  const permit = { kind: 'wolfClosingDialogue', session, frameId: 10, witnessFrameId: 10, createdAt: 9000, strikeRequestId: strikeId };
  return { strike, key, receipt, witness, report, permit };
}
function makeHarness({ rows = closingRows(), edits = {}, cap = false, persist = 'ok' } = {}) {
  let now = 10000, persistMode = persist, wrotePermit = false;
  const files = new Map();
  const p = proofFixture();
  Object.assign(p.permit, edits.permit || {});
  if (edits.witness) Object.assign(p.witness, edits.witness);
  if (edits.report) Object.assign(p.report, edits.report);
  if (edits.receipt) Object.assign(p.receipt, edits.receipt);
  if (edits.strike) Object.assign(p.receipt.details.inputEvents[0], edits.strike);
  if (edits.key) Object.assign(p.receipt.details.inputEvents[1], edits.key);
  if (edits.history) p.history = edits.history;
  else p.history = [entryReport(), p.report];
  files.set('wolf-closing-dialogue.json', JSON.stringify(p.permit));
  files.set('observations/' + session + '/frame-0010.json', JSON.stringify(p.witness));
  files.set('reports/' + session + '.json', JSON.stringify(p.history));
  files.set('receipts/' + session + '/' + strikeId + '.json', JSON.stringify(p.receipt));
  const keys = [], releases = [], clicks = [];
  let currentRows = rows;
  const context = {
    Date: class extends Date { static now() { return now; } },
    genshin: { isRemoteDesktopSession: true, windowsSessionId: 7, isGameForeground: true, getPositionFromMap: () => null, getCameraOrientation: () => 0 },
    file: {
      isExists: name => name.endsWith('.png') && name === 'observations/' + session + '/frame-0010.png' || files.has(name),
      readTextSync: name => { if (files.has(name)) return files.get(name); const disk = path.join(path.dirname(bgiPath), name); if (fs.existsSync(disk)) return fs.readFileSync(disk, 'utf8'); throw new Error('missing ' + name); },
      writeTextSync: (name, value) => { if (name === 'wolf-closing-dialogue.json') { if (persistMode === 'failWrite') return false; wrotePermit = true; if (persistMode === 'badReadback') files.set(name, JSON.stringify({ ...JSON.parse(value), usedFrameId: -1 })); else files.set(name, value); return true; } files.set(name, value); return true; },
      writeImageSync: () => true
    },
    RecognitionObject: { Ocr: () => ({}) },
    captureGameRegion: () => ({ width: 1920, height: 1080, srcMat: {}, findMulti: () => { const a = currentRows.map(x => ({ ...x })); a.count = a.length; return a; }, deriveCrop: () => ({ srcMat: { resize: () => ({}) }, dispose() {} }), dispose() {} }),
    ImageRegion: class { findMulti() { const a = []; a.count = 0; return a; } dispose() {} },
    OpenCvSharp: { OpenCvSharp: { Size: class { constructor(w, h) { this.width = w; this.height = h; } } } },
    keyDown: key => keys.push({ key, at: now }), keyUp: key => releases.push({ key, at: now }), click: (x, y) => clicks.push([x, y]),
    sleep: async ms => { now += ms; }, log: { info() {} }
  };
  vm.runInNewContext(source, context);
  const adapter = context.createActOneAdapter(7);
  adapter.beginMission({ mission: 'recover', session, createdAt: 6000, expectedFrameId: 10 });
  let frame = 10;
  async function observe(nextRows = currentRows) {
    currentRows = nextRows; frame++; now += 10;
    return adapter.observe(session, frame);
  }
  return { adapter, files, p, keys, releases, clicks, now: () => now, observe, setNow: n => { now = n; }, setRows: r => { currentRows = r; }, setPersist: mode => { persistMode = mode; }, permitWritten: () => wrotePermit };
}

function observation(rows, frameId = 11, timestamp = 10000, speaker = 'Kaeya') {
  return { session, frameId, timestamp, map: null, ocr: rows || closingRows(speaker), hud: {
    world: false, auto: true, dialogueReady: true, choice: false, health: null,
    journal: false, bigMap: false, tutorialStep: null, enemyBars: []
  }};
}

test('closing state requires fresh same-session dialogue with Auto, Kaeya/Paimon, and caption', () => {
  const valid = observation(closingRows(), 11, 10000);
  assert.equal(require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js').wolfClosingDialogueState(valid, 10000, session), true);
  for (const bad of [
    { ...valid, session: 'other' }, { ...valid, frameId: 1.5 }, { ...valid, timestamp: 8000 },
    { ...valid, map: { map: 'Teyvat' } }, { ...valid, hud: { ...valid.hud, choice: true } },
    observation(closingRows('Unknown'), 11, 10000), observation(closingRows('Kaeya', [row('Auto', 400, 24)]).filter(r => r.text !== 'Auto'), 11, 10000),
    observation([row('Auto', 30, 24), row('Kaeya', 800, 850)], 11, 10000)
  ]) assert.equal(require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js').wolfClosingDialogueState(bad, 10000, session), false, JSON.stringify(bad));
});

test('actual adapter consumes/readbacks one permit before one Space60 and releases it', async () => {
  const h = makeHarness();
  const first = await h.observe();
  assert.equal(h.adapter.wolfClosingDialogueRecoveryReady(first), true);
  await h.adapter.wolfClosingDialogueRecoveryAdvance();
  const saved = JSON.parse(h.files.get('wolf-closing-dialogue.json'));
  assert.equal(saved.usedFrameId, first.frameId);
  assert.ok(saved.usedAt <= h.now()); assert.equal(h.now() - saved.usedAt, 60);
  assert.equal(h.keys.length, 1); assert.deepEqual(h.keys[0].key, 'VK_SPACE');
  assert.equal(h.releases.length, 1); assert.equal(h.releases[0].key, 'VK_SPACE');
  const keyEvent = h.adapter.events().find(e => e.type === 'key'); assert.equal(keyEvent.key, 'VK_SPACE'); assert.equal(keyEvent.durationMs, 60);
  await assert.rejects(h.adapter.wolfClosingDialogueRecoveryAdvance(), /Fresh witnessed Wolf closing dialogue required/);
});

test('adapter rejects stale, wrong entry, mismatched receipt, forged strike, missing witness, replayed permit, and later input', async () => {
  const cases = [
    { permit: { createdAt: -120001 } },
    { history: [] },
    { receipt: { ...proofFixture().receipt, details: { result: { step: 'wolfWitnessAction', action: 'strike', actionAttempts: 1 }, inputEvents: [] } } },
    { receipt: { ...proofFixture().receipt, details: { result: { step: 'wolfWitnessAction', action: 'strike', actionAttempts: 1 }, inputEvents: [ { ...proofFixture().strike, rootDirected: false }, proofFixture().key ] } } },
    { witness: { frameId: 12 } },
    { permit: { usedAt: 9999 } },
    { strike: { frameId: 8.5 } },
    { key: { finishedAt: 8000 } },
    { history: [entryReport(), proofFixture().report, { session, details: { inputEvents: [{ type: 'key', startedAt: 8200 }] } }] }
  ];
  for (const edit of cases) {
    const h = makeHarness({ edits: edit });
    const o = await h.observe();
    assert.equal(h.adapter.wolfClosingDialogueRecoveryReady(o), false, JSON.stringify(edit));
    await assert.rejects(h.adapter.wolfClosingDialogueRecoveryAdvance(), /Fresh witnessed Wolf closing dialogue required/);
    assert.equal(h.keys.length, 0);
  }
  const replay = makeHarness();
  let o = await replay.observe(); await replay.adapter.wolfClosingDialogueRecoveryAdvance();
  o = await replay.observe();
  assert.equal(replay.adapter.wolfClosingDialogueRecoveryReady(o), true, JSON.stringify({o, events: replay.adapter.events().slice(-3), now: replay.now()}));
  // Replaying as a fresh request resets the in-memory one-use state; persisted usedAt still blocks it.
  replay.adapter.beginMission({ mission: 'recover', session, createdAt: 6000, expectedFrameId: 10 });
  o = await replay.observe();
  assert.equal(replay.adapter.wolfClosingDialogueRecoveryReady(o), false);
});

test('recovery loop only advances fresh dialogue, stops at choice/unknown speaker, and claims no completion', async () => {
  const sequence = [observation(closingRows('Kaeya'), 11, 10000), observation(closingRows('Paimon'), 12, 10660), { ...observation(closingRows('Paimon'), 13, 11320), hud: { ...observation(closingRows('Paimon'), 13, 11320).hud, choice: true } }];
  let index = 0, inputs = 0, clock = 10000;
  const api = {
    now: () => clock, checkStop() {}, sleep: async ms => { clock += ms; },
    wolfClosingDialogueRecoveryReady: o => o && o.hud.dialogueReady && !o.hud.choice && ['Kaeya', 'Paimon'].some(s => o.ocr.some(r => r.text === s)),
    wolfClosingDialogueRecoveryAdvance: async () => { inputs++; }
  };
  const result = await recovery.run(sequence[0], api, async () => sequence[++index]);
  assert.equal(result.closingDialogueAttempts, 2); assert.equal(inputs, 2);
  assert.equal(result.questComplete, false); assert.equal(result.rootDirected, true);
  for (const stop of [
    { ...observation([...closingRows('Kaeya'), row('Choose', 100, 700)], 11, 10000), hud: { ...observation(closingRows('Kaeya'), 11, 10000).hud, choice: true } },
    observation(closingRows('Unknown'), 11, 10000)
  ]) {
    const api2 = { ...api, wolfClosingDialogueRecoveryReady: o => o && o.hud.dialogueReady && !o.hud.choice && o.ocr.some(r => ['Kaeya', 'Paimon'].includes(r.text)) };
    const stopped = await recovery.run(stop, api2, async () => stop);
    assert.equal(stopped.closingDialogueAttempts || 0, 0); assert.notEqual(stopped.questComplete, true);
  }
});

test('recovery loop caps at 16 inputs and stops at the 20 second wall', async () => {
  for (const mode of ['inputs', 'time']) {
    let clock = 10000, inputs = 0, frame = 10;
    const current = () => observation(closingRows('Paimon'), frame, clock);
    const api = { now: () => clock, checkStop() {}, sleep: async ms => { clock += ms; },
      wolfClosingDialogueRecoveryReady: () => true,
      wolfClosingDialogueRecoveryAdvance: async () => { inputs++; if (mode === 'time') clock += 20000; } };
    const result = await recovery.run(current(), api, async () => { frame++; return current(); });
    assert.equal(result.closingDialogueAttempts, mode === 'inputs' ? 16 : 1);
    assert.equal(inputs, result.closingDialogueAttempts); assert.equal(result.questComplete, false);
  }
});














const continuationId = 'mission-' + 'b'.repeat(32);
function choiceRows(label = "Thanks, that's nice of you to say...") {
  return [row('Auto', 30, 24), row('Kaeya', 800, 850), row(label, 1180, 550, 460, 42)];
}
function continuationFixture() {
  const prior = { id: continuationId, session, mission: 'recover', status: 'completed', details: { result: {
    rootDirected: true, questComplete: false, closingDialogueAttempts: 2
  }, inputEvents: [
    { type: 'controllerRevision', startedAt: 6900 },
    { type: 'wolfClosingDialogueAdvance', frameId: 6, startedAt: 7000, finishedAt: 7060, rootDirected: true },
    { type: 'key', key: 'VK_SPACE', durationMs: 60, startedAt: 7010, finishedAt: 7050 },
    { type: 'wolfClosingDialogueAdvance', frameId: 8, startedAt: 7200, finishedAt: 7260, rootDirected: true },
    { type: 'key', key: 'VK_SPACE', durationMs: 60, startedAt: 7210, finishedAt: 7250 }
  ] } };
  const witness = { session, frameId: 10, timestamp: 8000, map: null, ocr: choiceRows(), hud: {
    world: false, auto: true, dialogueReady: true, choice: true, health: null, journal: false,
    bigMap: false, tutorialStep: null, enemyBars: []
  }};
  const permit = { kind: 'wolfClosingDialogueContinue', session, frameId: 10, witnessFrameId: 10,
    createdAt: 9000, priorRecoveryId: continuationId };
  return { prior, witness, permit };
}
function makeContinuationHarness({ rows = choiceRows(), edits = {}, persist = 'ok' } = {}) {
  const h = makeHarness({ rows, persist });
  const c = continuationFixture();
  Object.assign(c.permit, edits.permit || {});
  if (edits.witness) Object.assign(c.witness, edits.witness);
  if (edits.prior) Object.assign(c.prior, edits.prior);
  if (edits.priorEvents) c.prior.details.inputEvents = edits.priorEvents;
  c.history = edits.history || [entryReport(), c.prior];
  h.files.set('wolf-closing-dialogue.json', JSON.stringify(c.permit));
  h.files.set('observations/' + session + '/frame-0010.json', JSON.stringify(c.witness));
  h.files.set('reports/' + session + '.json', JSON.stringify(c.history));
  h.files.set('receipts/' + session + '/' + continuationId + '.json', JSON.stringify(c.prior));
  return { ...h, c };
}



test('continuation permit binds fresh exact Kaeya thanks-choice to a completed bounded prior recovery', async () => {
  const h = makeContinuationHarness();
  const first = await h.observe();
  assert.equal(h.adapter.wolfClosingDialogueContinuationReady(first), true);
  const outcome = await h.adapter.runWolfClosingDialogueContinuation(first, async () => h.observe());
  assert.equal(outcome.status, 'stopped');
  assert.equal(outcome.reason, 'dialogue_did_not_advance');
  assert.ok(outcome.presses >= 4 && outcome.presses < 10, 'unchanged recorded dialogue stops promptly');
  const saved = JSON.parse(h.files.get('wolf-closing-dialogue.json'));
  assert.equal(saved.usedFrameId, first.frameId);
  assert.ok(saved.usedAt <= h.now());
  assert.equal(h.adapter.events().filter(e => e.type === 'wolfClosingDialogueContinuation').length, 1);
  assert.equal(h.adapter.events().filter(e => e.type === 'dialogueChoice').length, outcome.presses);
  assert.ok(h.adapter.events().every(e => !['VK_LBUTTON', 'VK_W', 'VK_E'].includes(e.key)));
});

test('continuation gate rejects wrong choice, missing or forged receipt, mismatched witness, and later input', async () => {
  const cases = [
    { rows: choiceRows('A different compliment') },
    { edits: { history: [entryReport()] } },
    { edits: { prior: { details: { result: { rootDirected: true, questComplete: false, closingDialogueAttempts: 2 }, inputEvents: [] } } } },
    { edits: { prior: { details: { result: { rootDirected: false, questComplete: false, closingDialogueAttempts: 2 } } } } },
    { edits: { witness: { frameId: 12 } } },
    { edits: { witness: { timestamp: 12000 } } },
    { edits: { prior: { details: { inputEvents: [...continuationFixture().prior.details.inputEvents, { type: 'key', key: 'VK_SPACE', startedAt: 8100 }] } } } },
    { edits: { priorEvents: (() => { const e = continuationFixture().prior.details.inputEvents; e[2].frameId = undefined; e[3].frameId = undefined; e[1].frameId = 6; e[3].frameId = 6; return e; })() } },
    { edits: { priorEvents: (() => { const e = continuationFixture().prior.details.inputEvents; e[1].frameId = 8; e[3].frameId = 6; return e; })() } },
    { edits: { priorEvents: (() => { const e = continuationFixture().prior.details.inputEvents; e[2].frameId = 9; return e; })() } },
    { edits: { witness: { timestamp: 12000 } } },
  ];
  for (const options of cases) {
    const h = makeContinuationHarness(options);
    const o = await h.observe();
    assert.equal(h.adapter.wolfClosingDialogueContinuationReady(o), false, JSON.stringify(options));
  }
  const replay = makeContinuationHarness();
  let o = await replay.observe();
  await replay.adapter.runWolfClosingDialogueContinuation(o, async () => replay.observe());
  replay.adapter.beginMission({ mission: 'recover', session, createdAt: 6000, expectedFrameId: 10 });
  o = await replay.observe();
  assert.equal(replay.adapter.wolfClosingDialogueContinuationReady(o), false, 'consumed continuation permit cannot be replayed');
});

test('continuation does not start if permit persistence or readback fails', async () => {
  for (const mode of ['failWrite', 'badReadback']) {
    const h = makeContinuationHarness({ persist: mode });
    const o = await h.observe();
    assert.equal(h.adapter.wolfClosingDialogueContinuationReady(o), true);
    await assert.rejects(h.adapter.runWolfClosingDialogueContinuation(o, async () => h.observe()), /permit persistence failed|permit readback failed/);
    assert.equal(h.adapter.events().filter(e => e.type === 'dialogueChoice').length, 0);
    assert.equal(h.keys.length, 0);
  }
});

test('recovery preserves bounded continuation outcome and never reports quest completion', async () => {
  let calls = 0;
  const current = observation(choiceRows(), 11, 10000);
  const api = {
    wolfClosingDialogueContinuationReady: () => true,
    runWolfClosingDialogueContinuation: async (o, observe) => { calls++; assert.equal(o, current); return { status: 'stopped', reason: 'dialogue_limit_reached', presses: 40, inputMs: 2400 }; }
  };
  const result = await recovery.run(current, api, async () => current);
  assert.equal(calls, 1);
  assert.equal(result.dialoguePassStatus, 'stopped');
  assert.equal(result.presses, 40); assert.equal(result.inputMs, 2400);
  assert.equal(result.questComplete, false); assert.equal(result.closingDialogueContinuation, true);
});










const kaeyaAcquisitionRows = [
  row('Obtained New Character', 179, 536, 317, 39),
  row('Kaeya', 171, 568, 219, 92),
  row('Click anywhere in the blank area to continue', 715, 1016, 489, 31)
];
function makeCharacterHarness({ rows = kaeyaAcquisitionRows, edits = {} } = {}) {
  const h = makeHarness({ rows });
  const prior = { id: continuationId, session, mission: 'recover', status: 'completed', timestamp: 9000, details: {
    result: { closingDialogueContinuation: true, rootDirected: true, questComplete: false },
    inputEvents: [{ type: 'wolfClosingDialogueContinuation', frameId: 13, startedAt: 7000, rootDirected: true }]
  }};
  const history = [entryReport(), prior];
  if (edits.laterInput) history.push({ id: 'later-input', session, mission: 'recover', status: 'completed', details: { inputEvents: [{ type: 'key', startedAt: 9500 }] } });
  if (edits.wrongPrior) prior.details.result.rootDirected = false;
  h.files.set('reports/' + session + '.json', JSON.stringify(history));
  if (!edits.missingReceipt) h.files.set('receipts/' + session + '/' + continuationId + '.json', JSON.stringify(prior));
  return { ...h, prior, history };
}

test('Kaeya acquisition is dismissed once after exact same-session closing receipt and replay marker is durable', async () => {
  const h = makeCharacterHarness();
  const first = await h.observe();
  assert.equal(first.hud.characterAcquired, 'Kaeya');
  assert.equal(h.adapter.wolfClosingCharacterRecoveryReady(first), true);
  const result = await recovery.run(first, h.adapter, h.observe);
  assert.equal(result.characterAcquired, 'Kaeya');
  assert.equal(result.characterContinueAttempts, 1);
  assert.equal(result.questComplete, false);
  assert.deepEqual(h.clicks, [[1700, 900]]);
  assert.equal(h.adapter.events().filter(e => e.type === 'characterAcquiredContinue').length, 1);
  const markerPath = 'reports/' + session + '.wolfKaeyaAcquisitionContinue.json';
  const marker = JSON.parse(h.files.get(markerPath));
  assert.equal(marker.session, session); assert.equal(marker.frameId, first.frameId);
  h.adapter.beginMission({ mission: 'recover', session, createdAt: 6000, expectedFrameId: 10 });
  const fresh = await h.observe();
  assert.equal(h.adapter.wolfClosingCharacterRecoveryReady(fresh), false, 'durable marker blocks replay after request state resets');
  assert.deepEqual(h.clicks, [[1700, 900]]);
});

test('character continuation rejects wrong character, stale frame, missing closing receipt, and later input', async () => {
  const wrongRows = kaeyaAcquisitionRows.map(r => r.text === 'Kaeya' ? { ...r, text: 'Amber' } : r);
  for (const options of [
    { rows: wrongRows }, { edits: { missingReceipt: true } }, { edits: { laterInput: true } }, { edits: { wrongPrior: true } }
  ]) {
    const h = makeCharacterHarness(options);
    const o = await h.observe();
    assert.equal(h.adapter.wolfClosingCharacterRecoveryReady(o), false, JSON.stringify(options));
    assert.deepEqual(h.clicks, []);
  }
  const stale = makeCharacterHarness();
  const o = await stale.observe(); stale.setNow(stale.now() + 1001);
  assert.equal(stale.adapter.wolfClosingCharacterRecoveryReady(o), false);
  assert.deepEqual(stale.clicks, []);
});
