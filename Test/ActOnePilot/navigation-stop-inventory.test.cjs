const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const objective='Keep heading towards Mondstadt';
function frame({x=0,hp=1000,interact=false,ocr=[],world=true,climbing=false,overrides={}}={}) {
  return {frameId:1,map:{map:'Teyvat',x,y:0,cameraAngle:180},ocr,hud:{world,objectives:[objective],health:{current:hp,max:1000},
    lowHealth:false,interact,climbing,groundControls:!climbing,dialogueReady:false,choice:false,objectiveChanged:false,journal:false,bigMap:false,...overrides}};
}
function stopHarness({initial=frame(),observations=[],pauseResult=true,inventoryRows=[{text:'Food',x:150,y:50}],confirm=true}={}) {
  let now=1000,index=0;const events=[],moves=[];
  const api={now:()=>now,sleep:async ms=>{now+=ms;events.push(['sleep',ms]);},checkStop:()=>events.push(['guard']),
    rotate:async dx=>{events.push(['rotate',dx]);},forward:async ms=>{moves.push(ms);events.push(['forward',ms]);now+=ms;},
    pauseWorldInventory:async()=>{events.push(['pause',index]);return pauseResult;}};
  const observe=async()=>{index++;events.push(['observe',index]);return observations[index-1]||observations.at(-1)||frame({hp:800});};
  return {events,moves,get index(){return index;},run:()=>mission.runNavigation({objective,deadlineMs:20000,waypoints:[{map:'Teyvat',x:100,y:0}]},initial,api,observe)};
}

test('health-drop stop observes fresh state before pausing and confirms the inventory header',async()=>{
  const h=stopHarness({observations:[frame({x:1,hp:800}),frame({x:1,hp:800}),frame({x:1,hp:800,world:false,ocr:[{text:'Food',x:150,y:50}]})]});
  const result=await h.run();
  assert.match(result.reason,/Health dropped/);assert.equal(result.pausedInventory,true);
  const observeIndex=h.events.findIndex(e=>e[0]==='observe'),pauseIndex=h.events.findIndex(e=>e[0]==='pause');
  assert.ok(observeIndex>=0&&observeIndex<pauseIndex,'stop takes a fresh observation before asking the adapter to pause');
  assert.equal(h.events[pauseIndex][1],2,'pause consumes the second fresh frame, after the movement result and stop refresh');
  assert.deepEqual(h.moves,[800]);
});

test('failed pause or unrecognized post-pause screen never claims inventory is open',async()=>{
  const failed=stopHarness({pauseResult:false,observations:[frame({x:1,hp:800}),frame({x:1,hp:800})]});
  const failedResult=await failed.run();
  assert.notEqual(failedResult.pausedInventory,true);
  assert.equal(failed.events.some(e=>e[0]==='sleep'&&e[1]===500),false);

  const wrongScreen=stopHarness({observations:[frame({x:1,hp:800}),frame({x:1,hp:800}),frame({x:1,hp:800,world:false,ocr:[{text:'Options',x:150,y:50}]})]});
  const wrongResult=await wrongScreen.run();
  assert.equal(wrongResult.pausedInventory,false);
});

test('inventory transition polling confirms a delayed header with one B press and bounded waits',async()=>{
  const transition=frame({x:1,hp:800,world:false,ocr:[{text:'Inventory',x:800,y:500}]});
  const food=frame({x:1,hp:800,world:false,ocr:[{text:'Food',x:150,y:50}]});
  const h=stopHarness({observations:[frame({x:1,hp:800}),frame({x:1,hp:800}),transition,food]});
  const result=await h.run();
  assert.equal(result.pausedInventory,true);
  assert.equal(h.events.filter(e=>e[0]==='pause').length,1,'do not repeat the inventory toggle while the opening animation runs');
  assert.equal(h.events.filter(e=>e[0]==='sleep'&&e[1]===500).length,2,'poll at bounded 500 ms intervals until the header appears');
});

