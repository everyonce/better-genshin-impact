// Inert source-level qualification of the dedicated one-click Statue dialogue operation.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..'),pilot=path.join(root,'BetterGenshinImpact/User/JsScript/ActOnePilot');
// The candidate test lives at candidate/Test/ActOnePilot, just like the canonical test.
const source=fs.readFileSync(path.join(pilot,'bgi.js'),'utf8');
const missionSource=fs.readFileSync(path.join(pilot,'mission.js'),'utf8');
const engineSource=fs.readFileSync(path.join(pilot,'engine.js'),'utf8');
const body=source.match(/runStatueBlessingOpen: async function\(initial,observe\)\{([\s\S]*?)\n        \},/)[1];
const row=(text,x,y,width,height)=>({text,x,y,width,height});
const clone=value=>JSON.parse(JSON.stringify(value));
function dialogue(){
 return {session:'statue-test',frameId:1,capturedAt:1000,timestamp:1050,
  screenshotPath:'observations/statue-test/frame-0001.png',map:null,
  hud:{world:false,health:null,auto:true,choice:true,dialogueReady:false,journal:false,bigMap:false,climbing:false},
  ocr:[row('UID: 693306810',1684,1050,183,29),row('Auto',100,30,55,25),
   row('Statue of The Seven',785,850,300,35),row("Statue's Blessing",1260,570,301,35),
   row('Worship Statue',1324,613,229,35),row('Leave',1324,660,100,35)]};
}
function panel(frame,timestamp){
 return {session:'statue-test',frameId:frame,timestamp,map:null,
  hud:{world:false,journal:false,bigMap:false,choice:false,dialogueReady:false,auto:false,climbing:false},
  ocr:[row('UID: 693306810',1684,1050,183,29),
   row('Click on the character portrait to restore HP',28,34,800,35),
   row("Statue's Blessing",1519,27,251,44),row('Lv.20',441,213,73,38),
   row('Restorative Power: 10000 / 10000',1393,592,501,37)]};
}
function harness(options={}){
 const state={now:1100,checks:0,readies:0,reads:0,sleeps:[],inputs:[],keys:[],events:[]};
 const ctx={Date:{now:()=>state.now}};vm.createContext(ctx);vm.runInContext(source,ctx);
 Object.assign(ctx,{inventoryUiOnly:options.inventoryUiOnly===true,
  request:{id:'one-choice',session:'statue-test',mission:'questStep',step:'statueBlessingOpen',...options.request},
  lastObservation:options.source||dialogue(),events:state.events,
  checkStop:()=>{state.checks++;if(options.onCheck)options.onCheck(state,ctx);},
  ready:()=>{state.readies++;if(options.onReady)options.onReady(state,ctx);},
     boundedKey:async(key,duration,frameId,guard)=>{guard();const e={type:'key',key,durationMs:duration,frameId,startedAt:state.now};state.events.push(e);state.keys.push(key);state.now+=duration;e.finishedAt=state.now;if(options.onKey)options.onKey(state,ctx);},
   click:(x,y)=>{state.inputs.push([x,y]);state.now+=10;if(options.onClick)options.onClick(state,ctx);},
  sleep:async ms=>{state.sleeps.push(ms);state.now+=ms;if(options.onSleep)options.onSleep(state,ctx);}});
 ctx.initial=clone(ctx.lastObservation);delete ctx.initial.capturedAt;
 if(options.initial)Object.assign(ctx.initial,options.initial);
 ctx.observe=async()=>{state.reads++;state.now+=40;const observed=options.observe?
  options.observe(state,ctx):panel(state.reads+1,state.now);
   ctx.lastObservation=observed&&{...observed,capturedAt:observed.capturedAt===undefined?state.now-40:observed.capturedAt};return observed;};
 vm.runInContext('var invoke=async function(initial,observe){'+body+'};',ctx);
 return {state,ctx,run:()=>ctx.invoke(ctx.initial,ctx.observe)};
}
function selector(value,now=1100,scoped=false){const ctx={};vm.createContext(ctx);vm.runInContext(source,ctx);return ctx.actOneStatueBlessingChoiceTarget(value,now,'statue-test',scoped);}
async function refuses(change,pattern=/Fresh exact|Dedicated|changed or expired/){
 const raw=dialogue();change(raw);const h=harness({source:raw});await assert.rejects(h.run,pattern);
 assert.equal(h.state.inputs.length,0);assert.equal(h.state.events.length,0);assert.equal(h.state.reads,0);
}

