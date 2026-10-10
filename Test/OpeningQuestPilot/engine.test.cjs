const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const packageDir = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/OpeningQuestPilot');
const engine = require(path.join(packageDir, 'engine.js'));

function fixture(enabled = true) {
    const calls = [], writes = [];
    let clock = 1000000;
    const api = {
        now: () => clock,
        sleep: async ms => { clock += ms; },
        focusGame: async () => {},
        requireInputReady: () => {},
        write: (file, text, append) => writes.push({ file, value: JSON.parse(text), append }),
        capture: async file => ({ timestamp: clock, width: 1920, height: 1080, ocr: [{ text: 'Follow Paimon' }] }),
        ...Object.fromEntries(['keyPress', 'keyDown', 'keyUp', 'moveMouseBy', 'click'].map(k => [k, (...args) => calls.push([k, ...args])]))
    };
    const runner = engine.create(api, { session: 'test-session', enableInput: enabled });
    const command = (fields = {}) => ({ id: 'step-1', session: 'test-session', expectedFrameId: 1, createdAt: clock, action: 'observe', ...fields });
    return { api, runner, calls, writes, command, advance: ms => { clock += ms; } };
}

test('observation includes frame, nonce, dimensions, screenshot and plain OCR', async () => {
    const f = fixture(false);
    const observation = await f.runner.observe();
    assert.deepEqual(observation, { session: 'test-session', frameId: 1, timestamp: 1000000, width: 1920, height: 1080,
        screenshotPath: 'observations/test-session/frame-0001.png', enableInput: false, ocr: [{ text: 'Follow Paimon' }] });
    assert.equal(await f.runner.process(f.command()), 'completed');
    assert.deepEqual(f.calls, []);
});

test('rejects missing, stale, old-session, expired, future and malicious commands with no input', async () => {
    const f = fixture();
    await f.runner.observe();
    const invalid = [null, {}, [], f.command({ session: 'previous-session' }), f.command({ expectedFrameId: 0 }),
        f.command({ createdAt: 969999 }), f.command({ createdAt: 1000001 }),
        f.command({ action: 'eval', code: 'keyPress("VK_F")' }), f.command({ action: 'keyPress', key: 'VK_RETURN' }),
        f.command({ action: 'keyPress', key: 'VK_F', code: 'anything' }), f.command({ id: '__proto__', action: 'shell' })];
    for (const c of invalid) assert.equal(await f.runner.process(c), 'rejected');
    assert.deepEqual(f.calls, []);
});

test('rejects out-of-bounds, non-integral, string and forbidden hold input', async () => {
    const f = fixture();
    await f.runner.observe();
    for (const fields of [
        { action: 'hold', key: 'VK_F', ms: 30 }, { action: 'hold', key: 'VK_W', ms: 29 },
        { action: 'hold', key: 'VK_SPACE', ms: 1001 }, { action: 'hold', key: 'VK_W', ms: '30' },
        { action: 'moveMouseBy', dx: 301, dy: 0 }, { action: 'moveMouseBy', dx: 0, dy: -301 },
        { action: 'click', x: 1920, y: 0 }, { action: 'click', x: 0, y: 1080 },
        { action: 'click', x: -1, y: 0 }, { action: 'click', x: 0.1, y: 0 }
    ]) assert.equal(await f.runner.process(f.command(fields)), 'rejected');
    assert.deepEqual(f.calls, []);
});

test('records start before input and completion after capture; prevents duplicate replay', async () => {
    const f = fixture();
    await f.runner.observe();
    f.api.keyPress = key => {
        assert.equal(f.writes.at(-1).value.status, 'started');
        f.calls.push(['keyPress', key]);
    };
    const c = f.command({ action: 'keyPress', key: 'VK_F' });
    assert.equal(await f.runner.process(c), 'completed');
    assert.equal(f.writes.at(-1).value.status, 'completed');
    assert.equal(f.writes.at(-1).value.frameId, 2);
    assert.equal(await f.runner.process({ ...c, expectedFrameId: 2 }), 'rejected');
    assert.deepEqual(f.calls, [['keyPress', 'VK_F']]);
});

