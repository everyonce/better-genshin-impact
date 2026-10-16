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

test('Informant approach uses the finite protected navigation wrapper',async()=>{
 const observation={hud:{}};let wrapped=0;
 const api={runActTwoNavigationWithPause:async()=>{wrapped++;return {pauseVerified:true};}};
 const req={objective:'Meet with the informant at the designated location',deadlineMs:45000,waypoints:[{map:'Teyvat',x:-1125,y:2225}]};
 assert.equal((await mission.runNavigation(req,observation,api,()=>{})).pauseVerified,true);
 assert.equal(wrapped,1);
 assert.equal((await mission.runNavigation({...req,deadlineMs:45001},observation,api,()=>{})).status,'stopped');
 assert.equal(wrapped,1);
});

test('Vile talk requires selected exact NPC and objective and rejects spending choices',async()=>{
 const field=structuredClone(require('./act-two-vile.fixture.json'));
 let keys=[],now=0;const api={runActTwoNavigationWithPause:async(o,observe,fn)=>fn(field),keyPress:async k=>keys.push(k),sleep:async ms=>now+=ms,now:()=>now,checkStop:()=>{}};
 await mission.runQuestStep('actTwoVileTalk',{hud:{}},api,async()=>({hud:{world:true}}));assert.deepEqual(keys,['VK_F']);
 keys=[];field.ocr.find(r=>r.text==='Vile'&&r.x>=1150&&r.x<=1500&&r.y>=480&&r.y<=600).y=580;await mission.runQuestStep('actTwoVileTalk',{hud:{}},api,async()=>({hud:{world:true}}));assert.deepEqual(keys,[]);
 const dialogue={hud:{choice:true},ocr:[{text:'Vile',x:900,y:850},{text:'About the treasure...',x:1200,y:500}]};
 assert.equal(mission.selectDialogueChoice(dialogue),'About the treasure...');dialogue.ocr.push({text:'Spend Mora',x:1200,y:600});assert.equal(mission.selectDialogueChoice(dialogue),null);
});
