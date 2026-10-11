const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=100,height=30)=>({text,x,y,width,height});
function modal({timestamp=2000000,heading='Kaeya',item='Sweet Madame',quantity=1}={}) {
  return {session:'wolf',timestamp,frameId:18,map:null,ocr:[row('Food',140,32,67,31),row(item,1332,127,263,41),row(heading,891,259,136,59),
    row('Amount to use',639,611,217,39),row('Cancel',716,748,109,37),row('Confirm',1118,750,129,37)],
    hud:{world:false,climbing:false,dialogueReady:false,choice:false,bigMap:false,loading:false,foodQuantity:quantity===null?null:{value:quantity,source:'scaled-same-frame',frameId:18,x:1142,y:628}}};
}

test('feed target needs current exact Kaeya Sweet Madame modal and same-frame quantity one',()=>{
  assert.deepEqual(bgi.wolfFeedKaeyaTarget(modal(),2000000),{x:1183,y:769});
  for(const bad of [
    modal({timestamp:1998999}),modal({heading:'Traveler'}),modal({item:'Teyvat Fried Egg'}),modal({quantity:null}),modal({quantity:2}),
    {...modal(),hud:{...modal().hud,foodQuantity:{value:1,frameId:17}}},
    {...modal(),ocr:[...modal().ocr,row('Confirm',1118,750,129,37)]},
    {...modal(),map:{map:'Teyvat',x:1,y:2}},
    {...modal(),hud:{...modal().hud,choice:true}}
  ]) assert.equal(bgi.wolfFeedKaeyaTarget(bad,2000000),null);
});

test('mission permits one guarded confirm attempt, observes once, and never claims healing',async()=>{
  let now=2000000,clicks=0,reads=0;
  const result=await mission.runQuestStep('wolfFeedKaeya',modal(),{now:()=>now,wolfFeedKaeyaReady:o=>!!bgi.wolfFeedKaeyaTarget(o,now),
    wolfFeedKaeya:async()=>clicks++,sleep:async ms=>{assert.equal(ms,500);now+=ms;}},async()=>{reads++;return {...modal({timestamp:now}),frameId:19};});
  assert.equal(clicks,1);assert.equal(reads,1);assert.equal(result.status,'stopped');assert.equal(result.foodUseAttempts,1);
  assert.equal(result.foodUseAttempted,true);assert.equal(result.healingVerified,false);
});

test('mission rejects missing, stale, wrong food or wrong character before any click',async()=>{
  for(const initial of [modal({timestamp:1998999}),modal({item:'Teyvat Fried Egg'}),modal({heading:'Traveler'}),modal({quantity:null})]) {
    let clicks=0,reads=0;
    const result=await mission.runQuestStep('wolfFeedKaeya',initial,{wolfFeedKaeyaReady:o=>!!bgi.wolfFeedKaeyaTarget(o,2000000),wolfFeedKaeya:async()=>clicks++,sleep:async()=>{}},async()=>{reads++;return initial;});
    assert.equal(result.status,'stopped');assert.equal(result.foodUseAttempts,0);assert.equal(clicks,0);assert.equal(reads,0);
  }
});

function adapterHarness({entry=true,requestStep='wolfFeedKaeya',digits=['1']}={}) {
  let now=2000000;const clicks=[],captures=[];
  const rows=[row('Food',140,32,67,31),row('Sweet Madame',1332,127,263,41),row('Kaeya',891,259,136,59),row('Amount to use',639,611,217,39),row('Cancel',716,748,109,37),row('Confirm',1118,750,129,37)];
  const party={session:'wolf',mission:'questStep',status:'completed',timestamp:1999500,details:{result:{step:'wolfPartyStart'},inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:20,x:1705,y:1019,startedAt:1999400}]}};
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:()=>false,readTextSync:p=>p==='reports/wolf.json'?JSON.stringify(entry?[party]:[]):fs.readFileSync(path.join(root,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:(x,y,w,h)=>({x,y,w,h})},OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:c=>c,contourArea:()=>0}}},ImageRegion:class{constructor(mat){this.mat=mat;this.width=mat&&mat.kind==='quantity'?240:1920;this.height=mat&&mat.kind==='quantity'?240:1080;}findMulti(){const a=this.mat&&this.mat.kind==='quantity'?digits.map((text,i)=>({text,x:90+i,y:75,width:18,height:30})):[];a.count=a.length;return a;}dispose(){}},
    captureGameRegion:()=>{captures.push('capture');return {width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows.map(r=>({...r}));a.count=a.length;return a;},deriveCrop:(x,y,w,h)=>({srcMat:{resize:()=>({kind:x===1105?'quantity':'other'})},dispose(){}}),dispose(){}};},
    keyDown(){},keyUp(){},sleep:async ms=>{now+=ms;},click:(x,y)=>clicks.push([x,y]),log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);adapter.beginMission({mission:'questStep',step:requestStep,session:'wolf',createdAt:1999999});
  return {adapter,clicks,captures,observe:()=>adapter.observe('wolf',1),advance:ms=>{now+=ms;}};
}

test('adapter reads quantity from same-frame crop and allows exactly one fixed Confirm click with entry proof',async()=>{
  const h=adapterHarness();const o=await h.observe();
  assert.equal(o.hud.foodQuantity.value,1);assert.equal(o.hud.foodQuantity.source,'scaled-same-frame');assert.equal(o.hud.foodQuantity.frameId,1);
  assert.equal(o.hud.foodQuantity.x,1135);assert.equal(o.hud.foodQuantity.y,615);
  assert.equal(h.adapter.wolfFeedKaeyaReady(o),true);h.adapter.wolfFeedKaeya();assert.deepEqual(h.clicks,[[1183,769]]);
  assert.throws(()=>h.adapter.wolfFeedKaeya());assert.deepEqual(h.clicks,[[1183,769]]);
  assert.equal(h.adapter.events().filter(e=>e.type==='wolfFeedKaeya').length,1);
});

test('adapter rejects ambiguous quantity, absent proof, stale frame, or wrong request with zero clicks',async()=>{
  for(const opts of [{digits:['1','1']},{digits:['2']},{entry:false},{requestStep:'wolfSelectKaeyaFood'}]) {
    const h=adapterHarness(opts);const o=await h.observe();
    if(opts.digits) assert.equal(h.adapter.wolfFeedKaeyaReady(o),false);
    if(opts.entry===false||opts.requestStep) assert.throws(()=>h.adapter.wolfFeedKaeya());
    assert.deepEqual(h.clicks,[]);
  }
  const stale=adapterHarness();const o=await stale.observe();stale.advance(1001);
  assert.equal(stale.adapter.wolfFeedKaeyaReady(o),false);assert.throws(()=>stale.adapter.wolfFeedKaeya());assert.deepEqual(stale.clicks,[]);
});
