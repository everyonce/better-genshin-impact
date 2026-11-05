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

async function run(first, next, extensions = {}) {
    let now = 8000;
    const moves = [];
    const api = {now: () => now, checkStop() {}, sleep: async ms => { now += ms; },
        runActTwoNavigationWithPause: (_source, _observe, runField) => runField(first),
        forward: async ms => { moves.push(ms); now += ms; }, rotate: () => assert.fail('unexpected turn'), ...extensions};
    const result = await mission.runNavigation(request, first, api, async () => next(now));
    return {result, moves};
}

test('request validation limits measured ground to free exploration', () => {
    const validate = value => engine.validate(value, request.session, 1, {}, 8000);
    assert.equal(validate(request), null);
    for (const value of [{...request, requireMeasuredGround: false}, {...request, objective: 'Talk to Amber'},
                         {...request, mission: 'observe'}]) assert.ok(validate(value));
});

test('only a measured same-account native forward uses a smaller model hold; every exit revokes its waypoint', async () => {
    function sample(state, shownUid) {
        const f = frame(2, 8000, 2536, state);
        f.ocr = [{text:'UID: '+shownUid, x:1702, y:1046}];
        return f;
    }
    for (const [state, shownUid, expected] of [['clear','693306810',[50]], ['clear','123456789',[800]], ['threat','693306810',[]]]) {
        const armed = [], veto = [];
        const model = {gpuAdviserUid:'693306810', setGpuAdviserWaypoint:w=>armed.push(w),
            gpuAdviserStopped:(_f,reason)=>veto.push(reason), gpuAdvisedForwardMs:()=>50};
        const {moves} = await run(sample(state,shownUid), now=>frame(3,now,2552,'clear'),model);
        assert.deepEqual(moves,expected);
        assert.deepEqual(armed,[target,null]);
        assert.equal(veto.length,state==='threat'?1:0);
    }
});

test('pipe and public frame sequences are separate; wrong identity, stale or replayed frames leave the native owner in control', () => {
    const fs = require('node:fs'), vm = require('node:vm');
    const filename = require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
    const decide = vm.runInNewContext(fs.readFileSync(filename,'utf8')+'\nactOneGpuSteeringDecision;');
    const identity = {session:'route-session',processId:11,windowsSessionId:3,gameProcessId:22};
    const c = {session:identity.session,frameId:9,observedAtUnixMs:1000,expectedUid:'693306810',
        objective:request.objective,waypoint:target,requestId:'live-request'};
    // engine.observe publishes the capture-start identity in hud, not on the top-level snapshot.
    const f = {session:c.session,frameId:9,hud:{captureStamp:{capturedAt:1000}}};
    const s = {...identity,protocolVersion:1,type:'steeringSuggestion',sourceEpoch:'d'.repeat(32),frameId:119,capturedAtUnixMs:1080,publishedAtUnixMs:1104,
        validUntilUnixMs:1330,context:c,steering:{forward:true,holdMs:50}};
    const decision = (sample=s, current=f, now=1120, consumed=0) => decide(sample,c,identity,current,now,800,consumed);
    assert.equal(decision(),50);
    assert.equal(decide(s,c,identity,f,1120,45,0),45);
    for (const key of ['session','processId','windowsSessionId','gameProcessId']) assert.equal(decision({...s,[key]:0}),'context_mismatch');
    for (const key of ['session','requestId','expectedUid','objective','frameId','observedAtUnixMs','waypoint'])
        assert.equal(decision({...s,context:{...c,[key]:null}}),'context_mismatch');
    assert.equal(decision(s,{...f,frameId:10}),'context_mismatch');
    assert.equal(decision(s,{...f,hud:{captureStamp:{capturedAt:999}}}),'context_mismatch');
    assert.equal(decision({...s,sourceEpoch:null}),'context_mismatch');
    assert.equal(decision(s,f,1330),'expired_or_replayed');
    assert.equal(decision(s,f,1120,119),'expired_or_replayed');
    assert.equal(decision({...s,capturedAtUnixMs:999}),'expired_or_replayed');
    assert.equal(decision({...s,validUntilUnixMs:99999}),'expired_or_replayed');
    assert.equal(decision({...s,steering:{forward:false,holdMs:50}}),'no_forward_agreement');
    assert.equal(decision({...s,steering:{forward:true,holdMs:500}}),'no_forward_agreement');
});

