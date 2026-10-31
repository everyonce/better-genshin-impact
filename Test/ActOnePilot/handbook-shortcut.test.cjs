const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const engine=require(path.join(root,'engine.js'));
const handbookGate=require(path.join(root,'act-two-handbook.js'));
const mission=require(path.join(root,'mission.js'));

// Exercise the ordinary request runner against fresh world and handbook observations.
function world() {
  return {map:{x:-1265,y:2441,map:'Teyvat'},hud:{world:true,groundControls:true,
    journal:false,bigMap:false,choice:false,dialogueReady:false,climbing:false,auto:false,
    lowHealth:false,health:{current:2220,max:2764},enemyBars:[]}};
}
function handbook() {
  return {session:'handbook-test',timestamp:100000,map:null,
    hud:{world:false,journal:false,bigMap:false,choice:false,dialogueReady:false,auto:false},
    ocr:[['Experience',240,240],['Domains',240,340],['Enemies',240,440],['Guide',240,540],['X',1650,210]]
      .map(([text,x,y])=>({text,x,y,width:70,height:25}))};
}
function fixture(observations=[world()],enableInput=true) {
  let now=100000,index=0;const inputs=[],writes=[];
  const api={now:()=>now,sleep:async ms=>{now+=ms;},beginMission:()=>{},checkStop:()=>{},
    events:()=>inputs,requireInputReady:()=>{},release:()=>{},seedObservation:()=>true,
    observe:async(_,frameId)=>({timestamp:now,screenshotPath:'frame-'+frameId+'.png',
      ...observations[Math.min(index++,observations.length-1)]}),
    write:(name,value)=>writes.push([name,JSON.parse(value)]),keyPress:async key=>inputs.push(key)};
  const runner=engine.create(api,{session:'handbook-test',enableInput});
  const request=key=>({session:'handbook-test',id:'shortcut-'+key,createdAt:now,
    expectedFrameId:runner.getFrame(),mission:'keyPress',key});
  return {api,runner,request,inputs,writes};
}
// Load the real adapter so Escape tests cover the OCR gate and session binding together.
function closeAdapter() {
  const context={Date:class extends Date{static now(){return 100000;}},
    file:{isExists:()=>false,writeTextSync:()=>true,readTextSync:name=>fs.readFileSync(path.join(root,name),'utf8')},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:3,isGameForeground:true}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(3);
  adapter.beginMission({session:'handbook-test',mission:'keyPress',key:'VK_ESCAPE'});
  return adapter;
}

test('fresh healthy ground view opens the handbook once and observes after settling',async()=>{
  const f=fixture([world(),world(),handbook()]);await f.runner.observe();
  assert.equal(await f.runner.process(f.request('VK_F1'),()=>({})),'completed');
  assert.deepEqual(f.inputs,['VK_F1']);
  const receipt=f.writes.filter(([name])=>name==='receipt.json').at(-1)[1];
  assert.equal(receipt.status,'completed');assert.equal(f.api.now(),100900);
});

test('handbook opening rejects unhealthy, ambiguous, combat, climbing, stale, and future scenes',async()=>{
  const badHud=[{health:null},{health:{current:0,max:2764}},{health:{current:2220,max:0}},
    {health:{current:1658,max:2764}},{health:{current:3000,max:2764}},
    {health:{current:NaN,max:2764}},{lowHealth:true},{world:false},{groundControls:false},
    {enemyBars:[{x:20,y:20}]},{enemyBars:undefined},{climbing:true},{auto:true},
    {choice:true},{dialogueReady:true},{journal:true},{bigMap:true}];
  const invalid=badHud.map(patch=>({...world(),hud:{...world().hud,...patch}}));
  invalid.push({...world(),map:null},{...world(),timestamp:98999},{...world(),timestamp:100001});
  for(const observation of invalid){
    const f=fixture([world(),observation]);await f.runner.observe();
    await assert.rejects(f.runner.process(f.request('VK_F1'),()=>({})),/not valid in the recognized screen/);
    assert.deepEqual(f.inputs,[],JSON.stringify(observation));
  }
});

test('handbook keys retain disabled-input, focus, session, and frame protections',async()=>{
  for(const key of ['VK_F1','VK_ESCAPE']){
    const f=fixture([world()],false);await f.runner.observe();
    await assert.rejects(f.runner.process(f.request(key),()=>({})),/disabled/);assert.deepEqual(f.inputs,[]);
  }
  const focus=fixture();await focus.runner.observe();focus.api.requireInputReady=()=>{throw Error('foreground lost');};
  await assert.rejects(focus.runner.process(focus.request('VK_F1'),()=>({})),/foreground/);
  assert.deepEqual(focus.inputs,[]);
  for(const patch of [{session:'other'},{expectedFrameId:0},{key:'VK_F2'}]){
    const f=fixture();await f.runner.observe();
    assert.equal(await f.runner.process({...f.request('VK_F1'),...patch},()=>({})),'rejected');
    assert.deepEqual(f.inputs,[]);assert.equal(f.runner.getFrame(),1);
  }
});

