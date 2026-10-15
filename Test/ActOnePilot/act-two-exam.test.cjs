const test=require('node:test'),assert=require('node:assert/strict');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('License to Glide journal close requires its right-hand title',async()=>{
 let keys=[]; const api={keyPress:async k=>keys.push(k),sleep:async()=>{},finishActTwoDialogue:async(o,obs,r)=>r};
 const o={hud:{journal:true},ocr:[{text:'License to Glide',x:872,y:119}]};
 assert.equal((await mission.runQuestStep('actTwoJournalClose',o,api,async()=>({hud:{world:true}}))).status,'completed');
 assert.deepEqual(keys,['VK_ESCAPE']);
 for(const patch of [{x:186},{text:'Unrelated quest'},{y:400}]){keys=[];await mission.runQuestStep('actTwoJournalClose',{...o,ocr:[{...o.ocr[0],...patch}]},api,()=>{});assert.deepEqual(keys,[]);}
});
test('Exam approach retains finite protected navigation',async()=>{
 let calls=0;const api={runActTwoNavigationWithPause:async()=>{calls++;return {pauseVerified:true};}};
 const r={objective:'Go to the exam point',deadlineMs:45000,waypoints:[{map:'Teyvat',x:-1370,y:1850}]};
 assert.equal((await mission.runNavigation(r,{hud:{}},api,()=>{})).pauseVerified,true);
 assert.equal((await mission.runNavigation({...r,deadlineMs:45001},{hud:{}},api,()=>{})).status,'stopped');assert.equal(calls,1);
});
test('Exam cliff recovery opens only the map from the witnessed healthy climbing position',()=>{
 const fs=require('node:fs'),s=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8');
 const check=new Function('o','request',s.match(/function examMapEscape\(o\)\{([^\n]+)\}/)[1]);
 const o={map:{map:'Teyvat',x:-1342.426,y:1691.34},hud:{world:true,climbing:true,health:{current:2313,max:2313},objectives:['Go to the exam point']}};
 assert.equal(check(o,{step:'actTwoWorldMap'}),true);
 for(const patch of [{map:{...o.map,x:-1352}},{hud:{...o.hud,health:{current:2300,max:2313}}},{hud:{...o.hud,objectives:['Unrelated quest']}},{hud:{...o.hud,climbing:false}}])assert.equal(check({...o,...patch},{step:'actTwoWorldMap'}),false);
 assert.equal(check(o,{step:'actTwoCharacter'}),false);
});
