const test = require('node:test');
const assert = require('node:assert/strict');
const combat = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/combat.js');

function frame({health=1000, width=100, bars=true, ui={}, frameId=1}={}) {
  return {timestamp:1000,frameId,map:null,ocr:[
    {text:'Kaeya',x:1664,y:487},{text:'Trial',x:1796,y:463},
  ],hud:{world:false,groundControls:true,climbing:false,journal:false,bigMap:false,
    dialogueReady:false,choice:false,tutorialStep:null,health:{current:health,max:1000},
    enemyBars:bars?[{x:960,y:500,width,height:8}]:[],...ui}};
}
function harness(observations) {
  let clock=1000,index=0;
  const keys=[],events=[];
  const api={now:()=>clock, sleep:async ms=>{clock+=ms;},checkStop:()=>{},
    wolfCombatKey:async key=>{keys.push(key);events.push(['key',key,clock]);},
    wolfPauseCombat:async()=>{events.push(['pause']);}};
  const observe=async()=>{
    const item=observations[Math.min(index++,observations.length-1)];
    events.push(['observe',index]); return {...item,timestamp:clock};
  };
  return {api,observe,keys,events};
}
const paused=()=>frame({bars:false,frameId:90,ui:{}});

test('uses VK_E once and observes before every attack while respecting its cooldown',async()=>{
  const h=harness([frame(),frame(),frame(),frame({width:95}),frame({width:90}),frame({width:85}),frame({width:80}),frame({width:75}),frame({width:70}),frame({width:65}),paused(),paused(),paused(),{...paused(),ocr:[{text:'Continue Challenge'},{text:'Leave Domain?'}]}]);
  const result=await combat.runWolf(frame(),h.api,h.observe);
  assert.equal(h.keys[0],'VK_3');
  assert.equal(h.keys.filter(k=>k==='VK_E').length,1);
  assert.ok(h.keys.filter(k=>k==='VK_LBUTTON').length>=2);
  const clickTimes=h.events.filter(e=>e[0]==='key'&&e[1]==='VK_LBUTTON').map(e=>e[2]);
  assert.ok(clickTimes.length>=2);
  for(let i=1;i<clickTimes.length;i++)assert.ok(clickTimes[i]-clickTimes[i-1]>=250);
  assert.equal(result.status,'stopped');
  assert.equal(result.combatComplete,false);
});

test('requires an observed enemy bar before attacking and stops after two missing-bar observations',async()=>{
  const h=harness([frame(),frame({bars:false}),frame({bars:false}),paused(),{...paused(),ocr:[{text:'Continue Challenge'},{text:'Leave Domain?'}]}]);
  const result=await combat.runWolf(frame(),h.api,h.observe);
  assert.deepEqual(h.keys,['VK_3']);
  assert.match(result.reason,/two successive observations/);
});

test('does not select Kaeya when the initial frame has no enemy bar and handles missing API safely',async()=>{
  const h=harness([frame({bars:false})]);
  const result=await combat.runWolf(frame({bars:false}),h.api,h.observe);
  assert.equal(result.status,'stopped');
  assert.deepEqual(h.keys,[]);
  assert.match(result.reason,/before character selection/);
  const unavailable=await combat.runWolf(null,{},async()=>null);
  assert.match(unavailable.reason,/API unavailable/);
  assert.equal(unavailable.elapsedMs,0);
});

test('stops on health loss over twenty percent and verifies pause from fresh exact menu labels',async()=>{
  const h=harness([frame(),frame(),frame(),frame({health:700}),frame({health:400}),{...paused(),ocr:[{text:'Continue Challenge'},{text:'Leave Domain?'}]}]);
  const result=await combat.runWolf(frame(),h.api,h.observe);
  assert.match(result.reason,/dropped more than 20%/);
  assert.equal(result.pauseVerified,true);
  assert.deepEqual(h.keys,['VK_3','VK_E']);
});

test('stops after six attacks without bar-width progress',async()=>{
  const h=harness([frame(),frame(),frame(),...Array.from({length:20},()=>frame()),paused(),{...paused(),ocr:[{text:'Continue Challenge'},{text:'Leave Domain?'}]}]);
  const result=await combat.runWolf(frame(),h.api,h.observe);
  assert.match(result.reason,/no damage progress across six attacks/);
  assert.equal(h.keys.filter(k=>k==='VK_LBUTTON').length,6);
});

test('stops immediately when the no-UI domain state changes',async()=>{
  const invalid=frame({ui:{dialogueReady:true}});
  const h=harness([frame(),invalid,paused(),{...paused(),ocr:[{text:'Continue Challenge'},{text:'Leave Domain?'}]}]);
  const result=await combat.runWolf(frame(),h.api,h.observe);
  assert.match(result.reason,/state changed/);
  assert.deepEqual(h.keys,['VK_3']);
});
