const test = require('node:test');
const assert = require('node:assert/strict');
const combat = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/combat.js');

function world(health = 800, objectives = [combat.objective], extra = {}) {
  return { hud: {
    world: true,
    health: { current: health, max: 1000 },
    objectives,
    ...extra,
  } };
}

function harness(nextObservation = () => world(), startTime = 1000) {
  let time = startTime;
  const events = [];
  const api = {
    now: () => time,
    sleep: async ms => { events.push(['sleep', ms]); time += ms; },
    checkStop: () => events.push(['checkStop']),
    selectTraveler: async () => events.push(['selectTraveler']),
    combatAttack: async () => events.push(['attack', time]),
    combatSkill: async () => events.push(['skill', time]),
  };
  const observe = async () => {
    events.push(['observe', time]);
    return nextObservation();
  };
  return { api, observe, events, now: () => time, advance: ms => { time += ms; } };
}

test('selects Traveler once, reobserves, then attacks with a 350ms delay and fresh check', async () => {
  const f = harness();
  const result = await combat.run({ objective: combat.objective }, world(), f.api, f.observe);
  assert.equal(result.status, 'stopped');
  assert.equal(result.reason, 'Combat action limit reached');
  assert.equal(f.events.filter(e => e[0] === 'selectTraveler').length, 1);
  assert.deepEqual(f.events.slice(0, 5).map(e => e[0]), ['checkStop', 'selectTraveler', 'sleep', 'observe', 'checkStop']);
  const firstAttack = f.events.findIndex(e => e[0] === 'attack');
  assert.ok(firstAttack > 0);
  assert.deepEqual(f.events.slice(firstAttack, firstAttack + 3).map(e => e[0]), ['attack', 'sleep', 'observe']);
  assert.equal(f.events[firstAttack + 1][1], 350);
  assert.equal(result.actions, 40);
  assert.equal(result.attacks + result.skills + 1, 40);
});

test('rejects unsupported, missing, and nonexact objectives before selecting or attacking', async () => {
  for (const [request, observation, expected] of [
    [{ objective: 'Clear out the hilichurl camp' }, world(), 'Unsupported combat objective'],
    [{ objective: combat.objective }, world(800, []), 'Expected objective missing or changed'],
    [{ objective: combat.objective }, world(800, ['Defeat nearby hilichurls']), 'Expected objective missing or changed'],
    [{ objective: combat.objective }, world(800, [combat.objective], { objectiveChanged: true }), 'Objective changed'],
  ]) {
    const f = harness(() => observation);
    const result = await combat.run(request, observation, f.api, f.observe);
    assert.equal(result.reason, expected);
    assert.equal(f.events.some(e => e[0] === 'selectTraveler' || e[0] === 'attack'), false);
  }
});

test('supports the two verified exact objectives and binds each run to its requested text', async () => {
  const camp = 'Clear out the nearby hilichurl camp';
  assert.deepEqual(combat.objectives, [combat.objective, camp]);

  for (const [requested, observed] of [
    [combat.objective, camp],
    [camp, combat.objective],
  ]) {
    const f = harness(() => world(800, [observed]));
    const result = await combat.run({ objective: requested }, world(800, [observed]), f.api, f.observe);
    assert.equal(result.reason, 'Expected objective missing or changed');
    assert.equal(f.events.some(e => e[0] === 'selectTraveler' || e[0] === 'attack'), false);
  }

  const f = harness(() => world(800, [camp]));
  const result = await combat.run({ objective: camp }, world(800, [camp]), f.api, f.observe);
  assert.equal(result.reason, 'Combat action limit reached');
  assert.equal(f.events.filter(e => e[0] === 'selectTraveler').length, 1);
  assert.ok(result.attacks + result.skills > 0);
});

test('retries transient missing world or health evidence before stopping', async () => {
  for (const transient of [
    { hud: { ...world().hud, world: false, health: null } },
    world(800, [combat.objective], { health: null }),
  ]) {
    let frame = 0;
    const f = harness(() => ++frame === 1 ? transient : world());
    const result = await combat.run({ objective: combat.objective }, world(), f.api, f.observe);
    assert.equal(result.reason, 'Combat action limit reached');
    assert.equal(f.events.filter(e => e[0] === 'sleep' && e[1] === 200).length, 1);
    assert.equal(f.events.filter(e => e[0] === 'selectTraveler').length, 1);
    assert.ok(result.attacks + result.skills > 0);
  }
});

