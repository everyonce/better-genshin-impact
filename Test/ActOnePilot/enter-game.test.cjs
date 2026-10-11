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
function pulsingTitle(timestamp = 1000) {
  const observation = titleObservation(timestamp);
  observation.ocr = observation.ocr.filter(r => r.text !== 'CLICK TO BEGIN');
  return observation;
}
function doorObservation(timestamp = 1000, rows) {
  return { timestamp, frameId: 19, map: null,
    hud: { world: false, health: null, journal: false, bigMap: false, dialogueReady: false, choice: false },
    ocr: rows || [
      { text: 'CLICK TO BEGIN', x: 854, y: 1007, width: 209, height: 26 },
      { text: 'OSREL 6.0.0', x: 1700, y: 1040, width: 120, height: 20 },
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
  assert.equal(bgi.enterGameUnknownUi([{ text: 'Confirm' }]), true);
  assert.equal(bgi.enterGameTarget({ ...titleObservation(), hud: { world: true } }, 1000), null);
  const offCenter = titleObservation(); offCenter.ocr[1] = { text: 'CLICK TO BEGIN', x: 1400, y: 570, width: 215, height: 34 };
  assert.equal(bgi.enterGameTarget(offCenter, 1000), null);
});

test('title entry accepts only the measured clipped TART GAME OCR variant with exact Click to Begin', () => {
  const clipped = titleObservation(1000, [
    { text: 'TART GAME', x: 820, y: 472, width: 339, height: 69 },
    { text: 'CLICK TO BEGIN', x: 853, y: 568, width: 209, height: 39 },
    { text: 'America', x: 890, y: 907, width: 139, height: 37 },
  ]);
  assert.deepEqual(bgi.enterGameTarget(clipped, 1000), { x: 957, y: 587, label: 'CLICK TO BEGIN' });
  const wrongGeometry = { ...clipped, ocr: clipped.ocr.map(r => r.text === 'TART GAME' ? { ...r, x: 700 } : r) };
  assert.equal(bgi.enterGameTarget(wrongGeometry, 1000), null);
  const fuzzyText = { ...clipped, ocr: clipped.ocr.map(r => r.text === 'TART GAME' ? { ...r, text: 'T4RT GAME' } : r) };
  assert.equal(bgi.enterGameTarget(fuzzyText, 1000), null);
  const auth = { ...clipped, ocr: [...clipped.ocr, { text: 'Authentication required', x: 800, y: 700, width: 250, height: 30 }] };
  assert.equal(bgi.enterGameTarget(auth, 1000), null);
});

test('door entry target accepts only the exact measured bottom prompt, separate from the title', () => {
  assert.deepEqual(bgi.enterWorldTarget(doorObservation(), 1000), { x: 958, y: 1020, label: 'CLICK TO BEGIN' });
  const offPosition = doorObservation(); offPosition.ocr[0] = { ...offPosition.ocr[0], y: 568 };
  assert.equal(bgi.enterWorldTarget(offPosition, 1000), null);
  const auth = doorObservation(); auth.ocr.push({ text: 'Verification code', x: 800, y: 800, width: 200, height: 25 });
  assert.equal(bgi.enterWorldTarget(auth, 1000), null);
  const title = titleObservation();
  assert.equal(bgi.enterWorldTarget(title, 1000), null);
  const hasHealth = doorObservation(); hasHealth.hud.health = { current: 100, max: 100 };
  assert.equal(bgi.enterWorldTarget(hasHealth, 1000), null);
  assert.equal(bgi.enterWorldTarget(doorObservation(0), 1001), null);
});

test('enterGame waits for the pulsing exact prompt, clicks once, and waits until a world HUD is observed', async () => {
  let now = 1000, clicks = 0, polls = 0;
  const initial = pulsingTitle();
  const api = { now: () => now, sleep: async ms => { now += ms; }, checkStop() {}, requireInputReady() {},
    startGame() { clicks++; return { x: 956, y: 587, frameId: 8 }; } };
  const observe = async () => {
    polls++;
    if (polls === 1) { const paired = titleObservation(now); paired.frameId = 8; return paired; }
    if (polls === 2) return { timestamp: now, frameId: 9, map: null, hud: { world: false }, ocr: [{ text: 'Loading' }] };
    return { timestamp: now, frameId: 10, map: { map: 'Teyvat', x: 1, y: 2 }, hud: { world: true }, ocr: [{ text: 'Teyvat' }] };
  };
  const result = await mission.runQuestStep('enterGame', initial, api, observe);
  assert.equal(clicks, 1);
  assert.equal(result.status, 'completed');
  assert.equal(result.clicks, 1);
  assert.equal(result.postState, 'worldHud');
  assert.equal(result.polls, 2);
  assert.equal(result.preflightObservations, 2);
});

test('enterGame never clicks when the exact prompt pulse does not return within ten observations', async () => {
  let now = 1000, clicks = 0, polls = 0;
  const api = { now: () => now, sleep: async ms => { now += ms; }, checkStop() {}, requireInputReady() {}, startGame() { clicks++; } };
  const result = await mission.runQuestStep('enterGame', pulsingTitle(), api, async () => { polls++; return pulsingTitle(now); });
  assert.equal(result.status, 'stopped');
  assert.equal(result.clicks, 0);
  assert.equal(result.preState, 'titlePromptPulse');
  assert.equal(result.preflightObservations, 10);
  assert.equal(polls, 9);
  assert.equal(clicks, 0);
});

test('enterGame rejects stale evidence and stops on authentication without another click', async () => {
  let now = 1000, clicks = 0;
  const api = { now: () => now, sleep: async ms => { now += ms; }, checkStop() {}, requireInputReady() {}, startGame() { clicks++; } };
  const stale = await mission.runQuestStep('enterGame', titleObservation(-1), api, async () => titleObservation());
  assert.equal(stale.status, 'stopped');
  assert.equal(stale.clicks, 0);
  const result = await mission.runQuestStep('enterGame', pulsingTitle(), api, async () => ({ timestamp: now, frameId: 8, map: null,
    hud: { world: false }, ocr: [{ text: 'Verification code required' }] }));
  assert.equal(result.status, 'stopped');
  assert.equal(result.preState, 'authPrompt');
  assert.equal(result.clicks, 0);
  assert.equal(result.preflightObservations, 2);
  assert.equal(clicks, 0);
});

test('enterGame stops on unknown UI during the prompt wait and does not infer world entry from OCR clearing', async () => {
  let now = 1000, clicks = 0;
  const api = { now: () => now, sleep: async ms => { now += ms; }, checkStop() {}, requireInputReady() {}, startGame() { clicks++; } };
  const unknown = await mission.runQuestStep('enterGame', pulsingTitle(), api, async () => ({ timestamp: now, frameId: 8,
    map: null, hud: { world: false, journal: true }, ocr: [{ text: 'Inventory' }] }));
  assert.equal(unknown.status, 'stopped');
  assert.equal(unknown.preState, 'unknownScreen');
  assert.equal(unknown.clicks, 0);
  assert.equal(clicks, 0);

  const confirmation = await mission.runQuestStep('enterGame', pulsingTitle(now), api, async () => ({ timestamp: now, frameId: 8,
    map: null, hud: { world: false }, ocr: [{ text: 'Confirm' }] }));
  assert.equal(confirmation.status, 'stopped');
  assert.equal(confirmation.preState, 'unknownScreen');
  assert.equal(confirmation.clicks, 0);

  const afterClick = await mission.runQuestStep('enterGame', titleObservation(now), api, async () => ({ timestamp: now, frameId: 9,
    map: null, hud: { world: false }, ocr: [] }));
  assert.equal(afterClick.status, 'stopped');
  assert.equal(afterClick.postState, 'titleClearedUnverified');
  assert.match(afterClick.reason, /World HUD not observed/);
  assert.equal(afterClick.clicks, 1);
  assert.equal(afterClick.polls, 40);
  assert.equal(clicks, 1);
});

test('enterGame stops after one click on post-click auth or unknown UI evidence', async () => {
  let now = 1000, clicks = 0, polls = 0;
  const api = { now: () => now, sleep: async ms => { now += ms; }, checkStop() {}, requireInputReady() {}, startGame() { clicks++; } };
  for (const [ocr, postState] of [
    [[{ text: 'Verification code required' }], 'authPrompt'],
    [[{ text: 'Confirm' }], 'unknownUi'],
  ]) {
    polls = 0;
    const result = await mission.runQuestStep('enterGame', titleObservation(now), api, async () => {
      polls++; return { timestamp: now, frameId: 10 + polls, map: null, hud: { world: false }, ocr };
    });
    assert.equal(result.status, 'stopped');
    assert.equal(result.postState, postState);
    assert.equal(result.polls, 1);
  }
  assert.equal(clicks, 2);
});

test('enterGame uses at most one title click then one door click before world HUD verification', async () => {
  let now = 1000, frame = 0;
  const clicks = [];
  const initial = titleObservation();
  const api = { now: () => now, sleep: async ms => { now += ms; }, checkStop() {}, requireInputReady() {},
    startGame(phase) { clicks.push(phase || 'enterGame'); return { phase: phase || 'enterGame', frameId: frame }; } };
  const observe = async () => {
    frame++;
    if (frame === 1) return doorObservation(now);
    return { timestamp: now, frameId: 20, map: { map: 'Teyvat', x: 5, y: 6 }, hud: { world: true }, ocr: [{ text: 'Teyvat' }] };
  };
  const result = await mission.runQuestStep('enterGame', initial, api, observe);
  assert.deepEqual(clicks, ['enterGame', 'enterWorld']);
  assert.equal(result.status, 'completed');
  assert.equal(result.phaseClicks.title, 1);
  assert.equal(result.phaseClicks.door, 1);
  assert.equal(result.clicks, 2);
  assert.equal(result.postState, 'worldHud');
});

test('standalone enterWorld clicks once and stops unverified after forty door observations', async () => {
  let now = 1000, clicks = 0, polls = 0;
  const api = { now: () => now, sleep: async ms => { now += ms; }, checkStop() {}, requireInputReady() {},
    startGame(phase) { assert.equal(phase, 'enterWorld'); clicks++; } };
  const result = await mission.runQuestStep('enterWorld', doorObservation(), api, async () => { polls++; return doorObservation(now); });
  assert.equal(clicks, 1);
  assert.equal(result.status, 'stopped');
  assert.equal(result.postState, 'doorUnverified');
  assert.equal(result.clicks, 1);
  assert.equal(result.phaseClicks.door, 1);
  assert.equal(result.polls, 40);
  assert.equal(polls, 40);
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

test('windowInfo quest step returns parsed read-only diagnostics under the verified session guard', () => {
  const info = { rdpWidth: 2560, rdpHeight: 1440, gameWidth: 1920, gameHeight: 1080, desktop: false };
  const context = { module: { exports: {} }, genshin: { isRemoteDesktopSession: true, windowsSessionId: 5, isGameForeground: true,
    GetGameWindowInfo: () => JSON.stringify(info) }, file: { isExists: () => false, readTextSync: () => '', writeTextSync: () => true } };
  vm.runInNewContext(fs.readFileSync(path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'), 'utf8'), context);
  const adapter = context.createActOneAdapter(5);
  adapter.beginMission({ mission: 'questStep', step: 'windowInfo', session: 'test-session', createdAt: 1000 });
  assert.equal(JSON.stringify(adapter.windowInfo()), JSON.stringify(info));
});
