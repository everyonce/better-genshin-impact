const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const recovery=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/recovery.js');

const packageDir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const bgiSource=fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8');
const wet='If there is water around, opponents may become Wet';
const ocr=(text,x,y,width,height)=>({text,x,y,width,height});
function harness({caption=wet,captionRow=null,tutorialRows=null,proof=true,proofSession='test',mission='recover',postRows=false}={}) {
  let clock=2000000,frame=25,dismissed=false,observationCount=0;
  const partyCrops=[],controlCrops=[];
  const clicks=[],party={session:proofSession,mission:'questStep',status:'completed',details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[
    {type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:22,x:1705,y:1019,startedAt:1999000}
  ]}};
  const rows=[...(tutorialRows||[captionRow||ocr(caption,567,782,775,37)]),ocr('1427/1427',910,1000,100,25),ocr('E',1689,1028,18,21),ocr('Q',1802,1025,31,27)];
  const freezeRows=[ocr('Cryo skills can freeze water, Hydro opponents, or opponents that are Wet',422,786,1073,35),
    ocr('Utilize this elemental reaction to gain an advantage over your opponents.',427,816,1059,42),ocr('1427/1427',910,1000,100,25)];
  const nextRows=[ocr('Lumina',1682,304,81,23),ocr('Amber',1690,393,69,23),ocr('626/1427',910,1000,100,25)];
  const partyRows=[ocr('Kaeya',150,150,225,96),ocr('Trial',450,120,150,60)];
  function activeRows(){return dismissed&&postRows&&observationCount===2?freezeRows:dismissed&&postRows&&observationCount>=3?nextRows:rows;}
  const context={
    Date:class extends Date{static now(){return clock;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:()=>false,readTextSync:p=>p==='reports/test.json'?JSON.stringify(proof?[party]:[]):fs.readFileSync(path.join(packageDir,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const src=this.mat&&this.mat.kind==='control'?[ocr('E',600,130,54,63)]:this.mat&&this.mat.kind==='party'?partyRows:this.mat&&this.mat.kind==='health'?[ocr('626/1427',0,0,90,25)]:activeRows();const a=src.map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:c=>c,contourArea:()=>0}}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=activeRows().map(r=>({...r}));a.count=a.length;return a;},deriveCrop:(x,y,w,h)=>{const kind=x===1630?'party':x===1520?'control':x===900?'health':'other';if(kind==='party')partyCrops.push([x,y,w,h]);if(kind==='control')controlCrops.push([x,y,w,h]);return {srcMat:{resize:()=>({kind}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}};},dispose(){}}),
    sleep:async()=>{},click:(x,y)=>{clicks.push([x,y]);dismissed=true;},keyDown(){},keyUp(){},log:{info(){}}
  };
  vm.runInNewContext(bgiSource,context);
  const adapter=context.createActOneAdapter(7);
  adapter.beginMission({mission,session:'test',createdAt:clock});
  async function observe(){observationCount++;return adapter.observe('test',++frame);}
  return {adapter,clicks,observe,partyCrops,controlCrops,api:{checkStop:()=>adapter.checkStop(),wolfInfoReady:()=>adapter.wolfInfoReady(),recoverWolfInfo:()=>adapter.recoverWolfInfo(),sleep:ms=>adapter.sleep(ms)},advance:ms=>{clock+=ms;}};
}

test('recover dismisses exactly one fresh verified periodless Wet slide and reports the next screen for inspection',async()=>{
  const h=harness(),first=await h.observe();
  assert.equal(first.hud.tutorialStep,'wolfInfo');
  const result=await recovery.run(first,h.api,h.observe);
  assert.equal(result.status,'completed');assert.equal(result.clicks,1);
  assert.match(result.reason,/inspect the fresh next screen/);
  assert.deepEqual(h.clicks,[[960,900]]);
  assert.equal(h.adapter.events().filter(e=>e.type==='wolfInfoRecoveryDismiss').length,1);
  assert.throws(()=>h.adapter.recoverWolfInfo(),/Fresh exact Wolf tutorial required/);
  assert.deepEqual(h.clicks,[[960,900]]);
});

test('recover recognizes the measured flamethrower-core tutorial and dismisses only once',async()=>{
  const caption="A flamethrower's core is what gives it the energy to shoot fire";
  const h=harness({captionRow:ocr(caption,502,784,905,35)}),first=await h.observe();
  assert.equal(first.hud.tutorialStep,'wolfInfo');
  assert.equal(h.api.wolfInfoReady(),true);
  const result=await recovery.run(first,h.api,h.observe);
  assert.equal(result.status,'completed');assert.equal(result.clicks,1);
  assert.deepEqual(h.clicks,[[960,900]]);
  assert.equal(h.adapter.events().filter(e=>e.type==='wolfInfoRecoveryDismiss').length,1);
});

test('recover recognizes only the measured two-line flamethrower-disable caption and dismisses once',async()=>{
  const pair=[ocr("Use Cryo Skills to temporarily disable flamethrowers' cores and stop them",420,784,1079,35),
    ocr('from shooting fire.',820,820,277,35)];
  const h=harness({tutorialRows:pair}),first=await h.observe();
  assert.equal(first.hud.tutorialStep,'wolfInfo');assert.equal(h.api.wolfInfoReady(),true);
  const result=await recovery.run(first,h.api,h.observe);
  assert.equal(result.status,'completed');assert.equal(result.clicks,1);
  assert.deepEqual(h.clicks,[[960,900]]);
  assert.equal(h.adapter.events().filter(e=>e.type==='wolfInfoRecoveryDismiss').length,1);
});

test('cold, stale, unknown-caption, wrong-session-entry, and non-recover requests cannot dismiss Wolf info',async()=>{
  for(const options of [
    {proof:false},
    {caption:wet+'!'},
    {mission:'observe'},
    {proofSession:'other-session'}
  ]) {
    const h=harness(options),first=await h.observe();
    if(options.proof===false||options.caption||options.mission==='observe') {
      if(options.proof===false||options.proofSession) assert.equal(h.adapter.wolfInfoReady(),false);
      const result=await recovery.run(first,h.api,h.observe);
      assert.notEqual(result.reason,'One verified Wolf tutorial slide dismissed; inspect the fresh next screen');
      assert.deepEqual(h.clicks,[]);
    }
  }
  const stale=harness(),first=await stale.observe();stale.advance(1001);
  assert.equal(stale.adapter.wolfInfoReady(),false);
  assert.throws(()=>stale.adapter.recoverWolfInfo(),/Fresh exact Wolf tutorial required/);
  assert.deepEqual(stale.clicks,[]);
});

test('same-entry recover observation crops missing post-slide Trial, Kaeya, and E controls before recognizing safe Wolf HUD',async()=>{
  const h=harness({postRows:true}),first=await h.observe();
  await recovery.run(first,h.api,h.observe); // The exact Freeze slide is still present on the fresh post-click frame.
  assert.deepEqual(h.partyCrops,[]);assert.deepEqual(h.controlCrops,[]);
  const after=await h.observe();
  assert.equal(after.hud.tutorialStep,null);
  assert.equal(after.hud.health.current,626);
  assert.equal(after.hud.groundControls,true);
  assert.deepEqual(h.partyCrops,[[1630,330,230,300]]);
  assert.deepEqual(h.controlCrops,[[1520,985,390,80]]);
  const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
  assert.equal(bgi.wolfDomainHud(after,2000000,0),true,'positive-HP pause evidence accepts the OCR-corroborated crop');
  assert.equal(bgi.wolfDomainHud(after,2000000,0.6),false,'ordinary movement remains blocked below 60% HP');
});
