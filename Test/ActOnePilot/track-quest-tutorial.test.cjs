const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

// Privacy-filtered rows copied from live frame 813; personal UID/party text omitted.
const frame813 = [
  { text: 'Press Left Alt to show the cursor and', x: 769, y: 168, width: 469, height: 34 },
  { text: 'Left Alt', x: 634, y: 197, width: 113, height: 36 },
  { text: 'click here to navigate to the quest', x: 788, y: 202, width: 429, height: 29 },
  { text: 'objective', x: 944, y: 230, width: 121, height: 29 },
  { text: 'Go to the location designated by Amber', x: 80, y: 248, width: 469, height: 29 },
];
function tutorialObservation(overrides = {}) {
  return { timestamp: 1000, frameId: 813, ocr: frame813, hud: { tutorialStep: 'trackQuest' }, ...overrides };
}

test('frame 813 coachmark targets the highlighted quest icon, not the unreliable text center', () => {
  assert.equal(bgi.trackQuestState(frame813), true);
  const target = bgi.trackQuestTarget(tutorialObservation(), 1500);
  assert.deepEqual(target, { x: 58, y: 263 });
  assert.ok(target.x >= 35 && target.x <= 75, 'point is within highlighted icon column');
  assert.ok(target.y >= 230 && target.y <= 290, 'point is within highlighted quest row');
  assert.notDeepEqual(target, { x: 315, y: 263 }, 'text-center click previously failed to advance');
});

test('missing or ambiguous prompt/objective OCR fails closed', () => {
  for (const rows of [
    frame813.filter(row => row.text !== 'Press Left Alt to show the cursor and'),
    frame813.filter(row => row.text !== 'Left Alt'),
    frame813.filter(row => row.text !== 'click here to navigate to the quest'),
    frame813.filter(row => row.text !== 'objective'),
    frame813.filter(row => row.text !== 'Go to the location designated by Amber'),
    [...frame813, { ...frame813[4] }],
    [...frame813, { text: 'Go to the location designated by Amber', x: 800, y: 248, width: 400, height: 30 }],
  ]) assert.equal(bgi.trackQuestState(rows), false);
  for (const questRow of [
    { text: frame813[4].text, x: 30, y: 248, width: 469, height: 29 },
    { text: frame813[4].text, x: 80, y: 200, width: 469, height: 29 },
    { text: frame813[4].text, x: 80, y: 248, width: 80, height: 12 },
  ]) assert.equal(bgi.trackQuestTarget(tutorialObservation({ ocr: [...frame813.slice(0, 4), questRow] }), 1500), null, 'unsafe or nonstandard icon geometry fails closed');
  assert.equal(bgi.trackQuestTarget(tutorialObservation({ timestamp: 500 }), 1501), null, 'stale observations cannot select a target');
  assert.equal(bgi.trackQuestTarget(tutorialObservation({ hud: { tutorialStep: null } }), 1001), null, 'wrong tutorial state cannot select a target');
});

test('Alt-click shows cursor for 200 ms, clicks the icon point, settles, and releases within 260 ms', async () => {
  let now = 0;
  const events = [];
  await bgi.altClick({ x: 58, y: 263 }, {
    now: () => now,
    sleep: async ms => { events.push(['sleep', ms]); now += ms; },
    checkStop: () => events.push(['check']),
    keyDown: key => events.push(['down', key]),
    click: (x, y) => { assert.ok(now >= 200, 'cursor reveal settle precedes click'); events.push(['click', x, y]); },
    release: () => events.push(['release']),
  });
  assert.equal(now, 260);
  assert.deepEqual(events.slice(0, 3), [['check'], ['down', 'VK_LMENU'], ['check']]);
  const clickIndex = events.findIndex(event => event[0] === 'click');
  assert.ok(clickIndex > 3);
  assert.deepEqual(events[clickIndex], ['click', 58, 263]);
  assert.equal(events.filter(event => event[0] === 'sleep').length, 13);
  assert.deepEqual(events.at(-1), ['release']);
});

test('focus/stop failure during post-click settle still releases Alt', async () => {
  const events = [];
  let clicked = false;
  await assert.rejects(bgi.altClick({ x: 58, y: 263 }, {
    now: () => Date.now(),
    sleep: async ms => new Promise(resolve => setTimeout(resolve, ms)),
    checkStop: () => { if (clicked) throw new Error('focus lost'); },
    keyDown: key => events.push(['down', key]),
    click: () => { clicked = true; events.push(['click']); },
    release: () => events.push(['release']),
  }), /focus lost/);
  assert.deepEqual(events, [['down', 'VK_LMENU'], ['click'], ['release']]);
});

test('dialogue mission makes one trackQuest action, waits, and reobserves without generic input', async () => {
  let now = 0, index = 0;
  const first = { hud: { tutorialStep: 'trackQuest', world: false, choice: false, dialogueReady: false } };
  const returned = { hud: { tutorialStep: null, world: true, choice: false, dialogueReady: false } };
  const events = [];
  const api = {
    now: () => now,
    sleep: async ms => { events.push(['sleep', ms]); now += ms; },
    checkStop: () => {},
    advanceTutorial: async () => { events.push(['advanceTutorial']); return 'clicked'; },
    keyPress: async () => assert.fail('trackQuest must not use generic key input'),
    chooseChoice: async () => assert.fail('unexpected choice'),
  };
  const observe = async () => { const value = [first, returned][Math.min(index++, 1)]; events.push(['observe', value.hud.tutorialStep]); return value; };
  const result = await mission.runDialogue(api, observe);
  assert.equal(result.status, 'completed');
  assert.equal(result.presses, 1);
  assert.deepEqual(events, [['observe', 'trackQuest'], ['advanceTutorial'], ['sleep', 1000], ['observe', null]]);
});
