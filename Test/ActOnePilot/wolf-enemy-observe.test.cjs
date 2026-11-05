const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const packageDir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const source=fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8');
const row=(text,x,y,width=50,height=20)=>({text,x,y,width,height});

async function observeStep(step, missionName='questStep', options={}) {
  // Frame 66 bar bounds are x=651..812, y=364..377. A bar pixel is RGB(255,90,90),
  // or BGR(90,90,255), which must survive the detector color threshold.
  const fullRows=options.rows||[row('Lv. 5',690,330,82,25),row('626/1427',910,1000,100,25),row('E',1700,1015,30,20)];
  const bar={x:301,y:264,width:161,height:14};
  let enemyScans=0,now=2000000,groundScans=0;
  const context={
    host:{toSingle:v=>v},
    Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>options.map||null,getCameraOrientation:()=>0},
    file:{isExists:()=>false,readTextSync:p=>fs.readFileSync(path.join(packageDir,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:(x=0,y=0,w=1920,h=1080)=>({x,y,w,h})},
    ImageRegion:class{
      constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}
      findMulti(){const rows=this.mat&&this.mat.healthCrop?[row(options.health||'626/1427',30,25,150,30)]:[];rows.count=rows.length;return rows;}
      dispose(){}
    },
    OpenCvSharp:{OpenCvSharp:{
      Size:class{constructor(w,h){this.width=w;this.height=h;}},
      Scalar:class{constructor(a,b,c){this.values=[a,b,c];}},
      RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},
      Cv2:{boundingRect:c=>c,contourArea:c=>options.area===undefined?c.area===undefined?Math.max(0,((c.width||c.Width)-1)*((c.height||c.Height)-1)):c.area:options.area,
        countNonZero:mask=>mask.flameCount===undefined?(options.redPixels??100):mask.flameCount}
    }},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},
      findMulti:roi=>{const rows=fullRows.filter(r=>!roi||r.x>=roi.x&&r.y>=roi.y&&r.x<roi.x+roi.w&&r.y<roi.y+roi.h).map(r=>({...r}));rows.count=rows.length;return rows;},
      deriveCrop:(x,y,w,h)=>({srcMat:{
        inRange:(low,high)=>{
          if(x===350&&y===100) enemyScans++;
          const bgr=[90,90,255];
          const pixelPass=bgr.every((v,i)=>v>=low.values[i]&&v<=high.values[i]);
          if(x===0&&y===30)groundScans++;
          return {flameCount:w===25&&h===10?(options.flameCounts?.[y]??0):undefined,findContoursAsArray:()=>{
            if(x===0&&y===30){if(options.detectorError)throw Error('inert detector failure');
              return Object.hasOwn(options,'contours')?options.contours:[];}
            return x===350&&y===100&&pixelPass?[bar]:[];
          },dispose(){}};
        },
        resize:()=>({healthCrop:x===900&&y===990})
      },dispose(){}}),dispose(){}}),
    sleep:async()=>{},click:()=>{},log:{info(){}}
  };
  if(options.pngDelay)context.file.writeImageAsync=async()=>{now+=options.pngDelay;return true;};
  vm.runInNewContext(source,context);
  const adapter=context.createActOneAdapter(7,options.inventoryUiOnly?{inventoryUiOnlyV1:true}:undefined);
  if(!options.idle)adapter.beginMission({mission:missionName,step,session:'test',createdAt:2000000,...options.request});
  const observation=await adapter.observe('test',66);
  return {bars:JSON.parse(JSON.stringify(observation.hud.enemyBars)),enemyScans,groundScans,
    observation:JSON.parse(JSON.stringify(observation))};
}

