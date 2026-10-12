const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const recovery = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/recovery.js');

const captures = JSON.parse(fs.readFileSync(path.join(__dirname, 'recovery-captures.json'), 'utf8'));
const capture = frameId => captures.find(frame => frame.frameId === frameId);

const target = { map: 'Teyvat', x: -1323.474, y: 2566.115, cameraAngle: 0 };
function world(hp = 1000, x = target.x, extra = {}) {
  return { map: { ...target, x }, hud: { world: true, health: { current: hp, max: 1000 }, ...extra.hud }, ocr: extra.ocr || [] };
}
function harness(observations, overrides = {}) {
  const calls = [];
  let i = 0;
  const api = {
    checkStop() {}, sleep: async ms => calls.push(['sleep', ms]),
    keyPress: async key => calls.push(['key', key]),
    teleportStarfellStatue: async () => calls.push(['teleport']),
    forward: async ms => calls.push(['forward', ms]),
    rotate: async dx => calls.push(['rotate', dx]),
    pauseCombat: async () => { calls.push(['pause']); return true; },
    chooseStatueBlessing: async () => calls.push(['blessing']),
    healTravelerAtStatue: async () => calls.push(['healTraveler']),
    ...overrides,
  };
  return { calls, api, observe: async () => observations[Math.min(i++, observations.length - 1)], count: () => i };
}

test('unrelated journal is rejected before any input', async () => {
  const h = harness([]);
  const r = await recovery.run({ hud: { journal: true }, ocr: [{ text: 'Other quest' }] }, h.api, h.observe);
  assert.equal(r.status, 'stopped');
  assert.deepEqual(h.calls, []);
});

test('captured missing Statue whitespace still opens exactly one nearby healing interaction',async()=>{
  const interaction=world(719,target.x,{ocr:[{text:'Statue of TheSeven',x:1216,y:524,width:277,height:29}]});
  const speaker={map:null,hud:{world:false,dialogueReady:true},ocr:[{text:'Statue of The Seven',x:900,y:860}]};
  let interacted=false;
  const h=harness([speaker],{keyPress:async key=>{if(key==='VK_F')interacted=true;}});
  h.observe=async()=>interacted?speaker:interaction;
  const result=await recovery.run(interaction,h.api,h.observe);
  assert.equal(interacted,true);
  assert.equal(result.status,'stopped');
  assert.match(result.reason,/Statue blessing/);
});

test('fresh world observation within 15 units after journal close skips teleport', async () => {
  const h = harness([world(1000, target.x - 2), world(1000, target.x - 2), { hud: { journal: true } }]);
  const r = await recovery.run({ hud: { journal: true }, ocr: [{ text: 'Going Upon the Breeze' }] }, h.api, h.observe);
  assert.equal(r.status, 'completed');
  assert.deepEqual(h.calls.filter(x => x[0] === 'key'), [['key', 'VK_ESCAPE']]);
  assert.equal(h.calls.filter(x => x[0] === 'teleport').length, 0);
});

test('teleport loading fade is polled until world HUD, then health and pause are verified', async () => {
  const h = harness([
    { hud: { journal: true } }, world(1000, target.x - 100),
    { hud: { loading: true } }, { hud: { loading: true } }, world(1000),
    { hud: { journal: true } },
  ]);
  const r = await recovery.run({ hud: { journal: true }, ocr: [{ text: 'Going Upon the Breeze' }] }, h.api, h.observe);
  assert.equal(r.status, 'completed');
  assert.equal(h.calls.filter(x => x[0] === 'teleport').length, 1);
  assert.ok(h.calls.some(x => x[0] === 'sleep' && x[1] === 500));
  assert.equal(h.count(), 6);
});

test('low HP opens only the recognized nearby Statue interaction for inspection', async () => {
  const nearStatue = world(500, target.x, { ocr: [{ text: 'Statue of The Seven', x: 1300, y: 550 }] });
  const h = harness([
    ...Array.from({ length: 10 }, () => nearStatue),
    ...Array.from({ length: 7 }, () => ({ hud: { world: true }, ocr: [{ text: 'Statue menu' }] })),
  ]);
  const r = await recovery.run(world(500, target.x), h.api, h.observe);
  assert.equal(r.status, 'stopped');
  assert.equal(r.reason, 'Statue healing menu opened; inspect options');
  assert.deepEqual(h.calls.filter(x => x[0] === 'key'), [['key', 'VK_F']]);
  assert.equal(h.calls.some(x => x[0] === 'pause'), false);
});

