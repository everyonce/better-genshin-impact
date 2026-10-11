const test = require('node:test');
const assert = require('node:assert/strict');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

const wrappedTemple = [
  { text: 'Temple of the', x: 1228, y: 506, width: 181, height: 35 },
  { text: 'Falcon', x: 1217, y: 532, width: 98, height: 42 },
];
function safeScreen(overrides = {}) {
  return { objective: 'Enter the temple', world: true, position: true, health: { current: 1213, max: 1213 }, auto: false,
    journal: false, bigMap: false, dialogueReady: false, choice: false, objectiveChanged: false, tutorialStep: null, ...overrides };
}

test('named interaction recognizes Amber and adjacent aligned wrapped temple OCR rows', () => {
  assert.equal(bgi.namedInteractionVisible([{ text: 'Amber', x: 1300, y: 470 }], 'Talk to Amber'), true);
  assert.equal(bgi.namedInteractionVisible(wrappedTemple, 'Enter the temple'), true);
  assert.equal(bgi.namedInteractionVisible([{ text: 'Temple of the Falcon', x: 1300, y: 460 }], 'Enter the temple'), true);
  assert.equal(bgi.namedInteractionVisible([{ text: 'Amber', x: 1300, y: 470 }], 'Enter the temple'), false);
  assert.equal(bgi.namedInteractionVisible([
    wrappedTemple[0], { text: 'Falcon', x: 1300, y: 570, width: 98, height: 42 },
  ], 'Enter the temple'), false, 'nonadjacent rows are not concatenated');
  assert.equal(bgi.namedInteractionVisible([
    wrappedTemple[0], { text: 'Falcon', x: 1280, y: 532, width: 98, height: 42 },
  ], 'Enter the temple'), false, 'misaligned rows are rejected');
});

test('same-capture F crop is enabled only with named target and safe navigation HUD', () => {
  assert.equal(bgi.shouldReadInteractionCrop(wrappedTemple, 'Enter the temple', safeScreen()), true);
  assert.equal(bgi.shouldReadInteractionCrop([{ text: 'Amber', x: 1300, y: 470 }], 'Enter the temple', safeScreen()), false);
  assert.equal(bgi.shouldReadInteractionCrop(wrappedTemple, 'Enter the temple', safeScreen({ position: false })), false);
  assert.equal(bgi.shouldReadInteractionCrop(wrappedTemple, 'Enter the temple', safeScreen({ health: { current: 590, max: 1213 } })), false);
  assert.equal(bgi.shouldReadInteractionCrop(wrappedTemple, 'Enter the temple', safeScreen({ dialogueReady: true })), false);
  assert.equal(bgi.shouldReadInteractionCrop(wrappedTemple, 'Enter the temple', safeScreen({ journal: true })), false);
  assert.equal(bgi.shouldReadInteractionCrop(wrappedTemple, 'Enter the temple', safeScreen({ choice: true })), false);
  assert.equal(bgi.shouldReadInteractionCrop([...wrappedTemple, { text: 'F', x: 1098, y: 522 }], 'Enter the temple', safeScreen()), false,
    'same-capture crop is skipped when full-frame OCR already found the F prompt');
});

test('keyPress without a request objective uses only an observed exact supported objective', () => {
  const objective = bgi.resolveInteractionObjective(undefined, [{ text: 'Enter the temple', x: 100, y: 250 }]);
  assert.equal(objective, 'Enter the temple');
  assert.equal(bgi.shouldReadInteractionCrop(wrappedTemple, objective, safeScreen()), true,
    'the named screen and observed objective are enough without a fabricated request objective');
  assert.equal(bgi.resolveInteractionObjective(undefined, [{ text: 'Go to Mondstadt', x: 100, y: 250 }]), null);
  assert.equal(bgi.shouldReadInteractionCrop(wrappedTemple, null, safeScreen({ objective: null })), false);
});

test('3x-scaled same-image crop accepts one exact F prompt inside the bounded target region', () => {
  const f = bgi.interactionCropF([{ text: 'F', x: 54, y: 96, width: 135, height: 105 }], 1080, 490);
  assert.deepEqual({ text: f.text, x: Math.round(f.x), y: Math.round(f.y) }, { text: 'F', x: 1098, y: 522 });
  assert.equal(bgi.interactionCropF([{ text: 'F', x: 285, y: 20 }], 1080, 490), null, 'outside prompt region');
  assert.equal(bgi.interactionCropF([{ text: 'F', x: 54, y: 96 }, { text: 'F', x: 55, y: 97 }], 1080, 490), null,
    'ambiguous crop OCR is rejected');
});

