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
