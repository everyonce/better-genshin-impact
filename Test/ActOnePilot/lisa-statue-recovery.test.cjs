'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const recovery = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/lisa-statue-recovery.js');

function frame(id, patch = {}) {
  return { session: 'session-a', frameId: id, timestamp: 19990, map: null, hud: {
    world: true, groundControls: true, climbing: false, journal: false, bigMap: false, auto: false,
    choice: false, dialogueReady: false, objectiveChanged: false, unknownHud: false, loading: false,
    tutorial: false, tutorialStep: null, enemyBars: [], health: { current: 40, max: 100 },
  }, exactLisa: true, atStatue: false, mapReady: false, ...patch };
}
function setup(options = {}) {
  let calls = [], released = 0, current = frame(1);
  const api = {
    now: () => 20000,
    checkStop() { calls.push('check'); if (options.stopAt === calls.filter(x => x === 'check').length) throw new Error('Stop requested'); },
    sleep: async ms => { calls.push('sleep:' + ms); },
    release: async () => { released++; calls.push('release'); if (options.releaseError) throw new Error('release failed'); },
    lisaRecoveryInventoryReady: (initial, now) => options.inventory === undefined ? true : options.inventory,
    lisaRecoveryCloseInventory: async initial => { calls.push('close'); if (options.closeError) throw new Error('close failed'); },
    lisaRecoveryFieldReady: value => options.fieldError ? (() => { throw new Error('field failed'); })() : value.exactLisa === true,
    lisaRecoveryOpenMap: async value => { calls.push('openMap'); },
    lisaRecoveryMapReady: value => value.mapReady === true,
    lisaRecoveryTeleport: async value => { calls.push('teleport'); if (options.teleportError) throw new Error('teleport failed'); },
    lisaRecoveryAtStatue: value => value.atStatue === true,
  };
  if (options.healAtStatue) api.lisaRecoveryHealAtStatue = async (value, capture) => {
    calls.push('healAtStatue');
    if (options.healError) throw new Error('approach failed');
    return typeof options.healAtStatue === 'function' ? options.healAtStatue(value, capture) : options.healAtStatue;
  };
  const observe = async () => {
    if (options.observeError) throw new Error('capture failed');
    if (options.frames && options.frames.length) current = options.frames.shift();
    else { current = frame(current.frameId + 1); if (calls.includes('teleport')) current.atStatue = true; }
    return current;
  };
  return { initial: frame(1), api, observe, calls, get released() { return released; } };
}

function fullFrames() {
  return [
    frame(2),
    frame(3, { mapReady: true }),
    frame(4, { atStatue: true }),
    frame(5, { atStatue: true, hud: { ...frame(5).hud, health: { current: 95, max: 100 } } }),
  ];
}

test('retries a rejected map key only on fresh living field evidence and stops after three inputs', async () => {
  const ctx=setup({frames:[frame(2),frame(3),frame(4,{mapReady:true}),frame(5,{atStatue:true}),
    frame(6,{atStatue:true,hud:{...frame(6).hud,health:{current:100,max:100}}})]});
  assert.equal((await recovery.run(ctx.initial,ctx.api,ctx.observe)).recovered,true);
  assert.equal(ctx.calls.filter(x=>x==='openMap').length,2);
  const blocked=setup();
  assert.equal((await recovery.run(blocked.initial,blocked.api,blocked.observe)).recovered,false);
  assert.equal(blocked.calls.filter(x=>x==='openMap').length,3);
  assert.equal(blocked.calls.includes('teleport'),false);
});

test('does not retry map input against death, stale evidence, or an unverified map', async () => {
  for(const change of [f=>{f.hud.health.current=0;},f=>{f.timestamp=1;},f=>{f.hud.world=false;f.hud.bigMap=true;}]){
    const frames=Array.from({length:6},(_,i)=>{const f=frame(i+3);change(f);return f;});
    const ctx=setup({frames:[frame(2),...frames]});
    assert.equal((await recovery.run(ctx.initial,ctx.api,ctx.observe)).recovered,false);
    assert.equal(ctx.calls.filter(x=>x==='openMap').length,1);
  }
});

