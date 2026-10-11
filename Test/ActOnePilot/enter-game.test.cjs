const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const missionSource = fs.readFileSync(path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js'), 'utf8');
const missionContext = {};
vm.runInNewContext(fs.readFileSync(path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'), 'utf8'), missionContext);
vm.runInNewContext(missionSource, missionContext);
const mission = missionContext.ActOneMission;

function titleObservation(timestamp = 1000, rows = []) {
  return { timestamp, frameId: 7, map: null, hud: { world: false, journal: false, bigMap: false, dialogueReady: false, choice: false },
    ocr: rows.length ? rows : [
      { text: 'START GAME', x: 761, y: 472, width: 389, height: 67 },
      { text: 'CLICK TO BEGIN', x: 849, y: 570, width: 215, height: 34 },
      { text: 'America', x: 890, y: 907, width: 139, height: 37 },
      { text: 'OSREL 6.0.0', x: 1700, y: 1040, width: 120, height: 20 },
      { text: 'd***@example.com', x: 850, y: 1020, width: 130, height: 20 },
    ] };
}

test('title entry target requires a fresh unique centered English title and chooses Click to Begin', () => {
  const target = bgi.enterGameTarget(titleObservation(), 1000);
  assert.deepEqual(target, { x: 956, y: 587, label: 'CLICK TO BEGIN' });
  assert.equal(bgi.enterGameTarget(titleObservation(0), 1001), null);
  assert.equal(bgi.enterGameTarget(titleObservation(1001), 1000), null);
  assert.equal(bgi.enterGameTarget(titleObservation(0, [...titleObservation().ocr, titleObservation().ocr[1]]), 1000), null);
});

test('title entry rejects auth prompts, non-title screens, and ambiguous title geometry', () => {
  const auth = titleObservation(); auth.ocr.push({ text: 'Enter your password', x: 800, y: 700, width: 200, height: 30 });
  assert.equal(bgi.enterGameTarget(auth, 1000), null);
  assert.equal(bgi.enterGameAuthPrompt([{ text: 'Verification code' }]), true);
  assert.equal(bgi.enterGameTarget({ ...titleObservation(), hud: { world: true } }, 1000), null);
  const offCenter = titleObservation(); offCenter.ocr[1] = { text: 'CLICK TO BEGIN', x: 1400, y: 570, width: 215, height: 34 };
  assert.equal(bgi.enterGameTarget(offCenter, 1000), null);
});

test('enterGame makes one validated click and returns bounded post-click state', async () => {
  let now = 1000, clicks = 0, polls = 0;
  const initial = titleObservation();
  const api = { now: () => now, sleep: async ms => { now += ms; }, checkStop() {}, requireInputReady() {},
    startGame() { clicks++; return { x: 956, y: 587, frameId: initial.frameId }; } };
  const observe = async () => { polls++; return { timestamp: now, frameId: 7 + polls, map: null, hud: { world: false }, ocr: [{ text: 'Loading' }] }; };
  const result = await mission.runQuestStep('enterGame', initial, api, observe);
  assert.equal(clicks, 1);
  assert.equal(result.status, 'completed');
  assert.equal(result.clicks, 1);
  assert.equal(result.postState, 'loading');
  assert.equal(result.polls, 1);
});

test('enterGame rejects stale evidence and stops on authentication without another click', async () => {
  let now = 1000, clicks = 0;
  const api = { now: () => now, sleep: async ms => { now += ms; }, checkStop() {}, requireInputReady() {}, startGame() { clicks++; } };
  const stale = await mission.runQuestStep('enterGame', titleObservation(-1), api, async () => titleObservation());
  assert.equal(stale.status, 'stopped');
  assert.equal(stale.clicks, 0);
  const result = await mission.runQuestStep('enterGame', titleObservation(), api, async () => ({ timestamp: now, frameId: 8, map: null,
    hud: { world: false }, ocr: [{ text: 'Verification code required' }] }));
  assert.equal(result.status, 'stopped');
  assert.equal(result.postState, 'authPrompt');
  assert.equal(result.clicks, 1);
  assert.equal(clicks, 1);
});

test('adapter requires the verified RDP child session and foreground focus before entry', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'), 'utf8');
  for (const genshin of [
    { isRemoteDesktopSession: false, windowsSessionId: 5, isGameForeground: true },
    { isRemoteDesktopSession: true, windowsSessionId: 1, isGameForeground: true },
    { isRemoteDesktopSession: true, windowsSessionId: 5, isGameForeground: false },
  ]) {
    const context = { module: { exports: {} }, genshin };
    vm.runInNewContext(source, context);
    const adapter = context.createActOneAdapter(5);
    assert.throws(() => adapter.startGame(), /RDP child session|foreground focus/);
  }
});
