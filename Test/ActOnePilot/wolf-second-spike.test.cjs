const test=require('node:test');
const assert=require('node:assert/strict');
const route=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/wolf-second-spike.js');

function frame(id,now,opts={}) {
  return {session:opts.session||'s1',frameId:id,timestamp:now,body:opts.body||'amber',
    safe:opts.safe!==false,aligned:opts.aligned===true,ice:opts.ice===true,floor:opts.floor===true,
    canPause:opts.canPause===true,paused:opts.paused===true,
    hud:{world:false,groundControls:opts.safe!==false,health:{current:opts.hp===undefined?950:opts.hp,max:opts.max||1055}}};
}
function harness({aligned=true,alignAfter=0,iceSequence=[true],floorAt=2,kaeyaHp=900,amberHp=739,
  cooldown=0,faultStage=null,faultAt=1,fault='stale',extraDelayAt=0,extraDelay=0,crossingCharacter}={}) {
  let now=10000,id=1,stage='initial',moves=0,alignChecks=0,iceReads=0,stageReads=0,sleepCalls=0;
  const calls=[],initial=frame(id,now,{body:'paused',paused:true,hp:amberHp,max:1055});
  const api={now:()=>now,checkStop(){},sleep:async ms=>{calls.push(['sleep',ms]);sleepCalls++;now+=ms;if(sleepCalls===extraDelayAt)now+=extraDelay;},
    ...(crossingCharacter===undefined?{}:{wolfSecondCrossingCharacter:()=>crossingCharacter}),
    wolfSecondContinueReady:o=>o.paused===true,
    wolfSecondContinue:async()=>{calls.push('continue');stage='continued';stageReads=0;},
    wolfSecondActiveReady:(o,body,min)=>!!(o&&o.safe&&o.hud.health.current/o.hud.health.max>=min&&(body==='any'||o.body===body)),
    wolfSecondSelectKaeya:async()=>{calls.push('select-kaeya');stage='kaeya';stageReads=0;},
    wolfSecondCooldownPlan:()=>cooldown,
    wolfSecondAlignedReady:o=>{alignChecks++;return aligned&&alignChecks>alignAfter&&o.aligned===true;},
    wolfSecondCast:async()=>{calls.push('E');stage='cast';stageReads=0;},
    wolfSecondIceReady:o=>o.ice===true,
    wolfSecondSelectAmber:async()=>{calls.push('select-amber');stage='amber';stageReads=0;},
    wolfSecondMove:async()=>{calls.push(['W',600]);moves++;stage='moving';stageReads=0;},
    wolfSecondFloorReached:o=>o.floor===true,
    wolfSecondPauseReady:o=>o.canPause===true,
    wolfSecondEscape:async()=>{calls.push('escape');stage='escaped';stageReads=0;},
    wolfSecondPauseVerified:o=>o.paused===true};
  async function observe(){
    now+=5;id++;stageReads++;
    let o;
    if(stage==='initial')o=frame(id,now,{body:'paused',paused:true,hp:amberHp,max:1055});
    else if(stage==='continued')o=frame(id,now,{body:'amber',hp:amberHp,max:1055,canPause:true});
    else if(stage==='kaeya')o=frame(id,now,{body:'kaeya',hp:kaeyaHp,max:1427,aligned:aligned&&alignChecks>alignAfter,canPause:true});
    else if(stage==='cast'){
      const ice=iceSequence[Math.min(iceReads,iceSequence.length-1)];iceReads++;
      o=frame(id,now,{body:'kaeya',hp:kaeyaHp,max:1427,ice,aligned:true,canPause:true});
    } else if(stage==='amber')o=frame(id,now,{body:'amber',hp:amberHp,max:1055,canPause:true});
    else if(stage==='moving')o=frame(id,now,{body:crossingCharacter==='kaeya'?'kaeya':'amber',hp:crossingCharacter==='kaeya'?kaeyaHp:amberHp,max:crossingCharacter==='kaeya'?1427:1055,floor:moves>=floorAt,canPause:true});
    else if(stage==='escaped')o=frame(id,now,{body:'paused',paused:true,hp:amberHp,max:1055});
    if(faultStage===stage&&stageReads===faultAt){
      if(fault==='stale')o.frameId=id-1;
      if(fault==='session')o.session='other';
      if(fault==='focus')o.safe=false;
      if(fault==='health')o.hud.health.current=Math.max(1,o.hud.health.current-100);
    }
    return o;
  }
  return {initial,api,observe,calls,get alignChecks(){return alignChecks;}};
}

