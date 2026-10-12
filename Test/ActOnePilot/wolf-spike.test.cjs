const test=require('node:test');
const assert=require('node:assert/strict');
const spike=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/wolf-spike.js');

function frame(frameId,{session='s1',timestamp=10000+frameId,hp=950,max=1427,body='amber',landing=false,paused=false,
  spikeOff=false,bankWaitReady=false,pauseAllowed=false,iceEvidence=true,existingIce=false,groundControls=true,lip=false}={}) {
  return {session,frameId,timestamp,map:null,hud:{world:false,groundControls,climbing:false,interact:false,dialogueReady:false,
    choice:false,journal:false,bigMap:false,objectiveChanged:false,unknownHud:false,enemyBars:[],health:{current:hp,max}},
    body,landing,paused,spikeOff,bankWaitReady,pauseAllowed,iceEvidence,existingIce,groundControls,lip};
}
function harness({badSessionAt,damageAt,throwCast=false,landingAt=3,staleAt,frameFaultAt,frameFault='backward',cooldownPlan=0,iceResult=true,
  pulseOff=false,neverActive=false,unsafeBank=false,iceSequence,hpDropAt,focusLossAt,existingIce=false,omitExistingIceApi=false,existingHp=950,
  lipReady=false,landingAfterJumpAt=1,crossingPlan={character:'amber',minRatio:0.6,moveMs:500,maxMoves:3},omitCrossingPlanApi=false,
  kaeyaHp=950,kaeyaDamageAt,initialLanding=false,finishReady=false,finishLanding=false,finishStale=false,finishHpLoss=null,
  finishThrow=false,finishDeadlineDelay=0}={}) {
  let now=10020, reads=0, sequence=2, selected='amber', keyReleased=false, stage='initial', moves=0, jumpReads=0, cooldownCalls=0;
  const calls=[], initial=frame(1,{session:'s1',timestamp:10000,hp:950,body:'paused',paused:true});
  const api={now:()=>now,checkStop(){},sleep:async ms=>{calls.push(['sleep',ms]);now+=ms;},
    wolfSpikeContinueReady:o=>o.paused===true,
    wolfSpikeContinue:async()=>{calls.push('continue');stage='continued';},
    wolfSpikeActiveReady:(o,body,minRatio)=>!!(o&&o.hud&&o.hud.groundControls===true&&o.hud.world===false&&
      (!o.spikeOff||o.existingIce===true)&&!o.hud.unknownHud&&!o.hud.interact&&!o.hud.dialogueReady&&!o.hud.choice&&!o.hud.journal&&!o.hud.bigMap&&
      !(o.hud.enemyBars||[]).length&&o.hud.health.current/o.hud.health.max>=minRatio&&
      (body==='any'||o.body===body)),
    wolfSpikeBankWaitReady:o=>o.bankWaitReady===true,
    wolfSpikeExistingIceReady:o=>o.existingIce===true,
    wolfSpikeSelectKaeya:async()=>{calls.push('select-kaeya');selected='kaeya';stage='kaeya';},
    wolfSpikeCooldownPlan:()=>{cooldownCalls++;return cooldownPlan;},
    wolfSpikeCrossingPlan:()=>crossingPlan,
    wolfSpikeCast:async()=>{calls.push('E');stage='cast';if(throwCast){keyReleased=true;throw Error('cast input failed after key release');}},
    wolfSpikeIceReady:o=>o.iceEvidence===true,
    wolfSpikeSelectAmber:async()=>{calls.push('select-amber');selected='amber';stage='amber';},
    wolfSpikeMove:async ms=>{calls.push(['W',ms]);moves++;stage='moving';},
    wolfSpikeFinishReady:o=>{now+=finishDeadlineDelay;return finishReady===true;},
    wolfSpikeFinish:async()=>{calls.push(['finish-w',200]);stage='finishing';if(finishThrow){keyReleased=true;throw Error('finish input failed after key release');}},
    wolfSpikeLipReady:o=>o.lip===true,
    wolfSpikeLandingJump:async()=>{calls.push('jump');stage='jumped';jumpReads=0;},
    wolfSpikeLandingReady:o=>o.landing===true,
    wolfSpikePauseReady:o=>o.paused===true||o.landing===true||o.emergency===true||o.pauseAllowed===true,
    wolfSpikeEscape:async()=>{calls.push('escape');stage='escaped';},
    wolfSpikePauseVerified:o=>o.paused===true};
  if(omitExistingIceApi)delete api.wolfSpikeExistingIceReady;
  if(omitCrossingPlanApi)delete api.wolfSpikeCrossingPlan;
  let continuedReads=0, iceReads=0;
  const observe=async()=>{
    reads++;now+=10;
    const id=sequence++;
    if(staleAt===reads)return frame(id-1,{timestamp:now,body:selected});
    if(badSessionAt===reads)return frame(id,{session:'other',timestamp:now,body:selected});
    if(frameFaultAt===reads) return frame(frameFault==='fractional'?id+0.5:id-2,{timestamp:now,body:selected});
    if(throwCast&&reads===3)return frame(id,{timestamp:now,body:'paused',paused:true,emergency:true});
    if(damageAt===reads)return frame(id,{timestamp:now,body:'amber',hp:890,max:1055});
    if(hpDropAt===reads)return frame(id,{timestamp:now,body:'kaeya',hp:900,max:1427});
    if(focusLossAt===reads)return frame(id,{timestamp:now,body:'kaeya',groundControls:false});
    if(kaeyaDamageAt===reads)return frame(id,{timestamp:now,body:'kaeya',hp:250,max:1427});
    if(stage==='finishing'&&finishStale)return frame(id-1,{timestamp:now,body:'kaeya',hp:kaeyaHp,max:1427});
    if(stage==='finishing'&&finishHpLoss)return frame(id,{timestamp:now,body:'kaeya',hp:finishHpLoss,max:1427});
    if(stage==='continued') {
      continuedReads++;
      if(existingIce)return frame(id,{timestamp:now,body:'kaeya',hp:existingHp,max:1427,spikeOff:true,existingIce:true,landing:initialLanding});
      if(unsafeBank)return frame(id,{timestamp:now,body:'amber',hp:950,spikeOff:true,pauseAllowed:true});
      if(neverActive||pulseOff&&continuedReads===1)
        return frame(id,{timestamp:now,body:'amber',hp:950,spikeOff:true,bankWaitReady:!unsafeBank});
      return frame(id,{timestamp:now,body:'amber',hp:950});
    }
    if(stage==='kaeya')return frame(id,{timestamp:now,body:'kaeya',hp:kaeyaHp,max:1427});
    if(stage==='cast') {
      const iceEvidence=iceSequence?iceSequence[Math.min(iceReads,iceSequence.length-1)]:iceResult;
      iceReads++;
      return frame(id,{timestamp:now,body:'kaeya',hp:kaeyaHp,max:1427,iceEvidence});
    }
    if(stage==='amber')return frame(id,{timestamp:now,body:'amber',hp:950,max:1055});
    if(stage==='moving') {
      const isKaeya=crossingPlan&&crossingPlan.character==='kaeya';
      return frame(id,{timestamp:now,body:isKaeya?'kaeya':'amber',hp:isKaeya?kaeyaHp:950,max:isKaeya?1427:1055,
        landing:moves>=landingAt,lip:lipReady&&moves>=3});
    }
    if(stage==='finishing')return frame(id,{timestamp:now,body:'kaeya',hp:kaeyaHp,max:1427,landing:finishLanding===true});
    if(stage==='jumped') {jumpReads++;return frame(id,{timestamp:now,body:'amber',hp:950,max:1055,landing:jumpReads>=landingAfterJumpAt});}
    if(stage==='escaped')return frame(id,{timestamp:now,body:'paused',paused:true});
    return frame(id,{timestamp:now,body:selected});
  };
  return {initial,api,observe,calls,get reads(){return reads;},get keyReleased(){return keyReleased;},get cooldownCalls(){return cooldownCalls;}};
}

