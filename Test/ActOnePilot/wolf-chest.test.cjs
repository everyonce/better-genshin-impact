const test=require('node:test');
const assert=require('node:assert/strict');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
function frame(patch={}) {
  const o={session:'wolf',frameId:210,timestamp:10000,map:null,
    ocr:[{text:'Trial',x:1798,y:463},{text:'Kaeya',x:1665,y:487},{text:'F',x:1098,y:522},{text:'Common Chest',x:1214,y:518}],
    hud:{world:false,health:{current:1427,max:1427},groundControls:true,interact:true,enemyBars:[],auto:false}};
  return {...o,...patch,hud:{...o.hud,...patch.hud}};
}
test('Wolf chest interaction requires fresh unique Common Chest and F with healthy grounded Kaeya',()=>{
  assert.equal(bgi.wolfChestReady(frame(),10000),true);
  for(const bad of [frame({timestamp:8999}),frame({hud:{health:{current:800,max:1427}}}),
    frame({hud:{health:null}}),frame({hud:{enemyBars:[{}]}}),frame({hud:{climbing:true}}),frame({hud:{choice:true}}),
    frame({hud:{interact:false}}),frame({hud:{loading:true}}),frame({map:{map:'Teyvat'}}),
    frame({ocr:frame().ocr.filter(r=>r.text!=='F')}),frame({ocr:[...frame().ocr,{text:'Common Chest',x:1214,y:518}]}),
    frame({ocr:frame().ocr.map(r=>r.text==='Common Chest'?{...r,text:'Leave Domain?'}:r)})])
    assert.equal(bgi.wolfChestReady(bad,10000),false);
});
test('a paused chest step continues once, then verifies the fresh prompt before one F',async()=>{
  let now=10000,reads=0;const calls=[];
  const api={checkStop(){},wolfChestContinueReady:o=>o.paused===true,wolfContinue:()=>calls.push('continue'),
    wolfChestReady:o=>bgi.wolfChestReady(o,now),wolfChestInteract:async()=>calls.push('F'),sleep:async ms=>{now+=ms;}};
  const r=await mission.runQuestStep('wolfChestInteract',{paused:true},api,async()=>{reads++;return frame({timestamp:now});});
  assert.equal(r.chestAttempts,1);assert.equal(r.continueAttempts,1);assert.equal(reads,2);assert.deepEqual(calls,['continue','F']);
});
test('after one Continue an unknown or enemy screen gets read-only polls and no F',async()=>{
  for(const bad of [{hud:{enemyBars:[{}]}},{ocr:[]},{hud:{health:null}}]) {
    let now=10000,reads=0;const calls=[];
    const api={checkStop(){},wolfChestContinueReady:()=>true,wolfContinue:()=>calls.push('continue'),
      wolfChestReady:o=>bgi.wolfChestReady(o,now),wolfChestInteract:async()=>calls.push('F'),sleep:async ms=>{now+=ms;}};
    const r=await mission.runQuestStep('wolfChestInteract',{paused:true},api,async()=>{reads++;return frame({...bad,timestamp:now});});
    assert.equal(r.status,'stopped');assert.equal(r.chestAttempts,0);assert.equal(reads,4);assert.deepEqual(calls,['continue']);
  }
});
test('adapter requires entry proof and correct request, permits only one F, and releases it',async()=>{
  const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
  async function run({entry=true,step='wolfChestInteract'}={}) {
    let now=10000;const keys=[];
    const party={session:'wolf',mission:'questStep',status:'completed',timestamp:9500,
      details:{result:{step:'wolfPartyStart'},inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:20,x:1705,y:1019,startedAt:9400}]}};
    const context={Date:class extends Date{static now(){return now;}},
      genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true},
      file:{isExists:()=>false,writeTextSync:()=>true,readTextSync:p=>p==='reports/wolf.json'?JSON.stringify(entry?[party]:[]):fs.readFileSync(path.join(root,p),'utf8')},
      keyDown:k=>keys.push(['down',k]),keyUp:k=>keys.push(['up',k]),sleep:async ms=>{now+=ms;}};
    vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
    const a=context.createActOneAdapter(7);
    a.beginMission({mission:'questStep',step,session:'wolf',expectedFrameId:210,createdAt:10000});
    a.seedObservation(frame());
    if(!entry||step!=='wolfChestInteract') {await assert.rejects(a.wolfChestInteract());assert.deepEqual(keys,[]);return;}
    await a.wolfChestInteract();await assert.rejects(a.wolfChestInteract());
    assert.deepEqual(keys,[['down','VK_F'],['up','VK_F']]);
  }
  await run();await run({entry:false});await run({step:'wolfForward'});
});
