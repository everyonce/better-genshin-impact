// Portable pause-only regression; every native/game boundary is inert.
'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..');
const packageDir=path.join(root,'BetterGenshinImpact/User/JsScript/ActOnePilot');
const source=fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8');
const fixture=require('./fixtures/pause-eq-health-conflict.json');
const clone=o=>JSON.parse(JSON.stringify(o));
// Disable only the new evidence signal to reproduce the preserved R64 refusal.
// This is a counterfactual control, not a second production adapter or a live run.
const legacySource=source+'\nactOneLocalPauseEqPair=function(){return false;};';
const legacyContext={},context={};
vm.runInNewContext(legacySource,legacyContext,{filename:'pause-controls-without-eq-pair.js'});
vm.runInNewContext(source,context,{filename:'canonical-bgi.js'});
const conflicts=fixture.conflictFrames.map(o=>({...clone(o),session:fixture.conflictSession,hud:clone(fixture.conflictHud)}));
const real=conflicts[0],inventory=fixture.inventory;
const ready=o=>context.actOneLocalPauseInputReady(o,o.timestamp,o.session);
const oldReady=o=>legacyContext.actOneLocalPauseInputReady(o,o.timestamp,o.session);

test('all21 actual conflicted-health frames gain only local pause readiness without mutation',()=>{
 assert.equal(conflicts.length,21);
 for(const o of conflicts){
  const before=JSON.stringify(o);
  assert.equal(o.hud.health,null);assert.equal(o.hud.world,false);assert.equal(o.hud.groundControls,false);
  assert.equal(o.hud.healthDiagnostic.decision,'conflict-halves-disagree-or-missing');
  assert.equal(oldReady(o),false);assert.equal(ready(o),true);
  assert.equal(context.actOneGroundControlEvidence(o.ocr),false);
  assert.equal(context.actTwoRegionalWorldEvidence(o.ocr,o.hud),false);
  assert.equal(context.actOneLionFieldWorld(o,o.timestamp,o.session,.01,true),false);
  assert.equal(context.actOneWorldInventoryPauseReady(o,o.timestamp),false);
  assert.equal(JSON.stringify(o),before);
 }
});

test('existing readable-HP and uppercase-control HUD retains its prior readiness',()=>{
 const o=fixture.readableWorld;
 assert.equal(ready(o),true);assert.equal(oldReady(o),true);
 assert.equal(context.actOneGroundControlEvidence(o.ocr),true);
 assert.deepEqual(o.hud.health,{current:2211,max:4015});
 assert.equal(o.hud.world,true);assert.equal(o.hud.groundControls,true);
});

test('new evidence requires the original UID plus the existing independent party signal',()=>{
 for(const mutate of [o=>o.ocr=o.ocr.filter(r=>!String(r.text).includes('693306810')),
  o=>o.ocr=o.ocr.map(r=>({...r,text:String(r.text).replace('693306810','693306811')})),
  o=>o.ocr=o.ocr.filter(r=>!['Amber','Kaeya'].includes(r.text))]){
  const o=clone(real);mutate(o);assert.equal(ready(o),false);
 }
});

test('missing/duplicate/swapped/fuzzy labels cannot create the new pause evidence',()=>{
 for(const mutate of [o=>o.ocr=o.ocr.filter(r=>r.text!=='q'),
  o=>o.ocr.push({...o.ocr.find(r=>r.text==='e')}),
  o=>o.ocr.find(r=>r.text==='q').text='eq',
  o=>o.ocr.find(r=>r.text==='e').text='ｅ',
  o=>{o.ocr.find(r=>r.text==='e').x=1802;o.ocr.find(r=>r.text==='q').x=1684;}]){
  const o=clone(real);mutate(o);assert.equal(ready(o),false);
 }
});

test('keycap geometry and finite numeric metadata are mandatory',()=>{
 for(const patch of [{x:1639},{x:1746},{y:994},{y:1046},{width:9},{width:61},{height:9},{height:46},
  {x:NaN},{width:Infinity},{height:'25'},{y:1013}]){
  const o=clone(real);Object.assign(o.ocr.find(r=>r.text==='e'),patch);assert.equal(ready(o),false,JSON.stringify(patch));
 }
 const o=clone(real);delete o.ocr.find(r=>r.text==='q').width;assert.equal(ready(o),false);
});

