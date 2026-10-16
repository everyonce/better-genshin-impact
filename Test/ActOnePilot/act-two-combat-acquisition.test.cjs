const test=require('node:test'),assert=require('node:assert/strict');
const a=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-combat-acquisition.js');
const initial={session:'test',frameId:20};
const witness={session:'test',frameId:18,timestamp:1000,map:{map:'Teyvat',x:-1233,y:2326},hud:{world:true,health:{current:2635,max:2635},objectives:['Defeat the attacking monsters']}};
function sample(){return {acquisition:true,session:'test',timestamp:1100,accountPauseFrameId:20,map:{...witness.map},hud:{world:true,groundControls:true,climbing:false,menu:false,health:{current:2480,max:2635},objectives:['Defeat the attacking monsters'],enemyBars:[{x:950.5,y:199,width:131,height:12,rectangularity:.895}]}};}
test('same-image close encounter including upper-view bar can authorize native acquisition',()=>assert.equal(a.eligible(sample(),initial,witness,1150),true));

for(const [name,edit] of Object.entries({menu:o=>o.hud.menu=true,noEnemy:o=>o.hud.enemyBars=[],lowHealth:o=>o.hud.health.current=2325,noHealth:o=>o.hud.health=null,air:o=>o.hud.groundControls=false,wrongSession:o=>o.session='other',stale:o=>o.timestamp=1,wrongPause:o=>o.accountPauseFrameId=19,wrongMap:o=>o.map.map='Other',moved:o=>o.map.x-=20,wrongObjective:o=>o.hud.objectives=[],irregular:o=>o.hud.enemyBars[0].rectangularity=.4,ui:o=>o.hud.enemyBars[0].x=100}))test('acquisition rejects '+name,()=>{const o=sample();edit(o);assert.equal(a.eligible(o,initial,witness,1150),false);});
test('paused encounter witness binds account, frame, session and bounded location',()=>{assert.equal(a.pausedWitness(witness,initial,1100,()=>true),true);assert.equal(a.pausedWitness(witness,initial,1100,()=>false),false);assert.equal(a.pausedWitness({...witness,session:'other'},initial,1100,()=>true),false);assert.equal(a.pausedWitness(witness,initial,700000,()=>true),false);});
test('single reader uses crops and preserves menu rejection even with underlying health',()=>{
 const calls=[],out=a.read({}, {health:()=>({current:2635,max:2635}),rows:(_,x,y,w,h)=>{calls.push([x,y,w,h]);return y===20?[{text:'Food'}]:[{text:'Defeat the attacking monsters'}];},controls:()=>[{text:'E'}],ground:()=>true,bars:()=>sample().hud.enemyBars});
 assert.equal(out.hud.world,false);assert.equal(out.hud.menu,true);assert.deepEqual(calls,[[65,230,630,85],[100,20,350,70]]);
});

test('ambush OCR may merge whitespace but cannot change words or widen quest scope',()=>{
 for(const text of ['Defeat the attackingmonsters','Defeat theattacking monsters','Defeattheattackingmonsters']){
  const w={...witness,hud:{...witness.hud,objectives:[text]}},o=sample();o.hud.objectives=[text];
  assert.equal(a.pausedWitness(w,initial,1100,()=>true),true);assert.equal(a.eligible(o,initial,w,1150),true);
 }
 for(const text of ['Defeat attacking monsters','Defeat the attacking monster','Do not Defeat the attacking monsters','Defeat-the attacking monsters'])assert.equal(a.ambushObjective([text]),false);
});

test('single camera adjustment is bounded and does not authorize an off-center attack',()=>{const bar=sample().hud.enemyBars[0];assert.equal(a.cameraDelta([{...bar,x:1407}]),200);assert.equal(a.cameraDelta([{...bar,x:400}]),-200);assert.equal(a.cameraDelta([bar]),0);assert.equal(a.cameraDelta([]),0);assert.equal(a.centered([{...bar,x:1407}]),false);assert.equal(a.centered([bar]),true);});
test('recorded accented attacking OCR keeps the exact objective and rejects changed wording',()=>{for(const text of ['Defeat the att\u00e1cking monsters','Defeat the att\u00e4cking monsters'])assert.equal(a.ambushObjective([text]),true);for(const text of ['Do not Defeat the att\u00e1cking monsters','Defeat the att\u00e4cking monster','Defeat attacking monsters'])assert.equal(a.ambushObjective([text]),false);});
