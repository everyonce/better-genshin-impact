const test=require('node:test'),assert=require('node:assert/strict');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-team.js');
test('Upgrade result close requires the verified level and remaining balance',()=>{
 const row=(text,x,y)=>({text,x,y}),o={timestamp:1000,map:null,hud:{world:false},ocr:[row('Kaeya I Level Up',136,22),row('65706',1668,28),row('Lv.16',1418,139),row('2,184',1802,262)]},p={session:'s',frameId:3,createdAt:1000,reviewed:true,action:'closeLevelResult'},r={session:'s',expectedFrameId:3};
 assert.equal(gate.target(o,1000,p,r).key,'VK_ESCAPE');
 for(let i=0;i<o.ocr.length;i++)assert.equal(gate.target({...o,ocr:o.ocr.filter((_,n)=>n!==i)},1000,p,r),null);
});

test('level material preview and confirmation use distinct one-use exact cost gates',()=>{
 const row=(text,x,y)=>({text,x,y,width:100,height:30}),p={session:'s',frameId:3,reviewed:true,createdAt:1000,action:'previewLevelMaterials'},r={session:'s',expectedFrameId:3};
 const o={timestamp:1000,map:null,hud:{world:false},ocr:[row('Kaeya / Level Up',137,26),row('Lv. 10',1143,125),row('74506',1666,28),row('Select EXP materials',1376,675),row('Auto Add',1704,901)]};
 assert.deepEqual(gate.target(o,1000,p,r),{x:1760,y:917,action:p.action});
 assert.equal(gate.target(o,1000,{...p,action:'confirmLevelPreview'},r),null);
 const preview={...o,ocr:[row('Kaeya / Level·Up',137,28),row('74506',1668,30),row('Lv. 10 +6',1146,125),row('+44000 4215/5700',1642,144),row('2,184',1768,238),row('34',1408,721),row('2',1544,727),row('8800',1326,1005),row('Level Up',1663,998)]},confirm={...p,action:'confirmLevelPreview'};
 assert.equal(gate.target(preview,1000,confirm,r).action,'confirmLevelPreview');
 const split={...preview,ocr:preview.ocr.filter(q=>q.text!=='+44000 4215/5700').concat([row('+44000',1648,147),row('4215/5700',1748,145)])};
 assert.equal(gate.target(split,1000,confirm,r).action,'confirmLevelPreview');
 for(const label of ['+44000','4215/5700'])assert.equal(gate.target({...split,ocr:split.ocr.filter(q=>q.text!==label)},1000,confirm,r),null);
 for(let i=0;i<preview.ocr.length;i++)assert.equal(gate.target({...preview,ocr:preview.ocr.filter((_,n)=>i!==n)},1000,confirm,r),null);
 for(const patch of [{consumed:true},{session:'other'},{createdAt:-60000}])assert.equal(gate.target(preview,1000,{...confirm,...patch},r),null);
});
test('Fast equip requires the exact free stat preview and a recent Kaeya artifact witness',()=>{
 const row=(text,x,y)=>({text,x,y,width:100,height:30}),w={session:'s',frameId:2,timestamp:900,ocr:[row('Cryo / Kaeya',137,27),row('Fast Equip',1474,993)]};
 const o={timestamp:1000,map:null,hud:{world:false},ocr:[row('Fast Equip',138,30),row('Recommended Plan',52,121),row('Attribute Preview',496,518),row('No Set Bonus',514,457),row('1,700',1534,570),row('1,829',1776,569),row('102',1558,627),row('119',1810,629),row('Equip',1672,999)]},p={session:'s',frameId:3,witnessFrameId:2,reviewed:true,createdAt:1000,action:'equip'},r={session:'s',expectedFrameId:3};
 assert.equal(gate.target(o,1000,p,r,w).action,'equip');
 assert.equal(gate.target(o,1000,p,r),null);assert.equal(gate.target(o,1000,p,r,{...w,session:'other'}),null);
 assert.equal(gate.target({...o,ocr:o.ocr.map(q=>q.text==='119'?{...q,text:'120'}:q)},1000,p,r,w),null);
 assert.equal(gate.target(o,1000,{...p,consumed:true},r,w),null);
});
test('Closing a verified character menu hands off to pause protection',async()=>{
 const o={timestamp:1000,map:null,hud:{world:false},ocr:[{text:'Cryo /Kaeya',x:137,y:27},{text:'Attributes',x:148,y:131},{text:'Level Up',x:1607,y:989}]};assert.equal(gate.target(o,1000,{session:'s',frameId:5,reviewed:true,createdAt:1000,action:'close'},{session:'s',expectedFrameId:5}).key,'VK_ESCAPE');
 const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');let paused=0;
 const result=await mission.runQuestStep('actTwoTeamUi',{}, {actTwoTeamUi:async()=>'close',sleep:async()=>{},finishActTwoDialogue:async()=>{paused++;return {pauseVerified:true};}},async()=>({hud:{world:true}}));
 assert.equal(paused,1);assert.equal(result.pauseVerified,true);
});
test('Artifact menu permits its separate numeric new-item badge without broadening labels',()=>{
 const o={timestamp:1000,map:null,hud:{world:false},ocr:[{text:'Cryo / Kaeya',x:137,y:27},{text:' Artifacts 4',x:112,y:271,width:221,height:42}]},p={session:'s',frameId:5,reviewed:true,action:'artifacts',createdAt:1000},r={session:'s',expectedFrameId:5};
 assert.deepEqual(gate.target(o,1000,p,r),{x:223,y:292,action:'artifacts'});
 assert.equal(gate.target({...o,ocr:[o.ocr[0],{...o.ocr[1],text:'Artifacts Unavailable'}]},1000,p,r),null);
});
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
