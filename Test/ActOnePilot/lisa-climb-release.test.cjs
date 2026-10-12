'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const gate = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/lisa-climb-release.js');

const NOW = 200000;
function frame() {
  return {
    session: 'rdp-child-7', frameId: 142, timestamp: NOW - 50,
    hud: {
      world: true, climbing: true, groundControls: false, auto: false, choice: false,
      dialogueReady: false, journal: false, bigMap: false, objectiveChanged: false,
      loading: false, unknown: false, unknownHud: false, tutorial: false,
      auth: false, confirmation: false,
      health: { current: 876, max: 1186 }, enemyBars: [], objectives: ['Meet Lisa at the temple']
    },
    ocr: [
      { text: 'Meet Lisa at the temple', x: 82, y: 250, width: 293, height: 29 },
      { text: '126m', x: 82, y: 282, width: 46, height: 20 },
      { text: 'Kaeya', x: 1689, y: 479, width: 79, height: 36 },
      { text: '3', x: 1852, y: 486, width: 39, height: 35 },
      { text: 'X', x: 1594, y: 1022, width: 31, height: 31 },
      { text: 'Space', x: 1680, y: 1024, width: 69, height: 31 }
    ]
  };
}
function state() { return { armed: true, releaseAttempted: false, lastInputFrame: 141 }; }
function ready(o = frame(), n = NOW, s = 'rdp-child-7', st = state()) {
  return gate.ready(o, n, s, st);
}

test('accepts the fresh sanitized Lisa climbing frame', () => {
  assert.equal(ready(), true);
});

test('rejects stale, future, wrong-session, and replayed frames', () => {
  const o = frame();
  assert.equal(ready({ ...o, timestamp: NOW - 1001 }), false);
  assert.equal(ready({ ...o, timestamp: NOW + 1 }), false);
  assert.equal(ready(o, NOW, 'other'), false);
  assert.equal(ready({ ...o, frameId: 141 }), false);
  assert.equal(ready(o, NOW, 'rdp-child-7', { ...state(), lastInputFrame: 142 }), false);
});

test('requires an armed, unused release state', () => {
  assert.equal(ready(frame(), NOW, 'rdp-child-7', { ...state(), armed: false }), false);
  assert.equal(ready(frame(), NOW, 'rdp-child-7', { ...state(), releaseAttempted: true }), false);
});

test('rejects changed objective, nonworld, controls, transitions, and unknown context', () => {
  const cases = [
    o => { o.hud.objectives = ['Meet Lisa at the temple', 'Meet Lisa at the temple']; },
    o => { o.hud.objectives = ['Meet Lisa somewhere else']; },
    o => { o.hud.world = false; }, o => { o.hud.climbing = false; },
    o => { o.hud.groundControls = true; }, o => { o.hud.auto = true; },
    o => { o.hud.choice = true; }, o => { o.hud.dialogueReady = true; },
    o => { o.hud.journal = true; }, o => { o.hud.bigMap = true; },
    o => { o.hud.objectiveChanged = true; }, o => { o.hud.loading = true; },
    o => { o.hud.unknownHud = true; }, o => { o.hud.tutorialStep = 'glide'; },
    o => { o.hud.auth = true; }, o => { o.hud.confirmation = true; }
  ];
  for (let i = 0; i < cases.length; i++) { const o = frame(); cases[i](o); assert.equal(ready(o), false, 'case ' + i); }
});

test('rejects unsafe health or any enemy bar', () => {
  for (const health of [
    { current: 0, max: 1186 }, { current: -1, max: 1186 }, { current: 711, max: 1186 },
    { current: 1200, max: 1186 }, { current: 876, max: Infinity }, { current: NaN, max: 1186 }
  ]) { const o = frame(); o.hud.health = health; assert.equal(ready(o), false); }
  const o = frame(); o.hud.enemyBars = [{ x: 800, y: 250, width: 60, height: 8 }];
  assert.equal(ready(o), false);
});

test('rejects explicit death state and revival or disconnect UI text', () => {
  for (const field of ['deathUI', 'dead']) {
    const o = frame(); o.hud[field] = true; assert.equal(ready(o), false, field);
  }
  for (const text of ['Revive', 'Use revival item', 'Disconnected', 'Connection timed out']) {
    const o = frame(); o.ocr.push({ text, x: 500, y: 500, width: 140, height: 24 });
    assert.equal(ready(o), false, text);
  }
});

test('requires one exact owned Kaeya and one slot 3 in the party region', () => {
  const cases = [
    o => { o.ocr = o.ocr.filter(r => r.text !== 'Kaeya'); },
    o => { o.ocr.push({ text: 'Kaeya', x: 1690, y: 480, width: 75, height: 30 }); },
    o => { o.ocr[2].text = 'Kaeya!'; },
    o => { o.ocr[2].x = 1500; },
    o => { o.ocr = o.ocr.filter(r => r.text !== '3'); },
    o => { o.ocr.push({ text: '3', x: 1860, y: 490, width: 20, height: 20 }); },
    o => { o.ocr[3].x = 1849; },
    o => { o.ocr.push({ text: 'Trial', x: 600, y: 500, width: 50, height: 20 }); }
  ];
  for (const mutate of cases) { const o = frame(); mutate(o); assert.equal(ready(o), false); }
});

test('requires one X and one Space prompt with valid geometry', () => {
  const cases = [
    o => { o.ocr = o.ocr.filter(r => r.text !== 'X'); },
    o => { o.ocr.push({ text: 'X', x: 1590, y: 1020, width: 20, height: 20 }); },
    o => { o.ocr[4].x = 1579; },
    o => { o.ocr = o.ocr.filter(r => r.text !== 'Space'); },
    o => { o.ocr.push({ text: 'Space', x: 1680, y: 1024, width: 69, height: 31 }); },
    o => { o.ocr[5].x = 1781; },
    o => { o.ocr[5].height = 0; },
    o => { o.ocr[0].width = Infinity; },
    o => { o.ocr[0].x = NaN; }
  ];
  for (const mutate of cases) { const o = frame(); mutate(o); assert.equal(ready(o), false); }
});

test('rejects sensitive or authentication/confirmation text anywhere in OCR', () => {
  for (const text of ['Sign in', 'Verification code', 'Confirm purchase', 'Authentication required']) {
    const o = frame(); o.ocr.push({ text, x: 20, y: 20, width: 100, height: 20 });
    assert.equal(ready(o), false);
  }
});

test('supports BetterGI Script evaluation without leaking an eval variable', () => {
  const fs = require('node:fs');
  const vm = require('node:vm');
  const source = fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/lisa-climb-release.js'), 'utf8');
  const context = vm.createContext({});
  const evaluated = vm.runInContext(source + '\nActOneLisaClimbRelease;', context);
  assert.equal(typeof evaluated.ready, 'function');
  assert.equal(vm.runInContext('typeof lisaClimbReleaseTemporary', context), 'undefined');
});
