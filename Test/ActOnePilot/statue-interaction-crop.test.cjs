const test = require('node:test');
const assert = require('node:assert/strict');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

const statue = { text: 'Statue of The Seven', x: 1216, y: 524, width: 275, height: 29 };
function screen(patch = {}) {
  return { auto: false, journal: false, bigMap: false, dialogueReady: false, choice: false,
    climbing: false, objectiveChanged: false, tutorialStep: null, groundControls: true, ...patch };
}

test('measured Statue row with grounded controls enables the read-only same-frame F crop without health or position', () => {
  assert.equal(bgi.shouldReadStatueInteractionCrop([statue], screen()), true);
  assert.equal(bgi.shouldReadStatueInteractionCrop([statue, { text: 'E', x: 1660, y: 1008 }], screen()), true,
    'the grounded-control evidence can coexist with an E control row');
});

test('Statue crop policy rejects duplicates, wrong labels, and rows outside calibrated geometry', () => {
  assert.equal(bgi.shouldReadStatueInteractionCrop([statue, { ...statue }], screen()), false);
  assert.equal(bgi.shouldReadStatueInteractionCrop([{ ...statue, text: 'Statue of the Seven' }], screen()), false);
  for (const patch of [
    { x: 1179 }, { x: 1251 }, { y: 499 }, { y: 546 }, { width: 249 }, { width: 311 }, { height: 19 }, { height: 39 },
  ]) assert.equal(bgi.shouldReadStatueInteractionCrop([{ ...statue, ...patch }], screen()), false);
  assert.equal(bgi.shouldReadStatueInteractionCrop([statue, { text: 'Statue of The Seven', x: 300, y: 600, width: 275, height: 29 }], screen()), false,
    'an extra matching row anywhere in full-frame OCR is ambiguous');
});

test('Statue crop is disabled for missing ground controls, an existing F prompt, and unsafe UI states', () => {
  assert.equal(bgi.shouldReadStatueInteractionCrop([statue], screen({ groundControls: false })), false);
  assert.equal(bgi.shouldReadStatueInteractionCrop([statue, { text: 'F', x: 1100, y: 525 }], screen()), false);
  for (const patch of [
    { auto: true }, { journal: true }, { bigMap: true }, { dialogueReady: true }, { choice: true },
    { climbing: true }, { objectiveChanged: true }, { tutorialStep: 'glideOpen' },
  ]) assert.equal(bgi.shouldReadStatueInteractionCrop([statue], screen(patch)), false);
});

test('existing quest interaction crop keeps its stricter health, position, and objective checks', () => {
  assert.equal(bgi.shouldReadInteractionCrop([statue], 'Talk to Kaeya', screen({
    objective: 'Talk to Kaeya', world: true, position: false, health: null,
  })), false);
});

test('the shared 90x100 crop maps one measured F row back to the fixed prompt region', () => {
  const f = bgi.interactionCropF([{ text: 'F', x: 54, y: 96, width: 135, height: 105 }], 1080, 490);
  assert.deepEqual({ text: f.text, x: Math.round(f.x), y: Math.round(f.y) }, { text: 'F', x: 1098, y: 522 });
  assert.equal(bgi.interactionCropF([{ text: 'F', x: 285, y: 20 }], 1080, 490), null);
});
