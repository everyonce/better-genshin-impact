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

test('ambush OCR normalizes spacing and punctuation without widening quest scope',()=>{
 for(const text of ['Defeat the attackingmonsters','Defeat theattacking monsters','Defeattheattackingmonsters']){
  const w={...witness,hud:{...witness.hud,objectives:[text]}},o=sample();o.hud.objectives=[text];
  assert.equal(a.pausedWitness(w,initial,1100,()=>true),true);assert.equal(a.eligible(o,initial,w,1150),true);
 }
 assert.equal(a.ambushObjective(['Defeat-the attacking monsters']),true);
 for(const text of ['Defeat attacking monsters','Defeat the attacking monster','Do not Defeat the attacking monsters'])assert.equal(a.ambushObjective([text]),false);
});

test('bounded objective OCR substitutions retain independent live encounter guards',()=>{
 for(const text of ['Defeat the/attacking moosters','Defeat the attäcking monsters']){
  const o=sample();o.hud.objectives=[text];assert.equal(a.eligible(o,initial,witness,1150),true);
  o.map.map='Other';assert.equal(a.eligible(o,initial,witness,1150),false);
  o.map.map='Teyvat';o.hud.enemyBars=[];assert.equal(a.eligible(o,initial,witness,1150),false);
 }
 for(const text of ['Defeat the zzzacking monsters','Defeat those attacking monsters','Repeat the attacking monsters','Defeat the attacking monsters now'])assert.equal(a.ambushObjective([text]),false);
});

test('recorded depleted bars require an exact nearby same-image Lv5 anchor',()=>{
 const b={x:474.5,y:353.5,width:39,height:7,rectangularity:.765350877,levelAnchor:{text:'Lv.5',x:480,y:320,width:28,height:12}};
 assert.equal(a.targets([b]).length,1);
 for(const edit of [x=>delete x.levelAnchor,x=>x.levelAnchor.text='Lv.4',x=>x.levelAnchor.y=370,x=>x.levelAnchor.x=700,x=>x.rectangularity=.69,x=>x.width=70,x=>x.height=10]){
  const x=structuredClone(b);edit(x);assert.equal(a.targets([x]).length,0);
 }
});

test('single camera adjustment is bounded and does not authorize an off-center attack',()=>{const bar=sample().hud.enemyBars[0];assert.equal(a.cameraDelta([{...bar,x:1407}]),200);assert.equal(a.cameraDelta([{...bar,x:400}]),-200);assert.equal(a.cameraDelta([bar]),0);assert.equal(a.cameraDelta([]),0);assert.equal(a.centered([{...bar,x:1407}]),false);assert.equal(a.centered([bar]),true);});
test('edge bars authorize framing only with a nearby level label and never authorize a centered attack',()=>{
 const b={x:80,y:266,width:90,height:8,rectangularity:.9,levelAnchor:{text:'Lv. 5',x:99,y:234,width:58,height:22}},o=sample();o.hud.enemyBars=[b];
 assert.equal(a.framingTargets([b]).length,1);assert.equal(a.targets([b]).length,0);assert.equal(a.centered([b]),false);assert.equal(a.cameraDelta([b]),-200);assert.equal(a.eligible(o,initial,witness,1150),true);
 for(const change of [x=>delete x.levelAnchor,x=>x.levelAnchor.text='Lv.20',x=>x.levelAnchor.y=280,x=>x.levelAnchor.width=0,x=>x.rectangularity=.5,x=>x.height=33]){const x=structuredClone(b);change(x);assert.equal(a.framingTargets([x]).length,0);}
});
test('stationary close combat tolerates displacement after framing but retains range and identity checks',()=>{
 const b={x:292.5,y:457.5,width:67,height:13,rectangularity:.94255,levelAnchor:{text:'Lv.5',x:326,y:419,width:75.33,height:32}};
 assert.equal(a.stationaryReady([b]),true);
 for(const x of [{...b,levelAnchor:null},{...b,height:8},{...b,width:20},{...b,rectangularity:.5}])assert.equal(a.stationaryReady([x]),false);
 assert.equal(a.stationaryReady([]),false);
});
test('camera collision enlarges a close bar but still requires an exact same-image anchor',()=>{
 const b={x:335,y:118,width:130,height:24,rectangularity:.95,levelAnchor:{text:'Lv.5',x:412,y:56,width:115,height:40}};
 assert.equal(a.framingTargets([b]).length,1);assert.equal(a.stationaryReady([b]),true);
 for(const x of [{...b,levelAnchor:null},{...b,height:33},{...b,width:70},{...b,levelAnchor:{...b.levelAnchor,text:'Lv.20'}}])assert.equal(a.framingTargets([x]).length,0);
});
test('recorded accented attacking OCR keeps the exact objective and rejects changed wording',()=>{for(const text of ['Defeat the att\u00e1cking monsters','Defeat the att\u00e4cking monsters'])assert.equal(a.ambushObjective([text]),true);for(const text of ['Do not Defeat the att\u00e1cking monsters','Defeat the att\u00e4cking monster','Defeat attacking monsters'])assert.equal(a.ambushObjective([text]),false);});
