const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-town-recovery.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('captured Kaeya shop climb allows only fresh local healthy release',()=>{
 const o=JSON.parse(fs.readFileSync(__dirname+'/act-two-kaeya-shop.fixture.json','utf8'));
 assert.equal(gate.ready(o,o.timestamp,o.session),true);
 assert.equal(gate.ready(o,o.timestamp+1001,o.session),false);
 assert.equal(gate.ready({...o,map:{...o.map,x:o.map.x+3}},o.timestamp,o.session),false);
 assert.equal(gate.ready({...o,hud:{...o.hud,objectives:['Talk to Wagner the blacksmith']}},o.timestamp,o.session),false);
});
test('Kaeya navigation uses bounded pause protection',async()=>{
 let wrapped=0; const api={runActTwoNavigationWithPause:async()=>{wrapped++;return {pauseVerified:true};}};
 const request={objective:'Talk to Kaeya',deadlineMs:45000,waypoints:[{map:'Teyvat',x:0,y:0}]};
 assert.deepEqual(await mission.runNavigation(request,{hud:{}},api,()=>{}),{pauseVerified:true});
 assert.equal(wrapped,1);
 assert.equal((await mission.runNavigation({...request,deadlineMs:46000},{hud:{}},api,()=>{})).status,'stopped');
 assert.equal(wrapped,1);
});
test('Kaeya interaction rejects nearby Katheryne',async()=>{
 const field={hud:{interact:true,objectives:['Talk to Kaeya']},ocr:[{text:'F',x:1100,y:520},{text:'Katheryne',x:1214,y:517}]};
 let pressed=0;const api={runActTwoNavigationWithPause:async(o,observe,callback)=>callback(field),keyPress:async()=>{pressed++;}};
 assert.equal((await mission.runQuestStep('actTwoKaeyaTalk',{hud:{}},api,()=>{})).status,'stopped');assert.equal(pressed,0);
});

test('recorded white-text OCR resolves the cyan NPC overlap without fuzzy objective acceptance',async()=>{
 const raw=JSON.parse(fs.readFileSync(__dirname+'/act-two-kaeya-overlap.fixture.json','utf8'));
 const masked=JSON.parse(fs.readFileSync(__dirname+'/act-two-kaeya-white-ocr.fixture.json','utf8'));
 for(const [o,expected] of [[raw,'stopped'],[masked,'arrived']]){
  let now=o.timestamp;const api={now:()=>now,sleep:async ms=>{now+=ms;},checkStop:()=>{},runActTwoNavigationWithPause:async(initial,observe,callback)=>callback(initial)};
  const result=await mission.runNavigation({objective:'Talk to Kaeya',deadlineMs:1000,waypoints:[o.map]},o,api,async()=>o);
  assert.equal(result.status,expected);
 }
});

test('city wall climb requires the captured location, healthy Kaeya, and actual threat scan',()=>{
 const o=JSON.parse(fs.readFileSync(__dirname+'/act-two-kaeya-wall.fixture.json','utf8'));
 assert.equal(gate.wallReady(o,o.timestamp,o.session),true);
 assert.equal(gate.wallReady(o,o.timestamp+1001,o.session),false);
 assert.equal(gate.wallReady({...o,map:{...o.map,x:o.map.x+6}},o.timestamp,o.session),false);
 assert.equal(gate.wallReady({...o,hud:{...o.hud,enemyBarDiagnostic:null}},o.timestamp,o.session),false);
 assert.equal(gate.wallReady({...o,hud:{...o.hud,enemyBars:[{}]}},o.timestamp,o.session),false);
});

test('second witnessed wall accepts captured punctuation but rejects another objective',()=>{
 const o=JSON.parse(fs.readFileSync(__dirname+'/act-two-kaeya-second-wall.fixture.json','utf8'));
 assert.equal(gate.wallReady(o,o.timestamp,o.session),true);
 assert.equal(gate.wallReady({...o,hud:{...o.hud,objectives:['Talk to Lisa']}},o.timestamp,o.session),false);
});
