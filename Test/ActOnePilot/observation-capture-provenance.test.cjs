const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const source = fs.readFileSync(path.join(root, 'bgi.js'), 'utf8');
const Engine = require(path.join(root, 'engine.js'));
const plain = value => JSON.parse(JSON.stringify(value));

// Only capture, OCR, map, storage and clock boundaries are mocked; use the real adapter and engine.
function fixture({asyncWriter = true, uiOnly = false, syncSaved = true, failRecognition = false} = {}) {
  const files = new Map(), events = [], captures = [], raw = [], pending = [];
  let now = 999000;
  function advance(kind, milliseconds) { events.push({kind, startedAt: now}); now += milliseconds; }
  const row = (text, x, y, width = 100, height = 20) => ({text, x, y, width, height});
  const rows = [row('Food', 144, 28), row('Inventory capacity 487/26000', 1480, 29, 300),
    row('UID 123456789', 1700, 1060, 200)];
  function found(items) {
    advance('ocr', 5);
    if (failRecognition) throw new Error('Recognition failed');
    const value = items.map(item => ({...item})); value.count = value.length; return value;
  }
  const file = {
    isExists: name => files.has(name),
    readTextSync: name => files.has(name) ? files.get(name) : fs.readFileSync(path.join(root, name), 'utf8'),
    writeTextSync(name, value) { events.push({kind: 'json', name, startedAt: now}); files.set(name, value); return true; },
    appendTextSync(name, value) { files.set(name, (files.get(name) || '') + value); return true; },
    writeImageSync(name) { advance('png-sync', 100); if (syncSaved === 'throw') throw new Error('Disk failed');
      if (syncSaved) files.set(name, 'synthetic image'); return syncSaved; },
    pinCaptureEvidence() { return true; }
  };
  if (asyncWriter) file.writeImageAsync = name => {
    advance('png-scheduled', 2);
    return new Promise((resolve, reject) => pending.push({name, resolve, reject}));
  };
  const context = {
    Date: class extends Date { static now() { return now; } },
    genshin: {isRemoteDesktopSession: true, windowsSessionId: 7, isGameForeground: true,
      getPositionFromMap() { advance('map', 23); return null; },
      getCameraOrientation() { advance('orientation', 7); return 0; }},
    file, RecognitionObject: {Ocr: () => ({})},
    ImageRegion: class { constructor() { this.width = 1920; this.height = 1080; }
      findMulti() { return found([]); } dispose() {} },
    OpenCvSharp: {OpenCvSharp: {Size: class {}, Scalar: class {}, RetrievalModes: {External: 0},
      ContourApproximationModes: {ApproxSimple: 0}, Cv2: {boundingRect: value => value, contourArea: () => 0}}},
    captureGameRegion() {
      captures.push(now); advance('capture', 11);
      return {width: 1920, height: 1080, srcMat: {}, findMulti: () => found(rows),
        deriveCrop: () => ({srcMat: {resize: () => ({}),
          inRange: () => ({findContoursAsArray: () => [], dispose() {}})}, dispose() {}}),
        dispose() { events.push({kind: 'dispose', startedAt: now}); }};
    },
    sleep: async () => {}, log: {info() {}},
    click() { throw new Error('Unexpected input'); }, keyDown() { throw new Error('Unexpected input'); },
    keyUp() {}, mouseUp() {}
  };
  vm.runInNewContext(source, context);
  const adapter = context.createActOneAdapter(7, {inventoryUiOnlyV1: uiOnly});
  const originalObserve = adapter.observe;
  adapter.observe = async (...args) => { const value = await originalObserve(...args); raw.push(value); return value; };
  adapter.beginMission({mission: 'observe', session: 'active', createdAt: now});
  const engine = Engine.create(adapter, {session: 'active', enableInput: false, inventoryUiOnlyV1: uiOnly});
  return {adapter, engine, files, events, captures, raw, now: () => now,
    finish(saved = true, reject = false) {
      const item = pending.shift(); assert.ok(item, 'an owned image write must be pending');
      advance('png-completed', 17);
      if (reject) item.reject(new Error('Disk failed'));
      else { if (saved) files.set(item.name, 'synthetic image'); item.resolve(saved); }
    }};
}

// Export an actual completed observe receipt and serialized inventory snapshots for the Python consumer test.
async function nativeInventoryFixture(uiOnly = false) {
  const f = fixture({asyncWriter: false, uiOnly});
  await f.engine.observe();
  const request = {id: 'mission-00000', session: 'active', mission: 'observe',
    createdAt: f.now(), expectedFrameId: f.engine.getFrame()};
  await f.engine.process(request, () => {});
  const receipt = JSON.parse(f.files.get('receipts/active/mission-00000.json'));
  const observation = JSON.parse(f.files.get('observation.json'));
  const immutablePath = 'observations/active/frame-' + String(observation.frameId).padStart(4, '0') + '.json';
  return {fixtureKind: 'real-adapter-engine-synthetic-inventory', request, receipt, observation,
    immutableObservation: JSON.parse(f.files.get(immutablePath)), captures: f.captures, now: f.now()};
}

