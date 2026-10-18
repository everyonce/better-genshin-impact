const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-resupply.js');
const base=[['Item to purchase',790,252],['Chicken-Mushroom Skewer',754,336],['Qty.',928,494],['Left Today: 5',876,630],['Cost',866,679],['110300',1660,28],['Purchase',1105,756],['Cancel',715,757]].map(([text,x,y])=>({text,x,y}));
test('healing purchase is capped at five skewers and exactly2250 Mora from reviewed balance',()=>{
 const o={timestamp:1000,hud:{},ocr:[...base,{text:'5',x:946,y:534},{text:'2250',x:970,y:679}]};assert.equal(g.target(o,1000).action,'buyFive');
 for(const row of o.ocr){assert.equal(g.target({...o,ocr:o.ocr.filter(r=>r!==row)},1000),null);assert.equal(g.target({...o,ocr:[...o.ocr,row]},1000),null);}
 assert.equal(g.target(o,2001),null);assert.equal(g.target({...o,hud:{world:true}},1000),null);
});
test('quantity selection cannot submit a purchase and requires exact initial one-item modal',()=>{
 const o={timestamp:1000,hud:{},ocr:[...base,{text:'1',x:946,y:534},{text:'450',x:970,y:679},{text:'5',x:1216,y:584}]};assert.equal(g.target(o,1000).action,'setFive');assert.equal(g.target({...o,ocr:o.ocr.map(r=>r.text==='450'?{...r,text:'451'}:r)},1000),null);
});
test('recorded shop, modal, receipt and exhausted stock follow guarded stages',()=>{
 const fixtures=require('./act-two-resupply.fixture.json');const actions=['openPurchase','setFive','buyFive','continue','close',null];fixtures.forEach((f,i)=>assert.equal(g.target(f,f.timestamp)?.action||null,actions[i],String(f.frameId)));
});
test('ordinary purchased skewer is a healing food but toast and revival egg are not',()=>{
 const skewer=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-skewer.js');for(const [text,ok]of [['Chicken-Mushroom Skewer',true],["Fisherman's Toast",false],['Teyvat Fried Egg',false]])assert.equal(skewer.title([{text,x:1331,y:131}]),ok);
});
