const test=require('node:test'),assert=require('node:assert/strict');
const detector=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/climb-stamina.js');
const fixture=name=>require(`./${name}.fixture.json`).hud.climbStamina;

test('saved broad-wall climbing frames have absent yellow signal, not measured low reserve',()=>{
 for(const name of ['act-two-riddle-broad-wall-mounted','act-two-riddle-broad-wall-settled']){
  const result=detector.classify(fixture(name));
  assert.deepEqual(result,{kind:'absent',pixels:null,height:null});
 }
});
test('real noisy, short and substantial arcs remain distinct',()=>{
 assert.equal(detector.classify(fixture('act-two-hideout-climb')).kind,'occluded-or-ambiguous');
 const short=detector.classify(fixture('act-two-hideout-riddle-landing'));
 assert.equal(short.kind,'low');assert.equal(short.height,33);
 const substantial=detector.classify(fixture('act-two-stamina-visible'));
 assert.equal(substantial.kind,'usable');assert(substantial.height>=45);
});
test('a missing detector sample stays unknown rather than becoming full stamina',()=>{
 assert.equal(detector.classify(null).kind,'unknown');
 assert.equal(detector.classify({source:'same-frame-yellow-arc',rawPixels:0}).kind,'unknown');
});
