const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-hideout-dialogue.js'),entry=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-hideout-entry.js');
const wind=require('./act-two-dialogue-wind-current.fixture.json'),bomb=require('./act-two-dialogue-bomb-tutorial.fixture.json');
function apiFor(sequence){let clicks=[];return {clicks,api:{check(){},target:o=>entry.tutorialTarget(o,o.timestamp,o.session),advance:async(o)=>{clicks.push(o.frameId);return sequence.shift();}}};}
test('recorded wind and bomb tutorials hand off locally with two exact actions and verified pause',async()=>{
 const m=apiFor([{status:'stopped',inputs:1,reason:'Next aerial tutorial page; inspect before continuing',pauseVerified:false},{status:'completed',inputs:1,pauseVerified:true}]);
 const r=await g.run(wind,m.api,async()=>bomb);assert.deepEqual(m.clicks,[1784,1786]);assert.equal(r.inputs,2);assert.equal(r.pauseVerified,true);
});
test('unchanged, unknown and third tutorial cannot cause repeated actions',async()=>{
 const m=apiFor([{status:'stopped',inputs:1,reason:'Next aerial tutorial page; inspect before continuing',pauseVerified:false}]);const r=await g.run(wind,m.api,async()=>wind);assert.equal(m.clicks.length,1);assert.equal(r.pauseVerified,false);
 const n=apiFor([]);await g.run({...wind,ocr:[]},n.api,async()=>bomb);assert.equal(n.clicks.length,0);
 const p=apiFor(Array(2).fill({status:'stopped',inputs:1,reason:'Next aerial tutorial page; inspect before continuing',pauseVerified:false}));const z=await g.run(wind,p.api,async()=>bomb);assert.equal(p.clicks.length,2);assert.equal(z.pauseVerified,false);
});
test('tutorial failure never triggers generic Space or a second click',async()=>{let inputs=0;await assert.rejects(()=>g.run(wind,{check(){},target:()=>({label:'wind'}),advance:async()=>{inputs++;throw Error('focus lost');}},async()=>bomb),/focus lost/);assert.equal(inputs,1);});
test('dialogue mission hands recorded tutorial to the exact local handler without Space or unknown waits',async()=>{
 const fs=require('fs'),vm=require('vm'),context={module:{exports:{}}};vm.runInNewContext(fs.readFileSync('BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js','utf8'),context);
 let called=0;const r=await context.module.exports.runDialogue({now:()=>wind.timestamp,checkStop(){},actTwoHideoutTutorialReady:o=>!!entry.tutorialTarget(o,o.timestamp,o.session),runActTwoHideoutDialogueTutorials:async()=>{called++;return {status:'completed',inputs:2,pauseVerified:true};},keyPress:async()=>{throw Error('Generic input forbidden');},sleep:async()=>{throw Error('Unknown delay forbidden');}},async()=>wind);
 assert.equal(called,1);assert.equal(r.presses,2);assert.equal(r.dialoguePresses,0);assert.equal(r.pauseVerified,true);
});
