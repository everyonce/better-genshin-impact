const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=50,height=20)=>({text,x,y,width,height});
const surfaces={
  ice711:{iceLeft:.978,iceRight:.956,floorLeftIce:.196,floorRightIce:.002,floorLeftStone:.719,floorRightStone:.674,spikeLeft:0,spikeRight:0},
  ice720:{iceLeft:.042,iceRight:.487,floorLeftIce:.079,floorRightIce:.067,floorLeftStone:.921,floorRightStone:.893,frontLeftStone:.956187,frontRightStone:.555562,spikeLeft:.338,spikeRight:.193},
  firstLanding42:{iceLeft:.2244375,iceRight:.03475,floorLeftIce:.5652778,floorRightIce:.0681944,floorLeftStone:.8119444,floorRightStone:.9359722,frontLeftStone:.85075,frontRightStone:.8735,spikeLeft:.297407,spikeRight:.44662},
  iceFrame22:{iceLeft:.778875,iceRight:.615125,floorLeftIce:.1,floorRightIce:.1,floorLeftStone:.754861,floorRightStone:.750278,spikeLeft:0,spikeRight:0},
  iceFrame23:{iceLeft:.9895,iceRight:.957125,floorLeftIce:.1,floorRightIce:.1,floorLeftStone:.748889,floorRightStone:.727083,spikeLeft:0,spikeRight:0},
  iceFrame26:{iceLeft:.961,iceRight:.911,floorLeftIce:.068,floorRightIce:.006,floorLeftStone:.733,floorRightStone:.723,spikeLeft:0,spikeRight:0},
  continueLip:{iceLeft:.37256,iceRight:.02644,floorLeftIce:.099444,floorRightIce:.129583,floorLeftStone:.341666,floorRightStone:.326388,frontLeftStone:.804,frontRightStone:.97725,spikeLeft:0,spikeRight:0},
  kaeyaFrame716:{iceLeft:.954,iceRight:.981,floorLeftIce:.938,floorRightIce:.909,floorLeftStone:.130,floorRightStone:.152,spikeLeft:0,spikeRight:0},
  kaeyaFrame720:{iceLeft:.0388125,iceRight:.035375,floorLeftIce:.079,floorRightIce:.067,floorLeftStone:.921,floorRightStone:.893,frontLeftStone:.956187,frontRightStone:.555562,spikeLeft:.338,spikeRight:.193},
  iceFrame33:{iceLeft:.8,iceRight:.8,floorLeftIce:.1,floorRightIce:.1,floorLeftStone:.1,floorRightStone:.1,frontLeftStone:.08,frontRightStone:.09,spikeLeft:0,spikeRight:0},
  lipFrame34:{iceLeft:.0388125,iceRight:.035375,floorLeftIce:.9930556,floorRightIce:.9211111,floorLeftStone:.0179161,floorRightStone:.102361,frontLeftStone:.681625,frontRightStone:.675312,spikeLeft:0,spikeRight:0},
  wetFrame35:{iceLeft:.01,iceRight:.01,floorLeftIce:.4,floorRightIce:.4,floorLeftStone:.1,floorRightStone:.1,frontLeftStone:0,frontRightStone:.001,spikeLeft:0,spikeRight:0},
  bank:{iceLeft:.042,iceRight:.016,floorLeftIce:.283,floorRightIce:.075,floorLeftStone:1,floorRightStone:.976,spikeLeft:.346,spikeRight:.439}
};

