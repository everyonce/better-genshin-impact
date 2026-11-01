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
function actual(options={}){
 let text=fs.readFileSync(fixtureFile,'utf8'),cut=text.indexOf('\nfunction assertPauseProof');assert(cut>0);text=text.slice(0,cut);
 const dir="const dir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');";
 assert(text.includes(dir));text=text.replace(dir,'const dir='+JSON.stringify(packageDir)+';');
 const box={require,module:{exports:{}},__dirname:path.dirname(fixtureFile),setImmediate};
 vm.runInNewContext(text+'\nmodule.exports={fixture};',box,{filename:'inert-statue-adapter-fixture.cjs'});
 const f=box.module.exports.fixture({step:'statueBlessingOpen',noEnemy:true,initialScreen:'field',
  fieldRowsSequence:[dialogue(),dialogue(),panel(),panel()],...options});
 f.context.file.pinCaptureEvidence=()=>{};
 const calls=[];f.context.click=(x,y)=>calls.push({x,y,at:f.getNow()});
 vm.runInNewContext(fs.readFileSync(path.join(packageDir,'mission.js'),'utf8'),f.context);
 const engine=require(path.join(packageDir,'engine.js'));
 const runner=engine.create(f.adapter,{session:'lion-adapter-test',enableInput:true});
 return {f,calls,runner,run:async()=>{await runner.observe();return runner.process({id:'full-adapter-one',session:'lion-adapter-test',
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
