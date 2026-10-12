const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
global.ActOneCombat=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/combat.js');

const row=(text,x,y,width,height)=>({text,x,y,width,height});
const packageDir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');

function cryoTutorialAdapter({entrySession='wolf'}={}) {
  let clock=2000000;const clicks=[];
  const rows=[row("Kaeya's Cryo skill can freeze the surface of water, creating a safe passage",417,780,1081,43),row('across.',906,826,103,23)];
  const party={session:entrySession,mission:'questStep',status:'completed',details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[
    {type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:684,x:1705,y:1019,startedAt:1999900}
  ]}};
  const context={Date:class extends Date{static now(){return clock;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:()=>false,readTextSync:p=>p==='reports/wolf.json'?JSON.stringify([party]):fs.readFileSync(path.join(packageDir,p),'utf8'),
      writeTextSync:()=>true,writeImageSync:()=>true},RecognitionObject:{Ocr:()=>({})},
    ImageRegion:class{constructor(){this.width=1920;this.height=1080;}findMulti(){const found=rows.map(r=>({...r}));found.count=found.length;return found;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},
      ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x,contourArea:()=>0}}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const found=rows.map(r=>({...r}));found.count=found.length;return found;},
      deriveCrop:()=>({srcMat:{resize:()=>({rows:[]}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}}),dispose(){}}),
    sleep:async ms=>{clock+=ms;},click:(x,y)=>clicks.push([x,y]),keyDown(){},keyUp(){},moveMouseBy(){},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);adapter.beginMission({mission:'recover',session:'wolf',createdAt:1999800});
  return {adapter,clicks,observe:()=>adapter.observe('wolf',693)};
}

test('recorded underwater-spikes tutorial row is recognized only at its exact measured location and safe state',()=>{
  const caption='Underwater spikes make the area too dangerous to swim through';
  const recorded=row(caption,479,782,953,40);
  const observation={timestamp:2000000,frameId:685,map:null,ocr:[recorded],hud:{world:false,groundControls:false,climbing:false,
    auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,tutorialStep:'wolfInfo',loading:false,unknownHud:false,
    objectiveChanged:false,health:{current:471,max:1427}}};
  assert.equal(bgi.wolfInfoKind([recorded]),'underwaterSpikes');
  assert.equal(bgi.wolfInfoState(observation,2000000),true);
  assert.equal(bgi.wolfInfoKind([row(caption+'.',479,782,953,40)]),'underwaterSpikes','a terminal period is accepted');
  for(const bad of [
    row(caption+'!',479,782,953,40),row(caption,420,782,953,40),row(caption,479,782,850,40),
    row(caption,479,782,953,55),row(caption+' Also swim carefully',479,782,953,40)
  ]) assert.equal(bgi.wolfInfoKind([bad]),null);
  for(const patch of [{groundControls:true},{climbing:true},{auto:true},{loading:true},{unknownHud:true},{objectiveChanged:true}])
    assert.equal(bgi.wolfInfoState({...observation,hud:{...observation.hud,...patch}},2000000),false);
  assert.equal(bgi.wolfInfoState({...observation,timestamp:1998999},2000000),false);
});