test('inventory polling gives up after four observations without exact category evidence',async()=>{
  const unknown=frame({x:1,hp:800,world:false,ocr:[{text:'Inventory',x:800,y:500}]});
  const h=stopHarness({observations:[frame({x:1,hp:800}),frame({x:1,hp:800}),unknown,unknown,unknown,unknown]});
  const result=await h.run();
  assert.equal(result.pausedInventory,false);
  assert.equal(h.events.filter(e=>e[0]==='pause').length,1);
  assert.equal(h.events.filter(e=>e[0]==='sleep'&&e[1]===500).length,4);
});

test('normal arrival and intended interaction stop do not invoke inventory pause',async()=>{
  let now=0,pauseCalls=0;
  const api={now:()=>now,sleep:async ms=>{now+=ms;},checkStop:()=>{},rotate:async()=>{},forward:async()=>{},pauseWorldInventory:async()=>{pauseCalls++;return true;}};
  const arrived=await mission.runNavigation({objective,deadlineMs:5000,waypoints:[{map:'Teyvat',x:1,y:0}]},frame(),api,async()=>frame());
  assert.equal(arrived.status,'arrived');
  const targetObjective='Investigate what Paimon has found';
  const current={...frame({interact:true}),hud:{...frame({interact:true}).hud,objectives:[targetObjective]}};
  const interaction=await mission.runNavigation({objective:targetObjective,deadlineMs:5000,waypoints:[{map:'Teyvat',x:10,y:0}]},current,api,async()=>current);
  assert.equal(interaction.reason,'Interaction available');assert.equal(pauseCalls,0);
});

function adapterContext(rows) {
  const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
  const source=fs.readFileSync(path.join(root,'bgi.js'),'utf8'),events=[];
  function makeImage(imageRows) {return {width:1920,height:1080,srcMat:{},rows:imageRows,
    findMulti(ro){const found=imageRows.filter(r=>!(ro.x===1520&&ro.y===985));found.count=found.length;return found;},dispose(){}};}
  const context={genshin:{isRemoteDesktopSession:true,windowsSessionId:5,isGameForeground:true,getPositionFromMap:()=>({x:0,y:0}),getCameraOrientation:()=>180},
    file:{isExists:()=>false,writeImageSync:()=>true,writeTextSync:()=>true},RecognitionObject:{Ocr:(x,y)=>({x,y})},
    captureGameRegion:()=>makeImage(rows),keyDown:k=>events.push(['down',k]),keyUp:k=>events.push(['up',k]),click:()=>{},moveMouseBy:()=>{},sleep:async ms=>new Promise(resolve=>setTimeout(resolve,ms)),
    log:{info(){}},events};
  vm.runInNewContext(source,context);return {adapter:context.createActOneAdapter(5),events};
}
function baseRows() {return [{text:'900/1000',x:910,y:1000,width:85,height:22},{text:'E',x:1700,y:1015,width:24,height:24}];}

test('adapter pauses with bounded B only on a fresh safe world observation',async()=>{
  const safe=adapterContext(baseRows());await safe.adapter.observe('s',1);
  assert.equal(await safe.adapter.pauseWorldInventory(),true);
  assert.deepEqual(safe.events,[['down','VK_B'],['up','VK_B']]);
});

test('adapter declines climb, journal, choice, and dialogue screens without pressing B',async()=>{
  const unsafe=[
    [...baseRows(),{text:'X',x:1596,y:1024,width:24,height:24},{text:'Space',x:1680,y:1024,width:52,height:24}],
    [...baseRows(),{text:'In Progress',x:70,y:50,width:120,height:22}],
    [...baseRows(),{text:'Auto',x:50,y:20,width:60,height:20},{text:'Purchase Item',x:1200,y:500,width:150,height:24}],
    [...baseRows(),{text:'Auto',x:50,y:20,width:60,height:20},{text:'Paimon',x:700,y:850,width:80,height:24},{text:'We should keep moving forward',x:650,y:900,width:340,height:30}],
  ];
  for(const rows of unsafe) {
    const h=adapterContext(rows);await h.adapter.observe('s',1);
    assert.equal(await h.adapter.pauseWorldInventory(),false);
    assert.deepEqual(h.events,[]);
  }
});
