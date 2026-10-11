const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const root = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const missionContext = {};
vm.runInNewContext(fs.readFileSync(path.join(root, 'bgi.js'), 'utf8'), missionContext);
vm.runInNewContext(fs.readFileSync(path.join(root, 'mission.js'), 'utf8'), missionContext);
const mission = missionContext.ActOneMission;

function observation(timestamp = 1000, overrides = {}) {
  return { timestamp, frameId: 4, map: { map: 'Teyvat', x: -1640.8, y: 2159 }, ocr: [],
    hud: { world: true, health: { current: 1213, max: 1213 }, enemyBars: [], journal: false, bigMap: false,
      dialogueReady: false, choice: false, objectiveChanged: false, climbing: false, tutorialStep: null, lowHealth: false },
    ...overrides };
}
function info({ width = 2560, height = 1440, fillsDesktop = true, session = 5, foreground = true } = {}) {
  return { windowsSessionId: session, isRemoteDesktopSession: true, isForeground: foreground, isMinimized: false,
    desktop: { virtualBounds: { width: 2560, height: 1440 } },
    gameWindow: { clientWidth: width, clientHeight: height }, fillsDesktop };
}

test('windowedGame readiness requires fresh safe world HUD, numeric health, and no combat or modal state', () => {
  const base = observation();
  assert.equal(bgi.windowedGameReady(base, 1000), true);
  for (const changed of [
    { timestamp: -1 },
    { hud: { ...base.hud, world: false } },
    { hud: { ...base.hud, health: { current: 719, max: 1213 } } },
    { hud: { ...base.hud, health: null } },
    { hud: { ...base.hud, enemyBars: [{ x: 100, y: 100 }] } },
    { hud: { ...base.hud, journal: true } },
    { hud: { ...base.hud, bigMap: true } },
    { hud: { ...base.hud, dialogueReady: true } },
    { hud: { ...base.hud, choice: true } },
    { hud: { ...base.hud, tutorialStep: 'switchAmber' } },
    { hud: { ...base.hud, climbing: true } },
    { map: null },
  ]) assert.equal(bgi.windowedGameReady({ ...base, ...changed }, 1000), false);
});

test('window mode decision toggles only verified fullscreen RDP geometry and no-ops verified windowed geometry', () => {
  assert.equal(bgi.windowModeDecision(info(), 5), 'toggle');
  assert.equal(bgi.windowModeDecision(info({ width: 1920, height: 1080, fillsDesktop: false }), 5), 'noop');
  for (const invalid of [
    info({ session: 1 }), info({ session: 6 }), info({ foreground: false }),
    { ...info(), isRemoteDesktopSession: false },
    { ...info(), fillsDesktop: false },
    { ...info(), desktop: { virtualBounds: { width: 1920, height: 1080 } } },
    info({ width: 1920, height: 1080, fillsDesktop: true }),
  ]) assert.equal(bgi.windowModeDecision(invalid, 5), null);
});

test('Alt+Enter holds fixed keys for at least 60ms and releases both on focus loss or cancellation', async () => {
  let now = 0; const calls = [];
  const chord = await bgi.windowedGameChord({ now: () => now, sleep: async ms => { calls.push(['sleep', ms]); now += ms; },
    checkStop() {}, keyDown: key => calls.push(['down', key]), keyUp: key => calls.push(['up', key]) });
  assert.ok(chord.holdMs >= 60);
  assert.deepEqual(calls.filter(c => c[0] !== 'sleep'), [
    ['down', 'VK_MENU'], ['down', 'VK_RETURN'], ['up', 'VK_RETURN'], ['up', 'VK_MENU'],
  ]);

  for (const failure of [new Error('focus lost'), new Error('cancelled')]) {
    const released = [];
    await assert.rejects(bgi.windowedGameChord({ now: () => 0, sleep: async () => {}, checkStop() { throw failure; },
      keyDown() {}, keyUp: key => released.push(key) }), failure);
    assert.deepEqual(released, ['VK_RETURN', 'VK_MENU']);
  }
});

test('windowedGame mission is a verified noop when already windowed', async () => {
  const current = observation(); let inputs = 0, waits = 0, captures = 0;
  const api = { now: () => 1000, checkStop() {}, requireInputReady() {}, sleep: async () => { waits++; },
    windowedGame() { inputs++; return { action: 'noop', info: info({ width: 1920, height: 1080, fillsDesktop: false }) }; } };
  const result = await mission.runQuestStep('windowedGame', current, api, async () => { captures++; return current; });
  assert.equal(result.status, 'completed');
  assert.equal(result.clicks, 0);
  assert.equal(result.fillsDesktop, false);
  assert.equal(inputs, 1);
  assert.equal(waits, 0);
  assert.equal(captures, 0);
});

test('windowedGame verifies readback after one toggle and never repeats on failed geometry', async () => {
  let now = 1000, toggles = 0, captures = 0;
  const current = observation();
  const api = { now: () => now, checkStop() {}, requireInputReady() {}, sleep: async ms => { now += ms; },
    windowedGame() { toggles++; return { action: 'altEnter', holdMs: 80 }; },
    windowInfo() { return info({ width: 1920, height: 1080, fillsDesktop: false }); } };
  const result = await mission.runQuestStep('windowedGame', current, api, async () => { captures++; return observation(now, { frameId: 5 }); });
  assert.equal(result.status, 'completed');
  assert.equal(result.clicks, 1);
  assert.equal(result.clientWidth, 1920);
  assert.equal(result.desktopWidth, 2560);
  assert.equal(result.fillsDesktop, false);
  assert.equal(toggles, 1);
  assert.equal(captures, 1);

  api.windowInfo = () => info();
  const failed = await mission.runQuestStep('windowedGame', observation(now), api, async () => observation(now));
  assert.equal(failed.status, 'stopped');
  assert.equal(failed.clicks, 1);
  assert.equal(toggles, 2);
});

test('windowedGame mission rejects unsafe scene before calling the guarded adapter', async () => {
  let inputs = 0;
  const api = { now: () => 1000, checkStop() {}, requireInputReady() {}, windowedGame() { inputs++; } };
  const result = await mission.runQuestStep('windowedGame', observation(1000, { hud: { world: true } }), api, async () => null);
  assert.equal(result.status, 'stopped');
  assert.equal(result.clicks, 0);
  assert.equal(inputs, 0);
});
