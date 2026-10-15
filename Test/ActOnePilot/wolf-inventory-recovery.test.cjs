const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=100,height=30)=>({text,x,y,width,height});
function pause({timestamp=2000000,continueX=790,leave=true}={}) {
  return {session:'wolf',timestamp,frameId:40,map:null,ocr:[row('Continue Challenge',continueX,410,340,45),...(leave?[row('Leave Domain?',790,650,340,45)]:[])],
    hud:{world:false,journal:false,bigMap:false,dialogueReady:false,choice:false,climbing:false}};
}
function food({timestamp=2000000,confirm=false}={}) {
  return {session:'wolf',timestamp,frameId:42,map:null,ocr:[row('Food',150,45,80,30),...(confirm?[row('Confirm',700,750)]:[])],
    hud:{world:false,journal:false,bigMap:false,dialogueReady:false,choice:false,climbing:false}};
}
function foodModal({item='Sweet Madame',heading='Traveler',timestamp=2000000,cancel=true}={}) {
  return {session:'wolf',timestamp,frameId:93,map:null,ocr:[row('Food',140,32,67,31),row(item,1332,127,263,41),
    row(heading,heading==='Traveler'?869:872,266,heading==='Traveler'?177:177,43),row('Amount to use',639,611,217,39),
    ...(cancel?[row('Cancel',716,748,109,37)]:[]),row('Confirm',1118,750,129,37)],
    hud:{world:false,journal:false,bigMap:false,dialogueReady:false,choice:false,climbing:false}};
}

test('Wolf inventory recovery requires the fresh exact pause labels and unique measured Food tab',()=>{
  assert.deepEqual(bgi.wolfInventoryContinueTarget(pause(),2000000),row('Continue Challenge',790,410,340,45));
  for(const bad of [pause({timestamp:1998999}),pause({continueX:500}),pause({leave:false})])
    assert.equal(bgi.wolfInventoryContinueTarget(bad,2000000),null);
  assert.equal(bgi.wolfFoodInventoryReady(food(),2000000),true);
  assert.equal(bgi.wolfFoodInventoryReady(food({confirm:true}),2000000),false);
  assert.equal(bgi.wolfFoodInventoryReady({...food(),ocr:[row('Food',150,45),row('Food',150,45)]},2000000),false);
  assert.equal(bgi.wolfFoodInventoryReady({...food(),map:{map:'Teyvat',x:0,y:0}},2000000),false);
});

test('paused food-confirmation boundary is limited to the captured item, Traveler heading, and modal geometry',()=>{
  const captured=foodModal();
  assert.equal(bgi.knownSafeFoodBoundary(captured,2000000),true);
  assert.equal(bgi.wolfFoodInventoryReady(captured,2000000),false,'food-open completion remains stricter than paused-boundary recognition');
  assert.equal(bgi.knownSafeFoodBoundary(foodModal({item:'Teyvat Fried Egg'}),2000000),true);
  assert.equal(bgi.knownSafeFoodBoundary(foodModal({cancel:false}),2000000),true,'captured Use Again modal has no visible Cancel control');
  for(const bad of [
    {...captured,timestamp:1998999},
    {...captured,ocr:captured.ocr.filter(r=>r.text!=='Traveler')},
    {...captured,ocr:captured.ocr.filter(r=>r.text!=='Amount to use')},
    {...captured,ocr:captured.ocr.filter(r=>r.text!=='Sweet Madame')},
    {...captured,ocr:captured.ocr.map(r=>r.text==='Confirm'?{...r,x:900}:r)},
    {...captured,ocr:[...captured.ocr,row('Confirm',1118,750,129,37)]},
    {...captured,ocr:[...captured.ocr,row('Cancel',400,748,109,37)]},
    {...captured,ocr:captured.ocr.map(r=>r.text==='Traveler'?{...r,text:'Unknown'}:r)},
    {...captured,map:{map:'Teyvat',x:0,y:0}}
  ]) assert.equal(bgi.knownSafeFoodBoundary(bad,2000000),false);
});