test('all Wolf trial movement, look, info, pause, and continue observations retain the saved-frame Lv.5 bar', async()=>{
  // Frame 66 is WolfLookRight. Bounds are x=651..812, y=364..377; a bar pixel is RGB(255,90,90), BGR(90,90,255).
  const expected=[{x:731.5,y:371,width:161,height:14}];
  for(const step of ['wolfAdvance','wolfLookRight','wolfLookLeft','wolfLookDown','wolfLookUp','wolfInfo','wolfPause','wolfContinue','wolfForwardFine','wolfCombat','wolfOpeningDialogue']) {
    const result=await observeStep(step);
    assert.deepEqual(result.bars,expected,step);
    assert.equal(result.enemyScans,1,step);
  }
});

test('level-five enemy scan stays scoped away from Wolf entrance and unrelated quest requests',async()=>{
  for(const step of ['wolfEntryApproach','falconForward']) {
    const result=await observeStep(step);
    assert.deepEqual(result.bars,[]);
    assert.equal(result.enemyScans,0,step);
  }
  const unrelated=await observeStep('wolfLookRight','navigation');
  assert.deepEqual(unrelated.bars,[]);
  assert.equal(unrelated.enemyScans,0);
});

// Exercise the complete observer with inert native image/OCR boundaries, never an input actor.
const groundRows=()=>[row('4015/4015',910,1000,100,25),row('E',1700,1015,30,20),row('UID: 693306810',1690,1050,180,25)];
const groundOptions=()=>({rows:groundRows(),health:'4015/4015',map:{x:-1325.4,y:2565.19}});
const measure=options=>observeStep(undefined,'observe',{...groundOptions(),...options});

test('normal explicit ground observe distinguishes measured clear and preserves the capture-start source join',async()=>{
  const x=await measure({redPixels:0,pngDelay:37});
  assert.equal(x.groundScans,1);assert.deepEqual(x.bars,[]);
  assert.deepEqual(x.observation.hud.enemyBarObservation,{version:1,kind:'normal-ground-enemy-observation-v1',state:'clear',
    session:'test',frameId:66,capturedAt:2000000,reason:'no_bar_shaped_components',candidateCount:0,acceptedCount:0});
  assert.equal(x.observation.hud.captureStamp.capturedAt,2000000);
  assert.equal(x.observation.timestamp,2000037);
});

test('normal observe retains a visible rectangular bar even without any tracked objective or level OCR',async()=>{
  const x=await measure({contours:[{x:900,y:152,width:75,height:6}]});
  assert.equal(x.observation.hud.enemyBarObservation.state,'threat');
  assert.equal(x.observation.hud.enemyBarObservation.acceptedCount,1);
  assert.equal(x.bars[0].x,937.5);assert.equal(x.bars[0].y,185);
  assert.deepEqual(x.observation.hud.objectives,[]);
});

test('edge and depleted bar-shaped candidates rejected by level OCR remain ambiguous rather than clear',async()=>{
  for(const contour of [{x:140,y:369,width:76,height:6},{x:920,y:152,width:12,height:6}]){
    const x=await measure({contours:[contour]});
    assert.equal(x.observation.hud.enemyBarObservation.state,'ambiguous');assert.deepEqual(x.bars,[]);
    assert.equal(x.observation.hud.enemyBarObservation.candidateCount,1);
    assert.equal(x.observation.hud.enemyBarDiagnostic.rawCandidates.length,1);
  }
});

