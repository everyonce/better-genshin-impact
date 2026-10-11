const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

function frame(objective, x, y, angle) {
  return { map: { map: 'Teyvat', x, y, cameraAngle: angle }, hud: {
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
