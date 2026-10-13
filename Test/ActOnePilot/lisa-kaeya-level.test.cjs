'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'lion-field-combat-adapter.test.cjs'),'utf8'),sandbox={require,module:{exports:{}},__dirname,setImmediate};
vm.runInNewContext(source.slice(0,source.indexOf('\nfunction assertPauseProof'))+'\nmodule.exports={fixture,row};',sandbox);
const {fixture,row}=sandbox.module.exports;
function setup(){
 const f=fixture({step:'lisaKaeyaLevel'}),clicks=[];f.context.click=(x,y)=>clicks.push([x,y]);
 const panel=(amount,patch={})=>({session:'lion-adapter-test',frameId:amount+1,timestamp:f.getNow(),map:null,
  hud:{world:false,kaeyaLevel:{frameId:amount+1,amount,requiredMora:amount*1000,midTierStock:2,mora:18520,...patch}},
  ocr:[row('Kaeya / Level Up',135,28),row('Select EXP materials',1378,675),row('Amount to use',1150,903),
    row('Required',1148,1005),row('Level Up',1663,998),row('Base HP',1148,236)]});
 return {...f,clicks,panel};
}
test('Kaeya upgrade selects exactly two books and caps the confirmation at 2000 Mora',async()=>{
 const f=setup();let n=0;const result=await f.adapter.runLisaKaeyaLevel(f.panel(0),async()=>f.panel(++n));
 assert.equal(result.resourceSpendAttempted,true);assert.equal(result.upgradeVerified,false);
 assert.deepEqual(f.clicks,[[1595,917],[1595,917],[1730,1020]]);
});
test('invalid amount, stock or Mora refuses all upgrade input',async()=>{
 for(const patch of [{amount:1},{midTierStock:1},{mora:1999},{requiredMora:1000}]){
  const f=setup(),result=await f.adapter.runLisaKaeyaLevel(f.panel(0,patch),async()=>f.panel(1));
  assert.equal(result.resourceSpendAttempted,false);assert.equal(f.clicks.length,0);
 }
});
test('a changed selection after adding a book never reaches spend confirmation',async()=>{
 const f=setup(),result=await f.adapter.runLisaKaeyaLevel(f.panel(0),async()=>f.panel(1,{requiredMora:4000}));
 assert.equal(result.resourceSpendAttempted,false);assert.deepEqual(f.clicks,[[1595,917]]);
});
test('reviewed Lion upgrade consumes one low-tier book at exactly 200 Mora and refuses changed costs',async()=>{
 for(const changed of [false,true]){
  const f=setup(),files=f.getVirtualFiles(),session='lion-adapter-test';
  files.set('lion-kaeya-level.json',JSON.stringify({session,frameId:1,reviewed:true,createdAt:9900}));
  files.set('reports/'+session+'.json',JSON.stringify([{session,timestamp:9000,status:'completed',mission:'questStep',details:{result:{step:'lionPartyStart',label:'Deep Within the Temple of the Lion'},inputEvents:[{type:'lionPartyStart',label:'Deep Within the Temple of the Lion',startedAt:8900}]}}]));
  const low=(amount,cost=amount*200)=>f.panel(amount,{requiredMora:cost,lowTierStock:4,midTierStock:0,highTierStock:0,mora:17195});
  const result=await f.adapter.runLisaKaeyaLevel(low(0),async()=>low(1,changed?1000:200));
  assert.equal(result.resourceSpendAttempted,!changed);assert.equal(f.clicks.length,changed?1:2);
  assert.ok(JSON.parse(files.get('lion-kaeya-level.json')).usedAt);
  if(!changed)assert.equal(result.moraBudget,200);
 }
});
