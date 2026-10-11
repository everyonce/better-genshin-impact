const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const session='wolf-console-session',t=95000;
const row=(text,x,y,width=60,height=24)=>({text,x,y,width,height});
const party={session,mission:'questStep',status:'completed',id:'party',timestamp:t-10000,details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},
  inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:20,startedAt:t-11000,x:1700,y:1019}]}};
const pause={session,frameId:460,timestamp:t,map:null,ocr:[row('Continue Challenge',831,399,287,40),row('Leave Domain?',864,640,221,36)],
  hud:{world:false,auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,climbing:false,loading:false,unknownHud:false,objectiveChanged:false}};
const safeScreen={world:false,groundControls:true,auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,climbing:false,
  objectiveChanged:false,tutorialStep:null,loading:false,unknownHud:false,health:{current:1063,max:1427}};
const openDoorRows=[row('Open Door',1218,522,163,35),row('日',1094,518,57,41),row('Kaeya',1660,484,92,41),row('Trial',1790,463,49,24)];
const fPrompt=row('F',1098,522,45,35);
const active={session,frameId:461,timestamp:t+500,map:null,ocr:[...openDoorRows,fPrompt,row('1063/1427',906,1001,104,21)],
  hud:{world:false,groundControls:true,climbing:false,auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,tutorialStep:null,
    objectiveChanged:false,interact:true,enemyBars:[],health:{current:1063,max:1427}}};

test('frame 460 exact Open Door prompt enables only an enlarged same-frame F crop',()=>{
  assert.equal(bgi.shouldReadWolfOpenDoorCrop(openDoorRows,safeScreen),true);
  const f=bgi.interactionCropF([{text:'F',x:54,y:96,width:135,height:105}],1080,490);
  assert.deepEqual({text:f.text,x:f.x,y:f.y,width:f.width,height:f.height},{text:'F',x:1098,y:522,width:45,height:35});
  assert.equal(bgi.wolfOpenDoorF({...active,ocr:[...openDoorRows,f,row('1063/1427',906,1001,104,21)]},t+500).label,'Open Door');
});

test('crop and interaction target reject unsafe, missing, duplicate, or misaligned evidence',()=>{
  for(const patch of [{auto:true},{journal:true},{bigMap:true},{dialogueReady:true},{choice:true},{climbing:true},{objectiveChanged:true},
    {groundControls:false},{world:true},{health:{current:850,max:1427}},{health:{current:1063,max:1400}}])
    assert.equal(bgi.shouldReadWolfOpenDoorCrop(openDoorRows,{...safeScreen,...patch}),false,JSON.stringify(patch));
  assert.equal(bgi.shouldReadWolfOpenDoorCrop([...openDoorRows,row('F',1098,522,45,35)],safeScreen),false,'do not crop when full OCR already has F');
  assert.equal(bgi.shouldReadWolfOpenDoorCrop(openDoorRows.filter(r=>r.text!=='Open Door'),safeScreen),false);
  for(const bad of [
    {...active,timestamp:t-1000}, {...active,map:{x:0,y:0,map:'Teyvat'}},
    {...active,ocr:active.ocr.filter(r=>r.text!=='F')},
    {...active,ocr:[...active.ocr,row('F',1098,522,45,35)]},
    {...active,ocr:active.ocr.map(r=>r.text==='F'?{...r,y:600}:r)},
    {...active,ocr:active.ocr.map(r=>r.text==='Open Door'?{...r,x:1500}:r)},
    {...active,hud:{...active.hud,enemyBars:[{}]}}, {...active,hud:{...active.hud,auto:true}},
    {...active,hud:{...active.hud,interact:false,enemyBars:[]}},
  ]) assert.equal(bgi.wolfOpenDoorF(bad,t+500),null);
});

