const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const session='approach-session',t=120000;
const row=(text,x,y,width=60,height=24)=>({text,x,y,width,height});
const party={session,id:'entry',mission:'questStep',status:'completed',timestamp:t-20000,details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},
  inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:20,startedAt:t-21000,x:1700,y:1019}]}};
const hydroRows=[row('The blue stone in the center of the room is Hydro Amber. Breaking it will',436,784,1047,35),
  row('make it rain, making everything in its range Wet.',608,822,699,29)];
const hydroFrame={session,frameId:510,timestamp:t+1000,map:null,ocr:hydroRows,
  hud:{world:false,tutorialStep:'wolfInfo',groundControls:false,health:null}};
const recover={session,id:'hydro-recover',mission:'recover',status:'completed',timestamp:t+2100,frameId:516,
  details:{result:{step:'recover',clicks:1},inputEvents:[{type:'wolfInfoRecoveryDismiss',frameId:510,x:960,y:900,startedAt:t+1500}]}};
const pauseReport={session,id:'pause',mission:'questStep',status:'completed',timestamp:t+2600,frameId:517,
  details:{result:{step:'wolfPause',pauseVerified:true,frameId:517},inputEvents:[{type:'key',key:'VK_ESCAPE',durationMs:60,startedAt:t+2300,finishedAt:t+2360}]}};
const reports=[party,recover,pauseReport];
const pauseFrame={session,frameId:517,timestamp:t+3000,map:null,ocr:[row('Continue Challenge',831,399,287,40),row('Leave Domain?',864,640,221,36)],
  hud:{world:false,auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,climbing:false,loading:false,unknownHud:false,objectiveChanged:false}};
const bar={x:1190,y:394,width:128,height:8};
const liveRows=[row('Kaeya',1660,484,92,41),row('Trial',1790,463,49,24),row('1063/1427',906,1001,104,21),
  row('Lv.5',1126,350,58,24),row('E',1689,1027,19,21),row('Q',1808,1028,19,21)];
const active={session,frameId:518,timestamp:t+3500,map:null,ocr:liveRows,
  hud:{world:false,groundControls:true,climbing:false,auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,tutorialStep:null,
    objectiveChanged:false,interact:false,enemyBars:[bar],health:{current:1063,max:1427}}};

function phaseReports(patch={}) {
  const rs=JSON.parse(JSON.stringify(reports));
  if(patch.noEntry)rs.shift();
  if(patch.noHydro)rs.splice(1,1);
  if(patch.noPause)rs.pop();
  if(patch.wrongSource)patch.source={...hydroFrame,ocr:[row('Loading',800,500,120,30)]};
  if(patch.duplicateHydro)rs.splice(2,0,JSON.parse(JSON.stringify(recover)));
  if(patch.duplicatePause)rs.push({...JSON.parse(JSON.stringify(pauseReport)),id:'pause-duplicate'});
  if(patch.inputBetween)rs.push({session,id:'intervening',mission:'questStep',status:'completed',timestamp:t+2200,
    details:{result:{step:'wolfLookRight'},inputEvents:[{type:'rotate',dx:80,dy:0,startedAt:t+2201}]}});
  if(patch.inputAfterPause)rs.push({session,id:'after-pause',mission:'questStep',status:'completed',timestamp:t+2700,
    details:{result:{step:'wolfForward'},inputEvents:[{type:'key',key:'VK_W',startedAt:t+2650,finishedAt:t+2700}]}});
  return rs;
}

