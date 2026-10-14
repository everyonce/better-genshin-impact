const test=require('node:test'),assert=require('node:assert/strict');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-journal.js');
const quest="Welcome to the Adventurers' Guild";
const o={timestamp:1000,hud:{journal:true},ocr:[{text:'In Progress',x:135,y:26,width:153,height:41},{text:' Archon Quests',x:148,y:113,width:233,height:41},{text:quest,x:177,y:889,width:438,height:29}]};
const p={session:'s',frameId:52,reviewed:true,createdAt:1000,action:'select',quest};const request={session:'s',expectedFrameId:52};
test('journal permits only unique approved quest targets on fresh pinned screens',()=>{
 assert.deepEqual(gate.target(o,1000,p,request),{x:396,y:904});
 for(const patch of [{quest:'Unrelated quest'},{action:'spend'},{consumed:true},{reviewed:false},{session:'x'},{frameId:51},{createdAt:-60000}])assert.equal(gate.target(o,1000,{...p,...patch},request),null);
 assert.equal(gate.target(o,2001,p,request),null);assert.equal(gate.target({...o,ocr:[...o.ocr,o.ocr[2]]},1000,p,request),null);
});
test('Navigate requires the selected right-hand quest title',()=>{
 const n={...o,ocr:[...o.ocr,{text:'Navigate',x:1650,y:1000,width:150,height:35}]};
 assert.equal(gate.target(n,1000,{...p,action:'navigate'},request),null);
 n.ocr.push({text:quest,x:870,y:120,width:500,height:40});
 assert.deepEqual(gate.target(n,1000,{...p,action:'navigate'},request),{x:1725,y:1018});
});
