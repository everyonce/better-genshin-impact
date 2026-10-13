'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const dir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const objective='Meet Lisa at the temple';
const start={x:-1266.9238,y:1929.6914};
const row=(text,x,y,width=100,height=28)=>({text,x,y,width,height});
const inventoryRows=()=>[row('Food',140,32,67,31),row('Inventory capacity 9/2600',1504,34,295,27),
  row('Teyvat Fried Egg',1329,119,297,57),row('Food',1374,187,63,30),row('Use',1670,999,63,38)];
const fieldRows=(options={})=>[row(objective,80,250,300,35),row('Amber',1680,415,80,35),row('Kaeya',1660,500,80,35),
  ...(!options.omitSlot?[row(options.slotText||'3',1860,500,25,35)]:[]),...(options.duplicateSlot?[row('3',1875,505,20,25)]:[]),
  row('R',1580,1004,30,30),row('Q',1660,1004,30,30),row('1186/1186',900,1002,120,24)];
function witnessFrame(now){return {session:'lisa-adapter-test',frameId:19,timestamp:now-500,map:{map:'Teyvat',x:start.x,y:start.y,cameraAngle:0},
  hud:{world:true,groundControls:true,climbing:false,auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,
    health:{current:1186,max:1186},objectives:[objective],enemyBars:[]},
  ocr:[row(objective,80,250,300,35),row('Kaeya',1660,500,80,35),row('3',1860,500,25,35)]};}
function permit(now,patch={}){return {kind:'chartedLisaNavigation',session:'lisa-adapter-test',frameId:20,witnessFrameId:19,
  witnessVerified:true,createdAt:now-200,...patch};}

