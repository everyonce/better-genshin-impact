const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const packageDir = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=101,height=20)=>({text,x,y,width,height});
async function adapterHealth({full='369/1055',primary='369/1053',left='369',right='1055',narrowLeft=left}) {
  const cropRows={health: [row(primary,5,5,280,50)],left:[row(left,5,5,80,45)],narrowLeft:[row(narrowLeft,5,5,80,45)],right:[row(right,5,5,80,45)]};
  const fullRows=[row(full,906,1001,101,20),row('E',1700,1015,30,20),row('Q',1760,1015,30,20)];
  const context={Date:class extends Date{static now(){return 2000000;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>({x:-1640,y:2159}),getCameraOrientation:()=>0},
    file:{isExists:()=>false,readTextSync:p=>fs.readFileSync(path.join(packageDir,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},
    ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const found=(this.mat&&this.mat.cropKey?cropRows[this.mat.cropKey]:fullRows).map(r=>({...r}));found.count=found.length;return found;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}}}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const found=fullRows.map(r=>({...r}));found.count=found.length;return found;},deriveCrop:(x,y,w)=>({srcMat:{resize:()=>({cropKey:x===900?'health':x===905?'narrowLeft':x===893?'left':'right'})},dispose(){}}),dispose(){}}),
    sleep:async()=>{},click:()=>{},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);adapter.beginMission({mission:'observe',session:'hp',createdAt:2000000});
  return adapter.observe('hp',1);
}
test('numeric halves may rescue a low full-frame HP row only when both readings agree exactly',()=>{
 const full=[row('369/1055',906,1001)];
 assert.deepEqual(bgi.corroboratedFullHealth(full,[row('369',0,0)],[row('1055',0,0)]),full[0]);
 assert.equal(bgi.corroboratedFullHealth(full,[row('368',0,0)],[row('1055',0,0)]),null);
 assert.equal(bgi.corroboratedFullHealth(full,[row('369',0,0),row('369',0,0)],[row('1055',0,0)]),null);
});
test('adapter falls through conflicting scaled HP OCR when independent halves agree with the full row',async()=>{
 const o=await adapterHealth({});
 assert.deepEqual(JSON.parse(JSON.stringify(o.hud.health)),{current:369,max:1055});assert.equal(o.hud.world,true);
 assert.deepEqual(JSON.parse(JSON.stringify(o.hud.healthDiagnostic)),{fullRow:['369/1055'],primary:['369/1053'],left:['369'],right:['1055'],decision:'halves-agree-after-primary-conflict'});
});
test('adapter fails closed when either independent HP half disagrees with full-frame OCR',async()=>{
 const o=await adapterHealth({right:'1054'});
 assert.equal(o.hud.health,null);assert.equal(o.hud.world,false);
 assert.deepEqual(JSON.parse(JSON.stringify(o.hud.healthDiagnostic)),{fullRow:['369/1055'],primary:['369/1053'],left:['369'],right:['1054'],decision:'conflict-halves-disagree-or-missing'});
});

test('slash-contaminated HP needs an independently read narrower crop and matching maximum',async()=>{
 for(const [narrowLeft,right,accepted] of [['477','1363',true],['476','1363',false],['4771','1363',false],['477','1362',false]]){
  const o=await adapterHealth({full:'477/1363',primary:'1477/1363',left:'4771',right,narrowLeft});
  assert.deepEqual(o.hud.health?JSON.parse(JSON.stringify(o.hud.health)):null,accepted?{current:477,max:1363}:null);
 }
});

test('missing full HP row can use two valid independent halves without copying or trimming failed OCR',async()=>{
 const o=await adapterHealth({full:'',primary:'1477/1363',left:'4771',right:'1363',narrowLeft:'477'});
 assert.deepEqual(JSON.parse(JSON.stringify(o.hud.health)),{current:477,max:1363});
 const bad=await adapterHealth({full:'',primary:'1477/1363',left:'4771',right:'1363',narrowLeft:'4771'});assert.equal(bad.hud.health,null);
});
