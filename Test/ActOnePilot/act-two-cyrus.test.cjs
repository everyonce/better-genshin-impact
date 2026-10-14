const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const fixture=JSON.parse(fs.readFileSync(__dirname+'/act-two-cyrus.fixture.json','utf8'));
async function run(field){
 let now=0,keys=[];
 const api={now:()=>now,sleep:async ms=>now+=ms,checkStop:()=>{},keyPress:async k=>keys.push(k),runActTwoNavigationWithPause:async(o,observe,callback)=>callback(field)};
 const result=await mission.runQuestStep('actTwoCyrusTalk',{hud:{}},api,async()=>({hud:{world:true}}));
 return {result,keys};
}
test('recorded Cyrus quest interaction presses F once',async()=>{
 const r=await run(fixture);assert.deepEqual(r.keys,['VK_F']);assert.equal(r.result.reason,'world_returned');
});
test('Cyrus requires quest, exact NPC, and selected row',async()=>{
 for(const o of [
  {...fixture,hud:{...fixture.hud,objectives:['Talk to Kaeya']}},
  {...fixture,ocr:fixture.ocr.map(r=>r.text==='Cyrus'?{...r,text:'Wood'}:r)},
  {...fixture,ocr:fixture.ocr.map(r=>r.text==='F'?{...r,y:490}:r)}
 ])assert.deepEqual((await run(o)).keys,[]);
});
test('Cyrus dialogue still rejects spending choices',()=>{
 const o={hud:{choice:true},ocr:[{text:'Cyrus',x:900,y:850},{text:'About the treasure...',x:1200,y:500}]};
 assert.equal(mission.selectDialogueChoice(o),'About the treasure...');
 o.ocr.push({text:'Spend Primogems',x:1200,y:600});assert.equal(mission.selectDialogueChoice(o),null);
});
test('Report to Kaeya navigation retains the bounded wrapper',async()=>{
 let wrapped=0;
 const api={runActTwoNavigationWithPause:async()=>{wrapped++;return {pauseVerified:true};}};
 const r=await mission.runNavigation({objective:'Report to Kaeya',deadlineMs:45000,waypoints:[{map:'Teyvat',x:-816,y:2220}]},{hud:{}},api,()=>{});
 assert.equal(wrapped,1);assert.equal(r.pauseVerified,true);
});
test('captured report retaining wall is bounded by location, quest, threat scan and health',()=>{
 const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-town-recovery.js');
 for(const name of ['act-two-report-wall.fixture.json','act-two-report-hq-wall.fixture.json']){
 const o=JSON.parse(fs.readFileSync(__dirname+'/'+name,'utf8'));
 assert.equal(gate.wallReady(o,o.timestamp,o.session),true);
 for(const bad of [{...o,map:{...o.map,x:o.map.x+4}},{...o,hud:{...o.hud,objectives:['Talk to Kaeya']}},{...o,hud:{...o.hud,enemyBarDiagnostic:null}},{...o,hud:{...o.hud,health:{current:1000,max:1700}}}])assert.equal(gate.wallReady(bad,o.timestamp,o.session),false);
 }
});
test('captured automatic report dialogue can hand off without claiming pause',()=>{
 const file='../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js';
 const bgi=require(file),source=fs.readFileSync(require.resolve(file),'utf8');
 const body=source.match(/pauseDialogueHandoff: function\(o\)\{([\s\S]*?)\n        \},/)[1];
 const check=new Function('request','actTwoOriginalAccount','Date','o',body);
 const o=JSON.parse(fs.readFileSync(__dirname+'/act-two-report-dialogue.fixture.json','utf8'));
 const r={mission:'navigation',objective:'Report to Kaeya',session:o.session};
 const run=(request,frame,now=o.timestamp)=>check(request,bgi.originalAccount,{now:()=>now},frame);
 assert.equal(run(r,o),true);
 assert.equal(run({...r,objective:'Unrelated quest'},o),false);
 assert.equal(run({...r,session:'other'},o),false);
 assert.equal(run(r,o,o.timestamp+1001),false);
 assert.equal(run(r,{...o,hud:{...o.hud,health:{current:1700,max:1700}}}),false);
 assert.equal(run(r,{...o,ocr:o.ocr.map(x=>({...x,text:x.text.replace('693306810','665976391')}))}),false);
});