function fixture({permit='valid',ice='positive',wrongKaeyaHp=null,wrongAmberHp=null,amberDamage=false,focusLoss=false,sessionLoss=false,reusedFrame=false,spikeDisappearsAfterBank=false,floorLossAfterBank=false,spikePulseAfterSamples=null,spikeNeverPulses=false,partialIceThenFull=false,iceNeverFull=false,kaeyaHealthDropAfterCast=false,reuseIce=false,reuseMutation=null,expectedFrameId=1,landingLipMode=null,jumpFailure=null,crossingCharacter=null,kaeyaDamageOnMove=false,landingContinuation=false,landingFinisher=false,landingMutation=null,landingPermitCharacter='kaeya',localFinishMode=null}={}) {
  let now=3000000,frame=expectedFrameId-1,reuseFrames=reusedFrame,phase='pause',foreground=true,windowsSessionId=7,profile=landingContinuation?(landingFinisher?'firstLanding42':'continueLip'):reuseIce?'reuse':'bank',character='starter',moveCount=0,jumpActive=false,
      cooldownUntil=null,healthOverride=null,surfaceSamples=0,iceSamples=0,permitData={kind:'firstSpikeBank',session:'wolf',frameId:1,createdAt:now-1000};
  const priorMissionId='mission-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',priorIceFrame=26,priorReportFrame=27;
  let priorResult={step:'wolfSpikeCrossFirst',skillAttempts:1,movementAttempts:0,pauseVerified:true,frameId:priorReportFrame};
  let priorEvents=[{type:'key',key:'VK_E',durationMs:60,startedAt:now-2200,finishedAt:now-2140},{type:'key',key:'VK_ESCAPE',durationMs:60,startedAt:now-2100,finishedAt:now-2040}];
  let priorRow={id:priorMissionId,session:'wolf',mission:'questStep',status:'stopped',timestamp:now-1000,frameId:priorReportFrame,details:{result:priorResult,inputEvents:priorEvents}};
  let witness={session:'wolf',frameId:priorIceFrame,timestamp:now-2000,hud:{health:{current:329,max:1427},wolfSpikeSurface:{ice:true}}};
  const landingMissionId='mission-cccccccccccccccccccccccccccccccc',landingLastFrame=landingFinisher?42:38,landingRowFrame=expectedFrameId;
  const landingBase=now-10000;
  let landingEvents=landingFinisher?[
    {type:'wolfSpikeContinue',frameId:39,startedAt:landingBase,finishedAt:landingBase+10},
    {type:'key',key:'VK_W',durationMs:200,frameId:41,startedAt:landingBase+20,finishedAt:landingBase+220},
    {type:'key',key:'VK_ESCAPE',durationMs:60,frameId:landingLastFrame,startedAt:landingBase+230,finishedAt:landingBase+290}
  ]:[
    {type:'wolfSpikeContinue',frameId:32,startedAt:landingBase,finishedAt:landingBase+10},
    {type:'key',key:'VK_3',durationMs:60,frameId:33,startedAt:landingBase+20,finishedAt:landingBase+80},
    {type:'key',key:'VK_E',durationMs:60,frameId:34,startedAt:landingBase+90,finishedAt:landingBase+150},
    {type:'key',key:'VK_W',durationMs:800,frameId:35,startedAt:landingBase+160,finishedAt:landingBase+960},
    {type:'key',key:'VK_W',durationMs:800,frameId:36,startedAt:landingBase+970,finishedAt:landingBase+1770},
    {type:'key',key:'VK_ESCAPE',durationMs:60,frameId:landingLastFrame,startedAt:landingBase+1780,finishedAt:landingBase+1840}
  ];
  let landingResult=landingFinisher?
    {status:'stopped',step:'wolfSpikeCrossFirst',pauseVerified:true,landingVerified:false,iceEffectVerified:true,questComplete:false,continueAttempts:1,pauseAttempts:1,crossingCharacter:'kaeya',skillAttempts:0,characterSelectionAttempts:0,movementAttempts:1,jumpAttempts:0,landingContinuation:true,existingIceReused:true,lastFrameId:landingRowFrame,frameId:landingRowFrame}:
    {status:'stopped',step:'wolfSpikeCrossFirst',pauseVerified:true,landingVerified:false,iceEffectVerified:true,questComplete:false,continueAttempts:1,pauseAttempts:1,crossingCharacter:'kaeya',skillAttempts:1,characterSelectionAttempts:1,movementAttempts:2,jumpAttempts:0,lastFrameId:landingRowFrame,frameId:landingRowFrame};
  let landingRow={id:landingMissionId,session:'wolf',mission:'questStep',status:'stopped',timestamp:landingBase+2000,frameId:landingRowFrame,details:{result:landingResult,inputEvents:landingEvents}};
  let landingWitness={session:'wolf',frameId:landingLastFrame,timestamp:landingFinisher?landingBase+225:landingBase+1775,hud:{health:{current:landingFinisher?43:329,max:1427},wolfSpikeSurface:{metrics:landingFinisher?surfaces.firstLanding42:surfaces.continueLip}}};
  if(reuseIce){permitData.priorIceMission=priorMissionId;permitData.priorIceFrame=priorIceFrame;permitData.frameId=expectedFrameId;}
  if(crossingCharacter!==null)permitData.crossingCharacter=crossingCharacter;
  if(landingContinuation){permitData.kind='firstSpikeLanding';permitData.crossingCharacter=landingPermitCharacter;permitData.priorLandingMission=landingMissionId;permitData.frameId=expectedFrameId;}
  if(landingMutation==='wrongHP')landingWitness.hud.health.current=300;
  if(landingMutation==='wrongFrame')landingWitness.frameId=landingLastFrame-1;
  if(landingMutation==='wrongDuration')landingEvents[landingFinisher?1:3].durationMs=landingFinisher?800:200;
  if(landingMutation==='noLip'||landingMutation==='noLipCurrent')landingWitness.hud.wolfSpikeSurface.metrics={...(landingFinisher?surfaces.firstLanding42:surfaces.continueLip),frontLeftStone:.4};
  if(landingMutation==='wrongSourceSession')landingRow.session='other';
  if(reuseMutation==='staleWitness')witness.timestamp=now-2300;
  if(reuseMutation==='wrongWitnessSession')witness.session='other';
  if(reuseMutation==='wrongWitnessFrame')witness.frameId=priorIceFrame+1;
  if(reuseMutation==='missingWitnessHealth')delete witness.hud.health;
  if(reuseMutation==='changedWitnessHealth')witness.hud.health.current=300;
  if(reuseMutation==='laterW')priorEvents.push({type:'key',key:'VK_W',durationMs:500,startedAt:now-2050,finishedAt:now-1550});
  if(reuseMutation==='laterRotate')priorEvents.push({type:'rotate',dx:120,dy:0,startedAt:now-2050,finishedAt:now-2040});
  if(reuseMutation==='wrongPriorSession')priorRow.session='other';
  if(reuseMutation==='missingReuseSource'){delete permitData.priorIceMission;delete permitData.priorIceFrame;}
  if(reuseMutation==='wrongSourceMission')permitData.priorIceMission='mission-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
  if(reuseMutation==='missingWitness')witness=null;
  if(permit==='missing')permitData=null;
  if(permit==='expired')permitData.createdAt=now-120001;
  if(permit==='used')permitData.usedAt=now-100;
  if(permit==='wrongFrame')permitData.frameId=2;
  if(permit==='wrongSession')permitData.session='other';
  const inputs=[],clicks=[],observations=[],spikeSurfaceReads=[],iceSurfaceReads=[],lipSurfaceReads=[];
  function currentHp(){
    if(healthOverride)return healthOverride;
    if(character==='amber')return moveCount>0&&amberDamage?'890/1055':(wrongAmberHp||'950/1055');
    if(character==='kaeya'&&landingFinisher)return '43/1427';
    if(character==='kaeya'&&wrongKaeyaHp)return wrongKaeyaHp;
    return '329/1427';
  }
  function fullRows(){
    if(phase==='pause')return [row('Continue Challenge',831,399,287,40),row('Leave Domain?',864,640,221,36),row('Lower Difficulty',849,518,251,42)];
    const hp=currentHp(),rows=[row('Kaeya',1664,485,90,38),row('Trial',1802,463,43,22),row(hp,910,1002,100,18),row('E',1689,1028,20,20)];
    if(cooldownUntil!==null&&now<cooldownUntil)rows.push(row('0.9',1680,981,37,23));
    return rows;
  }
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId,isGameForeground:foreground,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='wolf-spike-first.json'&&permitData!==null,readTextSync:p=>{
      if(p==='wolf-spike-first.json'){if(!permitData)throw new Error('permit absent');return JSON.stringify(permitData);}
      if(p==='reports/wolf.json')return JSON.stringify([
        {session:'wolf',mission:'questStep',status:'completed',details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',startedAt:now-10000}]}}
      ].concat(reuseIce?[priorRow]:[]).concat(landingContinuation?[landingRow]:[]));
      if(p==='receipts/wolf/'+priorMissionId+'.json')return JSON.stringify(reuseMutation==='receiptMismatch'?{...priorRow,id:priorMissionId+'-wrong'}:priorRow);
      if(p==='observations/wolf/frame-0026.json'){if(!witness)throw new Error('witness missing');return JSON.stringify(witness);}
      if(p==='receipts/wolf/'+landingMissionId+'.json')return JSON.stringify(landingMutation==='wrongReceipt'?{...landingRow,id:landingMissionId+'-bad'}:landingRow);
      if(p==='observations/wolf/frame-'+String(landingLastFrame).padStart(4,'0')+'.json')return JSON.stringify(landingWitness);
      return fs.readFileSync(path.join(root,p),'utf8');
    },writeTextSync:(p,value)=>{if(p==='wolf-spike-first.json')permitData=JSON.parse(value);return true;},writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{constructor(a,b,c){this.values=[a,b,c];}},
      RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x,countNonZero:mask=>Math.round(mask.fraction*mask.area)},ColorConversionCodes:{GRAY2BGR:0}}},
    ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const a=(this.mat.rows||[]).map(x=>({...x}));a.count=a.length;return a;}dispose(){}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=fullRows().map(x=>({...x}));a.count=a.length;return a;},deriveCrop:(x,y,w,h)=>{
      if(x===900&&y===990)return {srcMat:{resize:()=>({rows:phase==='pause'?[]:[row(currentHp(),30,36,300,54)]})},dispose(){}};
      if(x===350&&y===100)return {srcMat:{inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}};
      const surfaceRoi=[700,660,1100,660,700,800,1160,800,600,590,1120,590];
      if(surfaceRoi.includes(x))return {srcMat:{inRange:(lower)=>{
        if(profile==='unavailable')throw new Error('surface mask unavailable');
        const values=lower.values,kind=values[0]===150?'ice':values[0]===65?'stone':'spike';
        if(x===700&&y===660&&kind==='ice')surfaceSamples++;
        if(x===700&&y===660&&kind==='ice'&&profile==='ice')iceSamples++;
        const metricKey=x===700&&y===660?(kind==='stone'?'frontLeftStone':'iceLeft'):x===1100&&y===660?(kind==='stone'?'frontRightStone':'iceRight'):
          x===700&&y===800?(kind==='ice'?'floorLeftIce':'floorLeftStone'):
          x===1160&&y===800?(kind==='ice'?'floorRightIce':'floorRightStone'):
          x===600&&y===590?'spikeLeft':'spikeRight';
        const metrics={...(profile==='bank'?surfaces.bank:profile==='reuse'?surfaces.iceFrame26:profile==='continueLip'?surfaces.continueLip:profile==='firstLanding42'?surfaces.firstLanding42:profile==='kaeyaMid'?surfaces.kaeyaFrame716:profile==='kaeyaLanding'?surfaces.kaeyaFrame720:profile==='iceEarly'?surfaces.iceFrame33:profile==='lip'?surfaces.lipFrame34:profile==='wet'?surfaces.wetFrame35:profile==='ice'?(iceNeverFull?surfaces.iceFrame22:partialIceThenFull&&iceSamples===1?surfaces.iceFrame22:partialIceThenFull?surfaces.iceFrame23:surfaces.ice711):surfaces.ice720)};
        if(['continueLip','firstLanding42'].includes(profile)&&landingMutation==='noLipCurrent')metrics.frontLeftStone=.4;
        if(spikeDisappearsAfterBank&&surfaceSamples>1){metrics.spikeLeft=0;metrics.spikeRight=0;}
        if(spikePulseAfterSamples!==null&&surfaceSamples<spikePulseAfterSamples||spikeNeverPulses){metrics.spikeLeft=0;metrics.spikeRight=0;}
        if(floorLossAfterBank&&surfaceSamples>1){metrics.floorLeftStone=.1;metrics.floorRightStone=.1;}
        if(x===700&&y===660&&kind==='ice')spikeSurfaceReads.push({frame,profile,iceLeft:metrics.iceLeft,iceRight:metrics.iceRight,floorLeftIce:metrics.floorLeftIce,floorRightIce:metrics.floorRightIce,spikeLeft:metrics.spikeLeft,spikeRight:metrics.spikeRight,floorLeftStone:metrics.floorLeftStone,floorRightStone:metrics.floorRightStone});
        if(x===700&&y===660&&kind==='ice'&&profile==='ice')iceSurfaceReads.push({frame,iceLeft:metrics.iceLeft,iceRight:metrics.iceRight,floorLeftStone:metrics.floorLeftStone,floorRightStone:metrics.floorRightStone});
        if(x===700&&y===660&&kind==='ice'&&['iceEarly','lip','wet'].includes(profile))lipSurfaceReads.push({frame,profile,iceLeft:metrics.iceLeft,iceRight:metrics.iceRight,floorLeftIce:metrics.floorLeftIce,floorRightIce:metrics.floorRightIce,frontLeftStone:metrics.frontLeftStone,frontRightStone:metrics.frontRightStone});
        return {fraction:Number.isFinite(metrics[metricKey])?metrics[metricKey]:0,area:w*h,dispose(){}};
      }},dispose(){}};
      return {srcMat:{resize:()=>({rows:[]}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}};
    },dispose(){}}),
    keyDown:key=>{
      inputs.push(['down',key,now]);
      if(key==='VK_ESCAPE'){phase='pause';return;}
      if(key==='VK_3'){character='kaeya';if(wrongKaeyaHp)healthOverride=wrongKaeyaHp;cooldownUntil=now+900;}
      if(key==='VK_E'){profile=ice==='unavailable'?'unavailable':ice==='missing'?'landing':'ice';iceSamples=0;if(kaeyaHealthDropAfterCast)healthOverride='200/1427';}
      if(key==='VK_2'){character='amber';healthOverride=wrongAmberHp||null;}
      if(key==='VK_W'){
        moveCount++;
        if(crossingCharacter==='kaeya'&&kaeyaDamageOnMove&&moveCount===1)healthOverride='250/1427';
        if(landingContinuation)profile=landingFinisher?'firstLanding42':'kaeyaLanding';
        else if(crossingCharacter==='kaeya'&&localFinishMode){
          if(moveCount===1)profile='kaeyaMid';
          else if(moveCount===2){profile=localFinishMode==='missingLip'?'kaeyaMid':'continueLip';if(localFinishMode==='healthDrop')healthOverride='250/1427';if(localFinishMode==='smallHealthDrop')healthOverride='328/1427';if(localFinishMode==='stale')reuseFrames=true;}
          else {profile='firstLanding42';if(localFinishMode==='focusLoss'){foreground=false;context.genshin.isGameForeground=false;}if(localFinishMode==='sessionLoss'){windowsSessionId=8;context.genshin.windowsSessionId=8;}}
        }
        else if(crossingCharacter==='kaeya'){profile=moveCount>=2?'kaeyaLanding':'kaeyaMid';}
        else if(landingLipMode){profile=moveCount>=3?landingLipMode==='positive'?'lip':landingLipMode==='wet'?'wet':'iceEarly':'iceEarly';}
        else if(moveCount>=1)profile='landing';
      }
      if(key==='VK_SPACE'){jumpActive=true;if(jumpFailure==='spaceDown')throw new Error('Injected jump Space keyDown failure');profile='landing';}
    },
    keyUp:key=>{inputs.push(['up',key,now]);if(key==='VK_W')jumpActive=false;},
    click:(x,y)=>{clicks.push([x,y]);phase='active';if(landingFinisher)character='kaeya';if(focusLoss){foreground=false;context.genshin.isGameForeground=false;}if(sessionLoss){windowsSessionId=8;context.genshin.windowsSessionId=8;}},
    moveMouseBy(){inputs.push(['move',now]);},sleep:async ms=>{
      if(jumpActive&&jumpFailure==='sleepThrow')throw new Error('Injected jump sleep failure');
      if(jumpActive&&jumpFailure==='focusLoss'){foreground=false;context.genshin.isGameForeground=false;}
      if(jumpActive&&jumpFailure==='sessionLoss'){windowsSessionId=8;context.genshin.windowsSessionId=8;}
      now+=ms;
    },log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);adapter.beginMission({mission:'questStep',step:'wolfSpikeCrossFirst',session:'wolf',createdAt:now-1000,expectedFrameId});
  async function observe(){if(!reuseFrames||frame===0)frame++;const o=await adapter.observe('wolf',frame);observations.push(o);return o;}
  return {adapter,observe,inputs,clicks,observations,spikeSurfaceReads,iceSurfaceReads,lipSurfaceReads,get permit(){return permitData;},setSession:v=>{windowsSessionId=v;context.genshin.windowsSessionId=v;}};
}

