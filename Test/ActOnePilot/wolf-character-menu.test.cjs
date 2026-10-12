const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const recovery=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/recovery.js');

const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const session='wolf-character-menu',row=(text,x,y,width=90,height=25)=>({text,x,y,width,height});
const foodRows=[row('Food',140,32,67,31),row('Sweet Madame',1332,127,263,41),row('Use',1640,1000,120,40)];
const pauseRows=[row('Continue Challenge',831,399,287,40),row('Leave Domain?',864,640,221,36)];
const characterRows=[row('Kaeya',1660,484,92,41),row('Trial',1790,463,49,24),row('100/1427',906,1001,104,21),row('E',1689,1027,19,21),row('Q',1808,1028,19,21)];
const menuRows=['Attributes','Weapons','Artifacts','Talents','Constellation'].map((s,i)=>row(s,75,100+i*90,160,35));
const amberLevelRows=[row('Amber / Level Up',120,30,300,35),row('Amber',1600,130,100,30),row('Select EXP materials',1300,650,300,35),
  row('Amount to use',1100,900,180,35),row('Required',1100,1000,100,30),row('Level Up',1600,990,120,35),row('Base HP',1100,240,100,30)];
const party={session,mission:'questStep',status:'completed',details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[
  {type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:20,startedAt:1999000}
]}};

function foodObs(patch={}) { return {session,frameId:1,timestamp:2000000,map:null,ocr:foodRows.map(r=>({...r})),hud:{world:false,climbing:false,dialogueReady:false,choice:false,bigMap:false,loading:false},...patch}; }
function menuObs(patch={}) { return {session,frameId:4,timestamp:2000000,map:null,ocr:menuRows.map(r=>({...r})),hud:{world:false,auto:false,loading:false,bigMap:false,dialogueReady:false,choice:false},...patch}; }

test('exact English character-menu anchors require fresh, unambiguous menu geometry',()=>{
  assert.equal(bgi.wolfCharacterMenuVisible(menuObs(),2000000),true);
  for(const bad of [
    menuObs({timestamp:1998999}),menuObs({timestamp:2000001}),menuObs({map:{map:'Teyvat',x:0,y:0}}),
    menuObs({ocr:menuRows.filter(r=>r.text!=='Artifacts')}),
    menuObs({ocr:[...menuRows,row('Talents',75,550,160,35)]}),
    menuObs({ocr:menuRows.map(r=>r.text==='Weapons'?{...r,x:500}:r)}),
    menuObs({hud:{world:false,auto:true,loading:false,bigMap:false,dialogueReady:false,choice:false}})
  ]) assert.equal(bgi.wolfCharacterMenuVisible(bad,2000000),false);
});

test('accent and character-shape noise in live OCR is accepted only for unique left-menu labels',()=>{
  const noisy=menuRows.map(r=>r.text==='Weapons'?{...r,text:'Wéapons.'}:r.text==='Artifacts'?{...r,text:' Artifacts à'}:r.text==='Talents'?{...r,text:'Falents'}:r);
  assert.equal(bgi.wolfCharacterMenuVisible(menuObs({ocr:noisy}),2000000),true);
  const canonicalDuplicate=[...noisy,row('Weapons',80,280,160,35)];
  assert.equal(bgi.wolfCharacterMenuVisible(menuObs({ocr:canonicalDuplicate}),2000000),false);
  assert.equal(bgi.wolfCharacterMenuVisible(menuObs({ocr:[...noisy,row('Talents',80,370,160,35)]}),2000000),false);
  assert.equal(bgi.wolfCharacterMenuVisible(menuObs({ocr:noisy.filter(r=>r.text!=='Wéapons.')}),2000000),false);
  assert.equal(bgi.wolfCharacterMenuVisible(menuObs({ocr:noisy.map(r=>r.text==='Wéapons.'?{...r,x:500}:r)}),2000000),false);
});