test('closes exact-food inventory, opens the verified map, teleports once, and passively heals', async () => {
  const ctx = setup({ frames: fullFrames() });
  ctx.initial.hud.enemyBars = [{ level: 3 }];
  const out = await recovery.run(ctx.initial, ctx.api, ctx.observe);
  assert.equal(out.recovered, true);
  assert.equal(out.status, 'completed'); assert.equal(out.step, 'lisaStatueRecovery');
  assert.deepEqual(out.health, { current: 95, max: 100 });
  assert.equal(out.frameId, 5);
  assert.equal(out.teleportAttempted, true);
  assert.equal(out.questComplete, false);
  assert.equal(ctx.calls.filter(x => x === 'close').length, 1);
  assert.equal(ctx.calls.filter(x => x === 'openMap').length, 1);
  assert.equal(ctx.calls.filter(x => x === 'teleport').length, 1);
  assert.equal(ctx.released, 1);
});

test('initial inventory refusal and malformed initial state make no gameplay input', async () => {
  for (const [initial, options] of [[frame(1), { inventory: false }], [{ ...frame(1), frameId: NaN }, {}]]) {
    const ctx = setup(options); const out = await recovery.run(initial, ctx.api, ctx.observe);
    assert.equal(out.recovered, false); assert.equal(out.teleportAttempted, false);
    assert.equal(ctx.calls.some(x => ['close', 'openMap', 'teleport'].includes(x)), false);
    assert.equal(ctx.released, 1);
  }
});

test('rejects stale, wrong-session, duplicate, nonworld, climbing, unknown, enemy, zero-HP, and wrong-objective frames', async () => {
  const bads = [
    f => { f.timestamp = 1; }, f => { f.session = 'other'; }, f => { f.frameId = 1; },
    f => { f.hud.world = false; }, f => { f.hud.climbing = true; }, f => { f.hud.unknownHud = true; },
    f => { f.hud.health.current = 0; }, f => { f.exactLisa = false; },
  ];
  for (const mutate of bads) {
    const ctx = setup(); const bad = frame(2); mutate(bad); ctx.observe = async () => bad;
    const out = await recovery.run(ctx.initial, ctx.api, ctx.observe);
    assert.equal(out.recovered, false); assert.equal(out.teleportAttempted, false);
    assert.equal(ctx.calls.includes('openMap'), false); assert.equal(ctx.released, 1);
  }
});

test('nearby enemies are allowed during the grounded retreat start but stop recovery at the Statue', async () => {
  const ctx = setup({ frames: [
    frame(2), frame(3, { mapReady: true }),
    frame(4, { atStatue: true, hud: { ...frame(4).hud, enemyBars: [{ level: 4 }] } }),
  ] });
  ctx.initial.hud.enemyBars = [{ level: 2 }, { level: 3 }];
  const out = await recovery.run(ctx.initial, ctx.api, ctx.observe);
  assert.equal(out.status, 'stopped'); assert.equal(out.recovered, false);
  assert.equal(out.teleportAttempted, true);
  assert.equal(ctx.calls.includes('openMap'), true); assert.equal(ctx.calls.includes('teleport'), true);
  assert.equal(ctx.calls.some(x => x === 'sleep:500'), true); assert.equal(ctx.released, 1);
});

test('unknown UI and readiness exceptions stop before the map and release in finally', async () => {
  for (const change of [f => { f.hud.loading = true; }, f => { f.hud.tutorialStep = 'unknown'; }]) {
    const ctx = setup(); ctx.observe = async () => { const f = frame(2); change(f); return f; };
    const out = await recovery.run(ctx.initial, ctx.api, ctx.observe);
    assert.equal(out.recovered, false); assert.equal(ctx.calls.includes('openMap'), false); assert.equal(ctx.released, 1);
  }
  const ctx = setup({ fieldError: true });
  const out = await recovery.run(ctx.initial, ctx.api, ctx.observe);
  assert.match(out.reason, /field failed/); assert.equal(ctx.released, 1);
});

