const test=require('node:test'),assert=require('node:assert/strict');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-hideout-aerial.js'),o=require('./act-two-hideout-airborne.fixture.json');
test('recorded airborne special HUD accepts relocated Space without claiming flight from text',()=>{
 assert.equal(g.state(o,o.timestamp,o.session),true);
 for(const x of [1600,1750,1900])assert.equal(g.state({...o,ocr:o.ocr.map(r=>r.text==='Space'?{...r,x}:r)},o.timestamp,o.session),false);
 assert.equal(g.state(o,o.timestamp+1001,o.session),false);
 assert.equal(g.state({...o,hud:{...o.hud,health:{current:2487,max:2764}}},o.timestamp,o.session),false);
});
test('bomb sends exactly one E only after exclusive positive fresh flight sample',async()=>{
 let keys=[],released=0;const api={check(){},sample:async()=>({valid:true,flying:true,jumping:false}),key:async(k,ms)=>keys.push([k,ms]),sleep:async()=>{},release(){released++;}};
 const r=await g.bomb(api);assert.deepEqual(keys,[['VK_E',60]]);assert.equal(released,1);assert.equal(r.damage,'requires-image-review');
 for(const sample of [null,{valid:false,flying:true},{valid:true,flying:false,jumping:true},{valid:true,flying:true,jumping:true}]){keys=[];await assert.rejects(()=>g.bomb({...api,sample:async()=>sample}),/positive flight/);assert.equal(keys.length,0);}
});
test('bomb key failure still releases input',async()=>{let released=0;await assert.rejects(()=>g.bomb({check(){},sample:async()=>({valid:true,flying:true,jumping:false}),key:async()=>{throw Error('focus');},release(){released++;}}),/focus/);assert.equal(released,1);});
test('recorded omitted UID label still requires the full exact numeric account and rejects conflicts',()=>{
 const q=require('./act-two-hideout-airborne-uid.fixture.json');assert.equal(g.state(q,q.timestamp,q.session),true);
 for(const uid of [':693306811',':69330681',':1693306810'])assert.equal(g.state({...q,ocr:q.ocr.map(r=>r.text===':693306810'?{...r,text:uid}:r)},q.timestamp,q.session),false);
 assert.equal(g.state({...q,ocr:q.ocr.concat({text:'UID:693306811',x:1700,y:1048})},q.timestamp,q.session),false);
});
