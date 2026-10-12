const test = require('node:test');
const assert = require('node:assert/strict');
const pause = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/local-pause.js');

function deferred() {
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return { promise, resolve };
}
function frame(frameId, timestamp, session = 's', kind = null) {
  return { frameId, timestamp, session, kind, activeField: true };
}
function harness(options = {}) {
  let now = 10000, index = 0, stopped = false, liveFocus = true;
  let proofCalls = 0;
  const queue = options.frames || [];
  const events = [];
  const api = {
    now: () => now,
    sleep: async ms => { events.push(['sleep', ms]); await new Promise(r => setImmediate(r)); now += ms; },
    pauseObserve: async () => {
      events.push(['observe']);
      if (options.captureThrows && index === 0) { index++; throw Error('capture'); }
      const item = queue[Math.min(index++, queue.length - 1)];
      if (item instanceof Promise) return await item;
      return item;
    },
    pauseProof: o => { events.push(['proof', o.frameId]); if (options.proofThrows && proofCalls++ === 0) throw Error('ocr'); return o.kind ? { kind: typeof o.kind === 'string' ? o.kind : 'domain', evidence: ['Pause'] } : null; },
    pauseInputReady: o => { events.push(['ready', o.frameId]); if (options.readyThrows) throw Error('predicate'); return liveFocus && o.activeField === true; },
    pauseKey: async (o, key, duration) => { events.push(['key', key, duration, o.frameId]); if (options.keyThrows && key === options.keyThrows) throw Error('keydown'); },
    release: async () => { events.push(['release']); if (options.releaseThrows && events.filter(x => x[0] === 'release').length === 1) throw Error('release'); },
    pauseRecoverFocus: async (session, detail) => { events.push(['recover', session, detail.readOnly]); },
    pausePending: async info => events.push(['pending', info.session]),
    shouldStop: () => stopped
  };
  return { api, events, stop: () => { stopped = true; }, focus: v => { liveFocus = v; }, setNow: v => { now = v; } };
}

test('already paused yields immutable verified proof without input', async () => {
  const h = harness({ frames: [frame(2, 8999), frame(3, 10000, 's', { kind: 'pause', evidence: ['Continue'] })] });
  const proof = await pause.ensure({ session: 's', afterFrameId: 1 }, h.api);
  assert.equal(proof.verified, true); assert.equal(proof.pauseFrameId, 3); assert.equal(proof.sourceFrameId, 1);
  assert.ok(Object.isFrozen(proof)); assert.ok(Object.isFrozen(proof.evidence));
  assert.ok(h.events.some(e => e[0] === 'release'));
  assert.equal(h.events.some(e => e[0] === 'key'), false);
});

test('visible pause waits for confirmed release and retries failed release without pressing keys', async () => {
  const h = harness({ releaseThrows: true, frames: [frame(1, 10000, 's', 'journal'), frame(2, 10250, 's', 'journal')] });
  const proof = await pause.ensure({ session: 's', afterFrameId: 0 }, h.api);
  assert.equal(proof.verified, true);
  assert.ok(h.events.filter(e => e[0] === 'release').length >= 2);
  assert.equal(h.events.some(e => e[0] === 'key'), false);
});

test('OCR exception and invalid request never produce an unverified success', async () => {
  const h = harness({ proofThrows: true, frames: [frame(1, 10000), frame(2, 10250, 's', 'domain')] });
  h.api.pauseInputReady = () => false;
  const proof = await pause.ensure({ session: 's', afterFrameId: 0 }, h.api);
  assert.equal(proof.verified, true);
  await assert.rejects(pause.ensure({ session: 's', afterFrameId: -1 }, h.api), /afterFrameId/);
  assert.equal(h.events.some(e => e[0] === 'key'), false);
});

test('release failure retries and a requested stop cannot cancel pause cleanup', async () => {
  const h = harness({ releaseThrows: true, frames: [frame(1, 10000), frame(2, 10250), frame(3, 10500, 's', 'inventory')] });
  const wait = pause.ensure({ session: 's', afterFrameId: 0 }, h.api);
  for (let i = 0; i < 8 && !h.events.some(e => e[0] === 'key'); i++) await new Promise(r => setImmediate(r));
  h.stop();
  const proof = await wait;
  assert.equal(proof.verified, true);
  assert.deepEqual(h.events.filter(e => e[0] === 'key').map(e => e[1]), ['VK_B']);
  assert.ok(h.events.filter(e => e[0] === 'release').length >= 2);
});