test('Kaeya selection target is limited to the measured Sweet Madame and Traveler modal',()=>{
  const modal=foodModal();
  assert.deepEqual(bgi.wolfKaeyaFoodTarget(modal,2000000),{x:1115,y:440});
  assert.equal(bgi.knownSafeFoodBoundary(foodModal({heading:'Kaeya'}),2000000),true);
  assert.equal(bgi.wolfKaeyaFoodSelected(foodModal({heading:'Kaeya'}),2000000),true);
  for(const bad of [
    {...modal,timestamp:1998999},
    {...modal,ocr:modal.ocr.filter(r=>r.text!=='Sweet Madame')},
    {...modal,ocr:modal.ocr.map(r=>r.text==='Sweet Madame'?{...r,x:900}:r)},
    {...modal,ocr:modal.ocr.map(r=>r.text==='Traveler'?{...r,text:'Unknown'}:r)},
    {...modal,ocr:[...modal.ocr,row('Kaeya',872,266,177,43)]},
    {...modal,map:{map:'Teyvat',x:0,y:0}}
  ]) assert.equal(bgi.wolfKaeyaFoodTarget(bad,2000000),null);
  assert.equal(bgi.wolfKaeyaFoodSelected(modal,2000000),false);
});

test('mission selects Kaeya once, captures fresh selection, and never uses food',async()=>{
  let now=2000000;const calls=[];
  const result=await mission.runQuestStep('wolfSelectKaeyaFood',foodModal(),{
    now:()=>now,wolfKaeyaFoodReady:o=>!!bgi.wolfKaeyaFoodTarget(o,now),
    wolfSelectKaeyaFood:async()=>calls.push('click'),sleep:async ms=>{calls.push(`sleep${ms}`);now+=ms;},
    wolfKaeyaFoodSelected:o=>bgi.wolfKaeyaFoodSelected(o,now)
  },async()=>{calls.push('observe');return foodModal({heading:'Kaeya',timestamp:now});});
  assert.equal(result.status,'completed');assert.equal(result.selectionAttempts,1);assert.equal(result.selectionVerified,true);assert.equal(result.foodConsumed,false);
  assert.deepEqual(calls,['click','sleep300','observe']);
});

test('mission continues once, opens inventory with B before capture, and claims no healing',async()=>{
  let now=2000000,reads=0;const calls=[];
  const result=await mission.runQuestStep('wolfInventoryRecover',pause(),{
    now:()=>now,wolfInventoryContinueReady:o=>!!bgi.wolfInventoryContinueTarget(o,now),
    wolfInventoryContinue:async()=>calls.push('continue'),wolfInventoryOpen:async()=>calls.push('B'),
    sleep:async ms=>{calls.push(`sleep${ms}`);now+=ms;},wolfFoodInventoryReady:o=>bgi.wolfFoodInventoryReady(o,now)
  },async()=>{reads++;calls.push('observe');return food();});
  assert.equal(result.status,'completed');assert.equal(result.inventoryVerified,true);assert.equal(result.healingAttempted,false);
  assert.deepEqual(calls,['continue','sleep450','B','sleep450','observe']);assert.equal(reads,1);
});

test('mission sends no input when the initial pause menu is stale, incomplete, or off-position',async()=>{
  for(const initial of [pause({timestamp:1998999}),pause({leave:false}),pause({continueX:500})]) {
    let actions=0;
    const result=await mission.runQuestStep('wolfInventoryRecover',initial,{wolfInventoryContinueReady:o=>!!bgi.wolfInventoryContinueTarget(o,2000000),
      wolfInventoryContinue:async()=>actions++,wolfInventoryOpen:async()=>actions++,sleep:async()=>{}},async()=>food());
    assert.equal(result.status,'stopped');assert.equal(actions,0);
  }
});

function adapterHarness({entry=true,requestStep='wolfInventoryRecover',menu=pause()}={}) {
  let now=2000000,opened=false,captures=0;const clicks=[],keys=[];
  const party={session:'wolf',mission:'questStep',status:'completed',timestamp:1999500,
    details:{result:{step:'wolfPartyStart'},inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:20,x:1705,y:1019,startedAt:1999400}]}};
  const rows=()=>opened?food({timestamp:now}).ocr:menu.ocr;
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:()=>false,readTextSync:p=>p==='reports/wolf.json'?JSON.stringify(entry?[party]:[]):fs.readFileSync(path.join(root,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(){this.width=1920;this.height=1080;}findMulti(){const a=rows().map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:c=>c,contourArea:()=>0}}},
    captureGameRegion:()=>{captures++;return {width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows().map(r=>({...r}));a.count=a.length;return a;},deriveCrop:()=>({srcMat:{resize:()=>({rows:[]}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}}),dispose(){}};},
    keyDown:k=>{keys.push(['down',k]);if(k==='VK_B')opened=true;},keyUp:k=>keys.push(['up',k]),sleep:async ms=>{now+=ms;},click:(x,y)=>clicks.push([x,y]),log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);
  adapter.beginMission({mission:'questStep',step:requestStep,session:'wolf',createdAt:1999999});
  return {adapter,clicks,keys,captures,observe:async()=>adapter.observe('wolf',1),advance:ms=>{now+=ms;},getCaptures:()=>captures};
}