test('recorded first-bank, ice, and solid-floor metrics remain distinct geometry evidence',()=>{
  const bank=bgi.wolfSpikeSurface(surfaces.bank),ice=bgi.wolfSpikeSurface(surfaces.ice711),landing=bgi.wolfSpikeSurface(surfaces.ice720);
  assert.equal(bank.startBank,true);assert.equal(bank.ice,false);assert.equal(bank.solidFloor,true);
  assert.equal(ice.ice,true);assert.equal(ice.solidFloor,false);assert.equal(ice.startBank,false);
  assert.equal(landing.ice,false);assert.equal(landing.solidFloor,true);assert.equal(landing.startBank,false);
  const frame22=bgi.wolfSpikeSurface(surfaces.iceFrame22),frame23=bgi.wolfSpikeSurface(surfaces.iceFrame23),bridge26=bgi.wolfSpikeSurface(surfaces.iceFrame26);
  assert.equal(frame22.ice,false,'frame 22 left-side ice is insufficient while right-side ice remains below threshold');
  assert.equal(frame22.solidFloor,false);assert.equal(frame23.ice,true,'frame 23 has positive ice on both sides');
  assert.equal(frame23.solidFloor,false,'full ice observation does not imply solid floor or landing');
  assert.equal(bridge26.ice,true);assert.equal(bridge26.solidFloor,false);assert.equal(bridge26.startBank,false,'native bridge evidence does not claim starting bank or landing');
  const finisherLanding=bgi.wolfSpikeSurface(surfaces.firstLanding42),noRedLanding=bgi.wolfSpikeSurface({...surfaces.firstLanding42,spikeLeft:0,spikeRight:0}),icy716=bgi.wolfSpikeSurface(surfaces.kaeyaFrame716);
  assert.equal(finisherLanding.firstLanding,true,'recorded frame 42 combines stone under both feet, front stone, low ice overlap, and bilateral spike evidence');
  assert.equal(noRedLanding.firstLanding,true,'the landing anchor remains positive when the animated red spike pulse is off');
  assert.equal(finisherLanding.ice,false,'blue paving overlap is not enough to classify the landing as ice');
  assert.equal(icy716.firstLanding,false,'icy frame 716 lacks the grounded first-landing geometry');
  assert.equal(landing.firstLanding,true,'frame 720 uses the recorded asymmetric front-stone values and bilateral spike evidence');
  const lip32=bgi.wolfSpikeSurface(surfaces.iceFrame33),lip34=bgi.wolfSpikeSurface(surfaces.lipFrame34),wet35=bgi.wolfSpikeSurface(surfaces.wetFrame35);
  assert.equal(lip32.landingLip,false);assert.equal(lip34.landingLip,true);assert.equal(lip34.solidFloor,false);
  assert.equal(wet35.landingLip,false,'wet frame with no front stone does not verify the lip');
  for(const proof of [bank,ice,landing,frame22,frame23,bridge26,lip32,lip34,wet35]){assert.equal(Object.hasOwn(proof,'destination'),false);assert.equal(Object.hasOwn(proof,'crossed'),false);}
});

