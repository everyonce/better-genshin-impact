const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const packageDir = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const mission = require(path.join(packageDir, 'mission.js'));

function observation(x, angle, objective) {
  return {
    map: { map: 'Teyvat', x, y: 0, cameraAngle: angle },
    hud: { world: true, dialogueReady: false, choice: false, objectiveChanged: false,
      lowHealth: false, health: { current: 900, max: 1000 },
      objectives: [objective], interact: false }
  };
}

test('large camera error turns with capped deltas until fresh angle is within tolerance before moving', async () => {
  let now = 0, angle = 10, x = 0;
  const rotations = [], forwardAtAngles = [];
  const objective = 'Follow the road to Mondstadt';
  const api = {
    now: () => now,
    sleep: async ms => { now += ms; },
    checkStop: () => {},
    rotate: async dx => { rotations.push(dx); angle = (angle + dx * 24 / 250 + 360) % 360; },
    forward: async ms => { forwardAtAngles.push({ angle, ms }); x = 10; now += ms; }
  };
  const request = { objective, deadlineMs: 10000, waypoints: [{ map: 'Teyvat', x: 10, y: 0 }] };
  const result = await mission.runNavigation(request, observation(x, angle, objective), api,
    async () => observation(x, angle, objective));

  assert.equal(result.status, 'arrived');
  assert.ok(rotations.length >= 2);
  assert.ok(rotations.every(dx => Number.isInteger(dx) && Math.abs(dx) <= 750));
  assert.equal(forwardAtAngles.length, 1);
  const finalError = Math.abs((forwardAtAngles[0].angle - 180 + 540) % 360 - 180);
  assert.ok(finalError <= 8, `movement began at ${finalError} degrees from target`);
});

test('BetterGI navigation adapter accepts 750px and rejects values above the cap', () => {
  const source = fs.readFileSync(path.join(packageDir, 'bgi.js'), 'utf8');
  const moved = [];
  const context = {
    genshin: { isRemoteDesktopSession: true, windowsSessionId: 5, isGameForeground: true },
    file: { isExists: () => false },
    moveMouseBy: (dx, dy) => moved.push([dx, dy]),
    keyUp: () => {},
    sleep: async () => {}
  };
  vm.runInNewContext(source, context);
  const adapter = context.createActOneAdapter(5);
  adapter.rotate(750);
  assert.throws(() => adapter.rotate(751), /Invalid rotation/);
  assert.deepEqual(moved, [[750, 0]]);
});

test('combatLook retains its independent 250px cap', () => {
  const source = fs.readFileSync(path.join(packageDir, 'bgi.js'), 'utf8');
  assert.match(source, /combatLook:\s*function\s*\(dx\)\s*\{\s*requireCombat\(\);\s*if\s*\(!Number\.isInteger\(dx\)\s*\|\|\s*Math\.abs\(dx\)\s*>\s*250\)/);
});

