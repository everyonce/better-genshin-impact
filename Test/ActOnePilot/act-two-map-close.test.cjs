const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const ctx={};vm.runInNewContext(fs.readFileSync(__dirname+'/../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js','utf8'),ctx);
const o=JSON.parse(fs.readFileSync(__dirname+'/act-two-map-merged.fixture.json','utf8').replace(/^\uFEFF/,''));
test('live merged map region proves pause only with fresh map and exploration evidence',()=>{
 assert.equal(ctx.actOneLocalPauseProof(o,o.timestamp,o.session).kind,'map');
 assert.equal(ctx.actOneLocalPauseProof(o,o.timestamp+1001,o.session),null);
 assert.equal(ctx.actOneLocalPauseProof({...o,hud:{...o.hud,bigMap:false}},o.timestamp,o.session),null);
 assert.equal(ctx.actOneLocalPauseProof({...o,ocr:o.ocr.filter(r=>!r.text.startsWith('Exploration Progress'))},o.timestamp,o.session),null);
});