test('case normalization is confined to the bounded pause pair',()=>{
 for(const letters of [['e','q'],['E','q'],['e','Q'],['E','Q']]){
  const o=clone(real);o.ocr.find(r=>r.text==='e').text=letters[0];o.ocr.find(r=>r.text==='q').text=letters[1];
  assert.equal(context.actOneLocalPauseEqPair(o.ocr),true);
 }
 const o=clone(real);o.ocr.find(r=>r.text==='q').text='r';assert.equal(context.actOneLocalPauseEqPair(o.ocr),false);
});

test('freshness/session/frame and contradictory UI gates stay strict',()=>{
 for(const change of [{session:'foreign'},{frameId:1.5},{timestamp:real.timestamp+1},{timestamp:real.timestamp-1001}])
  assert.equal(context.actOneLocalPauseInputReady({...real,...change},real.timestamp,real.session),false);
 for(const flag of ['auto','journal','bigMap','dialogueReady','choice','loading','unknownHud','tutorialStep']){
  const o=clone(real);o.hud[flag]=true;assert.equal(ready(o),false,flag);
 }
 for(const text of ['Confirm','Food','Inventory capacity 9/2600','Party Setup','Continue Challenge']){
  const o=clone(real);o.ocr.push({text,x:850,y:550,width:120,height:40});assert.equal(ready(o),false,text);
 }
});

test('a positively paused inventory grants no new toggle',()=>{
 assert(context.actOneLocalPauseProof(inventory,inventory.timestamp,inventory.session));
 assert.equal(ready(inventory),false);assert.equal(oldReady(inventory),false);
});

test('existing known pause fixtures retain their original outcomes',()=>{
 for(const name of ['act-two-hideout-pause.fixture.json','act-two-exam-flight-pause.fixture.json']){
  const o=JSON.parse(fs.readFileSync(path.join(root,'Test/ActOnePilot',name),'utf8'));
  assert.equal(ready(o),oldReady(o),name);
 }
 const o=fixture.readableWorld;assert.equal(ready(o),oldReady(o));
});

// Reuse the established real canonical adapter fixture and local-pause watchdog.
// Only capture/OCR/input/native boundaries are mocked; no installed app is read.
function actualFixture(usePair=true,options={}){
 const fixtureFile=path.join(__dirname,'lion-field-combat-adapter.test.cjs'),sourceText=fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8');
 let source=fs.readFileSync(fixtureFile,'utf8'),cut=source.indexOf('\nfunction assertPauseProof');assert(cut>0);
 source=source.slice(0,cut);
 const evalAnchor="vm.runInNewContext(fs.readFileSync(path.join(dir,'bgi.js'),'utf8'),context);";
 assert(source.includes(evalAnchor));source=source.replace(evalAnchor,'vm.runInNewContext(adapterSource,context);');
 const readAnchor='    readTextSync:p=>{';assert(source.includes(readAnchor));
 source=source.replace(readAnchor,readAnchor+"\n      if(p==='bgi.js')return adapterSource;");
 const box={require,module:{exports:{}},__dirname:path.dirname(fixtureFile),setImmediate,adapterSource:usePair?sourceText:legacySource};
 vm.runInNewContext(source+'\nmodule.exports={fixture,row};',box,{filename:'inert-real-adapter-fixture.cjs'});
 const rows=clone(real.ocr);if(options.missingQ)rows.splice(rows.findIndex(r=>r.text==='q'),1);
 if(options.unknownMenu)rows.push({text:'Confirm',x:850,y:550,width:120,height:40});
 const map=fixture.map;
 const f=box.module.exports.fixture({step:'actTwoWindriseTeleport',noEnemy:true,initialScreen:'map',
  mapRows:map.ocr,fieldRowsSequence:[rows],...options});
 const OriginalRegion=f.context.ImageRegion;
 f.context.ImageRegion=class{
  constructor(mat){this.mat=mat;this.original=new OriginalRegion(mat);}
  findMulti(ro){const rect=this.mat.rect;let texts=null;
   if(f.getScreen()==='field'&&rect){
    if(rect.x===900&&rect.y===990&&rect.w===125)texts=real.hud.healthDiagnostic.primary;
    if(rect.x===893&&rect.y===998&&rect.w===65)texts=real.hud.healthDiagnostic.left;
    if(rect.x===967&&rect.y===998&&rect.w===65)texts=real.hud.healthDiagnostic.right;
   }
   if(texts){const result=texts.map(text=>box.module.exports.row(text,0,0,150,24));result.count=result.length;return result;}
   return this.original.findMulti(ro);
  }
  dispose(){this.original.dispose();}
 };
 f.context.genshin.getPositionFromMap=()=>{
  if(f.getScreen()!=='field')throw Error('Inert map UI has no world pose');
  return {x:real.map.x,y:real.map.y};
 };
 f.context.genshin.tp=async(x,y,flag)=>{f.nativeCalls.push({kind:'tp',x,y,flag});f.setScreen('field');};
 return f;
}

