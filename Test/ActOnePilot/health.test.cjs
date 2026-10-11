const test = require('node:test');
const assert = require('node:assert/strict');
const {health} = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
test('camp capture rejects inserted HP digit so numeric-half fallback can run',()=>{
  assert.equal(health([{text:'8827/1062'}]),null);
  assert.deepEqual(health([{text:'882/1062'}]),{current:882,max:1062});
  assert.equal(health([{text:'882/0'}]),null);
  assert.equal(health([{text:'88211062'}]),null);
  assert.deepEqual(health([{text:'0/1062'}]),{current:0,max:1062});
});
