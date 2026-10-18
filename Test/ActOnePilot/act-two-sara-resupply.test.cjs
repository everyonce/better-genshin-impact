const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
test('Sara resupply opens only exact selected city counter with healthy grounded Traveler',async()=>{
 const c={};vm.createContext(c);vm.runInContext(fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js'),'utf8'),c);
 const base={map:{map:'Teyvat',x:-887,y:2240},hud:{world:true,groundControls:true,health:{current:2764,max:2764},enemyBars:[],objectives:["Enter Raptor's Hideout"]},ocr:[{text:'Sara',x:1240,y:520,height:25},{text:'F',x:1120,y:520,height:25}]};
 const cases=[[{},1],[{map:{...base.map,x:-900}},0],[{map:{...base.map,map:'Domain'}},0],[{hud:{...base.hud,health:{current:2510,max:2764}}},0],[{hud:{...base.hud,climbing:true}},0],[{hud:{...base.hud,enemyBars:[{}]}},0],[{hud:{...base.hud,objectives:['Unknown']}},0],[{ocr:[base.ocr[0]]},0],[{ocr:[base.ocr[0],{...base.ocr[1],y:580}]},0]];
 for(const [patch,count]of cases){let presses=0;const o={...base,...patch};await c.ActOneMission.runQuestStep('actTwoSaraOpen',o,{runActTwoNavigationWithPause:async(_o,_s,fn)=>fn(o),keyPress:async k=>{assert.equal(k,'VK_F');presses++},sleep:async()=>{},checkStop:()=>{}},async()=>({hud:{dialogueReady:true}}));assert.equal(presses,count,JSON.stringify(patch));}
});