function adapterHarness(){
  let now=t,rows=pause.ocr,frame=460,ocrCost=0,pngCost=0;
  const keys=[],clicks=[],cropCalls=[];
  const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
  const context={Date:class extends Date{static now(){return now;}},genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='reports/'+session+'.json',readTextSync:p=>p==='reports/'+session+'.json'?JSON.stringify([party]):fs.readFileSync(path.join(root,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>{now+=pngCost;return true;}},
    RecognitionObject:{Ocr:(x,y,w,h)=>({x,y,w,h})},ImageRegion:class{constructor(mat){this.rows=mat&&mat.rows||[];}findMulti(){now+=ocrCost;const a=this.rows.map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},ColorConversionCodes:{BGR2HSV:0},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x,contourArea:()=>0}}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:roi=>{now+=ocrCost;const a=rows.map(r=>({...r}));a.count=a.length;return a;},deriveCrop:(x,y,w,h)=>{cropCalls.push([x,y,w,h]);return {srcMat:{resize:()=>({rows:x===1080&&y===490? [row('F',54,96,135,105)]:[]}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}};},dispose(){}}),
    click:(x,y)=>clicks.push([x,y]),keyDown:k=>keys.push(['down',k,now]),keyUp:k=>keys.push(['up',k,now]),sleep:async ms=>{now+=ms;},moveMouseBy(){throw Error('Unexpected camera/cursor movement');},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);
  return {adapter,keys,clicks,cropCalls,setRows(v){rows=v;},setNow(v){now=v;},setFrame(v){frame=v;},nextFrame(){return frame++;},setCosts(o){ocrCost=o.ocr||0;pngCost=o.png||0;},now:()=>now};
}

test('adapter Continue and single F press are entry-bound, fresh, and key release is guaranteed',async()=>{
  const h=adapterHarness(),a=h.adapter;h.setRows(pause.ocr);
  a.beginMission({mission:'questStep',step:'wolfConsoleInteract',session,createdAt:t});
  const initial=await a.observe(session,h.nextFrame());assert.equal(a.wolfConsoleContinueReady(initial),true);
  a.wolfConsoleContinue();assert.deepEqual(h.clicks,[[975,419]]);
  h.setNow(t+500);h.setRows([...openDoorRows,row('1063/1427',906,1001,104,21),row('E',1689,1027,19,21),row('Q',1808,1028,19,21)]);
  const current=await a.observe(session,h.nextFrame());
  assert.equal(h.cropCalls.some(c=>c[0]===1080&&c[1]===490&&c[2]===90&&c[3]===100),true,'the named door prompt triggers only its same-frame F crop');
  assert.equal(a.wolfConsoleInteractReady(current),true,JSON.stringify({hud:current.hud,ocr:current.ocr}));
  assert.equal(a.wolfConsoleInteractTarget(current).label,'Open Door');
  await a.wolfConsolePressF(current);
  assert.deepEqual(h.keys.map(k=>k.slice(0,2)),[['down','VK_F'],['up','VK_F']]);assert.equal(h.keys[1][2]-h.keys[0][2],60);
  await assert.rejects(a.wolfConsolePressF(current),/one interaction/);
  assert.equal(a.wolfConsoleInteractReady(current),false);
  assert.equal(a.events().filter(e=>e.type==='wolfConsoleInteract').length,1);
});

test('mission sends one Continue then one verified-prompt F; reports door state as unverified',async()=>{
  let now=t,reads=0,continues=0,presses=0;
  const api={now:()=>now,checkStop(){},sleep:async ms=>{now+=ms;},wolfConsoleContinueReady:()=>true,wolfConsoleInteractReady:()=>true,
    wolfConsoleContinue:()=>{continues++;},wolfConsoleInteractTarget:()=>({label:'Open Door'}),wolfConsolePressF:async()=>{presses++;}};
  const result=await mission.runQuestStep('wolfConsoleInteract',pause,api,async()=>{
    reads++;now+=200;return {...active,frameId:460+reads,timestamp:now};
  });
  assert.equal(result.status,'stopped');assert.equal(result.continueAttempts,1);assert.equal(result.interactionAttempts,1);
  assert.equal(result.doorOpenVerified,false);assert.equal(result.promptLabel,'Open Door');assert.equal(result.questComplete,undefined);
  assert.equal(continues,1);assert.equal(presses,1);assert.equal(reads,2);assert.equal(result.polls,2);
});

test('exclusive OCR primitive timing excludes PNG-write time and resets per observation',async()=>{
  const h=adapterHarness(),a=h.adapter;h.setRows([...openDoorRows,row('1063/1427',906,1001,104,21),row('E',1689,1027,19,21),row('Q',1808,1028,19,21)]);
  h.setCosts({ocr:4,png:100});a.beginMission({mission:'questStep',step:'wolfConsoleInteract',session,createdAt:t});
  const first=await a.observe(session,h.nextFrame()),second=await a.observe(session,h.nextFrame());
  for(const o of [first,second]) {
    assert.equal(o.timings.ocrFindMultiMs,o.timings.ocrReadCount*4);
    assert.ok(o.timings.pngWriteMs>=100);
    assert.ok(o.timings.ocrFindMultiMs<o.timings.pngWriteMs);
  }
  assert.equal(first.timings.ocrReadCount,second.timings.ocrReadCount);
});
