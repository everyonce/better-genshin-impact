const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-map.js');
const p={reviewed:true,session:'s',frameId:10,createdAt:1000,action:'inspectEastBlueMarker'},r={session:'s',expectedFrameId:10};
const o={timestamp:1000,hud:{bigMap:true},ocr:[{text:'Mondstadt',x:962,y:417,width:129},{text:'Cider Lake',x:980,y:250,width:127},{text:'Windrise',x:1270,y:701,width:105}]};
test('blue marker inspection requires three unchanged map anchors and one-use fresh permit',()=>{
 assert.deepEqual(g.target(o,1001,p,r),{x:1458,y:522});
 assert.deepEqual(g.target(o,1001,{...p,action:'zoomRegionalMap'},r),{x:48,y:444});
 for(const patch of [{consumed:true},{session:'other'},{frameId:9},{createdAt:-60000}])assert.equal(g.target(o,1001,{...p,...patch},r),null);
 assert.equal(g.target(o,2001,p,r),null);
 for(const rows of [o.ocr.slice(1),o.ocr.concat(o.ocr[0]),o.ocr.map(q=>({...q,x:q.x+6})),o.ocr.map(q=>({...q,width:q.width*2}))])assert.equal(g.target({...o,ocr:rows},1001,p,r),null);
 assert.equal(g.target({...o,hud:{bigMap:false}},1001,p,r),null);
});
test('inspection panel close requires the exact region, title, close and teleport controls',()=>{
 const panel={...o,hud:{bigMap:false},ocr:[{text:'Starsnatch Cliff, Mondstadt',x:1472,y:103},{text:'Teleport Waypoint',x:1492,y:22},{text:'X',x:1848,y:8},{text:'Teleport',x:1626,y:989}]},plan={...p,action:'closeInspectedWaypoint'};
 assert.deepEqual(g.target(panel,1001,plan,r),{x:1876,y:34});
 for(let i=0;i<4;i++)assert.equal(g.target({...panel,ocr:panel.ocr.filter((_,n)=>n!==i)},1001,plan,r),null);
});
test('flower icon inspection is restricted to the newly witnessed zoom level',()=>{
 const zoomed={...o,ocr:[{text:'Mondstadt',x:980,y:373,width:149},{text:'Cider Lake',x:1004,y:139,width:149},{text:'Windrise',x:1405,y:765,width:124}]},plan={...p,action:'inspectBlossomIcon'};
 assert.deepEqual(g.target(zoomed,1001,plan,r),{x:956,y:969});
 assert.equal(g.target(o,1001,plan,r),null);
 assert.equal(g.target({...zoomed,ocr:zoomed.ocr.slice(1)},1001,plan,r),null);
});
test('Ley Line map navigation requires exact title, region and cost, without authorizing spending',()=>{
 const panel={...o,hud:{bigMap:false},ocr:[{text:'Ley Line Outcrop:',x:1492,y:6},{text:'Blossom of Revelation',x:1488,y:34},{text:'Windwail Highland, Mondstadt',x:1474,y:103},{text:'Treasure Collection Cost 20',x:1454,y:413},{text:'Navigate',x:1619,y:986,width:141,height:42},{text:'X',x:1844,y:0}]},plan={...p,action:'navigateBlossom'};
 assert.deepEqual(g.target(panel,1001,plan,r),{x:1690,y:1007});
 assert.deepEqual(g.target({...panel,ocr:panel.ocr.map(q=>({...q,text:' '+q.text}))},1001,plan,r),{x:1690,y:1007});
 assert.deepEqual(g.target(panel,1001,{...plan,action:'closeBlossomPanel'},r),{x:1876,y:34});
 for(let i=0;i<5;i++)assert.equal(g.target({...panel,ocr:panel.ocr.filter((_,n)=>n!==i)},1001,plan,r),null);
 assert.equal(g.target(panel,1001,{...plan,action:'spendResin'},r),null);
});
