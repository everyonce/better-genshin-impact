const test = require('node:test');
const assert = require('node:assert/strict');
const native = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-native-combat.js');

test('only one exact world level row in a local enlarged crop supplies a position',()=>{
 const row={text:'Lv. 6',x:177,y:54,width:102,height:32};
 const local=rows=>native.localLevel(rows,1177,385,6);
 const expected={level:6,x:1253,y:385+70/3};
 assert.deepEqual(local([row]),expected);
 for(const text of ['Lv. 16','Character Lv. 6','6','Ly.6','Lv. 6:'])assert.equal(local([{...row,text}]),null);
 assert.equal(local([row,{...row,x:300}]),null);
 assert.equal(local([{...row,width:320}]),null);
});

function replay(options={}){
 const actions=[],reads=[];
 const map={x:-1383.318359375,y:1644.26171875,map:'Teyvat',cameraAngle:159};
 const bar={x:1591.5,y:429,width:17,height:4,rectangularity:.979};
 function frame(id,angle,bars){return {frameId:id,session:'s',map:{...map,cameraAngle:angle},hud:{enemyBars:bars,objectives:[]}};}
 const initial=frame(13,159,[bar]),line=[frame(14,178,[]),frame(15,190,[]),
  frame(16,190,[{...bar,x:970,y:626,width:68,height:9}])];
 if(options.foreign)line[1].session='someone-else';
 if(options.poseJump)line[0].map.x+=20;
 let now=0;
 const budget={turns:0,steps:0};
 const api={pack:true,now:()=>now,checkStop(){},eligible:o=>o.hud.enemyBars.length>0,
  emptyField:o=>o?.session==='s'&&o.hud.enemyBars.length===0,
  origin:map,deadline:8500,approachBudget:budget,cameraDelta:bars=>Math.abs(bars[0].x-960)<180?0:200,
  turn:async(dx,o)=>actions.push(['turn',dx,o.frameId]),forward:async o=>actions.push(['forward',o.frameId]),
  sleep:async ms=>{now+=ms;},observe:async()=>line.shift(),
  levelAt(o,x,y,level){
   reads.push([o.frameId,x,y,level]);
   if(options.missing&&o.frameId===14)return null;
   const centers={13:[1618,416],14:[1249,409],15:[1008,406]};
   const point=centers[o.frameId];if(!point||Math.abs(point[0]-x)>78)return null;
   return {x:point[0],y:point[1],level:6};
  }};
 return {go:()=>native.approachFieldTarget(initial,api),actions,reads,budget};
}

test('recorded right turn moves the label left and permits approach until a genuine bar reappears',async()=>{
 const r=replay(),field=await r.go();
 assert.equal(field.frameId,16);
 assert.deepEqual(r.reads.map(row=>[row[0],row[1]]),[[13,1591.5],[14,1257],[15,1021]]);
 assert.deepEqual(r.actions.map(a=>a[0]),['turn','turn','forward']);
 assert.deepEqual(r.budget,{steps:1,turns:2});
});
test('missing nameplate or implausible movement issues no additional input',async()=>{
 for(const option of [{missing:true},{poseJump:true}]){
  const r=replay(option);await assert.rejects(r.go(),/grounded health/);
  assert.deepEqual(r.actions,[['turn',200,13]]);
 }
});
test('a changed session during approach cannot supply the reacquired target',async()=>{
 const r=replay({foreign:true});await assert.rejects(r.go(),/new field capture/);
 assert.deepEqual(r.actions.map(a=>a[0]),['turn','turn']);
});