test('real adapter completes one bounded first-spike sequence and verifies landing plus canonical pause',async()=>{
  const f=fixture(),initial=await f.observe(),result=await mission.runQuestStep('wolfSpikeCrossFirst',initial,f.adapter,f.observe);
  assert.equal(result.continueAttempts,1);assert.equal(result.characterSelectionAttempts,2);assert.equal(result.skillAttempts,1);
  assert.equal(result.movementAttempts,3);assert.equal(result.landingVerified,true);assert.equal(result.pauseVerified,true);
  assert.equal(result.iceEffectVerified,true);assert.equal(result.questProgressVerified,false);assert.equal(result.questComplete,false);
  assert.equal(f.clicks.length,1);assert.equal(f.permit.usedAt!==undefined,true);
  const down=f.inputs.filter(x=>x[0]==='down').map(x=>x[1]);assert.deepEqual(down,['VK_3','VK_E','VK_2','VK_W','VK_W','VK_W','VK_ESCAPE']);
  assert.ok(f.inputs.every((e,i,a)=>e[0]!=='down'||a[i+1]&&a[i+1][0]==='up'&&a[i+1][1]===e[1]),'every bounded key is released');
  const annotated=f.adapter.events().filter(e=>e.type==='wolfSpikeContinue'||e.type==='wolfSpikeSelectKaeya'||e.type==='wolfSpikeSkill'||e.type==='wolfSpikeSelectAmber'||e.type==='wolfSpikeMove'||e.type==='wolfSpikeEscape'||e.type==='key');
  assert.ok(annotated.length>=8);assert.ok(annotated.every(e=>Number.isInteger(e.frameId)),JSON.stringify(annotated));
  const actionFrames=annotated.map(e=>e.frameId);assert.ok(actionFrames.every((n,i)=>i===0||n>actionFrames[i-1]),'each action consumes a distinct newer source frame');
});

test('bank proof survives a disappearing red pulse, while loss of supporting floor blocks E',async()=>{
  const flicker=fixture({spikeDisappearsAfterBank:true}),flickerResult=await mission.runQuestStep('wolfSpikeCrossFirst',await flicker.observe(),flicker.adapter,flicker.observe);
  assert.equal(flickerResult.skillAttempts,1);assert.equal(flickerResult.movementAttempts,3);assert.equal(flickerResult.landingVerified,true);
  assert.equal(flickerResult.pauseVerified,true);assert.equal(flickerResult.iceEffectVerified,true);
  const flickerDown=flicker.inputs.filter(x=>x[0]==='down').map(x=>x[1]);assert.ok(flickerDown.includes('VK_E'));assert.equal(flickerDown.filter(x=>x==='VK_W').length,3);

  const lostFloor=fixture({floorLossAfterBank:true}),floorResult=await mission.runQuestStep('wolfSpikeCrossFirst',await lostFloor.observe(),lostFloor.adapter,lostFloor.observe);
  assert.equal(floorResult.skillAttempts,0);assert.equal(floorResult.movementAttempts,0);
  assert.equal(lostFloor.inputs.some(x=>x[0]==='down'&&x[1]==='VK_E'),false);
  assert.equal(lostFloor.inputs.some(x=>x[0]==='down'&&x[1]==='VK_W'),false);
});

