'use strict';
// All game, capture, input, native, and output-file boundaries are inert callbacks.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const candidate=path.resolve(__dirname,'../..'),root=process.env.BETTERGI_REPOSITORY_ROOT||candidate;
const packageDir=path.join(candidate,'BetterGenshinImpact/User/JsScript/ActOnePilot');
const read=n=>fs.readFileSync(path.join(packageDir,n),'utf8');
const source=read('bgi.js'),engine=require(path.join(packageDir,'engine.js'));
const recorded=require('./fixtures/inventory-ui-r67-admission-timing.fixture.json');
const row=(text,x,y,width=80,height=24)=>({text,x,y,width,height});
const core=['main.js','engine.js','bgi.js','mission.js','combat.js','recovery.js'];
const context={};vm.runInNewContext(source,context);

function originalHash(text){
 let hash=2166136261;
 for(let c=0;c<text.length;c++)hash=Math.imul(hash^text.charCodeAt(c),16777619)>>>0;
 return hash;
}

function actual(mode=true){
 const file=path.join(root,'Test/ActOnePilot/lion-field-combat-adapter.test.cjs');
 let text=fs.readFileSync(file,'utf8');text=text.slice(0,text.indexOf('\nfunction assertPauseProof'));
 text=text.replace("const dir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');",'const dir='+JSON.stringify(packageDir)+';');
 text=text.replace('const adapter=context.createActOneAdapter(5);','const adapter=context.createActOneAdapter(5,{inventoryUiOnlyV1:options.uiMode});');
 const box={require,module:{exports:{}},__dirname:path.dirname(file),setImmediate};
 vm.runInNewContext(text+'\nmodule.exports=fixture;',box);
 const result=box.module.exports({uiMode:mode,step:'worldInventory',initialScreen:'field',noEnemy:true,throwGps:mode,
  extra:[row('UID: 693306810',1680,1050,180,25)]});
 result.context.file.pinCaptureEvidence=()=>{};return result;
}

test('UI-only FNV is exactly the original UTF-16 arithmetic for all package sources and edge strings',()=>{
 const names=fs.readdirSync(packageDir).filter(n=>n.endsWith('.js'));
 const values=names.map(read).concat(['','\u0000','\ud800','\udc00','\ud83d\ude00','中文\r\nEnglish','a'.repeat(4097)]);
 for(const text of values)assert.equal(context.actOneInventoryUiRevisionHash(text),originalHash(text));
});

test('every exact source is still reread, rehashed and retained in its original revision path',()=>{
 const f=actual(),reads=[],rawRead=f.context.file.readTextSync;
 f.context.file.readTextSync=n=>{reads.push(n);return rawRead(n);};
 const value={id:'source-check',mission:'observe',session:'inert',expectedFrameId:1,createdAt:f.getNow()};
 f.adapter.beginMission(value);
 const first=JSON.parse(JSON.stringify(f.adapter.events()[0]));
 assert.deepEqual(Object.keys(first),['type','files','startedAt']);assert.deepEqual(reads,core);
 for(const name of core){
  const text=read(name),revision=originalHash(text).toString(16);
  assert.equal(first.files[name],revision);assert.equal(f.getVirtualFiles().get('revisions/'+revision+'/'+name+'.txt'),text);
 }
 const changed=read('mission.js')+'\n// Inert changed source.\n';
 f.getVirtualFiles().set('mission.js',changed);reads.length=0;f.adapter.beginMission({...value,id:'changed-source'});
 const second=f.adapter.events()[0];assert.deepEqual(reads,core);
 assert.equal(second.files['mission.js'],originalHash(changed).toString(16));assert.notEqual(second.files['mission.js'],first.files['mission.js']);
 assert.equal(f.getVirtualFiles().get('revisions/'+second.files['mission.js']+'/mission.js.txt'),changed);
 assert.equal(f.inputs.length,0);
});

test('legacy modes do not call the new UI-only helper',()=>{
 const f=actual(false);f.context.actOneInventoryUiRevisionHash=()=>{throw Error('UI-only branch reached');};
 f.adapter.beginMission({id:'legacy',mission:'observe',session:'inert',createdAt:f.getNow()});
 for(const name of core)assert.equal(f.adapter.events()[0].files[name],originalHash(read(name)).toString(16));
 assert.equal(f.inputs.length,0);
});

