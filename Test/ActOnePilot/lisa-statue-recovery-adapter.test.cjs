'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

// Reuse the integration fixture without registering or running its Lion tests.
const source=fs.readFileSync(path.join(__dirname,'lion-field-combat-adapter.test.cjs'),'utf8');
const cut=source.indexOf('\nfunction assertPauseProof');
if(cut<0)throw new Error('Lion fixture boundary not found');
function loadFixture(){
  const sandbox={require, module:{exports:{}}, __dirname, setImmediate};
  vm.runInNewContext(source.slice(0,cut)+'\nmodule.exports={fixture,row};',sandbox,
    {filename:'lion-field-combat-adapter.fixture.cjs'});
  return sandbox.module.exports;
}
const {fixture,row}=loadFixture();

function prepare(options={}){
  const healthRows=Array.from({length:30},(_,i)=>row(i<8?'685/1186':'1186/1186',900,1002,120,24));
  const f=fixture({step:'lisaStatueRecovery',noEnemy:true,healthText:'685/1186',
    mapPosition:{x:-1323.474,y:2566.115},fieldRowsSequence:options.unknownUi?undefined:healthRows.map(h=>[
      row('Meet Lisa at the temple',80,250,300,35),row('R',1580,1004,30,30),h,
      row('Amber',1680,415,80,35),row('Q',1660,1004,30,30),row('Kaeya',1660,500,80,35),row('3',1860,500,25,35)
    ]),...options});
  // Low HP requires agreement with the same capture's independently scaled
  // health crop. Keep the original fixture for every other OCR region.
  const OriginalImageRegion=f.context.ImageRegion;
  f.context.ImageRegion=class {
    constructor(mat){this.mat=mat;this.original=new OriginalImageRegion(mat);}
    findMulti(ro){
      const rect=this.mat.rect;
      if(rect&&rect.x===900&&rect.y===990&&rect.w===125&&rect.h===40){
        const health=f.lastRows().filter(r=>r.x===900&&r.y===1002&&/^\d+\/\d+$/.test(r.text));
        const found=health.map(r=>row(r.text,0,30,360,24));found.count=found.length;return found;
      }
      return this.original.findMulti(ro);
    }
    dispose(){this.original.dispose();}
  };
  const originalDown=f.context.keyDown;
  f.context.keyDown=function(key){
    originalDown(key);
    if(key==='VK_M')f.setScreen('map');
  };
  f.context.genshin.tp=async function(x,y,flag){
    f.nativeCalls.push({kind:'tp',x,y,flag});
    if(options.tpFailure)throw new Error('mock teleport failure');
    f.setScreen('field');
  };
  const initialPromise=f.adapter.observe('lion-adapter-test',1);
  async function observe(){
    return f.observe();
  }
  async function run(){
    const initial=await initialPromise;
    return f.adapter.runLisaStatueRecovery(initial,observe);
  }
  return {...f,run,observe};
}

test('low-health Lisa recovery uses food inventory, verifies regional map, and heals at the fixed statue',async()=>{
  const f=prepare();const result=await f.run();
  assert.equal(result.status,'completed',JSON.stringify(result));assert.equal(result.step,'lisaStatueRecovery');
  assert.equal(result.recovered,true);assert.equal(result.teleportAttempted,true);
  assert.equal(result.health.current,1186);
  assert.equal(result.pauseVerified,true);assert.ok(result.pauseProof);
  assert.deepEqual(JSON.parse(JSON.stringify(f.nativeCalls.filter(x=>x&&x.kind==='tp').map(x=>[x.x,x.y,x.flag]))),[[-1323.474,2566.115,false]]);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);
  assert.ok(!f.inputs.some(x=>x.kind==='down'&&['VK_3','VK_F','VK_W','VK_A','VK_S','VK_D'].includes(x.key)));
});

test('the recorded Galesong map without a Mondstadt title supports recovery directly from pause',async()=>{
  const f=prepare({initialScreen:'map',mapRows:[
    row('200/200',1622,28,123,35),row('Windrise',750,274,131,29),row('Falcon Coast',1332,502,191,35),
    row('Elemental Trial',916,590,175,26),row('Cape Oath',1594,828,151,37),row('Dadaupa Gorge',1063,941,231,41),
    row('Galesong Hill',1603,983,191,39),row('Exploration Progress: 0%',1505,1015,291,38),
  ]});
  const result=await f.run();
  assert.equal(result.recovered,true,JSON.stringify(result));assert.equal(result.pauseVerified,true);
  assert.equal(f.nativeCalls.filter(x=>x.kind==='tp').length,1);
  assert.ok(!f.inputs.some(x=>x.kind==='down'&&['VK_ESCAPE','VK_M'].includes(x.key)));
  assert.ok(f.adapter.events().some(e=>e.type==='lisaRecoveryAdoptPausedMap'&&e.inputSent===false));
});

