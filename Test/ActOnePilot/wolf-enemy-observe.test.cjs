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
      findMulti(){const rows=this.mat&&this.mat.levelCrop?(options.railSample?.labels||[]).map(r=>({...r})):this.mat&&this.mat.healthCrop?[row(options.health||'626/1427',30,25,150,30)]:[];rows.count=rows.length;return rows;}
      dispose(){}
    },
    OpenCvSharp:{OpenCvSharp:{
      Size:class{constructor(w,h){this.width=w;this.height=h;}},
      Scalar:class{constructor(a,b,c){this.values=[a,b,c];}},
      ColorConversionCodes:{BGR2GRAY:6},
      Mat:class{inRange(lo,hi){assert.equal(lo.values[0],20);assert.equal(hi.values[0],255);return this;}
        findContoursAsArray(){assert.equal(this.combined,true);return options.railSample?.contours||[];}
        dispose(){}},
      RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},
      Cv2:{subtract:options.railSample?(outside,center,out)=>{
          const r=options.railSample.red,cx=r.x+r.width,cy=Math.round(r.y+r.height/2),gap=Math.ceil(r.height/2)+3;
          assert.deepEqual([center.x,center.y,center.w,center.h],[cx,cy-1,155,3]);
          assert.equal(outside.x,cx);assert.equal(Math.abs(outside.y-center.y),gap);out.offset=outside.y-center.y;
        }:undefined,bitwiseAnd:options.railSample?(up,down,out)=>{assert(up.offset<0&&down.offset>0);out.combined=true;}:undefined,
        boundingRect:c=>c,contourArea:c=>options.area===undefined?c.area===undefined?Math.max(0,((c.width||c.Width)-1)*((c.height||c.Height)-1)):c.area:options.area,
        countNonZero:mask=>mask.pixelCount!==undefined?mask.pixelCount:mask.flameCount===undefined?(options.redPixels??100):mask.flameCount}
    }},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},
      findMulti:roi=>{const rows=fullRows.filter(r=>!roi||r.x>=roi.x&&r.y>=roi.y&&r.x<roi.x+roi.w&&r.y<roi.y+roi.h).map(r=>({...r}));rows.count=rows.length;return rows;},
      deriveCrop:(x,y,w,h)=>({srcMat:{
        inRange:(low,high)=>{
          const tile=(options.terrainTiles||[]).find(t=>x>=t.x&&y>=t.y&&x+w<=t.x+t.w&&y+h<=t.y+t.h);
          if(tile){
            let pixelCount=0;
            for(let j=y;j<y+h;j++)for(let i=x;i<x+w;i++){
              const k=3*((j-tile.y)*tile.w+i-tile.x);
              if([tile.rgb[k+2],tile.rgb[k+1],tile.rgb[k]].every((v,c)=>v>=low.values[c]&&v<=high.values[c]))pixelCount++;
            }
            return {pixelCount,dispose(){}};
          }
          if(x===350&&y===100) enemyScans++;
          const bgr=[90,90,255];
          const pixelPass=bgr.every((v,i)=>v>=low.values[i]&&v<=high.values[i]);
          if(x===0&&y===30)groundScans++;
          // Replay retained threshold pixels for the solid-core boundary; OCR and inputs stay inert.
          const sample=options.solidPixels;
          let pixelCount;
          if(sample&&x>=sample.x&&y>=sample.y&&x+w<=sample.x+sample.width&&y+h<=sample.y+sample.height){
            pixelCount=0;
            for(let py=y;py<y+h;py++)for(let px=x;px<x+w;px++)pixelCount+=sample.rows[py-sample.y][px-sample.x]==='1'?1:0;
          }
          return {pixelCount,flameCount:w===25&&h===10?(options.flameCounts?.[y]??0):undefined,findContoursAsArray:()=>{
            if(sample&&x===sample.x&&y===sample.y+sample.coreStartRow&&w===sample.width&&h===sample.coreRows)
              return options.coreContours??[{x:0,y:0,width:w,height:h,area:sample.coreArea}];
            if(options.trailSample||options.railSample){
              const {red,gold}=options.trailSample||options.railSample;
              if(pixelPass&&(x===350&&y===100||x===0&&y===30))return [{...red,x:red.x-x,y:red.y-y}];
              const rgb=[255,209,126],bgr=[rgb[2],rgb[1],rgb[0]];
              if(bgr.every((v,i)=>v>=low.values[i]&&v<=high.values[i])&&gold&&
                 gold.x>=x&&gold.y>=y&&gold.x+gold.width<=x+w&&gold.y+gold.height<=y+h)
                return [{...gold,x:gold.x-x,y:gold.y-y}];
            }
            if(x===0&&y===30){if(options.detectorError)throw Error('inert detector failure');
              return Object.hasOwn(options,'contours')?options.contours:[];}
            return x===350&&y===100&&pixelPass?(sample?[{x:sample.x-x,y:sample.y-y,width:sample.width,height:sample.height,area:sample.outerArea}]:[bar]):[];
          },dispose(){}};
        },
        cvtColor:()=>({x,y,w,h,dispose(){}}),
        resize:()=>({healthCrop:x===900&&y===990,levelCrop:w===130&&h===24})
      },dispose(){}}),dispose(){}}),
    sleep:async()=>{},click:()=>{},log:{info(){}}
  };
  if(options.pngDelay)context.file.writeImageAsync=async()=>{now+=options.pngDelay;return true;};
  vm.runInNewContext(source,context);
  const adapter=context.createActOneAdapter(7,options.inventoryUiOnly?{inventoryUiOnlyV1:true}:undefined);
  if(!options.idle)adapter.beginMission({mission:missionName,step,session:'test',createdAt:2000000,...options.request});
  if(options.rotationEvent)adapter.events().push(options.rotationEvent);
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
  // Gate-to-camp frame 76: a flame at (1375.5,180.5) produced 4.5 pixels of contour area in an 11Ã—9 box.
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

