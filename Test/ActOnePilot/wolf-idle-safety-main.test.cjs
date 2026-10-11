const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const bgiSource=fs.readFileSync(path.join(root,'bgi.js'),'utf8')+'\nfunction createActOneAdapter(){return testAdapter;}';

function domainFrame(now) {
  return {timestamp:now,map:null,ocr:[
    {text:'Kaeya',x:1663,y:487,width:70,height:30},{text:'Trial',x:1796,y:463,width:60,height:30}
  ],hud:{world:false,groundControls:true,health:{current:1000,max:1427},journal:false,bigMap:false,
    dialogueReady:false,choice:false,tutorialStep:null,enemyBars:[]}};
}
function pauseFrame(now) {
  return {timestamp:now,map:null,ocr:[
    {text:'Continue Challenge',x:800,y:400,width:300,height:40},{text:'Leave Domain?',x:800,y:650,width:300,height:40}
  ],hud:{world:false,groundControls:false,health:{current:1000,max:1427},journal:true,bigMap:false,
    dialogueReady:false,choice:false,tutorialStep:null}};
}
function worldFrame(now) { return {timestamp:now,map:{map:'Teyvat',x:0,y:0},ocr:[],hud:{world:true}}; }

async function runController({requestSteps=['wolfAdvance'],pauseSucceeds=true,initialScene='world',pauseProven=false,
  sceneAfterFirstMove=null,throwOnUnknownObserve=false,pauseReportsStopped=false,resumeProof=false,
  lateMenuAfterFault=false,laterInputAfterFault=false,corruptPauseProof=null}={}) {
  let now=2000000,callback=null,scene=initialScene,currentRequest=null,pauseInputs=0,continueInputs=0,moves=0;
  const files=new Map(),states=[],events=[],begun=[],frames=[];
  function write(file,value) {
    files.set(file,value);
    if(file==='controller-status.json') {
      const status=JSON.parse(value);states.push(status);
      if(lateMenuAfterFault&&status.state==='faulted') {
        scene='pause';
        if(laterInputAfterFault) {
          now++;
          const late={session:status.session,id:'later-input',mission:'questStep',status:'completed',timestamp:now,
            details:{result:{step:'wolfForward'},inputEvents:[{type:'key',key:'VK_W',startedAt:now}]}};
          files.set('reports/'+status.session+'.jsonl',(files.get('reports/'+status.session+'.jsonl')||'')+JSON.stringify(late)+'\n');
        }
      }
      if(status.state==='starting'&&status.session&&!files.has('reports/'+status.session+'.jsonl')) {
        const proof=resumeProof?null:{session:status.session,mission:'questStep',status:'completed',timestamp:now-1000,
          details:{result:{step:'wolfPartyStart'},inputEvents:[{type:'wolfPartyStart',frameId:1,startedAt:now-1100}]}};
        const history=proof?[proof]:[];
        if(resumeProof) {
          const result={step:'wolfResume',verified:true,fromSession:'prior-session',toSession:status.session,
            priorEntryId:'old-entry',priorPauseId:'old-pause',betterGiProcessId:1234,rdpSessionId:7,
            gameProcessId:5678,verifiedAt:now-100};
          const resumeRow={session:status.session,id:'resume-proof',mission:'questStep',status:'completed',timestamp:now-50,frameId:0,
            details:{result,inputEvents:[{type:'wolfResumeProof',verified:true,fromSession:result.fromSession,
              toSession:result.toSession,priorEntryId:result.priorEntryId,priorPauseId:result.priorPauseId,
              betterGiProcessId:result.betterGiProcessId,rdpSessionId:result.rdpSessionId,
              gameProcessId:result.gameProcessId,verifiedAt:result.verifiedAt,recordedAt:now-50}]}};
          history.push(resumeRow);
          files.set('receipts/'+status.session+'/resume-proof.json',JSON.stringify(resumeRow));
        }
        if(pauseProven) {
          const pauseRow={session:status.session,id:'prior-pause',mission:'questStep',status:'completed',timestamp:now-500,frameId:0,
            details:{result:{step:'wolfPause',pauseVerified:true},inputEvents:[{type:'key',key:'VK_ESCAPE',startedAt:now-600}]}};
          history.push(pauseRow);
          files.set('receipts/'+status.session+'/prior-pause.json',JSON.stringify(pauseRow));
        }
        files.set('reports/'+status.session+'.jsonl',history.map(row=>JSON.stringify(row)).join('\n')+'\n');
      }
    }
    return true;
  }
  const api={now:()=>now,sleep:async ms=>{now+=ms;},focusGame:async()=>{},setHeartbeat:fn=>{callback=fn;},heartbeat:(_,force)=>callback(force),
    beginMission:req=>{currentRequest=req;events.length=0;begun.push({...req,frameAtBegin:frames.length});
      if(req.step&&req.step!=='wolfPause'&&req.step!=='wolfContinue'&&req.step.startsWith('wolf')&&scene==='world')scene='domain';},
    observe:async(_session,frameId)=>{frames.push({frameId,scene,step:currentRequest&&currentRequest.step});
      if(scene==='unknown'&&throwOnUnknownObserve)throw Error('simulated capture failure after Wolf input');
      return scene==='pause'?pauseFrame(now):scene==='domain'?domainFrame(now):scene==='world'?worldFrame(now):
        scene==='dialogue'?{timestamp:now,map:null,ocr:[],hud:{world:false,dialogueReady:true}}:
        {timestamp:now,map:null,ocr:[],hud:{world:false}};},
    write,append:(file,value)=>{
      let row=JSON.parse(value);
      if(corruptPauseProof&&row.details&&row.details.result&&row.details.result.step==='wolfPause'&&
          row.id&&!row.id.startsWith('idle-safety-')) {
        if(corruptPauseProof==='wrong-id') row.id='different-request-id';
        if(corruptPauseProof==='old-timestamp') row.timestamp-=100000;
      }
      files.set(file,(files.get(file)||'')+JSON.stringify(row)+'\n');return true;
    },
    wasSeen:(s,id)=>files.has(`receipts/${s}/${id}.json`),events:()=>events.slice(),release:()=>{},checkStop:()=>{},requireInputReady:()=>{},
    wolfDomainHud:o=>!!(o&&o.hud&&o.hud.groundControls&&o.ocr&&o.ocr.some(r=>r.text==='Kaeya')&&o.ocr.some(r=>r.text==='Trial')),
    wolfDomainAction:async()=>{
      if(!currentRequest||currentRequest.step!=='wolfPause'&&currentRequest.step!=='wolfAdvance'&&currentRequest.step!=='wolfForward') throw Error('unexpected domain action');
      if(currentRequest.step==='wolfPause') {pauseInputs++;events.push({type:'key',key:'VK_ESCAPE',startedAt:now});if(pauseSucceeds)scene='pause';}
      else {moves++;events.push({type:'key',key:'VK_W',startedAt:now});if(moves===1&&sceneAfterFirstMove)scene=sceneAfterFirstMove;}
    },
    wolfContinue:()=>{if(scene!=='pause')throw Error('continue requires a fresh pause menu');continueInputs++;scene='domain';events.push({type:'wolfContinue',startedAt:now});}
  };
  let missionSource=fs.readFileSync(path.join(root,'mission.js'),'utf8');
  if(pauseReportsStopped) missionSource=missionSource.replace('pausePoll<3','pausePoll<0')
    .replace('var next=observation,paused=false,polls=0;', 'await api.sleep(600);var next=observation,paused=false,polls=0;');
  const source={
    'engine.js':fs.readFileSync(path.join(root,'engine.js'),'utf8'),
    'bgi.js':bgiSource,
    'mission.js':missionSource,
    'combat.js':fs.readFileSync(path.join(root,'combat.js'),'utf8'),
    'recovery.js':fs.readFileSync(path.join(root,'recovery.js'),'utf8'),
  };
  const context=vm.createContext({testAdapter:api,Date:{now:()=>now},Math,Number,JSON,Object,Error,RegExp,Array,String,
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,betterGiProcessId:1234,width:1920,height:1080},
    settings:{enableInput:true},dispatcher:{clearAllTriggers(){}},getGameMetrics:()=>[1920,1080,1],setGameMetrics(){},log:{info(){}},
    file:{readTextSync:p=>source[p]??files.get(p),writeTextSync:write,createDirectory:()=>true,
      isExists:p=>files.has(p)},sleep:async ms=>{now+=ms;
        if(states.at(-1)?.state!=='idle'&&states.at(-1)?.state!=='faulted')return;
        if(files.has('request.json')&&JSON.parse(files.get('request.json')).mission==='stop')return;
        let next=requestSteps.shift();
        const status=states.at(-1),session=status&&status.session;
        if(next) {
          const previous=JSON.parse(files.get('observation.json'));
          const req={id:'external-'+(begun.length+1),session,createdAt:now,expectedFrameId:previous.frameId,
            mission:typeof next==='object'?next.mission:'questStep',step:typeof next==='object'?next.step:next};
          write('request.json',JSON.stringify(req));
        } else {
          const latest=JSON.parse(files.get('observation.json'));
          write('request.json',JSON.stringify({id:'stop-now',session,createdAt:now,expectedFrameId:latest.frameId,mission:'stop'}));
        }
      }});
  let error=null;
  try { await vm.runInContext(fs.readFileSync(path.join(root,'main.js'),'utf8'),context); } catch(e) { error=e; }
  return {files,states,begun,frames,pauseInputs,continueInputs,moves,error};
}

