const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const sourcePath = path.join(__dirname, '..', '..', 'BetterGenshinImpact', 'User', 'JsScript', 'AutoCommissionEnglishPilots', 'bgi.js');
const source = fs.readFileSync(sourcePath, 'utf8');

function harness({ inWorld = true, ocrResults = [], questRouteApi = true } = {}) {
  const log = {
    images: [], hudMatches: [], foundLists: [], foundRows: [], clicks: [],
    timers: [], cleared: 0, metricSets: [], metrics: [2560, 1440, 2],
    questRoutes: [], oldRoutes: [],
  };
  let ocrIndex = 0;
  const context = {
    RecognitionObject: {
      Ocr: (...args) => ({ kind: 'ocr', args }),
      TemplateMatch: (...args) => ({ kind: 'template', args }),
    },
    captureGameRegion: () => {
      const image = {
        disposed: 0,
        find: () => {
          const match = { disposed: 0, isEmpty: () => !inWorld, dispose() { this.disposed++; } };
          log.hudMatches.push(match);
          return match;
        },
        findMulti: () => {
          const result = ocrResults[ocrIndex++];
          if (result instanceof Error) throw result;
          const rows = result || [];
          const list = { count: rows.length, dispose() { this.disposed = (this.disposed || 0) + 1; } };
          rows.forEach((row, i) => {
            const object = Object.defineProperties({}, {
              disposed: { value: 0, writable: true, enumerable: true },
              ...Object.getOwnPropertyDescriptors(row),
              dispose: { value() { this.disposed++; }, enumerable: true },
            });
            list[i] = object;
            log.foundRows.push(object);
          });
          log.foundLists.push(list);
          return list;
        },
        dispose() { this.disposed++; },
      };
      log.images.push(image);
      return image;
    },
    file: {
      readImageMatSync: () => ({ disposed: 0, dispose() { this.disposed++; } }),
      readTextSync: (p) => `file:${p}`,
    },
    click: (x, y) => log.clicks.push([x, y]),
    log: { info: () => {} },
    sleep: async () => {},
    keyPress: () => {},
    keyDown: () => {},
    keyUp: () => {},
    genshin: { width: 1920, height: 1080 },
    getGameMetrics: () => log.metrics.slice(),
    setGameMetrics: (...args) => log.metricSets.push(args),
    AutoSkipConfig: function AutoSkipConfig() {},
    RealtimeTimer: function RealtimeTimer(name, config) { this.name = name; this.config = config; },
    dispatcher: {
      addTimer: (timer) => log.timers.push(timer),
      clearAllTriggers: () => { log.cleared++; },
    },
    pathingScript: {
      ...(questRouteApi ? { runForQuest: async (route) => log.questRoutes.push(route) } : {}),
      run: async (route) => log.oldRoutes.push(route),
    },
  };
  vm.createContext(context);
  vm.runInContext(source, context, { filename: sourcePath });
  return { adapter: context.createBgiPilotAdapter(), context, log };
}

test('AutoSkip is configured explicitly to preserve choices and disable unrelated automation, then cleaned up', () => {
  const { adapter, log } = harness();
  adapter.enableDialogue();
  assert.deepEqual(log.metricSets, [[1920, 1080, 1]]);
  assert.equal(log.timers.length, 1);
  const timer = log.timers[0];
  assert.equal(timer.name, 'AutoSkip');
  assert.equal(timer.config.enabled, true);
  assert.equal(timer.config.quicklySkipConversationsEnabled, true);
  assert.equal(timer.config.clickChatOption, '不选择选项');
  assert.equal(timer.config.skipBuiltInClickOptions, true);
  assert.equal(timer.config.customPriorityOptionsEnabled, false);
  assert.equal(timer.config.customPriorityOptions, '');
  for (const flag of ['submitGoodsEnabled', 'autoGetDailyRewardsEnabled', 'autoReExploreEnabled',
    'autoHangoutEventEnabled', 'runBackgroundEnabled', 'closePopupPagedEnabled']) {
    assert.equal(timer.config[flag], false, `${flag} must be explicitly disabled`);
  }
  adapter.clearDialogue();
  assert.equal(log.cleared, 1);
  assert.deepEqual(log.metricSets, [[1920, 1080, 1], [2560, 1440, 2]]);
});

test('capture uses a full-frame OCR row and disposes fresh capture resources on success', () => {
  const row = { text: 'Mara', x: 123, y: 234, width: 51, height: 19 };
  const { adapter, log } = harness({ ocrResults: [[row], []] });
  const frame = adapter.capture();
  assert.equal(frame.hud, true);
  assert.equal(frame.interactions.length, 1);
  for (const key of ['text', 'x', 'y', 'width', 'height']) assert.equal(frame.interactions[0][key], row[key]);
  assert.deepEqual(log.clicks, []);
  assert.equal(log.images[0].disposed, 1);
  assert.equal(log.hudMatches[0].disposed, 1);
  assert.equal(log.foundRows[0].disposed, 1);
  adapter.dispose();
});

test('capture disposes its image, template result, and OCR rows even when OCR extraction throws', () => {
  const { adapter, log } = harness({ ocrResults: [[{
    get text() { throw new Error('OCR row failure'); }, x: 1, y: 2, width: 3, height: 4,
  }], [], []] });
  assert.throws(() => adapter.capture(), /OCR row failure/);
  assert.equal(log.images.length, 1);
  assert.equal(log.images[0].disposed, 1);
  assert.equal(log.hudMatches[0].disposed, 1);
  assert.equal(log.foundRows[0].disposed, 1);
  assert.equal(adapter.capture().hud, true);
  assert.equal(log.images.length, 2);
  assert.equal(log.images[1].disposed, 1);
  assert.equal(log.hudMatches[1].disposed, 1);
  adapter.dispose();
});

test('click uses the row center in full-frame coordinates', () => {
  const { adapter, log } = harness();
  adapter.click({ x: 1050, y: 220, width: 720, height: 650 });
  assert.deepEqual(log.clicks, [[1410, 545]]);
});

test('path adapter requires runForQuest and never falls back to the legacy run API', async () => {
  const route = '{"info":{"name":"test"},"positions":[]}';
  const available = harness({ questRouteApi: true });
  await available.adapter.path(route);
  assert.deepEqual(available.log.questRoutes, [route]);
  assert.deepEqual(available.log.oldRoutes, []);

  const missing = harness({ questRouteApi: false });
  await assert.rejects(missing.adapter.path(route), /quest-route API/);
  assert.deepEqual(missing.log.questRoutes, []);
  assert.deepEqual(missing.log.oldRoutes, []);
});
