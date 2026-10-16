const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const guard=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-journal-recovery.js');
const o={session:'s',frameId:1,timestamp:1000,map:null,hud:{journal:true,world:false,health:null,groundControls:false,bigMap:false,auto:false,dialogueReady:false,choice:false},ocr:[
 ['In Progress',135,26],['Not to be Missed',874,121],['Defeat the attacking monsters',890,254],['Quest Chain Rewards:',876,786],['World Quests',180,723],['Cancel',1624,989],['Navigation',1598,1018]
].map(([text,x,y])=>({text,x,y}))};
test('scrolled Cyrus journal supports close recovery, not a synthetic pause proof',()=>{
 assert.equal(guard.ready(o,1000,'s',true),true);
 for(let i=0;i<o.ocr.length;i++)assert.equal(guard.ready({...o,ocr:o.ocr.filter((_,n)=>n!==i)},1000,'s',true),false);
 assert.equal(guard.ready({...o,ocr:[...o.ocr,o.ocr[0]]},1000,'s',true),false);
 for(const [now,session,account] of [[2001,'s',true],[999,'s',true],[1000,'other',true],[1000,'s',false]])assert.equal(guard.ready(o,now,session,account),false);
 for(const hud of [{...o.hud,world:true},{...o.hud,health:{current:1,max:2}},{...o.hud,journal:false},{...o.hud,dialogueReady:true}])assert.equal(guard.ready({...o,hud},1000,'s',true),false);
});
test('fast acquisition pause allows inventory animation to settle before verification',()=>{
 const source=fs.readFileSync(__dirname+'/../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js','utf8');
 assert.match(source,/acquisitionPauseRequested=true;await sleep\(650\);/);
});