test('an idle boundary inside a proven Wolf trial pauses and records verified menu evidence',async()=>{
  const h=await runController({requestSteps:['wolfAdvance']});
  assert.equal(h.error,null);
  assert.equal(h.pauseInputs,1);
  assert.ok(h.states.some(s=>s.state==='idle'));
  const history=h.files.get('reports/'+JSON.parse(h.files.get('controller-status.json')).session+'.jsonl')
    .split(/\r?\n/).filter(Boolean).map(JSON.parse);
  const pause=history.find(r=>r.details&&r.details.result&&r.details.result.step==='wolfPause');
  assert.equal(pause.status,'completed');
  assert.equal(pause.details.result.pauseVerified,true);
  assert.ok(pause.details.inputEvents.some(e=>e.type==='key'&&e.key==='VK_ESCAPE'));
  assert.ok(h.frames.some(f=>f.scene==='pause'));
});

test('a late complete pause menu plus this automatic Escape proves safety even when the inner step stopped early',async()=>{
  const h=await runController({requestSteps:['wolfAdvance'],pauseReportsStopped:true});
  assert.equal(h.error,null);
  assert.equal(h.pauseInputs,1);
  assert.equal(h.states.some(s=>s.state==='faulted'),false);
  const session=JSON.parse(h.files.get('controller-status.json')).session;
  const history=h.files.get('reports/'+session+'.jsonl').split(/\r?\n/).filter(Boolean).map(JSON.parse);
  const pause=history.find(r=>r.details&&r.details.result&&r.details.result.step==='wolfPause');
  assert.equal(pause.status,'stopped');
  assert.equal(pause.details.result.pauseVerified,false);
  assert.ok(pause.details.inputEvents.some(e=>e.type==='key'&&e.key==='VK_ESCAPE'));
  assert.equal(JSON.parse(h.files.get('observation.json')).ocr.some(r=>r.text==='Continue Challenge'),true);
  assert.equal(JSON.parse(h.files.get('observation.json')).ocr.some(r=>r.text==='Leave Domain?'),true);
});

