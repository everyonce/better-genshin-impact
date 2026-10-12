const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
global.ActOneCombat=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/combat.js');

const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=50,height=20)=>({text,x,y,width,height});
const entry=[
  {session:'wolf',mission:'questStep',status:'completed',timestamp:1000,details:{result:{step:'wolfStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[{type:'wolfDomainStart',label:'Deep Within the Temple of the Wolf',startedAt:900}]}},
  {session:'wolf',mission:'questStep',status:'completed',timestamp:1500,details:{result:{step:'wolfPartyStart'},inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:2,x:1700,y:1019,startedAt:1400}]}}
];

function fixture({health='731/1427',focus=true,entryRows=entry,bar=true,throwKey=null}={}) {
  let now=2000,frame=0,phase='pause',foreground=focus;const keys=[],clicks=[];
  const rows=()=>phase==='pause'?[row('Continue Challenge',831,399,287,40),row('Lower Difficulty',849,518,251,42),row('Leave Domain?',864,640,221,36)]:[
    row('Kaeya',1664,485,90,38),row('Trial',1802,463,43,22),row(health,910,1002,100,18),row('Lv.5',930,430,35,15)];
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:foreground,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:()=>false,readTextSync:p=>p==='reports/wolf.json'?JSON.stringify(entryRows):fs.readFileSync(path.join(root,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x},ColorConversionCodes:{GRAY2BGR:0}}},
    ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const a=(this.mat.rows||[]).map(x=>({...x}));a.count=a.length;return a;}dispose(){}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows().map(x=>({...x}));a.count=a.length;return a;},deriveCrop:(x,y)=>{
      if(x===1520&&y===985)return {srcMat:{resize:()=>({rows:phase==='pause'?[]:[row('E',840,110,40,30)]})},dispose(){}};
      if(x===1630&&y===330)return {srcMat:{resize:()=>({rows:[row('Kaeya',100,450),row('Trial',500,400)]})},dispose(){}};
      if(x===900&&y===990)return {srcMat:{resize:()=>({rows:phase==='pause'?[]:[row(health,20,20,250,45)]})},dispose(){}};
      if(x===350&&y===100)return {srcMat:{inRange:()=>({findContoursAsArray:()=>bar&&phase!=='pause'?[{x:550,y:360,width:90,height:8}]:[],dispose(){}})},dispose(){}};
      if(x===893&&y===998||x===967&&y===998)return {srcMat:{resize:()=>({rows:[]})},dispose(){}};
      return {srcMat:{resize:()=>({rows:[]}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}};
    },dispose(){}}),
    keyDown:key=>{keys.push(['down',key,now]);if(key===throwKey)throw new Error('test keyDown failure');if(key==='VK_ESCAPE')phase='pause';},keyUp:key=>keys.push(['up',key,now]),click:(x,y)=>{clicks.push([x,y]);phase='active';},moveMouseBy(){},sleep:async ms=>{now+=ms;},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const api=context.createActOneAdapter(7);api.beginMission({mission:'questStep',step:'wolfRecoveryCombat',session:'wolf',createdAt:1900});
  async function observe(){frame++;return api.observe('wolf',frame);}
  return {api,observe,keys,clicks,setFocus:v=>{foreground=v;context.genshin.isGameForeground=v;},setHealth:v=>{health=v;},setBar:v=>{bar=v;}};
}

test('real pause schema runs one guarded recovery rotation and returns to a verified pause at 51%',async()=>{
  const f=fixture();const paused=await f.observe();
  assert.equal(paused.hud.health,null);assert.equal(paused.hud.groundControls,false);
  assert.equal(f.api.wolfRecoveryCombatContinueReady(paused),true);
  const result=await mission.runQuestStep('wolfRecoveryCombat',paused,f.api,f.observe);
  assert.equal(result.continueAttempts,1);assert.equal(result.hpInitial,731);assert.equal(result.maxHp,1427);
  assert.equal(result.pauseVerified,true,result.reason);assert.equal(result.combatComplete,false);assert.equal(result.questComplete,false);
  assert.equal(f.clicks.length,1);assert.ok(result.actionCounts.VK_LBUTTON>0);
  assert.equal(f.api.wolfRecoveryCombatContinueReady(paused),false,'the same request cannot Continue twice');
  assert.deepEqual(f.keys.filter(x=>x[0]==='down').map(x=>x[1]).filter(k=>['VK_Q','VK_W','VK_3'].includes(k)),[]);
  assert.ok(f.keys.every((e,i,a)=>e[0]!=='down'||a[i+1]&&a[i+1][0]==='up'&&a[i+1][1]===e[1]),'all combat and Escape inputs are released');
});

