const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const combat=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/combat.js');

const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=80,height=24)=>({text,x,y,width,height});
function rows(current=1300,max=1427) { return [row('Kaeya',1663,487),row('Trial',1796,463),row(`${current}/${max}`,910,1000,100,20),row('E',1700,1015)]; }
const start={session:'wolf',mission:'questStep',status:'completed',timestamp:1999000,details:{result:{step:'wolfStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[{type:'wolfDomainStart',label:'Deep Within the Temple of the Wolf',startedAt:1998900}]}};
const party={session:'wolf',mission:'questStep',status:'completed',timestamp:1999500,details:{result:{step:'wolfPartyStart'},inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:2,x:1700,y:1019,startedAt:1999400}]}};

async function fixture({step='wolfTurretPass',proof=true,hpRows=rows(),entrySession='wolf'}={}) {
  let now=2000000,frame=0;const inputs=[];
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:()=>false,readTextSync:p=>p==='reports/wolf.json'?JSON.stringify(proof?[start,{...party,session:entrySession}]:[]):fs.readFileSync(path.join(root,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const a=this.mat.rows.map(x=>({...x}));a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x,contourArea:()=>0}}},
    captureGameRegion:()=>({width:1920,height:1080,rows:hpRows,srcMat:{},findMulti:()=>{const a=hpRows.map(x=>({...x}));a.count=a.length;return a;},deriveCrop:()=>({srcMat:{inRange:()=>({findContoursAsArray:()=>[],dispose(){}}),resize:()=>({rows:[]})},dispose(){}}),dispose(){}}),
    keyDown:k=>inputs.push(['down',k,now]),keyUp:k=>inputs.push(['up',k,now]),sleep:async ms=>{now+=ms;},click(){},moveMouseBy(){},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);
  adapter.beginMission({mission:'questStep',step,session:'wolf',createdAt:1999999});
  const observe=async()=>{frame++;return adapter.observe('wolf',frame);};
  const first=await observe();
  return {adapter,first,observe,inputs,now:()=>now,setRows:v=>{hpRows=v;}};
}

test('turret adapter permits one E60 but permanently blocks passage W without freeze proof',async()=>{
  const f=await fixture();
  assert.equal(f.adapter.wolfTurretPassReady(f.first, f.first.hud.health).ok,true);
  await f.adapter.wolfTurretPassCast();
  await f.adapter.sleep(100);
  const afterE=await f.observe();
  assert.ok(afterE.timestamp>f.adapter.events().find(e=>e.type==='wolfTurretPassCast').finishedAt);
  await assert.rejects(f.adapter.wolfTurretPassForward(800),/disabled until core shutdown is verified/);
  assert.deepEqual(f.inputs.filter(x=>x[0]==='down').map(x=>x[1]),['VK_E']);
  assert.deepEqual(Array.from(f.adapter.events().filter(e=>/^wolfTurretPass/.test(e.type)).map(e=>e.type)),['wolfTurretPassCast']);
  await assert.rejects(f.adapter.wolfTurretPassCast(),/already attempted/);
  await assert.rejects(f.adapter.wolfTurretPassForward(800),/disabled until core shutdown is verified/);
});

test('turret adapter rejects wrong step, missing entry proof, wrong Kaeya max HP and every W attempt',async()=>{
  const wrong=await fixture({step:'wolfCombat'});
  await assert.rejects(wrong.adapter.wolfTurretPassCast(),/Exact Wolf turret request/);
  assert.deepEqual(wrong.inputs,[]);
  const noProof=await fixture({proof:false});
  await assert.rejects(noProof.adapter.wolfTurretPassCast(),/entry required/);
  assert.deepEqual(noProof.inputs,[]);
  const wrongMax=await fixture({hpRows:rows(1400,1500)});
  await assert.rejects(wrongMax.adapter.wolfTurretPassCast(),/max HP 1427/);
  assert.deepEqual(wrongMax.inputs,[]);
  const f=await fixture();
  await assert.rejects(f.adapter.wolfTurretPassForward(800),/disabled until core shutdown is verified/);
  await f.adapter.wolfTurretPassCast();
  await assert.rejects(f.adapter.wolfTurretPassForward(800),/disabled until core shutdown is verified/);
  assert.deepEqual(f.inputs.filter(x=>x[0]==='down').map(x=>x[1]),['VK_E']);
});

test('mission attempts only one Cryo skill and stops without claiming effect or passage',async()=>{
  const calls=[],start={timestamp:1000,frameId:1,hud:{health:{current:1400,max:1427}}};let now=1000,reads=0;
  const sandbox={ActOneCombat:combat,module:{exports:{}}};vm.runInNewContext(fs.readFileSync(path.join(root,'mission.js'),'utf8'),sandbox);const quest=sandbox.module.exports;
  const ready=(o,t)=>!!o&&t-o.timestamp<=1000;
  const result=await quest.runQuestStep('wolfTurretPass',start,{now:()=>now,checkStop(){calls.push('stop');},sleep:async ms=>{calls.push(`sleep${ms}`);now+=ms;},
    wolfKaeyaSkillReady:ready,wolfTurretPassReady:(o,b)=>ready(o,now)?{ok:true,health:o.hud.health}:{ok:false,reason:'stale'},
    wolfTurretPassCast:async()=>calls.push('E'),wolfTurretPassForward:async ms=>calls.push(`W${ms}`)},async()=>{reads++;now++;return {timestamp:now,frameId:reads+1,hud:{health:{current:1400,max:1427}}};});
  assert.equal(result.status,'stopped');assert.equal(result.targetEffectVerified,false);assert.equal(result.forwardAttempts,0);
  assert.equal(reads,1);assert.deepEqual(calls.filter(x=>x==='E'||x.startsWith('W')||x.startsWith('sleep')),['E','sleep100']);
});
