const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const recovery=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/recovery.js');

const packageDir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const source=fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8');
const row=(text,x,y,width=210,height=36)=>({text,x,y,width,height});
const pauseRows=()=>[row('Continue Challenge',800,400,300,40),row('Leave Domain?',800,650,300,40)];
const activeRows=()=>[row('1100/1427',910,1000,100,25),row('E',1689,1028,18,21),row('Q',1802,1025,31,27)];
const entry={session:'s',mission:'questStep',status:'completed',details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[
  {type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:20,x:1705,y:1019,startedAt:1999000}
]}};

function harness({proof=true,wrongMenu=false,missingTrial=false,priorAttempt=false}={}) {
  let clock=2000000,frame=10,continued=false;
  const clicks=[],keys=[],partyCrops=[];
  const entries=proof?[entry]:[];
  if(priorAttempt) entries.push({session:'s',mission:'recover',status:'stopped',details:{inputEvents:[{type:'wolfPauseRecoveryContinue',startedAt:1999900}]}});
  function currentRows(){return continued?activeRows():(wrongMenu?[row('Continue Challenge',1000,400,300,40),row('Leave Domain?',800,650,300,40)]:pauseRows());}
  const context={
    Date:class extends Date{static now(){return clock;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='reports/s.json'||p==='reports/s.jsonl',readTextSync:p=>p==='reports/s.json'?JSON.stringify(entries):entries.map(JSON.stringify).join('\n'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},
    ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){
      let rows=this.mat&&this.mat.kind==='party'?(missingTrial?[row('Kaeya',200,100,90,30)]:[row('Kaeya',200,100,90,30),row('Trial',240,120,90,30)]):currentRows();
      const a=rows.map(r=>({...r}));a.count=a.length;return a;
    }dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}}}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=currentRows().map(r=>({...r}));a.count=a.length;return a;},
      deriveCrop:(x,y)=>({srcMat:{resize:()=>({kind:x===1630?'party':'other'})},dispose(){} }),dispose(){}}),
    sleep:async()=>{},click:(x,y)=>{clicks.push([x,y]);continued=true;},keyDown:k=>keys.push(['down',k]),keyUp:k=>keys.push(['up',k]),moveMouseBy:(x,y)=>keys.push(['move',x,y]),log:{info(){}}
  };
  vm.runInNewContext(source,context);
  const adapter=context.createActOneAdapter(7);
  adapter.beginMission({mission:'recover',session:'s',createdAt:clock});
  const observe=()=>adapter.observe('s',++frame);
  const api={checkStop:()=>adapter.checkStop(),wolfInfoReady:()=>false,wolfPauseRecoveryReady:o=>adapter.wolfPauseRecoveryReady(o),
    recoverWolfPauseMenuContinue:()=>adapter.recoverWolfPauseMenuContinue(),wolfPauseRecoveryActiveReady:o=>adapter.wolfPauseRecoveryActiveReady(o),
    sleep:async ms=>{clock+=ms;}};
  return {adapter,api,observe,clicks,keys,partyCrops,advance:ms=>{clock+=ms;}};
}

test('pause-menu recovery target is fresh, unique, correctly positioned, and safely identified',()=>{
  const now=2000000,o={timestamp:now,frameId:1,map:null,hud:{world:false,auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,climbing:false},ocr:pauseRows()};
  assert.ok(bgi.wolfRecoveryPauseTarget(o,now));
  for(const patch of [
    {timestamp:now-1001},{timestamp:now+1},{map:{map:'Teyvat',x:0,y:0}},
    {hud:{...o.hud,world:true}},{hud:{...o.hud,auto:true}},{hud:{...o.hud,journal:true}},
    {hud:{...o.hud,bigMap:true}},{hud:{...o.hud,dialogueReady:true}},{hud:{...o.hud,choice:true}},
    {hud:{...o.hud,climbing:true}},{hud:{...o.hud,loading:true}},{hud:{...o.hud,unknownHud:true}},
    {ocr:[pauseRows()[0]]},{ocr:[...pauseRows(),pauseRows()[0]]},
    {ocr:[row('Continue Challenge',1000,400,300,40),pauseRows()[1]]},
    {ocr:[pauseRows()[0],row('Leave Domain?',1100,650,300,40)]}
  ]) assert.equal(bgi.wolfRecoveryPauseTarget({...o,...patch},now),null);
});

test('recovery sends one exact Continue, verifies a fresh positive Trial HUD, then leaves pause to main',async()=>{
  const h=harness(),initial=await h.observe();
  assert.ok(bgi.wolfRecoveryPauseTarget(initial,2000000));
  const result=await recovery.run(initial,h.api,h.observe);
  assert.equal(result.status,'completed');assert.equal(result.continueClicks,1);assert.equal(result.activeHudVerified,true);
  assert.equal(h.clicks.length,1);assert.deepEqual(h.clicks,[[950,420]]);
  assert.deepEqual(h.keys,[],'recovery must not send movement, combat, or camera input');
  assert.equal(h.adapter.events().filter(e=>e.type==='wolfPauseRecoveryContinue').length,1);
  assert.equal(h.adapter.events().some(e=>e.type==='key'||e.type==='rotate'),false);
  assert.throws(()=>h.adapter.recoverWolfPauseMenuContinue(),/Fresh unique Wolf pause menu required/);
});

test('missing entry, wrong menu geometry, stale observation, reused click, or missing Trial refuses further input',async()=>{
  for(const opts of [{proof:false},{wrongMenu:true},{priorAttempt:true}]) {
    const h=harness(opts),initial=await h.observe();
    const result=await recovery.run(initial,h.api,h.observe);
    assert.notEqual(result.activeHudVerified,true);assert.deepEqual(h.clicks,[]);assert.deepEqual(h.keys,[]);
  }
  const stale=harness(),initial=await stale.observe();stale.advance(1001);
  const result=await recovery.run(initial,stale.api,stale.observe);
  assert.notEqual(result.activeHudVerified,true);assert.deepEqual(stale.clicks,[]);assert.deepEqual(stale.keys,[]);
  const noTrial=harness({missingTrial:true}),pause=await noTrial.observe();
  const bounded=await recovery.run(pause,noTrial.api,noTrial.observe);
  assert.equal(bounded.status,'stopped');assert.equal(bounded.continueClicks,1);assert.equal(bounded.activeHudVerified,false);
  assert.equal(noTrial.clicks.length,1);assert.deepEqual(noTrial.keys,[],'missing post-Continue Trial evidence never authorizes more input');
});
