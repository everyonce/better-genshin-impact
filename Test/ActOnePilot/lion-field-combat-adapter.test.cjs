'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const dir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=100,height=28)=>({text,x,y,width,height});
const inventoryRows=()=>[
  row('Food',140,32,67,31),row('Inventory capacity 9/2600',1504,34,295,27),
  row('Teyvat Fried Egg',1329,119,297,57),row('Food',1374,187,63,30),row('Use',1670,999,63,38)
];
// Sanitized map anchors from the recorded r15 frame 1221; personal identifiers and unrelated OCR are omitted.
const windriseMap1221Rows=()=>[
  row('Mondstadt',410,2,149,15),row('200/200',1624,32,119,29),row('Thousand Winds',1344,83,239,29),
  row('Temple',1413,117,112,35),row('Windrise',890,441,135,34),row('Galesong Hill',1604,983,191,42),
  row('Exploration Progress: 0%',1505,1016,289,37)
];
const pausedLisaPosition={x:-1348.496,y:1815.992,cameraAngle:87};
function pausedLisaProbeFiles(now=10000,patch={}){
  const session='lion-adapter-test',expectedFrameId=40,fieldFrameId=19,pauseFrameId=21;
  const receiptId='mission-0123456789abcdef0123456789abcdef';
  const field={session,frameId:fieldFrameId,timestamp:now-500,map:{map:'Teyvat',...pausedLisaPosition},
    hud:{world:true,groundControls:true,climbing:false,auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,
      tutorialStep:null,objectiveChanged:false,unknownHud:false,health:{current:876,max:1186},objectives:['Meet Lisa at the temple'],enemyBars:[]},
    ocr:[row('Meet Lisa at the temple',80,250,300,35),row('Kaeya',1660,500,80,35),row('3',1860,500,25,35)]};
  const food=inventoryRows();
  const paused={session,frameId:pauseFrameId,timestamp:now-300,map:null,
    hud:{auto:false,dialogueReady:false,world:false,health:null},ocr:food};
  const proof={verified:true,session,sourceFrameId:20,pauseFrameId,timestamp:paused.timestamp,kind:'inventory',
    evidence:[food[0],food[1]]};
  const result={status:'completed',step:'lisaNavigation',fieldFrameId,fieldPosition:field.map,fieldHealth:{current:876,max:1186},
    pauseVerified:true,pauseProof:proof,questComplete:false,destinationReached:true,navigationStatus:'arrived'};
  const marker={kind:'pausedLisaPositionProbe',session,frameId:expectedFrameId,witnessVerified:true,receiptId,createdAt:now-100};
  const receipt={id:receiptId,mission:'navigation',status:'completed',session,timestamp:now-200,details:{result}};
  return {'paused-lisa-position-probe.json':{...marker,...(patch.marker||{})},
    [`receipts/${session}/${receiptId}.json`]:{...receipt,...(patch.receipt||{})},
    [`observations/${session}/frame-${String(fieldFrameId).padStart(4,'0')}.json`]:{...field,...(patch.field||{})},
    [`observations/${session}/frame-${String(fieldFrameId).padStart(4,'0')}.png`]:'sanitized-historic-field',
    [`observations/${session}/frame-${String(pauseFrameId).padStart(4,'0')}.json`]:{...paused,...(patch.paused||{})},
    [`observations/${session}/frame-${String(pauseFrameId).padStart(4,'0')}.png`]:'sanitized-historic-food-pause'};
}
function climbHudRows(options={}){
  const rows=[row(options.objectiveText||'Meet Lisa at the temple',80,250,300,35),row(options.healthText||'876/1186',900,1002,120,24),
    row('Amber',1680,415,80,35),row(options.kaeyaText||'Kaeya',1660,500,80,35),row(options.slotText||'3',1860,500,25,35),
    row(options.xText||'X',1594,1022,31,31),row(options.spaceText||'Space',1680,1024,69,31)];
  if(options.duplicateX)rows.push(row('X',1600,1022,31,31));
  if(options.duplicateSpace)rows.push(row('Space',1690,1024,69,31));
  if(options.extra)rows.push(...options.extra);
  return rows;
}
function pausedLisaClimbProbeFiles(now=10000,patch={}){
  const files=pausedLisaProbeFiles(now),session='lion-adapter-test',sourceFrameId=20,proofFrameId=21;
  const marker={...files['paused-lisa-position-probe.json'],releaseClimb:true};
  const receipt=files[`receipts/${session}/${marker.receiptId}.json`];
  receipt.details.result.navigationStatus='stopped';receipt.details.result.reason='Lisa navigation refuses climbing';
  receipt.details.result.pauseProof.sourceFrameId=sourceFrameId;
  receipt.details.result.pauseProof.pauseFrameId=proofFrameId;
  receipt.details.result.pauseProof.timestamp=now-300;
  const source={session,frameId:sourceFrameId,timestamp:now-400,map:{map:'Teyvat',...pausedLisaPosition},
    hud:{world:true,groundControls:false,climbing:true,auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,
      objectiveChanged:false,tutorialStep:null,unknownHud:false,health:{current:876,max:1186},objectives:['Meet Lisa at the temple'],enemyBars:[]},ocr:climbHudRows()};
  return {...files,'paused-lisa-position-probe.json':{...marker,...(patch.marker||{})},
    [`receipts/${session}/${marker.receiptId}.json`]:{...receipt,...(patch.receipt||{})},
    [`observations/${session}/frame-${String(sourceFrameId).padStart(4,'0')}.json`]:{...source,...(patch.climbSource||{})},
    [`observations/${session}/frame-${String(sourceFrameId).padStart(4,'0')}.png`]:patch.climbPng===false?undefined:'sanitized-historic-climb'};
}
const fieldRows=(options={})=>{
  const rows=[row(options.objectiveText||'Meet Lisa at the temple',80,250,300,35)];
  if(!options.noPauseHud)rows.push(row('R',1580,1004,30,30),row(options.healthText||'1186/1186',900,1002,120,24));
  if(!options.noPauseHud&&!options.omitPartyLabels)rows.push(row('Amber',1680,415,80,35));
  if(!options.noPauseHud&&!options.omitControls)rows.push(row('Q',1660,1004,30,30));
  if(!options.noPauseHud&&!options.omitPartyLabels&&options.kaeya!==false)rows.push(row(options.kaeyaText||'Kaeya',1660,500,80,35));
  if(!options.noPauseHud&&options.slot!==false)rows.push(row(options.slotText||'3',1860,500,25,35));
  if(options.duplicateSlot)rows.push(row('3',1875,505,20,25));
  if(options.duplicateKaeya)rows.push(row('Kaeya',1700,500,80,35));
  if(options.trial)rows.push(row('Trial',1750,480,70,30));
  if(options.tutorial)rows.push(row('Press 2 to switch to Amber',700,800,320,35),row('Use Amber to defeat the airborne Anemo Slime',700,840,500,35));
  if(options.unknownUi)rows.push(row('Confirm',850,550,120,40));
  if(options.extra)rows.push(...options.extra);
  return rows;
};
const scaledPartyRows=()=>[row('Amber',150,60,300,105),row('Kaeya',150,510,300,105)];
function fixture(options={}){
  let now=options.startNow||10000,frame=options.initialFrame||options.expectedFrameId||1,screen=options.initialScreen||'inventory',written=[],lastRows=[];
  let foreground=true,observerCalls=0,fieldCaptureCount=0,bDownCount=0,escapeDownCount=0,escapeKeyUpAttempts=0,xDownCount=0,xKeyUpAttempts=0,activeInputKey=null,
    unknownCaptureCount=0,noHudCaptureCount=0,paimonCaptureCount=0,blockedCaptureCount=0,foreignCaptureCount=0,invalidObservationCount=0;
  const inputs=[],events=[],nativeCalls=[],virtualFiles=new Map(),overlappingKeyDowns=[],mapQueries=[],mapQueryFrames=[],observations=[],metrics={mapCalls:0,captures:0,partyCropCalls:0,controlCropCalls:0,slotCropCalls:0,focusCalls:0,orientationCalls:0};
  const removedFiles=new Set(options.removeSeedFiles||[]);
  for(const [p,v] of Object.entries(options.seedFiles||{}))virtualFiles.set(p,typeof v==='string'?v:JSON.stringify(v));
  for(const p of removedFiles)virtualFiles.delete(p);
  const redBar=options.noEnemy?[]:[{x:500,y:250,width:90,height:8}];
  function mat(rect=null){return {rect,inRange(){const enemy=rect&&rect.x===350&&rect.y===100&&rect.w===1250&&rect.h===800;
    return {findContoursAsArray(){return enemy?redBar.map(b=>({...b})):[];},dispose(){}};},resize(){return mat(rect);},dispose(){}};}
  let cancelNative=null;
  const files={
    isExists:p=>!removedFiles.has(p)&&(virtualFiles.has(p)||fs.existsSync(path.join(dir,p))),
    readTextSync:p=>{
      if(removedFiles.has(p))throw new Error('mock file missing');
      if(options.corruptProbeReadback&&p==='paused-lisa-position-probe.json'&&written.includes(p)){
        const saved=JSON.parse(virtualFiles.get(p));saved.usedAt=Number(saved.usedAt)+1;return JSON.stringify(saved);
      }
      if(options.corruptClimbReadback&&p==='reports/lion-adapter-test.lisa-climb-release.json'&&written.includes(p)){
        const saved=JSON.parse(virtualFiles.get(p));saved.releaseAttempted=false;return JSON.stringify(saved);
      }
      return virtualFiles.has(p)?virtualFiles.get(p):fs.readFileSync(path.join(dir,p),'utf8');
    },
    writeTextSync:(p,v)=>{written.push(p);if(options.failWritePath===p)return false;virtualFiles.set(p,v);
      if(p==='paused-lisa-position-probe.json'&&options.advanceAfterProbeWrite)now+=options.advanceAfterProbeWrite;
      if(p==='reports/lion-adapter-test.lisa-climb-release.json'&&options.advanceAfterClimbWrite)now+=options.advanceAfterClimbWrite;return true;},
    writeImageSync:()=>true
  };
  class AutoFightParam{constructor(name){this.Name=name;this.Timeout=0;this.PickDropsAfterFightEnabled=true;}}
  const cts=()=>({Token:{},Cancel(){nativeCalls.push('cancel');if(cancelNative)cancelNative('cancelled');},Dispose(){nativeCalls.push('dispose');}});
  const dispatcher={GetLinkedCancellationTokenSource(){nativeCalls.push('linked');return cts();},
    RunAutoFightTask(param,token){nativeCalls.push({kind:'fight',name:param.Name,timeout:param.Timeout,pickDrops:param.PickDropsAfterFightEnabled,token});
      if(options.stopAfterNative)virtualFiles.set('stop.json',JSON.stringify({session:'lion-adapter-test',createdAt:9000}));
      if(options.loseFocusAfterNative)foreground=false;
       if(options.partyAfterNative)screen='party';
      if(options.nativeTimeout)return new Promise(resolve=>{cancelNative=resolve;});
      return options.nativeFailure?Promise.reject(new Error('mock native failure')):Promise.resolve('done');}};
  const context={Date:class extends Date{static now(){return now;}},file:files,AutoFightParam,dispatcher,host:{toSingle:v=>v},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:5,get isGameForeground(){return foreground;},async focusGame(){metrics.focusCalls++;if(!options.refuseFocusRecovery)foreground=true;},
      getPositionFromMap(...args){metrics.mapCalls++;mapQueries.push(args);mapQueryFrames.push({frame,fieldCaptureCount});if(options.throwGps||options.throwGpsAt===metrics.mapCalls)throw new Error('mock GPS failure');
        if(options.mapPositionSequence)return options.mapPositionSequence[Math.min(metrics.mapCalls-1,options.mapPositionSequence.length-1)];
        return options.mapPosition||{map:'Teyvat',x:1,y:2};},getCameraOrientation(){metrics.orientationCalls++;return 0;}},
    RecognitionObject:{Ocr:(x,y,w,h)=>({x,y,w,h})},
    captureGameRegion(){metrics.captures++;const fought=nativeCalls.some(x=>x&&x.kind==='fight');
      if(screen==='inventory')lastRows=inventoryRows();
      else if(screen==='map')lastRows=options.mapRows||windriseMap1221Rows();
      else if(screen==='journal')lastRows=[row('In Progress',130,45,120,30),row('Archon Quests',130,120,180,35)];
       else if(screen==='party')lastRows=[row('Party Setup',120,80,170,35),row('Deploy',1600,980,120,35)];
      else if(screen==='paimon')lastRows=options.paimonRows||[row('Adventure Rank',120,100,180,35),row('World Level',120,150,180,35),row('Shop',80,300,100,35),row('Party Setup',80,360,150,35)];
      else if(fought&&options.postFightInvalid==='unknown')lastRows=[row('Auto',50,50),row('Kaeya',900,850),row('A dialogue begins here',800,920,350,35)];
      else if(fought&&options.postFightInvalid==='trial')lastRows=fieldRows({...options,trial:true});
      else if(fought&&options.postFightInvalid==='zeroHp')lastRows=fieldRows({...options,healthText:'0/1186'});
      else if(screen==='field'&&options.fieldRowsSequence){fieldCaptureCount++;lastRows=options.fieldRowsSequence[Math.min(fieldCaptureCount-1,options.fieldRowsSequence.length-1)].map(r=>({...r}));}
      else {if(screen==='field')fieldCaptureCount++;lastRows=fieldRows(options);}
      if(screen==='paimon')paimonCaptureCount++;
      if(screen==='field'&&fought&&options.postFightInvalid==='unknown')unknownCaptureCount++;
      if(screen==='field'&&options.noPauseHud)noHudCaptureCount++;
      if(screen==='field'&&(options.tutorial||options.unknownUi))blockedCaptureCount++;
      return {width:1920,height:1080,srcMat:mat(),findMulti(ro){const a=lastRows.filter(r=>r.x>=ro.x&&r.x<ro.x+ro.w&&r.y>=ro.y&&r.y<ro.y+ro.h).map(r=>({...r}));a.count=a.length;return a;},
        deriveCrop(x,y,w,h){if(x===1630&&y===330&&w===230)metrics.partyCropCalls++;if(x===1520&&y===985)metrics.controlCropCalls++;
          if(x===1845&&y===475&&w===60&&h===65)metrics.slotCropCalls++;
          return {srcMat:mat({x,y,w,h}),dispose(){}};},dispose(){}};},
    ImageRegion:class{constructor(srcMat){this.srcMat=srcMat;}findMulti(ro){const rect=this.srcMat.rect;
      const party=rect&&rect.x===1630&&rect.y===330&&rect.w===230;
      const control=rect&&rect.x===1520&&rect.y===985;
      const slot=rect&&rect.x===1845&&rect.y===475&&rect.w===60&&rect.h===65;
      const fieldIndex=Math.max(0,fieldCaptureCount-1);
      const partyRows=options.partyCropRowsByField?options.partyCropRowsByField[Math.min(fieldIndex,options.partyCropRowsByField.length-1)]:options.partyCropRows;
      const slotRows=options.slotCropRowsByField?options.slotCropRowsByField[Math.min(fieldIndex,options.slotCropRowsByField.length-1)]:options.slotCropRows;
      const rows=party?(partyRows===undefined?scaledPartyRows():partyRows):control?(options.controlCropRows||[]):slot?(slotRows||[]):[];
      const a=rows.filter(r=>r.x>=ro.x&&r.x<ro.x+ro.w&&r.y>=ro.y&&r.y<ro.y+ro.h).map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},
      ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:b=>b,contourArea:()=>0,countNonZero:()=>0},ColorConversionCodes:{GRAY2BGR:0,BGR2HSV:1}}},
    keyDown(key){inputs.push({kind:'down',key,frame,at:now});
      if(activeInputKey)overlappingKeyDowns.push({held:activeInputKey,next:key,frame,at:now});
      activeInputKey=key;
      if(key==='VK_ESCAPE'){
        escapeDownCount++;
        if(options.throwCloseKeyDown&&escapeDownCount===1)throw new Error('mock Escape keydown failed');
         screen=nativeCalls.some(x=>x&&x.kind==='fight')&&options.fallbackScreen?options.fallbackScreen:
           (nativeCalls.some(x=>x&&x.kind==='fight')&&options.paimonOnFallbackEscape?'paimon':'field');
        if(options.stopAfterClose)virtualFiles.set('stop.json',JSON.stringify({session:'lion-adapter-test',createdAt:9000}));
      }
      if(key==='VK_3'){
        if(options.stopAfterSelect)virtualFiles.set('stop.json',JSON.stringify({session:'lion-adapter-test',createdAt:9000}));
        if(options.throwSelectionKeyDown)throw new Error('mock VK_3 keydown failed');
      }
      if(key==='VK_X'){
        xDownCount++;
        if(options.stopAfterX)virtualFiles.set('stop.json',JSON.stringify({session:'lion-adapter-test',createdAt:9000}));
        if(options.loseFocusAfterX)foreground=false;
        if(options.throwXKeyDown&&xDownCount===1)throw new Error('mock VK_X keydown failed');
      }
      if(key==='VK_2'&&options.throwAmberReturn)throw new Error('mock VK_2 keydown failed');
      if(key==='VK_B'){
        bDownCount++;
        if(options.throwBCount&&bDownCount<=options.throwBCount)throw new Error('mock VK_B keydown failed');
        if(options.silentBCount&&bDownCount<=options.silentBCount)return;
        if(options.blockPauseB)return;
        if(!(nativeCalls.some(x=>x&&x.kind==='fight')&&options.postFightInvalid==='unknown'))screen='inventory';
      }
      if(key==='VK_J'){if(!options.silentJ)screen='journal';}
    },
    keyUp(key){inputs.push({kind:'up',key,frame,at:now});if(key==='VK_ESCAPE'){escapeKeyUpAttempts++;if(options.throwEscapeKeyUpCount&&escapeKeyUpAttempts<=options.throwEscapeKeyUpCount)throw new Error('mock Escape key-up failed');}
      if(key==='VK_X'){xKeyUpAttempts++;if(options.throwXKeyUpCount&&xKeyUpAttempts<=options.throwXKeyUpCount)throw new Error('mock VK_X key-up failed');}
      if(activeInputKey===key)activeInputKey=null;},moveMouseBy(){},click(){},
    sleep:async ms=>{await new Promise(resolve=>setImmediate(resolve));now+=ms;},log:{info(){}}
  };
  vm.runInNewContext(fs.readFileSync(path.join(dir,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(5);
  const request={mission:'questStep',step:options.step||'lionFieldCombat',session:'lion-adapter-test',id:'lion-adapter-1',expectedFrameId:options.expectedFrameId||options.initialFrame||1,
    createdAt:9000,objective:'Meet Lisa at the temple'};
  adapter.beginMission(request);
  async function observe(){
    observerCalls++;
    if(options.throwObserveCount&&observerCalls<=options.throwObserveCount)throw new Error('mock capture failure');
    if(options.throwAfterInventoryPauseCapture&&screen==='inventory'&&bDownCount>0&&!options.inventoryPauseCaptureThrown){options.inventoryPauseCaptureThrown=true;throw new Error('mock pause verification capture failure');}
    frame++;now+=10;const foreign=options.crossSessionFirstField&&screen==='field'||options.crossSessionAfterFight&&nativeCalls.some(x=>x&&x.kind==='fight')||options.crossSessionAfterX&&xDownCount>0;
    const session=foreign?'other-session':'lion-adapter-test';
    if(foreign)foreignCaptureCount++;
    const nonfresh=options.nonfreshObserve&&(typeof options.nonfreshObserve!=='number'||observerCalls<=options.nonfreshObserve);
    const result=await adapter.observe(session,nonfresh?(typeof options.nonfreshObserve==='number'?1:frame-1):frame);
    if(nonfresh)invalidObservationCount++;
    if(options.staleObserve&&(typeof options.staleObserve!=='number'||observerCalls<=options.staleObserve)){result.timestamp=now-1501;invalidObservationCount++;}
    observations.push(result);
    return result;}
  async function run(){const initial=await adapter.observe('lion-adapter-test',request.expectedFrameId);if(options.staleInitial)initial.timestamp=now-1501;return adapter.runLionFieldCombat(initial,observe);}
  return {adapter,context,inputs,events,nativeCalls,metrics,mapQueries,mapQueryFrames,observations,run,observe,getNow:()=>now,setScreen:v=>{screen=v;},getScreen:()=>screen,
    lastRows:()=>lastRows,setFlag:(k,v)=>{options[k]=v;},setForeground:v=>{foreground=v;},getForeground:()=>foreground,
    getObserverCalls:()=>observerCalls,getEscapeKeyUpAttempts:()=>escapeKeyUpAttempts,getOverlappingKeyDowns:()=>overlappingKeyDowns,
    getUnknownCaptureCount:()=>unknownCaptureCount,getNoHudCaptureCount:()=>noHudCaptureCount,getPaimonCaptureCount:()=>paimonCaptureCount,
    getBlockedCaptureCount:()=>blockedCaptureCount,getForeignCaptureCount:()=>foreignCaptureCount,getInvalidObservationCount:()=>invalidObservationCount,
    getVirtualFiles:()=>virtualFiles,cancelNative:()=>{if(cancelNative)cancelNative('unwound');}};
}

function assertPauseProof(result){
  assert.equal(result.pauseVerified,true,JSON.stringify(result));
  const proof=result.pauseProof;
  assert.ok(proof&&proof.verified===true);
  assert.equal(proof.session,'lion-adapter-test');
  assert.ok(Number.isInteger(proof.sourceFrameId));
  assert.ok(Number.isInteger(proof.pauseFrameId)&&proof.pauseFrameId>proof.sourceFrameId);
  assert.ok(Number.isFinite(proof.timestamp));
  assert.ok(['inventory','journal','domain','menu','party','map'].includes(proof.kind));
  assert.ok(Array.isArray(proof.evidence)&&proof.evidence.length>0);
  assert.equal(result.frameId,proof.pauseFrameId);
}
function pauseProtectionStarted(f){return f.adapter.events().some(e=>e.type==='pauseProtectionStarted');}
async function waitUntil(predicate,label){
  const deadline=Date.now()+5000;
  while(!predicate()){
    if(Date.now()>deadline)throw new Error(`timed out waiting for ${label}`);
    await new Promise(resolve=>setImmediate(resolve));
  }
}
async function remainsPendingUntil(promise,restore,ready,label='blocked guardian state'){
  let outcome='pending';promise.then(x=>{outcome={status:'resolved',value:x};},e=>{outcome={status:'rejected',error:String(e)};});
  await waitUntil(ready,label);
  assert.equal(outcome,'pending',`must not return without a verified pause: ${JSON.stringify(outcome)}`);
  restore();
  return await Promise.race([promise,new Promise((_,reject)=>setTimeout(()=>reject(new Error('pause guardian did not recover')),5000))]);
}
test('valid known Lisa field closes Food, selects slot 3 once, runs native fight once, then verifies Food pause',async()=>{
  const f=fixture({kaeya:false,omitControls:true,controlCropRows:[row('Q',420,57,90,90)],objectiveText:'Meet.Lisa at the temple'});const result=await f.run();
  assert.equal(result.fightStarted,true,JSON.stringify({result,inputs:f.inputs,events:f.adapter.events()}));assert.equal(result.enemyClearVerified,false);assertPauseProof(result);
  assert.equal(result.amberReturnAttempted,false);
  assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_ESCAPE','VK_3','VK_B']);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_ESCAPE').length,1);
  const events=f.adapter.events();
  assert.equal(events.find(e=>e.type==='lionFieldInventoryClose').finishedAt-events.find(e=>e.type==='lionFieldInventoryClose').startedAt,360);
  const select=events.find(e=>e.type==='lionFieldKaeyaSelectAttempt'),fightEvent=events.find(e=>e.type==='lionFieldNativeFight');
  assert.ok(fightEvent.frameId>select.frameId,'native fight begins only from a distinct post-selection capture');
  assert.equal(events.some(e=>e.type==='lionFieldAmberReturnAttempt'),false);
  const fight=f.nativeCalls.filter(x=>x&&x.kind==='fight');assert.equal(fight.length,1);
  assert.equal(fight[0].timeout,15);assert.equal(fight[0].pickDrops,false);assert.equal(fight[0].name,'English Starter Trials');
  assert.ok(f.nativeCalls.includes('dispose'));assert.equal(f.metrics.mapCalls,0);assert.ok(f.metrics.partyCropCalls>0);
  assert.equal(f.adapter.events().filter(e=>e.type==='lionFieldNativeFight').length,1);
  assert.equal(f.adapter.events().find(e=>e.type==='lionFieldNativeFight').timeoutMs,15000);
  const replay=await f.run();assert.equal(replay.fightStarted,false);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,1);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,1);
  assert.equal(f.inputs.filter(x=>x.kind==='down').length,3,'replay sends no additional Escape, selection, or pause input');
});

