const test = require('node:test');
const assert = require('node:assert/strict');
const recovery = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/recovery.js');

const now = 10000;
const statue = { text: 'Statue of The Seven', x: 1216, y: 524, width: 275, height: 29 };
const fPrompt = { text: 'F', x: 1100, y: 524, width: 10, height: 20, frameId: 20 };
const healingPanel = { hud: { health: null }, ocr: [
  { text: 'Click on the character portrait to restore HP', x: 100, y: 40, width: 450, height: 25 },
  { text: "Statue's Blessing", x: 1450, y: 40, width: 200, height: 25 },
  { text: 'Restorative Power: 4838 / 5000', x: 1400, y: 115, width: 280, height: 25 },
] };
function observation(patch = {}) {
  return {
    timestamp: now, frameId: 20, map: { map: 'Teyvat', x: -1324.869, y: 2565.371 }, ocr: [statue],
    hud: { world: false, health: null, groundControls: true, climbing: false,
      journal: false, bigMap: false, dialogueReady: false, choice: false, auto: false,
      objectiveChanged: false, tutorialStep: null, enemyBars: [] },
    ...patch,
  };
}
function harness(nextFrames, prompt = fPrompt, overrides = {}) {
  const calls = [];
  let i = 0;
  const api = {
    now: () => now,
    checkStop() { calls.push(['checkStop']); },
    sleep: async ms => calls.push(['sleep', ms]),
    keyPress: async key => calls.push(['key', key]),
    statueInteractionF: async current => typeof prompt === 'function' ? prompt(current) : prompt,
    chooseStatueBlessing: async () => calls.push(['blessing']),
    ...overrides,
  };
  return { api, calls, observe: async () => nextFrames[Math.min(i++, nextFrames.length - 1)] };
}

test('valid-to-unresolved HP transition at measured Statue allows one adapter-corroborated interaction', async () => {
  const speaker = { timestamp: now, frameId: 21, hud: {}, map: null,
    ocr: [{ text: 'Statue of The Seven', x: 1216, y: 860, width: 275, height: 29 }, { text: "Statue's Blessing", x: 1200, y: 600, width: 200, height: 30 }] };
  const h = harness([observation({ frameId: 21, hud: { ...observation().hud, health: { current: 528, max: 1055 }, world: true } }),
    observation({ frameId: 22, hud: observation().hud }), speaker,
    { timestamp: now, frameId: 23, hud: {}, map: null, ocr: [{ text: 'Statue blessing screen' }] }],
    current => ({ ...fPrompt, frameId: current.frameId }));
  // The opening frame is valid HP, the next sampled frame loses health OCR.
  const result = await recovery.run(observation({ hud: { ...observation().hud, health: { current: 528, max: 1055 }, world: true } }), h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.deepEqual(h.calls.filter(x => x[0] === 'key'), [['key', 'VK_F']]);
  assert.equal(h.calls.filter(x => x[0] === 'blessing').length, 1);
});

test('no full-frame or adapter F corroboration means no input', async () => {
  const h = harness([], null);
  const result = await recovery.run(observation(), h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.deepEqual(h.calls, []);
});

test('stale observation, duplicate label, wrong geometry, and UI overlays are rejected', () => {
  const bad = [
    observation({ timestamp: now - 1001 }),
    observation({ ocr: [statue, { ...statue }] }),
    observation({ ocr: [{ ...statue, x: 1400 }] }),
    observation({ hud: { ...observation().hud, journal: true } }),
    observation({ hud: { ...observation().hud, dialogueReady: true } }),
    observation({ hud: { ...observation().hud, enemyBars: [{}] } }),
    observation({ map: null }),
    observation({ map: { map: 'Liyue', x: -1324.869, y: 2565.371 } }),
    observation({ map: { map: 'Teyvat', x: -1320, y: 2565.371 } }),
  ];
  for (const value of bad) assert.equal(recovery.safeStatueInteraction(value, now, fPrompt), false);
});

test('wrong or duplicate F prompt evidence is rejected', () => {
  assert.equal(recovery.safeStatueInteraction(observation(), now, { ...fPrompt, x: 900 }), false);
  assert.equal(recovery.safeStatueInteraction(observation(), now, { ...fPrompt, frameId: 19 }), false);
  assert.equal(recovery.safeStatueInteraction(observation({ ocr: [statue, fPrompt, { ...fPrompt }] }), now, fPrompt), false);
});

test('foreground/cancel adapter rejection prevents the F keypress', async () => {
  const h = harness([], fPrompt, { checkStop() { throw new Error('cancelled or game lost foreground'); } });
  await assert.rejects(recovery.run(observation(), h.api, h.observe), /cancelled or game lost foreground/);
  assert.equal(h.calls.some(x => x[0] === 'key'), false);
});

test('unknown post-interaction state stops without retrying F', async () => {
  const h = harness([observation()]);
  const result = await recovery.run(observation(), h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.match(result.reason, /speaker state not confirmed/);
  assert.equal(h.calls.filter(x => x[0] === 'key' && x[1] === 'VK_F').length, 1);
});

test('verified healing panel returns after transient animation OCR loss before the next paired heal', async () => {
  const missing = { hud: {}, ocr: [{ text: 'In combat Click on the' }] };
  const h = harness([missing, missing, healingPanel, missing, missing, missing, missing]);
  let heals = 0;
  h.api.healTravelerAtStatue = async () => { heals++; h.calls.push(['healTraveler']); };
  const result = await recovery.run(healingPanel, h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.match(result.reason, /panel did not return/);
  assert.equal(heals, 2, 'a second paired heal is allowed only after the panel reappears');
  assert.equal(h.calls.filter(x => x[0] === 'sleep' && x[1] === 500).length, 5);
  assert.equal(h.calls.some(x => x[0] === 'key' && x[1] === 'VK_ESCAPE'), false);
});

test('persistent panel OCR loss stops after one heal without another input', async () => {
  const missing = { hud: {}, ocr: [{ text: 'In combat Click on the' }] };
  const h = harness([missing, missing, missing, missing]);
  let heals = 0;
  h.api.healTravelerAtStatue = async () => { heals++; h.calls.push(['healTraveler']); };
  const result = await recovery.run(healingPanel, h.api, h.observe);
  assert.equal(result.status, 'stopped');
  assert.match(result.reason, /panel did not return/);
  assert.equal(heals, 1);
  assert.equal(h.calls.some(x => x[0] === 'key'), false);
});

test('Statue stop/focus errors from the guarded heal adapter propagate unchanged', async () => {
  const h = harness([]);
  h.api.healTravelerAtStatue = async () => { throw new Error('Fresh Statue healing panel required'); };
  await assert.rejects(recovery.run(healingPanel, h.api, h.observe), /Fresh Statue healing panel required/);
});
