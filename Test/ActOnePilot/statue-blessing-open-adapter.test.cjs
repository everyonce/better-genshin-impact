// Inert qualification of the complete adapter, engine and mission boundary.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..'),packageDir=path.join(root,'BetterGenshinImpact/User/JsScript/ActOnePilot');
const fixtureFile=path.join(__dirname,'lion-field-combat-adapter.test.cjs');
const row=(text,x,y,width,height)=>({text,x,y,width,height});
function dialogue(){return [row('UID: 693306810',1684,1050,183,29),row('Auto',100,30,55,25),
 row('Statue of The Seven',785,850,300,35),row("Statue's Blessing",1260,570,301,35),row('Worship Statue',1324,613,229,35)];}
function panel(){return [row('UID: 693306810',1684,1050,183,29),
 row('Click on the character portrait to restore HP',28,34,800,35),row("Statue's Blessing",1519,27,251,44),
 row('Lv.20',441,213,73,38),row('Restorative Power: 10000 / 10000',1393,592,501,37)];}
// Exact raw healing01 OCR; these fixtures never rename utc to Auto.
function recordedIntro(){return [row('utc',118,42,41,17),row('Statue of The Seven',789,858,343,36),row('UID: 693306810',1682,1050,181,27)];}
function recordedMissingAuto(){return [row('Statue of The Seven',789,858,343,36),row('UID:693306810',1684.6666666666667,1054,173.33333333333334,19.333333333333332)];}
function actual(options={}){
 let text=fs.readFileSync(fixtureFile,'utf8'),cut=text.indexOf('\nfunction assertPauseProof');assert(cut>0);text=text.slice(0,cut);
 const dir="const dir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');";
 assert(text.includes(dir));text=text.replace(dir,'const dir='+JSON.stringify(packageDir)+';');
  if(options.captureCostMs){assert.equal(options.captureCostMs,25);const needle='metrics.captures++;const fought';
   assert.equal(text.split(needle).length,2);text=text.replace(needle,'metrics.captures++;now+=25;const fought');}
 const box={require,module:{exports:{}},__dirname:path.dirname(fixtureFile),setImmediate};
 vm.runInNewContext(text+'\nmodule.exports={fixture};',box,{filename:'inert-statue-adapter-fixture.cjs'});
 const f=box.module.exports.fixture({step:'statueBlessingOpen',noEnemy:true,initialScreen:'field',
  fieldRowsSequence:[dialogue(),dialogue(),panel(),panel()],...options});
 f.context.file.pinCaptureEvidence=()=>{};
  // Only the OCR boundary is inert; the real observer chooses whether this exact same-image crop is allowed.
  const OriginalImageRegion=f.context.ImageRegion;f.metrics.statueAutoCropCalls=0;
  f.context.ImageRegion=class extends OriginalImageRegion{findMulti(ro){const rect=this.srcMat.rect;
   if(rect&&rect.x===90&&rect.y===20&&rect.w===100&&rect.h===65){f.metrics.statueAutoCropCalls++;
    const rows=(options.statueAutoCropRows||[]).map(r=>({...r}));rows.count=rows.length;return rows;}
   return super.findMulti(ro);}};
 const calls=[];f.context.click=(x,y)=>calls.push({x,y,at:f.getNow()});
 vm.runInNewContext(fs.readFileSync(path.join(packageDir,'mission.js'),'utf8'),f.context);
 const engine=require(path.join(packageDir,'engine.js'));
 const runner=engine.create(f.adapter,{session:'lion-adapter-test',enableInput:true});
 return {f,calls,runner,run:async()=>{if(options.idleBootstrap)f.adapter.beginMission({mission:'observe',session:'lion-adapter-test',id:'idle-only',createdAt:f.getNow()});await runner.observe();return runner.process({id:'full-adapter-one',session:'lion-adapter-test',
   expectedFrameId:runner.getFrame(),createdAt:f.getNow(),mission:'questStep',step:'statueBlessingOpen'},()=>f.context.ActOneMission);}};
}
test('complete adapter joins its private capture to the engine and records exactly one click without localization',async()=>{
 const x=actual();assert.equal(await x.run(),'completed');assert.equal(x.calls.length,1);
 assert.deepEqual(x.calls.map(c=>[c.x,c.y]),[[1411,588]]);
 const files=x.f.getVirtualFiles(),receipt=JSON.parse(files.get('receipt.json'));
 assert.equal(receipt.details.result.panelReady,true);assert.equal(receipt.frameId,4);
 const e=receipt.details.inputEvents.find(e=>e.type==='statueBlessingOpen');
 assert.equal(e.source.frameId,2);assert.equal(e.source.capturedAt,10000);assert.equal(e.source.timestamp,10000);
 assert.equal(e.source.screenshotPath,'observations/lion-adapter-test/frame-0002.png');assert.equal(e.panelConfirmedFrameId,3);
 assert.equal(e.outcome,'returned_unverified');assert.equal(e.physicalInputDeliveryVerified,false);
 const retained=JSON.parse(files.get('observations/lion-adapter-test/frame-0002.json'));
 assert.equal(retained.capturedAt,undefined);assert.equal(retained.map,null);
 assert.equal(retained.timings.mapDiagnostic.mode,'statue-blessing-dialogue-v1');
 assert.equal(x.f.inputs.filter(x=>x.kind==='down').length,0);assert.equal(x.f.metrics.captures,4);
 assert.equal(x.f.metrics.mapCalls,0);assert.equal(x.f.metrics.orientationCalls,0);
});
test('complete adapter without same-frame UID refuses and retains zero click input',async()=>{
 const missing=dialogue().filter(r=>!r.text.startsWith('UID'));
 const x=actual({fieldRowsSequence:[missing,missing,panel()]});await assert.rejects(x.run,/visible original UID/);
 assert.equal(x.calls.length,0);const receipt=JSON.parse(x.f.getVirtualFiles().get('receipt.json'));
 assert.equal(receipt.status,'failed');assert.equal(receipt.details.inputEvents.filter(e=>e.type==='statueBlessingOpen').length,0);
 assert.equal(x.f.inputs.filter(x=>x.kind==='down').length,0);assert.equal(x.f.metrics.mapCalls,0);
});
test('an unrelated legacy operation still calls existing map and orientation acquisition',async()=>{
 const x=actual({step:'actTwoStatueHeal'}),o=await x.f.adapter.observe('lion-adapter-test',1);
 assert.equal(x.f.metrics.mapCalls,1);assert.equal(x.f.metrics.orientationCalls,1);assert.equal(o.map.map,'Teyvat');
 assert.notEqual(o.timings.mapDiagnostic&&o.timings.mapDiagnostic.mode,'statue-blessing-dialogue-v1');assert.equal(x.calls.length,0);
});
test('complete inventory-only adapter still rejects the new operation at beginMission',()=>{
 const x=actual(),adapter=x.f.context.createActOneAdapter(5,{inventoryUiOnlyV1:true});
 assert.throws(()=>adapter.beginMission({mission:'questStep',step:'statueBlessingOpen',session:'lion-adapter-test',id:'blocked',createdAt:10000}),/Inventory UI-only mode rejects/);
 assert.equal(x.calls.length,0);assert.equal(x.f.metrics.captures,0);assert.equal(x.f.metrics.mapCalls,0);
});


