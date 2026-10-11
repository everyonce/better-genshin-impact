const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const packageDir = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const source = fs.readFileSync(path.join(packageDir, 'bgi.js'), 'utf8');
const row = (text, x, y, width = 50, height = 20) => ({ text, x, y, width, height });

async function observe({ step, full = [], crop = [], world = false, menu = false, auto = false, health = true }) {
  let partyCrops = 0;
  const rows = [...full, row('E', 1700, 1015), ...(health ? [row('1213/1213', 910, 1000, 100, 25)] : []), ...(menu ? [row('Exploration Progress', 100, 100)] : []), ...(auto ? [row('Auto', 100, 100)] : [])];
  const context = {
    Date: class extends Date { static now() { return 2000000; } },
    genshin: { isRemoteDesktopSession: true, windowsSessionId: 7, isGameForeground: true,
      getPositionFromMap: () => world ? { x: 1, y: 2 } : null, getCameraOrientation: () => 0 },
    file: { isExists: () => false, readTextSync: p => fs.readFileSync(path.join(packageDir, p), 'utf8'),
      writeTextSync: () => true, writeImageSync: () => true },
    RecognitionObject: { Ocr: (x, y, w, h) => ({ x, y, w, h }) },
    ImageRegion: class {
      constructor(mat) { this.mat = mat; this.width = 1920; this.height = 1080; }
      findMulti(ro) {
        const found = (this.mat && this.mat.party ? crop : rows).map(r => ({ ...r }));
        found.count = found.length;
        return found;
      }
      dispose() {}
    },
    OpenCvSharp: { OpenCvSharp: { Size: class { constructor(w, h) { this.width = w; this.height = h; } },
      Scalar: class { constructor() {} }, RetrievalModes: { External: 0 }, ContourApproximationModes: { ApproxSimple: 0 },
      Cv2: { boundingRect: c => c, contourArea: () => 0 } } },
    captureGameRegion: () => ({ width: 1920, height: 1080, srcMat: {},
      findMulti: ro => { const found = rows.map(r => ({ ...r })); found.count = found.length; return found; },
      deriveCrop: (x, y, w, h) => {
        if (x === 1630 && y === 330 && w === 230) partyCrops++;
        return { srcMat: { resize: () => ({ party: x === 1630 && y === 330 && w === 230 && h === 300 }),
          inRange: () => ({ findContoursAsArray: () => [], dispose() {} }) }, dispose() {} };
      }, dispose() {} }),
    sleep: async () => {}, click: () => {}, log: { info() {} },
  };
  vm.runInNewContext(source, context);
  const adapter = context.createActOneAdapter(7);
  adapter.beginMission({ mission: 'questStep', step, session: 'test', createdAt: 2000000 });
  await adapter.observe('test', 1);
  return partyCrops;
}

test('Wolf entry recrops the party labels when full-frame OCR misses Lumina', async () => {
  assert.equal(await observe({ step: 'wolfEntryApproach', full: [row('Amber', 1660, 450)], crop: [row('Lumina', 300, 90)] }), 1);
});

test('Wolf trial recrops for missing exact Kaeya and Trial labels in the third-slot area', async () => {
  assert.equal(await observe({ step: 'wolfPause', full: [row('Amber', 1660, 450)], crop: [row('Kaeya', 150, 150), row('Trial', 450, 120)] }), 1);
});

test('complete full-frame Wolf party OCR avoids another crop', async () => {
  assert.equal(await observe({ step: 'wolfEntryApproach', full: [row('Lumina', 1660, 350), row('Amber', 1660, 450)] }), 0);
  assert.equal(await observe({ step: 'wolfPause', full: [row('Kaeya', 1660, 450), row('Trial', 1800, 450)] }), 0);
});

test('Wolf party crop is excluded on world, menu, or missing-health frames', async () => {
  for (const state of [{ world: true }, { menu: true }, { health: false }]) {
    assert.equal(await observe({ step: 'wolfEntryApproach', full: [], crop: [row('Lumina', 300, 90)], ...state }), 0);
  }
});

test('existing Falcon party fallback still crops for missing labels and skips auto/menu frames', async () => {
  assert.equal(await observe({ step: 'falconEntryApproach', crop: [row('Amber', 300, 120), row('Trial', 510, 120)] }), 1);
  assert.equal(await observe({ step: 'falconEntryApproach', auto: true }), 0);
  assert.equal(await observe({ step: 'falconEntryApproach', menu: true }), 0);
});