test('frame-pipe opt-in is polled once per second and opens only for the exact pilot', () => {
    const fs = require('node:fs'), vm = require('node:vm');
    const main = fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/main.js'),'utf8');
    const code = main.slice(main.indexOf('    var gpuAdviserIdentity='), main.indexOf('    function heartbeat('));
    let config=null, checks=0;
    const calls=[];
    const ctx={session:'rdp-run',runner:{},genshin:{betterGiProcessId:31,windowsSessionId:4},
        file:{isExists:()=>{checks++;return config!==null;},readTextSync:()=>JSON.stringify(config)},
        questFrames:{start:(...args)=>calls.push(args)}};
    vm.runInNewContext(code,ctx);ctx.openGpuAdviser(1000);ctx.openGpuAdviser(1100);
    assert.equal(checks,1);assert.equal(calls.length,0);
    config={version:1,session:'old',processId:31,windowsSessionId:4,gameProcessId:88,expectedUid:'693306810'};
    ctx.openGpuAdviser(2000);assert.equal(calls.length,0);
    config.session=ctx.session;ctx.openGpuAdviser(3000);ctx.openGpuAdviser(4000);
    assert.deepEqual(calls,[[ctx.session,31,4,88]]);assert.equal(checks,3);
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

test('a completed guild greeting does not block free exploration away from the counter', async () => {
    const initial = frame(2, 8000, 2564, 'clear');
    initial.hud.interact = true;
    initial.ocr.push({text: 'F', x: 1121, y: 534}, {text: 'Katheryne', x: 1220, y: 535});
    const {result, moves} = await run(initial, now => frame(3, now, 2552, 'clear'));
    assert.equal(result.status, 'arrived');
    assert.equal(moves.length, 1);
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
    waypoint = {map: 'Teyvat', x: -1329.832, y: 2564.187},
    landingStates = ['clear', 'clear'], landingChange = () => {}} = {}) {
    ground = structuredClone(ground); climb = structuredClone(climb);
    let now = ground.timestamp, observations = 0;
    const inputs = [];
    const route = {...request, session: ground.session, expectedFrameId: ground.frameId,
        createdAt: now, waypoints: [waypoint]};
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

const cityMount = require('./city-low-mount.fixture.json');
const cityWaypoint = {map: 'Teyvat', x: -834, y: 2188};

test('city frames 154–156 allow one in-run low-mount detach after stable 3649/4015 HP', async () => {
    const {ground,climb,parked}=cityMount;
    const eligible=(c,g=ground,at=g.timestamp)=>mission.reviewedClimbRelease(c,g,c.timestamp,6000,at);
    assert(eligible(climb));
    assert(!eligible(parked)); // the same ground frame cannot justify a second detach.
    assert(!mission.reviewedClimbRelease(climb,ground,climb.timestamp,6000)); // legacy path
    const {inputs,result}=await runRecordedClimb({ground,climb,waypoint:cityWaypoint});
    assert.deepEqual(inputs.map(i=>i[0]),['forward','release']);
    assert.equal(result.status,'stopped');assert.equal(result.groundRecovered,true);
    assert.deepEqual(result.recoveryFrames,[156,157]);assert.equal(result.nextWaypointIndex,0);
    for(const change of [g=>{g.hud.health.current--;},g=>{g.hud.health.current++;},
        g=>{g.map.x+=1;},g=>{g.mapPositionInherited=true;},g=>{g.hud.world=false;},
        g=>{g.hud.groundControls=false;},g=>{g.hud.enemyBarObservation.state='ambiguous';},
        g=>{g.session='elsewhere';},g=>{g.frameId--;},g=>{g.timestamp-=2010;
            g.hud.captureStamp.capturedAt-=2010;g.hud.enemyBarObservation.capturedAt-=2010;}]){
        const bad=structuredClone(ground);change(bad);assert(!eligible(climb,bad),String(change));
    }
    for(const change of [o=>{o.hud.health.current--;},o=>{o.ocr=o.ocr.filter(r=>r.text!=='Space');},
        o=>{o.ocr.find(r=>r.text==='X').y=800;},o=>{o.fastSample=true;},o=>{o.hud.enemyBars=[{}];}]){
        const bad=structuredClone(climb);change(bad);assert(!eligible(bad),String(change));
    }
    const lower=structuredClone(climb),earlier=structuredClone(ground);
    lower.hud.health.current=earlier.hud.health.current=3600;assert(!eligible(lower,earlier));
});

test('partial-HP city landing requires two new clear unchanged nearby ground captures', async () => {
    for (const change of [(o,i)=>{if(!i)o.hud.health.current++;},(o,i)=>{if(i)o.hud.health.current--;},
        o=>{o.map.x+=3;},(o,i)=>{if(i)o.mapPositionInherited=true;},
        (o,i)=>{if(i===0){o.frameId=cityMount.climb.frameId;
            o.hud.captureStamp.frameId=o.hud.enemyBarObservation.frameId=o.frameId;}}]){
        const {result,inputs}=await runRecordedClimb({...cityMount,waypoint:cityWaypoint,landingChange:change});
        assert.deepEqual(inputs.map(i=>i[0]),['forward','release']);
        assert.equal(result.groundRecovered,false);assert.equal(result.status,'stopped');
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

test('a hostile during inventory exit reports a protected zero-waypoint interruption',()=>{
    const fs=require('node:fs'),vm=require('node:vm'),context={};
    vm.createContext(context);
    vm.runInContext(fs.readFileSync('BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js','utf8'),context);
    const o={session:'s',frameId:15,hud:{enemyBars:[{width:37}],enemyBarObservation:{session:'s',frameId:15,state:'threat'}}};
    const entry=context.actOneExplorationEntryThreat(request,o);
    assert.equal(entry.reason,'Enemy observed during exploration');
    assert.equal(entry.nextWaypointIndex,0);
    assert.equal(entry.movements,0);
    o.hud.enemyBarObservation.frameId=14;
    assert.equal(context.actOneExplorationEntryThreat(request,o).reason,'Ground enemy scan did not establish clear ground');
    assert.equal(context.actOneExplorationEntryThreat({...request,requireMeasuredGround:false},o),null);
});

const katheryne = {map:'Teyvat',x:-913.51,y:2232.67};
const shortOfBooth = {map:'Teyvat',x:-913.171875,y:2234.4805}; // Last measured position in city-katheryne-01.
async function boothApproach({named=true,waypoints=[katheryne],start=shortOfBooth,change=()=>{}}={}) {
    let now=8000, frameId=2;
    const moves=[];
    const plan={...request,waypoints,...(named?{talkTo:'Katheryne',expectedUid:'693306810'}:{})};
    function readWorld(point) {
        const o=frame(frameId++,now,point.y,'clear');
        o.map={...point,cameraAngle:mission.bearing(point,katheryne)};
        o.ocr=[{text:'UID: 693306810',x:1680,y:1050}];
        return o;
    }
    const first=readWorld(start);change(first);
    const api={now:()=>now,checkStop(){},sleep:async ms=>{now+=ms;},
        runActTwoNavigationWithPause:(_inventory,_observe,walk)=>walk(first),
        forward:async ms=>{moves.push(ms);now+=ms;},
        rotate:()=>assert.fail('unexpected turn'),keyPress:()=>assert.fail('navigation attempted interaction')};
    const result=await mission.runNavigation(plan,{hud:{}},api,async()=>{
        assert.ok(moves.length===1,'extra movement after the close approach');
        return readWorld({...katheryne,y:katheryne.y+.54});
    });
    return {result,moves};
}
test('the 1.84-unit Katheryne shortfall still advances once, with a bounded final hold',async()=>{
    const {result,moves}=await boothApproach();
    assert.equal(result.status,'arrived');assert.equal(result.nextWaypointIndex,1);
    assert.equal(moves.length,1);assert.ok(moves[0]>=175&&moves[0]<=190);
    for(const setup of [{start:{...katheryne,y:katheryne.y+.74}},{named:false},{waypoints:[katheryne,shortOfBooth]}]){
        const arrival=await boothApproach(setup);
        assert.equal(arrival.result.status,'arrived');assert.deepEqual(arrival.moves,[]);
    }
});
test('only the exact selected name ends the final approach early; navigation never presses F',async()=>{
    function prompt(o,name,dy=0){
        o.hud.interact=true;
        o.ocr.push({text:'F',x:1110,y:505,height:30},{text:name,x:1270,y:505+dy,height:30});
    }
    const aligned=await boothApproach({change:o=>prompt(o,'Katheryne')});
    assert.equal(aligned.result.status,'arrived');assert.deepEqual(aligned.moves,[]);
    for(const change of [o=>prompt(o,'Cyrus'),o=>prompt(o,'Katheryne',51)]){
        const {moves}=await boothApproach({change});assert.equal(moves.length,1);
    }
    for(const change of [o=>{prompt(o,'Katheryne');o.ocr[0].text='UID: 123456789';},
        o=>{prompt(o,'Katheryne');o.hud.enemyBarObservation.state='threat';}]){
        const {result,moves}=await boothApproach({change});assert.equal(result.status,'stopped');assert.deepEqual(moves,[]);
    }
});
test('named navigation requires an exact NPC and UID, and ordinary navigation keeps its existing schema',()=>{
    const validate=r=>engine.validate(r,request.session,request.expectedFrameId,{},request.createdAt);
    const named={...request,talkTo:'Katheryne',expectedUid:'693306810'};
    assert.equal(validate(named),null);assert.equal(validate(request),null);
    for(const change of [{expectedUid:null},{talkTo:' '},{mission:'observe'}])assert.ok(validate({...named,...change}));
});
