const test=require('node:test'),assert=require('node:assert/strict');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-rank-rewards.js');
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
