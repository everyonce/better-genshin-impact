const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

// Privacy-filtered OCR rows recorded on frames 93-95; the UID row is excluded.
const dressingRows = [
  { text: 'Dressing Room', x: 803, y: 514, width: 309, height: 53 },
  { text: 'Dressing Room unlocked. Collect unique wind', x: 673, y: 582, width: 569, height: 31 },
  { text: 'gliders and outfits to alter the appearance of', x: 677, y: 609, width: 565, height: 33 },
  { text: 'your characters.', x: 852, y: 643, width: 211, height: 27 },
];
const banner = { map: null, ocr: dressingRows, hud: { world: false, dialogueReady: false,
  choice: false, journal: false, bigMap: false } };
const unknown = { map: null, ocr: [], hud: { world: false, dialogueReady: false,
  choice: false, journal: false, bigMap: false } };
const world = { map: { map: 'Teyvat', x: -764.2, y: 2307.9 }, ocr: [], hud: { world: true,
  dialogueReady: false, choice: false, journal: false, bigMap: false, objectives: [] } };

function harness(sequence) {
  let now = 0, index = 0; const calls = [];
  const api = {
    now: () => now,
    sleep: async ms => { calls.push(['sleep', ms]); now += ms; },
    checkStop: () => {},
    advanceTutorial: async () => assert.fail('Dressing Room unlock must not receive input'),
    keyPress: async () => assert.fail('Dressing Room unlock must not receive Space'),
    chooseChoice: async () => assert.fail('Dressing Room unlock must not click a choice'),
  };
  async function observe() { calls.push(['observe']); return sequence[Math.min(index++, sequence.length - 1)]; }
  return { calls, api, run: () => mission.runDialogue(api, observe), now: () => now };
}

test('exact unlock notice polls without input and resets prior generic unknown budget', async () => {
  const sequence = [...Array(5).fill(unknown), banner, banner, ...Array(5).fill(unknown), world];
  const h = harness(sequence);
  const result = await h.run();
  assert.equal(result.status, 'completed');
  assert.equal(result.reason, 'world_returned');
  assert.equal(result.presses, 0);
  assert.equal(h.calls.filter(c => c[0] === 'sleep' && c[1] === 1000).length, 12);
  assert.equal(h.calls.filter(c => c[0] === 'observe').length, 13);
});

test('near-match unlock text and wrong screen do not bypass ordinary unknown stop', async () => {
  const wrongRows = dressingRows.map(row => row.text === 'your characters.' ? { ...row, text: 'your character.' } : row);
  for (const current of [
    { ...banner, ocr: wrongRows },
    { ...banner, map: { map: 'Teyvat', x: 0, y: 0 } },
    { ...banner, ocr: dressingRows.filter(row => row.text !== 'Dressing Room') },
  ]) {
    const h = harness(Array(8).fill(current));
    const result = await h.run();
    assert.equal(result.status, 'stopped');
    assert.equal(result.reason, 'unrecognized_dialogue_state');
    assert.equal(result.presses, 0);
    assert.equal(h.calls.filter(c => c[0] === 'observe').length, 6);
  }
});

test('persistent exact unlock notice stays observation-only within the 60 second mission bound', async () => {
  const h = harness([banner]);
  const result = await h.run();
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'dialogue_limit_reached');
  assert.equal(result.presses, 0);
  assert.equal(h.now(), 60000);
  assert.equal(h.calls.filter(c => c[0] === 'observe').length, 61);
  assert.equal(h.calls.filter(c => c[0] === 'sleep' && c[1] === 1000).length, 60);
});
