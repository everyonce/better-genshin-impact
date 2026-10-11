const test=require('node:test');
const assert=require('node:assert/strict');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const prior='session-prior',current='session-current',now=1000000;
function pauseScreen(patch={}) {
  return {timestamp:now,map:null,ocr:[
    {text:'Continue Challenge',x:790,y:410,width:185,height:32},
    {text:'Leave Domain?',x:800,y:650,width:150,height:30},
  ],hud:{world:false,health:null,journal:false,bigMap:false,dialogueReady:false,choice:false,climbing:false,...patch}};
}
function entryReceipt(){return {session:prior,id:'entry-1',mission:'questStep',status:'completed',timestamp:now-60000,
  details:{result:{step:'falconPartyStart'},inputEvents:[{type:'falconPartyStart'}]}};}
function pauseReceipt(){return {session:prior,id:'pause-1',mission:'questStep',status:'stopped',timestamp:now-1000,
  details:{result:{step:'falconCombat',paused:true},inputEvents:[{type:'key',key:'VK_ESCAPE'}]}};}
function evidence(patch={}){return {fromSession:prior,toSession:current,priorEntryId:'entry-1',priorPauseId:'pause-1',verifiedAt:now,rdpSessionId:5,...patch};}

test('resume provenance validates real prior entry and pause receipts with a fresh pause screen lacking HP OCR',()=>{
  const screen=pauseScreen();
  assert.equal(screen.hud.health,null,'pause menu does not provide HP OCR');
  const entry=entryReceipt(),pause=pauseReceipt();
  const records=[{...entry,status:'started',details:null},entry,{...pause,status:'started',details:null},pause];
  assert.deepEqual(bgi.validateFalconResume(evidence(),records,[],current,5,screen,now),
    {fromSession:prior,toSession:current,priorEntryId:'entry-1',priorPauseId:'pause-1',verifiedAt:now});
  const explicitPause=pauseReceipt();explicitPause.status='completed';explicitPause.details.result={step:'falconPause'};
  assert.ok(bgi.validateFalconResume(evidence(),[entryReceipt(),explicitPause],[],current,5,screen,now));
});

test('resume provenance fails closed on missing receipts, mismatched sessions, stale attestation or reused proof',()=>{
  const records=[entryReceipt(),pauseReceipt()],screen=pauseScreen();
  assert.equal(bgi.validateFalconResume(evidence(),[pauseReceipt()],[],current,5,screen,now),null,'missing entry must not throw');
  for(const [e,session,rdp,obs,cur] of [
    [evidence({fromSession:'other'}),current,5,screen,[]],
    [evidence({toSession:'other'}),current,5,screen,[]],
    [evidence({rdpSessionId:4}),current,5,screen,[]],
    [evidence({verifiedAt:now-300001}),current,5,screen,[]],
    [evidence(),current,4,screen,[]],
    [evidence(),current,5,{...screen,timestamp:now-1001},[]],
    [evidence(),current,5,{...screen,hud:{...screen.hud,world:true}},[]],
    [evidence(),current,5,{...screen,map:{map:'Teyvat'}},[]],
    [evidence(),current,5,{...screen,ocr:[{text:'Continue Challenge',x:500,y:410,width:185,height:32},{text:'Leave Domain?',x:800,y:650,width:150,height:30}]},[]],
    [evidence(),current,5,screen,[{session:current,id:'used',mission:'questStep',status:'completed',details:{result:{step:'falconResume'}}}]],
  ]) assert.equal(bgi.validateFalconResume(e,records,cur,session,rdp,obs,now),null);
  const staleEntry=entryReceipt();staleEntry.timestamp=now-7200001;
  assert.equal(bgi.validateFalconResume(evidence(),[staleEntry,pauseReceipt()],[],current,5,screen,now),null);
  const forgedPause=pauseReceipt();forgedPause.details.inputEvents=[];
  assert.equal(bgi.validateFalconResume(evidence(),[entryReceipt(),forgedPause],[],current,5,screen,now),null);
});

test('falconResume mission delegates only the verified one-shot continue and returns a fresh observation',async()=>{
  let clock=now,clicks=0,observations=0;const calls=[];
  const api={now:()=>clock,checkStop:()=>calls.push('guard'),falconResume:()=>{clicks++;return {fromSession:prior,toSession:current,priorEntryId:'entry-1',priorPauseId:'pause-1'};},
    sleep:async ms=>{calls.push(['sleep',ms]);clock+=ms;}};
  const result=await mission.runQuestStep('falconResume',pauseScreen(),api,async()=>{observations++;return {frameId:23};});
  assert.equal(result.status,'completed');assert.equal(result.step,'falconResume');assert.equal(result.frameId,23);
  assert.equal(clicks,1);assert.equal(observations,1);assert.deepEqual(calls,[['sleep',500]]);
});

test('missing resume proof produces no click or follow-up observation',async()=>{
  let clicks=0,observations=0;
  const api={now:()=>now,falconResume:()=>{throw new Error('Explicit Falcon resume evidence required');},sleep:async()=>{}};
  await assert.rejects(mission.runQuestStep('falconResume',pauseScreen(),api,async()=>{observations++;return {};}),/resume evidence/);
  assert.equal(clicks,0);assert.equal(observations,0);
});

test('combat reports the time limit when 30 seconds expires before the action cap',async()=>{
  let clock=1000,observations=0,pause=false;
  const api={now:()=>clock,sleep:async ms=>{clock+=ms;},checkStop:()=>{},
    falconContinue:()=>{},falconCombatKey:async()=>{},falconPause:async()=>{pause=true;}};
  const observe=async()=>{observations++;clock+=5000;return {frameId:observations,map:null,ocr:pause?[{text:'Continue Challenge'}]:[],
    hud:{health:{current:1000,max:1000},enemyBars:[{x:800,y:500,width:100,height:8}],journal:false,bigMap:false}};};
  const result=await mission.runQuestStep('falconCombat',{frameId:0},api,observe);
  assert.equal(result.reason,'Combat time limit');assert.ok(result.actions<30);assert.equal(result.paused,true);
});