const solidFixture=require('./enemy-bar-solid-core.fixture.json');
// Public06 frame13: the 67x5 outer component has area176.5; its three solid rows have area128.
const solidOptions=(extra={})=>({solidPixels:structuredClone(solidFixture),contours:[{x:solidFixture.x,y:solidFixture.y-30,width:67,height:5,area:176.5}],...extra});
test('actual anti-aliased Lv6 bar reconstructs measured solid core and preserves original diagnostics',async()=>{
 const x=await measure(solidOptions());const d=x.observation.hud.enemyBarDiagnostic;
 assert.equal(x.observation.hud.enemyBarObservation.state,'threat');assert.equal(x.bars.length,1);
 assert.deepEqual(x.bars[0],{x:1419.5,y:457.5,width:67,height:3,rectangularity:128/132});
 assert.equal(d.rawCandidates[0].height,5);assert.equal(d.rawCandidates[0].rectangularity,176.5/264);
 assert.deepEqual(d.solidCores[0].rowCounts,[19,64,67,64,30]);assert.deepEqual(d.solidCores[0].centralCounts,[19,61,61,61,29]);
 assert.equal(d.solidCores[0].contourArea,128);assert.equal(d.localReads.length,0);
});
test('explicit pack receives measured core while old ordinary combat retains its original result',async()=>{
 const opts={...groundOptions(),...solidOptions()};
 const pack=await observeStep('actTwoFieldCombat','questStep',opts);
 assert.equal(pack.bars[0].rectangularity,128/132);assert.equal(pack.observation.hud.enemyBarDiagnostic.solidCores.length,1);
 const old=await observeStep('actTwoNativeCombat','questStep',opts);
 assert.deepEqual(old.bars,[]);assert.equal(old.observation.hud.enemyBarDiagnostic.solidCores,undefined);
});
test('two solid rows, central holes and separated red rows cannot reconstruct a bar',async()=>{
 for(const mutate of [s=>{s.rows[3]='0'.repeat(67);},s=>{s.rows[2]=s.rows[2].slice(0,30)+'0'+s.rows[2].slice(31);},
  s=>{s.rows=[s.rows[1],'0'.repeat(67),s.rows[1],'0'.repeat(67),s.rows[1]];}]){
  const opts=solidOptions();mutate(opts.solidPixels);const x=await measure(opts);
  assert.equal(x.observation.hud.enemyBarObservation.state,'ambiguous');assert.deepEqual(x.bars,[]);
  assert.deepEqual(x.observation.hud.enemyBarDiagnostic.solidCores,[]);
 }
});
test('short flames, invalid inner contour quality and foreign geometry gain no reconstructed authority',async()=>{
 const short=await measure({contours:[{x:1000,y:300,width:25,height:5,area:30}],solidPixels:solidFixture});
 assert.deepEqual(short.bars,[]);assert.deepEqual(short.observation.hud.enemyBarDiagnostic.solidCores,[]);
 for(const coreContours of [[{x:0,y:0,width:67,height:3,area:20}],[{x:0,y:0,width:20,height:3,area:38}],
  [{x:0,y:0,width:67,height:3,area:128},{x:0,y:0,width:67,height:3,area:128}]]){
  const x=await measure(solidOptions({coreContours}));assert.deepEqual(x.bars,[]);assert.equal(x.observation.hud.enemyBarObservation.state,'ambiguous');
 }
 const malformed=await measure(solidOptions({coreContours:[{x:1,y:0,width:67,height:3,area:128}]}));
 assert.equal(malformed.observation.hud.enemyBarObservation.state,'unavailable');
});

