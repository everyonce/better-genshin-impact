const test=require('node:test'),assert=require('node:assert/strict'),v=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-visual.js');
const p={reviewed:true,session:'test',frameId:10,witnessFrameId:9,createdAt:1000,mode:'base',actions:[{type:'key',key:'VK_S',ms:800},{type:'look',dx:0,dy:-500}]},req={session:'test',expectedFrameId:10};
test('visual plan bounds identity, age, replay and action budget',()=>{
 assert.equal(v.plan(p,req,1001),true);
 for(const bad of [{usedAt:1001},{session:'other'},{createdAt:2000},{createdAt:-130000},{frameId:11},{witnessFrameId:10},{mode:'other'},
 {actions:[{type:'key',key:'VK_X',ms:60}]},{actions:[{type:'key',key:'VK_W',ms:801}]},{actions:[{type:'look',dx:751,dy:0}]},
 {actions:Array(4).fill({type:'key',key:'VK_W',ms:800})},{mode:'climb',actions:[{type:'key',key:'VK_SPACE',ms:60}]}])assert.equal(v.plan({...p,...bad},req,1001),false);
});
test('visual field requires fresh safe clue context, witnessed vicinity and full health',()=>{
 const o={session:'test',timestamp:1000,map:{map:'Teyvat',x:-842,y:2215},hud:{world:true,groundControls:true,health:{current:1700,max:1700},enemyBarDiagnostic:{},enemyBars:[],objectives:['Solve the mystery (Go to Kaeya at the Knights of Favonius','HQ for a hint)']}};
 assert.equal(v.field(o,o,1001,'test','base'),true);
 for(const h of [{climbing:true},{health:{current:1699,max:1700}},{enemyBarDiagnostic:null},{enemyBars:[{}]},{objectives:['Another quest']},{dialogueReady:true}])assert.equal(v.field({...o,hud:{...o.hud,...h}},o,1001,'test','base'),false);
 assert.equal(v.field(o,o,2001,'test','base'),false);assert.equal(v.field({...o,map:{...o.map,x:-830}},o,1001,'test','base'),false);
});
