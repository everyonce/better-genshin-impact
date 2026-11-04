const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const engine = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/engine.js');

const target = {map: 'Teyvat', x: -1325, y: 2552};
const request = {id: 'route-test', mission: 'navigation', objective: 'Explore for Adventure Rank',
    session: 'route-session', expectedFrameId: 1, createdAt: 8000, deadlineMs: 20000,
    waypoints: [target], requireMeasuredGround: true};

// Build the ordinary native data shape. Successive frames can change independently of the first one.
function frame(id, now, y, state) {
    const map = {map: 'Teyvat', x: -1325, y};
    map.cameraAngle = mission.bearing(map, target);
    const stamp = {session: request.session, frameId: id, capturedAt: now};
    return {session: request.session, frameId: id, timestamp: now, map, ocr: [],
        hud: {world: true, groundControls: true, health: {current: 4015, max: 4015}, objectives: [],
            enemyBars: state === 'threat' ? [{x: 960, y: 320, width: 88, height: 5}] : [],
            captureStamp: {...stamp, source: 'game-capture-start'},
            enemyBarObservation: {...stamp, version: 1, kind: 'normal-ground-enemy-observation-v1', state,
                candidateCount: state === 'clear' ? 0 : 1, acceptedCount: state === 'threat' ? 1 : 0}}};
}

async function run(first, next) {
    let now = 8000;
    const moves = [];
    const api = {now: () => now, checkStop() {}, sleep: async ms => { now += ms; },
        runActTwoNavigationWithPause: (_source, _observe, runField) => runField(first),
        forward: async ms => { moves.push(ms); now += ms; }, rotate: () => assert.fail('unexpected turn')};
    const result = await mission.runNavigation(request, first, api, async () => next(now));
    return {result, moves};
}

test('request validation limits measured ground to free exploration', () => {
    const validate = value => engine.validate(value, request.session, 1, {}, 8000);
    assert.equal(validate(request), null);
    for (const value of [{...request, requireMeasuredGround: false}, {...request, objective: 'Talk to Amber'},
                         {...request, mission: 'observe'}]) assert.ok(validate(value));
});

test('unmeasured, stale, or mismatched ground stops before a movement', async () => {
    for (const change of [o => { delete o.hud.enemyBarObservation; },
        o => { o.hud.enemyBarObservation.frameId = 99; }, o => {
            o.hud.captureStamp.capturedAt = o.hud.enemyBarObservation.capturedAt = 6500;
        }, o => { o.hud.enemyBarObservation.state = 'ambiguous'; }]) {
        const first = frame(2, 8000, 2564, 'clear');
        change(first);
        const {result, moves} = await run(first, () => assert.fail('unexpected movement capture'));
        assert.equal(result.status, 'stopped');
        assert.deepEqual(moves, []);
    }
});

test('a new hostile stops the next movement even after a clear initial frame', async () => {
    const {result, moves} = await run(frame(2, 8000, 2564, 'clear'), now => frame(3, now, 2560, 'threat'));
    assert.equal(moves.length, 1);
    assert.equal(result.status, 'stopped');
    assert.equal(result.reason, 'Enemy observed during exploration');
});

test('measured clear frames allow the normal route to arrive', async () => {
    const {result, moves} = await run(frame(2, 8000, 2564, 'clear'), now => frame(3, now, 2552, 'clear'));
    assert.equal(moves.length, 1);
    assert.equal(result.status, 'arrived');
});
