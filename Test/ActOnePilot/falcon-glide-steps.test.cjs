const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const packageDir = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const bgiSource = fs.readFileSync(path.join(packageDir, 'bgi.js'), 'utf8');
const bgi = require(path.join(packageDir, 'bgi.js'));
const mission = require(path.join(packageDir, 'mission.js'));

function domainRows({space=false,climb=false,hp='900/1000'}={}) {
  const rows=[
    {text:'Amber',x:1600,y:400,width:65,height:24},
    {text:'Trial',x:1750,y:420,width:45,height:20},
    {text:hp,x:910,y:1000,width:85,height:22},
    {text:'E',x:1700,y:1015,width:24,height:24},
  ];
  if(space) rows.push({text:'Space',x:1680,y:1024,width:52,height:24});
  if(climb) rows.push({text:'X',x:1596,y:1024,width:24,height:24});
  return rows;
}

function adapterHarness({rows=domainRows(),reports=[],stopAfterSleep=false}={}) {
  let clock=1000,stop=false;
  const inputs=[],mouse=[],writes=[];
  const readRows=(image,x,y)=>{
    const found=(image.rows||[]).filter(r=>!((x===1520&&y===985)&&r.text==='never'));
    found.count=found.length;return found;
  };
  const makeImage=(imageRows)=>({width:1920,height:1080,srcMat:{},rows:imageRows,
    findMulti:function(ro){return readRows(this,ro.x,ro.y);},
    deriveCrop:()=>({srcMat:{resize:()=>({})},dispose(){}}),dispose(){}});
  const context={
    Date:class extends Date { static now(){return clock;} },
    genshin:{isRemoteDesktopSession:true,windowsSessionId:5,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='stop.json'&&stop,readTextSync:p=>{
      if(p.startsWith('reports/')) return JSON.stringify(reports);
      if(p==='stop.json') return JSON.stringify({session:'test-session',createdAt:1000});
      const full=path.join(packageDir,p);return fs.existsSync(full)?fs.readFileSync(full,'utf8'):'';
    },writeTextSync:(p,v)=>{writes.push([p,v]);return true;},writeImageSync:()=>true},
    RecognitionObject:{Ocr:(x,y,w,h)=>({x,y,w,h})},
    ImageRegion:class {constructor(mat){this.width=1920;this.height=1080;this.srcMat=mat;this.rows=[];this.findMulti=function(){const a=[];a.count=0;return a};}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class {constructor(w,h){this.width=w;this.height=h;}}}},
    captureGameRegion:()=>makeImage(rows),sleep:async ms=>{clock+=ms;if(stopAfterSleep)stop=true;},
    keyDown:k=>inputs.push(['down',k,clock]),keyUp:k=>inputs.push(['up',k,clock]),moveMouseBy:(x,y)=>mouse.push([x,y]),
    click:()=>{},log:{info(){}},
  };
  vm.runInNewContext(bgiSource,context);
  const adapter=context.createActOneAdapter(5);
  return {adapter,inputs,mouse,writes,advance:ms=>clock+=ms,setStop:()=>stop=true,now:()=>clock,
    observe:()=>adapter.observe('test-session',1),begin:step=>adapter.beginMission({mission:'questStep',step,session:'test-session',createdAt:clock})};
}

const glideReport=[{status:'completed',details:{result:{step:'falconGlideForward'}}}];
const shotReport=[{status:'completed',timestamp:900,details:{result:{step:'falconFireAim'}}}];

test('crystal strike requires its request, fresh safe domain HUD, and completed glide evidence',async()=>{
  const missing=adapterHarness();missing.begin('falconCrystalStrike');await missing.observe();
  await assert.rejects(missing.adapter.falconCrystalStrike(),/glide progression required/);
  assert.deepEqual(missing.inputs,[]);

  const valid=adapterHarness({reports:glideReport});valid.begin('falconCrystalStrike');await valid.observe();
  await valid.adapter.falconCrystalStrike();
  assert.deepEqual(valid.inputs.map(x=>x.slice(0,2)),[['down','VK_LBUTTON'],['up','VK_LBUTTON']]);
  assert.equal(valid.adapter.events().find(e=>e.type==='key').durationMs,60);
});

