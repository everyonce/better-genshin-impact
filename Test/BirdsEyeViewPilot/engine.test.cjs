'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { run } = require('../../BetterGenshinImpact/User/JsScript/BirdsEyeViewPilot/engine.js');

function harness(observations, extra = {}) {
  const calls = [];
  return {
    calls,
    api: {
      assertRdp: async () => calls.push('rdp'),
      observe: async () => { calls.push('observe'); return observations.shift(); },
      navigate: async segment => calls.push(['navigate', segment]),
      advanceDialogue: async () => calls.push('dialogue'),
      wait: async ms => calls.push(['wait', ms]),
      saveStatus: async state => calls.push(['status', state.state]),
      release: async () => calls.push('release'),
      ...extra,
    },
  };
}

test('navigates only supplied segment and requires a fresh observation before completion', async () => {
  const h = harness([
    { screen: 'journal', quest: "Bird's Eye View", stage: 'follow_path' },
    { screen: 'journal', quest: "Bird's Eye View", stage: 'follow_path', completed: true },
  ]);
  const result = await run({ api: h.api, routes: { follow_path: ['provided-segment'] } });
  assert.equal(result.state, 'completed');
  assert.deepEqual(h.calls.filter(x => Array.isArray(x) && x[0] === 'navigate'), [['navigate', 'provided-segment']]);
  assert.equal(h.calls.filter(x => x === 'observe').length, 2);
  assert.equal(h.calls.at(-1), 'release');
});

test('unknown observations never trigger input and stop after the bound', async () => {
  const h = harness(Array(4).fill({ screen: 'unknown', quest: null, stage: null }));
  const result = await run({ api: h.api, maxUnknownObservations: 2, routes: {} });
  assert.equal(result.reason, 'unknown_state');
  assert.equal(h.calls.some(x => Array.isArray(x) && x[0] === 'navigate'), false);
  assert.equal(h.calls.at(-1), 'release');
});

test('dialogue requires target confirmation and signatures, and caps repeated advances', async () => {
  const denied = harness([{ screen: 'dialogue', quest: null }]);
  assert.equal((await run({ api: denied.api })).reason, 'dialogue_without_target_confirmation');
  assert.equal(denied.calls.includes('dialogue'), false);

  const permitted = harness([
    { screen: 'journal', quest: "Bird's Eye View", stage: 'talk_to_paimon' },
    { screen: 'dialogue', quest: "Bird's Eye View", signature: 'line-a' },
    { screen: 'dialogue', quest: "Bird's Eye View", signature: 'line-a' },
    { screen: 'dialogue', quest: "Bird's Eye View", signature: 'line-a' },
  ]);
  const result = await run({ api: permitted.api, routes: { talk_to_paimon: 'one-step' } });
  assert.equal(result.reason, 'dialogue_signature_stalled');
  assert.equal(permitted.calls.filter(x => x === 'dialogue').length, 2);
  assert.equal(permitted.calls.filter(x => Array.isArray(x) && x[0] === 'wait' && x[1] === 1000).length, 3);
});

test('stops before Unexpected Power and releases after API errors', async () => {
  const next = harness([
    { screen: 'journal', quest: "Bird's Eye View", stage: 'follow_path' },
    { screen: 'journal', quest: 'Unexpected Power', stage: 'start' },
  ]);
  assert.equal((await run({ api: next.api, routes: { follow_path: 'confirmed-route' } })).reason, 'verified_next_quest_transition');
  const unconfirmedNext = harness([{ screen: 'journal', quest: 'Unexpected Power', stage: 'start' }]);
  assert.equal((await run({ api: unconfirmedNext.api })).reason, 'next_quest_reached');
  const broken = harness([], { assertRdp: async () => { throw new Error('RDP focus lost'); } });
  const failed = await run({ api: broken.api });
  assert.equal(failed.reason, 'runner_error');
  assert.match(failed.error, /RDP focus lost/);
  assert.equal(broken.calls.at(-1), 'release');
});

test('each input rechecks RDP, unknown cutscenes wait one second, and signature change resets no-progress', async () => {
  let checks = 0;
  const h = harness([
    { screen: 'unknown' },
    { screen: 'journal', quest: "Bird's Eye View", stage: 'follow_path' },
    { screen: 'dialogue', quest: "Bird's Eye View", signature: 'first' },
    { screen: 'dialogue', quest: "Bird's Eye View", signature: 'second' },
    { screen: 'journal', quest: "Bird's Eye View", stage: 'follow_path', completed: true },
  ], { assertRdp: async () => { checks++; } });
  const result = await run({ api: h.api, routes: { follow_path: 'route' }, maxNoProgress: 2 });
  assert.equal(result.state, 'completed');
  assert.equal(checks, 4); // initial guard, navigation, and each dialogue advance
  assert.equal(h.calls.filter(x => Array.isArray(x) && x[0] === 'wait' && x[1] === 1000).length, 4);
});

test('dialogue without a signature blocks before advancing', async () => {
  const h = harness([
    { screen: 'journal', quest: "Bird's Eye View", stage: 'talk_to_paimon' },
    { screen: 'dialogue', quest: "Bird's Eye View" },
  ]);
  const result = await run({ api: h.api, routes: { talk_to_paimon: 'route' } });
  assert.equal(result.reason, 'dialogue_signature_missing');
  assert.equal(h.calls.includes('dialogue'), false);
});

test('missing route and repeated stage segment block without retrying navigation', async () => {
  const missing = harness([{ screen: 'journal', quest: "Bird's Eye View", stage: 'swim_to_island' }]);
  assert.equal((await run({ api: missing.api, routes: {} })).reason, 'no_route_for_stage');
  const same = harness([
    { screen: 'journal', quest: "Bird's Eye View", stage: 'follow_path' },
    { screen: 'journal', quest: "Bird's Eye View", stage: 'follow_path' },
  ]);
  const outcome = await run({ api: same.api, routes: { follow_path: 'single-segment' }, maxNoProgress: 3 });
  assert.equal(outcome.reason, 'route_segment_already_used');
  assert.equal(same.calls.filter(x => Array.isArray(x) && x[0] === 'navigate').length, 1);
});