test('input disabled still permits observe and stop', async () => {
    const f = fixture(false);
    await f.runner.observe();
    assert.equal(await f.runner.process(f.command({ action: 'click', x: 100, y: 100 })), 'rejected');
    assert.equal(await f.runner.process(f.command({ action: 'stop' })), 'stopped');
    assert.equal(f.runner.expired(), true);
    assert.deepEqual(f.calls, []);
});

test('hold releases its key on cancellation and fails closed', async () => {
    const f = fixture();
    await f.runner.observe();
    f.api.sleep = async ms => { if (ms === 50) throw new Error('Cancelled'); };
    await assert.rejects(f.runner.process(f.command({ action: 'hold', key: 'VK_W', ms: 1000 })), /Cancelled/);
    assert.deepEqual(f.calls, [['keyDown', 'VK_W'], ['keyUp', 'VK_W']]);
    assert.equal(await f.runner.process(f.command({ id: 'step-2', action: 'keyPress', key: 'VK_F' })), 'stopped');
    assert.equal(f.writes.at(-1).value.status, 'failed');
});

test('focus failure and commands expiring during focus never send input', async () => {
    for (const fail of [true, false]) {
        const f = fixture();
        await f.runner.observe();
        f.api.focusGame = async () => {
            if (fail) throw new Error('Cannot focus game');
            f.advance(30001);
        };
        await assert.rejects(f.runner.process(f.command({ action: 'keyPress', key: 'VK_F' })),
            fail ? /Cannot focus game/ : /Expired/);
        assert.deepEqual(f.calls, []);
        assert.equal(f.runner.expired(), true);
    }
});

test('hold detects lost foreground within a 50ms sleep chunk and releases key', async () => {
    const f = fixture();
    await f.runner.observe();
    const sleeps = [];
    f.api.sleep = async ms => { sleeps.push(ms); };
    f.api.requireInputReady = () => { throw new Error('Game lost foreground focus'); };
    await assert.rejects(f.runner.process(f.command({ action: 'hold', key: 'VK_W', ms: 1000 })), /lost foreground/);
    assert.deepEqual(sleeps, [1, 50]);
    assert.deepEqual(f.calls, [['keyDown', 'VK_W'], ['keyUp', 'VK_W']]);
    assert.equal(f.runner.expired(), true);
});

test('adapter rejects unfocused input while allowing cleanup key-up', async () => {
    const calls = [], genshin = { width: 1920, height: 1080, isRemoteDesktopSession: true, isGameForeground: false, focusGame: async () => {} };
    const context = { genshin, ...Object.fromEntries(['keyPress', 'keyDown', 'keyUp', 'moveMouseBy', 'click']
        .map(k => [k, (...args) => calls.push([k, ...args])])) };
    vm.runInNewContext(fs.readFileSync(path.join(packageDir, 'bgi.js'), 'utf8'), context);
    const adapter = context.createOpeningQuestAdapter();
    await assert.rejects(adapter.focusGame(), /lost foreground/);
    for (const action of ['keyPress', 'keyDown', 'moveMouseBy', 'click']) {
        assert.throws(() => adapter[action]('VK_W', 1), /lost foreground/);
    }
    adapter.keyUp('VK_W');
    assert.deepEqual(calls, [['keyUp', 'VK_W']]);
});

test('adapter refuses console-session input and focus while still releasing keys', async () => {
    const calls = [];
    const context = { genshin: { isRemoteDesktopSession: false, isGameForeground: true,
        focusGame: async () => calls.push('focus') },
        keyPress: () => calls.push('press'), keyUp: key => calls.push(key) };
    vm.runInNewContext(fs.readFileSync(path.join(packageDir, 'bgi.js'), 'utf8'), context);
    const adapter = context.createOpeningQuestAdapter();
    await assert.rejects(adapter.focusGame(), /RDP session required/);
    assert.throws(() => adapter.keyPress('VK_W'), /RDP session required/);
    adapter.keyUp('VK_W');
    assert.deepEqual(calls, ['VK_W']);
});