test('lionFieldProbe closes Food, captures field evidence, and performs no combat or party selection',async()=>{
  const f=fixture({step:'lionFieldProbe'});const result=await f.run();
  assert.equal(result.step,'lionFieldProbe');
  assert.equal(result.fightStarted,false);assert.equal(result.kaeyaSelectAttempted,false);
  assert.equal(result.amberReturnAttempted,false);assert.equal(result.enemyClearVerified,false);
  assertPauseProof(result);
  assert.ok(result.fieldProbe);
  assert.ok(Number.isInteger(result.fieldProbe.frameId));
  assert.equal(result.fieldProbe.health.current,1186);assert.equal(result.fieldProbe.health.max,1186);
  assert.ok(result.fieldProbe.objectives.some(x=>String(x).replace(/[^a-z0-9]/gi,'').toLowerCase()==='meetlisaatthetemple'));
  assert.equal(result.fieldProbe.enemyBars.length,1);
  assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_ESCAPE','VK_B']);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);
});

test('lionFieldProbe refusal from an already-open safe field skips Escape and combat, then verifies a guardian pause',async()=>{
  const f=fixture({step:'lionFieldProbe',initialScreen:'field'});const result=await f.run();
  assertPauseProof(result);
  assert.match(String(result.reason||''),/Food inventory/i);
  assert.equal(result.fieldProbe,undefined);
  assert.equal(result.fightStarted,false);assert.equal(result.kaeyaSelectAttempted,false);
  assert.equal(result.amberReturnAttempted,false);assert.equal(result.enemyClearVerified,false);
  assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_B']);
  assert.equal(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_ESCAPE'),false);
  assert.equal(f.inputs.some(x=>x.kind==='down'&&(x.key==='VK_3'||x.key==='VK_2')),false);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);
});

