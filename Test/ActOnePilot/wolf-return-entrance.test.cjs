const test=require('node:test');const assert=require('node:assert/strict');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const row=(text,x=1650,y=400)=>({text,x,y,width:90,height:25});
function world(patch={}){return {timestamp:1000,frameId:1,map:{map:'Teyvat',x:-1323.474,y:2566.115},ocr:[row('Amber'),row('Enter the temple',60,250)],hud:{world:true,health:{current:1055,max:1055},lowHealth:false,objectives:['Enter the temple'],journal:false,bigMap:false,climbing:false,dialogueReady:false,choice:false,tutorialStep:null,objectiveChanged:false,auto:false,enemyBars:[]},...patch};}
test('Wolf return guard accepts fresh safe Teyvat world with starter label and exact objective',()=>{
 const o=world();assert.equal(bgi.wolfReturnToEntranceReady(o,1000),true);
 for(const p of [{timestamp:-1},{map:null},{map:{map:'Liyue',x:0,y:0}},{hud:{...o.hud,health:{current:500,max:1055}}},{hud:{...o.hud,objectives:['Meet Kaeya at the temple']}},{hud:{...o.hud,journal:true}},{hud:{...o.hud,climbing:true}},{hud:{...o.hud,dialogueReady:true}},{hud:{...o.hud,choice:true}},{ocr:[row('Amber'),row('Trial',1780,450),row('Enter the temple',60,250)]},{ocr:[row('Kaeya'),row('Enter the temple',60,250)]},{ocr:[row('Unrelated'),row('Enter the temple',60,250)]}])assert.equal(bgi.wolfReturnToEntranceReady({...o,...p},1000),false);
});
test('Wolf return mission issues one native teleport and completes only after safe arrival verification',async()=>{
 let teleports=0,reads=0,now=1000;const calls=[];
 const result=await mission.runQuestStep('wolfReturnToEntrance',world(),{now:()=>now,checkStop(){},wolfReturnToEntranceReady:o=>bgi.wolfReturnToEntranceReady(o,now),wolfReturnToEntrance:async()=>{teleports++;calls.push('teleport');},sleep:async ms=>{now+=ms;calls.push(ms);}},async()=>{reads++;return world({timestamp:now,frameId:reads+1,map:{map:'Teyvat',x:-1648.1,y:2168.4}});});
 assert.equal(result.status,'completed');assert.equal(result.teleported,true);assert.equal(result.polls,1);assert.equal(teleports,1);assert.deepEqual(calls,['teleport',500]);assert.match(result.reason,/arrival verified/);
});
test('Wolf return fails closed on unsafe arrival and never retries after the single teleport',async()=>{
 let teleports=0,reads=0,now=1000;
 const result=await mission.runQuestStep('wolfReturnToEntrance',world(),{now:()=>now,checkStop(){},wolfReturnToEntranceReady:o=>bgi.wolfReturnToEntranceReady(o,now),wolfReturnToEntrance:async()=>{teleports++;},sleep:async ms=>{now+=ms;}},async()=>{reads++;return world({timestamp:now,frameId:2,map:{map:'Teyvat',x:-1600,y:2200},hud:{...world().hud,choice:true}});});
 assert.equal(result.status,'stopped');assert.equal(teleports,1);assert.equal(reads,1);assert.match(result.reason,/Unexpected UI/);
});
test('Wolf return times out after twelve bounded polls without a retry or false arrival claim',async()=>{
 let teleports=0,reads=0,now=1000;
 const result=await mission.runQuestStep('wolfReturnToEntrance',world(),{now:()=>now,checkStop(){},wolfReturnToEntranceReady:o=>bgi.wolfReturnToEntranceReady(o,now),wolfReturnToEntrance:async()=>{teleports++;},sleep:async ms=>{now+=ms;}},async()=>{reads++;return world({timestamp:now,frameId:reads+1,map:{map:'Teyvat',x:-1590,y:2300}});});
 assert.equal(result.status,'stopped');assert.equal(result.polls,12);assert.equal(teleports,1);assert.equal(reads,12);assert.match(result.reason,/timed out/);
});
test('Wolf return does not call native teleport when the initial state is unsafe',async()=>{
 let teleports=0;
 const result=await mission.runQuestStep('wolfReturnToEntrance',world({hud:{...world().hud,health:{current:400,max:1055}}}),{wolfReturnToEntranceReady:o=>bgi.wolfReturnToEntranceReady(o,1000),wolfReturnToEntrance:async()=>{teleports++;},checkStop(){},sleep:async()=>{}},async()=>{throw Error('unexpected poll');});
 assert.equal(result.status,'stopped');assert.equal(teleports,0);
});

test('live adapter accepts only the fixed guarded Wolf TP and records one native target',async()=>{
 const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
 const packageDir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');let clock=2000000;const calls=[];
 const ocr=[row('Amber',1650,400),row('Enter the temple',60,250),row('E',1700,1015),row('Q',1760,1015),row('1055/1055',910,1000,100,20)];
 const context={Date:class extends Date{static now(){return clock;}},genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>({x:-1323.474,y:2566.115}),getCameraOrientation:()=>0,tp:async(x,y,wait)=>calls.push(['tp',x,y,wait])},
 file:{isExists:()=>false,readTextSync:p=>fs.readFileSync(path.join(packageDir,p),'utf8'),writeTextSync:()=>true,writeImageSync:()=>true},RecognitionObject:{Ocr:()=>({})},
 ImageRegion:class{constructor(){this.width=1920;this.height=1080;}findMulti(){const a=ocr.map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
 OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}}}},captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=ocr.map(r=>({...r}));a.count=a.length;return a;},deriveCrop:()=>({srcMat:{resize:()=>({})},dispose(){}}),dispose(){}}),
 sleep:async ms=>{clock+=ms;calls.push(['sleep',ms]);},keyDown:key=>calls.push(['down',key]),keyUp:key=>calls.push(['up',key]),click:()=>{},moveMouseBy:()=>{},verticalScroll:()=>{},log:{info(){}}};
 vm.runInNewContext(fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8'),context);const adapter=context.createActOneAdapter(7);
 adapter.beginMission({mission:'questStep',step:'wolfReturnToEntrance',session:'wolf-return',createdAt:clock});const observed=await adapter.observe('wolf-return',1);assert.equal(observed.hud.world,true);
 const ready=adapter.wolfReturnToEntranceReady(observed);assert.equal(ready,true);await adapter.wolfReturnToEntrance();
 assert.deepEqual(calls.filter(c=>c[0]==='tp'),[['tp',-1642.421,2163.664,false]]);
 assert.ok(calls.some(c=>c[0]==='down'&&c[1]==='VK_M'));assert.ok(calls.some(c=>c[0]==='up'&&c[1]==='VK_M'));
 const event=adapter.events().find(e=>e.type==='wolfReturnTeleport');assert.equal(event.x,-1642.421);assert.equal(event.y,2163.664);assert.equal(event.frameId,1);
});
