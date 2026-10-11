const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const packageDir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const source=fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8');
const row=(text,x,y,width=50,height=20)=>({text,x,y,width,height});

async function observeStep(step, missionName='questStep') {
  // Frame 66 bar bounds are x=651..812, y=364..377. A bar pixel is RGB(255,90,90),
  // or BGR(90,90,255), which must survive the detector color threshold.
  const fullRows=[row('Lv. 5',690,330,82,25),row('626/1427',910,1000,100,25),row('E',1700,1015,30,20)];
  const bar={x:301,y:264,width:161,height:14};
  let enemyScans=0;
  const context={
    Date:class extends Date{static now(){return 2000000;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:()=>false,readTextSync:p=>fs.readFileSync(path.join(packageDir,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},
    ImageRegion:class{
      constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}
      findMulti(){const rows=this.mat&&this.mat.healthCrop?[row('626/1427',30,25,150,30)]:[];rows.count=rows.length;return rows;}
      dispose(){}
    },
    OpenCvSharp:{OpenCvSharp:{
      Size:class{constructor(w,h){this.width=w;this.height=h;}},
      Scalar:class{constructor(a,b,c){this.values=[a,b,c];}},
      RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},
      Cv2:{boundingRect:c=>c,contourArea:()=>0}
    }},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},
      findMulti:()=>{const rows=fullRows.map(r=>({...r}));rows.count=rows.length;return rows;},
      deriveCrop:(x,y,w,h)=>({srcMat:{
        inRange:(low,high)=>{
          if(x===350&&y===100) enemyScans++;
          const bgr=[90,90,255];
          const pixelPass=bgr.every((v,i)=>v>=low.values[i]&&v<=high.values[i]);
          return {findContoursAsArray:()=>x===350&&y===100&&pixelPass?[bar]:[],dispose(){}};
        },
        resize:()=>({healthCrop:x===900&&y===990})
      },dispose(){}}),dispose(){}}),
    sleep:async()=>{},click:()=>{},log:{info(){}}
  };
  vm.runInNewContext(source,context);
  const adapter=context.createActOneAdapter(7);
  adapter.beginMission({mission:missionName,step,session:'test',createdAt:2000000});
  const observation=await adapter.observe('test',66);
  return {bars:JSON.parse(JSON.stringify(observation.hud.enemyBars)),enemyScans};
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
