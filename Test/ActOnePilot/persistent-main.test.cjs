const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const bgiSource=fs.readFileSync(path.join(root,'bgi.js'),'utf8')+'\nfunction createActOneAdapter(){return testAdapter;}';

function scene(now,kind='blank') {
  const hud={world:false,journal:false,bigMap:false,dialogueReady:false,choice:false};
  if(kind==='inventory') return {timestamp:now,screenshotPath:'inventory.png',map:null,hud,ocr:[
    {text:'Weapons',x:139,y:28,width:119,height:40},{text:'Weapons 7/2000',x:1612,y:32,width:189,height:27}]};
  if(kind==='world') return {timestamp:now,screenshotPath:'world.png',map:{map:'Teyvat',x:0,y:0},hud:{...hud,world:true},ocr:[{text:'Teyvat'}]};
  if(kind==='auth') return {timestamp:now,screenshotPath:'auth.png',map:null,hud,ocr:[{text:'Verification code required'}]};
  if(kind==='titlePulse') return {timestamp:now,screenshotPath:'title.png',map:null,hud,ocr:[
    {text:'START GAME',x:761,y:472,width:389,height:67},
    {text:'America',x:890,y:907,width:139,height:35}
  ]};
  if(kind==='door') return {timestamp:now,screenshotPath:'door.png',map:null,hud,ocr:[
    {text:'CLICK TO BEGIN',x:853,y:1003,width:209,height:39}
  ]};
  return {timestamp:now,screenshotPath:'blank.png',map:null,hud,ocr:[]};
}

async function runMain({storageVersion=1,focusFailures=0,sessionId=6,remote=true,enableInput=false,autoEnterGame,observations=['world'],cancelDuringFocus=false,requestSequence,missionSource}={}) {
  let now=100000,polls=0,releases=0,focuses=0,callback=null,observeCount=0,startupObservationCount=null;
  const files=new Map(),states=[],sleeps=[],captures=[],startupSteps=[];
  const write=(p,t)=>{files.set(p,t);if(p==='controller-status.json')states.push(JSON.parse(t));return true;};
  const api={now:()=>now,focusGame:async()=>{focuses++;if(focuses<=focusFailures)throw Error('No RDP game focus');},
    setHeartbeat:fn=>{callback=fn;},heartbeat:(_,force)=>callback(force),checkStop:()=>{},requireInputReady:()=>{},
    observe:async(session,n)=>{captures.push([session,n]);const kind=observations[Math.min(observeCount,observations.length-1)]||'blank';observeCount++;
      return scene(now,kind);},
    write,append:(p,t)=>write(p,(files.get(p)||'')+t),wasSeen:(s,id)=>files.has(`receipts/${s}/${id}.json`),
    beginMission:()=>{},events:()=>[],release:()=>{releases++;}};
  const source={
    'engine.js':fs.readFileSync(path.join(root,'engine.js'),'utf8'),
    'bgi.js':bgiSource,
    'mission.js':missionSource||'var ActOneMission={runQuestStep:async function(step,observation){startupSteps.push({step:step,frameId:observation.frameId,observationCount:observeCount});return {status:"completed",step:step};}};',
    'combat.js':'var ActOneCombat={};','recovery.js':'var ActOneRecovery={};'
  };
  const context=vm.createContext({testAdapter:api,startupSteps,get observeCount(){return observeCount;},Date:{now:()=>now},Math,Number,JSON,Object,Error,
    genshin:{isRemoteDesktopSession:remote,windowsSessionId:sessionId,betterGiProcessId:1234,width:1920,height:1080},
    settings:{enableInput,autoEnterGame},dispatcher:{clearAllTriggers:()=>{}},getGameMetrics:()=>[1920,1080,1],setGameMetrics:()=>{},log:{info:()=>{}},
    file:{captureStorageVersion:storageVersion,readTextSync:p=>source[p]??files.get(p),writeTextSync:write,createDirectory:()=>true,isExists:p=>files.has(p)},
    sleep:async ms=>{
      sleeps.push(ms);now+=ms;
      if(cancelDuringFocus && focuses===1 && !files.has('observation.json')) {
        const status=JSON.parse(files.get('controller-status.json'));
        write('stop.json',JSON.stringify({session:status.session,createdAt:now}));
      }
      if(states.at(-1)?.state!=='idle'&&!(requestSequence&&states.at(-1)?.state==='faulted')) return;
      if(startupObservationCount===null) startupObservationCount=observeCount;
      polls++;if(polls>(requestSequence?.length||3))throw Error('Listener did not honor explicit stop');
      if(!requestSequence)now+=polls===1?7200000:polls===2?30*24*3600000:0;
      if(files.has('observation.json')) {
        const latest=JSON.parse(files.get('observation.json'));
        write('request.json',JSON.stringify({id:`request-${polls}`,session:latest.session,expectedFrameId:latest.frameId,createdAt:now,...(requestSequence?requestSequence[polls-1]:{mission:polls===3?'stop':'observe'})}));
      }
    }
  });
  let error=null;try{await vm.runInContext(fs.readFileSync(path.join(root,'main.js'),'utf8'),context);}catch(e){error=e;}
  return {files,states,polls,releases,focuses,captures,sleeps,startupSteps,startupObservationCount,error};
}

