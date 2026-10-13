'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'lion-field-combat-adapter.test.cjs'),'utf8');
const sandbox={require,module:{exports:{}},__dirname,setImmediate};
vm.runInNewContext(source.slice(0,source.indexOf('\nfunction assertPauseProof'))+'\nmodule.exports={fixture,fieldRows,row};',sandbox);
const {fixture,fieldRows,row}=sandbox.module.exports;
test('party switch completion requires the requested owned health identity and no rejection banner',async()=>{
 for(const [health,banner,selected] of [['1186/1186',false,true],['1288/1288',false,false],['1186/1186',true,false]]){
  const before=fieldRows({healthText:'1288/1288',extra:[row('2',1860,410,25,35)]});
  const after=fieldRows({healthText:health,extra:banner?[row('Cannot switch character now',750,200,450,35)]:[]});
  const f=fixture({step:'lisaTravelAmber',initialScreen:'field',noEnemy:true,fieldRowsSequence:[before,after]});
  const initial=await f.adapter.observe('lion-adapter-test',1),r=await f.adapter.runLisaTravelAmber(initial,f.observe);
  assert.equal(r.selected,selected,JSON.stringify(r));assert.equal(r.status,selected?'completed':'stopped');
  assert.equal(r.pauseVerified,true);assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_2').length,1);
 }
});
