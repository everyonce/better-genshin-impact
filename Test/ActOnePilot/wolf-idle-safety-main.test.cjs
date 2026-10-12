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

async function runController({requestSteps=['wolfAdvance'],pauseSucceeds=true,initialScene='world',pauseProven=false,combatPauseProven=false,combatPauseVariant=null,
  sceneAfterFirstMove=null,throwOnUnknownObserve=false,pauseReportsStopped=false,resumeProof=false,
  lateMenuAfterFault=false,laterInputAfterFault=false,corruptPauseProof=null,domainHp=1000,cryoWaitPauseVariant=null,spikePauseVariant=null}={}) {
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
        if(pauseProven||combatPauseProven) {
          const pauseRow={session:status.session,id:'prior-pause',mission:'questStep',status:combatPauseProven?'stopped':'completed',timestamp:now-500,frameId:0,
            details:{result:{step:combatPauseProven?'wolfCombat':'wolfPause',pauseVerified:true},inputEvents:[{type:'key',key:'VK_ESCAPE',startedAt:now-600}]}};
          if(combatPauseVariant==='missing-verified')pauseRow.details.result.pauseVerified=false;
          if(combatPauseVariant==='no-escape')pauseRow.details.inputEvents=[];
          if(combatPauseVariant==='multiple-escape')pauseRow.details.inputEvents.push({type:'key',key:'VK_ESCAPE',startedAt:now-550});
          if(combatPauseVariant==='later-input')pauseRow.details.inputEvents.push({type:'key',key:'VK_W',startedAt:now-550});
          if(combatPauseVariant==='wrong-session')pauseRow.session='other-session';
          history.push(pauseRow);
          const receipt=JSON.parse(JSON.stringify(pauseRow));if(combatPauseVariant==='receipt-mismatch')receipt.timestamp++;
          files.set('receipts/'+status.session+'/prior-pause.json',JSON.stringify(receipt));
        }
        if(cryoWaitPauseVariant) {
          const skillAttempted=cryoWaitPauseVariant!=='abort-before-skill';
          const events=[{type:'controllerRevision'},
            {type:'wolfCryoWaitContinue',frameId:1,startedAt:now-600,finishedAt:now-590},
            {type:'wolfCryoWaitPlan',frameId:2,startedAt:now-500}];
          if(skillAttempted)events.push(
            {type:'wolfCryoWaitSkill',key:'VK_E',frameId:2,startedAt:now-300,finishedAt:now-240},
            {type:'key',key:'VK_E',startedAt:now-297,finishedAt:now-237});
          events.push({type:'wolfCryoWaitEscape',key:'VK_ESCAPE',frameId:3,startedAt:now-200,finishedAt:now-180},
            {type:'key',key:'VK_ESCAPE',startedAt:now-198,finishedAt:now-138});
          const result={step:'wolfCryoWait',pauseVerified:true,continueAttempts:1,skillAttempted,skillAttempts:skillAttempted?1:0,
            pauseAttempts:1,targetEffectVerified:false,questComplete:false,frameId:4};
          if(cryoWaitPauseVariant==='not-verified')result.pauseVerified=false;
          if(cryoWaitPauseVariant==='claims-effect')result.targetEffectVerified=true;
          if(cryoWaitPauseVariant==='out-of-order')events.find(e=>e.type==='wolfCryoWaitEscape').frameId=1;
          if(cryoWaitPauseVariant==='out-of-order-time')events.find(e=>e.type==='wolfCryoWaitEscape').startedAt=now-400;
          if(cryoWaitPauseVariant==='wrong-skill-key')events.find(e=>e.type==='wolfCryoWaitSkill').key='VK_Q';
          if(cryoWaitPauseVariant==='wrong-escape-key')events.find(e=>e.type==='wolfCryoWaitEscape').key='VK_SPACE';
          if(cryoWaitPauseVariant==='wrong-bounded-skill-key')events.find(e=>e.type==='key'&&e.key==='VK_E').key='VK_Q';
          if(cryoWaitPauseVariant==='wrong-bounded-escape-key')events.find(e=>e.type==='key'&&e.key==='VK_ESCAPE').key='VK_SPACE';
          if(cryoWaitPauseVariant==='unexpected-input')events.push({type:'key',key:'VK_W',startedAt:now-120,finishedAt:now-119});
          const row={session:cryoWaitPauseVariant==='wrong-session'?'other-session':status.session,id:'cryo-wait-pause',mission:'questStep',status:'stopped',timestamp:now-100,frameId:4,
            details:{result,inputEvents:events}};
          history.push(row);
          files.set('receipts/'+status.session+'/cryo-wait-pause.json',JSON.stringify(row));
          if(cryoWaitPauseVariant==='later-input') {
            history.push({session:status.session,id:'later-wolf-input',mission:'questStep',status:'stopped',timestamp:now-50,
              details:{result:{step:'wolfCryoWait'},inputEvents:[{type:'wolfCryoWaitEscape',key:'VK_ESCAPE',frameId:711,startedAt:now-50}]}});
          }
        }
        if(spikePauseVariant) {
          const jumping=spikePauseVariant.indexOf('jump-')===0||spikePauseVariant==='landing-jump';
          const full=spikePauseVariant==='valid'||spikePauseVariant==='bad-count'||spikePauseVariant==='key-frame-order'||jumping;
          const events=[{type:'wolfSpikeContinue',frameId:1,startedAt:now-900,finishedAt:now-890}];
          const keys=jumping?[
            ['VK_3',2,now-800,now-790],['VK_E',3,now-700,now-640],['VK_2',4,now-600,now-590],
            ['VK_W',5,now-500,now-480],['VK_W',6,now-460,now-440],['VK_W',7,now-420,now-400],['VK_ESCAPE',9,now-200,now-180]
          ]:full?[
            ['VK_3',2,now-800,now-790],['VK_E',3,now-700,now-640],['VK_2',4,now-600,now-590],['VK_W',5,now-500,now-300],['VK_ESCAPE',6,now-200,now-180]
          ]:[['VK_ESCAPE',2,now-200,now-180]];
          if(full)events.push({type:'wolfSpikeCooldownPlan',frameId:2,waitMs:6500,source:'fixedActiveFallback',startedAt:now-750});
          for(const [key,frameId,startedAt,finishedAt] of keys)events.push({type:'key',key,frameId,startedAt,finishedAt});
          if(jumping) events.push({type:'wolfSpikeLandingJump',keys:['VK_W','VK_SPACE'],durationMs:500,spaceDurationMs:60,frameId:8,startedAt:now-350,finishedAt:now-250,keysReleased:true});
          const lastFrame=jumping?10:full?7:3,lastTimestamp=now-100;
          const result={status:'stopped',step:'wolfSpikeCrossFirst',pauseVerified:true,questComplete:false,
            continueAttempts:1,characterSelectionAttempts:full?2:0,skillAttempts:full?1:0,movementAttempts:full?1:0,pauseAttempts:1,
            lastFrameId:lastFrame,lastTimestamp,iceEffectVerified:false,landingVerified:false,questProgressVerified:false};
          if(jumping) {result.movementAttempts=3;result.jumpAttempts=1;}
          if(spikePauseVariant==='wrong-frame')result.lastFrameId=full?6:2;
          if(spikePauseVariant==='bad-count')result.movementAttempts=0;
          if(spikePauseVariant==='wrong-key')events[events.length-1].key='VK_SPACE';
          if(spikePauseVariant==='key-frame-order')events.find(e=>e.type==='key'&&e.key==='VK_E').frameId=2;
          if(spikePauseVariant==='jump-no-release')events.find(e=>e.type==='wolfSpikeLandingJump').keysReleased=false;
          if(spikePauseVariant==='jump-wrong-key')events.find(e=>e.type==='wolfSpikeLandingJump').keys[1]='VK_E';
          if(spikePauseVariant==='jump-wrong-duration')events.find(e=>e.type==='wolfSpikeLandingJump').durationMs=501;
          if(spikePauseVariant==='jump-wrong-frame')events.find(e=>e.type==='wolfSpikeLandingJump').frameId=7;
          if(spikePauseVariant==='jump-count')result.jumpAttempts=0;
          if(spikePauseVariant==='jump-extra')events.push({...events.find(e=>e.type==='wolfSpikeLandingJump')});
          if(spikePauseVariant==='jump-late-key')events.find(e=>e.type==='key'&&e.key==='VK_ESCAPE').frameId=10;
          if(spikePauseVariant==='jump-forward-after') {
            const escapeIndex=events.findIndex(e=>e.type==='key'&&e.key==='VK_ESCAPE');
            events.splice(escapeIndex,0,{type:'key',key:'VK_W',frameId:9,startedAt:now-230,finishedAt:now-220});
            result.movementAttempts=4;events.find(e=>e.type==='key'&&e.key==='VK_ESCAPE').frameId=10;
          }
          if(spikePauseVariant==='unknown-event')events.push({type:'wolfSpikeUnexpectedAction',startedAt:now-160});
          const row={session:spikePauseVariant==='wrong-session'?'other-session':status.session,id:'spike-cross-pause',mission:'questStep',status:'stopped',timestamp:now-80,frameId:lastFrame,
            details:{result,inputEvents:events}};
          history.push(row);
          files.set('receipts/'+status.session+'/spike-cross-pause.json',JSON.stringify(row));
          if(spikePauseVariant==='later-w'||spikePauseVariant==='later-2') {
            history.push({session:status.session,id:'later-spike-input',mission:'questStep',status:'stopped',timestamp:now-50,
              details:{result:{step:'wolfSpikeCrossFirst'},inputEvents:[{type:'key',key:spikePauseVariant==='later-w'?'VK_W':'VK_2',frameId:lastFrame+1,startedAt:now-50,finishedAt:now-40}]}});
          }
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

test('verified wolfCryoWait Escape is accepted as a same-session pause receipt without claiming gameplay effects',async()=>{
  const h=await runController({requestSteps:[{mission:'observe'},{mission:'observe'},{mission:'observe'},'wolfAdvance'],initialScene:'pause',cryoWaitPauseVariant:'valid'});
  assert.equal(h.error,null);
  assert.equal(h.continueInputs,1,'the canonical pause was resumed only after provenance validation');
  assert.ok(h.moves>0,'the authorized Wolf step proceeded after the verified resume');
  assert.equal(h.states.some(s=>s.state==='faulted'),false);
});

test('wolfCryoWait accepts a verified safe abort before E when Continue and Escape are source-frame ordered',async()=>{
  const h=await runController({requestSteps:[{mission:'observe'},{mission:'observe'},{mission:'observe'},'wolfAdvance'],initialScene:'pause',cryoWaitPauseVariant:'abort-before-skill'});
  assert.equal(h.error,null);
  assert.equal(h.continueInputs,1);
  assert.ok(h.moves>0);
  assert.equal(h.states.some(s=>s.state==='faulted'),false);
});

test('wolfCryoWait pause provenance rejects failed Escape, later input, wrong session, and unordered evidence',async()=>{
  for(const variant of ['not-verified','claims-effect','later-input','wrong-session','out-of-order','out-of-order-time','wrong-skill-key','wrong-escape-key','wrong-bounded-skill-key','wrong-bounded-escape-key','unexpected-input']) {
    const h=await runController({requestSteps:[{mission:'observe'},{mission:'observe'},{mission:'observe'},'wolfAdvance'],initialScene:'pause',cryoWaitPauseVariant:variant});
    assert.equal(h.error,null,variant);
    assert.equal(h.continueInputs,0,variant+' must not authorize Continue');
    assert.equal(h.moves,0,variant+' must not authorize follow-up gameplay input');
  }
});

test('verified Spike routine pause resumes from its final fresh receipt without claiming landing or ice effect',async()=>{
  const h=await runController({requestSteps:[...Array(6).fill({mission:'observe'}),'wolfAdvance'],initialScene:'pause',spikePauseVariant:'valid'});
  assert.equal(h.error,null);
  assert.equal(h.continueInputs,1);
  assert.ok(h.moves>0);
  assert.equal(h.states.some(s=>s.state==='faulted'),false);
});

test('verified Spike abort before E can prove pause with only Continue and released Escape',async()=>{
  const h=await runController({requestSteps:[{mission:'observe'},{mission:'observe'},'wolfAdvance'],initialScene:'pause',spikePauseVariant:'abort-before-skill'});
  assert.equal(h.error,null);
  assert.equal(h.continueInputs,1);
  assert.ok(h.moves>0);
  assert.equal(h.states.some(s=>s.state==='faulted'),false);
});

test('verified Spike landing jump is tracked between three forward inputs and the final pause Escape',async()=>{
  const requests=[...Array(12).fill({mission:'observe'}),'wolfAdvance'];
  const h=await runController({requestSteps:requests,initialScene:'pause',spikePauseVariant:'landing-jump'});
  assert.equal(h.error,null);
  assert.equal(h.continueInputs,1);
  assert.ok(h.moves>0);
  assert.equal(h.states.some(s=>s.state==='faulted'),false);
});

test('Spike pause provenance rejects later movement/selection, wrong Escape, session, frame order, and inconsistent counters',async()=>{
  for(const variant of ['later-w','later-2','wrong-key','wrong-session','wrong-frame','key-frame-order','bad-count','unknown-event']) {
    const requests=[...Array(6).fill({mission:'observe'}),'wolfAdvance'];
    const h=await runController({requestSteps:requests,initialScene:'pause',spikePauseVariant:variant});
    assert.equal(h.error,null,variant);
    assert.equal(h.continueInputs,0,variant+' must not authorize Continue');
    assert.equal(h.moves,0,variant+' must not authorize follow-up movement');
  }
});

test('Spike jump provenance rejects unreleased, altered, extra, uncounted, or mistimed jump events',async()=>{
  for(const variant of ['jump-no-release','jump-wrong-key','jump-wrong-duration','jump-wrong-frame','jump-count','jump-extra','jump-forward-after']) {
    const requests=[...Array(8).fill({mission:'observe'}),'wolfAdvance'];
    const h=await runController({requestSteps:requests,initialScene:'pause',spikePauseVariant:variant});
    assert.equal(h.error,null,variant);
    assert.equal(h.continueInputs,0,variant+' must not authorize Continue');
    assert.equal(h.moves,0,variant+' must not authorize follow-up movement');
  }
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

test('verified stopped Wolf combat pause with exactly one Escape resumes from the fresh menu',async()=>{
  const h=await runController({requestSteps:['wolfForward'],initialScene:'pause',combatPauseProven:true});
  assert.equal(h.error,null);assert.equal(h.continueInputs,1);assert.equal(h.moves,1);
  assert.equal(h.states.some(s=>s.state==='faulted'),false);
});

for(const variant of ['missing-verified','no-escape','multiple-escape','later-input','wrong-session','receipt-mismatch']) {
  test('combat pause resume rejects '+variant+' evidence',async()=>{
    const h=await runController({requestSteps:['wolfForward'],initialScene:'pause',combatPauseProven:true,combatPauseVariant:variant});
    assert.equal(h.error,null);assert.equal(h.continueInputs,0);assert.equal(h.moves,0);
  });
}

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
