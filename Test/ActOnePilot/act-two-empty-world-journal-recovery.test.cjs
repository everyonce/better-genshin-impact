const test=require('node:test'),assert=require('node:assert/strict');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-journal-recovery.js');
test('empty World Quests tab can close only on its exact fresh screen',()=>{
 const rows=[['World Quests',144,29],['No active quests',710,449],['Check another tab',821,550],['Q',670,30],['E',1208,30],['UID: 693306810',1672,1043]].map(([text,x,y])=>({text,x,y,width:170,height:35}));
 const o={session:'s',frameId:460,timestamp:1000,map:null,hud:{journal:false,world:false,health:null,groundControls:false,bigMap:false,auto:false,dialogueReady:false,choice:false},ocr:rows};
 assert.equal(gate.ready(o,1000,'s',true),true);
 for(const i of [0,1,2,3,4])assert.equal(gate.ready({...o,ocr:rows.filter((_,j)=>j!==i)},1000,'s',true),false);
 assert.equal(gate.ready(o,2001,'s',true),false);
 assert.equal(gate.ready(o,1000,'s',false),false);
});