test('native failure from an adopted map still returns only with verified map pause',async()=>{
  const f=prepare({initialScreen:'map',tpFailure:true}),result=await f.run();
  assert.equal(result.recovered,false);assert.equal(result.pauseVerified,true);
  assert.equal(result.pauseProof.kind,'map');
  assert.ok(!f.inputs.some(x=>x.kind==='down'&&['VK_ESCAPE','VK_M'].includes(x.key)));
});

test('failed teleport from the verified map returns only after local pause proof',async()=>{
  const f=prepare({tpFailure:true});const result=await f.run();
  assert.equal(result.pauseVerified,true);assert.ok(result.pauseProof);
  assert.equal(result.status,'stopped');
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='tp').length,1);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='fight').length,0);
});

test('a stopped request after inventory close remains pause protected until proof',async()=>{
  const f=prepare({stopAfterClose:true});const result=await f.run();
  assert.equal(result.pauseVerified,true);assert.ok(result.pauseProof);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='tp').length,0);
});

test('unknown UI after closing inventory cannot return without verified pause',async()=>{
  const f=prepare({unknownUi:true});
  const pending=f.run();
  const deadline=Date.now()+1500;
  while(!f.adapter.events().some(e=>e.type==='pauseProtectionStarted')){
    if(Date.now()>deadline)throw new Error('pause protection did not arm');
    await new Promise(resolve=>setImmediate(resolve));
  }
  // Keep the request pending while the unknown screen is present, then let a fresh
  // grounded field observation provide the pause proof needed to return.
  await new Promise(resolve=>setImmediate(resolve));
  f.setFlag('unknownUi',false);
  const result=await pending;
  assert.equal(result.pauseVerified,true);assert.ok(result.pauseProof);
  assert.equal(f.nativeCalls.filter(x=>x&&x.kind==='tp').length,0);
});

for(const [label,options] of [
  ['Escape keydown exception',{throwCloseKeyDown:true}],
  ['Escape keyup exception',{throwEscapeKeyUpCount:1}],
  ['capture exception after close',{throwObserveCount:1}],
  ['GPS exception after teleport',{throwGps:true}],
  ['GPS outside the fixed Statue radius',{mapPosition:{x:0,y:0}}],
  ['passive healing timeout',{fieldRowsSequence:undefined}],
])test(label+' returns only with a fresh local pause',async()=>{
  const f=prepare(options),result=await f.run();
  assert.equal(result.status,'stopped',JSON.stringify(result));
  assert.equal(result.recovered,false);assert.equal(result.pauseVerified,true);
  assert.ok(result.pauseProof.pauseFrameId>result.pauseProof.sourceFrameId);
  assert.equal(f.nativeCalls.filter(x=>x.kind==='fight').length,0);
  assert.ok(!f.inputs.some(x=>x.kind==='down'&&['VK_2','VK_3','VK_F','VK_W'].includes(x.key)));
  assert.deepEqual(JSON.parse(JSON.stringify(f.getOverlappingKeyDowns())),[]);
});

test('a silent map key falls back to verified Food without teleport',async()=>{
  const f=prepare();
  const original=f.context.keyDown;
  f.context.keyDown=function(key){original(key);if(key==='VK_M')f.setScreen('field');};
  const result=await f.run();
  assert.equal(result.recovered,false);assert.equal(result.pauseVerified,true);
  assert.equal(result.pauseProof.kind,'inventory');
  assert.equal(f.nativeCalls.filter(x=>x.kind==='tp').length,0);
});

for(const [label,flag] of [['wrong-session observations','crossSessionFirstField'],['stale observations','staleObserve']])
test(label+' cannot make the guardian return before fresh proof',async()=>{
  const f=prepare({[flag]:true});let returned=false;
  const pending=f.run().then(result=>{returned=true;return result;});
  const deadline=Date.now()+1500;
  while(!f.adapter.events().some(e=>e.type==='pauseProtectionStarted')){
    if(Date.now()>deadline)throw new Error('pause guardian did not arm');
    await new Promise(setImmediate);
  }
  for(let i=0;i<10;i++)await new Promise(setImmediate);
  assert.equal(returned,false);
  f.setFlag(flag,false);
  const result=await pending;
  assert.equal(result.pauseVerified,true);assert.equal(result.recovered,false);
  assert.equal(f.nativeCalls.filter(x=>x.kind==='tp').length,0);
});

test('lost foreground after native teleport is recovered before verifying pause',async()=>{
  const f=prepare(),tp=f.context.genshin.tp;
  f.context.genshin.tp=async function(...args){await tp(...args);f.setForeground(false);};
  const result=await f.run();
  assert.equal(result.recovered,false);assert.equal(result.pauseVerified,true);
  assert.equal(f.metrics.focusCalls,1);assert.equal(f.getForeground(),true);
});
