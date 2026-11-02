'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const dir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const heal=require(path.join(dir,'combat-statue-heal.js'));

// The runner fixture grants only its listed inert transitions; the real adapter cases below test their recognition.
function pure(options={}){
  let now=1000,id=1,kind=options.initialKind||'inventory',distance=options.distance===undefined?5:options.distance,
    angle=options.angle===undefined?90:options.angle,unsafe=false;
  const calls=[];
  const source=()=>({session:'heal-test',frameId:id,timestamp:now,kind,map:{map:'Teyvat',x:-1323.474+distance,y:2566.115,cameraAngle:angle},
    hud:{captureStamp:{session:'heal-test',frameId:id,capturedAt:now,source:'game-capture-start'},health:{current:options.healthy?1001:797,max:1001}}});
  const api={now:()=>now,checkStop(){if(options.stop)throw Error('original STOP');},sleep:async ms=>{now+=ms;},combatHealDeadline:()=>90000,
    release:async()=>{calls.push('release');if(options.releaseFailure)throw Error('release failed');},
    combatHealInventoryReady:o=>o.kind==='inventory',combatHealPrepareNavigation:async()=>{calls.push('warm');if(options.expiredWarm)now=90000;},
    combatHealCloseInventory:async()=>{calls.push('Escape');kind='world';},
    combatHealFieldReady:o=>o.kind==='world'&&distance<=15&&!unsafe,
    combatHealRotate:async(o,dx)=>{calls.push(['turn',dx]);if(!options.stalledTurn)angle=0;},
    combatHealForward:async(o,ms)=>{calls.push(['W',ms]);if(!options.stalledMove)distance=2;if(options.unsafeMove)unsafe=true;},
    combatHealInteractReady:o=>o.kind==='world'&&distance<=3&&!options.noPrompt,
    combatHealInteract:async()=>{calls.push('F');kind='dialogue';},
    combatHealBlessingReady:o=>o.kind==='dialogue'&&!options.noChoice,
    combatHealChooseBlessing:async()=>{calls.push('Blessing');kind='panel';},
    combatHealPanelReady:o=>o.kind==='panel'&&!options.noPanel,
    combatHealRunPanel:async()=>{calls.push('panel');if(options.expirePanel)now=90000;return {status:'completed',healthVerified:true,frameId:id,health:{current:1001,max:1001}};}};
  const initial=source();
  const observe=async()=>{if(!options.repeat)id++;const o=source();if(options.reusedStart)o.hud.captureStamp.capturedAt=1000;return o;};
  return {calls,api,run:()=>heal.run(initial,api,observe)};
}
test('runner performs only bounded current-party approach and exact F/Blessing/panel sequence',async()=>{
  const f=pure(),r=await f.run();assert.equal(r.status,'completed');
  assert.deepEqual(f.calls,['warm','Escape',['turn',-250],['W',500],'F','Blessing','panel','release']);
  assert.deepEqual(r.approach,{moves:1,turns:1,interactAttempted:true,blessingChoiceAttempted:true,worldToPanelOwned:true});
});
for(const [name,options,count,kind] of [['turn bound',{stalledTurn:true},12,'turn'],['move bound',{angle:0,stalledMove:true},4,'W']])
test(name+' stops without F or panel fallback',async()=>{
  const f=pure(options),r=await f.run();assert.equal(r.status,'stopped');
  assert.equal(f.calls.filter(c=>Array.isArray(c)&&c[0]===kind).length,count);assert.ok(!f.calls.includes('F'));
});
for(const [name,options] of [['outside15',{distance:15.01}],['unsafe after move',{angle:0,unsafeMove:true}],['missing prompt',{distance:2,noPrompt:true}]])
test(name+' sends no F',async()=>{const f=pure(options),r=await f.run();assert.equal(r.status,'stopped');assert.ok(!f.calls.includes('F'));});
test('missing exact choice never adds Space or a generic recovery fallback',async()=>{
  const f=pure({distance:2,noChoice:true}),r=await f.run();assert.equal(r.status,'stopped');
  assert.deepEqual(f.calls,['warm','Escape','F','release']);
});
test('already sufficient numeric health skips all approach/Statue input',async()=>{
  const f=pure({healthy:true}),r=await f.run();assert.equal(r.healthVerified,true);assert.deepEqual(f.calls,['warm','Escape','release']);
});
for(const options of [{expiredWarm:true},{repeat:true},{reusedStart:true},{initialKind:'map'}])
test('preparation refuses without Escape '+JSON.stringify(options),async()=>{
  const f=pure(options),r=await f.run();assert.equal(r.status,'stopped');assert.ok(!f.calls.includes('Escape'));
});
test('a completed panel result cannot renew the original request deadline',async()=>{
  const f=pure({distance:2,expirePanel:true}),r=await f.run();assert.equal(r.healthVerified,false);assert.match(r.reason,/deadline/);
});
test('primary refusal survives a separate release failure',async()=>{
  const f=pure({initialKind:'map',releaseFailure:true}),r=await f.run();assert.match(r.reason,/inventory required/);assert.deepEqual(r.cleanupErrors,['release failed']);
});