// Same-image OpenCV red contours and gold RGB(255,209,126) spans from Temple public09.
const hitFrames=[
 {frame:22,red:{x:989,y:565,width:4,height:8,area:8},gold:{x:994,y:566,width:62,height:5}},
 {frame:23,red:{x:980,y:577,width:4,height:7,area:10},gold:{x:986,y:577,width:50,height:7}},
 {frame:24,red:{x:968,y:438,width:3,height:6,area:6},gold:{x:972,y:437,width:44,height:7}}
];
const returnedHit={type:'actTwoNativeCombat',chunkIndex:1,actionId:'field-test:rotation:1',finishedAt:1999900,nativeReturned:true};
function damageRead(trailSample,rotationEvent=returnedHit,step='actTwoFieldCombat'){
 return observeStep(step,'questStep',{...groundOptions(),trailSample,rotationEvent,request:{id:'field-test'}});
}
test('post-hit Temple frames retain the depleted target using its adjoining gold contour',async()=>{
 for(const sample of hitFrames){
  const {bars}=await damageRead(sample);
  assert.equal(bars.length,1);const bar=bars[0];
  assert.equal(bar.damageTrail.actionId,returnedHit.actionId);
  assert.equal(bar.damageTrail.remainingRed.width,sample.red.width);
  assert.deepEqual([bar.x,bar.y,bar.width,bar.height],[sample.gold.x+sample.gold.width/2,sample.gold.y+sample.gold.height/2,sample.gold.width,sample.gold.height]);
 }
});
test('a distant or missing trail and a stale, failed, foreign or absent rotation grant no field target',async()=>{
 const sample=hitFrames[0];
 for(const update of [{gold:null},{gold:{...sample.gold,x:1005}},{gold:{...sample.gold,width:8}},
                       {gold:{...sample.gold,area:40}},{gold:{...sample.gold,y:572}}]){
  assert.deepEqual((await damageRead({...sample,...update})).bars,[]);
 }
 for(const event of [null,{...returnedHit,actionId:'other:rotation:1'},{...returnedHit,nativeReturned:false},
                     {...returnedHit,finishedAt:1997400},{...returnedHit,finishedAt:2000001}]){
  assert.deepEqual((await damageRead(sample,event)).bars,[]);
 }
 assert.deepEqual((await damageRead(sample,returnedHit,'actTwoNativeCombat')).bars,[]);
});

// Temple frame 65 replay. Red and rail geometry come from the original capture;
// the local label is the installed V6 model's result on the exact 3x OpenCV crop.
const rail65={red:{x:1428,y:536,width:3,height:6,area:5},
 contours:[{x:1,y:0,width:90,height:3,area:164.5}],
 labels:[row('Lv.6',58,-0,174,72)]};
