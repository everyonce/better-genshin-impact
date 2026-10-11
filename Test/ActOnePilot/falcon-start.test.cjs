const test = require('node:test');
const assert = require('node:assert/strict');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

function row(text,x,y,width=100,height=30){return {text,x,y,width,height};}
function screen(patch={}) {
  return {timestamp:1000,frameId:145,map:null,ocr:[
    row('Domain Entrance',137,30),
    row('Deep Within the Temple of the Falcon',52,157,390,30),
    row('Recommended Party Level: 4',56,206,290,30),
    row('Deep Within the Temple of the Falcon',1274,149,469,29),
    row('Start',1688,999,85,36),
  ],hud:{world:false,journal:false,bigMap:false,dialogueReady:false,choice:false,tutorialStep:null},...patch};
}

test('falcon Start target requires fresh unambiguous selected-domain screen and derives button center',()=>{
  assert.deepEqual(bgi.falconStartTarget(screen(),1500),{x:1731,y:1017,label:'Deep Within the Temple of the Falcon'});
  const base=screen();
  for(const bad of [
    {...base,timestamp:499}, {...base,timestamp:1501}, {...base,map:{map:'Teyvat'}},
    {...base,hud:{...base.hud,world:true}},
    {...base,ocr:base.ocr.filter(r=>r.text!=='Domain Entrance')},
    {...base,ocr:base.ocr.filter(r=>!(r.text==='Deep Within the Temple of the Falcon'&&r.x<500))},
    {...base,ocr:base.ocr.map(r=>r.x===1274?{...r,text:'Windy Cliff'}:r)},
    {...base,ocr:base.ocr.filter(r=>!r.text.startsWith('Recommended Party'))},
    {...base,ocr:[...base.ocr,row('Start',700,500)]},
    {...base,ocr:[...base.ocr,row('Start',1700,1000)]},
    {...base,hud:{...base.hud,journal:true}},
  ]) assert.equal(bgi.falconStartTarget(bad,1500),null);
});

test('falconStart clicks once, waits 800ms, then makes one fresh observation',async()=>{
  let now=1000,observations=0,clicks=0;const calls=[];
  const api={now:()=>now,checkStop:()=>calls.push('guard'),startFalconDomain:()=>{clicks++;calls.push('click');now+=35;return 'Deep Within the Temple of the Falcon';},
    sleep:async ms=>{calls.push(['sleep',ms]);now+=ms;}};
  const result=await mission.runQuestStep('falconStart',screen(),api,async()=>{observations++;calls.push('observe');return {frameId:146};});
  assert.equal(result.status,'completed'); assert.equal(result.clicks,1); assert.equal(result.frameId,146);assert.equal(result.inputMs,35);
  assert.equal(clicks,1);assert.equal(observations,1);
  assert.deepEqual(calls,['guard','click',['sleep',800],'guard','observe']);
});

test('falconStart does not click when stop is already requested',async()=>{
  let clicks=0,observations=0;
  const api={now:()=>1000,checkStop:()=>{throw new Error('Stop requested');},startFalconDomain:()=>{clicks++;},sleep:async()=>{}};
  const result=await mission.runQuestStep('falconStart',screen(),api,async()=>{observations++;return {};});
  assert.equal(result.status,'stopped');assert.equal(result.clicks,0);assert.equal(clicks,0);assert.equal(observations,0);
});
