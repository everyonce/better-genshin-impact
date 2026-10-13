'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'lion-field-combat-adapter.test.cjs'),'utf8');
const sandbox={require,module:{exports:{}},__dirname,setImmediate};
vm.runInNewContext(source.slice(0,source.indexOf('\nfunction assertPauseProof'))+'\nmodule.exports={fixture,fieldRows,row};',sandbox);
const {fixture,fieldRows,row}=sandbox.module.exports;
function setup(patch={},options={}){
 const session='lion-adapter-test',w={session,frameId:2,timestamp:9900,map:null,
  hud:{groundControls:true,climbing:false,auto:false,choice:false,dialogueReady:false,journal:false,bigMap:false,
   health:{current:1288,max:1288},objectives:['Meet Lisa at the temple']},ocr:fieldRows({healthText:'1288/1288'})};
 return fixture({step:'lisaGlide',initialFrame:5,expectedFrameId:5,noEnemy:true,fieldRowsSequence:[fieldRows({healthText:'1288/1288'})],
  seedFiles:{'lisa-glide.json':{session,frameId:5,witnessFrameId:2,reviewed:true,createdAt:9950,action:'launch',relativeDx:0,holds:8,...patch},
   [`observations/${session}/frame-0002.json`]:w,[`observations/${session}/frame-0002.png`]:'field'},...options});
}
async function run(f){return f.adapter.runLisaGlide(await f.adapter.observe('lion-adapter-test',5),f.observe);}
test('bounded launch releases both Space pulses and forward, then stops on grounded HUD and pauses',async()=>{
 const f=setup(),r=await run(f);assert.equal(r.launchAttempted,true,JSON.stringify(r));assert.equal(r.moves,0);
 assert.equal(r.groundVerified,true);assert.equal(r.pauseVerified,true);assert.equal(f.getOverlappingKeyDowns().length,0);
 assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_SPACE').length,2);
 assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_W').length,1);
});
test('expired, unreviewed, reused, wrong-phase and excessive permits never unpause',async()=>{
 for(const p of [{reviewed:false},{createdAt:0-200000},{usedAt:9999},{action:'continue'},{holds:9},{relativeDx:751},{session:'foreign'}]){
  const f=setup(p),r=await run(f);assert.equal(r.launchAttempted,false);assert.equal(f.inputs.length,0);
 }
});
test('unsafe resumed field sends no launch and still verifies pause',async()=>{
 const f=setup({}, {fieldRowsSequence:[fieldRows({healthText:'400/1288'})]}),r=await run(f);
 assert.equal(r.launchAttempted,false);assert.equal(r.pauseVerified,true);assert.ok(!f.inputs.some(x=>x.kind==='down'&&x.key==='VK_SPACE'));
});
test('airborne guard requires fresh owned Traveler, exact Lisa objective, Space and all party names',()=>{
 const f=setup(),now=f.context.Date.now(),o={session:'lion-adapter-test',frameId:8,timestamp:now,hud:{groundControls:false,climbing:false,
  health:{current:1288,max:1288},objectives:['Meet Lisa at the temple']},ocr:[row('Lumina',1650,312),row('Amber',1680,400),row('Kaeya',1680,480),row('Space',1700,1025)]};
 assert.equal(f.context.actOneLisaAirfield(o,now,o.session),true);
 for(const bad of [{...o,timestamp:now-1001},{...o,session:'foreign'},{...o,ocr:o.ocr.slice(0,3)},
  {...o,hud:{...o.hud,climbing:true}},{...o,hud:{...o.hud,health:{current:1288,max:1427}}},
  {...o,hud:{...o.hud,objectives:['Enter the temple']}},{...o,hud:{...o.hud,choice:true}}])
   assert.equal(f.context.actOneLisaAirfield(bad,now,o.session),false);
});