test('Amber Level Up panel requires every exact unique English anchor in its measured region',()=>{
  const panel={session,frameId:8,timestamp:2000000,map:null,ocr:amberLevelRows.map(r=>({...r})),hud:{world:false,auto:false,loading:false,bigMap:false,dialogueReady:false,choice:false}};
  assert.equal(bgi.wolfAmberLevelPanelVisible(panel,2000000),true);
  for(const bad of [
    {...panel,timestamp:1998999},{...panel,timestamp:2000001},{...panel,map:{map:'Teyvat',x:0,y:0}},
    {...panel,ocr:panel.ocr.filter(r=>r.text!=='Select EXP materials')},
    {...panel,ocr:[...panel.ocr,row('Level Up',1600,990,120,35)]},
    {...panel,ocr:panel.ocr.map(r=>r.text==='Base HP'?{...r,x:1000}:r)},
    {...panel,hud:{...panel.hud,loading:true}}
  ]) assert.equal(bgi.wolfAmberLevelPanelVisible(bad,2000000),false);
});

function harness({proof=true,foreground=true,wrongSession=false}={}) {
  let now=2000000,frame=0,rows=foodRows.map(r=>({...r}));const keys=[],clicks=[];
  const history=proof?[party]:[];
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:wrongSession?8:7,isGameForeground:foreground,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='reports/'+session+'.json',readTextSync:p=>p==='reports/'+session+'.json'?JSON.stringify(history):fs.readFileSync(path.join(root,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:c=>c,contourArea:()=>0}}},
    ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const a=rows.map(r=>({...r}));a.count=a.length;return a;}inRange(){return {findContoursAsArray:()=>[],dispose(){}};}dispose(){}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows.map(r=>({...r}));a.count=a.length;return a;},deriveCrop:()=>({srcMat:{resize:()=>({}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}}),dispose(){}}),
    keyDown:k=>keys.push(['down',k]),keyUp:k=>keys.push(['up',k]),click:(x,y)=>clicks.push([x,y]),sleep:async ms=>{now+=ms;},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);adapter.beginMission({mission:'questStep',step:'wolfCharactersOpen',session,createdAt:now,expectedFrameId:1});
  const observe=async()=>adapter.observe(session,++frame);
  return {adapter,observe,keys,clicks,setRows(value){rows=value.map(r=>({...r}));},advance(ms){now+=ms;},now:()=>now};
}

test('Food close needs exact no-confirm grid and same-session Wolf entry before Escape',async()=>{
  const h=harness(),o=await h.observe();assert.equal(h.adapter.wolfCharactersFoodCloseReady(o),true,JSON.stringify({ocr:o.ocr,hud:o.hud,map:o.map,timestamp:o.timestamp,session:o.session}));
  await h.adapter.wolfCharactersFoodClose();
  assert.deepEqual(h.keys,[['down','VK_ESCAPE'],['up','VK_ESCAPE']]);
  assert.equal(h.adapter.events().filter(e=>e.type==='wolfCharactersCloseInventory').length,1);
  for(const options of [{proof:false},{wrongSession:true},{foreground:false}]) {
    const bad=harness(options);
    if(options.proof===false) {
      const fresh=await bad.observe();assert.equal(bad.adapter.wolfCharactersFoodCloseReady(fresh),false);
    }
    await assert.rejects(bad.adapter.wolfCharactersFoodClose());assert.deepEqual(bad.keys,[]);
  }
  for(const badRows of [[...foodRows,row('Confirm',1118,750,129,37)],[...foodRows,row('Amount to use',639,611,217,39)]]) {
    const bad=harness();bad.setRows(badRows);const fresh=await bad.observe();
    assert.equal(bad.adapter.wolfCharactersFoodCloseReady(fresh),false);await assert.rejects(bad.adapter.wolfCharactersFoodClose());assert.deepEqual(bad.keys,[]);
  }
  const stale=harness(),staleObs=await stale.observe();stale.advance(1001);
  assert.equal(stale.adapter.wolfCharactersFoodCloseReady(staleObs),false);await assert.rejects(stale.adapter.wolfCharactersFoodClose());assert.deepEqual(stale.keys,[]);
});

