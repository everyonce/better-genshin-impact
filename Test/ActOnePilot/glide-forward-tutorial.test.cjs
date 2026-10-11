const test = require('node:test');
const assert = require('node:assert/strict');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

// Privacy-filtered OCR from recorded post-toast frame 437; the transient
// warning row and all unrelated/identity-bearing UI rows are omitted.
const frame437Rows = [
  { text: 'Press W to move forward', x: 827, y: 198, width: 321, height: 32 },
  { text: 'Meet Amber at the fountain plaza', x: 82, y: 250, width: 413, height: 29 },
];
const frame437Map = { map: 'Teyvat', x: -779.98828125, y: 2298.4638671875, cameraAngle: 24.5 };
const frame437Health = { current: 921, max: 1062 };
function observation(overrides = {}) {
  return {
    timestamp: 1000,
    frameId: 437,
    ocr: frame437Rows,
    map: frame437Map,
    hud: { tutorialStep: 'glideForward', world: true, health: frame437Health,
      dialogueReady: false, choice: false, journal: false, bigMap: false, objectiveChanged: false },
    ...overrides,
  };
}

test('recorded post-toast frame 437 permits one bounded 500 ms forward action without a warning banner', async () => {
  assert.equal(bgi.glideForwardState(frame437Rows, frame437Map, frame437Health, observation().hud), true);
  const calls = [];
  const result = await bgi.glideForward(observation(), 1500, {
    checkStop: () => calls.push(['checkStop']),
    forward: async ms => calls.push(['forward', ms]),
  });
  assert.equal(result, 'glideForward');
  assert.deepEqual(calls, [['checkStop'], ['forward', 500]]);
});

test('glide cue fails closed for wrong objective, missing map, unsafe HP, or UI/dialogue state', () => {
  const cases = [
    observation({ ocr: frame437Rows.map(row => row.text === 'Meet Amber at the fountain plaza' ? { ...row, text: 'Go to Mondstadt' } : row) }),
    observation({ map: null }),
    observation({ hud: { ...observation().hud, health: { current: 590, max: 1062 } } }),
    observation({ hud: { ...observation().hud, world: false } }),
    observation({ hud: { ...observation().hud, journal: true } }),
    observation({ hud: { ...observation().hud, bigMap: true } }),
    observation({ hud: { ...observation().hud, dialogueReady: true } }),
    observation({ hud: { ...observation().hud, choice: true } }),
    observation({ hud: { ...observation().hud, objectiveChanged: true } }),
    observation({ ocr: frame437Rows.filter(row => row.text !== 'Meet Amber at the fountain plaza') }),
    observation({ ocr: frame437Rows.filter(row => row.text !== 'Press W to move forward') }),
    observation({ ocr: frame437Rows.map(row => row.text === 'Meet Amber at the fountain plaza' ? { ...row, y: 229 } : row) }),
    observation({ map: { ...frame437Map, x: frame437Map.x + 8.1 } }),
  ];
  for (const current of cases) {
    assert.equal(bgi.glideForwardState(current.ocr, current.map, current.hud.health, current.hud), false);
  }
});

test('glide action rejects stale or unsafe observations without forwarding', async () => {
  let forwards = 0;
  const ops = { checkStop: () => {}, forward: async () => forwards++ };
  await assert.rejects(bgi.glideForward(observation({ timestamp: 0 }), 1500, ops), /Fresh safe fountain-plaza glide cue/);
  await assert.rejects(bgi.glideForward(observation({ hud: { ...observation().hud, world: false } }), 1500, ops), /Fresh safe fountain-plaza glide cue/);
  assert.equal(forwards, 0);
});