test('actual main listener survives two hours and a month idle, then honors explicit stop',async()=>{
  const h=await runMain();assert.equal(h.error,null);assert.equal(h.polls,3);assert.equal(h.focuses,1);
  assert.equal(new Set(h.captures.map(c=>c[0])).size,1,'no periodic session restart');
  assert.ok(h.states.some(s=>s.heartbeatAt>=30*24*3600000&&s.state==='idle'));
  assert.equal(h.states.at(-1).state,'stopped');assert.equal(h.states.at(-1).processId,1234);
  assert.ok(h.releases>=3);assert.equal(JSON.parse(h.files.get('receipt.json')).status,'stopped');
});

test('an old runtime cannot capture or focus the game without native storage enforcement',async()=>{
  // An unsupported version exercises the same missing-property admission failure.
  const unsupported=await runMain({storageVersion:0});
  assert.match(String(unsupported.error),/bounded capture-storage runtime/);
  assert.equal(unsupported.focuses,0);assert.equal(unsupported.captures.length,0);
});

test('transient startup focus failures retry with starting heartbeats before observing',async()=>{
  const h=await runMain({focusFailures:2});
  assert.equal(h.error,null);assert.equal(h.focuses,3);assert.deepEqual(h.sleeps.slice(0,2),[350,350]);
  assert.equal(h.captures.length>0,true);assert.ok(h.states.slice(0,4).every(s=>s.state==='starting'));
  assert.ok(h.releases>=2);
});

test('five failed focus attempts fault without observing or dispatching gameplay and release held input',async()=>{
  const h=await runMain({focusFailures:5,enableInput:true,observations:['titlePulse']});
  assert.match(h.error.message,/focus failed after 5 bounded attempts.*No RDP game focus/);
  assert.equal(h.focuses,5);assert.deepEqual(h.sleeps,[350,350,350,350]);
  assert.equal(h.captures.length,0);assert.equal(h.startupSteps.length,0);assert.equal(h.releases,6);
  assert.equal(h.states.at(-1).state,'faulted');
});

test('startup title frame dispatches enterGame while its CLICK TO BEGIN hint is blinking',async()=>{
  const h=await runMain({enableInput:true,observations:['titlePulse']});
  assert.equal(h.error,null);assert.deepEqual(h.startupSteps.map(x=>x.step),['enterGame']);
  assert.equal(h.startupSteps[0].frameId,2);assert.equal(h.startupSteps[0].observationCount,2);assert.equal(h.focuses,1);
});

test('account switching can disable automatic title and door entry while retaining an idle supervised controller',async()=>{
  for(const kind of ['titlePulse','door']) {
    const h=await runMain({enableInput:true,autoEnterGame:false,observations:[kind]});
    assert.equal(h.error,null);assert.equal(h.startupSteps.length,0);
    assert.ok(h.states.some(s=>s.state==='idle'));assert.equal(h.states.at(-1).state,'stopped');
  }
});

