const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const entry=[{id:'entry',session:'wolf',mission:'questStep',status:'completed',timestamp:1,
  details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[{type:'wolfPartyStart',frameId:1,label:'Deep Within the Temple of the Wolf',startedAt:1}]}}];
const pauseRows=[{text:'Continue Challenge',x:831,y:399,width:287,height:40},{text:'Leave Domain?',x:864,y:640,width:221,height:36}];
const activeRows=[{text:'Kaeya',x:1664,y:485,width:90,height:38},{text:'Trial',x:1802,y:463,width:43,height:22},{text:'800/1000',x:910,y:1002,width:100,height:18},{text:'E',x:1689,y:1028,width:20,height:20},{text:'Q',x:1830,y:1028,width:20,height:20}];

function fixture(opts={}){
  let now=500000,frameId=10,phase='pause',foreground=true,windowsSessionId=7,hp=800,maxHp=1000,failReadback=false,staleAfterFirst=false,observeCount=0;
  const inputs=[],clicks=[],moves=[],writes=[],files=new Map(),observations=[],partyCrops=[];let landingProbeIndex=0,captureId=0;
  const permit={kind:'wolfWitnessAction',session:'wolf',frameId:11,witnessFrameId:9,createdAt:now-10,action:opts.action||'jumpForward'};
  const witness={session:'wolf',frameId:9,timestamp:now-100, map:null,ocr:activeRows,hud:{world:false,groundControls:true,climbing:false,journal:false,bigMap:false,dialogueReady:false,choice:false,tutorialStep:null,auto:false,loading:false,unknownHud:false,objectiveChanged:false,interact:false,enemyBars:[],health:{current:800,max:1000}}};
  files.set('wolf-witness-action.json',JSON.stringify(permit));files.set('reports/wolf.json',JSON.stringify(entry));
  files.set('observations/wolf/frame-0009.json',JSON.stringify(witness));
  files.set('observations/wolf/frame-0009.png','png');
  const file={isExists:p=>files.has(p)||fs.existsSync(path.join(root,p)),readTextSync:p=>{if(p==='wolf-witness-action.json'&&failReadback)throw Error('permit readback failed');if(files.has(p))return files.get(p);if(fs.existsSync(path.join(root,p)))return fs.readFileSync(path.join(root,p),'utf8');throw Error('missing '+p);},
    writeTextSync:(p,v)=>{writes.push([p,v]);files.set(p,v);if(p==='wolf-witness-action.json'&&opts.failReadbackAfterWrite)failReadback=true;return true;},writeImageSync:(p)=>{files.set(p,'png');return true;}};
  function rows(){return phase==='pause'?pauseRows:activeRows.map(r=>r.text==='800/1000'?{...r,text:`${hp}/${maxHp}`}:
    r.text==='Kaeya'&&opts.fullKaeya?{...r,text:opts.fullKaeya}:{...r});}
  const context={Date:class extends Date{static now(){return now;}},console,
    genshin:{isRemoteDesktopSession:true,windowsSessionId,isGameForeground:foreground,getPositionFromMap:()=>null,getCameraOrientation:()=>0},file,
    RecognitionObject:{Ocr:()=>({})},OpenCvSharp:{OpenCvSharp:{Size:class{},Scalar:class{constructor(a,b,c){this.values=[a,b,c];}},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:()=>({}),countNonZero:m=>Math.round(m.fraction*m.area),contourArea:()=>0},ColorConversionCodes:{GRAY2BGR:0,BGR2HSV:1}}},
    ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const a=(this.mat.rows||[]).map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
    captureGameRegion:()=>{
      const thisCapture=++captureId;
      return {width:1920,height:1080,srcMat:{},
        findMulti:()=>{const a=rows().map(r=>({...r}));a.count=a.length;return a;},
        deriveCrop:(x,y,w,h)=>{
          const partyCrop=x===1630&&y===330&&w===230&&h===300;
          if(partyCrop)partyCrops.push({captureId:thisCapture,x,y,w,h});
          return {srcMat:{
            resize:()=>({rows:partyCrop?(opts.partyCropRows||[]).map(r=>({...r})):[]}),
            inRange:(lo,hi)=>{
              const colors=lo.values||[],landing=colors[0]===105&&colors[1]===95&&colors[2]===60;let fraction=0;
              if(landing){const ix=x===750?0:1,sequence=opts.landingSequence||[{left:Object.prototype.hasOwnProperty.call(opts,'landingLeft')?opts.landingLeft:.8,right:Object.prototype.hasOwnProperty.call(opts,'landingRight')?opts.landingRight:.8}],pair=sequence[Math.min(phase==='active'?landingProbeIndex:0,sequence.length-1)];if(ix===0&&phase==='active')landingProbeIndex++;fraction=ix===0?pair.left:pair.right;}
              return {fraction,area:w*h,findContoursAsArray:()=>[],dispose(){}};
            }
          },dispose(){}};
        },
        dispose(){}
      };
    },
    keyDown:k=>{inputs.push(['down',k,now]);if(k==='VK_ESCAPE')phase='pause';if(k==='VK_SPACE'&&opts.throwSpaceDown)throw Error('injected jump-key failure');if(k==='VK_SPACE'&&opts.cancelOnSpace)files.set('stop.json',JSON.stringify({session:'wolf',createdAt:now-100}));},keyUp:k=>inputs.push(['up',k,now]),click:(x,y)=>{clicks.push([x,y]);phase='active';if(opts.focusLossAfterContinue){foreground=false;context.genshin.isGameForeground=false;}},moveMouseBy:(x,y)=>moves.push([x,y]),sleep:async ms=>{now+=ms;},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);
  adapter.beginMission({id:'witness-request',mission:'questStep',step:'wolfWitnessAction',session:'wolf',createdAt:now-100,expectedFrameId:11});
  async function observe(){frameId++;now+=20;const o=await adapter.observe('wolf',frameId);observations.push(o);observeCount++;if(staleAfterFirst&&observeCount===2)o.frameId--;if(phase==='active'&&opts.activeFault){if(opts.activeFault==='enemy')o.hud.enemyBars=[{x:10,y:10}];if(opts.activeFault==='diagLevel')o.hud.enemyBarDiagnostic.level=4;if(opts.activeFault==='diagCandidates')o.hud.enemyBarDiagnostic.candidates=1;}return o;}
  return {adapter,observe,inputs,clicks,moves,writes,files,observations,partyCrops,setFailReadback(v){failReadback=v;},setHp(v){hp=v;},setStale(v){staleAfterFirst=v;},get now(){return now;}};
}
async function run(opts){const f=fixture(opts),result=await mission.runQuestStep('wolfWitnessAction',await f.observe(),f.adapter,f.observe);return {f,result};}

