const test=require('node:test');
const assert=require('node:assert/strict');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

function active() {
  return {timestamp:1000,map:null,ocr:[
    {text:'Kaeya',x:1664,y:485},{text:'Trial',x:1802,y:463}
  ],hud:{world:false,groundControls:true,climbing:false,journal:false,bigMap:false,auto:false,
    objectiveChanged:false,dialogueReady:false,choice:false,tutorialStep:null,interact:false,
    health:{current:471,max:1427},enemyBars:[],enemyBarDiagnostic:{level:5,candidates:0,localReads:[]}}};
}

test('low-health travel requires an invoked detector with no candidates and exact Trial Kaeya',()=>{
  const o=active();assert.equal(bgi.wolfRecoveryTravelHud(o,1000),true);
  for(const change of [
    v=>{v.hud.health.current=428;},v=>{v.hud.health.max=1500;},
    v=>{v.hud.enemyBars=[{width:70}];},v=>{v.hud.enemyBarDiagnostic=null;},
    v=>{v.hud.enemyBarDiagnostic.candidates=1;},v=>{v.hud.enemyBarDiagnostic.localReads=[{}];},
    v=>{v.hud.enemyBarDiagnostic.level=4;},v=>{v.ocr.pop();},
    v=>{v.timestamp=-1;},v=>{v.timestamp=1001;}
  ]) {const value=active();change(value);assert.equal(bgi.wolfRecoveryTravelHud(value,1000),false);}
});

test('low-health travel stops for UI, interaction, climbing, and changed-objective states',()=>{
  for(const flag of ['journal','bigMap','auto','climbing','objectiveChanged','dialogueReady','choice','interact','loading','unknownHud']) {
    const o=active();o.hud[flag]=true;assert.equal(bgi.wolfRecoveryTravelHud(o,1000),false,flag);
  }
  const tutorial=active();tutorial.hud.tutorialStep='wolfInfo';assert.equal(bgi.wolfRecoveryTravelHud(tutorial,1000),false);
});

test('bounded recovery walking retains the five-percent damage-loss stop and default sixty-percent fallback',()=>{
  const o=active();assert.equal(bgi.wolfAdvanceState(o,1000).ok,true);
  assert.equal(bgi.wolfAdvanceState(o,1000,{current:543,max:1427}).ok,false);
  o.hud.enemyBarDiagnostic=null;assert.equal(bgi.wolfAdvanceState(o,1000).ok,false);
});
