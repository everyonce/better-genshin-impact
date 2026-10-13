const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const engineSource=fs.readFileSync(path.join(root,'engine.js'),'utf8');
const bgiSource=fs.readFileSync(path.join(root,'bgi.js'),'utf8');
const missionSource=fs.readFileSync(path.join(root,'mission.js'),'utf8');
const mainSource=fs.readFileSync(path.join(root,'main.js'),'utf8');
const row=(text,x,y,width=80,height=24)=>({text,x,y,width,height});
const entry={session:'s',mission:'questStep',status:'completed',timestamp:1998000,details:{result:{step:'wolfPartyStart'},
  inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',startedAt:1997900}]}};

function fixture(initialRows) {
  let now=2000000,rows=initialRows.slice(),frame=0;
  const files=new Map([['reports/s.json',JSON.stringify([entry])]]),clicks=[],keys=[],observations=[];
  const sources={'engine.js':engineSource,'bgi.js':bgiSource,'mission.js':missionSource,'main.js':'','combat.js':'','recovery.js':''};
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{pinCaptureEvidence:()=>{},isExists:p=>files.has(p),readTextSync:p=>sources[p]??files.get(p),writeTextSync:(p,v,append)=>{files.set(p,append?(files.get(p)||'')+v:v);return true;},writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const a=(this.mat.rows||[]).map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x,contourArea:()=>0}}},
    captureGameRegion:()=>{const captured=rows.slice();return {width:1920,height:1080,srcMat:{},findMulti:()=>{const a=captured.map(r=>({...r}));a.count=a.length;return a;},
      deriveCrop:()=>({srcMat:{resize:()=>({rows:[]}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}}),dispose(){}};},
    keyDown:k=>keys.push(['down',k]),keyUp:k=>keys.push(['up',k]),sleep:async ms=>{now+=ms;},moveMouseBy(){},click:(x,y)=>{clicks.push([x,y]);rows=[row('Kaeya',1663,487),row('Trial',1796,463),row('1000/1427',910,1000,100,20),row('E',1700,1015)];},
    log:{info(){}}};
  vm.runInNewContext(bgiSource,context);
  const adapter=context.createActOneAdapter(7);
  const runner=require(path.join(root,'engine.js')).create(adapter,{session:'s',enableInput:true});
  runner.report({session:'s',id:'party-start',mission:'questStep'},'completed',{result:{step:'wolfPartyStart'},
    inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',startedAt:1997900}]});
  const observe=async()=>{frame++;const result=await runner.observe();observations.push(result);return result;};
  const missionSandbox={module:{exports:{}},ActOneCombat:{}};vm.runInNewContext(missionSource,missionSandbox);
  return {adapter,runner,observe,mission:missionSandbox.module.exports,clicks,keys,observations,files,context,setRows:v=>{rows=v;},advance:ms=>{now+=ms;},now:()=>now};
}

const pauseRows=()=>[row('Continue Challenge',800,400,300,40),row('Leave Domain?',800,650,300,40)];

test('real engine and adapter bind the fresh exact pause frame and allow one Continue with HP absent',async()=>{
  const f=fixture(pauseRows()),seed=await f.observe();
  assert.equal(seed.hud.health,null);assert.equal(seed.hud.auto,false);
  const req={session:'s',id:'continue-once',createdAt:f.now(),expectedFrameId:seed.frameId,mission:'questStep',step:'wolfContinue'};
  assert.equal(await f.runner.process(req,()=>f.mission,seed),'completed');
  assert.deepEqual(f.clicks,[[950,420]]);assert.deepEqual(f.keys,[]);assert.equal(f.runner.getFrame(),2);
  assert.equal(f.adapter.wolfDomainHud(undefined),true,'adapter state is the captured post-Continue active HUD, not null or the old seed');
});

test('Continue seed rejects missing, duplicated, or off-position pause labels before any click',async()=>{
  const variants=[
    [row('Continue Challenge',800,400,300,40)],
    [...pauseRows(),row('Continue Challenge',800,400,300,40)],
    [row('Continue Challenge',1000,400,300,40),row('Leave Domain?',800,650,300,40)],
    [row('Continue Challenge',800,400,300,40),row('Leave Domain?',1100,650,300,40)],
    [...pauseRows(),row('Auto',100,100,50,20)],
  ];
  for(const variant of variants) {
    const f=fixture(variant),seed=await f.observe();
    const req={session:'s',id:'bad-continue',createdAt:f.now(),expectedFrameId:seed.frameId,mission:'questStep',step:'wolfContinue'};
    assert.equal(await f.runner.process(req,()=>f.mission,seed),'rejected');assert.deepEqual(f.clicks,[]);assert.deepEqual(f.keys,[]);
  }
});

test('adapter seed binding checks focus and same-session entry before Continue input',async()=>{
  const f=fixture(pauseRows()),seed=await f.observe(),req={session:'s',id:'focus-loss',createdAt:f.now(),expectedFrameId:seed.frameId,mission:'questStep',step:'wolfContinue'};
  f.context.genshin.isGameForeground=false;
  await assert.rejects(f.runner.process(req,()=>f.mission,seed),/foreground/);assert.deepEqual(f.clicks,[]);
  const g=fixture(pauseRows()),other=await g.observe();g.files.set('reports/s.json',JSON.stringify([]));
  const r={session:'s',id:'no-entry',createdAt:g.now(),expectedFrameId:other.frameId,mission:'questStep',step:'wolfContinue'};
  await assert.rejects(g.runner.process(r,()=>g.mission,other),/entry required/);assert.deepEqual(g.clicks,[]);
});

test('real main refreshes an aged pause once, then reuses the single post-Continue active capture',async()=>{
  let now=3000000,scene='pause',rows=pauseRows(),externalSent=false,stopSent=false,session=null,sleepCalls=0;
  const files=new Map(),sources={'engine.js':engineSource,'bgi.js':bgiSource,'mission.js':missionSource,'main.js':mainSource,
    'combat.js':fs.readFileSync(path.join(root,'combat.js'),'utf8'),'recovery.js':fs.readFileSync(path.join(root,'recovery.js'),'utf8')};
  const timeline=[],captures={pause:0,domain:0};
  const entry={session:'SESSION',id:'old-resume',mission:'questStep',status:'completed',timestamp:2900000,frameId:0,
    details:{result:{step:'wolfResume',verified:true,fromSession:'older',toSession:'SESSION',priorEntryId:'old-entry',priorPauseId:'old-pause',
      betterGiProcessId:1234,rdpSessionId:7,gameProcessId:5678,verifiedAt:2899000},
      inputEvents:[{type:'wolfResumeProof',verified:true,fromSession:'older',toSession:'SESSION',priorEntryId:'old-entry',priorPauseId:'old-pause',
        betterGiProcessId:1234,rdpSessionId:7,gameProcessId:5678,verifiedAt:2899000,recordedAt:2899900}]}};
  function write(p,v,append) {
    if(p==='controller-status.json') {
      const status=JSON.parse(v);session=status.session;
      if(status.state==='starting'&&!files.has('reports/'+session+'.jsonl')) {
        const currentEntry=JSON.parse(JSON.stringify(entry));currentEntry.session=session;
        currentEntry.details.result.toSession=session;currentEntry.details.inputEvents[0].toSession=session;
        const pause={session,id:'old-pause',mission:'questStep',status:'completed',timestamp:2990000,frameId:0,
          details:{result:{step:'wolfPause',pauseVerified:true},inputEvents:[{type:'key',key:'VK_ESCAPE',startedAt:2989900}]}};
        const seeded=JSON.stringify([currentEntry,pause]);
        files.set('reports/'+session+'.json',seeded);
        files.set('reports/'+session+'.jsonl',JSON.stringify(currentEntry)+'\n'+JSON.stringify(pause)+'\n');
        files.set('receipts/'+session+'/old-resume.json',JSON.stringify(currentEntry));
        files.set('receipts/'+session+'/old-pause.json',JSON.stringify(pause));
      }
    }
    if(p==='reports/'+session+'.json'&&!append) {
      const fresh=JSON.parse(v),prior=JSON.parse(files.get(p)||'[]');
      const ids=new Set(fresh.map(r=>r.id));
      files.set(p,JSON.stringify(prior.filter(r=>!ids.has(r.id)).concat(fresh)));
      return true;
    }
    files.set(p,append?(files.get(p)||'')+v:v);return true;
  }
  const activeRows=()=>[row('Kaeya',1663,487,70,30),row('Trial',1796,463,60,30),row('1000/1427',910,1000,100,20),row('E',1700,1015,30,20)];
  const context={Date:class extends Date{static now(){return now;}},Math,Number,JSON,Object,Error,RegExp,Array,String,
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,betterGiProcessId:1234,width:1920,height:1080,
      focusGame:async()=>{},getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    settings:{enableInput:true},dispatcher:{clearAllTriggers(){}},getGameMetrics:()=>[1920,1080,1],setGameMetrics(){},
    log:{info(){}},RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}
      findMulti(){const a=(this.mat.rows||[]).map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},
      ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x,contourArea:()=>0}}},
    captureGameRegion:()=>{const captured=rows.slice(),mode=scene;captures[mode]++;timeline.push('capture:'+mode);
      return {width:1920,height:1080,srcMat:{},findMulti:()=>{const a=captured.map(r=>({...r}));a.count=a.length;return a;},
        deriveCrop:()=>({srcMat:{resize:()=>({rows:[]}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}}),dispose(){}};},
    keyDown:k=>{if(k==='VK_ESCAPE'&&scene==='domain'){scene='pause';rows=pauseRows();}},keyUp(){},moveMouseBy:(x,y)=>timeline.push('rotate:'+x+','+y),click:(x,y)=>{timeline.push('click:'+x+','+y);
      if(scene==='pause'){scene='domain';rows=activeRows();}},
    file:{captureStorageVersion:1,pinCaptureEvidence:()=>{},isExists:p=>files.has(p),readTextSync:p=>sources[p]??files.get(p),writeTextSync:write,createDirectory:()=>true,writeImageSync:()=>true},
    sleep:async ms=>{if(++sleepCalls>100)throw new Error('integration watchdog: '+JSON.stringify({state:files.get('controller-status.json'),request:files.get('request.json'),timeline}));now+=ms;
      const status=files.get('controller-status.json')&&JSON.parse(files.get('controller-status.json'));
      if(status&&status.state==='idle'&&!externalSent) {
        now+=1500;
        const observation=JSON.parse(files.get('observation.json'));
        write('request.json',JSON.stringify({id:'authorized-aim',session,createdAt:now,expectedFrameId:observation.frameId,mission:'questStep',step:'wolfAimCryo'}));
        externalSent=true;
      } else if(status&&status.state==='idle'&&externalSent&&!stopSent&&
          (files.has('receipts/'+session+'/authorized-aim.json')||String(files.get('reports/'+session+'.jsonl')||'').split(/\r?\n/).some(line=>{
            try {const r=JSON.parse(line);return r.id==='authorized-aim'&&['completed','stopped','rejected'].includes(r.status);}catch(_){return false;}
          }))) {
        const observation=JSON.parse(files.get('observation.json'));
        write('request.json',JSON.stringify({id:'stop-test',session,createdAt:now,expectedFrameId:observation.frameId,mission:'stop'}));stopSent=true;
      }
    }};
  let failure=null;
  try { await vm.runInNewContext(mainSource,context); } catch(e) { failure=e; }
  assert.equal(failure,null,failure&&failure.stack);
  assert.equal(externalSent,true);assert.equal(stopSent,true);
  assert.equal(captures.pause,3,'startup pause, one fresh pre-Continue refresh, and one post-action safety pause');
  assert.equal(captures.domain,2,JSON.stringify({timeline,captures,log:files.get('reports/'+session+'.jsonl'),request:files.get('request.json'),states:files.get('controller-status.json')}));
  const clickIndex=timeline.indexOf('click:950,420'),activeCaptureIndex=timeline.indexOf('capture:domain'),rotateIndex=timeline.indexOf('rotate:250,0');
  assert.ok(clickIndex>=0&&activeCaptureIndex>clickIndex&&rotateIndex>activeCaptureIndex);
  assert.equal(timeline.slice(0,clickIndex).filter(x=>x==='capture:pause').length,2,
    'only one additional capture occurs while paused before Continue');
  assert.equal(timeline.slice(activeCaptureIndex+1,rotateIndex).filter(x=>x==='capture:domain').length,0,
    'the next authorized action consumes the seeded active frame without another fresh capture');
  const history=files.get('reports/'+session+'.jsonl').split(/\r?\n/).filter(Boolean).map(JSON.parse);
  assert.ok(history.some(r=>r.id&&r.id.indexOf('idle-safety-wolfContinue-')===0&&r.status==='completed'&&
    r.details.inputEvents.some(e=>e.type==='wolfContinue')));
  assert.ok(history.some(r=>r.id==='authorized-aim'&&r.status==='stopped'&&r.details.result.step==='wolfAimCryo'&&r.details.result.skillAttempts===1),JSON.stringify(history));
});