test('initial bank wait is read-only until pulse reacquires and stops safely if it never does or the floor is lost',async()=>{
  const reacquired=fixture({spikePulseAfterSamples:3}),reacquiredResult=await mission.runQuestStep('wolfSpikeCrossFirst',await reacquired.observe(),reacquired.adapter,reacquired.observe);
  assert.equal(reacquiredResult.bankObserveRetries,2);assert.equal(reacquiredResult.skillAttempts,1);assert.equal(reacquiredResult.movementAttempts,3);
  assert.ok(reacquired.spikeSurfaceReads.length>=3);assert.deepEqual(reacquired.spikeSurfaceReads.slice(0,2).map(x=>[x.spikeLeft,x.spikeRight]),[[0,0],[0,0]]);
  assert.ok(reacquired.spikeSurfaceReads.slice(2).some(x=>x.spikeLeft>=.22&&x.spikeRight>=.22));
  assert.equal(reacquired.inputs.filter(x=>x[0]==='down'&&x[1]==='VK_3').length,1);
  const selectFrame=reacquired.adapter.events().find(x=>x.type==='key'&&x.key==='VK_3').frameId;
  assert.ok(reacquired.spikeSurfaceReads.some(x=>x.frame===selectFrame&&x.spikeLeft>=.22&&x.spikeRight>=.22),'Kaeya switch consumes a positive bank frame');

  const absent=fixture({spikeNeverPulses:true}),absentResult=await mission.runQuestStep('wolfSpikeCrossFirst',await absent.observe(),absent.adapter,absent.observe);
  assert.equal(absentResult.bankObserveRetries,8);assert.equal(absentResult.skillAttempts,0);assert.equal(absentResult.movementAttempts,0);
  assert.equal(absent.inputs.some(x=>x[0]==='down'&&['VK_3','VK_E','VK_W'].includes(x[1])),false);

  const lostFloor=fixture({spikeNeverPulses:true,floorLossAfterBank:true}),floorResult=await mission.runQuestStep('wolfSpikeCrossFirst',await lostFloor.observe(),lostFloor.adapter,lostFloor.observe);
  assert.equal(floorResult.skillAttempts,0);assert.equal(floorResult.movementAttempts,0);
  assert.equal(lostFloor.inputs.some(x=>x[0]==='down'&&['VK_3','VK_E','VK_W'].includes(x[1])),false);
});

test('post-E partial ice waits for full bilateral ice; never-full or Kaeya HP loss blocks Amber and W',async()=>{
  const transition=fixture({partialIceThenFull:true}),transitionResult=await mission.runQuestStep('wolfSpikeCrossFirst',await transition.observe(),transition.adapter,transition.observe);
  assert.equal(transitionResult.iceObserveRetries,1);assert.equal(transitionResult.iceEffectVerified,true);
  assert.equal(transitionResult.movementAttempts,3);assert.equal(transitionResult.landingVerified,true);
  assert.deepEqual(transition.iceSurfaceReads.slice(0,2).map(x=>[x.iceLeft,x.iceRight]),[[.778875,.615125],[.9895,.957125]]);
  assert.equal(transition.inputs.filter(x=>x[0]==='down'&&x[1]==='VK_2').length,1);
  assert.equal(transition.inputs.filter(x=>x[0]==='down'&&x[1]==='VK_W').length,3);

  const absent=fixture({iceNeverFull:true}),absentResult=await mission.runQuestStep('wolfSpikeCrossFirst',await absent.observe(),absent.adapter,absent.observe);
  assert.equal(absentResult.iceObserveRetries,3);assert.equal(absentResult.iceEffectVerified,false);assert.equal(absentResult.movementAttempts,0);
  assert.equal(absent.inputs.some(x=>x[0]==='down'&&['VK_2','VK_W'].includes(x[1])),false);

  const hpLoss=fixture({kaeyaHealthDropAfterCast:true}),hpResult=await mission.runQuestStep('wolfSpikeCrossFirst',await hpLoss.observe(),hpLoss.adapter,hpLoss.observe);
  assert.equal(hpResult.skillAttempts,1);assert.equal(hpResult.movementAttempts,0);
  assert.equal(hpLoss.inputs.some(x=>x[0]==='down'&&['VK_2','VK_W'].includes(x[1])),false);
});

test('same-bank saved ice reuses only a matching stopped receipt and exact healthy witness',async()=>{
  const reused=fixture({reuseIce:true,expectedFrameId:30}),result=await mission.runQuestStep('wolfSpikeCrossFirst',await reused.observe(),reused.adapter,reused.observe);
  assert.equal(result.existingIceReused,true);assert.equal(result.iceEffectVerified,true);assert.equal(result.skillAttempts,0);
  assert.equal(result.cooldownWaitMs,0);assert.equal(result.movementAttempts,3);assert.equal(result.landingVerified,true);assert.equal(result.pauseVerified,true);
  assert.equal(reused.clicks.length,1);
  const down=reused.inputs.filter(x=>x[0]==='down').map(x=>x[1]);
  assert.deepEqual(down,['VK_2','VK_W','VK_W','VK_W','VK_ESCAPE']);
  assert.ok(reused.inputs.every((e,i,a)=>e[0]!=='down'||a[i+1]&&a[i+1][0]==='up'&&a[i+1][1]===e[1]));
  assert.ok(reused.spikeSurfaceReads.some(x=>x.frame===31&&x.floorLeftStone===.733&&x.floorRightStone===.723));

  for(const reuseMutation of ['missingReuseSource','wrongSourceMission','missingWitness','staleWitness','wrongWitnessSession','wrongWitnessFrame','missingWitnessHealth','changedWitnessHealth','receiptMismatch','laterW','laterRotate','wrongPriorSession']){
    const f=fixture({reuseIce:true,reuseMutation,expectedFrameId:30}),rejected=await mission.runQuestStep('wolfSpikeCrossFirst',await f.observe(),f.adapter,f.observe);
    assert.equal(rejected.skillAttempts,0,reuseMutation);assert.equal(rejected.movementAttempts,0,reuseMutation);
    assert.equal(f.inputs.some(x=>x[0]==='down'&&['VK_3','VK_E','VK_W'].includes(x[1])),false,reuseMutation);
  }

  const weakAmber=fixture({reuseIce:true,wrongAmberHp:'500/1055',expectedFrameId:30}),weakResult=await mission.runQuestStep('wolfSpikeCrossFirst',await weakAmber.observe(),weakAmber.adapter,weakAmber.observe);
  assert.equal(weakResult.existingIceReused,true);assert.equal(weakResult.movementAttempts,0);
  assert.equal(weakAmber.inputs.some(x=>x[0]==='down'&&x[1]==='VK_W'),false);
});