test('an unknown initial field HUD is refused without any input or false pause claim',async()=>{
  const f=fixture({step:'lionFieldProbe',initialScreen:'field',unknownUi:true});
  const result=await f.run();
  assert.notEqual(result.pauseVerified,true);
  assert.deepEqual(f.inputs.filter(x=>x.kind==='down'),[]);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);
});

test('a prior verified Windrise chart marker authorizes one anchored GPS read from Food',async()=>{
  const revealFrameId=9,createdAt=9500,marker={kind:'windriseCharted',session:'lion-adapter-test',witnessVerified:true,revealFrameId,createdAt};
  const mapFrame={session:'lion-adapter-test',frameId:revealFrameId,timestamp:9400,hud:{bigMap:true},ocr:windriseMap1221Rows()};
  const seedFiles={'windrise-charted.json':marker,[`observations/lion-adapter-test/frame-${String(revealFrameId).padStart(4,'0')}.json`]:mapFrame,
    [`observations/lion-adapter-test/frame-${String(revealFrameId).padStart(4,'0')}.png`]:'sanitized-png-fixture'};
  const f=fixture({step:'lionFieldProbe',expectedFrameId:10,seedFiles,mapPosition:{x:-1265.917,y:1928.381}});const result=await f.run();
  assertPauseProof(result);assert.equal(result.pauseProof.kind,'inventory');
  assert.equal(f.mapQueries.length,1);assert.deepEqual(f.mapQueries[0],['Teyvat',-1265.917,1928.381]);
  assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_ESCAPE','VK_B']);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);
});