test('pause fallback requires fresh exact canonical pause and same-session entry before one Continue',async()=>{
  const h=harness();h.setRows(pauseRows);const o=await h.observe();
  assert.equal(h.adapter.wolfCharactersPauseContinueReady(o),true);
  h.adapter.wolfCharactersPauseContinue();
  assert.deepEqual(h.clicks,[[975,419]]);assert.deepEqual(h.keys,[]);
  assert.equal(h.adapter.events().filter(e=>e.type==='wolfCharactersContinue').length,1);
  assert.equal(h.adapter.wolfCharactersFoodCloseReady(o),false);
  assert.equal(h.adapter.wolfCharactersPauseContinueReady(o),false);
  assert.throws(()=>h.adapter.wolfCharactersPauseContinue());assert.deepEqual(h.clicks,[[975,419]]);

  const noProof=harness({proof:false});noProof.setRows(pauseRows);const unproven=await noProof.observe();
  assert.equal(noProof.adapter.wolfCharactersPauseContinueReady(unproven),false);
  assert.throws(()=>noProof.adapter.wolfCharactersPauseContinue());assert.deepEqual(noProof.clicks,[]);
  const stale=harness();stale.setRows(pauseRows);const old=await stale.observe();stale.advance(1001);
  assert.equal(stale.adapter.wolfCharactersPauseContinueReady(old),false);
  assert.throws(()=>stale.adapter.wolfCharactersPauseContinue());assert.deepEqual(stale.clicks,[]);
  const wrongSession=harness();wrongSession.setRows(pauseRows);const foreign=await wrongSession.observe();foreign.session='other-session';
  assert.equal(wrongSession.adapter.wolfCharactersPauseContinueReady(foreign),false);
  assert.throws(()=>wrongSession.adapter.wolfCharactersPauseContinue());assert.deepEqual(wrongSession.clicks,[]);
});

test('C opens once only from a newer living Kaeya HUD and always releases the key',async()=>{
  const h=harness(),food=await h.observe();await h.adapter.wolfCharactersFoodClose();
  h.setRows(characterRows);const active=await h.observe();
  assert.equal(h.adapter.wolfCharactersOpenReady(active),true);
  await h.adapter.wolfCharactersOpen();assert.deepEqual(h.keys,[['down','VK_ESCAPE'],['up','VK_ESCAPE'],['down','VK_C'],['up','VK_C']]);
  assert.equal(h.adapter.wolfCharactersOpenReady(active),false);await assert.rejects(h.adapter.wolfCharactersOpen());
  assert.equal(h.adapter.events().filter(e=>e.type==='wolfCharactersOpen').length,1);
  assert.equal(food.hud.world,false);
});

test('menu opening rejects zero HP, enemies, loading, interaction and stale observations before C',async()=>{
  for(const unsafe of [
    {health:{current:0,max:1427}}, {enemyBars:[{width:40}]}, {loading:true}, {interact:true}
  ]) {
    const h=harness(),food=await h.observe();await h.adapter.wolfCharactersFoodClose();
    const base={world:false,groundControls:true,climbing:false,journal:false,bigMap:false,dialogueReady:false,choice:false,tutorialStep:null,
      health:{current:100,max:1427},enemyBars:[],enemyBarDiagnostic:{level:5,candidates:0,localReads:[]},auto:false,loading:false,unknownHud:false,objectiveChanged:false,interact:false};
    h.setRows(characterRows);const active=await h.observe();active.hud={...active.hud,...base,...unsafe};
    assert.equal(h.adapter.wolfCharactersOpenReady(active),false);
    await assert.rejects(h.adapter.wolfCharactersOpen());assert.deepEqual(h.keys,[['down','VK_ESCAPE'],['up','VK_ESCAPE']]);
    assert.equal(food.hud.world,false);
  }
  const stale=harness(),food=await stale.observe();await stale.adapter.wolfCharactersFoodClose();stale.setRows(characterRows);const active=await stale.observe();stale.advance(1001);
  assert.equal(stale.adapter.wolfCharactersOpenReady(active),false);await assert.rejects(stale.adapter.wolfCharactersOpen());assert.deepEqual(stale.keys,[['down','VK_ESCAPE'],['up','VK_ESCAPE']]);
  assert.equal(food.hud.world,false);
});

