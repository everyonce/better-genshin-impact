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
  focusLossAt=0,sessionLossAt=0,stopAt=0,reusedFrame=false}={}) {
  let now=5000000,frame=expectedFrameId-1,reuseFrames=reusedFrame,phase='pause',character='starter',moves=0,cast=false,foreground=true,windowsSessionId=7,stopped=false;
  let liveKaeyaHp=kaeyaHp,cooldownUntil=null,platformSample=0,cooldownDamageApplied=false,adapter=null;
  let permitData={kind:'secondSpikeBank',session:'wolf',frameId:expectedFrameId,createdAt:now-1000};
  if(permit==='missing')permitData=null;
  if(permit==='wrongSession')permitData.session='other';
  if(permit==='wrongFrame')permitData.frameId=expectedFrameId-1;
  if(permit==='used')permitData.usedAt=now-10;
  const entries=[{id:'mission-11111111111111111111111111111111',session:'wolf',mission:'questStep',status:'completed',timestamp:now-10000,
    details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[{type:'wolfPartyStart',frameId:1,label:'Deep Within the Temple of the Wolf',startedAt:now-11000}]}}];
  const inputs=[],clicks=[],observations=[],platformReads=[];
  function healthText(){return character==='amber'?amberHp:liveKaeyaHp;}
  function fullRows(){
    if(phase==='pause')return [row('Continue Challenge',831,399,287,40),row('Leave Domain?',864,640,221,36),row('Lower Difficulty',849,518,251,42)];
    const hp=healthText(),rows=[row('Kaeya',1664,485,90,38),row('Trial',1802,463,43,22),row(hp,910,1002,100,18),row('E',1689,1028,20,20),row('Q',1830,1028,20,20)];
    if(!cast&&cooldownUntil!==null&&cooldownUntil>now)rows.push(row(Math.max(.1,(cooldownUntil-now)/1000).toFixed(1),1680,981,37,23));
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
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId,isGameForeground:foreground,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='wolf-spike-second.json'?permitData!==null:p==='stop.json'?stopped:false,
      readTextSync:p=>{
        if(p==='wolf-spike-second.json'){if(!permitData)throw new Error('permit absent');return JSON.stringify(permitData);}
        if(p==='wolf-second-spike.js')return fs.readFileSync(path.join(root,p),'utf8');
        if(p==='reports/wolf.json')return JSON.stringify(entries);
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
      return {srcMat:{resize:()=>({rows:[]}),inRange:(lower)=>{
        const color=lower.values[0],fractions=platformFractions();let fraction=0;
        if(color===65){
          if(x===750&&y===520)fraction=fractions.left;
          else if(x===1050&&y===520)fraction=fractions.right;
          else if(x===700&&y===800||x===1160&&y===800)fraction=moves===0||moves>=floorAt?.94:.1;
          else fraction=.12;
        } else if(color===150){
          if(cast&&ice==='positive')fraction=.82;
          else if(cast&&ice==='leftOnly')fraction=x===700?.82:.2;
          else fraction=.05;
        } else if(color===0)fraction=.15;
        if(x===750&&y===520&&color===65){platformReads.push({frame,phase,character,left:fractions.left,right:fractions.right});platformSample++;}
        return {fraction,area:w*h,dispose(){}};
      }},dispose(){}};
    },dispose(){}}),
    keyDown:key=>{
      inputs.push(['down',key,now]);
      if(key==='VK_ESCAPE'){phase='pause';return;}
      if(key==='VK_3'){character='kaeya';cooldownUntil=now+900;}
      if(key==='VK_2')character='amber';
      if(key==='VK_E'){cast=true;if(kaeyaDamagePhase==='afterCast')liveKaeyaHp='42/1427';}
      if(key==='VK_W'){
        moves++;
        if(amberDamageAt===moves)amberHp='680/1055';
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
  async function observe(){if(!reuseFrames||frame===0)frame++;const o=await adapter.observe('wolf',frame);observations.push(o);return o;}
  return {adapter,observe,inputs,clicks,observations,platformReads,get permit(){return permitData;}};
}

async function run(opts){const f=fixture(opts),result=await mission.runQuestStep('wolfSpikeCrossSecond',await f.observe(),f.adapter,f.observe);return {f,result};}

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
