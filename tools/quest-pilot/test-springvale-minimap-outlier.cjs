const fs = require('node:fs');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const probe = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/localization-probe.js');

const stem = 'tools/quest-pilot/fixtures/act-two-springvale-minimap-2198';
const observed = JSON.parse(fs.readFileSync(stem + '.json', 'utf8'));
const pixels = fs.readFileSync(stem + '.png');
assert.equal(crypto.createHash('sha256').update(pixels).digest('hex').toUpperCase(),
  'F638C69218053BEAAA0EEDC11F292F19A78B7AC07371385C63F5518266B42DA6');
assert.equal(observed.session, 'mvf7ifnp-30yiczwdy7v');
assert.equal(observed.frameId, 2198);
assert.equal(observed.hud.groundControls, true);
assert.equal(observed.hud.health.current, 3942);
assert(observed.hud.objectives.includes("Enter Raptor's Hideout"));
assert.equal(observed.map.map, 'Teyvat');
assert.equal(probe.candidate(observed.map), false, 'Global matcher outlier must not become a route anchor');
assert.equal(probe.candidate({ ...probe.anchor }), true, 'Known waypoint remains a candidate, not proof');
console.log('Recorded Springvale minimap outlier rejected; no position inferred');
