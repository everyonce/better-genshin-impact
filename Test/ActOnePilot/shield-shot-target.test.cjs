const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const policy=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/shield-response.js');
const source=fs.readFileSync(process.env.BGI_MODULE||'BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js','utf8');
const body=source.slice(source.indexOf('shieldFireDecision:function'),source.indexOf('shieldDecision:function'));
const api=vm.runInNewContext('({'+body+'})',{shieldPolicy:policy,genshin:{isGameForeground:true,isRemoteDesktopSession:true},request:{session:'s'},g:{aim:()=>true},Date:{now:()=>1000}});
function frame(x=945){return {session:'s',frameId:12,timestamp:950,hud:{health:{current:1733,max:1733}},shieldVision:{wood:[{x,y:510,width:33,height:61,confidenceLowerBound:.9}]}};}
test('actual adapter only authorizes charged Pyro when current reticle is inside tracked wooden shield',()=>{
 const before=frame(),o=frame();assert.equal(api.shieldFireDecision(before,o,{}).action,'apply-element');
 assert.equal(api.shieldFireDecision(before,frame(961),{}).action,'retreat');
 o.shieldVision.wood=[];assert.equal(api.shieldFireDecision(before,o,{}).action,'retreat');
});
test('actual adapter refuses stale target, target jumps and actual recorded health loss',()=>{
 const before=frame();for(const change of [o=>o.timestamp=100,o=>o.shieldVision.wood[0].x=700,o=>o.hud.health.current=1453]){const o=frame();change(o);assert.equal(api.shieldFireDecision(before,o,{}).action,'retreat');}
});
test('phase aim witness requires reviewed source frame and live recognition',()=>{
 const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-shield-pyro.js');
 const p={reviewed:true,session:'s',frameId:100,createdAt:1000,mode:'fire',vision:true,woodenShieldReviewed:true,aimWitnessFrameId:260000099,aimWitnessSourceFrameId:90,offset:{dx:0,dy:0}};
 assert(g.plan(p,{session:'s',expectedFrameId:100},1000));
 assert(!g.plan({...p,aimWitnessSourceFrameId:100},{session:'s',expectedFrameId:100},1000));
 assert(!g.plan({...p,vision:false},{session:'s',expectedFrameId:100},1000));
});
const burstBody=source.slice(source.indexOf('shieldDecision:function'),source.indexOf('key:async function(k,ms,o)',source.indexOf('shieldDecision:function')));
const burstApi=vm.runInNewContext('({'+burstBody+'})',{shieldPolicy:policy,genshin:{isGameForeground:true,isRemoteDesktopSession:true},request:{session:'s'},g:{ground:()=>true},Date:{now:()=>1000}});
test('ready Q cannot be authorized before a safe cast validates the primitive',()=>{const o=frame(800);o.shieldVision.wood[0].height=160;o.shieldVision.amberBurstReady=true;assert.equal(burstApi.shieldDecision(o,o,{rangeAndFacingReviewed:true}).action,'retreat');});
