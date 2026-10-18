const test=require('node:test'),assert=require('node:assert/strict'),g=require(process.env.ACT_TWO_FIELD_MODULE||'../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js'),o=require('./act-two-wind-seal-injured.fixture.json'),map=require('./act-two-wind-seal-map.fixture.json');
const p={reviewed:true,session:o.session,frameId:8497,witnessFrameId:o.frameId,createdAt:o.timestamp,mode:'combat',windSealCombat:true,nativeCombat:true,enemyLevel:9,nativeAvatar:'Kaeya',regionMapFrameId:map.frameId,visualPositionReviewed:true,actions:[]},r={session:o.session,expectedFrameId:8497};
test('Lv9 native plan requires exact Eye flag, verified starter and bounded stationary windows',()=>{
 assert(g.plan(p,r,o.timestamp));
 for(const patch of [{windSealCombat:undefined},{windSealCombat:false},{nativeAvatar:'Lumina'},{nativeCombat:false},{enemyLevel:10},{mode:'actions'},{actions:[{type:'key',key:'VK_W',ms:600}]},{regionMapFrameId:undefined}])assert(!g.plan({...p,...patch},r,o.timestamp));
});
test('recorded damaged Eye witness is eligible above85percent; identity, health and session remain required',()=>{
 assert.equal(g.originalWitnessFailure(o,{...p,regionWitness:map},r,o.timestamp),null);
 const ready=q=>g.ready({...q,hud:{...q.hud,enemyBarDiagnostic:{level:9}}},o,q.timestamp,o.session,false,true,false,false,map,false,true);
 assert(ready(o));assert(!ready({...o,hud:{...o.hud,health:{current:3412,max:4015}}}));assert(!ready({...o,session:'other'}));
 for(const text of ['Eye of the Storm','Restless Pure Elemental','Lv.9'])assert(!g.windSealEncounter({...o,ocr:o.ocr.filter(r=>r.text!==text)}));
});

test('combat map geometry reuses explicit30minute policy; default travel still expires at10minutes',()=>{assert(!g.regionalMap(map,map.timestamp+900000,map.session));assert(g.regionalMap(map,map.timestamp+900000,map.session,1800000));assert(!g.regionalMap(map,map.timestamp+1800001,map.session,1800000));});

test('Eye strategy uses a real installed English alias and bounded Cryo/physical commands',()=>{
 const fs=require('node:fs'),path=require('node:path'),root=path.resolve(__dirname,'../..');const avatars=JSON.parse(fs.readFileSync(path.join(root,'BetterGenshinImpact/GameTask/AutoFight/Assets/combat_avatar.json'),'utf8').replace(/^\uFEFF/,''));
 const lines=fs.readFileSync(path.join(root,'tools/quest-pilot/strategies/English Eye Cryo.txt'),'utf8').split(/\r?\n/).filter(t=>t.trim()&&!t.startsWith('//'));assert.equal(lines.length,1);const alias=lines[0].split(' ')[0];assert.equal(alias,'Kaeya');assert(avatars.some(v=>v.nameEn==='Kaeya'&&v.alias.includes(alias)));assert(!lines[0].includes('keypress(q)'));assert(!/keydown|walk|dash/.test(lines[0]));
});

test('support admits one bounded camera or party switch only, no movement or multi-action replay',()=>{const q={...p,mode:'actions',enemyLevel:undefined,nativeCombat:undefined,windSealCombat:undefined,windSealSupport:true,actions:[{type:'look',dx:500,dy:0}]};assert(g.plan(q,r,o.timestamp));assert(g.plan({...q,actions:[{type:'key',key:'VK_2',ms:60}]},r,o.timestamp));assert(!g.plan({...q,actions:[{type:'key',key:'VK_W',ms:600}]},r,o.timestamp));assert(!g.plan({...q,actions:[q.actions[0],q.actions[0]]},r,o.timestamp));assert(g.nativeHealth('Amber',1733));assert(!g.nativeHealth('Amber',4015));});

test('actual full Amber Eye world frame passes fresh native entry, with no permission for other1733HP encounters',()=>{const a=require('./act-two-wind-seal-amber-world.fixture.json'),m={...map,timestamp:a.timestamp-1000};const ready=q=>g.ready(q,q,q.timestamp,q.session,false,true,false,false,m,false,true);assert(ready(a));assert(!ready({...a,ocr:a.ocr.filter(r=>r.text!=='Eye of the Storm')}));assert(!ready({...a,hud:{...a.hud,health:{current:1473,max:1733}}}));});

test('four local ranged windows require bar reduction after each, stop on health loss or stall',async()=>{
 const base=require('./act-two-wind-seal-amber-world.fixture.json');
 for(const mode of ['progress','stall','damage']){
 let now=base.timestamp,calls=0,releases=0;const q={...p,nativeAvatar:'Amber',nativeWindows:4,regionWitness:{...map,timestamp:now-1000}};
 const api={now:()=>now,checkStop(){},sleep:async ms=>now+=ms,release:async()=>releases++,nativeCombat:async()=>{calls++;now+=2000;return{nativeReturned:true,nativeMs:2000};}};
 const result=await g.run(base,base,q,api,async()=>({...base,timestamp:now,frameId:base.frameId+calls,hud:{...base.hud,health:{current:mode==='damage'?1713:1733,max:1733},windSealBoss:{level:9,barFraction:mode==='stall'?1:1-.05*calls}}}));
 assert.equal(calls,mode==='progress'?4:1);assert.equal(result.nativeWindows.length,calls);assert.equal(releases,1);assert.equal(result.bossProgressVerified,mode!=='stall');
 }
});

test('wrong-identity original witness is refused before unpause',()=>{assert.equal(g.originalWitnessFailure({...o,ocr:o.ocr.filter(r=>r.text!=='Eye of the Storm')},{...p,regionWitness:map},r,o.timestamp),'witness_exact_eye_identity_required');});
