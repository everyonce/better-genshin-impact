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
  if(options.journalRows){const capture=f.context.captureGameRegion;
    f.context.captureGameRegion=function(){const img=capture();if(f.getScreen()==='journal')img.findMulti=function(ro){
      const rows=options.journalRows.filter(r=>r.x>=ro.x&&r.x<ro.x+ro.w&&r.y>=ro.y&&r.y<ro.y+ro.h).map(r=>({...r}));rows.count=rows.length;return rows;};return img;};}
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

function healingFixture(options={}){
  let position={x:-1329.8,y:2566.115},angle=options.needsTurn?0:180,healed=false,portraits=0,settledCaptures=0;
  const field=()=>[
    row('Meet Lisa at the temple',80,250,300,35),row('R',1580,1004,30,30),row(healed?'1186/1186':'685/1186',900,1002,120,24),
    row('Amber',1680,415,80,35),row('Q',1660,1004,30,30),row('Kaeya',1660,500,80,35),row('3',1860,500,25,35),
    ...(position.x>-1327&&(!options.delayedLabel||settledCaptures>=2)?[row('Statue of The Seven',1216,524,275,29),
      ...(options.missingFullF?[]:[row('F',1100,510,30,30)])]:[])
  ];
  const opening=options.silentOpening?[row('Auto',100,32,67,31),row('Statue of The Seven',783,852,349,42)]:
    [row('Auto',123,32,72,35),row('Statue of The Seven',788,850,345,35),
    row('The world opens itself before those with noble hearts.',575,918,896,32)];
  const choices=[...opening,row("Statue's Blessing",1260,570,300,34),row('Leave',1260,640,120,30)];
  const panel=[row('Click on the character portrait to restore HP',150,40,640,30),
    row("Statue's Blessing",1450,40,200,25),row(options.depletedPower?'Restorative Power: 0 / 5000':'Restorative Power: 4838 / 5000',1400,115,280,25)];
  const f=prepare({fieldRowsSequence:[field()]});
  f.context.genshin.getPositionFromMap=()=>({...position});
  f.context.genshin.getCameraOrientation=()=>angle;
  f.context.moveMouseBy=dx=>{if(options.rotateFailure)throw new Error('mock rotation failure');angle=(angle+dx/8+360)%360;};
  const capture=f.context.captureGameRegion;
  f.context.captureGameRegion=function(){
    if(f.getScreen()==='field'&&position.x>-1327)settledCaptures++;
    if(f.getScreen()==='field')f.setFlag('fieldRowsSequence',[field()]);
    const img=capture(),stage=f.getScreen(),rows=stage==='statueOpening'?opening:stage==='statueChoices'?choices:stage==='statuePanel'?panel:null;
    if(stage===options.captureFailureStage&&!options.captureFailed){options.captureFailed=true;throw new Error('mock Statue capture failure');}
    if(rows)img.findMulti=function(ro){const out=rows.filter(r=>r.x>=ro.x&&r.x<ro.x+ro.w&&r.y>=ro.y&&r.y<ro.y+ro.h).map(r=>({...r}));out.count=out.length;return out;};
    return img;
  };
  const Image=f.context.ImageRegion;
  f.context.ImageRegion=class{constructor(mat){this.original=new Image(mat);this.rect=mat.rect;}
    findMulti(ro){if(f.getScreen().startsWith('statue')){const out=[];out.count=0;return out;}
      if(options.missingFullF&&this.rect&&this.rect.x===1080&&this.rect.y===490&&this.rect.w===90){
        const out=[row('F',54,96,135,105)];out.count=1;return out;}
      return this.original.findMulti(ro);}
    dispose(){this.original.dispose();}};
  const down=f.context.keyDown;
  f.context.keyDown=function(key){
    const before=f.getScreen();down(key);
    if(key==='VK_W'){position={x:-1325.2,y:2566.115};if(options.moveFailure)throw new Error('mock movement failure');}
    if(key==='VK_F'){f.setScreen('statueOpening');if(options.policyFailureAfterF){f.setScreen('field');f.getVirtualFiles().set('statue-dialogue.js','bad syntax !!');throw new Error('mock F did not open dialogue');}
      if(options.stopAfterF)f.getVirtualFiles().set('stop.json',JSON.stringify({session:'lion-adapter-test',createdAt:9000}));if(options.interactionFailure)throw new Error('mock Statue F failure');}
    if(key==='VK_SPACE'){f.setScreen('statueChoices');if(options.advanceFailure)throw new Error('mock Statue Space failure');}
    if(key==='VK_ESCAPE'&&before==='statuePanel'&&options.closeFailure&&!options.closedOnce){
      options.closedOnce=true;f.setScreen('statuePanel');throw new Error('mock Statue close failure');}
  };
  f.context.click=function(x,y){
    f.inputs.push({kind:'click',x,y,screen:f.getScreen()});
    if(f.getScreen()==='statueChoices'&&y<620){
      if(options.blessingFailure)throw new Error('mock Blessing click failure');
      f.setScreen('statuePanel');
    }else if(f.getScreen()==='statueChoices'&&y>=620)f.setScreen('field');
    else if(f.getScreen()==='statuePanel'){
      if(options.portraitFailure)throw new Error('mock portrait click failure');
      portraits++;if(portraits>=10)healed=true;
    }
  };
  return {...f,getPortraits:()=>portraits};
}

