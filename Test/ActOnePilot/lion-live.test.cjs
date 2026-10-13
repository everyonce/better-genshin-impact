'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const guard=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/lion-live-guard.js');
const title='Deep Within the Temple of the Lion';
const entry={session:'lion-adapter-test',timestamp:9000,status:'completed',mission:'questStep',details:{result:{step:'lionPartyStart',label:title},inputEvents:[{type:'lionPartyStart',label:title,startedAt:8900}]}};
const source=fs.readFileSync(__dirname+'/lion-field-combat-adapter.test.cjs','utf8'),sandbox={require,module:{exports:{}},__dirname,setImmediate};
vm.runInNewContext(source.slice(0,source.indexOf('\nfunction assertPauseProof'))+'\nmodule.exports={fixture,fieldRows,row};',sandbox);
const {fixture,fieldRows,row}=sandbox.module.exports;
const rows=()=>fieldRows({objectiveText:'',healthText:'1288/1288',extra:[row('Lumina',1656,312,93,21)]}).filter(r=>r.text!=='Meet Lisa at the temple');
function setup(patch={}){
 const session='lion-adapter-test',w={session,frameId:2,timestamp:9900,map:null,hud:{world:false,groundControls:true,climbing:false,health:{current:1288,max:1288}},ocr:rows()};
 return fixture({step:'lionVisualMove',initialFrame:5,expectedFrameId:5,noEnemy:true,throwGps:true,fieldRowsSequence:[rows()],seedFiles:{
  ['reports/'+session+'.json']:[entry],
  ['observations/'+session+'/frame-0002.json']:w,['observations/'+session+'/frame-0002.png']:'field',
  'lion-visual-move.json':{session,frameId:5,witnessFrameId:2,reviewed:true,createdAt:9950,relativeDx:0,holds:2,...patch}}});
}
test('Lion movement requires fresh owned domain HUD and a unique current entry',()=>{
 const o={session:'lion-adapter-test',timestamp:10000,frameId:3,map:null,hud:{world:false,groundControls:true,climbing:false,health:{current:1288,max:1288}},ocr:rows()};
 assert.ok(guard.entry([entry],o.session,o));assert.ok(guard.field(o,10000,o.session));
 assert.equal(guard.entry([entry,entry],o.session,o),false);
 assert.equal(guard.entry([{...entry,session:'other'}],o.session,o),false);
 assert.equal(guard.entry([entry,{session:o.session,details:{inputEvents:[{type:'teleportRecovery',startedAt:9500}]}}],o.session,o),false);
 for(const patch of [{map:{map:'Teyvat'}},{timestamp:8999},{hud:{...o.hud,climbing:true}},{hud:{...o.hud,health:{current:100,max:1288}}}])assert.equal(guard.field({...o,...patch},10000,o.session),false);
});
test('reviewed session handoff requires the exact stopped predecessor and rejects later source activity',()=>{
 const old={...entry,id:'entry'},stop={id:'stop',session:entry.session,status:'failed',timestamp:9500,details:{reason:'Pause protection exhausted: pause is UNVERIFIED; operator intervention required'}};
 const o={session:'new-session',timestamp:10000},handoff={session:o.session,sourceSession:entry.session,entryId:'entry',sourceStopId:'stop',createdAt:9700,reviewed:true};
 assert.ok(guard.entry([old,stop],o.session,o,handoff));
 for(const patch of [{reviewed:false},{sourceStopId:'wrong'},{entryId:'wrong'},{createdAt:10001}])assert.equal(guard.entry([old,stop],o.session,o,{...handoff,...patch}),false);
 assert.equal(guard.entry([old,stop,{session:entry.session,timestamp:9800}],o.session,o,handoff),false);
});
test('captured Lisa trial party requires all four labels, trial marker and active health identity',()=>{
 const o={session:'s',timestamp:1000,frameId:1,map:null,hud:{world:false,groundControls:true,climbing:false,health:{current:1196,max:1196}},
  ocr:[row('Lumina',1682,257),row('Amber',1690,347),row('Kaeya',1694,437),row('Lisa',1690,540),row('Trial',1800,509),row('4',1856,540)]};
 assert.ok(guard.field(o,1000,'s'));
 for(const label of ['Lumina','Amber','Kaeya','Lisa','Trial','4'])assert.equal(guard.field({...o,ocr:o.ocr.filter(r=>r.text!==label)},1000,'s'),false);
 assert.equal(guard.field({...o,hud:{...o.hud,health:{current:1288,max:1288}}},1000,'s'),false);
});
test('Lion adapter bounds movement, releases keys and verifies pause',async()=>{
 const f=setup(),initial=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(initial,f.observe);
 assert.equal(r.moves,2,JSON.stringify(r));assert.equal(r.pauseVerified,true);assert.equal(f.getOverlappingKeyDowns().length,0);
});
test('Lion adapter rejects unreviewed and excessive movement without input',async()=>{
 for(const patch of [{reviewed:false},{holds:9},{relativeDx:751},{usedAt:9900}]){
  const f=setup(patch),o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
  assert.equal(r.moves,0);assert.equal(f.inputs.length,0);
 }
});
test('Lion movement cancels before walking and verifies pause',async()=>{
 const f=setup();f.setFlag('stopAfterClose',true);
 const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
 assert.equal(r.moves,0);assert.equal(r.pauseVerified,true);assert.equal(f.getOverlappingKeyDowns().length,0);
 assert.ok(!f.inputs.some(x=>x.kind==='down'&&x.key==='VK_W'));
});
test('automatic Lisa dialogue settles after a blank transition without entering a pause loop',async()=>{
 const f=setup();f.setFlag('fieldRowsSequence',[rows(),[],[row('Auto',102,32),row('Lisa',926,854),row('I guess I could give this a go.',744,907,443,43)]]);
 const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
 assert.equal(r.moves,1,JSON.stringify(r));assert.equal(r.dialoguePending,true);assert.equal(r.pauseVerified,false);
 assert.equal(f.getOverlappingKeyDowns().length,0);assert.ok(!f.inputs.some(x=>x.kind==='down'&&x.key==='VK_B'));
});
