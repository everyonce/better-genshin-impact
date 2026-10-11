const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

function frame(tutorialStep, extra = {}) {
  return {
    hud: {
      tutorialStep: tutorialStep || null,
      world: tutorialStep ? true : false,
      dialogueReady: false,
      choice: false,
      ...extra,
    },
  };
}

function dialogueRun(observations, tutorialActionResult = () => undefined) {
  let now = 0;
  let current = null;
  let next = 0;
  const events = [];
  const sleeps = [];
  const api = {
    now: () => now,
    sleep: async ms => { now += ms; sleeps.push({ step: current && current.hud.tutorialStep, ms }); },
    checkStop: () => {},
    advanceTutorial: async () => {
      events.push({ type: 'action', step: current.hud.tutorialStep });
      return tutorialActionResult(current.hud.tutorialStep);
    },
    keyPress: async () => assert.fail('Tutorial handling must not issue generic Space input'),
    chooseChoice: async () => assert.fail('No dialogue choices in this fixture'),
  };
  async function observe() {
    current = observations[Math.min(next++, observations.length - 1)];
    events.push({ type: 'observe', step: current.hud.tutorialStep });
    return current;
  }
  return { run: () => mission.runDialogue(api, observe), events, sleeps };
}

test('Amber tutorial steps are acted in order and observed again before world return', async () => {
  const run = dialogueRun([
    frame('switchAmber'),
    frame('enterAim'),
    frame('aimSlime'),
    frame(null, { world: true }),
  ]);

  const result = await run.run();
  assert.equal(result.status, 'completed');
  assert.equal(result.reason, 'world_returned');
  assert.equal(result.presses, 3);
  assert.deepEqual(run.events, [
    { type: 'observe', step: 'switchAmber' },
    { type: 'action', step: 'switchAmber' },
    { type: 'observe', step: 'enterAim' },
    { type: 'action', step: 'enterAim' },
    { type: 'observe', step: 'aimSlime' },
    { type: 'action', step: 'aimSlime' },
    { type: 'observe', step: null },
  ]);
});

test('unchanged Amber switch or aim-mode entry/exit prompt stops after one action and a fresh observation', async () => {
  for (const step of ['switchAmber', 'enterAim', 'exitAim']) {
    const run = dialogueRun([frame(step), frame(step)]);
    const result = await run.run();
    assert.equal(result.status, 'stopped');
    assert.equal(result.reason, 'tutorial_did_not_advance');
    assert.equal(result.presses, 1);
    assert.deepEqual(run.events, [
      { type: 'observe', step },
      { type: 'action', step },
      { type: 'observe', step },
    ]);
  }
});

test('aim corrections wait 250 ms but a shot waits 1000 ms before the next observation', async () => {
  const correction = dialogueRun([frame('aimSlime'), frame(null, { world: true })]);
  const corrected = await correction.run();
  assert.equal(corrected.reason, 'world_returned');
  assert.deepEqual(correction.sleeps, [{ step: 'aimSlime', ms: 250 }]);
  assert.deepEqual(correction.events.map(event => event.type), ['observe', 'action', 'observe']);

  const shot = dialogueRun([frame('aimSlime'), frame(null, { world: true })], () => 'shot');
  const fired = await shot.run();
  assert.equal(fired.reason, 'world_returned');
  assert.deepEqual(shot.sleeps, [{ step: 'aimSlime', ms: 1000 }]);
  assert.deepEqual(shot.events.map(event => event.type), ['observe', 'action', 'observe']);
});

test('aim-slime tutorial caps repeated corrective actions at twelve, observing after each', async () => {
  const run = dialogueRun(Array.from({ length: 13 }, () => frame('aimSlime')));
  const result = await run.run();
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'tutorial_did_not_advance');
  assert.equal(result.presses, 12);
  assert.equal(run.events.filter(event => event.type === 'action').length, 12);
  assert.equal(run.events.filter(event => event.type === 'observe').length, 13);
  for (let i = 1; i < run.events.length; i += 2) {
    assert.equal(run.events[i].type, 'action');
    assert.equal(run.events[i + 1].type, 'observe');
  }
});

test('unknown tutorial screen is observed repeatedly but receives no input', async () => {
  const run = dialogueRun(Array.from({ length: 6 }, () => frame(null)));
  const result = await run.run();
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'unrecognized_dialogue_state');
  assert.equal(result.presses, 0);
  assert.ok(run.events.every(event => event.type === 'observe'));
  assert.equal(run.events.length, 6);
});
