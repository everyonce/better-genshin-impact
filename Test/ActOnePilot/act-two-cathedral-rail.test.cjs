const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-town-recovery.js'),fixture=require('./act-two-cathedral-rail.fixture.json');
test('recorded pavement contacts permit release only with fresh matching proof',()=>{
 const fixtures=require('./act-two-cathedral-releases.fixture.json');assert.deepEqual(fixtures.map(o=>o.frameId),[10222,10280,10354]);
 for(const o of fixtures){
  assert.equal(g.ready(o,o.timestamp,o.session),true,`frame ${o.frameId}`);assert.equal(g.wallReady(o,o.timestamp,o.session),false);
  assert.equal(g.ready(o,o.timestamp+1001,o.session),false);assert.equal(g.ready(o,o.timestamp,'other'),false);
  for(const patch of [{map:{...o.map,x:o.map.x+3}},{hud:{...o.hud,health:{current:3000,max:4015}}},{hud:{...o.hud,objectives:['Talk to Amber']}},{hud:{...o.hud,enemyBars:[{}]}},{ocr:o.ocr.filter(r=>r.text!=='X')}])assert.equal(g.ready({...o,...patch},o.timestamp,o.session),false);
 }
});
test('house contact permits only release to witnessed pavement',()=>{const o=require('./act-two-cathedral-house-release.fixture.json');assert.equal(g.ready(o,o.timestamp,o.session),true);assert.equal(g.wallReady(o,o.timestamp,o.session),false);assert.equal(g.ready({...o,map:{...o.map,x:o.map.x+3}},o.timestamp,o.session),false);assert.equal(g.ready({...o,hud:{...o.hud,health:{current:3000,max:4015}}},o.timestamp,o.session),false);});
test('recorded adjacent stair wall is confined to its witnessed position',()=>{const o=require('./act-two-cathedral-stair-wall.fixture.json');assert.equal(g.wallReady(o,o.timestamp,o.session),true);assert.equal(g.wallReady({...o,map:{...o.map,y:o.map.y+4}},o.timestamp,o.session),false);assert.equal(g.wallReady({...o,hud:{...o.hud,climbing:false,groundControls:true}},o.timestamp,o.session),false);});
test('recorded cathedral low rail allows bounded existing climb handler only',()=>{
 const o=structuredClone(fixture);assert.equal(g.wallReady(o,o.timestamp,o.session),true);assert.equal(g.railReady(o,o.timestamp,o.session),false);
 const patches=[{map:{...o.map,x:o.map.x+4}},{map:{...o.map,cameraAngle:220}},{hud:{...o.hud,health:{current:3000,max:4015}}},{hud:{...o.hud,climbing:false,groundControls:true}},{hud:{...o.hud,enemyBars:[{}]}},{hud:{...o.hud,objectives:['Talk to Amber']}},{ocr:o.ocr.filter(r=>r.text!=='Space')},{ocr:o.ocr.filter(r=>!String(r.text).includes('693306810'))}];
 for(const patch of patches)assert.equal(g.wallReady({...o,...patch},o.timestamp,o.session),false);
 assert.equal(g.wallReady(o,o.timestamp+1001,o.session),false);assert.equal(g.wallReady(o,o.timestamp,'other'),false);
});
