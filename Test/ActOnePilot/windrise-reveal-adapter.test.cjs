'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const dir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=100,height=28)=>({text,x,y,width,height});
const fieldRows=()=>[
  row('Meet Lisa at the temple',80,250,300,35),row('Amber',1680,350,100,35),row('Kaeya',1680,500,100,35),
  row('R',1580,1004,30,30),row('Q',1660,1004,30,30),row('1186/1186',900,1002,120,24)
];
const scaledPartyRows=()=>[row('Amber',150,60,300,105),row('Kaeya',150,510,300,105)];
const statueRows=()=>[...fieldRows(),row('Statue of The Seven',1190,505,290,30),row('F',1100,510,24,30)];
const inventoryRows=()=>[
  row('Food',140,32,67,31),row('Inventory capacity 9/2600',1504,34,295,27),
  row('Teyvat Fried Egg',1329,119,297,57),row('Food',1374,187,63,30),row('Use',1670,999,63,38)
];
const inventoryTransitionRows=()=>[row('Food',138,12,67,24),row('Inventory capacity 9/2600',1499,9,295,20)];
const statueDialogueRows=()=>[
  row('Auto',102,32,65,31),row('Statue of The Seven',783,850,351,46),
  row('The world opens itself before those with noble hearts.',527,909,864,35)
];
const statueUnlockMapRows=()=>[row('Starfell Valley',1500,960,190,35),row('Exploration Progress: 23.4%',1500,1000,280,30)];
function observation({session='s1',frameId=10,timestamp=1000,rows=fieldRows(),hudPatch={},map=null}={}) {
  return {session,frameId,timestamp,capture:{width:1920,height:1080},map,ocr:rows,
    hud:{world:false,groundControls:true,climbing:false,auto:false,dialogueReady:false,choice:false,journal:false,bigMap:false,
      tutorialStep:null,health:{current:1186,max:1186},enemyBars:[],objectives:['Meet Lisa at the temple'],...hudPatch}};
}
function permit({session='s1',frameId=10,witnessFrameId=frameId,action='look',dx=100,holds=2,createdAt=1500,patch={}}={}) {
  return {kind:'windriseReveal',session,frameId,witnessFrameId,witnessVerified:true,createdAt,
    lastKnownFrameId:witnessFrameId-1,action,dx,holds,...patch};
}
function fixture(options={}) {
  const requestFrameId=options.requestFrameId===undefined?10:options.requestFrameId;
  const witnessFrameId=options.witnessFrameId===undefined?requestFrameId:options.witnessFrameId;
  const pausedSourceFrameId=options.pausedSourceFrameId===undefined?requestFrameId:options.pausedSourceFrameId;
  let now=10000,frame=requestFrameId,screen=options.initialScreen||'field',transitionCaptures=0,currentPermit=options.permit||permit({frameId:requestFrameId,witnessFrameId}),writtenPermit=null;
  let raceWActive=false,wSleepCalls=0,boundaryTarget=null,boundaryReads=0,negativeSleepAttempts=0,foreground=true;
  const writes=[],inputs=[],timeline=[],captureScreens=[],files=new Map(),images=new Set(),metrics={mapCalls:0,compassCalls:0,contourCalls:0,inRangeCalls:0,captures:0,partyCropCalls:0,narrowPartyCropCalls:0,controlCropCalls:0};
  const witness=options.witness||observation({frameId:witnessFrameId,timestamp:1000});
  const known={session:'s1',frameId:witnessFrameId-1,timestamp:900,map:{map:'Teyvat',x:-1124.705,y:2080.445},hud:{health:{current:1186,max:1186}}};
  files.set('windrise-reveal.json',JSON.stringify(currentPermit));
  files.set('observations/s1/frame-'+String(witnessFrameId).padStart(4,'0')+'.json',JSON.stringify(witness));
  files.set('observations/s1/frame-'+String(witnessFrameId-1).padStart(4,'0')+'.json',JSON.stringify(options.known||known));
  if(!options.missingWitnessPng)images.add('observations/s1/frame-'+String(witnessFrameId).padStart(4,'0')+'.png');
  if(options.missingWitnessJson)files.delete('observations/s1/frame-'+String(witnessFrameId).padStart(4,'0')+'.json');

  function mat(rect=null,scale=1) {
    return {rect,scale,inRange(){metrics.inRangeCalls++;const isEnemy=rect&&rect.x===350&&rect.y===100&&rect.w===1250&&rect.h===800;
      const contours=isEnemy?(options.redBarBoxes||[]):[];
      return {findContoursAsArray(){metrics.contourCalls++;return contours.map(b=>({...b}));},dispose(){}};},
      findContoursAsArray(){metrics.contourCalls++;return [];},resize(size){return mat(rect,rect?size.width/rect.w:scale);},dispose(){}};
  }
  const context={
    Date:class extends Date { static now(){
      if(options.deadlineRace&&raceWActive&&boundaryTarget!==null&&now===boundaryTarget){boundaryReads++;if(boundaryReads===2)now+=2;}
      return now;
    } },
    ...(options.deadlineRace?{setTimeout:(resolve,ms)=>{
      if(ms<0){negativeSleepAttempts++;throw new Error('native sleep received negative duration');}
      if(raceWActive&&ms===50){wSleepCalls++;if(wSleepCalls===10){now+=49;boundaryTarget=now;boundaryReads=0;return setImmediate(resolve);}}
      now+=ms;return setImmediate(resolve);
    }}:{}),
    genshin:{isRemoteDesktopSession:true,windowsSessionId:5,get isGameForeground(){return foreground;},
      getPositionFromMap(){metrics.mapCalls++;return {map:'Teyvat',x:-1124.705,y:2080.445};},
      getCameraOrientation(){metrics.compassCalls++;return 42;}},
    file:{isExists:p=>{
      if(options.missingWitnessPng&&p==='observations/s1/frame-'+String(witnessFrameId).padStart(4,'0')+'.png')return false;
      if(options.missingWitnessJson&&p==='observations/s1/frame-'+String(witnessFrameId).padStart(4,'0')+'.json')return false;
      return files.has(p)||images.has(p)||fs.existsSync(path.join(dir,p));
    },
      readTextSync:p=>options.missingStatueDialogue&&p==='statue-dialogue.js'?'':files.has(p)?files.get(p):fs.existsSync(path.join(dir,p))?fs.readFileSync(path.join(dir,p),'utf8'):'',
      writeTextSync:(p,v)=>{writes.push({path:p,value:v,at:now});if(p==='windrise-reveal.json')timeline.push('permit-write');if(p==='windrise-reveal.json'&&options.rejectPermitWrite)return true;if(p.endsWith('.statue-dialogue-actions.json')&&options.rejectStatueDialogueWrite)return false;files.set(p,p.endsWith('.statue-dialogue-actions.json')&&options.alterStatueDialogueReadback?'{}':v);if(p==='windrise-reveal.json')writtenPermit=v;if(p==='pause-protection.json'&&options.restoreAfterPending){screen='inventory';foreground=true;}return true;},
      writeImageSync:p=>{images.add(p);return true;}},
    RecognitionObject:{Ocr:(x,y,w,h)=>({x,y,w,h})},
    captureGameRegion:()=>{
      metrics.captures++;
      if(screen==='field'&&options.failFieldCaptureOnce){options.failFieldCaptureOnce=false;throw new Error('injected field capture failure');}
      const capturedScreen=screen;captureScreens.push(capturedScreen);let rows;
      if(screen==='transition'){
        rows=options.transitionRows||inventoryTransitionRows();transitionCaptures++;
        if(transitionCaptures>=(options.inventoryTransitionFrames||1))screen='field';
      } else if(screen==='unlockMap'){
        rows=options.unlockMapRows||statueUnlockMapRows();screen='field';
      } else rows=screen==='inventory'?inventoryRows():screen==='postInteraction'?
        (options.postInteractionRows||[...fieldRows(),row('Auto',50,50),row('Lisa',900,850),row('The statue responds',900,920,250,30)]):
        (options.fullFieldRows||fieldRows());
      return {width:1920,height:1080,srcMat:mat(),
        findMulti(ro){const found=rows.filter(r=>r.x>=ro.x&&r.x<ro.x+ro.w&&r.y>=ro.y&&r.y<ro.y+ro.h).map(r=>({...r}));found.count=found.length;return found;},
        deriveCrop(x,y,w,h){if(x===1630&&y===330&&w===230&&h===300)metrics.partyCropCalls++;
          if(x===1650&&y===390&&w===100&&h===45)metrics.narrowPartyCropCalls++;
          if(x===1520&&y===985&&w===390&&h===80)metrics.controlCropCalls++;
          return {srcMat:mat({x,y,w,h}),dispose(){}};},dispose(){}};
    },
    ImageRegion:class{constructor(srcMat){this.srcMat=srcMat;}findMulti(ro){
      const rect=this.srcMat.rect;
      const broad=rect&&rect.x===1630&&rect.y===330&&rect.w===230&&rect.h===300;
      const narrow=rect&&rect.x===1650&&rect.y===390&&rect.w===100&&rect.h===45;
      const health=rect&&rect.x===900&&rect.y===990&&rect.w===125&&rect.h===40;
      const controls=rect&&rect.x===1520&&rect.y===985&&rect.w===390&&rect.h===80;
      const rows=broad?(options.partyCropRows===undefined?scaledPartyRows():options.partyCropRows):
        narrow?(options.narrowPartyCropRows||[]):health?(options.healthCropRows||[]):controls?(options.controlCropRows||[]):[];
      const a=rows.filter(r=>r.x>=ro.x&&r.x<ro.x+ro.w&&r.y>=ro.y&&r.y<ro.y+ro.h).map(r=>({...r}));a.count=a.length;return a;
    }dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},
      Scalar:class{constructor(a,b,c){this.values=[a,b,c];}},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},
      Cv2:{boundingRect:b=>b,contourArea:()=>0,countNonZero:()=>0},ColorConversionCodes:{GRAY2BGR:0,BGR2HSV:1}}},
    keyDown:key=>{inputs.push({kind:'down',key,at:now,screen});timeline.push('input:'+key);if(options.deadlineRace&&key==='VK_W'){raceWActive=true;wSleepCalls=0;}if(key==='VK_ESCAPE'&&options.failEscapeDown)throw new Error('injected Escape failure');if(key==='VK_ESCAPE')screen=options.inventoryTransitionOnce?'transition':'field';if(key==='VK_B')screen='inventory';if(key==='VK_F'){screen='postInteraction';if(options.focusLostOnF)foreground=false;}if(key==='VK_SPACE'){if(options.failSpaceDown){options.failSpaceDown=false;throw new Error('injected Space failure');}screen=options.statueUnlockMap?'unlockMap':'inventory';}},
    keyUp:key=>{inputs.push({kind:'up',key,at:now});if(key==='VK_W'){raceWActive=false;boundaryTarget=null;boundaryReads=0;}},moveMouseBy:(dx,dy)=>{inputs.push({kind:'look',dx,dy,at:now});timeline.push('input:look');},click(){},sleep:async ms=>{if(ms<0)throw new Error('native sleep received negative duration');now+=ms;await new Promise(resolve=>setImmediate(resolve));},log:{info(){}}
  };
  vm.runInNewContext(fs.readFileSync(path.join(dir,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(5);
  adapter.beginMission({mission:'questStep',step:'windriseReveal',session:'s1',id:'req-1',expectedFrameId:requestFrameId,createdAt:900,objective:'Meet Lisa at the temple'});
  async function observeNext() { frame++; now+=10;return adapter.observe('s1',frame); }
  return {adapter,context,files,writes,inputs,timeline,captureScreens,metrics,observeNext,setNow:v=>{now=v;},getNow:()=>now,getNegativeSleepAttempts:()=>negativeSleepAttempts,
    setScreen:s=>{screen=s;},getWrittenPermit:()=>writtenPermit};
}
function pausedFoodFixture(options={}) {
  const requestFrameId=options.requestFrameId===undefined?20:options.requestFrameId;
  const witnessFrameId=options.witnessFrameId===undefined?10:options.witnessFrameId;
  const witness=options.witness||observation({frameId:witnessFrameId,timestamp:1000});
  if(!Number.isFinite(witness.hud.compassAngle))witness.hud.compassAngle=42;
  const f=fixture({...options,witness,requestFrameId,witnessFrameId,pausedSourceFrameId:requestFrameId,initialScreen:'inventory',
    permit:options.permit||permit({frameId:requestFrameId,witnessFrameId,createdAt:3000})});
  const pausedSource=observation({frameId:requestFrameId,timestamp:2000,rows:inventoryRows()});
  f.files.set('observations/s1/frame-'+String(requestFrameId).padStart(4,'0')+'.json',JSON.stringify(pausedSource));
  f.files.set('observations/s1/frame-'+String(requestFrameId).padStart(4,'0')+'.png','paused-source');
  return f;
}

test('paused Food closes once before fresh field capture and guarded batch, then returns with immutable local pause proof',async()=>{
  const f=pausedFoodFixture();const initial=await f.adapter.observe('s1',20);
  assert.equal(f.adapter.windriseRevealReady(initial),false,'the wrapper must not treat the paused inventory frame as field evidence');
  const result=await f.adapter.runWindriseReveal(initial,f.observeNext);
  assert.equal(result.turns,1);assert.equal(result.moves,0);assert.equal(result.pauseVerified,true);
  assert.equal(result.pauseProof.kind,'inventory');assert.ok(Object.isFrozen(result.pauseProof));
  assert.ok(Object.isFrozen(result.pauseProof.evidence));assert.equal(result.pausedInventory,true);
  assert.equal(f.adapter.events().filter(e=>e.type==='windriseInventoryClose').length,1);
  assert.ok(f.adapter.events().some(e=>e.type==='windriseRevealAction'));
  const downs=f.inputs.filter(i=>i.kind==='down').map(i=>i.key);
  assert.equal(downs[0],'VK_ESCAPE');assert.equal(downs.filter(k=>k==='VK_ESCAPE').length,1);
  assert.deepEqual(downs,['VK_ESCAPE','VK_B']);
  assert.ok(f.metrics.captures>=3,'initial paused proof, fresh post-close field, and final pause proof');
  assert.ok(result.pauseProof.pauseFrameId>20);assert.equal(result.frameId,result.pauseProof.pauseFrameId);
});

test('fading inventory labels wait for the next field capture without repeating Escape or acting early',async()=>{
  const f=pausedFoodFixture({inventoryTransitionOnce:true});const initial=await f.adapter.observe('s1',20),postClose=[];
  const result=await f.adapter.runWindriseReveal(initial,async()=>{const o=await f.observeNext();postClose.push(o);return o;});
  assert.ok(postClose.length>=2,'wrapper should poll past the ambiguous transition capture');
  assert.equal(postClose[0].frameId,21);assert.equal(postClose[0].hud.health,null);
  assert.ok(postClose[0].ocr.some(r=>r.text==='Food'&&r.x===138&&r.y===12));
  assert.ok(postClose[0].ocr.some(r=>r.text==='Inventory capacity 9/2600'&&r.x===1499&&r.y===9));
  assert.equal(postClose[1].frameId,22);assert.equal(postClose[1].hud.health.current,1186);
  assert.ok(result.turns===1&&result.moves===0&&result.interactions===0);
  assert.equal(result.fieldFrameId,24,'the result retains the last field frame before pause proof updates frameId');
  assert.ok(result.frameId>result.fieldFrameId);
  assert.ok(result.pauseVerified);assert.equal(result.pauseProof.kind,'inventory');
  assert.equal(f.adapter.events().filter(e=>e.type==='windriseInventoryClose').length,1);
  assert.deepEqual(f.inputs.filter(i=>i.kind==='down').map(i=>i.key),['VK_ESCAPE','VK_B']);
  assert.equal(f.inputs.filter(i=>i.kind==='look').length,1);
  assert.equal(f.inputs.filter(i=>i.kind==='down'&&i.key==='VK_W').length,0);
});

test('missing local pause protector fails while still paused and before Escape',async()=>{
  const f=pausedFoodFixture();const initial=await f.adapter.observe('s1',20);
  const original=f.context.file.readTextSync;
  f.context.file.readTextSync=p=>p==='local-pause.js'?'':original(p);
  await assert.rejects(()=>f.adapter.runWindriseReveal(initial,f.observeNext),/Local verified-pause protector is required before unpausing|ActOneLocalPause is not defined/);
  assert.deepEqual(f.inputs,[]);assert.equal(f.adapter.events().some(e=>e.type==='windriseInventoryClose'),false);
});

test('close-attempt readiness failure stops action and still verifies a local pause',async()=>{
  const lowRows=fieldRows().map(r=>r.text==='1186/1186'?row('500/1186',900,1002,120,24):r);
  const f=pausedFoodFixture({fullFieldRows:lowRows,healthCropRows:[row('500/1186',0,0,375,120)]});
  const initial=await f.adapter.observe('s1',20);const result=await f.adapter.runWindriseReveal(initial,f.observeNext);
  assert.equal(result.moves,0);assert.equal(result.turns,0);assert.equal(result.interactions,0);
  assert.equal(result.pauseVerified,true);assert.equal(result.pausedInventory,true);
  assert.equal(f.adapter.events().some(e=>e.type==='windriseRevealAction'),false);
  assert.deepEqual(f.inputs.filter(i=>i.kind==='down').map(i=>i.key),['VK_ESCAPE','VK_B']);
});

test('paused permit rejects a changed saved field heading and still verifies the local pause',async()=>{
  const witness=observation({frameId:10,timestamp:1000,hudPatch:{compassAngle:90}});
  const f=pausedFoodFixture({witness});const initial=await f.adapter.observe('s1',20);
  const result=await f.adapter.runWindriseReveal(initial,f.observeNext);
  assert.equal(result.turns,0);assert.equal(result.moves,0);assert.equal(result.interactions,0);
  assert.equal(result.pauseVerified,true);assert.equal(result.pausedInventory,true);
  assert.equal(f.adapter.events().some(e=>e.type==='windriseRevealAction'),false);
  assert.deepEqual(f.inputs.filter(i=>i.kind==='down').map(i=>i.key),['VK_ESCAPE','VK_B']);
});

test('Escape and capture failures still reach a confirmed pause before the wrapper returns',async()=>{
  for(const options of [{failEscapeDown:true},{failFieldCaptureOnce:true}]){
    const f=pausedFoodFixture(options);const initial=await f.adapter.observe('s1',20);
    const result=await f.adapter.runWindriseReveal(initial,f.observeNext);
    assert.equal(result.pauseVerified,true);assert.equal(result.pausedInventory,true);
    assert.ok(f.adapter.events().some(e=>e.type==='pauseProtectionVerified'));
  }
});

test('unknown post-interaction UI remains pending until an explicit inventory restoration',async()=>{
  const witness=observation({frameId:10,timestamp:1000,rows:statueRows()});
  const unknown=[...fieldRows(),row('Auto',50,50),row('Lisa',900,850),row('A long dialogue subtitle appears',800,920,350,35)];
  const f=pausedFoodFixture({witness,fullFieldRows:statueRows(),postInteractionRows:unknown,restoreAfterPending:true,permit:permit({frameId:20,witnessFrameId:10,action:'interact',createdAt:3000})});
  const initial=await f.adapter.observe('s1',20);const result=await f.adapter.runWindriseReveal(initial,f.observeNext);
  assert.equal(result.interactions,1);assert.equal(result.pauseVerified,true);assert.equal(result.pauseProof.kind,'inventory');
  assert.ok(f.adapter.events().some(e=>e.type==='pauseProtectionStarted'));
  assert.ok(f.writes.some(w=>w.path==='pause-protection.json'&&JSON.parse(w.value).state==='pause-pending'));
  assert.ok(f.inputs.filter(i=>i.kind==='down').every(i=>['VK_ESCAPE','VK_F','VK_B'].includes(i.key)));
  assert.equal(f.inputs.filter(i=>i.kind==='down'&&i.key==='VK_F').length,1);
});

test('Windrise observation leaves GPS unqueried and performs fresh enemy scan plus compass read',async()=>{
  const f=fixture();
  const o=await f.adapter.observe('s1',10);
  assert.equal(o.map,null,'the tempting global GPS stub must not become an observation coordinate');
  assert.equal(f.metrics.mapCalls,0);
  assert.ok(f.metrics.inRangeCalls>0);
  assert.ok(f.metrics.contourCalls>0);
  assert.equal(o.hud.compassAngle,42);
  assert.equal(f.metrics.compassCalls,1);
  assert.equal(o.hud.enemyBars.length,0);
});

test('same-capture Windrise control crop can restore Q evidence but never invent controls',async()=>{
  const missingControls=fieldRows().filter(r=>r.text!=='E'&&r.text!=='Q');
  const repaired=fixture({fullFieldRows:missingControls,controlCropRows:[row('Q',420,57,90,90)]});
  const observed=await repaired.adapter.observe('s1',10);
  assert.equal(observed.hud.groundControls,true);
  assert.ok(observed.ocr.some(r=>r.text==='Q'&&r.x>1500&&r.y>990));
  assert.equal(repaired.metrics.controlCropCalls,1);

  for(const controlCropRows of [[],[row('Space',180,57,90,90)]]) {
    const denied=fixture({fullFieldRows:missingControls,controlCropRows});
    const frame=await denied.adapter.observe('s1',10);
    assert.equal(frame.hud.groundControls,false);
    assert.equal(denied.metrics.controlCropCalls,1);
    const result=await denied.adapter.runWindriseReveal(frame,denied.observeNext);
    assert.equal(result.moves,0);assert.equal(result.turns,0);assert.equal(result.interactions,0);
    assert.deepEqual(denied.inputs.filter(i=>i.kind==='down').map(i=>i.key),['VK_B']);
    assert.equal(result.pauseVerified,true);
  }

  const alreadyVerified=fixture();
  const full=await alreadyVerified.adapter.observe('s1',10);
  assert.equal(full.hud.groundControls,true);
  assert.equal(alreadyVerified.metrics.controlCropCalls,0,'complete full-frame E/Q evidence skips the crop');
});

test('outdoor enemy scan excludes red leaf pixels unless a nearby enemy level anchors them',async()=>{
  const leaf={x:340,y:386,width:4,height:3};
  const unanchored=fixture({redBarBoxes:[leaf]});
  const ordinary=await unanchored.adapter.observe('s1',10);
  assert.equal(ordinary.hud.enemyBars.length,0,'4x3 environmental red leaf is not a threat');

  const anchored=fixture({redBarBoxes:[leaf],fullFieldRows:[...fieldRows(),row('Lv.3',670,450,40,20)]});
  const enemy=await anchored.adapter.observe('s1',10);
  assert.equal(enemy.hud.enemyBars.length,1,'nearby same-frame Lv.3 anchors a nearly depleted 4x3 bar');
  assert.equal(enemy.hud.enemyBars[0].x,692);

  const playerLabel=fixture({redBarBoxes:[leaf],fullFieldRows:[...fieldRows(),row('Lv.7',1660,1000,55,25)]});
  const falseAnchor=await playerLabel.adapter.observe('s1',10);
  assert.equal(falseAnchor.hud.enemyBars.length,0,'player level at the bottom HUD cannot anchor a distant red leaf');
});

test('same-capture party crop repairs missing full-frame Amber and permits bounded reveal plus inventory pause',async()=>{
  const full=fieldRows().filter(r=>r.text!=='Amber');
  const f=fixture({fullFieldRows:full,partyCropRows:scaledPartyRows()});
  const initial=await f.adapter.observe('s1',10);
  assert.ok(initial.ocr.some(r=>r.text==='Amber'&&r.x>1550&&r.y>300&&r.y<600));
  assert.equal(f.adapter.windriseRevealReady(initial),true);
  assert.equal(f.metrics.partyCropCalls,1);
  const result=await f.adapter.runWindriseReveal(initial,f.observeNext);
  assert.equal(result.turns,1);assert.equal(result.pausedInventory,true);
  assert.equal(f.adapter.events().filter(e=>e.type==='windriseRevealAction').length,1);
  assert.equal(f.inputs.filter(i=>i.kind==='down'&&i.key==='VK_B').length,1);
});

test('missing or wrong same-capture party crop cannot repair missing full-frame roster evidence',async()=>{
  const full=fieldRows().filter(r=>r.text!=='Amber');
  for(const partyCropRows of [[],[row('Am6er',120,60,300,105),row('Kaeya',120,510,300,105)]]) {
    const f=fixture({fullFieldRows:full,partyCropRows});
    const initial=await f.adapter.observe('s1',10);
    assert.equal(f.metrics.partyCropCalls,1);
    assert.equal(f.adapter.windriseRevealReady(initial),false);
    const result=await f.adapter.runWindriseReveal(initial,f.observeNext);
    assert.equal(result.turns,0);assert.equal(result.moves,0);
    assert.deepEqual(f.inputs.filter(i=>i.kind==='down').map(i=>i.key),['VK_B']);
    assert.equal(result.pauseVerified,true);
    assert.equal(f.adapter.events().some(e=>e.type==='windriseRevealAction'),false);
  }
});

test('broad Amber4 OCR is repaired only by exact Amber from the narrow same-capture crop',async()=>{
  const full=fieldRows().filter(r=>r.text!=='Amber');
  const broad=[row('Amber4',150,60,300,105),row('Kaeya',150,510,300,105)];
  const narrow=[row('Amber',60,30,240,90)];
  const f=fixture({fullFieldRows:full,partyCropRows:broad,narrowPartyCropRows:narrow});
  const initial=await f.adapter.observe('s1',10);
  assert.ok(initial.ocr.some(r=>r.text==='Amber'&&r.x>=1550&&r.x<=1800&&r.y>=300&&r.y<=600));
  assert.equal(f.metrics.partyCropCalls,1);assert.equal(f.metrics.narrowPartyCropCalls,1);
  assert.equal(f.adapter.windriseRevealReady(initial),true);
  const result=await f.adapter.runWindriseReveal(initial,f.observeNext);
  assert.equal(result.turns,1);assert.equal(result.pausedInventory,true);
  assert.equal(f.adapter.events().filter(e=>e.type==='windriseRevealAction').length,1);
});

test('missing or incorrect narrow Amber read cannot repair broad Amber4 evidence',async()=>{
  const full=fieldRows().filter(r=>r.text!=='Amber');
  const broad=[row('Amber4',150,60,300,105),row('Kaeya',150,510,300,105)];
  for(const narrowPartyCropRows of [[],[row('Amber4',60,30,240,90)]]) {
    const f=fixture({fullFieldRows:full,partyCropRows:broad,narrowPartyCropRows});
    const initial=await f.adapter.observe('s1',10);
    assert.equal(f.metrics.partyCropCalls,1);assert.equal(f.metrics.narrowPartyCropCalls,1);
    assert.equal(f.adapter.windriseRevealReady(initial),false);
    const result=await f.adapter.runWindriseReveal(initial,f.observeNext);
    assert.equal(result.turns,0);assert.equal(result.moves,0);
    assert.deepEqual(f.inputs.filter(i=>i.kind==='down').map(i=>i.key),['VK_B']);
    assert.equal(result.pauseVerified,true);
    assert.equal(f.adapter.events().some(e=>e.type==='windriseRevealAction'),false);
  }
});

test('same-capture party crop is skipped when full-frame OCR already has both names',async()=>{
  const f=fixture({fullFieldRows:fieldRows(),partyCropRows:[]});
  const initial=await f.adapter.observe('s1',10);
  assert.equal(f.adapter.windriseRevealReady(initial),true);
  assert.equal(f.metrics.partyCropCalls,0);
});

test('valid root permit is consumed and verified before one bounded root-directed action, then inventory pause is verified',async()=>{
  const f=fixture();const initial=await f.adapter.observe('s1',10);
  const result=await f.adapter.runWindriseReveal(initial,f.observeNext);
  assert.equal(result.rootDirected,true);assert.equal(result.turns,1);assert.equal(result.moves,0);
  assert.equal(result.pausedInventory,true);assert.equal(result.questComplete,false);
  const action=f.adapter.events().find(e=>e.type==='windriseRevealAction');
  assert.deepEqual(JSON.parse(JSON.stringify(action)),{type:'windriseRevealAction',rootDirected:true,action:'look',amount:100,frameId:10,startedAt:10000,finishedAt:10000});
  const permitEvent=f.adapter.events().find(e=>e.type==='windriseRevealPermit');
  assert.equal(permitEvent.rootDirected,true);
  assert.ok(f.timeline.indexOf('permit-write')<f.timeline.indexOf('input:look'),'permit consumption write precedes action');
  assert.equal(JSON.parse(f.getWrittenPermit()).usedAt,10000);
  assert.equal(f.inputs.filter(i=>i.kind==='look').length,1);
  assert.equal(f.inputs.filter(i=>i.kind==='down'&&i.key==='VK_B').length,1);
  assert.ok(f.adapter.events().some(e=>e.type==='windriseRevealPause'));
  assert.ok(f.adapter.events().filter(e=>e.type==='windriseRevealAction').length<=1);
  assert.throws(()=>f.adapter.windriseRevealPlan(),/Unused root-witnessed Windrise permit/);
});

test('missing, expired, pre-used, cross-session and out-of-scope coordinate permits send no input',async t=>{
  const cases=[
    {name:'missing permit',patch:{permitFile:null}},
    {name:'missing witness JSON',missingWitnessJson:true},
    {name:'missing witness PNG',missingWitnessPng:true},
    {name:'expired witness authorization',permit:permit({createdAt:-120001})},
    {name:'pre-used permit',permit:permit({patch:{usedAt:9999}})},
    {name:'wrong session',permit:permit({patch:{session:'other'}})},
    {name:'out-of-scope known coordinate',known:{session:'s1',frameId:9,timestamp:900,map:{map:'Teyvat',x:-1110,y:2080.445},hud:{health:{current:1186,max:1186}}}}
  ];
  for(const c of cases){await t.test(c.name,async()=>{
    const opts={...c};const f=fixture(opts);if(c.patch&&c.patch.permitFile===null)f.files.delete('windrise-reveal.json');
    const o=await f.adapter.observe('s1',10);
    assert.throws(()=>f.adapter.windriseRevealPlan(),/Unused root-witnessed Windrise permit/);
    assert.deepEqual(f.inputs,[]);assert.equal(f.adapter.events().some(e=>e.type==='windriseRevealAction'),false);
  });}
});

test('altered or unknown-UI witness sources cannot authorize a live frame',async()=>{
  for(const witness of [
    observation({frameId:10,timestamp:1000,hudPatch:{dialogueReady:true}}),
    observation({frameId:11,timestamp:1000}),
    observation({frameId:10,timestamp:1000,hudPatch:{health:{current:1186,max:1055}}}),
    observation({frameId:10,timestamp:1000,rows:[...fieldRows(),row('Trial',1800,420)]})
  ]){
    const f=fixture({witness});await f.adapter.observe('s1',10);
    assert.throws(()=>f.adapter.windriseRevealPlan(),/Unused root-witnessed Windrise permit/);
    assert.deepEqual(f.inputs,[]);
  }
});

test('failed permit readback blocks action and same-frame or cross-session attempts fail closed',async()=>{
  const failed=fixture({rejectPermitWrite:true});const initial=await failed.adapter.observe('s1',10);
  const result=await failed.adapter.runWindriseReveal(initial,failed.observeNext);
  assert.match(result.reason,/Windrise permit consumption not verified/);
  assert.deepEqual(failed.inputs.filter(i=>i.kind==='down').map(i=>i.key),['VK_B']);
  assert.equal(result.pauseVerified,true);

  const guarded=fixture();const o=await guarded.adapter.observe('s1',10);
  assert.equal(guarded.adapter.windriseRevealReady({...o,session:'other'}),false);
  assert.equal(guarded.adapter.windriseRevealConsumePermit({...o,session:'other'}),false);
  assert.deepEqual(guarded.inputs,[]);
});

test('a consumed permit authorizes one action only on its exact session and frame',async()=>{
  const same=fixture();const o=await same.adapter.observe('s1',10);
  assert.equal(same.adapter.windriseRevealConsumePermit(o),true);
  await same.adapter.windriseRevealAction('look',100);
  await assert.rejects(()=>same.adapter.windriseRevealAction('look',100),/Fresh bounded root-witnessed field action required/);
  assert.equal(same.inputs.filter(i=>i.kind==='look').length,1);

  const other=fixture();const initial=await other.adapter.observe('s1',10);
  assert.equal(other.adapter.windriseRevealConsumePermit(initial),true);
  const foreign=await other.adapter.observe('other',11);
  await assert.rejects(()=>other.adapter.windriseRevealAction('look',100),/Fresh bounded root-witnessed field action required/);
  assert.equal(foreign.session,'other');assert.deepEqual(other.inputs,[]);
});

test('forward permits accept at most 24 fresh independently observed 500ms holds',async()=>{
  for(const holds of [0,-1,1.5,25]) {
    const denied=fixture({permit:permit({action:'forward',holds})});const initial=await denied.adapter.observe('s1',10);
    const result=await denied.adapter.runWindriseReveal(initial,denied.observeNext);
    assert.match(result.reason,/Unused root-witnessed Windrise permit/);
    assert.equal(result.moves,0);assert.deepEqual(denied.inputs.filter(i=>i.kind==='down').map(i=>i.key),['VK_B']);
    assert.equal(result.pauseVerified,true);
  }

  const bounded=fixture({permit:permit({action:'forward',holds:24})});const start=await bounded.adapter.observe('s1',10);
  const completed=await bounded.adapter.runWindriseReveal(start,bounded.observeNext);
  assert.equal(completed.moves,24);assert.equal(completed.pausedInventory,true);
  const actions=bounded.adapter.events().filter(e=>e.type==='windriseRevealAction');
  assert.equal(actions.length,24);assert.ok(actions.every(e=>e.rootDirected&&e.action==='forward'&&e.amount===500));
  assert.equal(bounded.inputs.filter(i=>i.kind==='down'&&i.key==='VK_W').length,24);
  assert.equal(bounded.inputs.filter(i=>i.kind==='down'&&i.key==='VK_B').length,1);
});

test('Windrise definition is evaluated once per mission while valid readiness still permits the requested hold count',async()=>{
  const f=fixture({permit:permit({action:'forward',holds:3})});let moduleReads=0;
  const read=f.context.file.readTextSync;f.context.file.readTextSync=p=>{if(p==='windrise-reveal.js')moduleReads++;return read(p);};
  const initial=await f.adapter.observe('s1',10);const result=await f.adapter.runWindriseReveal(initial,f.observeNext);
  assert.equal(result.moves,3);assert.equal(result.turns,0);assert.equal(result.pauseVerified,true);
  assert.equal(f.inputs.filter(i=>i.kind==='down'&&i.key==='VK_W').length,3);
  assert.equal(moduleReads,1,'module source evaluation stays bounded across all readiness checks in the mission');
});

test('stale post-hold frame blocks the next forward input and records its guard diagnosis',async()=>{
  const f=fixture({permit:permit({action:'forward',holds:3})});let readyCalls=0;
  const ready=f.adapter.windriseRevealReady.bind(f.adapter);
  f.adapter.windriseRevealReady=o=>{
    const accepted=ready(o);readyCalls++;
    // The fifth readiness check is the successful post-hold check. Age that same capture before the next pre-hold check.
    if(readyCalls===5&&accepted)f.setNow(o.timestamp+1001);
    return accepted;
  };
  const initial=await f.adapter.observe('s1',10);const result=await f.adapter.runWindriseReveal(initial,f.observeNext);
  assert.equal(result.moves,1);assert.equal(result.pauseVerified,true);
  assert.equal(f.inputs.filter(i=>i.kind==='down'&&i.key==='VK_W').length,1,'no second hold may start from a stale capture');
  const rejected=f.adapter.events().filter(e=>e.type==='windriseRevealGuardRejected');
  assert.equal(rejected.length,1);
  assert.equal(rejected[0].frameId,11);assert.ok(rejected[0].ageMs>=1000);
  assert.equal(rejected[0].currentFrameValid,true);assert.equal(rejected[0].fieldReady,false);
  assert.ok(Number.isFinite(rejected[0].guardMs)&&rejected[0].guardMs>=0);
});

test('bounded W holds tolerate a deadline crossing between clock reads with matched releases',async()=>{
  const f=fixture({deadlineRace:true,permit:permit({action:'forward',holds:2})});
  const initial=await f.adapter.observe('s1',10);const result=await f.adapter.runWindriseReveal(initial,f.observeNext);
  assert.equal(result.moves,2);assert.equal(result.pauseVerified,true);assert.equal(result.pausedInventory,true);
  assert.equal(f.getNegativeSleepAttempts(),0,'native sleep must never receive a negative duration');
  const downs=f.inputs.filter(i=>i.kind==='down'&&i.key==='VK_W'),ups=f.inputs.filter(i=>i.kind==='up'&&i.key==='VK_W');
  assert.equal(downs.length,2);assert.equal(ups.length,2);
  for(let i=0;i<2;i++)assert.ok(ups[i].at>=downs[i].at+500,'each W hold reaches its full bounded duration before release');
  const events=f.adapter.events().filter(e=>e.type==='key'&&e.key==='VK_W');
  assert.equal(events.length,2);assert.ok(events.every(e=>e.durationMs===500&&e.finishedAt>=e.startedAt+500));
});

test('unreadable level-three red bar blocks forward but permits a root-directed retreat',async()=>{
  const redBar={x:180,y:250,width:90,height:8};
  const forward=fixture({redBarBoxes:[redBar],permit:permit({action:'forward',holds:1})});
  const threatened=await forward.adapter.observe('s1',10);
  assert.equal(threatened.hud.enemyBars.length,1);
  assert.equal(forward.adapter.windriseRevealReady(threatened),false);
  const stopped=await forward.adapter.runWindriseReveal(threatened,forward.observeNext);
  assert.equal(stopped.moves,0);assert.equal(stopped.turns,0);assert.equal(stopped.interactions,0);
  assert.equal(stopped.pausedInventory,true);
  assert.deepEqual(forward.inputs.filter(i=>i.kind==='down').map(i=>i.key),['VK_B']);
  assert.equal(forward.adapter.events().some(e=>e.type==='windriseRevealAction'),false);
  const pausePermit=forward.adapter.events().find(e=>e.type==='windriseRevealPermit');
  assert.equal(pausePermit.pauseOnly,true);assert.equal(JSON.parse(forward.getWrittenPermit()).pauseOnly,true);

  const witness=observation({frameId:10,timestamp:1000,hudPatch:{enemyBars:[{x:575,y:354,width:90,height:8}]}});
  const retreat=fixture({redBarBoxes:[redBar],witness,permit:permit({action:'retreat',holds:1})});
  const start=await retreat.adapter.observe('s1',10);
  assert.equal(start.hud.enemyBars.length,1);
  assert.equal(retreat.adapter.windriseRevealReady(start),true);
  const result=await retreat.adapter.runWindriseReveal(start,retreat.observeNext);
  assert.equal(result.retreats,1);assert.equal(result.moves,0);assert.equal(result.pausedInventory,true);
  const action=retreat.adapter.events().find(e=>e.type==='windriseRevealAction');
  assert.equal(action.action,'retreat');assert.equal(action.amount,500);assert.equal(action.rootDirected,true);
  assert.equal(retreat.inputs.filter(i=>i.kind==='down'&&i.key==='VK_S').length,1);
});

test('statue interaction requires one exact F/Statue pair and stops after F plus wait and observation',async()=>{
  const validWitness=observation({frameId:10,timestamp:1000,rows:statueRows()});
  const valid=fixture({witness:validWitness,fullFieldRows:statueRows(),postInteractionRows:fieldRows(),permit:permit({action:'interact'})});
  const initial=await valid.adapter.observe('s1',10);
  const result=await valid.adapter.runWindriseReveal(initial,valid.observeNext);
  assert.equal(result.interactions,1);assert.equal(result.pausedInventory,true);assert.equal(result.pauseVerified,true);
  assert.equal(result.questComplete,false);assert.equal(result.inputMs,1330);
  const action=valid.adapter.events().find(e=>e.type==='windriseRevealAction');
  assert.equal(action.action,'interact');assert.equal(action.amount,60);assert.equal(action.rootDirected,true);
  assert.deepEqual(valid.inputs.filter(i=>i.kind==='down').map(i=>i.key),['VK_F','VK_B']);
  assert.equal(valid.metrics.captures,5,'initial capture, post-interaction, pause-ready, pause attempt, and proof frames');
  assert.equal(valid.adapter.events().some(e=>e.type==='pauseProtectionVerified'),true);

  // A fresh runner mission cannot reuse the consumed statue witness.
  valid.adapter.beginMission({mission:'questStep',step:'windriseReveal',session:'s1',id:'req-statue-replay',expectedFrameId:10,createdAt:900,objective:'Meet Lisa at the temple'});
  valid.setScreen('field');
  const replayFrame=await valid.observeNext();
  const replayResult=await valid.adapter.runWindriseReveal(replayFrame,valid.observeNext);
  assert.equal(replayResult.interactions,0);
  assert.equal(valid.inputs.filter(i=>i.kind==='down'&&i.key==='VK_F').length,1);

  for(const rows of [
    [...statueRows().filter(r=>r.text!=='F')],
    [...statueRows(),row('Statue of The Seven',1190,505,290,30)]
  ]) {
    const denied=fixture({witness:validWitness,fullFieldRows:rows,permit:permit({action:'interact'})});
    const frame=await denied.adapter.observe('s1',10);
    const deniedResult=await denied.adapter.runWindriseReveal(frame,denied.observeNext);
    assert.equal(deniedResult.interactions,0);assert.equal(deniedResult.pausedInventory,true);
    assert.deepEqual(denied.inputs.filter(i=>i.kind==='down').map(i=>i.key),['VK_B']);
    assert.equal(deniedResult.pauseVerified,true);
  }
});

test('known frame-1180 Statue dialogue advances once and the pause guardian proves inventory afterward',async()=>{
  const witness=observation({frameId:1178,rows:statueRows()});
  const f=fixture({requestFrameId:1178,witnessFrameId:1178,witness,fullFieldRows:statueRows(),postInteractionRows:statueDialogueRows(),
    permit:permit({frameId:1178,witnessFrameId:1178,action:'interact'})});
  const initial=await f.adapter.observe('s1',1178),seen=[];
  const result=await f.adapter.runWindriseReveal(initial,async()=>{const o=await f.observeNext();seen.push(o);return o;});
  assert.equal(result.interactions,1);assert.equal(result.pauseVerified,true);assert.equal(result.pauseProof.kind,'inventory');
  assert.ok(seen.some(o=>o.frameId===1180&&o.hud.dialogueReady===true&&o.ocr.some(r=>r.text==='The world opens itself before those with noble hearts.')));
  const advance=f.adapter.events().filter(e=>e.type==='windriseStatueDialogueAdvance');
  assert.equal(advance.length,1);assert.equal(advance[0].frameId,1180);
  assert.deepEqual(f.inputs.filter(i=>i.kind==='down').map(i=>i.key),['VK_F','VK_SPACE']);
  assert.equal(f.inputs.filter(i=>i.kind==='down'&&i.key==='VK_SPACE').length,1);
  assert.equal(f.inputs.filter(i=>i.kind==='down'&&i.key==='VK_B').length,0);
  const marker=JSON.parse(f.files.get('reports/s1.statue-dialogue-actions.json'));
  assert.equal(marker.frameId,1180);assert.equal(marker.kind,'advance');assert.equal(marker.advanceAttempted,true);
});

test('statue unlock map is transient: guardian waits for field before opening inventory',async()=>{
  const witness=observation({frameId:1178,rows:statueRows()});
  const f=fixture({statueUnlockMap:true,requestFrameId:1178,witnessFrameId:1178,witness,fullFieldRows:statueRows(),postInteractionRows:statueDialogueRows(),
    permit:permit({frameId:1178,witnessFrameId:1178,action:'interact'})});
  const initial=await f.adapter.observe('s1',1178),result=await f.adapter.runWindriseReveal(initial,f.observeNext);
  const mapIndex=f.captureScreens.indexOf('unlockMap'),fieldIndex=f.captureScreens.indexOf('field',mapIndex+1);
  assert.ok(mapIndex>=0,'the unlock map transition was captured');
  assert.ok(fieldIndex>mapIndex,'the transient map was followed by a field capture');
  assert.equal(result.pauseVerified,true);assert.equal(result.pauseProof.kind,'inventory');
  assert.deepEqual(f.inputs.filter(i=>i.kind==='down').map(i=>i.key),['VK_F','VK_SPACE','VK_B']);
  assert.equal(f.inputs.filter(i=>i.kind==='down'&&i.key==='VK_B').length,1);
  assert.ok(f.inputs.filter(i=>i.kind==='down'&&i.key==='VK_B').every(i=>i.screen==='field'),
    'no pause key is sent while the transient map is visible');
  assert.ok(f.adapter.events().some(e=>e.type==='pauseProtectionVerified'&&e.kind==='inventory'));
});

test('known dialogue failures and untrusted context never repeat Space and eventually restore the pause guardian',async t=>{
  const wrongDialogue=[row('Auto',120,25,70,30),row('Statue of The Seven',750,850,350,30),row('A different blessing is offered.',500,900,900,35)];
  const cases=[
    {name:'throwing Space',options:{failSpaceDown:true,restoreAfterPending:true}},
    {name:'dialogue attempt write failure',options:{rejectStatueDialogueWrite:true,restoreAfterPending:true}},
    {name:'dialogue attempt readback mismatch',options:{alterStatueDialogueReadback:true,restoreAfterPending:true}},
    {name:'focus loss',options:{focusLostOnF:true,restoreAfterPending:true}},
    {name:'wrong dialogue context',options:{postInteractionRows:wrongDialogue,restoreAfterPending:true}},
    {name:'unknown dialogue context',options:{postInteractionRows:[row('Auto',120,25,70,30),row('A long dialogue subtitle appears',500,900,900,35)],restoreAfterPending:true}}
  ];
  for(const c of cases){await t.test(c.name,async()=>{
    const witness=observation({frameId:1178,rows:statueRows()});
    const f=fixture({...c.options,requestFrameId:1178,witnessFrameId:1178,witness,fullFieldRows:statueRows(),
      postInteractionRows:c.options.postInteractionRows||statueDialogueRows(),permit:permit({frameId:1178,witnessFrameId:1178,action:'interact'})});
    const initial=await f.adapter.observe('s1',1178),result=await f.adapter.runWindriseReveal(initial,f.observeNext);
    assert.equal(result.pauseVerified,true);assert.equal(result.pauseProof.kind,'inventory');
    assert.equal(f.inputs.filter(i=>i.kind==='down'&&i.key==='VK_F').length,1);
    assert.ok(f.adapter.events().some(e=>e.type==='pauseProtectionVerified'));
    if(c.name==='throwing Space')assert.equal(f.inputs.filter(i=>i.kind==='down'&&i.key==='VK_SPACE').length,1);
    else assert.equal(f.inputs.filter(i=>i.kind==='down'&&i.key==='VK_SPACE').length,0);
    assert.ok(f.inputs.filter(i=>i.kind==='down').every(i=>['VK_F','VK_SPACE','VK_B'].includes(i.key)));
    if(c.name==='throwing Space'||c.name==='dialogue attempt write failure'||c.name==='dialogue attempt readback mismatch') {
      assert.equal(f.writes.filter(w=>w.path==='reports/s1.statue-dialogue-actions.json').length,1);
    }
    if(c.name==='dialogue attempt write failure'||c.name==='dialogue attempt readback mismatch'||c.name==='focus loss'||c.name==='wrong dialogue context'||c.name==='unknown dialogue context')
      assert.equal(f.inputs.filter(i=>i.kind==='down'&&i.key==='VK_SPACE').length,0);
  });}
});

test('missing Statue dialogue resolver blocks a paused interact permit before Escape or F',async()=>{
  const witness=observation({frameId:10,rows:statueRows()});
  const f=pausedFoodFixture({missingStatueDialogue:true,witness,permit:permit({frameId:20,witnessFrameId:10,action:'interact',createdAt:3000})});
  const initial=await f.adapter.observe('s1',20);
  await assert.rejects(()=>f.adapter.runWindriseReveal(initial,f.observeNext),/Statue dialogue resolver is required before the interaction|ActOneStatueDialogue is not defined/);
  assert.deepEqual(f.inputs,[]);
  assert.equal(f.adapter.events().some(e=>e.type==='windriseInventoryClose'||e.type==='windriseRevealAction'),false);
});

test('pause-only permit accepts positive HP below movement threshold when its original witness was healthy',async()=>{
  const lowRows=fieldRows().map(r=>r.text==='1186/1186'?row('500/1186',900,1002,120,24):r);
  // Injured HP is accepted only when the independent enlarged HUD crop agrees.
  const f=fixture({fullFieldRows:lowRows,healthCropRows:[row('500/1186',0,0,375,120)]});
  const initial=await f.adapter.observe('s1',10);
  assert.equal(initial.hud.health.current,500);
  assert.equal(f.adapter.windriseRevealReady(initial),false);
  const result=await f.adapter.runWindriseReveal(initial,f.observeNext);
  assert.equal(result.pausedInventory,true);assert.equal(result.moves,0);assert.equal(result.turns,0);
  assert.deepEqual(f.inputs.filter(i=>i.kind==='down').map(i=>i.key),['VK_B']);
  const consumed=JSON.parse(f.getWrittenPermit());
  assert.equal(consumed.pauseOnly,true);assert.equal(consumed.usedAt,10000);
  assert.equal(f.adapter.events().some(e=>e.type==='windriseRevealAction'),false);
});

test('witness failures stop actions but leave the initially active field locally paused',async()=>{
  const unsafeWitness=observation({frameId:10,timestamp:1000,hudPatch:{dialogueReady:true}});
  for(const options of [
    {witness:unsafeWitness},
    {missingWitnessJson:true},
    {missingWitnessPng:true},
    {rejectPermitWrite:true},
    {fullFieldRows:[...fieldRows(),row('Auto',50,50),row('Lisa',900,850),row('A long dialogue subtitle appears',800,920,350,35)]}
  ]) {
    const f=fixture(options);const initial=await f.adapter.observe('s1',10);
    const result=await f.adapter.runWindriseReveal(initial,f.observeNext);
    assert.equal(result.moves,0);assert.equal(result.turns,0);assert.equal(result.interactions,0);
    if(options.fullFieldRows) {
      assert.equal(result.pausedInventory,false);
      assert.deepEqual(f.inputs,[]);
      assert.equal(result.pauseVerified,undefined);
    } else {
      assert.equal(result.pausedInventory,true);assert.equal(result.pauseVerified,true);
      assert.deepEqual(f.inputs.filter(i=>i.kind==='down').map(i=>i.key),['VK_B']);
    }
  }

  const replay=fixture();const initial=await replay.adapter.observe('s1',10);
  const first=await replay.adapter.runWindriseReveal(initial,replay.observeNext);
  assert.equal(first.pausedInventory,true);
  const priorInputCount=replay.inputs.filter(i=>i.kind==='down').length;
  replay.adapter.beginMission({mission:'questStep',step:'windriseReveal',session:'s1',id:'req-replay',expectedFrameId:10,createdAt:900,objective:'Meet Lisa at the temple'});
  replay.setScreen('field');
  const again=await replay.adapter.observe('s1',10);
  const second=await replay.adapter.runWindriseReveal(again,replay.observeNext);
  assert.equal(second.pausedInventory,true);assert.equal(second.pauseVerified,true);assert.equal(second.moves,0);assert.equal(second.turns,0);
  assert.equal(replay.inputs.filter(i=>i.kind==='down').length,priorInputCount+1);
});
