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


const climbEvidence = require('./navigation-ground-climb.fixture.json');

// Run the real route body with the two unchanged recorded sources. Only the
// input boundary and later landing captures are synthetic; no live recovery is claimed.
async function runRecordedClimb({ground = climbEvidence.ground, climb = climbEvidence.climb,
    landingStates = ['clear', 'clear'], landingChange = () => {}} = {}) {
    ground = structuredClone(ground); climb = structuredClone(climb);
    let now = ground.timestamp, observations = 0;
    const inputs = [];
    const route = {...request, session: ground.session, expectedFrameId: ground.frameId,
        createdAt: now, waypoints: [{map: 'Teyvat', x: -1329.832, y: 2564.187}]};
    const api = {now: () => now, checkStop() {}, sleep: async ms => {now += ms;},
        runActTwoNavigationWithPause: (_source, _observe, runField) => runField(ground),
        forward: async ms => {inputs.push(['forward', ms]); now += ms;},
        releaseClimb: async () => {inputs.push(['release']); now += 60;},
        rotate: () => assert.fail('Recorded heading must not require a turn')};
    const observe = async () => {
        if (observations++ === 0) {now = Math.max(now, climb.timestamp); return climb;}
        // Model 350 ms capture/OCR cost on each new landed source. The first
        // capture is legitimately older than 1000 ms when the second returns.
        const capturedAt = now; now += 350;
        const landed = structuredClone(ground), state = landingStates[observations - 2];
        assert.notEqual(state, undefined, 'Recovery must stop after two landing captures');
        landed.frameId = climb.frameId + observations - 1; landed.timestamp = now;
        landed.map = {...climb.map};
        landed.hud.captureStamp = {session: landed.session, frameId: landed.frameId, capturedAt,
            source: 'game-capture-start'};
        landed.hud.enemyBarObservation = {version: 1, kind: 'normal-ground-enemy-observation-v1',
            session: landed.session, frameId: landed.frameId, capturedAt, state,
            reason: state === 'clear' ? 'no_bar_shaped_components' : 'inert_uncertain_landing',
            candidateCount: state === 'clear' ? 0 : null, acceptedCount: state === 'clear' ? 0 : null};
        landingChange(landed, observations - 2);
        return landed;
    };
    const result = await mission.runNavigation(route, ground, api, observe);
    return {result, inputs};
}

test('recorded route-04 measured ground permits exactly one incidental release and stops for replan', async () => {
    const {ground, climb} = climbEvidence;
    assert.equal(climb.hud.enemyBarObservation.state, 'unavailable');
    assert(mission.reviewedClimbRelease(climb, ground, climb.timestamp, 5000, ground.timestamp));
    const {result, inputs} = await runRecordedClimb();
    assert.deepEqual(inputs.map(x => x[0]), ['forward', 'release']);
    assert.equal(result.status, 'stopped');
    assert.equal(result.reason, 'Incidental climb recovered; inspect alternate path');
    assert.equal(result.groundRecovered, true);
    assert.equal(result.climbReleases, 1);
    assert.equal(result.nextWaypointIndex, 0);
});

test('measured release rejects foreign, stale, damaged, unmeasured or threatening witnesses', () => {
    const {ground, climb} = climbEvidence;
    const eligible = (c, g = ground, at = ground.timestamp, remaining = 5000) =>
        mission.reviewedClimbRelease(c, g, c.timestamp, remaining, at);
    assert.equal(eligible(climb, null, null), false);
    assert.equal(eligible(climb, ground, climb.timestamp), false); // old capture cannot be renewed
    assert.equal(eligible(climb, ground, ground.timestamp, 3999), false);
    for (const change of [o => {o.session = 'foreign';}, o => {o.frameId = ground.frameId;},
        o => {o.hud.health.current--;}, o => {o.hud.groundControls = true;},
        o => {o.hud.enemyBarObservation.state = 'threat';}, o => {o.hud.enemyBarObservation.state = 'ambiguous';},
        o => {o.hud.enemyBarObservation.reason = 'unknown';}, o => {o.hud.enemyBarObservation.frameId--;},
        o => {o.hud.captureStamp.capturedAt = o.hud.enemyBarObservation.capturedAt = o.timestamp - 1001;}]) {
        const bad = structuredClone(climb); change(bad); assert.equal(eligible(bad), false);
    }
    for (const change of [o => {o.hud.health.current--;}, o => {o.hud.groundControls = false;},
        o => {o.hud.climbing = true;}, o => {o.hud.enemyBarObservation.state = 'ambiguous';},
        o => {o.map.x += 3;}]) {
        const bad = structuredClone(ground); change(bad); assert.equal(eligible(climb, bad), false);
    }
});

test('unknown or threatening current climb never reaches the release even after one valid move', async () => {
    for (const state of ['threat', 'ambiguous', 'overloaded']) {
        const climb = structuredClone(climbEvidence.climb);
        climb.hud.enemyBarObservation.state = state;
        const {result, inputs} = await runRecordedClimb({climb});
        assert.deepEqual(inputs.map(x => x[0]), ['forward']);
        assert.equal(result.status, 'stopped');
        assert.equal(result.climbReleases, 0);
    }
});

test('both landed frames must independently prove fresh measured clear ground; no forward resumes', async () => {
    for (const landingStates of [['unavailable', 'clear'], ['clear', 'ambiguous'], ['clear', 'threat']]) {
        const {result, inputs} = await runRecordedClimb({landingStates});
        assert.deepEqual(inputs.map(x => x[0]), ['forward', 'release']);
        assert.equal(result.status, 'stopped');
        assert.equal(result.groundRecovered, false);
    }
    for (const change of [o => {o.hud.enemyBarObservation.frameId--;},
        o => {o.hud.captureStamp.capturedAt = o.hud.enemyBarObservation.capturedAt = o.timestamp - 1001;},
        o => {o.hud.health.current--;}, o => {o.hud.climbing = true;}]) {
        const {result, inputs} = await runRecordedClimb({landingChange: change});
        assert.deepEqual(inputs.map(x => x[0]), ['forward', 'release']);
        assert.equal(result.groundRecovered, false);
    }
});
