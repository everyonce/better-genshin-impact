const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const sourcePath = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const source = fs.readFileSync(sourcePath, 'utf8');
const context = { module: { exports: {} }, exports: {} };
vm.runInNewContext(source, context, { filename: sourcePath });
const lionFieldWorld = context.actOneLionFieldWorld;
assert.equal(typeof lionFieldWorld, 'function');

const session = 'test-session';
const now = 2_000_000;
const row = (text, x, y, width = 54, height = 20) => ({ text, x, y, width, height });

function observation(name, geometry, patch = {}) {
  return {
    session,
    frameId: geometry.frameId || 1259,
    timestamp: now - 100,
    hud: {
      groundControls: true,
      climbing: false,
      auto: false,
      journal: false,
      bigMap: false,
      dialogueReady: false,
      choice: false,
      tutorialStep: null,
      objectiveChanged: false,
      unknownHud: false,
      health: { current: 876, max: 1186 },
      objectives: ['Meet Lisa at the Temple'],
    },
    ocr: [row(name, geometry.x, geometry.y, geometry.width, geometry.height),
      row('3', 1858, 490, 27, 27), row('R', 1858, 970), row('Q', 1858, 1000)],
    ...patch,
  };
}

// These anonymized rectangles preserve only the OCR boxes' geometry; no frame
// pixels, session identifiers, account data, or live capture artifacts are used.
const observedRows = [
  { name: 'Kāeya', geometry: { x: 1694, y: 482, width: 73, height: 29, frameId: 1259 } },
  { name: 'Kaeyā', geometry: { x: 1689, y: 479, width: 79, height: 38, frameId: 1260 } },
];

test('the two observed Kaeya diacritic spellings pass with their party row geometry', () => {
  for (const { name, geometry } of observedRows) {
    assert.equal(lionFieldWorld(observation(name, geometry), now, session, 0.6), true, name);
  }
});

test('Kaeya evidence must be unique and paired with the unique third-slot marker', () => {
  const good = observation('Kaeya', { x: 1660, y: 480 });
  for (const bad of [
    { ...good, ocr: [...good.ocr, row('Kaeya', 1700, 500)] },
    { ...good, ocr: [...good.ocr, row('Kāeya', 1700, 500)] },
    { ...good, ocr: good.ocr.filter(r => r.text !== '3') },
    { ...good, ocr: [...good.ocr.filter(r => r.text !== '3'), row('2', 1860, 480)] },
    { ...good, ocr: [...good.ocr, row('3', 1861, 480)] },
  ]) assert.equal(lionFieldWorld(bad, now, session, 0.6), false);
});

test('stale, future, and cross-session observations fail', () => {
  const good = observation('Kaeya', { x: 1660, y: 480 });
  assert.equal(lionFieldWorld({ ...good, timestamp: now - 1001 }, now, session, 0.6), false);
  assert.equal(lionFieldWorld({ ...good, timestamp: now + 1 }, now, session, 0.6), false);
  assert.equal(lionFieldWorld(good, now, 'other-session', 0.6), false);
});

test('Trial, unknown UI, and missing health fail closed', () => {
  const good = observation('Kaeya', { x: 1660, y: 480 });
  for (const bad of [
    { ...good, ocr: [...good.ocr, row('Trial', 1780, 480)] },
    { ...good, hud: { ...good.hud, unknownHud: true } },
    { ...good, hud: { ...good.hud, health: undefined } },
  ]) assert.equal(lionFieldWorld(bad, now, session, 0.6), false);
});

test('matching remains limited to accent normalization and the approved name geometry', () => {
  for (const name of ['Amber', 'Kaeeya', 'Kaeya,', 'kaeya']) {
    assert.equal(lionFieldWorld(observation(name, { x: 1660, y: 480 }), now, session, 0.6), false, name);
  }
  for (const geometry of [{ x: 1599, y: 480 }, { x: 1660, y: 541 }]) {
    assert.equal(lionFieldWorld(observation('Kaeya', geometry), now, session, 0.6), false);
  }
});
