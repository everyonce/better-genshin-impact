const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const recovery = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/recovery.js');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const bgiPath = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

const objective = 'Go to the location designated by Amber';
function frame({ climbing = true, hp = 900, world = true, objectives = [objective], ocr = [], ...hud } = {}) {
  return { ocr, hud: { world, climbing, objectives, health: hp === null ? null : { current: hp, max: 1000 }, ...hud } };
}
const grounded = () => frame({ climbing: false, ocr: [{ text: 'E', x: 1684, y: 1026 }] });

// Sanitized control-only rows from frames 285-294. UID and all other screen text omitted.
const recordedControlRows = {
  285: [{ text: 'Space', x: 1680, y: 1024 }],
  286: [{ text: 'X', x: 1596, y: 1026 }, { text: 'Space', x: 1680, y: 1024 }],
  291: [],
  292: [],
  293: [{ text: 'Q', x: 1806, y: 1028 }],
  294: [],
};
function harness(observations) {
  const calls = [];
  let index = 0;
  return {
    calls,
    api: {
      checkStop: () => calls.push(['checkStop']),
      descendClimb: async ms => calls.push(['descend', ms]),
      sleep: async ms => calls.push(['sleep', ms]),
      keyPress: async key => calls.push(['key', key]),
      teleportStarfellStatue: async () => calls.push(['teleport']),
    },
    observe: async () => observations[Math.min(index++, observations.length - 1)],
  };
}

test('bounded VK_S descent stops on fresh grounded world observation', async () => {
  const h = harness([grounded(), grounded(), grounded()]);
  const result = await recovery.run(frame(), h.api, h.observe);
  assert.deepEqual(result, { status: 'completed', reason: 'Climb descent reached world ground', climbSteps: 1 });
  assert.deepEqual(h.calls.filter(c => c[0] === 'descend'), [['descend', 800]]);
  assert.equal(h.calls.filter(c => c[0] === 'sleep' && c[1] === 200).length, 3, 'ground evidence is spaced by 200 ms');
  assert.equal(h.calls.some(c => c[0] === 'teleport' || c[0] === 'key'), false);
});

test('transient missing climb prompt cannot complete; climbing return resumes bounded descent', async () => {
  const h = harness([
    frame({ climbing: false, ocr: [{ text: 'Space', x: 1680, y: 1024 }] }),
    frame(),
    grounded(), grounded(), grounded(),
  ]);
  const result = await recovery.run(frame(), h.api, h.observe);
  assert.equal(result.status, 'completed');
  assert.equal(result.climbSteps, 2, 'descent resumes after the fresh frame reports climbing');
  assert.equal(h.calls.filter(c => c[0] === 'descend').length, 2);
  assert.equal(h.calls.filter(c => c[0] === 'sleep' && c[1] === 200).length, 5);
});

test('recorded full-frame control OCR requests same-capture crop only when labels are missing or ambiguous', () => {
  assert.equal(bgi.needsControlCrop(recordedControlRows[285]), true, 'Space-only frame is ambiguous');
  assert.equal(bgi.needsControlCrop(recordedControlRows[286]), false, 'X plus Space already confirms climbing');
  assert.equal(bgi.needsControlCrop(recordedControlRows[291]), true);
  assert.equal(bgi.needsControlCrop(recordedControlRows[292]), true);
  assert.equal(bgi.needsControlCrop(recordedControlRows[293]), false, 'recognized Q is grounded control evidence');
  assert.equal(bgi.needsControlCrop(recordedControlRows[294]), true, 'whole-frame OCR missed visible E and Q');

  // Crop OCR is 3x-scaled and relative to the crop; merge maps it back to
  // normalized full-frame coordinates before recovery consumes the rows.
  const crop294 = [
    { text: 'E', x: 510, y: 123, width: 42, height: 54 },
    { text: 'Q', x: 885, y: 123, width: 42, height: 54 },
  ];
  const merged = bgi.mergeControlCropRows(recordedControlRows[294], crop294, 1520, 985);
  assert.deepEqual(merged.map(r => [r.text, Math.round(r.x), Math.round(r.y)]), [['E', 1690, 1026], ['Q', 1815, 1026]]);
  assert.equal(bgi.groundControlEvidence(merged), true);
});

