const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const root = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/UnexpectedPowerPilot');
const policy = require(path.join(root, 'policy.js'));
const prompt = text => [{ text, x: 900, y: 220, width: 500, height: 30 }];

function harness({ frames = [], remote = true, focus = true, session = 4, onSleep, writeImage = true, saveFails = false } = {}) {
    let frameIndex = 0;
    const calls = [], written = [], saved = [];
    let currentRows = [];
    const image = { width: 1920, height: 1080, srcMat: {}, disposed: false,
        findMulti: recognition => {
            const area = recognition && recognition.args;
            const selected = area && area[0] === 800
                ? currentRows.filter(r => r.y >= 985)
                : currentRows;
            return Object.assign(selected.map(r => ({ ...r, dispose() { this.disposed = true; } })), {
                count: selected.length, dispose() { calls.push('dispose-found'); }
            });
        }, dispose() { this.disposed = true; calls.push('dispose-image'); }
    };
    const context = {
        genshin: { isRemoteDesktopSession: remote, windowsSessionId: session, isGameForeground: focus },
        RecognitionObject: { Ocr: (...args) => ({ args }) },
        captureGameRegion: () => { calls.push('capture'); currentRows = frames[Math.min(frameIndex++, frames.length - 1)] || []; return image; },
        file: { writeImageSync: (p, src) => { calls.push('write-image'); written.push(p); return writeImage; } },
        sleep: async ms => { calls.push(['sleep', ms]); if (onSleep) await onSleep(context, ms); },
        keyDown: key => calls.push(['down', key]),
        keyUp: key => calls.push(['up', key]),
        Date, String, Number, Math, Object, Array, Error, RegExp,
        save: x => { calls.push(['save', x]); if (saveFails) throw new Error('save_failed'); saved.push(x); }
    };
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(path.join(root, 'adapter.js'), 'utf8') + '\nthis.createAdapter = createUnexpectedPowerAdapter;', context);
    return { context, calls, written, saved, create: () => context.createAdapter(policy, 's1', context.save) };
}

const rowsOf = text => prompt(text).concat([{ text: '987/987', x: 918, y: 1002 }]);

test('holds only prompt-matched bounded E and Q inputs and releases every key', async () => {
    for (const [text, key, ms] of [
        ['Hold E to unleash Elemental Skill', 'E', 1200],
        ['Press E to unleash Elemental Skill', 'E', 60],
        ['Press Q to unleash Elemental Burst', 'Q', 60]
    ]) {
        const h = harness({ frames: [rowsOf(text)] });
        await h.create().hold(key, ms);
        assert.deepEqual(h.calls.filter(c => Array.isArray(c) && c[0] === 'down'), [['down', `VK_${key}`]]);
        assert.deepEqual(h.calls.filter(c => Array.isArray(c) && c[0] === 'up'), [['up', `VK_${key}`]]);
        const sleeps = h.calls.filter(c => Array.isArray(c) && c[0] === 'sleep').map(c => c[1]);
        assert.equal(sleeps.reduce((a, b) => a + b, 0), ms + 800);
        assert.ok(sleeps.slice(0, -1).every(n => n <= 50));
    }
});

test('releases actual key on sleep rejection, cancellation/readiness loss, and foreground loss', async () => {
    const sleeperFails = harness({ frames: [rowsOf('Hold E to unleash Elemental Skill')], onSleep: () => { throw new Error('cancelled'); } });
    await assert.rejects(sleeperFails.create().hold('E', 1200), /cancelled/);
    assert.deepEqual(sleeperFails.calls.filter(c => Array.isArray(c) && c[0] === 'up'), [['up', 'VK_E']]);

    for (const change of [c => { c.genshin.windowsSessionId = 9; }, c => { c.genshin.isGameForeground = false; }]) {
        const h = harness({ frames: [rowsOf('Hold E to unleash Elemental Skill')], onSleep: c => change(c) });
        await assert.rejects(h.create().hold('E', 1200), /rdp_session_changed|game_focus_lost/);
        assert.deepEqual(h.calls.filter(c => Array.isArray(c) && c[0] === 'up'), [['up', 'VK_E']]);
    }
});

