'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

const dir = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row = (text,x,y,width=100,height=30) => ({text,x,y,width,height});
function start(patch={}) { return {session:'s1',timestamp:1000,frameId:5,map:null,ocr:[
  row('Domain Entrance',137,30),row('Temple of the Lion',55,120),row('Deep Within the Temple of the Lion',52,157,390),
  row('Deep Within the Temple of the Lion',1274,149,469),row('Start',1688,999,85,36)],
  hud:{world:false,journal:false,bigMap:false,dialogueReady:false,choice:false,climbing:false,auto:false,tutorialStep:null},...patch}; }
function party(patch={}) { return {session:'s1',timestamp:1200,frameId:7,map:null,ocr:[row('Party Setup',75,30),row('Lumina',410,320),row('Amber',760,350),
  row('Team Standing By',80,1010,280,35),row('Start',1688,999,85,36)],hud:{world:false,journal:false,bigMap:false,dialogueReady:false,
  choice:false,climbing:false,auto:false,tutorialStep:null},...patch}; }
const proof = {session:'s1',mission:'questStep',status:'completed',timestamp:1100,details:{result:{step:'lionStart',label:'Deep Within the Temple of the Lion'},inputEvents:[
  {type:'lionDomainStart',label:'Deep Within the Temple of the Lion',frameId:5,x:1731,y:1017,startedAt:1050} ]}};
function fixture(reports=[]) {
  let now=1500, visibleRows=[]; const clicks=[], files=new Map();
  const context={Date:class extends Date {static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:5,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>files.has(p),readTextSync:p=>p==='reports/s1.jsonl'?reports.map(JSON.stringify).join('\n'):
      fs.existsSync(path.join(dir,p))?fs.readFileSync(path.join(dir,p),'utf8'):'',
      writeTextSync:(p,v)=>{files.set(p,v);return true;},writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=visibleRows.map(r=>({...r}));a.count=a.length;return a;},
      deriveCrop:()=>({srcMat:{resize:()=>({})},dispose(){}}),dispose(){}}),
    ImageRegion:class{constructor(){this.findMulti=()=>{const a=[];a.count=0;return a;};}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}}}},
    click:(x,y)=>clicks.push([x,y]), keyUp(){}, keyDown(){}, moveMouseBy(){}, sleep:async()=>{}, log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(dir,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(5);
  return {adapter,clicks,files,setNow:v=>{now=v;},setRows:r=>{visibleRows=r;}};
}

test('Lion adapter readiness delegates to fresh unique target and rejects stale or replayed starts',async()=>{
  const f=fixture(); f.adapter.beginMission({mission:'questStep',step:'lionStart',session:'s1',expectedFrameId:5,createdAt:900});
  const target=start();f.setRows(target.ocr);await f.adapter.observe('s1',5);
  assert.equal(f.adapter.lionStartReady({...target,timestamp:499}),false);
  assert.equal(f.adapter.lionStartReady({...target,ocr:[...target.ocr,row('Start',1688,999)]}),false);
  assert.equal(f.adapter.lionStartReady(target),true);
  assert.equal(f.adapter.startLionDomain(),'Deep Within the Temple of the Lion');
  assert.deepEqual(f.clicks,[[1731,1017]]);
  assert.equal(f.adapter.events().filter(e=>e.type==='lionDomainStart').length,1);
  assert.throws(()=>f.adapter.startLionDomain(),/Fresh exact Lion Domain Entrance/);
  assert.equal(f.clicks.length,1);
});

test('Lion party adapter requires exact uninterrupted same-session entry proof before one click',async()=>{
  const f=fixture([proof]); f.adapter.beginMission({mission:'questStep',step:'lionPartyStart',session:'s1',expectedFrameId:7,createdAt:900});
  f.setRows(party().ocr);await f.adapter.observe('s1',7);
  assert.equal(f.adapter.lionPartyReady(),true);
  f.adapter.startLionParty();
  assert.deepEqual(f.clicks,[[1731,1017]]);
  const event=f.adapter.events().find(e=>e.type==='lionPartyStart');
  assert.deepEqual(JSON.parse(JSON.stringify(event)),{type:'lionPartyStart',label:'Deep Within the Temple of the Lion',frameId:7,x:1731,y:1017,startedAt:1500});
  assert.throws(()=>f.adapter.startLionParty(),/Lion party start request required/);
  assert.equal(f.clicks.length,1);
});

test('Lion party adapter blocks absent, duplicate, stale-session, and interrupted entry proof',async()=>{
  const interrupted=structuredClone(proof); interrupted.details.inputEvents.push({type:'key',key:'VK_ESCAPE',startedAt:1150});
  for(const records of [[],[proof,structuredClone(proof)],[{...proof,session:'s2'}],[interrupted]]) {
    const f=fixture(records); f.adapter.beginMission({mission:'questStep',step:'lionPartyStart',session:'s1',expectedFrameId:7,createdAt:900});
    f.setRows(party().ocr);await f.adapter.observe('s1',7);
    assert.equal(f.adapter.lionPartyReady(),false);
    assert.throws(()=>f.adapter.startLionParty(),/uninterrupted same-session entrance/);
    assert.deepEqual(f.clicks,[]);
  }
});

test('Lion revision records lion-entry.js only for Lion entry requests',()=>{
  const f=fixture(); f.adapter.beginMission({mission:'questStep',step:'lionStart',session:'s1',expectedFrameId:5,createdAt:900});
  const revision=f.adapter.events().find(e=>e.type==='controllerRevision');
  assert.ok(revision.files['lion-entry.js']);
  assert.ok(f.files.has('revisions/'+revision.files['lion-entry.js']+'/lion-entry.js.txt'));
  assert.equal(bgi.falconStartTarget(start(),1500),null);
});
