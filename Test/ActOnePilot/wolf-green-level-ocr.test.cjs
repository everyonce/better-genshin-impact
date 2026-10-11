const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

const packageDir = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const source = fs.readFileSync(path.join(packageDir, 'bgi.js'), 'utf8');
const row = (text, x, y, width = 50, height = 20) => ({ text, x, y, width, height });

async function observe({ level = 5, greenRows = [], extraContours = [], wrongRed = false } = {}) {
  const barContour = { x: 762, y: 709, width: 164, height: 13 }; // full-screen center 1194,815.5
  const contours = [barContour, ...extraContours];
  const full = [row('Kaeya', 1664, 484), row('Trial', 1796, 463), row('1427/1427', 912, 1003, 195, 14), row('E', 1700, 1015, 30, 20)];
  if (level === 1) full.push(row('Defeat the nearby hilichurls', 100, 250, 300, 24));
  const cropCalls = [], counters = { normalOcr: 0, greenOcr: 0, inRange: [], regionsCreated: 0, regionsDisposed: 0,
    barLocalOcr: 0, cropsCreated: 0, cropsDisposed: 0, masksCreated: 0, masksDisposed: 0, convertedCreated: 0, convertedDisposed: 0 };
  const context = {
    Date: class extends Date { static now() { return 2000000; } },
    genshin: { isRemoteDesktopSession: true, windowsSessionId: 7, isGameForeground: true, getPositionFromMap: () => null, getCameraOrientation: () => 0 },
    file: { isExists: () => false, readTextSync: p => fs.readFileSync(path.join(packageDir, p), 'utf8'), writeTextSync: () => true, writeImageSync: () => true },
    RecognitionObject: { Ocr: () => ({}) },
    ImageRegion: class {
      constructor(mat) { this.mat = mat; this.width = 1920; this.height = 1080; counters.regionsCreated++; }
      findMulti() {
        const result = this.mat && this.mat.green ? greenRows.map(r => ({ ...r, x: (r.x - this.mat.x) * 3, y: (r.y - this.mat.y) * 3, width: r.width * 3, height: r.height * 3 })) : [];
        if (this.mat && this.mat.green) counters.greenOcr++; else counters.normalOcr++;
        if (this.mat && this.mat.barLocal) counters.barLocalOcr++;
        result.count = result.length; return result;
      }
      dispose() { counters.regionsDisposed++; if (this.mat && this.mat.dispose) this.mat.dispose(); }
    },
    OpenCvSharp: { OpenCvSharp: {
      Size: class { constructor(w, h) { this.width = w; this.height = h; } },
      Scalar: class { constructor(a, b, c) { this.values = [a, b, c]; } },
      ColorConversionCodes: { GRAY2BGR: 1 },
      RetrievalModes: { External: 0 }, ContourApproximationModes: { ApproxSimple: 0 }, Cv2: { boundingRect: c => c, contourArea: () => 0 },
    } },
    captureGameRegion: () => ({ width: 1920, height: 1080, srcMat: {}, findMulti: () => { const result = full.map(r => ({ ...r })); result.count = result.length; return result; },
      deriveCrop: (x, y, w, h) => {
        counters.cropsCreated++; cropCalls.push({ x, y, w, h });
        if (x === 350 && y === 100) return { srcMat: { inRange: (low, high) => {
          counters.inRange.push({ low: low.values, high: high.values }); counters.masksCreated++;
          return { findContoursAsArray: () => wrongRed ? [] : contours, dispose() { counters.masksDisposed++; } };
        } }, dispose() { counters.cropsDisposed++; } };
        if (w === 240 && h === 70) return { srcMat: { inRange: (low, high) => {
          counters.inRange.push({ low: low.values, high: high.values }); counters.masksCreated++;
          return { cvtColor: () => { counters.convertedCreated++; return { green: true, x, y, resize: () => ({ green: true, x, y, dispose() {} }), dispose() { counters.convertedDisposed++; } }; }, dispose() { counters.masksDisposed++; } };
        } }, dispose() { counters.cropsDisposed++; } };
        return { srcMat: { resize: () => ({ local: true, barLocal: w === 300 && h === 90, dispose() {} }) }, dispose() { counters.cropsDisposed++; } };
      }, dispose() {} }),
    sleep: async () => {}, click: () => {}, log: { info() {} },
  };
  vm.runInNewContext(source, context);
  const adapter = context.createActOneAdapter(7);
  const step = level === 5 ? 'wolfLookLeft' : level === 4 ? 'falconCombat' : 'combat';
  const objective = level === 1 ? 'Defeat the nearby hilichurls' : undefined;
  adapter.beginMission({ mission: 'questStep', step, objective, session: 'test', createdAt: 2000000 });
  const result = await adapter.observe('test', 1);
  return { bars: JSON.parse(JSON.stringify(result.hud.enemyBars)), diagnostic: JSON.parse(JSON.stringify(result.hud.enemyBarDiagnostic)), cropCalls, counters };
}

