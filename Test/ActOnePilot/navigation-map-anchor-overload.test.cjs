const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const packageDir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
function adapterWithSingleMapBinding() {
  const source=fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8'),calls=[];
  const rows=[{text:'900/1000',x:910,y:1000,width:85,height:22},{text:'E',x:1700,y:1015,width:24,height:24}];
  const image={width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows.slice();a.count=a.length;return a;},dispose(){}};
  const context={
    genshin:{isRemoteDesktopSession:true,windowsSessionId:5,isGameForeground:true,getCameraOrientation:()=>180,
      getPositionFromMap:function(mapName,x,y){calls.push({mapName,x,y});if(arguments.length===3&&(Math.fround(x)!==x||Math.fround(y)!==y))throw new TypeError('host overload requires Single coordinates');return {x:x,y:y};}},
    host:{toSingle:value=>Math.fround(value)},
    file:{isExists:()=>false,readTextSync:name=>fs.readFileSync(path.join(packageDir,name),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:(x,y,w,h)=>({x,y,w,h})},captureGameRegion:()=>image,
    keyDown:()=>{},keyUp:()=>{},moveMouseBy:()=>{},click:()=>{},sleep:async()=>{},log:{info(){}},
  };
  vm.runInNewContext(source,context);
  return {adapter:context.createActOneAdapter(5),calls};
}

test('navigation converts waypoint seed to Single precision for the typed host overload',async()=>{
  const h=adapterWithSingleMapBinding();
  h.adapter.beginMission({mission:'navigation',session:'s',id:'i',createdAt:Date.now(),expectedFrameId:0,objective:'Meet Amber',deadlineMs:10000,
    waypoints:[{map:'Teyvat',x:-1122.173,y:2197.455}]});
  const observation=await h.adapter.observe('s',1);
  assert.deepEqual(h.calls,[{mapName:'Teyvat',x:Math.fround(-1122.173),y:Math.fround(2197.455)}]);
  assert.ok(!Number.isInteger(h.calls[0].x)&&!Number.isInteger(h.calls[0].y),'preserve float precision rather than rounding route anchors');
  assert.ok(Math.abs(observation.map.x+1122.173)<=0.001&&Math.abs(observation.map.y-2197.455)<=0.001);
});

test('subsequent accepted map anchors also use Single precision',async()=>{
  const h=adapterWithSingleMapBinding();
  h.adapter.beginMission({mission:'navigation',session:'s',id:'i',createdAt:Date.now(),expectedFrameId:0,objective:'Meet Amber',deadlineMs:10000,
    waypoints:[{map:'Teyvat',x:-1122.173,y:2197.455}]});
  await h.adapter.observe('s',1);
  await h.adapter.observe('s',2);
  assert.deepEqual(h.calls.map(c=>[c.x,c.y]),[[Math.fround(-1122.173),Math.fround(2197.455)],[Math.fround(-1122.173),Math.fround(2197.455)]]);
});

test('navigation candidate thresholds remain 150m initially and 25m from the last accepted position',()=>{
  const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
  const request={mission:'navigation',waypoints:[{map:'Teyvat',x:-1122.173,y:2197.455}]};
  const first=bgi.navigationMapAnchor(request,null),accepted=bgi.acceptNavigationPosition(request,null,{x:-1122.173,y:2197.455});
  const next=bgi.navigationMapAnchor(request,{x:accepted.x,y:accepted.y});
  assert.equal(first.maxDistance,150);assert.equal(next.maxDistance,25);
  assert.ok(bgi.acceptNavigationPosition(request,null,{x:first.x+150,y:first.y}));
  assert.equal(bgi.acceptNavigationPosition(request,null,{x:first.x+150.01,y:first.y}),null);
  assert.ok(bgi.acceptNavigationPosition(request,accepted,{x:accepted.x+25,y:accepted.y}));
  assert.equal(bgi.acceptNavigationPosition(request,accepted,{x:accepted.x+25.01,y:accepted.y}),null);
});

test('field combat preparation rejection skips inventory cleanup and all subsequent combat actions',async()=>{
  let now=0,pauses=0,selects=0,fights=0;const frames=[];
  const observation={frameId:3,map:{map:'Teyvat',x:0,y:0,cameraAngle:0},hud:{world:true,health:{current:900,max:1000},objectives:['Meet Kaeya at the temple']},ocr:[]};
  const api={now:()=>now,sleep:async ms=>{now+=ms;},fieldFightPrepare:async()=>{throw new Error('Food inventory prerequisite absent');},
    fieldSelectTraveler:async()=>{selects++;},fieldNativeFight:async()=>{fights++;},pauseWorldInventory:async()=>{pauses++;return true;}};
  const result=await mission.runQuestStep('fieldCombat',observation,api,async()=>{frames.push(1);return observation;});
  assert.equal(result.status,'stopped');assert.match(result.reason,/Food inventory prerequisite absent/);
  assert.equal(pauses,0);assert.equal(selects,0);assert.equal(fights,0);assert.equal(frames.length,1);
});