test('sparse camp torch outline is diagnostic only; dense or anchored fragments still stop exploration',async()=>{
  // Gate-to-camp frame 76: a flame at (1375.5,180.5) produced 4.5 pixels of contour area in an 11×9 box.
  const torch={x:1370,y:146,width:11,height:9,area:4.5};
  const clear=await measure({contours:[torch],redPixels:38,flameCounts:{185:144,166:0}});
  assert.equal(clear.observation.hud.enemyBarObservation.state,'clear');
  assert.equal(clear.observation.hud.enemyBarDiagnostic.rawCandidates[0].rectangularity,.05625);
  assert.equal(clear.observation.hud.enemyBarObservation.candidateCount,0);
  const flicker={x:1370,y:151,width:9,height:6,area:10};
  const clearFlicker=await measure({contours:[flicker],flameCounts:{188:151,169:0}});
  assert.equal(clearFlicker.observation.hud.enemyBarObservation.state,'clear');
  assert.equal(clearFlicker.observation.hud.enemyBarDiagnostic.flameTips[0].orangePixelsBelow,151);
  // Next camp capture showed two tips simultaneously, including a taller 12-by-14 outline.
  const twoTips=await measure({contours:[{x:1346,y:151,width:12,height:14,area:4.5},{x:1371,y:151,width:12,height:12,area:16.5}],flameCounts:{192:145,173:2,191:123,172:0}});
  assert.equal(twoTips.observation.hud.enemyBarObservation.state,'clear');
  assert.equal(twoTips.observation.hud.enemyBarDiagnostic.flameTips.length,2);
  for(const flameCounts of [{},{185:95,166:0},{185:144,166:100}]){
    const fragment=await measure({contours:[torch],flameCounts});
    assert.equal(fragment.observation.hud.enemyBarObservation.state,'ambiguous');
  }
  const dense=await measure({contours:[{...torch,area:60}],flameCounts:{185:144}});
  assert.equal(dense.observation.hud.enemyBarObservation.state,'ambiguous');
  const tiny=await measure({contours:[{...torch,width:3,height:3,area:0.1}]});
  assert.equal(tiny.observation.hud.enemyBarObservation.state,'ambiguous');
  const horizontal=await measure({contours:[{...torch,width:26,height:5}]});
  assert.equal(horizontal.observation.hud.enemyBarObservation.state,'ambiguous');
  const anchored=await measure({contours:[torch],flameCounts:{185:144},rows:[...groundRows(),row('Lv.6',1355,153,36,16)]});
  assert.equal(anchored.observation.hud.enemyBarObservation.state,'threat');
});

test('native indexed array and Pascal-case rectangle shapes are measured without Array.isArray assumptions',async()=>{
  for(const contours of [{0:{X:900,Y:152,Width:75,Height:6},Length:1},{0:{x:900,y:152,width:75,height:6},length:1}]){
    const x=await measure({contours});assert.equal(x.observation.hud.enemyBarObservation.state,'threat');
  }
});

test('detector exceptions and malformed native shapes never produce measured clear',async()=>{
  for(const options of [{detectorError:true},{contours:null},{contours:{}},{contours:{length:1}},
    {contours:[{x:0,y:0,width:NaN,height:5}]},{contours:[{x:1910,y:10,width:50,height:5}]},
    {contours:[{x:900,y:152,width:75,height:6}],area:NaN},{redPixels:NaN}]){
    const x=await measure(options);assert.equal(x.observation.hud.enemyBarObservation.state,'unavailable');
    assert.equal(x.observation.hud.enemyBarObservation.reason,'detector_result_unavailable_or_rejected');
  }
});

test('color, component and candidate overloads explicitly refuse clear evidence',async()=>{
  for(const options of [{redPixels:100000},{contours:{length:4097}},
    {contours:Array.from({length:65},(_,i)=>({x:400+i*10,y:200,width:5,height:4}))}]){
    const x=await measure(options);assert.equal(x.observation.hud.enemyBarObservation.state,'overloaded');
    assert.deepEqual(x.bars,[]);
  }
});

test('only positively recognized ground receives the new scan; UI, climbing, missing pose and dead HP remain unavailable',async()=>{
  for(const options of [{map:null},{rows:[...groundRows(),row('Space',1700,1015)]},
    {rows:[...groundRows(),row('Auto',100,30)]},{rows:[...groundRows(),row('In Progress',200,40)]},
    {health:'0/4015',rows:groundRows().map(r=>r.text==='4015/4015'?{...r,text:'0/4015'}:r)}]){
    const x=await measure(options);assert.equal(x.groundScans,0);
    assert.equal(x.observation.hud.enemyBarObservation.state,'unavailable');
  }
});

