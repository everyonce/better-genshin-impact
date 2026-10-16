const test=require('node:test'),assert=require('node:assert/strict'),gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-town-recovery.js');

test('recorded post-trial roof gap permits one existing rail jump only at exact healthy aligned position',()=>{
 const o=require('./act-two-city-roof-gap.fixture.json');assert.equal(gate.railReady(o,o.timestamp,o.session),true);
 const upper=require('./act-two-city-roof-gap-upper.fixture.json');assert.equal(gate.railReady(upper,upper.timestamp,upper.session),true);
 for(const patch of [{map:{...o.map,x:o.map.x+2}},{map:{...o.map,cameraAngle:90}},{hud:{...o.hud,health:{current:3000,max:4015}}},{hud:{...o.hud,objectives:['Talk to Kaeya']}},{hud:{...o.hud,climbing:true}},{ocr:[]}])assert.equal(gate.railReady({...o,...patch},o.timestamp,o.session),false);
 assert.equal(gate.railReady(o,o.timestamp+1001,o.session),false);
});
test('Cyrus stair release is confined to the freshly witnessed low base and full health',()=>{const o={session:'s',timestamp:1000,map:{map:'Teyvat',x:-830.3945,y:2195.9316},hud:{climbing:true,health:{current:2635,max:2635},objectives:['Talk to Cyrus'],enemyBars:[]},ocr:[{text:'X',x:1594,y:1026},{text:'Space',x:1680,y:1026}]};assert.equal(gate.ready(o,1000,'s'),true);for(const patch of [{map:{...o.map,x:-835}},{hud:{...o.hud,health:{current:2300,max:2635}}},{hud:{...o.hud,objectives:['Talk to Kaeya']}},{hud:{...o.hud,enemyBars:[{}]}},{hud:{...o.hud,climbing:false}}])assert.equal(gate.ready({...o,...patch},1000,'s'),false);});
test('pillar release is restricted to the captured short city climb and healthy Kaeya',()=>{
 const o={session:'s',timestamp:1000,map:{map:'Teyvat',x:-925.867,y:2217.009},hud:{climbing:true,health:{current:1700,max:1700},objectives:['Talk to Wagner the blacksmith'],enemyBars:[]},ocr:[{text:'X',x:1594,y:1026},{text:'Space',x:1680,y:1026}]};
 assert.equal(gate.ready(o,1000,'s'),true);assert.equal(gate.ready(o,2001,'s'),false);
 assert.equal(gate.ready({...o,map:{...o.map,x:-900}},1000,'s'),false);
 assert.equal(gate.ready({...o,hud:{...o.hud,climbing:false}},1000,'s'),false);
 assert.equal(gate.ready({...o,hud:{...o.hud,enemyBars:[{}]}},1000,'s'),false);
});
test('ore cliff release requires the separately witnessed spot and mining objective',()=>{
 const o={session:'s',timestamp:1000,map:{map:'Teyvat',x:-1128.578,y:2210.419},hud:{climbing:true,health:{current:1700,max:1700},objectives:['Collect three Iron Chunks and give them to Wagner'],enemyBars:[]},ocr:[{text:'X',x:1594,y:1026},{text:'Space',x:1680,y:1026}]};
 assert.equal(gate.ready(o,1000,'s'),true);
 assert.equal(gate.ready({...o,map:null},1000,'s'),false);
 assert.equal(gate.ready({...o,map:{...o.map,x:-1131}},1000,'s'),false);
 assert.equal(gate.ready({...o,hud:{...o.hud,objectives:['Talk to Wagner the blacksmith']}},1000,'s'),false);
 assert.equal(gate.ready({...o,hud:{...o.hud,health:{current:1000,max:1700}}},1000,'s'),false);
});
test('recorded meeting wall, rail and shop releases stay location and objective bound',()=>{
 const fs=require('node:fs');
 const f=name=>JSON.parse(fs.readFileSync(__dirname+'/act-two-'+name+'.fixture.json','utf8'));
 const shop=f('meeting-shop-climb'),wall=f('meeting-wall-climb'),rail=f('meeting-rail');
 assert.equal(gate.ready(shop,shop.timestamp,shop.session),true);
 assert.equal(gate.wallReady(wall,wall.timestamp,wall.session),true);
 assert.equal(gate.railReady(rail,rail.timestamp,rail.session),true);
 assert.equal(gate.railReady({...rail,map:{...rail.map,cameraAngle:5}},rail.timestamp,rail.session),false);
 assert.equal(gate.railReady({...rail,map:{...rail.map,x:rail.map.x+10}},rail.timestamp,rail.session),false);
 assert.equal(gate.railReady({...rail,hud:{...rail.hud,objectives:['Talk to Kaeya']}},rail.timestamp,rail.session),false);
 assert.equal(gate.wallReady({...wall,hud:null},wall.timestamp,wall.session),false);
 assert.equal(gate.wallReady({...wall,hud:{...wall.hud,enemyBars:[{}]}},wall.timestamp,wall.session),false);
 for(const anchor of [[-845.066,2276.975],[-814.559,2319.845],[-790.848,2290.881]]){
  const o={...wall,map:{...wall.map,x:anchor[0],y:anchor[1]},hud:{...wall.hud,objectives:['Talk to Kaeya']}};
  assert.equal(gate.wallReady(o,o.timestamp,o.session),true);
  assert.equal(gate.wallReady(o,o.timestamp+1001,o.session),false);
 }
});

test('meeting terrace continuations reject other objectives and distant positions',()=>{
 for(const [x,y] of [[-824.875,2198.704],[-807.387,2194.526]]){
  const o={session:'s',timestamp:1000,map:{map:'Teyvat',x,y},hud:{objectives:['Talk to Kaeya at the meeting spot'],climbing:true,health:{current:1700,max:1700},enemyBars:[],enemyBarDiagnostic:{}}};
  assert.equal(gate.wallReady(o,1000,'s'),true);
  assert.equal(gate.wallReady({...o,map:{...o.map,x:x+4}},1000,'s'),false);
  assert.equal(gate.wallReady({...o,hud:{...o.hud,objectives:['Talk to Kaeya']}},1000,'s'),false);
 }
});

test('recorded informant tree releases only the witnessed short climb',()=>{
 const o=require('./act-two-informant-tree.fixture.json');
 assert.equal(gate.ready(o,o.timestamp,o.session),true);
 assert.equal(gate.ready({...o,map:{...o.map,x:o.map.x+3}},o.timestamp,o.session),false);
 assert.equal(gate.ready({...o,hud:{...o.hud,objectives:['Report to Kaeya']}},o.timestamp,o.session),false);
});

test('recorded final-trial return wall keeps health, location, heading and objective guards',()=>{const o=require('./act-two-city-return-climb.fixture.json');assert.equal(gate.wallReady(o,o.timestamp,o.session),true);for(const patch of [{map:{...o.map,x:o.map.x+4}},{map:{...o.map,cameraAngle:20}},{hud:{...o.hud,health:{max:4015,current:0}}},{hud:{...o.hud,enemyBars:[{}]}},{hud:{...o.hud,objectives:['Other quest']}}])assert.equal(gate.wallReady({...o,...patch},o.timestamp,o.session),false);assert.equal(gate.wallReady(o,o.timestamp+1001,o.session),false);});
