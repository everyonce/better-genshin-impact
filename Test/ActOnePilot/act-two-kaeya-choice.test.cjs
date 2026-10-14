const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('recorded Kaeya eye-patch choice recovers missing Auto through same-capture crop',()=>{
 const raw=JSON.parse(fs.readFileSync(__dirname+'/act-two-kaeya-choice-raw.fixture.json','utf8'));
 const fixed=JSON.parse(fs.readFileSync(__dirname+'/act-two-kaeya-choice-cropped.fixture.json','utf8'));
 assert.equal(bgi.autoCropNeeded(raw.ocr),true);
 assert.equal(bgi.autoCropNeeded(fixed.ocr),false);
 assert.equal(fixed.hud.choice,true);
 assert.ok(mission.selectDialogueChoice(fixed));
 assert.equal(bgi.autoCropNeeded([{text:'Kaeya',x:1665,y:442}]),false);
 assert.equal(bgi.autoCropNeeded([{text:'Unrecognized',x:902,y:850}]),false);
 assert.equal(bgi.dialogueReady(fixed.ocr,true),false);
});
