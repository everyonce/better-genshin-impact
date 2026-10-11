const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const recovery=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/recovery.js');

const packageDir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=90,height=25)=>({text,x,y,width,height});
const gridRows=(health='902/1427')=>[row('Food',140,32,67,31),row('Sweet Madame',1332,127,263,41),row('Use',1640,1000,120,40),row(health,906,1000,101,20)];
function modalRows(heading='Traveler',health='902/1427') {return [row('Food',140,32,67,31),row(heading,891,259,136,59),row('Sweet Madame',1332,127,263,41),row('Amount to use',639,611,217,39),
  row('Cancel',716,748,109,37),row('Confirm',1118,750,129,37),row(health,906,1000,101,20)];}
const entry={session:'wolf',mission:'questStep',status:'completed',details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[
  {type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:20,x:1705,y:1019,startedAt:1999000}
]}};

function harness({entryProof=true,initial='grid',useTransition='traveler',feedTransition='gridAfterFeed',health='902/1427'}={}) {
  let now=2000000,frame=20,state=initial,actions=[],keys=[],partyCrops=0,controlCrops=0;
  const history=entryProof?[entry]:[];
  function rows() {
    if(state==='grid'||state==='gridAfterFeed') return gridRows(health);
    if(state==='traveler') return modalRows('Traveler',health);
    if(state==='kaeya') return modalRows('Kaeya',health);
    if(state==='world') return [row(health,906,1000,101,20),row('E',1689,1028,18,21),row('Q',1802,1025,31,27)];
    if(state==='unknown') return [row('Settings',100,100)];
    return [];
  }
  function record() {const ev=apiAdapter.events();if(ev.length)history.push({session:'wolf',mission:'recover',status:'stopped',timestamp:now,details:{inputEvents:ev}});}
  const context={
    Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='reports/wolf.json'||p==='reports/wolf.jsonl',readTextSync:p=>p==='reports/wolf.json'?JSON.stringify(history):history.map(x=>JSON.stringify(x)).join('\n'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},
    ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){
      let r=this.mat&&this.mat.kind==='quantity'?[row('1',90,120,30,60)]:this.mat&&this.mat.kind==='party'?[row('Kaeya',200,100),row('Trial',240,120)]:this.mat&&this.mat.kind==='control'?[row('E',200,120),row('Q',280,120)]:rows();
      const a=r.map(x=>({...x}));a.count=a.length;return a;
    }dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:c=>c,contourArea:()=>0}}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows().map(r=>({...r}));a.count=a.length;return a;},
      deriveCrop:(x,y)=>({srcMat:{resize:()=>({kind:x===1105?'quantity':x===1630?'party':x===1520?'control':'other'}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}}),dispose(){}}),
    sleep:async ms=>{now+=ms;},click:(x,y)=>{actions.push(['click',x,y]);if(state==='grid')state=useTransition;else if(state==='traveler')state='kaeya';else if(state==='kaeya')state=feedTransition;},
    keyDown:k=>{keys.push(['down',k]);if(k==='VK_ESCAPE')state='world';},keyUp:k=>keys.push(['up',k]),moveMouseBy:(x,y)=>actions.push(['move',x,y]),log:{info(){}}
  };
  vm.runInNewContext(fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8'),context);
  const apiAdapter=context.createActOneAdapter(7);
  apiAdapter.beginMission({mission:'recover',session:'wolf',createdAt:now});
  const api={checkStop:()=>apiAdapter.checkStop(),wolfInfoReady:()=>false,wolfPauseRecoveryReady:()=>false,
    wolfRecoveryFoodStage:o=>apiAdapter.wolfRecoveryFoodStage(o),recoverWolfFoodAction:s=>apiAdapter.recoverWolfFoodAction(s),
    wolfRecoveryFoodActiveReady:o=>apiAdapter.wolfRecoveryFoodActiveReady(o),sleep:ms=>apiAdapter.sleep(ms)};
  const observe=()=>apiAdapter.observe('wolf',++frame);
  function nextRequest(){record();now+=10;apiAdapter.beginMission({mission:'recover',session:'wolf',createdAt:now});}
  return {api,apiAdapter,observe,nextRequest,actions,keys,getState:()=>state,getHistory:()=>history,getNow:()=>now,getCrops:()=>({partyCrops,controlCrops})};
}

