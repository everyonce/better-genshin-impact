const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

function frame(objective, x, y, angle) {
  return { map: { map: 'Teyvat', x, y, cameraAngle: angle }, ocr: [], hud: {
    world: true, dialogueReady: false, choice: false, journal: false, bigMap: false,
    objectiveChanged: false, lowHealth: false, health: { current: 900, max: 1000 }, objectives: [objective],
  } };
}

test('HQ waypoint uses 2m arrival radius while normal navigation keeps 5m', async () => {
  const hqObjective = 'Go to the Knights of Favonius Headquarters';
  let now = 1000, hqX = -875;
  const hqInput = [];
  const hqApi = { now: () => now, sleep: async ms => { now += ms; }, checkStop: () => {},
    rotate: async () => assert.fail('route begins aligned'),
    forward: async ms => { hqInput.push(ms); now += ms; hqX -= 1; } };
  const hqResult = await mission.runNavigation({ objective: hqObjective, deadlineMs: 5000,
    waypoints: [{ map: 'Teyvat', x: -879, y: 2263 }] }, frame(hqObjective, hqX, 2263, 0), hqApi,
  async () => frame(hqObjective, hqX, 2263, 0));
  assert.equal(hqResult.status, 'arrived');
  assert.deepEqual(hqInput, [250, 250], 'at 4m HQ routing moves until within 2m');

  let normalNow = 1000; const normalInput = [];
  const normalObjective = 'Follow the road to Mondstadt';
  const normalApi = { now: () => normalNow, sleep: async ms => { normalNow += ms; }, checkStop: () => {},
    rotate: async () => assert.fail('route begins aligned'),
    forward: async ms => { normalInput.push(ms); normalNow += ms; } };
  const normalResult = await mission.runNavigation({ objective: normalObjective, deadlineMs: 5000,
    waypoints: [{ map: 'Teyvat', x: 4, y: 0 }] }, frame(normalObjective, 0, 0, 180), normalApi,
  async () => frame(normalObjective, 0, 0, 180));
  assert.equal(normalResult.status, 'arrived');
  assert.deepEqual(normalInput, [], 'normal 5m arrival behavior is unchanged');
});

test('HQ door interaction ends approach before walking into the closed door', async () => {
 const objective='Enter the Knights of Favonius Headquarters';const o=frame(objective,-778.2,2243.7,180);o.hud.interact=true;
 const api={now:()=>0,checkStop:()=>{},forward:async()=>assert.fail('already at door'),rotate:async()=>assert.fail('already at door')};
 const r=await mission.runNavigation({objective,deadlineMs:5000,waypoints:[{map:'Teyvat',x:-775,y:2243}]},o,api,async()=>o);
 assert.equal(r.reason,'Interaction available');assert.equal(r.movements,0);
});

test('Talk to Amber uses a 2m radius and stops at a fresh interaction prompt', async () => {
 const objective='Talk to Amber';let now=0,x=-4;const inputs=[];
 const api={now:()=>now,sleep:async ms=>{now+=ms;},checkStop:()=>{},rotate:async()=>assert.fail('route begins aligned'),
  forward:async ms=>{inputs.push(ms);now+=ms;x+=1;}};
 const request={objective,deadlineMs:5000,waypoints:[{map:'Teyvat',x:0,y:0}]};
 const result=await mission.runNavigation(request,frame(objective,x,0,180),api,async()=>frame(objective,x,0,180));
 assert.equal(result.status,'arrived');assert.deepEqual(inputs,[250,250],'at 4m, movement continues until within 2m');

 const prompted=frame(objective,-4,0,180);prompted.hud.interact=true;
 prompted.ocr=[{text:'Amber',x:1250,y:450},{text:'F',x:1098,y:522}];
 const stopped=await mission.runNavigation(request,prompted,{now:()=>0,checkStop:()=>{},forward:async()=>assert.fail('interaction prompt must stop approach'),rotate:async()=>assert.fail('already aligned')},async()=>prompted);
 assert.equal(stopped.status,'stopped');assert.equal(stopped.reason,'Interaction available');assert.equal(stopped.movements,0);

 const wrongName=frame(objective,-4,0,180);wrongName.hud.interact=true;wrongName.ocr=[{text:'Kaeya',x:1250,y:450},{text:'F',x:1098,y:522}];
 let moved=0;
 let continueNow=0;const continueApi={now:()=>continueNow,sleep:async ms=>{continueNow+=ms;},checkStop:()=>{},rotate:async()=>assert.fail('already aligned'),forward:async()=>{moved++;continueNow+=250;}};
 const continueResult=await mission.runNavigation(request,wrongName,continueApi,async()=>frame(objective,-2,0,180));
 assert.equal(continueResult.status,'arrived');assert.equal(moved,1,'unrelated NPC interaction does not end Amber approach');
});

test('Enter the temple ignores Amber prompt and stops only for a temple target label', async () => {
 const objective='Enter the temple',request={objective,deadlineMs:5000,waypoints:[{map:'Teyvat',x:6,y:0}]};
 const amber=frame(objective,0,0,180);amber.hud.interact=true;amber.ocr=[{text:'Amber',x:1250,y:450},{text:'F',x:1098,y:522}];
 let moved=0;let now=0;const api={now:()=>now,sleep:async ms=>{now+=ms;},checkStop:()=>{},rotate:async()=>assert.fail('route begins aligned'),forward:async()=>{moved++;now+=250;}};
 const continued=await mission.runNavigation(request,amber,api,async()=>frame(objective,6,0,180));
 assert.equal(continued.status,'arrived');assert.equal(moved,1,'Amber is not the temple interaction target');

 const temple=frame(objective,0,0,180);temple.hud.interact=true;temple.ocr=[
  {text:'Temple of the',x:1228,y:506,width:181,height:35},{text:'Falcon',x:1217,y:532,width:98,height:42},
  {text:'F',x:1098,y:522,width:40,height:34},
 ];
 const stopped=await mission.runNavigation(request,temple,{now:()=>0,checkStop:()=>{},forward:async()=>assert.fail('temple target should stop'),rotate:async()=>assert.fail('already aligned')},async()=>temple);
 assert.equal(stopped.status,'stopped');assert.equal(stopped.reason,'Interaction available');assert.equal(stopped.movements,0);
});
