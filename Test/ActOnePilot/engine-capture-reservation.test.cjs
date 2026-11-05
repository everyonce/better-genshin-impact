const test = require('node:test');
const assert = require('node:assert/strict');
const engine = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/engine.js');

// Model an immutable image saved before recognition succeeds or throws.
function harness(failedAttempts = []) {
  const images = new Map(), metadata = new Map(), pins = [], attempts = [];
  const failures = new Set(failedAttempts);
  const api = {
    now: () => 100000,
    beginMission() {}, events: () => [], release() {},
    observe: async (session, frame) => {
      attempts.push(frame);
      assert.equal(images.has(frame), false, 'capture must not replace existing image evidence');
      images.set(frame, `original pixels for ${frame}`);
      if (failures.has(attempts.length)) throw new Error('recognition failed after image save');
      return { timestamp: 100000, screenshotPath: `frame-${frame}.png`,
        hud: { world: frame === 1, journal: frame > 1 }, ocr: [] };
    },
    write: (path, value) => metadata.set(path, JSON.parse(value)),
    pinObservation: (session, frame) => pins.push(frame)
  };
  const runner = engine.create(api, { session: 'capture-reservation', enableInput: false });
  return { runner, images, metadata, pins, attempts };
}

test('failed first capture reserves its immutable image ID and the next capture succeeds', async () => {
  const h = harness([1]);
  await assert.rejects(h.runner.observe(), /recognition failed/);
  assert.equal(h.runner.getFrame(), 0);
  const next = await h.runner.observe();
  assert.equal(next.frameId, 2);
  assert.deepEqual(h.attempts, [1, 2]);
  assert.equal(h.images.get(1), 'original pixels for 1');
  assert.equal(h.metadata.has('observations/capture-reservation/frame-0001.json'), false);
  assert.equal(h.metadata.get('observations/capture-reservation/frame-0002.json').frameId, 2);
});

test('scene change after a failed capture pins the previous successful observation', async () => {
  const h = harness([2]);
  await h.runner.observe();
  await assert.rejects(h.runner.observe(), /recognition failed/);
  assert.equal(h.runner.getFrame(), 1);
  assert.equal((await h.runner.observe()).frameId, 3);
  assert.deepEqual(h.pins, [1, 1, 3]);
  assert.equal(h.images.get(2), 'original pixels for 2');
});

test('request admission stays bound to the successful frame across a failed capture', async () => {
  const h = harness([2]);
  await h.runner.observe();
  await assert.rejects(h.runner.observe(), /recognition failed/);
  const request = { session: 'capture-reservation', id: 'failed-frame', createdAt: 100000,
    expectedFrameId: 2, mission: 'observe' };
  assert.equal(await h.runner.process(request, () => ({})), 'rejected');
  assert.deepEqual(h.attempts, [1, 2]);
  assert.equal(await h.runner.process({ ...request, id: 'successful-frame', expectedFrameId: 1 }, () => ({})), 'completed');
  assert.deepEqual(h.attempts, [1, 2, 3]);
  assert.equal(h.metadata.get('receipts/capture-reservation/successful-frame.json').frameId, 3);
});

test('consecutive recognition failures each keep a distinct immutable image', async () => {
  const h = harness([1, 2, 3]);
  for (let attempt = 0; attempt < 3; attempt++) await assert.rejects(h.runner.observe(), /recognition failed/);
  assert.equal(h.runner.getFrame(), 0);
  assert.equal((await h.runner.observe()).frameId, 4);
  assert.deepEqual([...h.images.keys()], [1, 2, 3, 4]);
  assert.deepEqual(h.pins, [4]);
});
