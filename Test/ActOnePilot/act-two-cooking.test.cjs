const test=require('node:test'),assert=require('node:assert/strict'),c=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-cooking.js');
test('three-dish errand permits only the three reviewed remaining ingredient pairs',()=>{
 const row=(text,x,y)=>({text,x,y}),base=[row('Cook',140,32),row('Chicken-Mushro',78,298),row('om Skewer',98,315),row('Cook Manually',850,990),row('Cooking ingredients required',75,411),row('Amber',1716,292),row('No Character Bonus',1624,349)];
 for(const [m,f,ok] of [[5,14,true],[4,13,true],[3,12,true],[2,11,false],[0,14,false],[5,13,false]]){
  const o={timestamp:1000,hud:{},ocr:[...base,row(m+'/1',100,530),row(f+' /1',210,530)]};
  assert.equal(c.target(o,1000)?.action,ok?'manual':undefined);
 }
 const panel={timestamp:1000,hud:{},ocr:[row('Cook',140,32),row('Chicken-Mushroom Skewer',1330,130),row('Ingredients',1330,580),row('Proficiency: 4/5',1330,430),row('Cook',1650,1000)]};
 assert.equal(c.target(panel,1000).action,'prepare');panel.ocr[3].text='Proficiency: 5/5';assert.equal(c.target(panel,1000),null);
});
test('cooking peak requires stable target color then substantial loss',()=>{const s={peak:null,candidate:null,stable:0};for(const n of [0,600,740,745,743,730,700])assert.equal(c.peak(s,n),false);assert.equal(c.peak(s,440),true);});
test('manual cooking requires exact recipe and one mushroom and non-special cook',()=>{const row=(text,x,y)=>({text,x,y});const o={timestamp:1000,hud:{},ocr:[row('Cook',140,32),row('Chicken-Mushro',78,298),row('om Skewer',98,315),row('Cook Manually',850,990),row('Cooking ingredients required',75,411),row('1/1',100,530),row('3/1',210,530),row('Amber',1716,292),row('No Character Bonus',1624,349)]};assert.equal(c.target(o,1000).action,'manual');assert.equal(c.target(o,2001),null);o.ocr[5].text='0/1';assert.equal(c.target(o,1000),null);});