test('verified read-only Wolf restart proof permits one fresh-menu resume and re-arms the idle pause',async()=>{
  const h=await runController({requestSteps:['wolfForward'],initialScene:'pause',resumeProof:true});
  assert.equal(h.error,null);
  assert.equal(h.continueInputs,1);
  assert.equal(h.moves,1);
  assert.equal(h.pauseInputs,1);
  assert.equal(h.states.some(s=>s.state==='faulted'),false);
  const session=JSON.parse(h.files.get('controller-status.json')).session;
  const history=h.files.get('reports/'+session+'.jsonl').split(/\r?\n/).filter(Boolean).map(JSON.parse);
  assert.ok(history.some(r=>r.details&&r.details.result&&r.details.result.step==='wolfResume'&&
    r.details.result.verified===true&&r.details.inputEvents.some(e=>e.type==='wolfResumeProof')));
});

test('the next authorized Wolf step resumes once from verified menu, binds to the fresh frame, then pauses again',async()=>{
  const h=await runController({requestSteps:['wolfAdvance','wolfAdvance']});
  assert.equal(h.error,null);
  assert.equal(h.continueInputs,1);
  assert.equal(h.pauseInputs,2);
  const resumeIndex=h.begun.findIndex(r=>r.step==='wolfContinue');
  const secondAdvanceIndex=h.begun.map((r,i)=>r.step==='wolfAdvance'?i:-1).filter(i=>i>=0)[1];
  assert.ok(resumeIndex>=0&&secondAdvanceIndex>resumeIndex);
  const lastBeforeSecond=h.frames[h.begun[secondAdvanceIndex].frameAtBegin-1];
  assert.equal(lastBeforeSecond.scene,'domain');
  assert.equal(h.begun[secondAdvanceIndex].expectedFrameId,lastBeforeSecond.frameId);
  assert.equal(JSON.parse(h.files.get('request.json')).step,undefined,'request.json should contain only the final stop request');
  const session=JSON.parse(h.files.get('controller-status.json')).session;
  const history=h.files.get('reports/'+session+'.jsonl').split(/\r?\n/).filter(Boolean).map(JSON.parse);
  assert.ok(history.some(r=>r.details&&r.details.result&&r.details.result.step==='wolfContinue'&&
    r.details.inputEvents.some(e=>e.type==='wolfContinue')));
});

