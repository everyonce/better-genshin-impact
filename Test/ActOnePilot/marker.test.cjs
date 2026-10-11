const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const bgiPath = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const markerAssets = ['assets/quest-marker.png', 'assets/quest-marker-near.png'];

function found(items = []) {
  items.count = items.length;
  return items;
}

function observeMarker(results) {
  const templateCalls = [];
  function findMulti(ro) {
    if (ro.kind === 'ocr') return found();
    templateCalls.push(ro);
    return found((results[ro.template] || []).map(point => ({
      x: point.x, y: point.y, width: point.width, height: point.height,
      dispose() {},
    })));
  }
  const image = {
    width: 1920,
    height: 1080,
    srcMat: {},
    deriveCrop() {
      return { srcMat: { resize: () => ({}) }, dispose() {} };
    },
    findMulti,
  };
  const context = {
    module: { exports: {} },
    genshin: {
      isRemoteDesktopSession: true,
      windowsSessionId: 5,
      isGameForeground: true,
      getPositionFromMap: () => ({ x: 0, y: 0 }),
      getCameraOrientation: () => 180,
    },
    file: {
      isExists: () => false,
      readTextSync: name => fs.readFileSync(path.join(path.dirname(bgiPath),name),'utf8'),
      writeTextSync: () => true,
      readImageMatSync: asset => ({ asset, dispose() {} }),
      writeImageSync: () => true,
    },
    RecognitionObject: {
      Ocr: () => ({ kind: 'ocr', dispose() {} }),
      TemplateMatch: mat => ({ kind: 'template', template: mat.asset, templateImageGreyMat: { dispose() {} } }),
    },
    OpenCvSharp: { OpenCvSharp: { Size: function Size() {} } },
    ImageRegion: function ImageRegion() { return { findMulti, dispose() {} }; },
    captureGameRegion: () => image,
    sleep: async () => {},
    keyUp: () => {},
  };
  vm.runInNewContext(fs.readFileSync(bgiPath, 'utf8'), context);
  const adapter = context.createActOneAdapter(5);
  adapter.beginMission({ objective: 'Investigate what Paimon has found' });
  return adapter.observe('test-session', 1).then(observation => ({ observation, templateCalls }));
}

test('crystal marker scans both scales and merges overlapping detections of one marker', async () => {
  const result = await observeMarker({
    [markerAssets[0]]: [{ x: 950, y: 330, width: 20, height: 20 }],
    [markerAssets[1]]: [{ x: 956, y: 333, width: 20, height: 20 }],
  });

  assert.deepEqual(result.templateCalls.map(call => call.template), markerAssets);
  assert.ok(result.templateCalls.every(call => call.threshold === 0.82 && call.use3Channels === true));
  assert.equal(result.observation.hud.worldMarker.x, 960);
  assert.equal(result.observation.hud.worldMarker.y, 340);
});

test('near marker template can identify the sole marker and distinct detections remain ambiguous', async () => {
  const nearOnly = await observeMarker({
    [markerAssets[1]]: [{ x: 1040, y: 350, width: 20, height: 20 }],
  });
  assert.equal(nearOnly.observation.hud.worldMarker.x, 1050);
  assert.equal(nearOnly.observation.hud.worldMarker.y, 360);

  const ambiguous = await observeMarker({
    [markerAssets[0]]: [{ x: 800, y: 320, width: 20, height: 20 }],
    [markerAssets[1]]: [{ x: 1200, y: 320, width: 20, height: 20 }],
  });
  assert.equal(ambiguous.observation.hud.worldMarker, null);
});
