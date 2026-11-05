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

test('actual Gate map OCR can establish Starfell from three distinct map labels and the region footer',()=>{
 const c={};vm.createContext(c);vm.runInContext(source,c);
 const row=(text,x,y)=>({text,x,y,width:130,height:30});
 const rows=[row('Mondstadt',578,292),row('Windrise',1063,738),row('Starfell Lake',1130,93),
  row('StarFelVauleyas',1588,979),row('Exploration Progress: 16%',1504,1020)];
 const o={session:'s',frameId:8,timestamp:1000,map:null,hud:{bigMap:true,world:false},ocr:rows};
 assert.equal(c.actOneStarfellMapFooter(rows).text,'StarFelVauleyas');
 assert.equal(c.actOneLocalPauseProof(o,1000,'s').kind,'map');
 for(const subset of [rows.slice(1),rows.slice(0,3),[...rows,rows[0]]])assert.equal(c.actOneStarfellMapFooter(subset),null);
 assert.equal(c.actOneLocalPauseProof(o,3000,'s'),null);
});