test('Starfell spawn is approached once and the existing Blessing flow heals both starters before verified pause',async()=>{
  const f=healingFixture(),result=await f.run();
  assert.equal(result.recovered,true,JSON.stringify(result));assert.equal(result.healingAttempted,true);
  assert.equal(result.health.current,1186);assert.equal(result.pauseVerified,true);assert.equal(result.pauseProof.kind,'journal');
  assert.equal(result.moves,1);assert.equal(f.getPortraits(),10);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_F').length,1);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_SPACE').length,1);
  assert.deepEqual(JSON.parse(JSON.stringify(f.getOverlappingKeyDowns())),[]);
  assert.ok(!f.inputs.some(x=>x.kind==='down'&&['VK_1','VK_2','VK_3','VK_E','VK_Q','VK_LBUTTON'].includes(x.key)));
});

test('the near-statue interaction label is reobserved after its movement fade before F',async()=>{
  const f=healingFixture({delayedLabel:true}),result=await f.run();
  assert.equal(result.recovered,true,JSON.stringify(result));assert.equal(result.pauseVerified,true);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_F').length,1);
  assert.ok(result.fieldFrameId>1);
});
test('recorded Statue label in a normal HUD does not disable the same-capture scaled F prompt',async()=>{
  const f=healingFixture({missingFullF:true}),result=await f.run();
  assert.equal(result.recovered,true,JSON.stringify(result));assert.equal(result.pauseVerified,true);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_F').length,1);
  const interaction=f.observations.find(o=>o.ocr.some(r=>r.text==='Statue of The Seven')&&o.hud.world);
  assert.equal(interaction.hud.choice,false);assert.ok(interaction.ocr.some(r=>r.text==='F'&&r.x>1080&&r.x<1170));
});
test('recorded Starfell ellipsis opening is advanced and healed without root or human input',async()=>{
  const f=healingFixture({silentOpening:true,missingFullF:true}),result=await f.run();
  assert.equal(result.recovered,true,JSON.stringify(result));assert.equal(result.pauseVerified,true);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_SPACE').length,1);
  assert.equal(f.getPortraits(),10);
});
test('a failed Starfell ellipsis advance is resolved to Leave by the local pause guardian',async()=>{
  const f=healingFixture({silentOpening:true,advanceFailure:true}),result=await f.run();
  assert.equal(result.recovered,false);assert.equal(result.pauseVerified,true);
  assert.equal(f.getPortraits(),0);
});
test('a pending local guard adopts a corrected pure Statue UI policy without restart or an external gameplay key',async()=>{
  const currentPolicy=fs.readFileSync(path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot/statue-dialogue.js'),'utf8');
  const oldPolicy=currentPolicy.replace('exactDialogueRows(o, state.allowSilentOpening)','exactDialogueRows(o, false)');
  assert.notEqual(oldPolicy,currentPolicy);
  const f=healingFixture({silentOpening:true});f.getVirtualFiles().set('statue-dialogue.js',oldPolicy);
  let returned=false;const pending=f.run().then(out=>{returned=true;return out;});
  const deadline=Date.now()+1500;
  while(!f.adapter.events().some(e=>e.type==='pauseProtectionStarted')){
    if(Date.now()>deadline)throw new Error('Statue pause guardian did not arm');await new Promise(setImmediate);
  }
  for(let i=0;i<5;i++)await new Promise(setImmediate);
  assert.equal(returned,false);assert.equal(f.getScreen(),'statueOpening');
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_SPACE').length,0);
  f.getVirtualFiles().set('statue-dialogue.js',currentPolicy);
  const result=await pending;assert.equal(result.recovered,false);assert.equal(result.pauseVerified,true);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_SPACE').length,1);
  assert.equal(f.getPortraits(),0);
});
test('an invalid replacement dialogue policy cannot prevent verified pause in a normal field',async()=>{
  const f=healingFixture({policyFailureAfterF:true}),result=await f.run();
  assert.equal(result.recovered,false);assert.equal(result.pauseVerified,true);
  assert.equal(result.pauseProof.kind,'inventory');assert.equal(f.getPortraits(),0);
});

test('a canonical paused quest journal can resume recovery without a human inventory switch',async()=>{
  const f=prepare({initialScreen:'journal'}),result=await f.run();
  assert.equal(result.recovered,true,JSON.stringify(result));assert.equal(result.pauseVerified,true);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_ESCAPE').length,1);
});

const lisaJournalRows=()=>[row('In Progress',135,26,153,41),row('Archon Quests',150,117,229,35),
  row('Sparks Amongst the Pages',869,119,457,45),row('Meet Lisa at the temple',890,254,331,29),
  row('Cancel',1624,989,95,30),row('Navigation',1600,1018,147,35)];
test('recorded Lisa journal Cancel Navigation is a known close-only widget',async()=>{
  const f=prepare({initialScreen:'journal',journalRows:lisaJournalRows()}),result=await f.run();
  assert.equal(result.recovered,true,JSON.stringify(result));assert.equal(result.pauseVerified,true);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_ESCAPE').length,1);
});
test('an extra Cancel modal outside the known journal widget cannot be dismissed',async()=>{
  const f=prepare({initialScreen:'journal',journalRows:[...lisaJournalRows(),row('Cancel',850,550,100,30)]}),result=await f.run();
  assert.equal(result.recovered,false);assert.equal(result.teleportAttempted,false);
  assert.equal(f.inputs.length,0);
});

for(const [name,options] of [
  ['movement failure',{moveFailure:true}],['rotation failure',{needsTurn:true,rotateFailure:true}],
  ['Statue F failure',{interactionFailure:true}],['Statue dialogue failure',{advanceFailure:true}],
  ['Blessing click failure',{blessingFailure:true}],['portrait click failure',{portraitFailure:true}],
  ['panel close failure',{closeFailure:true}],
  ['dialogue capture failure',{captureFailureStage:'statueOpening'}],['panel capture failure',{captureFailureStage:'statuePanel'}],
  ['stop after interaction',{stopAfterF:true}],['depleted restorative power',{depletedPower:true}],
])test(name+' returns only after resolving the known UI and locally verifying pause',async()=>{
  const f=healingFixture(options),result=await f.run();
  assert.equal(result.recovered,false,JSON.stringify(result));assert.equal(result.pauseVerified,true);
  assert.ok(result.pauseProof.pauseFrameId>result.pauseProof.sourceFrameId);
  assert.equal(f.nativeCalls.filter(x=>x.kind==='fight').length,0);
  assert.deepEqual(JSON.parse(JSON.stringify(f.getOverlappingKeyDowns())),[]);
});
