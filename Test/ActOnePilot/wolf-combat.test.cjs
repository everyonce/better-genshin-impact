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
function harness(observations,{onObserve,transformObservation}={}) {
  let clock=1000,index=0;
  const keys=[],events=[];
  const api={now:()=>clock, sleep:async ms=>{clock+=ms;},checkStop:()=>{},
    wolfCombatKey:async key=>{keys.push(key);events.push(['key',key,clock]);},
    wolfPauseCombat:async()=>{events.push(['pause']);}};
  const observe=async()=>{
    const item=observations[Math.min(index++,observations.length-1)];
    if(onObserve)onObserve(index,ms=>{clock+=ms;});
    const observed={...item,timestamp:clock};
    if(transformObservation)transformObservation(index,observed,()=>clock);
    events.push(['observe',index]); return observed;
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

test('requires an observed enemy bar before attacking and stops after bounded reacquisition fails',async()=>{
  const absent=frame({bars:false});
  const h=harness([frame(),absent,...Array(16).fill(absent),paused(),{...paused(),ocr:[{text:'Continue Challenge'},{text:'Leave Domain?'}]}]);
  const result=await combat.runWolf(frame(),h.api,h.observe);
  assert.deepEqual(h.keys,['VK_3']);
  assert.match(result.reason,/bounded reacquisition window/);
  assert.ok(result.elapsedMs>=4000);
  assert.equal(result.pauseVerified,true,JSON.stringify(h.events));
});

test('resumes attacks only after enemy bars return during the no-input reacquisition window',async()=>{
  const absent=frame({bars:false});
  const h=harness([frame(),frame(),absent,absent,frame(),absent,...Array(17).fill(absent),paused(),{...paused(),ocr:[{text:'Continue Challenge'},{text:'Leave Domain?'}]}]);
  const result=await combat.runWolf(frame(),h.api,h.observe);
  assert.deepEqual(h.keys.slice(0,3),['VK_3','VK_E','VK_LBUTTON']);
  const returnedBars=h.events.findIndex(e=>e[0]==='observe'&&e[1]===5);
  const resumedAttack=h.events.findIndex(e=>e[0]==='key'&&e[1]==='VK_LBUTTON');
  assert.ok(resumedAttack>returnedBars,'no attack is sent until a fresh bar observation returns');
  assert.match(result.reason,/bounded reacquisition window/);
  assert.equal(result.pauseVerified,true,JSON.stringify(h.events));
});

test('health loss during reacquisition stops combat immediately and pauses safely',async()=>{
  const absent=frame({bars:false});
  const h=harness([frame(),frame(),absent,absent,frame({bars:false,health:700}),paused(),{...paused(),ocr:[{text:'Continue Challenge'},{text:'Leave Domain?'}]}]);
  const result=await combat.runWolf(frame(),h.api,h.observe);
  assert.match(result.reason,/dropped more than 20%/);
  assert.deepEqual(h.keys,['VK_3','VK_E']);
  assert.equal(result.pauseVerified,true);
});

test('reacquisition wait cannot extend the twenty-second combat deadline',async()=>{
  const absent=frame({bars:false});
  const h=harness([frame(),frame(),absent,absent,absent,paused(),{...paused(),ocr:[{text:'Continue Challenge'},{text:'Leave Domain?'}]}],{
    onObserve:(index,advance)=>{if(index===3)advance(18750);}
  });
  const result=await combat.runWolf(frame(),h.api,h.observe);
  assert.match(result.reason,/time limit reached/);
  assert.deepEqual(h.keys,['VK_3','VK_E']);
  assert.ok(result.elapsedMs<21000,'only the safety pause may add time after the combat deadline');
});

test('does not attack when the reacquisition observation returns bars after the total deadline',async()=>{
  const absent=frame({bars:false});
  const h=harness([frame(),frame(),absent,absent,frame(),paused(),{...paused(),ocr:[{text:'Continue Challenge'},{text:'Leave Domain?'}]}],{
    onObserve:(index,advance)=>{if(index===5)advance(20000);}
  });
  const result=await combat.runWolf(frame(),h.api,h.observe);
  assert.match(result.reason,/time limit reached/);
  assert.deepEqual(h.keys,['VK_3','VK_E']);
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

test('retries one transient missing Kaeya HUD read without input and requires fresh exact party evidence',async()=>{
  const missing=frame({width:95});
  missing.ocr=[{text:'Trial',x:1796,y:463}];
  const h=harness([frame(),frame(),frame(),missing,frame({width:95}),frame({width:95}),
    ...Array.from({length:12},()=>frame({width:95})),paused(),{...paused(),ocr:[{text:'Continue Challenge'},{text:'Leave Domain?'}]}]);
  const result=await combat.runWolf(frame(),h.api,h.observe);
  const missingRead=h.events.findIndex(e=>e[0]==='observe'&&e[1]===4);
  const restoredRead=h.events.findIndex(e=>e[0]==='observe'&&e[1]===5);
  const nextInput=h.events.findIndex((e,i)=>i>missingRead&&e[0]==='key'&&e[1]!=='VK_3');
  assert.ok(restoredRead>missingRead);
  assert.ok(nextInput>restoredRead,'no combat input occurs until fresh Kaeya and Trial evidence returns');
  assert.match(result.reason,/no damage progress|action limit/);
});

test('caps transient missing-party retries at two observations before stopping',async()=>{
  const missing=frame();missing.ocr=[{text:'Trial',x:1796,y:463}];
  const h=harness([frame(),frame(),frame(),missing]);
  const result=await combat.runWolf(frame(),h.api,h.observe);
  assert.deepEqual(h.keys,['VK_3','VK_E']);
  assert.equal(h.events.filter(e=>e[0]==='observe').length,7,'selection, combat reads, two retries, then one guarded stop read');
  assert.match(result.reason,/Trial Kaeya HUD evidence unavailable/);
});

test('does not retry missing-party evidence when health, freshness, or scene safety fails',async t=>{
  const cases=[
    {name:'health is exactly 60%',health:600},
    {name:'baseline health loss exceeds 20%',health:790},
    {name:'timestamp is stale',stale:true},
    {name:'menu text is present',ocr:[{text:'Trial',x:1796,y:463},{text:'Party Setup'}]},
    {name:'loading is present',ui:{loading:true}},
    {name:'HUD is unknown',ui:{unknownHud:true}},
    {name:'objective changed',ui:{objectiveChanged:true}},
    {name:'dialogue is present',ui:{dialogueReady:true}},
    {name:'tutorial is present',ui:{tutorialStep:'tutorial'}}
  ];
  for(const scenario of cases) await t.test(scenario.name,async()=>{
    const missing=frame({health:scenario.health??1000,ui:scenario.ui||{}});
    missing.ocr=scenario.ocr||[{text:'Trial',x:1796,y:463}];
    const h=harness([frame(),frame(),frame(),missing],{
      transformObservation:(index,observation)=>{if(index===4&&scenario.stale)observation.timestamp-=1001;}
    });
    const result=await combat.runWolf(frame(),h.api,h.observe);
    assert.deepEqual(h.keys,['VK_3','VK_E']);
    assert.equal(h.events.filter(e=>e[0]==='observe').length,5,'unsafe evidence gets no retry; only the guarded stop read follows');
    assert.equal(result.status,'stopped');
  });
});

test('does not send combat input when a retry restores party evidence after the 20-second deadline',async()=>{
  const missing=frame();missing.ocr=[{text:'Trial',x:1796,y:463}];
  const h=harness([frame(),frame(),frame(),missing,frame()],{
    onObserve:(index,advance)=>{if(index===5)advance(20000);}
  });
  const result=await combat.runWolf(frame(),h.api,h.observe);
  assert.deepEqual(h.keys,['VK_3','VK_E']);
  assert.match(result.reason,/time limit reached/);
  assert.equal(result.combatComplete,false);
});

test('reacquires a transiently missing initial enemy bar before character selection',async()=>{
  const absent=frame({bars:false});
  const h=harness([frame(),frame(),...Array.from({length:16},()=>frame()),paused(),
    {...paused(),ocr:[{text:'Continue Challenge'},{text:'Leave Domain?'}]}]);
  const result=await combat.runWolf(absent,h.api,h.observe);
  const firstObservation=h.events.findIndex(e=>e[0]==='observe');
  const selection=h.events.findIndex(e=>e[0]==='key'&&e[1]==='VK_3');
  assert.ok(selection>firstObservation,'the fresh valid enemy bar is observed before selecting Kaeya');
  assert.equal(h.keys[0],'VK_3');
  assert.notEqual(result.reason,'Wolf enemy bar evidence unavailable before character selection');
});

test('stops without input after two initial enemy-bar polls fail',async()=>{
  const absent=frame({bars:false});
  const h=harness([absent,absent,absent,{...paused(),ocr:[{text:'Continue Challenge'},{text:'Leave Domain?'}]}]);
  const result=await combat.runWolf(absent,h.api,h.observe);
  assert.deepEqual(h.keys,[]);
  assert.equal(h.events.filter(e=>e[0]==='observe').length,4,'two initial polls and one guarded pause read');
  assert.match(result.reason,/enemy bar evidence unavailable before character selection/);
  assert.equal(result.pauseVerified,true);
});

test('stops initial enemy reacquisition when the HUD changes',async()=>{
  const changed=frame({bars:false,ui:{dialogueReady:true}});
  const h=harness([changed,paused(),{...paused(),ocr:[{text:'Continue Challenge'},{text:'Leave Domain?'}]}]);
  const result=await combat.runWolf(frame({bars:false}),h.api,h.observe);
  assert.deepEqual(h.keys,[]);
  assert.match(result.reason,/state changed/);
});

test('does not select or attack when the initial enemy bar returns after the 20-second deadline',async()=>{
  const h=harness([frame()],{onObserve:(index,advance)=>{if(index===1)advance(20000);}});
  const result=await combat.runWolf(frame({bars:false}),h.api,h.observe);
  assert.deepEqual(h.keys,[]);
  assert.match(result.reason,/time limit reached/);
  assert.equal(result.combatComplete,false);
});
