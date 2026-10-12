const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const combat=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/combat.js');

function frame(now,id,{health=1300,x=960,y=500,width=130,bars=true,ocr}={}) {
  return {session:'wolf',timestamp:now,frameId:id,map:null,ocr:ocr||[
    {text:'Kaeya',x:1664,y:487},{text:'Trial',x:1796,y:463}],
    hud:{world:false,groundControls:true,climbing:false,journal:false,bigMap:false,
      dialogueReady:false,choice:false,tutorialStep:null,health:{current:health,max:1427},
      enemyBars:bars?[{x,y,width,height:8}]:[]}};
}
function pauseFrame(now,id,menu=false) {
  return frame(now,id,{bars:false,ocr:menu?[{text:'Continue Challenge'},{text:'Leave Domain?'}]:undefined});
}

function combatHarness({healthAfterFirstSeek=1300,initialX=1080,widths=[130]}={}) {
  let now=1000,id=0,latestX=initialX,health=1300,paused=false,widthIndex=0;
  const inputs=[],seeks=[],events=[];
  function observe() {
    id++;
    const width=widths[Math.min(widthIndex++,widths.length-1)];
    const value=paused?pauseFrame(now,id,true):frame(now,id,{health,x:latestX,width});
    events.push(['observe',id,now]);return value;
  }
  const api={now:()=>now,sleep:async ms=>{now+=ms;},checkStop:()=>{},
    wolfCombatKey:async key=>{inputs.push(key);events.push(['key',key,id,now]);},
    wolfCombatSeek:async(kind,frameId,dx,durationMs)=>{
      assert.equal(frameId,id,'seek is authorized by the current checked crop frame');
      assert.notEqual(seeks.at(-1)&&seeks.at(-1).frameId,frameId,'never repeat a seek on one decision frame');
      seeks.push({kind,frameId,dx,durationMs});inputs.push(kind==='forward'?'VK_W':'rotate');
      events.push(['seek',kind,frameId]);
      if(kind==='turn')latestX=Math.max(850,Math.min(1070,latestX-dx));
      if(seeks.length===1)health=healthAfterFirstSeek;
      now+=kind==='forward'?250:0;
    },
    wolfPauseCombat:async()=>{paused=true;events.push(['pause']);}};
  return {api,observe,inputs,seeks,events,first:()=>frame(now,0,{health,x:initialX,width:widths[0]})};
}

test('Wolf melee seek turns toward the anchored bar, then uses at most four short forward pulses',async()=>{
  // The combat crop begins at x=350; a contour center at crop-x 730 maps to
  // full-frame x=1080. It needs one capped 32px turn before entering the W corridor.
  const h=combatHarness();
  const result=await combat.runWolf(h.first(),h.api,async()=>h.observe());
  assert.equal(h.seeks[0].kind,'turn');
  assert.equal(h.seeks[0].dx,32);
  assert.ok(h.events.some(e=>e[0]==='observe'&&e[1]===h.seeks[0].frameId));
  assert.ok(h.seeks.some(s=>s.kind==='forward'));
  assert.ok(h.seeks.filter(s=>s.kind==='forward').every(s=>s.durationMs===250));
  assert.ok(h.seeks.filter(s=>s.kind==='forward').length<=4);
  assert.ok(h.seeks.filter(s=>s.kind==='turn').length<=2);
  assert.equal(result.seekForward,h.seeks.filter(s=>s.kind==='forward').length);
  assert.equal(result.seekTurns,h.seeks.filter(s=>s.kind==='turn').length);
  assert.equal(result.presses,h.inputs.length,'selection, attacks, and seek actions share the action counter');
  assert.equal(result.reason,'Wolf bounded approach pulse limit reached');
  assert.equal(result.pauseVerified,true);
});

test('camera correction sign is symmetric for bars on either side of center',async()=>{
  const right=combatHarness({initialX:1080});
  await combat.runWolf(right.first(),right.api,async()=>right.observe());
  const left=combatHarness({initialX:840});
  await combat.runWolf(left.first(),left.api,async()=>left.observe());
  assert.equal(right.seeks[0].dx,32,'right-side bar gets positive mouse delta');
  assert.equal(left.seeks[0].dx,-32,'left-side bar gets negative mouse delta');
  assert.ok(right.seeks.some(s=>s.kind==='forward'));
  assert.ok(left.seeks.some(s=>s.kind==='forward'));
});

test('one-to-two pixel contour jitter does not suppress the bounded seek trigger',async()=>{
  const h=combatHarness({initialX:960,widths:[128,129,130]});
  const result=await combat.runWolf(h.first(),h.api,async()=>h.observe());
  assert.ok(h.seeks.some(s=>s.kind==='forward'),'stable bar with 128/129/130px variation still triggers melee approach');
  assert.ok(h.seeks.filter(s=>s.kind==='forward').length<=4);
  assert.equal(result.seekForward,h.seeks.filter(s=>s.kind==='forward').length);
});

