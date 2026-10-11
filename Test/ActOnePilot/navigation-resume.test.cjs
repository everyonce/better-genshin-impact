const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
function observation(x, objective = 'Follow the road to Mondstadt') {
  return { map: { map: 'Teyvat', x, y: 0, cameraAngle: 180 }, hud: { world: true, dialogueReady: false, choice: false, objectiveChanged: false, lowHealth: false, health: { current: 900, max: 1000 }, objectives: [objective] } };
}
function api() {
  let now = 0; const holds = [];
  return { holds, now: () => now, sleep: async ms => { now += ms; }, checkStop: () => {},
    forward: async ms => { holds.push(ms); now += ms; }, rotate: async () => {},
    getNow: () => now };
}
test('deadline result points to the unfinished waypoint after earlier waypoint completion', async () => {
  const a = api();
  const request = { objective: 'Follow the road to Mondstadt', deadlineMs: 1000, waypoints: [
    { map: 'Teyvat', x: 0, y: 0 },
    { map: 'Teyvat', x: 10, y: 0 }
  ] };
  const result = await mission.runNavigation(request, observation(0), a, async () => observation(3));
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'Navigation deadline reached');
  assert.equal(result.nextWaypointIndex, 1);
  assert.deepEqual(a.holds, [800, 50]);
});
test('successful result marks all requested waypoints complete', async () => {
  const a = api();
  const request = { objective: 'Follow the road to Mondstadt', deadlineMs: 5000, waypoints: [
    { map: 'Teyvat', x: 0, y: 0 },
    { map: 'Teyvat', x: 2, y: 2 }
  ] };
  const result = await mission.runNavigation(request, observation(0), a, async () => observation(0));
  assert.equal(result.status, 'arrived');
  assert.equal(result.nextWaypointIndex, request.waypoints.length);
});
test('a policy stop preserves the current waypoint index', async () => {
  const a = api();
  const request = { objective: 'Follow the road to Mondstadt', deadlineMs: 5000, waypoints: [
    { map: 'Teyvat', x: 0, y: 0 },
    { map: 'Mondstadt', x: 20, y: 0 }
  ] };
  const result = await mission.runNavigation(request, observation(0), a, async () => observation(0));
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'Waypoint map does not match current map');
  assert.equal(result.nextWaypointIndex, 1);
});