test('stops after two retries when world or health evidence remains unavailable', async () => {
  for (const transient of [
    { hud: { ...world().hud, world: false, health: null } },
    world(800, [combat.objective], { health: null }),
  ]) {
    let frame = 0;
    const f = harness(() => { frame++; return transient; });
    const result = await combat.run({ objective: combat.objective }, world(), f.api, f.observe);
    assert.ok(result.reason === 'World HUD unavailable' || result.reason === 'Health evidence unavailable');
    assert.equal(f.events.filter(e => e[0] === 'sleep' && e[1] === 200).length, 2);
    assert.equal(f.events.filter(e => e[0] === 'observe').length, 3);
    assert.equal(result.actions, 1); // Traveler selection only; no combat action.
    assert.equal(result.attacks + result.skills, 0);
  }
});

test('retries nonexplicit objective OCR misses but hard-stops explicit objective changes', async () => {
  let frame = 0;
  const f = harness(() => ++frame === 1
    ? world(800, ['Clear out the heårby hilichurlcamp'])
    : world());
  const recovered = await combat.run({ objective: combat.objective }, world(), f.api, f.observe);
  assert.equal(recovered.reason, 'Combat action limit reached');
  assert.equal(f.events.filter(e => e[0] === 'sleep' && e[1] === 200).length, 1);
  const firstCombatInput = f.events.findIndex(e => e[0] === 'attack' || e[0] === 'skill');
  const observations = f.events.reduce((indices, event, index) => {
    if (event[0] === 'observe') indices.push(index);
    return indices;
  }, []);
  assert.ok(observations[1] < firstCombatInput); // The exact objective was reacquired before combat.

  let explicitFrame = 0;
  const explicit = harness(() => {
    explicitFrame++;
    return world(800, ['Different objective'], { objectiveChanged: true });
  });
  const stopped = await combat.run({ objective: combat.objective }, world(), explicit.api, explicit.observe);
  assert.equal(stopped.reason, 'Objective changed');
  assert.equal(explicit.events.filter(e => e[0] === 'sleep' && e[1] === 200).length, 0);
  assert.equal(explicit.events.filter(e => e[0] === 'attack' || e[0] === 'skill').length, 0);
});

test('requires world HUD and at least 60% HP before combat input', async () => {
  for (const [observation, expected] of [
    [{ hud: { ...world().hud, world: false } }, 'World HUD unavailable'],
    [world(599), 'Health below 60%'],
    [world(800, [combat.objective], { health: null }), 'Health evidence unavailable'],
  ]) {
    const f = harness(() => observation);
    const result = await combat.run({ objective: combat.objective }, observation, f.api, f.observe);
    assert.equal(result.reason, expected);
    assert.equal(f.events.some(e => e[0] === 'selectTraveler' || e[0] === 'attack'), false);
  }
});

test('stops after a fresh observation detects objective loss or a 20% maximum-HP drop', async () => {
  for (const [next, expected] of [
    [world(800, ['New objective']), 'Expected objective missing or changed'],
    [world(600), 'Health dropped 20% or more of maximum'],
    [{ hud: { ...world().hud, world: false } }, 'World HUD unavailable'],
  ]) {
    let observed = 0;
    const f = harness(() => (++observed === 1 ? world() : next));
    const result = await combat.run({ objective: combat.objective }, world(), f.api, f.observe);
    assert.equal(result.reason, expected);
    assert.equal(result.attacks, 0);
    assert.equal(f.events.filter(e => e[0] === 'selectTraveler').length, 1);
  }
});

test('uses the optional skill no more often than once per eight seconds', async () => {
  const f = harness(undefined, 1e12);
  f.api.combatAttack = async () => { f.events.push(['attack', f.now()]); f.advance(1000); };
  await combat.run({ objective: combat.objective }, world(), f.api, f.observe);
  const skillTimes = f.events.filter(e => e[0] === 'skill').map(e => e[1]);
  assert.ok(skillTimes.length >= 2);
  assert.equal(f.events.find(e => e[0] === 'skill')[1], 1e12 + 500);
  for (let i = 1; i < skillTimes.length; i++) assert.ok(skillTimes[i] - skillTimes[i - 1] >= 8000);
});

