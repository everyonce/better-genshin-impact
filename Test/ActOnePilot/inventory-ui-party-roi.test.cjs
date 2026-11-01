'use strict';
// Retained full-frame OCR and the explicitly named native fixture are measured.
// Other enlarged OCR values are inert boundary fixtures; no test launches OCR or the game.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..');
const dir=path.join(root,'BetterGenshinImpact/User/JsScript/ActOnePilot');
const source=fs.readFileSync(path.join(dir,'bgi.js'),'utf8');
const recorded=require('./fixtures/inventory-ui-party-r66.fixture.json');
const native=require('./fixtures/inventory-ui-party-roi-r66-native.fixture.json');
const clone=v=>JSON.parse(JSON.stringify(v));
const context={};vm.runInNewContext(source,context);
const row=(text,x,y,width=80,height=24)=>({text,x,y,width,height});
const strip={x:1640,y:240,width:140,height:350,scale:3};
const expected=[row('Lumina',1682,260,79,23),row('Amber',1690,351,65,23),
 row('Kaeya',1670,447,75,25),row('Lisa',1717,533,43,25)];
const scaled=rows=>rows.map(r=>({...r,x:(r.x-strip.x)*3,y:(r.y-strip.y)*3,width:r.width*3,height:r.height*3}));
const fixturePath=path.join(root,'Test/ActOnePilot/lion-field-combat-adapter.test.cjs');

function actual(options={}){
 let text=fs.readFileSync(fixturePath,'utf8'),cut=text.indexOf('\nfunction assertPauseProof');assert(cut>0);text=text.slice(0,cut);
 const directoryLine="const dir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');";
 assert(text.includes(directoryLine));text=text.replace(directoryLine,'const dir='+JSON.stringify(dir)+';');
 const createLine='const adapter=context.createActOneAdapter(5);';assert(text.includes(createLine));
 text=text.replace(createLine,'const adapter=context.createActOneAdapter(5,{inventoryUiOnlyV1:options.inventoryUiOnlyV1!==false});');
 const box={require,module:{exports:{}},__dirname:path.dirname(fixturePath),setImmediate};
 vm.runInNewContext(text+'\nmodule.exports={fixture,row};',box,{filename:'inert-ui-party-adapter.cjs'});
 const f=box.module.exports.fixture({step:'worldInventoryClose',noEnemy:true,initialScreen:'field',
  fieldRowsSequence:[clone(recorded.ocr)],...options});
 f.context.file.pinCaptureEvidence=()=>{};
 const oldCapture=f.context.captureGameRegion,OldRegion=f.context.ImageRegion,OldDate=f.context.Date;
 let offset=0,captureId=0;
 const trace={roiCalls:[],disposals:[],captures:[]};
 f.context.Date=class extends OldDate{static now(){return OldDate.now()+offset;}};
 f.context.captureGameRegion=()=>{
  const image=oldCapture(),id=++captureId,oldCrop=image.deriveCrop,oldDispose=image.dispose;
  trace.captures.push(id);
  image.deriveCrop=(x,y,w,h)=>{
   const crop=oldCrop(x,y,w,h),prior=crop.dispose;
   crop.srcMat.rect.captureId=id;
   crop.dispose=()=>{trace.disposals.push({kind:'crop',x,y,w,h,id});prior();};
   return crop;
  };
  image.dispose=()=>{trace.disposals.push({kind:'image',id});oldDispose();};
  return image;
 };
 f.context.ImageRegion=class extends OldRegion{
  findMulti(ro){
   const rect=this.srcMat.rect;
   if(rect&&rect.x===strip.x&&rect.y===strip.y&&rect.w===strip.width&&rect.h===strip.height){
    trace.roiCalls.push({rect:clone(rect),request:clone(ro)});offset+=options.roiDurationMs||37;
    if(options.throwParty)throw new Error('inert party OCR failure');
    const values=options.roiByCapture?options.roiByCapture[rect.captureId-1]:options.roiRows;
    const result=clone(values===undefined?scaled(expected):values);result.count=result.length;return result;
   }
   if(rect&&rect.x===900&&rect.y===990&&rect.w===125&&rect.h===40){
    const result=options.healthCrop===false?[]:[row('2211/4015',30,30,290,60)];result.count=result.length;return result;
   }
   return super.findMulti(ro);
  }
  dispose(){trace.disposals.push({kind:'scaled',rect:clone(this.srcMat.rect)});super.dispose();}
 };
 return {...f,trace,currentNow:()=>f.context.Date.now()};
}

