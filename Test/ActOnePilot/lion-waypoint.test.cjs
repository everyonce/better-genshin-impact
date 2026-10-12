'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const dir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=100,height=20)=>({text,x,y,width,height});
function frame(patch={}) {return {session:'s1',timestamp:2000000,frameId:55,map:{map:'Teyvat',x:-1000,y:2100},ocr:[],
  hud:{world:true,objectives:['Meet Lisa at the temple'],health:{current:1000,max:1427},lowHealth:false,dialogueReady:false,choice:false,
    journal:false,bigMap:false,climbing:false,tutorialStep:null,objectiveChanged:false},...patch};}
function fixture() {
  let now=2000000,rows=[],map={x:-1000,y:2100}; const calls=[],files=new Map();
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:5,isGameForeground:true,getPositionFromMap:()=>map,getCameraOrientation:()=>0,
      tp:async(x,y,force)=>{calls.push(['tp',x,y,force]);now+=15;}},
    file:{isExists:p=>files.has(p),readTextSync:p=>fs.existsSync(path.join(dir,p))?fs.readFileSync(path.join(dir,p),'utf8'):'',
      writeTextSync:(p,v)=>{files.set(p,v);return true;},writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},
    ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const a=(this.mat.rows||[]).map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}}}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{rows},findMulti:()=>{const a=rows.map(r=>({...r}));a.count=a.length;return a;},
      deriveCrop:(x,y)=>({srcMat:{resize:()=>({rows:[]})},dispose(){}}),dispose(){}}),
    keyDown:k=>calls.push(['down',k]),keyUp:k=>calls.push(['up',k]),moveMouseBy(){},sleep:async ms=>{calls.push(['sleep',ms]);now+=ms;},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(dir,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(5);
  return {adapter,calls,files,setRows:r=>{rows=r;},setNow:n=>{now=n;},setMap:p=>{map=p;}};
}

test('Lion waypoint readiness requires fresh same-session Teyvat world state, exact Lisa objective and safe HUD',()=>{
  const base=frame();
  assert.equal(bgi.lionFalconWaypointReady(base,2000000,'s1'),true);
  for(const bad of [
    {...base,timestamp:1998999},{...base,timestamp:2000001},{...base,session:'s2'},
    {...base,map:{map:'Other',x:-1000,y:2100}},{...base,map:null},{...base,hud:{...base.hud,world:false}},
    {...base,hud:{...base.hud,objectives:['Meet Kaeya at the temple']}},
    {...base,hud:{...base.hud,health:{current:850,max:1427}}},
    ...['dialogueReady','choice','journal','bigMap','climbing','objectiveChanged'].map(k=>({...base,hud:{...base.hud,[k]:true}})),
    {...base,hud:{...base.hud,tutorialStep:'aimSlime'}},
  ]) assert.equal(bgi.lionFalconWaypointReady(bad,2000000,'s1'),false);
});

test('Lion Falcon waypoint opens map briefly, teleports once to the fixed waypoint and records source frame',async()=>{
  const f=fixture();
  f.adapter.beginMission({mission:'questStep',step:'lionFalconWaypoint',session:'s1',expectedFrameId:55,createdAt:1999000,objective:'Meet Lisa at the temple'});
  f.setRows([row('Meet Lisa at the temple',100,250,260,22),row('1000/1427',910,1003,97,14)]);
  await f.adapter.observe('s1',55);
  assert.equal(f.adapter.lionFalconWaypointReady(),true);
  const result=await f.adapter.teleportLionFalconWaypoint();
  assert.deepEqual(JSON.parse(JSON.stringify(result)),{x:-1122.173,y:2197.455,frameId:55,session:'s1'});
  assert.deepEqual(f.calls.filter(c=>c[0]==='tp'),[['tp',-1122.173,2197.455,false]]);
  assert.deepEqual(f.calls.slice(0,4),[['down','VK_M'],['sleep',50],['sleep',10],['up','VK_M']]);
  assert.ok(f.calls.some(c=>c[0]==='sleep'&&c[1]===200));
  const event=f.adapter.events().find(e=>e.type==='lionFalconWaypoint');
  assert.deepEqual(JSON.parse(JSON.stringify(event)),{type:'lionFalconWaypoint',x:-1122.173,y:2197.455,frameId:55,session:'s1',startedAt:2000260,finishedAt:2000275});
  await assert.rejects(()=>f.adapter.teleportLionFalconWaypoint(),/Fresh safe same-session Lisa objective/);
  assert.equal(f.calls.filter(c=>c[0]==='tp').length,1);
});

test('Lion waypoint adapter does not teleport with stale or unsafe observations',async()=>{
  const f=fixture();
  f.adapter.beginMission({mission:'questStep',step:'lionFalconWaypoint',session:'s1',expectedFrameId:55,createdAt:1999000,objective:'Meet Lisa at the temple'});
  f.setRows([row('Meet Kaeya at the temple',100,250,260,22),row('1000/1427',910,1003,97,14)]);
  await f.adapter.observe('s1',55);
  assert.equal(f.adapter.lionFalconWaypointReady(),false);
  await assert.rejects(()=>f.adapter.teleportLionFalconWaypoint(),/Fresh safe same-session Lisa objective/);
  assert.equal(f.calls.some(c=>c[0]==='tp'),false);
});
