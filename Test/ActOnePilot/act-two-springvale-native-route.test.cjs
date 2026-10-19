const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js','utf8');
const mission=fs.readFileSync('BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js','utf8');
test('known Lion waypoint can establish the exact Galesong map guard for Springvale native teleport',async()=>{
 assert.match(source,/actTwoSpringvaleTeleport'\?\{x:-867\.23413,y:1992\.874\}/);
 assert.match(source,/request\.step==='actTwoSpringvaleTeleport'&&!rows\.some\(function\(r\)\{return r\.text\.trim\(\)==='Galesong Hill'&&r\.x>=1500&&r\.y>=950;/);
 const c={};vm.createContext(c);vm.runInContext(mission,c);
 const calls=[],api={runLisaWindriseTeleport:async o=>{calls.push(o);return {status:'completed'}}};
 for(const step of ['actTwoLionTeleport','actTwoSpringvaleTeleport']){
  const map={hud:{bigMap:true},ocr:[{text:step==='actTwoSpringvaleTeleport'?'Galesong Hill':'Starfell Valley',x:1600,y:990}]};
  assert.equal((await c.ActOneMission.runQuestStep(step,map,api,async()=>map)).status,'completed');
 }
 assert.equal(calls.length,2);
});