test('real adapter recognizes only fresh same-session handbook anchors for Escape',()=>{
  const adapter=closeAdapter(),good=handbook();assert.equal(adapter.handbookCloseReady(good),true);
  const invalid=[{...good,session:'other'},{...good,timestamp:98999},{...good,timestamp:100001},
    {...good,map:{x:1,y:2}},{...good,ocr:[{text:'Inventory',x:10,y:10}]}];
  for(const key of ['world','journal','bigMap','choice','dialogueReady','auto'])
    invalid.push({...good,hud:{...good.hud,[key]:true}});
  for(const row of good.ocr)invalid.push({...good,ocr:good.ocr.filter(other=>other!==row)});
  for(const observation of invalid)assert.equal(adapter.handbookCloseReady(observation),false,JSON.stringify(observation));
});

test('recognized handbook closes with one Escape and unknown panels receive no input',async()=>{
  const f=fixture([handbook(),handbook(),world()]);f.api.handbookCloseReady=closeAdapter().handbookCloseReady;
  await f.runner.observe();assert.equal(await f.runner.process(f.request('VK_ESCAPE'),()=>({})),'completed');
  assert.deepEqual(f.inputs,['VK_ESCAPE']);
  for(const recognizer of [undefined,()=>false]){
    const denied=fixture([handbook()]);denied.api.handbookCloseReady=recognizer;await denied.runner.observe();
    await assert.rejects(denied.runner.process(denied.request('VK_ESCAPE'),()=>({})),/not valid in the recognized screen/);
    assert.deepEqual(denied.inputs,[]);
  }
});

test('existing map and journal Escape remain available without a handbook match',async()=>{
  for(const field of ['bigMap','journal']){
    const observation={map:null,hud:{world:false,[field]:true}},f=fixture([observation]);
    f.api.handbookCloseReady=closeAdapter().handbookCloseReady;await f.runner.observe();
    assert.equal(await f.runner.process(f.request('VK_ESCAPE'),()=>({})),'completed');assert.deepEqual(f.inputs,['VK_ESCAPE']);
  }
});

// Preserve the observed header casing while requiring each menu row at its recorded location.
function allEnemies(popup=false) {
  const page=handbook();page.ocr.push({text:'AlL',x:406,y:193,width:39,height:26});
  if(popup)page.ocr.push({text:'Easy',x:401,y:294,width:51,height:30},
    {text:'Elite Enemies',x:402,y:353,width:160,height:30},
    {text:'Boss Enemies',x:399,y:407,width:160,height:30});
  else page.ocr.push({text:'Navigate',x:1387,y:822,width:120,height:35});
  return page;
}

test('Easy category opens only on the known All page and selects only the visible popup row',()=>{
  assert.deepEqual(handbookGate.target(allEnemies(),100000,null,'easyCategory'),
    {action:'openEasyEnemyCategory',x:695,y:204});
  assert.deepEqual(handbookGate.target(allEnemies(true),100000,null,'easySelect'),
    {action:'selectEasyEnemies',x:427,y:309});
  assert.equal(handbookGate.target(allEnemies(),100000,null,'easySelect'),null);
  assert.equal(handbookGate.target(allEnemies(true),100000,null,'easyCategory'),null);
  for(const [page,operation] of [[allEnemies(),'easyCategory'],[allEnemies(true),'easySelect']]){
    for(const row of page.ocr)assert.equal(handbookGate.target({...page,ocr:page.ocr.filter(other=>other!==row)},100000,null,operation),null);
    for(const now of [99999,101001,NaN])assert.equal(handbookGate.target(page,now,null,operation),null);
    for(const key of ['world','journal','bigMap','choice','dialogueReady','auto','climbing','groundControls'])
      assert.equal(handbookGate.target({...page,hud:{...page.hud,[key]:true}},100000,null,operation),null);
  }
  const duplicate=allEnemies(true);duplicate.ocr.push({...duplicate.ocr.find(row=>row.text==='Easy')});
  assert.equal(handbookGate.target(duplicate,100000,null,'easySelect'),null);
  const invalidBounds=allEnemies(true);invalidBounds.ocr.find(row=>row.text==='Easy').width=2000;
  assert.equal(handbookGate.target(invalidBounds,100000,null,'easySelect'),null);
});

test('mission routing keeps the two Easy steps separate from claims and navigation',async()=>{
  for(const [step,mode,action] of [['actTwoHandbookEasyCategory','easyCategory','openEasyEnemyCategory'],
    ['actTwoHandbookEasySelect','easySelect','selectEasyEnemies']]){
    const calls=[],api={actTwoHandbookClaim:async value=>{calls.push(value);return {action};},sleep:async()=>{}};
    const result=await mission.runQuestStep(step,handbook(),api,async()=>({...handbook(),frameId:2}));
    assert.deepEqual(calls,[mode]);assert.equal(result.status,'completed');
    assert.equal(result.claimAttempted,false);assert.equal(result.action,action);
  }
});
