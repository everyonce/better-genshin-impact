const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
function frame(name='Fowl',patch={}) {
  const o={session:'wolf',frameId:236,timestamp:10000,map:null,
    ocr:[{text:'Trial',x:1796,y:463},{text:'Kaeya',x:1663,y:484},{text:'F',x:1100,y:449},
      {text:name,x:1214,y:447},{text:"Adventurer's Flower",x:1218,y:520},{text:"Wanderer's Advice",x:1220,y:596}],
    hud:{world:false,health:{current:1361,max:1427},groundControls:true,interact:true,enemyBars:[{width:38}],auto:false}};
  return {...o,...patch,hud:{...o.hud,...patch.hud}};
}
test('known selected loot is anchored to one F; unselected rows never authorize a pickup',()=>{
  assert.equal(bgi.wolfLootTarget(frame(),10000),'Fowl');
  assert.equal(bgi.wolfLootTarget(frame("Wanderer's Advice"),10000),"Wanderer's Advice");
  for(const bad of [frame('Leave Domain?'),frame('Common Chest'),frame('Unknown Item'),frame('Fowl',{timestamp:8999}),
    frame('Fowl',{hud:{health:{current:800,max:1427}}}),frame('Fowl',{hud:{health:null}}),
    frame('Fowl',{hud:{climbing:true}}),frame('Fowl',{hud:{choice:true}}),frame('Fowl',{hud:{loading:true}}),
    frame('Fowl',{hud:{unknownHud:true}}),frame('Fowl',{hud:{interact:false}}),frame('Fowl',{map:{map:'Teyvat'}}),
    frame('Fowl',{ocr:frame().ocr.filter(r=>r.text!=='F')}),frame('Fowl',{ocr:[...frame().ocr,{text:'F',x:1100,y:520}]}),
    frame('Fowl',{ocr:[...frame().ocr,{text:'Fowl',x:1218,y:447}]})])
    assert.equal(bgi.wolfLootTarget(bad,10000),null);
  assert.equal(bgi.wolfLootTarget(frame(),10000,{current:1427,max:1427}),'Fowl');
  assert.equal(bgi.wolfLootTarget(frame(),10000,{current:1433,max:1427}),null,'more than 5% health loss blocks the next pickup');
});
test('paused loot request continues once and observes each selected item before a maximum of four F presses',async()=>{
  let now=10000,reads=0;const calls=[];
  const api={checkStop(){},wolfLootContinueReady:o=>o.paused===true,wolfContinue:()=>calls.push('continue'),
    wolfLootReady:(o,base)=>!!bgi.wolfLootTarget(o,now,base),
    wolfLootInteract:async()=>{calls.push('F');return 'Fowl';},sleep:async ms=>{now+=ms;}};
  const r=await mission.runQuestStep('wolfLootInteract',{paused:true},api,async()=>{reads++;return frame('Fowl',{frameId:236+reads,timestamp:now});});
  assert.equal(r.lootAttempts,4);assert.equal(r.continueAttempts,1);assert.equal(reads,5);assert.deepEqual(calls,['continue','F','F','F','F']);
});
test('fresh unknown prompt and health loss stop loot input without reusing the previous prompt',async()=>{
  let now=10000,reads=0;const calls=[];
  const api={checkStop(){},wolfLootContinueReady:()=>false,wolfContinue(){throw Error('unexpected continue');},
    wolfLootReady:(o,base)=>!!bgi.wolfLootTarget(o,now,base),
    wolfLootInteract:async()=>{calls.push('F');return 'Fowl';},sleep:async ms=>{now+=ms;}};
  for(const after of [frame('Leave Domain?'),frame('Fowl',{hud:{health:{current:1289,max:1427}}})]) {
    calls.length=0;reads=0;
    const r=await mission.runQuestStep('wolfLootInteract',frame('Fowl',{timestamp:now}),api,async()=>{reads++;return {...after,timestamp:now};});
    assert.equal(r.lootAttempts,1);assert.equal(reads,1);assert.deepEqual(calls,['F']);
  }
});
test('adapter requires the same-session Wolf entry, correct step, fresh distinct frames, four-pick cap, and key release',async()=>{
  const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
  async function run({entry=true,step='wolfLootInteract'}={}) {
    let now=10000;const keys=[];
    const party={session:'wolf',mission:'questStep',status:'completed',timestamp:9500,
      details:{result:{step:'wolfPartyStart'},inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:20,x:1705,y:1019,startedAt:9400}]}};
    const context={Date:class extends Date{static now(){return now;}},genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true},
      file:{isExists:()=>false,writeTextSync:()=>true,readTextSync:p=>p==='reports/wolf.json'?JSON.stringify(entry?[party]:[]):fs.readFileSync(path.join(root,p),'utf8')},
      keyDown:k=>keys.push(['down',k]),keyUp:k=>keys.push(['up',k]),sleep:async ms=>{now+=ms;}};
    vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
    const a=context.createActOneAdapter(7),request={mission:'questStep',step,session:'wolf',expectedFrameId:236,createdAt:now};a.beginMission(request);
    a.seedObservation(frame('Fowl',{timestamp:now}));
    if(!entry||step!=='wolfLootInteract'){await assert.rejects(a.wolfLootInteract());assert.deepEqual(keys,[]);return;}
    await a.wolfLootInteract();await assert.rejects(a.wolfLootInteract());
    // Advance the verified fixture seed; live missions obtain each new frame through observe().
    for(let i=1;i<4;i++){request.expectedFrameId=236+i;a.seedObservation(frame('Fowl',{frameId:236+i,timestamp:now}));await a.wolfLootInteract();}
    request.expectedFrameId=240;a.seedObservation(frame('Fowl',{frameId:240,timestamp:now}));await assert.rejects(a.wolfLootInteract());
    assert.deepEqual(keys,Array.from({length:4},()=>[['down','VK_F'],['up','VK_F']]).flat());
    assert.equal(a.events().filter(e=>e.type==='wolfLootInteract').length,4);
  }
  await run();await run({entry:false});await run({step:'wolfForward'});
});