test('recorded Cryo water-passage tutorial requires exact rows and permits the safe frozen HUD with unreadable HP',()=>{
  const first=row("Kaeya's Cryo skill can freeze the surface of water, creating a safe passage",417,780,1081,43);
  const second=row('across.',906,826,103,23);
  const observation={timestamp:2000000,frameId:688,map:null,ocr:[first,second],hud:{world:false,groundControls:true,climbing:false,
    auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,tutorialStep:'wolfInfo',
    objectiveChanged:false,health:{current:471,max:1427}}};
  assert.equal(Object.hasOwn(observation.hud,'loading'),false);
  assert.equal(Object.hasOwn(observation.hud,'unknownHud'),false);
  assert.equal(bgi.wolfInfoKind([first,second]),'cryoWaterPassage');
  assert.equal(bgi.wolfInfoState(observation,2000000),true);
  assert.equal(bgi.wolfInfoState({...observation,hud:{...observation.hud,groundControls:false}},2000000),true,
    'the recorded tutorial may be recognized with either grounded-control reading');
  for(const rows of [
    [first],[second],[first,second,{...second}],
    [first,row('across.',850,826,103,23)],[row(first.text,360,780,1081,43),second],
    [row(first.text,417,780,1000,43),second],[first,row('across.',906,826,140,23)],
    [{...first,text:first.text+'!'},second],[first,second,first]
  ]) assert.equal(bgi.wolfInfoKind(rows),null,JSON.stringify(rows));
  for(const patch of [{world:true},{journal:true},{bigMap:true},{dialogueReady:true},{choice:true},{auto:true},{climbing:true},
    {loading:true},{unknownHud:true},{objectiveChanged:true},{tutorialStep:null},
    {health:{current:0,max:1427}},{groundControls:undefined}])
    assert.equal(bgi.wolfInfoState({...observation,hud:{...observation.hud,...patch}},2000000),false);
  assert.equal(bgi.wolfInfoState({...observation,hud:{...observation.hud,loading:false,unknownHud:false}},2000000),true);
  assert.equal(bgi.wolfInfoState({...observation,timestamp:1998999},2000000),false);
  const frozen={...observation,frameId:693,hud:{...observation.hud,groundControls:false,health:null}};
  assert.equal(bgi.wolfInfoState(frozen,2000000),true,'the actual frame-693 OCR retry had no readable health row');
  assert.equal(bgi.wolfInfoState({...frozen,hud:{...frozen.hud,groundControls:true}},2000000),false);
  assert.equal(bgi.wolfInfoState({...frozen,hud:{...frozen.hud,unknownHud:true}},2000000),false);
  assert.equal(bgi.wolfInfoState({...frozen,hud:{...frozen.hud,loading:true}},2000000),false);
});

test('frame-693 unreadable HP is accepted only through same-session Wolf-entry recovery authorization',async()=>{
  const matching=cryoTutorialAdapter(),actual=await matching.observe();
  assert.equal(actual.hud.health,null);
  assert.equal(actual.hud.groundControls,false);
  assert.equal(Object.hasOwn(actual.hud,'loading'),false);
  assert.equal(Object.hasOwn(actual.hud,'unknownHud'),false);
  assert.equal(matching.adapter.wolfInfoReady(),true);
  matching.adapter.recoverWolfInfo();
  assert.deepEqual(matching.clicks,[[960,900]]);

  const foreign=cryoTutorialAdapter({entrySession:'other-session'}),wrong=await foreign.observe();
  assert.equal(bgi.wolfInfoState(wrong,2000000),true,'caption state alone does not establish session entry');
  assert.equal(foreign.adapter.wolfInfoReady(),false);
  assert.throws(()=>foreign.adapter.recoverWolfInfo(),/Same-session Wolf entry required/);
  assert.deepEqual(foreign.clicks,[]);
  assert.equal(bgi.wolfInfoState({...actual,timestamp:1998999},2000000),false);
});

test('cooldown OCR accepts only one measured E-circle value; ambiguity uses the full fallback',()=>{
  const strictHud={world:false,groundControls:true,climbing:false,journal:false,bigMap:false,auto:false,objectiveChanged:false,
    dialogueReady:false,choice:false,tutorialStep:null,interact:false,health:{current:471,max:1427},enemyBars:[],
    enemyBarDiagnostic:{level:5,candidates:0,localReads:[]}};
  const base={timestamp:2000000,map:null,hud:strictHud,ocr:[]};
  const cooldown=row('0.9',1680,981,37,23);
  assert.equal(bgi.wolfCryoCooldownRemaining({...base,ocr:[cooldown]}),0.9);
  for(const rows of [[],[cooldown,{...cooldown}], [row('0.9',1650,981,37,23)], [row('0.9',1680,960,37,23)],
    [row('0.9',1680,981,55,23)], [row('09',1680,981,37,23)], [row('0.0',1680,981,37,23)],
    [row('6.1',1680,981,37,23)], [row('?',1680,981,37,23)]])
    assert.equal(bgi.wolfCryoCooldownRemaining({...base,ocr:rows}),null,JSON.stringify(rows));
});