// Reuse the existing real adapter fixture without registering its own tests or changing canonical fixture code.
const fixtureFile=path.join(__dirname,'combat-statue-retreat.test.cjs');
const box={require:n=>n==='node:test'?()=>{}:require(n),module:{exports:{}},__dirname,setImmediate};
vm.runInNewContext(fs.readFileSync(fixtureFile,'utf8')+'\nmodule.exports={actual,row,party};',box,{filename:'healing-retreat-fixture.cjs'});
const row=box.module.exports.row,party=box.module.exports.party;
const panelRows=JSON.parse(fs.readFileSync(path.join(__dirname,'combat-statue-panel.fixture.json'),'utf8')).panel.ocr;
function dialogue(){return [row('UID: 693306810',1684,1050,183,29),row('Auto',100,30,55,25),
  row('Statue of The Seven',785,850,300,35),row("Statue's Blessing",1260,570,301,35),row('Worship Statue',1324,613,229,35)];}
function actual(options={}){
  const hp={text:`${options.health===undefined?797:options.health}/${options.max||1001}`,x:900,y:1002,width:120,height:24};
  const rows=[row('LY.',80,250),row('E',1550,1005,25,25),row('Q',1660,1005,25,25),hp,...party()];
  if(!options.noPrompt)rows.push(row('Statue of The Seven',1200,550,280,30));
  const position={x:-1323.474+(options.distance===undefined?2:options.distance),y:2566.115};
  const f=box.module.exports.actual({uid:options.uid,max:options.max,health:options.health,enemy:options.enemy,
    fixture:{step:'combatStatueHeal',mapPosition:position,fieldRowsSequence:[rows]}});
  let phase=options.initialPanel?'panel':'inventory',angle=options.angle||0,warm=0,portraits=0,offset=0;
  const clicks=[],warmScreens=[],clock=f.context.Date.now.bind(f.context.Date),capture=f.context.captureGameRegion;
  f.context.Date.now=()=>clock()+offset;
  if(options.initialPanel)f.setScreen('field');
  f.context.captureGameRegion=()=>{
    const image=capture();
    if(phase==='dialogue'||phase==='panel'){
      let selected=(phase==='dialogue'?dialogue():panelRows).map(r=>({...r}));
      if(options.noChoice&&phase==='dialogue')selected=selected.filter(r=>r.text!=="Statue's Blessing");
      if(options.foreignDialogue&&phase==='dialogue')selected.find(r=>String(r.text).startsWith('UID')).text='UID: 693306811';
      image.findMulti=ro=>{const found=selected.filter(r=>r.x>=ro.x&&r.x<ro.x+ro.w&&r.y>=ro.y&&r.y<ro.y+ro.h);found.count=found.length;return found;};
    }
    return image;
  };
  Object.defineProperty(f.context.genshin,'LazyNavigationInstance',{get(){warm++;warmScreens.push(f.getScreen());
    if(options.warmFailure)throw Error('retained warm failure');offset+=options.warmMs||0;return {Value:{}};}});
  const down=f.context.keyDown;
  f.context.keyDown=key=>{
    down(key);
    if(key==='VK_ESCAPE'&&phase==='inventory'){phase='world';f.setScreen('field');}
    else if(key==='VK_ESCAPE'&&phase==='panel'){phase='world';f.setScreen('field');}
    else if(key==='VK_F'){phase='dialogue';f.setScreen('field');}
    else if(key==='VK_B'){phase='inventory';f.setScreen('inventory');}
    else if(key==='VK_W'&&!options.stalledMove)position.x=-1323.474+2;
  };
  const move=f.context.moveMouseBy;
  f.context.moveMouseBy=(dx,dy)=>{move(dx,dy);if(!options.stalledTurn)angle=0;};
  f.context.genshin.getCameraOrientation=()=>{f.metrics.orientationCalls++;return angle;};
  f.context.click=(x,y)=>{
    clicks.push({x,y,phase,at:f.context.Date.now()});
    if(phase==='dialogue'){phase='panel';f.setScreen('field');}
    else if(phase==='panel'&&x===658&&y===160){portraits++;if(portraits===3&&!options.noHeal)hp.text='1001/'+(options.postMax||1001);}
    else throw Error('Unexpected click target');
  };
  return {...f,clicks,warmScreens,position,getWarm:()=>warm,getPortraits:()=>portraits,
    run:async()=>f.adapter.runCombatStatueHeal(await f.initial(),f.observe)};
}
const downs=f=>Array.from(f.inputs).filter(e=>e.kind==='down').map(e=>e.key);
test('real adapter warms while paused, uses one F/choice and three Lisa clicks, then verifies numeric health and inventory',async()=>{
  const f=actual({warmMs:2000}),r=await f.run();assert.equal(r.status,'completed',JSON.stringify(r));
  assert.equal(r.healthVerified,true);assert.equal(r.health.current,1001);assert.equal(r.pauseVerified,true);
  assert.deepEqual(f.warmScreens,['inventory']);assert.equal(f.getWarm(),1);
  assert.deepEqual(downs(f),['VK_ESCAPE','VK_F','VK_ESCAPE','VK_B']);
  assert.deepEqual(f.clicks.map(c=>[c.x,c.y]),[[1411,588],[658,160],[658,160],[658,160]]);
  assert.equal(f.nativeCalls.length,0);assert.equal(f.metrics.orientationCalls,0);assert.equal(f.getScreen(),'inventory');
  const e=Array.from(f.adapter.events());assert.ok(e.some(e=>e.type==='combatStatueHealNavigationPreparation'&&e.inputSent===false));
  const p=e.filter(e=>e.type==='combatStatueHealLisaPortrait');assert.equal(p.length,3);
  assert.ok(p.every(e=>e.worldFrameId<e.choiceFrameId&&e.choiceFrameId<e.frameId));
  assert.match(JSON.stringify(e),/combat-statue-panel\.js/);
});
test('real local approach preserves one bounded horizontal turn and forward500 pulse',async()=>{
  const f=actual({distance:5,angle:90}),r=await f.run();assert.equal(r.status,'completed',JSON.stringify(r));
  assert.equal(r.approach.moves,1);assert.equal(r.approach.turns,1);
  assert.equal(downs(f).filter(k=>k==='VK_W').length,1);assert.equal(f.getOverlappingKeyDowns().length,0);
});
for(const [name,options] of [['foreign UID',{uid:'UID: 693306811'}],['missing UID',{uid:false}],['warm failure',{warmFailure:true}],['original deadline',{warmMs:90000}]])
test('real '+name+' leaves inventory without input',async()=>{
  const f=actual(options),r=await f.run();assert.equal(r.status,'stopped');assert.deepEqual(downs(f),[]);assert.equal(f.clicks.length,0);assert.equal(f.getScreen(),'inventory');
});
for(const [name,options] of [['wrong maximum',{max:4015}],['enemies',{enemy:true}],['outside radius',{distance:15.01}]])
test('real '+name+' refuses approach/F and obtains local protection',async()=>{
  const f=actual(options),r=await f.run();assert.equal(r.status,'stopped',JSON.stringify(r));
  assert.equal(r.pauseVerified,true);assert.deepEqual(downs(f),['VK_ESCAPE','VK_B']);assert.equal(f.clicks.length,0);
});
test('real panel layout without this request world/F/choice chain cannot heal',async()=>{
  const f=actual({initialPanel:true}),o=await f.initial();
  assert.equal(!!f.adapter.combatHealPanelReady(o),false);
  await assert.rejects(f.adapter.combatHealRunPanel(o,f.observe),/Owned world-to-panel/);assert.equal(f.clicks.length,0);assert.deepEqual(downs(f),[]);
});
test('real low post-panel health is reported truthfully and protected',async()=>{
  const f=actual({noHeal:true}),r=await f.run();assert.equal(r.healthVerified,false);assert.equal(r.status,'stopped');
  assert.equal(r.pauseVerified,true);assert.equal(r.health.current,797);assert.equal(f.getPortraits(),3);
});
for(const mode of ['age','stop'])test('healing final helper read rechecks '+mode+' before Escape',async()=>{
  const f=actual();let offset=0,reads=0;const clock=f.context.Date.now.bind(f.context.Date),capture=f.context.captureGameRegion;
  f.context.Date.now=()=>clock()+offset;f.context.captureGameRegion=()=>{const image=capture();offset+=500;return image;};
  const o=await f.initial();await f.adapter.combatHealPrepareNavigation(o);
  const read=f.context.file.readTextSync;f.context.file.readTextSync=p=>{const data=read(p);if(p==='world-inventory.js'&&++reads===2){
    if(mode==='age')offset+=501;else f.getVirtualFiles().set('stop.json',JSON.stringify({session:'lion-adapter-test',createdAt:f.getNow()}));}return data;};
  await assert.rejects(f.adapter.combatHealCloseInventory(o),mode==='age'?/inventory changed/:/Stop requested/);
  assert.deepEqual(downs(f),[]);assert.equal(f.getScreen(),'inventory');
});
test('real Engine/mission receipts join both new runners and preserve final inventory',async()=>{
  const f=actual();vm.runInNewContext(fs.readFileSync(path.join(dir,'engine.js'),'utf8'),f.context);
  vm.runInNewContext(fs.readFileSync(path.join(dir,'mission.js'),'utf8'),f.context);
  const engine=f.context.ActOnePilot.create(f.adapter,{session:'lion-adapter-test',enableInput:true});await engine.observe();
  assert.equal(await engine.process({id:'heal-engine-1',session:'lion-adapter-test',mission:'questStep',step:'combatStatueHeal',
    createdAt:f.context.Date.now(),expectedFrameId:engine.getFrame()},()=>f.context.ActOneMission),'completed');
  const receipt=JSON.parse(f.getVirtualFiles().get('receipts/lion-adapter-test/heal-engine-1.json'));
  assert.equal(receipt.details.result.healthVerified,true);assert.equal(receipt.details.result.pauseVerified,true);
  const revision=receipt.details.inputEvents.find(e=>e.type==='controllerRevision');
  assert.deepEqual(Object.keys(revision.files).sort(),['main.js','engine.js','bgi.js','mission.js','combat.js','recovery.js',
    'combat-statue-retreat.js','combat-statue-heal.js','combat-statue-panel.js','world-inventory.js','local-pause.js'].sort());
  assert.equal(f.getOverlappingKeyDowns().length,0);
});
test('inventory-only UI mode cannot acquire the new healing authority',()=>{
  const f=actual(),a=f.context.createActOneAdapter(5,{inventoryUiOnlyV1:true});
  assert.throws(()=>a.beginMission({mission:'questStep',step:'combatStatueHeal',id:'blocked',session:'lion-adapter-test',createdAt:10000}),/Inventory UI-only mode rejects/);
  assert.deepEqual(downs(f),[]);assert.equal(f.getWarm(),0);
});

