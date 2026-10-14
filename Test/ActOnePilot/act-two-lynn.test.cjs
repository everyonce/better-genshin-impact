const test=require('node:test'),assert=require('node:assert/strict');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
function field(){return {hud:{interact:true,objectives:['Speak to Lynn']},ocr:[{text:'Lynn',x:1230,y:530,width:70,height:25},{text:'F',x:1120,y:530,width:20,height:25}]};}
async function run(o){let now=0,keys=[];const api={now:()=>now,sleep:async ms=>now+=ms,checkStop:()=>{},keyPress:async k=>keys.push(k),runActTwoNavigationWithPause:async(i,observe,fn)=>fn(o)};return {result:await mission.runQuestStep('actTwoLynnTalk',{hud:{}},api,async()=>({hud:{world:true}})),keys};}
test('Lynn selected interaction requires exact quest and selected F row',async()=>{assert.deepEqual((await run(field())).keys,['VK_F']);for(const modify of [o=>o.hud.objectives=['Other quest'],o=>o.ocr[0].text='Cook',o=>o.ocr[1].y=480]){const o=field();modify(o);assert.deepEqual((await run(o)).keys,[]);}});
test('Lynn navigation requires finite pause wrapper',async()=>{let wrapped=0;const api={runActTwoNavigationWithPause:async()=>{wrapped++;return {pauseVerified:true};}};assert.equal((await mission.runNavigation({objective:'Speak to Lynn',deadlineMs:30000,waypoints:[{map:'Teyvat',x:0,y:0}]},{hud:{}},api,()=>{})).pauseVerified,true);assert.equal(wrapped,1);});
test('Lynn dialogue recognizes normal choice but rejects spending',()=>{const o={hud:{choice:true},ocr:[{text:'Lynn',x:900,y:850},{text:'What should I cook?',x:1200,y:500}]};assert.equal(mission.selectDialogueChoice(o),'What should I cook?');o.ocr.push({text:'Spend Primogems',x:1200,y:600});assert.equal(mission.selectDialogueChoice(o),null);});
test('Lynn delivery accepts full objective but rejects incomplete toast',async()=>{const o=field();o.hud.objectives=['Give the Chicken-Mushroom Skewer to Lynn'];assert.deepEqual((await run(o)).keys,['VK_F']);o.hud.objectives=['Give the Chicken-Mushroom Skewer'];assert.deepEqual((await run(o)).keys,[]);});
test('Cook selector uses readiness and only scrolls one selected-row offset',async()=>{
 const fs=require('node:fs'),source=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8');
 const body=source.match(/selectActTwoCook: async function\(\)\{([\s\S]*?)\n        \},/)[1];
 const fn=new Function('checkStop','ready','lastObservation','file','request','actTwoOriginalAccount','events','verticalScroll','return (async()=>{'+body+'})();');
 let ready=0,scroll=[];const o=field();o.ocr.push({text:'Cook',x:1230,y:600,width:70,height:25});o.hud.world=true;o.hud.health={current:1700};
 const file={readTextSync:()=>fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-interaction.js'),'utf8')};
 await fn(()=>{},()=>ready++,o,file,{step:'actTwoCookOpen'},()=>true,[],n=>scroll.push(n));assert.equal(ready,1);assert.deepEqual(scroll,[-1]);
 o.ocr[1].y=450;await assert.rejects(fn(()=>{},()=>{},o,file,{step:'actTwoCookOpen'},()=>true,[],()=>{}),/Fresh exact/);
});
