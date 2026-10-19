const test = require('node:test');
const assert = require('node:assert/strict');
const field = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js');

// Compact OCR from the actual Springvale regional map, session mvf7..., frame 466.
const rows = [
  ['Whispering Woods', 1014, 268, 199, 29],
  ['Mondstadt', 874, 296, 121, 23],
  ['Windrise', 1126, 522, 97, 23],
  ['Falcon Coast', 1407, 633, 143, 34],
  ['Windwail Highland', 1532, 987, 261, 34],
  ['UID: 693306810', 1680, 1048, 183, 29],
].map(([text, x, y, width, height]) => ({text, x, y, width, height}));
const witness = {session:'s', timestamp:1000, hud:{bigMap:true, world:false}, ocr:rows};

test('recorded Springvale wide map has a bounded regional witness', () => {
  assert.equal(field.regionalMap(witness, 1000, 's'), true);
  assert.equal(field.regionalMap(witness, 601001, 's'), false);
  assert.equal(field.regionalMap(witness, 1000, 'other'), false);
});

test('map witness rejects inconsistent labels, footer, and account', () => {
  const shifted = structuredClone(witness);
  shifted.ocr.find(r => r.text === 'Windrise').x += 20;
  assert.equal(field.regionalMap(shifted, 1000, 's'), false);
  const footer = structuredClone(witness);
  footer.ocr.find(r => r.text === 'Windwail Highland').text = 'Galesong Hill';
  assert.equal(field.regionalMap(footer, 1000, 's'), false);
  const account = structuredClone(witness);
  account.ocr.find(r => r.text.startsWith('UID:')).text = 'UID: 000000000';
  assert.equal(field.regionalMap(account, 1000, 's'), false);
});