test('real already sufficient Lisa health does not move, turn, F or click',async()=>{
  const f=actual({health:1001,distance:5,angle:90}),r=await f.run();
  assert.equal(r.healthVerified,true);assert.equal(r.pauseVerified,true);
  assert.deepEqual(downs(f),['VK_ESCAPE','VK_B']);assert.equal(f.clicks.length,0);assert.equal(f.metrics.orientationCalls,0);
});
test('a changed post-panel health maximum never qualifies as Lisa healing',async()=>{
  const f=actual({postMax:4015}),r=await f.run();assert.equal(r.status,'stopped',JSON.stringify(r));
  assert.equal(r.healthVerified,false);assert.equal(r.pauseVerified,true);assert.equal(r.health,undefined);
});
test('mutated public source cannot authorize navigation preparation or Escape',async()=>{
  const f=actual(),o=await f.initial();o.hud.captureStamp.capturedAt--;
  assert.equal(f.adapter.combatHealInventoryReady(o),false);
  await assert.rejects(f.adapter.combatHealPrepareNavigation(o),/Fresh owned inventory/);
  assert.equal(f.getWarm(),0);assert.deepEqual(downs(f),[]);
});


test('missing release refuses before preparation or input',async()=>{
  const f=pure({healthy:true});delete f.api.release;const r=await f.run();
  assert.equal(r.status,'stopped');assert.equal(r.healthVerified,false);
  assert.match(r.reason,/Required owned Statue healing adapter/);assert.deepEqual(f.calls,[]);
});