test('recovery accepts HUD control evidence produced by the same-frame crop', async () => {
  const croppedGround = frame({ climbing: false, groundControls: true, ocr: [] });
  const h = harness([croppedGround, croppedGround, croppedGround]);
  const result = await recovery.run(frame(), h.api, h.observe);
  assert.equal(result.status, 'completed');
  assert.equal(result.climbSteps, 1);
});

test('space-only and missing normal controls never produce false completion', async () => {
  const h = harness(Array(13).fill(frame({ climbing: false, ocr: [{ text: 'Space', x: 1680, y: 1024 }] })));
  const result = await recovery.run(frame(), h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'Grounded HUD controls not confirmed');
  assert.notEqual(result.status, 'completed');
  assert.equal(h.calls.filter(c => c[0] === 'descend').length, 1);
});

test('unknown climb cannot exceed twelve descent holds and never drops automatically', async () => {
  const h = harness(Array(12).fill(frame()));
  const result = await recovery.run(frame(), h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'Bounded climb descent hold limit reached');
  assert.equal(result.climbSteps, 12);
  assert.equal(h.calls.filter(c => c[0] === 'descend').length, 12);
  assert.equal(h.calls.some(c => c[0] === 'key' || c[0] === 'teleport'), false);
});

test('missing or low HP after a descent stops before another hold', async () => {
  for (const next of [frame({ hp: null }), frame({ hp: 590, lowHealth: true })]) {
    const h = harness([next]);
    const result = await recovery.run(frame(), h.api, h.observe);
    assert.equal(result.status, 'stopped');
    assert.equal(result.climbSteps, 1);
    assert.equal(h.calls.filter(c => c[0] === 'descend').length, 1);
  }
});

test('missing or unsafe HP in the initial Amber climbing state stops before input', async () => {
  for (const initial of [frame({ hp: null }), frame({ hp: 590, lowHealth: true })]) {
    const h = harness([]);
    const result = await recovery.run(initial, h.api, h.observe);
    assert.equal(result.status, 'stopped');
    assert.equal(result.reason, 'Unsafe initial state for bounded climb descent');
    assert.equal(h.calls.some(c => c[0] === 'descend' || c[0] === 'key'), false);
  }
});

test('health loss over ten percent and objective changes stop the descent', async () => {
  const health = harness([frame({ hp: 790 })]);
  const healthResult = await recovery.run(frame(), health.api, health.observe);
  assert.match(healthResult.reason, /Health dropped more than 10%/);
  assert.equal(health.calls.filter(c => c[0] === 'descend').length, 1);

  const changed = harness([frame({ objectives: ['New quest'] })]);
  const objectiveResult = await recovery.run(frame(), changed.api, changed.observe);
  assert.match(objectiveResult.reason, /Unsafe or changed state during bounded climb descent/);
  assert.equal(changed.calls.filter(c => c[0] === 'descend').length, 1);
});

test('climbing under a different objective never descends or enters Statue recovery', async () => {
  const wrong = frame({ objectives: ['Defeat the nearby hilichurls'] });
  const h = harness([]);
  const result = await recovery.run(wrong, h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'Recovery requires the verified Going Upon the Breeze journal');
  assert.equal(h.calls.some(c => c[0] === 'descend' || c[0] === 'key' || c[0] === 'teleport'), false);
});

test('BetterGI descent adapter holds only VK_S and enforces the 800 ms bound', async () => {
  const calls = [];
  const ctx = {
    genshin: { isRemoteDesktopSession: true, windowsSessionId: 5, isGameForeground: true },
    file: { isExists: () => false },
    keyDown: key => calls.push(['down', key]),
    keyUp: key => calls.push(['up', key]),
    sleep: ms => new Promise(resolve => setTimeout(resolve, ms)),
  };
  vm.runInNewContext(fs.readFileSync(bgiPath, 'utf8'), ctx);
  const adapter = ctx.createActOneAdapter(5);
  assert.throws(() => adapter.descendClimb(801), /Invalid climb descent duration/);
  await adapter.descendClimb(30);
  assert.deepEqual(calls, [['down', 'VK_S'], ['up', 'VK_S']]);
});
