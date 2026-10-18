const test=require('node:test'),assert=require('node:assert/strict'),g=require(process.env.ACT_TWO_FIELD_MODULE||'../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js');
test('retired road-bypass experiment cannot authorize further movement',()=>{assert.equal(g.plan({roadBypass:true},{},Date.now()),false);assert.equal(g.plan({roadBypass:false},{},Date.now()),false);});
