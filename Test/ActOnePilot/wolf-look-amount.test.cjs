const test = require('node:test');
const assert = require('node:assert/strict');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

test('Wolf look deltas preserve default 250 and apply bounded amounts with signed directions',()=>{
  const directions={wolfLookRight:[250,0],wolfLookLeft:[-250,0],wolfLookDown:[0,250],wolfLookUp:[0,-250]};
  for(const [step,expected] of Object.entries(directions))
    assert.deepEqual(bgi.wolfLookDelta(step,undefined,false),{dx:expected[0],dy:expected[1]});
  const custom={wolfLookRight:[80,0],wolfLookLeft:[-80,0],wolfLookDown:[0,80],wolfLookUp:[0,-80]};
  for(const [step,expected] of Object.entries(custom))
    assert.deepEqual(bgi.wolfLookDelta(step,80,true),{dx:expected[0],dy:expected[1]});
});

test('Wolf look rejects malformed or unbounded values and non-look misuse',()=>{
  for(const amount of [NaN,'80',15,251,80.5,null])
    assert.throws(()=>bgi.wolfLookDelta('wolfLookLeft',amount,true),/lookAmount/);
  assert.throws(()=>bgi.wolfLookDelta('wolfForward',80,true),/only valid for Wolf look steps/);
  assert.equal(bgi.wolfLookDelta('wolfForward',undefined,false),null);
});