test('one green-mask OCR recovers only a spatially anchored Lv.5 above a bar-shaped red candidate', async () => {
  const result = await observe({ greenRows: [row('Lv.5', 1149, 772, 70, 28)] });
  assert.deepEqual(result.bars, [{ x: 1194, y: 815.5, width: 164, height: 13 }]);
  assert.equal(result.counters.greenOcr, 1);
  assert.deepEqual(result.diagnostic.greenMask.rows.map(r => r.text), ['Lv.5']);
  assert.deepEqual(result.diagnostic.greenMask.rows[0], { text: 'Lv.5', x: 1149, y: 772, width: 70, height: 28 });
  assert.deepEqual(result.cropCalls.filter(c => c.w === 240), [{ x: 1074, y: 738, w: 240, h: 70 }]);
  assert.deepEqual(result.counters.inRange.find(v => v.low[0] === 20), { low: [20, 110, 40], high: [130, 230, 190] });
});

test('wrong, absent, or ambiguous level labels never anchor a red bar', async () => {
  for (const greenRows of [[], [row('Lv.4', 1149, 772, 70, 28)],
    [row('Lv.5', 1149, 772, 70, 28), row('Lv.5', 1150, 772, 70, 28)]]) {
    const result = await observe({ greenRows });
    assert.deepEqual(result.bars, []);
  }
  const offAnchor = await observe({ greenRows: [row('Lv.5', 1149, 750, 70, 28)] });
  assert.deepEqual(offAnchor.bars, [], 'vertical distance outside the existing label-to-bar anchor is rejected');
});

test('Lv, 5 OCR punctuation is accepted only as a unique exact level-5 token at the bar anchor', async () => {
  const accepted = await observe({ greenRows: [row('Lv, 5', 1149, 772, 70, 28)] });
  assert.equal(accepted.bars.length, 1);
  for (const greenRows of [
    [row('Lv,4', 1149, 772, 70, 28)],
    [row('LV,55', 1149, 772, 70, 28)],
    [row('Lv, 5 enemy', 1149, 772, 70, 28)],
    [row('Lv, 5', 1149, 772, 70, 28), row('Lv, 5', 1150, 738, 70, 25)],
  ]) assert.deepEqual((await observe({ greenRows })).bars, []);
  const bar = { x: 1194, y: 815.5, width: 164, height: 13 };
  assert.equal(bgi.enemyBarAnchored(bar, [row('Lv, 5', 1149, 772, 70, 28)], 5), true);
  assert.equal(bgi.enemyBarAnchored(bar, [row('Lv,4', 1149, 772, 70, 28)], 5), false);
  assert.equal(bgi.enemyBarAnchored(bar, [row('Lv, 4', 1149, 772, 70, 28)], 4), false,
    'comma normalization does not change level-4 semantics');
  assert.equal(bgi.enemyBarAnchored(bar, [row('Lv.4', 1149, 772, 70, 28)], 4), true);
});

test('green fallback is level-5-only and keeps the four existing local reads unchanged', async () => {
  const extraContours = Array.from({ length: 7 }, (_, i) => ({ x: 80 + i * 150, y: 200, width: 20, height: 6 }));
  const level5 = await observe({ greenRows: [row('Lv.5', 1149, 772, 70, 28)], extraContours });
  assert.equal(level5.counters.barLocalOcr, 4);
  assert.equal(level5.counters.greenOcr, 1);
  for (const level of [1, 4]) {
    const other = await observe({ level, greenRows: [row('Lv.5', 1149, 772, 70, 28)], extraContours });
    assert.equal(other.counters.greenOcr, 0);
    assert.equal(other.counters.barLocalOcr, 4);
  }
});

test('masked diagnostics exclude the bottom-right UID and all crop/mask/region resources are disposed', async () => {
  const result = await observe({ greenRows: [row('Lv.5', 1149, 772, 70, 28), row('UID: 693300001', 1680, 1040, 200, 20)] });
  assert.doesNotMatch(JSON.stringify(result.diagnostic.greenMask), /UID|693300001/);
  assert.equal(result.counters.cropsCreated, result.counters.cropsDisposed);
  assert.equal(result.counters.masksCreated, result.counters.masksDisposed);
  assert.equal(result.counters.convertedCreated, result.counters.convertedDisposed);
  assert.equal(result.counters.regionsCreated, result.counters.regionsDisposed);
});
