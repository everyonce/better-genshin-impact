const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

const rows = [
  { text: 'In Progress', x: 138, y: 30, width: 149, height: 35 },
  { text: 'City of Freedom', x: 188, y: 270, width: 213, height: 35 },
  { text: 'Go to the location designated by Amber', x: 924, y: 254, width: 491, height: 29 },
  { text: 'Click to navigate to quest', x: 1507, y: 929, width: 291, height: 38 },
  { text: 'objective', x: 1600, y: 957, width: 111, height: 35 },
  { text: 'Navigate', x: 1602, y: 1003, width: 139, height: 36 },
];
function observation(overrides = {}) {
  return { timestamp: 1000, frameId: 803, ocr: rows, hud: { journal: true, tutorialStep: 'navigateQuest' }, ...overrides };
}

test('frame 803 exact journal, selected quest, Amber objective, coachmark, and unique button are recognized', () => {
  assert.equal(bgi.navigateQuestState(rows), true);
  const button = bgi.navigateQuestButton(observation(), 1500);
  assert.deepEqual(button, rows[5]);
  assert.deepEqual({ x: Math.round(button.x + button.width / 2), y: Math.round(button.y + button.height / 2) }, { x: 1672, y: 1021 });
});

test('navigate quest state fails closed when any required context is missing or ambiguous', () => {
  for (const changed of [
    rows.filter(r => r.text !== 'In Progress'),
    rows.filter(r => r.text !== 'City of Freedom'),
    rows.filter(r => r.text !== 'Go to the location designated by Amber'),
    rows.filter(r => r.text !== 'objective'),
    rows.filter(r => r.text !== 'Navigate'),
    [...rows, { ...rows[5] }],
    [...rows, { text: 'Navigate', x: 1200, y: 1000, width: 100, height: 30 }],
  ]) assert.equal(bgi.navigateQuestState(changed), false);
  assert.equal(bgi.navigateQuestState([...rows, { text: 'Go to Liyue', x: 924, y: 254, width: 300, height: 30 }]), true,
    'unrelated OCR elsewhere does not change the selected, exact objective evidence');
});

test('navigate button selector requires current matching journal/tutorial evidence', () => {
  assert.equal(bgi.navigateQuestButton(observation(), 2001), null, 'stale frame');
  assert.equal(bgi.navigateQuestButton(observation({ hud: { journal: false, tutorialStep: 'navigateQuest' } }), 1001), null);
  assert.equal(bgi.navigateQuestButton(observation({ hud: { journal: true, tutorialStep: null } }), 1001), null);
  assert.equal(bgi.navigateQuestButton(observation({ ocr: [...rows, { ...rows[5] }] }), 1001), null, 'ambiguous button');
});

test('dialogue mission makes one tutorial action then waits and observes before continuing', async () => {
  let now = 1000, index = 0;
  const first = { hud: { tutorialStep: 'navigateQuest', world: false, choice: false, dialogueReady: false } };
  const returned = { hud: { tutorialStep: null, world: true, choice: false, dialogueReady: false } };
  const events = [];
  const api = {
    now: () => now,
    sleep: async ms => { events.push(['sleep', ms]); now += ms; },
    checkStop: () => {},
    advanceTutorial: async () => { events.push(['advanceTutorial']); return 'clicked'; },
    keyPress: async () => assert.fail('must not send generic Space during journal tutorial'),
    chooseChoice: async () => assert.fail('unexpected choice'),
  };
  const observe = async () => { const value = [first, returned][Math.min(index++, 1)]; events.push(['observe', value.hud.tutorialStep]); return value; };
  const result = await mission.runDialogue(api, observe);
  assert.equal(result.status, 'completed');
  assert.equal(result.reason, 'world_returned');
  assert.equal(result.presses, 1);
  assert.deepEqual(events, [['observe', 'navigateQuest'], ['advanceTutorial'], ['sleep', 1000], ['observe', null]]);
});
