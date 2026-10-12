const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=50,height=20)=>({text,x,y,width,height});

function fixture({permit='valid',expectedFrameId=60,platform='aligned',kaeyaHp='43/1427',amberHp='739/1055',ice='positive',floorAt=3,amberDamageAt=0,
  kaeyaDamagePhase=null,
  focusLossAt=0,sessionLossAt=0,stopAt=0,reusedFrame=false,crossingCharacter=undefined,bankPosition=undefined,witnessFrameId=expectedFrameId-1,kaeyaDamageAt=0,
  underfoot='both',lipBoard='aligned',priorCrossingRequest='mission-22222222222222222222222222222222',receipt='valid',iceBridgeCooldownMs=5000,
  iceBridgePostcastCooldownMs=5000,iceBridgeFloorIce=0.95,iceBridgeFrontRightIce=0.82,approachMoves=undefined,
  iceBridgePostcastCooldownHeight=23,iceProofFrameId=expectedFrameId-3,platformLeftFloor=.283,platformRightFloor=.951,
  platformLeftUnderfoot=.382,platformRightUnderfoot=.898,platformBoardRight=.986,platformBoardFarRight=.960,
  platformRightUnderfootSupport=.952,platformBoardRightSupport=.986,platformBoardFarRightSupport=.960}={}) {
  let now=5000000,frame=expectedFrameId-1,reuseFrames=reusedFrame,phase='pause',character='starter',moves=0,cast=false,foreground=true,windowsSessionId=7,stopped=false;
  let liveKaeyaHp=kaeyaHp,cooldownUntil=null,platformSample=0,cooldownDamageApplied=false,adapter=null;
  if(bankPosition==='iceBridge'){character='kaeya';cast=true;cooldownUntil=now+iceBridgeCooldownMs;if(crossingCharacter===undefined)crossingCharacter='kaeya';}
  if(bankPosition==='platform'){character='kaeya';if(crossingCharacter===undefined)crossingCharacter='kaeya';}
  let permitData={kind:'secondSpikeBank',session:'wolf',frameId:expectedFrameId,createdAt:now-1000};
  if(crossingCharacter!==undefined)permitData.crossingCharacter=crossingCharacter;
  if(bankPosition!==undefined)permitData.bankPosition=bankPosition;
  if(approachMoves!==undefined)permitData.approachMoves=approachMoves;
  if((bankPosition==='lip'||bankPosition==='iceBridge'||bankPosition==='platform')&&witnessFrameId!=='missing')permitData.witnessFrameId=witnessFrameId;
  if(bankPosition==='iceBridge'&&priorCrossingRequest!=='missing')permitData.priorCrossingRequest=priorCrossingRequest;
  if(bankPosition==='iceBridge'&&String(receipt).indexOf('refreshed')===0&&receipt!=='refreshedMissing')permitData.iceProofFrameId=iceProofFrameId;
  if(permit==='missing')permitData=null;
  if(permit==='wrongSession')permitData.session='other';
  if(permit==='wrongFrame')permitData.frameId=expectedFrameId-1;
  if(permit==='used')permitData.usedAt=now-10;
  const entries=[{id:'mission-11111111111111111111111111111111',session:'wolf',mission:'questStep',status:'completed',timestamp:now-10000,
    details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[{type:'wolfPartyStart',frameId:1,label:'Deep Within the Temple of the Wolf',startedAt:now-11000}]}}];
  let parentReceipt=null,proofData=null;
  if(bankPosition==='iceBridge'&&String(receipt).indexOf('refreshed')===0){
    const proofFrame=receipt==='refreshedWrongFrame'?iceProofFrameId+10:iceProofFrameId;
    const proofRows=[row('Kaeya',1664,485,90,38),row('Trial',1802,463,43,22),row('E',1689,1028,20,20),row('Q',1830,1028,20,20)];
    if(receipt!=='refreshedNoCD')proofRows.push(row('4.8',1681.667,985,35.667,iceBridgePostcastCooldownHeight));
    const floorIce=receipt==='refreshedWeakIce'?.89:.95,frontIce=receipt==='refreshedWeakIce'?.69:.82;
    proofData={session:'wolf',frameId:proofFrame,timestamp:now-4000,map:null,ocr:proofRows,hud:{world:false,groundControls:true,climbing:false,journal:false,bigMap:false,
      dialogueReady:false,choice:false,tutorialStep:null,auto:false,loading:false,unknownHud:false,objectiveChanged:false,interact:false,
      health:{current:receipt==='refreshedTamperedHp'?99:100,max:1427},enemyBars:[],enemyBarDiagnostic:{level:5,candidates:0,localReads:[]},
      wolfSpikeSurface:{metrics:{iceLeft:frontIce,iceRight:frontIce,floorLeftIce:floorIce,floorRightIce:floorIce,floorLeftStone:.95,floorRightStone:.95,
        spikeLeft:.05,spikeRight:.05,frontLeftStone:.05,frontRightStone:.05}}}};
    parentReceipt={id:priorCrossingRequest,session:'wolf',mission:'questStep',status:'stopped',timestamp:now-2000,frameId:expectedFrameId,
      details:{result:{step:'wolfSpikeCrossSecond',frameId:expectedFrameId,pauseVerified:true,iceEffectVerified:false,skillAttempts:1,movementAttempts:0,
        crossingCharacter:'kaeya',kaeyaHealth:{current:100,max:1427}},inputEvents:[
        {type:'key',key:'VK_E',durationMs:60,frameId:expectedFrameId-6,startedAt:now-9000,finishedAt:now-8940},
        {type:'key',key:'VK_ESCAPE',durationMs:60,frameId:expectedFrameId-1,startedAt:now-3000,finishedAt:now-2940}
      ]}};
    entries.push(parentReceipt);
  } else if(bankPosition==='iceBridge'&&receipt!=='missing'){
    const prior={id:priorCrossingRequest,session:receipt==='wrongSession'?'other':'wolf',mission:'questStep',status:'stopped',timestamp:now-2000,frameId:expectedFrameId,
    details:{result:{step:'wolfSpikeCrossSecond',frameId:receipt==='wrongFrame'?expectedFrameId-1:expectedFrameId,pauseVerified:receipt!=='wrongPause',iceEffectVerified:true,
      crossingCharacter:'kaeya',kaeyaHealth:{current:100,max:receipt==='wrongHp'?1200:1427}},inputEvents:[
      {type:'key',key:'VK_3',durationMs:60,frameId:39,startedAt:now-10000,finishedAt:now-9940},
      {type:'key',key:'VK_E',durationMs:60,frameId:40,startedAt:now-9000,finishedAt:now-8940},
      {type:'key',key:'VK_W',durationMs:receipt==='wrongEvents'?500:600,frameId:43,startedAt:now-7000,finishedAt:now-6400},
      {type:'key',key:'VK_W',durationMs:600,frameId:46,startedAt:now-5000,finishedAt:now-4400},
      ...(receipt==='thirdW'?[{type:'key',key:'VK_W',durationMs:600,frameId:47,startedAt:now-4000,finishedAt:now-3400}]:[]),
      {type:'key',key:'VK_ESCAPE',durationMs:60,frameId:48,startedAt:now-3000,finishedAt:now-2940}
    ]}};
    parentReceipt=prior;
    if(receipt==='duplicate')entries.push({...prior},{...prior});else entries.push(prior);
  }
  const inputs=[],clicks=[],observations=[],platformReads=[],bridgeIceReads=[];
  function healthText(){return character==='amber'?amberHp:liveKaeyaHp;}
  function fullRows(){
    if(phase==='pause')return [row('Continue Challenge',831,399,287,40),row('Leave Domain?',864,640,221,36),row('Lower Difficulty',849,518,251,42)];
    const hp=healthText(),rows=[row('Kaeya',1664,485,90,38),row('Trial',1802,463,43,22),row(hp,910,1002,100,18),row('E',1689,1028,20,20),row('Q',1830,1028,20,20)];
    if((!cast||bankPosition==='iceBridge')&&cooldownUntil!==null&&cooldownUntil>now)rows.push(row(Math.max(.1,(cooldownUntil-now)/1000).toFixed(1),1681.667,985,35.667,iceBridgePostcastCooldownHeight));
    return rows;
  }
  function platformFractions(){
    if(platform==='off')return {left:.04,right:.06};
    if(platform==='leftOnly')return {left:.42,right:.05};
    if(platform==='rightOnly')return {left:.05,right:.42};
    if(platform==='low')return {left:.14,right:.30};
    if(platform==='onePulse')return platformSample===2?{left:.20,right:.37}:{left:.04,right:.06};
    return {left:.20,right:.37};
  }
  function lipFractions(x,y){
    if((x===700||x===1160)&&y===940){
      if(bankPosition==='platform'){
        const value=x===700?platformLeftUnderfoot:platformRightUnderfoot;
        return value==='missing'?undefined:value;
      }
      const checkpoint=bankPosition==='lip'&&approachMoves!==undefined?moves<=approachMoves:moves===0||moves>=floorAt;
      if(!checkpoint||underfoot==='off')return .1;
      return underfoot==='both'||underfoot==='left'&&x===700||underfoot==='right'&&x===1160?.94:.1;
    }
    if(bankPosition==='platform'&&y===580&&x===1130)return platformBoardRight==='missing'?undefined:platformBoardRight;
    if(bankPosition==='platform'&&y===580&&x===1320)return platformBoardFarRight==='missing'?undefined:platformBoardFarRight;
    if(lipBoard==='off')return .05;
    if(lipBoard==='badMid'&&x===940)return .05;
    if(lipBoard==='badRight'&&x===1130)return .2;
    if(lipBoard==='badFarRight'&&x===1320)return .2;
    return x===750?.7:x===940?.4:.01;
  }
  function platformStoneFraction(x,y){
    if(y===580&&x===1130)return platformBoardRight;
    if(y===580&&x===1320)return platformBoardFarRight;
    if(y===940&&x===1160)return platformRightUnderfoot;
    return .12;
  }
  function platformSupportFraction(x,y){
    if(y===580&&x===1130)return platformBoardRightSupport;
    if(y===580&&x===1320)return platformBoardFarRightSupport;
    if(y===940&&x===1160)return platformRightUnderfootSupport;
    return .12;
  }
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId,isGameForeground:foreground,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='wolf-spike-second.json'?permitData!==null:p==='stop.json'?stopped:
        p==='receipts/wolf/'+priorCrossingRequest+'.json'?parentReceipt!==null:
        p==='observations/wolf/frame-'+String(iceProofFrameId).padStart(4,'0')+'.json'?proofData!==null&&receipt!=='refreshedMissing':false,
      readTextSync:p=>{
        if(p==='wolf-spike-second.json'){if(!permitData)throw new Error('permit absent');return JSON.stringify(permitData);}
        if(p==='wolf-second-spike.js')return fs.readFileSync(path.join(root,p),'utf8');
        if(p==='reports/wolf.json')return JSON.stringify(entries);
        if(p==='receipts/wolf/'+priorCrossingRequest+'.json'){if(!parentReceipt)throw new Error('parent receipt absent');return JSON.stringify(parentReceipt);}
        if(p==='observations/wolf/frame-'+String(iceProofFrameId).padStart(4,'0')+'.json'){if(!proofData||receipt==='refreshedMissing')throw new Error('ice proof absent');return JSON.stringify(proofData);}
        if(p==='stop.json')return JSON.stringify({session:'wolf',createdAt:now});
        return fs.readFileSync(path.join(root,p),'utf8');
      },
      writeTextSync:(p,value)=>{if(p==='wolf-spike-second.json')permitData=JSON.parse(value);return true;},writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{constructor(a,b,c){this.values=[a,b,c];}},
      RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x,countNonZero:mask=>Math.round(mask.fraction*mask.area),contourArea:()=>0},ColorConversionCodes:{GRAY2BGR:0,BGR2HSV:1}}},
    ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const a=(this.mat.rows||[]).map(x=>({...x}));a.count=a.length;return a;}dispose(){}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=fullRows().map(x=>({...x}));a.count=a.length;return a;},deriveCrop:(x,y,w,h)=>{
      if(x===900&&y===990)return {srcMat:{resize:()=>({rows:phase==='pause'?[]:[row(healthText(),30,36,300,54)]})},dispose(){}};
      if(x===350&&y===100)return {srcMat:{inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}};
      return {srcMat:{resize:()=>({rows:[]}),inRange:(lower,upper)=>{
        const color=lower.values[0],upperColor=upper.values[0],fractions=platformFractions();let fraction=0;
        if(color===65){
          if(x===750&&y===520)fraction=fractions.left;
          else if(x===1050&&y===520)fraction=fractions.right;
          else if((x===750||x===940||x===1130||x===1320)&&y===580)fraction=lipFractions(x,y);
          else if((x===700||x===1160)&&y===940)fraction=lipFractions(x,y);
          else if(bankPosition==='platform'&&(x===700||x===1160)&&y===800)fraction=x===700?platformLeftFloor:platformRightFloor;
          else if(x===700&&y===800||x===1160&&y===800)fraction=moves===0||moves>=floorAt?.94:.1;
          else fraction=.12;
        } else if(color===150){
          if(bankPosition==='platform'&&((y===580&&(x===1130||x===1320))||(y===940&&x===1160)))
            fraction=upperColor===175?platformStoneFraction(x,y):platformSupportFraction(x,y);
          else if(bankPosition==='iceBridge'){
            if((x===700||x===1160)&&y===800)fraction=iceBridgeFloorIce;
            else if(x===700&&y===660)fraction=.82;
            else if(x===1100&&y===660)fraction=iceBridgeFrontRightIce;
            else fraction=.05;
          } else if(cast&&ice==='positive')fraction=.82;
          else if(cast&&ice==='leftOnly')fraction=x===700?.82:.2;
          else fraction=.05;
        } else if(color===0)fraction=.15;
        if(bankPosition==='iceBridge'&&color===150&&x===700&&y===800)bridgeIceReads.push({frame,fraction});
        if(x===750&&y===520&&color===65){platformReads.push({frame,phase,character,left:fractions.left,right:fractions.right});platformSample++;}
        return {fraction,area:w*h,dispose(){}};
      }},dispose(){}};
    },dispose(){}}),
    keyDown:key=>{
      inputs.push(['down',key,now]);
      if(key==='VK_ESCAPE'){phase='pause';return;}
      if(key==='VK_3'){character='kaeya';cooldownUntil=now+900;}
      if(key==='VK_2')character='amber';
      if(key==='VK_E'){cast=true;if(bankPosition==='iceBridge')cooldownUntil=now+iceBridgePostcastCooldownMs;if(kaeyaDamagePhase==='afterCast')liveKaeyaHp='42/1427';}
      if(key==='VK_W'||key==='VK_D'){
        moves++;
        if(amberDamageAt===moves)amberHp='680/1055';
        if(kaeyaDamageAt===moves)liveKaeyaHp='42/1427';
        if(focusLossAt===moves){foreground=false;context.genshin.isGameForeground=false;}
        if(sessionLossAt===moves){windowsSessionId=8;context.genshin.windowsSessionId=8;}
        if(stopAt===moves)stopped=true;
      }
    },
    keyUp:key=>inputs.push(['up',key,now]),
    click:(x,y)=>{clicks.push([x,y]);phase='active';},moveMouseBy(){},
    sleep:async ms=>{
      now+=ms;
      if(kaeyaDamagePhase==='afterCooldown'&&!cooldownDamageApplied&&adapter&&adapter.events().some(e=>e.type==='wolfSecondCooldownPlan')){liveKaeyaHp='42/1427';cooldownDamageApplied=true;}
    },log:{info(){}}
  };
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  adapter=context.createActOneAdapter(7);adapter.beginMission({mission:'questStep',step:'wolfSpikeCrossSecond',session:'wolf',createdAt:now-1000,expectedFrameId});
  async function observe(){if(!reuseFrames||frame===0)frame++;if(bankPosition==='iceBridge')now++;const o=await adapter.observe('wolf',frame);observations.push(o);return o;}
  return {adapter,observe,inputs,clicks,observations,platformReads,bridgeIceReads,entries,get permit(){return permitData;}};
}