test('inventory-only and passive idle observers retain their existing lightweight contracts',async()=>{
  for(const options of [{inventoryUiOnly:true},{idle:true}]){
    const x=await measure(options);assert.equal(x.groundScans,0);
    assert.equal(x.observation.hud.enemyBarObservation,undefined);
  }
});

test('only explicitly opted-in free exploration requests receive the same per-capture measurement',async()=>{
  const waypoints=[{map:'Teyvat',x:-1325.4,y:2565.19}];
  const x=await observeStep(undefined,'navigation',{...groundOptions(),request:{waypoints,objective:'Explore for Adventure Rank',requireMeasuredGround:true}});
  assert.equal(x.groundScans,1);assert.equal(x.enemyScans,0);
  assert.equal(x.observation.hud.enemyBarObservation.state,'clear');
  for(const request of [{objective:'Explore for Adventure Rank'},{objective:'Explore for Adventure Rank',requireMeasuredGround:'true'},
    {objective:'Go to the exam point',requireMeasuredGround:true}]){
    const old=await observeStep(undefined,'navigation',{...groundOptions(),request:{waypoints,...request}});
    assert.equal(old.groundScans,0);assert.equal(old.observation.hud.enemyBarObservation,undefined);
  }
});

test('the three Gate07 saved-image red components cannot become a clear untracked observation',async()=>{
  // PNG SHA ee643e569596e31af482582b5c412afcdb3f3bb8df4bf19571bdc17f7d93688b.
  // Exact 8-connected BGR-threshold bounds, measured from the original 1920x1080 PNG.
  // Native contour/OCR calls remain inert here; this is not a live recognition qualification.
  const contours=[{x:141,y:369,width:75,height:6},{x:922,y:154,width:64,height:4},{x:437,y:389,width:49,height:5}];
  const x=await measure({contours,redPixels:862});
  assert.equal(x.observation.hud.enemyBarObservation.state,'threat');
  assert.equal(x.observation.hud.enemyBarObservation.candidateCount,3);
  assert.equal(x.observation.hud.enemyBarDiagnostic.rawCandidates[0].x,178.5);
  assert.equal(x.observation.hud.enemyBarDiagnostic.localReads.length,0);
});

test('R63 saved clear scene excludes its small side-HUD fragment but retains the raw detector evidence',async()=>{
  // Shipped OpenCvSharp replay: original top-left (1647,569), 8x7, contour area 17.
  const x=await measure({contours:[{x:1647,y:539,width:8,height:7,area:17}]});
  assert.equal(x.observation.hud.enemyBarObservation.state,'clear');
  assert.equal(x.observation.hud.enemyBarObservation.candidateCount,0);
  assert.equal(x.observation.hud.enemyBarDiagnostic.rawCandidates.length,1);
  assert.equal(x.observation.hud.enemyBarDiagnostic.rawCandidates[0].x,1651);
});

test('travel03 actual native contour geometry preserves all three close hostile bars',async()=>{
  // Original PNG SHA 64a3b5152cc6d87f779b2962cbe6da4b2c1bf22633cb28b15b786f29f3d6aa52.
  // Exact shipped OpenCvSharp contour bounds/areas; y is relative to the new 30px crop origin.
  const contours=[[1167,895,8,5,17],[1154,894,10,6,28],[1408,685,15,10,66.5],
    [1266,567,158,13,1697],[1405,514,109,9,844.5],[772,369,156,12,1654]]
    .map(([x,y,width,height,area])=>({x,y:y-30,width,height,area}));
  const x=await measure({contours,redPixels:5000});
  assert.equal(x.observation.hud.enemyBarObservation.state,'threat');
  assert.equal(x.observation.hud.enemyBarObservation.acceptedCount,3);
  assert.equal(x.observation.hud.enemyBarDiagnostic.rawCandidates.length,6);
  assert.equal(x.observation.hud.enemyBarDiagnostic.localReads.length,0);
});