test('resets the health-loss baseline after Traveler selection', async () => {
  let frame = 0;
  const f = harness(() => {
    frame++;
    return frame === 1 ? world(650, [combat.objective], { health: { current: 650, max: 1000 } }) : world();
  });
  const initial = world(900, [combat.objective], { health: { current: 900, max: 1000 } });
  const result = await combat.run({ objective: combat.objective }, initial, f.api, f.observe);
  assert.equal(result.reason, 'Combat action limit reached');
  assert.ok(result.attacks > 0);
  assert.equal(f.events.filter(e => e[0] === 'selectTraveler').length, 1);
});

test('stops at the 60-second deadline even when objective evidence remains unchanged', async () => {
  const f = harness();
  // Simulate slow but successful input calls so the time bound is reached before the action cap.
  f.api.combatAttack = async () => { f.events.push(['attack', f.now()]); f.advance(2500); };
  f.api.combatSkill = async () => { f.events.push(['skill', f.now()]); f.advance(2500); };
  const result = await combat.run({ objective: combat.objective }, world(), f.api, f.observe);
  assert.equal(result.reason, 'Combat deadline reached');
  assert.ok(result.elapsedMs >= 60000);
  assert.ok(result.actions <= 40);
});

test('honors a shorter validated request deadline', async () => {
  const f = harness();
  f.api.combatAttack = async () => { f.events.push(['attack', f.now()]); f.advance(2500); };
  f.api.combatSkill = async () => { f.events.push(['skill', f.now()]); f.advance(2500); };
  const result = await combat.run({ objective: combat.objective, deadlineMs: 2000 }, world(), f.api, f.observe);
  assert.equal(result.reason, 'Combat deadline reached');
  assert.ok(result.elapsedMs >= 2000);
  assert.ok(result.actions < 40);
});

test('bounded camera scan with no enemy health bars reobserves each turn and never attacks', async () => {
  const f = harness(() => world(800, [combat.objective], { enemyBars: [] }));
  const looks = [];
  f.api.combatLook = async dx => { looks.push(dx); f.events.push(['look', dx]); };

  const result = await combat.run({ objective: combat.objective }, world(), f.api, f.observe);

  assert.equal(result.reason, 'No enemy health bar found after four bounded camera scans');
  assert.deepEqual(looks, Array(4).fill(250));
  assert.equal(result.attacks, 0);
  assert.equal(result.skills, 0);
  assert.equal(result.actions, 5); // Traveler selection plus four bounded turns.
  for (let i = 0; i < looks.length; i++) {
    const at = f.events.findIndex((e, index) => index > 0 && e[0] === 'look' && e[1] === looks[i] &&
      f.events.slice(0, index).filter(x => x[0] === 'look').length === i);
    assert.ok(at >= 0);
    assert.deepEqual(f.events.slice(at, at + 3).map(e => e[0]), ['look', 'sleep', 'observe']);
    assert.equal(f.events[at + 1][1], 250);
  }
});

test('an off-center enemy bar is corrected and reobserved before any combat action', async () => {
  let frame = 0;
  const f = harness(() => {
    frame++;
    return world(800, [combat.objective], { enemyBars: [{ x: frame <= 1 ? 1300 : 1000 }] });
  });
  const looks = [];
  f.api.combatLook = async dx => { looks.push(dx); f.events.push(['look', dx]); };

  const result = await combat.run({ objective: combat.objective }, world(), f.api, f.observe);

  assert.equal(result.reason, 'Combat action limit reached');
  assert.deepEqual(looks, [170]);
  const firstLook = f.events.findIndex(e => e[0] === 'look');
  const firstCombat = f.events.findIndex(e => e[0] === 'attack' || e[0] === 'skill');
  assert.ok(firstLook >= 0 && firstLook < firstCombat);
  assert.deepEqual(f.events.slice(firstLook, firstLook + 3).map(e => e[0]), ['look', 'sleep', 'observe']);
  assert.equal(f.events[firstLook + 1][1], 250);
});

