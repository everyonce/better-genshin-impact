const test=require('node:test'),assert=require('node:assert/strict');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-journal.js');
test('new Cyrus quest is selectable only beneath exact journal anchors',()=>{
 const q='Not to be Missed',o={timestamp:1000,hud:{journal:true},ocr:[{text:'In Progress',x:135,y:26,width:150,height:40},{text:'World Quests',x:194,y:740,width:180,height:30},{text:q,x:177,y:880,width:260,height:30}]},p={session:'s',frameId:12,createdAt:1000,reviewed:true,quest:q,action:'select'},r={session:'s',expectedFrameId:12};
 assert.ok(gate.target(o,1000,p,r));assert.equal(gate.target({...o,ocr:o.ocr.filter(x=>x.text!=='World Quests')},1000,p,r),null);
});
test('Cyrus threat route uses bounded pause wrapper',async()=>{
 let calls=0;const api={runActTwoNavigationWithPause:async()=>{calls++;return{pauseVerified:true};}},r={objective:'Check the suspicious location and eliminate any threats',deadlineMs:45000,waypoints:[{map:'Teyvat',x:-1130,y:2235}]};
 assert.equal((await mission.runNavigation(r,{hud:{}},api,()=>{})).pauseVerified,true);
 assert.equal((await mission.runNavigation({...r,deadlineMs:45001},{hud:{}},api,()=>{})).status,'stopped');assert.equal(calls,1);
});
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js');
test('Cyrus combat evidence remains scoped and tolerates a witnessed OCR insertion',()=>{
 const f={session:'s',timestamp:1000,map:{map:'Teyvat',x:-1125,y:2220},ocr:[{text:'UID: 693306810',x:1680,y:1050},{text:'Lv. 12',x:700,y:400}],hud:{world:true,groundControls:true,health:{current:2313,max:2313},enemyBars:[],enemyBarDiagnostic:{level:'any'},objectives:['Check the suspicious locationrand eliminate any threats','(0/3)']}};
 assert.equal(g.ready(f,f,1000,'s'),true);assert.equal(g.combatTargets(f,{enemyLevel:'any'}).length,1);
 const other={...f,hud:{...f.hud,objectives:['Talk to Cyrus']}};assert.equal(g.ready(other,other,1000,'s'),false);assert.equal(g.combatTargets(other,{enemyLevel:'any'}).length,0);
 assert.equal(g.ready({...f,map:{...f.map,x:-900}},f,1000,'s'),false);
});

test('enemy level noise and accented OCR do not hide the exact Cyrus objective',()=>{
 const f={session:'s',timestamp:1000,map:{map:'Teyvat',x:-1129,y:2245},ocr:[{text:'UID: 693306810',x:1680,y:1050},{text:'Lv. 12',x:700,y:400}],hud:{world:true,groundControls:true,health:{current:2313,max:2313},enemyBars:[],enemyBarDiagnostic:{level:'any'},objectives:['Lv. 12','Che\u010dk the suspicious location and eliminate any threats','(0/3)']}};
 assert.equal(g.ready(f,f,1000,'s'),true);assert.equal(g.combatTargets(f,{enemyLevel:'any'}).length,1);
 const changed={...f,hud:{...f.hud,objectives:['Lv. 12','Talk to Cyrus']}};
 assert.equal(g.failureReason(changed,f,1000,'s'),'objective_mismatch');assert.equal(g.ready(changed,f,1000,'s'),false);
});

test('scrolled journal permits another exact authorized quest beside World Quests heading',()=>{
 const o={timestamp:1000,hud:{journal:true},ocr:[{text:'In Progress',x:138,y:30,width:150,height:30},{text:'World Quests',x:176,y:723,width:180,height:30},{text:'Mystery of the Arcadian Ruins',x:194,y:419,width:350,height:30}]};
 const p={session:'s',frameId:12,createdAt:1000,reviewed:true,quest:'Mystery of the Arcadian Ruins',action:'select'},r={session:'s',expectedFrameId:12};assert.ok(gate.target(o,1000,p,r));assert.equal(gate.target({...o,ocr:o.ocr.filter(x=>x.text!=='World Quests')},1000,p,r),null);
});
