const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const objective = 'Go to the Knights of Favonius Headquarters';
function frame({ climbing = true, x = -795.5, y = 2282.95, angle = 140,
  health = { current: 1000, max: 1000 }, groundControls = false, ...patch } = {}) {
  return { frameId: 1, map: { map: 'Teyvat', x, y, cameraAngle: angle }, hud: {
    world: true, climbing, groundControls, health, lowHealth: false, dialogueReady: false, choice: false,
    journal: false, bigMap: false, tutorialStep: null, objectiveChanged: false, objectives: [objective], ...patch,
  } };
}
function harness(observations) {
  let now = 1000, index = 0; const calls = [];
  const api = {
    now: () => now,
    sleep: async ms => { calls.push(['sleep', ms]); now += ms; },
    checkStop: () => calls.push(['checkStop']),
    forward: async ms => { calls.push(['forward', ms]); now += ms; },
  };
  async function observe() { const next = observations[Math.min(index++, observations.length - 1)]; calls.push(['observe', next]); return next; }
  return { calls, api, run: initial => mission.runQuestStep('headquartersWall', initial, api, observe) };
}

test('headquarters wall recovery requires the exact local climbing state before input', async () => {
  const invalid = [
    frame({ x: -790.4 }),
    frame({ objectives: ['Go to Mondstadt'] }),
    frame({ health: { current: 590, max: 1000 } }),
    frame({ climbing: false, groundControls: true }),
    frame({ angle: 109.9 }),
    frame({ journal: true }),
    frame({ dialogueReady: true }),
    frame({ tutorialStep: 'headquartersWall' }),
    frame({ objectiveChanged: true }),
  ];
  for (const observation of invalid) {
    const h = harness([]), result = await h.run(observation);
    assert.equal(result.status, 'stopped');
    assert.equal(h.calls.some(call => call[0] === 'forward'), false);
  }
});

test('two bounded forward holds and three fresh grounded frames confirm the wall cleared', async () => {
  const h = harness([
    frame(),
    frame({ climbing: false, groundControls: true }),
    frame({ climbing: false, groundControls: true }),
  ]);
  const result = await h.run(frame());
  assert.equal(result.status, 'completed');
  assert.equal(result.reason, 'headquarters wall cleared; three grounded observations confirmed');
  assert.equal(result.holds, 2);
  assert.deepEqual(h.calls.filter(call => call[0] === 'forward'), [['forward', 800], ['forward', 800]]);
  assert.equal(h.calls.filter(call => call[0] === 'observe').length, 4);
});

test('persistent climbing reaches the twelve-hold cap without jump or drop recovery', async () => {
  const h = harness([frame()]);
  const result = await h.run(frame());
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'headquarters wall climb reached twelve holds');
  assert.equal(result.holds, 12);
  assert.equal(h.calls.filter(call => call[0] === 'forward').length, 12);
  assert.equal(h.calls.some(call => call[0] === 'keyPress'), false);
});

test('map escape, objective change, low HP, and deadline stop before another hold', async () => {
  const cases = [
    [frame({ x: -784.49, y: 2282.95 }), 'unsafe or changed evidence during headquarters wall recovery'],
    [frame({ objectives: ['New objective'] }), 'unsafe or changed evidence during headquarters wall recovery'],
    [frame({ health: { current: 590, max: 1000 } }), 'unsafe or changed evidence during headquarters wall recovery'],
    [frame({ health: { current: 890, max: 1000 } }), 'health dropped more than 10% during headquarters wall recovery'],
  ];
  for (const [next, reason] of cases) {
    const h = harness([next]);
    const result = await h.run(frame());
    assert.equal(result.status, 'stopped');
    assert.equal(result.reason, reason);
    assert.equal(result.holds, 1);
    assert.equal(h.calls.filter(call => call[0] === 'forward').length, 1);
  }

  const timed = harness([frame()]);
  let clockCalls = 0;
  timed.api.now = () => clockCalls++ === 0 ? 1000 : 21000;
  const deadline = await timed.run(frame());
  assert.match(deadline.reason, /deadline reached/);
  assert.equal(deadline.holds, 0);
});

test('verified stair retaining wall has its own narrow position and heading gate', async () => {
  const initial=frame({x:-821.37,y:2273.58,angle:198});
  const ground=frame({x:-821.37,y:2273.58,angle:198,climbing:false,groundControls:true});
  let now=0,holds=0;
  const api={now:()=>now,checkStop:()=>{},sleep:async ms=>{now+=ms;},forward:async ms=>{holds++;now+=ms;}};
  const result=await mission.runQuestStep('headquartersStairWall',initial,api,async()=>ground);
  assert.equal(result.status,'completed');assert.equal(holds,1);
  holds=0;
  const rejected=await mission.runQuestStep('headquartersStairWall',frame(),api,async()=>ground);
  assert.equal(rejected.status,'stopped');assert.equal(holds,0);
});

test('observed stair rail accepts only its own heading and location', async () => {
  let now=0,holds=0;
  const initial=frame({x:-815.45,y:2277.52,angle:251});
  const ground=frame({x:-815.45,y:2277.52,angle:251,climbing:false,groundControls:true});
  const api={now:()=>now,checkStop:()=>{},sleep:async ms=>{now+=ms;},forward:async ms=>{holds++;now+=ms;}};
  assert.equal((await mission.runQuestStep('headquartersStairRail',initial,api,async()=>ground)).status,'completed');
  assert.equal(holds,1);holds=0;
  assert.equal((await mission.runQuestStep('headquartersStairRail',frame(),api,async()=>ground)).status,'stopped');
  assert.equal(holds,0);
});
