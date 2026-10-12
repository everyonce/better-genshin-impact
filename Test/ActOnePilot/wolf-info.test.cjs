const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const packageDir = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const source = fs.readFileSync(path.join(packageDir, 'bgi.js'), 'utf8');
const caption = 'If there is water around, opponents may become Wet.';
const row = (text, x = 565, y = 780, width = 781, height = 43) => ({ text, x, y, width, height });
function observation(patch = {}) {
  return { session:'test', timestamp:2000000, frameId:59, map:null, ocr:[row(caption)],
    hud:{ world:false, journal:false, bigMap:false, dialogueReady:false, choice:false, health:{current:1427,max:1427}, groundControls:true, tutorialStep:'wolfInfo' }, ...patch };
}

test('Wolf Wet tutorial requires a fresh exact single caption in its verified position and safe scene', () => {
  const good = observation();
  assert.equal(bgi.wolfInfoState(good, 2000000), true);
  for (const patch of [
    { timestamp:1998999 },
    { ocr:[row(caption, 400, 780)] },
    { ocr:[row(caption, 620, 780)] },
    { ocr:[row(caption, 565, 780, 500, 43)] },
    { ocr:[row(caption), row(caption)] },
    { map:{map:'Teyvat',x:0,y:0} },
    { hud:{...good.hud,world:true} },
    { hud:{...good.hud,dialogueReady:true} },
    { hud:{...good.hud,choice:true} },
    { hud:{...good.hud,health:{current:0,max:1427}} },
  ]) assert.equal(bgi.wolfInfoState({...good,...patch},2000000),false);
  assert.equal(bgi.wolfDomainHud(good,2000000),false, 'ordinary Wolf movement/combat HUD gate rejects the tutorial');
});

test('release-r14 frame-26 Wet OCR without its trailing period remains a Wolf tutorial guard',()=>{
  const actualRow=row('If there is water around, opponents may become Wet',567,782,775,37);
  const actual=observation({ocr:[actualRow]});
  assert.equal(bgi.wolfInfoKind([actualRow]),'wet');
  assert.equal(bgi.wolfInfoState(actual,2000000),true);
  assert.equal(bgi.wolfDomainHud(actual,2000000),false);
  assert.equal(bgi.wolfDomainHud({...actual,hud:{...actual.hud,tutorialStep:'wolfInfo'}},2000000),false);
  assert.equal(bgi.wolfInfoKind([row(actualRow.text+'!',567,782,775,37)]),null);
});

test('frame-138 flamethrower-core tutorial accepts only the exact single caption at its measured position',()=>{
  const text="A flamethrower's core is what gives it the energy to shoot fire";
  const actualRow=row(text,502,784,905,35);
  const actual=observation({ocr:[actualRow]});
  assert.equal(bgi.wolfInfoKind([actualRow]),'flamethrower');
  assert.equal(bgi.wolfInfoState(actual,2000000),true);
  assert.equal(bgi.wolfInfoKind([row(text+'.',502,784,905,35)]),'flamethrower');
  assert.equal(bgi.wolfInfoKind([row(text+'!',502,784,905,35)]),null);
  for(const bad of [
    row(text,450,784,905,35),row(text,502,740,905,35),row(text,502,784,800,35),row(text,502,784,905,50),
    row('If there is water around, opponents may become Wet',567,782,775,37)
  ]) assert.equal(bgi.wolfInfoKind([actualRow,bad]),null);
  assert.equal(bgi.wolfInfoKind([row('A flamethrower core gives energy to shoot fire',502,784,905,35)]),null);
  assert.equal(bgi.wolfInfoKind([row(text,502,784,905,35),row(text,502,784,905,35)]),null);
});

