const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),entry=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-hideout-entry.js');
const prompt=require('./act-two-hideout-entry-prompt.fixture.json'),transition=require('./act-two-hideout-entry-transition.fixture.json'),settled=require('./act-two-hideout-entry-settled.fixture.json');
test('recorded transitioning entrance is rejected until all exact labels appear',()=>{
 assert.equal(entry.entryHandoff(transition,1000,transition.session),false);
 assert.equal(entry.entryHandoff(settled,1000,settled.session),true);
});
test('hideout interaction sends F once and lets the entrance settle before capture',async()=>{
 const map=require('./act-two-hideout-blossom-map.fixture.json'),p={mode:'actions',visualPositionReviewed:true,regionMapFrameId:map.frameId,regionWitness:{...map,session:prompt.session,timestamp:1000},actions:[{type:'key',key:'VK_F',ms:60,target:"Raptor's Hideout"}]};
 let now=1000,inputs=0,released=0,sleeps=[];
 const api={now:()=>now,checkStop(){},sleep:async n=>{sleeps.push(n);now+=n;},action:async a=>{assert.equal(a.key,'VK_F');inputs++;now+=60;},release:async()=>released++};
 const r=await g.run(prompt,prompt,p,api,async()=>{assert.deepEqual(sleeps,[1200]);return {...settled,timestamp:now};});
 assert.equal(inputs,1);assert.equal(r.actions,1);assert.equal(released,1);
});
