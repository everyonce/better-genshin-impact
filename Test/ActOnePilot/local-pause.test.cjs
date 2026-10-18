const test = require('node:test');
const assert = require('node:assert/strict');
const pause = require(process.env.LOCAL_PAUSE_MODULE || '../../BetterGenshinImpact/User/JsScript/ActOnePilot/local-pause.js');

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
  if (options.knownUi) api.pauseResolveKnownUi = async o => {
    events.push(['knownUi', o.frameId]);
    return await options.knownUi(o, events);
  };
  return { api, events, stop: () => { stopped = true; }, focus: v => { liveFocus = v; }, setNow: v => { now = v; } };
}

test('fresh post-action seed requests pause before the next capture, then independently verifies Inventory',async()=>{
 const h=harness({frames:[frame(2,10900,'s','inventory')]});
 const proof=await pause.ensure({session:'s',afterFrameId:0,initialObservation:frame(1,10000)},h.api);
 const key=h.events.findIndex(e=>e[0]==='key'),capture=h.events.findIndex(e=>e[0]==='observe');
 assert.ok(key>=0&&capture>key);assert.equal(h.events[key][1],'VK_B');
 assert.ok(h.events.slice(key,capture).some(e=>e[0]==='sleep'&&e[1]===650));
 assert.equal(proof.pauseFrameId,2);assert.equal(proof.sourceFrameId,1);
 assert.equal(h.events.filter(e=>e[0]==='key').length,1);
});
for(const [label,seed] of Object.entries({stale:frame(1,8999),future:frame(1,10001),session:frame(1,10000,'other'),reused:frame(0,10000)}))test('invalid '+label+' seed cannot trigger input',async()=>{
 const h=harness({frames:[frame(2,10000,'s','inventory')]});
 await pause.ensure({session:'s',afterFrameId:0,initialObservation:seed},h.api);
 assert.equal(h.events.some(e=>e[0]==='key'),false);assert.equal(h.events.filter(e=>e[0]==='observe').length,1);
});
test('recognized menu seed is input-proof and unknown menu seed cannot request a key',async()=>{
 for(const known of [true,false]){
  const seed=frame(1,10000,'s',known?'inventory':null);seed.activeField=false;
  const h=harness({frames:[frame(2,10250,'s','inventory')]});
  const proof=await pause.ensure({session:'s',afterFrameId:0,initialObservation:seed},h.api);
  assert.equal(h.events.some(e=>e[0]==='key'),false);assert.equal(proof.kind,'inventory');
 }
});
test('fresh seed never bypasses foreground readiness or failed key release',async()=>{
 const h=harness({frames:[frame(2,10250,'s','inventory')]});h.focus(false);
 await pause.ensure({session:'s',afterFrameId:0,initialObservation:frame(1,10000)},h.api);
 assert.equal(h.events.some(e=>e[0]==='key'),false);
 const failed=harness({frames:[frame(2,10250,'s','inventory')],releaseThrows:true});
 await pause.ensure({session:'s',afterFrameId:0,initialObservation:frame(1,10000)},failed.api);
 assert.equal(failed.events.some(e=>e[0]==='key'),false);
});

test('unchanged stalled dialogue ends within 60 seconds, releases keys, and never claims pause', async () => {
  const h = harness({ frames: [frame(1, 10000)] });
  h.api.pauseInputReady = () => false;
  await assert.rejects(pause.ensure({ session: 's', afterFrameId: 0 }, h.api),
    error => error.code === 'PAUSE_PROTECTION_EXHAUSTED' && /UNVERIFIED/.test(error.message));
  assert.ok(h.events.filter(e => e[0] === 'observe').length <= 40);
  assert.ok(h.api.now() <= 75000);
  assert.equal(h.events.some(e => e[0] === 'key'), false);
  assert.equal(h.events.at(-2)[0], 'release');
});

test('disk-low capture failures do not retry forever even with a frozen clock and failing sleeps', async () => {
  const h = harness();
  h.api.pauseObserve = async () => { h.events.push(['observe']); throw Error('Capture storage backpressure'); };
  h.api.sleep = async () => { throw Error('cancelled'); };
  await assert.rejects(pause.ensure({ session: 's', afterFrameId: 0 }, h.api),
    error => error.code === 'PAUSE_PROTECTION_EXHAUSTED');
  assert.equal(h.events.filter(e => e[0] === 'observe').length, 120);
  assert.equal(h.events.some(e => e[0] === 'key'), false);
});