test('valid permit is consumed and read back before the Continue click; result remains root directed and incomplete',async()=>{
  const {f,result}=await run();
  assert.equal(result.step,'wolfWitnessAction');assert.equal(result.rootDirected,true);assert.equal(result.questComplete,false);assert.equal(result.routeComplete,false);
  const used=JSON.parse(f.files.get('wolf-witness-action.json'));assert.equal(used.usedAt>0,true);
  assert.equal(f.files.get('observations/wolf/frame-0009.png'),'png','the witnessed PNG remains unchanged');
  assert.equal(f.writes.filter(x=>x[0]==='wolf-witness-action.json').length,1);
  assert.equal(f.clicks.length,1);assert.equal(f.clicks[0][0],Math.round(831+287/2));
  assert.equal(result.actionAttempts,1);assert.equal(result.action,'jumpForward');
});

test('permit identity, session, expected frame, witness JSON and immutable PNG all gate Continue',async()=>{
  for(const change of [
    p=>p.kind='other',p=>p.session='other',p=>p.frameId=12,p=>p.usedAt=1,p=>p.witnessFrameId=10,
    p=>p.action='bad',p=>p.createdAt=0,
  ]){
    const f=fixture();const p=JSON.parse(f.files.get('wolf-witness-action.json'));change(p);f.files.set('wolf-witness-action.json',JSON.stringify(p));
    const o=await f.observe();const r=await mission.runQuestStep('wolfWitnessAction',o,f.adapter,f.observe);
    assert.equal(r.continueAttempts,0);assert.equal(f.clicks.length,0);assert.equal(f.inputs.length,0);
  }
  for(const bad of ['json','png','entry','baseline']){
    const f=fixture();if(bad==='json')f.files.set('observations/wolf/frame-0009.json','{');
    if(bad==='png')f.files.delete('observations/wolf/frame-0009.png');if(bad==='entry')f.files.set('reports/wolf.json','[]');
    if(bad==='baseline'){const w=JSON.parse(f.files.get('observations/wolf/frame-0009.json'));w.hud.health={current:0,max:1000};f.files.set('observations/wolf/frame-0009.json',JSON.stringify(w));}
    const r=await mission.runQuestStep('wolfWitnessAction',await f.observe(),f.adapter,f.observe);
    assert.equal(r.continueAttempts,0,bad);assert.equal(f.clicks.length,0,bad);
  }
});

