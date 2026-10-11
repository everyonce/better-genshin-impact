const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const bgiSource=fs.readFileSync(path.join(root,'bgi.js'),'utf8')+'\nfunction createActOneAdapter(){return testAdapter;}';

function domainFrame(now,missingKaeya=false,currentHp=1000) {
  return {timestamp:now,map:null,ocr:[
    ...(missingKaeya?[{text:'Kaea',x:1665,y:489,width:64,height:27}]:[{text:'Kaeya',x:1663,y:487,width:70,height:30}]),{text:'Trial',x:1802,y:463,width:60,height:30}
  ],hud:{world:false,groundControls:true,health:{current:currentHp,max:1427},journal:false,bigMap:false,
    dialogueReady:false,choice:false,tutorialStep:null,enemyBars:[]}};
}
function pauseFrame(now) {
  return {timestamp:now,map:null,ocr:[
    {text:'Continue Challenge',x:800,y:400,width:300,height:40},{text:'Leave Domain?',x:800,y:650,width:300,height:40}
  ],hud:{world:false,auto:false,groundControls:false,health:{current:1000,max:1427},journal:true,bigMap:false,
    dialogueReady:false,choice:false,tutorialStep:null}};
}
function worldFrame(now) { return {timestamp:now,map:{map:'Teyvat',x:0,y:0},ocr:[],hud:{world:true}}; }
function foodFrame(now) { return {timestamp:now,map:null,ocr:[{text:'Food',x:150,y:45,width:80,height:30}],hud:{world:false,journal:false,bigMap:false,dialogueReady:false,choice:false}}; }
function foodModalFrame(now) { return {timestamp:now,map:null,ocr:[
  {text:'Food',x:140,y:32,width:67,height:31},{text:'Sweet Madame',x:1332,y:127,width:263,height:41},
  {text:'Traveler',x:869,y:260,width:181,height:54},{text:'Amount to use',x:639,y:611,width:217,height:39},
  {text:'Cancel',x:716,y:748,width:109,height:37},{text:'Confirm',x:1118,y:750,width:129,height:37}
],hud:{world:false,journal:false,bigMap:false,dialogueReady:false,choice:false}}; }