test('mission reports only character-menu verification and never levels up or consumes food',async()=>{
  let now=2000000,closes=0,opens=0,reads=0;
  const initial=foodObs(),active={...foodObs(),frameId:2,timestamp:2000000,hud:{world:false,groundControls:true,health:{current:100,max:1427},enemyBars:[],interact:false}},menu=menuObs({frameId:4});
  const api={now:()=>now,checkStop(){},sleep:async ms=>{now+=ms;},wolfCharactersFoodCloseReady:()=>true,wolfCharactersFoodClose:async()=>{closes++;},
    wolfCharactersOpenReady:()=>true,wolfCharactersOpen:async()=>{opens++;},wolfCharactersMenuVisible:o=>bgi.wolfCharacterMenuVisible(o,now)};
  const result=await mission.runQuestStep('wolfCharactersOpen',initial,api,async()=>{reads++;return reads===1?active:{...menu,timestamp:now};});
  assert.equal(result.status,'completed',JSON.stringify(result));assert.equal(result.characterMenuVerified,true);assert.equal(result.levelUpAttempts,0);
  assert.equal(Object.hasOwn(result,'foodUseAttempts'),false);assert.equal(closes,1);assert.equal(opens,1);assert.equal(reads,2);
});

test('mission uses one Continue, waits through two HUD fade frames, then sends C once',async()=>{
  let now=2000000,reads=0,calls=0,closes=0,continues=0,opens=0;const inputs=[];
  const initial={...foodObs(),ocr:pauseRows.map(r=>({...r}))};
  const faded=()=>({session,frameId:++reads+1,timestamp:now,map:null,ocr:[row('100/1427',906,1001,104,21)],
    hud:{world:false,groundControls:false,health:{current:100,max:1427},enemyBars:[],interact:false}});
  const active=()=>({session,frameId:++reads+1,timestamp:now,map:null,ocr:characterRows.map(r=>({...r})),
    hud:{world:false,groundControls:true,health:{current:100,max:1427},enemyBars:[],enemyBarDiagnostic:{level:5,candidates:0,localReads:[]},interact:false}});
  const api={now:()=>now,checkStop(){},sleep:async ms=>{now+=ms;},wolfCharactersFoodCloseReady:()=>false,wolfCharactersFoodClose:async()=>{closes++;},
    wolfCharactersPauseContinueReady:o=>o===initial,wolfCharactersPauseContinue:async()=>{continues++;inputs.push('Continue');},
    wolfCharactersOpenReady:o=>o.hud.groundControls===true,wolfCharactersOpen:async()=>{opens++;inputs.push('C');},
    wolfCharactersMenuVisible:o=>bgi.wolfCharacterMenuVisible(o,now)};
  const result=await mission.runQuestStep('wolfCharactersOpen',initial,api,async()=>{
    calls++;
    if(reads<2)return faded();if(reads===2)return active();
    return {...menuObs({frameId:5}),timestamp:now};
  });
  assert.equal(result.status,'completed',JSON.stringify(result));assert.equal(result.characterMenuVerified,true);
  assert.equal(result.inventoryCloseAttempts,0);assert.equal(result.pauseResumeAttempts,1);assert.equal(result.readOnlyPolls,2);
  assert.equal(result.characterMenuAttempts,1);assert.equal(result.levelUpAttempts,0);
  assert.deepEqual(inputs,['Continue','C']);assert.equal(closes,0);assert.equal(continues,1);assert.equal(opens,1);assert.equal(reads,3);assert.equal(calls,4);
});

