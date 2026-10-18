const test=require('node:test'),assert=require('node:assert/strict');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-hideout-aerial.js');
function mock({lag=0,samples=[{valid:true,jumping:true,flying:false},{valid:true,jumping:false,flying:true}],failPress=0}={}){
 let t=0,presses=0,paused=0,released=0;
 return {api:{now:()=>t,check(){},sample:async()=>samples.shift(),space:async()=>{presses++;if(presses===failPress)throw Error('Focus lost');t+=60;},sleep:async ms=>{t+=ms+(ms===350?lag:0);},release(){released++;},pause:async()=>{paused++;}},counts:()=>({presses,paused,released})};
}
test('current probe requires explicit named current and forbids bundled movement/camera',()=>{
 const p={reviewed:true,session:'s',frameId:2,createdAt:1000,mode:'currentProbe',ms:0,key:'VK_W',dx:0,dy:0,currentReviewed:true,currentLandmark:'Visible spiral wind column directly around the character'},r={session:'s',expectedFrameId:2};
 assert.equal(g.plan(p,r,1000),true);
 for(const patch of [{currentReviewed:false},{currentLandmark:''},{ms:200},{dx:1},{dy:1},{usedAt:1},{session:'other'}])assert.equal(g.plan({...p,...patch},r,1000),false);
});
test('two local presses preserve350ms window and distinguish control evidence from wings or bomb damage',async()=>{
 const m=mock(),r=await g.currentProbe({},m.api);assert.equal(r.presses,2);assert.equal(r.releaseToDeployMs,350);assert.equal(r.flightControlDetected,true);assert.equal(r.visibleWings,'requires-image-review');assert.equal(r.bombs,0);assert.equal(m.counts().paused,1);assert.equal(r.timeline[1].startedAt-r.timeline[0].finishedAt,350);
});
test('unknown or already flying control sends zero presses and always pauses',async()=>{
 for(const before of [null,{valid:false},{valid:true,jumping:false,flying:true},{valid:true,jumping:true,flying:true}]){const m=mock({samples:[before]});await assert.rejects(()=>g.currentProbe({},m.api),/fresh jump control/);assert.equal(m.counts().presses,0);assert.equal(m.counts().paused,1);}
});
test('scheduling delay cannot produce a late deployment or repeated attempt',async()=>{
 const m=mock({lag:250});await assert.rejects(()=>g.currentProbe({},m.api),e=>{assert.equal(e.currentProbeResult.presses,1);return /timing window/.test(e.message);});assert.equal(m.counts().presses,1);assert.equal(m.counts().paused,1);
});
test('focus loss and negative flight sample retain diagnostics and release/pause',async()=>{
 const m=mock({failPress:2});await assert.rejects(()=>g.run({mode:'currentProbe'},m.api),e=>{assert.equal(e.aerialResult.currentProbe.presses,1);return /Focus lost/.test(e.message);});assert.equal(m.counts().paused,1);assert.ok(m.counts().released);
 const n=mock({samples:[{valid:true,jumping:true,flying:false},{valid:true,jumping:true,flying:false}]});const r=await g.currentProbe({},n.api);assert.equal(r.flightControlDetected,false);assert.equal(n.counts().presses,2);
});
