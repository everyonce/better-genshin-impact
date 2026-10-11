const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

function frame(step, overrides = {}) {
  return {
    frameId: step ? 440 : 441,
    map: { map: 'Teyvat', x: -879, y: 2263, cameraAngle: 0 },
    hud: {
      tutorialStep: step || null, world: true, dialogueReady: false, choice: false,
      journal: false, bigMap: false, objectiveChanged: false, lowHealth: false,
      climbing: false, health: { current: 921, max: 1062 },
      objectives: ['Meet Amber at the fountain plaza'],
      ...overrides,
    },
  };
}

function fixture(after) {
  let now = 1000;
  let seen = 0;
  const calls = [];
  const api = {
    now: () => now,
    sleep: async ms => { now += ms; calls.push(['sleep', ms]); },
    checkStop: () => calls.push(['checkStop']),
    advanceTutorial: async () => { calls.push(['tutorial', 'glideOpen']); return 'glideOpen'; },
    rotate: async dx => calls.push(['rotate', dx]),
    forward: async ms => calls.push(['forward', ms]),
    keyPress: async key => calls.push(['keyPress', key]),
  };
  const observations = [frame('glideOpen'), after];
  async function observe() { calls.push(['observe']); return observations[Math.min(seen++, observations.length - 1)]; }
  return { api, calls, run: () => mission.runDialogue(api, observe) };
}

test('glideOpen hands off once to the fixed local waypoint using the fresh observation', async () => {
  const f = fixture(frame(null));
  const result = await f.run();
  assert.equal(result.status, 'completed');
  assert.equal(result.reason, 'glide_open_navigation_arrived');
  assert.equal(result.presses, 1);
  assert.equal(result.tutorial.action, 'glideOpen');
  assert.equal(result.tutorial.frameId, 441);
  assert.equal(result.handoff, true);
  assert.deepEqual(result.navigation, {
    status: 'arrived', nextWaypointIndex: 1, inputMs: 0, turns: 0,
    movements: 0, jumpRecoveries: 0, climbSteps: 0, climbReleases: 0,
  });
  assert.deepEqual(f.calls.filter(call => call[0] === 'forward' || call[0] === 'rotate'), []);
  assert.ok(f.calls.some(call => call[0] === 'sleep' && call[1] === 250));
});

test('unsafe or changed fresh observation does not hand off or issue navigation input', async () => {
  const variants = [
    frame(null, { world: false }),
    frame(null, { health: { current: 590, max: 1062 }, lowHealth: true }),
    frame(null, { objectiveChanged: true }),
    frame(null, { objectives: ['Go to Mondstadt'] }),
    frame(null, { climbing: true }),
    frame('aimSlime'),
  ];
  for (const fresh of variants) {
    const f = fixture(fresh);
    const result = await f.run();
    assert.equal(result.status, 'stopped');
    assert.equal(result.reason, 'glide_open_handoff_evidence_not_safe');
    assert.equal(result.presses, 1);
    assert.equal(result.navigation, null);
    assert.equal(result.handoff, false);
    assert.deepEqual(f.calls.filter(call => call[0] === 'forward' || call[0] === 'rotate'), []);
  }
});

test('navigation stop is returned as stopped rather than world-return success', async () => {
  const fresh = frame(null);
  fresh.map.x = -820;
  fresh.map.y = 2280;
  const f = fixture(fresh);
  const result = await f.run();
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'Camera did not converge');
  assert.equal(result.navigation.status, 'stopped');
  assert.equal(result.handoff, true);
  assert.equal(result.presses, 17);
  assert.equal(result.tutorialPresses, 1);
});
