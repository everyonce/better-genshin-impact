'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'lion-field-combat-adapter.test.cjs'),'utf8');
const sandbox={require,module:{exports:{}},__dirname,setImmediate};
vm.runInNewContext(source.slice(0,source.indexOf('\nfunction assertPauseProof'))+'\nmodule.exports={fixture,row};',sandbox);
const {row}=sandbox.module.exports;
function fixture(options){const f=sandbox.module.exports.fixture(options);f.context.click=(x,y)=>f.inputs.push({kind:'click',x,y});return f;}
function menu(f,patch={}){return {session:'lion-adapter-test',frameId:1,timestamp:f.context.Date.now(),map:null,
 hud:{world:false,auto:false,loading:false,bigMap:false,dialogueReady:false,choice:false},
 ocr:[row('Cryo / Kaeya',138,26),...['Attributes','Weapons','Artifacts','Constellation','Talents'].map((v,i)=>row(v,140,140+i*70)),
 row('Base ATK',1460,230),row('Switch',1500,990)],...patch};}
test('weapon inspection opens two menus without spending, equipping or enhancing',async()=>{
 const f=fixture({step:'lisaWeaponSwitch'}),o=menu(f);let polls=0;
 const r=await f.adapter.runLisaWeaponSwitch(o,async()=>{polls++;return menu(f,{frameId:polls+1});});
 assert.equal(r.status,'completed');assert.equal(r.resourcesSpent,false);assert.equal(polls,2);
 assert.deepEqual(Array.from(r.panels,x=>x.label),['Weapons','Switch']);assert.equal(f.inputs.length,2);
});
test('stale or foreign character menus send no input',async()=>{
 for(const patch of [{timestamp:0},{session:'other'},{ocr:[row('Cryo / Kaeya',138,26)]}]){
  const f=fixture({step:'lisaWeaponSwitch'});const r=await f.adapter.runLisaWeaponSwitch(menu(f,patch),async()=>assert.fail());
  assert.equal(r.status,'stopped');assert.equal(f.inputs.length,0);
 }
});
test('a missing weapon detail or ambiguous Switch stops before the second click',async()=>{
 for(const change of [rows=>rows.filter(r=>r.text!=='Base ATK'),rows=>[...rows,row('Switch',1520,990)]]){
  const f=fixture({step:'lisaWeaponSwitch'});const r=await f.adapter.runLisaWeaponSwitch(menu(f),async()=>{const o=menu(f);o.ocr=change(o.ocr);return o;});
  assert.equal(r.status,'stopped');assert.equal(f.inputs.length,1);assert.equal(r.resourcesSpent,false);
 }
});
function choice(patch={},equipped=false){
 const p={session:'lion-adapter-test',frameId:5,reviewed:true,createdAt:9950,action:'equip',name:'Cool Steel',baseAttack:39,...patch};
 const f=fixture({step:'lisaWeaponChoice',initialFrame:5,expectedFrameId:5,seedFiles:{'lisa-weapon-choice.json':p}});
 const o=menu(f,{frameId:5,ocr:[row('Weapon Selection',137,28),row('Base ATK',1468,224),row('Cool Steel',1460,133),row('39',1808,222),row('Switch',1512,993)]});
 if(equipped)o.ocr.push(row('Equipped: Lumina',1522,923));
 return {f,o};
}
test('one reviewed reversible equip consumes its permit and verifies the resulting owner and sword',async()=>{
 const {f,o}=choice();const r=await f.adapter.runLisaWeaponChoice(o,async()=>({...o,timestamp:f.context.Date.now(),ocr:[...o.ocr,row('Equipped: Kaeya',1522,923)]}));
 assert.equal(r.equippedVerified,true);assert.equal(r.resourcesSpent,false);assert.equal(f.inputs.length,1);
 const second=await f.adapter.runLisaWeaponChoice({...o,timestamp:f.context.Date.now()},async()=>assert.fail());
 assert.equal(second.status,'stopped');assert.equal(f.inputs.length,1);
});
test('equipment action rejects another owner, a reused/foreign permit and unmatched sword stats',async()=>{
 for(const [patch,equipped] of [[{},true],[{usedAt:9990},false],[{session:'foreign'},false],[{baseAttack:40},false],[{action:'enhance'},false],[{reviewed:false},false]]){
  const {f,o}=choice(patch,equipped);const r=await f.adapter.runLisaWeaponChoice(o,async()=>assert.fail());
  assert.equal(r.status,'stopped');assert.equal(f.inputs.length,0);
 }
});
test('back from a verified weapon list sends one released Escape and no click',async()=>{
 const {f,o}=choice({action:'back'});const r=await f.adapter.runLisaWeaponChoice(o,async()=>menu(f));
 assert.equal(r.status,'completed');assert.equal(r.resourcesSpent,false);
 assert.deepEqual(Array.from(f.inputs.filter(x=>x.kind==='down'),x=>x.key),['VK_ESCAPE']);
 assert.equal(f.inputs.filter(x=>x.kind==='click').length,0);assert.equal(f.getOverlappingKeyDowns().length,0);
});