test('approach target requires one finite anchored bar in the calibrated forward zone and safe grounded Trial Kaeya',()=>{
  const rows=[...active.ocr,row('Lv.5',1126,350,58,24)];
  assert.deepEqual(bgi.wolfApproachEnemyTarget(active,t+3500),bar);
  const realFrame519={...active,frameId:519,ocr:active.ocr.filter(r=>r.text!=='Lv.5'),hud:{...active.hud,enemyBarDiagnostic:{level:5,candidates:1,localReads:[
    {bar:{...bar},anchored:true,rows:[row('Lv. 5',1115,368.6666666666667,40.666666666666664,18.666666666666668)]}
  ]}}};
  assert.deepEqual(bgi.wolfApproachEnemyTarget(realFrame519,t+3500),bar,'same-frame anchored local level OCR substitutes for missing full-frame Lv row');
  for(const bad of [
    {...active,timestamp:t+2000}, {...active,map:{map:'Teyvat',x:1,y:1}},
    {...active,hud:{...active.hud,health:{current:850,max:1427}}},
    {...active,hud:{...active.hud,health:{current:1063,max:1400}}},
    {...active,hud:{...active.hud,enemyBars:[]}}, {...active,hud:{...active.hud,enemyBars:[bar,{...bar,x:1200}]}},
    {...active,hud:{...active.hud,interact:true}}, {...active,hud:{...active.hud,enemyBars:[{...bar,x:1400}]}},
    {...active,hud:{...active.hud,enemyBars:[{...bar,width:0}]}},
    {...active,ocr:active.ocr.filter(r=>r.text!=='Lv.5')},
    {...active,ocr:active.ocr.map(r=>r.text==='Lv.5'?row('Lv.4',1126,350,58,24):r)},
    {...active,hud:{...active.hud,auto:true}}, {...active,hud:{...active.hud,dialogueReady:true}},
    {...active,hud:{...active.hud,groundControls:false}},
  ]) assert.equal(bgi.wolfApproachEnemyTarget(bad,t+3500),null);
  for(const diagnostic of [
    {...realFrame519.hud.enemyBarDiagnostic,level:4},
    {...realFrame519.hud.enemyBarDiagnostic,localReads:[{bar:{...bar,x:bar.x+8},anchored:true,rows:[row('Lv. 5',1115,368.6,40.6,18.7)]}]},
    {...realFrame519.hud.enemyBarDiagnostic,localReads:[{bar:{...bar},anchored:true,rows:[row('Lv. 4',1115,368.6,40.6,18.7)]}]},
    {...realFrame519.hud.enemyBarDiagnostic,localReads:[{bar:{...bar},anchored:false,rows:[row('Lv. 5',1115,368.6,40.6,18.7)]}]},
    {...realFrame519.hud.enemyBarDiagnostic,localReads:[{bar:{...bar},anchored:true,rows:[row('Lv. 5',1500,368.6,40.6,18.7)]}]},
  ]) assert.equal(bgi.wolfApproachEnemyTarget({...realFrame519,hud:{...realFrame519.hud,enemyBarDiagnostic:diagnostic}},t+3500),null);
});

test('Hydro checkpoint links only exact saved tutorial, one recover dismissal, entry, and later canonical pause',()=>{
  const proof=bgi.wolfHydroApproachProof(phaseReports(),hydroFrame,session);
  assert.deepEqual(proof,{receiptId:'hydro-recover',hydroFrameId:510,dismissedAt:t+1500,pauseId:'pause',pauseFrameId:517,pauseAt:t+2600,escapeFinishedAt:t+2360});
  for(const [patch,source] of [
    [{noEntry:true},hydroFrame],[{noHydro:true},hydroFrame],[{noPause:true},hydroFrame],
    [{},{...hydroFrame,ocr:[row('Loading',800,500,120,30)]}],[{duplicateHydro:true},hydroFrame],[{duplicatePause:true},hydroFrame],
    [{inputBetween:true},hydroFrame],[{inputAfterPause:true},hydroFrame],
  ]) assert.equal(bgi.wolfHydroApproachProof(phaseReports(patch),source||hydroFrame,session),null);
  assert.equal(bgi.wolfHydroApproachProof(phaseReports(),{...hydroFrame,session:'foreign'},session),null);
});