const entry=[
  {session:'wolf',mission:'questStep',status:'completed',timestamp:1000,details:{result:{step:'wolfStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[{type:'wolfDomainStart',label:'Deep Within the Temple of the Wolf',startedAt:900}]}},
  {session:'wolf',mission:'questStep',status:'completed',timestamp:1500,details:{result:{step:'wolfPartyStart'},inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:2,x:1700,y:1019,startedAt:1400}]}}
];

function cryoAdapterFixture({cooldown='0.9',focus=true,loseFocusAfterContinue=false,stop=false,throwKey=null,health='471/1427',journal=false,wrongSession=false,duplicate=false,unsafeBars=false}={}) {
  let now=3000000,frame=0,phase='pause',foreground=focus,stopRequested=stop,healthText=health,activeRowsSeen=0;
  const keys=[],clicks=[],observations=[];let cooldownRows=cooldown===null?[]:Array.isArray(cooldown)?cooldown.map(x=>row(x,1680,981,37,23)):[row(cooldown,1680,981,37,23)];
  const rows=()=>phase==='pause'?[row('Continue Challenge',831,399,287,40),row('Lower Difficulty',849,518,251,42),row('Leave Domain?',864,640,221,36)]:[
    row('Kaeya',1664,485,90,38),row('Trial',1802,463,43,22),row(healthText,910,1002,100,18),row('E',1689,1028,20,20),
    ...cooldownRows,...(journal?[row('In Progress',40,80,100,22)]:[])];
  const rootPath=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:foreground,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='stop.json'&&stopRequested,readTextSync:p=>p==='stop.json'?JSON.stringify({session:'wolf',createdAt:2900000}):p==='reports/wolf.json'?JSON.stringify(entry):fs.readFileSync(path.join(rootPath,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x},ColorConversionCodes:{GRAY2BGR:0}}},
    ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const a=(this.mat.rows||[]).map(x=>({...x}));a.count=a.length;return a;}dispose(){}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows().map(x=>({...x}));a.count=a.length;return a;},deriveCrop:(x,y)=>{
      if(x===1520&&y===985)return {srcMat:{resize:()=>({rows:phase==='pause'?[]:[row('E',840,110,40,30)]})},dispose(){}};
      if(x===1630&&y===330)return {srcMat:{resize:()=>({rows:phase==='pause'?[]:[row('Kaeya',100,450),row('Trial',500,400)]})},dispose(){}};
      if(x===900&&y===990)return {srcMat:{resize:()=>({rows:phase==='pause'?[]:[row(healthText,20,20,250,45)]})},dispose(){}};
      if(x===350&&y===100)return {srcMat:{inRange:()=>({findContoursAsArray:()=>phase!=='pause'&&unsafeBars?[{x:550,y:360,width:90,height:8}]:[],cvtColor:()=>({resize:()=>({rows:[]}),dispose(){}}),dispose(){}})},dispose(){}};
      if(x===893&&y===998||x===967&&y===998)return {srcMat:{resize:()=>({rows:[]})},dispose(){}};
      return {srcMat:{resize:()=>({rows:[]}),inRange:()=>({findContoursAsArray:()=>[],cvtColor:()=>({resize:()=>({rows:[]}),dispose(){}}),dispose(){}})},dispose(){}};
    },dispose(){}}),
    keyDown:key=>{keys.push(['down',key,now]);if(key===throwKey)throw new Error('test keyDown failure');if(key==='VK_ESCAPE')phase='pause';},
    keyUp:key=>keys.push(['up',key,now]),click:(x,y)=>{clicks.push([x,y]);phase='active';if(loseFocusAfterContinue){foreground=false;context.genshin.isGameForeground=false;}},moveMouseBy(){},
    sleep:async ms=>{now+=ms;},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(rootPath,'bgi.js'),'utf8'),context);
  const api=context.createActOneAdapter(7);api.beginMission({mission:'questStep',step:'wolfCryoWait',session:'wolf',createdAt:2900000});
  async function observe(){if(!duplicate)frame++;else if(frame===0)frame++;if(phase==='active')activeRowsSeen++;
    const o=await api.observe(wrongSession&&activeRowsSeen>0?'wrong':'wolf',frame);observations.push({observation:o,keysAtCapture:keys.map(x=>x.slice(0,2))});return o;}
  return {api,observe,keys,clicks,observations,setFocus:v=>{foreground=v;context.genshin.isGameForeground=v;},setHealth:v=>{healthText=v;},setStop:v=>{stopRequested=v;},get activeRowsSeen(){return activeRowsSeen;}};
}

