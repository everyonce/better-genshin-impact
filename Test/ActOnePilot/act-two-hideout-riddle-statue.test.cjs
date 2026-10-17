const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
test('riddle recovery uses only the existing safe Windrise corridor and exact selected Statue',async()=>{
 const context={file:{readTextSync:()=>fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-interaction.js'),'utf8')}};
 vm.createContext(context);vm.runInContext(fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js'),'utf8'),context);
 const base={map:{map:'Teyvat',x:-1266.34,y:1933.05,cameraAngle:269},hud:{world:true,groundControls:true,enemyBars:[],objectives:['Look for the location in the riddle']},ocr:[]};
 for(const [patch,count] of [[{},6],[{map:{...base.map,x:0}},0],[{map:{...base.map,cameraAngle:90}},0],[{hud:{...base.hud,enemyBars:[{}]}},0]]){
  const field={...base,...patch};let steps=0;await context.ActOneMission.runQuestStep('actTwoStatueOpen',field,{runActTwoNavigationWithPause:async(o,observe,fn)=>fn(field),descendClimb:async ms=>{assert.equal(ms,600);steps++},keyPress:async()=>{throw Error('No unrecognized interaction')},sleep:async()=>{},checkStop:()=>{}},async()=>field);assert.equal(steps,count);
 }
});
