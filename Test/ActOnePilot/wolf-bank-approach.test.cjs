const test=require('node:test');
const assert=require('node:assert/strict');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
function state() {
 const now=10000,request={mission:'questStep',step:'wolfForwardFine',session:'s1',expectedFrameId:10};
 const permit={kind:'wolfBankApproach',session:'s1',frameId:10,witnessFrameId:9,createdAt:9900,health:{current:100,max:1427}};
 const o={session:'s1',frameId:11,timestamp:9900,map:null,ocr:[{text:'Kaeya',x:1660,y:490},{text:'Trial',x:1800,y:465}],
 hud:{world:false,groundControls:true,climbing:false,journal:false,bigMap:false,dialogueReady:false,choice:false,tutorialStep:null,
 interact:false,enemyBars:[],enemyBarDiagnostic:{level:5,candidates:0,localReads:[]},health:{current:100,max:1427},
 wolfSpikeSurface:{metrics:{floorLeftStone:0.975,floorRightStone:0.955,frontLeftStone:0.754,frontRightStone:0.977}}}};
 return {o,request,permit,now};
}
test('one-use bank witness permits a fine approach with unchanged revived Kaeya on positive stone',()=>{
 const s=state();assert.equal(bgi.wolfBankApproachReady(s.o,s.request,s.permit,s.now),true);
 s.o.hud.wolfSpikeSurface.metrics.frontLeftStone=0.1;assert.equal(bgi.wolfBankApproachReady(s.o,s.request,s.permit,s.now),true);
 s.o.hud.health.current=99;assert.equal(bgi.wolfBankApproachReady(s.o,s.request,s.permit,s.now),false);
});
test('bank witness cannot authorize stale, foreign, consumed, broader, or ambiguous ground input',()=>{
 const mutations=[s=>s.request.step='wolfForward',s=>s.request.mission='recover',s=>s.permit.usedAt=9950,
 s=>s.permit.session='other',s=>s.o.session='other',s=>s.permit.frameId=9,s=>s.permit.witnessFrameId=11,
 s=>s.permit.createdAt=-120001,s=>s.permit.createdAt=10001,s=>s.o.timestamp=8999,s=>s.o.frameId=9,
 s=>s.o.hud.groundControls=false,s=>s.o.hud.loading=true,s=>s.o.hud.interact=true,
 s=>s.o.hud.enemyBars=[{}],s=>s.o.hud.enemyBarDiagnostic.candidates=1,s=>s.o.hud.health.current=0,
 s=>s.o.hud.health.max=1055,s=>s.o.ocr=[],s=>s.o.hud.wolfSpikeSurface.metrics.floorLeftStone=0.64,
 s=>s.o.hud.wolfSpikeSurface.metrics.floorRightStone=0.64,s=>s.o.hud.wolfSpikeSurface.metrics.floorLeftStone=NaN];
 for(const mutate of mutations){const s=state();mutate(s);assert.equal(bgi.wolfBankApproachReady(s.o,s.request,s.permit,s.now),false,mutate.toString());}
});
