const test = require('node:test');
const assert = require('node:assert/strict');
const dialogueReady = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js').dialogueReady;

const frame779 = [
  { text: 'Auto', x: 100, y: 32, width: 69, height: 31 },
  { text: 'Paimon', x: 891, y: 851, width: 137, height: 43 },
  { text: 'Jean?', x: 907, y: 899, width: 102, height: 53 }
];

test('frame 779 short line is dialogue only with exact Auto and separate known speaker', () => {
  assert.equal(dialogueReady(frame779, false), true);
});

test('speaker label alone is not mistaken for subtitle text', () => {
  assert.equal(dialogueReady(frame779.slice(0, 2), false), false);
});

test('short subtitle without an exact known speaker is rejected', () => {
  const shortLine = frame779.filter(r => r.text !== 'Paimon');
  assert.equal(dialogueReady(shortLine, false), false);
  assert.equal(dialogueReady([...frame779.slice(0, 1), { text: 'Traveler', x: 891, y: 851 }, frame779[2]], false), false);
  assert.equal(dialogueReady([...frame779.slice(0, 1), { text: 'Paimon', x: 891, y: 905 }, frame779[2]], false), false);
});

test('long subtitle retains the established dialogue recognition path', () => {
  assert.equal(dialogueReady([
    frame779[0],
    { text: 'Paimon almost got blown away by that strong gust of wind', x: 571, y: 903, width: 771, height: 48 }
  ], false), true);
});

test('ambiguous Auto placement and choice state remain blocked', () => {
  assert.equal(dialogueReady([
    { text: 'Auto', x: 500, y: 32 }, frame779[1], frame779[2]
  ], false), false);
  assert.equal(dialogueReady(frame779, true), false);
});
