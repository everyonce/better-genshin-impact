const test = require('node:test');
const assert = require('node:assert/strict');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

// Privacy-filtered rows from recorded frame 440; identity-bearing and unrelated
// OCR is omitted while preserving the prompt/objective positions.
const frame440Rows = [
  { text: 'Press Space while in mid-air to glide', x: 784, y: 202, width: 383, height: 31 },
  { text: 'Meet Amber at the fountain plaza', x: 82, y: 250, width: 413, height: 29 },
];
const frame440Map = { map: 'Teyvat', x: -781.449, y: 2297.814, cameraAngle: 24.5 };
const frame440Health = { current: 921, max: 1062 };
function observation(overrides = {}) {
  return {
    timestamp: 1000,
    frameId: 440,
    ocr: frame440Rows,
    map: frame440Map,
    hud: { tutorialStep: 'glideOpen', world: true, health: frame440Health,
      dialogueReady: false, choice: false, journal: false, bigMap: false, objectiveChanged: false },
    ...overrides,
  };
}

test('recorded frame 440 allows one bounded 60 ms Space press', async () => {
  assert.equal(bgi.glideOpenState(frame440Rows, frame440Map, frame440Health, observation().hud), true);
  const calls = [];
  assert.equal(await bgi.glideOpen(observation(), 1500, {
    checkStop: () => calls.push('checkStop'),
    pressSpace: async ms => calls.push(['VK_SPACE', ms]),
  }), 'glideOpen');
  assert.deepEqual(calls, ['checkStop', ['VK_SPACE', 60]]);
});

test('glide-open recognition rejects wrong cue/objective, stale frames, or unsafe state without input', async () => {
  const invalid = [
    observation({ ocr: frame440Rows.map(row => row.text.startsWith('Press Space') ? { ...row, text: 'Press W to move forward' } : row) }),
    observation({ ocr: frame440Rows.map(row => row.text.startsWith('Meet Amber') ? { ...row, text: 'Go to Mondstadt' } : row) }),
    observation({ map: { ...frame440Map, x: frame440Map.x + 11.5 } }),
    observation({ hud: { ...observation().hud, health: { current: 590, max: 1062 } } }),
    observation({ hud: { ...observation().hud, world: false } }),
    observation({ hud: { ...observation().hud, journal: true } }),
    observation({ hud: { ...observation().hud, bigMap: true } }),
    observation({ hud: { ...observation().hud, dialogueReady: true } }),
    observation({ hud: { ...observation().hud, choice: true } }),
  ];
  let presses = 0;
  const ops = { checkStop: () => {}, pressSpace: async () => presses++ };
  for (const current of invalid) {
    await assert.rejects(bgi.glideOpen(current, 1500, ops), /Fresh safe glide-open cue/);
  }
  await assert.rejects(bgi.glideOpen(observation({ timestamp: 0 }), 1500, ops), /Fresh safe glide-open cue/);
  assert.equal(presses, 0);
});
