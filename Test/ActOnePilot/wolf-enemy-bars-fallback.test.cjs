const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const packageDir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const source=fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8');
const row=(text,x,y,width=50,height=20)=>({text,x,y,width,height});

async function observe({contours, fullLabels=[], localLabels={}, pixel=[90,90,255]}) {
  const full=[...fullLabels,row('Kaeya',1664,484),row('Trial',1796,463),row('1000/1000',912,1003,195,14),row('E',1700,1015,30,20)];
  const crops=[];
  const context={
    Date:class extends Date{static now(){return 2000000;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:()=>false,readTextSync:p=>fs.readFileSync(path.join(packageDir,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},
    ImageRegion:class{
      constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}
      findMulti(){const result=this.mat&&this.mat.local?this.mat.rows.map(r=>({...r})):[];result.count=result.length;return result;}
      dispose(){}
    },
    OpenCvSharp:{OpenCvSharp:{
      Size:class{constructor(w,h){this.width=w;this.height=h;}},
      Scalar:class{constructor(a,b,c){this.values=[a,b,c];}},
      RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:c=>c,contourArea:()=>0}
    }},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const result=full.map(r=>({...r}));result.count=result.length;return result;},
      deriveCrop:(x,y,w,h)=>{
        if(x===350&&y===100) return {srcMat:{inRange:(low,high)=>({findContoursAsArray:()=>{
          const pass=pixel.every((v,i)=>v>=low.values[i]&&v<=high.values[i]);return pass?contours:[];
        },dispose(){}})},dispose(){}};
        crops.push({x,y,w,h});
        const labels=localLabels[`${x},${y}`]||[];
        return {srcMat:{resize:()=>({local:true,rows:labels.map(r=>({...r,x:(r.x-x)*3,y:(r.y-y)*3,width:r.width*3,height:r.height*3}))})},dispose(){}};
      },dispose(){}}),
    sleep:async()=>{},click:()=>{},log:{info(){}}
  };
  vm.runInNewContext(source,context);
  const adapter=context.createActOneAdapter(7);
  adapter.beginMission({mission:'questStep',step:'wolfLookLeft',session:'test',createdAt:2000000});
  const result=await adapter.observe('test',1);
  return {bars:JSON.parse(JSON.stringify(result.hud.enemyBars)),crops};
}

test('larger local OCR crop includes a low Lv.5 label clipped by the previous crop',async()=>{
  const bar={x:198,y:375,width:28,height:6}; // full-screen center x=562, y=478
  const label=row('Lv.5',550,456,24,18);
  const result=await observe({contours:[bar],localLabels:{'412,408':[label]}});
  assert.deepEqual(result.bars,[{x:562,y:478,width:28,height:6}],JSON.stringify(result.crops));
  assert.deepEqual(result.crops,[{x:412,y:408,w:300,h:90}]);
});

test('tries a missed candidate locally even when another enemy is anchored in full-frame OCR',async()=>{
  const bars=[{x:250,y:280,width:72,height:8},{x:587,y:375,width:28,height:6}];
  const fullLabels=[row('Lv.5',605,328,55,20)];
  const result=await observe({contours:bars,fullLabels,localLabels:{'801,408':[row('Lv.5',940,456,24,18)]}});
  assert.equal(result.bars.length,2);
  assert.deepEqual(result.bars.map(b=>b.x),[636,951]);
  assert.equal(result.crops.length,1);
});

test('rejects incorrect level labels and red-like contours outside the accepted color range',async()=>{
  const bar={x:301,y:264,width:161,height:14};
  const wrongLevel=await observe({contours:[bar],fullLabels:[row('Lv.4',690,330,82,25)],localLabels:{'581,294':[row('Lv.4',690,330,82,25)]}});
  assert.deepEqual(wrongLevel.bars,[]);
  const wrongColor=await observe({contours:[bar],fullLabels:[row('Lv.5',690,330,82,25)],pixel:[120,90,255]});
  assert.deepEqual(wrongColor.bars,[]);
});

test('keeps local candidate OCR bounded to four crops per frame',async()=>{
  const contours=Array.from({length:7},(_,i)=>({x:80+i*150,y:200,width:20,height:6}));
  const result=await observe({contours});
  assert.equal(result.crops.length,4);
  assert.deepEqual(result.bars,[]);
});