test('authorized Kaeya crossing uses two fresh 800 ms W inputs and keeps Amber safeguards intact',async()=>{
  const kaeya=fixture({reuseIce:true,crossingCharacter:'kaeya',expectedFrameId:30}),kaeyaResult=await mission.runQuestStep('wolfSpikeCrossFirst',await kaeya.observe(),kaeya.adapter,kaeya.observe);
  assert.equal(kaeyaResult.crossingCharacter,'kaeya');assert.deepEqual({...kaeyaResult.crossingHealth},{current:329,max:1427});
  assert.equal(kaeyaResult.existingIceReused,true);assert.equal(kaeyaResult.skillAttempts,0);assert.equal(kaeyaResult.movementAttempts,2);
  assert.equal(kaeyaResult.landingVerified,true);assert.equal(kaeyaResult.pauseVerified,true);assert.equal(kaeyaResult.jumpAttempts,0);
  const down=kaeya.inputs.filter(x=>x[0]==='down').map(x=>x[1]);assert.deepEqual(down,['VK_W','VK_W','VK_ESCAPE']);
  const moveEvents=kaeya.adapter.events().filter(e=>e.type==='key'&&e.key==='VK_W');
  assert.equal(moveEvents.length,2);assert.ok(moveEvents.every(e=>e.durationMs===800&&Number.isInteger(e.frameId)));
  assert.ok(moveEvents[1].frameId>moveEvents[0].frameId);assert.ok(kaeya.inputs.every((e,i,a)=>e[0]!=='down'||a[i+1]&&a[i+1][0]==='up'&&a[i+1][1]===e[1]));
  assert.ok(kaeya.spikeSurfaceReads.some(x=>x.frame===moveEvents[0].frameId+1&&x.profile==='kaeyaMid'&&x.floorLeftIce===.938&&x.floorRightIce===.909&&x.floorLeftStone===.130&&x.floorRightStone===.152));
  assert.ok(kaeya.spikeSurfaceReads.some(x=>x.frame===moveEvents[1].frameId+1&&x.profile==='kaeyaLanding'&&x.floorLeftStone===.921&&x.floorRightStone===.893));
  const beforeThird=kaeya.inputs.filter(x=>x[0]==='down'&&x[1]==='VK_W').length;
  await assert.rejects(()=>kaeya.adapter.wolfSpikeMove(800));assert.equal(kaeya.inputs.filter(x=>x[0]==='down'&&x[1]==='VK_W').length,beforeThird,'adapter rejects a third Kaeya crossing W even on a fresh landed frame');

  const damaged=fixture({reuseIce:true,crossingCharacter:'kaeya',kaeyaDamageOnMove:true,expectedFrameId:30}),damageResult=await mission.runQuestStep('wolfSpikeCrossFirst',await damaged.observe(),damaged.adapter,damaged.observe);
  assert.equal(damageResult.crossingCharacter,'kaeya');assert.equal(damageResult.movementAttempts,1);
  assert.equal(damaged.inputs.filter(x=>x[0]==='down'&&x[1]==='VK_W').length,1,'more than 5% Kaeya loss blocks the next W');

  const badBody=fixture({reuseIce:true,crossingCharacter:'kaeya',expectedFrameId:30});
  const badInitial=await badBody.observe(),realPlan=badBody.adapter.wolfSpikeCrossingPlan;
  badBody.adapter.wolfSpikeCrossingPlan=()=>({character:'kaeya',minRatio:.6,moveMs:500,maxMoves:3});
  const badPlanResult=await mission.runQuestStep('wolfSpikeCrossFirst',badInitial,badBody.adapter,badBody.observe);
  badBody.adapter.wolfSpikeCrossingPlan=realPlan;
  assert.equal(badPlanResult.movementAttempts,0);assert.equal(badBody.inputs.some(x=>x[0]==='down'&&x[1]==='VK_W'),false);
});

test('current suspended Kaeya landing continuation requires exact receipt, final lip witness, and one 200 ms W',async()=>{
  const continued=fixture({landingContinuation:true,expectedFrameId:39}),result=await mission.runQuestStep('wolfSpikeCrossFirst',await continued.observe(),continued.adapter,continued.observe);
  assert.equal(result.landingContinuation,true);assert.equal(result.existingIceReused,true);assert.equal(result.crossingCharacter,'kaeya');
  assert.deepEqual({...result.crossingHealth},{current:329,max:1427});assert.equal(result.skillAttempts,0);assert.equal(result.movementAttempts,1);
  assert.equal(result.landingVerified,true);assert.equal(result.pauseVerified,true);assert.equal(result.jumpAttempts,0);assert.equal(continued.clicks.length,1);
  const keys=continued.adapter.events().filter(e=>e.type==='key');
  assert.deepEqual(Array.from(keys,e=>[e.key,e.durationMs]),[['VK_W',200],['VK_ESCAPE',60]]);
  assert.ok(keys.every((e,i)=>i===0||e.frameId>keys[i-1].frameId));
  assert.deepEqual(continued.inputs.filter(x=>x[0]==='down').map(x=>x[1]),['VK_W','VK_ESCAPE']);
  assert.ok(continued.spikeSurfaceReads.some(x=>x.frame===39+1&&x.profile==='continueLip'&&x.floorLeftStone===.341666&&x.floorRightStone===.326388));

  for(const landingMutation of ['wrongReceipt','wrongHP','wrongFrame','wrongDuration','noLip','noLipCurrent','wrongSourceSession']){
    const f=fixture({landingContinuation:true,landingMutation,expectedFrameId:39}),rejected=await mission.runQuestStep('wolfSpikeCrossFirst',await f.observe(),f.adapter,f.observe);
    assert.equal(rejected.movementAttempts,0,landingMutation);assert.equal(rejected.skillAttempts,0,landingMutation);
    assert.equal(f.inputs.some(x=>x[0]==='down'&&x[1]==='VK_W'),false,landingMutation);
  }
  const unknown=fixture({landingContinuation:true,landingPermitCharacter:'amber',expectedFrameId:39}),unknownResult=await mission.runQuestStep('wolfSpikeCrossFirst',await unknown.observe(),unknown.adapter,unknown.observe);
  assert.equal(unknownResult.continueAttempts,0);assert.equal(unknown.clicks.length,0);assert.deepEqual(unknown.inputs,[]);
});