// Simulate a passive HP change in the same captured numeric row, without fabricating a receipt or native action.
function passiveHealth(f,ready){
  const capture=f.context.captureGameRegion;
  f.context.captureGameRegion=()=>{
    const image=capture(),find=image.findMulti;
    image.findMulti=region=>{const rows=find(region);if(ready())for(const row of rows)if(row.text==='797/1001')row.text='1001/1001';return rows;};
    return image;
  };
}
for(const count of [1,4])test('passive sufficient HP after W'+count+' ends the approach before missing orientation or movement limit',async()=>{
  const f=actual({distance:5,angle:0,stalledMove:true});let moves=0;
  const down=f.context.keyDown;f.context.keyDown=key=>{down(key);if(key==='VK_W')moves++;};
  passiveHealth(f,()=>moves>=count);const r=await f.run();
  assert.equal(r.status,'completed',JSON.stringify(r));assert.equal(r.healthVerified,true);assert.equal(r.moves,count);
  assert.equal(r.interactAttempted,false);assert.equal(r.blessingChoiceAttempted,false);assert.equal(f.clicks.length,0);
  assert.equal(downs(f).filter(key=>key==='VK_W').length,count);assert.ok(!downs(f).includes('VK_F'));
  assert.equal(r.pauseVerified,true);assert.equal(f.getScreen(),'inventory');
});
test('passive sufficient HP after a turn ends the approach without another turn or F',async()=>{
  const f=actual({distance:5,angle:90,stalledTurn:true});let turns=0;
  const move=f.context.moveMouseBy;f.context.moveMouseBy=(dx,dy)=>{move(dx,dy);turns++;};
  passiveHealth(f,()=>turns===1);const r=await f.run();
  assert.equal(r.status,'completed',JSON.stringify(r));assert.equal(r.healthVerified,true);assert.equal(r.turns,1);
  assert.equal(r.moves,0);assert.equal(turns,1);assert.ok(!downs(f).includes('VK_F'));assert.equal(f.clicks.length,0);
  assert.equal(r.pauseVerified,true);assert.equal(f.getScreen(),'inventory');
});
test('passive sufficient HP during prompt settling returns before F',async()=>{
  const f=actual({distance:2,noPrompt:true});let fieldCaptures=0;
  const capture=f.context.captureGameRegion;f.context.captureGameRegion=()=>{if(f.getScreen()==='field')fieldCaptures++;return capture();};
  passiveHealth(f,()=>fieldCaptures>=2);const r=await f.run();
  assert.equal(r.status,'completed',JSON.stringify(r));assert.equal(r.healthVerified,true);assert.equal(r.moves,0);
  assert.equal(r.interactAttempted,false);assert.ok(!downs(f).includes('VK_F'));assert.equal(f.clicks.length,0);
  assert.equal(r.pauseVerified,true);assert.equal(f.getScreen(),'inventory');
});

