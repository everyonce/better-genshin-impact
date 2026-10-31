const test = require('node:test');
const assert = require('node:assert/strict');
const recovery = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/recovery.js');

// Preserve the observed header geometry and slash-as-seven OCR without importing live artifacts.
const unreadableRows = [
  { text: "Statue's Blessing", x: 1525, y: 24, width: 253, height: 51 },
  { text: 'In combat', x: 28, y: 38, width: 203, height: 27 },
  { text: 'Click on the character portrait to restore HP', x: 218, y: 38, width: 559, height: 29 },
  { text: 'Restorative Power:10000710000', x: 1401, y: 591, width: 501, height: 39 },
];
const validRows = [
  { text: "Statue's Blessing", x: 1519, y: 27, width: 251, height: 44 },
  { text: '+ In combat', x: 30, y: 38, width: 197, height: 27 },
  { text: 'Click on the character portrait to restore HP', x: 220, y: 38, width: 555, height: 29 },
  { text: 'Restorative Power: 10000 / 10000', x: 1393, y: 592, width: 501, height: 37 },
];

// Synthetic session metadata makes the separately captured OCR samples one inert transition.
function panel(frameId, ocr = unreadableRows) {
  return { session: 'statue-power-transition', frameId, timestamp: 10000 + frameId * 350,
    map: null, hud: { world: false, health: null }, ocr: structuredClone(ocr) };
}

// Record every possible recovery input so a refusal cannot silently enter another branch.
function harness(initial, observations, overrides = {}) {
  const calls = [];
  let current = initial, index = 0;
  const api = {
    checkStop() {},
    sleep: async ms => calls.push(['sleep', ms]),
    healTravelerAtStatue: async () => calls.push(['heal', current.frameId]),
    keyPress: async key => calls.push(['key', key]),
    chooseStatueBlessing: async () => calls.push(['blessing']),
    teleportStarfellStatue: async () => calls.push(['teleport']),
    forward: async ms => calls.push(['forward', ms]),
    rotate: async dx => calls.push(['rotate', dx]),
    pauseCombat: async () => { calls.push(['pause']); return true; },
    ...overrides,
  };
  return { api, calls, count: () => index, observe: async () => {
    assert.ok(index < observations.length, 'observation budget exceeded');
    current = observations[index++];
    calls.push(['observe', current && current.frameId]);
    return current;
  } };
}

// Only passive waits and captures are allowed while the panel remains unqualified.
function assertNoInput(h) {
  assert.deepEqual(h.calls.filter(row => !['sleep', 'observe'].includes(row[0])), []);
}

test('captured slash-as-seven transition accepts the third fresh valid panel before healing', async () => {
  const initial = panel(17);
  assert.equal(recovery.hasStatueHealingPanel(initial), false);
  const frames = [panel(18), panel(19), panel(20, validRows),
    ...Array.from({ length: 5 }, (_, i) => panel(21 + i, validRows)),
    { ...panel(26, []), hud: { world: true, health: { current: 2764, max: 2764 } } },
    { ...panel(27, []), hud: { journal: true } }];
  const h = harness(initial, frames);
  const result = await recovery.run(initial, h.api, h.observe);
  assert.equal(result.status, 'completed');
  assert.equal(result.reason, 'Statue healing applied');
  assert.equal(h.calls.filter(row => row[0] === 'heal').length, 5);
  assert.deepEqual(h.calls.find(row => row[0] === 'heal'), ['heal', 20]);
  assert.deepEqual(h.calls.slice(0, 6), [
    ['sleep', 350], ['observe', 18], ['sleep', 350], ['observe', 19], ['sleep', 350], ['observe', 20],
  ]);
  assert.deepEqual(h.calls.filter(row => row[0] === 'key'), [['key', 'VK_ESCAPE']]);
  assert.equal(h.count(), 10);
});