test('crystal and wind actions reject wrong step, stale HUD, and unsafe health without input',async()=>{
  const wrong=adapterHarness({reports:glideReport});wrong.begin('falconWindJump');await wrong.observe();
  await assert.rejects(wrong.adapter.falconCrystalStrike(),/Fresh Falcon HUD/);
  await assert.rejects(wrong.adapter.falconWindJump(),/Recent Falcon Pyro shot required/);
  assert.deepEqual(wrong.inputs,[]);

  const stale=adapterHarness({reports:shotReport});stale.begin('falconWindJump');await stale.observe();stale.advance(1001);
  await assert.rejects(stale.adapter.falconWindJump(),/Fresh Falcon ground HUD/);
  const low=adapterHarness({rows:domainRows({hp:'500/1000'}),reports:shotReport});low.begin('falconWindJump');await low.observe();
  await assert.rejects(low.adapter.falconWindJump(),/Fresh Falcon ground HUD/);
  assert.deepEqual(stale.inputs,[]);assert.deepEqual(low.inputs,[]);
});

test('wind jump requires recent Pyro-shot report and emits two bounded Space holds with releases',async()=>{
  const absent=adapterHarness();absent.begin('falconWindJump');await absent.observe();
  await assert.rejects(absent.adapter.falconWindJump(),/Recent Falcon Pyro shot required/);
  assert.deepEqual(absent.inputs,[]);

  const valid=adapterHarness({reports:shotReport});valid.begin('falconWindJump');await valid.observe();
  await valid.adapter.falconWindJump();
  assert.deepEqual(valid.inputs.map(x=>x[0]+':'+x[1]),['down:VK_SPACE','up:VK_SPACE','down:VK_SPACE','up:VK_SPACE']);
  assert.ok(valid.adapter.events().filter(e=>e.type==='key').every(e=>e.key==='VK_SPACE'&&e.durationMs===60));
  assert.equal(valid.adapter.events().filter(e=>e.type==='key').length,2);
});

test('wind jump rejects an expired or future-dated Pyro-shot receipt',async()=>{
  for(const timestamp of [-600000,1000000]) {
    const h=adapterHarness({reports:[{...shotReport[0],timestamp}]});h.begin('falconWindJump');await h.observe();
    await assert.rejects(h.adapter.falconWindJump(),/Recent Falcon Pyro shot required/);
    assert.deepEqual(h.inputs,[]);
  }
});

test('stop during the first Space hold releases the key and prevents the second jump',async()=>{
  const h=adapterHarness({reports:shotReport,stopAfterSleep:true});h.begin('falconWindJump');await h.observe();
  await assert.rejects(h.adapter.falconWindJump(),/Stop requested/);
  assert.deepEqual(h.inputs.map(x=>x[0]+':'+x[1]),['down:VK_SPACE','up:VK_SPACE']);
});

test('glide action accepts Space-only midair evidence and rejects absent Space or climbing evidence',async()=>{
  const noSpace=adapterHarness({reports:glideReport});noSpace.begin('falconGlideForward');await noSpace.observe();
  await assert.rejects(noSpace.adapter.falconGlideForward(),/Fresh Falcon gliding HUD/);
  const climbing=adapterHarness({rows:domainRows({space:true,climb:true}),reports:glideReport});climbing.begin('falconGlideForward');await climbing.observe();
  await assert.rejects(climbing.adapter.falconGlideForward(),/Fresh Falcon gliding HUD/);
  const valid=adapterHarness({rows:domainRows({space:true}),reports:glideReport});valid.begin('falconGlideForward');await valid.observe();
  await valid.adapter.falconGlideForward();
  assert.deepEqual(valid.inputs.map(x=>x[0]+':'+x[1]),['down:VK_W','up:VK_W']);
  assert.equal(valid.adapter.events().find(e=>e.type==='key').durationMs,800);
  assert.deepEqual(noSpace.inputs,[]);assert.deepEqual(climbing.inputs,[]);
});