test('a validated paused Lisa receipt seeds one nearby probe beyond the Windrise anchor and then pauses',async()=>{
  const now=10000,seedFiles=pausedLisaProbeFiles(now);
  const f=fixture({step:'lionFieldProbe',initialFrame:40,expectedFrameId:40,seedFiles,
    mapPosition:{x:pausedLisaPosition.x-1.5,y:pausedLisaPosition.y-2.99}});
  const result=await f.run();assertPauseProof(result);assert.equal(result.pauseProof.kind,'inventory');
  assert.ok(result.fieldProbe&&Number.isInteger(result.fieldProbe.frameId));
  assert.equal(f.mapQueries.length,1);
  assert.deepEqual(f.mapQueries[0],['Teyvat',pausedLisaPosition.x,pausedLisaPosition.y]);
  assert.ok(Math.hypot(f.mapQueries[0][1]+1265.917,f.mapQueries[0][2]-1928.381)>80,'seeded field is beyond the old static anchor radius');
  assert.ok(Math.hypot(f.mapQueries[0][1]-pausedLisaPosition.x,f.mapQueries[0][2]-pausedLisaPosition.y)<=25);
  const probed=f.observations.find(o=>o.frameId===result.fieldProbe.frameId);
  assert.ok(probed&&probed.map,'the returned probe frame retains the accepted nearby native position');
  assert.ok(Math.hypot(probed.map.x-f.mapQueries[0][1],probed.map.y-f.mapQueries[0][2])<=25);
  assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_ESCAPE','VK_B']);
  assert.equal(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_W'||x.key==='VK_3'),false);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);
  const marker=JSON.parse(f.getVirtualFiles().get('paused-lisa-position-probe.json'));
  assert.ok(Number.isFinite(marker.usedAt),'the marker is durably consumed before Escape');
  assert.ok(f.getVirtualFiles().has(`receipts/lion-adapter-test/${marker.receiptId}.json`));
});

test('a witnessed Lisa climb is released once from its adjacent ledge, then a grounded nearby fix is returned',async()=>{
  // Genshin.GetPositionFromMap returns Point2f, with no map-name property.
  const grounded={x:pausedLisaPosition.x+1.25,y:pausedLisaPosition.y-1.5};
  const climb={x:pausedLisaPosition.x,y:pausedLisaPosition.y};
  const f=fixture({step:'lionFieldProbe',initialFrame:40,expectedFrameId:40,seedFiles:pausedLisaClimbProbeFiles(10000),
    noEnemy:true,fieldRowsSequence:[climbHudRows(),fieldRows()],mapPositionSequence:[climb,grounded]});
  const result=await f.run();
  assertPauseProof(result);assert.equal(result.step,'lionFieldProbe');assert.equal(result.climbReleaseAttempts,1);
  assert.ok(result.fieldProbe&&Number.isInteger(result.fieldProbe.frameId));
  assert.equal(f.mapQueries.length,2,'one reviewed-cliff fix before X and one grounded fix after X');
  assert.deepEqual(f.mapQueries[0],['Teyvat',climb.x,climb.y]);assert.deepEqual(f.mapQueries[1],['Teyvat',climb.x,climb.y]);
  assert.ok(f.mapQueryFrames[1].fieldCaptureCount>f.mapQueryFrames[0].fieldCaptureCount);
  const release=f.adapter.events().find(e=>e.type==='lisaClimbRelease');
  assert.ok(release&&release.position&&release.position.map==='Teyvat');
  assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_ESCAPE','VK_X','VK_B']);
  assert.equal(f.inputs.some(x=>x.kind==='down'&&['VK_W','VK_SPACE','VK_3','VK_2'].includes(x.key)),false);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);
  const used=JSON.parse(f.getVirtualFiles().get('paused-lisa-position-probe.json'));
  assert.equal(used.releaseClimb,true);assert.ok(Number.isFinite(used.usedAt));
  const persisted=JSON.parse(f.getVirtualFiles().get('reports/lion-adapter-test.lisa-climb-release.json'));
  assert.equal(persisted.releaseAttempted,true);assert.equal(persisted.witnessFrameId,20);
});

