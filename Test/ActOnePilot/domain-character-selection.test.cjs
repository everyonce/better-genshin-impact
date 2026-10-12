const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=50,height=20)=>({text,x,y,width,height});

function fixture({step='falconSelectAmber',mission='questStep',health='329/1427',focus=true,ui={},names=['Amber','Trial']}={}) {
  let now=2000000,frame=0,foreground=focus,windowsSessionId=7;
  const inputs=[];
  const ocrRows=()=>[
    row('Kaeya',1664,485,70,30),
    ...names.map(text=>row(text,text==='Trial'?1802:1664,text==='Trial'?463:530,50,20)),
    ...(health===null?[]:[row(health,910,1002,100,18)]),row('E',1689,1028,20,20),
    ...(ui.journal?[row('In Progress',40,80,100,22)]:[]),
    ...(ui.loading?[row('Loading',900,500,100,20)]:[]),
    ...(ui.auto||ui.choice?[row('Auto',100,100,50,20),row('Choose an option',1200,550,200,30)]:[]),
    ...(ui.bigMap?[row('Starfell Valley',100,100,200,30)]:[]),
    ...(ui.climbing?[row('X',1680,1000,20,20),row('Space',1710,1000,50,20)]:[]),
    ...(ui.objectiveChanged?[row('Objective Updated',120,200,200,30)]:[])
  ];
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId,isGameForeground:foreground,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:()=>false,readTextSync:p=>fs.readFileSync(path.join(root,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},
      ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x},ColorConversionCodes:{GRAY2BGR:0}}},
    ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const rows=(this.mat.rows||[]).map(x=>({...x}));rows.count=rows.length;return rows;}dispose(){}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const rows=ocrRows().map(x=>({...x}));rows.count=rows.length;return rows;},
      deriveCrop:(x,y)=>({srcMat:{resize:()=>({rows:x===900&&y===990&&health!==null?[row(health,30,20,300,54)]:[]}),
        inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}}),dispose(){}}),
    keyDown:key=>inputs.push(['down',key,now]),keyUp:key=>inputs.push(['up',key,now]),moveMouseBy:(dx,dy)=>inputs.push(['move',dx,dy,now]),
    sleep:async ms=>{now+=ms;},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);adapter.beginMission({mission,step,session:'falcon-test',createdAt:1999000});
  async function observe(){frame++;return adapter.observe('falcon-test',frame);}
  return {adapter,observe,inputs,ui,advance:ms=>{now+=ms;},setFocus:v=>{foreground=v;context.genshin.isGameForeground=v;},
    setSession:v=>{windowsSessionId=v;context.genshin.windowsSessionId=v;}};
}

test('one stationary Amber or Traveler switch is permitted for a fresh living low-HP domain character',async()=>{
  for(const [step,health,key] of [
    ['falconSelectAmber','329/1427','VK_2'],
    ['falconSelectTraveler','485/1213','VK_1']
  ]){
    const f=fixture({step,health}),observation=await f.observe();
    assert.equal(observation.hud.health.current,Number(health.split('/')[0]));
    assert.equal(observation.hud.groundControls,true);assert.equal(observation.hud.world,false);
    await f.adapter.falconSelectAmber();
    assert.deepEqual(f.inputs.map(x=>x.slice(0,2)),[['down',key],['up',key]]);
    assert.equal(f.inputs[1][2]-f.inputs[0][2],60,'the switch is one bounded stationary 60 ms press');
    assert.equal(f.adapter.events().filter(e=>e.type==='key').length,1);
    assert.equal(f.adapter.events().filter(e=>e.type==='key')[0].key,key);
    assert.equal(f.inputs.some(x=>x[0]==='move'||x[1]==='VK_E'||x[1]==='VK_Q'),false);
  }
});

test('selection rejects zero, missing, nonfinite, and unrecognized health evidence without input',async()=>{
  for(const health of ['0/1427',null,'HP/1427','329/0']){
    const f=fixture({health}),o=await f.observe();
    assert.ok(!o.hud.health||!Number.isFinite(o.hud.health.current)||o.hud.health.current<=0||o.hud.health.max<=0,`expected unusable parsed HP for ${health}`);
    await assert.rejects(()=>f.adapter.falconSelectAmber());assert.deepEqual(f.inputs,[]);
  }
  for(const names of [[],['Amber'],['Trial']]){
    const f=fixture({names}),o=await f.observe();assert.ok(o.hud.health&&o.hud.health.current>0);
    await assert.rejects(()=>f.adapter.falconSelectAmber());assert.deepEqual(f.inputs,[],JSON.stringify(names));
  }
});

test('selection rejects stale, UI, wrong-step, focus-loss, and Windows-session-loss states',async()=>{
  const stale=fixture(),staleObs=await stale.observe();stale.advance(1001);await assert.rejects(()=>stale.adapter.falconSelectAmber());
  assert.ok(staleObs.hud.health);assert.deepEqual(stale.inputs,[]);
  for(const ui of [{journal:true},{auto:true},{choice:true},{climbing:true},{objectiveChanged:true},{bigMap:true}]){
    const f=fixture({ui}),o=await f.observe();assert.ok(o.hud.health);assert.equal(o.hud[Object.keys(ui)[0]],true,JSON.stringify(ui));
    await assert.rejects(()=>f.adapter.falconSelectAmber());assert.deepEqual(f.inputs,[],JSON.stringify(ui));
  }
  const wrongStep=fixture({step:'falconCombat'});await wrongStep.observe();await assert.rejects(()=>wrongStep.adapter.falconSelectAmber());assert.deepEqual(wrongStep.inputs,[]);
  const wrongMission=fixture({mission:'recover'});await wrongMission.observe();await assert.rejects(()=>wrongMission.adapter.falconSelectAmber());assert.deepEqual(wrongMission.inputs,[]);
  const unfocused=fixture();await unfocused.observe();unfocused.setFocus(false);await assert.rejects(()=>unfocused.adapter.falconSelectAmber(),/foreground/);assert.deepEqual(unfocused.inputs,[]);
  const sessionLost=fixture();await sessionLost.observe();sessionLost.setSession(8);await assert.rejects(()=>sessionLost.adapter.falconSelectAmber());assert.deepEqual(sessionLost.inputs,[]);
});
