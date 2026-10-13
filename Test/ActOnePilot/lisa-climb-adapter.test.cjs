'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'lion-field-combat-adapter.test.cjs'),'utf8');
const sandbox={require,module:{exports:{}},__dirname,setImmediate};
vm.runInNewContext(source.slice(0,source.indexOf('\nfunction assertPauseProof'))+'\nmodule.exports={fixture,row,climbHudRows};',sandbox);
const {fixture,row,climbHudRows}=sandbox.module.exports;
function setup(options={}){
 const session='lion-adapter-test',witness={session,frameId:2,timestamp:9900,map:null,
  hud:{world:true,climbing:true,groundControls:false,auto:false,choice:false,dialogueReady:false,journal:false,bigMap:false,
   objectiveChanged:false,tutorialStep:null,health:{current:876,max:1186},enemyBars:[],objectives:['Meet Lisa at the temple']},ocr:climbHudRows()};
 const f=fixture({step:'lisaClimb',initialFrame:5,expectedFrameId:5,noEnemy:true,fieldRowsSequence:[climbHudRows()],
  seedFiles:{'lisa-climb-witness.json':{session,frameId:5,witnessFrameId:2,reviewed:true,createdAt:9950},
   ['observations/'+session+'/frame-0002.json']:witness,['observations/'+session+'/frame-0002.png']:'climb'},...options});
 f.context.genshin.getPositionFromMap=()=>{if(f.getScreen()!=='field')throw Error('not world');return {x:-1575,y:1666};};
 return f;
}
test('climbing holds are bounded to 6.4 seconds with released keys and verified pause',async()=>{
 const f=setup(),initial=await f.adapter.observe('lion-adapter-test',5),result=await f.adapter.runLisaClimb(initial,f.observe);
 assert.equal(result.holds,8,JSON.stringify(result));assert.equal(result.pauseVerified,true);assert.equal(result.questComplete,false);
 assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_W').length,8);
 assert.equal(f.getOverlappingKeyDowns().length,0);
});
test('unsafe health prevents climbing input after inventory close',async()=>{
 const f=setup({fieldRowsSequence:[climbHudRows({healthText:'400/1186'})]}),initial=await f.adapter.observe('lion-adapter-test',5);
 const result=await f.adapter.runLisaClimb(initial,f.observe);
 assert.equal(result.holds,0);assert.equal(result.pauseVerified,true);
 assert.ok(!f.inputs.some(x=>x.kind==='down'&&x.key==='VK_W'));
});
test('menu transition is observed until climbing controls settle, without blind input',async()=>{
 const f=setup({fieldRowsSequence:[[],climbHudRows()]}),initial=await f.adapter.observe('lion-adapter-test',5);
 const result=await f.adapter.runLisaClimb(initial,f.observe);
 assert.equal(result.holds,8);assert.equal(result.pauseVerified,true);
});
test('cancellation after close never starts climbing and still pauses',async()=>{
 const f=setup({stopAfterClose:true}),initial=await f.adapter.observe('lion-adapter-test',5);
 const result=await f.adapter.runLisaClimb(initial,f.observe);
 assert.equal(result.holds,0);assert.equal(result.pauseVerified,true);
});
