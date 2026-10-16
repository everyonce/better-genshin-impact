const test=require('node:test');
const assert=require('node:assert/strict');
const native=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-native-combat.js');
test('native pause handoff accepts the engine serialized copy of the latest capture',()=>{
 const last={session:'current',frameId:3829,timestamp:1000,hud:{world:true}};
 const copy=JSON.parse(JSON.stringify(last));
 assert.notEqual(copy,last);
 assert.equal(native.pauseSeed(copy,last,1014,'current'),copy);
 for(const patch of [{frameId:3828},{timestamp:999},{session:'other'},{frameId:null}])
  assert.equal(native.pauseSeed({...copy,...patch},last,1014,'current'),null);
 for(const now of [999,2001,NaN])assert.equal(native.pauseSeed(copy,last,now,'current'),null);
 assert.equal(native.pauseSeed(copy,null,1014,'current'),null);
});