function fixture(options={}){
  let now=200000,frame=20,screen='inventory',foreground=true,cameraAngle=0,escapeUpCount=0;
  const inputs=[],events=[],writes=[],mapQueries=[],captures=[],slotCropFrames=[],virtualFiles=new Map();let mapQueriesAtPause=null;
  const metrics={slotCropCalls:0};
  const witnessed=witnessFrame(now),p=permit(now);
  const baseFiles={'lisa-navigation-witness.json':p,
    'observations/lisa-adapter-test/frame-0019.json':witnessed,
    'observations/lisa-adapter-test/frame-0019.png':'sanitized-png-fixture'};
  for(const [name,value] of Object.entries({...baseFiles,...(options.seedFiles||{})}))
    if(value!==undefined)virtualFiles.set(name,typeof value==='string'?value:JSON.stringify(value));
  for(const name of options.removeFiles||[])virtualFiles.delete(name);
  const writeHistory=[];
  const files={
    isExists(name){return virtualFiles.has(name)||name==='bgi.js'||fs.existsSync(path.join(dir,name));},
    readTextSync(name){if(options.hidePauseModule&&name==='local-pause.js')throw new Error('mock missing guardian');
      if(virtualFiles.has(name))return virtualFiles.get(name);return fs.readFileSync(path.join(dir,name),'utf8');},
    writeTextSync(name,value){writes.push([name,value]);writeHistory.push({name,value,at:now});
      if(options.failWrite&&name==='lisa-navigation-witness.json')return false;
      virtualFiles.set(name,value);if(name==='lisa-navigation-witness.json'&&options.advanceAfterPermitWrite)now+=options.advanceAfterPermitWrite;
      return true;},writeImageSync(){return true;}
  };
  const gpsSequence=(options.gpsSequence||[start,start,{x:start.x+14,y:start.y}]).map(v=>({...v}));
  const matrix=(rect=null,captureFrame=null)=>({rect,captureFrame,inRange(){return {findContoursAsArray(){return [];},dispose(){}};},resize(){return matrix(rect,captureFrame);},dispose(){}});
  const context={Date:class extends Date{static now(){return now;}},file:files,host:{toSingle(v){return v;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:5,get isGameForeground(){return foreground;},async focusGame(){foreground=true;},
      getPositionFromMap(...args){mapQueries.push(args);const next=gpsSequence.length?gpsSequence.shift():start;if(options.throwGps)throw new Error('mock GPS failure');return {map:'Teyvat',...next};},
      getCameraOrientation(){return cameraAngle;}},
    RecognitionObject:{Ocr:(x,y,w,h)=>({x,y,w,h})},
    captureGameRegion(){captures.push(screen);const capturedFrame=frame,rows=screen==='inventory'?inventoryRows():fieldRows(options);
      return {width:1920,height:1080,srcMat:matrix(null,capturedFrame),findMulti(ro){const found=rows.filter(r=>r.x>=ro.x&&r.x<ro.x+ro.w&&r.y>=ro.y&&r.y<ro.y+ro.h).map(r=>({...r}));found.count=found.length;return found;},
        deriveCrop(x,y,w,h){return {srcMat:matrix({x,y,w,h},capturedFrame),dispose(){}};},dispose(){}};},
    ImageRegion:class{constructor(srcMat){this.srcMat=srcMat;}findMulti(ro){const rect=this.srcMat.rect,slot=rect&&rect.x===1845&&rect.y===475&&rect.w===60&&rect.h===65;
      if(!slot){const empty=[];empty.count=0;return empty;}metrics.slotCropCalls++;slotCropFrames.push(this.srcMat.captureFrame);
      const rows=options.slotCropRows||[],found=rows.filter(r=>r.x>=ro.x&&r.x<ro.x+ro.w&&r.y>=ro.y&&r.y<ro.y+ro.h).map(r=>({...r}));found.count=found.length;return found;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},
      ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:b=>b,contourArea:()=>0,countNonZero:()=>0},ColorConversionCodes:{GRAY2BGR:0,BGR2HSV:1}}},
    keyDown(key){inputs.push({kind:'down',key,frame,at:now});
      if(key==='VK_ESCAPE'){screen='field';if(options.stopAfterClose)virtualFiles.set('stop.json',JSON.stringify({session:'lisa-adapter-test',createdAt:199000}));}
      if(key==='VK_B'){mapQueriesAtPause=mapQueries.length;if(!options.blockPause)screen='inventory';}},
    keyUp(key){inputs.push({kind:'up',key,frame,at:now});if(key==='VK_ESCAPE'){escapeUpCount++;if(options.throwEscapeUpCount&&escapeUpCount<=options.throwEscapeUpCount)throw new Error('mock Escape key-up failure');}},
    moveMouseBy(dx){events.push({type:'mouse',dx,frame});cameraAngle=180;},click(){},
    sleep:async ms=>{now+=ms;await new Promise(resolve=>setImmediate(resolve));},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(dir,'bgi.js'),'utf8'),context);
  vm.runInNewContext(fs.readFileSync(path.join(dir,'mission.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(5);
  const request={mission:'navigation',objective,deadlineMs:8000,session:'lisa-adapter-test',id:'lisa-adapter-1',expectedFrameId:20,
    createdAt:199000,waypoints:[{map:'Teyvat',x:start.x+1,y:start.y},{map:'Teyvat',x:start.x+14,y:start.y}]};
  if(options.requestPatch)Object.assign(request,options.requestPatch);
  adapter.beginMission(request);
  let observerCalls=0;
  async function observe(){observerCalls++;if(options.throwObserveAt===observerCalls)throw new Error('mock observation failure');
    if(options.focusLostAt===observerCalls)foreground=false;
    if(options.stopAfterClose&&screen==='field'&&options.stopCreatedEarly)virtualFiles.set('stop.json',JSON.stringify({session:'lisa-adapter-test',createdAt:199000}));
    now+=10;frame++;return adapter.observe(request.session,frame);}
  async function run(){const initial=await adapter.observe(request.session,request.expectedFrameId);
    if(options.staleInitial)initial.timestamp=now-1501;
    return context.ActOneMission.runNavigation(request,initial,adapter,observe);}
  return {run,adapter,request,inputs,events,writes,writeHistory,mapQueries,captures,slotCropFrames,metrics,virtualFiles,context,observe,
    setForeground:v=>{foreground=v;},getNow:()=>now,getEscapeUpCount:()=>escapeUpCount,getMapQueriesAtPause:()=>mapQueriesAtPause};
}
function assertPause(result){assert.equal(result.status,'completed',JSON.stringify(result));assert.equal(result.pauseVerified,true,JSON.stringify(result));
  assert.ok(result.pauseProof&&result.pauseProof.verified);assert.equal(result.pauseProof.session,'lisa-adapter-test');
  assert.ok(result.pauseProof.pauseFrameId>result.pauseProof.sourceFrameId);assert.equal(result.pauseProof.kind,'inventory');
  assert.equal(result.destinationReached,result.navigationStatus==='arrived');assert.equal(result.questComplete,false);}

test('mission dispatch consumes the chart witness before one Escape, bounds local GPS, navigates, then proves Food pause',async()=>{
  const f=fixture();const result=await f.run();assertPause(result);
  assert.equal(result.step,'lisaNavigation');assert.equal(result.navigationStatus,'arrived');assert.equal(result.destinationReached,true);
  assert.equal(result.questComplete,false);assert.equal(result.status,'completed');
  const downs=f.inputs.filter(x=>x.kind==='down').map(x=>x.key);
  assert.deepEqual(downs,['VK_ESCAPE','VK_SHIFT','VK_W','VK_B'],JSON.stringify({result,events:f.adapter.events(),mapQueries:f.mapQueries}));
  const stored=JSON.parse(f.virtualFiles.get('lisa-navigation-witness.json'));assert.ok(Number.isFinite(stored.usedAt));
  const consumeIndex=f.writeHistory.findIndex(x=>x.name==='lisa-navigation-witness.json');
  const escapeIndex=f.inputs.findIndex(x=>x.kind==='down'&&x.key==='VK_ESCAPE');assert.ok(consumeIndex>=0&&consumeIndex<f.writeHistory.length);
  assert.ok(f.writeHistory[consumeIndex].at<=f.inputs[escapeIndex].at,'consumed witness is persisted before Escape');
  const gpsEvents=f.mapQueries;assert.equal(gpsEvents.length,4,JSON.stringify({gpsEvents,result,events:f.adapter.events()}));
  assert.ok(gpsEvents.every(q=>q[0]==='Teyvat'&&Number.isFinite(q[1])&&Number.isFinite(q[2])));
  assert.equal(f.mapQueries.some(q=>Math.hypot(q[1]-start.x,q[2]-start.y)>25),false);
  const moves=f.adapter.events().filter(e=>e.type==='rotate'||e.type==='key'&&e.key==='VK_W');
  assert.equal(moves.length,2);assert.notEqual(moves[0].frameId,moves[1].frameId,'each bounded navigation input uses a distinct fresh frame');
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_ESCAPE').length,1);
  assert.equal(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_B'),true);
  assert.equal(f.captures.at(-1),'inventory','no map GPS probe is issued while the guardian proves Food pause');
});

test('same-capture slot crop repairs a missing or B-read slot 3 before Lisa navigation input',async()=>{
  for(const options of [{omitSlot:true},{slotText:'B'}]){
    const f=fixture({...options,slotCropRows:[row('3',30,30,60,60)]});const result=await f.run();assertPause(result);
    assert.equal(result.navigationStatus,'arrived');assert.equal(result.destinationReached,true);
    assert.ok(f.metrics.slotCropCalls>0);
    assert.ok(f.slotCropFrames.length>0);
    const move=f.adapter.events().find(e=>e.type==='key'&&e.key==='VK_W');assert.ok(move,'verified crop permits bounded navigation');
    assert.ok(f.slotCropFrames.includes(move.frameId),'crop evidence belongs to the capture used for input');
    assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_ESCAPE','VK_SHIFT','VK_W','VK_B']);
  }
});

test('missing, wrong, or duplicate same-capture slot OCR never authorizes Lisa forward input and still verifies pause',async()=>{
  const cases=[
    ['crop absent',{omitSlot:true}],
    ['wrong crop',{omitSlot:true,slotCropRows:[row('2',30,30,60,60)]}],
    ['B remains wrong',{slotText:'B',slotCropRows:[row('B',30,30,60,60)]}],
    ['duplicate full slot',{duplicateSlot:true,slotCropRows:[row('3',30,30,60,60)]}]
  ];
  for(const [label,options] of cases){
    const f=fixture(options);const result=await f.run();assertPause(result);
    assert.equal(result.navigationStatus,'stopped',label);assert.equal(result.destinationReached,false,label);
    assert.equal(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_W'),false,label);
    assert.deepEqual(f.inputs.filter(x=>x.kind==='down').map(x=>x.key),['VK_ESCAPE','VK_B'],label);
    if(label==='duplicate full slot')assert.equal(f.metrics.slotCropCalls,0,'ambiguous full-frame slot labels do not trigger OCR repair');
  }
});

test('missing, expired, reused, cross-session, uncharted, far, or stale witness blocks Escape',async()=>{
  const now=200000,base=permit(now),witness=witnessFrame(now),json='observations/lisa-adapter-test/frame-0019.json',png='observations/lisa-adapter-test/frame-0019.png';
  const cases=[
    ['missing permit',{removeFiles:['lisa-navigation-witness.json']}],
    ['expired permit',{seedFiles:{'lisa-navigation-witness.json':permit(now,{createdAt:now-120001})}}],
    ['preused permit',{seedFiles:{'lisa-navigation-witness.json':permit(now,{usedAt:now-1})}}],
    ['cross-session permit',{seedFiles:{'lisa-navigation-witness.json':permit(now,{session:'foreign'})}}],
    ['missing witness PNG',{removeFiles:[png]}],
    ['invalid witness map',{seedFiles:{[json]:{...witness,map:{...witness.map,x:1000}}}}],
    ['expired source map',{seedFiles:{[json]:{...witness,timestamp:now-120001}}}],
    ['source timestamp after permit creation',{seedFiles:{[json]:{...witness,timestamp:now-100},'lisa-navigation-witness.json':permit(now,{createdAt:now-200})}}],
    ['route not bound to witness',{requestPatch:{waypoints:[{map:'Teyvat',x:start.x+6,y:start.y}]} }],
    ['stale Food capture',{staleInitial:true}],
    ['write not verified',{failWrite:true}],
    ['permit write made Food stale',{advanceAfterPermitWrite:1501}]
  ];
  for(const [label,options] of cases){
    const f=fixture(options);await assert.rejects(f.run(),undefined,label);
    assert.equal(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_ESCAPE'),false,label);
    assert.equal(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_W'),false,label);
  }
});

test('GPS candidates outside the first 25 m witness anchor stop navigation and still reach verified Food pause',async()=>{
  const f=fixture({gpsSequence:Array.from({length:8},(_,i)=>({x:start.x+80+i,y:start.y}))});const result=await f.run();assertPause(result);
  assert.equal(result.navigationStatus,'stopped');assert.equal(result.destinationReached,false);assert.equal(result.questComplete,false);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_ESCAPE').length,1);
  assert.equal(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_W'),false);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_B').length,1);
  assert.equal(f.getMapQueriesAtPause(),f.mapQueries.length,'the guardian pauses Food without a GPS query');
});

test('arrived, stopped, thrown, expired-input, capture, stop, key-up, and focus-loss callbacks all finish behind the pause guardian',async()=>{
  const cases=[
    ['arrived',{},async(api)=>({status:'arrived',movements:0})],
    ['stopped',{},async()=>({status:'stopped',reason:'bounded stop'})],
    ['callback throws',{},async()=>{throw new Error('mock navigation callback failure');}],
    ['expired input',{},async(api,observe)=>{await api.sleep(1100);await api.forward(100);return {status:'arrived'};}],
    ['observation throws',{throwObserveAt:1},async()=>({status:'stopped'})],
    ['stop after close',{stopAfterClose:true},async()=>({status:'stopped'})],
    ['Escape key-up fails',{throwEscapeUpCount:1},async()=>({status:'stopped'})],
    ['focus lost after close',{focusLostAt:1},async()=>({status:'stopped'})]
  ];
  for(const [label,options,callback] of cases){
    const f=fixture(options);const initial=await f.adapter.observe(f.request.session,f.request.expectedFrameId);
    const result=await f.adapter.runLisaNavigationWithPause(initial, f.observe, (field)=>callback(f.adapter,f.observe,field));
    assertPause(result);assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_ESCAPE').length,1,label);
    assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_B').length,1,label);
    assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_W').length,label==='expired input'?0:0,label);
    assert.equal(result.questComplete,false,label);
  }
});

test('missing local pause guardian blocks Escape before inventory is dismissed',async()=>{
  assert.throws(()=>fixture({hidePauseModule:true}),/mock missing guardian/);
});
