const test=require('node:test'),assert=require('node:assert/strict');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const door=require('./act-two-hideout-mystery-door.fixture.json');
test('HQ hint objective permits the same exact entrance and rejects unrelated quests',async()=>{
 async function run(objectives,change=()=>{}){
  const frame=structuredClone(door);frame.hud.objectives=objectives;change(frame);const keys=[];
  const api={runActTwoNavigationWithPause:async(o,observe,fn)=>fn(frame),keyPress:async k=>keys.push(k),sleep:async()=>{},checkStop:()=>{}};
  await mission.runQuestStep('actTwoHqEnter',frame,api,async()=>({hud:{groundControls:true}}));return keys;
 }
 const hint=['Solve the mystery (Go to Kaeya at the Knights of Favonius','HQ for a hint)'];
 assert.deepEqual(await run(hint),['VK_F']);
 assert.deepEqual(await run(['Talk to Lisa']),[]);
 assert.deepEqual(await run(hint,o=>o.ocr=o.ocr.filter(r=>r.text!=='F')),[]);
 assert.deepEqual(await run(hint,o=>o.map.x+=10),[]);
});
test('missing-control indoor frame requests OCR only in the exact quest context, never in menus or dialogue',()=>{
 const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),o=require('./act-two-hideout-mystery-controls.fixture.json');
 const request={mission:'questStep',step:'actTwoIndoorMove'},quest=o.hud.objectives.map(text=>({text}));
 assert.equal(o.hud.groundControls,false);
 assert(bgi.indoorControlCandidate(request,o.ocr,o.hud.health,{},quest));
 assert.equal(bgi.indoorSafe(o,o.timestamp,o.session),false,'requesting OCR does not grant input permission');
 for(const flag of ['auto','journal','bigMap','choice','dialogueReady','tutorialStep'])assert.equal(bgi.indoorControlCandidate(request,o.ocr,o.hud.health,{[flag]:true},quest),false);
 assert.equal(bgi.indoorControlCandidate({...request,step:'actTwoRecover'},o.ocr,o.hud.health,{},quest),false);
 assert.equal(bgi.indoorControlCandidate(request,o.ocr,o.hud.health,{},[{text:'Unrelated quest'}]),false);
 assert.equal(bgi.indoorControlCandidate(request,o.ocr.filter(r=>!r.text.includes('693306810')),o.hud.health,{},quest),false);
});
test('recorded full-health hint interior retains account, freshness, quest and threat checks without GPS',()=>{
 const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),o=require('./act-two-hideout-mystery-interior.fixture.json');
 assert(bgi.indoorSafe({...o,map:null},o.timestamp,o.session));
 for(const change of [v=>v.hud.health.current--,v=>v.hud.objectives=['Talk to Lisa'],v=>v.hud.enemyBars=[{}],v=>v.hud.climbing=true,v=>v.ocr=v.ocr.filter(r=>!r.text.includes('693306810'))]){
  const v=structuredClone(o);change(v);assert.equal(bgi.indoorSafe(v,o.timestamp,o.session),false);
 }
 assert.equal(bgi.indoorSafe(o,o.timestamp+1001,o.session),false);assert.equal(bgi.indoorSafe(o,o.timestamp,'other'),false);
});