test('stopped finisher receipt plus fresh frame-42 first-landing witness resumes at frame 43 with zero W',async()=>{
  const f=fixture({landingContinuation:true,landingFinisher:true,expectedFrameId:43}),result=await mission.runQuestStep('wolfSpikeCrossFirst',await f.observe(),f.adapter,f.observe);
  assert.equal(result.existingIceReused,true);assert.equal(result.landingContinuation,true);assert.equal(result.crossingCharacter,'kaeya');
  assert.deepEqual({...result.crossingHealth},{current:43,max:1427});assert.equal(result.landingVerified,true);assert.equal(result.pauseVerified,true);
  assert.equal(result.movementAttempts,0);assert.equal(result.skillAttempts,0);assert.equal(result.jumpAttempts,0);assert.equal(result.continueAttempts,1);
  assert.equal(f.clicks.length,1);assert.deepEqual(f.inputs.filter(e=>e[0]==='down').map(e=>e[1]),['VK_ESCAPE']);
  assert.ok(f.spikeSurfaceReads.some(x=>x.frame===44&&x.profile==='firstLanding42'&&x.floorLeftStone===.8119444&&x.floorRightStone===.9359722));
  const escape=f.adapter.events().find(e=>e.type==='key'&&e.key==='VK_ESCAPE');assert.ok(escape&&escape.frameId>43);

  for(const landingMutation of ['wrongReceipt','wrongHP','wrongFrame','wrongDuration','noLip','noLipCurrent','wrongSourceSession']){
    const bad=fixture({landingContinuation:true,landingFinisher:true,landingMutation,expectedFrameId:43}),rejected=await mission.runQuestStep('wolfSpikeCrossFirst',await bad.observe(),bad.adapter,bad.observe);
    assert.equal(rejected.movementAttempts,0,landingMutation);assert.equal(rejected.landingVerified,false,landingMutation);
    assert.equal(bad.inputs.some(e=>e[0]==='down'&&e[1]==='VK_W'),false,landingMutation);
  }
});

test('real adapter inserts exactly one local 200 ms Kaeya finish between two W800s and the Escape pause',async()=>{
  const f=fixture({crossingCharacter:'kaeya',localFinishMode:'valid'}),result=await mission.runQuestStep('wolfSpikeCrossFirst',await f.observe(),f.adapter,f.observe);
  assert.equal(result.crossingCharacter,'kaeya');assert.deepEqual({...result.crossingHealth},{current:329,max:1427});
  assert.equal(result.movementAttempts,3);assert.equal(result.finishAttempts,1);assert.equal(result.landingVerified,true);assert.equal(result.pauseVerified,true);
  assert.equal(result.skillAttempts,1);assert.equal(result.characterSelectionAttempts,1);assert.equal(result.jumpAttempts,0);
  const keyEvents=f.adapter.events().filter(e=>e.type==='key');
  assert.deepEqual(Array.from(keyEvents,e=>[e.key,e.durationMs]),[['VK_3',60],['VK_E',60],['VK_W',800],['VK_W',800],['VK_W',200],['VK_ESCAPE',60]]);
  assert.deepEqual(f.inputs.filter(e=>e[0]==='down').map(e=>e[1]),['VK_3','VK_E','VK_W','VK_W','VK_W','VK_ESCAPE']);
  assert.ok(keyEvents.every((e,i)=>i===0||e.frameId>keyEvents[i-1].frameId));
  assert.ok(f.spikeSurfaceReads.some(x=>x.frame===keyEvents[3].frameId+1&&x.profile==='continueLip'));
  assert.ok(f.spikeSurfaceReads.some(x=>x.frame===keyEvents[4].frameId+1&&x.profile==='firstLanding42'));
  assert.ok(f.inputs.filter(e=>e[0]==='down').every(e=>f.inputs.some(u=>u[0]==='up'&&u[1]===e[1]&&u[2]>=e[2])),JSON.stringify(f.inputs));
  const downsBefore=f.inputs.filter(e=>e[0]==='down').length;
  await assert.rejects(()=>f.adapter.wolfSpikeFinish(),'finish cannot be repeated after the one bounded local W');
  assert.equal(f.inputs.filter(e=>e[0]==='down').length,downsBefore);

  for(const localFinishMode of ['missingLip','healthDrop','smallHealthDrop','stale']){
    const bad=fixture({crossingCharacter:'kaeya',localFinishMode});let finishCheck=null,activeEligible=null;
    if(localFinishMode==='smallHealthDrop'){
      const original=bad.adapter.wolfSpikeFinishReady;
      bad.adapter.wolfSpikeFinishReady=function(o){finishCheck=o;activeEligible=bad.adapter.wolfSpikeActiveReady(o,'kaeya',0.01);return original.call(bad.adapter,o);};
    }
    const stopped=await mission.runQuestStep('wolfSpikeCrossFirst',await bad.observe(),bad.adapter,bad.observe);
    assert.equal(stopped.finishAttempts,0,localFinishMode);assert.equal(stopped.movementAttempts,2,localFinishMode);
    assert.equal(bad.inputs.filter(e=>e[0]==='down'&&e[1]==='VK_W').length,2,localFinishMode);
    if(localFinishMode==='smallHealthDrop'){
      assert.equal(finishCheck.hud.health.current,328);assert.equal(finishCheck.hud.health.max,1427);
      assert.equal(activeEligible,true,'small loss remains inside the general movement health budget');
      assert.equal(bad.adapter.events().some(e=>e.type==='key'&&e.key==='VK_W'&&e.durationMs===200),false,'exact local finish guard denies even a one-HP loss');
    }
  }
  for(const localFinishMode of ['focusLoss','sessionLoss']){
    const bad=fixture({crossingCharacter:'kaeya',localFinishMode}),stopped=await mission.runQuestStep('wolfSpikeCrossFirst',await bad.observe(),bad.adapter,bad.observe);
    assert.equal(stopped.finishAttempts,1,localFinishMode);
    const finishDown=bad.inputs.find(e=>e[0]==='down'&&e[1]==='VK_W'&&e[2]>bad.adapter.events().find(x=>x.type==='key'&&x.key==='VK_W'&&x.durationMs===800).startedAt);
    assert.ok(finishDown,localFinishMode);assert.ok(bad.inputs.some(e=>e[0]==='up'&&e[1]==='VK_W'&&e[2]>=finishDown[2]),localFinishMode+' releases finish W');
  }
});

