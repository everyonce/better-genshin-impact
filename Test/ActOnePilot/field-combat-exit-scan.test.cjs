const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('combat uses the full-width route scan only when its final inventory protector is active', () => {
  const context = {};
  const adapter = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
  vm.runInNewContext(fs.readFileSync(adapter, 'utf8'), context);
  const scan = context.actOneRequestsGroundObservation;
  const combat = {mission:'questStep', step:'actTwoFieldCombat'};
  assert.equal(scan(combat, false, false), false);
  assert.equal(scan(combat, false, true), true);
  assert.equal(scan(combat, true, true), false);
  assert.equal(scan({mission:'questStep', step:'actTwoNativeCombat'}, false, true), false);
  assert.equal(scan({mission:'observe'}, false, false), true);
  assert.equal(scan({mission:'navigation', objective:'Explore for Adventure Rank', requireMeasuredGround:true}, false, false), true);
  assert.equal(scan({mission:'navigation', objective:'Explore for Adventure Rank'}, false, false), false);
});
