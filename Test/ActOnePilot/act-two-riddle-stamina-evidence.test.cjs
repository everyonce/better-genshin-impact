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
 const oldNoise=require('./act-two-lower-climb-recorded.fixture.json').ambiguousStamina.hud.climbStamina;
 const recovered=detector.classify(oldNoise);
 assert.equal(oldNoise.pixels,null);assert.equal(recovered.kind,'usable');assert.equal(recovered.pixels,370);assert.equal(recovered.height,60);
 const short=detector.classify(fixture('act-two-hideout-riddle-landing'));
 assert.equal(short.kind,'low');assert.equal(short.height,33);
 const substantial=detector.classify(fixture('act-two-stamina-visible'));
 assert.equal(substantial.kind,'usable');assert(substantial.height>=45);
});
test('a missing detector sample stays unknown rather than becoming full stamina',()=>{
 assert.equal(detector.classify(null).kind,'unknown');
 assert.equal(detector.classify({source:'same-frame-yellow-arc',rawPixels:0}).kind,'unknown');
});
test('live reader ignores the two-pixel stray contour in a real climb sample',()=>{
 const sample=require('./act-two-lower-climb-recorded.fixture.json').ambiguousStamina.hud.climbStamina;
 let disposed=0;const contours=sample.boxes.map((box,i)=>({box,i})),mask={dispose(){disposed++;},findContoursAsArray(){return contours;}},crop={srcMat:{cvtColor(){return {inRange(){return mask;},dispose(){disposed++;}};}},dispose(){disposed++;}};
 const cv={Scalar:function(){},ColorConversionCodes:{BGR2HSV:1},RetrievalModes:{External:1},ContourApproximationModes:{ApproxSimple:1},Cv2:{countNonZero(){return sample.rawPixels;},boundingRect(c){return c.box;}}};
 const read=detector.read({deriveCrop(...rect){assert.deepEqual(rect,[1000,430,220,200]);return crop;}},cv);
 assert.equal(read.pixels,370);assert.equal(read.boxes.length,2);assert.equal(detector.classify(read).kind,'usable');assert.equal(disposed,3);
});