test('a failed automatic pause faults the pilot visibly but leaves the listener available for stop',async()=>{
  const h=await runController({requestSteps:['wolfAdvance'],pauseSucceeds:false});
  assert.equal(h.error,null);
  assert.equal(h.pauseInputs,1);
  assert.ok(h.states.some(s=>s.state==='faulted'&&/human attention/i.test(s.error||'')));
  assert.equal(JSON.parse(h.files.get('controller-status.json')).state,'stopped');
});

test('a later read-only observe clears the fault only after the recorded automatic Escape and a fresh full pause menu',async()=>{
  const h=await runController({requestSteps:['wolfAdvance',{mission:'observe'}],pauseSucceeds:false,lateMenuAfterFault:true});
  assert.equal(h.error,null);
  assert.equal(h.pauseInputs,1);
  assert.ok(h.states.some(s=>s.state==='faulted'));
  assert.ok(h.states.some(s=>s.state==='idle'&&s.frameId>=9));
  assert.equal(JSON.parse(h.files.get('observation.json')).ocr.some(r=>r.text==='Leave Domain?'),true);
});

test('an explicit verified pause after the fault clears it using its exact current request ID',async()=>{
  const h=await runController({requestSteps:['wolfAdvance','wolfPause'],pauseSucceeds:false,lateMenuAfterFault:true});
  assert.equal(h.error,null);
  assert.equal(h.pauseInputs,2);
  assert.ok(h.states.some(s=>s.state==='faulted'));
  assert.ok(h.states.slice(h.states.findIndex(s=>s.state==='faulted')+1).some(s=>s.state==='idle'));
  const session=JSON.parse(h.files.get('controller-status.json')).session;
  const history=h.files.get('reports/'+session+'.jsonl').split(/\r?\n/).filter(Boolean).map(JSON.parse);
  const explicit=history.find(r=>typeof r.id==='string'&&r.id.startsWith('external-')&&
    r.details&&r.details.result&&r.details.result.step==='wolfPause');
  assert.equal(explicit.details.result.step,'wolfPause');
  assert.equal(explicit.status,'completed');
  assert.equal(explicit.details.result.pauseVerified,true);
  assert.ok(explicit.details.inputEvents.some(e=>e.type==='key'&&e.key==='VK_ESCAPE'));
});