test('bottom CLICK TO BEGIN startup frame dispatches enterWorld',async()=>{
  const h=await runMain({enableInput:true,observations:['door']});
  assert.equal(h.error,null);assert.deepEqual(h.startupSteps.map(x=>x.step),['enterWorld']);
  assert.equal(h.startupSteps[0].frameId,2);assert.equal(h.startupSteps[0].observationCount,2);
});

test('blank startup recognition stops after eight observations and does not dispatch a mission',async()=>{
  const h=await runMain({enableInput:true,observations:Array(10).fill('blank')});
  assert.equal(h.error,null);assert.equal(h.startupObservationCount,8);assert.equal(h.startupSteps.length,0);
  assert.equal(h.sleeps.filter(ms=>ms===350).length,7);
});

test('known authentication screen stops startup polling without mission dispatch',async()=>{
  const h=await runMain({enableInput:true,observations:['auth','titlePulse']});
  assert.equal(h.error,null);assert.equal(h.startupObservationCount,1);assert.equal(h.startupSteps.length,0);
});

test('startup cancellation during focus retry releases keys and accepts no work',async()=>{
  const h=await runMain({focusFailures:5,cancelDuringFocus:true});
  assert.match(h.error.message,/Stop requested during controller startup/);
  assert.equal(h.focuses,1);assert.equal(h.captures.length,0);assert.ok(h.releases>=2);
  assert.equal(h.states.at(-1).state,'faulted');
});

test('main accepts session 6 and rejects non-RDP, console, and session 0 before accepting work',async()=>{
  const allowed=await runMain();
  assert.equal(allowed.error,null);
  assert.equal(allowed.states[0].windowsSessionId,6);
  assert.equal(allowed.states[0].remoteDesktop,true);
  for(const options of [{remote:false},{sessionId:1,remote:true},{sessionId:0}]) {
    const rejected=await runMain(options);
    assert.match(rejected.error.message,/verified RDP child session above Windows session 1/);
    assert.equal(rejected.captures.length,0);
  }
});

test('pause exhaustion retains listener, blocks gameplay, permits observation and explicit stop',async()=>{
 const h=await runMain({enableInput:true,requestSequence:[{mission:'questStep',step:'actTwoForgeClose'},{mission:'questStep',step:'actTwoKaeyaTalk'},{mission:'observe'},{mission:'stop'}],
 missionSource:'var ActOneMission={runQuestStep:async function(step){startupSteps.push({step});var e=new Error("Unknown UI pause exhausted");e.code="PAUSE_PROTECTION_EXHAUSTED";throw e;}};'});
 assert.equal(h.error,null);assert.equal(h.polls,4);assert.equal(h.startupSteps.length,1);
 assert.ok(h.states.some(s=>s.state==='faulted'&&s.error==='Unknown UI pause exhausted'));
 const receipts=[...h.files].filter(([p])=>p.startsWith('receipts/')).map(([,v])=>JSON.parse(v));
 assert.equal(receipts.find(r=>r.id==='request-2').status,'rejected');
 assert.equal(receipts.find(r=>r.id==='request-3').status,'completed');
 assert.equal(h.states.at(-1).state,'stopped');assert.ok(h.releases>=2);
});

test('Act II fault clears only after matching recovery result and fresh independent pause proof',async()=>{
 for(const verified of [true,false]){
 const h=await runMain({enableInput:true,observations:['inventory'],requestSequence:[{mission:'questStep',step:'actTwoForgeClose'},{mission:'questStep',step:'actTwoRecover'},{mission:'questStep',step:'actTwoKaeyaTalk'},{mission:'stop'}],
 missionSource:'var ActOneMission={runQuestStep:async function(step){startupSteps.push({step});if(step==="actTwoForgeClose"){var e=new Error("Unknown UI pause exhausted");e.code="PAUSE_PROTECTION_EXHAUSTED";throw e;}return {status:"completed",step:step,pauseVerified:'+verified+'};}};'});
 assert.equal(h.error,null);
 const receipts=[...h.files].filter(([p])=>p.startsWith('receipts/')).map(([,v])=>JSON.parse(v));
 assert.equal(receipts.find(r=>r.id==='request-3').status,verified?'completed':'rejected');
 assert.equal(h.startupSteps.length,verified?3:2);
 }
});