test('Blessing selection reaching unreadable power waits rather than falling into journal recovery', async () => {
  const initial = { ...panel(16, []), ocr: [
    { text: 'Statue of The Seven', x: 1200, y: 860 },
    { text: "Statue's Blessing", x: 1500, y: 600 },
  ] };
  const h = harness(initial, [panel(17), panel(18), panel(19), panel(20)]);
  const result = await recovery.run(initial, h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.match(result.reason, /Restorative Power remained unqualified/);
  assert.equal(result.powerPolls, 3);
  assert.deepEqual(h.calls.filter(row => !['sleep', 'observe'].includes(row[0])), [['blessing']]);
  assert.equal(h.count(), 4);
});

for (const power of ['Restorative Power:10000710000', null, 'Restorative Power: 10001 / 10000', 'Restorative Power: 10000 / 0']) {
  test(`unqualified power remains bounded and input-free: ${power}`, async () => {
    const rows = unreadableRows.filter(row => !row.text.startsWith('Restorative Power:'));
    if (power !== null) rows.push({ ...unreadableRows[3], text: power });
    const initial = panel(17, rows);
    const h = harness(initial, [panel(18, rows), panel(19, rows), panel(20, rows)]);
    const result = await recovery.run(initial, h.api, h.observe);
    assert.equal(result.status, 'stopped');
    assert.match(result.reason, /Restorative Power remained unqualified/);
    assert.equal(result.powerPolls, 3);
    assert.equal(h.count(), 3);
    assert.deepEqual(h.calls.filter(row => row[0] === 'sleep'), [['sleep', 350], ['sleep', 350], ['sleep', 350]]);
    assertNoInput(h);
  });
}

test('parsed depleted power stops immediately and cannot wait into renewed authority', async () => {
  const depleted = validRows.map(row => row.text.startsWith('Restorative Power:')
    ? { ...row, text: 'Restorative Power: 0 / 10000' } : row);
  for (const polls of [0, 1, 3]) {
    const initial = panel(17, polls ? unreadableRows : depleted);
    const observations = Array.from({ length: polls }, (_, i) => panel(18 + i,
      i === polls - 1 ? depleted : unreadableRows));
    const h = harness(initial, [...observations, panel(18 + polls, validRows)]);
    const result = await recovery.run(initial, h.api, h.observe);
    assert.equal(result.status, 'stopped');
    assert.match(result.reason, /Power is depleted/);
    assert.equal(h.count(), polls);
    assert.equal(result.powerPolls, polls);
    assertNoInput(h);
  }
});

test('unreadable initial power without source identity cannot enter a polling transition', async () => {
  for (const patch of [{ session: undefined }, { frameId: undefined }, { timestamp: undefined }]) {
    const initial = { ...panel(17), ...patch };
    const h = harness(initial, [panel(18, validRows)]);
    const result = await recovery.run(initial, h.api, h.observe);
    assert.equal(result.status, 'stopped');
    assert.match(result.reason, /lacks source identity/);
    assert.equal(h.count(), 0);
    assertNoInput(h);
  }
});

test('either lost header or a changed journal stops without another capture or fallback input', async () => {
  for (const next of [
    panel(18, validRows.filter(row => !row.text.includes('character portrait'))),
    panel(18, validRows.filter(row => !row.text.includes('Blessing'))),
    { ...panel(18, [{ text: 'Going Upon the Breeze' }]), hud: { journal: true } },
  ]) {
    const initial = panel(17);
    const h = harness(initial, [next, panel(19, validRows)]);
    const result = await recovery.run(initial, h.api, h.observe);
    assert.equal(result.status, 'stopped');
    assert.match(result.reason, /headers changed/);
    assert.equal(h.count(), 1);
    assertNoInput(h);
  }
});

test('repeated, older, missing, or foreign-session source evidence cannot authorize healing', async () => {
  for (const patch of [
    { frameId: 17 }, { frameId: 16 }, { timestamp: panel(17).timestamp },
    { timestamp: undefined }, { session: 'replacement-session' },
  ]) {
    const initial = panel(17);
    const h = harness(initial, [{ ...panel(18, validRows), ...patch }]);
    const result = await recovery.run(initial, h.api, h.observe);
    assert.equal(result.status, 'stopped');
    assert.match(result.reason, /fresh same-session frame/);
    assert.equal(h.count(), 1);
    assertNoInput(h);
  }
});

test('stop during the observation gap prevents capture and all healing input', async () => {
  const initial = panel(17);
  let checks = 0;
  const h = harness(initial, [panel(18, validRows)], {
    checkStop() { if (++checks === 2) throw Error('operator stop'); },
  });
  await assert.rejects(recovery.run(initial, h.api, h.observe), /operator stop/);
  assert.equal(h.count(), 0);
  assertNoInput(h);
});

// The captured post-J journal retained its quest text but read the header as "In Progres".
function journalTransition(frameId, ready = false) {
  return { ...panel(frameId, [
    { text: ready ? 'In Progress' : 'In Progres', x: 143, y: 11, width: 133, height: 28 },
    { text: 'Archon Quests', x: 156, y: 118, width: 221, height: 37 },
    { text: 'Unexpected Encounter', x: 877, y: 121, width: 391, height: 43 },
  ]), hud: { world: false, journal: ready, health: null } };
}

// Reach the unchanged successful-healing branch before exercising journal settling.
function healedFrames() {
  return [...Array.from({ length: 5 }, (_, i) => panel(18 + i, validRows)),
    { ...panel(23, []), hud: { world: true, health: { current: 2764, max: 2764 } } }];
}

test('captured In Progres transition settles after one pause without repeated J or healing', async () => {
  const initial = panel(17, validRows);
  const h = harness(initial, [...healedFrames(), journalTransition(24), journalTransition(25),
    journalTransition(26), journalTransition(27, true)]);
  const result = await recovery.run(initial, h.api, h.observe);
  assert.equal(result.status, 'completed');
  assert.equal(result.paused, true);
  assert.deepEqual(result.health, { current: 2764, max: 2764 });
  assert.equal(h.calls.filter(row => row[0] === 'heal').length, 5);
  assert.equal(h.calls.filter(row => row[0] === 'pause').length, 1);
  assert.deepEqual(h.calls.filter(row => row[0] === 'key'), [['key', 'VK_ESCAPE']]);
  const afterPause = h.calls.slice(h.calls.findIndex(row => row[0] === 'pause') + 1);
  assert.deepEqual(afterPause, [['observe', 24], ['sleep', 350], ['observe', 25],
    ['sleep', 350], ['observe', 26], ['sleep', 350], ['observe', 27]]);
});

test('persistent unknown journal remains stopped after three passive polls and one pause', async () => {
  const initial = panel(17, validRows);
  const h = harness(initial, [...healedFrames(), ...[24, 25, 26, 27].map(id => journalTransition(id))]);
  const result = await recovery.run(initial, h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.equal(result.paused, false);
  assert.equal(h.count(), 10);
  assert.equal(h.calls.filter(row => row[0] === 'pause').length, 1);
  assert.equal(h.calls.filter(row => row[0] === 'heal').length, 5);
  assert.equal(h.calls.filter(row => row[0] === 'sleep' && row[1] === 350).length, 3);
});

test('already settled journal and refused pause add no transition polls', async () => {
  for (const paused of [true, false]) {
    const initial = panel(17, validRows);
    const h = harness(initial, [...healedFrames(), journalTransition(24, paused)]);
    h.api.pauseCombat = async () => { h.calls.push(['pause']); return paused; };
    const result = await recovery.run(initial, h.api, h.observe);
    assert.equal(result.status, paused ? 'completed' : 'stopped');
    assert.equal(result.paused, paused);
    assert.equal(h.count(), 7);
    assert.equal(h.calls.filter(row => row[0] === 'pause').length, 1);
    assert.equal(h.calls.some(row => row[0] === 'sleep' && row[1] === 350), false);
  }
});

test('repeated or foreign-session journal cannot complete the healed transition', async () => {
  for (const patch of [{ frameId: 24 }, { timestamp: panel(24).timestamp }, { session: 'another-session' }]) {
    const initial = panel(17, validRows);
    const h = harness(initial, [...healedFrames(), journalTransition(24),
      { ...journalTransition(25, true), ...patch }]);
    const result = await recovery.run(initial, h.api, h.observe);
    assert.equal(result.status, 'stopped');
    assert.equal(result.paused, false);
    assert.match(result.reason, /fresh same-session frame/);
    assert.equal(h.count(), 8);
    assert.equal(h.calls.filter(row => row[0] === 'pause').length, 1);
    assert.equal(h.calls.filter(row => row[0] === 'heal').length, 5);
  }
});
