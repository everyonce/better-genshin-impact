const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const fixtureSource=fs.readFileSync(path.join(__dirname,'lion-field-combat-adapter.test.cjs'),'utf8');
const sandbox={require,module:{exports:{}},__dirname,setImmediate};
vm.runInNewContext(fixtureSource.slice(0,fixtureSource.indexOf('\nfunction assertPauseProof'))+
  '\nmodule.exports={fixture};',sandbox);

test('outer protector does not swallow exhaustion and restart the capture loop',async()=>{
  const f=sandbox.module.exports.fixture({unknownUi:true});
  const original=f.context.file.readTextSync;
  let loaded=0;
  f.context.file.readTextSync=p=>p==='local-pause.js'?
    (loaded++,'var ActOneLocalPause={ensure:async function(){var e=new Error("Pause is UNVERIFIED");e.code="PAUSE_PROTECTION_EXHAUSTED";throw e;}};'):
    original(p);
  await assert.rejects(()=>f.run(),
    e=>e.code==='PAUSE_PROTECTION_EXHAUSTED');
  assert.equal(loaded,1);
  assert.equal(f.adapter.events().some(e=>e.type==='pauseProtectionVerified'),false);
});