test('adapter gates Continue and B on same-entry proof, freshness, request, and one-attempt state',async()=>{
  const noEntry=adapterHarness({entry:false});await noEntry.observe();
  assert.throws(()=>noEntry.adapter.wolfInventoryContinue(),/entry required/);assert.deepEqual(noEntry.clicks,[]);
  const stale=adapterHarness();await stale.observe();stale.advance(1001);
  assert.throws(()=>stale.adapter.wolfInventoryContinue(),/pause menu required/);assert.deepEqual(stale.clicks,[]);
  const wrongRequest=adapterHarness({requestStep:'wolfForward'});await wrongRequest.observe();
  assert.throws(()=>wrongRequest.adapter.wolfInventoryContinue(),/pause menu required/);assert.deepEqual(wrongRequest.clicks,[]);
  const noPause=adapterHarness({menu:pause({leave:false})});await noPause.observe();
  assert.throws(()=>noPause.adapter.wolfInventoryContinue(),/pause menu required/);assert.deepEqual(noPause.clicks,[]);

  const h=adapterHarness();const first=await h.observe();assert.equal(h.adapter.wolfInventoryContinueReady(first),true);
  h.adapter.wolfInventoryContinue();assert.deepEqual(h.clicks,[[960,433]]);
  assert.throws(()=>h.adapter.wolfInventoryContinue(),/pause menu required/);
  await h.adapter.sleep(450);await h.adapter.wolfInventoryOpen();
  assert.deepEqual(h.keys,[['down','VK_B'],['up','VK_B']]);
  await assert.rejects(h.adapter.wolfInventoryOpen(),/Immediate verified Wolf Continue/);
  const after=await h.observe();assert.equal(h.adapter.wolfFoodInventoryReady(after),true);
  assert.equal(h.getCaptures(),2,'no expensive capture occurs between Continue and B');
});

test('adapter Kaeya selection needs same-entry proof, correct fresh modal, and permits one click only',async()=>{
  for(const opts of [
    {entry:false,requestStep:'wolfSelectKaeyaFood',menu:foodModal()},
    {requestStep:'wolfForward',menu:foodModal()},
    {requestStep:'wolfSelectKaeyaFood',menu:foodModal({item:'Teyvat Fried Egg'})},
    {requestStep:'wolfSelectKaeyaFood',menu:foodModal({heading:'Kaeya'})}
  ]) {
    const h=adapterHarness(opts);await h.observe();
    assert.throws(()=>h.adapter.wolfSelectKaeyaFood());assert.deepEqual(h.clicks,[]);
  }
  const h=adapterHarness({requestStep:'wolfSelectKaeyaFood',menu:foodModal()});
  const first=await h.observe();assert.equal(h.adapter.wolfKaeyaFoodReady(first),true);
  h.adapter.wolfSelectKaeyaFood();assert.deepEqual(h.clicks,[[1115,440]]);
  assert.throws(()=>h.adapter.wolfSelectKaeyaFood());assert.deepEqual(h.clicks,[[1115,440]]);
});

test('inventory recovery stops when post-open OCR does not confirm the Food screen',async()=>{
  let now=2000000,opens=0;
  const result=await mission.runQuestStep('wolfInventoryRecover',pause(),{now:()=>now,checkStop:()=>{},wolfInventoryContinueReady:()=>true,
    wolfInventoryContinue:async()=>{},wolfInventoryOpen:async()=>opens++,sleep:async ms=>{now+=ms;},wolfFoodInventoryReady:()=>false},async()=>food());
  assert.equal(opens,1);assert.equal(result.status,'stopped');assert.equal(result.inventoryVerified,false);assert.equal(result.healingAttempted,false);
});
