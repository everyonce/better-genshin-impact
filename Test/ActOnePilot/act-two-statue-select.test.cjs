const test=require('node:test'),assert=require('node:assert/strict'),m=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('statue recovery switches only a living Traveler in the verified safe location',async()=>{
 const o={map:{map:'Teyvat',x:-1265.917,y:1928.381},hud:{world:true,groundControls:true,health:{current:1363,max:1363},enemyBars:[],objectives:[]},ocr:[{text:'Kaeya',x:1690,y:440}]};
 for(const [p,ok] of [[{hud:{...o.hud,health:{current:2436,max:2764},objectives:['Defeat the ambush']}},true],[{hud:{...o.hud,health:{current:2451,max:2451}}},true],[{hud:{...o.hud,health:{current:1740,max:1740}}},true],[{},true],[{map:{map:'Teyvat',x:-1300,y:2300}},false],[{hud:{...o.hud,enemyBars:[{}]}},false],[{hud:{...o.hud,health:{current:600,max:1363}}},true],[{hud:{...o.hud,health:{current:0,max:1363}}},false],[{map:{map:"Teyvat",x:-1266.35,y:1934.03}},true],[{ocr:[]},false]]){
  let keys=[];const f={...o,...p},api={runActTwoNavigationWithPause:async(a,b,cb)=>cb(f),keyPress:async k=>keys.push(k),sleep:async()=>{}};
  await m.runQuestStep('actTwoStatueSelectKaeya',f,api,async()=>({...f,frameId:3}));assert.deepEqual(keys,ok?['VK_3']:[]);
 }
});

test('final glider recovery still requires the safe Statue and living Traveler',async()=>{
 const o={map:{map:'Teyvat',x:-1265.917,y:1928.381},hud:{world:true,groundControls:true,health:{current:2451,max:2451},enemyBars:[],objectives:['Follow the route and fly to the finish line in time']},ocr:[{text:'Kaeya',x:1690,y:440}]};
 for(const [change,ok] of [[{},true],[{map:{map:'Teyvat',x:0,y:0}},false],[{hud:{...o.hud,enemyBars:[{}]}},false],[{hud:{...o.hud,objectives:['Another quest']}},false]]){
  const f={...o,...change},keys=[];await m.runQuestStep('actTwoStatueSelectKaeya',f,{runActTwoNavigationWithPause:async(a,b,cb)=>cb(f),keyPress:async k=>keys.push(k),sleep:async()=>{}},async()=>({...f,frameId:3}));assert.deepEqual(keys,ok?['VK_3']:[]);
 }
});

// Keep the new Starfell route on the same guarded callback and exact party-slot input.
function starfellField(patch={}) {
 return {session:'starfell-selection',frameId:20,timestamp:10000,map:{map:'Teyvat',x:-1323.474,y:2566.115},
  hud:{world:true,groundControls:true,climbing:false,health:{current:2764,max:2764},enemyBars:[],objectives:[]},
  ocr:[{text:'Kaeya',x:1690,y:440}],...patch};
}

// The wrapper supplies the fresh field; the initial observation remains the paused inventory.
async function selectAt(field) {
 const calls=[],initial={session:'starfell-selection',frameId:19,hud:{world:false},ocr:[{text:'Weapons'}]};
 const after={...field,frameId:21,hud:{...field.hud,health:{current:4015,max:4015}}};
 const observe=async()=>{calls.push(['observe']);return after;};
 const api={
  runActTwoNavigationWithPause:async(source,reader,callback)=>{
   assert.equal(source,initial);assert.equal(reader,observe);calls.push(['wrapper']);return callback(field);
  },
  keyPress:async key=>calls.push(['key',key]),sleep:async ms=>calls.push(['sleep',ms]),
 };
 return {result:await m.runQuestStep('actTwoStatueSelectKaeya',initial,api,observe),calls};
}

test('Starfell center and retained healed position select slot three exactly once through the wrapper',async()=>{
 for(const map of [{map:'Teyvat',x:-1323.474,y:2566.115},{map:'Teyvat',x:-1325.6796875,y:2565.2578125}]) {
  const {result,calls}=await selectAt(starfellField({map}));
  assert.deepEqual(calls,[['wrapper'],['key','VK_3'],['sleep',800],['observe']]);
  assert.equal(result.status,'stopped');
  assert.equal(result.fieldFrameId,21);
  assert.equal(result.reason,'Kaeya selected; verify recovered health');
 }
});

test('both Statue scopes retain the exact eight-unit radius and reject the space between them',async()=>{
 for(const [x,y] of [[-1265.917,1928.381],[-1323.474,2566.115]]) {
  for(const [dx,dy,allowed] of [[8,0,true],[-8,0,true],[0,8,true],[0,-8,true],[8.001,0,false],[0,8.001,false],[8,8,false]]) {
   const {calls}=await selectAt(starfellField({map:{map:'Teyvat',x:x+dx,y:y+dy}}));
   assert.deepEqual(calls.filter(row=>row[0]==='key'),allowed?[['key','VK_3']]:[]);
  }
 }
 for(const map of [
  {map:'Teyvat',x:(-1265.917-1323.474)/2,y:(1928.381+2566.115)/2},
  {map:'Liyue',x:-1323.474,y:2566.115},{map:'Teyvat',x:NaN,y:2566.115},null,
 ]) {
  const {result,calls}=await selectAt(starfellField({map}));
  assert.equal(result.status,'stopped');assert.deepEqual(calls,[['wrapper']]);
 }
});

test('Starfell retains grounded living starter, objective, threat, and unique Kaeya slot-three guards',async()=>{
 const base=starfellField();
 for(const patch of [
  {hud:{...base.hud,world:false}},{hud:{...base.hud,groundControls:false}},
  {hud:{...base.hud,climbing:true}},{hud:{...base.hud,health:null}},
  {hud:{...base.hud,health:{current:0,max:2764}}},
  {hud:{...base.hud,health:{current:2765,max:2764}}},
  {hud:{...base.hud,health:{current:4015,max:4015}}},
  {hud:{...base.hud,enemyBars:[{}]}},{hud:{...base.hud,objectives:['Another quest']}},
  {ocr:[]},{ocr:[...base.ocr,...base.ocr]},{ocr:[{text:'Kaeya',x:1690,y:350}]},
 ]) {
  const {result,calls}=await selectAt(starfellField(patch));
  assert.equal(result.status,'stopped');assert.deepEqual(calls,[['wrapper']]);
 }
});

test('inventory-wrapper refusal cannot be bypassed by Starfell coordinates',async()=>{
 const calls=[];
 await assert.rejects(m.runQuestStep('actTwoStatueSelectKaeya',starfellField(),{
  runActTwoNavigationWithPause:async()=>{throw Error('Fresh inventory required');},
  keyPress:async key=>calls.push(key),
 },async()=>starfellField()),/Fresh inventory required/);
 assert.deepEqual(calls,[]);
});
