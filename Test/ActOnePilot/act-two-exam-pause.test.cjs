const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm');
const ctx={};vm.runInNewContext(fs.readFileSync(__dirname+'/../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js','utf8'),ctx);
const o=require('./act-two-exam-flight-pause.fixture.json');
test('recorded Space-only flight with faded party names permits pause using health and original UID',()=>{assert.equal(ctx.actOneLocalPauseInputReady(o,o.timestamp,o.session),true);for(const patch of [{session:'other'},{timestamp:o.timestamp-1001},{hud:{...o.hud,health:null}},{hud:{...o.hud,choice:true}},{ocr:o.ocr.filter(r=>r.text!=='Space')},{ocr:o.ocr.filter(r=>!r.text.includes('693306810'))}])assert.equal(ctx.actOneLocalPauseInputReady({...o,...patch},o.timestamp,o.session),false);});