async function runTeleport(f){
 const initial=await f.adapter.observe('lion-adapter-test',1);
 return f.adapter.runLisaWindriseTeleport(initial,f.observe);
}

test('disabling the new pair reproduces the original zero-key bounded safety failure',async()=>{
 const f=actualFixture(false);
 await assert.rejects(runTeleport(f),e=>e.code==='PAUSE_PROTECTION_EXHAUSTED');
 assert.equal(f.inputs.filter(x=>x.kind==='down').length,0);assert.equal(f.nativeCalls.length,1);
 assert(f.observations.some(o=>o.hud.health===null&&o.hud.healthDiagnostic.decision==='conflict-halves-disagree-or-missing'));
});

test('real adapter/watchdog pauses once while arrival and HP remain unverified',async()=>{
 const f=actualFixture(),seen=[],originalReady=f.adapter.pauseInputReady;
 f.adapter.pauseInputReady=function(o){const answer=originalReady.call(this,o);seen.push({frame:o.frameId,answer,hud:clone(o.hud)});return answer;};
 const result=await runTeleport(f);
 assert.equal(result.status,'stopped');assert.equal(result.destinationReached,false);assert.equal(result.fieldHealth,null);
 assert.equal(result.pauseVerified,true);assert.equal(result.pauseProof.kind,'inventory');
 assert.deepEqual(Array.from(f.inputs.filter(x=>x.kind==='down'),x=>x.key),['VK_B']);
 assert.equal(f.getOverlappingKeyDowns().length,0);assert.equal(f.nativeCalls.length,1);
 assert(seen.some(x=>x.answer&&x.hud.health===null&&x.hud.world===false&&x.hud.groundControls===false));
 assert.equal(f.metrics.controlCropCalls,0);
 const key=f.adapter.events().find(x=>x.type==='key');
 assert.equal(key.durationMs,60);assert(key.finishedAt>=key.startedAt+60);
 assert(result.pauseProof.pauseFrameId>key.frameId);assert(result.pauseProof.timestamp>=key.finishedAt);
 for(const o of f.observations.filter(o=>o.hud.healthDiagnostic?.decision==='conflict-halves-disagree-or-missing')){
  assert.equal(o.hud.health,null);assert.equal(o.hud.world,false);assert.equal(o.hud.groundControls,false);
 }
});

test('real adapter rejects pause keys outside armed protection and rejects older active frames',async()=>{
 const f=actualFixture();const initial=await f.adapter.observe('lion-adapter-test',1);
 assert.equal(f.adapter.pauseInputReady(initial),false);
 await assert.rejects(f.adapter.pauseKey(initial,'VK_B'),/Fresh pinned/);
 const originalReady=f.adapter.pauseInputReady;let checked=0;
 f.adapter.pauseInputReady=function(o){
  assert.equal(originalReady.call(this,{...o,frameId:o.frameId-1}),false);
  assert.equal(originalReady.call(this,{...o,session:'foreign'}),false);checked++;return originalReady.call(this,o);
 };
 await f.adapter.runLisaWindriseTeleport(initial,f.observe);
 assert(checked>0);assert.deepEqual(Array.from(f.inputs.filter(x=>x.kind==='down'),x=>x.key),['VK_B']);
});

test('real missing-pair scene still times out with zero input',async()=>{
 const f=actualFixture(true,{missingQ:true});
 await assert.rejects(runTeleport(f),e=>e.code==='PAUSE_PROTECTION_EXHAUSTED');
 assert.equal(f.inputs.filter(x=>x.kind==='down').length,0);
});

test('real adapter refuses an unknown menu despite the otherwise valid pair',async()=>{
 const f=actualFixture(true,{unknownMenu:true});
 await assert.rejects(runTeleport(f),e=>e.code==='PAUSE_PROTECTION_EXHAUSTED');
 assert.equal(f.inputs.filter(x=>x.kind==='down').length,0);
});
