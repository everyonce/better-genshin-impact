const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const source=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8');
const body=source.match(/runActTwoStatue: async function\(initial,observe\)\{([\s\S]*?)\n        \},/)[1];
async function run(rows,change={}){
 const inputs=[],o={timestamp:Date.now(),session:'s',frameId:1,hud:{},ocr:rows,...change};
 const fn=new Function('initial','observe','checkStop','ready','request','actTwoOriginalAccount','click','boundedKey','events','sleep','return (async()=>{'+body+'})();');
 const result=await fn(o,async()=>({...o,frameId:2}),()=>{},()=>{},{session:'s'},()=>true,(x,y)=>inputs.push([x,y]),async k=>inputs.push(k),[],async()=>{});return {result,inputs};
}
const row=(text,x,y)=>({text,x,y,width:100,height:30});
const offer=[row('Worship Statue',1340,195),row('Anemoculus 0/1',1720,195),row("Statue's Rewards",1515,252),row('Required Anemoculus',1491,840),row('Owned',1442,883),row('1',1438,911),row('Offer',1422,1001)];
test('Statue offering spends only one explicitly owned starter Anemoculus',async()=>{
 assert.equal((await run(offer)).result.action,'offerOne');
 for(const rows of [offer.filter(r=>r.text!=='1'),offer.map(r=>r.text==='Anemoculus 0/1'?{...r,text:'Anemoculus 0/2'}:r),[...offer,row('Offer',1422,1001)]])await assert.rejects(run(rows),/Statue speaker/);
});
test('Statue stale, world and different-session frames cannot act',async()=>{
 for(const change of [{timestamp:Date.now()-2000},{hud:{world:true}},{session:'other'}])await assert.rejects(run(offer,change),/Fresh original/);
});
test('Statue dialogue advances once or chooses only exact worship option',async()=>{
 const dialogue=[row('Auto',100,30),row('Statue of The Seven',785,850)];
 assert.deepEqual((await run(dialogue)).inputs,['VK_SPACE']);
 assert.equal((await run([...dialogue,row('Worship Statue',1320,612)],{hud:{choice:true}})).result.action,'worship');
 assert.deepEqual((await run([...dialogue,row('Offer All',1320,612)],{hud:{choice:true}})).inputs,[]);
});
