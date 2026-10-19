const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-team.js');
test('exact Kaeya artifact screen permits only one reviewed empty Sands inspection',()=>{
 const rows=[['Cryo / Kaeya',138,26],['Artifacts 2',136,272],['Fast Equip',1471,988],['Switch',1674,993],['Adventurer',1462,389],['UID: 693306810',1677,1046]].map(([text,x,y])=>({text,x,y}));
 const o={session:'s',timestamp:100000,map:null,hud:{world:false,dialogueReady:false},ocr:rows},p={action:'inspectEmptySands',session:'s',frameId:388,reviewed:true,createdAt:100100},r={session:'s',expectedFrameId:388};
 assert.deepEqual(g.target(o,100100,p,r,null),{action:'inspectEmptySands',x:1460,y:610});
 for(const text of ['Cryo / Kaeya','Artifacts 2','Fast Equip','Switch','Adventurer','UID: 693306810'])assert.equal(g.target({...o,ocr:rows.filter(q=>q.text!==text)},100100,p,r,null),null,text);
 assert.equal(g.target(o,100100,{...p,consumed:true},r,null),null);
 assert.equal(g.target(o,100100,p,{session:'else',expectedFrameId:388},null),null);
});
test('flower selection permits one reviewed Sands tab inspection',()=>{
 const rows=[["Adventurer's Flower",1460,117],['Flower of Life',1460,173],['Set Filter',230,993],['Equipped: Kaeya',1524,925],['UID: 693306810',1677,1046]].map(([text,x,y])=>({text,x,y}));
 const o={session:'s',timestamp:100000,map:null,hud:{world:false,dialogueReady:false},ocr:rows},p={action:'inspectSandsTab',session:'s',frameId:395,reviewed:true,createdAt:100100},r={session:'s',expectedFrameId:395};
 assert.deepEqual(g.target(o,100100,p,r,null),{action:'inspectSandsTab',x:310,y:47});
 for(const text of ["Adventurer's Flower",'Flower of Life','Set Filter','Equipped: Kaeya','UID: 693306810'])assert.equal(g.target({...o,ocr:rows.filter(q=>q.text!==text)},100100,p,r,null),null,text);
});
test('artifact recommendation tutorial can be dismissed only from its exact overlay',()=>{
 const rows=[["Berserker's Timepiece",1457,115],['When you view an artifact in the Character Menu, the Main Affix and Minor',415,782],['This function can be toggled on and off in your Settings.',553,850],['UID: 693306810',1680,1046]].map(([text,x,y])=>({text,x,y}));
 const o={session:'s',timestamp:100000,map:null,hud:{world:false,dialogueReady:false},ocr:rows},p={action:'dismissArtifactTip',session:'s',frameId:398,reviewed:true,createdAt:100100},r={session:'s',expectedFrameId:398};
 assert.deepEqual(g.target(o,100100,p,r,null),{action:'dismissArtifactTip',x:960,y:750});
 for(const text of rows.map(q=>q.text))assert.equal(g.target({...o,ocr:rows.filter(q=>q.text!==text)},100100,p,r,null),null,text);
});
test('Sands inventory allows inspecting one unequipped item before any equip',()=>{
 const rows=[["Berserker's Timepiece",1457,115],['Sands of Eon',1460,173],['Equipped: Lumina',1523,925],['Equip',1518,991],['Set Filter',230,993],['UID: 693306810',1678,1048]].map(([text,x,y])=>({text,x,y}));
 const o={session:'s',timestamp:100000,map:null,hud:{world:false,dialogueReady:false},ocr:rows},p={action:'inspectUnusedSands',session:'s',frameId:401,reviewed:true,createdAt:100100},r={session:'s',expectedFrameId:401};
 assert.deepEqual(g.target(o,100100,p,r,null),{action:'inspectUnusedSands',x:240,y:195});
 assert.deepEqual(g.target({...o,ocr:rows.map(q=>q.text==='UID: 693306810'?{...q,text:'UID:693306810'}:q)},100100,p,r,null),{action:'inspectUnusedSands',x:240,y:195});
 assert.deepEqual(g.target({...o,ocr:rows.map(q=>q.text==='Sands of Eon'?{...q,text:'Sandsof Eon'}:q)},100100,p,r,null),{action:'inspectUnusedSands',x:240,y:195});
 assert.deepEqual(g.target({...o,ocr:rows.map(q=>q.text==="Berserker's Timepiece"?{...q,text:"*Berserker's Timepiece"}:q)},100100,p,r,null),{action:'inspectUnusedSands',x:240,y:195});
 for(const text of rows.map(q=>q.text).filter(t=>t!=="Berserker's Timepiece"))assert.equal(g.target({...o,ocr:rows.filter(q=>q.text!==text)},100100,p,r,null),null,text);
});
test('only the reviewed unoccupied Lucky Dog Sands can be equipped once',()=>{
 const rows=[["Lucky Dog's Hourglass",1457,115],['Sands of Eon',1460,173],['5.2%',1776,210],['Equip',1518,991],['Set Filter',230,993],['UID: 693306810',1675,1046]].map(([text,x,y])=>({text,x,y}));
 const o={session:'s',timestamp:100000,map:null,hud:{world:false,dialogueReady:false},ocr:rows},p={action:'equipUnusedSands',session:'s',frameId:407,reviewed:true,createdAt:100100},r={session:'s',expectedFrameId:407};
 assert.deepEqual(g.target(o,100100,p,r,null),{action:'equipUnusedSands',x:1555,y:1010});
 for(const text of rows.map(q=>q.text))assert.equal(g.target({...o,ocr:rows.filter(q=>q.text!==text)},100100,p,r,null),null,text);
 assert.equal(g.target({...o,ocr:rows.concat({text:'Equipped: Lumina',x:1520,y:925})},100100,p,r,null),null);
});
test('verified Kaeya-equipped Sands allows one back key without removing it',()=>{
 const rows=[["Lucky Dog's Hourglass",1451,117],['Sands of Eon',1460,177],['Equipped: Kaeya',1524,925],['Remove',1506,993],['UID:693306810',1680,1048]].map(([text,x,y])=>({text,x,y}));
 const o={session:'s',timestamp:100000,map:null,hud:{world:false,dialogueReady:false},ocr:rows},p={action:'backFromEquippedSands',session:'s',frameId:410,reviewed:true,createdAt:100100},r={session:'s',expectedFrameId:410};
 assert.deepEqual(g.target(o,100100,p,r,null),{action:'backFromEquippedSands',key:'VK_ESCAPE'});
 assert.deepEqual(g.target({...o,ocr:rows.map(q=>q.text==='Sands of Eon'?{...q,text:'Sands Qf Eon'}:q)},100100,p,r,null),{action:'backFromEquippedSands',key:'VK_ESCAPE'});
 for(const text of rows.map(q=>q.text))assert.equal(g.target({...o,ocr:rows.filter(q=>q.text!==text)},100100,p,r,null),null,text);
});
