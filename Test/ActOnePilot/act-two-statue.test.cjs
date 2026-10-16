const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const source=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8');
const body=source.match(/runActTwoStatue: async function\(initial,observe\)\{([\s\S]*?)\n        \},/)[1];
const healingVerifier=source.slice(source.indexOf('function actOneStatueHealingVerified('),source.indexOf('function actOneStatueHealingPortraits('));
async function run(rows,change={}){
 const inputs=[],o={timestamp:Date.now(),session:'s',frameId:1,hud:{},ocr:rows,...change};
 const fn=new Function('initial','observe','checkStop','ready','request','actTwoOriginalAccount','click','boundedKey','events','sleep','return (async()=>{'+body+'})();');
 const result=await fn(o,async()=>({...o,frameId:2}),()=>{},()=>{},{session:'s'},()=>true,(x,y)=>inputs.push([x,y]),async k=>inputs.push(k),[],async()=>{});return {result,inputs};
}
const row=(text,x,y)=>({text,x,y,width:100,height:30});
test('Repeat Statue visit allows no active quest only at its selected Windrise interaction',async()=>{
 const vm=require('node:vm'),missionSource=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js'),'utf8'),interaction=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-interaction.js'),'utf8');
 const context={file:{readTextSync:()=>interaction}};vm.createContext(context);vm.runInContext(missionSource,context);
 const base={map:{x:-1265.917,y:1928.381},hud:{objectives:[],world:true,groundControls:true,enemyBars:[]},ocr:[row('Statue of The Seven',1200,520),row('F',1100,520)]};
 for(const [field,expected] of [[base,1],[{...base,hud:{...base.hud,objectives:['Follow the routeand fly to the finish line in time']}},1],[{...base,hud:{...base.hud,objectives:['Follow the route and fly to the finish line in time']}},1],[{...base,map:{x:0,y:0}},0],[{...base,hud:{objectives:['Another quest']}},0],[{...base,ocr:[]},0]]){
  let inputs=0;await context.ActOneMission.runQuestStep('actTwoStatueOpen',{}, {runActTwoNavigationWithPause:async(o,observe,fn)=>fn(field),keyPress:async()=>inputs++,sleep:async()=>{},checkStop:()=>{}},async()=>({hud:{dialogueReady:true},frameId:2}));assert.equal(inputs,expected);
 }
});
const offer=[row('Worship Statue',1340,195),row('Anemoculus 0/1',1720,195),row("Statue's Rewards",1515,252),row('Required Anemoculus',1491,840),row('Owned',1442,883),row('1',1438,911),row('Offer',1422,1001)];
test('Statue offering spends only one explicitly owned starter Anemoculus',async()=>{
 assert.equal((await run(offer)).result.action,'offerOne');
 for(const rows of [offer.filter(r=>r.text!=='1'),offer.map(r=>r.text==='Anemoculus 0/1'?{...r,text:'Anemoculus 0/2'}:r),[...offer,row('Offer',1422,1001)]])await assert.rejects(run(rows),/Statue speaker/);
});
test('Statue stale, world and different-session frames cannot act',async()=>{
 for(const change of [{timestamp:Date.now()-2000},{hud:{world:true}},{session:'other'}])await assert.rejects(run(offer,change),/Fresh original/);
});
test('Level two Offer All is bounded to exactly two owned Anemoculi',async()=>{
 const rows=[row('Worship Statue',1340,195),row('Anemoculus 0/2',1716,195),row('Current Stamina Limit: 107/240',1438,339),row('Required Anemoculus',1491,840),row('Owned',1442,883),row('2',1436,909),row('Offer All',1692,1001)];
 assert.deepEqual((await run(rows)).inputs,[[1740,1018]]);
 for(const text of ['1','3','20'])await assert.rejects(run(rows.map(r=>r.text==='2'?{...r,text}:r)));
});
test('Odd-sized dialogue boxes use integer BetterGI click coordinates',async()=>{
 const rows=[row('Auto',100,30),row('Statue of The Seven',785,850),{text:'Worship Statue',x:1324,y:613,width:229,height:35}];
 assert.deepEqual((await run(rows,{hud:{choice:true}})).inputs,[[1439,631]]);
});
test('Statue dialogue advances once or chooses only exact worship option',async()=>{
 const dialogue=[row('Auto',100,30),row('Statue of The Seven',785,850)];
 assert.deepEqual((await run(dialogue)).inputs,['VK_SPACE']);
 assert.equal((await run([...dialogue,row('Worship Statue',1320,612)],{hud:{choice:true}})).result.action,'worship');
 assert.deepEqual((await run([...dialogue,row('Offer All',1320,612)],{hud:{choice:true}})).inputs,[]);
});

test('healing animation OCR gap is retried within a bound and never bypasses the original panel guard',async()=>{
 const base=[row("Statue's Blessing",1515,23),row('Restorative Power: 9736 / 10000',1391,590),{text:'Lv.20',x:441,y:213,width:73,height:38}],instruction=row('In combat Click on the character portrait to restore HP',28,34);
 for(const recovers of [true,false]){
  let reads=0,heals=0,keys=0;const initial={session:'s',timestamp:Date.now(),hud:{},ocr:base};
  const factory=new Function('checkStop','ready','request','actTwoOriginalAccount','click','boundedKey','events','sleep',healingVerifier+'\nreturn async function(initial,observe){'+body+'}');
  const fn=factory(()=>{},()=>{},{session:'s',step:'actTwoStatueHeal'},()=>true,()=>{},async()=>keys++,[],async()=>{});
  let current=initial;const api={healTravelerAtStatue:async()=>{if(!current.ocr.some(r=>r.text.includes('Click on')))throw Error('Fresh Statue healing panel required');heals++;},finishActTwoDialogue:async()=>({pauseVerified:true})};
  const invoke=()=>fn.call(api,initial,async()=>{reads++;current={...initial,hud:{world:keys>0},ocr:recovers?[...base,instruction]:base};return current;});
  if(recovers){assert.equal((await invoke()).pauseVerified,true);assert.equal(heals,3);assert.equal(keys,1);}
  else{await assert.rejects(invoke(),/Fresh Statue healing panel/);assert.equal(heals,0);assert.equal(keys,0);assert.equal(reads,4);}
 }
});
