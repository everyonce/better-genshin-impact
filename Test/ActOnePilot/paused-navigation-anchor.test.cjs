'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const anchor = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/paused-navigation-anchor.js');

const now = 200500;
function fixture() {
  const session = 'paused-anchor-test';
  const field = {
    session, frameId: 83, timestamp: 1000,
    map: { map: 'Teyvat', x: -1265.917, y: 1928.381, cameraAngle: 54 },
    hud: { world: true, groundControls: true, climbing: false, auto: false, journal: false, bigMap: false,
      dialogueReady: false, choice: false, enemyBars: [], health: { current: 1186, max: 1186 }, objectives: ['Meet Lisa at the temple'] },
    ocr: [{ text: 'Kaeya', x: 1660, y: 500 }, { text: '3', x: 1860, y: 500 }]
  };
  const paused = { session, frameId: 87, timestamp: 199900, hud: { auto: false, dialogueReady: false }, ocr: [
    { text: 'Food', x: 140, y: 32, width: 67, height: 31 },
    { text: 'Inventory capacity 9/2600', x: 1504, y: 34, width: 295, height: 27 }
  ] };
  const receipt = { id: 'mission-123', session, mission: 'navigation', status: 'completed', frameId: 88, timestamp: 200000,
    details: { result: { step: 'lisaNavigation', status: 'completed', pauseVerified: true, questComplete: false,
      fieldFrameId: field.frameId, fieldPosition: { ...field.map }, fieldHealth: { ...field.hud.health },
      pauseProof: { verified: true, session, sourceFrameId: 85, kind: 'inventory', pauseFrameId: paused.frameId,
        timestamp: paused.timestamp, evidence: [...paused.ocr] } } } };
  const request = { mission: 'questStep', step: 'lionFieldProbe', session, expectedFrameId: 88 };
  const marker = { kind: 'pausedLisaPositionProbe', session, frameId: 30, witnessVerified: true,
    receiptId: receipt.id, createdAt: 200100 };
  marker.frameId = request.expectedFrameId;
  return { request, marker, receipt, field, paused };
}
function seed(overrides = {}, timestamp = now) {
  const f = fixture(); Object.assign(f, overrides);
  return anchor.seed(f.request, f.marker, f.receipt, f.field, f.paused, timestamp);
}

test('uses an old validated field GPS only as a seed and returns a 25m fresh-fix limit', () => {
  const f = fixture();
  assert.equal(now - f.field.timestamp > 120000, true);
  assert.deepEqual(anchor.seed(f.request, f.marker, f.receipt, f.field, f.paused, now),
    { x: -1265.917, y: 1928.381, maxDistance: 25, witnessFrameId: 83 });
});

test('rejects wrong request, marker, receipt, or noncompleted Lisa result', () => {
  const cases = [
    { request: { ...fixture().request, step: 'lionFieldCombat' } },
    { marker: { ...fixture().marker, witnessVerified: false } },
    { marker: { ...fixture().marker, usedAt: 1 } },
    { marker: { ...fixture().marker, createdAt: now - 120001 } },
    { receipt: { ...fixture().receipt, session: 'other' } },
    { receipt: { ...fixture().receipt, status: 'stopped' } },
    { receipt: { ...fixture().receipt, details: { result: { ...fixture().receipt.details.result, questComplete: true } } } }
  ];
  for (const c of cases) assert.equal(seed(c), null);
});

test('rejects mismatched saved coordinates, health, session, or invalid field HUD/party evidence', () => {
  const f = fixture();
  const cases = [
    { field: { ...f.field, map: { ...f.field.map, x: f.field.map.x + 1 } } },
    { field: { ...f.field, hud: { ...f.field.hud, health: { current: 0, max: 1186 } } } },
    { field: { ...f.field, session: 'other' } },
    { field: { ...f.field, hud: { ...f.field.hud, bigMap: true } } },
    { field: { ...f.field, map: { ...f.field.map, cameraAngle: NaN } } },
    { field: { ...f.field, map: { ...f.field.map, x: -700 } } },
    { field: { ...f.field, hud: { ...f.field.hud, enemyBars: [{ x: 500, y: 250, width: 90, height: 8 }] } } },
    { field: { ...f.field, ocr: [...f.field.ocr, { text: 'Kaeya', x: 1700, y: 500 }] } },
    { field: { ...f.field, ocr: [{ ...f.field.ocr[0], text: 'kaeya' }, f.field.ocr[1]] } },
    { field: { ...f.field, ocr: [{ ...f.field.ocr[0], text: 'Kaeya!' }, f.field.ocr[1]] } },
    { field: { ...f.field, ocr: [...f.field.ocr, { text: 'Trial', x: 700, y: 500 }] } }
  ];
  for (const c of cases) assert.equal(seed(c), null);
});

test('requires a saved, canonical Food pause proof before the request frame', () => {
  const f = fixture();
  const cases = [
    { paused: null },
    { paused: { ...f.paused, timestamp: f.paused.timestamp + 1 } },
    { paused: { ...f.paused, ocr: [{ text: 'Food', x: 140, y: 32 }] } },
    { paused: { ...f.paused, session: 'other' } },
    { paused: { ...f.paused, ocr: [{ ...f.paused.ocr[0], text: 'Weapons' }, f.paused.ocr[1]] } },
    { receipt: { ...f.receipt, details: { result: { ...f.receipt.details.result,
      pauseProof: { ...f.receipt.details.result.pauseProof,
        evidence: [{ ...f.paused.ocr[0], text: 'Weapons' }, f.paused.ocr[1]] } } } } },
    { receipt: { ...f.receipt, details: { result: { ...f.receipt.details.result,
      pauseProof: { ...f.receipt.details.result.pauseProof, pauseFrameId: 89 } } } } }
  ];
  for (const c of cases) assert.equal(seed(c), null);
});

test('rejects incoherent timestamps and frame ordering', () => {
  const f = fixture();
  const cases = [
    { field: { ...f.field, timestamp: f.receipt.timestamp + 1 } },
    { marker: { ...f.marker, createdAt: f.receipt.timestamp - 1 } },
    { request: { ...f.request, expectedFrameId: f.paused.frameId } },
    { paused: { ...f.paused, frameId: f.request.expectedFrameId + 1 } }
  ];
  for (const c of cases) assert.equal(seed(c), null);
});
