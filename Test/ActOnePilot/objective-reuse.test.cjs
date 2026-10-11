const test = require('node:test');
const assert = require('node:assert/strict');
const {objectiveRows} = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
test('reuses only matching full-frame objective rows inside the objective region', () => {
  const rows=[{text:'Go toMondstadt',x:80,y:250},{text:'Higher 4m',x:100,y:284}];
  assert.deepEqual(objectiveRows(rows,'Go to Mondstadt'),rows);
  assert.equal(objectiveRows([{text:'Go to Mondstadt',x:800,y:250}],'Go to Mondstadt'),null);
  assert.equal(objectiveRows([{text:'Go to Mondstad',x:80,y:250}],'Go to Mondstadt'),null);
  assert.equal(objectiveRows(rows,'Enter the city'),null);
  assert.equal(objectiveRows(rows,null),null);
});
test('crystal approach retains cropped distance OCR even when full-frame title matches', () => {
  assert.equal(objectiveRows([{text:'Investigate what Paimon has found',x:80,y:250}],'Investigate what Paimon has found'),null);
});