// Exact retained native JSON is portable evidence; synthetic replay clocks/frames are identified below.
const crypto=require('node:crypto');
const reacquisitionFixture=JSON.parse(fs.readFileSync(path.join(__dirname,'combat-statue-heal-reacquisition.fixture.json'),'utf8'));
const retainedHealFrames={};
for(const document of reacquisitionFixture.documents){
  assert.equal(crypto.createHash('sha256').update(document.utf8,'utf8').digest('hex'),document.sha256);
  retainedHealFrames[document.frameId]=JSON.parse(document.utf8);
}
const retreatFieldGate=require(path.join(dir,'combat-statue-retreat.js'));
const cloneHeal=value=>JSON.parse(JSON.stringify(value));

// Replay the real9→10 conflict through the pure runner; later variants are explicitly synthetic.
function reacquisitionReplay(sequence=['conflict','healthy'],options={}){
  const good=retainedHealFrames[9],bad=retainedHealFrames[10],calls=[];
  let now=good.hud.captureStamp.capturedAt-1000,current=null,reads=0,turns=0,moves=0,nextIndex=0,stopped=false,readyForAgeCheck=false;
  const deadline=now+90000;
  function stamp(o,id,start,completion){
    o.frameId=id;o.timestamp=completion;o.hud.captureStamp.frameId=id;o.hud.captureStamp.capturedAt=start;
    o.hud.combatHealObservation={version:1,session:o.session,frameId:id,observationStartedAtUnixMs:start,phase:'approach'};
    return o;
  }
  const initial=stamp(cloneHeal(good),1,now-50,now);initial.kind='inventory';
  current=initial;
  function fresh(kind){
    const o=stamp(cloneHeal(kind==='conflict'?bad:good),current.frameId+1,now+1,now+21);
    if(kind==='healthy'||kind==='mapless'){
      o.hud.health={current:1001,max:1001};o.hud.healthOcr=['1001/1001'];
      for(const r of o.ocr)if(r.text==='719 /1001')r.text='1001/1001';
    }
    if(kind==='mapless')o.map=null;
    return o;
  }
  const api={
    now:()=>now,checkStop(){if(stopped)throw Error('original STOP');
      if(options.ageFinalCheck&&readyForAgeCheck){readyForAgeCheck=false;now+=1001;} },
    sleep:async ms=>{calls.push(['sleep',ms,current.frameId]);now+=ms;
      if(options.expireRetry&&ms===150&&current.frameId>=10)now=deadline;},
    combatHealDeadline:()=>deadline,
    release:async()=>calls.push(['release']),
    combatHealInventoryReady:o=>o.kind==='inventory',
    combatHealPrepareNavigation:async()=>calls.push(['warm']),
    combatHealCloseInventory:async o=>calls.push(['Escape',o.frameId]),
    combatHealFieldReady:o=>{
      const ready=o===current&&retreatFieldGate.worldReady(o,now,o.session,true)&&
        o.map&&o.map.map==='Teyvat'&&Math.hypot(o.map.x+1323.474,o.map.y-2566.115)<=15;
      if(ready&&o.hud.health.current===1001)readyForAgeCheck=true;
      return ready;
    },
    combatHealRotate:async(o,dx)=>{turns++;calls.push(['turn',o.frameId,dx]);},
    combatHealForward:async(o,ms)=>{moves++;calls.push(['W',o.frameId,ms]);},
    combatHealInteractReady:()=>false,combatHealInteract:async()=>calls.push(['F']),
    combatHealBlessingReady:()=>false,combatHealChooseBlessing:async()=>calls.push(['choice']),
    combatHealPanelReady:()=>false,combatHealRunPanel:async()=>{throw Error('Unexpected panel');},
  };
  async function observe(){
    reads++;let o;
    if(reads===1){o=fresh('safe');o.kind='inventory';}
    else if(reads===2)o=cloneHeal(good);
    else{
      const kind=sequence[Math.min(nextIndex++,sequence.length-1)];
      o=reads===3&&kind==='conflict'?cloneHeal(bad):kind==='protection'?cloneHeal(retainedHealFrames[11]):fresh(kind);
      if(reads===3&&options.mutate)options.mutate(o,current);
    }
    now=Math.max(now,o.timestamp);current=o;calls.push(['observe',o.frameId]);
    if(reads===3&&options.stopAfterConflict)stopped=true;
    return o;
  }
  return {calls,run:()=>heal.run(initial,api,observe),reads:()=>reads,turns:()=>turns,moves:()=>moves};
}

