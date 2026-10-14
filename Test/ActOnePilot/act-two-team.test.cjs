const test=require('node:test'),assert=require('node:assert/strict');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-team.js');
test('Kaeya upgrade requires exact selected material quantity, cost and live stock',()=>{
 const p={frameId:5,amount:3,requiredMora:3000,lowTierStock:26,midTierStock:3,highTierStock:0,mora:68395};
 const o={session:'s',frameId:5,timestamp:1000,map:null,hud:{world:false,kaeyaLevel:p},ocr:[{text:'Kaeya / Level Up.',x:135,y:26}]};
 assert.equal(gate.upgradeReady(o,1000,'s',3),true);
 for(const patch of [{amount:2},{requiredMora:600},{mora:68394},{lowTierStock:25},{midTierStock:4},{highTierStock:1},{frameId:4}])
  assert.equal(gate.upgradeReady({...o,hud:{...o.hud,kaeyaLevel:{...p,...patch}}},1000,'s',3),false);
 assert.equal(gate.upgradeReady(o,2001,'s',3),false);assert.equal(gate.upgradeReady(o,1000,'other',3),false);
});
test('read-only team menu requires unique current character and consumed-plan prevention',()=>{
 const o={timestamp:1000,map:null,hud:{world:false},ocr:[{text:'Cryo / Kaéya',x:137,y:27},{text:'Level Up',x:1607,y:989,width:119,height:37}]};
 const p={session:'s',frameId:90,reviewed:true,action:'level',createdAt:1000},r={session:'s',expectedFrameId:90};
 assert.deepEqual(gate.target(o,1000,p,r),{action:'level',x:1667,y:1008});
 for(const patch of [{consumed:true},{createdAt:undefined},{frameId:89},{action:'spend'}])assert.equal(gate.target(o,1000,{...p,...patch},r),null);
});