test('wolfCryoWait uses one Continue, a bounded active-time cooldown, one released E, and verifies canonical pause',async()=>{
  const h=cryoAdapterFixture(),initial=await h.observe();
  assert.equal(initial.hud.health,null);assert.equal(h.api.wolfCryoWaitContinueReady(initial),true);
  const result=await mission.runQuestStep('wolfCryoWait',initial,h.api,h.observe);
  assert.equal(result.continueAttempts,1);assert.equal(result.skillAttempted,true);assert.equal(result.targetEffectVerified,false);
  assert.equal(result.questComplete,false);assert.equal(result.pauseVerified,true);assert.equal(result.cooldownSource,'capturedRemaining');
  assert.equal(result.capturedRemainingSeconds,0.9);assert.equal(result.cooldownWaitMs,1200);assert.equal(result.cooldownElapsedMs,1200);
  assert.equal(h.clicks.length,1);assert.deepEqual(h.keys.map(x=>x.slice(0,2)),[['down','VK_E'],['up','VK_E'],['down','VK_ESCAPE'],['up','VK_ESCAPE']]);
  assert.ok(result.captureCount>=3);assert.ok(result.captureMs>=0);
  const active=h.api.events().filter(e=>e.type==='wolfCryoWaitSkill');assert.equal(active.length,1);
  assert.ok(h.activeRowsSeen>=3,'active OCR was actually captured and parsed by the adapter');
});

test('wolfCryoWait rejects unsafe, wrong-session, duplicate, focus-loss, and cancelled observations before E',async()=>{
  for(const options of [{unsafeBars:true},{wrongSession:true},{duplicate:true},{loseFocusAfterContinue:true},{stop:true},{journal:true}]){
    const h=cryoAdapterFixture(options.stop?{}:options),initial=await h.observe();if(options.stop)h.setStop(true);
    const result=await mission.runQuestStep('wolfCryoWait',initial,h.api,h.observe);
    assert.equal(result.skillAttempted,false,JSON.stringify(options));
    assert.equal(result.targetEffectVerified,false);assert.equal(result.questComplete,false);
    assert.equal(h.keys.some(x=>x[0]==='down'&&x[1]==='VK_E'),false,JSON.stringify(options));
    if(options.journal)assert.equal(h.keys.some(x=>x[0]==='down'&&x[1]==='VK_ESCAPE'),false,'unsafe UI cannot authorize Escape');
    if(options.loseFocusAfterContinue||options.stop)assert.equal(h.keys.some(x=>x[0]==='down'&&x[1]==='VK_ESCAPE'),false,'stop condition forbids further input');
    if(options.stop)assert.match(result.reason,/Stop requested/);
    if(options.unsafeBars){
      assert.match(result.reason,/Strict safe grounded Trial Kaeya HUD unavailable/);
      const active=h.observations.filter(x=>x.observation.hud.world===false&&x.observation.hud.health);
      assert.ok(active.length>0,'unsafe case produced actual active HUD observations');
      for(const {observation:o} of active){assert.equal(o.hud.groundControls,true);assert.equal(o.hud.health.max,1427);assert.equal(o.hud.enemyBarDiagnostic.level,5);assert.ok(o.hud.enemyBarDiagnostic.candidates>0);}
      assert.equal(h.keys.filter(x=>x[0]==='down'&&x[1]==='VK_ESCAPE').length,1,'fresh living Trial HUD may be explicitly paused after unsafe detector evidence');
      const continueEvent=h.api.events().find(e=>e.type==='wolfCryoWaitContinue'),escapeEvent=h.api.events().find(e=>e.type==='wolfCryoWaitEscape');
      assert.ok(escapeEvent.frameId>continueEvent.frameId,'unsafe post-Continue HUD is freshly observed before the safe Escape');
    }
  }
});