test('permit consumption readback failure prevents the click',async()=>{
  const f=fixture({failReadbackAfterWrite:true});
  const r=await mission.runQuestStep('wolfWitnessAction',await f.observe(),f.adapter,f.observe);
  assert.equal(r.continueAttempts,1);assert.equal(f.clicks.length,0);assert.equal(f.inputs.length,0);
});

test('guard rejects changed HP and replayed action, while exact active HP and no-enemy diagnostic are required',async()=>{
  const changed=fixture();changed.setHp(799);const cr=await mission.runQuestStep('wolfWitnessAction',await changed.observe(),changed.adapter,changed.observe);
  assert.equal(cr.actionAttempts,0);assert.equal(changed.inputs.some(x=>x[0]==='down'&&x[1]!=='VK_ESCAPE'),false);
  const good=await run();assert.equal(good.result.actionAttempts,1);
  await assert.rejects(good.f.adapter.wolfWitnessAction());
  const stale=fixture();stale.setStale(true);const sr=await mission.runQuestStep('wolfWitnessAction',await stale.observe(),stale.adapter,stale.observe);
  assert.equal(sr.actionAttempts,0);assert.equal(stale.inputs.some(x=>x[0]==='down'&&x[1]!=='VK_ESCAPE'),false);
});

test('same-capture party crop repairs clipped Kaeya OCR before the fresh action guard',async()=>{
  const exactKaeya={text:'Kaeya',x:102,y:465,width:270,height:114};
  const repaired=await run({fullKaeya:'aeya',partyCropRows:[exactKaeya]});
  assert.equal(repaired.result.actionAttempts,1);
  assert.ok(repaired.f.observations.some(o=>o.ocr.some(r=>r.text==='aeya')&&o.ocr.some(r=>r.text==='Kaeya')),
    'the original clipped full-frame read and exact cropped read are both retained');
  assert.ok(repaired.f.partyCrops.length>0,'the scoped party crop was read');
  assert.equal(repaired.f.clicks.length,1);
  assert.ok(repaired.f.inputs.some(x=>x[0]==='down'&&x[1]==='VK_W'),'the subsequent fresh guard allowed the permitted action');

  for(const partyCropRows of [[],[{text:'Kayea',x:102,y:465,width:270,height:114}]]){
    const rejected=await run({fullKaeya:'aeya',partyCropRows});
    assert.equal(rejected.result.actionAttempts,0,JSON.stringify(partyCropRows));
    assert.equal(rejected.f.inputs.some(x=>x[0]==='down'&&['VK_W','VK_A','VK_D','VK_LBUTTON','VK_SPACE'].includes(x[1])),false,
      JSON.stringify(partyCropRows));
  }
});

test('enemy bars, incomplete level-5 diagnostics, and focus loss each prevent the witnessed action',async()=>{
  for(const fault of ['enemy','diagLevel','diagCandidates']){
    const f=fixture({activeFault:fault});const r=await mission.runQuestStep('wolfWitnessAction',await f.observe(),f.adapter,f.observe);
    assert.equal(r.actionAttempts,0,fault);assert.equal(f.inputs.some(x=>x[0]==='down'&&['VK_W','VK_A','VK_D','VK_LBUTTON','VK_SPACE'].includes(x[1])),false,fault);
  }
  const f=fixture({focusLossAfterContinue:true});const r=await mission.runQuestStep('wolfWitnessAction',await f.observe(),f.adapter,f.observe);
  assert.equal(r.actionAttempts,0);assert.equal(f.inputs.some(x=>x[0]==='down'&&['VK_W','VK_A','VK_D','VK_LBUTTON','VK_SPACE'].includes(x[1])),false);
});

