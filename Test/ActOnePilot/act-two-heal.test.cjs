const test=require('node:test'),assert=require('node:assert/strict');
const heal=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-heal.js');
function setup(bad={}){
 let now=10000,reads=0;const clicks=[];
 const first={session:'test',timestamp:now,frameId:1,selected:false,original:true};
 const api={session:'test',now:()=>now,original:o=>o.original,selected:o=>o.selected,
 selectTarget:o=>({x:1045,y:440}),feedTarget:o=>o.selected&&o.quantity===1?{x:1183,y:769}:null,
 sleep:async ms=>{now+=ms;},click:async(t,o,a)=>clicks.push(a),paused:()=>true};
 return {first,api,clicks,observe:async()=>{reads++;return {session:'test',timestamp:now,frameId:reads+1,original:true,selected:true,quantity:1,...bad};}};
}
test('selects Kaeya and confirms once; does not assert unobserved healing',async()=>{
 const h=setup(),r=await heal.run(h.first,h.api,h.observe);
 assert.deepEqual(h.clicks,['selectKaeya','useOneSweetMadame']);assert.equal(r.foodUseAttempts,1);assert.equal(r.healingVerified,false);
});
test('changed account, session, stale frame, wrong character or quantity prevents confirm',async()=>{
 for(const bad of [{original:false},{session:'other'},{timestamp:1},{selected:false},{quantity:2}]){
  const h=setup(bad);await assert.rejects(heal.run(h.first,h.api,h.observe));assert.deepEqual(h.clicks,['selectKaeya']);
 }
});
test('wrong initial account does not send inputs',async()=>{
 const h=setup();h.first.original=false;await assert.rejects(heal.run(h.first,h.api,h.observe));assert.deepEqual(h.clicks,[]);
});
