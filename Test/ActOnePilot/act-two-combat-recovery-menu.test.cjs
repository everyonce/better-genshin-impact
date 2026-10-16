const test=require('node:test'),assert=require('node:assert/strict');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-team.js');
const frames=require('./act-two-combat-recovery-menu.fixture.json');
function target(frame,action,patch){const f=frames.find(x=>x.frameId===frame),o={...f,...patch},p={session:f.session,frameId:f.frameId,createdAt:f.timestamp,reviewed:true,action},r={session:f.session,expectedFrameId:f.frameId};return g.target(o,f.timestamp,p,r);}
test('Recorded character-menu OCR variants preserve specific safe targets',()=>{
 for(const [f,a] of [[6221,'selectKaeya'],[6226,'artifacts'],[6236,'selectLumina']])assert.ok(target(f,a));
});
test('One-book recovery confirms only the exact5000EXP and1000Mora preview',()=>{
 for(const frame of [6246,6247])assert.ok(target(frame,'luminaRecoveryConfirm'));
 const f=frames.find(x=>x.frameId===6246);
 for(const [old,wrong] of [['1000','2000'],['102357','102358'],['UID: 693306810','UID: 999999999'],['Lv. 12 +1','Lv. 12 +2']]){
  assert.equal(target(6246,'luminaRecoveryConfirm',{ocr:f.ocr.map(r=>r.text===old?{...r,text:wrong}:r)}),null);
 }
 assert.equal(target(6243,'luminaRecoveryConfirm'),null);
});
