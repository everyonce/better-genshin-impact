const path = require('node:path');
if (!process.argv[2]) { throw new Error('Usage: node tools/quest-pilot/benchmark-combat-observations.cjs <prechange-combat.js>'); }
const before = require(path.resolve(process.argv[2]));
const after = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/combat.js');

function makeFrame(frameId, paused) {
  return {
    timestamp: 0,
    frameId,
    map: null,
    ocr: paused ? [
      { text: 'Continue Challenge', x: 700, y: 500 },
      { text: 'Leave Domain?', x: 700, y: 600 },
    ] : [
      { text: 'Kaeya', x: 1664, y: 487 },
      { text: 'Trial', x: 1796, y: 463 },
    ],
    hud: {
      world: false,
      groundControls: true,
      climbing: false,
      journal: false,
      bigMap: false,
      dialogueReady: false,
      choice: false,
      tutorialStep: null,
      health: { current: 1000, max: 1000 },
      enemyBars: paused ? [] : [{ x: 960, y: 500, width: 100, height: 8 }],
    },
  };
}

async function run(combat, observationCostMs) {
  let clock = 1000;
  let frameId = 1;
  let paused = false;
  const actions = [];
  const observations = [];
  const api = {
    now: () => clock,
    sleep: async ms => { clock += ms; },
    checkStop: () => {},
    wolfCombatKey: async key => { actions.push(key); },
    wolfPauseCombat: async () => { paused = true; },
  };
  const observe = async () => {
    clock += observationCostMs;
    const o = makeFrame(++frameId, paused);
    o.timestamp = clock;
    observations.push({ frameId: o.frameId, timestamp: o.timestamp, health: o.hud.health.current,
      enemyBarWidth: o.hud.enemyBars[0] ? o.hud.enemyBars[0].width : null, paused });
    return o;
  };
  const initial = makeFrame(frameId, false);
  initial.timestamp = clock;
  const result = await combat.runWolf(initial, api, observe);
  return {
    observationCostMs,
    observationCount: observations.length,
    actionCount: actions.length,
    actions,
    health: 1000,
    enemyBarWidth: 100,
    result: { status: result.status, reason: result.reason, presses: result.presses,
      elapsedMs: result.elapsedMs, pauseVerified: result.pauseVerified, combatComplete: result.combatComplete },
  };
}

(async () => {
  const rows = [];
  for (const cost of [20, 300]) {
    const oldRun = await run(before, cost);
    const newRun = await run(after, cost);
    rows.push({ costMs: cost, prechange: oldRun, updated: newRun,
      observationDelta: oldRun.observationCount - newRun.observationCount,
      fakeElapsedDeltaMs: oldRun.result.elapsedMs - newRun.result.elapsedMs,
      sameActions: JSON.stringify(oldRun.actions) === JSON.stringify(newRun.actions),
      sameOutcome: oldRun.result.reason === newRun.result.reason && oldRun.result.pauseVerified === newRun.result.pauseVerified });
  }
  process.stdout.write(JSON.stringify({ description: 'Simulated only; fixed healthy no-progress HUD and same input outcomes.', rows }, null, 2) + '\n');
})().catch(error => { process.stderr.write(String(error && error.stack || error) + '\n'); process.exitCode = 1; });
