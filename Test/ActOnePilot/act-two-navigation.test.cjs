const test=require('node:test'),assert=require('node:assert/strict');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('Guild navigation rejects unbounded travel and requires local pause protection',async()=>{
 const request={objective:'Talk to Katheryne for more details',deadlineMs:30000,waypoints:[{map:'Teyvat',x:0,y:0}]};
 const observation={hud:{}};
 assert.equal((await mission.runNavigation(request,observation,{},()=>{})).status,'stopped');
 let wrapped=0;
 const api={runActTwoNavigationWithPause:async(initial,observe,callback)=>{wrapped++;assert.equal(initial,observation);assert.equal(typeof callback,'function');return {pauseVerified:true};}};
 assert.equal((await mission.runNavigation({...request,deadlineMs:90000},observation,api,()=>{})).status,'stopped');
 assert.equal(wrapped,0);
 assert.deepEqual(await mission.runNavigation(request,observation,api,()=>{}),{pauseVerified:true});
 assert.equal(wrapped,1);
});
test('Guild conversation refuses nearby unrelated interaction and recognizes Katheryne choices',async()=>{
 const field={hud:{interact:true,objectives:['Talk to Katheryne for more details']},ocr:[{text:'F',x:1100,y:520},{text:'Wagner',x:1214,y:517}]};
 let pressed=0;
 const api={runActTwoNavigationWithPause:async(o,observe,callback)=>callback(field),keyPress:async()=>{pressed++;}};
 const result=await mission.runQuestStep('actTwoGuildTalk',{hud:{}},api,()=>{});
 assert.equal(result.reason,'Exact Katheryne interaction required');assert.equal(pressed,0);
 const dialogue={hud:{choice:true},ocr:[{text:'Katheryne',x:820,y:850},{text:'About the Adventurers Guild...',x:1200,y:500}]};
 assert.equal(mission.selectDialogueChoice(dialogue),'About the Adventurers Guild...');
 dialogue.ocr.push({text:'Spend Primogems',x:1200,y:600});assert.equal(mission.selectDialogueChoice(dialogue),null);
});
