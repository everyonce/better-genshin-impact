const test=require('node:test');
const assert=require('node:assert/strict');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

test('saved frame 448 full and crop Space boxes identify one physical airborne control',()=>{
  const full=[{text:'Space',x:1680,y:1024,width:69,height:31}];
  const crop=[{text:'Space',x:11,y:11,width:184,height:73}];
  const rows=bgi.mergeControlCropRows(full,crop,1680,1024);
  assert.deepEqual(rows,full);
  assert.equal(full.length,1,'caller rows are not mutated');
  const frame={timestamp:1000,map:null,ocr:[...rows,{text:'Kaeya',x:1664,y:487,width:88,height:36},{text:'Trial',x:1796,y:463,width:49,height:24}],
    hud:{world:false,groundControls:false,climbing:false,health:{current:1063,max:1427},auto:false,loading:false,unknownHud:false,
      objectiveChanged:false,dialogueReady:false,choice:false,journal:false,bigMap:false,tutorialStep:null}};
  assert.equal(bgi.wolfAirPauseOnlyHud(frame,1000),true);
});

test('control merging preserves distinct, disagreeing, distant, or malformed OCR boxes',()=>{
  const full=[{text:'Space',x:1680,y:1024,width:69,height:31}];
  for(const crop of [
    {text:'Space',x:60,y:-42,width:165,height:72},
    {text:'E',x:11,y:11,width:184,height:73},
    {text:'Space',x:11,y:11,width:0,height:73},
    {text:'Space',x:Infinity,y:11,width:184,height:73},
  ]) assert.equal(bgi.mergeControlCropRows(full,[crop],1680,1024).length,2);
  assert.equal(bgi.mergeControlCropRows([...full,...full],[],1680,1024).length,2,
    'independent full-frame ambiguity is not hidden');
});