test('retained conflict stays unknown and the next protection frame is not location evidence',()=>{
  const a=retainedHealFrames[9],b=retainedHealFrames[10],c=retainedHealFrames[11];
  assert.equal(retreatFieldGate.worldReady(a,a.timestamp,a.session,true),true);
  assert.equal(b.hud.health,null);assert.equal(b.hud.world,false);assert.equal(b.map,null);
  assert.deepEqual(b.hud.healthDiagnostic,{fullRow:['19/100'],primary:['719/1001'],left:['719'],right:['1001'],decision:'conflict-halves-disagree-or-missing'});
  assert.equal(retreatFieldGate.worldReady(b,b.timestamp,b.session,true),false);
  assert.deepEqual(c.hud.health,{current:719,max:1001});assert.equal(c.hud.combatHealObservation.phase,'protection');assert.equal(c.map,null);
});

test('one numeric conflict permits only passive reacquisition before fresh health completion',async()=>{
  const f=reacquisitionReplay(),r=await f.run();
  assert.equal(r.status,'completed');assert.equal(r.healthVerified,true);assert.deepEqual(r.health,{current:1001,max:1001});
  assert.equal(r.passiveReacquisitionAttempts,1);assert.equal(f.turns(),1);assert.equal(f.moves(),0);
  const after=f.calls.findIndex(c=>c[0]==='observe'&&c[1]===10);
  assert.deepEqual(f.calls.slice(after+1),[['sleep',150,10],['observe',11],['release']]);
});

test('three passive retries are shared across gaps instead of resetting the input limits',async()=>{
  const f=reacquisitionReplay(['conflict','safe','conflict','safe','conflict','safe','conflict','healthy']),r=await f.run();
  assert.equal(r.status,'stopped');assert.equal(r.healthVerified,false);assert.equal(r.passiveReacquisitionAttempts,3);
  assert.equal(f.turns(),4);assert.equal(f.moves(),0);assert.equal(f.reads(),9);
});