test('focus loss and non-RDP sessions fail closed before input', async () => {
    for (const opts of [{ remote: false }, { focus: false }]) {
        const h = harness({ ...opts, frames: [rowsOf('Press E to unleash Elemental Skill')] });
        await assert.rejects(h.create().hold('E', 60));
        assert.equal(h.calls.some(c => Array.isArray(c) && ['down', 'up'].includes(c[0])), false);
    }
});

test('fresh prompt change, arbitrary key, and altered duration are rejected before keydown', async () => {
    const changed = harness({ frames: [rowsOf('Press E to unleash Elemental Skill'), rowsOf('Press Q to unleash Elemental Burst')] });
    const changedAdapter = changed.create();
    await changedAdapter.observe(); // The runner's prompt is E; the adapter must recheck before holding.
    await assert.rejects(changedAdapter.hold('E', 60), /tutorial_prompt_changed_before_input/);
    assert.equal(changed.calls.some(c => Array.isArray(c) && c[0] === 'down'), false);

    for (const [key, ms] of [['X', 60], ['E', 61], ['Q', 1200]]) {
        const h = harness({ frames: [rowsOf('Hold E to unleash Elemental Skill')] });
        await assert.rejects(h.create().hold(key, ms), /tutorial_prompt_changed_before_input/);
        assert.equal(h.calls.some(c => Array.isArray(c) && c[0] === 'down'), false);
    }
});

test('capture, screenshot-write, and status-save failures never send input', async () => {
    const badCapture = harness({ frames: [rowsOf('Press E to unleash Elemental Skill')] });
    badCapture.context.captureGameRegion = () => { throw new Error('capture_failed'); };
    await assert.rejects(badCapture.create().hold('E', 60), /capture_failed/);

    const badWrite = harness({ frames: [rowsOf('Press E to unleash Elemental Skill')], writeImage: false });
    await assert.rejects(badWrite.create().hold('E', 60), /screenshot_write_failed/);

    const badSave = harness({ frames: [rowsOf('Press E to unleash Elemental Skill')], saveFails: true });
    await assert.rejects(badSave.create().hold('E', 60), /save_failed/);
    for (const h of [badCapture, badWrite, badSave])
        assert.equal(h.calls.some(c => Array.isArray(c) && c[0] === 'down'), false);
});

test('combat input requires a live world HUD and refuses menu overlays', async () => {
    for (const rows of [prompt('Press E to unleash Elemental Skill'),
        rowsOf('Press E to unleash Elemental Skill').concat([{ text: 'Settings', x: 80, y: 50 }])]) {
        const h = harness({ frames: [rows] });
        await assert.rejects(h.create().hold('E', 60), /world_hud_unavailable/);
        assert.equal(h.calls.some(c => Array.isArray(c) && c[0] === 'down'), false);
    }
});

test('verifiedWorld requires health plus party or tutorial evidence and rejects menu text', async () => {
    async function observe(rows) {
        const h = harness({ frames: [rows] });
        return await h.create().observe();
    }
    const health = { text: '1200 / 1200', x: 950, y: 1000 };
    const lumina = { text: 'Lumina', x: 1650, y: 450 };
    assert.equal((await observe([health, lumina])).mode, 'verifiedWorld');
    assert.equal((await observe([health])).mode, null);
    assert.equal((await observe([lumina])).mode, null);
    assert.equal((await observe([health, lumina, { text: 'Settings', x: 900, y: 100 }])).mode, null);
    assert.equal((await observe([health, ...prompt('Press E to unleash Elemental Skill')])).mode, 'verifiedWorld');
    assert.equal((await observe(prompt('Press E to unleash Elemental Skill'))).mode, null);
});
