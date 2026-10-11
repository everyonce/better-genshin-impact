const test = require('node:test');
const assert = require('node:assert/strict');
const engine = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/engine.js');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

test('questStep accepts only one bounded step identifier and no extra parameters', () => {
  const base = { session: 's', id: 'step', createdAt: 1000, expectedFrameId: 2, mission: 'questStep', step: 'glideOpen' };
  assert.equal(engine.validate(base, 's', 2, {}, 1000), null);
  for (const bad of [
    { ...base, step: 'GlideOpen' }, { ...base, step: 'glide_open' }, { ...base, step: 'a'.repeat(41) },
    { ...base, step: '' }, { ...base, key: 'VK_F' }, { ...base, objective: 'anything' },
  ]) assert.ok(engine.validate(bad, 's', 2, {}, 1000));
});

test('unsupported local quest step stops after a fresh observation without input', async () => {
  let now = 1000, frame = 0, ready = 0; const calls = [], writes = [];
  const api = {
    now: () => now, sleep: async ms => { now += ms; }, beginMission: () => {}, events: () => calls,
    checkStop: () => {}, requireInputReady: () => { ready++; }, release: () => {},
    write: (path, body) => writes.push([path, JSON.parse(body)]),
    observe: async (_, n) => { frame++; return { timestamp: now, screenshotPath: 'frame.png', map: null, ocr: [], hud: { world: false } }; },
    keyPress: async key => calls.push(['keyPress', key]), fireAerial: async ms => calls.push(['fireAerial', ms]),
  };
  const runner = engine.create(api, { session: 's', enableInput: true });
  await runner.observe();
  const request = { session: 's', id: 'unsupported-step', createdAt: now, expectedFrameId: runner.getFrame(), mission: 'questStep', step: 'templeDoor' };
  const result = await runner.process(request, () => ({ runQuestStep: mission.runQuestStep }));
  assert.equal(result, 'stopped');
  assert.equal(ready, 1);
  assert.deepEqual(calls, []);
  const receipt = writes.filter(([path]) => path === 'receipt.json').at(-1)[1];
  assert.equal(receipt.status, 'stopped');
  assert.equal(receipt.details.result.reason, 'Unsupported quest step: templeDoor');
});

test('missing fixed quest-step policy fails closed without input', async () => {
  let now = 1000, frame = 0; const writes = [], calls = [];
  const api = { now: () => now, sleep: async ms => { now += ms; }, beginMission: () => {}, events: () => calls,
    checkStop: () => {}, requireInputReady: () => {}, release: () => {}, write: (p,v) => writes.push([p,JSON.parse(v)]),
    observe: async () => ({ timestamp: now, screenshotPath: 'frame.png', map: null, ocr: [], hud: { world: false } }) };
  const runner = engine.create(api, { session:'s', enableInput:true }); await runner.observe();
  const request = { session:'s', id:'missing-step-policy', createdAt:now, expectedFrameId:runner.getFrame(), mission:'questStep', step:'futureStep' };
  assert.equal(await runner.process(request, () => ({})), 'stopped');
  const receipt = writes.filter(([p]) => p === 'receipt.json').at(-1)[1];
  assert.equal(receipt.details.result.reason, 'Unsupported quest step: futureStep');
  assert.deepEqual(calls, []);
});