test('dead or ungrounded state cannot trigger cleanup Escape',async()=>{
  const f=fixture();f.setHp(0);const r=await mission.runQuestStep('wolfWitnessAction',await f.observe(),f.adapter,f.observe);
  assert.equal(r.actionAttempts,0);assert.equal(f.inputs.some(x=>x[0]==='down'&&x[1]==='VK_ESCAPE'),false);
});

test('jump requires both fresh landing probes in range and uses the restored local poll',async()=>{
  for(const pair of [
    {left:.699,right:.8},{left:.8,right:.699},{left:undefined,right:.8},{left:.8,right:NaN},{left:1.001,right:.8},{left:.8,right:1.001}
  ]){
    const f=fixture({landingLeft:pair.left,landingRight:pair.right});
    const r=await mission.runQuestStep('wolfWitnessAction',await f.observe(),f.adapter,f.observe);
    assert.equal(r.actionAttempts,0,JSON.stringify(pair));
    assert.equal(f.inputs.some(x=>x[0]==='down'&&['VK_W','VK_SPACE'].includes(x[1])),false,JSON.stringify(pair));
  }
  const restored=fixture({landingSequence:[{left:.1,right:.8},{left:.7936,right:.8645},{left:.8,right:.8}]});
  const accepted=await mission.runQuestStep('wolfWitnessAction',await restored.observe(),restored.adapter,restored.observe);
  assert.equal(accepted.actionAttempts,1,'a later fresh aligned observation authorizes the jump');
  const afterActionMisaligned=fixture({landingSequence:[{left:.8,right:.8},{left:.0012,right:.1169},{left:.8,right:.8}]});
  const completed=await mission.runQuestStep('wolfWitnessAction',await afterActionMisaligned.observe(),afterActionMisaligned.adapter,afterActionMisaligned.observe);
  assert.equal(completed.actionAttempts,1,'post-action verification does not reapply the landing gate');
});

test('bounded action chords match their exact authorized input sizes and release held jump keys',async()=>{
  for(const [action,expected] of [['forwardFine',[['VK_W',200]]],['forwardBounded',[['VK_W',800]]],['leftFine',[['VK_A',200]]],['rightFine',[['VK_D',200]]],['strike',[['VK_LBUTTON',60]]],['lookLeft',[]],['lookRight',[]],['jumpForward',[['VK_W',600],['VK_SPACE',60]]]]){
    const {f,result}=await run({action});assert.equal(result.actionAttempts,1,action);
    const keys=f.adapter.events().filter(e=>e.type==='key');assert.deepEqual(Array.from(keys,e=>[e.key,e.durationMs]),[...expected,['VK_ESCAPE',60]],action);
    if(action==='lookLeft'||action==='lookRight')assert.deepEqual(f.moves,[[action==='lookLeft'?-250:250,0]]);
    for(const down of f.inputs.filter(x=>x[0]==='down'))assert.ok(f.inputs.some(x=>x[0]==='up'&&x[1]===down[1]),down[1]);
  }
});

test('successful jump releases both chord keys; injected failure and cancellation release them too',async()=>{
  const {f,result}=await run({action:'jumpForward'});assert.equal(result.pauseVerified,true);
  assert.ok(f.inputs.some(x=>x[0]==='up'&&x[1]==='VK_W'));assert.ok(f.inputs.some(x=>x[0]==='up'&&x[1]==='VK_SPACE'));
  const events=f.adapter.events();assert.ok(events.some(e=>e.type==='wolfWitnessEscape'));
  assert.equal(result.rootDirected,true);assert.equal(result.questComplete,false);
  for(const option of [{throwSpaceDown:true},{cancelOnSpace:true}]){
    const failed=fixture({action:'jumpForward',...option});const stopped=await mission.runQuestStep('wolfWitnessAction',await failed.observe(),failed.adapter,failed.observe);
    assert.equal(stopped.actionAttempts,1);assert.ok(failed.inputs.some(x=>x[0]==='up'&&x[1]==='VK_SPACE'),JSON.stringify(option));
    assert.ok(failed.inputs.some(x=>x[0]==='up'&&x[1]==='VK_W'),JSON.stringify(option));
  }
});