test('persistent ambiguous pause transition stops after four observations without C',async()=>{
  let now=2000000,reads=0,continues=0,opens=0;
  const initial={...foodObs(),ocr:pauseRows.map(r=>({...r}))};
  const api={now:()=>now,checkStop(){},sleep:async ms=>{now+=ms;},wolfCharactersFoodCloseReady:()=>false,wolfCharactersFoodClose:async()=>{},
    wolfCharactersPauseContinueReady:()=>true,wolfCharactersPauseContinue:async()=>{continues++;},wolfCharactersOpenReady:()=>false,wolfCharactersOpen:async()=>{opens++;},
    wolfCharactersMenuVisible:()=>false};
  const result=await mission.runQuestStep('wolfCharactersOpen',initial,api,async()=>{
    reads++;return {session,frameId:reads+1,timestamp:now,map:null,ocr:[row('Loading...',800,400,180,35)],hud:{world:false,loading:true,groundControls:false}};
  });
  assert.equal(result.status,'stopped');assert.equal(result.pauseResumeAttempts,1);assert.equal(result.inventoryCloseAttempts,0);
  assert.equal(result.readOnlyPolls,3);assert.equal(result.characterMenuAttempts,0);assert.equal(result.characterMenuVerified,false);
  assert.equal(continues,1);assert.equal(opens,0);assert.equal(reads,4);
});

function recoveryHarness({action='selectAmber',expectedCharacter='Kaeya',name='Kaeya',permitPatch={},extraRows=[],ocrRows=null,
    cropValues={amount:0,requiredMora:0,midTierStock:1,mora:1000},writeOk=true,verifyOk=true}={}) {
  let now=2000000,frame=0,rows=[...(ocrRows||menuRows),row(name,1600,130,100,30),...extraRows],permit={kind:'wolfCharacterMenu',session,frameId:1,createdAt:now,materialBudget:1,moraBudget:1000,
    expectedCharacter,action,...permitPatch};const clicks=[],keys=[],holds=[],keyStart={};
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='reports/'+session+'.json'||p==='character-menu-action.json',
      readTextSync:p=>p==='reports/'+session+'.json'?JSON.stringify([party]):p==='character-menu-action.json'?JSON.stringify(!verifyOk&&permit.usedAt?{...permit,requestId:'mismatched-readback'}:permit):fs.readFileSync(path.join(root,p),'utf8'),
      writeTextSync:(p,text)=>{if(p!=='character-menu-action.json')return true;if(!writeOk)return false;permit=JSON.parse(text);return true;},writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:c=>c,contourArea:()=>0}}},
      ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){
        if(this.mat&&this.mat.levelPanelCrop){const vals=[[1480,895,cropValues.amount],[1315,995,cropValues.requiredMora],[1480,832,cropValues.midTierStock],[1665,24,cropValues.mora]],hit=vals.find(v=>v[0]===this.mat.x&&v[1]===this.mat.y),a=hit&&Number.isFinite(hit[2])?[row(String(hit[2]),1,1,20,20)]:[];a.count=a.length;return a;}
        const a=rows.map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows.map(r=>({...r}));a.count=a.length;return a;},
      deriveCrop:(x,y)=>({srcMat:{x,y,resize:()=>({x,y,levelPanelCrop:true}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}}),dispose(){}}),
    keyDown:k=>{keys.push(['down',k]);keyStart[k]=now;},keyUp:k=>{keys.push(['up',k]);holds.push(now-keyStart[k]);delete keyStart[k];},click:(x,y)=>clicks.push([x,y]),sleep:async ms=>{now+=ms;},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);adapter.beginMission({id:'character-recovery-1',mission:'recover',session,createdAt:now,expectedFrameId:1});
  const observe=async()=>adapter.observe(session,++frame);
  return {adapter,observe,clicks,keys,holds,permit:()=>permit,setPermit(v){permit=v;},setRows(v){rows=v.map(r=>({...r}));},advance(ms){now+=ms;},verifyOk};
}

