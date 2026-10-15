const test=require('node:test'),assert=require('node:assert/strict');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-rank-rewards.js');
test('earned rank return requires fresh selected counter NPC and safe city field',()=>{
 const o={session:'test',timestamp:1000,map:{map:'Teyvat',x:-913,y:2232},hud:{world:true,interact:true,groundControls:true,health:{current:1000,max:1000},enemyBars:[],objectives:[]},ocr:[{text:'Katheryne',x:1200,y:525,height:30},{text:'F',x:1100,y:525,height:30}]};
 assert.equal(gate.returnVisit(o,1000,'test'),true);
 for(const bad of [{session:'other'},{timestamp:-1},{map:{...o.map,x:-930}},{hud:{...o.hud,climbing:true}},{hud:{...o.hud,enemyBars:[{}]}},{hud:{...o.hud,objectives:['Other quest']}},{hud:{...o.hud,health:{current:300,max:1000}}},{ocr:o.ocr.slice(1)},{ocr:[...o.ocr,o.ocr[0]]},{ocr:[o.ocr[0],{...o.ocr[1],y:580}]}])assert.equal(gate.returnVisit({...o,...bad},1000,'test'),false);
 assert.equal(gate.returnVisit(o,2001,'test'),false);
});
test('rank claim requires fresh original-account reward menu and unique button',()=>{
 const o={timestamp:1000,map:null,hud:{world:false,health:null},ocr:[
 {text:'UID: 693306810',x:1680,y:1046},{text:'Adventure Rank',x:1396,y:14},{text:'Rewards',x:1465,y:381},
 {text:'Claim Rewards',x:1444,y:1005,width:217,height:28}]};
 assert.deepEqual(gate.target(o,1000),{x:1553,y:1019,action:'claim'});
 assert.equal(gate.target(o,2001),null);assert.equal(gate.target(o,999),null);
 assert.equal(gate.target({...o,ocr:o.ocr.slice(1)},1000),null);
 assert.equal(gate.target({...o,ocr:[...o.ocr,o.ocr[3]]},1000),null);
 assert.equal(gate.target({...o,hud:{world:true}},1000),null);
});
