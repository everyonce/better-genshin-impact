const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),o=require('./act-two-hideout-shelf.fixture.json');
const actions=[{type:'key',key:'VK_SPACE',ms:60,target:'Reviewed low rock shelf'},{type:'key',key:'VK_W',ms:600}];
test('shelf hop requires one reviewed low crest and exact short jump/forward pair',()=>{
 const p={reviewed:true,session:'s',frameId:3,witnessFrameId:2,regionMapFrameId:1,createdAt:100,visualPositionReviewed:true,mode:'actions',shelfHop:true,shelfLandmark:'Visible low crest above the character beside the bush',actions},r={session:'s',expectedFrameId:3};assert(g.plan(p,r,100));
 for(const patch of [{shelfHop:false},{shelfLandmark:''},{visualPositionReviewed:false},{regionMapFrameId:undefined},{actions:[...actions,actions[1]]},{actions:[actions[0],{...actions[1],ms:800}]},{session:'other'}])assert(!g.plan({...p,...patch},r,100));
});
test('actual shelf frame is eligible only with full health, ground controls, no enemies and Outrider objective',()=>{
 assert(g.shelfReady(o));for(const patch of [{health:{current:4014,max:4015}},{climbing:true},{groundControls:false},{enemyBars:[{}]},{objectives:['Explore for Adventure Rank']},{world:false}])assert(!g.shelfReady({...o,hud:{...o.hud,...patch}}));
});
test('one local shelf hop observes after both inputs and releases on input failure',async()=>{
 const map=require('./act-two-hideout-blossom-map.fixture.json'),p={shelfHop:true,shelfLandmark:'Visible low crest above the character beside the bush',mode:'actions',visualPositionReviewed:true,regionMapFrameId:map.frameId,regionWitness:{...map,session:o.session,timestamp:1000},actions};
 for(const fail of [false,true]){let now=1000,released=0,keys=[];const api={now:()=>now,checkStop(){},sleep:async n=>now+=n,key:async(k,n)=>{keys.push([k,n]);if(fail)throw Error('input failure');now+=n;},release:async()=>released++},observe=async()=>{assert.equal(keys.length,2);return {...o,timestamp:now,frameId:o.frameId+1};};
 if(fail)await assert.rejects(g.run(o,o,p,api,observe),/input failure/);else{const r=await g.run(o,o,p,api,observe);assert.equal(r.actions,2);assert.deepEqual(keys,[['VK_SPACE',60],['VK_W',600]]);assert.match(r.reason,/shelf hop/);}assert.equal(released,1);}
});