test('post-seek unsafe health stops before another attack and still attempts guarded pause',async()=>{
  const h=combatHarness({healthAfterFirstSeek:1000});
  const result=await combat.runWolf(h.first(),h.api,async()=>h.observe());
  assert.match(result.reason,/dropped more than 20%/);
  assert.equal(h.seeks.length,1);
  assert.equal(h.inputs.filter(x=>x==='VK_LBUTTON').length,2);
  assert.equal(result.pauseVerified,true);
});

test('bounded approach works with a fresh crop-shaped centered Lv.5 bar and stops on stale safety data',async()=>{
  const h=combatHarness({initialX:960});
  let madeStale=false;
  const observe=async()=>{
    const value=h.observe();
    if(!madeStale&&h.seeks.length>0) {madeStale=true;value.timestamp-=1001;}
    return value;
  };
  const result=await combat.runWolf(h.first(),h.api,observe);
  assert.equal(h.seeks.length,1,'stale post-pulse evidence prevents any second seek or attack');
  assert.equal(h.inputs.filter(x=>x==='VK_W').length,1);
  assert.match(result.reason,/stale/);
});

const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const start={session:'wolf',mission:'questStep',status:'completed',timestamp:1000,
  details:{result:{step:'wolfStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[
    {type:'wolfDomainStart',label:'Deep Within the Temple of the Wolf',startedAt:900}]}};
const party={session:'wolf',mission:'questStep',status:'completed',timestamp:1500,
  details:{result:{step:'wolfPartyStart'},inputEvents:[
    {type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:2,x:1700,y:1019,startedAt:1400}]}};

function adapterFixture({foreground=true,proof=true,step='wolfCombat'}={}) {
  let now=2000;const inputs=[],rotations=[];
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:foreground},
    file:{isExists:()=>false,readTextSync:p=>p==='reports/wolf.json'?JSON.stringify(proof?[start,party]:[]):fs.readFileSync(path.join(root,p),'utf8'),
      writeTextSync:()=>true,writeImageSync:()=>true},
    keyDown:key=>inputs.push(['down',key,now]),keyUp:key=>inputs.push(['up',key,now]),
    moveMouseBy:(dx,dy)=>rotations.push([dx,dy]),sleep:async ms=>{now+=ms;}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);
  const request={mission:'questStep',step,session:'wolf',createdAt:1900,expectedFrameId:10};
  adapter.beginMission(request);
  function seed({frameId=10,x=1200,max=1427,health=1300,age=0,bars=1,session='wolf'}={}) {
    const observation={session,frameId,timestamp:now-age,map:null,
      ocr:[{text:'Kaeya',x:1664,y:487},{text:'Trial',x:1796,y:463},{text:'Lv.5',x:x-20,y:455,width:40,height:20}],
      hud:{world:false,groundControls:true,climbing:false,journal:false,bigMap:false,auto:false,loading:false,
        unknownHud:false,objectiveChanged:false,interact:false,dialogueReady:false,choice:false,tutorialStep:null,
        health:{current:health,max},enemyBarDiagnostic:{level:5,localReads:[]},
        enemyBars:Array.from({length:bars},()=>({x,y:500,width:130,height:8}))}};
    // seedObservation enforces request.expectedFrameId and stores an immutable copy.
    request.expectedFrameId=frameId;
    adapter.seedObservation(observation);
  }
  return {adapter,inputs,rotations,seed,setForeground:value=>{context.genshin.isGameForeground=value;},advance:ms=>{now+=ms;}};
}

async function croppedAdapterFixture() {
  let now=2000,frameId=9,barX=1080;const inputs=[],rotations=[];
  const rows=()=>[
    {text:'Kaeya',x:1664,y:487,width:50,height:20},{text:'Trial',x:1796,y:463,width:40,height:20},
    {text:'1300/1427',x:910,y:1002,width:100,height:18},{text:'E',x:1700,y:1015,width:30,height:20},
    {text:'Lv.5',x:barX-20,y:455,width:40,height:20}];
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:()=>false,readTextSync:p=>p==='reports/wolf.json'?JSON.stringify([start,party]):fs.readFileSync(path.join(root,p),'utf8'),
      writeTextSync:()=>true,writeImageSync:()=>true},RecognitionObject:{Ocr:()=>({})},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},
      RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:value=>value}}},
    ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}dispose(){}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows().map(x=>({...x}));a.count=a.length;return a;},
      deriveCrop:(x,y)=>({srcMat:{inRange:()=>({findContoursAsArray:()=>[
        {x:barX-350-65,y:500-100-4,width:130,height:8}],dispose(){}})},dispose(){}}),dispose(){}}),
    keyDown:key=>inputs.push(['down',key,now]),keyUp:key=>inputs.push(['up',key,now]),
    moveMouseBy:(dx,dy)=>{rotations.push([dx,dy]);barX-=dx;},sleep:async ms=>{now+=ms;}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7),request={mission:'questStep',step:'wolfCombat',session:'wolf',createdAt:1900,expectedFrameId:9};
  adapter.beginMission(request);
  async function observe(){frameId++;request.expectedFrameId=frameId;return adapter.observe('wolf',frameId);}
  const first=await observe();
  return {adapter,first,observe,inputs,rotations};
}

