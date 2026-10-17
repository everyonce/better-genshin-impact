const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const source=fs.readFileSync('BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js','utf8');
const body=source.slice(source.indexOf('nativeCombat:async function(o){',source.indexOf('runActTwoField: async function')),source.indexOf('key:async function(k,ms,o){safe(o);',source.indexOf('runActTwoField: async function'))).trim().replace(/,$/,'');
async function exercise(probe,hp,sampleHp){
 let calls=[],released=0;
 const p={nativeCombat:true,enemyLevel:13,regionWitness:{},nativeAvatar:'Kaeya',shieldProbe:probe,shieldReviewed:probe};
 const observation={frameId:1,hud:{health:{current:hp,max:4015},groundControls:true},ocr:[]};
 const guard={nativeHealth:()=>true,combatTargets:()=>[{}],leyLine:()=>true};
 const nativeSource=fs.readFileSync('BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-native-combat.js','utf8');
 const file={readTextSync:()=>nativeSource.replace('function leyLineProfile(p){','function leyLineProfile(p){')};
 const ng=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-native-combat.js');
 file.readTextSync=()=>`var ActTwoNativeCombat=testNative;`;
 const testNative=ng;const original=ng.chunk;ng.chunk=async(native,stop,options)=>{calls.push({seconds:param.Timeout,strategy:param.name,deadline:options.timeoutMs,sample:options.sampleAfterMs});try{await options.sample();return {nativeReturned:true};}finally{native.release();}};
 let param;function AutoFightParam(name){param=this;this.name=name;this.FinishDetectConfig={};}
 const api=eval('({'+body+'})');
 const safe=()=>{},witness={},events=[],actTwoRegionalCombatStrategy=()=> 'ordinary',release=()=>released++,keyUp=()=>{},leftButtonUp=()=>{},rightButtonUp=()=>{},checkStop=()=>{},ready=()=>{},sleep=async()=>{},observe=async()=>({...observation,hud:{...observation.hud,health:{current:sampleHp,max:4015}}}),actTwoOriginalAccount=()=>true,dispatcher={};
 try{return {value:await api.nativeCombat(observation),calls,released};}finally{ng.chunk=original;}
}
test('actual adapter uses two-second probe and85percent sampled floor',async()=>{const r=await exercise(true,4015,4015);assert.deepEqual(r.calls,[{seconds:2,strategy:'English Whopperflower Shield Probe',deadline:3000,sample:750}]);assert.equal(r.released,1);await assert.rejects(exercise(true,4015,3300),/sampled health/);await assert.rejects(exercise(true,3300,3300),/below85/);});
test('ordinary adapter retains its proven six-second strategy',async()=>{const r=await exercise(false,3500,3000);assert.deepEqual(r.calls,[{seconds:6,strategy:'ordinary',deadline:8000,sample:2500}]);});
