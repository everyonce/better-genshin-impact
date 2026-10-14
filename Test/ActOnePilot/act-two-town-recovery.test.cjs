const test=require('node:test'),assert=require('node:assert/strict'),gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-town-recovery.js');
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