test('map and teleport failures are bounded and never report recovery', async () => {
  const mapCtx = setup({ frames: Array.from({ length: 6 }, (_, i) => frame(i + 2)) });
  const mapOut = await recovery.run(mapCtx.initial, mapCtx.api, mapCtx.observe);
  assert.equal(mapOut.recovered, false); assert.equal(mapOut.teleportAttempted, false); assert.equal(mapCtx.released, 1);
  const tpCtx = setup({ frames: [frame(2), frame(3, { mapReady: true })], teleportError: true });
  const tpOut = await recovery.run(tpCtx.initial, tpCtx.api, tpCtx.observe);
  assert.equal(tpOut.recovered, false); assert.equal(tpOut.teleportAttempted, true); assert.equal(tpCtx.released, 1);
});

test('fade timeout, capture failure, stop, and release failure all return stopped', async () => {
  const fadeCtx = setup({ frames: [frame(2), frame(3, { mapReady: true }), ...Array.from({ length: 12 }, (_, i) => frame(i + 4))] });
  const fadeOut = await recovery.run(fadeCtx.initial, fadeCtx.api, fadeCtx.observe);
  assert.equal(fadeOut.recovered, false); assert.equal(fadeOut.teleportAttempted, true); assert.equal(fadeCtx.released, 1);
  const captureCtx = setup({ observeError: true });
  const captureOut = await recovery.run(captureCtx.initial, captureCtx.api, captureCtx.observe);
  assert.match(captureOut.reason, /capture failed/); assert.equal(captureCtx.released, 1);
  const stopCtx = setup({ stopAt: 2 });
  const stopOut = await recovery.run(stopCtx.initial, stopCtx.api, stopCtx.observe);
  assert.equal(stopOut.recovered, false); assert.equal(stopCtx.released, 1);
  const releaseCtx = setup({ frames: fullFrames(), releaseError: true });
  const releaseOut = await recovery.run(releaseCtx.initial, releaseCtx.api, releaseCtx.observe);
  assert.equal(releaseOut.recovered, false); assert.match(releaseOut.reason, /release failed/);
  assert.equal(releaseCtx.released, 1);
});

test('passive healing stops at twelve polls when health remains below 95 percent', async () => {
  const ctx = setup({ frames: [frame(2), frame(3, { mapReady: true }), frame(4, { atStatue: true })] });
  const out = await recovery.run(ctx.initial, ctx.api, ctx.observe);
  assert.equal(out.recovered, false); assert.match(out.reason, /did not reach 95%/);
  assert.equal(ctx.calls.filter(x => x === 'sleep:500').length >= 12, true);
  assert.equal(ctx.released, 1);
});

test('accepts one verified Statue approach result and preserves its field health and frame', async () => {
  const ctx = setup({
    frames: [frame(2), frame(3, { mapReady: true }), frame(4, {
      atStatue: true, map: { map: 'Teyvat', x: -1315, y: 2566.115 },
    })],
    healAtStatue: (current, capture) => {
      assert.equal(current.frameId, 4); assert.equal(typeof capture, 'function');
      return { recovered: true, health: { current: 97, max: 100 }, fieldFrameId: 5, reason: 'healed', moves: 2, turns: 4 };
    },
  });
  const out = await recovery.run(ctx.initial, ctx.api, ctx.observe);
  assert.equal(out.recovered, true); assert.equal(out.teleportAttempted, true); assert.equal(out.questComplete, false);
  assert.equal(out.healingAttempted, true); assert.deepEqual(out.health, { current: 97, max: 100 });
  assert.equal(out.frameId, 5); assert.equal(out.moves, 2); assert.equal(out.turns, 4);
  assert.equal(out.polls, 3); assert.equal(ctx.calls.filter(x => x === 'healAtStatue').length, 1);
  assert.equal(ctx.released, 1);
});

