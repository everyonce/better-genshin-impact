const test=require('node:test');
const assert=require('node:assert/strict');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const target={x:960,y:495,width:120,height:8};
function hud({health={current:1000,max:1000},enemyBars=[target]}={}) {
  return {map:null,ocr:[{text:'R',x:1700,y:1020,width:24,height:24},{text:'Amber',x:1660,y:440,width:80,height:24},{text:'Trial',x:1800,y:420,width:45,height:20}],hud:{world:false,groundControls:false,climbing:false,
    journal:false,bigMap:false,dialogueReady:false,choice:false,tutorialStep:null,objectiveChanged:false,health,enemyBars}};
}
function harness({observe=()=>hud(),sleepHook=()=>{},initial=hud()}={}) {
  let now=1000,pause=false,observations=0;const actions=[];
  const api={now:()=>now,checkStop:()=>{},sleep:async ms=>{sleepHook(ms,()=>now,n=>{now=n;},actions);now+=ms;},
    falconRangedAction:async(kind,bar)=>{actions.push({kind,bar,at:now});},
    falconPause:async()=>{actions.push({kind:'pause',at:now});pause=true;}};
  const read=async()=>{observations++;return pause?{...hud(),ocr:[{text:'Continue Challenge'}]}:observe(observations);};
  return {api,actions,initial,read,get observations(){return observations;},run:()=>mission.runQuestStep('falconRanged',initial,api,read)};
}

test('ranged trial uses the operator-verified initial crosshair for its first shot, then caps at five shots',async()=>{
  const h=harness();
  const result=await h.run();
  const sequence=h.actions.map(a=>a.kind);
  assert.equal(result.shots,5);assert.equal(sequence[0],'fire','the initial shot is taken at the operator-verified crosshair');
  assert.equal(sequence.filter(k=>k==='fire').length,5);assert.ok(sequence.includes('aim'));
  assert.equal(sequence.at(-2),'exit');assert.equal(sequence.at(-1),'pause');assert.equal(result.paused,true);
});

test('ranged trial stops before another shot when fresh enemy bars disappear',async()=>{
  const h=harness({observe:n=>n===2?hud({enemyBars:[]}):hud()});
  const result=await h.run();
  assert.equal(result.reason,'No fresh ranged target');assert.equal(result.shots,1);
  assert.deepEqual(h.actions.filter(a=>['fire','aim'].includes(a.kind)).map(a=>a.kind),['fire']);
  assert.ok(h.actions.some(a=>a.kind==='exit'));assert.ok(h.actions.some(a=>a.kind==='pause'));
});

test('ranged trial stops before another shot after health falls over 20 percent',async()=>{
  const h=harness({observe:n=>n===2?hud({health:{current:750,max:1000}}):hud()});
  const result=await h.run();
  assert.equal(result.reason,'Ranged health guard');assert.equal(result.shots,1);
  assert.deepEqual(h.actions.filter(a=>['fire','aim'].includes(a.kind)).map(a=>a.kind),['fire']);
});

test('ranged trial stops after two aim observations fail to settle the target',async()=>{
  const offCenter={x:1100,y:650,width:100,height:8};
  const h=harness({observe:()=>hud({enemyBars:[offCenter]})});
  const result=await h.run();
  assert.equal(result.reason,'Ranged aim did not settle');assert.equal(result.shots,1);
  assert.deepEqual(h.actions.filter(a=>['fire','aim'].includes(a.kind)).map(a=>a.kind),['fire','aim','aim']);
});

test('ranged trial does not fire after its 20-second deadline is reached during shot preparation',async()=>{
  const started=1000,deadline=started+20000;
  const h=harness({sleepHook:(ms,getNow,setNow,actions)=>{
    if(ms===1800&&actions.some(a=>a.kind==='fire'))setNow(deadline);
  }});
  await h.run();
  const shots=h.actions.filter(a=>a.kind==='fire');
  assert.ok(shots.every(a=>a.at<deadline),'all fire inputs must occur before the mission deadline');
});

test('aim HUD permits the optional low-HP exit threshold while default firing gate remains 60 percent',()=>{
  const low={...hud({health:{current:100,max:1000}}),timestamp:1000};
  assert.equal(bgi.falconAimHud(low,1500),false);
  assert.equal(bgi.falconAimHud(low,1500,0.01),true);
  const safe={...hud({health:{current:600,max:1000}}),timestamp:1000};
  assert.equal(bgi.falconAimHud(safe,1500),true);
  assert.equal(bgi.falconAimHud({...safe,timestamp:0},1500),false);
});