test('recovery action permits reject wrong, stale, expired, used, missing, duplicate, and incomplete evidence',async()=>{
  const cases=[
    {permitPatch:{frameId:2}},
    {permitPatch:{session:'another-session'}},
    {permitPatch:{createdAt:1879999}},
    {permitPatch:{usedAt:1999999}},
    {name:'Traveler'},
    {expectedCharacter:'Amber',name:'Kaeya'},
    {extraRows:[row('Kaeya',1700,150,80,30)]},
    {action:'selectAmber',expectedCharacter:'Amber',extraRows:[row('Q',500,50,20,20)]}
  ];
  for(const opts of cases) {
    const h=recoveryHarness(opts),o=await h.observe();assert.equal(h.adapter.wolfCharacterRecoveryPlan(o),null);
    await assert.rejects(h.adapter.wolfCharacterRecoveryAction());assert.deepEqual(h.clicks,[]);assert.deepEqual(h.keys,[]);
  }
});

test('selectAmber uses the one portrait target, consumes its permit, and cannot replay',async()=>{
  const h=recoveryHarness({extraRows:[row('E',600,50,24,22),row('Q',700,50,24,22)]}),o=await h.observe();
  const plan=h.adapter.wolfCharacterRecoveryPlan(o);assert.equal(plan.action,'selectAmber');assert.equal(plan.selected,'Kaeya');assert.deepEqual([plan.x,plan.y],[960,48]);
  await h.adapter.wolfCharacterRecoveryAction();assert.deepEqual(h.clicks,[[960,48]]);assert.deepEqual(h.keys,[]);
  assert.equal(h.permit().usedAt,2000000);assert.equal(h.permit().requestId,'character-recovery-1');
  await assert.rejects(h.adapter.wolfCharacterRecoveryAction());assert.deepEqual(h.clicks,[[960,48]]);
  assert.equal(h.adapter.events().filter(e=>e.type==='wolfCharacterRecoveryAction').length,1);
});

test('close recovery uses Escape with guaranteed key release and never calls leveling successful',async()=>{
  const h=recoveryHarness({action:'close',expectedCharacter:'Lumina',name:'Lumina'}),o=await h.observe();
  assert.equal(h.adapter.wolfCharacterRecoveryPlan(o).key,'VK_ESCAPE');await h.adapter.wolfCharacterRecoveryAction();
  assert.deepEqual(h.keys,[['down','VK_ESCAPE'],['up','VK_ESCAPE']]);assert.deepEqual(h.holds,[60]);assert.deepEqual(h.clicks,[]);
});

test('openLevel recovery is available only for one exact Amber Level Up button',async()=>{
  const h=recoveryHarness({action:'openLevel',expectedCharacter:'Amber',name:'Amber',extraRows:[row('Level Up',1600,950,120,40)]}),o=await h.observe();
  const plan=h.adapter.wolfCharacterRecoveryPlan(o);assert.equal(plan.action,'openLevel');assert.deepEqual([plan.x,plan.y],[1660,970]);
  await h.adapter.wolfCharacterRecoveryAction();assert.deepEqual(h.clicks,[[1660,970]]);
  for(const opts of [
    {action:'openLevel',expectedCharacter:'Kaeya',name:'Kaeya',extraRows:[row('Level Up',1600,950,120,40)]},
    {action:'openLevel',expectedCharacter:'Amber',name:'Amber'},
    {action:'openLevel',expectedCharacter:'Amber',name:'Amber',extraRows:[row('Level Up',1600,950,120,40),row('Level Up',1600,950,120,40)]}
  ]) {
    const bad=recoveryHarness(opts),fresh=await bad.observe();assert.equal(bad.adapter.wolfCharacterRecoveryPlan(fresh),null);
    await assert.rejects(bad.adapter.wolfCharacterRecoveryAction());assert.deepEqual(bad.clicks,[]);assert.deepEqual(bad.keys,[]);
  }
});