test('attempts the bounded second-pit sequence and stops on native floor evidence without completion claim',async()=>{
  const h=harness({floorAt:2}),r=await route.runWolfSecondSpike(h.initial,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.equal(r.step,'wolfSpikeCrossSecond');
  assert.equal(r.continueAttempts,1);assert.equal(r.characterSelectionAttempts,2);assert.equal(r.skillAttempts,1);
  assert.equal(r.movementAttempts,2);assert.equal(r.solidFloorReached,true);assert.equal(r.iceEffectVerified,true);
  assert.equal(r.secondPitComplete,false);assert.equal(r.questComplete,false);assert.equal(r.pauseVerified,true);
  assert.deepEqual(h.calls.filter(x=>typeof x==='string'||Array.isArray(x)&&x[0]==='W'),
    ['continue','select-kaeya','E','select-amber',['W',600],['W',600],'escape']);
});

test('alignment timeout is read-only and stops before skill, Amber, or movement',async()=>{
  const h=harness({aligned:false}),r=await route.runWolfSecondSpike(h.initial,h.api,h.observe);
  assert.match(r.reason,/alignment was not positively verified/);assert.equal(r.alignmentObserveRetries,8);
  assert.equal(r.skillAttempts,0);assert.equal(r.characterSelectionAttempts,1);assert.equal(r.movementAttempts,0);
  assert.equal(r.pauseVerified,true);assert.equal(h.calls.includes('E'),false);assert.equal(h.calls.includes('select-amber'),false);
  assert.equal(h.calls.filter(x=>Array.isArray(x)&&x[0]==='sleep'&&x[1]===200).length,8);
});

test('partial or missing ice proof never switches Amber or moves',async()=>{
  const h=harness({iceSequence:[false]}),r=await route.runWolfSecondSpike(h.initial,h.api,h.observe);
  assert.match(r.reason,/Positive second-pit ice proof/);assert.equal(r.iceObserveRetries,3);
  assert.equal(r.iceEffectVerified,false);assert.equal(r.movementAttempts,0);assert.equal(h.calls.includes('select-amber'),false);
});

test('stale, foreign-session, focus-loss, and Kaeya-health frames stop safely before movement',async()=>{
  for(const [faultStage,faultAt,fault] of [['cast',1,'stale'],['cast',1,'session'],['cast',1,'focus'],['cast',2,'health']]) {
    const h=harness({iceSequence:[false,true],faultStage,faultAt,fault}),r=await route.runWolfSecondSpike(h.initial,h.api,h.observe);
    assert.equal(r.movementAttempts,0,fault);assert.equal(h.calls.includes('select-amber'),false,fault);
    assert.equal(r.secondPitComplete,false,fault);
  }
});

test('opt-in Kaeya crossing skips Amber selection and uses at most three bounded moves',async()=>{
  const h=harness({crossingCharacter:'kaeya',floorAt:3}),r=await route.runWolfSecondSpike(h.initial,h.api,h.observe);
  assert.equal(r.crossingCharacter,'kaeya');assert.equal(r.characterSelectionAttempts,1);assert.equal(r.movementAttempts,3);
  assert.equal(h.calls.includes('select-amber'),false);assert.equal(r.solidFloorReached,true);assert.equal(r.secondPitComplete,false);
  assert.equal(r.pauseVerified,true);
});

test('Kaeya crossing stops on health change, stale frames, or foreign sessions',async()=>{
  for(const fault of ['health','stale','session']) {
    const h=harness({crossingCharacter:'kaeya',floorAt:3,faultStage:'moving',faultAt:1,fault}),r=await route.runWolfSecondSpike(h.initial,h.api,h.observe);
    assert.equal(r.movementAttempts,1,fault);assert.equal(h.calls.includes('select-amber'),false,fault);
    assert.equal(r.secondPitComplete,false,fault);
  }
});

test('invalid crossing character is rejected before Continue',async()=>{
  const h=harness({crossingCharacter:'amber-ish'}),r=await route.runWolfSecondSpike(h.initial,h.api,h.observe);
  assert.match(r.reason,/must be kaeya or amber/);assert.equal(r.continueAttempts,0);assert.equal(h.calls.includes('continue'),false);
});

test('post-skill and whole-run deadlines block further inputs',async()=>{
  const post=harness({extraDelayAt:4,extraDelay:11000,iceSequence:[true]}),p=await route.runWolfSecondSpike(post.initial,post.api,post.observe);
  assert.match(p.reason,/10-second post-skill deadline/);assert.equal(p.movementAttempts,0);assert.equal(post.calls.includes('select-amber'),false);
  const whole=harness({extraDelayAt:2,extraDelay:36000}),w=await route.runWolfSecondSpike(whole.initial,whole.api,whole.observe);
  assert.match(w.reason,/35-second second-pit deadline/);assert.equal(w.skillAttempts,0);assert.equal(w.movementAttempts,0);
});
