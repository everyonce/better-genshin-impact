const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-clock.js');
const o={session:'s',timestamp:1000,map:{map:'Teyvat',x:-831.36,y:2189.45},ocr:[{text:'UID: 693306810',x:1680,y:1050}],hud:{world:true,groundControls:true,health:{current:2313,max:2313},enemyBarDiagnostic:{level:'any'},enemyBars:[],objectives:[]}};
test('daytime check requires the fresh safe quest-giver terrace',()=>{
 assert.equal(g.ready(o,1000,'s'),true);
 for(const p of [{session:'other'},{timestamp:0},{map:{...o.map,x:-900}},{ocr:[]},{ocr:[{text:'UID: 123456789',x:1680,y:1050}]},...[{climbing:true},{groundControls:false},{world:false},{enemyBars:[{}]},{health:{current:2300,max:2313}},{objectives:['Talk to Amber']},{dialogueReady:true},{choice:true}].map(h=>({hud:{...o.hud,...h}}))])assert.equal(g.ready({...o,...p},1001,'s'),false);
});

test('daytime request enables the existing threat diagnostic',()=>{const fs=require('node:fs'),s=fs.readFileSync('BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js','utf8');assert.ok(s.includes("['actTwoDaytime','actTwoMageNative','actTwoMageFinish'"));});