test('retry history permits only prior Continue-without-W followed by a verified canonical pause',()=>{
  const proof=bgi.wolfHydroApproachProof(reports,hydroFrame,session);
  const retry={session,id:'approach-no-w',mission:'questStep',status:'stopped',timestamp:t+4300,frameId:519,
    details:{result:{step:'wolfApproachEnemy',continueAttempts:1,moveAttempts:0,approachVerified:false,questComplete:false},
      inputEvents:[{type:'controllerRevision',startedAt:t+3200},
        {type:'wolfApproachEnemyContinue',frameId:518,hydroFrameId:510,hydroReceiptId:'hydro-recover',startedAt:t+3300}]}};
  const pause={session,id:'approach-auto-pause',mission:'questStep',status:'completed',timestamp:t+5000,frameId:520,
    details:{result:{step:'wolfPause',pauseVerified:true,frameId:520},inputEvents:[{type:'key',key:'VK_ESCAPE',durationMs:60,startedAt:t+4400,finishedAt:t+4460}]}};
  const history=bgi.wolfApproachHistory([...reports,retry,pause],proof,session);
  assert.deepEqual(history,{attemptCount:1,moveCount:0,latestPauseFrameId:520,latestPauseAt:t+5000});
  const moved={...retry,id:'approach-with-w',timestamp:t+4300,details:{result:{step:'wolfApproachEnemy',continueAttempts:1,moveAttempts:1},
    inputEvents:[...retry.details.inputEvents,{type:'wolfApproachEnemyMove',key:'VK_W',durationMs:500,frameId:518,hydroFrameId:510,hydroReceiptId:'hydro-recover',startedAt:t+3400,finishedAt:t+3915},
      {type:'key',key:'VK_W',durationMs:500,frameId:518,startedAt:t+3401,finishedAt:t+3903}]}};
  const movedPause={...pause,id:'moved-pause',timestamp:t+5000,frameId:521,details:{result:{step:'wolfPause',pauseVerified:true,frameId:521},
    inputEvents:[{type:'key',key:'VK_ESCAPE',durationMs:60,startedAt:t+4400,finishedAt:t+4460}]}};
  assert.equal(bgi.wolfApproachHistory([...reports,moved,movedPause],proof,session).moveCount,1);
  assert.equal(bgi.wolfApproachHistory([...reports,retry],proof,session),null,'cannot retry without a later verified pause');
  assert.equal(bgi.wolfApproachHistory([...reports,{...retry,details:{...retry.details,result:{...retry.details.result,moveAttempts:1}}},pause],proof,session),null,
    'malformed receipt cannot claim a zero-move retry');
  const unrelated={session,id:'unrelated-input',mission:'questStep',status:'completed',timestamp:t+4200,
    details:{result:{step:'wolfLookRight'},inputEvents:[{type:'rotate',dx:16,dy:0,startedAt:t+4100}]}};
  assert.equal(bgi.wolfApproachHistory([...reports,retry,pause,unrelated],proof,session),null,'unrelated game input invalidates retry continuity');
});

function adapterHarness(rs=phaseReports()) {
  let now=t+3000,rows=pauseFrame.ocr,frame=517,events=[];const keys=[],clicks=[];
  const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
  const context={Date:class extends Date{static now(){return now;}},genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,
      getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='reports/'+session+'.json'||p==='observations/'+session+'/frame-0510.json',
      readTextSync:p=>p==='reports/'+session+'.json'?JSON.stringify(rs):p==='observations/'+session+'/frame-0510.json'?JSON.stringify(hydroFrame):fs.readFileSync(path.join(root,p),'utf8'),
      writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(mat){this.rows=mat&&mat.rows||[];}findMulti(){const a=this.rows.map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},ColorConversionCodes:{BGR2HSV:0},
      RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:c=>c,contourArea:()=>0}}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows.map(r=>({...r}));a.count=a.length;return a;},
      deriveCrop:()=>({srcMat:{resize:()=>({rows:[]}),inRange:()=>({findContoursAsArray:()=>[{x:776,y:290,width:128,height:8}],dispose(){}})},dispose(){}}),dispose(){}}),
    click:(x,y)=>clicks.push([x,y]),keyDown:k=>keys.push(['down',k,now]),keyUp:k=>keys.push(['up',k,now]),
    sleep:async ms=>{now+=ms;},moveMouseBy(){throw Error('Unexpected movement other than bounded W');},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);adapter.beginMission({mission:'questStep',step:'wolfApproachEnemy',session,createdAt:now});
  return {adapter,keys,clicks,events,rs,setRows(v){rows=v;},setNow(v){now=v;},setFrame(v){frame=v;},nextFrame(){return frame++;},now:()=>now};
}