test('malformed or unproven historic climb evidence blocks Escape, GPS, and X',async()=>{
  const base=pausedLisaClimbProbeFiles(10000),sourcePath='observations/lion-adapter-test/frame-0020';
  const source=base[`${sourcePath}.json`];
  const badSource=changes=>({...source,...changes});
  const cases=[
    ['malformed release flag',{seedFiles:{...base,'paused-lisa-position-probe.json':{...base['paused-lisa-position-probe.json'],releaseClimb:'yes'}}}],
    ['missing historic climb PNG',{seedFiles:base,removeSeedFiles:[`${sourcePath}.png`]}],
    ['wrong navigation result',{seedFiles:pausedLisaClimbProbeFiles(10000,{receipt:{details:{result:{navigationStatus:'arrived'}}}})}],
    ['wrong stop reason',{seedFiles:pausedLisaClimbProbeFiles(10000,{receipt:{details:{result:{reason:'other'}}}})}],
    ['climb frame precedes ground field',{seedFiles:pausedLisaClimbProbeFiles(10000,{climbSource:{frameId:18}})}],
    ['climb source predates field',{seedFiles:pausedLisaClimbProbeFiles(10000,{climbSource:{timestamp:9999-500-1}})}],
    ['climb source follows pause proof',{seedFiles:pausedLisaClimbProbeFiles(10000,{climbSource:{timestamp:10000}})}],
    ['cliff fix is not adjacent',{seedFiles:pausedLisaClimbProbeFiles(10000,{climbSource:{map:{map:'Teyvat',x:source.map.x+6,y:source.map.y}}})}],
    ['wrong map',{seedFiles:pausedLisaClimbProbeFiles(10000,{climbSource:{map:{map:'Domains',x:source.map.x,y:source.map.y}}})}],
    ['health differs from ground witness',{seedFiles:pausedLisaClimbProbeFiles(10000,{climbSource:{hud:{...source.hud,health:{current:875,max:1186}}}})}],
    ['climbing flag absent',{seedFiles:pausedLisaClimbProbeFiles(10000,{climbSource:{hud:{...source.hud,climbing:false}}})}],
    ['wrong ground controls',{seedFiles:pausedLisaClimbProbeFiles(10000,{climbSource:{hud:{...source.hud,groundControls:true}}})}],
    ['historic enemy bar',{seedFiles:pausedLisaClimbProbeFiles(10000,{climbSource:{hud:{...source.hud,enemyBars:[{x:1,y:2,width:20,height:5}]}}})}],
    ['duplicate historic X',{seedFiles:pausedLisaClimbProbeFiles(10000,{climbSource:{ocr:climbHudRows({duplicateX:true})}})}],
    ['missing historic Space',{seedFiles:pausedLisaClimbProbeFiles(10000,{climbSource:{ocr:climbHudRows({spaceText:'F'})}})}]
  ];
  for(const [label,options] of cases){
    const f=fixture({step:'lionFieldProbe',initialFrame:40,expectedFrameId:40,seedFiles:base,...options});
    const result=await f.run();assert.equal(result.status,'stopped',label);
    assert.equal(f.inputs.some(x=>x.kind==='down'&&['VK_X','VK_W','VK_SPACE'].includes(x.key)),false,label);
    assert.equal(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_ESCAPE'),false,label);
    assert.equal(f.mapQueries.length,0,label);assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0,label);
  }
});

