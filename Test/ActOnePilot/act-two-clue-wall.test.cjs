const test=require('node:test'),assert=require('node:assert/strict');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-town-recovery.js');
test('clue retaining wall accepts wrapped objective and rejects unsafe or unrelated scenes',()=>{
 const o={session:'synthetic',timestamp:1000,map:{map:'Teyvat',x:-866.869,y:2247.621},hud:{climbing:true,health:{current:1335,max:1700},enemyBarDiagnostic:{},enemyBars:[],objectives:['Solve the mystery (Go to Kaeya at the Knights of Favonius','HQ for a hint)']}};
 assert.equal(gate.wallReady(o,1000,'synthetic'),true);
 assert.equal(gate.wallReady(o,2001,'synthetic'),false);
 assert.equal(gate.wallReady(o,1000,'other'),false);
 for(const hud of [{health:{current:1189,max:1700}},{enemyBars:[{}]},{objectives:['Talk to Kaeya']},{dialogueReady:true}])
  assert.equal(gate.wallReady({...o,hud:{...o.hud,...hud}},1000,'synthetic'),false);
 assert.equal(gate.wallReady({...o,map:{...o.map,x:-860}},1000,'synthetic'),false);
 const upper={...o,map:{...o.map,x:-852.076,y:2277.981,cameraAngle:164.5},hud:{...o.hud,objectives:[o.hud.objectives[0],'HQ forla hint)'],climbing:false,groundControls:true}};
 assert.equal(gate.wallReady(upper,1000,'synthetic'),true);
 assert.equal(gate.railReady(upper,1000,'synthetic'),true);
 assert.equal(gate.railReady({...upper,map:{...upper.map,cameraAngle:10}},1000,'synthetic'),false);
});
