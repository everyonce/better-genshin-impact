const test = require('node:test');
const assert = require('node:assert/strict');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

function row(text, x, y, width = 100, height = 30) { return { text, x, y, width, height }; }
function wolfEntrance(patch = {}) {
  return {
    timestamp: 1000, frameId: 1519, map: null,
    ocr: [
      row('Domain Entrance', 137, 30),
      row('Deep Within the Temple of the Wolf', 52, 157, 390, 30),
      row('Recommended Party Level: 5', 56, 206, 290, 30),
      row('Deep Within the Temple of the Wolf', 1274, 149, 469, 29),
      row('Start', 1688, 999, 85, 36),
    ],
    hud: { world: false, journal: false, bigMap: false, dialogueReady: false, choice: false, tutorialStep: null },
    ...patch,
  };
}

function wolfPartyFrame(patch = {}) {
  return {
    session: 'same-session', timestamp: 2000000, frameId: 5, map: null,
    ocr: [row('Party Setup', 113, 27, 161, 40), row('Lumina', 387, 293, 141, 40),
      row('Amber', 737, 329, 111, 34), row('Team Standing By', 122, 1007, 257, 28), row('Start', 1662, 1001, 85, 36)],
    hud: { world: false, journal: false, bigMap: false, dialogueReady: false, choice: false },
    ...patch,
  };
}
function recordedWolfEntry() {
  return {session:'same-session',mission:'questStep',status:'completed',timestamp:1000000,
    details:{result:{step:'wolfStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[
      {type:'controllerRevision',startedAt:999000},
      {type:'wolfDomainStart',label:'Deep Within the Temple of the Wolf',frameId:4,x:1731,y:1017,startedAt:999100},
    ]}};
}

test('Wolf party target accepts frame-5 OCR with recorded same-session Wolf entrance and later revision metadata', () => {
  const revision = {session:'same-session',mission:'observe',status:'completed',timestamp:1000100,
    details:{result:{},inputEvents:[{type:'controllerRevision',startedAt:1000050}]}};
  assert.deepEqual(bgi.wolfPartyTarget(wolfPartyFrame(), 2000000, [recordedWolfEntry(), revision], 'same-session'), {x:1705,y:1019});
});

test('Wolf party target rejects wrong temple, other session, missing Wolf input proof, and any later state input', () => {
  const entry = recordedWolfEntry();
  const wrongTemple = structuredClone(entry);
  wrongTemple.details.result.label = 'Deep Within the Temple of the Falcon';
  const noInput = structuredClone(entry);
  noInput.details.inputEvents = [{type:'controllerRevision',startedAt:999000}];
  const laterInput = {session:'same-session',mission:'observe',status:'completed',timestamp:1000100,
    details:{result:{},inputEvents:[{type:'key',key:'VK_ESCAPE',startedAt:1000050}]}};
  assert.equal(bgi.wolfPartyTarget(wolfPartyFrame(), 2000000, [wrongTemple], 'same-session'), null);
  assert.equal(bgi.wolfPartyTarget(wolfPartyFrame(), 2000000, [entry], 'other-session'), null);
  assert.equal(bgi.wolfPartyTarget(wolfPartyFrame(), 2000000, [noInput], 'same-session'), null);
  assert.equal(bgi.wolfPartyTarget(wolfPartyFrame(), 2000000, [entry, laterInput], 'same-session'), null);
});

test('wolfPartyStart delegates one click, waits, then captures a fresh frame', async () => {
  let now = 2000000, clicks = 0, observes = 0;
  const calls = [];
  const api = {now:()=>now, checkStop:()=>calls.push('check'), startWolfParty:()=>{clicks++;calls.push('click');},
    sleep:async ms=>{calls.push(['sleep',ms]);now+=ms;}};
  const result = await mission.runQuestStep('wolfPartyStart', wolfPartyFrame(), api, async()=>{
    observes++;calls.push('observe');return {frameId:6};
  });
  assert.equal(result.status,'completed');
  assert.equal(result.step,'wolfPartyStart');
  assert.equal(result.clicks,1);
  assert.equal(clicks,1);
  assert.equal(observes,1);
  assert.deepEqual(calls,['check','click',['sleep',800],'observe']);
});

