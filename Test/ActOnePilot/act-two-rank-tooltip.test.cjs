const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const ctx={};vm.runInNewContext(fs.readFileSync(__dirname+'/../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js','utf8'),ctx);
const o=JSON.parse(fs.readFileSync(__dirname+'/act-two-rank-tooltip.fixture.json','utf8'));
test('recorded rank tooltip does not hide independently anchored Paimon menu proof',()=>{
 assert.equal(ctx.actOneLocalPauseProof(o,o.timestamp,o.session).kind,'menu');
 assert.equal(ctx.actOneLocalPauseProof(o,o.timestamp+1001,o.session),null);
 const rank=o.ocr.find(r=>r.text==='Adventure Rank'&&r.x===310);
 assert.equal(ctx.actOneLocalPauseProof({...o,ocr:o.ocr.concat(rank)},o.timestamp,o.session),null);
 assert.equal(ctx.actOneLocalPauseProof({...o,hud:{...o.hud,world:true}},o.timestamp,o.session),null);
});
