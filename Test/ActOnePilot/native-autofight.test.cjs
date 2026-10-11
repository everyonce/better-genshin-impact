const test = require('node:test');
const assert = require('node:assert/strict');
const {
  DEFAULT_POLL_MS,
  DEFAULT_TIMEOUT_MS,
  NativeFightTimeoutError,
  STARTER_TRIAL_STRATEGY,
  runStarterTrialAutoFight,
} = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

function harness(runAutoFightTask, checkStop = () => {}) {
  const calls = [];
  let onCancel;
  const token = {};
  const cts = {
    Token: token,
    Cancel() { calls.push('cancel'); if (onCancel) onCancel(); },
    Dispose() { calls.push('dispose'); },
  };
  const native = {
    createLinkedCancellationTokenSource() { calls.push('linked-cts'); return cts; },
    createAutoFightParam(name) {
      calls.push(['param', name]);
      return { Timeout: 120, PickDropsAfterFightEnabled: true };
    },
    runAutoFightTask(param, receivedToken) {
      calls.push(['run', param.Timeout, param.PickDropsAfterFightEnabled, receivedToken]);
      return runAutoFightTask({ calls, token, setOnCancel: fn => { onCancel = fn; } });
    },
  };
  return { native, calls, checkStop, token };
}

test('runs exact starter strategy with local 15-second settings and cleans up after success', async () => {
  const h = harness(async () => 'finished');
  const result = await runStarterTrialAutoFight(h.native, h.checkStop);
  assert.equal(result, 'finished');
  assert.equal(h.calls[0], 'linked-cts');
  assert.deepEqual(h.calls[1], ['param', STARTER_TRIAL_STRATEGY]);
  assert.deepEqual(h.calls[2].slice(0, 3), ['run', 15, false]);
  assert.equal(h.calls[2][3], h.token);
  assert.ok(h.calls.includes('cancel'));
  assert.equal(h.calls.at(-1), 'dispose');
  assert.equal(DEFAULT_TIMEOUT_MS, 15_000);
  assert.equal(DEFAULT_POLL_MS, 50);
});

test('deadline requests linked cancellation and waits for cooperative native unwind before disposal', async () => {
  let unwound = false;
  const h = harness(({ setOnCancel }) => new Promise(resolve => {
    setOnCancel(() => setTimeout(() => { unwound = true; resolve('unwound'); }, 15));
  }));
  await assert.rejects(
    runStarterTrialAutoFight(h.native, h.checkStop, { timeoutMs: 8, pollMs: 1 }),
    error => error instanceof NativeFightTimeoutError && error.timeoutMs === 8,
  );
  assert.equal(unwound, true);
  assert.ok(h.calls.indexOf('dispose') > h.calls.indexOf('cancel'));
});

test('local stop check cancels and waits for native unwind before propagating its error', async () => {
  let unwound = false;
  let checks = 0;
  const h = harness(({ setOnCancel }) => new Promise(resolve => {
    setOnCancel(() => setTimeout(() => { unwound = true; resolve(); }, 15));
  }), () => { if (++checks > 1) throw new Error('stop.json requested stop'); });
  await assert.rejects(
    runStarterTrialAutoFight(h.native, h.checkStop, { timeoutMs: 1000, pollMs: 1 }),
    /stop\.json requested stop/,
  );
  assert.equal(unwound, true);
  assert.equal(h.calls.at(-1), 'dispose');
});

test('native rejection is propagated after linked cancellation and disposal', async () => {
  const h = harness(async () => { throw new Error('native failure'); });
  await assert.rejects(runStarterTrialAutoFight(h.native, h.checkStop), /native failure/);
  assert.ok(h.calls.includes('cancel'));
  assert.equal(h.calls.at(-1), 'dispose');
});

test('preflight stop denial creates no token source, parameter, or native task', async () => {
  const h = harness(async () => 'should not run', () => { throw new Error('focus lost'); });
  await assert.rejects(runStarterTrialAutoFight(h.native, h.checkStop), /focus lost/);
  assert.deepEqual(h.calls, []);
});