test('wolfCryoWait releases E after adapter failure and never claims effect or completion',async()=>{
  const h=cryoAdapterFixture({throwKey:'VK_E'}),initial=await h.observe(),result=await mission.runQuestStep('wolfCryoWait',initial,h.api,h.observe);
  assert.equal(result.skillAttempted,true);assert.deepEqual(h.keys.map(x=>x.slice(0,2)),[['down','VK_E'],['up','VK_E'],['down','VK_ESCAPE'],['up','VK_ESCAPE']]);
  assert.equal(result.pauseVerified,true);assert.equal(result.targetEffectVerified,false);assert.equal(result.questComplete,false);
  const skill=h.api.events().find(e=>e.type==='wolfCryoWaitSkill'),escape=h.api.events().find(e=>e.type==='wolfCryoWaitEscape');
  assert.ok(escape.frameId>skill.frameId,'Escape uses a newer frame than the failed E frame');
  const failureCapture=h.observations.find(x=>x.observation.frameId===escape.frameId);
  assert.ok(failureCapture,'a fresh capture is made after failed E before Escape');
  assert.ok(failureCapture.keysAtCapture.some(x=>x[0]==='up'&&x[1]==='VK_E'));
});

test('real adapter uses full fallback for absent or multiple cooldown rows and rejects direct early E',async()=>{
  for(const cooldown of [null,['0.9','0.8']]){
    const h=cryoAdapterFixture({cooldown}),initial=await h.observe();h.api.wolfCryoWaitContinue();
    const active=await h.observe();assert.equal(h.api.wolfCryoWaitActiveReady(active),true);
    const plan=h.api.wolfCryoWaitCooldownPlan(active);assert.equal(plan.source,'fixedActiveFallback');assert.equal(plan.waitMs,6500);
    await assert.rejects(()=>h.api.wolfCryoWaitCast(),/selected active-time cooldown plan/);
    assert.equal(h.keys.some(x=>x[0]==='down'&&x[1]==='VK_E'),false);
  }
  const early=cryoAdapterFixture(),initial=await early.observe();early.api.wolfCryoWaitContinue();const active=await early.observe();
  assert.equal(early.api.wolfCryoWaitActiveReady(active),true);early.api.wolfCryoWaitCooldownPlan(active);
  await assert.rejects(()=>early.api.wolfCryoWaitCast(),/selected active-time cooldown plan/);
  assert.equal(early.keys.some(x=>x[0]==='down'&&x[1]==='VK_E'),false);
});

test('real adapter enforces health-loss budget and captures the invoked level-five enemy detector',async()=>{
  const h=cryoAdapterFixture(),initial=await h.observe();h.api.wolfCryoWaitContinue();let active=await h.observe();
  assert.equal(active.hud.enemyBarDiagnostic.level,5);assert.equal(active.hud.enemyBarDiagnostic.candidates,0);assert.deepEqual(Array.from(active.hud.enemyBarDiagnostic.localReads),[]);
  assert.equal(h.api.wolfCryoWaitActiveReady(active),true);h.api.wolfCryoWaitCooldownPlan(active);h.setHealth('390/1427');
  active=await h.observe();assert.equal(h.api.wolfCryoWaitActiveReady(active),false);
  assert.equal(h.api.wolfCryoWaitPauseReady(active),true,'Escape uses the fresh living-Trial pause guard after a health-budget abort');
  assert.equal(h.keys.some(x=>x[0]==='down'&&(x[1]==='VK_E'||x[1]==='VK_ESCAPE')),false);
});
