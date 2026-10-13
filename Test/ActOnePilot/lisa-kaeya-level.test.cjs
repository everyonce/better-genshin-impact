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