test('three exhausted passive retries stop without consuming a later healthy source',async()=>{
  const f=reacquisitionReplay(['conflict','conflict','conflict','conflict','healthy']),r=await f.run();
  assert.equal(r.status,'stopped');assert.equal(r.passiveReacquisitionAttempts,3);assert.equal(f.turns(),1);
  assert.equal(f.reads(),6);assert.equal(r.health,undefined);
});

for(const [name,mutate] of [
  ['raw enemy',o=>o.hud.enemyBarDiagnostic.candidates=1],
  ['final enemy',o=>o.hud.enemyBars.push({x:500,y:250,width:90,height:8})],
  ['climbing',o=>o.hud.climbing=true],['missing ground',o=>o.hud.groundControls=false],
  ['foreign UID',o=>o.ocr.find(r=>r.text.startsWith('UID')).text='UID: 693306811'],
  ['duplicate UID',o=>o.ocr.push(cloneHeal(o.ocr.find(r=>r.text.startsWith('UID'))))],
  ['positive zero health',o=>o.hud.health={current:0,max:1001}],
  ['foreign maximum',o=>o.hud.health={current:719,max:4015}],
  ['missing diagnostic',o=>o.hud.healthDiagnostic=null],
  ['protection phase',o=>o.hud.combatHealObservation.phase='protection'],
  ['foreign source',o=>o.session='foreign'],
  ['stale source',o=>o.hud.captureStamp.capturedAt=o.timestamp-1001],
  ['reused capture start',(o,prior)=>o.hud.captureStamp.capturedAt=prior.hud.captureStamp.capturedAt],
  ['reused completion',(o,prior)=>o.timestamp=prior.timestamp],
])test('reacquisition immediately refuses '+name,async()=>{
  const f=reacquisitionReplay(['conflict','healthy'],{mutate}),r=await f.run();
  assert.equal(r.status,'stopped');assert.equal(r.healthVerified,false);assert.equal(r.passiveReacquisitionAttempts,0);
  assert.equal(f.reads(),3);assert.equal(f.turns(),1);assert.equal(f.moves(),0);
});

test('original STOP prevents the next passive capture',async()=>{
  const f=reacquisitionReplay(['conflict','healthy'],{stopAfterConflict:true}),r=await f.run();
  assert.match(r.reason,/original STOP/);assert.equal(f.reads(),3);assert.equal(r.passiveReacquisitionAttempts,0);
});

test('original deadline expiring during retry spacing prevents capture and further input',async()=>{
  const f=reacquisitionReplay(['conflict','healthy'],{expireRetry:true}),r=await f.run();
  assert.match(r.reason,/deadline/);assert.equal(f.reads(),3);assert.equal(f.turns(),1);assert.equal(r.passiveReacquisitionAttempts,1);
});

for(const kind of ['protection','mapless'])test('fresh numeric health without approach location remains refused: '+kind,async()=>{
  const f=reacquisitionReplay(['conflict',kind]),r=await f.run();
  assert.equal(r.status,'stopped');assert.equal(r.healthVerified,false);assert.equal(r.passiveReacquisitionAttempts,1);
  assert.equal(f.turns(),1);assert.equal(f.moves(),0);assert.equal(f.reads(),4);
});

// Replay retained OCR rows/halves at the actual adapter boundary; game, clock and OCR execution remain inert.
function actualReacquisition(options={}){
  const f=actual({health:719,distance:options.prompt?2:5,angle:90,stalledTurn:true,noPrompt:!!options.prompt});
  let turns=0,fieldCaptures=0,delivered=false,mode='normal';
  const move=f.context.moveMouseBy,capture=f.context.captureGameRegion,ImageRegion=f.context.ImageRegion;
  f.context.moveMouseBy=(dx,dy)=>{turns++;move(dx,dy);};
  f.context.captureGameRegion=()=>{
    const image=capture();
    if(f.getScreen()==='field')fieldCaptures++;
    mode=f.getScreen()==='field'&&(options.prompt?fieldCaptures>=2:turns>0)?(delivered?'healthy':'conflict'):'normal';
    if(mode==='normal')return image;
    const source=cloneHeal(retainedHealFrames[mode==='conflict'?10:9]);
    if(mode==='conflict')delivered=true;
    else for(const r of source.ocr)if(r.text==='719 /1001')r.text='1001/1001';
    image.findMulti=ro=>{
      const rows=source.ocr.filter(r=>r.x>=ro.x&&r.x<ro.x+ro.w&&r.y>=ro.y&&r.y<ro.y+ro.h);
      rows.count=rows.length;return rows;
    };
    return image;
  };
  f.context.ImageRegion=class extends ImageRegion{
    findMulti(ro){
      const rect=this.srcMat.rect,d=retainedHealFrames[10].hud.healthDiagnostic;
      const text=mode==='conflict'&&rect&&(rect.x===900&&rect.y===990?d.primary:rect.x===893&&rect.y===998?d.left:rect.x===967&&rect.y===998?d.right:null);
      if(text){const rows=text.map(t=>row(t,1,1,90,20));rows.count=rows.length;return rows;}
      return super.findMulti(ro);
    }
  };
  return {...f,turns:()=>turns};
}

