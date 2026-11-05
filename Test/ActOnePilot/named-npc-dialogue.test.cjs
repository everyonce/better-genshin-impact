const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const engine = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/engine.js');
const prompt = require('./act-two-amber-prompt-9052.fixture.json');
const greeting = require('./act-two-amber-final-11121.fixture.json');

const uid = '693306810';
const session = 'arrival-amber';
function replay(frames, name = 'Amber', budget = 6000) {
    let now = 1000, count = 0;
    const keys = [];
    const request = {id:'talk-test', mission:'dialogue', session, expectedFrameId:0, createdAt:now,
        talkTo:name, expectedUid:uid, deadlineMs:budget};
    const api = {now:()=>now, checkStop(){}, sleep:async ms=>{ now += ms; },
        keyPress:async (key, source)=>keys.push([key, source && source.frameId]), chooseChoice:async()=>assert.fail('unexpected choice')};
    async function observe() {
        const frame = structuredClone(frames[Math.min(count, frames.length - 1)]);
        frame.frameId = ++count; frame.session = session; frame.timestamp = now;
        // These archived images predate per-frame ground scans. Reproduce the current scanner's envelope.
        if (frame.hud.world) {
            const count = frame.hud.enemyBars.length;
            const stamp = {session,frameId:frame.frameId,capturedAt:now};
            frame.hud.captureStamp = {...stamp,source:'game-capture-start'};
            frame.hud.enemyBarObservation = {...stamp,version:1,kind:'normal-ground-enemy-observation-v1',
                state:count?'threat':'clear',candidateCount:count,acceptedCount:count};
        }
        return frame;
    }
    return mission.runDialogue(api,observe,request).then(result=>({result,keys}));
}

test('a recorded selected Amber prompt and a recorded Amber greeting lead back to the world',async()=>{
    const {result,keys} = await replay([prompt, prompt, greeting, prompt]);
    assert.deepEqual(keys.map(call=>call[0]), ['VK_F','VK_SPACE']);
    assert.equal(keys[0][1], 1);
    assert.deepEqual([result.status,result.talkTo,result.interactionFrameId,result.greetingFrameId,result.worldFrameId],
        ['completed','Amber',1,3,4]);
});

test('recorded Amber frames 9051 and 9052 let the F prompt settle without extra input',async()=>{
    const early = require('./act-two-amber-prompt-9051.fixture.json');
    const {result,keys} = await replay([early,prompt,greeting,prompt]);
    assert.equal(result.reason,'world_returned');
    assert.deepEqual(keys[0],['VK_F',2]);
    assert.deepEqual(keys.map(call=>call[0]),['VK_F','VK_SPACE']);
});

test('an automatic conversation at the waypoint uses the same speaker and never sends F',async()=>{
    const {result,keys} = await replay([greeting,prompt]);
    assert.deepEqual(keys.map(call=>call[0]), ['VK_SPACE']);
    assert.equal(result.interactionFrameId, null);
    assert.equal(result.reason, 'world_returned');
});

test('wrong selected name, adjacent prompt or measured enemy produces no input',async()=>{
    const offset = structuredClone(prompt);
    offset.ocr.find(row=>row.text==='F' && row.x>1080).y -= 52;
    const enemy = structuredClone(prompt);
    enemy.hud.enemyBars = [{x:800,y:400,width:40}];
    for (const [field,name] of [[prompt,'Cyrus'],[offset,'Amber'],[enemy,'Amber']]) {
        const {result,keys} = await replay([field],name);
        assert.equal(result.status,'stopped');
        assert.deepEqual(keys,[]);
    }
});

test('a missed interaction, a different speaker or a changed account cannot count as a conversation',async()=>{
    const other = structuredClone(greeting);
    other.ocr.find(row=>row.text==='Amber').text = 'Cyrus';
    const foreign = structuredClone(greeting);
    foreign.ocr.find(row=>row.text.startsWith('UID')).text = 'UID: 123456789';
    for (const next of [prompt,other,foreign]) {
        const {result,keys} = await replay([prompt,next]);
        assert.equal(result.status,'stopped');
        assert.deepEqual(keys.map(call=>call[0]),['VK_F']);
        assert.equal(result.worldFrameId,undefined);
    }
});

test('a tutorial reached during a named conversation does not start the tutorial or claim a world return',async()=>{
    const tutorial = structuredClone(greeting);
    tutorial.hud.tutorialStep = 'glideOpen';
    const {result,keys} = await replay([prompt,greeting,tutorial,prompt]);
    assert.equal(result.status,'stopped');
    assert.deepEqual(keys.map(call=>call[0]),['VK_F','VK_SPACE']);
});

test('legacy dialogue and bounded named dialogue validate independently',()=>{
    const base={id:'dialogue-test',session,expectedFrameId:1,createdAt:1000,mission:'dialogue'};
    const named={...base,talkTo:'Amber',expectedUid:uid,deadlineMs:5000};
    const verify=request=>engine.validate(request,session,1,{},1000);
    assert.equal(verify(base),null);
    assert.equal(verify(named),null);
    for (const rejected of [{...named,deadlineMs:60001},{...named,expectedUid:''},{...named,talkTo:'   '},
        {...base,deadlineMs:5000},{...named,mission:'observe'}]) assert.notEqual(verify(rejected),null);
});

test('native guild quest routing and its launcher share the same inventory entry predicate',()=>{
    const base={objective:"Go to the Adventurers' Guild and listen to their report",
        waypoints:[{map:'Teyvat',x:-834,y:2188}]};
    assert.equal(mission.guildNavigationFromInventory(base),true);
    assert.equal(mission.guildNavigationFromInventory({...base,objective:'Go to Mondstadt'}),false);
    const amber={objective:'Talk to Amber',waypoints:[{map:'Teyvat',x:-1309.119,y:1722.077}]};
    assert.equal(mission.guildNavigationFromInventory(amber),true);
    assert.equal(mission.guildNavigationFromInventory({...amber,waypoints:[{map:'Teyvat',x:0,y:0}]}),false);
});
