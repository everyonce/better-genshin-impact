const test=require('node:test'),assert=require('node:assert/strict'),gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-map.js');
test('Handbook mage pin can only close without committing a marker',()=>{
 const o={timestamp:1000,hud:{},ocr:[['Hunt down a Cryo Abyss',1490,0],['Mage',1490,30],['Total Pins 0/350',1440,910],['Confirm',1620,980],['X',1850,10]].map(([text,x,y])=>({text,x,y}))},p={reviewed:true,session:'s',frameId:1,createdAt:1000,action:'closeUnconfirmedPin'},r={session:'s',expectedFrameId:1};
 assert.deepEqual(gate.target(o,1000,p,r),{x:1876,y:34});
 for(const row of o.ocr)assert.equal(gate.target({...o,ocr:o.ocr.filter(q=>q!==row)},1000,p,r),null);
 assert.equal(gate.target(o,1000,{...p,action:'teleport'},r),null);
 assert.equal(gate.target(o,2001,p,r),null);
});