test('refuses under-threshold, malformed health, and stale field-frame approach results', async () => {
  const results = [
    { recovered: true, health: { current: 94, max: 100 }, fieldFrameId: 5 },
    { recovered: true, health: { current: NaN, max: 100 }, fieldFrameId: 5 },
    { recovered: true, health: { current: 95, max: Infinity }, fieldFrameId: 5 },
    { recovered: true, health: { current: 95, max: 100 }, fieldFrameId: 3 },
  ];
  for (const result of results) {
    const ctx = setup({
      frames: [frame(2), frame(3, { mapReady: true }), frame(4, {
        atStatue: true, map: { map: 'Teyvat', x: -1315, y: 2566.115 },
      })],
      healAtStatue: result,
    });
    const out = await recovery.run(ctx.initial, ctx.api, ctx.observe);
    assert.equal(out.recovered, false); assert.equal(out.teleportAttempted, true);
    assert.equal(out.healingAttempted, true); assert.equal(out.questComplete, false);
    assert.equal(out.frameId, 4); assert.equal(ctx.calls.filter(x => x === 'healAtStatue').length, 1);
    assert.equal(ctx.released, 1);
  }
});

test('approach errors and stop requests release controls and never recover', async () => {
  const frames = [frame(2), frame(3, { mapReady: true }), frame(4, {
    atStatue: true, map: { map: 'Teyvat', x: -1315, y: 2566.115 },
  })];
  const errorCtx = setup({ frames, healAtStatue: {}, healError: true });
  const errorOut = await recovery.run(errorCtx.initial, errorCtx.api, errorCtx.observe);
  assert.equal(errorOut.recovered, false); assert.match(errorOut.reason, /approach failed/);
  assert.equal(errorCtx.released, 1);

  const stopCtx = setup({ stopAt: 7, frames: [frame(2), frame(3, { mapReady: true }), frame(4, { atStatue: true })] });
  const stopOut = await recovery.run(stopCtx.initial, stopCtx.api, stopCtx.observe);
  assert.equal(stopOut.recovered, false); assert.equal(stopOut.teleportAttempted, true);
  assert.equal(stopCtx.calls.includes('healAtStatue'), false); assert.equal(stopCtx.released, 1);
});

test('after twelve passive polls invokes the optional hook exactly once', async () => {
  const ctx = setup({
    frames: [frame(2), frame(3, { mapReady: true }), frame(4, { atStatue: true })],
    healAtStatue: { recovered: true, health: { current: 96, max: 100 }, fieldFrameId: 16 },
  });
  const out = await recovery.run(ctx.initial, ctx.api, ctx.observe);
  assert.equal(out.recovered, true); assert.equal(out.healingAttempted, true);
  assert.equal(out.polls, 15); assert.equal(ctx.calls.filter(x => x === 'healAtStatue').length, 1);
  assert.equal(ctx.released, 1);
});

test('within three meters passive healing remains available without the hook', async () => {
  const ctx = setup({ frames: [
    frame(2), frame(3, { mapReady: true }),
    frame(4, { atStatue: true, map: { map: 'Teyvat', x: -1321.5, y: 2566.115 } }),
    frame(5, { atStatue: true, hud: { ...frame(5).hud, health: { current: 95, max: 100 } } }),
  ] });
  const out = await recovery.run(ctx.initial, ctx.api, ctx.observe);
  assert.equal(out.recovered, true); assert.equal(out.health.current, 95); assert.equal(out.frameId, 5);
  assert.equal(out.healingAttempted, undefined); assert.equal(ctx.calls.includes('healAtStatue'), false);
  assert.equal(ctx.released, 1);
});
