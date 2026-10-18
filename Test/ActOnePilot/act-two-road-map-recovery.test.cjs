const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-emergency-switch.js'),w=require('./act-two-canopy-threat.fixture.json');
test('actual canopy threat may refresh map through Inventory but grants no switch or combat',()=>{
 const p={reviewed:true,roadMapReviewed:true,partyReviewed:true,session:w.session,frameId:7824,witnessFrameId:w.frameId,createdAt:w.timestamp},r={session:w.session,expectedFrameId:7824},o={session:w.session};
 assert(g.permit(o,w,p,r,w.timestamp,true,'map'));
 assert(g.permit(o,{...w,hud:{...w.hud,enemyBars:[]}},p,r,w.timestamp,true,'map'));
 assert(!g.permit(o,w,p,r,w.timestamp,true));
 for(const q of [{...p,usedAt:1},{...p,roadMapReviewed:false},{...p,session:'wrong'}])assert(!g.permit(o,w,q,r,w.timestamp,true,'map'));
 assert(!g.permit(o,w,p,r,w.timestamp+600001,true,'map'));
 assert(!g.permit(o,{...w,ocr:w.ocr.filter(x=>!x.text.includes('693306810'))},p,r,w.timestamp,true,'map'));
});
