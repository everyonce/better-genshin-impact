const test=require('node:test'),assert=require('node:assert/strict');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
async function run(field,name='actTwoJackTalk'){
 let now=0,keys=[];
 const api={now:()=>now,sleep:async ms=>now+=ms,checkStop:()=>{},keyPress:async k=>keys.push(k),runActTwoNavigationWithPause:async(o,observe,callback)=>callback(field)};
 await mission.runQuestStep(name,{hud:{}},api,async()=>({hud:{world:true}}));return keys;
}
test('Jack interaction requires selected prompt, healthy terrace and no threats',async()=>{
 const f={map:{map:'Teyvat',x:-846.2,y:2189.2},hud:{world:true,interact:true,groundControls:true,health:{current:2313,max:2313},enemyBarDiagnostic:{level:'any'},enemyBars:[],objectives:[]},ocr:[{text:'F',x:1110,y:530,height:30},{text:'Jack',x:1210,y:530,height:30}]};
 assert.deepEqual(await run(f),['VK_F']);
 for(const p of [{map:{...f.map,x:-900}},{hud:{...f.hud,health:{current:2000,max:2313}}},{hud:{...f.hud,climbing:true}},{hud:{...f.hud,enemyBars:[{}]}},{hud:{...f.hud,enemyBarDiagnostic:null}},{hud:{...f.hud,objectives:['Unrelated quest']}},{ocr:[f.ocr[0],{...f.ocr[1],text:'Cyrus'}]},{ocr:[{...f.ocr[0],y:490},f.ocr[1]]}])assert.deepEqual(await run({...f,...p}),[]);
});
test('Jack dialogue rejects spending choices',()=>{
 const o={hud:{choice:true},ocr:[{text:'Jack',x:900,y:850},{text:'About adventuring...',x:1200,y:500}]};
 assert.equal(mission.selectDialogueChoice(o),'About adventuring...');
 o.ocr.push({text:'Spend Primogems',x:1200,y:600});assert.equal(mission.selectDialogueChoice(o),null);
});

test('Cyrus available quest uses a separate exact healthy prompt',async()=>{const f={map:{map:'Teyvat',x:-838,y:2187},hud:{world:true,interact:true,groundControls:true,health:{current:2313,max:2313},enemyBarDiagnostic:{level:'any'},enemyBars:[],objectives:[]},ocr:[{text:'F',x:1110,y:530,height:30},{text:'Cyrus',x:1210,y:530,height:30}]};assert.deepEqual(await run(f,'actTwoCyrusTalk'),['VK_F']);assert.deepEqual(await run(f),[]);assert.deepEqual(await run({...f,hud:{...f.hud,enemyBarDiagnostic:null}},'actTwoCyrusTalk'),[]);});
test('Cyrus ambush handoff supports upgraded Kaeya only with exact return objective and safe prompt',async()=>{const f={map:{map:'Teyvat',x:-838,y:2187},hud:{world:true,interact:true,groundControls:true,health:{current:2635,max:2635},enemyBarDiagnostic:{level:'any'},enemyBars:[],objectives:['Talk to Cyrus']},ocr:[{text:'F',x:1110,y:530,height:30},{text:'Cyrus',x:1210,y:530,height:30}]};assert.deepEqual(await run(f,'actTwoCyrusTalk'),['VK_F']);for(const p of [{map:{...f.map,x:-900}},{hud:{...f.hud,health:{current:2326,max:2635}}},{hud:{...f.hud,objectives:['Defeat the attacking monsters']}},{hud:{...f.hud,enemyBars:[{}]}},{hud:{...f.hud,enemyBarDiagnostic:null}},{ocr:[f.ocr[0],{...f.ocr[1],text:'Jack'}]}])assert.deepEqual(await run({...f,...p},'actTwoCyrusTalk'),[]);});

test('truncated Cyrus speaker requires his exact guild title and retains spending rejection',()=>{
 const o={hud:{choice:true},ocr:[{text:'yrus',x:940,y:860},{text:"Branch Master, Adventurers' Guild",x:770,y:895},{text:'Is that a bad thing?',x:1319,y:792}]};
 assert.equal(mission.selectDialogueChoice(o),'Is that a bad thing?');
 assert.equal(mission.selectDialogueChoice({...o,ocr:o.ocr.filter(r=>r.y!==895)}),null);
 assert.equal(mission.selectDialogueChoice({...o,ocr:[...o.ocr,{text:'Spend Primogems',x:1200,y:600}]}),null);
});