test('B not pausing leads to J only after a new fresh active-field frame and the input gap', async () => {
  const h = harness({ frames: [frame(1, 10000), frame(2, 10250), frame(3, 10500), frame(4, 10750), frame(5, 11000), frame(6, 11250), frame(7, 11500, 's', 'domain')] });
  const p = await pause.ensure({ session: 's', afterFrameId: 0 }, h.api);
  assert.deepEqual(h.events.filter(e => e[0] === 'key').map(e => e[1]), ['VK_B', 'VK_J']);
  assert.equal(p.verified, true); assert.equal(p.sourceFrameId, 4);
});

test('B and J ineffective lead to one VK_ESCAPE fallback and a fresh verified menu proof', async () => {
  const h = harness({ frames: [frame(1, 10000), frame(2, 10250), frame(3, 10500), frame(4, 10750),
    frame(5, 11000), frame(6, 11250), frame(7, 11500), frame(8, 11750, 's', 'menu')] });
  const proof = await pause.ensure({ session: 's', afterFrameId: 0 }, h.api);
  assert.equal(proof.kind, 'menu');
  assert.deepEqual(h.events.filter(e => e[0] === 'key').map(e => e[1]), ['VK_B', 'VK_J', 'VK_ESCAPE']);
  assert.equal(new Set(h.events.filter(e => e[0] === 'key').map(e => e[1])).size, 3);
  assert.equal(proof.sourceFrameId, 7);
});

test('release and capture failures retry from the next cycle, then return a local pause proof', async () => {
  const h = harness({ releaseThrows: true, captureThrows: true, frames: [frame(2, 10250, 's', 'map')] });
  const proof = await pause.ensure({ session: 's', afterFrameId: 0 }, h.api);
  assert.equal(proof.verified, true);
  assert.equal(proof.kind, 'map');
  assert.ok(h.events.filter(e => e[0] === 'release').length >= 2);
  assert.equal(h.events.some(e => e[0] === 'key'), false);
});

test('throwing capture, predicate, and key-down are contained; failed key is consumed', async () => {
  const h = harness({ captureThrows: true, keyThrows: 'VK_B', frames: [frame(2, 10000), frame(4, 10250), frame(6, 10500), frame(8, 10750, 's', 'domain')] });
  const ready = h.api.pauseInputReady; let readyCalls = 0;
  h.api.pauseInputReady = o => { if (readyCalls++ === 0) throw Error('predicate'); return ready(o); };
  const wait = pause.ensure({ session: 's', afterFrameId: 0 }, h.api);
  for (let i = 0; i < 8 && !h.events.some(e => e[0] === 'key'); i++) await new Promise(r => setImmediate(r));
  h.stop();
  const proof = await wait;
  assert.equal(proof.verified, true);
  assert.equal(h.events.filter(e => e[0] === 'key' && e[1] === 'VK_B').length, 1);
  assert.equal(h.events.some(e => e[0] === 'recover'), true);
});

test('unrecognized persistent UI remains pending with no false proof until pause appears', async () => {
  const gate = deferred();
  const h = harness({ frames: [gate.promise] });
  const wait = pause.ensure({ session: 's', afterFrameId: 0 }, h.api);
  let settled = false; wait.then(() => { settled = true; }, () => { settled = true; });
  await new Promise(r => setImmediate(r));
  assert.equal(settled, false); assert.equal(h.events.some(e => e[0] === 'key'), false);
  gate.resolve(frame(1, 10001, 's', { kind: 'pause', evidence: ['Continue'] }));
  const proof = await wait; assert.equal(proof.verified, true);
});

test('session change or stale focus observations recover read-only and never input', async () => {
  const h = harness({ frames: [frame(1, 10000, 'other'), frame(2, 5000, 's'), frame(3, 10500, 's', 'journal')] });
  const wait = pause.ensure({ session: 's', afterFrameId: 0 }, h.api);
  h.stop();
  const proof = await wait;
  assert.equal(proof.verified, true);
  assert.ok(h.events.some(e => e[0] === 'recover'));
  assert.equal(h.events.some(e => e[0] === 'key'), false);
});
