const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const script = fs.readFileSync(path.join(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'), 'utf8');
const session = 'test-field';
const id = 'mission-' + '9'.repeat(32);
const uid = { text: 'UID: 693306810', x: 1710, y: 1050 };
function rect(x, y, width, height, area) { return {x, y, width, height, area}; }

// OpenCvSharp external contours from the warning-color mask in 57x49 field captures.
const cases = [
    {frame:25, c:{x:1391.5,y:513.5,width:42,height:8}, shapes:[rect(7,20,42,8,280.5)], side:null},
    {frame:33, c:{x:1431.5,y:659.5,width:15,height:11}, shapes:[rect(20,19,15,9,64.5),rect(22,10,27,27,168)], side:'right'},
    {frame:34, c:{x:1440.5,y:637,width:15,height:10}, shapes:[rect(20,19,15,10,67),rect(23,11,27,27,169.5)], side:'right'},
    {frame:76, c:{x:1451,y:428.5,width:14,height:9}, shapes:[rect(21,19,14,9,58.5),rect(25,10,26,27,153)], side:'right'},
    {frame:35, c:{x:1767,y:479.5,width:16,height:3}, shapes:[rect(20,22,16,3,24)], side:null},
];
test('sunlit camp and shadow warning pixels both pass the native mask', () => {
    const ctx=vm.createContext({});
    vm.runInContext(script,ctx);
    class Scalar extends Array {}
    function matches(pixel) {
        const mat={inRange:(low,high)=>pixel.every((v,i)=>low[i]<=v && v<=high[i])};
        return ctx.actOneWarningPinkMask(mat,{Scalar});
    }
    // BGR samples from the red warning ring in the saved camp/courtyard captures.
    assert.equal(matches([104,103,255]),true);
    assert.equal(matches([99,88,255]),true);
    assert.equal(matches([94,158,126]),false);
    assert.equal(matches([20,18,235]),false);
});
function mirror(value) {
    return {...value, c:{...value.c,x:1920-value.c.x},shapes:value.shapes.map(s=>({...s,x:57-s.x-s.width}))};
}
test('single warning-ring chevron and separate diamond select only the indicated side', () => {
    const ctx = vm.createContext({});
    vm.runInContext(script,ctx);
    for (const sample of cases) assert.equal(ctx.actOneWarningArrow(sample.c,sample.shapes)?.side ?? null,sample.side);
    const left=mirror(cases[1]);
    assert.equal(ctx.actOneWarningArrow(left.c,left.shapes).side,'left');
    assert.equal(ctx.actOneWarningArrow(cases[1].c,left.shapes),null);
    assert.equal(ctx.actOneWarningArrow(cases[1].c,[...cases[1].shapes,rect(3,3,10,10,70)]),null);
    assert.equal(ctx.actOneWarningArrow({...cases[1].c,x:1250},cases[1].shapes),null);
});

function harness(left=false) {
    const now=10000, files={}, moves=[], captures=[];
    const ctx=vm.createContext({
        Date: {now:()=>now},
        genshin:{isRemoteDesktopSession:true, windowsSessionId:7,isGameForeground:true},
        file:{isExists:p=>Object.hasOwn(files,p),readTextSync:p=>files[p]??'',writeTextSync:(p,v)=>{files[p]=v;return true;}},
        moveMouseBy:(x,y)=>moves.push([x,y]), sleep:async ms=>{assert.ok(ms>=60);},
    });
    vm.runInContext(script,ctx);
    const request={mission:'questStep',step:'actTwoFaceRemainingEnemy',session,id:'new-request',
        expectedFrameId:33,combatRequestId:id,rewardFrameId:20,createdAt:9700};
    const frame=(n,sample) => {
        sample=left?mirror(sample):sample;
        const timestamp=n===33?9500:9850;
        const stamp={frameId:n,session,capturedAt:timestamp-300};
        return {session,frameId:n,timestamp,map:{map:'Teyvat',x:12,y:40},ocr:[uid],
            hud:{world:true,groundControls:true,health:{current:3888,max:4015},objectives:[],enemyBars:[],
                captureStamp:{...stamp,source:'game-capture-start'},
                enemyBarObservation:{...stamp,version:1,kind:'normal-ground-enemy-observation-v1',
                    state:'ambiguous',reason:'unanchored_bar_shaped_components',candidateCount:1,acceptedCount:0},
                enemyBarDiagnostic:{fieldCandidates:[sample.c]},
                hostileDirectionArrow:ctx.actOneWarningArrow(sample.c,sample.shapes)}};
    };
    const source=frame(33,cases[1]), fresh=frame(34,cases[2]);
    const before={frameId:18,session,timestamp:1000,ocr:[uid],hud:{world:true,enemyBars:[{x:880}]}};
    const award={frameId:20,session,timestamp:5200,ocr:[uid,{text:'Character EXP  10',x:160,y:485}],
        hud:{world:true,captureStamp:{source:'game-capture-start',capturedAt:4800,frameId:20,session}}};
    const receipt={id,session,mission:'questStep',status:'stopped',frameId:28,timestamp:7800,details:{
        inputEvents:[{type:'actTwoNativeCombat',actionId:id+':rotation:0',frameId:18,startedAt:1300,finishedAt:3110}],
        result:{nativeGroup:false,nativeReturned:true,pauseVerified:true,
            chunks:[{actionId:id+':rotation:0',nativeReturned:true,beforeFrameId:18,afterFrameId:19}],
            pauseProof:{verified:true,kind:'inventory',session,sourceFrameId:25,pauseFrameId:27}}}};
    async function run() {
        for(const o of [source,before,award])
            files['observations/'+session+'/frame-'+String(o.frameId).padStart(4,'0')+'.json']=JSON.stringify(o);
        files['receipts/'+session+'/'+id+'.json']=JSON.stringify(receipt);
        const api=ctx.createActOneAdapter(7);
        api.beginMission(request);
        return api.faceRemainingEnemy(fresh,async()=>{captures.push(35);return {frameId:35};});
    }
    return {moves,captures,source,fresh,before,award,receipt,run};
}

test('two fresh matching observations and an earned reward admit one camera-only turn, including after adapter refresh', async()=>{
    for(const left of [false,true]){
        const h=harness(left);
        assert.equal((await h.run()).turnSent,true);
        assert.equal((await h.run()).turnSent,false);
        assert.deepEqual(h.moves,[[left?-200:200,0]]);
        assert.deepEqual(h.captures,[35]);
    }
});

test('stale or mismatched observations and unconfirmed awards grant zero input',async()=>{
    for(const change of [
        h=>{delete h.fresh.hud.hostileDirectionArrow;}, h=>{h.source.hud.hostileDirectionArrow.side='left';},
        h=>{h.fresh.hud.enemyBarObservation.candidateCount=2;}, h=>{h.fresh.hud.enemyBars=[{x:500}];},
        h=>{h.fresh.hud.health.current=1200;}, h=>{h.fresh.frameId++;},
        h=>{h.fresh.timestamp=10001;}, h=>{h.source.timestamp=2000;},
        h=>{h.fresh.ocr=[];}, h=>{h.receipt.session='another';}, h=>{h.award.ocr=[uid];},
        h=>{h.before.ocr.push(h.award.ocr[1]);}, h=>{h.receipt.details.inputEvents[0].finishedAt=5100;},
        h=>{h.receipt.timestamp=-40000;}, h=>{h.receipt.details.result.nativeReturned=false;}
    ]){
        const h=harness();change(h);
        assert.equal((await h.run()).turnSent,false,String(change));
        assert.deepEqual(h.moves,[]);assert.deepEqual(h.captures,[]);
    }
});
