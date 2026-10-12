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
const fieldRows=(options={})=>{
  const rows=[row(options.objectiveText||'Meet Lisa at the temple',80,250,300,35)];
  if(!options.noPauseHud)rows.push(row('R',1580,1004,30,30),row(options.healthText||'1186/1186',900,1002,120,24));
  if(!options.noPauseHud&&!options.omitPartyLabels)rows.push(row('Amber',1680,415,80,35));
  if(!options.noPauseHud&&!options.omitControls)rows.push(row('Q',1660,1004,30,30));
  if(!options.noPauseHud&&!options.omitPartyLabels&&options.kaeya!==false)rows.push(row('Kaeya',1660,500,80,35));
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
  let now=10000,frame=1,screen='inventory',written=[],lastRows=[];
  let foreground=true,observerCalls=0,bDownCount=0,escapeDownCount=0,escapeKeyUpAttempts=0,activeInputKey=null,
    unknownCaptureCount=0,noHudCaptureCount=0,paimonCaptureCount=0,blockedCaptureCount=0,foreignCaptureCount=0,invalidObservationCount=0;
  const inputs=[],events=[],nativeCalls=[],virtualFiles=new Map(),overlappingKeyDowns=[],metrics={mapCalls:0,captures:0,partyCropCalls:0,controlCropCalls:0,slotCropCalls:0,focusCalls:0};
  const redBar=options.noEnemy?[]:[{x:500,y:250,width:90,height:8}];
  function mat(rect=null){return {rect,inRange(){const enemy=rect&&rect.x===350&&rect.y===100&&rect.w===1250&&rect.h===800;
    return {findContoursAsArray(){return enemy?redBar.map(b=>({...b})):[];},dispose(){}};},resize(){return mat(rect);},dispose(){}};}
  let cancelNative=null;
  const files={
    isExists:p=>virtualFiles.has(p)||fs.existsSync(path.join(dir,p)),
    readTextSync:p=>virtualFiles.has(p)?virtualFiles.get(p):fs.readFileSync(path.join(dir,p),'utf8'),
    writeTextSync:(p,v)=>{virtualFiles.set(p,v);return true;},
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
  const context={Date:class extends Date{static now(){return now;}},file:files,AutoFightParam,dispatcher,
    genshin:{isRemoteDesktopSession:true,windowsSessionId:5,get isGameForeground(){return foreground;},async focusGame(){metrics.focusCalls++;if(!options.refuseFocusRecovery)foreground=true;},
      getPositionFromMap(){metrics.mapCalls++;return {map:'Teyvat',x:1,y:2};},getCameraOrientation(){return 0;}},
    RecognitionObject:{Ocr:(x,y,w,h)=>({x,y,w,h})},
    captureGameRegion(){metrics.captures++;const fought=nativeCalls.some(x=>x&&x.kind==='fight');
      if(screen==='inventory')lastRows=inventoryRows();
      else if(screen==='journal')lastRows=[row('In Progress',130,45,120,30),row('Archon Quests',130,120,180,35)];
       else if(screen==='party')lastRows=[row('Party Setup',120,80,170,35),row('Deploy',1600,980,120,35)];
      else if(screen==='paimon')lastRows=options.paimonRows||[row('Adventure Rank',120,100,180,35),row('World Level',120,150,180,35),row('Shop',80,300,100,35),row('Party Setup',80,360,150,35)];
      else if(fought&&options.postFightInvalid==='unknown')lastRows=[row('Auto',50,50),row('Kaeya',900,850),row('A dialogue begins here',800,920,350,35)];
      else if(fought&&options.postFightInvalid==='trial')lastRows=fieldRows({...options,trial:true});
      else if(fought&&options.postFightInvalid==='zeroHp')lastRows=fieldRows({...options,healthText:'0/1186'});
      else lastRows=fieldRows(options);
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
      const rows=party?(options.partyCropRows===undefined?scaledPartyRows():options.partyCropRows):control?(options.controlCropRows||[]):slot?(options.slotCropRows||[]):[];
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
    keyUp(key){inputs.push({kind:'up',key,frame,at:now});if(key==='VK_ESCAPE'){escapeKeyUpAttempts++;if(options.throwEscapeKeyUpCount&&escapeKeyUpAttempts<=options.throwEscapeKeyUpCount)throw new Error('mock Escape key-up failed');}if(activeInputKey===key)activeInputKey=null;},moveMouseBy(){},click(){},
    sleep:async ms=>{await new Promise(resolve=>setImmediate(resolve));now+=ms;},log:{info(){}}
  };
  vm.runInNewContext(fs.readFileSync(path.join(dir,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(5);
  const request={mission:'questStep',step:options.step||'lionFieldCombat',session:'lion-adapter-test',id:'lion-adapter-1',expectedFrameId:1,
    createdAt:9000,objective:'Meet Lisa at the temple'};
  adapter.beginMission(request);
  async function observe(){
    observerCalls++;
    if(options.throwObserveCount&&observerCalls<=options.throwObserveCount)throw new Error('mock capture failure');
    if(options.throwAfterInventoryPauseCapture&&screen==='inventory'&&bDownCount>0&&!options.inventoryPauseCaptureThrown){options.inventoryPauseCaptureThrown=true;throw new Error('mock pause verification capture failure');}
    frame++;now+=10;const foreign=options.crossSessionFirstField&&screen==='field'||options.crossSessionAfterFight&&nativeCalls.some(x=>x&&x.kind==='fight');
    const session=foreign?'other-session':'lion-adapter-test';
    if(foreign)foreignCaptureCount++;
    const nonfresh=options.nonfreshObserve&&(typeof options.nonfreshObserve!=='number'||observerCalls<=options.nonfreshObserve);
    const result=await adapter.observe(session,nonfresh?(typeof options.nonfreshObserve==='number'?1:frame-1):frame);
    if(nonfresh)invalidObservationCount++;
    if(options.staleObserve&&(typeof options.staleObserve!=='number'||observerCalls<=options.staleObserve)){result.timestamp=now-1501;invalidObservationCount++;}
    return result;}
  async function run(){const initial=await adapter.observe('lion-adapter-test',1);return adapter.runLionFieldCombat(initial,observe);}
  return {adapter,context,inputs,events,nativeCalls,metrics,run,observe,getNow:()=>now,setScreen:v=>{screen=v;},getScreen:()=>screen,
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
  assert.equal(result.amberReturnAttempted,true);
  assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_ESCAPE','VK_3','VK_2','VK_B']);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_ESCAPE').length,1);
  const events=f.adapter.events();
  assert.equal(events.find(e=>e.type==='lionFieldInventoryClose').finishedAt-events.find(e=>e.type==='lionFieldInventoryClose').startedAt,360);
  const select=events.find(e=>e.type==='lionFieldKaeyaSelectAttempt'),fightEvent=events.find(e=>e.type==='lionFieldNativeFight');
  assert.ok(fightEvent.frameId>select.frameId,'native fight begins only from a distinct post-selection capture');
  assert.equal(events.find(e=>e.type==='lionFieldAmberReturnAttempt').key,'VK_2');
  assert.ok(events.find(e=>e.type==='lionFieldInventoryPause').frameId>events.find(e=>e.type==='lionFieldAmberReturnAttempt').frameId);
  const fight=f.nativeCalls.filter(x=>x&&x.kind==='fight');assert.equal(fight.length,1);
  assert.equal(fight[0].timeout,15);assert.equal(fight[0].pickDrops,false);assert.equal(fight[0].name,'English Starter Trials');
  assert.ok(f.nativeCalls.includes('dispose'));assert.equal(f.metrics.mapCalls,0);assert.ok(f.metrics.partyCropCalls>0);
  assert.equal(f.adapter.events().filter(e=>e.type==='lionFieldNativeFight').length,1);
  assert.equal(f.adapter.events().find(e=>e.type==='lionFieldNativeFight').timeoutMs,15000);
  const replay=await f.run();assert.equal(replay.fightStarted,false);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,1);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,1);
  assert.equal(f.inputs.filter(x=>x.kind==='down').length,4,'replay sends no additional Escape, selection, return, or pause input');
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
  assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_ESCAPE','VK_3','VK_2','VK_B']);
  for(const key of ['VK_ESCAPE','VK_3','VK_2','VK_B'])assert.equal(f.inputs.filter(x=>x.kind==='up'&&x.key===key).length,1,`${key} released`);
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
  assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_ESCAPE','VK_3','VK_2','VK_B','VK_B','VK_J','VK_ESCAPE']);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,1);
});

test('a native return to the Party Setup screen is recognized as a pause proof',async()=>{
  const f=fixture({nativeFailure:true,partyAfterNative:true});
  const result=await f.run();
  assertPauseProof(result);assert.equal(result.pauseProof.kind,'party');
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,1);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,1);
});
