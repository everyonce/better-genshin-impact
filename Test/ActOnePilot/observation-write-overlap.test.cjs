const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const source = fs.readFileSync(path.join(root, 'bgi.js'), 'utf8');

// Exercise the real observer with controlled recognition and a genuinely pending writer.
function harness({asyncWriter = true, failRecognition = false} = {}) {
  const events = [];
  let now = 2000000, completeWrite, rejectWrite;
  const pending = new Promise((resolve, reject) => { completeWrite = resolve; rejectWrite = reject; });
  const row = (text, x, y, width = 100, height = 20) => ({text, x, y, width, height});
  const rows = [row('1427/1427', 906, 1001), row('E', 1700, 1015), row('Q', 1800, 1015)];
  function found(items) {
    events.push('recognize'); now += 5;
    if (failRecognition) throw new Error('Recognition failed');
    const value = items.map(r => ({...r})); value.count = value.length; return value;
  }
  const file = {
    isExists: () => false,
    readTextSync: p => fs.readFileSync(path.join(root, p), 'utf8'),
    writeTextSync: () => true,
    writeImageSync: () => { events.push('write-sync'); now += 100; return true; }
  };
  if (asyncWriter) file.writeImageAsync = () => { events.push('schedule-write'); now += 2; return pending; };
  const context = {
    Date: class extends Date { static now() { return now; } },
    genshin: {isRemoteDesktopSession: true, windowsSessionId: 7, isGameForeground: true,
      getPositionFromMap: () => { events.push('map'); return null; }, getCameraOrientation: () => 0},
    file, RecognitionObject: {Ocr: () => ({})},
    ImageRegion: class { constructor() { this.width = 1920; this.height = 1080; }
      findMulti() { return found([]); } dispose() {} },
    OpenCvSharp: {OpenCvSharp: {Size: class {}, Scalar: class {}, RetrievalModes: {External: 0},
      ContourApproximationModes: {ApproxSimple: 0}, Cv2: {boundingRect: value => value, contourArea: () => 0}}},
    captureGameRegion: () => ({width: 1920, height: 1080, srcMat: {},
      findMulti: () => found(rows), deriveCrop: () => ({srcMat: {resize: () => ({}),
        inRange: () => ({findContoursAsArray: () => [], dispose() {}})}, dispose() {}}),
      dispose() { events.push('dispose-capture'); }}),
    sleep: async () => {}, click: () => {}, log: {info() {}}
  };
  vm.runInNewContext(source, context);
  const adapter = context.createActOneAdapter(7);
  adapter.beginMission({mission: 'observe', session: 'overlap', createdAt: now});
  return {adapter, events, finish(saved = true) { now += 17; events.push('persisted'); completeWrite(saved); },
    fail() { rejectWrite(new Error('Disk failed')); }};
}

test('PNG starts before recognition; proof waits for persistence and retains the same image', async () => {
  const h = harness();
  let published = false;
  const task = h.adapter.observe('overlap', 1).then(o => { published = true; return o; });
  await Promise.resolve();
  assert.equal(h.events[0], 'schedule-write');
  assert.ok(h.events.includes('recognize'));
  assert.ok(h.events.includes('map'));
  assert.equal(published, false);
  assert.equal(h.events.includes('write-sync'), false);
  assert.equal(h.events.includes('dispose-capture'), false);
  h.finish();
  const observation = await task;
  assert.equal(observation.screenshotPath, 'observations/overlap/frame-0001.png');
  assert.equal(observation.timings.pngWriteMode, 'overlapped');
  assert.equal(observation.timings.pngScheduleMs, 2);
  assert.equal(observation.timings.pngWaitMs, 17);
  assert.equal(observation.timings.pngWriteMs, 19);
  assert.equal(observation.timings.ocrFindMultiMs, observation.timings.ocrReadCount * 5);
  assert.equal(h.events.at(-1), 'dispose-capture');
});

test('storage refusal and rejected task never publish proof or retry synchronously', async () => {
  for (const reject of [false, true]) {
    const h = harness(), task = h.adapter.observe('overlap', 1);
    if (reject) h.fail(); else h.finish(false);
    await assert.rejects(task, error => error.code === 'CAPTURE_STORAGE_BLOCKED');
    assert.equal(h.events.includes('write-sync'), false);
    assert.equal(h.events.at(-1), 'dispose-capture');
  }
});

test('recognition failure releases the original image and drains the owned write', async () => {
  const h = harness({failRecognition: true});
  let settled = false;
  const task = h.adapter.observe('overlap', 1);
  task.then(() => { settled = true; }, () => { settled = true; });
  await Promise.resolve();
  assert.equal(h.events.includes('dispose-capture'), true);
  assert.equal(settled, false);
  h.finish();
  await assert.rejects(task, /Recognition failed/);
});

test('older runtime preserves its synchronous proof path and timing', async () => {
  const h = harness({asyncWriter: false});
  const observation = await h.adapter.observe('overlap', 1);
  assert.equal(h.events.includes('schedule-write'), false);
  assert.ok(h.events.indexOf('write-sync') > h.events.indexOf('recognize'));
  assert.equal(observation.timings.pngWriteMode, 'synchronous');
  assert.equal(observation.timings.pngWriteMs, 100);
  assert.equal(observation.timings.pngScheduleMs, 0);
  assert.equal(observation.timings.pngWaitMs, 0);
});
