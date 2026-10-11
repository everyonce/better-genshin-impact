const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const session='glide-session',t=70000;
const row=(text,x,y,width=80,height=24)=>({text,x,y,width,height});
const party={session,mission:'questStep',status:'completed',timestamp:t-10000,id:'party',details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},
  inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',startedAt:t-11000,frameId:20,x:1700,y:1019}]}};
const pause={session,frameId:20,timestamp:t,map:null,ocr:[row('Continue Challenge',831,399,287,40),row('Leave Domain?',864,640,221,36)],
  hud:{world:false,auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,climbing:false,loading:false,unknownHud:false,objectiveChanged:false}};
const air={session,frameId:21,timestamp:t+500,map:null,ocr:[row('Kaeya',1660,484,92,41),row('Trial',1790,463,49,24),row('1063/1427',906,1001,104,21),row('Space',1695,1010,81,28)],
  hud:{world:false,groundControls:false,climbing:false,auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,tutorialStep:null,
    objectiveChanged:false,interact:false,enemyBars:[],health:{current:1063,max:1427}}};
const ground={session,frameId:22,timestamp:t+1100,map:null,ocr:[row('Kaeya',1660,484,92,41),row('Trial',1790,463,49,24),row('1063/1427',906,1001,104,21),row('E',1689,1027,19,21),row('Q',1808,1028,19,21)],
  hud:{...air.hud,groundControls:true}};

test('glide state accepts only fresh safe airborne or grounded Trial Kaeya at captured max HP',()=>{
  assert.equal(bgi.wolfGlideState(air,t+500),'airborne');
  assert.equal(bgi.wolfGlideState(ground,t+1100),'grounded');
  for(const bad of [
    {...air,timestamp:t-1},
    {...air,hud:{...air.hud,health:{current:850,max:1427}}},
    {...air,hud:{...air.hud,health:{current:1063,max:1400}}},
    {...air,hud:{...air.hud,enemyBars:[{}]}},
    {...air,hud:{...air.hud,interact:true}},
    {...air,hud:{...air.hud,dialogueReady:true}},
    {...air,ocr:air.ocr.filter(r=>r.text!=='Trial')},
  ]) assert.equal(bgi.wolfGlideState(bad,t+1200),null);
});

test('mission Continues once, observes each W400 separately, and stops on verified grounding without quest claim',async()=>{
  let now=t,idx=0,continues=0,moves=0,reads=0;
  const states=['unused','airborne','airborne','grounded'];
  const api={now:()=>now,checkStop(){},sleep:async ms=>{now+=ms;},wolfGlideForwardReady:()=>true,
    wolfGlideForwardContinue:()=>{continues++;},wolfGlideState:()=>states[idx],wolfGlideForwardMove:async()=>{moves++;now+=400;}};
  const result=await mission.runQuestStep('wolfGlideForward',pause,api,async()=>{reads++;idx++;now+=100;return {...air,frameId:20+reads,timestamp:now};});
  assert.equal(result.status,'stopped');assert.equal(result.continueAttempts,1);assert.equal(result.moveAttempts,2,JSON.stringify(result));
  assert.equal(result.inputMs,800);assert.equal(result.landingVerified,true);assert.equal(result.questComplete,false);
  assert.equal(continues,1);assert.equal(moves,2);assert.equal(reads,3);assert.equal(result.polls,3);
});

test('a grounded post-Continue capture is not a landing and sends no glide input',async()=>{
  let now=t,continues=0,moves=0,reads=0;
  const api={now:()=>now,checkStop(){},sleep:async ms=>{now+=ms;},wolfGlideForwardReady:()=>true,
    wolfGlideForwardContinue:()=>{continues++;},wolfGlideState:()=> 'grounded',wolfGlideForwardMove:async()=>{moves++;}};
  const result=await mission.runQuestStep('wolfGlideForward',pause,api,async()=>{reads++;now+=100;return {...ground,frameId:30,timestamp:now};});
  assert.equal(result.status,'stopped');assert.match(result.reason,/Already grounded after Continue/);
  assert.equal(result.continueAttempts,1);assert.equal(result.moveAttempts,0);assert.equal(result.inputMs,0);
  assert.equal(result.groundedBeforeGlide,true);assert.equal(result.landingVerified,false);assert.equal(result.questComplete,false);
  assert.equal(continues,1);assert.equal(moves,0);assert.equal(reads,1);
});

test('mission stops at four holds or on invalid fresh state without asserting landing',async()=>{
  let now=t,reads=0,moves=0;
  const api={now:()=>now,checkStop(){},sleep:async ms=>{now+=ms;},wolfGlideForwardReady:()=>true,wolfGlideForwardContinue(){},
    wolfGlideState:()=>reads===0?'airborne':reads===5?null:'airborne',wolfGlideForwardMove:async()=>{moves++;now+=400;}};
  const result=await mission.runQuestStep('wolfGlideForward',pause,api,async()=>{reads++;now+=100;return {...air,frameId:20+reads,timestamp:now};});
  assert.equal(result.moveAttempts,4);assert.equal(result.landingVerified,false);assert.equal(result.questComplete,false);
  assert.equal(moves,4);assert.equal(reads,5);
});

test('actual adapter Continue and W400 are guarded, released, and capped per request',async()=>{
  let now=t,rows=pause.ocr,frame=20;const keys=[],clicks=[];
  const reports=[party];const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
  const context={Date:class extends Date{static now(){return now;}},genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='reports/'+session+'.json',readTextSync:p=>p==='reports/'+session+'.json'?JSON.stringify(reports):fs.readFileSync(path.join(root,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(mat){this.rows=mat&&mat.rows||[];}findMulti(){const a=this.rows.map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x,contourArea:()=>0}}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows.map(r=>({...r}));a.count=a.length;return a;},deriveCrop:()=>({srcMat:{resize:()=>({rows:[]}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}}),dispose(){}}),
    click:(x,y)=>clicks.push([x,y]),keyDown:k=>keys.push(['down',k,now]),keyUp:k=>keys.push(['up',k,now]),sleep:async ms=>{now+=ms;},moveMouseBy(){throw Error('Unexpected cursor movement');},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);adapter.beginMission({mission:'questStep',step:'wolfGlideForward',session,createdAt:now});
  const start=await adapter.observe(session,frame++);assert.equal(adapter.wolfGlideForwardReady(start),true);
  adapter.wolfGlideForwardContinue();assert.deepEqual(clicks,[[975,419]]);
  rows=air.ocr;await adapter.sleep(450);const current=await adapter.observe(session,frame++);
  assert.equal(adapter.wolfGlideState(current),'airborne');
  await adapter.wolfGlideForwardMove(current);
  assert.deepEqual(keys.map(e=>e.slice(0,2)),[['down','VK_W'],['up','VK_W']]);
  assert.equal(keys[1][2]-keys[0][2],400);
  await assert.rejects(adapter.wolfGlideForwardMove(current),/Fresh safe airborne/,'a second hold requires a new observation');
});
