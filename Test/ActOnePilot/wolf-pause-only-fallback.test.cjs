const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=80,height=25)=>({text,x,y,width,height});
function domain({timestamp=2000000,hp=1427,max=1427,kaeya='Kaeya',trial=true,flags={}}={}) {
  return {session:'wolf',timestamp,frameId:8,map:null,ocr:[...(kaeya?[row(kaeya,1665,489,64,27)]:[]),...(trial?[row('Trial',1802,463,60,30)]:[]),row('E',1778,1005),row('Q',1840,1005),row(`${hp}/${max}`,906,1001,101,20)],
    hud:{world:false,groundControls:true,health:{current:hp,max},journal:false,bigMap:false,dialogueReady:false,choice:false,tutorialStep:null,...flags}};
}
function deadTrialAmber({timestamp=2000000,session='wolf',kaeya=true,amber=true,controls=['R'],flags={}}={}) {
  const rows=[];
  if(amber)rows.push(row('Amber',1664,401,63,25));
  if(kaeya)rows.push(row('Kaeya',1696,486,64,27));
  rows.push(row('633/1055',906,1001,101,20));
  for(const control of controls)rows.push(row(control,control==='R'?1588:control==='E'?1778:1840,1024));
  return {session,timestamp,frameId:26,map:null,ocr:rows,hud:{world:false,groundControls:false,climbing:false,
    health:{current:633,max:1055},journal:false,bigMap:false,dialogueReady:false,choice:false,tutorialStep:null,
    auto:false,loading:false,unknownHud:false,objectiveChanged:false,...flags}};
}
test('strict pause-only predicate accepts only fresh living grounded Trial max-1427 domain frames',()=>{
  const fallback=domain({kaeya:'Kaea'});
  assert.equal(bgi.wolfDomainHud(fallback,2000000),false,'movement still requires exact Kaeya');
  assert.equal(bgi.wolfPauseOnlyHud(fallback,2000000),true);
  for(const bad of [
    domain({timestamp:1998999}),domain({timestamp:2001001}),domain({trial:false}),
    domain({hp:0}),domain({hp:1428}),domain({max:1055}),
    {...fallback,map:{map:'Teyvat',x:0,y:0}},
    {...fallback,ocr:fallback.ocr.map(r=>r.text==='Trial'?{...r,x:1500}:r)},
    ...['groundControls','climbing','journal','bigMap','dialogueReady','choice','tutorialStep','auto','loading','unknownHud'].map(k=>({...fallback,hud:{...fallback.hud,[k]:k==='groundControls'?false:true}}))
  ]) assert.equal(bgi.wolfPauseOnlyHud(bad,2000000),false);
});

test('dead-Trial fallback accepts only same-session living Amber with both party anchors and known bottom controls',()=>{
  const current=deadTrialAmber();
  assert.equal(bgi.wolfDeadTrialPauseOnlyHud(current,2000000,'wolf'),true);
  for(const bad of [
    {...current,session:'other'}, {...current,timestamp:1998999}, {...current,timestamp:2001001},
    {...current,map:{map:'Teyvat',x:0,y:0}}, deadTrialAmber({kaeya:false}),deadTrialAmber({amber:false}),
    deadTrialAmber({controls:[]}),deadTrialAmber({controls:['Space']}),
    ...['world','climbing','journal','bigMap','dialogueReady','choice','tutorialStep','auto','loading','unknownHud','objectiveChanged']
      .map(flag=>({...current,hud:{...current.hud,[flag]:flag==='world'?true:flag==='tutorialStep'?'wolfInfo':true}}))
  ]) assert.equal(bgi.wolfDeadTrialPauseOnlyHud(bad,2000000,'wolf'),false);
  assert.equal(bgi.wolfDeadTrialPauseOnlyHud(current,2000000,'other'),false);
  assert.equal(bgi.wolfDeadTrialPauseOnlyHud({...current,ocr:[...current.ocr,row('Start Game',850,470,200,50)]},2000000,'wolf'),false);
});

test('defensive Cryo mission accepts any positive HP but sends one E only and makes no effect claim',async()=>{
  let now=2000000,actions=[],reads=0;
  const result=await mission.runQuestStep('wolfDefensiveCryo',domain({hp:1}),{wolfDefensiveCryoReady:o=>bgi.wolfDefensiveCryoReady(o,now),
    wolfDefensiveCryo:async()=>actions.push('E'),sleep:async ms=>{assert.equal(ms,500);now+=ms;}},async()=>{reads++;return domain({timestamp:now,frameId:9,hp:1});});
  assert.deepEqual(actions,['E']);assert.equal(reads,1);assert.equal(result.status,'stopped');assert.equal(result.skillAttempts,1);assert.equal(result.targetEffectVerified,false);
});