test('Wolf entrance target accepts only exact selected Wolf level-5 screen', () => {
  assert.deepEqual(bgi.templeStartTarget(wolfEntrance(), 1500, 'Wolf'), {
    x: 1731, y: 1017, label: 'Deep Within the Temple of the Wolf',
  });
  const base = wolfEntrance();
  const wrongTitle = base.ocr.map(r => r.x === 1274 ? { ...r, text: 'Deep Within the Temple of the Falcon' } : r);
  const wrongLevel = base.ocr.map(r => r.text === 'Recommended Party Level: 5' ? { ...r, text: 'Recommended Party Level: 25' } : r);
  const badScreens = [
    { ...base, timestamp: 499 },
    { ...base, timestamp: 1501 },
    { ...base, map: { map: 'Teyvat', x: 0, y: 0 } },
    { ...base, hud: { ...base.hud, journal: true } },
    { ...base, hud: { ...base.hud, bigMap: true } },
    { ...base, hud: { ...base.hud, dialogueReady: true } },
    { ...base, ocr: wrongTitle },
    { ...base, ocr: wrongLevel },
    { ...base, ocr: [...base.ocr, row('Start', 1700, 1000)] },
  ];
  for (const bad of badScreens) assert.equal(bgi.templeStartTarget(bad, 1500, 'Wolf'), null);
  assert.equal(bgi.templeStartTarget(base, 1500, 'Falcon'), null);
  assert.equal(bgi.templeStartTarget(base, 1500, 'Lion'), null);
});

test('wolfStart clicks once, waits, then captures a new frame', async () => {
  let now = 1000, clicks = 0, observes = 0;
  const calls = [];
  const api = {
    now: () => now,
    startWolfDomain: () => { clicks++; calls.push('click'); return 'Deep Within the Temple of the Wolf'; },
    sleep: async ms => { calls.push(['sleep', ms]); now += ms; },
  };
  const result = await mission.runQuestStep('wolfStart', wolfEntrance(), api, async () => {
    observes++; calls.push('observe'); return { frameId: 1520 };
  });
  assert.equal(result.status, 'completed');
  assert.equal(result.step, 'wolfStart');
  assert.equal(result.label, 'Deep Within the Temple of the Wolf');
  assert.equal(clicks, 1);
  assert.equal(observes, 1);
  assert.deepEqual(calls, ['click', ['sleep', 800], 'observe']);
});

function doorFrame(frameId, aligned) {
  const fY = aligned ? 520 : 450;
  return {
    timestamp: 1000 + frameId, frameId, map: { map: 'Teyvat', x: -1642.421, y: 2163.664 },
    ocr: [row('Kaeya', 1200, fY), row('F', 1095, fY), row('Temple of the Wolf', 1200, aligned ? 520 : 540)],
    hud: { world: true, objectives: ['Enter the temple'], dialogueReady: false, choice: false, climbing: false },
  };
}

test('wolfDoorInteract observes after scrolling before F interaction and stays within two attempts', async () => {
  let now = 1000, index = 0;
  const calls = [], actions = [];
  const frames = [doorFrame(1, false), doorFrame(2, true)];
  const api = {
    now: () => now,
    wolfDoorAction: async () => { const action = actions.length === 0 ? 'scroll' : 'interact'; actions.push(action); calls.push(action); return action; },
    sleep: async ms => { calls.push(['sleep', ms]); now += ms; },
  };
  const result = await mission.runQuestStep('wolfDoorInteract', frames[0], api, async () => {
    const next = frames[Math.min(index++, frames.length - 1)]; calls.push(`observe-${next.frameId}`); return next;
  });
  assert.equal(result.status, 'completed');
  assert.equal(result.step, 'wolfDoorInteract');
  assert.equal(result.frameId, 2);
  assert.deepEqual(calls, ['scroll', ['sleep', 400], 'observe-1', 'interact', ['sleep', 1000], 'observe-2']);
  assert.equal(actions.length, 2);
});

test('wolfDoorInteract stops after two unresolved attempts and after an action exception', async () => {
  let now = 1000, attempts = 0, observations = 0;
  const noSettle = await mission.runQuestStep('wolfDoorInteract', doorFrame(1, false), {
    now: () => now,
    wolfDoorAction: async () => { attempts++; return 'scroll'; },
    sleep: async ms => { now += ms; },
  }, async () => { observations++; return doorFrame(observations + 1, false); });
  assert.equal(noSettle.status, 'stopped');
  assert.equal(attempts, 2);
  assert.equal(observations, 2);

  attempts = 0;
  await assert.rejects(() => mission.runQuestStep('wolfDoorInteract', doorFrame(1, false), {
    now: () => now,
    wolfDoorAction: async () => { attempts++; throw new Error('Unsafe/ambiguous row'); },
    sleep: async () => {},
  }, async () => { throw new Error('must not observe after failed action'); }), /Unsafe\/ambiguous row/);
  assert.equal(attempts, 1);
});