test('actual adapter reacquires exact conflicting OCR without carrying HP or another input',async()=>{
  const f=actualReacquisition(),r=await f.run();
  assert.equal(r.status,'completed',JSON.stringify(r));assert.equal(r.healthVerified,true);assert.equal(r.pauseVerified,true);
  assert.equal(r.health.current,1001);assert.equal(r.passiveReacquisitionAttempts,1);assert.equal(f.turns(),1);
  assert.deepEqual(downs(f),['VK_ESCAPE','VK_B']);assert.equal(f.clicks.length,0);
  const bad=f.observations.find(o=>o.hud.healthDiagnostic&&o.hud.healthDiagnostic.decision==='conflict-halves-disagree-or-missing');
  assert.ok(bad);assert.equal(bad.hud.health,null);assert.equal(bad.map,null);assert.equal(bad.hud.world,false);
  assert.deepEqual(JSON.parse(JSON.stringify(bad.hud.healthDiagnostic)),retainedHealFrames[10].hud.healthDiagnostic);
  const fresh=f.observations.find(o=>o.frameId>bad.frameId&&o.hud.health&&o.hud.health.current===1001&&o.map);
  assert.ok(fresh);assert.ok(fresh.hud.captureStamp.capturedAt>bad.timestamp);assert.equal(f.getScreen(),'inventory');
});

test('actual Engine receipt preserves one passive retry and qualified final inventory',async()=>{
  const f=actualReacquisition();
  vm.runInNewContext(fs.readFileSync(path.join(dir,'engine.js'),'utf8'),f.context);
  vm.runInNewContext(fs.readFileSync(path.join(dir,'mission.js'),'utf8'),f.context);
  const engine=f.context.ActOnePilot.create(f.adapter,{session:'lion-adapter-test',enableInput:true});
  await engine.observe();
  assert.equal(await engine.process({id:'heal-reacquire-engine',session:'lion-adapter-test',mission:'questStep',step:'combatStatueHeal',
    createdAt:f.context.Date.now(),expectedFrameId:engine.getFrame()},()=>f.context.ActOneMission),'completed');
  const receipt=JSON.parse(f.getVirtualFiles().get('receipts/lion-adapter-test/heal-reacquire-engine.json'));
  assert.equal(receipt.details.result.passiveReacquisitionAttempts,1);assert.equal(receipt.details.result.healthVerified,true);
  assert.equal(receipt.details.result.pauseVerified,true);assert.deepEqual(downs(f),['VK_ESCAPE','VK_B']);
  assert.equal(f.getOverlappingKeyDowns().length,0);assert.equal(f.nativeCalls.length,0);
});


test('actual prompt settling reacquires conflicting OCR before any F or movement',async()=>{
  const f=actualReacquisition({prompt:true}),r=await f.run();
  assert.equal(r.status,'completed',JSON.stringify(r));assert.equal(r.healthVerified,true);assert.equal(r.pauseVerified,true);
  assert.equal(r.passiveReacquisitionAttempts,1);assert.equal(r.health.current,1001);assert.equal(f.turns(),0);
  assert.deepEqual(downs(f),['VK_ESCAPE','VK_B']);assert.equal(f.clicks.length,0);
});


test('final blocking STOP check cannot turn an aged reacquired source into a health claim',async()=>{
  const f=reacquisitionReplay(['conflict','healthy'],{ageFinalCheck:true}),r=await f.run();
  assert.equal(r.status,'stopped');assert.equal(r.healthVerified,false);assert.equal(r.passiveReacquisitionAttempts,1);
  assert.equal(f.turns(),1);assert.equal(f.reads(),4);assert.equal(r.health,undefined);
});