if (require.main === module && ['--emit-native-inventory', '--emit-native-inventory-ui'].includes(process.argv[2])) {
  nativeInventoryFixture(process.argv[2] === '--emit-native-inventory-ui').then(value => process.stdout.write(JSON.stringify(value))).catch(error => {
    process.stderr.write(String(error.stack || error)); process.exitCode = 1;
  });
} else {
  const test = require('node:test');

  test('capture stamp survives delayed capture/OCR/map/PNG and both engine publications', async () => {
    const f = fixture();
    const task = f.engine.observe();
    await Promise.resolve();
    assert.ok(f.events.some(row => row.kind === 'ocr'));
    assert.ok(f.events.some(row => row.kind === 'map'));
    assert.equal(f.files.has('observation.json'), false);
    assert.equal(f.files.has('observations/active/frame-0001.json'), false);
    f.finish();
    const returned = await task, expected = {session: 'active', frameId: 1,
      capturedAt: f.captures[0], source: 'game-capture-start'};
    const immutable = JSON.parse(f.files.get('observations/active/frame-0001.json'));
    const current = JSON.parse(f.files.get('observation.json'));
    assert.deepEqual(returned.hud.captureStamp, expected);
    assert.deepEqual(current, returned);
    assert.deepEqual(immutable, returned);
    assert.deepEqual(plain(f.raw[0].hud.captureStamp), expected);
    assert.equal(f.raw[0].capturedAt, expected.capturedAt);
    assert.equal(Object.hasOwn(returned, 'capturedAt'), false);
    assert.ok(returned.timestamp > expected.capturedAt + 11 + 23 + 17);
    assert.equal(returned.timestamp - expected.capturedAt, returned.timings.totalMs);
    assert.equal(returned.timings.captureMs, 11);
    assert.equal(returned.timings.mapMs, 23);
    assert.equal(returned.timings.pngWaitMs, 17);
    assert.ok(f.events.findIndex(row => row.kind === 'png-completed') <
      f.events.findIndex(row => row.kind === 'json' && row.name === 'observation.json'));
  });

  test('consecutive frames retain distinct original stamps and immutable engine copies', async () => {
    const f = fixture({asyncWriter: false});
    const first = await f.engine.observe();
    const retained = f.files.get('observations/active/frame-0001.json');
    const originalRaw = plain(f.raw[0]);
    first.hud.captureStamp.capturedAt = 0;
    const second = await f.engine.observe();
    assert.equal(f.files.get('observations/active/frame-0001.json'), retained);
    assert.deepEqual(plain(f.raw[0]), originalRaw);
    assert.equal(second.hud.captureStamp.frameId, 2);
    assert.equal(second.hud.captureStamp.capturedAt, f.captures[1]);
    assert.ok(f.captures[1] > f.captures[0]);
    assert.equal(second.timings.pngWriteMode, 'synchronous');
    assert.equal(second.timings.pngWriteMs, 100);
    assert.deepEqual(JSON.parse(f.files.get('observation.json')), second);
  });

  test('UI-only provenance agrees with the same capture stamp without localization', async () => {
    const f = fixture({asyncWriter: false, uiOnly: true});
    const observed = await f.engine.observe();
    assert.equal(observed.map, null);
    assert.equal(observed.hud.captureStamp.capturedAt, observed.uiObservation.observationStartedAtUnixMs);
    assert.equal(observed.hud.captureStamp.capturedAt, f.captures[0]);
    assert.equal(observed.uiObservation.kind, 'inventory-ui-only-v1');
    assert.equal(f.events.some(row => ['map', 'orientation'].includes(row.kind)), false);
    assert.deepEqual(JSON.parse(f.files.get('observation.json')), observed);
  });

  test('failed async persistence cannot publish a new frame or replace completed evidence', async () => {
    for (const reject of [false, true]) {
      const f = fixture(), firstTask = f.engine.observe(); f.finish(); await firstTask;
      const current = f.files.get('observation.json'), immutable = f.files.get('observations/active/frame-0001.json');
      const task = f.engine.observe(); f.finish(false, reject);
      await assert.rejects(task, error => error.code === 'CAPTURE_STORAGE_BLOCKED');
      assert.equal(f.files.get('observation.json'), current);
      assert.equal(f.files.get('observations/active/frame-0001.json'), immutable);
      assert.equal(f.files.has('observations/active/frame-0002.json'), false);
      assert.equal(f.raw.length, 1);
    }
  });

  test('failed synchronous persistence cannot publish a capture stamp', async () => {
    for (const syncSaved of [false, 'throw']) {
      const f = fixture({asyncWriter: false, syncSaved});
      await assert.rejects(f.engine.observe(), error => syncSaved === 'throw'
        ? error.message === 'Disk failed' : error.code === 'CAPTURE_STORAGE_BLOCKED');
      assert.equal(f.files.has('observation.json'), false);
      assert.equal(f.files.has('observations/active/frame-0001.json'), false);
      assert.equal(f.raw.length, 0);
    }
  });

  test('completed input-disabled inventory request retains actual producer chronology', async () => {
    const value = await nativeInventoryFixture(), stamp = value.observation.hud.captureStamp;
    assert.equal(value.receipt.status, 'completed');
    assert.equal(value.receipt.frameId, value.observation.frameId);
    assert.equal(value.request.session, stamp.session);
    assert.equal(stamp.frameId, value.observation.frameId);
    assert.ok(value.request.createdAt <= stamp.capturedAt);
    assert.ok(stamp.capturedAt < value.observation.timestamp);
    assert.ok(value.observation.timestamp <= value.receipt.timestamp);
    assert.deepEqual(value.immutableObservation, value.observation);
    assert.equal(value.observation.hud.world, false);
    assert.equal(value.observation.hud.health, null);
  });
}