test('defensive Cryo mission rejects dead, stale, wrong max HP, missing Trial or unsafe HUD flags',async()=>{
  for(const initial of [domain({hp:0}),domain({timestamp:1998999}),domain({max:1055}),domain({trial:false}),domain({kaeya:'Kaea'}),
    ...['choice','auto','loading','unknownHud','objectiveChanged'].map(flag=>domain({flags:{[flag]:true}}))]) {
    let actions=0,reads=0;
    const result=await mission.runQuestStep('wolfDefensiveCryo',initial,{wolfDefensiveCryoReady:o=>bgi.wolfDefensiveCryoReady(o,2000000),wolfDefensiveCryo:async()=>actions++,sleep:async()=>{}},async()=>{reads++;return initial;});
    assert.equal(result.status,'stopped');assert.equal(actions,0);assert.equal(reads,0);
  }
});

function adapterHarness({entry=true,foreground=true,step='wolfPause',frame=domain({kaeya:'Kaea'})}={}) {
  let now=2000000,currentFrame=frame;const keys=[];
  const entryReceipt={session:'wolf',mission:'questStep',status:'completed',timestamp:1999500,details:{result:{step:'wolfPartyStart'},inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:2,x:1705,y:1019,startedAt:1999400}]}};
  const context={Date:class extends Date{static now(){return now;}},genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:foreground,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:()=>false,readTextSync:p=>p==='reports/wolf.json'?JSON.stringify(entry?[entryReceipt]:[]):fs.readFileSync(path.join(root,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(){this.width=1920;this.height=1080;}findMulti(){const a=[];a.count=0;return a;}dispose(){}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=currentFrame.ocr.map(r=>({...r}));a.count=a.length;return a;},deriveCrop:()=>({srcMat:{resize:()=>({})},dispose(){}}),dispose(){}}),
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:c=>c,contourArea:()=>0}}},
    keyDown:k=>keys.push(['down',k]),keyUp:k=>keys.push(['up',k]),sleep:async ms=>{now+=ms;},moveMouseBy:(dx,dy)=>keys.push(['move',dx,dy]),click(){},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);const adapter=context.createActOneAdapter(7);
  adapter.beginMission({mission:'observe',session:'wolf',createdAt:1999999});return {adapter,keys,observe:async()=>{await adapter.observe('wolf',1);adapter.beginMission({mission:'questStep',step,session:'wolf',createdAt:1999999});},setFrame:f=>{currentFrame=f;}};
}

test('pause-only adapter fallback still requires current RDP focus and recorded same-session entry',async()=>{
  const noEntry=adapterHarness({entry:false});await noEntry.observe();await assert.rejects(noEntry.adapter.wolfDomainAction(),/entry required/);assert.deepEqual(noEntry.keys,[]);
  const unfocused=adapterHarness({foreground:false});await assert.rejects(unfocused.observe(),/foreground focus/);assert.deepEqual(unfocused.keys,[]);
  const good=adapterHarness();await good.observe();await good.adapter.wolfDomainAction();assert.deepEqual(good.keys,[['down','VK_ESCAPE'],['up','VK_ESCAPE']]);
});

test('dead-Trial fallback permits exactly one pause Escape after same-session entry, never movement',async()=>{
  const deadPause=adapterHarness({entry:true,step:'wolfPause',frame:deadTrialAmber()});
  await deadPause.observe();await deadPause.adapter.wolfDomainAction();
  assert.deepEqual(deadPause.keys,[['down','VK_ESCAPE'],['up','VK_ESCAPE']]);
  const noEntry=adapterHarness({entry:false,step:'wolfPause',frame:deadTrialAmber()});
  await noEntry.observe();await assert.rejects(noEntry.adapter.wolfDomainAction(),/entry required/);assert.deepEqual(noEntry.keys,[]);
  const movement=adapterHarness({entry:true,step:'wolfForwardFine',frame:deadTrialAmber()});
  await movement.observe();await assert.rejects(movement.adapter.wolfDomainAction(),/safe Wolf trial HUD required/);assert.deepEqual(movement.keys,[]);
});