test('a health or objective change after a scan stops before another turn or combat input', async () => {
  for (const [changed, reason] of [
    [world(599, [combat.objective], { enemyBars: [] }), 'Health below 60%'],
    [world(800, ['New objective'], { enemyBars: [] }), 'Expected objective missing or changed'],
    [world(800, [combat.objective], { enemyBars: [], objectiveChanged: true }), 'Objective changed'],
  ]) {
    let observationCount = 0;
    const f = harness(() => ++observationCount === 1
      ? world(800, [combat.objective], { enemyBars: [] })
      : changed);
    const looks = [];
    f.api.combatLook = async dx => { looks.push(dx); f.events.push(['look', dx]); };

    const result = await combat.run({ objective: combat.objective }, world(), f.api, f.observe);

    assert.equal(result.reason, reason);
    assert.equal(looks.length, 1);
    assert.equal(result.attacks, 0);
    assert.equal(result.skills, 0);
  }
});

test('prioritizes the tallest enemy bar and does not center close-target bars', async () => {
  const f = harness(() => world(800, [combat.objective], { enemyBars: [
    { x: 1200, y: 400, width: 70, height: 6 },
    { x: 960, y: 300, width: 80, height: 4 },
  ] }));
  const looks = [];
  f.api.combatLook = async dx => { looks.push(dx); f.events.push(['look', dx]); };

  const result = await combat.run({ objective: combat.objective }, world(), f.api, f.observe);

  assert.deepEqual(looks, []);
  const firstCombat = f.events.find(e => e[0] === 'attack' || e[0] === 'skill');
  assert.equal(firstCombat[0], 'skill'); // First Traveler E is useful; subsequent E remains cooldown bounded.
  assert.ok(result.attacks >= 2); // The taller off-center bar remains selected for a two-click attack.
});

test('limits consecutive camera corrections to four before stopping', async () => {
  const f = harness(() => world(800, [combat.objective], { enemyBars: [{ x: 1500, height: 4 }] }));
  f.api.combatLook = async dx => { f.events.push(['look', dx]); };
  const result = await combat.run({ objective: combat.objective }, world(), f.api, f.observe);
  assert.equal(result.reason, 'Enemy camera alignment exceeded four corrections');
  assert.equal(f.events.filter(e => e[0] === 'look').length, 4);
  assert.equal(result.attacks + result.skills, 0);
});

test('approaches a far aligned enemy only through guarded bounded API, then attacks once close', async () => {
  let advances = 0;
  const observed = () => world(800, [combat.objective], {
    enemyBars: [{ x: 960, height: advances >= 3 ? 6 : 4 }],
  });
  const f = harness(() => observed());
  f.api.combatLook = async () => {};
  f.api.combatAdvance = async () => { advances++; f.events.push(['combatAdvance']); };
  const initial = observed();
  initial.map = { x: 0, y: 0 };
  f.observe = async () => {
    f.events.push(['observe', f.now()]);
    const next = observed(); next.map = { x: advances, y: 0 }; return next;
  };
  const result = await combat.run({ objective: combat.objective }, initial, f.api, f.observe);
  assert.equal(advances, 3);
  assert.equal(result.reason, 'Combat action limit reached');
  const firstAdvance = f.events.findIndex(e => e[0] === 'combatAdvance');
  assert.deepEqual(f.events.slice(firstAdvance, firstAdvance + 3).map(e => e[0]),
    ['combatAdvance', 'sleep', 'observe']);
  assert.equal(f.events[firstAdvance + 1][1], 150);
  const firstCombat = f.events.findIndex(e => e[0] === 'attack' || e[0] === 'skill');
  assert.ok(firstCombat > f.events.map(e => e[0]).lastIndexOf('combatAdvance'));
});

test('stops far approach after two consecutive map-position stalls', async () => {
  const f = harness(() => {
    const result = world(800, [combat.objective], { enemyBars: [{ x: 960, height: 4 }] });
    result.map = { x: 10, y: 20 };
    return result;
  });
  f.api.combatLook = async () => {};
  f.api.combatAdvance = async () => { f.events.push(['combatAdvance']); };
  const initial = world(800, [combat.objective], { enemyBars: [{ x: 960, height: 4 }] });
  initial.map = { x: 10, y: 20 };
  const result = await combat.run({ objective: combat.objective }, initial, f.api, f.observe);
  assert.equal(result.reason, 'Combat approach stalled for two observed steps');
  assert.equal(f.events.filter(e => e[0] === 'combatAdvance').length, 2);
  assert.equal(result.attacks + result.skills, 0);
});