test('climb controls, enemy bars, invalid HUD, persistence failures, and stale evidence never trigger X',async()=>{
  const optionsFor=changes=>({step:'lionFieldProbe',initialFrame:40,expectedFrameId:40,seedFiles:pausedLisaClimbProbeFiles(10000),noEnemy:true,
    fieldRowsSequence:[climbHudRows(),fieldRows()],mapPositionSequence:[{map:'Teyvat',...pausedLisaPosition},{map:'Teyvat',x:pausedLisaPosition.x+1,y:pausedLisaPosition.y+1}],...changes});
  const cases=[
    ['duplicate X',optionsFor({fieldRowsSequence:[climbHudRows({duplicateX:true}),fieldRows()]})],
    ['duplicate Space',optionsFor({fieldRowsSequence:[climbHudRows({duplicateSpace:true}),fieldRows()]})],
    ['wrong Kaeya',optionsFor({fieldRowsSequence:[climbHudRows({kaeyaText:'Kaeya?' }),fieldRows()],partyCropRowsByField:[[],[]]})],
    ['wrong slot',optionsFor({fieldRowsSequence:[climbHudRows({slotText:'2'}),fieldRows()]})],
    ['wrong objective',optionsFor({fieldRowsSequence:[climbHudRows({objectiveText:'Find Lisa'}),fieldRows()]})],
    ['low health',optionsFor({fieldRowsSequence:[climbHudRows({healthText:'400/1186'}),fieldRows()]})],
    ['enemy bar',optionsFor({noEnemy:false})],
    ['X persistence write failure',optionsFor({failWritePath:'reports/lion-adapter-test.lisa-climb-release.json'})],
    ['X persistence readback failure',optionsFor({corruptClimbReadback:true})],
    ['climb HUD ages during persistence',optionsFor({advanceAfterClimbWrite:1001})],
    ['cliff GPS too far',optionsFor({mapPositionSequence:[{map:'Teyvat',x:pausedLisaPosition.x+3.01,y:pausedLisaPosition.y},{map:'Teyvat',x:pausedLisaPosition.x+1,y:pausedLisaPosition.y+1}]})],
    ['cliff GPS exception',optionsFor({throwGpsAt:1})]
  ];
  for(const [label,options] of cases){
    const f=fixture(options),result=await f.run();assertPauseProof(result);
    assert.equal(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_X'),false,label);
    assert.equal(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_ESCAPE'),true,label);
    assert.equal(f.inputs.some(x=>x.kind==='down'&&(x.key==='VK_W'||x.key==='VK_SPACE'||x.key==='VK_3'||x.key==='VK_2')),false,label);
    assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0,label);
    if(label.includes('persistence')||label.includes('ages during'))assert.ok(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_ESCAPE'),label);
  }
});

test('one climb release attempt survives key and stop faults, but repeated climbing never sends a second X',async()=>{
  const baseOptions={step:'lionFieldProbe',initialFrame:40,expectedFrameId:40,seedFiles:pausedLisaClimbProbeFiles(10000),noEnemy:true,
    fieldRowsSequence:[climbHudRows(),fieldRows()],mapPositionSequence:[{map:'Teyvat',...pausedLisaPosition},{map:'Teyvat',x:pausedLisaPosition.x+1,y:pausedLisaPosition.y+1}]};
  for(const [label,changes] of [
    ['X keydown fault',{throwXKeyDown:true}],['X keyup retry',{throwXKeyUpCount:1}],['stop after X',{stopAfterX:true}],
    ['focus recovery after X',{loseFocusAfterX:true}]
  ]){
    const f=fixture({...baseOptions,...changes}),result=await f.run();assertPauseProof(result);
    assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_X').length,1,label);
    assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_ESCAPE','VK_X','VK_B'],label);
    assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0,label);
  }
  const disconnected=fixture({...baseOptions,crossSessionAfterX:true}),pending=disconnected.run();
  const recovered=await remainsPendingUntil(pending,()=>disconnected.setFlag('crossSessionAfterX',false),
    ()=>pauseProtectionStarted(disconnected)&&disconnected.getForeignCaptureCount()>0,'climb post-input session recovery');
  assertPauseProof(recovered);
  assert.equal(disconnected.inputs.filter(x=>x.kind==='down'&&x.key==='VK_X').length,1);
  assert.equal(disconnected.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);
  const repeated=fixture({...baseOptions,fieldRowsSequence:[climbHudRows(),climbHudRows(),climbHudRows(),climbHudRows(),climbHudRows(),climbHudRows()]});
  const result=await repeated.run();assertPauseProof(result);
  assert.equal(repeated.inputs.filter(x=>x.kind==='down'&&x.key==='VK_X').length,1);
  assert.equal(repeated.inputs.some(x=>x.kind==='down'&&(x.key==='VK_W'||x.key==='VK_SPACE'||x.key==='VK_3'||x.key==='VK_2')),false);
  assert.equal(repeated.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);
});

test('paused Lisa probe marker, saved receipt, screenshots, source proof, readback, and Food freshness gate Escape',async()=>{
  const now=10000,valid=pausedLisaProbeFiles(now),receiptPath='receipts/lion-adapter-test/mission-0123456789abcdef0123456789abcdef.json';
  const cases=[
    ['wrong marker kind',{seedFiles:{...valid,'paused-lisa-position-probe.json':{...valid['paused-lisa-position-probe.json'],kind:'other'}}}],
    ['wrong marker session',{seedFiles:{...valid,'paused-lisa-position-probe.json':{...valid['paused-lisa-position-probe.json'],session:'foreign'}}}],
    ['wrong expected frame',{seedFiles:{...valid,'paused-lisa-position-probe.json':{...valid['paused-lisa-position-probe.json'],frameId:39}}}],
    ['not witnessed',{seedFiles:{...valid,'paused-lisa-position-probe.json':{...valid['paused-lisa-position-probe.json'],witnessVerified:false}}}],
    ['expired marker',{seedFiles:pausedLisaProbeFiles(now,{marker:{createdAt:now-120001}})}],
    ['preused marker',{seedFiles:pausedLisaProbeFiles(now,{marker:{usedAt:now-1}})}],
    ['invalid receipt id',{seedFiles:{...valid,'paused-lisa-position-probe.json':{...valid['paused-lisa-position-probe.json'],receiptId:'mission-bad'}}}],
    ['missing receipt',{removeSeedFiles:[receiptPath]}],
    ['wrong receipt result',{seedFiles:pausedLisaProbeFiles(now,{receipt:{details:{result:{status:'stopped'}}}})}],
    ['missing historic field PNG',{removeSeedFiles:['observations/lion-adapter-test/frame-0019.png']}],
    ['missing Food pause PNG',{removeSeedFiles:['observations/lion-adapter-test/frame-0021.png']}],
    ['invalid historic source',{seedFiles:pausedLisaProbeFiles(now,{field:{hud:{...pausedLisaProbeFiles(now)['observations/lion-adapter-test/frame-0019.json'].hud,enemyBars:[{x:1,y:2,width:30,height:5}]}}})}],
    ['invalid Food proof',{seedFiles:pausedLisaProbeFiles(now,{paused:{ocr:[row('Food',140,32,67,31)]}})}],
    ['marker write failed',{failWritePath:'paused-lisa-position-probe.json'}],
    ['readback changed',{corruptProbeReadback:true}],
    ['Food expired during source validation',{advanceAfterProbeWrite:1501}]
  ];
  for(const [label,options] of cases){
    const f=fixture({step:'lionFieldProbe',initialFrame:40,expectedFrameId:40,seedFiles:valid,...options});
    const result=await f.run();
    assert.equal(result.status,'stopped',label);
    assert.equal(f.mapQueries.length,0,label);
    if(result.pauseVerified===true)assertPauseProof(result);
    assert.equal(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_ESCAPE'),false,label);
    assert.equal(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_W'),false,label);
  }
});

test('a seeded candidate beyond 25 m or GPS failure is rejected and the probe still reaches verified Food pause',async()=>{
  for(const [label,options] of [
    ['26m candidate',{mapPosition:{x:pausedLisaPosition.x+26,y:pausedLisaPosition.y}}],
    ['GPS exception',{throwGps:true}]
  ]){
    const f=fixture({step:'lionFieldProbe',initialFrame:40,expectedFrameId:40,seedFiles:pausedLisaProbeFiles(10000),...options});
    const result=await f.run();assertPauseProof(result);
    assert.equal(f.mapQueries.length,1,label);
    assert.deepEqual(f.mapQueries[0],['Teyvat',pausedLisaPosition.x,pausedLisaPosition.y],label);
    assert.equal(f.inputs.filter(x=>x.kind==='down').map(x=>x.key).join(','),'VK_ESCAPE,VK_B',label);
    assert.equal(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_W'),false,label);
    assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0,label);
    if(label==='26m candidate')assert.equal(f.observations.some(o=>o.map&&Math.hypot(o.map.x-pausedLisaPosition.x,o.map.y-pausedLisaPosition.y)>25),false);
  }
});

test('charted GPS evidence rejects missing or altered marker, map, image, session, and frame bindings',async()=>{
  const revealFrameId=9,createdAt=9500;
  const validMarker={kind:'windriseCharted',session:'lion-adapter-test',witnessVerified:true,revealFrameId,createdAt};
  const mapFrame={session:'lion-adapter-test',frameId:revealFrameId,timestamp:9400,hud:{bigMap:true},ocr:windriseMap1221Rows()};
  const jsonPath=`observations/lion-adapter-test/frame-${String(revealFrameId).padStart(4,'0')}.json`;
  const pngPath=`observations/lion-adapter-test/frame-${String(revealFrameId).padStart(4,'0')}.png`;
  const cases=[
    ['missing marker',{}],
    ['missing PNG',{[jsonPath]:mapFrame}],
    ['wrong marker session',{'windrise-charted.json':{...validMarker,session:'other-session'},[jsonPath]:mapFrame,[pngPath]:'fixture'}],
    ['unwitnessed marker',{'windrise-charted.json':{...validMarker,witnessVerified:false},[jsonPath]:mapFrame,[pngPath]:'fixture'}],
    ['frame outside request',{'windrise-charted.json':{...validMarker,revealFrameId:10},[jsonPath]:mapFrame,[pngPath]:'fixture'}],
    ['wrong map session',{'windrise-charted.json':validMarker,[jsonPath]:{...mapFrame,session:'other-session'},[pngPath]:'fixture'}],
    ['missing Windrise geometry',{'windrise-charted.json':validMarker,[jsonPath]:{...mapFrame,ocr:windriseMap1221Rows().filter(r=>r.text!=='Windrise')},[pngPath]:'fixture'}]
  ];
  for(const [label,seedFiles] of cases){
    const f=fixture({step:'lionFieldProbe',expectedFrameId:10,seedFiles,mapPosition:{x:-1265.917,y:1928.381}});const result=await f.run();
    assertPauseProof(result);assert.equal(f.mapQueries.length,0,label);
    assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_ESCAPE','VK_B'],label);
    assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0,label);
  }
});

test('charted frame 1221 permits one Windrise map probe, then verifies the Food pause',async()=>{
  const f=fixture({step:'lionFieldProbe',initialScreen:'map',mapPosition:{x:-1265.917,y:1928.381}});
  const result=await f.run();
  assert.equal(result.step,'lionFieldProbe');assert.equal(result.fightStarted,false);
  assert.equal(result.kaeyaSelectAttempted,false);assert.equal(result.amberReturnAttempted,false);
  assertPauseProof(result);assert.equal(result.pauseProof.kind,'inventory');
  assert.ok(result.fieldProbe&&Number.isInteger(result.fieldProbe.frameId));
  assert.equal(f.mapQueries.length,1);
  assert.equal(f.mapQueries[0][0],'Teyvat');assert.equal(f.mapQueries[0][1],-1265.917);assert.equal(f.mapQueries[0][2],1928.381);
  assert.equal(f.metrics.orientationCalls,3,'one accepted-position compass read plus bounded observation compass reads');
  assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_ESCAPE','VK_B']);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);
  assert.equal(f.adapter.events().filter(e=>e.type==='lionFieldMapClose').length,1);
});

test('charted probe defers GPS until a fresh capture has exact Kaeya and slot 3, then returns that accepted map frame',async()=>{
  const first=[row('Meet Lisa at the temple',80,250,300,35),row('1186/1186',900,1002,120,24),row('R',1580,1004,30,30),
    row('Amber',1680,415,80,35),row('Kaeyā',1660,500,80,35),row('Q',1660,1004,30,30)];
  const complete=[row('Meet Lisa at the temple',80,250,300,35),row('1186/1186',900,1002,120,24),row('R',1580,1004,30,30),
    row('Amber',1680,415,80,35),row('Kaeya',1660,500,80,35),row('3',1860,500,25,35),row('Q',1660,1004,30,30)];
  const f=fixture({step:'lionFieldProbe',initialScreen:'map',mapPosition:{x:-1265.917,y:1928.381},
    fieldRowsSequence:[first,complete],
    partyCropRowsByField:[[],[]],
    slotCropRowsByField:[[row('2',30,30,60,60)],[]]});
  const result=await f.run();assert.equal(result.step,'lionFieldProbe');assertPauseProof(result);
  assert.ok(result.fieldProbe&&Number.isInteger(result.fieldProbe.frameId));
  assert.equal(f.mapQueries.length,1,'only the complete field capture may spend the charted GPS read');
  assert.equal(f.mapQueryFrames[0].fieldCaptureCount,2,'first capture with Kaeyā and no verified slot remains unmapped');
  const probed=f.observations.find(o=>o.frameId===result.fieldProbe.frameId);
  assert.ok(probed&&probed.map,'the returned probe frame must retain its accepted native map position');
  assert.equal(probed.map.map,'Teyvat');assert.ok(Math.hypot(probed.map.x+1265.917,probed.map.y-1928.381)<=80);
  assert.equal(probed.hud.health.current,1186);assert.ok(probed.hud.objectives.some(x=>/Meet Lisa at the temple/i.test(x)));
  assert.equal(f.inputs.filter(x=>x.kind==='down').map(x=>x.key).join(','),'VK_ESCAPE,VK_B');
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);
});

test('map probe rejects missing Windrise, wrong region, combat step, stale witness, and lost focus before input',async()=>{
  const cases=[
    {name:'missing Windrise',options:{mapRows:windriseMap1221Rows().filter(r=>r.text!=='Windrise')}},
    {name:'wrong region',options:{mapRows:windriseMap1221Rows().map(r=>r.text==='Galesong Hill'?row('Yashiori Island',r.x,r.y,r.width,r.height):r)}},
    {name:'combat step',options:{step:'lionFieldCombat'}},
    {name:'stale map witness',options:{staleInitial:true}}
  ];
  for(const c of cases){
    const f=fixture({step:'lionFieldProbe',initialScreen:'map',...c.options});
    const result=await f.run();
    assert.equal(f.inputs.filter(x=>x.kind==='down').length,0,c.name);
    assert.equal(f.mapQueries.length,0,c.name);
    assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0,c.name);
    assert.notEqual(result.pauseVerified,true,c.name);
  }
  const unfocused=fixture({step:'lionFieldProbe',initialScreen:'map'});unfocused.setForeground(false);
  await assert.rejects(unfocused.run());
  assert.deepEqual(unfocused.inputs.filter(x=>x.kind==='down'),[]);
  assert.equal(unfocused.mapQueries.length,0);
});