test('XP add and confirm plans require one-book and 1000-Mora caps plus same-frame panel OCR',async()=>{
  for(const [action,amount,requiredMora,target] of [['addXpOne',0,0,[1595,917]],['confirmXpOne',1,1000,[1730,1020]]]) {
    const h=recoveryHarness({action,expectedCharacter:'Amber',name:'Amber',ocrRows:amberLevelRows,
      cropValues:{amount,requiredMora,midTierStock:1,mora:1200}}),o=await h.observe();
    assert.deepEqual({amount:o.hud.wolfAmberLevel.amount,requiredMora:o.hud.wolfAmberLevel.requiredMora,
      midTierStock:o.hud.wolfAmberLevel.midTierStock,mora:o.hud.wolfAmberLevel.mora,frameId:o.hud.wolfAmberLevel.frameId},
      {amount,requiredMora,midTierStock:1,mora:1200,frameId:o.frameId});
    const plan=h.adapter.wolfCharacterRecoveryPlan(o);assert.equal(plan.action,action);assert.deepEqual([plan.x,plan.y],target);
    await h.adapter.wolfCharacterRecoveryAction();assert.deepEqual(h.clicks,[target]);assert.deepEqual(h.keys,[]);
    assert.equal(h.permit().usedAt,2000000);await assert.rejects(h.adapter.wolfCharacterRecoveryAction());assert.deepEqual(h.clicks,[target]);
  }
  const wrongFrame=recoveryHarness({action:'addXpOne',expectedCharacter:'Amber',name:'Amber',ocrRows:amberLevelRows});
  const old=await wrongFrame.observe();old.hud.wolfAmberLevel.frameId=old.frameId-1;
  assert.equal(wrongFrame.adapter.wolfCharacterRecoveryPlan(old),null);await assert.rejects(wrongFrame.adapter.wolfCharacterRecoveryAction());
  assert.deepEqual(wrongFrame.clicks,[]);
});

test('XP actions reject wrong caps, insufficient inventory or Mora, and malformed number crops',async()=>{
  const invalid=[
    {action:'addXpOne',cropValues:{amount:1,requiredMora:1000,midTierStock:1,mora:1000}},
    {action:'addXpOne',cropValues:{amount:0,requiredMora:0,midTierStock:0,mora:1000}},
    {action:'addXpOne',cropValues:{amount:0,requiredMora:0,midTierStock:1,mora:999}},
    {action:'addXpOne',cropValues:{amount:null,requiredMora:0,midTierStock:1,mora:1000}},
    {action:'addXpOne',permitPatch:{materialBudget:2}},
    {action:'addXpOne',permitPatch:{moraBudget:1001}},
    {action:'confirmXpOne',cropValues:{amount:0,requiredMora:0,midTierStock:1,mora:1000}},
    {action:'confirmXpOne',cropValues:{amount:1,requiredMora:1001,midTierStock:1,mora:1000}},
    {action:'confirmXpOne',cropValues:{amount:1,requiredMora:1000,midTierStock:0,mora:1000}},
    {action:'confirmXpOne',cropValues:{amount:1,requiredMora:1000,midTierStock:1,mora:999}},
    {action:'confirmXpOne',expectedCharacter:'Kaeya',name:'Kaeya',cropValues:{amount:1,requiredMora:1000,midTierStock:1,mora:1000}},
    {action:'confirmXpOne',ocrRows:amberLevelRows.filter(r=>r.text!=='Level Up'),cropValues:{amount:1,requiredMora:1000,midTierStock:1,mora:1000}}
  ];
  for(const opts of invalid) {
    const h=recoveryHarness({expectedCharacter:'Amber',name:'Amber',ocrRows:amberLevelRows,...opts}),o=await h.observe();
    assert.equal(h.adapter.wolfCharacterRecoveryPlan(o),null,JSON.stringify(opts));
    await assert.rejects(h.adapter.wolfCharacterRecoveryAction());assert.deepEqual(h.clicks,[]);assert.deepEqual(h.keys,[]);
  }
});