test('frame-34 lip evidence gates one W+Space jump and both keys release on success or failure',async()=>{
  const jumped=fixture({landingLipMode:'positive'}),jumpResult=await mission.runQuestStep('wolfSpikeCrossFirst',await jumped.observe(),jumped.adapter,jumped.observe);
  assert.equal(jumpResult.jumpAttempts,1);assert.equal(jumpResult.movementAttempts,3);assert.equal(jumpResult.landingVerified,true);
  const jump=jumped.adapter.events().find(e=>e.type==='wolfSpikeLandingJump');
  assert.ok(jump);assert.deepEqual(Array.from(jump.keys),['VK_W','VK_SPACE']);assert.equal(jump.durationMs,500);assert.equal(jump.spaceDurationMs,60);assert.equal(jump.keysReleased,true);
  const moves=jumped.adapter.events().filter(e=>e.type==='key'&&e.key==='VK_W');
  assert.equal(moves.length,3);assert.ok(moves[2].frameId<jump.frameId,'third W finishes before fresh lip-frame jump');
  assert.ok(jumped.lipSurfaceReads.some(x=>x.frame===jump.frameId&&x.profile==='lip'&&x.frontLeftStone>=.6&&x.frontRightStone>=.6));
  const down=jumped.inputs.filter(x=>x[0]==='down'),spaceDown=down.find(x=>x[1]==='VK_SPACE');
  assert.equal(down.filter(x=>x[1]==='VK_SPACE').length,1);
  assert.equal(down.filter(x=>x[1]==='VK_W'&&x[2]<jump.startedAt).length,3,'no jump before all three bounded W inputs');
  const spaceUp=jumped.inputs.find(x=>x[0]==='up'&&x[1]==='VK_SPACE'),walkUp=jumped.inputs.find(x=>x[0]==='up'&&x[1]==='VK_W'&&x[2]>=spaceDown[2]);
  const jumpWalkDown=down.find(x=>x[1]==='VK_W'&&x[2]>=jump.startedAt);
  assert.ok(spaceUp&&spaceUp[2]-spaceDown[2]===60,'Space must be held for exactly 60 ms');
  assert.ok(walkUp&&jumpWalkDown&&walkUp[2]-jumpWalkDown[2]===500,'W must be held for exactly 500 ms');

  for(const landingLipMode of ['missing','wet']){
    const f=fixture({landingLipMode}),result=await mission.runQuestStep('wolfSpikeCrossFirst',await f.observe(),f.adapter,f.observe);
    assert.equal(result.movementAttempts,3,landingLipMode);assert.equal(result.jumpAttempts,0,landingLipMode);
    assert.equal(f.inputs.some(x=>x[0]==='down'&&x[1]==='VK_SPACE'),false,landingLipMode);
  }

  for(const jumpFailure of ['spaceDown','focusLoss','sessionLoss','sleepThrow']){
    const failed=fixture({landingLipMode:'positive',jumpFailure}),failedResult=await mission.runQuestStep('wolfSpikeCrossFirst',await failed.observe(),failed.adapter,failed.observe);
    assert.equal(failedResult.jumpAttempts,1,jumpFailure);assert.equal(failed.inputs.some(x=>x[0]==='down'&&x[1]==='VK_SPACE'),true,jumpFailure);
    const jumpEvent=failed.adapter.events().find(e=>e.type==='wolfSpikeLandingJump');
    assert.equal(jumpEvent.keysReleased,true,jumpFailure);
    assert.ok(failed.inputs.some(x=>x[0]==='up'&&x[1]==='VK_SPACE'),jumpFailure);
    assert.ok(failed.inputs.some(x=>x[0]==='up'&&x[1]==='VK_W'&&x[2]>=failed.inputs.find(x=>x[0]==='down'&&x[1]==='VK_W'&&x[2]>=jumpEvent.startedAt)[2]),jumpFailure);
  }
});

test('missing or unavailable first-spike ice prevents Amber selection and every W input',async()=>{
  for(const ice of ['missing','unavailable']){
    const f=fixture({ice}),initial=await f.observe(),result=await mission.runQuestStep('wolfSpikeCrossFirst',initial,f.adapter,f.observe);
    assert.equal(result.skillAttempts,1);assert.equal(result.iceEffectVerified,false);assert.equal(result.movementAttempts,0);assert.equal(result.landingVerified,false);
    const down=f.inputs.filter(x=>x[0]==='down').map(x=>x[1]);
    assert.deepEqual(down.slice(0,2),['VK_3','VK_E']);
    assert.equal(down.includes('VK_2'),false);assert.equal(down.includes('VK_W'),false);
    assert.ok(down.length===2||down[2]==='VK_ESCAPE','cleanup may pause only when a fresh safe HUD remains available');
    assert.ok(f.inputs.every((e,i,a)=>e[0]!=='down'||a[i+1]&&a[i+1][0]==='up'&&a[i+1][1]===e[1]),'every attempted key is released');
  }
});

test('first-bank permit provenance must be present, fresh, unused, and match the exact frame and session',async()=>{
  for(const permit of ['missing','expired','used','wrongFrame','wrongSession']){
    const f=fixture({permit}),initial=await f.observe(),result=await mission.runQuestStep('wolfSpikeCrossFirst',initial,f.adapter,f.observe);
    assert.equal(result.continueAttempts,0,permit);assert.equal(result.skillAttempts,0,permit);assert.equal(f.clicks.length,0,permit);assert.deepEqual(f.inputs,[],permit);
  }
  const unknown=fixture({crossingCharacter:'traveler'}),unknownResult=await mission.runQuestStep('wolfSpikeCrossFirst',await unknown.observe(),unknown.adapter,unknown.observe);
  assert.equal(unknownResult.continueAttempts,0);assert.equal(unknown.clicks.length,0);assert.deepEqual(unknown.inputs,[]);
});

test('wrong party HP, stale/reused frames, focus/session loss, and excess Amber damage stop before unsafe W',async()=>{
  const kaeya=fixture({wrongKaeyaHp:'485/1213'}),kaeyaResult=await mission.runQuestStep('wolfSpikeCrossFirst',await kaeya.observe(),kaeya.adapter,kaeya.observe);
  assert.equal(kaeyaResult.skillAttempts,0);assert.equal(kaeyaResult.movementAttempts,0);assert.deepEqual(kaeya.inputs.filter(x=>x[0]==='down').map(x=>x[1]),['VK_3','VK_ESCAPE']);
  const amber=fixture({wrongAmberHp:'950/1427'}),amberResult=await mission.runQuestStep('wolfSpikeCrossFirst',await amber.observe(),amber.adapter,amber.observe);
  assert.equal(amberResult.skillAttempts,1);assert.equal(amberResult.movementAttempts,0);assert.ok(!amber.inputs.some(x=>x[0]==='down'&&x[1]==='VK_W'));
  const stale=fixture(),staleInitial=await stale.observe();staleInitial.timestamp-=2000;
  const staleResult=await mission.runQuestStep('wolfSpikeCrossFirst',staleInitial,stale.adapter,stale.observe);
  assert.equal(staleResult.continueAttempts,0);assert.equal(stale.clicks.length,0);
  const reused=fixture({reusedFrame:true}),reusedResult=await mission.runQuestStep('wolfSpikeCrossFirst',await reused.observe(),reused.adapter,reused.observe);
  assert.equal(reusedResult.skillAttempts,0);assert.equal(reusedResult.movementAttempts,0);
  for(const option of ['focusLoss','sessionLoss']){
    const f=fixture({[option]:true}),result=await mission.runQuestStep('wolfSpikeCrossFirst',await f.observe(),f.adapter,f.observe);
    assert.equal(result.skillAttempts,0,option);assert.equal(result.movementAttempts,0,option);
    assert.deepEqual(f.inputs.filter(x=>x[0]==='down').map(x=>x[1]),[],option);
  }
  const damaged=fixture({amberDamage:true}),damageResult=await mission.runQuestStep('wolfSpikeCrossFirst',await damaged.observe(),damaged.adapter,damaged.observe);
  assert.equal(damageResult.movementAttempts,1);assert.equal(damageResult.landingVerified,false);
  assert.equal(damaged.inputs.filter(x=>x[0]==='down'&&x[1]==='VK_W').length,1);
});
