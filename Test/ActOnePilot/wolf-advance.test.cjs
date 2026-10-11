const test = require('node:test');
const assert = require('node:assert/strict');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const row=(text,x,y)=>({text,x,y,width:80,height:25});
function frame(id=1,patch={}) { return {timestamp:1000+id,frameId:id,map:null,ocr:[row('Kaeya',1660,480),row('Trial',1780,455)],hud:{world:false,groundControls:true,health:{current:1400,max:1400},enemyBars:[],interact:false,dialogueReady:false,choice:false,climbing:false,tutorialStep:null,objectiveChanged:false},...patch}; }
test('Wolf advance safety matcher requires fresh grounded safe trial state',()=>{
 const o=frame();assert.equal(bgi.wolfAdvanceState(o,o.timestamp).ok,true);
 for(const patch of [{timestamp:0},{map:{map:'Teyvat',x:0,y:0}},{hud:{...o.hud,groundControls:false}},{hud:{...o.hud,climbing:true}},{hud:{...o.hud,interact:true}},{hud:{...o.hud,enemyBars:[{}]}},{hud:{...o.hud,dialogueReady:true}},{hud:{...o.hud,choice:true}},{hud:{...o.hud,tutorialStep:'x'}},{hud:{...o.hud,health:null}},{hud:{...o.hud,health:{current:800,max:1400}}}]) assert.equal(bgi.wolfAdvanceState({...o,...patch},o.timestamp).ok,false);
 assert.match(bgi.wolfAdvanceState(frame(2,{hud:{...o.hud,health:{current:1329,max:1400}}}),1002,{current:1400,max:1400}).reason,/5%/);
});
test('wolfAdvance makes at most four individually observed 500ms W moves and reports no destination claim',async()=>{
 let now=1000,moves=0,obs=0;const calls=[];
 const r=await mission.runQuestStep('wolfAdvance',frame(1,{timestamp:1000}),{now:()=>now,checkStop(){},wolfDomainHud:o=>bgi.wolfDomainHud(o,now),wolfDomainAction:async()=>{moves++;calls.push('move');},sleep:async ms=>{now+=ms;calls.push(ms);}},async()=>{obs++;return frame(obs+1,{timestamp:now});});
 assert.equal(r.status,'completed');assert.equal(r.moves,4);assert.equal(r.capReached,true);assert.match(r.reason,/target not verified/);assert.equal(moves,4);assert.equal(obs,4);assert.deepEqual(calls,['move',180,'move',180,'move',180,'move',180]);
});
test('wolfAdvance stops before input on unsafe initial state and during any intermediate observation',async()=>{
 for(const unsafe of [{hud:{...frame().hud,interact:true}},{hud:{...frame().hud,enemyBars:[{}]}},{hud:{...frame().hud,climbing:true}},{hud:{...frame().hud,health:{current:800,max:1400}}}]) {
  let moves=0;const r=await mission.runQuestStep('wolfAdvance',frame(1,unsafe),{now:()=>1001,checkStop(){},wolfDomainHud:o=>bgi.wolfDomainHud(o,1001),wolfDomainAction:async()=>moves++,sleep:async()=>{}},async()=>frame(2));
  assert.equal(r.status,'stopped');assert.equal(moves,0);
 }
 let moves=0,reads=0,now=1001;const start=frame(1);
 const result=await mission.runQuestStep('wolfAdvance',start,{now:()=>now,checkStop(){},wolfDomainHud:o=>bgi.wolfDomainHud(o,now),wolfDomainAction:async()=>moves++,sleep:async ms=>{now+=ms;}},async()=>{reads++;return reads===1?frame(2,{hud:{...start.hud,health:{current:1300,max:1400}}}):frame(reads+1);});
 assert.equal(result.status,'stopped');assert.match(result.reason,/5%/);assert.equal(moves,1);assert.equal(reads,1);
});