test('adapter continues once, sends one released W500 only with same-session Hydro proof and anchored bar',async()=>{
  const h=adapterHarness(),a=h.adapter;h.setRows(pauseFrame.ocr);
  const pause=await a.observe(session,h.nextFrame());assert.equal(a.wolfApproachEnemyReady(pause),true);
  a.wolfApproachEnemyContinue();assert.deepEqual(h.clicks,[[975,419]]);
  h.setNow(t+3500);h.setRows(liveRows);const targetFrame=await a.observe(session,h.nextFrame());
  assert.ok(a.wolfApproachEnemyTarget(targetFrame));await a.wolfApproachEnemyMove(targetFrame);
  assert.deepEqual(h.keys.map(k=>k.slice(0,2)),[['down','VK_W'],['up','VK_W']]);assert.equal(h.keys[1][2]-h.keys[0][2],500);
  await assert.rejects(a.wolfApproachEnemyMove(targetFrame),/one anchored enemy bar/);
  assert.equal(a.events().filter(e=>e.type==='wolfApproachEnemyMove').length,1);
});

test('adapter permits a fresh-pause retry after one durable Continue-only attempt, but not after W',async()=>{
  const retry={session,id:'approach-no-w',mission:'questStep',status:'stopped',timestamp:t+4300,frameId:519,
    details:{result:{step:'wolfApproachEnemy',continueAttempts:1,moveAttempts:0,approachVerified:false,questComplete:false},
      inputEvents:[{type:'wolfApproachEnemyContinue',frameId:518,hydroFrameId:510,hydroReceiptId:'hydro-recover',startedAt:t+3300}]}};
  const laterPause={session,id:'approach-auto-pause',mission:'questStep',status:'completed',timestamp:t+5000,frameId:520,
    details:{result:{step:'wolfPause',pauseVerified:true,frameId:520},inputEvents:[{type:'key',key:'VK_ESCAPE',durationMs:60,startedAt:t+4400,finishedAt:t+4460}]}};
  const h=adapterHarness([...phaseReports(),retry,laterPause]),a=h.adapter;
  h.setNow(t+6000);h.setFrame(520);h.setRows(pauseFrame.ocr);
  const freshPause=await a.observe(session,520);
  assert.equal(a.wolfApproachEnemyReady(freshPause),true);
  a.wolfApproachEnemyContinue();
  assert.deepEqual(h.clicks,[[975,419]]);

  const moved={...retry,id:'approach-with-w',timestamp:t+4300,details:{result:{step:'wolfApproachEnemy',continueAttempts:1,moveAttempts:1},
    inputEvents:[...retry.details.inputEvents,{type:'wolfApproachEnemyMove',key:'VK_W',durationMs:500,frameId:518,hydroFrameId:510,hydroReceiptId:'hydro-recover',startedAt:t+3400,finishedAt:t+3900}]}};
  const blockedHarness=adapterHarness([...phaseReports(),moved,laterPause]),blocked=blockedHarness.adapter;
  blockedHarness.setNow(t+6000);blockedHarness.setFrame(520);blockedHarness.setRows(pauseFrame.ocr);
  const blockedPause=await blocked.observe(session,520);
  assert.equal(blocked.wolfApproachEnemyReady(blockedPause),false);
});

test('mission reports one unverified approach and stops on unsafe or missing post-Continue target',async()=>{
  let now=t+3000,continues=0,moves=0,reads=0,provideTarget=true;
  const api={now:()=>now,checkStop(){},sleep:async ms=>{now+=ms;},wolfApproachEnemyReady:()=>true,wolfApproachEnemyContinue:()=>{continues++;},
    wolfApproachEnemyTarget:()=>provideTarget&&reads===1?bar:null,wolfApproachEnemyMove:async()=>{moves++;now+=500;}};
  const result=await mission.runQuestStep('wolfApproachEnemy',pauseFrame,api,async()=>{reads++;now+=100;return {...active,frameId:518+reads,timestamp:now};});
  assert.equal(result.status,'stopped');assert.equal(result.moveAttempts,1);assert.equal(result.approachVerified,false);assert.equal(result.questComplete,false);
  assert.equal(continues,1);assert.equal(moves,1);assert.equal(reads,2);assert.equal(result.polls,2);

  now=t+3000;reads=0;continues=0;moves=0;provideTarget=false;
  const noTarget=await mission.runQuestStep('wolfApproachEnemy',pauseFrame,api,async()=>{reads++;now+=100;return {...active,hud:{...active.hud,health:{current:850,max:1427}},timestamp:now};});
  assert.equal(noTarget.moveAttempts,0);assert.equal(noTarget.approachVerified,false);assert.equal(continues,1);assert.equal(moves,0);
});
