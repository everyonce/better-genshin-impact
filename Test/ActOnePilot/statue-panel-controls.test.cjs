const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const packageDir = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const source = fs.readFileSync(path.join(packageDir, 'bgi.js'), 'utf8');

// Replay R63's retained frame-0010 OCR through the actual adapter, with inert native boundaries.
function adapterFixture({ scoped = true, omitScope = false, cropText = ['E', 'Q'], journal = false, foreignUid = false } = {}) {
  let clock = 2000000, captures = 0;
  const controls = [], inputs = [];
  const rows = [
    { text: ' 24 ms', x: 1802, y: 83, width: 89, height: 23 },
    { text: 'umina', x: 1698, y: 260, width: 65, height: 23 },
    { text: 'Amber', x: 1690, y: 349, width: 77, height: 29 },
    { text: ' Statue of The Seven', x: 1209, y: 521, width: 289, height: 38 },
    { text: '..', x: 1184, y: 534, width: 19, height: 13 },
    { text: '01540', x: 922, y: 1005, width: 73, height: 14 },
    { text: '9Enter', x: 42, y: 1024, width: 113, height: 29 },
    { text: 'e', x: 1684, y: 1026, width: 33, height: 27 },
    { text: 'q', x: 1802, y: 1026, width: 35, height: 27 },
    { text: foreignUid ? 'UID: 123456789' : 'UID: 693306810', x: 1684, y: 1050, width: 181, height: 29 },
  ];
  if (journal) rows.push({ text: 'In Progress', x: 143, y: 35, width: 180, height: 30 });
  // Both reads belong to the one mocked capture; the adapter still performs its real crop/merge logic.
  function found(values) {
    clock++;
    const result = values.map(row => ({ ...row }));
    result.count = result.length;
    return result;
  }
  // Only image reading is mocked. No key or click is needed to repair the observation.
  function crop(x, y, width, height) {
    let values = [];
    if (x === 1520 && y === 985) {
      controls.push([x, y, width, height]);
      values = cropText.map((text, i) => ({ text, x: (1684 + 120 * i - x) * 3,
        y: (1026 - y) * 3, width: 90, height: 81 }));
    } else if (x === 900 && y === 990) {
      values = [{ text: '4015/4015', x: 20, y: 20, width: 250, height: 45 }];
    }
    return { srcMat: { resize: () => ({ rows: values }),
      inRange: () => ({ findContoursAsArray: () => [], dispose() {} }) }, dispose() {} };
  }
  const context = {
    Date: class extends Date { static now() { return clock; } },
    genshin: { isRemoteDesktopSession: true, windowsSessionId: 3, isGameForeground: true,
      getPositionFromMap: () => ({ x: -1325.40234375, y: 2565.19140625 }), getCameraOrientation: () => 194 },
    file: { isExists: () => false, readTextSync: name => fs.readFileSync(path.join(packageDir, name), 'utf8'),
      writeTextSync: () => true, writeImageSync: () => true },
    RecognitionObject: { Ocr: () => ({}) },
    ImageRegion: class {
      constructor(mat) { this.mat = mat; this.width = 1920; this.height = 1080; }
      findMulti() { return found(this.mat.rows || []); }
      dispose() {}
    },
    OpenCvSharp: { OpenCvSharp: { Size: class {}, Scalar: class {},
      RetrievalModes: { External: 0 }, ContourApproximationModes: { ApproxSimple: 0 },
      Cv2: { boundingRect: value => value, contourArea: () => 0 } } },
    captureGameRegion() {
      captures++;
      return { width: 1920, height: 1080, srcMat: {}, findMulti: () => found(rows), deriveCrop: crop, dispose() {} };
    },
    sleep: async ms => { clock += ms; }, click: (...args) => inputs.push(['click', ...args]),
    keyDown: key => inputs.push(['down', key]), keyUp: key => inputs.push(['up', key]), log: { info() {} },
  };
  vm.runInNewContext(source, context);
  const adapter = context.createActOneAdapter(3);
  const request = { mission: 'recover', session: 'statue-controls', createdAt: clock };
  if (!omitScope) request.statuePanelOnly = scoped;
  adapter.beginMission(request);
  return { adapter, controls, inputs, captures: () => captures,
    observe: () => adapter.observe('statue-controls', 1) };
}

test('scoped recovery repairs the retained lowercase E/Q frame through one same-capture crop', async () => {
  const f = adapterFixture(), observation = await f.observe();
  assert.equal(f.captures(), 1);
  assert.deepEqual(f.controls, [[1520, 985, 390, 80]]);
  assert.equal(observation.hud.world, true);
  assert.equal(observation.hud.health.current, 4015);
  assert.equal(observation.hud.groundControls, true);
  assert.equal(f.adapter.statuePanelRecoveryWorldReady(observation), true);
  assert.deepEqual(f.inputs, []);
});

test('the scoped change does not enable this crop for ordinary recovery or journal frames', async () => {
  for (const options of [{ scoped: false }, { omitScope: true }, { journal: true }]) {
    const f = adapterFixture(options), observation = await f.observe();
    assert.deepEqual(f.controls, []);
    assert.equal(observation.hud.groundControls, false);
    assert.equal(f.adapter.statuePanelRecoveryWorldReady(observation), false);
    assert.deepEqual(f.inputs, []);
  }
});

test('empty, lowercase or Space crop output cannot fabricate ground controls', async () => {
  for (const cropText of [[], ['e', 'q'], ['Space']]) {
    const f = adapterFixture({ cropText }), observation = await f.observe();
    assert.equal(f.controls.length, 1);
    assert.equal(observation.hud.groundControls, false);
    assert.equal(f.adapter.statuePanelRecoveryWorldReady(observation), false);
    assert.deepEqual(f.inputs, []);
  }
});

test('repaired controls still cannot admit a different account to the scoped pause', async () => {
  const f = adapterFixture({ foreignUid: true }), observation = await f.observe();
  assert.equal(observation.hud.groundControls, true);
  assert.equal(f.adapter.statuePanelRecoveryWorldReady(observation), false);
  assert.deepEqual(f.inputs, []);
});