test('recovery pause provenance rejects stale frame, wrong session, focus loss, bad max HP, UI and missing bars',async()=>{
  const f=fixture();const paused=await f.observe();assert.equal(f.api.wolfRecoveryCombatContinueReady({...paused,frameId:paused.frameId-1}),false);
  assert.equal(f.api.wolfRecoveryCombatContinueReady({...paused,session:'other'}),false);
  assert.equal(f.api.wolfRecoveryCombatContinueReady({...paused,timestamp:paused.timestamp-2000}),false);
  assert.equal(f.api.wolfRecoveryCombatContinueReady({...paused,hud:{...paused.hud,unknownHud:true}}),false);
  f.setFocus(false);assert.throws(()=>f.api.wolfRecoveryCombatContinueReady(paused),/foreground/);f.setFocus(true);
  f.api.wolfRecoveryCombatContinue();const active=await f.observe();f.api.wolfRecoveryCombatBegin(active);
  f.setHealth('731/1500');await f.observe();await assert.rejects(()=>f.api.wolfRecoveryCombatKey('VK_E'));
  f.setHealth('440/1427');await f.observe();await assert.rejects(()=>f.api.wolfRecoveryCombatKey('VK_E'),/guards/);
  const g=fixture({bar:false});const p=await g.observe();g.api.wolfRecoveryCombatContinue();const a=await g.observe();g.api.wolfRecoveryCombatBegin(a);
  await assert.rejects(()=>g.api.wolfRecoveryCombatKey('VK_LBUTTON'));
});

test('adapter enforces the 30 percent floor, 20 percent loss budget, fresh input frames, and cooldowns',async()=>{
  const f=fixture();const p=await f.observe();f.api.wolfRecoveryCombatContinue();const a=await f.observe();f.api.wolfRecoveryCombatBegin(a);
  await f.api.wolfRecoveryCombatKey('VK_LBUTTON');await assert.rejects(()=>f.api.wolfRecoveryCombatKey('VK_LBUTTON'),/guards/);
  f.setHealth('440/1427');let current=await f.observe();await assert.rejects(()=>f.api.wolfRecoveryCombatKey('VK_E'),/guards/);
  const low=fixture({health:'700/1427'});const lp=await low.observe();low.api.wolfRecoveryCombatContinue();current=await low.observe();low.api.wolfRecoveryCombatBegin(current);
  low.setHealth('420/1427');current=await low.observe();await assert.rejects(()=>low.api.wolfRecoveryCombatKey('VK_E'),/guards/);
  const ui=fixture();const up=await ui.observe();ui.api.wolfRecoveryCombatContinue();current=await ui.observe();ui.api.wolfRecoveryCombatBegin(current);
  current.hud.journal=true;await assert.rejects(()=>ui.api.wolfRecoveryCombatKey('VK_E'));
  assert.equal(ui.api.wolfRecoveryCombatPauseReady(current),false);
});

test('adapter enforces the 20-second and 30-input caps; keyDown failure still releases its key',async()=>{
  const timed=fixture();const p=await timed.observe();timed.api.wolfRecoveryCombatContinue();let a=await timed.observe();timed.api.wolfRecoveryCombatBegin(a);
  await timed.api.sleep(20000);a=await timed.observe();await assert.rejects(()=>timed.api.wolfRecoveryCombatKey('VK_LBUTTON'),/time/);
  const capped=fixture();const cp=await capped.observe();capped.api.wolfRecoveryCombatContinue();a=await capped.observe();capped.api.wolfRecoveryCombatBegin(a);
  for(let i=0;i<30;i++){await capped.api.wolfRecoveryCombatKey('VK_LBUTTON');await capped.api.sleep(250);a=await capped.observe();}
  await assert.rejects(()=>capped.api.wolfRecoveryCombatKey('VK_LBUTTON'),/action/);
  const failed=fixture({throwKey:'VK_LBUTTON'});const fp=await failed.observe();failed.api.wolfRecoveryCombatContinue();a=await failed.observe();failed.api.wolfRecoveryCombatBegin(a);
  await assert.rejects(()=>failed.api.wolfRecoveryCombatKey('VK_LBUTTON'),/test keyDown failure/);
  assert.deepEqual(failed.keys.map(x=>x.slice(0,2)),[['down','VK_LBUTTON'],['up','VK_LBUTTON']]);
});