test('searches only after an acquired enemy bar disappears, then stops after four turns', async () => {
  let frame = 0;
  const f = harness(() => {
    frame++;
    return world(800, [combat.objective], { enemyBars: frame === 1 ? [{ x: 960, height: 4 }] : [] });
  });
  const looks = [];
  f.api.combatLook = async dx => { looks.push(dx); f.events.push(['look', dx]); };

  const result = await combat.run({ objective: combat.objective }, world(), f.api, f.observe);

  assert.equal(result.reason, 'No enemy health bar found after four bounded camera scans');
  assert.equal(result.attacks, 0);
  assert.equal(result.skills, 1);
  assert.equal(looks.length, 4);
  assert.ok(f.events.findIndex(e => e[0] === 'attack') < f.events.findIndex(e => e[0] === 'look'));
});

test('counts a one-time combat-view preparation against the forty-action limit', async () => {
  const f = harness();
  f.api.prepareCombatView = async () => { f.events.push(['prepareCombatView']); return true; };
  const result = await combat.run({ objective: combat.objective }, world(), f.api, f.observe);
  assert.equal(result.reason, 'Combat action limit reached');
  assert.equal(result.actions, 40);
  assert.equal(result.attacks + result.skills + 2, 40);
  assert.equal(f.events.filter(e => e[0] === 'prepareCombatView').length, 1);
});

test('pauses low-health world safely after fresh state and verifies the journal', async () => {
  const f = harness();
  let pauseRequested = false;
  f.observe = async () => {
    f.events.push(['observe', f.now()]);
    return pauseRequested ? { hud: { world: false, journal: true } } : world(599);
  };
  f.api.pauseCombat = async () => { f.events.push(['pauseCombat']); pauseRequested = true; return true; };

  const result = await combat.run({ objective: combat.objective }, world(599), f.api, f.observe);

  assert.equal(result.status, 'stopped');
  assert.equal(result.outcome, 'combat_stopped');
  assert.equal(result.paused, true);
  assert.equal(result.reason, 'Health below 60%');
  assert.deepEqual(f.events.map(e => e[0]), ['checkStop', 'observe', 'checkStop', 'pauseCombat', 'observe', 'checkStop']);
});

test('pauses after objective loss but does not call it completion without explicit completion evidence', async () => {
  const f = harness();
  let phase = 0;
  f.observe = async () => {
    f.events.push(['observe', f.now()]);
    phase++;
    if (phase === 1) return world(); // after Traveler selection
    if (phase >= 2 && phase <= 4) return world(800, ['New objective']); // action observation and two OCR retries
    if (phase === 5) return world(800, ['New objective']); // fresh stop verification
    return { hud: { world: false, journal: true } }; // post-pause verification
  };
  f.api.pauseCombat = async () => { f.events.push(['pauseCombat']); return true; };

  const result = await combat.run({ objective: combat.objective }, world(), f.api, f.observe);

  assert.equal(result.status, 'stopped');
  assert.equal(result.outcome, 'combat_stopped');
  assert.equal(result.reason, 'Expected objective missing or changed');
  assert.equal(result.paused, true);
  assert.equal(result.attacks + result.skills, 1);
  assert.equal(f.events.filter(e => e[0] === 'sleep' && e[1] === 200).length, 2);
});

test('distinguishes explicit objective completion from ordinary combat stops', async () => {
  const f = harness(() => ({ hud: { ...world().hud, objectiveCompleted: true } }));
  f.api.pauseCombat = async () => true;
  f.observe = async () => ({ hud: { ...world().hud, objectiveCompleted: true, world: false, journal: true } });
  const result = await combat.run({ objective: combat.objective }, world(), f.api, f.observe);
  assert.equal(result.status, 'completed');
  assert.equal(result.outcome, 'objective_completed');
  assert.equal(result.reason, 'Objective completion verified');
  assert.equal(result.paused, false);
});

test('readiness exceptions do not trigger a local pause', async () => {
  const checkFailure = harness();
  let pauses = 0;
  checkFailure.api.checkStop = () => { throw new Error('focus lost'); };
  checkFailure.api.pauseCombat = async () => { pauses++; return true; };
  await assert.rejects(combat.run({ objective: combat.objective }, world(599), checkFailure.api, checkFailure.observe), /focus lost/);
  assert.equal(pauses, 0);

  const observeFailure = harness();
  observeFailure.api.pauseCombat = async () => { pauses++; return true; };
  observeFailure.observe = async () => { throw new Error('capture not ready'); };
  await assert.rejects(combat.run({ objective: combat.objective }, world(599), observeFailure.api, observeFailure.observe), /capture not ready/);
  assert.equal(pauses, 0);
});

