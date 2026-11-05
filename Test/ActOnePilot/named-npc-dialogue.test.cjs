const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const engine = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/engine.js');
const prompt = require('./act-two-amber-prompt-9052.fixture.json');
const greeting = require('./act-two-amber-final-11121.fixture.json');

const uid = '693306810';
const session = 'arrival-amber';
function replay(frames, name = 'Amber', budget = 6000, fields = {}) {
    let now = 1000, count = 0;
    const keys = [];
    const request = {id:'talk-test', mission:'dialogue', session, expectedFrameId:0, createdAt:now,
        talkTo:name, expectedUid:uid, deadlineMs:budget, ...fields};
    const api = {now:()=>now, checkStop(){}, sleep:async ms=>{ now += ms; },
        keyPress:async (key, source)=>keys.push([key, source && source.frameId]), chooseChoice:async label=>keys.push(['choice', label])};
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

// Use real English dialogue HUD geometry; the service rows represent the shipped guild interaction.
function guildMenu(labels, choice=true, speaker='Katheryne') {
    const scene=structuredClone(greeting);
    scene.hud.choice=choice;scene.hud.dialogueReady=!choice;
    scene.ocr=scene.ocr.filter(row=>!(row.x>1000 && row.x<1800 && row.y>430 && row.y<820));
    scene.ocr.find(row=>row.text==='Amber' && row.y>=820 && row.y<900).text=speaker;
    labels.forEach((text,i)=>scene.ocr.push({text,x:1280,y:475+55*i,width:250,height:36}));
    return scene;
}
test('Katheryne chooses the exact farewell after Daily and Expedition and waits through a slow closing menu',async()=>{
    const menu=guildMenu(['Claim Daily Commission Rewards','Dispatch Character on Expedition','Goodbye.']);
    const {result,keys}=await replay([menu,menu,prompt],'Katheryne');
    assert.equal(result.status,'completed');assert.deepEqual(result.farewell,{label:'Goodbye.',frameId:1});
    assert.deepEqual([result.greetingFrameId,result.worldFrameId],[1,3]);
    assert.deepEqual(keys,[['choice','Goodbye.']]);
});
test('named arrival records a greeting and leaves unknown, ambiguous and unconfirmed menus untouched',async()=>{
    const greetingOnly=guildMenu([],false);
    for(const menu of [guildMenu(['Daily Commission Rewards','Expeditions']),
                       guildMenu(['Bye.','Farewell!']),guildMenu(['Goodbye for now, tell me more']),
                       guildMenu(['Bye.'],false),guildMenu(['Goodbye.'],true,'Amber')]){
        const {result,keys}=await replay([greetingOnly,menu],'Katheryne');
        assert.equal(result.status,'stopped');assert.equal(result.reason,'named_dialogue_no_farewell');
        assert.deepEqual([result.greetingFrameId,result.menuFrameId],[1,2]);
        assert.deepEqual(keys.map(row=>row[0]),['VK_SPACE']);
    }
});

const guildKeyboard=require('./katheryne-keyboard-menu-35.fixture.json');
function highlighted(index){
    const scene=structuredClone(guildKeyboard);
    scene.ocr.find(r=>r.text==='F').y=[639,711,782][index];
    return scene;
}
test('recorded Auto-off frame 35 clicks only the confirmed Goodbye row and verifies the world',async()=>{
    const {result,keys}=await replay([guildKeyboard,guildKeyboard,prompt],'Katheryne',8000,{resumeMenuOnly:true});
    assert.deepEqual(keys,[['choice','Goodbye.']]);assert.equal(result.status,'completed');
    assert.deepEqual([result.interactionFrameId,result.greetingFrameId,result.farewell.frameId,result.worldFrameId],[null,1,2,3]);
});
test('a persistent keyboard guide moves the highlight one observed step at a time before F',async()=>{
    const scenes=[0,0,0,0,1,1,2,2].map(highlighted);
    const {result,keys}=await replay([...scenes,prompt],'Katheryne',10000,{resumeMenuOnly:true});
    assert.equal(result.status,'completed');assert.deepEqual(keys,[['choice','Goodbye.'],['VK_S',4],['VK_S',6],['VK_F',8]]);
    assert.equal(result.farewell.confirmFrameId,8);
});
test('a stuck reward highlight, changed speaker, missing marker, and an already closed menu cannot confirm',async()=>{
    const {result,keys}=await replay(Array(9).fill(guildKeyboard),'Katheryne',10000,{resumeMenuOnly:true});
    assert.equal(result.reason,'named_menu_highlight_did_not_advance');
    assert.deepEqual(keys,[['choice','Goodbye.'],['VK_S',4]]);
    for(const change of [f=>f.ocr.find(r=>r.text==='Katheryne').text='Cyrus',
        f=>f.ocr.find(r=>r.text==='F').y=590,f=>f.ocr.find(r=>r.text==='Goodbye.').text='Claim Rewards',
        f=>f.ocr.push({...f.ocr.find(r=>r.text==='F')})]){
        const altered=structuredClone(guildKeyboard);change(altered);
        const {result,keys}=await replay([guildKeyboard,altered],'Katheryne',8000,{resumeMenuOnly:true});
        assert.equal(result.status,'stopped');assert.deepEqual(keys,[]);
    }
    const closed=await replay([prompt],'Katheryne',8000,{resumeMenuOnly:true});
    assert.deepEqual(closed.keys,[]);assert.equal(closed.result.status,'stopped');
});
test('the native Auto-off text click uses the exact last frame and never clicks its selected reward',()=>{
    const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
    const dir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
    const source=fs.readFileSync(path.join(dir,'bgi.js'),'utf8');
    const member=source.slice(source.indexOf('        chooseChoice: function'),source.indexOf('        rotate: function',source.indexOf('        chooseChoice: function'))).trim().replace(/,$/,'');
    const frame=structuredClone(guildKeyboard),clicks=[];
    const runtime={checkStop(){},lastObservation:frame,Date:{now:()=>frame.timestamp},request:{mission:'dialogue',session:frame.session,talkTo:'Katheryne',expectedUid:uid},
        file:{readTextSync:n=>fs.readFileSync(path.join(dir,n),'utf8')},events:[],click:(x,y)=>clicks.push([x,y])};
    const adapter=vm.runInNewContext('({'+member+'})',runtime);
    assert.throws(()=>adapter.chooseChoice('Claim Adventure Rank Rewards',frame));assert.throws(()=>adapter.chooseChoice('Goodbye.',{...frame,frameId:34}));
    adapter.chooseChoice('Goodbye.',frame);assert.deepEqual(clicks,[[1389,802]]);
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