test('frame-145 full-screen flamethrower tutorial permits missing HP only for the exact safe modal state',()=>{
  const text="A flamethrower's core is what gives it the energy to shoot fire.";
  const row145=row(text,504,784,905,35);
  const modal={world:false,journal:false,bigMap:false,dialogueReady:false,choice:false,health:null,
    groundControls:false,climbing:false,auto:false,tutorialStep:'wolfInfo',loading:false,unknownHud:false,objectiveChanged:false};
  const actual=observation({ocr:[row145],hud:modal});
  assert.equal(bgi.wolfInfoKind([row145]),'flamethrower');
  assert.equal(bgi.wolfInfoState(actual,2000000),true,'the captured full-screen tutorial hides health but remains an exact identified modal');
  assert.equal(bgi.wolfInfoState({...actual,timestamp:1998999},2000000),false);
  assert.equal(bgi.wolfInfoState({...actual,timestamp:2000001},2000000),false);
  for(const patch of [
    {map:{map:'Teyvat',x:1,y:2}},
    {hud:{...modal,world:true}},
    {hud:{...modal,groundControls:true}},
    {hud:{...modal,climbing:true}},
    {hud:{...modal,auto:true}},
    {hud:{...modal,tutorialStep:null}},
    {hud:{...modal,journal:true}},
    {hud:{...modal,bigMap:true}},
    {hud:{...modal,dialogueReady:true}},
    {hud:{...modal,choice:true}},
    {hud:{...modal,loading:true}},
    {hud:{...modal,unknownHud:true}},
    {hud:{...modal,objectiveChanged:true}},
    {ocr:[row145,row145]},
    {ocr:[row(text+'!',504,784,905,35)]},
    {ocr:[row(text,450,784,905,35)]},
    {hud:{...modal,health:{current:0,max:1427}}},
    {hud:{...modal,health:{current:NaN,max:1427}}},
    {hud:{...modal,health:{current:1,max:0}}},
    {hud:{...modal,health:{current:1428,max:1427}}},
    {hud:{...modal,health:undefined}},
    {ocr:[row('Loading',900,500,120,30)]}
  ]) assert.equal(bgi.wolfInfoState({...actual,...patch},2000000),false);
});

test('frame-146 flamethrower-disable tutorial requires the exact two-line caption pair and measured positions',()=>{
  const first="Use Cryo Skills to temporarily disable flamethrowers' cores and stop them";
  const second='from shooting fire';
  const pair=[row(first,420,784,1079,35),row(second,820,820,277,35)];
  assert.equal(bgi.wolfInfoKind(pair),'disableFlamethrower');
  assert.equal(bgi.wolfInfoKind([pair[0],row(second+'.',820,820,277,35)]),'disableFlamethrower');
  assert.equal(bgi.wolfInfoState(observation({ocr:pair}),2000000),true);
  for(const rows of [
    [pair[0]],[pair[1]],[...pair,pair[0]],[...pair,pair[1]],
    [row(first+'.',420,784,1079,35),pair[1]],
    [row(first,380,784,1079,35),pair[1]],[pair[0],row(second,820,850,277,35)],
    [pair[0],row(second,820,820,200,35)],
    [...pair,row("A flamethrower's core is what gives it the energy to shoot fire",502,784,905,35)],
    [...pair,row('If there is water around, opponents may become Wet',567,782,775,37)]
  ]) assert.equal(bgi.wolfInfoKind(rows),null);
});

function adapterHarness(proof = true, proofSession = 'test') {
  const clicks = [], rows = [row(caption), row('E',1700,1015,30,20), row('1427/1427',910,1000,100,25)];
  const partyStart = {session:proofSession,mission:'questStep',status:'completed',details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[
    {type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:58,x:1705,y:1019,startedAt:1999990}
  ]}};
  const context = {
    Date:class extends Date { static now(){return 2000000;} },
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:()=>false,readTextSync:p=>p==='reports/test.json'?JSON.stringify(proof?[partyStart]:[]):p==='reports/test.jsonl'?(proof?[partyStart].map(JSON.stringify).join('\n'): ''):fs.readFileSync(path.join(packageDir,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(){this.width=1920;this.height=1080;}findMulti(){const a=rows.map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:c=>c,contourArea:()=>0}}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows.map(r=>({...r}));a.count=a.length;return a;},deriveCrop:()=>({srcMat:{resize:()=>({}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}}),dispose(){}}),
    sleep:async()=>{},click:(x,y)=>clicks.push([x,y]),log:{info(){}}
  };
  vm.runInNewContext(source,context);
  const adapter=context.createActOneAdapter(7);
  adapter.beginMission({mission:'questStep',step:'wolfInfo',session:'test',createdAt:2000000});
  return {adapter,clicks,proof:proof?[partyStart]:[]};
}