test('map probe contains GPS errors, distant candidates, bad field OCR, stop, and release faults under the pause guardian',async()=>{
  for(const [label,options] of [
    ['GPS exception',{throwGps:true}],
    ['distant GPS',{mapPosition:{x:-1100,y:2000}}],
    ['bad post-close OCR',{objectiveText:'Meet Lisa in the temple'}],
    ['stop after close',{stopAfterClose:true}],
    ['key-up failures',{throwEscapeKeyUpCount:2}]
  ]){
    const f=fixture({step:'lionFieldProbe',initialScreen:'map',...options});
    const result=await f.run();
    assertPauseProof(result);
    assert.equal(f.mapQueries.length,label==='bad post-close OCR'?0:1,label);
    assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0,label);
    assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,0,label);
    if(label==='distant GPS')assert.equal(f.metrics.orientationCalls,2,`${label}: no compass read is made for the rejected map candidate`);
    if(label==='bad post-close OCR')assert.equal(result.fieldProbe,undefined,label);
    if(label==='key-up failures'){
      assert.deepEqual(f.getOverlappingKeyDowns(),[],label);
      assert.ok(f.getEscapeKeyUpAttempts()>=3,label);
    }
  }
});

test('objective OCR diacritics, NFD marks, punctuation, and spacing normalize through the real observation adapter',async()=>{
  for(const objectiveText of [
    'Méet Lisa at the temple',
    'Meet Liša at the temple',
    'Meet Liśa at the temple',
    'Méet.Liša   at the temple',
    'Me\u0301et Li\u0301sa at the temple'
  ]) {
    const f=fixture({objectiveText});const result=await f.run();
    assert.equal(result.fightStarted,true,objectiveText);
    assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,1,objectiveText);
    assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,1,objectiveText);
  }
  const recorded=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/lion-pause-failures.json'),'utf8'));
  for(const objectiveText of [...new Set(recorded.flatMap(c=>c.objectives||[]).filter(x=>/Lisa/i.test(x)))]){
    const f=fixture({objectiveText});const result=await f.run();
    assert.equal(result.fightStarted,true,`sanitized recorded OCR: ${objectiveText}`);
    assertPauseProof(result);
  }
});

test('same-capture narrow crop restores the unique missing Kaeya slot 3 label',async()=>{
  const f=fixture({slot:false,slotCropRows:[row('3',30,30,60,60)]});const result=await f.run();
  assert.equal(result.fightStarted,true);
  assert.ok(f.metrics.slotCropCalls>=1);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,1);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,1);

  for(const slotCropRows of [
    [row('2',30,30,60,60)],
    [row('3',30,30,30,30),row('3',60,30,30,30)],
    [row('3',190,30,60,60)]
  ]) {
    const denied=fixture({slot:false,slotCropRows});const stopped=await denied.run();
    assert.equal(stopped.fightStarted,false);
    assert.equal(denied.metrics.slotCropCalls>=1,true);
    assert.equal(denied.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,0);
    assert.equal(denied.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);
    assertPauseProof(stopped);
  }

  const duplicateFull=fixture({duplicateSlot:true,slotCropRows:[row('3',30,30,60,60)]});
  const duplicateResult=await duplicateFull.run();
  assert.equal(duplicateResult.fightStarted,false);
  assert.equal(duplicateFull.metrics.slotCropCalls,0,'existing ambiguous full-frame slot reads do not trigger repair');
  assert.equal(duplicateFull.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,0);

  const accented=fixture({kaeyaText:'Kaeyā',slot:false,
    partyCropRows:[row('Amber',150,60,300,105),row('Kaeya',150,510,300,105)],
    slotCropRows:[row('3',30,30,60,60)]});
  const accentedResult=await accented.run();
  assert.equal(accentedResult.fightStarted,true,'same-capture OCR crop can resolve an accented Kaeyā label');
  assert.ok(accented.metrics.slotCropCalls>=1);
  assert.equal(accented.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,1);
});

test('field combat rejects wrong quest, Trial, invalid HP, bad or duplicate Kaeya evidence, and missing enemies',async()=>{
  const cases=[
    {name:'wrong quest',step:'windriseReveal'},
    {name:'changed objective word',objectiveText:'Meet Lisa in the temple'},
    {name:'Trial party',trial:true},
    {name:'zero HP',healthText:'0/1186'},
    {name:'wrong slot',slotText:'2'},
    {name:'missing slot',slot:false},
    {name:'duplicate Kaeya',duplicateKaeya:true},
    {name:'no enemy',noEnemy:true}
  ];
  for(const c of cases){
    const f=fixture(c);const result=await f.run();
    assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0,`${c.name}: ${JSON.stringify({result,inputs:f.inputs,metrics:f.metrics})}`);
    assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,c.noEnemy?1:0,c.name);
    if(c.noEnemy)assert.match(result.reason,/No fresh detected red enemy bar/);
    if(c.step==='windriseReveal')assert.deepEqual(f.inputs.filter(x=>x.kind==='down'),[],c.name);
    if(c.trial||c.healthText==='0/1186'||c.slotText||c.slot===false||c.duplicateKaeya)
    assertPauseProof(result);
    assert.equal(result.enemyClearVerified,false,c.name);
  }
});

