const test=require('node:test'),assert=require('node:assert/strict');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/field-progress.js');
const frames=require('./field-progress-real.fixture.json'),[start,mid,end,ground,exit]=frames;
const p={mode:'climb',actions:Array(4).fill({type:'key',key:'VK_W',ms:600})};
function history(){return g.finish(g.begin({version:1,entries:[]},p,mid,'attempt'), 'attempt',end);}
test('real unchanged upper corner rejects another climb batch, including shortened holds',()=>{
 for(const actions of [p.actions,[{type:'key',key:'VK_W',ms:100}],[{type:'key',key:'VK_D',ms:600}]])assert.match(g.rejection(history(),{...p,actions},end),/Climb progress unverified/);
});
test('horizontal drift alone never establishes vertical climb progress',()=>{
 const w=structuredClone(end);w.map.x+=2;assert.match(g.rejection(history(),p,w),/Climb progress/);
});
test('same corner after full-health fall is not proof of a safe exit',()=>{
 assert.match(g.rejection(history(),{mode:'actions',actions:[{type:'key',key:'VK_W',ms:600}]},ground),/Climb progress/);
 assert.equal(g.rejection(history(),p,exit),null);
});
test('camera-only inspection remains available without history and does not erase it',()=>{
 const camera={mode:'actions',actions:[{type:'look',dx:500,dy:0}]},h=history();
 assert.equal(g.rejection(null,camera,end),null);assert.equal(g.begin(h,camera,end,'camera'),h);
 assert.match(g.rejection(null,p,end),/unavailable/);
});
test('pending attempt survives an uncertain terminal and blocks blind replay',()=>{
 const h=g.begin({version:1,entries:[]},p,mid,'uncertain');assert.match(g.rejection(h,p,mid),/unverified/);
});
test('measured same-view vertical landmark evidence permits one new continuation',()=>{
 const review={fromFrame:mid.frameId,toFrame:end.frameId,kind:'vertical-landmark',landmark:'Distinct horizontal upper rock seam',beforeY:300,afterY:330,cameraUnchanged:true};
 assert.equal(g.rejection(history(),{...p,progressReview:review},end),null);
 for(const patch of [{toFrame:1},{afterY:305},{cameraUnchanged:false},{landmark:'wall'}])assert.match(g.rejection(history(),{...p,progressReview:{...review,...patch}},end),/unverified/);
});
test('quest elevation permits progress with a matching nonempty objective',()=>{
 const a=structuredClone(mid),b=structuredClone(end);a.hud.objectives=['Reach target','Higher 26m'];b.hud.objectives=['Reach target','Higher 24m'];
 let h=g.finish(g.begin({version:1,entries:[]},p,a,'r'),'r',b);assert.equal(g.rejection(h,p,b),null);
 b.hud.objectives=['Different target','Higher 24m'];assert.match(g.rejection(h,p,b),/unverified/);
});
test('a camera change alone cannot approve another contact pulse',()=>{
 const w=structuredClone(ground);w.map.cameraAngle+=50;assert.match(g.rejection(history(),p,w),/unverified/);
 const progressReview={fromFrame:mid.frameId,toFrame:w.frameId,kind:'different-approach',landmark:'Visible grassy exit beside the outer rock',visibleTraversableExit:true,description:'Clear dry shelf visibly connects away from the corner'};
 assert.equal(g.rejection(history(),{...p,progressReview},w),null);
});
test('ground stall survives a reload and history stays bounded',()=>{
 const q={mode:'actions',actions:p.actions},w=structuredClone(ground);let h={version:1,entries:[]};
 for(let i=0;i<25;i++)h=g.finish(g.begin(h,q,w,String(i)),String(i),w);
 assert.equal(h.entries.length,16);assert.match(g.rejection(JSON.parse(JSON.stringify(h)),q,w),/Ground progress stalled/);
});
test('recorded 600 ms Mondstadt stride is progress while a long 2 m slide remains stalled',()=>{
 const a={session:'city',frameId:570,timestamp:1000,map:{x:-867.68359375,y:2281.37890625,map:'Teyvat',cameraAngle:50},hud:{world:true,groundControls:true,objectives:[]}};
 const b={...a,frameId:577,timestamp:2000,map:{x:-869.421875,y:2279.275390625,map:'Teyvat',cameraAngle:49.5}};
 const q={mode:'actions',actions:[{type:'key',key:'VK_W',ms:600}]},next={mode:'actions',actions:[{type:'key',key:'VK_D',ms:800}]};
 const progressed=g.finish(g.begin({version:1,entries:[]},q,a,'short'),'short',b);
 assert.equal(g.rejection(progressed,next,b),null);
 const slow={...q,actions:Array.from({length:4},()=>({type:'key',key:'VK_W',ms:800}))};
 const stalled=g.finish(g.begin({version:1,entries:[]},slow,a,'long'),'long',b);
 assert.match(g.rejection(stalled,next,b),/Ground progress stalled/);
});
test('runtime checks and persists the attempt before unpause, then records outcome',()=>{
 const fs=require('fs'),source=fs.readFileSync('BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js','utf8');
 const block=source.slice(source.indexOf('runActTwoField: async'),source.indexOf('runActTwoWindriseSlime: async'));
 assert.ok(block.indexOf('progress.rejection')<block.indexOf("await boundedKey('VK_ESCAPE'"));
 assert.ok(block.indexOf('progress.begin')<block.indexOf("await boundedKey('VK_ESCAPE'"));
 assert.ok(block.includes('progress.finish(progressHistory,request.id,lastObservation)'));
 assert.ok(block.includes("throw Error('Progress history persistence failed')"));
});