async function run(opts){const f=fixture(opts),result=await mission.runQuestStep('wolfSpikeCrossSecond',await f.observe(),f.adapter,f.observe);return {f,result};}
async function runWithObservedPlatformMetric(metric,value){
  const f=fixture({expectedFrameId:60,crossingCharacter:'kaeya',bankPosition:'platform',witnessFrameId:59,approachMoves:2});
  async function observe(){
    const o=await f.observe();
    if(o.hud&&o.hud.wolfSpikeSurface&&o.hud.wolfSpikeSurface.metrics)o.hud.wolfSpikeSurface.metrics[metric]=value;
    return o;
  }
  const result=await mission.runQuestStep('wolfSpikeCrossSecond',await observe(),f.adapter,observe);
  return {f,result};
}

test('actual second-spike adapter completes one bounded E and three W600 holds to a floor checkpoint',async()=>{
  const {f,result}=await run({}),events=f.adapter.events();
  assert.equal(result.status,'stopped');assert.equal(result.continueAttempts,1,JSON.stringify({result,hud:f.observations[1]&&f.observations[1].hud}));assert.equal(result.characterSelectionAttempts,2,JSON.stringify({result,hud:f.observations[1]&&f.observations[1].hud}));
  assert.equal(result.skillAttempts,1,JSON.stringify(result));assert.equal(result.movementAttempts,3,JSON.stringify(result));assert.equal(result.iceEffectVerified,true,JSON.stringify(result));
  assert.equal(result.solidFloorReached,true);assert.equal(result.pauseVerified,true);
  assert.equal(result.secondPitComplete,false);assert.equal(result.questProgressVerified,false);assert.equal(result.questComplete,false);
  assert.equal(f.clicks.length,1);assert.equal(f.permit.usedAt!==undefined,true);
  const keys=events.filter(e=>e.type==='key');
  assert.deepEqual(Array.from(keys,e=>[e.key,e.durationMs]),[['VK_3',60],['VK_E',60],['VK_2',60],['VK_W',600],['VK_W',600],['VK_W',600],['VK_ESCAPE',60]]);
  assert.deepEqual(f.inputs.filter(e=>e[0]==='down').map(e=>e[1]),['VK_3','VK_E','VK_2','VK_W','VK_W','VK_W','VK_ESCAPE']);
  assert.ok(keys.every((e,i)=>i===0||e.frameId>keys[i-1].frameId));
  assert.ok(f.platformReads.some((a,i)=>i>0&&a.left>=.15&&a.right>=.15&&f.platformReads[i-1].frame<a.frame),'alignment is confirmed on two distinct fresh positive frames');
  assert.ok(f.inputs.filter(e=>e[0]==='down').every(e=>f.inputs.some(u=>u[0]==='up'&&u[1]===e[1]&&u[2]>=e[2])),'all bounded keys are released');
});

