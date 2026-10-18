const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-emergency-switch.js'),w=require('./act-two-wind-seal-recovery.fixture.json');
const p={reviewed:true,session:w.session,frameId:8557,witnessFrameId:w.frameId,createdAt:w.timestamp,windSealMapReviewed:true,partyReviewed:true},r={session:w.session,expectedFrameId:8557},o={session:w.session};
test('actual damaged Amber has map-only escape despite combat world classifier refusing low health',()=>{
 assert.equal(w.hud.world,false);assert(g.permit(o,w,p,r,w.timestamp,true,'map'));assert(!g.permit(o,w,p,r,w.timestamp,true));
 for(const patch of [{windSealMapReviewed:false},{usedAt:1},{session:'other'},{witnessFrameId:1}])assert(!g.permit(o,w,{...p,...patch},r,w.timestamp,true,'map'));
 assert(!g.permit(o,w,p,r,w.timestamp+120001,true,'map'));
 for(const text of ['Eye of the Storm','Restless Pure Elemental'])assert(!g.permit(o,{...w,ocr:w.ocr.filter(r=>r.text!==text)},p,r,w.timestamp,true,'map'));
 assert(g.permit(o,{...w,hud:{...w.hud,health:{current:1,max:1733}}},p,r,w.timestamp,true,'map'));assert(!g.permit(o,{...w,hud:{...w.hud,health:{current:0,max:1733}}},p,r,w.timestamp,true,'map'));
});