async function runController({requestSteps=['wolfAdvance'],pauseSucceeds=true,initialScene='world',pauseProven=false,
  sceneAfterFirstMove=null,throwOnUnknownObserve=false,pauseReportsStopped=false,resumeProof=false,
  lateMenuAfterFault=false,laterInputAfterFault=false,corruptPauseProof=null,domainHp=1000}={}) {
  let now=2000000,callback=null,scene=initialScene,currentRequest=null,pauseInputs=0,continueInputs=0,moves=0,kaeyaSelects=0,kaeyaSkills=0,defensiveCryos=0,aimCryos=0,foodCloseActions=[],turretSkills=0,turretForwards=0,inventoryContinues=0,inventoryOpens=0;
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
      return scene==='pause'?pauseFrame(now):scene==='domain'?domainFrame(now,false,domainHp):scene==='domainNoKaeya'?domainFrame(now,true,domainHp):scene==='inventory'?foodFrame(now):scene==='foodModal'?foodModalFrame(now):scene==='world'?worldFrame(now):
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
    wasSeen:(s,id)=>files.has(`receipts/${s}/${id}.json`),events:()=>events.slice(),release:()=>{},checkStop:()=>{},requireInputReady:()=>{},seedObservation:()=>true,
    wolfDomainHud:o=>!!(o&&o.hud&&o.hud.groundControls&&o.ocr&&o.ocr.some(r=>r.text==='Kaeya')&&o.ocr.some(r=>r.text==='Trial')),
    wolfDomainAction:async()=>{
      if(!currentRequest||currentRequest.step!=='wolfPause'&&currentRequest.step!=='wolfAdvance'&&currentRequest.step!=='wolfForward') throw Error('unexpected domain action');
      if(currentRequest.step==='wolfPause') {pauseInputs++;events.push({type:'key',key:'VK_ESCAPE',startedAt:now});if(pauseSucceeds)scene='pause';}
      else {moves++;events.push({type:'key',key:'VK_W',startedAt:now});if(moves===1&&sceneAfterFirstMove)scene=sceneAfterFirstMove;}
    },
    wolfKaeyaSkillReady:o=>!!(api.wolfDomainHud(o)&&o.hud.health&&o.hud.health.max===1427),
    wolfKaeyaSkillSelect:async()=>{kaeyaSelects++;events.push({type:'key',key:'VK_3',startedAt:now});},
    wolfKaeyaSkillCast:async()=>{kaeyaSkills++;events.push({type:'key',key:'VK_E',startedAt:now});},
    wolfDefensiveCryoReady:o=>!!(api.wolfDomainHud(o)&&o.hud.health&&o.hud.health.max===1427&&o.hud.health.current>0),
    wolfDefensiveCryo:async()=>{if(currentRequest.step!=='wolfDefensiveCryo')throw Error('wrong defensive Cryo request');defensiveCryos++;events.push({type:'key',key:'VK_E',startedAt:now});if(sceneAfterFirstMove)scene=sceneAfterFirstMove;},
    wolfAimCryoReady:o=>!!(api.wolfKaeyaSkillReady(o)&&o.hud.health.current/o.hud.health.max>=0.6),
    wolfAimCryo:async()=>{if(currentRequest.step!=='wolfAimCryo')throw Error('wrong aim Cryo request');aimCryos++;events.push({type:'rotate',dx:250,dy:0,startedAt:now},{type:'key',key:'VK_W',durationMs:60,startedAt:now},{type:'key',key:'VK_E',durationMs:60,startedAt:now});if(sceneAfterFirstMove)scene=sceneAfterFirstMove;},
    wolfCloseFoodCryoReady:()=>scene==='inventory',
    wolfCloseFoodCryoAction:async kind=>{if(currentRequest.step!=='wolfCloseFoodCryo')throw Error('wrong close-food request');foodCloseActions.push(kind);if(kind==='close')scene='domain';if(kind==='skill'&&sceneAfterFirstMove)scene=sceneAfterFirstMove;events.push(kind==='look'?{type:'rotate',dx:250,dy:0,startedAt:now}:{type:'key',key:kind==='close'?'VK_ESCAPE':kind==='forward'?'VK_W':'VK_E',startedAt:now});},
    wolfTurretPassReady:o=>api.wolfKaeyaSkillReady(o)&&o.hud.health.current/o.hud.health.max>=0.6&&!(o.hud.enemyBars||[]).length&&!o.hud.interact?
      {ok:true,health:o.hud.health}:{ok:false,reason:'unsafe Wolf turret HUD'},
    wolfTurretPassCast:async()=>{if(currentRequest.step!=='wolfTurretPass')throw Error('wrong turret request');turretSkills++;events.push({type:'key',key:'VK_E',startedAt:now});},
    wolfTurretPassForward:async ms=>{if(currentRequest.step!=='wolfTurretPass'||ms!==800)throw Error('wrong turret forward');turretForwards++;events.push({type:'key',key:'VK_W',durationMs:ms,startedAt:now});},
    wolfInventoryContinueReady:()=>scene==='pause',
    wolfInventoryContinue:()=>{inventoryContinues++;events.push({type:'wolfContinue',startedAt:now});scene='domain';},
    wolfInventoryOpen:async()=>{inventoryOpens++;events.push({type:'key',key:'VK_B',startedAt:now});scene='inventory';},
    wolfFoodInventoryReady:o=>scene==='inventory'&&o.ocr.some(r=>r.text==='Food'),
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
  return {files,states,begun,frames,pauseInputs,continueInputs,moves,kaeyaSelects,kaeyaSkills,defensiveCryos,aimCryos,foodCloseActions,turretSkills,turretForwards,inventoryContinues,inventoryOpens,error};
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

test('one Kaeya skill attempt is fully observed then paused at the idle boundary',async()=>{
  const h=await runController({requestSteps:['wolfKaeyaSkill']});
  assert.equal(h.error,null);
  assert.equal(h.kaeyaSelects,1);
  assert.equal(h.kaeyaSkills,1);
  assert.equal(h.pauseInputs,1);
  const history=h.files.get('reports/'+JSON.parse(h.files.get('controller-status.json')).session+'.jsonl')
    .split(/\r?\n/).filter(Boolean).map(JSON.parse);
  const attempt=history.find(r=>r.details&&r.details.result&&r.details.result.step==='wolfKaeyaSkill');
  assert.equal(attempt.status,'completed');
  assert.equal(attempt.details.result.targetEffectVerified,false);
  assert.deepEqual(attempt.details.inputEvents.filter(e=>e.type==='key').map(e=>e.key),['VK_3','VK_E']);
  assert.ok(history.some(r=>r.details&&r.details.result&&r.details.result.step==='wolfPause'));
});

test('aim Cryo resumes once from verified pause, records one bounded sequence, then pauses again',async()=>{
  const h=await runController({requestSteps:['wolfAimCryo'],initialScene:'pause',pauseProven:true});
  assert.equal(h.error,null);assert.equal(h.continueInputs,1);assert.equal(h.aimCryos,1);assert.equal(h.pauseInputs,1);
  assert.equal(h.frames.length,4,'startup, one post-Continue proof, post-action proof, and pause-menu proof only');
  assert.equal(h.states.some(s=>s.state==='faulted'),false);
  const session=JSON.parse(h.files.get('controller-status.json')).session;
  const history=h.files.get('reports/'+session+'.jsonl').split(/\r?\n/).filter(Boolean).map(JSON.parse);
  const attempt=history.find(r=>r.details&&r.details.result&&r.details.result.step==='wolfAimCryo');
  assert.equal(attempt.status,'stopped');assert.equal(attempt.details.result.targetEffectVerified,false);
  assert.deepEqual(attempt.details.inputEvents.filter(e=>e.type==='key').map(e=>e.key),['VK_W','VK_E']);
  assert.ok(attempt.details.inputEvents.some(e=>e.type==='rotate'&&e.dx===250));
  assert.ok(history.some(r=>r.details&&r.details.result&&r.details.result.step==='wolfPause'&&r.details.result.pauseVerified===true));
});

test('Wolf turret action auto-continues a proved pause, attempts E only, then pauses again',async()=>{
  const h=await runController({requestSteps:['wolfTurretPass'],initialScene:'pause',pauseProven:true});
  assert.equal(h.error,null);assert.equal(h.continueInputs,1);assert.equal(h.turretSkills,1);assert.equal(h.turretForwards,0);assert.equal(h.pauseInputs,1);
  assert.equal(h.states.some(s=>s.state==='faulted'),false);
  const session=JSON.parse(h.files.get('controller-status.json')).session;
  const history=h.files.get('reports/'+session+'.jsonl').split(/\r?\n/).filter(Boolean).map(JSON.parse);
  const attempt=history.find(r=>r.details&&r.details.result&&r.details.result.step==='wolfTurretPass');
  assert.equal(attempt.status,'stopped');assert.equal(attempt.details.result.targetEffectVerified,false);assert.equal(attempt.details.result.forwardAttempts,0);
  assert.deepEqual(attempt.details.inputEvents.filter(e=>e.type==='key').map(e=>e.key),['VK_E']);
  assert.ok(history.some(r=>r.details&&r.details.result&&r.details.result.step==='wolfPause'&&r.details.result.pauseVerified===true));
});

test('Wolf inventory recovery runs directly from the verified pause and remains paused without auto-continue',async()=>{
  const h=await runController({requestSteps:['wolfInventoryRecover'],initialScene:'pause',pauseProven:true});
  assert.equal(h.error,null);assert.equal(h.inventoryContinues,1);assert.equal(h.inventoryOpens,1);
  assert.equal(h.continueInputs,0);assert.equal(h.pauseInputs,0);
  assert.equal(h.states.some(s=>s.state==='faulted'),false);
  assert.equal(JSON.parse(h.files.get('observation.json')).ocr[0].text,'Food');
});

test('exact captured Sweet Madame confirmation modal is a safe boundary without generic Confirm exemption',async()=>{
  const h=await runController({requestSteps:['wolfAdvance'],sceneAfterFirstMove:'foodModal'});
  assert.equal(h.error,null);assert.equal(h.pauseInputs,0);
  assert.equal(h.states.some(s=>s.state==='faulted'),false);
  assert.equal(JSON.parse(h.files.get('observation.json')).ocr[1].text,'Sweet Madame');
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




test('auto-pause uses the narrow Trial/max-HP fallback when Kaeya OCR falls to Kaea',async()=>{
  const h=await runController({requestSteps:['wolfAdvance'],sceneAfterFirstMove:'domainNoKaeya'});
  assert.equal(h.error,null);assert.equal(h.moves,1);assert.equal(h.pauseInputs,1);
  assert.equal(h.states.some(s=>s.state==='faulted'),false);
  const session=JSON.parse(h.files.get('controller-status.json')).session;
  const history=h.files.get('reports/'+session+'.jsonl').split(/\r?\n/).filter(Boolean).map(JSON.parse);
  assert.ok(history.some(r=>r.details&&r.details.result&&r.details.result.step==='wolfPause'&&r.details.result.pauseVerified===true));
});

test('defensive Cryo allows one E below 60 percent then auto-pauses; no movement is issued',async()=>{
  const h=await runController({requestSteps:['wolfDefensiveCryo'],domainHp:600,sceneAfterFirstMove:'domainNoKaeya'});
  assert.equal(h.error,null);assert.equal(h.defensiveCryos,1);assert.equal(h.moves,0);assert.equal(h.pauseInputs,1);
  assert.equal(h.states.some(s=>s.state==='faulted'),false);
  const session=JSON.parse(h.files.get('controller-status.json')).session;
  const history=h.files.get('reports/'+session+'.jsonl').split(/\r?\n/).filter(Boolean).map(JSON.parse);
  const attempt=history.find(r=>r.details&&r.details.result&&r.details.result.step==='wolfDefensiveCryo');
  assert.equal(attempt.status,'stopped');assert.equal(attempt.details.result.targetEffectVerified,false);
  assert.deepEqual(attempt.details.inputEvents.filter(e=>e.type==='key').map(e=>e.key),['VK_E']);
});



test('close-food Cryo never auto-continues, performs the bounded sequence, and re-pauses afterward',async()=>{
  const h=await runController({requestSteps:['wolfCloseFoodCryo'],initialScene:'inventory',sceneAfterFirstMove:'domainNoKaeya',domainHp:600});
  assert.equal(h.error,null);assert.deepEqual(h.foodCloseActions,['close','skill']);
  assert.equal(h.continueInputs,0);assert.equal(h.moves,0);assert.equal(h.pauseInputs,1);
  assert.equal(h.states.some(s=>s.state==='faulted'),false);
  const session=JSON.parse(h.files.get('controller-status.json')).session;
  const history=h.files.get('reports/'+session+'.jsonl').split(/\r?\n/).filter(Boolean).map(JSON.parse);
  const attempt=history.find(r=>r.details&&r.details.result&&r.details.result.step==='wolfCloseFoodCryo');
  assert.equal(attempt.status,'stopped');assert.equal(attempt.details.result.targetEffectVerified,false);
  assert.deepEqual(attempt.details.inputEvents.filter(e=>e.type==='key').map(e=>e.key),['VK_ESCAPE','VK_E']);
  assert.ok(history.some(r=>r.details&&r.details.result&&r.details.result.step==='wolfPause'&&r.details.result.pauseVerified===true));
});
