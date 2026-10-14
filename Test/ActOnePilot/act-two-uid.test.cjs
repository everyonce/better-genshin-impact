const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
test('matching full and cropped UID reads remain valid; conflicting or absent identities fail',()=>{
 const o=JSON.parse(fs.readFileSync(__dirname+'/act-two-duplicate-uid.fixture.json','utf8'));
 assert.equal(bgi.originalAccount(o.ocr),true);
 assert.equal(bgi.originalAccount(o.ocr.concat({text:'UID: 665976391',x:1680,y:1052})),false);
 assert.equal(bgi.originalAccount([{text:'693306810',x:1500,y:1052}]),false);
 assert.equal(bgi.originalAccount([]),false);
});