test('low positive HP and stale, nonfresh, cross-session, or replayed observations never start native combat',async()=>{
  const low=fixture({healthText:'500/1186'});
  const lowResult=await low.run();assert.equal(lowResult.fightStarted,false);
  assert.equal(low.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);assert.equal(low.inputs.filter(x=>x.key==='VK_3').length,0);

  const foreign=fixture({crossSessionAfterFight:true});
  const foreignResult=await remainsPendingUntil(foreign.run(),()=>foreign.setFlag('crossSessionAfterFight',false),
    ()=>pauseProtectionStarted(foreign)&&foreign.getForeignCaptureCount()>=1,'foreign-session observation under pause protection');
  assert.equal(foreignResult.fightStarted,true);assertPauseProof(foreignResult);
});

test('native failure releases all input and pauses only from a fresh known Lisa field',async()=>{
  const f=fixture({nativeFailure:true});const result=await f.run();
  assert.match(result.reason,/mock native failure/);assert.equal(result.fightStarted,true);assertPauseProof(result);
  assert.ok(f.nativeCalls.includes('cancel'));assert.ok(f.nativeCalls.includes('dispose'));
  assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_ESCAPE','VK_3','VK_B']);
  for(const key of ['VK_ESCAPE','VK_3','VK_B'])assert.equal(f.inputs.filter(x=>x.kind==='up'&&x.key===key).length,1,`${key} released`);
});

test('unknown aftermath remains pending until the screen is restored, then guardian proves pause',async()=>{
  const f=fixture({postFightInvalid:'unknown',nativeFailure:true});
  const result=await remainsPendingUntil(f.run(),()=>f.setFlag('postFightInvalid',null),
    ()=>pauseProtectionStarted(f)&&f.getUnknownCaptureCount()>=1,'unknown aftermath capture under pause protection');
  assert.equal(result.fightStarted,true);assertPauseProof(result);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_2').length,0);
});

test('stale and nonfresh post-close observations stay pending until a fresh same-session proof is available',async()=>{
  for(const key of ['staleObserve','nonfreshObserve']){
    const f=fixture({[key]:1000000,blockPauseB:true});
    const result=await remainsPendingUntil(f.run(),()=>{f.setFlag(key,false);f.setFlag('blockPauseB',false);},
      ()=>pauseProtectionStarted(f)&&f.getInvalidObservationCount()>=4,`${key} invalid observations under pause protection`);
    assert.equal(result.fightStarted,false,key);
    assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0,key);
    assertPauseProof(result);
  }
});

test('minimal pause evidence cannot dismiss unknown HUD, while party OCR loss still permits pause from health and controls',async()=>{
  const unknown=fixture({noPauseHud:true,partyCropRows:[]});
  const unknownResult=await remainsPendingUntil(unknown.run(),()=>unknown.setFlag('noPauseHud',false),
    ()=>pauseProtectionStarted(unknown)&&unknown.getNoHudCaptureCount()>=4,'no-HUD captures under pause protection');
  assert.equal(unknownResult.fightStarted,false);assertPauseProof(unknownResult);
  assert.equal(unknown.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);
  assert.equal(unknown.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,0);

  for(const flag of ['tutorial']){
    const blocked=fixture({[flag]:true});
    const restored=await remainsPendingUntil(blocked.run(),()=>blocked.setFlag(flag,false),
      ()=>pauseProtectionStarted(blocked)&&blocked.getBlockedCaptureCount()>=4,`${flag} captures under pause protection`);
    assert.equal(restored.fightStarted,false,flag);assertPauseProof(restored);
    assert.equal(blocked.nativeCalls.filter(x=>x&&x.kind==='fight').length,0,flag);
    assert.equal(blocked.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,0,flag);
  }

  const partyMissing=fixture({omitPartyLabels:true,partyCropRows:[]});
  const pauseResult=await partyMissing.run();
  assert.equal(pauseResult.fightStarted,false);assertPauseProof(pauseResult);
  assert.equal(partyMissing.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,0);
  assert.equal(partyMissing.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);
  assert.ok(partyMissing.inputs.some(x=>x.kind==='down'&&x.key==='VK_B'));
});

test('every post-unpause failure resolves only after a fresh verified pause',async()=>{
  const cases=[
    {name:'Escape keydown',options:{throwCloseKeyDown:true}},
    {name:'stop after close',options:{stopAfterClose:true}},
    {name:'selection keydown',options:{throwSelectionKeyDown:true}},
    {name:'stop after selection',options:{stopAfterSelect:true}},
    {name:'one transient capture error',options:{throwObserveCount:1}},
    {name:'native rejection',options:{nativeFailure:true}},
    {name:'native timeout',options:{nativeTimeout:true}},
    {name:'Amber return keydown',options:{throwAmberReturn:true}},
    {name:'stop after native',options:{stopAfterNative:true}},
    {name:'Amber return then native rejection',options:{throwAmberReturn:true,nativeFailure:true}},
    {name:'pause keydown failures then journal fallback',options:{throwBCount:2}},
    {name:'silent pause keys then journal fallback',options:{silentBCount:2}},
    {name:'pause verification capture error',options:{throwAfterInventoryPauseCapture:true}}
  ];
  for(const c of cases){
    const f=fixture(c.options),result=await f.run();
    assertPauseProof(result);
    assert.ok(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_ESCAPE'),`${c.name}: inventory close attempted`);
    assert.ok(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_B'||x.kind==='down'&&x.key==='VK_J'||x.kind==='down'&&x.key==='VK_ESCAPE'),`${c.name}: bounded pause attempt`);
    assert.ok(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length<=1,`${c.name}: no combat retry`);
    assert.ok(f.nativeCalls.filter(x=>x&&x.kind==='fight').length<=1,`${c.name}: no native retry`);
    if(c.options.throwBCount||c.options.silentBCount){
      assert.equal(result.pauseProof.kind,'journal',c.name);
      assert.ok(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_J'),c.name);
    }
  }
});

test('Escape key-up failures keep the held key protected until release succeeds and pause is proved',async()=>{
  const f=fixture({throwEscapeKeyUpCount:2});const result=await f.run();
  assertPauseProof(result);
  assert.deepEqual(f.getOverlappingKeyDowns(),[],'must not start another key while Escape remains held');
  assert.ok(f.getEscapeKeyUpAttempts()>=3,`Escape release retried ${f.getEscapeKeyUpAttempts()} times before proof`);
  assert.ok(result.pauseProof.pauseFrameId>1);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,0);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);
  assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_ESCAPE','VK_B']);
});

test('lost focus or foreign session stays pending until the pinned game context returns',async()=>{
  for(const [name,options,key,restore] of [
    ['focus',{loseFocusAfterNative:true,refuseFocusRecovery:true},'focus',f=>f.setForeground(true)],
    ['session',{crossSessionAfterFight:true},'crossSessionAfterFight',f=>f.setFlag('crossSessionAfterFight',false)]
  ]){
    const f=fixture(options);
    const result=await remainsPendingUntil(f.run(),()=>restore(f),
      ()=>pauseProtectionStarted(f)&&f.getObserverCalls()>=10,`${name} guarded observations`);
    assert.equal(result.fightStarted,true,name);assertPauseProof(result);
    assert.ok(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length<=1,name);
  }
});

test('guardian verifies a Paimon menu after B and J are ineffective, and rejects partial menu OCR',async()=>{
  const full=[row('Adventure Rank',120,100,180,35),row('World Level',120,150,180,35),row('Shop',80,300,100,35),row('Party Setup',80,360,150,35)];
  const f=fixture({nativeFailure:true,silentBCount:2,silentJ:true,paimonOnFallbackEscape:true,paimonRows:[...full.slice(0,3)]});
  const result=await remainsPendingUntil(f.run(),()=>f.setFlag('paimonRows',full),
    ()=>pauseProtectionStarted(f)&&f.getPaimonCaptureCount()>=1,'partial Paimon menu under pause protection');
  assertPauseProof(result);assert.equal(result.pauseProof.kind,'menu');
  assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_ESCAPE','VK_3','VK_B','VK_B','VK_J','VK_ESCAPE']);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,1);
});

test('a native return to the Party Setup screen is recognized as a pause proof',async()=>{
  const f=fixture({nativeFailure:true,partyAfterNative:true});
  const result=await f.run();
  assertPauseProof(result);assert.equal(result.pauseProof.kind,'party');
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,1);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,1);
});