test('recover-only food gates require exact fresh grid/modal, same-entry proof, and reject explicit zero HP',()=>{
  const now=2000000,base={timestamp:now,frameId:1,map:null,hud:{world:false,health:null},ocr:gridRows()};
  assert.deepEqual(bgi.wolfRecoveryFoodUseTarget(base,now),{x:1700,y:1020});
  for(const patch of [
    {timestamp:now-1001},{timestamp:now+1},{map:{map:'Teyvat',x:0,y:0}},
    {hud:{world:false,health:{current:0,max:1427}}},{hud:{world:false,health:{current:NaN,max:1427}}},
    {hud:{world:true,health:null}},{ocr:[...gridRows(),row('Use',1640,1000,120,40)]},
    {ocr:gridRows().filter(r=>r.text!=='Sweet Madame')},
    {ocr:gridRows().map(r=>r.text==='Use'?{...r,x:2000}:r)},
    {ocr:gridRows().map(r=>r.text==='Use'?{...r,y:1075}:r)}
  ]) assert.equal(bgi.wolfRecoveryFoodUseTarget({...base,...patch},now),null);
});

test('recover progresses one verified Food action per call and never repeats consumption',async()=>{
  const h=harness();
  let o=await h.observe(),r=await recovery.run(o,h.api,h.observe);
  assert.equal(r.foodStage,'use');assert.equal(r.nextFoodStage,'selectKaeya');assert.deepEqual(h.actions,[['click',1700,1020]]);
  h.nextRequest();o=await h.observe();r=await recovery.run(o,h.api,h.observe);
  assert.equal(r.foodStage,'selectKaeya');assert.equal(r.nextFoodStage,'feedKaeya');assert.deepEqual(h.actions,[['click',1700,1020],['click',1115,440]]);
  h.nextRequest();o=await h.observe();
  assert.equal(h.api.wolfRecoveryFoodStage(o),'feedKaeya');
  r=await recovery.run(o,h.api,h.observe);
  assert.equal(r.status,'stopped');assert.equal(r.foodUseAttempted,true);assert.equal(r.healingVerified,false);
  assert.equal(h.actions.length,3);assert.equal(h.actions[2][0],'click');assert.equal(h.keys.length,0);
  h.nextRequest();o=await h.observe();r=await recovery.run(o,h.api,h.observe);
  assert.equal(r.foodStage,'close');assert.equal(r.activeHudVerified,true);
  assert.equal(h.actions.length,3,'the post-consumption request closes Food without selecting or confirming again');
  assert.deepEqual(h.keys,[['down','VK_ESCAPE'],['up','VK_ESCAPE']]);
  assert.equal(h.actions.some(a=>a[0]==='move'||a.some(v=>v==='VK_W'||v==='VK_E')),false);
});

test('recover refuses unknown Food transitions, foreign entry, and zero HP; close needs prior use proof',async()=>{
  for(const opts of [{entryProof:false},{initial:'unknown'},{health:'0/1427'}]) {
    const h=harness(opts),o=await h.observe(),r=await recovery.run(o,h.api,h.observe);
    assert.notEqual(r.foodStage,'use');assert.deepEqual(h.actions,[]);assert.deepEqual(h.keys,[]);
  }
  const h=harness({initial:'traveler'}),o=await h.observe(),r=await recovery.run(o,h.api,h.observe);
  assert.notEqual(r.foodStage,'selectKaeya');assert.deepEqual(h.actions,[]);
});

test('a close fade is polled read-only and requires fresh positive Trial HUD before return',async()=>{
  const h=harness({initial:'gridAfterFeed'});
  h.getHistory().push({session:'wolf',mission:'recover',status:'stopped',details:{inputEvents:[{type:'wolfRecoveryFoodFeedKaeya',startedAt:1999900}]}});
  let o=await h.observe(),r=await recovery.run(o,h.api,h.observe);
  assert.equal(r.foodStage,'close');assert.equal(r.activeHudVerified,true);
  assert.deepEqual(h.keys,[['down','VK_ESCAPE'],['up','VK_ESCAPE']]);
  assert.equal(h.actions.length,0);
});

test('a retained food confirmation after a use cannot consume the inventory-close latch',async()=>{
  const h=harness({initial:'kaeya'});
  h.getHistory().push({session:'wolf',mission:'recover',status:'stopped',details:{inputEvents:[{type:'wolfRecoveryFoodFeedKaeya',startedAt:1999900}]}});
  const o=await h.observe();
  assert.equal(h.api.wolfRecoveryFoodStage(o),null);
  const r=await recovery.run(o,h.api,h.observe);
  assert.notEqual(r.foodStage,'close');
  assert.deepEqual(h.actions,[]);assert.deepEqual(h.keys,[]);
});