test('normal wolf combat keeps the 60 percent floor',async()=>{
  const combat=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/combat.js');let now=1;
  const obs={hud:{health:{current:731,max:1427},enemyBars:[{width:90,x:950,y:460}],world:false,groundControls:true},map:null,frameId:1,timestamp:1,ocr:[row('Kaeya',1664,485),row('Trial',1802,463)]};
  const result=await combat.runWolf(obs,{now:()=>now,sleep:async ms=>{now+=ms;},checkStop(){},wolfCombatKey:async()=>{throw new Error('must not input');},wolfPauseCombat:async()=>{}},async()=>obs);
  assert.match(result.reason,/below 60%/);assert.equal(result.presses,0);
});

test('fresh post-Continue health below 30 percent gets one safe Escape and no combat input',async()=>{
  const f=fixture({health:'400/1427'});const paused=await f.observe();assert.equal(f.api.wolfRecoveryCombatContinueReady(paused),true);
  const result=await mission.runQuestStep('wolfRecoveryCombat',paused,f.api,f.observe);
  assert.equal(result.continueAttempts,1,result.reason);assert.equal(result.hpInitial,400);assert.equal(result.pauseVerified,true);
  assert.equal(result.combatComplete,false);assert.deepEqual(f.keys.map(x=>x.slice(0,2)),[['down','VK_ESCAPE'],['up','VK_ESCAPE']]);
});

test('combat key failure releases it, captures a new safe frame, and pauses once',async()=>{
  const f=fixture({throwKey:'VK_E'});const paused=await f.observe();
  const result=await mission.runQuestStep('wolfRecoveryCombat',paused,f.api,f.observe);
  assert.equal(result.pauseVerified,true,result.reason);assert.equal(result.combatComplete,false);
  assert.deepEqual(f.keys.map(x=>x.slice(0,2)),[['down','VK_E'],['up','VK_E'],['down','VK_ESCAPE'],['up','VK_ESCAPE']]);
});

test('a loss-budget stop reports the latest active health after the pause hides HP',async()=>{
  const f=fixture();const paused=await f.observe();
  const observe=async()=>{
    if(f.keys.some(e=>e[0]==='down'&&e[1]==='VK_E'))f.setHealth('440/1427');
    return f.observe();
  };
  const result=await mission.runQuestStep('wolfRecoveryCombat',paused,f.api,observe);
  assert.match(result.reason,/dropped more than 20%/);
  assert.equal(result.pauseVerified,true);assert.equal(result.hpInitial,731);assert.equal(result.hpLast,440);
  assert.equal(result.actionCounts.VK_E,1);assert.equal(result.actionCounts.VK_LBUTTON,0);
  assert.equal(result.combatComplete,false);assert.equal(result.questComplete,false);
});

test('enemy-bar reacquisition retains the recovery floor at 51 percent health',async()=>{
  const f=fixture({bar:false});const paused=await f.observe();let activeReads=0;
  const observe=async()=>{
    if(++activeReads===2)f.setBar(true);
    return f.observe();
  };
  const result=await mission.runQuestStep('wolfRecoveryCombat',paused,f.api,observe);
  assert.equal(result.pauseVerified,true,result.reason);assert.equal(result.hpInitial,731);
  assert.ok(result.actionCounts.VK_E>0);assert.ok(result.actionCounts.VK_LBUTTON>0);
  assert.equal(result.combatComplete,false);assert.equal(result.questComplete,false);
});