test('real crop contour and anchored Lv.5 label authorize one turn then a released approach pulse',async()=>{
  const f=await croppedAdapterFixture();
  assert.deepEqual(JSON.parse(JSON.stringify(f.first.hud.enemyBars)),[{x:1080,y:500,width:130,height:8}]);
  await f.adapter.wolfCombatSeek('turn',f.first.frameId,32,0);
  assert.deepEqual(f.rotations,[[32,0]]);
  const centered=await f.observe();
  assert.deepEqual(JSON.parse(JSON.stringify(centered.hud.enemyBars)),[{x:1048,y:500,width:130,height:8}]);
  await f.adapter.wolfCombatSeek('forward',centered.frameId,0,250);
  assert.deepEqual(f.inputs.map(e=>e.slice(0,2)),[['down','VK_W'],['up','VK_W']]);
  assert.equal(f.adapter.events().filter(e=>e.type==='wolfCombatSeek').length,2);
});

test('adapter accepts only same-session fresh Lv.5 seek, releases W, records rotation timing, and blocks replay',async()=>{
  const f=adapterFixture();f.seed();
  await f.adapter.wolfCombatSeek('turn',10,32,0);
  assert.deepEqual(f.rotations,[[32,0]]);
  const turn=f.adapter.events().find(e=>e.type==='wolfCombatSeek');
  assert.equal(turn.frameId,10);assert.ok(turn.finishedAt>=turn.startedAt);
  f.seed({frameId:11,x:960});
  await f.adapter.wolfCombatSeek('forward',11,0,250);
  assert.deepEqual(f.inputs.map(e=>e.slice(0,2)),[['down','VK_W'],['up','VK_W']]);
  assert.ok(f.inputs[1][2]-f.inputs[0][2]>=250);
  const forward=f.adapter.events().find(e=>e.type==='wolfCombatSeek'&&e.kind==='forward');
  assert.equal(forward.frameId,11);assert.equal(forward.durationMs,250);assert.ok(forward.finishedAt>=forward.startedAt);
  await assert.rejects(f.adapter.wolfCombatSeek('forward',11,0,250),/Fresh unique/);
});

test('adapter rejects stale, off-center W, ambiguous targets, unhealthy/wrong-max HP, missing proof, and lost focus',async t=>{
  const cases=[
    {name:'stale observation',stale:true},
    {name:'off-center forward pulse',seed:{x:1200},call:['forward',0,250]},
    {name:'multiple enemy bars',seed:{bars:2}},
    {name:'under 60 percent HP',seed:{health:850}},
    {name:'wrong max HP',seed:{max:1500}},
    {name:'missing same-session entry receipt',proof:false},
    {name:'wrong step',step:'wolfTurretPass'},
  ];
  for(const scenario of cases) await t.test(scenario.name,async()=>{
    const f=adapterFixture(scenario);f.seed(scenario.seed||{});if(scenario.stale)f.advance(1001);
    const call=scenario.call||['turn',10,32,0];
    await assert.rejects(f.adapter.wolfCombatSeek(call[0],10,call[1],call[2]));
    assert.deepEqual(f.inputs,[]);assert.deepEqual(f.rotations,[]);
  });
  const unfocused=adapterFixture();unfocused.seed();unfocused.setForeground(false);
  await assert.rejects(unfocused.adapter.wolfCombatSeek('turn',10,-32,0),/foreground/);
  assert.deepEqual(unfocused.rotations,[]);
  const wrongSession=adapterFixture();wrongSession.seed();
  wrongSession.adapter.beginMission({mission:'questStep',step:'wolfCombat',session:'other',createdAt:1900,expectedFrameId:10});
  await assert.rejects(wrongSession.adapter.wolfCombatSeek('turn',10,32,0),/Fresh unique/);
  assert.deepEqual(wrongSession.inputs,[]);assert.deepEqual(wrongSession.rotations,[]);
  const wrongSign=adapterFixture();wrongSign.seed();
  await assert.rejects(wrongSign.adapter.wolfCombatSeek('turn',10,-32,0),/Valid bounded/);
  assert.deepEqual(wrongSign.rotations,[]);
});

test('adapter enforces four W pulses and two camera corrections within one mission',async()=>{
  const f=adapterFixture();
  for(let frameId=10;frameId<14;frameId++) {
    f.seed({frameId,x:960});await f.adapter.wolfCombatSeek('forward',frameId,0,250);
  }
  f.seed({frameId:14,x:960});
  await assert.rejects(f.adapter.wolfCombatSeek('forward',14,0,250),/Centered Wolf target/);
  for(let frameId=20;frameId<22;frameId++) {
    f.seed({frameId,x:1200});await f.adapter.wolfCombatSeek('turn',frameId,32,0);
  }
  f.seed({frameId:22,x:1200});
  await assert.rejects(f.adapter.wolfCombatSeek('turn',22,32,0),/Valid bounded/);
  assert.equal(f.adapter.events().filter(e=>e.type==='wolfCombatSeek'&&e.kind==='forward').length,4);
  assert.equal(f.adapter.events().filter(e=>e.type==='wolfCombatSeek'&&e.kind==='turn').length,2);
});
