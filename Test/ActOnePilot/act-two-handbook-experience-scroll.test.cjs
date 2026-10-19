const test=require('node:test'),assert=require('node:assert/strict');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-handbook.js');
const rows=[['Chapter 2',1340,185],['Experience',230,228],['Investigation Progress',414,269],['4/8',513,358],['Open 30 chests',880,421],['18/30',886,453],['Enhance a weapon to Lv. 10',880,796]].map(([text,x,y])=>({text,x,y}));
const witness={session:'chapter2',timestamp:100000,map:null,hud:{world:false,dialogueReady:false},ocr:rows};
test('reviewed Chapter 2 experience page scrolls within its objective list',()=>{
 assert.deepEqual(gate.target(witness,100100,null,'experienceScroll'),{action:'scrollExperience',x:1000,y:650,scroll:-8});
 const shifted={...witness,ocr:rows.map(r=>r.x>=850&&r.y>=266?{...r,y:r.y-54}:r).concat({text:'Equip 4 artifacts on a single',x:878,y:852})};
 assert.deepEqual(gate.target(shifted,100100,null,'experienceScroll'),{action:'scrollExperience',x:1000,y:650,scroll:-8});
 for(const label of ['Chapter 2','4/8','18/30','Enhance a weapon to Lv. 10'])assert.equal(gate.target({...witness,ocr:rows.filter(r=>r.text!==label)},100100,null,'experienceScroll'),null,label);
 assert.equal(gate.target(witness,101001,null,'experienceScroll'),null);
 assert.equal(gate.target({...witness,hud:{world:true,dialogueReady:false}},100100,null,'experienceScroll'),null);
});