test('explicit native storage backpressure releases and propagates without another capture or input',async()=>{
  const h=harness();
  h.api.pauseObserve=async()=>{h.events.push(['observe']);const e=Error('quota');e.code='CAPTURE_STORAGE_BLOCKED';throw e;};
  await assert.rejects(pause.ensure({session:'s',afterFrameId:0},h.api),e=>e.code==='CAPTURE_STORAGE_BLOCKED');
  assert.equal(h.events.filter(e=>e[0]==='observe').length,1);
  assert.ok(h.events.filter(e=>e[0]==='release').length>=2);
  assert.equal(h.events.some(e=>e[0]==='key'),false);
});

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

test('known UI resolver transitions through a fresh field to pause; attempted action is never proof', async () => {
  let attempts = 0;
  const h = harness({ frames: [
    { ...frame(1, 10000), activeField: false }, { ...frame(2, 10250), activeField: false },
    { ...frame(3, 10500), activeField: false }, { ...frame(4, 10750), activeField: false },
    frame(5, 11000, 's', 'menu')
  ], knownUi: () => attempts++ === 0 });
  const proof = await pause.ensure({ session: 's', afterFrameId: 0 }, h.api);
  assert.equal(proof.verified, true);
  assert.equal(proof.kind, 'menu');
  assert.equal(proof.pauseFrameId, 5);
  assert.equal(proof.sourceFrameId, 1);
  assert.deepEqual(h.events.filter(e => e[0] === 'knownUi').map(e => e[1]), [1, 4]);
  assert.equal(h.events.some(e => e[0] === 'key'), false);
});

test('throwing known UI resolver recovers read-only, waits for a fresh frame, and never fakes proof', async () => {
  let calls = 0;
  const h = harness({ frames: [{ ...frame(1, 10000), activeField: false },
    { ...frame(2, 10250), activeField: false }, frame(3, 10500, 's', 'party')],
    knownUi: () => { if (calls++ === 0) throw Error('resolver'); return undefined; } });
  const proof = await pause.ensure({ session: 's', afterFrameId: 0 }, h.api);
  assert.equal(proof.kind, 'party');
  assert.ok(h.events.some(e => e[0] === 'recover'));
  assert.equal(h.events.some(e => e[0] === 'key'), false);
});

test('stale observations, failed release, and already-recognized pause block known UI hook', async () => {
  let staleCalls = 0;
  const stale = harness({ frames: [frame(1, 8999), frame(2, 10250, 's', 'map')], knownUi: () => { staleCalls++; return true; } });
  assert.equal((await pause.ensure({ session: 's', afterFrameId: 0 }, stale.api)).kind, 'map');
  assert.equal(staleCalls, 0);

  let pausedCalls = 0;
  const release = harness({ releaseThrows: true, frames: [frame(1, 10000, 's', 'domain'), frame(2, 10250, 's', 'domain')],
    knownUi: () => { pausedCalls++; return true; } });
  assert.equal((await pause.ensure({ session: 's', afterFrameId: 0 }, release.api)).kind, 'domain');
  assert.equal(pausedCalls, 0);
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
test('fresh recognized conversation hands off immediately without inventing a pause proof',async()=>{
 const h=harness({frames:[frame(1,10000)]});
 h.api.pauseDialogueHandoff=()=>true;
 const result=await pause.ensure({session:'s',afterFrameId:0},h.api);
 assert.equal(result.conversationActive,true);assert.equal(result.verified,undefined);
 assert.ok(Object.isFrozen(result));assert.equal(result.frameId,1);
 assert.equal(h.events.some(e=>e[0]==='key'),false);
 assert.equal(h.events.filter(e=>e[0]==='observe').length,1);
});

test('short menu watchdog releases and fails within bounded time without false proof',async()=>{
 let now=0,frame=0,releases=0,keys=0;
 const api={now:()=>now,release:()=>{releases++},pauseObserve:async()=>({session:'s',frameId:++frame,timestamp:now}),pauseProof:()=>null,pauseInputReady:()=>false,pauseKey:()=>{keys++},sleep:async ms=>{now+=ms},pausePending:async()=>{}};
 await assert.rejects(pause.ensure({session:'s',afterFrameId:0,maxWaitMs:12000},api),e=>e.code==='PAUSE_PROTECTION_EXHAUSTED');
 assert.ok(now>=12000&&now<=13000);assert.ok(releases>1);assert.equal(keys,0);
});
