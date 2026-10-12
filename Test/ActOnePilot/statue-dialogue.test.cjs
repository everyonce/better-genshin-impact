const test = require('node:test');
const assert = require('node:assert/strict');
const resolver = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/statue-dialogue.js');

const NOW = 5000;
const SESSION = 'windrise-statue-session';

function row(text, x, y, width, height) { return { text, x, y, width, height }; }
function openingPatch() {
  return {
    hud: { auto: true, dialogueReady: true, world: false, journal: false, bigMap: false, choice: false,
      climbing: false, objectiveChanged: false, tutorialStep: null, unknownHud: false, health: null },
    ocr: [
      row('Auto', 102, 32, 65, 31),
      row('Statue of The Seven', 783, 850, 351, 46),
      row('The world opens itself before those with noble hearts.', 527, 909, 864, 35)
    ]
  };
}
function frame(id = 42, patch = {}) {
  return { session: SESSION, frameId: id, timestamp: NOW, ...openingPatch(), ...patch };
}
function state(patch = {}) {
  return { session: SESSION, armed: true, interactionAttempted: true, lastInputFrame: 41,
    advanceAttempted: false, leaveAttempted: false, ...patch };
}

test('sanitized recorded frame 1180 permits one bounded Space advance with omitted loading flag', () => {
  // Data-only transcription of observed HUD/OCR; private screenshot and artifact path are not copied here.
  const recordedFrame1180 = frame(1180);
  assert.equal(Object.hasOwn(recordedFrame1180.hud, 'loading'), false);
  assert.deepEqual(resolver.action(recordedFrame1180, NOW, SESSION, state({ lastInputFrame: 1179 })),
    { kind: 'advance', key: 'VK_SPACE', durationMs: 60 });
});

test('rejects stale, future, cross-session, and unproven observations', () => {
  const cases = [
    frame(42, { timestamp: NOW - 1001 }), frame(42, { timestamp: NOW + 1 }),
    frame(42, { session: 'other' }), frame(41), frame(42, { frameId: 42.5 })
  ];
  for (const o of cases) assert.equal(resolver.action(o, NOW, SESSION, state()), null);
  for (const proof of [{ armed: false }, { interactionAttempted: false }, { session: 'other' },
    { lastInputFrame: 42 }, { advanceAttempted: true }, { advanceAttempted: undefined }])
    assert.equal(resolver.action(frame(), NOW, SESSION, state(proof)), null);
  assert.equal(resolver.action(frame(), NOW, SESSION, state({ leaveAttempted: undefined })), null);
});

test('rejects changed dialogue, duplicate targets, and unsafe screen state', () => {
  const changedBody = frame(); changedBody.ocr[1] = row('The world opens itself.', 530, 909, 850, 33);
  const duplicateSpeaker = frame(); duplicateSpeaker.ocr.push(row('Statue of The Seven', 785, 852, 350, 31));
  const duplicateBody = frame(); duplicateBody.ocr.push(row('The world opens itself before those with noble hearts.', 530, 909, 850, 33));
  const wrongGeometry = frame(); wrongGeometry.ocr[0] = row('Statue of The Seven', 400, 500, 350, 31);
  const hazards = [
    frame(42, { hud: { ...openingPatch().hud, auto: false } }),
    frame(42, { hud: { ...openingPatch().hud, dialogueReady: false } }),
    frame(42, { hud: { ...openingPatch().hud, loading: true } }),
    frame(42, { hud: { ...openingPatch().hud, tutorialStep: 'something' } }),
    frame(42, { hud: { ...openingPatch().hud, world: true } }),
    frame(42, { hud: { ...openingPatch().hud, journal: true } }),
    frame(42, { hud: { ...openingPatch().hud, health: { current: 50, max: 100 } } })
  ];
  const missingAuto = frame(); missingAuto.ocr = missingAuto.ocr.filter(r => r.text !== 'Auto');
  const duplicateAuto = frame(); duplicateAuto.ocr.push(row('Auto', 102, 32, 65, 31));
  const wrongAuto = frame(); wrongAuto.ocr[0] = row('Auto', 500, 400, 65, 31);
  for (const o of [changedBody, duplicateSpeaker, duplicateBody, wrongGeometry, missingAuto, duplicateAuto, wrongAuto, ...hazards])
    assert.equal(resolver.action(o, NOW, SESSION, state()), null);
});

test('rejects known confirmation, offering, and authentication text anywhere in the frame', () => {
  for (const text of ['Confirm', 'Confirmation', 'Offering', 'Offer', 'Authentication required', 'Log in', 'Loading']) {
    const o = frame(); o.ocr.push(row(text, 1200, 500, 170, 32));
    assert.equal(resolver.action(o, NOW, SESSION, state()), null, text);
  }
});

test('synthetic choice fixture resolves only a unique bounded Leave beside the known blessing choice', () => {
  const o = frame(43, { hud: { ...openingPatch().hud, choice: true }, ocr: [
    row('Auto', 102, 32, 65, 31), row('Statue of The Seven', 783, 850, 351, 46),
    row('The world opens itself before those with noble hearts.', 527, 909, 864, 35),
    row('Statue’s Blessing', 1260, 570, 300, 34), row('Leave.', 1260, 640, 120, 30)
  ] });
  assert.deepEqual(resolver.action(o, NOW, SESSION, state()),
    { kind: 'leave', x: 1320, y: 655 });
  assert.equal(resolver.action(o, NOW, SESSION, state({ leaveAttempted: true })), null);
});

test('choice rejects duplicates, off-box labels, and offering or confirmation panels', () => {
  const baseRows = [row('Auto', 102, 32, 65, 31), row('Statue of The Seven', 783, 850, 351, 46),
    row('The world opens itself before those with noble hearts.', 527, 909, 864, 35),
    row("Statue's Blessing", 1260, 570, 300, 34), row('Leave', 1260, 640, 120, 30)];
  const withRows = rows => frame(43, { hud: { ...openingPatch().hud, choice: true }, ocr: rows });
  const cases = [
    withRows([...baseRows, row('Leave', 1260, 690, 120, 30)]),
    withRows([...baseRows, row('Statue’s Blessing', 1260, 700, 300, 34)]),
    withRows(baseRows.map(r => r.text === 'Leave' ? row('Leave', 950, 640, 120, 30) : r)),
    withRows([...baseRows, row('Offer', 1260, 710, 120, 30)]),
    withRows([...baseRows, row('Confirm', 1260, 710, 120, 30)]),
    frame(43, { hud: { ...openingPatch().hud, choice: true }, ocr: openingPatch().ocr })
  ];
  for (const o of cases) assert.equal(resolver.action(o, NOW, SESSION, state()), null);
});

test('each action type requires its own explicit unused boolean', () => {
  assert.equal(resolver.action(frame(), NOW, SESSION, state({ advanceAttempted: true })), null);
  const choice = frame(43, { hud: { ...openingPatch().hud, choice: true }, ocr: [
    ...openingPatch().ocr, row("Statue's Blessing", 1260, 570, 300, 34), row('Leave', 1260, 640, 120, 30)
  ] });
  assert.equal(resolver.action(choice, NOW, SESSION, state({ leaveAttempted: true })), null);
});