test('actual idle utc source gains no alias until the sole scoped request observes its own source',async()=>{
 const x=actual({idleBootstrap:true,throwGps:true,captureCostMs:25,
  fieldRowsSequence:[recordedIntro(),recordedIntro(),dialogue(),panel(),panel()]});
 assert.equal(await x.run(),'completed');const files=x.f.getVirtualFiles(),receipt=JSON.parse(files.get('receipt.json'));
 const before=JSON.parse(files.get('observations/lion-adapter-test/frame-0001.json')),
  source=JSON.parse(files.get('observations/lion-adapter-test/frame-0002.json'));
 assert.equal(before.hud.auto,false);assert.equal(before.hud.dialogueReady,false);assert.equal(source.hud.auto,true);
 assert.equal(source.hud.dialogueReady,true);assert.deepEqual(source.ocr,recordedIntro());
 assert.deepEqual(Array.from(x.f.inputs.filter(e=>e.kind==='down'),e=>e.key),['VK_SPACE']);assert.equal(x.calls.length,1);
 const advance=receipt.details.inputEvents.find(e=>e.type==='statueBlessingIntroAdvance');assert.equal(advance.frameId,2);
 assert.equal(advance.source.capturedAt,source.hud.captureStamp.capturedAt);assert.equal(advance.target.auto.text,'utc');
 assert.equal(receipt.details.result.panelReady,true);assert.equal(x.f.metrics.statueAutoCropCalls,0);
});
test('actual missing-Auto source uses one scoped same-image crop and keeps every original raw row',async()=>{
 const x=actual({idleBootstrap:true,throwGps:true,captureCostMs:25,
  statueAutoCropRows:[row('Auto',30,30,165,75)],
  fieldRowsSequence:[recordedMissingAuto(),recordedMissingAuto(),dialogue(),panel(),panel()]});
 assert.equal(await x.run(),'completed');const files=x.f.getVirtualFiles(),before=JSON.parse(files.get('observations/lion-adapter-test/frame-0001.json')),
  source=JSON.parse(files.get('observations/lion-adapter-test/frame-0002.json'));
 assert.deepEqual(before.ocr,recordedMissingAuto());assert.equal(before.hud.auto,false);assert.equal(source.hud.auto,true);
 for(const raw of recordedMissingAuto())assert(source.ocr.some(r=>JSON.stringify(r)===JSON.stringify(raw)));
 assert.equal(x.f.metrics.statueAutoCropCalls,1);assert.equal(source.ocr.find(r=>r.text==='Auto').x,100);
 assert.deepEqual(Array.from(x.f.inputs.filter(e=>e.kind==='down'),e=>e.key),['VK_SPACE']);assert.equal(x.calls.length,1);
});
test('actual missing or ambiguous crop remains input-free and cannot use the request-only context as permission',async()=>{
 for(const crop of [[],[row('uto',30,30,165,75)],[row('Auto',30,30,165,75),row('Auto',120,30,165,75)]]){
  const x=actual({idleBootstrap:true,throwGps:true,statueAutoCropRows:crop,
   fieldRowsSequence:[recordedMissingAuto(),recordedMissingAuto()]});await assert.rejects(x.run,/Fresh exact/);
  assert.equal(x.calls.length,0);assert.equal(x.f.inputs.filter(e=>e.kind==='down').length,0);
 }
});
test('only the two Statue steps gain the raw alias and the missing-Auto crop',async()=>{
 for(const step of ['actTwoStatueHeal','actTwoStatueOpen','combatStatueHeal','other']){
  const x=actual({step,throwGps:true,fieldRowsSequence:[recordedIntro()],statueAutoCropRows:[row('Auto',30,30,165,75)]});
  const o=await x.f.adapter.observe('lion-adapter-test',1);assert.equal(o.hud.auto,false);assert.equal(o.hud.dialogueReady,false);
  assert.equal(x.f.metrics.statueAutoCropCalls,0);assert.equal(x.f.inputs.length,0);
 }
 for(const step of ['actTwoStarfellStatueOpen','statueBlessingOpen']){
  const x=actual({step,throwGps:true,fieldRowsSequence:[recordedIntro()]});const o=await x.f.adapter.observe('lion-adapter-test',1);
  assert.equal(o.hud.auto,true);assert.equal(o.hud.dialogueReady,true);assert.equal(x.f.inputs.length,0);
 }
});
test('Statue alias and crop require the same-frame unique original UID and exact speaker geometry',async()=>{
 for(const change of [rows=>rows[1].text='Kaeya',rows=>rows[1].y=500,rows=>rows[2].text='UID: 693306811',rows=>rows.push({...rows[1]})]){
  const rows=recordedIntro();change(rows);const x=actual({throwGps:true,fieldRowsSequence:[rows],statueAutoCropRows:[row('Auto',30,30,165,75)]});
  try{const o=await x.f.adapter.observe('lion-adapter-test',1);assert.equal(o.hud.auto,false);assert.equal(o.hud.dialogueReady,false);}
  catch(e){assert.match(String(e),/original UID/);}assert.equal(x.f.metrics.statueAutoCropCalls,0);assert.equal(x.f.inputs.length,0);
 }
});
test('Starfell opener passes its selected observation explicitly to the F call',async()=>{
 const c={file:{readTextSync:name=>fs.readFileSync(path.join(packageDir,name),'utf8')}};
 vm.runInNewContext(fs.readFileSync(path.join(packageDir,'mission.js'),'utf8'),c);
 const field={session:'selection',frameId:14,timestamp:10000,map:{map:'Teyvat',x:-1324.474,y:2566.115,cameraAngle:180},
  hud:{world:true,groundControls:true,climbing:false,auto:false,dialogueReady:false,choice:false,health:{current:2211,max:4015},enemyBars:[],objectives:[]},
  ocr:[{text:'Statue of The Seven',x:1200,y:510,height:24},{text:'F',x:1120,y:510,height:24},{text:'693306810',x:1732,y:1050}]};
 const keys=[],api={runActTwoNavigationWithPause:async(a,b,run)=>run(field),checkStop(){},sleep:async()=>{},
  keyPress:async(key,source)=>{assert.equal(source,field);keys.push(key);},forward:()=>assert.fail(),rotate:()=>assert.fail()};
 const result=await c.ActOneMission.runQuestStep('actTwoStarfellStatueOpen',{frameId:1},api,async()=>({...field,frameId:15,hud:{...field.hud,dialogueReady:true}}));
 assert.deepEqual(keys,['VK_F']);assert.equal(result.fieldFrameId,15);
});
test('explicit F source is rechecked and recorded while legacy omitted or numeric arguments remain unframed',async()=>{
 for(const mode of ['explicit','omitted','numeric']){
  const x=actual(),o=await x.f.adapter.observe('lion-adapter-test',1);
  await x.f.adapter.keyPress('VK_F',mode==='explicit'?o:mode==='numeric'?100:undefined);
  const e=x.f.adapter.events().find(e=>e.type==='key');assert.equal(e.key,'VK_F');assert.equal(e.durationMs,60);
  assert.equal(e.frameId,mode==='explicit'?1:undefined);
 }
});
test('foreign changed or stale explicit F source refuses without using the global latest frame as provenance',async()=>{
 for(const change of [o=>o.frameId=2,o=>o.session='foreign',o=>o.ocr[0].text='UID: 693306811',o=>o.map={map:'Teyvat',x:1,y:2},
  o=>o.hud.captureStamp.capturedAt=1]){
  const x=actual(),o=JSON.parse(JSON.stringify(await x.f.adapter.observe('lion-adapter-test',1)));change(o);
  await assert.rejects(()=>x.f.adapter.keyPress('VK_F',o),/Explicit key source changed or expired/);assert.equal(x.f.inputs.length,0);
 }
 const x=actual(),o=await x.f.adapter.observe('lion-adapter-test',1);await x.f.context.sleep(1001);
 await assert.rejects(()=>x.f.adapter.keyPress('VK_F',o),/Explicit key source changed or expired/);assert.equal(x.f.inputs.length,0);
});