test('actual retained-image R66 CPU OCR resolves all four names in the exact3x strip',()=>{
 assert.equal(native.status,'completed');assert.equal(native.gameAttached,false);assert.equal(native.inputCalls,0);
 assert.equal(native.modelLoads,1);assert.equal(native.inferenceCalls,2);assert.equal(native.serviceDisposed,true);
 assert.equal(native.imageSha256,'26ff2fa739bfab5d533999c85b1436e4320508132d517593e5491bdb774fc01b');
 assert.deepEqual(native.region,{x:1640,y:240,width:140,height:350});assert.equal(native.scale,3);
 assert.deepEqual(native.fullFrameRows.filter(r=>['Lumina','Ambe','Amber','Kaeya','Lisa'].includes(r.text)).map(r=>r.text),['Lumina','Ambe']);
 assert.deepEqual(native.stripRows.map(r=>r.text),['Lumina','Amber','Kaeya','Lisa']);
 assert(native.stripRows.every(r=>r.score>.99));assert.equal(native.inputsUnchanged,true);
 const joined=context.actOneMergeInventoryUiPartyRows(recorded.ocr,native.stripRows);
 assert.equal(context.actOneInventoryUiWorldEvidence(joined.rows,recorded.hud),true);
 assert.deepEqual(clone(joined.addedRows).map(r=>r.text),['Amber','Kaeya','Lisa']);
 const lisa=joined.addedRows.find(r=>r.text==='Lisa');
 assert.equal(lisa.x,1640+235/3);assert.equal(lisa.y,240+872/3);
});

test('retained R66 false-negative is missing exact names, not UID/health/EQ',()=>{
 assert.equal(recorded.timestamp-recorded.uiObservation.observationStartedAtUnixMs,325);
 assert.equal(recorded.hud.world,false);assert.deepEqual(recorded.hud.health,{current:2211,max:4015});
 assert(recorded.ocr.some(r=>r.text==='Ambe'));assert.equal(context.actOneInventoryUiWorldEvidence(recorded.ocr,recorded.hud),false);
 assert.equal(context.actOneInventoryUiPartyCropNeeded(recorded.ocr,recorded.hud),true);
 const prior=JSON.stringify(recorded),m=context.actOneMergeInventoryUiPartyRows(recorded.ocr,scaled(expected));
 assert.equal(JSON.stringify(recorded),prior);
 assert.deepEqual(clone(m.rows.slice(0,recorded.ocr.length)),recorded.ocr);
 assert.deepEqual(clone(m.addedRows),expected.slice(1));
 assert.equal(context.actOneInventoryUiWorldEvidence(m.rows,recorded.hud),true);
});

test('merge accepts exact unique names only and preserves partial/duplicate full OCR',()=>{
 const m=context.actOneMergeInventoryUiPartyRows(recorded.ocr,[...scaled([expected[1],expected[1]]),
  row('Ambe',10,10),row('lisa',10,20),row('Lisa 4',10,30),row('Traveler!',10,40)]);
 assert.deepEqual(clone(m.addedRows),[]);assert.deepEqual(clone(m.rows),recorded.ocr);
 const repeated=[recorded.ocr[0],clone(recorded.ocr[0])];
 const d=context.actOneMergeInventoryUiPartyRows(repeated,scaled([expected[0]]));
 assert.equal(d.rows.length,2);assert.equal(context.actOneInventoryUiWorldEvidence(d.rows,recorded.hud),false);
});

test('scaled coordinates must be finite, positive and entirely within the exact strip',()=>{
 for(const mutate of [r=>r.x=-1,r=>r.y=-1,r=>r.x=420,r=>r.y=1050,r=>r.width=0,r=>r.height=-1,
  r=>r.width=421,r=>r.height=1051,r=>r.x=NaN,r=>r.y=Infinity,r=>r.width='30']){
  const r=scaled([expected[3]])[0];mutate(r);
  assert.equal(context.actOneMergeInventoryUiPartyRows(recorded.ocr,[r]).addedRows.length,0);
 }
 const edge=row('Lisa',0,0,420,1050);
 assert.deepEqual(clone(context.actOneMergeInventoryUiPartyRows([], [edge]).addedRows),[row('Lisa',1640,240,140,350)]);
});

test('the actual adapter makes exactly one same-capture crop and retains transformed label/timing provenance',async()=>{
 const f=actual(),o=await f.observe();
 assert.equal(o.hud.world,true);assert.deepEqual(clone(o.hud.health),{current:2211,max:4015});
 assert.deepEqual(f.trace.captures,[1]);assert.equal(f.trace.roiCalls.length,1);
 assert.deepEqual(f.trace.roiCalls[0],{rect:{x:1640,y:240,w:140,h:350,captureId:1},request:{x:0,y:0,w:420,h:1050}});
 const d=o.hud.partyNameOcr;
 assert.equal(d.session,o.session);assert.equal(d.frameId,o.frameId);
 assert.equal(d.observationStartedAtUnixMs,o.uiObservation.observationStartedAtUnixMs);
 assert.equal(d.observationStartedAtUnixMs,o.capturedAt);assert.equal(d.finishedAtUnixMs-d.startedAtUnixMs,37);
 assert.equal(o.timings.partyNameOcrMs,37);assert(o.timings.ocrFindMultiMs>=37);
 assert.deepEqual(clone(d.region),{x:1640,y:240,width:140,height:350});assert.equal(d.scale,3);
 assert.deepEqual(clone(d.rawRows),scaled(expected));assert.deepEqual(clone(d.addedRows),expected.slice(1));
 assert.deepEqual(Object.keys(o.uiObservation).sort(),['kind','mapOmitted','observationStartedAtUnixMs','orientationOmitted','version']);
 assert.equal(f.metrics.mapCalls,0);assert.equal(f.metrics.orientationCalls,0);assert.deepEqual(clone(f.inputs),[]);
});