test('inventory close still reads and archives its exact seventh world-inventory source',()=>{
 const f=actual(),reads=[],rawRead=f.context.file.readTextSync;
 f.context.file.readTextSync=n=>{reads.push(n);return rawRead(n);};
 const request={id:'close-revisions',mission:'questStep',step:'worldInventoryClose',session:'inert',createdAt:f.getNow()};
 f.adapter.beginMission(request);assert.deepEqual(reads,core.concat(['world-inventory.js']));
 const first=f.adapter.events()[0].files['world-inventory.js'];
 assert.equal(first,originalHash(read('world-inventory.js')).toString(16));
 const changed=read('world-inventory.js')+'\n// Inert changed seventh source.\n';
 f.getVirtualFiles().set('world-inventory.js',changed);reads.length=0;f.adapter.beginMission({...request,id:'close-revisions-changed'});
 const next=f.adapter.events()[0].files['world-inventory.js'];
 assert.deepEqual(reads,core.concat(['world-inventory.js']));assert.notEqual(next,first);
 assert.equal(next,originalHash(changed).toString(16));
 assert.equal(f.getVirtualFiles().get('revisions/'+next+'/world-inventory.js.txt'),changed);assert.equal(f.inputs.length,0);
});

async function timingBoundary(age){
 const f=actual();let now=recorded.before.uiObservation.observationStartedAtUnixMs,captures=0,observations=0;
 const capture=f.context.captureGameRegion;
 f.context.Date.now=()=>now;f.context.sleep=async ms=>{now+=ms;};
 f.context.captureGameRegion=()=>{const value=capture();now+=(++captures===1?recorded.before.timings.totalMs:335);return value;};
 const observe=f.adapter.observe;
 f.adapter.observe=async(...args)=>{if(++observations===2)now+=12;return observe(...args);};
 const runner=engine.create(f.adapter,{session:recorded.request.session,enableInput:true,inventoryUiOnlyV1:true});
 const before=await runner.observe();assert.equal(before.timestamp,recorded.before.timestamp);
 assert.equal(before.uiObservation.observationStartedAtUnixMs,recorded.before.uiObservation.observationStartedAtUnixMs);
 now=recorded.request.createdAt;
 const readSource=f.context.file.readTextSync;
 f.context.file.readTextSync=n=>{const text=readSource(n);if(n==='main.js')now=before.uiObservation.observationStartedAtUnixMs+age;return text;};
 const request={...recorded.request,id:'age-'+age};
 const result=await runner.process(request,()=>require(path.join(packageDir,'mission.js')));
 const receipt=JSON.parse(f.getVirtualFiles().get('receipts/'+request.session+'/'+request.id+'.json'));
 const revision=receipt.details.inputEvents.find(e=>e.type==='controllerRevision');
 assert.equal(revision.startedAt,before.uiObservation.observationStartedAtUnixMs+age);
 const keys=receipt.details.inputEvents.filter(e=>e.type==='key');
 if(age>1000){assert.equal(result,'stopped');assert.deepEqual(keys,[]);assert.equal(f.inputs.length,0);}
 else {assert.equal(result,'completed');assert.equal(keys.length,1);assert.equal(keys[0].key,'VK_B');assert.equal(keys[0].durationMs,60);}
 return {f,before,receipt,revision};
}

test('retained R67 1058ms admission still refuses B despite its later fresh positive frame',async()=>{
 const age=recorded.receipt.details.inputEvents[0].startedAt-recorded.before.uiObservation.observationStartedAtUnixMs;
 assert.equal(age,1058);const {f,revision}=await timingBoundary(age);
 assert.equal(revision.startedAt,recorded.receipt.details.inputEvents[0].startedAt);
 const next=JSON.parse(f.getVirtualFiles().get('observations/'+recorded.request.session+'/frame-0002.json'));
 assert.equal(next.timestamp,recorded.frame2.timestamp);assert.equal(next.hud.world,true);
 assert.equal(next.timings.totalMs,335);assert.equal(f.inputs.length,0);
});

test('original source age1000 remains eligible and1001 refuses after source checks',async()=>{
 await timingBoundary(1000);await timingBoundary(1001);
});

test('failed revision archive cannot reach UI input',async()=>{
 const f=actual();const originalExists=f.context.file.isExists,originalWrite=f.context.file.writeTextSync;
 f.context.file.isExists=p=>p.startsWith('revisions/')?false:originalExists(p);
 f.context.file.writeTextSync=(p,v)=>p.startsWith('revisions/')?false:originalWrite(p,v);
 assert.throws(()=>f.adapter.beginMission({id:'archive-failure',mission:'observe',session:'inert',createdAt:f.getNow()}),/preserve controller revision/);
 assert.equal(f.inputs.length,0);
});
