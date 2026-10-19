const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const guard = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-journal-recovery.js');
const observed = JSON.parse(fs.readFileSync(path.join(__dirname, 'act-two-ar9-journal.fixture.json'), 'utf8').replace(/^\uFEFF/, ''));
const now = observed.timestamp + 500;
assert.equal(guard.ready(observed, now, observed.session, true), true);
assert.equal(guard.ready(observed, now, observed.session, false), false);
for (const omitted of ['Requires Adventure Rank 10', "Enter Raptor's Hideout", 'In Progress']) {
  const changed = structuredClone(observed);
  changed.ocr = changed.ocr.filter(row => row.text !== omitted);
  assert.equal(guard.ready(changed, now, changed.session, true), false, omitted);
}
console.log('5 AR9 journal recovery guard assertions passed');
