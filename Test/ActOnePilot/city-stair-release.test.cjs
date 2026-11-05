const test = require('node:test');
const assert = require('node:assert/strict');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

function climb() {
    return {session:'city',frameId:163,timestamp:1000,map:{map:'Teyvat',x:-836.08,y:2198.67},
        hud:{world:true,groundControls:false,climbing:true,enemyBars:[],health:{current:3649,max:4015}},
        ocr:[{text:'UID: 693306810',x:1680,y:1048},{text:'X',x:1594,y:1022},{text:'Space',x:1680,y:1024}]};
}

function run(entry, scene, template=true) {
    let clock=1000, frame=163;
    const calls=[];
    const api={now:()=>clock, sleep:async ms=>{clock+=ms;}, releaseCityStair:async(o,check)=>{
        assert.equal(o,entry);check();
        if(!template)throw Error('Stair tread template missing');
        calls.push('X');
    }};
    return {calls,result:mission.runQuestStep('cityStairRelease',entry,api,async()=>{
        return {...scene,frameId:++frame,timestamp:clock};
    })};
}

test('a single release requires two distinct local grounded frames',async()=>{
    const input=climb(),ground={...input,hud:{...input.hud,climbing:false,groundControls:true}};
    const run1=run(input,ground);
    assert.deepEqual((await run1.result).groundedFrames,[164,165]);
    assert.deepEqual(run1.calls,['X']);
    for(const terminal of [input,{...ground,map:{...ground.map,x:-830}},
            {...ground,hud:{...ground.hud,health:{current:3500,max:4015}}}]) {
        const testCase=run(input,terminal);
        assert.equal((await testCase.result).status,'stopped');
        assert.deepEqual(testCase.calls,['X']);
    }
});

test('stale, misplaced, contradictory, or visually unsupported sources consume no key',async()=>{
    const sample=climb();
    for(const changed of [{timestamp:-1},{map:{...sample.map,y:2210}},{ocr:sample.ocr.slice(0,2)},
            {ocr:[...sample.ocr,{text:'UID: 123456789',x:1690,y:1055}]},
            {hud:{...sample.hud,choice:true}},{hud:{...sample.hud,enemyBars:[{}]}}]) {
        const a=run({...sample,...changed},sample);
        await assert.rejects(a.result);assert.deepEqual(a.calls,[]);
    }
    const reject=run(sample,sample,false);
    await assert.rejects(reject.result);assert.deepEqual(reject.calls,[]);
});