function missionFrame(groundControls) {return {frameId:1,hud:{groundControls},ocr:[],map:null};}
test('glide policy stops at first ground-control transition and reports landing still needs inspection',async()=>{
  let now=0,observations=0;const actions=[];
  const api={now:()=>now,sleep:async ms=>{now+=ms;},checkStop:()=>{},falconGlideForward:async()=>actions.push('forward')};
  const result=await mission.runQuestStep('falconGlideForward',missionFrame(false),api,async()=>{
    observations++;return {...missionFrame(true),frameId:1+observations};
  });
  assert.deepEqual(actions,['forward']);assert.equal(observations,1);
  assert.equal(result.frameId,2);assert.match(result.reason,/inspect landing/i);
  assert.doesNotMatch(result.reason,/landed|landing confirmed/i);
});

test('glide policy remains bounded to twelve holds when no ground-control transition appears',async()=>{
  let now=0,observations=0;const actions=[];
  const api={now:()=>now,sleep:async ms=>{now+=ms;},checkStop:()=>{},falconGlideForward:async()=>actions.push('forward')};
  const result=await mission.runQuestStep('falconGlideForward',missionFrame(false),api,async()=>{
    observations++;return {...missionFrame(false),frameId:1+observations};
  });
  assert.equal(actions.length,12);assert.equal(observations,12);assert.equal(result.status,'completed');
});

test('dialogue completes only on the exact fresh domain-return banner with safe HUD evidence',async()=>{
  const banner={text:'Leaving in 8 second(s)',x:802,y:952,width:210,height:28};
  const base={frameId:20,map:null,hud:{world:false,groundControls:true,health:{current:900,max:1000},dialogueReady:false,choice:false},ocr:[banner]};
  const run=async current=>{
    let now=1000,inputs=0;
    const result=await mission.runDialogue({now:()=>now,sleep:async ms=>{now+=ms;},checkStop:()=>{},keyPress:async()=>inputs++},async()=>current);
    return {result,inputs};
  };
  const valid=await run(base);
  assert.equal(valid.result.status,'completed');assert.equal(valid.result.reason,'completed_domain_returned');assert.equal(valid.inputs,0);
  for(const current of [
    {...base,map:{map:'Teyvat'},hud:{...base.hud,world:true}},
    {...base,hud:{...base.hud,health:null}},
    {...base,hud:{...base.hud,choice:true}},
    {...base,ocr:[{...banner,text:'Leaving in 8 seconds'}]},
    {...base,ocr:[{...banner,x:1200}]},
  ]) {
    const rejected=await run(current);
    assert.notEqual(rejected.result.reason,'completed_domain_returned');assert.equal(rejected.inputs,0);
  }
});

test('Falcon domain HUD accepts Leaving banner in place of Trial only on fresh safe mapless HUD',()=>{
  const rows=[{text:'Amber',x:1600,y:400,width:65,height:24},{text:'Leaving in 8 second(s)',x:802,y:952,width:210,height:28}];
  const frame={timestamp:1000,map:null,ocr:rows,hud:{world:false,groundControls:true,climbing:false,journal:false,bigMap:false,
    dialogueReady:false,choice:false,tutorialStep:null,objectiveChanged:false,health:{current:900,max:1000},lowHealth:false}};
  assert.equal(bgi.falconDomainHud(frame,1500),true);
  assert.equal(bgi.falconDomainHud({...frame,timestamp:0},1500),false);
  assert.equal(bgi.falconDomainHud({...frame,hud:{...frame.hud,health:{current:500,max:1000}}},1500),false);
  assert.equal(bgi.falconDomainHud({...frame,map:{map:'Teyvat'}},1500),false);
  assert.equal(bgi.falconDomainHud({...frame,ocr:rows.filter(r=>r.text==='Amber')},1500),false);
});