test('second-spike permit failures reject before Continue or input',async()=>{
  for(const permit of ['missing','wrongSession','wrongFrame','used']){
    const {f,result}=await run({permit});
    assert.equal(result.continueAttempts,0,permit);assert.equal(f.clicks.length,0,permit);assert.equal(f.inputs.length,0,permit);
  }
});

test('second-spike E requires two fresh consecutive bilateral block alignments',async()=>{
  for(const platform of ['off','leftOnly','rightOnly','low','onePulse']){
    const {f,result}=await run({platform});
    assert.equal(result.skillAttempts,0,platform);assert.equal(result.movementAttempts,0,platform);
    assert.equal(f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_E'),false,platform);
  }
  const {f,result}=await run({});
  const aligned=f.platformReads.filter(x=>x.left>=.15&&x.right>=.15);
  assert.ok(aligned.length>=2);assert.equal(aligned[1].frame,aligned[0].frame+1);
  assert.equal(result.skillAttempts,1);
});

test('Kaeya identity, max HP, and unchanged HP are required through cooldown and E',async()=>{
  for(const options of [{kaeyaHp:'43/1213'},{kaeyaDamagePhase:'afterCooldown'}]){
    const {f,result}=await run(options);
    assert.equal(result.skillAttempts,0,JSON.stringify({options,result}));
    assert.equal(result.movementAttempts,0,JSON.stringify({options,result}));
    assert.equal(f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_2'),false);
  }
  const afterCast=await run({kaeyaDamagePhase:'afterCast'});
  assert.equal(afterCast.result.skillAttempts,1);assert.equal(afterCast.result.iceEffectVerified,false);
  assert.equal(afterCast.result.movementAttempts,0);assert.equal(afterCast.f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_2'),false);
});

test('cooldown uses a fixed captured wait and ice must be bilateral before Amber',async()=>{
  const {f,result}=await run({});
  const plan=f.adapter.events().find(e=>e.type==='wolfSecondCooldownPlan');
  assert.ok(plan);assert.equal(plan.waitMs,800);
  assert.ok(result.sleepMs>=plan.waitMs);
  const failed=await run({ice:'leftOnly'});
  assert.equal(failed.result.skillAttempts,1);assert.equal(failed.result.iceEffectVerified,false);
  assert.equal(failed.result.characterSelectionAttempts,1);assert.equal(failed.result.movementAttempts,0);
  assert.equal(failed.f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_2'),false);
});

test('Amber health floor and cumulative damage limit bound W movement',async()=>{
  const low=await run({amberHp:'500/1055'});
  assert.equal(low.result.movementAttempts,0);assert.equal(low.f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_W'),false);
  const damaged=await run({amberDamageAt:1});
  assert.equal(damaged.result.movementAttempts,1);assert.equal(damaged.result.solidFloorReached,false);
  assert.equal(damaged.f.inputs.filter(e=>e[0]==='down'&&e[1]==='VK_W').length,1);
  assert.ok(damaged.f.inputs.some(e=>e[0]==='up'&&e[1]==='VK_W'));
});

test('second-spike movement stops at a floor checkpoint or three moves without claiming completion',async()=>{
  const early=await run({floorAt:1});
  assert.equal(early.result.movementAttempts,1);assert.equal(early.result.solidFloorReached,true);
  const bounded=await run({floorAt:99});
  assert.equal(bounded.result.movementAttempts,3);assert.equal(bounded.result.solidFloorReached,false);
  for(const result of [early.result,bounded.result]){
    assert.equal(result.secondPitComplete,false);assert.equal(result.questProgressVerified,false);assert.equal(result.questComplete,false);
  }
});

test('focus, session, stop, and reused-frame failures never leave W held',async()=>{
  for(const options of [{focusLossAt:1},{sessionLossAt:1},{stopAt:1},{reusedFrame:true}]){
    const {f,result}=await run(options);
    assert.ok(result.movementAttempts<=1,JSON.stringify({options,result}));
    const downs=f.inputs.filter(e=>e[0]==='down'),ups=f.inputs.filter(e=>e[0]==='up');
    for(const down of downs)assert.ok(ups.some(up=>up[1]===down[1]&&up[2]>=down[2]),JSON.stringify({options,down,ups}));
  }
});

test('lip permit witness and unknown choices reject before Continue',async()=>{
  for(const options of [
    {crossingCharacter:'bogus'},
    {bankPosition:'bogus'},
    {crossingCharacter:'kaeya',bankPosition:'lip',witnessFrameId:'missing'},
    {crossingCharacter:'kaeya',bankPosition:'lip',witnessFrameId:-1},
    {crossingCharacter:'kaeya',bankPosition:'lip',witnessFrameId:60},
    {crossingCharacter:'kaeya',bankPosition:'lip',witnessFrameId:1.5}
  ]){
    const {f,result}=await run(options);
    assert.equal(result.continueAttempts,0,JSON.stringify(options));
    assert.equal(f.clicks.length,0,JSON.stringify(options));
    assert.equal(f.inputs.length,0,JSON.stringify(options));
  }
});

test('Kaeya lip opt-in keeps Kaeya and uses only bilateral underfoot proof for floor',async()=>{
  const {f,result}=await run({crossingCharacter:'kaeya',bankPosition:'lip'});
  assert.equal(result.status,'stopped');assert.equal(result.characterSelectionAttempts,1,JSON.stringify(result));
  assert.equal(result.skillAttempts,1,JSON.stringify(result));assert.equal(result.movementAttempts,3,JSON.stringify(result));
  assert.equal(result.solidFloorReached,true);assert.equal(result.secondPitComplete,false);
  assert.equal(result.questProgressVerified,false);assert.equal(result.questComplete,false);
  assert.equal(f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_2'),false);
  assert.equal(f.inputs.filter(e=>e[0]==='down'&&e[1]==='VK_3').length,1);
  assert.equal(f.inputs.filter(e=>e[0]==='down'&&e[1]==='VK_W').length,3);
  assert.ok(f.adapter.events().filter(e=>e.type==='key'&&e.key==='VK_W').every(e=>e.durationMs===600));
  assert.ok(f.platformReads.some((a,i)=>i>0&&a.left>=.15&&a.right>=.15&&f.platformReads[i-1].frame<a.frame));
});

test('lip alignment thresholds need two adjacent fresh frames and unilateral underfoot never relaxes floor',async()=>{
  for(const lipBoard of ['off','badMid','badRight','badFarRight']){
    const {f,result}=await run({crossingCharacter:'kaeya',bankPosition:'lip',lipBoard});
    assert.equal(result.skillAttempts,0,lipBoard);assert.equal(result.movementAttempts,0,lipBoard);
    assert.equal(f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_E'),false,lipBoard);
  }
  const unilateral=await run({crossingCharacter:'kaeya',bankPosition:'lip',underfoot:'left',floorAt:99});
  assert.equal(unilateral.result.movementAttempts,3);assert.equal(unilateral.result.solidFloorReached,false);
  assert.equal(unilateral.result.secondPitComplete,false);
  const defaultBank=await run({floorAt:1});
  assert.equal(defaultBank.result.movementAttempts,1);assert.equal(defaultBank.result.solidFloorReached,true);
});

test('Kaeya lip opt-in stops W after unchanged-HP breach and releases it',async()=>{
  const {f,result}=await run({crossingCharacter:'kaeya',bankPosition:'lip',kaeyaDamageAt:1});
  assert.equal(result.movementAttempts,1);assert.equal(result.secondPitComplete,false);
  assert.ok(f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_W'));
  assert.ok(f.inputs.some(e=>e[0]==='up'&&e[1]==='VK_W'));
  assert.equal(f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_2'),false);
  for(const down of f.inputs.filter(e=>e[0]==='down'))
    assert.ok(f.inputs.some(e=>e[0]==='up'&&e[1]===down[1]&&e[2]>=down[2]),down[1]);
});

test('iceBridge validates its same-session stopped crossing receipt before Continue',async()=>{
  for(const options of [
    {receipt:'missing'},
    {receipt:'wrongSession'},
    {receipt:'wrongFrame'},
    {receipt:'wrongPause'},
    {receipt:'wrongHp'},
    {receipt:'wrongEvents'},
    {receipt:'thirdW'},
    {receipt:'duplicate'},
    {priorCrossingRequest:'missing'},
    {witnessFrameId:47},
    {witnessFrameId:'missing'}
  ]){
    const {f,result}=await run({expectedFrameId:49,bankPosition:'iceBridge',crossingCharacter:'kaeya',witnessFrameId:48,...options});
    assert.equal(result.continueAttempts,0,JSON.stringify(options));
    assert.equal(f.clicks.length,0,JSON.stringify(options));
    assert.equal(f.inputs.length,0,JSON.stringify(options));
  }
});

test('iceBridge refreshes the known Kaeya ice once, skips VK3, and bounds crossing to three W holds',async()=>{
  const {f,result}=await run({expectedFrameId:49,bankPosition:'iceBridge',crossingCharacter:'kaeya',witnessFrameId:48,kaeyaHp:'100/1427'});
  assert.equal(result.continueAttempts,1,JSON.stringify(result));
  assert.equal(result.crossingCharacter,'kaeya');
  assert.equal(result.movementAttempts,3,JSON.stringify(result));
  assert.equal(result.pauseVerified,true);
  assert.equal(result.secondPitComplete,false);assert.equal(result.questComplete,false);
  assert.equal(f.inputs.filter(e=>e[0]==='down'&&e[1]==='VK_W').length,3);
  assert.equal(f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_3'),false);
  assert.equal(f.inputs.filter(e=>e[0]==='down'&&e[1]==='VK_E').length,1);
  const keyEvents=f.adapter.events().filter(e=>e.type==='key');
  assert.deepEqual(Array.from(keyEvents,e=>[e.key,e.durationMs]),[['VK_E',60],['VK_W',600],['VK_W',600],['VK_W',600],['VK_ESCAPE',60]]);
  const before=f.inputs.length;
  await assert.rejects(f.adapter.wolfSecondMove());
  assert.equal(f.inputs.length,before,'third W attempt is rejected before input');
  assert.equal(f.adapter.wolfSecondSelectionSettleMs(),0);
  assert.ok(f.adapter.events().find(e=>e.type==='wolfSecondCooldownPlan').waitMs<=6500);
  const castFrame=keyEvents.find(e=>e.key==='VK_E').frameId;
  const aligned=f.bridgeIceReads.filter(x=>x.fraction>=.9&&x.frame<=castFrame);
  assert.ok(aligned.length>=2&&aligned[1].frame===aligned[0].frame+1,'resume and post-cooldown frames independently verify the known ice before casting');
  for(const down of f.inputs.filter(e=>e[0]==='down'))
    assert.ok(f.inputs.some(up=>up[0]==='up'&&up[1]===down[1]&&up[2]>=down[2]),down[1]);
});

test('iceBridge refresh proof requires four postcast seconds and uses a 300ms fallback when the old cooldown is absent',async()=>{
  const low=await run({expectedFrameId:49,bankPosition:'iceBridge',crossingCharacter:'kaeya',witnessFrameId:48,kaeyaHp:'100/1427',iceBridgePostcastCooldownMs:1000});
  assert.equal(low.result.movementAttempts,0,JSON.stringify(low.result));
  assert.equal(low.f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_W'),false);
  assert.equal(low.f.inputs.filter(e=>e[0]==='down'&&e[1]==='VK_E').length,1);
  const absent=await run({expectedFrameId:49,bankPosition:'iceBridge',crossingCharacter:'kaeya',witnessFrameId:48,kaeyaHp:'100/1427',iceBridgeCooldownMs:0});
  const plan=absent.f.adapter.events().find(e=>e.type==='wolfSecondCooldownPlan');
  assert.ok(plan);assert.equal(plan.waitMs,300);
});

test('iceBridge stops before W when live Kaeya HP no longer matches the parent receipt',async()=>{
  const {f,result}=await run({expectedFrameId:49,bankPosition:'iceBridge',crossingCharacter:'kaeya',witnessFrameId:48,kaeyaHp:'99/1427'});
  assert.equal(result.movementAttempts,0,JSON.stringify(result));
  assert.equal(f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_W'),false);
  assert.equal(f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_3'),false);
  assert.equal(f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_E'),false);
});

test('iceBridge requires high floor ice before E and bilateral front ice after E',async()=>{
  const weakFloor=await run({expectedFrameId:49,bankPosition:'iceBridge',crossingCharacter:'kaeya',witnessFrameId:48,kaeyaHp:'100/1427',iceBridgeFloorIce:0.89});
  assert.equal(weakFloor.f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_E'),false);
  assert.equal(weakFloor.f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_W'),false);
  const weakFront=await run({expectedFrameId:49,bankPosition:'iceBridge',crossingCharacter:'kaeya',witnessFrameId:48,kaeyaHp:'100/1427',iceBridgeFrontRightIce:0.69});
  assert.equal(weakFront.f.inputs.filter(e=>e[0]==='down'&&e[1]==='VK_E').length,1);
  assert.equal(weakFront.f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_W'),false);
  assert.equal(weakFront.result.iceEffectVerified,false);
});

test('iceBridge accepts immutable refreshed-ice proof and the observed 17.333px cooldown geometry',async()=>{
  const {f,result}=await run({expectedFrameId:52,bankPosition:'iceBridge',crossingCharacter:'kaeya',witnessFrameId:51,iceProofFrameId:49,
    receipt:'refreshed',kaeyaHp:'100/1427',iceBridgePostcastCooldownHeight:17.333});
  assert.equal(result.continueAttempts,1,JSON.stringify(result));
  assert.equal(result.skillAttempts,1);
  assert.equal(result.iceEffectVerified,true);
  assert.ok(f.inputs.filter(e=>e[0]==='down'&&e[1]==='VK_W').length>0);
  const cooldownRows=f.observations.flatMap(o=>o.ocr||[]).filter(r=>r.height===17.333);
  assert.ok(cooldownRows.some(r=>r.x===1681.667&&r.y===985&&r.width===35.667),JSON.stringify(f.observations.map(o=>o.ocr)));
});

test('iceBridge rejects refreshed receipts with missing, stale, weak, cooldown-free, or HP-tampered proof before Continue',async()=>{
  for(const receipt of ['refreshedMissing','refreshedWrongFrame','refreshedWeakIce','refreshedNoCD','refreshedTamperedHp']){
    const {f,result}=await run({expectedFrameId:52,bankPosition:'iceBridge',crossingCharacter:'kaeya',witnessFrameId:51,iceProofFrameId:49,
      receipt,kaeyaHp:'100/1427',iceBridgePostcastCooldownHeight:17.333});
    assert.equal(result.continueAttempts,0,receipt);
    assert.equal(f.clicks.length,0,receipt);
    assert.equal(f.inputs.length,0,receipt);
  }
});

test('iceBridge still rejects a 15px cooldown OCR box after E',async()=>{
  const {f,result}=await run({expectedFrameId:49,bankPosition:'iceBridge',crossingCharacter:'kaeya',witnessFrameId:48,kaeyaHp:'100/1427',iceBridgePostcastCooldownHeight:15});
  assert.equal(result.skillAttempts,1);
  assert.equal(result.iceEffectVerified,false);
  assert.equal(f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_W'),false);
});

test('approach-only permits require an explicit Kaeya lip plan and bounded integer count',async()=>{
  for(const options of [
    {crossingCharacter:'amber',bankPosition:'lip',approachMoves:1},
    {crossingCharacter:'kaeya',bankPosition:'iceBridge',approachMoves:1},
    {crossingCharacter:'kaeya',bankPosition:'lip',approachMoves:0},
    {crossingCharacter:'kaeya',bankPosition:'lip',approachMoves:3},
    {crossingCharacter:'kaeya',bankPosition:'lip',approachMoves:1.5},
    {crossingCharacter:'kaeya',bankPosition:'lip',approachMoves:-1},
    {crossingCharacter:'kaeya',bankPosition:'lip',approachMoves:null},
    {crossingCharacter:'kaeya',bankPosition:'lip',approachMoves:1,witnessFrameId:'missing'}
  ]){
    const {f,result}=await run({expectedFrameId:60,witnessFrameId:options.witnessFrameId==='missing'?'missing':59,...options});
    assert.equal(result.continueAttempts,0,JSON.stringify(options));
    assert.equal(f.clicks.length,0,JSON.stringify(options));
    assert.equal(f.inputs.length,0,JSON.stringify(options));
  }
  const defaults=fixture({expectedFrameId:60,crossingCharacter:'kaeya',bankPosition:'lip',witnessFrameId:59});
  assert.equal(defaults.adapter.wolfSecondApproachPlan(),0);
  assert.equal(defaults.adapter.wolfSecondApproachPlan(),0);
  assert.equal(defaults.inputs.length,0,'default plan reads do not change state or send input');
});

test('approach-only plan sends exactly its authorized W200 holds and no combat input',async()=>{
  const {f,result}=await run({expectedFrameId:60,crossingCharacter:'kaeya',bankPosition:'lip',witnessFrameId:59,approachMoves:2});
  assert.equal(result.continueAttempts,1,JSON.stringify(result));
  assert.equal(result.pauseVerified,true);
  assert.equal(result.secondPitComplete,false);assert.equal(result.questComplete,false);
  const keys=f.adapter.events().filter(e=>e.type==='key');
  assert.deepEqual(Array.from(keys,e=>[e.key,e.durationMs]),[['VK_3',60],['VK_W',200],['VK_W',200],['VK_ESCAPE',60]]);
  assert.equal(f.inputs.some(e=>e[0]==='down'&&['VK_E','VK_2'].includes(e[1])),false);
  const before=f.inputs.length;
  await assert.rejects(f.adapter.wolfSecondApproach(200));
  await assert.rejects(f.adapter.wolfSecondApproach(199));
  assert.equal(f.inputs.length,before,'a further approach hold is rejected before input');
  assert.equal(f.adapter.wolfSecondApproachPlan(),2);
  assert.equal(f.adapter.wolfSecondApproachPlan(),2,'reading the plan does not consume its allowance');
  for(const down of f.inputs.filter(e=>e[0]==='down'))
    assert.ok(f.inputs.some(up=>up[0]==='up'&&up[1]===down[1]&&up[2]>=down[2]),down[1]);
});

test('approach-only holds stop on changed HP, missing stone, stale frames, or lost focus',async()=>{
  const changedHp=await run({expectedFrameId:60,crossingCharacter:'kaeya',bankPosition:'lip',witnessFrameId:59,approachMoves:2,kaeyaDamageAt:1});
  assert.equal(changedHp.f.inputs.filter(e=>e[0]==='down'&&e[1]==='VK_W').length,1);
  assert.ok(changedHp.f.inputs.some(e=>e[0]==='up'&&e[1]==='VK_W'));
  const noStone=await run({expectedFrameId:60,crossingCharacter:'kaeya',bankPosition:'lip',witnessFrameId:59,approachMoves:2,underfoot:'off'});
  assert.equal(noStone.f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_W'),false);
  const stale=await run({expectedFrameId:60,crossingCharacter:'kaeya',bankPosition:'lip',witnessFrameId:59,approachMoves:2,reusedFrame:true});
  assert.equal(stale.f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_W'),false);
  const focus=await run({expectedFrameId:60,crossingCharacter:'kaeya',bankPosition:'lip',witnessFrameId:59,approachMoves:2,focusLossAt:1});
  assert.equal(focus.f.inputs.filter(e=>e[0]==='down'&&e[1]==='VK_W').length,1);
  assert.ok(focus.f.inputs.some(e=>e[0]==='up'&&e[1]==='VK_W'));
  assert.equal(focus.f.inputs.filter(e=>e[0]==='down'&&e[1]==='VK_E').length,0);
});

test('platform rescue permits require a witnessed Kaeya approach plan',async()=>{
  for(const options of [
    {crossingCharacter:'amber',bankPosition:'platform',approachMoves:1},
    {crossingCharacter:'kaeya',bankPosition:'platform'},
    {crossingCharacter:'kaeya',bankPosition:'platform',approachMoves:0},
    {crossingCharacter:'kaeya',bankPosition:'platform',approachMoves:3},
    {crossingCharacter:'kaeya',bankPosition:'platform',approachMoves:1.5},
    {crossingCharacter:'kaeya',bankPosition:'platform',approachMoves:2,witnessFrameId:'missing'},
    {crossingCharacter:'kaeya',bankPosition:'platform',approachMoves:2,witnessFrameId:60}
  ]){
    const {f,result}=await run({expectedFrameId:60,witnessFrameId:59,...options});
    assert.equal(result.continueAttempts,0,JSON.stringify(options));
    assert.equal(f.clicks.length,0,JSON.stringify(options));
    assert.equal(f.inputs.length,0,JSON.stringify(options));
  }
});

test('platform rescue keeps Kaeya selected and uses only two bounded rightward D200 holds',async()=>{
  const {f,result}=await run({expectedFrameId:60,crossingCharacter:'kaeya',bankPosition:'platform',witnessFrameId:59,approachMoves:2,
    platformLeftFloor:.319,platformRightFloor:.952,platformLeftUnderfoot:.382,platformRightUnderfoot:.952,
    platformBoardRight:.986,platformBoardFarRight:.960,platformRightUnderfootSupport:3428/3600,
    platformBoardRightSupport:.986,platformBoardFarRightSupport:.960});
  assert.equal(result.continueAttempts,1,JSON.stringify(result));
  assert.equal(result.pauseVerified,true);
  assert.equal(result.secondPitComplete,false);assert.equal(result.questComplete,false);
  const keys=f.adapter.events().filter(e=>e.type==='key');
  assert.deepEqual(Array.from(keys,e=>[e.key,e.durationMs]),[['VK_D',200],['VK_D',200],['VK_ESCAPE',60]]);
  assert.equal(f.inputs.some(e=>e[0]==='down'&&['VK_3','VK_E','VK_W','VK_2'].includes(e[1])),false);
  const before=f.inputs.length;
  await assert.rejects(f.adapter.wolfSecondApproach(200));
  assert.equal(f.inputs.length,before,'a third directional hold is rejected before input');
  assert.ok(f.inputs.filter(e=>e[0]==='down'&&e[1]==='VK_D').every(d=>f.inputs.some(u=>u[0]==='up'&&u[1]==='VK_D'&&u[2]>=d[2])));
});

test('platform rescue accepts mixed-color union support at witnessed frames 138 and 139',async()=>{
  const frame139=await run({expectedFrameId:60,crossingCharacter:'kaeya',bankPosition:'platform',witnessFrameId:59,approachMoves:2,
    platformLeftFloor:.319,platformRightFloor:.952,platformRightUnderfoot:.581,platformRightUnderfootSupport:3587/3600,
    platformBoardRight:.60,platformBoardFarRight:.50,platformBoardRightSupport:4667/4800,platformBoardFarRightSupport:4562/4800});
  assert.equal(frame139.f.inputs.filter(e=>e[0]==='down'&&e[1]==='VK_D').length,2);
  assert.deepEqual(Array.from(frame139.f.adapter.events().filter(e=>e.type==='key'),e=>[e.key,e.durationMs]),[['VK_D',200],['VK_D',200],['VK_ESCAPE',60]]);

  const frame138=await run({expectedFrameId:60,crossingCharacter:'kaeya',bankPosition:'platform',witnessFrameId:59,approachMoves:2,
    platformLeftFloor:.319,platformRightFloor:.952,platformRightUnderfoot:.58,platformRightUnderfootSupport:3565/3600,
    platformBoardRight:.569,platformBoardFarRight:.50,platformBoardRightSupport:1,platformBoardFarRightSupport:.94375});
  assert.equal(frame138.f.inputs.filter(e=>e[0]==='down'&&e[1]==='VK_D').length,2);
  assert.deepEqual(Array.from(frame138.f.adapter.events().filter(e=>e.type==='key'),e=>[e.key,e.durationMs]),[['VK_D',200],['VK_D',200],['VK_ESCAPE',60]]);
});

test('platform rescue requires right-foot union support at least .9 and both board unions at least .8',async()=>{
  for(const options of [
    {platformRightUnderfootSupport:.899},
    {platformBoardRightSupport:.799},
    {platformBoardFarRightSupport:.799},
    ...['platformRightUnderfootSupport','platformBoardRightSupport','platformBoardFarRightSupport'].flatMap(probe=>[
      {[probe]:'missing'}, {[probe]:NaN}
    ])
  ]){
    const {f}=await run({expectedFrameId:60,crossingCharacter:'kaeya',bankPosition:'platform',witnessFrameId:59,approachMoves:2,
      platformRightUnderfoot:.95,platformBoardRight:.95,platformBoardFarRight:.95,...options});
    assert.equal(f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_D'),false,JSON.stringify(options));
  }
  const overOne=await runWithObservedPlatformMetric('underfootRightSupport',1.01);
  assert.equal(overOne.f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_D'),false,'observed support over 1 is rejected');
  const missingUnion=await run({expectedFrameId:60,crossingCharacter:'kaeya',bankPosition:'platform',witnessFrameId:59,approachMoves:2,
    platformRightUnderfoot:.99,platformBoardRight:.99,platformBoardFarRight:.99,
    platformRightUnderfootSupport:'missing',platformBoardRightSupport:'missing',platformBoardFarRightSupport:'missing'});
  assert.equal(missingUnion.f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_D'),false,'high stone-only fractions do not substitute for missing union support');
  const lip=await run({expectedFrameId:60,crossingCharacter:'kaeya',bankPosition:'lip',witnessFrameId:59,approachMoves:2,underfoot:'right'});
  assert.equal(lip.f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_W'),false);
  assert.equal(lip.f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_D'),false);
});

test('platform rescue retains permit, health, session, focus, stop, and key-release guards',async()=>{
  for(const permit of ['missing','wrongSession','wrongFrame','used']){
    const {f}=await run({expectedFrameId:60,crossingCharacter:'kaeya',bankPosition:'platform',witnessFrameId:59,approachMoves:2,permit});
    assert.equal(f.inputs.some(e=>e[0]==='down'&&e[1]==='VK_D'),false,permit);
  }
  for(const options of [{kaeyaDamageAt:1},{sessionLossAt:1},{focusLossAt:1},{stopAt:1}]){
    const {f}=await run({expectedFrameId:60,crossingCharacter:'kaeya',bankPosition:'platform',witnessFrameId:59,approachMoves:2,...options});
    assert.equal(f.inputs.filter(e=>e[0]==='down'&&e[1]==='VK_D').length,1,JSON.stringify(options));
    assert.ok(f.inputs.some(e=>e[0]==='up'&&e[1]==='VK_D'),JSON.stringify(options));
  }
});