test('uses two spaced attacks only with fresh high HP and a near recognized enemy bar', async () => {
  const f = harness(() => world(800, [combat.objective], { enemyBars: [{ x: 960, height: 6 }] }));
  f.api.combatSkill = undefined;
  f.api.combatLook = async () => {};
  const result = await combat.run({ objective: combat.objective }, world(800), f.api, f.observe);
  assert.equal(result.actions, 40);
  assert.equal(result.attacks, 39); // Nineteen two-click bursts plus one single final input.
  const firstAttack = f.events.findIndex(e => e[0] === 'attack');
  assert.deepEqual(f.events.slice(firstAttack, firstAttack + 6).map(e => e[0]),
    ['attack', 'sleep', 'checkStop', 'attack', 'sleep', 'observe']);
  assert.equal(f.events[firstAttack + 1][1], 200);
  assert.equal(f.events[firstAttack + 4][1], 200);
});

test('does not burst below 80% HP or without an observed enemy bar', async () => {
  for (const observation of [
    world(799, [combat.objective], { enemyBars: [{ x: 960, height: 8 }] }),
    world(800), // No bar evidence: the loop may attack once, but cannot burst.
  ]) {
    let frame = 0;
    const f = harness(() => {
      frame++;
      return frame === 1 ? observation : world(800, ['Objective changed']);
    });
    f.api.combatSkill = undefined;
    if (observation.hud.enemyBars) f.api.combatLook = async () => {};
    const result = await combat.run({ objective: combat.objective }, observation, f.api, f.observe);
    assert.equal(result.attacks, 1);
    const attackAt = f.events.findIndex(e => e[0] === 'attack');
    assert.ok(attackAt >= 0);
    assert.equal(f.events[attackAt + 1][0], 'sleep');
    assert.equal(f.events[attackAt + 1][1], 350);
  }
});

test('honors a stop request between the two burst attacks', async () => {
  const f = harness(() => world(800, [combat.objective], { enemyBars: [{ x: 960, height: 6 }] }));
  f.api.combatSkill = undefined;
  f.api.combatLook = async () => {};
  let stopAfterFirstAttack = false;
  f.api.checkStop = () => {
    f.events.push(['checkStop']);
    if (stopAfterFirstAttack) throw new Error('stop requested');
  };
  f.api.combatAttack = async () => {
    f.events.push(['attack', f.now()]);
    stopAfterFirstAttack = true;
  };
  await assert.rejects(combat.run({ objective: combat.objective }, world(800), f.api, f.observe), /stop requested/);
  assert.equal(f.events.filter(e => e[0] === 'attack').length, 1);
  const attackAt = f.events.findIndex(e => e[0] === 'attack');
  assert.deepEqual(f.events.slice(attackAt, attackAt + 3).map(e => e[0]),
    ['attack', 'sleep', 'checkStop']);
});

test('uses optional Q burst once after Traveler validation and observes before continuing', async () => {
  const f = harness(() => world(800, [combat.objective], { enemyBars: [{ x: 960, height: 6 }] }));
  f.api.combatLook = async () => {};
  f.api.combatBurst = async () => { f.events.push(['combatBurst']); };
  const result = await combat.run({ objective: combat.objective }, world(800, [combat.objective], { enemyBars: [{ x: 960, height: 6 }] }), f.api, f.observe);
  assert.equal(result.reason, 'Combat action limit reached');
  assert.equal(result.bursts, 1);
  assert.equal(f.events.filter(e => e[0] === 'combatBurst').length, 1);
  const selected = f.events.findIndex(e => e[0] === 'selectTraveler');
  const burst = f.events.findIndex(e => e[0] === 'combatBurst');
  assert.ok(selected < burst);
  assert.ok(f.events.slice(selected + 1, burst).some(e => e[0] === 'observe'));
  assert.deepEqual(f.events.slice(burst, burst + 3).map(e => e[0]), ['combatBurst', 'sleep', 'observe']);
  assert.equal(f.events[burst + 1][1], 700);
});
