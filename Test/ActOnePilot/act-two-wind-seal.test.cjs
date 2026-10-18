const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-wind-seal.js'),o=require('./act-two-wind-seal-eye.fixture.json');
test('actual Lv9 Eye header permits tutorial study only on fresh healthy owned ground',()=>{
 assert(g.eye(o));assert(g.ground(o,o.timestamp,o.session));
 for(const label of ['Eye of the Storm','Restless Pure Elemental','Lv.9'])assert(!g.ground({...o,ocr:o.ocr.filter(r=>r.text!==label)},o.timestamp,o.session));
 assert(!g.ground(o,o.timestamp+1001,o.session));assert(!g.ground(o,o.timestamp,'other'));
 for(const patch of [{climbing:true},{health:{current:4014,max:4015}},{world:false}])assert(!g.ground({...o,hud:{...o.hud,...patch}},o.timestamp,o.session));
});
test('synthetic tutorial cycle captures mechanics, closes exactly once, releases on unknown panel',async()=>{
 for(const recognized of [true,false]){
  let now=o.timestamp,keys=[],released=0,reads=0;
  const actual=require('./act-two-wind-seal-tutorial.fixture.json');const tutorial={...actual,ocr:recognized?actual.ocr:actual.ocr.filter(r=>r.text!=='Tutorials / All')};
  const api={now:()=>now,checkStop(){},sleep:async n=>now+=n,release:async()=>released++,key:async(k,ms)=>keys.push(k),observe:async()=>({...((reads++===0)?tutorial:o),timestamp:now,frameId:o.frameId+reads})};
  if(recognized){const r=await g.study(o,api);assert(r.tutorialOpened);assert.deepEqual(keys,['VK_G','VK_ESCAPE']);assert.equal(r.tutorialFrameId,o.frameId+1);}
  else{await assert.rejects(g.study(o,api),/not recognized/);assert.deepEqual(keys,['VK_G']);}
  assert.equal(released,1);
 }
});

test('actual tutorial panel needs both selected title and main title, UID and fresh session',()=>{
 const a=require('./act-two-wind-seal-tutorial.fixture.json');assert(g.panel(a,a.timestamp,a.session));
 for(const index of a.ocr.map((r,i)=>r.text==='Eye of the Storm'||r.text==='Tutorials / All'||r.text.includes('693306810')?i:-1).filter(i=>i>=0))assert(!g.panel({...a,ocr:a.ocr.filter((r,i)=>i!==index)},a.timestamp,a.session));
 assert(!g.panel(a,a.timestamp+1001,a.session));assert(!g.panel(a,a.timestamp,'other'));
});
test('actual Next changes archive entry, so recovery sends only Escape from either observed panel',async()=>{
 for(const file of ['act-two-wind-seal-tutorial.fixture.json','act-two-wind-seal-tutorial-next-entry.fixture.json']){
 const a=require('./'+file);let now=a.timestamp,keys=[],release=0;assert(g.recoveryPanel(a,now,a.session));
 const result=await g.recoverStudy(a,{now:()=>now,checkStop(){},sleep:async ms=>now+=ms,key:async k=>keys.push(k),release:async()=>release++,observe:async()=>({...o,timestamp:now})});
 assert.deepEqual(keys,['VK_ESCAPE']);assert.equal(release,1);assert.equal(result.tutorialPages.length,1);assert(result.windSealTutorialClosed);
 }
});
