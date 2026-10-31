const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const recovery = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/recovery.js');
const adapterSource = fs.readFileSync(path.join(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'), 'utf8');

// Exact OCR rows retained after the second live Kaeya healing pass (frame26).
// Screenshots and original session records remain private diagnostic artifacts.
const capturedRows = [
  { text: ' Click on the character portrait to restore HP', x: 213, y: 32, width: 565, height: 37 },
  { text: "Statue's Blessing", x: 1517, y: 25, width: 252, height: 48 },
  { text: 'Lv. 20', x: 440, y: 226, width: 79, height: 29 },
  { text: 'Restorative Power: 9196 710000', x: 1397, y: 597, width: 492, height: 29 },
];

// Synthetic metadata preserves the actual OCR while keeping fixtures independent of live files.
function panel(ocr = capturedRows, frameId = 1) {
  return { session: 'statue-power-ocr', frameId, timestamp: 1000 + frameId,
    map: null, hud: { world: false, health: null }, ocr: structuredClone(ocr) };
}

// Execute the actual adapter method with inert input callbacks and its real pure recognizers.
async function adapterHeal(observation, now = observation.timestamp + 1, stopped = false) {
  const clicks = [], context = { Date: { now: () => now }, lastObservation: observation,
    checkStop() { if (stopped) throw Error('operator stop'); }, events: [], request: { mission: 'recover' },
    click(x, y) { clicks.push([x, y]); }, sleep: async () => {} };
  vm.runInNewContext(adapterSource, context);
  const label = 'healTravelerAtStatue: ';
  const start = adapterSource.lastIndexOf(label + 'async function () {');
  const end = adapterSource.indexOf('\n        },', start);
  assert.ok(start >= 0 && end > start, 'actual adapter method must be located');
  const method = adapterSource.slice(start + label.length, end + '\n        }'.length);
  let error = null;
  try { await vm.runInNewContext('(' + method + ')', context)(); }
  catch (failure) { error = failure; }
  return { clicks, error, events: JSON.parse(JSON.stringify(context.events)),
    alternative: context.actOneStatueAlternativePower(observation.ocr) };
}

// Change only the captured numeric row; headers and portrait remain independently bound.
function power(text) {
  const rows = structuredClone(capturedRows);
  rows[3].text = text;
  return panel(rows);
}

test('actual9196 slash-as-seven frame qualifies in both recovery and the physical-input adapter gate', async () => {
  const observation = panel();
  assert.equal(recovery.hasStatueHealingPanel(observation), true);
  const result = await adapterHeal(observation);
  assert.equal(result.error, null);
  assert.equal(result.alternative, 9196);
  assert.deepEqual(result.clicks, [[118, 160], [298, 160], [478, 160]]);
  assert.deepEqual(result.events[0].portraits, [118, 298, 478]);
});

test('the exact seven separator permits whitespace and bounded decimal reserves only', async () => {
  for (const [text, value] of [
    ['Restorative Power:9196710000', 9196],
    ['Restorative Power: 9196 7 10000', 9196],
    ['Restorative Power:\t9196\t7\t10000 ', 9196],
    ['Restorative Power:10000710000', 10000],
    ['Restorative Power: 1 710000', 1],
  ]) {
    const observation = power(text);
    assert.equal(recovery.hasStatueHealingPanel(observation), true, text);
    const result = await adapterHeal(observation);
    assert.equal(result.error, null, text);
    assert.equal(result.alternative, value, text);
  }
});

test('ordinary literal-slash behavior remains accepted without alternate parsing', async () => {
  for (const text of ['Restorative Power: 9598 / 10000', 'Restorative Power: 10000/10000',
    'Restorative Power: 400 / 500']) {
    const observation = power(text);
    assert.equal(recovery.hasStatueHealingPanel(observation), true);
    const result = await adapterHeal(observation);
    assert.equal(result.error, null);
    assert.equal(result.alternative, null);
  }
});

test('depleted alternate reserve is recognized only for refusal and never authorizes a portrait click', async () => {
  const observation = power('Restorative Power: 0 710000');
  assert.equal(recovery.hasStatueHealingPanel(observation), false);
  assert.equal(recovery.hasStatueHealingPanel(observation, true), true);
  const result = await adapterHeal(observation);
  assert.equal(result.alternative, 0);
  assert.match(String(result.error), /Fresh Statue healing panel required/);
  assert.deepEqual(result.clicks, []);
  const actions = [];
  const stopped = await recovery.run(observation, {
    checkStop() {}, healTravelerAtStatue: async () => actions.push('heal'),
    keyPress: async () => actions.push('key'), sleep: async () => actions.push('sleep'),
  }, async () => { throw Error('depletion must not poll into new authority'); });
  assert.match(stopped.reason, /Power is depleted/);
  assert.deepEqual(actions, []);
});

test('malformed counts, alternate denominators and arbitrary digit substitutions remain refused', async () => {
  for (const text of [
    'Restorative Power: 10001 710000', 'Restorative Power: -1 710000',
    'Restorative Power: +9196 710000', 'Restorative Power: 9196.0 710000',
    'Restorative Power: 9,196 710000', 'Restorative Power: 9196 810000',
    'Restorative Power: 9196 710001', 'Restorative Power: 9196 7 0',
    'Restorative Power: 9196 77 10000', 'Restorative Power: 9196 710000 extra',
    'Other Power: 9196 710000', 'Restorative Power: 9196 10000',
  ]) {
    const observation = power(text);
    assert.equal(recovery.hasStatueHealingPanel(observation), false, text);
    const result = await adapterHeal(observation);
    assert.ok(result.error, text);
    assert.deepEqual(result.clicks, [], text);
  }
});

test('wrong geometry, missing or duplicated headers, and ambiguous power rows refuse in both gates', async () => {
  const changes = [
    rows => rows.splice(0, 1), rows => rows.splice(1, 1),
    rows => rows.push({ ...rows[0] }), rows => rows.push({ ...rows[1] }),
    rows => rows.push({ ...rows[3] }), rows => rows.push({ ...rows[3], text: 'Restorative Power: 0 710000' }),
    rows => rows.push({ ...rows[3], text: 'Restorative Power: 9196 / 10000' }),
    rows => rows.push({ ...rows[3], text: 'Restorative Power: 0 / 10000' }),
    rows => rows[0].y = 101, rows => rows[1].x = 1399,
    rows => rows[3].x = 1379, rows => rows[3].x = 1421,
    rows => rows[3].y = 579, rows => rows[3].y = 631,
    rows => rows[3].width = 449, rows => rows[3].width = 531,
    rows => rows[3].height = 19, rows => rows[3].height = 51,
    rows => rows[3].x = '1397', rows => rows[3].width = NaN,
    rows => delete rows[3].height,
  ];
  for (const change of changes) {
    const rows = structuredClone(capturedRows); change(rows);
    const observation = panel(rows);
    assert.equal(recovery.hasStatueHealingPanel(observation), false, change.toString());
    const result = await adapterHeal(observation);
    assert.ok(result.error, change.toString());
    assert.deepEqual(result.clicks, [], change.toString());
  }
});

test('recognition does not bypass the adapter freshness or operator-stop checks', async () => {
  const observation = panel();
  for (const [now, stopped] of [[observation.timestamp + 1001, false], [observation.timestamp + 1, true]]) {
    const result = await adapterHeal(observation, now, stopped);
    assert.ok(result.error);
    assert.deepEqual(result.clicks, []);
  }
});

test('actual alternate rows can finish the unchanged bounded five-pass recovery and verified journal pause', async () => {
  const initial = panel(), actions = [];
  const frames = [...Array.from({ length: 5 }, (_, i) => panel(capturedRows, i + 2)),
    { ...panel([], 7), hud: { world: true, health: { current: 4015, max: 4015 } } },
    { ...panel([], 8), hud: { journal: true } }];
  const result = await recovery.run(initial, {
    checkStop() {}, sleep: async () => {}, healTravelerAtStatue: async () => actions.push('heal'),
    keyPress: async key => actions.push(key), pauseCombat: async () => { actions.push('pause'); return true; },
  }, async () => { assert.ok(frames.length); return frames.shift(); });
  assert.equal(result.status, 'completed');
  assert.equal(result.reason, 'Statue healing applied');
  assert.equal(result.paused, true);
  assert.deepEqual(result.health, { current: 4015, max: 4015 });
  assert.deepEqual(actions, ['heal', 'heal', 'heal', 'heal', 'heal', 'VK_ESCAPE', 'pause']);
});