test('closeLevel uses a bounded Escape press with release and no resource or level-up claim',async()=>{
  const h=recoveryHarness({action:'closeLevel',expectedCharacter:'Amber',name:'Amber',ocrRows:amberLevelRows}),initial=await h.observe();
  assert.equal(h.adapter.wolfCharacterRecoveryPlan(initial).key,'VK_ESCAPE');
  const result=await recovery.run(initial,h.adapter,h.observe);
  assert.equal(result.status,'stopped');assert.equal(result.characterMenuAction,'closeLevel');assert.equal(result.levelUpAttempts,0);
  assert.equal(result.foodUseAttempts,0);assert.equal(result.questComplete,false);
  assert.deepEqual(h.keys,[['down','VK_ESCAPE'],['up','VK_ESCAPE']]);assert.deepEqual(h.holds,[60]);assert.deepEqual(h.clicks,[]);
});

test('confirmXpOne reports one attempted click without claiming a level or quest completion',async()=>{
  const h=recoveryHarness({action:'confirmXpOne',expectedCharacter:'Amber',name:'Amber',ocrRows:amberLevelRows,
    cropValues:{amount:1,requiredMora:1000,midTierStock:1,mora:1000}}),initial=await h.observe();
  const result=await recovery.run(initial,h.adapter,h.observe);
  assert.equal(result.status,'stopped');assert.equal(result.characterMenuAction,'confirmXpOne');assert.equal(result.characterMenuAttempts,1);
  assert.equal(result.levelUpAttempts,1);assert.equal(result.foodUseAttempts,0);assert.equal(result.questComplete,false);
  assert.deepEqual(h.clicks,[[1730,1020]]);assert.deepEqual(h.keys,[]);
});

test('permit write or read-back verification failure sends no character input',async()=>{
  const noWrite=recoveryHarness({writeOk:false,extraRows:[row('E',600,50,24,22),row('Q',700,50,24,22)]}),a=await noWrite.observe();
  await assert.rejects(noWrite.adapter.wolfCharacterRecoveryAction());assert.deepEqual(noWrite.clicks,[]);assert.deepEqual(noWrite.keys,[]);
  const noVerify=recoveryHarness({verifyOk:false,extraRows:[row('E',600,50,24,22),row('Q',700,50,24,22)]});
  await noVerify.observe();await assert.rejects(noVerify.adapter.wolfCharacterRecoveryAction());
  assert.deepEqual(noVerify.clicks,[]);assert.deepEqual(noVerify.keys,[]);
});

test('recovery reports one witnessed action with no food use, level-up, or resource claim',async()=>{
  const h=recoveryHarness({action:'close',expectedCharacter:'Lumina',name:'Lumina'}),initial=await h.observe();
  const result=await require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/recovery.js').run(initial,h.adapter,h.observe);
  assert.equal(result.status,'stopped');assert.equal(result.characterMenuAction,'close');assert.equal(result.characterMenuAttempts,1);
  assert.equal(result.levelUpAttempts,0);assert.equal(result.foodUseAttempts,0);assert.equal(result.questComplete,false);
  assert.equal(result.characterMenuResourcesClaimed,undefined);assert.deepEqual(h.keys,[['down','VK_ESCAPE'],['up','VK_ESCAPE']]);
});
