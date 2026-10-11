const test = require('node:test');
const assert = require('node:assert/strict');
const combat = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/combat.js');

const row=(text,x,y)=>({text,x,y});
function frame(overrides={}) {
  return {timestamp:1000,frameId:1,map:null,ocr:[row('Kaeya',1664,480),row('Trial',1796,455)],hud:{world:false,groundControls:true,
    climbing:false,journal:false,bigMap:false,dialogueReady:false,choice:false,tutorialStep:null,objectiveChanged:false,unknownHud:false,
    interact:false,enemyBars:[],health:{current:1400,max:1427}},...overrides};
}
function ready(o,now) {
  const h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
  return !!(o&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&o.map===null&&h&&h.world===false&&h.groundControls===true&&
    rows.some(r=>r.text==='Kaeya'&&r.x>1550)&&rows.some(r=>r.text==='Trial'&&r.x>1700)&&hp&&hp.max===1427&&hp.current/hp.max>=0.6);
}
function advanceState(o,baseline) {
  const h=o&&o.hud,hp=h&&h.health;
  if(!ready(o,o&&o.timestamp)||!h||h.groundControls!==true||h.climbing||h.interact||h.dialogueReady||h.choice||h.tutorialStep||
    h.objectiveChanged||h.unknownHud||(h.enemyBars||[]).length) return {ok:false,reason:'Wolf action HUD unsafe'};
  if(baseline&&baseline.current-hp.current>baseline.max*0.05)return {ok:false,reason:'Wolf health dropped more than 5%'};
  return {ok:true};
}
function harness({initial=frame(),afterCast=frame({frameId:2}),afterForward=frame({frameId:3}),now=()=>1000}={}) {
  const events=[];let observations=0;
  const result=combat.runWolfTurretPass({observation:initial,now,observe:async()=>{
    observations++;events.push('observe');return observations===1?afterCast:afterForward;
  },sleep:async ms=>events.push(['sleep',ms]),checkStop:()=>{},wolfReady:o=>ready(o,now()),wolfAdvanceState:advanceState,
  wolfCast:async()=>events.push('E'),wolfForward:async ms=>events.push(['W',ms])});
  return {result,events};
}

test('rejects stale, non-Trial, wrong-max-HP, and unsafe initial observations before E',async()=>{
  for(const initial of [frame({timestamp:-1}),frame({ocr:[row('Kaeya',1664,480)]}),frame({hud:{...frame().hud,health:{current:1400,max:1426}}}),
    frame({hud:{...frame().hud,interact:true}})]) {
    const h=harness({initial}),r=await h.result;
    assert.equal(r.status,'stopped',JSON.stringify(initial));assert.equal(r.skillAttempts,0);assert.equal(r.forwardAttempts,0);assert.deepEqual(h.events,[]);
  }
});

test('post-E observation never authorizes passage movement, including with low HP or unknown UI',async()=>{
  const unsafe=[
    frame({frameId:2,hud:{...frame().hud,health:{current:1328,max:1427}}}),
    frame({frameId:2,timestamp:-1}),
    frame({frameId:2,hud:{...frame().hud,unknownHud:true}}),
  ];
  for(const afterCast of unsafe) {
    const h=harness({afterCast}),r=await h.result;
    assert.equal(r.status,'stopped',JSON.stringify(afterCast));assert.equal(r.skillAttempts,1);assert.equal(r.forwardAttempts,0);
    assert.equal(h.events.filter(e=>Array.isArray(e)&&e[0]==='W').length,0);
  }
});

test('one E is followed by one observation and stops without passage movement',async()=>{
  const h=harness(),r=await h.result;
  assert.deepEqual(h.events,['E',['sleep',100],'observe']);
  assert.equal(r.status,'stopped');assert.equal(r.skillAttempts,1);assert.equal(r.forwardAttempts,0);
  assert.equal(r.targetEffectVerified,false);assert.equal(r.passageVerified,false);
});

test('reports stopped if final observation is unsafe without claiming a freeze or passage',async()=>{
  const h=harness({afterForward:frame({frameId:3,hud:{...frame().hud,groundControls:false}})}),r=await h.result;
  assert.equal(r.status,'stopped');assert.equal(r.forwardAttempts,0);
  assert.equal(r.targetEffectVerified,false);assert.equal(r.passageVerified,false);
});
