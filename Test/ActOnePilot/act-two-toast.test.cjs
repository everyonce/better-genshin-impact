const test=require('node:test'),assert=require('node:assert/strict'),gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-toast.js');
const rows=[['Item to purchase',790,252],["Fisherman's Toast",754,338],['Qty.',928,494],['1',944,532],['Left Today: 5',878,631],['Cost',864,679],['1025',944,679],['71120',1676,28],['Purchase',1105,756],['Cancel',715,757]].map(([text,x,y])=>({text,x,y,width:100,height:30}));
test('Sara food dialogue only enters the shop and does not accept generic spending',()=>{
 const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
 const o={hud:{choice:true},ocr:[{text:'Sara',x:916,y:850},{text:'Can I get food to-go?',x:1320,y:560}]};
 assert.equal(mission.selectDialogueChoice(o),'Can I get food to-go?');o.ocr.push({text:'Buy with Primogems',x:1320,y:630});assert.equal(mission.selectDialogueChoice(o),null);
});
test('Quest toast purchase requires one item, exact Mora cost and unchanged starting stock/balance',()=>{
 const o={timestamp:1000,hud:{},ocr:rows};assert.equal(gate.target(o,1000).action,'buyOne');
 for(const t of ['1','1025','71120','Left Today: 5',"Fisherman's Toast",'Cost'])assert.equal(gate.target({...o,ocr:rows.filter(r=>r.text!==t)},1000),null);
 assert.equal(gate.target({...o,ocr:[...rows,rows[8]]},1000),null);assert.equal(gate.target(o,2001),null);assert.equal(gate.target(o,999),null);assert.equal(gate.target({...o,hud:{world:true}},1000),null);
});