test('live adapter reads complete JSONL history, preserves observation session, and blocks historical intervening input', async () => {
  const fs=require('node:fs'), path=require('node:path'), vm=require('node:vm');
  const packageDir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
  const source=fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8');
  async function exercise(intervening) {
    const clicks=[], reads=[], rows=wolfPartyFrame().ocr;
    const records=[recordedWolfEntry(),{session:'same-session',mission:'questStep',status:'started',timestamp:2000000,details:null}];
    if(intervening)records.splice(1,0,{session:'same-session',mission:'keyPress',status:'completed',timestamp:1500000,details:{inputEvents:[{type:'key',key:'VK_ESCAPE',startedAt:1500000}]}});
    const context={Date:class extends Date{static now(){return 2000000;}},
      genshin:{isRemoteDesktopSession:true,windowsSessionId:5,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
      file:{isExists:()=>false,readTextSync:p=>{reads.push(p);if(p.endsWith('.jsonl'))return records.map(x=>JSON.stringify(x)).join('\n');if(p.startsWith('reports/'))throw Error('rolling history must not be used');const full=path.join(packageDir,p);return fs.existsSync(full)?fs.readFileSync(full,'utf8'):'';},writeTextSync:()=>true,writeImageSync:()=>true},
      RecognitionObject:{Ocr:()=>({})},
      ImageRegion:class{constructor(){this.width=1920;this.height=1080;this.findMulti=()=>{const a=[];a.count=0;return a;};}dispose(){}},
      OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}}}},
      captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows.map(r=>({...r}));a.count=a.length;return a;},deriveCrop:()=>({srcMat:{resize:()=>({})},dispose(){}}),dispose(){}}),
      sleep:async()=>{},click:(x,y)=>clicks.push([x,y]),log:{info(){}}};
    vm.runInNewContext(source,context);
    const adapter=context.createActOneAdapter(5);
    adapter.beginMission({mission:'questStep',step:'wolfPartyStart',session:'same-session',createdAt:2000000});
    await adapter.observe('same-session',6);
    if(intervening)assert.throws(()=>adapter.startWolfParty(),/uninterrupted/);else adapter.startWolfParty();
    assert.ok(reads.includes('reports/same-session.jsonl'));
    assert.deepEqual(clicks,intervening?[]:[[1705,1019]]);
  }
  await exercise(false); await exercise(true);
});

test('real adapter and engine preserve the validated Wolf label in the completed party receipt',async()=>{
  const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
  const packageDir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
  const source=fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8'),files=new Map(),clicks=[];
  let now=2000000;
  const context={Date:class extends Date{static now(){return now;}},genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,
      getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>files.has(p),readTextSync:p=>files.has(p)?files.get(p):fs.readFileSync(path.join(packageDir,p),'utf8'),
      pinCaptureEvidence:()=>{},writeTextSync:(p,v,append)=>{files.set(p,append?(files.get(p)||'')+v:v);return true;},writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}
      findMulti(){const a=(this.mat.rows||[]).map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},
      ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x,contourArea:()=>0}}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=wolfPartyFrame().ocr.map(r=>({...r}));a.count=a.length;return a;},
      deriveCrop:()=>({srcMat:{resize:()=>({rows:[]}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}}),dispose(){}}),
    sleep:async ms=>{now+=ms;},click:(x,y)=>clicks.push([x,y]),keyDown(){},keyUp(){},moveMouseBy(){},log:{info(){}}};
  vm.runInNewContext(source,context);
  const adapter=context.createActOneAdapter(7),runner=require(path.join(packageDir,'engine.js')).create(adapter,{session:'same-session',enableInput:true});
  const startAt=1999400;
  runner.report({session:'same-session',id:'verified-wolf-start',mission:'questStep'},'completed',{result:{step:'wolfStart',label:'Deep Within the Temple of the Wolf'},
    inputEvents:[{type:'wolfDomainStart',label:'Deep Within the Temple of the Wolf',frameId:4,x:1731,y:1017,startedAt:startAt}]});
  const fresh=await runner.observe();
  const request={session:'same-session',id:'party-start',createdAt:now,expectedFrameId:fresh.frameId,mission:'questStep',step:'wolfPartyStart'};
  const processStatus=await runner.process(request,()=>mission);
  assert.equal(processStatus,'completed',JSON.stringify(JSON.parse(files.get('reports/same-session.jsonl').split(/\r?\n/).filter(Boolean).at(-1))));
  assert.deepEqual(clicks,[[1705,1019]]);
  const rows=JSON.parse(files.get('reports/same-session.json'));
  const receipt=rows.find(r=>r.id==='party-start'&&r.status==='completed');
  assert.equal(receipt.details.result.step,'wolfPartyStart');
  assert.equal(receipt.details.result.label,undefined,'the mission result stays as emitted; the durable input event carries its verified target');
  assert.equal(receipt.details.inputEvents.find(e=>e.type==='wolfPartyStart').label,'Deep Within the Temple of the Wolf');
  assert.equal(bgi.wolfEntryProven(rows,'same-session'),true);
  const legacy=structuredClone(receipt);legacy.details.inputEvents=legacy.details.inputEvents.map(e=>e.type==='wolfPartyStart'?{...e,label:undefined}:e);
  assert.equal(bgi.wolfEntryProven([rows.find(r=>r.id==='verified-wolf-start'),legacy],'same-session'),false,
    'an unlabeled old party click is not promoted into fresh entry proof');
});