test('fresh depleted rail and centered exact level identify a live target for route observation and combat entry',async()=>{
 for(const mission of ['observe','questStep']){
  const x=await observeStep(mission==='questStep'?'actTwoFieldCombat':undefined,mission,{...groundOptions(),railSample:rail65});
  assert.equal(x.bars.length,1);const b=x.bars[0];assert.equal(b.width,90);assert.equal(b.x,1477);
  assert.equal(b.rectangularity,164.5/178);assert.equal(b.depletedRail.remainingRed.width,3);assert.equal(b.depletedRail.level.text,'Lv.6');
  if(mission==='observe')assert.equal(x.observation.hud.enemyBarObservation.state,'threat');
 }
});
test('depleted rail needs three contrast rows and an exact same-image centered level',async()=>{
 for(const sample of [{...rail65,labels:[]},{...rail65,labels:[row('Ly.6',58,0,174,72)]},
    {...rail65,labels:[row('Lv.6',155,0,174,72)]},{...rail65,labels:[...rail65.labels,...rail65.labels]},
    {...rail65,contours:[]},{...rail65,contours:[{x:1,y:0,width:90,height:3,area:22.5}]},
    {...rail65,contours:[{x:10,y:0,width:90,height:3,area:170}]},
    {...rail65,contours:[{x:1,y:1,width:90,height:2,area:86}]}]){
  const x=await measure({railSample:sample});assert.equal(x.bars.length,0);
  assert.equal(x.observation.hud.enemyBarObservation.state,'ambiguous');
 }
});

// Return a small crop including the two-pixel rim; no account or screenshot is needed.
function warmStreetCase(x=900){
  const contour={x,y:368,width:5,height:7,area:6},w=9,h=11,rgb=[];
  for(let j=0;j<h;j++)for(let i=0;i<w;i++){
    const inner=i>=2&&i<7&&j>=2&&j<9;
    rgb.push(...(inner&&(i+j)%3===0?[233,108,77]:[222,109,76]));
  }
  return {contour,tile:{x:x-2,y:396,w,h,rgb}};
}
test('sparse warm street texture requires all fringe pixels and a warm surrounding rim',async()=>{
  async function sample(change,rows=groundRows()){
    const {contour,tile}=warmStreetCase();if(change)change(contour,tile);
    return (await measure({contours:[contour],terrainTiles:[tile],rows})).observation.hud;
  }
  const hud=await sample();assert.equal(hud.enemyBarObservation.state,'clear');
  assert.equal(hud.enemyBarDiagnostic.rawCandidates.length,1);assert.equal(hud.enemyBarDiagnostic.candidates,1);
  assert.equal(hud.enemyBarDiagnostic.fieldCandidates.length,0);
  assert.equal(hud.enemyBarDiagnostic.warmTerrain[0].redPixels,hud.enemyBarDiagnostic.warmTerrain[0].warmRedPixels);
  for(const change of [
    (c,t)=>t.rgb.splice(3*(2*t.w+2),3,255,90,90), // A single enemy-health core pixel.
    (c,t)=>{for(let x=0;x<t.w;x++)for(const y of [0,1,t.h-2,t.h-1])t.rgb.splice(3*(y*t.w+x),3,80,80,80);},
    (c,t)=>{c.area=22;}, // Near-solid compact contours remain ambiguous even in a warm environment.
    (c,t)=>{c.width=9;}
  ])assert.equal((await sample(change)).enemyBarObservation.state,'ambiguous');
  const anchored=await sample(null,[...groundRows(),row('Lv. 5',881,359,40,18)]);
  assert.equal(anchored.enemyBarObservation.state,'threat');assert.equal(anchored.enemyBars.length,1);
});
test('extra tiny components stay unresolved when their pixel-probe budget is exhausted',async()=>{
  const cases=Array.from({length:9},(_,i)=>warmStreetCase(900+i*16));
  const hud=(await measure({contours:cases.map(c=>c.contour),terrainTiles:cases.map(c=>c.tile)})).observation.hud;
  assert.equal(hud.enemyBarDiagnostic.rawCandidates.length,9);assert.equal(hud.enemyBarDiagnostic.warmTerrain.length,8);
  assert.equal(hud.enemyBarObservation.state,'ambiguous');assert.equal(hud.enemyBarObservation.candidateCount,1);
});
