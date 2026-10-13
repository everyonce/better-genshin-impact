'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'lion-field-combat-adapter.test.cjs'),'utf8');
const sandbox={require,module:{exports:{}},__dirname,setImmediate};
vm.runInNewContext(source.slice(0,source.indexOf('\nfunction assertPauseProof'))+'\nmodule.exports={fixture,fieldRows,row};',sandbox);
const {fixture,fieldRows,row}=sandbox.module.exports;
function setup(options={},patch={}){
 const session='lion-adapter-test',witness={session,frameId:2,timestamp:9900,map:null,
  hud:{world:true,climbing:false,groundControls:true,auto:false,choice:false,dialogueReady:false,journal:false,bigMap:false,
   objectiveChanged:false,tutorialStep:null,health:{current:876,max:1186},enemyBars:[],objectives:['Meet Lisa at the temple']},ocr:fieldRows()};
 return fixture({step:'lisaVisualMove',initialFrame:5,expectedFrameId:5,noEnemy:true,
  seedFiles:{'lisa-visual-move.json':{session,frameId:5,witnessFrameId:2,reviewed:true,createdAt:9950,heading:0,holds:8,...patch},
   ['observations/'+session+'/frame-0002.json']:witness,['observations/'+session+'/frame-0002.png']:'field'},...options});
}
async function run(f){const initial=await f.adapter.observe('lion-adapter-test',5);return f.adapter.runLisaVisualMove(initial,f.observe);}
test('reviewed visual movement stays within 6.4 seconds, releases every key, and verifies pause without GPS',async()=>{
 const f=setup(),r=await run(f);assert.equal(r.moves,8,JSON.stringify(r));assert.equal(r.inputMs,6400);
 assert.equal(r.pauseVerified,true);assert.equal(r.questComplete,false);assert.equal(f.getOverlappingKeyDowns().length,0);
 assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_W').length,8);
});
test('unsafe health and cancellation stop before any visual movement and still pause',async()=>{
 for(const options of [{fieldRowsSequence:[fieldRows({healthText:'400/1186'})]},{stopAfterClose:true}]){
  const f=setup(options),r=await run(f);assert.equal(r.moves,0);assert.equal(r.pauseVerified,true);
  assert.ok(!f.inputs.some(x=>x.kind==='down'&&x.key==='VK_W'));
 }
});
test('unreviewed, excessive, expired and invalid heading permits never dismiss inventory',async()=>{
 for(const p of [{reviewed:false},{holds:9},{heading:360},{createdAt:-200000},{usedAt:9999}]){
  const f=setup({},p),r=await run(f);assert.equal(r.moves,0);assert.equal(f.inputs.length,0);
 }
});
test('nonconverging compass has a finite turn budget and pauses',async()=>{
 const f=setup({},{heading:90}),r=await run(f);assert.equal(r.moves,0);assert.equal(r.pauseVerified,true);
 assert.match(r.reason,/converge/);
});

test('same-image control crop recovers omitted Q without a GPS dependency',async()=>{
 const f=setup({omitControls:true,controlCropRows:[row('Q',420,57,90,90)]}),r=await run(f);
 assert.equal(r.moves,8,JSON.stringify(r));assert.ok(f.metrics.controlCropCalls>0);assert.equal(r.pauseVerified,true);
});
