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
