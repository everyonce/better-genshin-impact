const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=80,height=24)=>({text,x,y,width,height});
function rows(current=1300,max=1427) { return [row('Kaeya',1663,487),row('Trial',1796,463),row(`${current}/${max}`,910,1000,100,20),row('E',1700,1015)]; }
const start={session:'wolf',mission:'questStep',status:'completed',timestamp:1999000,details:{result:{step:'wolfStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[{type:'wolfDomainStart',label:'Deep Within the Temple of the Wolf',startedAt:1998900}]}};
const party={session:'wolf',mission:'questStep',status:'completed',timestamp:1999500,details:{result:{step:'wolfPartyStart'},inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:2,x:1700,y:1019,startedAt:1999400}]}};

async function fixture({step='wolfAimCryo',proof=true,hpRows=rows(),foreground=true,entrySession='wolf',session='wolf'}={}) {
  let now=2000000,frame=0;const inputs=[],rotations=[];
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:foreground,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:()=>false,readTextSync:p=>p==='reports/'+session+'.json'?JSON.stringify(proof?[{...start,session},{...party,session:entrySession}]:[]):fs.readFileSync(path.join(root,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const a=this.mat.rows.map(x=>({...x}));a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x,contourArea:()=>0}}},
    captureGameRegion:()=>({width:1920,height:1080,rows:hpRows,srcMat:{},findMulti:()=>{const a=hpRows.map(x=>({...x}));a.count=a.length;return a;},deriveCrop:()=>({srcMat:{inRange:()=>({findContoursAsArray:()=>[],dispose(){}}),resize:()=>({rows:[]})},dispose(){}}),dispose(){}}),
    keyDown:k=>inputs.push(['down',k,now]),keyUp:k=>inputs.push(['up',k,now]),sleep:async ms=>{now+=ms;},click(){},moveMouseBy:(x,y)=>rotations.push([x,y]),log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);
  adapter.beginMission({mission:'questStep',step,session,createdAt:1999999});
  const observe=async()=>{frame++;return adapter.observe(session,frame);};
  const first=await observe();
  return {adapter,first,observe,inputs,rotations,now:()=>now,setForeground:v=>{context.genshin.isGameForeground=v;},setRows:v=>{hpRows=v;}};
}

test('aim Cryo uses one right turn, W60, E60, releases both keys, and never retries',async()=>{
  const f=await fixture();
  assert.equal(f.adapter.wolfAimCryoReady(f.first),true);
  await f.adapter.wolfAimCryo();
  assert.deepEqual(f.rotations,[[250,0]]);
  assert.deepEqual(f.inputs.map(x=>x.slice(0,2)),[['down','VK_W'],['up','VK_W'],['down','VK_E'],['up','VK_E']]);
  assert.ok(f.inputs[1][2]-f.inputs[0][2]>=60);assert.ok(f.inputs[3][2]-f.inputs[2][2]>=60);
  await assert.rejects(f.adapter.wolfAimCryo(),/required/);
  assert.equal(f.rotations.length,1);assert.equal(f.inputs.length,4);
});

test('aim Cryo refuses stale, unhealthy, wrong max HP, missing Trial, wrong session, missing entry, and lost focus',async()=>{
  for(const options of [
    {hpRows:rows(800)}, {hpRows:rows(800,1055)}, {hpRows:rows(1300,1500)},
    {hpRows:[row('Kaeya',1663,487),row('1300/1427',910,1000,100,20)]},
    {proof:false}, {entrySession:'other'}, {session:'other'}
  ]) {
    const f=await fixture(options);
    if(options.session==='other') { await assert.rejects(f.adapter.wolfAimCryo(),/entry required/); }
    else if(options.proof===false||options.entrySession) { assert.equal(f.adapter.wolfAimCryoReady(f.first),false); await assert.rejects(f.adapter.wolfAimCryo(),/entry required/); }
    else { assert.equal(f.adapter.wolfAimCryoReady(f.first),false); await assert.rejects(f.adapter.wolfAimCryo(),/required/); }
    assert.deepEqual(f.inputs,[]);assert.deepEqual(f.rotations,[]);
  }
  const unfocused=await fixture();unfocused.setForeground(false);
  await assert.rejects(unfocused.adapter.wolfAimCryo(),/foreground/);assert.deepEqual(unfocused.inputs,[]);assert.deepEqual(unfocused.rotations,[]);
  const stale=await fixture();stale.first.timestamp-=1001;
  assert.equal(stale.adapter.wolfAimCryoReady(stale.first),false);
  await assert.rejects(stale.adapter.wolfAimCryo(),/required/);assert.deepEqual(stale.inputs,[]);
});

test('mission stops after one bounded aim and Cryo sequence without claiming target effect',async()=>{
  let now=2000000,reads=0;const calls=[];
  const observation={timestamp:now,frameId:1};
  const result=await mission.runQuestStep('wolfAimCryo',observation,{now:()=>now,wolfAimCryoReady:()=>true,
    wolfAimCryo:async()=>calls.push('aimSequence'),sleep:async ms=>{calls.push(`sleep${ms}`);now+=ms;}},async()=>{reads++;return {timestamp:now,frameId:2};});
  assert.equal(result.status,'stopped');assert.equal(result.targetEffectVerified,false);assert.equal(result.skillAttempts,1);
  assert.equal(reads,1);assert.deepEqual(calls,['aimSequence','sleep100']);
});