test('wolfInfo makes one fixed click after same-session party proof, then observes the next slide', async () => {
  const {adapter,clicks}=adapterHarness();
  const first=await adapter.observe('test',59);
  assert.equal(first.hud.tutorialStep,'wolfInfo');
  let sleeps=0,observes=0;
  const result=await mission.runQuestStep('wolfInfo',first,{now:()=>2000000,checkStop(){},wolfDismissInfo:()=>adapter.wolfDismissInfo(),sleep:async ms=>{assert.equal(ms,500);sleeps++;}},async()=>{observes++;return {frameId:60};});
  assert.equal(result.status,'completed');
  assert.equal(result.clicks,1);
  assert.match(result.reason,/inspect next slide/);
  assert.equal(sleeps,1);
  assert.equal(observes,1);
  assert.deepEqual(clicks,[[960,900]]);
  assert.throws(()=>adapter.wolfDismissInfo(),/Fresh exact Wolf tutorial required/);
});

test('Wolf freeze information requires both verified frame-62 lines and rejects partial or duplicate captions', () => {
  const lines=[row('Cryo skills can freeze water, Hydro opponents, or opponents that are Wet.',422,786,1073,35),
    row('Utilize this elemental reaction to gain an advantage over your opponents.',427,816,1059,42)];
  assert.equal(bgi.wolfInfoKind(lines),'freeze');
  assert.equal(bgi.wolfInfoState(observation({ocr:lines}),2000000),true);
  for(const bad of [[lines[0]],[lines[1]],[...lines,lines[0]],[...lines,row(caption)],
    [{...lines[0],x:700},lines[1]],[lines[0],{...lines[1],y:100}]]) assert.equal(bgi.wolfInfoKind(bad),null);
});

test('frame-510 Hydro Amber tutorial requires its unique exact two-line caption and measured positions',()=>{
  const first='The blue stone in the center of the room is Hydro Amber. Breaking it will';
  const second='make it rain, making everything in its range Wet.';
  const lines=[row(first,436,784,1047,35),row(second,608,822,699,29)];
  const actual=observation({ocr:lines});
  assert.equal(bgi.wolfInfoKind(lines),'hydroAmber');
  assert.equal(bgi.wolfInfoState(actual,2000000),true);
  assert.equal(bgi.wolfInfoKind([row(first+'.',436,784,1047,35),row(second.slice(0,-1),608,822,699,29)]),'hydroAmber',
    'the exact pair accepts either terminal-period form on each row');
  assert.equal(bgi.wolfInfoState({...actual,timestamp:1998999},2000000),false);
  assert.equal(bgi.wolfInfoState({...actual,timestamp:2000001},2000000),false);
  for(const rows of [
    [lines[0]],[lines[1]],[...lines,lines[0]],[...lines,lines[1]],
    [row(first+'!',436,784,1047,35),lines[1]],
    [row(first,380,784,1047,35),lines[1]],[lines[0],row(second,608,850,699,29)],
    [lines[0],row(second,608,822,600,29)],
    [...lines,row(caption)],
    [...lines,row("A flamethrower's core is what gives it the energy to shoot fire",502,784,905,35)],
  ]) assert.equal(bgi.wolfInfoKind(rows),null);
});

test('wolfInfo cannot click without same-session completed Wolf party proof', async () => {
  const {adapter,clicks}=adapterHarness(false);
  await adapter.observe('test',59);
  assert.throws(()=>adapter.wolfDismissInfo(),/Same-session Wolf entry required/);
  assert.deepEqual(clicks,[]);

  const wrongSession=adapterHarness(true,'other-session');
  await wrongSession.adapter.observe('test',59);
  assert.throws(()=>wrongSession.adapter.wolfDismissInfo(),/Same-session Wolf entry required/);
  assert.deepEqual(wrongSession.clicks,[]);
});