test('runs one bounded first-pit sequence and reports landing and pause only from adapter evidence',async()=>{
  const h=harness(),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');
  assert.deepEqual(h.calls.filter(x=>typeof x==='string'||Array.isArray(x)&&x[0]==='W'),['continue','select-kaeya','E','select-amber',['W',500],['W',500],['W',500],'escape']);
  assert.deepEqual(h.calls.filter(x=>Array.isArray(x)&&x[0]==='sleep').map(x=>x[1]),[450,350,700,350,180,180,180,600]);
  assert.equal(r.continueAttempts,1);assert.equal(r.characterSelectionAttempts,2);assert.equal(r.skillAttempts,1);assert.equal(r.movementAttempts,3);
  assert.equal(r.landingVerified,true);assert.equal(r.pauseVerified,true);assert.equal(r.questProgressVerified,false);assert.equal(r.iceEffectVerified,true);
  assert.equal(r.step,'wolfSpikeCrossFirst');assert.equal(r.frameId,r.lastFrameId);assert.equal(r.questComplete,false);
});

test('stops on a same-session freshness violation before issuing skill or movement',async()=>{
  const h=harness({badSessionAt:2}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.match(r.reason,/same-session/);assert.equal(r.skillAttempts,0);assert.equal(r.movementAttempts,0);
  assert.equal(h.calls.includes('E'),false);assert.equal(r.landingVerified,false);
});

test('stops when Amber loses over five percent and does not move again',async()=>{
  const h=harness({damageAt:5}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.match(r.reason,/5% health/);assert.equal(r.movementAttempts,1);assert.equal(r.landingVerified,false);
});

test('input rejection observes state before safe pause cleanup and preserves the stopped result',async()=>{
  const h=harness({throwCast:true}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.match(r.reason,/cast input failed/);assert.equal(h.keyReleased,true);
  assert.equal(h.calls.includes('escape'),true);assert.equal(r.pauseVerified,true);assert.equal(r.skillAttempts,1);assert.equal(r.movementAttempts,0);
});

test('rejects stale frames without attempting to continue',async()=>{
  const h=harness({staleAt:1}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.equal(r.continueAttempts,1);assert.equal(r.characterSelectionAttempts,0);assert.equal(r.skillAttempts,0);
});

test('rejects backward and noninteger frame IDs after continue',async()=>{
  for(const frameFault of ['backward','fractional']) {
    const h=harness({frameFaultAt:2,frameFault}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
    assert.equal(r.status,'stopped',frameFault);assert.equal(r.skillAttempts,0,frameFault);assert.equal(r.movementAttempts,0,frameFault);
  }
});

test('requires positive ice evidence before Amber selection or movement',async()=>{
  const h=harness({iceResult:false}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.match(r.reason,/Positive first-spike ice evidence/);
  assert.equal(r.characterSelectionAttempts,1);assert.equal(r.movementAttempts,0);assert.equal(r.landingVerified,false);
});

test('uses a single bounded cooldown deadline for absent and constant 6500ms adapter plans',async()=>{
  for(const cooldownPlan of [null,6500]) {
    const h=harness({cooldownPlan}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
    assert.equal(r.cooldownSource,cooldownPlan===null?'6500ms-fallback':'adapter');assert.equal(r.cooldownWaitMs,6500);
    assert.equal(r.status,'stopped');assert.equal(r.skillAttempts,1);assert.equal(h.cooldownCalls,1);
    const select=h.calls.indexOf('select-kaeya'),cast=h.calls.indexOf('E');
    assert.equal(h.calls.slice(select+1,cast).filter(x=>Array.isArray(x)&&x[0]==='sleep').reduce((n,x)=>n+x[1],0),6790);
  }
});

test('reacquires a pulsing first bank read-only before selecting Kaeya',async()=>{
  const h=harness({pulseOff:true}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.equal(r.bankObserveRetries,1);
  assert.equal(h.calls.filter(x=>typeof x==='string').filter(x=>x==='continue').length,1);
  assert.equal(h.calls.indexOf('select-kaeya')>h.calls.indexOf('continue'),true);
  assert.equal(r.skillAttempts,1);assert.equal(r.movementAttempts,3);
  assert.equal(r.bankObserveRetries,1);
});

test('never-positive or unsafe-floor bank reacquisition stops before selection and allows only verified safe cleanup',async()=>{
  const h=harness({unsafeBank:true}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.match(r.reason,/unsafe or ambiguous/);
  assert.equal(r.bankObserveRetries,0);assert.equal(r.characterSelectionAttempts,0);assert.equal(r.skillAttempts,0);assert.equal(r.movementAttempts,0);
  assert.equal(r.pauseVerified,true);assert.equal(h.calls.includes('select-kaeya'),false);
});

test('caps positive provisional bank polling at eight frames without selecting',async()=>{
  const h=harness({neverActive:true}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.match(r.reason,/did not reach the active Wolf HUD/);
  assert.equal(r.bankObserveRetries,8);assert.equal(r.characterSelectionAttempts,0);assert.equal(r.skillAttempts,0);assert.equal(r.movementAttempts,0);
  assert.equal(h.calls.includes('select-kaeya'),false);assert.equal(h.calls.includes('E'),false);
  assert.equal(h.calls.filter(x=>Array.isArray(x)&&x[0]==='sleep').filter(x=>x[1]===500).length,8);
});

test('waits for partial post-E ice evidence to become fully positive before Amber or movement',async()=>{
  const h=harness({iceSequence:[false,true]}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.equal(r.iceObserveRetries,1);assert.equal(r.iceEffectVerified,true);
  assert.equal(r.characterSelectionAttempts,2);assert.equal(r.movementAttempts,3);
  const cast=h.calls.indexOf('E'),amber=h.calls.indexOf('select-amber');
  assert.equal(h.calls.slice(cast+1,amber).some(x=>Array.isArray(x)&&x[0]==='sleep'&&x[1]===100),true);
});

test('never-positive post-E ice stops after three read-only retries without Amber or movement',async()=>{
  const h=harness({iceSequence:[false]}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.match(r.reason,/Positive first-spike ice evidence/);
  assert.equal(r.iceObserveRetries,3);assert.equal(r.iceEffectVerified,false);
  assert.equal(h.calls.includes('select-amber'),false);assert.equal(r.movementAttempts,0);
});

test('health or strict HUD loss during ice polling stops before Amber or movement',async()=>{
  for(const opts of [{hpDropAt:4},{focusLossAt:4}]) {
    const h=harness({...opts,iceSequence:[false,true]}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
    assert.equal(r.status,'stopped');assert.equal(r.characterSelectionAttempts,1);assert.equal(r.movementAttempts,0);
    assert.equal(h.calls.includes('select-amber'),false);assert.equal(r.landingVerified,false);
  }
});

test('reuses a fresh already-verified ice bridge without Kaeya select, cooldown or E',async()=>{
  const h=harness({existingIce:true}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.equal(r.existingIceReused,true);assert.equal(r.iceEffectVerified,true);
  assert.equal(r.continueAttempts,1);assert.equal(r.characterSelectionAttempts,1);assert.equal(r.skillAttempts,0);
  assert.equal(r.movementAttempts,3);assert.equal(r.landingVerified,true);
  assert.equal(h.calls.includes('select-kaeya'),false);assert.equal(h.calls.includes('E'),false);assert.equal(h.cooldownCalls,0);
});

test('missing existing-ice API keeps the normal Kaeya skill path',async()=>{
  const h=harness({omitExistingIceApi:true}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.existingIceReused,false);assert.equal(r.skillAttempts,1);assert.equal(r.movementAttempts,3);
  assert.equal(h.calls.includes('select-kaeya'),true);assert.equal(h.calls.includes('E'),true);
});

test('false existing-ice proof cannot bypass bank reacquisition, and fresh or HP loss still stops',async()=>{
  const unsafe=harness({unsafeBank:true,existingIce:false}),stopped=await spike.runWolfSpike(unsafe.initial,unsafe.api,unsafe.observe);
  assert.equal(stopped.status,'stopped');assert.equal(stopped.existingIceReused,false);assert.equal(stopped.characterSelectionAttempts,0);
  assert.equal(stopped.skillAttempts,0);assert.equal(unsafe.calls.includes('select-kaeya'),false);

  for(const opts of [{badSessionAt:1},{existingIce:true,existingHp:0}]) {
    const h=harness(opts),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
    assert.equal(r.status,'stopped');assert.equal(r.characterSelectionAttempts,0);assert.equal(r.skillAttempts,0);assert.equal(r.movementAttempts,0);
    assert.equal(h.calls.includes('select-amber'),false);
  }
});

test('checks the lip after three W inputs and uses exactly one bounded landing jump',async()=>{
  const h=harness({landingAt:99,lipReady:true,landingAfterJumpAt:2}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.equal(r.movementAttempts,3);assert.equal(r.jumpAttempts,1);
  assert.equal(r.landingObserveRetries,1);assert.equal(r.landingVerified,true);assert.equal(r.pauseVerified,true);
  const jump=h.calls.indexOf('jump');assert.notEqual(jump,-1);
  assert.equal(h.calls.slice(0,jump).filter(x=>Array.isArray(x)&&x[0]==='W').length,3);
  assert.equal(h.calls.slice(jump+1).some(x=>Array.isArray(x)&&x[0]==='W'),false);
  assert.deepEqual(h.calls.filter(x=>Array.isArray(x)&&x[0]==='sleep').slice(-4).map(x=>x[1]),[180,300,100,600]);
});

test('does not send a fourth blind W when the lip is unproven, and never repeats the jump',async()=>{
  const noLip=harness({landingAt:99,lipReady:false}),stopped=await spike.runWolfSpike(noLip.initial,noLip.api,noLip.observe);
  assert.equal(stopped.movementAttempts,3);assert.equal(stopped.jumpAttempts,0);assert.equal(stopped.landingVerified,false);
  assert.equal(noLip.calls.filter(x=>Array.isArray(x)&&x[0]==='W').length,3);

  const noLanding=harness({landingAt:99,lipReady:true,landingAfterJumpAt:99}),afterJump=await spike.runWolfSpike(noLanding.initial,noLanding.api,noLanding.observe);
  assert.equal(afterJump.jumpAttempts,1);assert.equal(afterJump.movementAttempts,3);assert.equal(afterJump.landingObserveRetries,2);
  assert.equal(afterJump.landingVerified,false);assert.equal(noLanding.calls.filter(x=>Array.isArray(x)&&x[0]==='W').length,3);
  assert.equal(noLanding.calls.filter(x=>x==='jump').length,1);
});

test('uses only the explicitly authorized two-W Kaeya crossing plan at 329 HP',async()=>{
  const kaeyaPlan={character:'kaeya',minRatio:0.01,moveMs:800,maxMoves:2};
  const h=harness({crossingPlan:kaeyaPlan,kaeyaHp:329,landingAt:2}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.equal(r.crossingCharacter,'kaeya');
  assert.deepEqual(r.crossingHealth,{current:329,max:1427});assert.equal(r.skillAttempts,1);
  assert.equal(r.movementAttempts,2);assert.equal(r.landingVerified,true);
  assert.deepEqual(h.calls.filter(x=>Array.isArray(x)&&x[0]==='W'),[['W',800],['W',800]]);
  assert.equal(h.calls.includes('select-amber'),false);assert.equal(h.calls.includes('jump'),false);
});

test('finishes the approved two-W Kaeya route with one native-verified W200 lip action',async()=>{
  const kaeyaPlan={character:'kaeya',minRatio:0.01,moveMs:800,maxMoves:2};
  const h=harness({crossingPlan:kaeyaPlan,existingIce:true,existingHp:329,kaeyaHp:329,landingAt:99,finishReady:true,finishLanding:true}),
    r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.equal(r.crossingCharacter,'kaeya');
  assert.equal(r.finishAttempts,1);assert.equal(r.movementAttempts,3);assert.equal(r.landingVerified,true);assert.equal(r.pauseVerified,true);
  assert.deepEqual(h.calls.filter(x=>Array.isArray(x)&&['W','finish-w'].includes(x[0])),[['W',800],['W',800],['finish-w',200]]);
  assert.equal(h.calls.includes('select-amber'),false);assert.equal(h.calls.includes('jump'),false);
  assert.equal(h.calls.indexOf('escape')>h.calls.indexOf('finish-w'),true);
});

test('does not add a Kaeya finish action without exact native lip permission or the companion API',async()=>{
  const kaeyaPlan={character:'kaeya',minRatio:0.01,moveMs:800,maxMoves:2};
  const noPermit=harness({crossingPlan:kaeyaPlan,existingIce:true,existingHp:329,kaeyaHp:329,landingAt:99,finishReady:false});
  const stopped=await spike.runWolfSpike(noPermit.initial,noPermit.api,noPermit.observe);
  assert.equal(stopped.finishAttempts,0);assert.equal(stopped.movementAttempts,2);assert.equal(stopped.landingVerified,false);
  assert.equal(noPermit.calls.some(x=>Array.isArray(x)&&x[0]==='finish-w'),false);
  const noApi=harness({crossingPlan:kaeyaPlan,existingIce:true,existingHp:329,kaeyaHp:329,landingAt:99});
  delete noApi.api.wolfSpikeFinishReady;
  const legacy=await spike.runWolfSpike(noApi.initial,noApi.api,noApi.observe);
  assert.equal(legacy.finishAttempts,0);assert.equal(legacy.movementAttempts,2);
  assert.equal(noApi.calls.some(x=>Array.isArray(x)&&x[0]==='finish-w'),false);
});

test('finish move respects the post-skill deadline and requires a fresh distinct frame and safe HP',async()=>{
  const kaeyaPlan={character:'kaeya',minRatio:0.01,moveMs:800,maxMoves:2};
  const deadline=harness({crossingPlan:kaeyaPlan,existingIce:true,existingHp:329,kaeyaHp:329,landingAt:99,finishReady:true,finishDeadlineDelay:11000});
  const timed=await spike.runWolfSpike(deadline.initial,deadline.api,deadline.observe);
  assert.match(timed.reason,/10-second post-skill deadline/);assert.equal(timed.finishAttempts,0);
  assert.equal(deadline.calls.some(x=>Array.isArray(x)&&x[0]==='finish-w'),false);

  const stale=harness({crossingPlan:kaeyaPlan,existingIce:true,existingHp:329,kaeyaHp:329,landingAt:99,finishReady:true,finishStale:true});
  const staleResult=await spike.runWolfSpike(stale.initial,stale.api,stale.observe);
  assert.match(staleResult.reason,/Fresh distinct same-session/);assert.equal(staleResult.finishAttempts,1);assert.equal(staleResult.landingVerified,false);

  const damaged=harness({crossingPlan:kaeyaPlan,existingIce:true,existingHp:329,kaeyaHp:329,landingAt:99,finishReady:true,finishLanding:true,finishHpLoss:250});
  const hurt=await spike.runWolfSpike(damaged.initial,damaged.api,damaged.observe);
  assert.match(hurt.reason,/5% health/);assert.equal(hurt.finishAttempts,1);assert.equal(hurt.landingVerified,false);
});

test('finish input exception observes the frame before verified pause cleanup',async()=>{
  const kaeyaPlan={character:'kaeya',minRatio:0.01,moveMs:800,maxMoves:2};
  const h=harness({crossingPlan:kaeyaPlan,existingIce:true,existingHp:329,kaeyaHp:329,landingAt:99,finishReady:true,finishThrow:true,finishLanding:true}),
    r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.match(r.reason,/finish input failed after key release/);assert.equal(h.keyReleased,true);
  assert.equal(r.finishAttempts,1);assert.equal(r.movementAttempts,3);assert.equal(r.pauseVerified,true);
  assert.equal(h.calls.indexOf('escape')>h.calls.indexOf('finish-w'),true);
  assert.equal(r.observeCount>=5,true);
});

test('stops the authorized Kaeya route when 329 HP loses more than five percent',async()=>{
  const kaeyaPlan={character:'kaeya',minRatio:0.01,moveMs:800,maxMoves:2};
  const h=harness({crossingPlan:kaeyaPlan,kaeyaHp:329,kaeyaDamageAt:4,landingAt:2}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.match(r.reason,/kaeya lost more than 5%/);
  assert.equal(r.crossingCharacter,'kaeya');assert.equal(r.movementAttempts,1);assert.equal(r.landingVerified,false);
  assert.deepEqual(h.calls.filter(x=>Array.isArray(x)&&x[0]==='W'),[['W',800]]);
  assert.equal(h.calls.includes('select-amber'),false);assert.equal(h.calls.includes('jump'),false);
});

test('missing crossing plan retains the bounded Amber route',async()=>{
  const h=harness({omitCrossingPlanApi:true}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.crossingCharacter,'amber');assert.equal(r.movementAttempts,3);
  assert.deepEqual(h.calls.filter(x=>Array.isArray(x)&&x[0]==='W'),[['W',500],['W',500],['W',500]]);
});

test('uses only the exact parent-permitted one-W200 Kaeya landing continuation',async()=>{
  const continuation={character:'kaeya',minRatio:0.01,moveMs:200,maxMoves:1,landingContinuation:true};
  const h=harness({crossingPlan:continuation,existingIce:true,existingHp:43,kaeyaHp:43,landingAt:1}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.equal(r.landingContinuation,true);assert.equal(r.existingIceReused,true);
  assert.equal(r.crossingCharacter,'kaeya');assert.deepEqual(r.crossingHealth,{current:43,max:1427});
  assert.equal(r.skillAttempts,0);assert.equal(r.characterSelectionAttempts,0);assert.equal(r.movementAttempts,1);assert.equal(r.jumpAttempts,0);
  assert.deepEqual(h.calls.filter(x=>typeof x==='string'||Array.isArray(x)&&x[0]==='W'),['continue',['W',200],'escape']);
  assert.equal(r.landingVerified,true);
});

test('rejects malformed or unflagged 200ms plans and never issues a continuation move',async()=>{
  const plans=[
    {character:'kaeya',minRatio:0.01,moveMs:200,maxMoves:1,landingContinuation:false},
    {character:'kaeya',minRatio:0.01,moveMs:200,maxMoves:2,landingContinuation:true},
    {character:'kaeya',minRatio:0.01,moveMs:200,maxMoves:1,landingContinuation:true}
  ];
  for(let i=0;i<plans.length;i++) {
    const h=harness({crossingPlan:plans[i],existingIce:i<2}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
    assert.equal(r.status,'stopped');assert.match(r.reason,/Crossing plan was not an approved/);
    assert.equal(r.movementAttempts,0);assert.equal(r.jumpAttempts,0);
    assert.equal(h.calls.some(x=>Array.isArray(x)&&x[0]==='W'),false);
  }
});

test('skips the continuation W when the fresh native parent-receipt frame already verifies landing',async()=>{
  const continuation={character:'kaeya',minRatio:0.01,moveMs:200,maxMoves:1,landingContinuation:true};
  const h=harness({crossingPlan:continuation,existingIce:true,existingHp:43,kaeyaHp:43,initialLanding:true}),r=await spike.runWolfSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.equal(r.landingContinuation,true);assert.equal(r.landingVerified,true);
  assert.equal(r.movementAttempts,0);assert.equal(r.jumpAttempts,0);assert.equal(r.pauseVerified,true);
  assert.deepEqual(h.calls.filter(x=>typeof x==='string'||Array.isArray(x)&&x[0]==='W'),['continue','escape']);
});