test('new sessions retain distinct screenshot paths', async () => {
    const f = fixture();
    const first = await f.runner.observe();
    const second = await engine.create(f.api, { session: 'second-session', enableInput: false }).observe();
    assert.notEqual(first.screenshotPath, second.screenshotPath);
    assert.equal(second.screenshotPath, 'observations/second-session/frame-0001.png');
});

test('cancel before input and receipt-write failure never send input', async () => {
    for (const stage of ['sleep', 'write']) {
        const f = fixture();
        await f.runner.observe();
        f.api[stage] = () => { throw new Error('Injected failure'); };
        await assert.rejects(f.runner.process(f.command({ action: 'keyPress', key: 'VK_F' })), /Injected failure/);
        assert.deepEqual(f.calls, []);
        assert.equal(f.runner.expired(), true);
    }
});

test('capture failure after input stops further input; ambiguous action cannot replay', async () => {
    const f = fixture();
    await f.runner.observe();
    f.api.capture = () => { throw new Error('Capture failed'); };
    const c = f.command({ action: 'click', x: 1919, y: 1079 });
    await assert.rejects(f.runner.process(c), /Capture failed/);
    assert.equal(await f.runner.process(c), 'stopped');
    assert.deepEqual(f.calls, [['click', 1919, 1079]]);
});

test('valid bounded hold and camera delta execute once; overlap is blocked', async () => {
    const f = fixture();
    await f.runner.observe();
    let resume;
    const normalSleep = f.api.sleep;
    f.api.sleep = ms => ms === 30 ? new Promise(resolve => { resume = resolve; }) : normalSleep(ms);
    const running = f.runner.process(f.command({ action: 'hold', key: 'VK_SPACE', ms: 30 }));
    await Promise.resolve();
    await Promise.resolve();
    assert.equal(await f.runner.process(f.command({ id: 'overlap' })), 'busy');
    resume();
    assert.equal(await running, 'completed');
    assert.equal(await f.runner.process(f.command({ id: 'camera', expectedFrameId: 2, action: 'moveMouseBy', dx: -300, dy: 300 })), 'completed');
    assert.deepEqual(f.calls, [['keyDown', 'VK_SPACE'], ['keyUp', 'VK_SPACE'], ['moveMouseBy', -300, 300]]);
});

test('idle and maximum session time cannot be extended by rejected commands', async () => {
    const f = fixture();
    await f.runner.observe();
    f.advance(120000);
    assert.equal(await f.runner.process(f.command()), 'stopped');
    assert.deepEqual(f.calls, []);
    const g = fixture();
    await g.runner.observe();
    for (let i = 1; i <= 17; i++) {
        g.advance(100000);
        assert.equal(await g.runner.process(g.command({ id: `step-${i}`, expectedFrameId: i })), 'completed');
    }
    g.advance(100000);
    assert.equal(await g.runner.process(g.command({ id: 'last', expectedFrameId: 18 })), 'stopped');
});

test('main safely polls missing command file and restores metrics and triggers', async () => {
    let clock = 0, clears = 0, metrics = [], captures = 0, reads = [];
    const context = {
        Date: { now: () => clock }, Math, settings: {}, genshin: { width: 2560, height: 1440, isRemoteDesktopSession: true, windowsSessionId: 5 },
        dispatcher: { clearAllTriggers: () => clears++ }, getGameMetrics: () => [1280, 720, 1.25],
        setGameMetrics: (...args) => metrics.push(args), log: { info: () => {} },
        sleep: async ms => { clock += ms; }, RecognitionObject: { Ocr: () => ({}) },
        captureGameRegion: () => { captures++; return { width: 1920, height: 1080, srcMat: {}, findMulti: () => ({ count: 0 }), dispose() {} }; },
        file: { isExists: () => false, writeTextSync: () => true, writeImageSync: () => true,
            readTextSync: file => { reads.push(file); return fs.readFileSync(path.join(packageDir, file), 'utf8'); } }
    };
    await vm.runInNewContext(fs.readFileSync(path.join(packageDir, 'main.js'), 'utf8'), context);
    assert.equal(captures, 1);
    assert.deepEqual(reads, ['engine.js', 'bgi.js']);
    assert.equal(clears, 2);
    assert.deepEqual(metrics, [[1920, 1080, 1], [1280, 720, 1.25]]);
});
