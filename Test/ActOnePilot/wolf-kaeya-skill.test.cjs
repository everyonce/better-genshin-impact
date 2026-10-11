const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const row=(text,x,y,width=80,height=24)=>({text,x,y,width,height});
function observation({max=1427,current=max,trial=true,age=0}={}) {
  return {session:'wolf',timestamp:2000000-age,frameId:8,map:null,ocr:[row('Kaeya',1663,487),...(trial?[row('Trial',1796,463)]:[]),row(`${current}/${max}`,910,1000,100,20),row('E',1700,1015)],
    hud:{world:false,groundControls:true,climbing:false,journal:false,bigMap:false,dialogueReady:false,choice:false,tutorialStep:null,
      health:{current,max},enemyBars:[]}};
}

test('Wolf Kaeya skill mission selects once, observes, presses E once, then observes again',async()=>{
  let now=2000000,reads=0;const calls=[];
  const result=await mission.runQuestStep('wolfKaeyaSkill',observation(),{
    now:()=>now,checkStop(){},wolfDomainHud:o=>bgi.wolfDomainHud(o,now),wolfKaeyaSkillReady:o=>bgi.wolfKaeyaSkillReady(o,now),
    wolfKaeyaSkillSelect:async()=>calls.push('3'),wolfKaeyaSkillCast:async()=>calls.push('E'),sleep:async ms=>{assert.equal(ms,500);now+=ms;}
  },async()=>{reads++;return observation();});
  assert.equal(result.status,'completed');
  assert.equal(result.targetEffectVerified,false);
  assert.equal(result.characterSelectionAttempts,1);assert.equal(result.skillAttempts,1);
  assert.deepEqual(calls,['3','E']);assert.equal(reads,2);
});

test('Wolf Kaeya skill mission rejects unsafe initial HUDs before selecting',async()=>{
  for(const [label,o] of [
    ['stale',observation({age:1001})],['unhealthy',observation({max:1427,current:850})],
    ['no Trial',observation({trial:false})]
  ]) {
    let selects=0,reads=0,now=2000000;
    const result=await mission.runQuestStep('wolfKaeyaSkill',o,{now:()=>now,checkStop(){},wolfDomainHud:x=>bgi.wolfDomainHud(x,now),
      wolfKaeyaSkillSelect:async()=>selects++,wolfKaeyaSkillReady:x=>bgi.wolfKaeyaSkillReady(x,now),sleep:async()=>{}},async()=>{reads++;return o;});
    assert.equal(result.status,'stopped',label);assert.equal(selects,0,label);assert.equal(reads,0,label);
  }
});

test('a wrong post-selection max HP stops before E and reports zero skill attempts',async()=>{
  let now=2000000,selects=0,skills=0;
  const result=await mission.runQuestStep('wolfKaeyaSkill',observation(),{now:()=>now,checkStop(){},wolfDomainHud:o=>bgi.wolfDomainHud(o,now),
    wolfKaeyaSkillReady:o=>bgi.wolfKaeyaSkillReady(o,now),wolfKaeyaSkillSelect:async()=>selects++,wolfKaeyaSkillCast:async()=>skills++,
    sleep:async ms=>{now+=ms;}},async()=>observation({max:1000,current:1000}));
  assert.equal(result.status,'stopped');assert.equal(selects,1);assert.equal(skills,0);assert.equal(result.skillAttempts,0);
  assert.match(result.reason,/max HP 1427/);
});

test('adapter skill input rejects missing same-entry proof, stale HUD, no Trial, and wrong max HP',async()=>{
  const packageDir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
  const source=fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8');
  const start={session:'wolf',mission:'questStep',status:'completed',timestamp:1999000,details:{result:{step:'wolfStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[
    {type:'wolfDomainStart',label:'Deep Within the Temple of the Wolf',startedAt:1998900}]}};
  const party={session:'wolf',mission:'questStep',status:'completed',timestamp:1999500,details:{result:{step:'wolfPartyStart'},inputEvents:[
    {type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:2,x:1700,y:1019,startedAt:1999400}]}};
  async function make({proof=true,o=observation()}={}) {
    let now=2000000;const inputs=[];const rows=o.ocr;
    const context={Date:class extends Date{static now(){return now;}},
      genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
      file:{isExists:()=>false,readTextSync:p=>p==='reports/wolf.json'?JSON.stringify(proof?[start,party]:[]):fs.readFileSync(path.join(packageDir,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
      RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const a=this.mat&&this.mat.rows?this.mat.rows.map(x=>({...x})):[];a.count=a.length;return a;}dispose(){}},
      OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{constructor(a,b,c){this.values=[a,b,c];}},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x,contourArea:()=>0}}},
      captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows.map(x=>({...x}));a.count=a.length;return a;},deriveCrop:(x,y,w,h)=>({srcMat:{inRange:()=>({findContoursAsArray:()=>[],dispose(){}}),resize:()=>({rows:[]})},dispose(){} }),dispose(){}}),
      keyDown:k=>inputs.push(['down',k]),keyUp:k=>inputs.push(['up',k]),sleep:async ms=>{now+=ms;},click(){},moveMouseBy(){},log:{info(){}}};
    vm.runInNewContext(source,context);const adapter=context.createActOneAdapter(7);
    adapter.beginMission({mission:'questStep',step:'wolfKaeyaSkill',session:'wolf',createdAt:1999999});
    await adapter.observe('wolf',1);return {adapter,inputs,setNow:n=>{now=n;},inputs};
  }
  const missingProof=await make({proof:false});
  await assert.rejects(missingProof.adapter.wolfKaeyaSkillSelect(),/entry required/);assert.deepEqual(missingProof.inputs,[]);
  const stale=await make();stale.setNow(2001002);
  await assert.rejects(stale.adapter.wolfKaeyaSkillSelect(),/Fresh safe Wolf trial HUD/);assert.deepEqual(stale.inputs,[]);
  const noTrial=await make({o:observation({trial:false})});
  await assert.rejects(noTrial.adapter.wolfKaeyaSkillSelect(),/Fresh safe Wolf trial HUD/);assert.deepEqual(noTrial.inputs,[]);
  const wrongMax=await make({o:observation({max:1000,current:1000})});
  await assert.rejects(wrongMax.adapter.wolfKaeyaSkillCast(),/max HP 1427/);assert.deepEqual(wrongMax.inputs,[]);
});
