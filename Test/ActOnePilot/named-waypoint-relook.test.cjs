const test=require('node:test'), assert=require('node:assert/strict');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const engine=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/engine.js');
const request={id:'mission-'+ 'c'.repeat(32),session:'street',mission:'questStep',step:'namedWaypointRelook',
    expectedFrameId:57,createdAt:1000,talkTo:'Katheryne',expectedUid:'693306810',waypoints:[{map:'Teyvat',x:-913.51,y:2232.67}]};
function frame(id,time,angle,state='ambiguous') {
    const stamp={session:'street',frameId:id,capturedAt:time};
    return {session:'street',frameId:id,timestamp:time,map:{map:'Teyvat',x:-908.1582,y:2242.0254,cameraAngle:angle},
        ocr:[{text:'UID: 693306810',x:1700,y:1050}],hud:{world:true,groundControls:true,enemyBars:[],
            health:{current:3809,max:4015},captureStamp:{...stamp,source:'game-capture-start'},enemyBarObservation:{...stamp,
                kind:'normal-ground-enemy-observation-v1',version:1,state,reason:'unanchored_bar_shaped_components',
                acceptedCount:0,candidateCount:state==='clear'?0:1}}};
}
function run(source,after,req=request) {
    let t=1000;
    const inputs=[];
    const api={now:()=>t,rotate:async(dx,guard)=>{guard();inputs.push(dx);},sleep:async(ms)=>{t+=ms;}};
    return {inputs,result:mission.runQuestStep(req.step,source,api,async()=>after,req)};
}
test('the recorded street pose turns once toward the named booth and verifies a new measured view',async()=>{
    const p=run(frame(58,1000,27),frame(59,1180,59,'clear'));
    const result=await p.result;
    assert.equal(result.measuredClear,true);assert.equal(result.waypoint,request.waypoints[0]);
    assert.equal(p.inputs.length,1);assert(p.inputs[0]>250&&p.inputs[0]<280);
    for(const after of [frame(59,1180,27,'clear'),frame(59,1180,59),frame(59,1180,59,'threat'),
            frame(58,1000,59,'clear')]){
        const a=run(frame(58,1000,27),after);
        assert.equal((await a.result).measuredClear,false);assert.equal(a.inputs.length,1);
    }
});
test('only the fresh ambiguous original field may turn; aligned cameras hold',async()=>{
    for(const change of [s=>s.hud.enemyBarObservation.state='threat',s=>s.hud.enemyBarObservation.acceptedCount=1,
            s=>s.hud.choice=true,s=>s.hud.world=false,s=>s.hud.hostileDirectionArrow={side:'right'},
            s=>s.ocr=[],s=>s.hud.captureStamp.frameId=1,s=>s.hud.health.current=100,s=>s.map.cameraAngle=NaN]){
        const s=frame(58,1000,27);change(s);const a=run(s,null);
        await assert.rejects(a.result);assert.deepEqual(a.inputs,[]);
    }
    const a=run(frame(58,1000,59),null);assert.equal((await a.result).turnSent,false);assert.deepEqual(a.inputs,[]);
});
test('native request validation joins one finite Teyvat target, named NPC and expected UID',()=>{
    const check=r=>engine.validate(r,'street',57,{},1000);
    assert.equal(check(request),null);
    for(const change of [{waypoints:[]},{waypoints:[...request.waypoints,...request.waypoints]},{waypoints:[{x:Infinity,y:0,map:'Teyvat'}]},
            {waypoints:[{...request.waypoints[0],attack:true}]},{talkTo:''},{expectedUid:'wrong'},{step:'worldInventory'}])
        assert(check({...request,...change}));
});

const temple={map:'Teyvat',x:-1390.082,y:1647.763};
const grid={...request,step:'explorationWaypointRelook',objective:'Explore for Adventure Rank',waypoints:[temple],deadlineMs:5000};
delete grid.talkTo;
function gridFrame(id,time,angle,state='ambiguous'){
    const o=frame(id,time,angle,state);
    o.map={map:'Teyvat',x:-1427.4238,y:1661.8262,cameraAngle:angle};
    o.hud.objectives=[];o.hud.enemyBarDiagnostic={fieldCandidates:[{x:945.5,y:277,width:11,height:6,rectangularity:.16}]};
    if(state==='threat'){o.hud.enemyBars=[{x:900,y:400,width:65,height:5}];
        Object.assign(o.hud.enemyBarObservation,{acceptedCount:1,candidateCount:1,reason:'outdoor_bar_candidates'});}
    return o;
}
function gridRun(before,stationary,after,req=grid){
    let t=before.timestamp,updates=[stationary,after],inputs=[];
    const api={now:()=>t,rotate:async(dx,guard)=>{guard();inputs.push(dx);},sleep:async ms=>{t+=ms;}};
    return {inputs,result:mission.runQuestStep(req.step,before,api,async()=>{
        const next=updates.shift();t=Math.max(t,next.timestamp);return next;},req)};
}
test('Temple waypoint behind stationary character admits one bounded camera turn and can reveal a hostile',async()=>{
    for(const state of ['clear','threat','ambiguous']){
        const x=gridRun(gridFrame(58,1000,18.5),gridFrame(59,1150,18.5),gridFrame(60,1400,112,state));
        const r=await x.result;assert.deepEqual(x.inputs,[750]);assert.equal(r.viewChanged,true);
        assert.equal(r.measuredClear,state==='clear');assert.equal(r.postScan,state);
        assert.equal(r.sourceFrameId,59);assert.equal(r.frameId,60);
    }
    const x=gridRun(gridFrame(58,1000,18.5),gridFrame(59,1150,18.5),gridFrame(60,1400,18.5,'clear'));
    assert.equal((await x.result).viewChanged,false);assert.deepEqual(x.inputs,[750]);
});
test('grid look refuses drifting, damaged, threatened or unmeasured source pairs and incomplete ownership',async()=>{
    for(const change of [
        o=>o.map.x+=1.7,o=>o.map.cameraAngle+=5,o=>o.hud.health.current-=20,o=>o.ocr=[],
        o=>o.hud.enemyBarDiagnostic.fieldCandidates=[],o=>o.hud.hostileDirectionArrow={side:'right'},
        o=>o.hud.enemyBarDiagnostic.fieldCandidates[0]={x:1451,y:428.5,width:14,height:9,rectangularity:.57},
        o=>o.hud.enemyBarDiagnostic.fieldCandidates[0]={x:1250,y:445,width:43,height:8,rectangularity:.75},
        o=>o.hud.interact=true,o=>o.hud.objectives=['Defeat all opponents'],o=>o.hud.health.current=2000]){
        const next=gridFrame(59,1150,18.5);change(next);
        const x=gridRun(gridFrame(58,1000,18.5),next,null);await assert.rejects(x.result);assert.deepEqual(x.inputs,[]);
    }
    const expired=gridRun(gridFrame(58,1000,18.5),gridFrame(59,1850,18.5),null,{...grid,deadlineMs:1000});
    await assert.rejects(expired.result);assert.deepEqual(expired.inputs,[]);
    const check=r=>engine.validate(r,'street',57,{},1000);assert.equal(check(grid),null);
    for(const patch of [{talkTo:'Bob'},{deadlineMs:5001},{objective:'Something else'},{expectedUid:''},{waypoints:[]},
        {waypoints:[temple,temple]},{waypoints:[{...temple,map:'Elsewhere'}]}])assert(check({...grid,...patch}));
});