test('one exact choice click retains its raw source and confirms the unchanged panel predicate',async()=>{
 const h=harness(),result=await h.run(),e=h.state.events[0];
 assert.deepEqual(h.state.inputs,[[1411,588]]);assert.equal(result.status,'completed');assert.equal(result.panelReady,true);
 assert.equal(result.panelFrameId,2);assert.equal(result.healingAttempted,false);assert.equal(result.offeringAttempted,false);
 assert.equal(result.physicalInputDeliveryVerified,false);assert.equal(e.physicalInputDeliveryVerified,false);
 assert.deepEqual(clone(e.source),{session:'statue-test',frameId:1,capturedAt:1000,timestamp:1050,screenshotPath:'observations/statue-test/frame-0001.png'});
 assert.equal(e.outcome,'returned_unverified');assert.equal(e.startedAt,1100);assert.equal(e.finishedAt,1110);
 assert.equal(e.panelConfirmedFrameId,2);assert.deepEqual(clone(e.observedFrameIds),[2]);
 assert.equal(e.target.choice.text,"Statue's Blessing");assert.equal(e.target.uid.text,'UID: 693306810');
 assert.notEqual(e.target.choice,h.ctx.lastObservation.ocr[3]);assert.deepEqual(h.state.sleeps,[350]);
});
test('Engine-style immutable initial snapshot need not carry private capturedAt',async()=>{
 const h=harness();assert.equal(h.ctx.initial.capturedAt,undefined);assert.equal((await h.run()).panelReady,true);
});
test('fresh completion cannot renew an expired raw capture request clock',async()=>{
 const h=harness({source:{...dialogue(),capturedAt:99,timestamp:1099}});await assert.rejects(h.run,/Fresh exact/);assert.deepEqual(h.state.inputs,[]);
});
test('future, missing and contradictory source clocks refuse before input',async()=>{
 for(const change of [o=>delete o.capturedAt,o=>o.capturedAt=1101,o=>o.timestamp=1101,o=>o.timestamp=999,o=>o.capturedAt=NaN])await refuses(change);
});
test('foreign session, missing frame and different retained screenshot refuse before input',async()=>{
 for(const change of [o=>o.session='foreign',o=>o.frameId=0,o=>o.screenshotPath='foreign.png'])await refuses(change);
});
test('initial snapshot must identify the same private raw source',async()=>{
 for(const initial of [{frameId:2},{session:'foreign'},{timestamp:1051},{screenshotPath:'other.png'}]){
  const h=harness({initial});await assert.rejects(h.run,/Fresh exact/);assert.deepEqual(h.state.inputs,[]);
 }
});
test('source replacement during pre-click readiness check refuses without a click',async()=>{
 const h=harness({onReady:(s,c)=>{if(s.readies===2)c.lastObservation=clone(c.lastObservation);}});
 await assert.rejects(h.run,/changed or expired/);assert.deepEqual(h.state.inputs,[]);
});
test('source expiry during pre-click readiness check refuses without a click',async()=>{
 const h=harness({onReady:s=>{if(s.readies===2)s.now=2001;}});
 await assert.rejects(h.run,/changed or expired/);assert.deepEqual(h.state.inputs,[]);
});
test('same-frame original UID must be visible, unique and exact',async()=>{
 for(const change of [o=>o.ocr.shift(),o=>o.ocr[0].text='UID: 693306811',o=>o.ocr[0].text='UID: 69330681',
  o=>o.ocr[0].text='UID: 693306810 Cape',o=>o.ocr.push(clone(o.ocr[0])),
  o=>o.ocr.push(row('693306810',1684,1050,183,29)),o=>o.ocr[0].x=1500])await refuses(change);
});
test('only the exact unique Statue speaker and Auto mode qualify',async()=>{
 for(const change of [o=>o.ocr[2].text='Another NPC',o=>o.ocr.push(clone(o.ocr[2])),o=>o.ocr[2].y=500,
  o=>o.ocr[1].text='Auto Play',o=>o.ocr.push(clone(o.ocr[1])),o=>o.hud.auto=false])await refuses(change);
});
test('only the exact unique in-bounds Blessing choice qualifies',async()=>{
 for(const change of [o=>o.ocr[3].text="Statue's Rewards",o=>o.ocr[3].text='Statue’s Blessing',
  o=>o.ocr.push(clone(o.ocr[3])),o=>o.ocr[3].x=900,o=>o.ocr[3].y=20,o=>o.ocr[3].width=500])await refuses(change);
});
test('offering screens and mixed offering evidence never cause input',async()=>{
 for(const text of ['Offer','Offer All','Required Anemoculus','Owned',"Statue's Rewards",'Anemoculus 0/1','Current Stamina Limit: 107/240'])
  await refuses(o=>o.ocr.push(row(text,1400,800,200,35)));
});
test('world, menus, loading and incomplete choice layouts never cause input',async()=>{
 for(const change of [o=>o.map={},o=>o.hud.world=true,o=>o.hud.health={current:2211,max:4015},
  o=>o.hud.choice=false,o=>o.hud.dialogueReady=true,o=>o.hud.journal=true,o=>o.hud.bigMap=true,
  o=>o.hud.climbing=true,o=>o.hud.loading=true,o=>o.hud.unknownHud=true])await refuses(change);
});
test('malformed OCR geometry refuses rather than deriving an unsafe click',async()=>{
 for(const change of [o=>o.ocr.push(null),o=>o.ocr[3].x=NaN,o=>o.ocr[3].width=0,o=>o.ocr[3].text=null])await refuses(change);
});
test('UI-only declarations cannot be stripped selectively to enter the new operation',async()=>{
 for(const change of [o=>o.uiObservation={},o=>o.mapDiagnostic={mode:'inventory-ui-only-v1'},
  o=>o.timings={mapDiagnostic:{mode:'inventory-ui-only-v1'}},
  o=>{o.mapDiagnostic={mode:'legacy'};o.timings={mapDiagnostic:{mode:'inventory-ui-only-v1'}};}])await refuses(change);
});
test('dedicated request and non-inventory mode are required inside the API method',async()=>{
 for(const options of [{inventoryUiOnly:true},{request:{mission:'recover'}},{request:{step:'actTwoStatueHeal'}}]){
  const h=harness(options);await assert.rejects(h.run,/Dedicated/);assert.deepEqual(h.state.inputs,[]);
 }
});
test('STOP before either pre-click check sends no input',async()=>{
 for(const stopAt of [1,2]){const h=harness({onCheck:s=>{if(s.checks===stopAt)throw Error('STOP');}});
  await assert.rejects(h.run,/STOP/);assert.deepEqual(h.state.inputs,[]);assert.deepEqual(h.state.events,[]);}
});
test('click exception retains the exact attempted event and does not retry or observe',async()=>{
 const h=harness({onClick:()=>{throw Error('native click rejected');}});await assert.rejects(h.run,/native click rejected/);
 assert.deepEqual(h.state.inputs,[[1411,588]]);assert.equal(h.state.reads,0);assert.equal(h.state.events.length,1);
 const e=h.state.events[0];assert.equal(e.outcome,'threw');assert.equal(e.error,'native click rejected');assert.equal(e.finishedAt,1110);
});
test('STOP after the click retains one returned attempt and causes no fallback input',async()=>{
 const h=harness({onCheck:s=>{if(s.checks===3)throw Error('STOP');}});await assert.rejects(h.run,/STOP/);
 assert.deepEqual(h.state.inputs,[[1411,588]]);assert.equal(h.state.events[0].outcome,'returned_unverified');assert.equal(h.state.reads,0);
});
test('post-click clock reversal is retained and refuses confirmation',async()=>{
 const h=harness({onClick:s=>s.now=1099});await assert.rejects(h.run,/clock moved backwards/);
 assert.equal(h.state.events[0].finishedAt,1099);assert.equal(h.state.inputs.length,1);assert.equal(h.state.reads,0);
});
test('confirmation can follow an intermediate passive frame without another click',async()=>{
 const h=harness({observe:s=>s.reads===1?{...panel(2,s.now),ocr:[]} : panel(s.reads+1,s.now)});
 const r=await h.run();assert.equal(r.panelReady,true);assert.equal(h.state.inputs.length,1);
 assert.deepEqual(clone(h.state.events[0].observedFrameIds),[2,3]);assert.deepEqual(h.state.sleeps,[350,250]);
});
test('missing or depleted healing panel ends after six passive polls with no fallback',async()=>{
 for(const depleted of [false,true]){const h=harness({observe:s=>{const o=panel(s.reads+1,s.now);
   if(depleted)o.ocr[4].text='Restorative Power: 0 / 10000';else o.ocr=[];return o;}});
  const r=await h.run();assert.equal(r.status,'stopped');assert.equal(r.panelReady,false);
  assert.equal(h.state.reads,6);assert.equal(h.state.inputs.length,1);assert.equal(h.state.sleeps.length,6);}
});
test('passive wall-clock bound stops before another observation',async()=>{
 const h=harness({onSleep:s=>s.now+=3001});const r=await h.run();assert.equal(r.status,'stopped');
 assert.equal(h.state.reads,0);assert.equal(h.state.sleeps.length,1);assert.equal(h.state.inputs.length,1);
});
test('foreign, repeated or pre-click result frames are not panel confirmation',async()=>{
 for(const patch of [{session:'foreign'},{frameId:1},{timestamp:1110},{timestamp:NaN}]){
  const h=harness({observe:s=>({...panel(2,s.now),...patch})});await assert.rejects(h.run,/fresh later frame/);
  assert.equal(h.state.inputs.length,1);assert.equal(h.state.reads,1);
 }
});
test('fresh post-click frame still must pass the unchanged strict panel predicate',async()=>{
 const h=harness({observe:s=>{const o=panel(s.reads+1,s.now);o.ocr[0].text='UID: 693306811';return o;}});
 assert.equal((await h.run()).panelReady,false);assert.equal(h.state.inputs.length,1);
});
test('copied click evidence remains unchanged if later OCR rows are mutated',async()=>{
 const h=harness({onClick:(s,c)=>c.lastObservation.ocr[3].text='mutated later'});await h.run();
 assert.equal(h.state.events[0].target.choice.text,"Statue's Blessing");
});
test('mission dispatch calls only the dedicated API',async()=>{
 const ctx={};vm.createContext(ctx);vm.runInContext(missionSource,ctx);let called=0;
 const initial=dialogue(),observe=async()=>{};
 const api=new Proxy({runStatueBlessingOpen:async(o,fn)=>{assert.equal(o,initial);assert.equal(fn,observe);called++;return {only:true};}},
  {get:(target,name)=>{if(name in target)return target[name];throw Error('Unexpected API '+String(name));}});
 assert.equal((await ctx.ActOneMission.runQuestStep('statueBlessingOpen',initial,api,observe)).only,true);assert.equal(called,1);
});
test('existing engine inventory-only allowlist rejects this new operation',()=>{
 const ctx={};vm.createContext(ctx);vm.runInContext(engineSource,ctx);
 assert.equal(ctx.ActOnePilot.inventoryUiRequestAllowed({mission:'questStep',step:'statueBlessingOpen'}),false);
 assert.equal(ctx.ActOnePilot.inventoryUiRequestAllowed({mission:'questStep',step:'worldInventory'}),true);
 assert.equal(ctx.ActOnePilot.inventoryUiRequestAllowed({mission:'questStep',step:'worldInventoryClose'}),true);
});
test('the operation contains one click and only the scoped one-shot Space advance',()=>{
 assert.equal((body.match(/\bclick\(/g)||[]).length,1);
 assert.equal((body.match(/boundedKey\('VK_SPACE',60,source.frameId,introGuard\)/g)||[]).length,1);
  assert.doesNotMatch(body,/\b(?:keyPress|forward|moveMouse|healTravelerAtStatue|runActTwoStatue|recover|finishActTwoDialogue)\s*\(/);
 assert.equal(selector(dialogue()).x,1411);
});

// Exercise the real engine's immutable snapshot, terminal receipt and release paths.
async function engineFixture(options={}){
 const h=harness(options),writes=[];let releases=0;
 vm.runInContext(engineSource,h.ctx);vm.runInContext(missionSource,h.ctx);
 const api={now:()=>h.state.now,requireInputReady(){},pinObservation(){},
  write:(name,text)=>writes.push([name,JSON.parse(text)]),
  beginMission:req=>{h.ctx.request=req;},events:()=>h.state.events,release:()=>releases++,
  runStatueBlessingOpen:(initial,observe)=>h.ctx.invoke(initial,observe),
  observe:async(session,frameId)=>{
   const capturedAt=h.state.now;h.state.now+=40;
   const raw=h.state.inputs.length?panel(frameId,h.state.now):dialogue();
   Object.assign(raw,{session,frameId,capturedAt,timestamp:h.state.now,
    screenshotPath:'observations/'+session+'/frame-'+String(frameId).padStart(4,'0')+'.png'});
   h.ctx.lastObservation=raw;return raw;
  }};
 const runner=h.ctx.ActOnePilot.create(api,{session:'statue-test',enableInput:true,inventoryUiOnlyV1:options.engineUiOnly===true});
 if(!options.engineUiOnly)await runner.observe();
 const request={id:'engine-choice',session:'statue-test',expectedFrameId:runner.getFrame(),
  createdAt:h.state.now,mission:'questStep',step:'statueBlessingOpen'};
 return {h,writes,runner,request,releases:()=>releases,run:()=>runner.process(request,()=>h.ctx.ActOneMission)};
}
test('real engine retains click source, terminal panel and releases after the dedicated dispatch',async()=>{
 const f=await engineFixture();assert.equal(await f.run(),'completed');assert.equal(f.releases(),1);
 const receipt=f.writes.filter(([name])=>name==='receipt.json').at(-1)[1];
 assert.equal(receipt.status,'completed');assert.equal(receipt.details.result.panelReady,true);
 assert.equal(receipt.details.inputEvents.length,1);assert.equal(receipt.details.inputEvents[0].source.frameId,2);
 assert.equal(receipt.details.inputEvents[0].panelConfirmedFrameId,3);assert.equal(receipt.frameId,4);
 assert.equal(f.h.state.inputs.length,1);assert.equal(await f.run(),'rejected');assert.equal(f.h.state.inputs.length,1);
});
test('real engine preserves attempted click and native failure in its failed receipt',async()=>{
 const f=await engineFixture({onClick:()=>{throw Error('native refusal');}});await assert.rejects(f.run,/native refusal/);
 const receipt=f.writes.filter(([name])=>name==='receipt.json').at(-1)[1];
 assert.equal(receipt.status,'failed');assert.equal(receipt.details.inputEvents[0].outcome,'threw');
 assert.equal(receipt.details.inputEvents[0].error,'native refusal');assert.equal(f.releases(),1);
 assert.equal(f.h.state.inputs.length,1);assert.equal(await f.run(),'rejected');
});
test('real engine inventory-only mode rejects before observation or native input',async()=>{
 const f=await engineFixture({engineUiOnly:true});assert.equal(await f.run(),'rejected');
 assert.equal(f.h.state.inputs.length,0);assert.equal(f.runner.getFrame(),0);
 const receipt=f.writes.filter(([name])=>name==='receipt.json').at(-1)[1];
 assert.match(receipt.details.reason,/Inventory UI-only mode rejects/);
});


// Retained healing01 frame33 OCR, SHA d35acc4fe57686c9d5cb0683f3908de9a361ec1d8751cd968f2c568ba6c9cb4f.
function silentIntro(){
 const o=dialogue();o.hud.choice=false;o.hud.dialogueReady=true;
 o.ocr=[row('utc',118,42,41,17),row('Statue of The Seven',789,858,343,36),row('UID: 693306810',1682,1050,181,27)];return o;
}
// New observations carry genuinely later inert capture/publication times, never edited causal receipts.
function nextChoice(state){const o=dialogue();Object.assign(o,{frameId:state.reads+1,capturedAt:state.now-40,timestamp:state.now,
 screenshotPath:'observations/statue-test/frame-'+String(state.reads+1).padStart(4,'0')+'.png'});return o;}
function introHarness(extra={}){return harness({source:silentIntro(),observe:s=>s.reads===1?nextChoice(s):panel(s.reads+1,s.now),...extra});}

test('retained utc intro advances once then clicks only the later exact Blessing choice',async()=>{
 const h=introHarness(),raw=clone(h.ctx.lastObservation.ocr),r=await h.run();
 assert.deepEqual(h.state.keys,['VK_SPACE']);assert.equal(h.state.inputs.length,1);assert.equal(r.panelReady,true);
 const e=h.state.events.find(e=>e.type==='statueBlessingIntroAdvance'),click=h.state.events.find(e=>e.type==='statueBlessingOpen');
 assert.equal(e.target.auto.text,'utc');assert.deepEqual(raw,silentIntro().ocr);assert.equal(e.source.frameId,1);
 assert.equal(e.durationMs,60);assert.equal(e.deadlineAt,e.attemptedAt+3000);assert.deepEqual(clone(e.observedFrameIds),[2]);
 assert.equal(click.source.frameId,2);assert(click.source.capturedAt>e.finishedAt);assert.equal(r.introSourceFrameId,1);
});
test('the raw utc choice alias is explicit and does not change the legacy selector default',async()=>{
 const o=dialogue();o.ocr[1]=row('utc',118,42,41,17);assert.equal(selector(o),null);assert.equal(selector(o,1100,true).x,1411);
 const h=harness({source:o}),r=await h.run();assert.equal(r.panelReady,true);assert.deepEqual(h.state.keys,[]);
 assert.equal(r.introAdvanceAttempted,undefined);assert.equal(h.state.events[0].target.auto.text,'utc');
});
test('intro refuses wrong UID speaker Auto geometry duplicate anchors choices and unknown text',async()=>{
 for(const change of [o=>o.ocr[2].text='UID: 693306811',o=>o.ocr[1].text='Kaeya',o=>o.ocr[0].x=400,
  o=>o.ocr[0].text='uto',o=>o.ocr.push(clone(o.ocr[0])),o=>o.ocr.push(row('Leave',1324,660,100,35)),
  o=>o.ocr.push(row('Offer All',1324,660,150,35)),o=>o.ocr.push(row('Unknown prompt',800,930,200,30))]){
  const o=silentIntro();change(o);const h=introHarness({source:o});await assert.rejects(h.run,/Fresh exact/);
  assert.deepEqual(h.state.keys,[]);assert.deepEqual(h.state.inputs,[]);
 }
});
test('intro requires exact source clocks snapshot and non-inventory scope before its sole advance',async()=>{
 for(const change of [o=>o.capturedAt=99,o=>o.timestamp=999,o=>o.capturedAt=1101,o=>o.session='foreign',
  o=>o.hud.world=true,o=>o.hud.health={current:1,max:4015},o=>o.uiObservation={},o=>o.hud.choice=true]){
  const o=silentIntro();change(o);const h=introHarness({source:o});await assert.rejects(h.run,/Fresh exact/);assert.deepEqual(h.state.keys,[]);
 }
 const h=introHarness({inventoryUiOnly:true});await assert.rejects(h.run,/Dedicated/);assert.deepEqual(h.state.keys,[]);
});
test('intro final source recheck consumes failure without a key when readiness expires its capture',async()=>{
 const h=introHarness({onReady:s=>{if(s.readies===2)s.now=2001;}});await assert.rejects(h.run,/intro source changed or expired/);
 assert.deepEqual(h.state.keys,[]);assert.equal(h.state.events.length,1);assert.equal(h.state.events[0].outcome,'threw');
});
test('intro STOP after its single key does not send a second key or click',async()=>{
 const h=introHarness({onKey:()=>{throw Error('Stop requested');}});await assert.rejects(h.run,/Stop requested/);
 assert.deepEqual(h.state.keys,['VK_SPACE']);assert.deepEqual(h.state.inputs,[]);assert.equal(h.state.reads,0);
});
test('intro cannot click a Blessing choice captured before or at completion of Space',async()=>{
 const h=introHarness({observe:s=>({...nextChoice(s),capturedAt:1160})}),r=await h.run();
 assert.equal(r.status,'stopped');assert.equal(r.clicks,0);assert.deepEqual(h.state.keys,['VK_SPACE']);assert.equal(h.state.reads,6);
});
test('intro and panel confirmation share exactly six passive observations',async()=>{
 const h=introHarness({observe:s=>s.reads===5?nextChoice(s):s.reads<5?{...silentIntro(),frameId:s.reads+1,
  timestamp:s.now,screenshotPath:'observations/statue-test/frame-'+String(s.reads+1).padStart(4,'0')+'.png'}:panel(s.reads+1,s.now)});
 const r=await h.run();assert.equal(r.panelReady,true);assert.equal(h.state.reads,6);assert.equal(h.state.keys.length,1);assert.equal(h.state.inputs.length,1);
});
test('intro time spent before the click cannot renew the original three-second bound',async()=>{
 const h=introHarness({onSleep:s=>{s.now+=1100;},observe:s=>s.reads===1?nextChoice(s):panel(s.reads+1,s.now)}),r=await h.run();
 assert.equal(r.status,'stopped');assert.equal(r.panelReady,false);assert.equal(h.state.inputs.length,1);
 assert.equal(h.state.reads,1);assert(h.state.now>=h.state.events[0].deadlineAt);
});
test('a repeated or foreign post-advance frame fails with one consumed Space and no click',async()=>{
 for(const patch of [{frameId:1},{session:'other'},{timestamp:1160}]){
  const h=introHarness({observe:s=>({...nextChoice(s),...patch})});await assert.rejects(h.run,/fresh later frame/);
  assert.deepEqual(h.state.keys,['VK_SPACE']);assert.deepEqual(h.state.inputs,[]);
 }
});