test('Wolf entrance movement requires fresh healthy starter roster and no menu, trial, or dialogue',()=>{
 const o={timestamp:1000,map:null,hud:{world:false,groundControls:true,health:{current:803,max:1055}},ocr:[row('Lumina',1684,349),row('Amber',1664,447)]};
 assert.equal(bgi.wolfEntryHud(o,1000),true);
 for(const patch of [{timestamp:-1},{map:{}},{hud:{...o.hud,dialogueReady:true}},{hud:{...o.hud,health:{current:20,max:1055}}},{ocr:[...o.ocr,row('Trial',1740,550)]}])assert.equal(bgi.wolfEntryHud({...o,...patch},1000),false);
});

test('Wolf approach observes after each bounded move and stops on interaction or health loss',async()=>{
 for(const stop of ['interact','health']) {
 let moves=0,observes=0;
 const initial={frameId:9,hud:{health:{current:803,max:1055}}};
 const next={frameId:10,hud:{health:{current:stop==='health'?600:803,max:1055},interact:stop==='interact'}};
 const r=await mission.runQuestStep('wolfEntryApproach',initial,{wolfEntryForward:async()=>{moves++;},sleep:async()=>{}},async()=>{observes++;return next;});
 assert.equal(moves,1);assert.equal(observes,1);assert.equal(r.status,stop==='health'?'stopped':'completed');
 }
});


test('Wolf opening dialogue observes after Space and stops before any choice',async()=>{
 let presses=0;
 const result=await mission.runQuestStep('wolfOpeningDialogue',{hud:{dialogueReady:true}},{wolfAdvanceDialogue:async()=>{presses++;},sleep:async()=>{}},async()=>({frameId:23,hud:{choice:true}}));
 assert.equal(presses,1);assert.equal(result.status,'stopped');assert.match(result.reason,/choice/);
});


test('Wolf domain movement needs trial Kaeya, fresh controls, numeric safe HP, and no dialog or map',()=>{
 const o={timestamp:1000,map:null,hud:{world:false,groundControls:true,health:{current:1427,max:1427}},ocr:[row('Kaeya',1663,487),row('Trial',1796,463)]};
 assert.equal(bgi.wolfDomainHud(o,1000),true);
 for(const patch of [{timestamp:-1},{map:{}},{hud:{...o.hud,choice:true}},{hud:{...o.hud,health:{current:200,max:1427}}},{ocr:[row('Kaeya',1663,487)]}])assert.equal(bgi.wolfDomainHud({...o,...patch},1000),false);
});


test('Wolf enemy bars require nearby exact level 5, not player or other levels',()=>{
 const bar={x:1000,y:500,width:100,height:8};
 assert.equal(bgi.enemyBarAnchored(bar,[row('Lv. 5',960,470,80,20)],5),true);
 for(const r of [row('Lv. 4',960,470,80,20),row('Lv. 5',760,1000),row('Lv. 6',960,470)])assert.equal(bgi.enemyBarAnchored(bar,[r],5),false);
});