test('a fresh second capture cannot inherit the repaired roster from the first',async()=>{
 const f=actual({roiByCapture:[scaled(expected),[]]}),first=await f.observe(),second=await f.observe();
 assert.equal(first.hud.world,true);assert.equal(second.hud.world,false);
 assert.equal(second.hud.partyNameOcr.frameId,second.frameId);assert.notEqual(first.frameId,second.frameId);
 assert.deepEqual(clone(second.hud.partyNameOcr.addedRows),[]);
 assert.equal(second.ocr.some(r=>r.text==='Lisa'),false);assert.equal(f.trace.roiCalls.length,2);
 assert.deepEqual(f.trace.roiCalls.map(r=>r.rect.captureId),[1,2]);
});

test('all four original names avoid a redundant crop; legacy mode remains untouched',async()=>{
 const rows=[...recorded.ocr.filter(r=>r.text!=='Ambe'),...expected.slice(1)];
 const f=actual({fieldRowsSequence:[rows]}),o=await f.observe();
 assert.equal(o.hud.world,true);assert.equal(f.trace.roiCalls.length,0);assert.equal(o.timings.partyNameOcrMs,0);
 assert.equal(o.hud.partyNameOcr,undefined);
 const legacy=actual({inventoryUiOnlyV1:false}),old=await legacy.observe();
 assert.equal(legacy.trace.roiCalls.length,0);assert.equal(old.hud.partyNameOcr,undefined);
 assert.equal(old.timings.partyNameOcrMs,undefined);assert.equal(old.uiObservation,undefined);
});

test('missing UID, controls or corroborated health never trigger the repair or qualify world',async()=>{
 const cases=[recorded.ocr.filter(r=>!r.text.startsWith('UID:')),
  recorded.ocr.map(r=>r.text.startsWith('UID:')?{...r,text:'UID: 123456789'}:r),
  recorded.ocr.filter(r=>!/^[EeQq]$/.test(r.text)),
  recorded.ocr.filter(r=>!r.text.includes('4015'))];
 for(let index=0;index<cases.length;index++){
  const f=actual({fieldRowsSequence:[cases[index]],healthCrop:index===3?false:undefined}),o=await f.observe();
  assert.equal(f.trace.roiCalls.length,0,'case '+index);assert.equal(o.hud.world,false,'case '+index);assert.deepEqual(clone(f.inputs),[]);
 }
});

test('same-image menu, dialogue, loading, climbing and unknown markers refuse party repair',async()=>{
 for(const extra of [row('Food',140,32),row('Inventory capacity 9/2600',1504,34,295),row('In Progress',130,45),
  row('Teyvat',1600,990),row('Party Setup',120,80),row('Loading',850,550),row('Login',850,550),
  row('Confirm',850,550),row('Space',1680,1024),row('Auto',50,50)]){
  const f=actual({fieldRowsSequence:[[...recorded.ocr,extra]]}),o=await f.observe();
  assert.equal(f.trace.roiCalls.length,0,extra.text);assert.equal(o.hud.world,false,extra.text);assert.deepEqual(clone(f.inputs),[]);
 }
});

test('ROI time consumes the unchanged original capture freshness budget',async()=>{
 for(const delay of [1000,1001]){
  const f=actual({roiDurationMs:delay}),o=await f.observe();assert.equal(o.hud.world,true);
  assert.equal(f.context.actOneInventoryUiInputFresh(o,f.currentNow(),o.session),delay===1000);
  assert.equal(f.context.actOneInventoryUiInputFresh(o,f.currentNow(),'foreign'),false);
  assert.deepEqual(clone(f.inputs),[]);
 }
});

test('OCR failure disposes the same-image resources and sends no input',async()=>{
 const f=actual({throwParty:true});await assert.rejects(f.observe(),/inert party OCR failure/);
 assert.equal(f.trace.roiCalls.length,1);assert.deepEqual(clone(f.inputs),[]);
 assert.equal(f.trace.disposals.filter(r=>r.kind==='image').length,1);
 assert.equal(f.trace.disposals.filter(r=>r.kind==='crop'&&r.x===1640).length,1);
 assert.equal(f.trace.disposals.filter(r=>r.kind==='scaled'&&r.rect.x===1640).length,1);
});

test('the single ROI is bounded to32 OCR rows and refuses an oversized result',async()=>{
 const noise=Array.from({length:33},()=>row('noise',0,0,1,1));
 assert.equal(context.actOneMergeInventoryUiPartyRows(recorded.ocr,noise.slice(0,32)).addedRows.length,0);
 const f=actual({roiRows:noise});await assert.rejects(f.observe(),/exceeded its row bound/);
 assert.equal(f.trace.roiCalls.length,1);assert.equal(f.trace.disposals.filter(r=>r.kind==='image').length,1);
 assert.deepEqual(clone(f.inputs),[]);
});
