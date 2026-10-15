const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const ctx={};vm.runInNewContext(fs.readFileSync(__dirname+'/../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js','utf8'),ctx);
test('overlapping map label requires exact regional map anchors and fresh state',()=>{
 const o={session:'s',frameId:1,timestamp:1000,map:null,hud:{bigMap:true,world:false},ocr:[{text:'Starfell Valley',x:1580,y:980},{text:'TExploration Progress: 9%',x:1500,y:1010}]};
 assert.equal(ctx.actOneLocalPauseProof(o,1000,'s').kind,'map');
 assert.equal(ctx.actOneLocalPauseProof(o,2001,'s'),null);
 assert.equal(ctx.actOneLocalPauseProof({...o,hud:{world:true,bigMap:true}},1000,'s'),null);
 assert.equal(ctx.actOneLocalPauseProof({...o,ocr:o.ocr.slice(1)},1000,'s'),null);
 assert.equal(ctx.actOneLocalPauseProof({...o,ocr:o.ocr.map(r=>r.text.startsWith('TExploration')?{...r,text:'Other Exploration Progress: 9%'}:r)},1000,'s'),null);
});