test('close-food Cryo chain is mission-bounded and skips look/W below 60 percent',async()=>{
  let now=2000000,actions=[],reads=0;
  const initial={timestamp:now,frameId:1};const active=domain({timestamp:now+450,frameId:2,hp:600});
  const result=await mission.runQuestStep('wolfCloseFoodCryo',initial,{wolfCloseFoodCryoReady:()=>true,
    wolfCloseFoodCryoAction:async kind=>actions.push(kind),wolfDefensiveCryoReady:o=>bgi.wolfDefensiveCryoReady(o,now),
    sleep:async ms=>{actions.push(`sleep${ms}`);now+=ms;}},async()=>{reads++;return {...active,timestamp:now};});
  assert.deepEqual(actions,['close','sleep450','skill','sleep100']);assert.equal(reads,2);
  assert.equal(result.status,'stopped');assert.equal(result.foodCloseAttempts,1);assert.equal(result.orientationAttempts,0);assert.equal(result.skillAttempts,1);
});

test('close-food Cryo chain uses only lookRight250/W60/E60 when active HP is at least 60 percent',async()=>{
  let now=2000000;const actions=[];
  const result=await mission.runQuestStep('wolfCloseFoodCryo',{timestamp:now,frameId:1},{wolfCloseFoodCryoReady:()=>true,
    wolfCloseFoodCryoAction:async kind=>actions.push(kind),wolfDefensiveCryoReady:()=>true,sleep:async ms=>{actions.push(`sleep${ms}`);now+=ms;}},async()=>domain({timestamp:now+450,frameId:2,hp:900}));
  assert.deepEqual(actions,['close','sleep450','look','forward','skill','sleep100']);assert.equal(result.orientationAttempts,2);assert.equal(result.skillAttempts,1);
});


test('Wolf food-grid close gate requires exact Food, Sweet Madame and a unique bottom Use control',()=>{
  const o={timestamp:2000000,map:null,ocr:[row('Food',140,32,67,31),row('Sweet Madame',1332,127,263,41),row('Use',1690,1000,120,40)],
    hud:{world:false,climbing:false,dialogueReady:false,choice:false,bigMap:false,loading:false}};
  assert.equal(bgi.wolfFoodGridReady(o,2000000),true);
  for(const bad of [
    {...o,timestamp:1998999},{...o,ocr:o.ocr.filter(r=>r.text!=='Use')},{...o,ocr:[...o.ocr,row('Use',1680,1000,120,40)]},
    {...o,ocr:[...o.ocr,row('Confirm',1118,750,129,37)]},{...o,ocr:[...o.ocr,row('Amount to use',639,611,217,39)]},
    {...o,map:{map:'Teyvat',x:0,y:0}}
  ]) assert.equal(bgi.wolfFoodGridReady(bad,2000000),false);
});

test('close-food adapter rejects pre-close and stale-frame orientation, then caps look/W/E',async()=>{
  const foodGrid={timestamp:2000000,map:null,ocr:[row('Food',140,32,67,31),row('Sweet Madame',1332,127,263,41),row('Use',1690,1000,120,40)],hud:{world:false,choice:false}};
  const h=adapterHarness({entry:true,step:'wolfCloseFoodCryo',frame:foodGrid});
  await h.observe();assert.equal(h.adapter.wolfCloseFoodCryoReady(),true);
  await assert.rejects(h.adapter.wolfCloseFoodCryoAction('look'),/entry required|post-close/);assert.deepEqual(h.keys,[]);
  await h.adapter.wolfCloseFoodCryoAction('close');
  await assert.rejects(h.adapter.wolfCloseFoodCryoAction('look'),/post-close/);
  await h.adapter.sleep(450);h.setFrame(domain({kaeya:'Kaeya',hp:900}));await h.adapter.observe('wolf',2);
  await h.adapter.wolfCloseFoodCryoAction('look');await h.adapter.wolfCloseFoodCryoAction('forward');await h.adapter.wolfCloseFoodCryoAction('skill');
  await assert.rejects(h.adapter.wolfCloseFoodCryoAction('skill'),/already attempted/);
  assert.deepEqual(h.keys.filter(x=>x[0]==='down').map(x=>x[1]),['VK_ESCAPE','VK_W','VK_E']);
  assert.ok(h.keys.some(x=>x[0]==='move'&&x[1]===250&&x[2]===0));
});
