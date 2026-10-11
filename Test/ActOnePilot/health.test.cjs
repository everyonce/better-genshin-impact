const test = require('node:test');
const assert = require('node:assert/strict');
const {health,fullHealthRows} = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
test('camp capture rejects inserted HP digit so numeric-half fallback can run',()=>{
  assert.equal(health([{text:'8827/1062'}]),null);
  assert.deepEqual(health([{text:'882/1062'}]),{current:882,max:1062});
  assert.equal(health([{text:'882/0'}]),null);
  assert.equal(health([{text:'88211062'}]),null);
  assert.deepEqual(health([{text:'0/1062'}]),{current:0,max:1062});
  assert.equal(health([{text:'062/1062'}]),null);
  assert.equal(health([{text:'1062/01062'}]),null);
});

test('frame 258 full-frame 1062/1062 row avoids the scaled false-low 062/1062 result',()=>{
  const frame258=[{text:'1062/1062',x:910,y:1003,width:97,height:14}];
  assert.deepEqual(fullHealthRows(frame258),frame258);
});

test('frame 181 invalid leading-zero full-frame row falls back to the correct scaled result',()=>{
  const frame181=[{text:'062/1062',x:916,y:1003,width:91,height:14}];
  assert.equal(fullHealthRows(frame181),null);
  assert.deepEqual(health([{text:'1062/1062'}]),{current:1062,max:1062});
});

test('full-frame fast path requires one exact numeric row in the HP-bar region',()=>{
  assert.equal(fullHealthRows([{text:'HP 1062/1062',x:910,y:1003,width:115,height:14}]),null);
  assert.equal(fullHealthRows([{text:'1062/1062',x:850,y:1003,width:97,height:14}]),null);
  assert.equal(fullHealthRows([
    {text:'1062/1062',x:910,y:1003,width:97,height:14},
    {text:'1062/1062',x:916,y:1003,width:91,height:14},
  ]),null);
});

test('a low full-frame value is accepted only when scaled OCR agrees',()=>{
  const low=[{text:'500/1062',x:916,y:1003,width:91,height:14}];
  assert.equal(fullHealthRows(low),null,'needs scaled confirmation');
  assert.deepEqual(fullHealthRows(low,[{text:'500/1062'}]),low);
  assert.deepEqual(fullHealthRows(low,[{text:'800/1062'}]),[],'conflict is represented as unknown health');
});