for(const corruption of ['wrong-id','old-timestamp']) {
  test('explicit pause fault clearing rejects '+corruption+' proof',async()=>{
    const h=await runController({requestSteps:['wolfAdvance','wolfPause'],pauseSucceeds:false,
      lateMenuAfterFault:true,corruptPauseProof:corruption});
    assert.equal(h.error,null);
    const faultIndex=h.states.findIndex(s=>s.state==='faulted');
    assert.ok(faultIndex>=0);
    assert.equal(h.states.slice(faultIndex+1).some(s=>s.state==='idle'),false);
  });
}

test('fault clearing rejects a pause proof followed by a later Wolf input',async()=>{
  const h=await runController({requestSteps:['wolfAdvance',{mission:'observe'}],pauseSucceeds:false,
    lateMenuAfterFault:true,laterInputAfterFault:true});
  assert.equal(h.error,null);
  const faultIndex=h.states.findIndex(s=>s.state==='faulted');
  assert.ok(faultIndex>=0);
  assert.equal(h.states.slice(faultIndex+1).some(s=>s.state==='idle'),false);
});

test('a failed explicit pause faults after one attempt instead of toggling Escape again',async()=>{
  const h=await runController({requestSteps:['wolfPause'],initialScene:'domain',pauseSucceeds:false});
  assert.equal(h.error,null);
  assert.equal(h.pauseInputs,1);
  assert.ok(h.states.some(s=>s.state==='faulted'&&/explicit pause request/i.test(s.error||'')));
});

test('an explicit Wolf continue is not immediately reversed by an automatic pause',async()=>{
  const h=await runController({requestSteps:['wolfContinue'],initialScene:'pause',pauseProven:true});
  assert.equal(h.error,null);
  assert.equal(h.continueInputs,1);
  assert.equal(h.pauseInputs,0);
  const session=JSON.parse(h.files.get('controller-status.json')).session;
  const history=h.files.get('reports/'+session+'.jsonl').split(/\r?\n/).filter(Boolean).map(JSON.parse);
  assert.ok(history.some(r=>r.details&&r.details.result&&r.details.result.step==='wolfContinue'&&
    r.details.inputEvents.some(e=>e.type==='wolfContinue')));
});

test('an ambiguous scene after known Wolf activity faults visibly without speculative pause input',async()=>{
  const h=await runController({requestSteps:['wolfAdvance'],sceneAfterFirstMove:'unknown'});
  assert.equal(h.error,null);
  assert.equal(h.moves,1);
  assert.equal(h.pauseInputs,0);
  assert.ok(h.states.some(s=>s.state==='faulted'&&/ambiguous scene/i.test(s.error||'')));
  assert.equal(JSON.parse(h.files.get('controller-status.json')).state,'stopped');
});

test('a known dialogue transition remains inspectable and does not fault or send pause input',async()=>{
  const h=await runController({requestSteps:['wolfAdvance'],sceneAfterFirstMove:'dialogue'});
  assert.equal(h.error,null);
  assert.equal(h.moves,1);
  assert.equal(h.pauseInputs,0);
  assert.equal(h.states.some(s=>s.state==='faulted'),false);
});

test('a thrown observation after Wolf input faults from the failed request event evidence',async()=>{
  const h=await runController({requestSteps:['wolfAdvance'],sceneAfterFirstMove:'unknown',throwOnUnknownObserve:true});
  assert.equal(h.error,null);
  assert.equal(h.moves,1);
  assert.equal(h.pauseInputs,0);
  assert.ok(h.states.some(s=>s.state==='faulted'&&/fresh observation after it/i.test(s.error||'')));
});
