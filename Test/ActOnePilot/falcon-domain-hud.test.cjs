const test = require('node:test');
const assert = require('node:assert/strict');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

function row(text,x,y){return {text,x,y,width:80,height:25};}
function trial(patch={}) {
  const {hud:hudPatch,...rest}=patch;
  return {timestamp:1000,map:null,ocr:[row('Amber',1600,400),row('Trial',1750,420)],hud:{
    world:false,groundControls:true,climbing:false,journal:false,bigMap:false,dialogueReady:false,choice:false,
    tutorialStep:null,objectiveChanged:false,health:{current:900,max:1000},lowHealth:false,...hudPatch
  },...rest};
}

test('Falcon domain HUD requires fresh mapless trial screen, safe HP and clear grounded state',()=>{
  assert.equal(bgi.falconDomainHud(trial(),1500),true);
  const base=trial();
  const bad=[
    {...base,timestamp:499},{...base,timestamp:1501},
    {...base,ocr:base.ocr.filter(r=>r.text!=='Trial')},
    {...base,map:{map:'Teyvat'}},{...base,hud:{...base.hud,world:true}},
    {...base,hud:{...base.hud,health:{current:599,max:1000}}},
    {...base,hud:{...base.hud,journal:true}},{...base,hud:{...base.hud,bigMap:true}},
    {...base,hud:{...base.hud,dialogueReady:true}},{...base,hud:{...base.hud,choice:true}},
    {...base,hud:{...base.hud,climbing:true}},{...base,hud:{...base.hud,groundControls:false}},
  ];
  for(const o of bad) assert.equal(bgi.falconDomainHud(o,1500),false);
});

function harness(observations) {
  let now=1000,index=0;const moves=[],calls=[];
  const api={now:()=>now,checkStop:()=>calls.push('guard'),sleep:async ms=>{now+=ms;calls.push(['sleep',ms]);},
    falconMove:async(key,ms)=>{moves.push([key,ms]);now+=ms;}};
  const observe=async()=>{const next=observations[Math.min(index++,observations.length-1)];calls.push('observe');return next;};
  return {moves,calls,run:()=>mission.runQuestStep('falconConsoleApproach',trial(),api,observe)};
}

test('Falcon console approach stops on fresh interaction prompt before the next movement',async()=>{
  const visible=trial({frameId:2,hud:{interact:true}}),h=harness([visible]);
  const result=await h.run();
  assert.equal(result.status,'stopped');assert.equal(result.reason,'Domain interaction available');
  assert.deepEqual(h.moves,[['VK_W',800]]);
});

test('Falcon console approach stops before another movement after a greater-than-10-percent HP drop',async()=>{
  const damaged=trial({frameId:3,hud:{health:{current:790,max:1000}}}),h=harness([damaged]);
  const result=await h.run();
  assert.equal(result.status,'stopped');assert.equal(result.reason,'Domain health evidence changed');
  assert.deepEqual(h.moves,[['VK_W',800]]);
});