test('recognized Statue speaker reveals and selects the blessing, then stops for inspection', async () => {
  const speaker = { text: 'Statue of The Seven', x: 1200, y: 860 };
  const h = harness([
    { hud: {}, ocr: [speaker] },
    { hud: {}, ocr: [speaker] },
    { hud: {}, ocr: [speaker, { text: "Statue's Blessing", x: 1500, y: 600 }] },
    ...Array.from({ length: 7 }, () => ({ hud: {}, ocr: [{ text: 'Statue healing panel' }] })),
  ]);
  const r = await recovery.run({ hud: {}, ocr: [speaker] }, h.api, h.observe);
  assert.equal(r.status, 'stopped');
  assert.deepEqual(h.calls.filter(x => x[0] === 'key'), [['key', 'VK_SPACE']]);
  assert.equal(h.calls.filter(x => x[0] === 'blessing').length, 1);
  assert.ok(h.count() <= 10);
});

test('recognized Traveler healing panel clicks five bounded charges, closes, waits for HUD, and verifies pause', async () => {
  const panel = { hud: { health: { current: 500, max: 1000 } }, ocr: [
    { text: 'Click on the character portrait to restore HP', x: 100, y: 40, width: 450, height: 25 },
    { text: "Statue's Blessing", x: 1450, y: 40, width: 200, height: 25 },
    { text: 'Restorative Power: 4838 / 5000', x: 1400, y: 115, width: 280, height: 25 },
  ] };
  const h = harness([
    ...Array.from({ length: 5 }, () => panel),
    { hud: { loading: true } }, world(1000), { hud: { journal: true } },
  ]);
  const r = await recovery.run(panel, h.api, h.observe);
  assert.equal(r.status, 'completed');
  assert.equal(h.calls.filter(x => x[0] === 'healTraveler').length, 5);
  assert.deepEqual(h.calls.filter(x => x[0] === 'key'), [['key', 'VK_ESCAPE']]);
  assert.equal(h.calls.filter(x => x[0] === 'pause').length, 1);
  assert.equal(h.count(), 8);
});

test('healing panel is rejected when its exact title or positive Restorative Power anchor is absent', () => {
  const panel = capture(56);
  assert.ok(panel, 'sanitized healing capture exists');
  assert.equal(recovery.hasStatueHealingPanel(panel), true);
  for (const mutate of [
    rows => rows.filter(row => !/^Statue.s Blessing$/.test(row.text.trim())),
    rows => rows.filter(row => !/^Restorative Power:/.test(row.text.trim())),
    rows => rows.map(row => row.text.startsWith('Restorative Power:') ? { ...row, text: 'Restorative Power: 0 / 5000' } : row),
  ]) {
    assert.equal(recovery.hasStatueHealingPanel({ ...panel, ocr: mutate(panel.ocr) }), false);
  }
});

test('recorded Statue frames 53→56→85→86 complete five guarded heals and verify the journal', async () => {
  const blessingOptions = capture(53);
  const healingPanel = capture(56);
  const fullHealth = capture(85);
  const journal = capture(86);
  assert.ok(blessingOptions && healingPanel && fullHealth && journal, 'required sanitized capture frames exist');
  const h = harness([
    healingPanel,
    ...Array.from({ length: 5 }, () => healingPanel),
    fullHealth,
    journal,
  ]);
  const r = await recovery.run(blessingOptions, h.api, h.observe);
  assert.equal(r.status, 'completed');
  assert.equal(r.reason, 'Statue healing applied');
  assert.equal(r.health.current, 1062);
  assert.equal(h.calls.filter(x => x[0] === 'blessing').length, 1);
  assert.equal(h.calls.filter(x => x[0] === 'healTraveler').length, 5);
  assert.deepEqual(h.calls.filter(x => x[0] === 'key'), [['key', 'VK_ESCAPE']]);
  assert.equal(h.calls.filter(x => x[0] === 'pause').length, 1);
});

test('recorded healing panel with changed or missing instruction never clicks Traveler', async () => {
  const recordedPanel = capture(56);
  for (const ocr of [
    recordedPanel.ocr.map(row => row.text.includes('Click on the character portrait')
      ? { ...row, text: 'Click on the character to restore HP' } : row),
    recordedPanel.ocr.filter(row => !row.text.includes('Click on the character portrait')),
  ]) {
    const changed = { ...recordedPanel, ocr };
    const h = harness([]);
    const r = await recovery.run(changed, h.api, h.observe);
    assert.equal(r.status, 'stopped');
    assert.equal(h.calls.some(x => x[0] === 'healTraveler'), false);
    assert.deepEqual(h.calls, []);
  }
});
