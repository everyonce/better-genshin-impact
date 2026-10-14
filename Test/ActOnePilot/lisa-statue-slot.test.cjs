'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const context={};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8'),context);
function recorded(){return {session:'statue-test',frameId:604,timestamp:1000,
  hud:{groundControls:true,climbing:false,auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,
    tutorialStep:null,objectiveChanged:false,health:{current:787,max:1379},enemyBars:[],objectives:['Meet Lisa at the temple']},
  ocr:[{text:'Amber',x:1688,y:391,width:73,height:29},{text:'Kaeya',x:1664,y:485,width:78,height:36},
    {text:'Statue of The Seven',x:1216,y:520,width:279,height:35},{text:'F',x:1103.6667,y:522,width:28,height:33}]};}
const ready=(o,allowed=true,now=1000)=>context.actOneLionFieldWorld(o,now,'statue-test',0,allowed);
test('recorded selected Kaeya field grants Statue-only recovery without inferring a missing slot digit',()=>{
  const o=recorded();assert.equal(ready(o,false),false);assert.equal(ready(o),true);
  assert.equal(o.ocr.some(r=>r.text==='3'),false);
});
test('Statue fallback requires fresh living grounded party and unique exact NPC interaction evidence',()=>{
  for(const mutate of [o=>o.ocr.pop(),o=>o.ocr.push({...o.ocr[3]}),o=>o.ocr[2].text='Cooking',
    o=>o.ocr[2].x=700,o=>o.ocr.shift(),o=>o.ocr.push({...o.ocr[1]}),
    o=>o.hud.enemyBars=[{x:900,y:400,width:80,height:8}],o=>o.hud.health.current=0,
    o=>o.hud.climbing=true,o=>o.hud.dialogueReady=true,o=>o.hud.objectives=['Other quest'],
    o=>o.ocr.push({text:'Trial',x:1700,y:500}),o=>o.ocr.push({text:'3',x:1860,y:500},{text:'3',x:1870,y:500})]){
      const o=recorded();mutate(o);assert.equal(ready(o),false);
  }
  assert.equal(ready(recorded(),true,2001),false);
});
test('recorded third healing portrait is included only with unique card geometry',()=>{
  const third={text:'Lv.6',x:452,y:222,width:57,height:27};
  const targets=rows=>Array.from(context.actOneStatueHealingPortraits(rows));
  assert.deepEqual(targets([third]),[118,298,478]);
  for(const rows of [[],[third,third],[{...third,y:300}],[{...third,text:'6'}]])
    assert.deepEqual(targets(rows),[118,298]);
});

test('Statue-only recovery accepts the later Lisa stages but rejects ambiguity and unrelated quests',()=>{
  for(const objective of ['Talk to Lisa','Enter the temple']){
    const o=recorded();o.hud.objectives=[objective];o.hud.health={current:477,max:1363};
    assert.equal(ready(o),true);assert.equal(ready(o,false),false);
    o.hud.objectives.push('Meet Lisa at the temple');assert.equal(ready(o),false);
  }
  const o=recorded();o.hud.objectives=['Go to Mondstadt'];assert.equal(ready(o),false);
});

test('selected owned Kaeya is verified by the recorded max HP and two explicit other party slots',()=>{
  const o=recorded();o.ocr=o.ocr.slice(0,2).concat([
    {text:'Lumina',x:1682,y:303,width:83,height:24},{text:'1',x:1856,y:308,width:31,height:27},
    {text:'2',x:1856,y:397,width:31,height:29}]);
  assert.equal(ready(o,false),true);
  for(const mutate of [x=>x.hud.health.max=2000,x=>x.ocr.pop(),x=>x.ocr.push({...x.ocr[1]}),
    x=>x.ocr.push({text:'2',x:1856,y:488,width:31,height:31}),x=>x.hud.health.current=0]){
      const x=JSON.parse(JSON.stringify(o));mutate(x);assert.equal(ready(x,false),false);
  }
});
