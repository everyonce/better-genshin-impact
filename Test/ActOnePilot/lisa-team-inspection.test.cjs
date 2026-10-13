'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'lion-field-combat-adapter.test.cjs'),'utf8');
const sandbox={require,module:{exports:{}},__dirname,setImmediate};
vm.runInNewContext(source.slice(0,source.indexOf('\nfunction assertPauseProof'))+'\nmodule.exports={fixture,row};',sandbox);
const {fixture,row}=sandbox.module.exports;
function setup(options={}){
 const f=fixture({step:'lisaTeamInspect',noEnemy:true,...options});
 const down=f.context.keyDown,capture=f.context.captureGameRegion;
 f.context.keyDown=key=>{down(key);if(key==='VK_C')f.setScreen('characters');};
 f.context.genshin.getPositionFromMap=()=>{if(f.getScreen()!=='field')throw Error('not world');return {x:-1356.54,y:1866.08};};
 f.context.captureGameRegion=()=>{const img=capture();if(f.getScreen()==='characters')img.findMulti=ro=>{
   const found=['Attributes','Weapons','Artifacts','Talents','Constellation'].map((t,i)=>row(t,100,150+70*i))
     .filter(r=>r.x>=ro.x&&r.x<ro.x+ro.w&&r.y>=ro.y&&r.y<ro.y+ro.h);found.count=found.length;return found;
 };return img;};
 return f;
}
test('team inspection opens only the character menu and spends no resources',async()=>{
 const f=setup(),initial=await f.adapter.observe('lion-adapter-test',1);
 const result=await f.adapter.runLisaTeamInspect(initial,f.observe);
 assert.equal(result.characterMenuVerified,true,JSON.stringify(result));assert.equal(result.pauseVerified,true);
 assert.equal(result.resourcesSpent,false);assert.equal(result.questComplete,false);
 assert.deepEqual(Array.from(f.inputs.filter(x=>x.kind==='down'),x=>x.key),['VK_ESCAPE','VK_C']);
 assert.equal(f.getOverlappingKeyDowns().length,0);
});
test('team inspection refuses an enemy field and returns to verified pause',async()=>{
 const f=setup({noEnemy:false,extra:[row('Lv.7',500,220)]}),initial=await f.adapter.observe('lion-adapter-test',1);
 const result=await f.adapter.runLisaTeamInspect(initial,f.observe);
 assert.equal(result.characterMenuVerified,false);assert.equal(result.pauseVerified,true);
 assert.ok(!f.inputs.some(x=>x.kind==='down'&&x.key==='VK_C'));
});
test('team inspection refuses a stale inventory without input',async()=>{
 const f=setup(),initial=await f.adapter.observe('lion-adapter-test',1);initial.timestamp-=1501;
 const result=await f.adapter.runLisaTeamInspect(initial,f.observe);
 assert.equal(result.status,'stopped');assert.equal(f.inputs.length,0);
});
test('verified Lion inventory switches pause menus without an exposed field capture',async()=>{
 const session='lion-adapter-test',entry={session,timestamp:9000,status:'completed',mission:'questStep',details:{result:{step:'lionPartyStart',label:'Deep Within the Temple of the Lion'},inputEvents:[{type:'lionPartyStart',label:'Deep Within the Temple of the Lion',startedAt:8900}]}};
 for(const stopAfterClose of [false,true]){
  const f=setup({noEnemy:false,stopAfterClose,seedFiles:{['reports/'+session+'.json']:[entry]}}),initial=await f.adapter.observe(session,1);
  const result=await f.adapter.runLisaTeamInspect(initial,f.observe);
  assert.equal(result.pauseVerified,true,JSON.stringify(result));
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_C').length,stopAfterClose?0:1);
  if(!stopAfterClose){assert.equal(result.characterMenuVerified,true);assert.equal(f.observations.some(o=>o.hud.health),false);}
  assert.equal(f.getOverlappingKeyDowns().length,0);
 }
});
test('stop after inventory close releases and obtains a pause without opening characters',async()=>{
 const f=setup({stopAfterClose:true}),initial=await f.adapter.observe('lion-adapter-test',1);
 const result=await f.adapter.runLisaTeamInspect(initial,f.observe);
 assert.equal(result.pauseVerified,true);assert.ok(!f.inputs.some(x=>x.kind==='down'&&x.key==='VK_C'));
});
test('read-only Lisa witness repairs the selected grey slot from the same capture',async()=>{
 const f=setup({initialScreen:'field',slot:false,slotCropRows:[row('3',30,30,60,60)]});
 f.adapter.beginMission({mission:'observe',id:'read-only',session:'lion-adapter-test',expectedFrameId:1,createdAt:9000});
 const o=await f.adapter.observe('lion-adapter-test',1);
 assert.equal(f.metrics.slotCropCalls,1);assert.ok(o.ocr.some(r=>r.text==='3'&&r.x>=1850));assert.equal(f.inputs.length,0);
});
test('read-only Lisa witness detects an anchored enemy bar from the same capture',async()=>{
 const f=setup({initialScreen:'field',noEnemy:false,extra:[row('Lv.7',500,220)]});
 f.adapter.beginMission({mission:'observe',id:'read-only',session:'lion-adapter-test',expectedFrameId:1,createdAt:9000});
 const o=await f.adapter.observe('lion-adapter-test',1);
 assert.equal(o.hud.enemyBars.length,1);assert.equal(f.inputs.length,0);
});
