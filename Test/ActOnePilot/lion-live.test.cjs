'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const guard=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/lion-live-guard.js');
const title='Deep Within the Temple of the Lion';
const entry={session:'lion-adapter-test',timestamp:9000,status:'completed',mission:'questStep',details:{result:{step:'lionPartyStart',label:title},inputEvents:[{type:'lionPartyStart',label:title,startedAt:8900}]}};
const source=fs.readFileSync(__dirname+'/lion-field-combat-adapter.test.cjs','utf8'),sandbox={require,module:{exports:{}},__dirname,setImmediate};
vm.runInNewContext(source.slice(0,source.indexOf('\nfunction assertPauseProof'))+'\nmodule.exports={fixture,fieldRows,row};',sandbox);
const {fixture,fieldRows,row}=sandbox.module.exports;
test('Lisa skill overlay dismissal recognizes only fresh exact trial tutorial',()=>{
 const ctx={};vm.runInNewContext(fs.readFileSync(__dirname+'/../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js','utf8'),ctx);
 const o={session:'s',timestamp:1000,map:null,hud:{world:false,health:{current:1148,max:1196}},ocr:[row("Lisa's Elemental Skill can be unleashed by pressing, or charged by holding.",419,780),row('Lisa',1694,540),row('Trial',1798,509)]};
 assert.equal(ctx.actOneLisaSkillInfo(o,1000,'s'),true);
 const second={...o,ocr:[row('When the skill is fully charged, releasing it unleashes an area attack, dealing',405,780),row('massive Electro DMG.',793,816),...o.ocr.slice(1)]};
 assert.equal(ctx.actOneLisaSkillInfo(second,1000,'s'),true);
 assert.equal(ctx.actOneLisaSkillInfo({...second,ocr:second.ocr.filter(r=>r.text!=='massive Electro DMG.')},1000,'s'),false);
 for(const now of [999,2001])assert.equal(ctx.actOneLisaSkillInfo(o,now,'s'),false);
 assert.equal(ctx.actOneLisaSkillInfo(o,1000,'other'),false);
 for(const patch of [{world:true},{journal:true},{dialogueReady:true},{health:{current:0,max:1196}},{health:{current:1148,max:1459}}])assert.equal(ctx.actOneLisaSkillInfo({...o,hud:{...o.hud,...patch}},1000,'s'),false);
 for(const rs of [o.ocr.slice(1),o.ocr.slice(0,2),[...o.ocr,o.ocr[0]],o.ocr.map(r=>({...r,y:r.y+100}))])assert.equal(ctx.actOneLisaSkillInfo({...o,ocr:rs},1000,'s'),false);
});
test('missing Lion F keycap uses same-frame crop only for exact healthy trial interaction',()=>{
 const ctx={};vm.runInNewContext(fs.readFileSync(__dirname+'/../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js','utf8'),ctx);
 const rs=[row('Open Door',1218,522,163,35),row('Lisa',1694,540),row('Trial',1798,509)];
 const s={world:false,groundControls:true,health:{current:1196,max:1196}};
 assert.equal(ctx.actOneShouldReadLionInteractionCrop(rs,s),true);
 for(const bad of [rs.slice(0,2),rs.concat(rs[0]),rs.concat(row('F',1096,520)),[row('Cooking',1218,522),...rs.slice(1)]])assert.equal(ctx.actOneShouldReadLionInteractionCrop(bad,s),false);
 for(const patch of [{world:true},{groundControls:false},{dialogueReady:true},{auto:true},{journal:true},{bigMap:true},{climbing:true},{health:{current:100,max:1196}}])assert.equal(ctx.actOneShouldReadLionInteractionCrop(rs,{...s,...patch}),false);
 assert.equal(ctx.actOneInteractionCropF([],1080,490),null);
});
const rows=()=>fieldRows({objectiveText:'',healthText:'1288/1288',extra:[row('Lumina',1656,312,93,21)]}).filter(r=>r.text!=='Meet Lisa at the temple');
function setup(patch={}){
 const session='lion-adapter-test',w={session,frameId:2,timestamp:9900,map:null,hud:{world:false,groundControls:true,climbing:false,health:{current:1288,max:1288}},ocr:rows()};
 return fixture({step:'lionVisualMove',initialFrame:5,expectedFrameId:5,noEnemy:true,throwGps:true,fieldRowsSequence:[rows()],seedFiles:{
  ['reports/'+session+'.json']:[entry],
  ['observations/'+session+'/frame-0002.json']:w,['observations/'+session+'/frame-0002.png']:'field',
  'lion-visual-move.json':{session,frameId:5,witnessFrameId:2,reviewed:true,createdAt:9950,relativeDx:0,holds:2,...patch}}});
}
test('Lion movement requires fresh owned domain HUD and a unique current entry',()=>{
 const o={session:'lion-adapter-test',timestamp:10000,frameId:3,map:null,hud:{world:false,groundControls:true,climbing:false,health:{current:1288,max:1288}},ocr:rows()};
 assert.ok(guard.entry([entry],o.session,o));assert.ok(guard.field(o,10000,o.session));
 assert.equal(guard.entry([entry,entry],o.session,o),false);
 assert.equal(guard.entry([{...entry,session:'other'}],o.session,o),false);
 assert.equal(guard.entry([entry,{session:o.session,details:{inputEvents:[{type:'teleportRecovery',startedAt:9500}]}}],o.session,o),false);
 for(const patch of [{map:{map:'Teyvat'}},{timestamp:8999},{hud:{...o.hud,climbing:true}},{hud:{...o.hud,health:{current:100,max:1288}}}])assert.equal(guard.field({...o,...patch},10000,o.session),false);
});
test('reviewed session handoff requires the exact stopped predecessor and rejects later source activity',()=>{
 const old={...entry,id:'entry'},stop={id:'stop',session:entry.session,status:'failed',timestamp:9500,details:{reason:'Pause protection exhausted: pause is UNVERIFIED; operator intervention required'}};
 const o={session:'new-session',timestamp:10000},handoff={session:o.session,sourceSession:entry.session,entryId:'entry',sourceStopId:'stop',createdAt:9700,reviewed:true};
 assert.ok(guard.entry([old,stop],o.session,o,handoff));
 for(const patch of [{reviewed:false},{sourceStopId:'wrong'},{entryId:'wrong'},{createdAt:10001}])assert.equal(guard.entry([old,stop],o.session,o,{...handoff,...patch}),false);
 assert.equal(guard.entry([old,stop,{session:entry.session,timestamp:9800}],o.session,o,handoff),false);
 const previous={id:'previous-stop',session:'intermediate',status:'failed',timestamp:9600,details:{reason:stop.details.reason}},chain={...handoff,predecessorSession:'intermediate',predecessorStopId:'previous-stop'};
 assert.ok(guard.entry([old,stop,previous],o.session,o,chain));
 assert.equal(guard.entry([old,stop],o.session,o,chain),false);
 assert.equal(guard.entry([old,stop,previous,{session:'intermediate',timestamp:9650}],o.session,o,chain),false);
 assert.equal(guard.entry([old,stop,previous,{session:'intermediate',timestamp:9501,details:{inputEvents:[{type:'LeaveDomain',startedAt:9500}]}}],o.session,o,chain),false);
});
test('captured trial party requires active identity, three named rows and the trial marker',()=>{
 const o={session:'s',timestamp:1000,frameId:1,map:null,hud:{world:false,groundControls:true,climbing:false,health:{current:1196,max:1196}},
  ocr:[row('Lumina',1682,257),row('Amber',1690,347),row('Kaeya',1694,437),row('Lisa',1690,540),row('Trial',1800,509),row('4',1856,540)]};
 assert.ok(guard.field(o,1000,'s'));
 for(const label of ['Lisa','Trial'])assert.equal(guard.field({...o,ocr:o.ocr.filter(r=>r.text!==label)},1000,'s'),false);
 assert.ok(guard.field({...o,ocr:o.ocr.filter(r=>r.text!=='Amber')},1000,'s'));
 assert.equal(guard.field({...o,ocr:o.ocr.filter(r=>!['Amber','Kaeya'].includes(r.text))},1000,'s'),false);
 for(const max of [1379,1459,1186,1288,1363])assert.ok(guard.field({...o,hud:{...o.hud,health:{current:max,max}}},1000,'s'));
 assert.equal(guard.field({...o,hud:{...o.hud,health:{current:9999,max:9999}}},1000,'s'),false);
 const injured={...o,hud:{...o.hud,health:{current:640,max:1196}}};
 assert.equal(guard.field(injured,1000,'s'),false);assert.ok(guard.living(injured,1000,'s'));
 assert.ok(guard.combat(injured,1000,'s'));
 assert.equal(guard.combat({...injured,hud:{...injured.hud,health:{current:350,max:1196}}},1000,'s'),false);
 assert.equal(guard.living({...injured,hud:{...injured.hud,health:{current:0,max:1196}}},1000,'s'),false);
 // Bright world effects obscure the redundant keycap digits. The four unique
 // names in their exact rows, Trial and observed active HP identify the layout.
 const alternate=o.ocr.filter(r=>r.text!=='4').concat([row('1',1856,262),row('2',1852,349),row('3',1854,445)]);
 assert.ok(guard.field({...o,ocr:alternate},1000,'s'));
 assert.ok(guard.field({...o,ocr:alternate.filter(r=>!['1','2','3'].includes(r.text))},1000,'s'));
 for(const label of ['Lisa','Trial'])assert.equal(guard.field({...o,ocr:alternate.filter(r=>r.text!==label)},1000,'s'),false);
});
test('Lion adapter bounds movement, releases keys and verifies pause',async()=>{
 const f=setup(),initial=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(initial,f.observe);
 assert.equal(r.moves,2,JSON.stringify(r));assert.equal(r.pauseVerified,true);assert.equal(f.getOverlappingKeyDowns().length,0);
});
test('probe reacquires a transition witness without gameplay input and rejects holds',async()=>{
 for(const holds of [0,1]){
  const f=setup({action:'probe',holds}),files=f.getVirtualFiles(),key='observations/lion-adapter-test/frame-0002.json',w=JSON.parse(files.get(key));
  w.hud.groundControls=false;files.set(key,JSON.stringify(w));
  const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
  assert.equal(r.moves,0);assert.ok(!f.inputs.some(x=>x.kind==='down'&&['VK_W','VK_E','VK_Q','VK_LBUTTON'].includes(x.key)));
  if(!holds)assert.equal(r.pauseVerified,true);else assert.equal(f.inputs.length,0);
 }
});
test('reviewed side-step stays bounded and rejects unsupported keys',async()=>{
 for(const key of ['VK_A','VK_SPACE']){
  const f=setup({moveKey:key}),o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
  assert.equal(r.moves,key==='VK_A'?2:0);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key===key).length,key==='VK_A'?2:0);
  assert.equal(f.getOverlappingKeyDowns().length,0);
 }
});
test('short approach steps accept only bounded walking durations and at most two holds',async()=>{
 for(const patch of [{moveMs:200,holds:1},{moveMs:400,holds:2},{moveMs:200,holds:2,action:'carefulWalk'},{moveMs:400,holds:2,action:'carefulWalk'},{moveMs:400,holds:3,action:'carefulWalk'},{moveMs:0,holds:1},{moveMs:801,holds:1},{moveMs:200,holds:3},{moveMs:200,holds:0,action:'jumpForward'}]){
  const f=setup(patch),o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
  const accepted=patch.moveMs>0&&patch.moveMs<=400&&patch.holds<=2&&(!patch.action||patch.action==='carefulWalk');
  assert.equal(r.moves,accepted?patch.holds:0);
  if(!accepted){assert.equal(f.inputs.length,0);continue;}
  const down=f.inputs.find(x=>x.kind==='down'&&x.key==='VK_W'),up=f.inputs.find(x=>x.kind==='up'&&x.key==='VK_W');
  assert.equal(up.at-down.at,patch.moveMs);assert.equal(r.pauseVerified,true);
 }
});
test('injured reviewed travel is restricted to at most two forward holds and bounded turns',async()=>{
 for(const patch of [{holds:2},{holds:3},{holds:1,relativeDx:751},{holds:1,moveKey:'VK_A'}]){
  const f=setup({action:'carefulWalk',...patch}),o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
  assert.equal(r.moves,patch.holds===2?2:0);
  if(patch.holds!==2)assert.equal(f.inputs.length,0);
 }
});
test('reviewed Kaeya selection sends one slot key and pauses without combat or movement',async()=>{
 const f=setup({action:'selectKaeya',holds:0});
 const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
 assert.equal(r.characterSelectionAttempted,'Kaeya',JSON.stringify(r));
 assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,1);
 assert.ok(!f.inputs.some(x=>x.kind==='down'&&['VK_W','VK_E','VK_LBUTTON'].includes(x.key)));
 assert.equal(r.pauseVerified,true);assert.equal(f.getOverlappingKeyDowns().length,0);
});
test('defensive Traveler selection uses slot one and never attacks',async()=>{
 const f=setup({action:'selectTraveler',holds:0}),o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
 assert.equal(r.characterSelectionAttempted,'Traveler',JSON.stringify(r));
 assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_1').length,1);
 assert.ok(!f.inputs.some(x=>x.kind==='down'&&['VK_3','VK_W','VK_E','VK_LBUTTON'].includes(x.key)));
 assert.equal(r.pauseVerified,true);
});
test('defensive selection resumes an exact journal pause with an injured living witness',async()=>{
 const f=setup({action:'selectKaeya',holds:0});f.setScreen('journal');
 const files=f.getVirtualFiles(),key='observations/lion-adapter-test/frame-0002.json',w=JSON.parse(files.get(key));
 w.hud.health.current=348;files.set(key,JSON.stringify(w));
 const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
 assert.equal(r.characterSelectionAttempted,'Kaeya',JSON.stringify(r));assert.equal(r.pauseVerified,true);
 assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_3').length,1);
});
test('Lion adapter rejects unreviewed and excessive movement without input',async()=>{
 for(const patch of [{reviewed:false},{holds:9},{relativeDx:751},{usedAt:9900}]){
  const f=setup(patch),o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
  assert.equal(r.moves,0);assert.equal(f.inputs.length,0);
 }
});
test('reviewed platform jump overlaps only its bounded forward and jump keys with release',async()=>{
 const f=setup({action:'jumpForward',holds:0}),o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
 assert.equal(r.moves,1);assert.equal(r.pauseVerified,true);
 assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_SPACE').length,1);
 assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_W').length,1);
 assert.equal(f.getOverlappingKeyDowns().length,1);
 const overlap=f.getOverlappingKeyDowns()[0];assert.equal(overlap.held,'VK_W');assert.equal(overlap.next,'VK_SPACE');
 for(const [key,duration] of [['VK_W',800],['VK_SPACE',60]]){
  const down=f.inputs.find(x=>x.kind==='down'&&x.key===key),up=f.inputs.find(x=>x.kind==='up'&&x.key===key);
  assert.equal(up.at-down.at,duration);
 }
});
test('platform jump cancellation releases both chord keys before verified pause',async()=>{
 const f=setup({action:'jumpForward',holds:0}),keyDown=f.context.keyDown;
 f.context.keyDown=key=>{keyDown(key);if(key==='VK_SPACE')f.getVirtualFiles().set('stop.json',JSON.stringify({session:'lion-adapter-test',createdAt:9000}));};
 const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
 assert.equal(r.moves,0);assert.equal(r.pauseVerified,true);
 for(const key of ['VK_W','VK_SPACE']){
  const down=f.inputs.find(x=>x.kind==='down'&&x.key===key),up=f.inputs.find(x=>x.kind==='up'&&x.key===key);
  assert.ok(down&&up);assert.ok(up.at-down.at<=50);
 }
});
test('Kaeya fight requires his observed max HP and reviewed visible combat',async()=>{
 const party=[row('Lumina',1682,257),row('Amber',1690,347),row('Kaeya',1694,437),row('Lisa',1690,540),row('Trial',1800,509),row('4',1856,540),row('Q',1802,1026),row('1379/1379',910,1003,100,20)];
 for(const enemy of [true,false]){
  const ground=party.concat(enemy?[row('Lv. 7',570,435)]:[]),f=setup({action:'kaeyaCombat',holds:0,combatReviewed:enemy});
  f.setFlag('fieldRowsSequence',[ground]);
  const files=f.getVirtualFiles(),key='observations/lion-adapter-test/frame-0002.json',w=JSON.parse(files.get(key));w.hud.health={current:1379,max:1379};w.ocr=ground;files.set(key,JSON.stringify(w));
  const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_Q').length,enemy?1:0,JSON.stringify(r));
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_LBUTTON').length,enemy?12:0,JSON.stringify(r));
  if(enemy)assert.equal(r.pauseVerified,true);assert.equal(f.getOverlappingKeyDowns().length,0);
 }
});
test('Lion movement cancels before walking and verifies pause',async()=>{
 const f=setup();f.setFlag('stopAfterClose',true);
 const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
 assert.equal(r.moves,0);assert.equal(r.pauseVerified,true);assert.equal(f.getOverlappingKeyDowns().length,0);
 assert.ok(!f.inputs.some(x=>x.kind==='down'&&x.key==='VK_W'));
});
test('reviewed domain native fallback always returns to verified pause',async()=>{
 const f=setup({action:'nativeCombat',holds:0,combatReviewed:true}),o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
 assert.equal(r.nativeFightAttempted,true,JSON.stringify(r));assert.equal(r.pauseVerified,true);
 assert.equal(f.nativeCalls.find(x=>x&&x.kind==='fight').name,'English Lion Trial');
 assert.equal(f.getOverlappingKeyDowns().length,0);
});
test('automatic Lisa dialogue settles after a blank transition without entering a pause loop',async()=>{
 const f=setup();f.setFlag('fieldRowsSequence',[rows(),[],[row('Auto',102,32),row('Lisa',926,854),row('I guess I could give this a go.',744,907,443,43)]]);
 const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
 assert.equal(r.moves,1,JSON.stringify(r));assert.equal(r.dialoguePending,true);assert.equal(r.pauseVerified,false);
 assert.equal(f.getOverlappingKeyDowns().length,0);assert.ok(!f.inputs.some(x=>x.kind==='down'&&x.key==='VK_B'));
});
test('recorded wind tutorial permits exactly two spaced Space presses and never walks',async()=>{
 const party=[row('Lumina',1682,257),row('Amber',1690,347),row('Kaeya',1694,437),row('Lisa',1690,540),row('Trial',1800,509),row('4',1856,540),row('1196/1196',910,1003,100,20)];
 const ground=[...party,row('Q',1802,1026)],air=[...party,row('Space',1730,1026)];
 const f=setup({action:'windLaunch',holds:0,windTutorialFrameId:3});f.setFlag('fieldRowsSequence',[ground,air]);
 const files=f.getVirtualFiles(),key='observations/lion-adapter-test/frame-0002.json',w=JSON.parse(files.get(key));w.hud.health={current:1196,max:1196};w.ocr=ground;files.set(key,JSON.stringify(w));
 files.set('observations/lion-adapter-test/frame-0003.json',JSON.stringify({...w,frameId:3,ocr:[...ground,row('Tap Space twice in a wind current to',780,186),row('ride it up',946,216)]}));
 files.set('observations/lion-adapter-test/frame-0003.png','tutorial');
 const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
 assert.equal(r.gliderAttempted,true,JSON.stringify(r));assert.equal(r.airborneVerified,true);assert.equal(r.pauseVerified,true);
 assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_SPACE').length,2);assert.ok(!f.inputs.some(x=>x.kind==='down'&&x.key==='VK_W'));
 assert.equal(f.getOverlappingKeyDowns().length,0);
});

test('Lion glide stops forward input when the visible landing restores ground controls',async()=>{
 const party=[row('Lumina',1682,257),row('Amber',1690,347),row('Kaeya',1694,437),row('Lisa',1690,540),row('Trial',1800,509),row('4',1856,540),row('1196/1196',910,1003,100,20)];
 const ground=[...party,row('Q',1802,1026)],air=[...party,row('Space',1730,1026)];
 const f=setup({action:'glideForward',holds:4});f.setFlag('fieldRowsSequence',[air,ground]);
 const files=f.getVirtualFiles(),key='observations/lion-adapter-test/frame-0002.json',w=JSON.parse(files.get(key));
 w.hud.health={current:1196,max:1196};w.hud.groundControls=false;w.ocr=air;files.set(key,JSON.stringify(w));
 const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
 assert.equal(r.moves,1,JSON.stringify(r));assert.equal(r.landingVerified,true);assert.equal(r.pauseVerified,true);
 assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_W').length,1);assert.equal(f.getOverlappingKeyDowns().length,0);
});
test('later reviewed wind launch reuses a verified same-session receipt for healthy Traveler',async()=>{
 const party=[row('Lumina',1682,257),row('Amber',1690,347),row('Kaeya',1694,437),row('Lisa',1690,540),row('Trial',1800,509),row('4',1856,540),row('1288/1288',910,1003,100,20)];
 for(const priorSession of ['lion-adapter-test','other']){
  const ground=[...party,row('Q',1802,1026)],air=[...party,row('Space',1730,1026)],f=setup({action:'windLaunch',holds:0,windTutorialFrameId:0});
  f.setFlag('fieldRowsSequence',[ground,air]);
  const files=f.getVirtualFiles();files.set('reports/lion-adapter-test.json',JSON.stringify([entry,{session:priorSession,status:'completed',timestamp:9800,details:{result:{step:'lionVisualMove',airborneVerified:true,gliderAttempted:true},inputEvents:[{type:'key',key:'VK_SPACE',durationMs:60},{type:'key',key:'VK_SPACE',durationMs:60}]}}]));
  const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_SPACE').length,priorSession==='lion-adapter-test'?2:0,JSON.stringify(r));
  if(priorSession==='lion-adapter-test'){assert.equal(r.airborneVerified,true);assert.equal(r.pauseVerified,true);}
  assert.equal(f.getOverlappingKeyDowns().length,0);
 }
});

test('Lion door and chest inputs require fresh matching F labels and reject leaving',async()=>{
 for(const [action,label,expected] of [['openDoor','Open Door',1],['openDoor','Leave Domain',0],['openChest','Common Chest',1],['openChest','Leave Domain',0]]){
  const f=setup({action,holds:0});f.setFlag('fieldRowsSequence',[[...rows(),row('F',1100,522),row(label,1218,524)]]);
  const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_F').length,expected,JSON.stringify(r));
  assert.equal(r.pauseVerified,true);assert.equal(f.getOverlappingKeyDowns().length,0);
 }
});
test('loot pickup matches a known item to the selected F row and never repeats an unchanged label',async()=>{
 for(const label of ['Fowl','Leave Domain']){
  const f=setup({action:'collectLoot',holds:0});f.setFlag('fieldRowsSequence',[[...rows(),row('F',1100,449),row(label,1213,449)]]);
  const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_F').length,label==='Fowl'?1:0,JSON.stringify(r));
  assert.equal(r.pauseVerified,true);assert.equal(f.getOverlappingKeyDowns().length,0);
 }
});

test('reviewed Lisa Electro attack stops on health loss and releases held skill',async()=>{
 const party=[row('Lumina',1682,257),row('Amber',1690,347),row('Kaeya',1694,437),row('Lisa',1690,540),row('Trial',1800,509),row('4',1856,540),row('Q',1802,1026)];
 const ground=[...party,row('1196/1196',910,1003,100,20)],hurt=[...party,row('900/1196',910,1003,100,20)];
 for(const reviewed of [true,false]){
  const f=setup({action:'electroAttack',combatReviewed:reviewed,holds:0});f.setFlag('fieldRowsSequence',[ground,hurt]);
  const files=f.getVirtualFiles(),key='observations/lion-adapter-test/frame-0002.json',w=JSON.parse(files.get(key));w.hud.health={current:1196,max:1196};w.ocr=ground;files.set(key,JSON.stringify(w));
  const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_E').length,reviewed?1:0,JSON.stringify(r));
  assert.ok(!f.inputs.some(x=>x.kind==='down'&&x.key==='VK_LBUTTON'));assert.equal(f.getOverlappingKeyDowns().length,0);
  if(reviewed)assert.equal(r.pauseVerified,true);
 }
});

test('timed trial waits for cooldown, bounds three attack bursts and releases every key',async()=>{
 const party=[row('Lumina',1682,257),row('Amber',1690,347),row('Kaeya',1694,437),row('Lisa',1690,540),row('Trial',1800,509),row('4',1856,540),row('Q',1802,1026)];
 const ground=[...party,row('1196/1196',910,1003,100,20)];
 const f=setup({action:'electroTrial',combatReviewed:true,holds:0});f.setFlag('fieldRowsSequence',[[...ground,row('2.2',1680,980)],ground]);
 const files=f.getVirtualFiles(),key='observations/lion-adapter-test/frame-0002.json',w=JSON.parse(files.get(key));w.hud.health={current:1196,max:1196};w.ocr=ground;files.set(key,JSON.stringify(w));
 const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
 assert.equal(r.attacks,12,JSON.stringify(r));assert.equal(r.pauseVerified,true);
 assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_E').length,2);
 assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_LBUTTON').length,12);assert.equal(f.getOverlappingKeyDowns().length,0);
});

test('normal trial bursts require a fresh active count and positive timer',async()=>{
 const party=[row('Lumina',1682,257),row('Amber',1690,347),row('Kaeya',1694,437),row('Lisa',1690,540),row('Trial',1800,509),row('4',1856,540),row('Q',1802,1026),row('1196/1196',910,1003,100,20)];
 for(const time of ['Time Remaining: 11s','Time Remaining: 0s']){
  const ground=[...party,row('Opponents Defeated: 2/4',80,250),row(time,77,282)];
  const f=setup({action:'normalBurst',combatReviewed:true,holds:0});f.setFlag('fieldRowsSequence',[ground]);
  const files=f.getVirtualFiles(),key='observations/lion-adapter-test/frame-0002.json',w=JSON.parse(files.get(key));w.hud.health={current:1196,max:1196};w.ocr=ground;files.set(key,JSON.stringify(w));
  const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
  assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_LBUTTON').length,time.endsWith('11s')?12:0,JSON.stringify(r));
  assert.ok(!f.inputs.some(x=>x.kind==='down'&&x.key==='VK_E'));assert.equal(r.pauseVerified,true);assert.equal(f.getOverlappingKeyDowns().length,0);
 }
});
test('local platform boarding requires two fresh dock samples and otherwise sends no movement',async()=>{
 for(const mode of ['docked','void','one-only','cancel']){
  const f=setup({action:'boardPlatform',holds:0});let samples=0,disposed=0;
  const capture=f.context.captureGameRegion;
  f.context.captureGameRegion=()=>{
   const img=capture();const crop=img.deriveCrop;
   img.deriveCrop=(x,y,w,h)=>{
    if(y!==770||w!==80||h!==30)return crop(x,y,w,h);
    if(x===740)samples++;
    const good=mode==='docked'||mode==='one-only'&&samples===1;
    if(mode==='cancel')f.getVirtualFiles().set('stop.json',JSON.stringify({session:'lion-adapter-test',createdAt:9000}));
    return {srcMat:{cvtColor(){return {inRange(){return {dockCount:good?2400:0,dispose(){disposed++;}};},dispose(){disposed++;}};}},dispose(){disposed++;}};
   };
   return img;
  };
  f.context.OpenCvSharp.OpenCvSharp.Cv2.countNonZero=m=>m.dockCount||0;
  const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
  assert.equal(r.boardStepAttempted===true,mode==='docked',JSON.stringify(r));
  assert.ok(!f.inputs.some(x=>x.kind==='down'&&x.key==='VK_SPACE'));
  if(mode==='docked'){const down=f.inputs.find(x=>x.kind==='down'&&x.key==='VK_W'),up=f.inputs.find(x=>x.kind==='up'&&x.key==='VK_W'&&x.at>=down.at);assert.equal(up.at-down.at,400);}
  assert.equal(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_W'),mode==='docked');
  assert.ok(disposed>=6);assert.equal(r.pauseVerified,true);
  if(mode==='docked')assert.equal(r.dockSamples.length,2);
 }
});

test('mechanism wait cannot press F for another label or move',async()=>{
 const f=setup({action:'activateMechanism',holds:0}),o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
 assert.ok(!f.inputs.some(x=>x.kind==='down'&&['VK_F','VK_W','VK_SPACE'].includes(x.key)));assert.equal(r.pauseVerified,true);
});

test('disembark waits for the near mechanism marker and uses one short step',async()=>{
 for(const visible of [false,true]){const f=setup({action:'disembarkPlatform',holds:0}),capture=f.context.captureGameRegion;
 f.context.captureGameRegion=()=>{const img=capture(),crop=img.deriveCrop;img.deriveCrop=(x,y,w,h)=>x===650&&y===350&&w===85&&h===80?{srcMat:{cvtColor(){return {inRange(){return {dockCount:visible?400:0,dispose(){}};},dispose(){}};}},dispose(){}}:crop(x,y,w,h);return img;};
 f.context.OpenCvSharp.OpenCvSharp.Cv2.countNonZero=m=>m.dockCount||0;
 const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);assert.equal(r.disembarkAttempted===true,visible,JSON.stringify(r));assert.equal(r.pauseVerified,true);
 if(visible){const d=f.inputs.find(x=>x.kind==='down'&&x.key==='VK_W'),u=f.inputs.find(x=>x.kind==='up'&&x.key==='VK_W'&&x.at>=d.at);assert.equal(u.at-d.at,600);}else assert.ok(!f.inputs.some(x=>x.kind==='down'&&x.key==='VK_W'));}
});

test('mechanism uses the verified English Start label exactly once',async()=>{
 const f=setup({action:'activateMechanism',holds:0});f.setFlag('fieldRowsSequence',[rows().concat([row('Start',1220,525),row('F',1105,525)])]);
 const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
 assert.equal(r.interactionAttempted,'activateMechanism',JSON.stringify(r));assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_F').length,1);assert.equal(r.pauseVerified,true);
});

test('activated mechanism docking requires its receipt and two cyan samples',async()=>{
 for(const mode of ['missing-receipt','void','one-only','docked']){
  const f=setup({action:'carefulDisembarkActive',holds:0}),files=f.getVirtualFiles(),capture=f.context.captureGameRegion;let samples=0;
  if(mode!=='missing-receipt')files.set('reports/lion-adapter-test.json',JSON.stringify([entry,{session:'lion-adapter-test',status:'completed',timestamp:9800,details:{result:{interactionAttempted:'activateMechanism'}}}]));
  f.context.captureGameRegion=()=>{const img=capture(),crop=img.deriveCrop;img.deriveCrop=(x,y,w,h)=>{
   if(x!==740||y!==430||w!==60||h!==80)return crop(x,y,w,h);samples++;
   return {srcMat:{cvtColor(){return {inRange(){return {dockCount:mode==='docked'||mode==='one-only'&&samples===1?1000:0,dispose(){}};},dispose(){}};}},dispose(){}};
  };return img;};
  f.context.OpenCvSharp.OpenCvSharp.Cv2.countNonZero=m=>m.dockCount||0;
  const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);
  assert.equal(r.disembarkAttempted===true,mode==='docked',JSON.stringify(r));
  assert.equal(f.inputs.some(x=>x.kind==='down'&&x.key==='VK_W'),mode==='docked');
  assert.ok(!f.inputs.some(x=>x.kind==='down'&&x.key==='VK_SPACE'));
  if(mode==='missing-receipt')assert.equal(f.inputs.length,0);else assert.equal(r.pauseVerified,true);
 }
});

test('wind learning follows only the entry-validated stopped predecessor chain',async()=>{
 for(const valid of [true,false]){const f=setup({action:'windLaunch',holds:0,windTutorialFrameId:0}),files=f.getVirtualFiles();
 const old={...entry,id:'entry',session:'old-one'},stop={id:'stop',session:'old-one',status:'failed',timestamp:9500,details:{reason:'Pause protection exhausted: pause is UNVERIFIED; operator intervention required'}},previous={...stop,id:'previous',session:'old-two',timestamp:9850};
 files.set('reports/lion-adapter-test.json','[]');files.set('reports/old-one.json',JSON.stringify([old,stop]));
 files.set('reports/old-two.json',JSON.stringify([{session:'old-two',status:'completed',timestamp:9800,details:{result:{step:'lionVisualMove',airborneVerified:true,gliderAttempted:true},inputEvents:[{type:'key',key:'VK_SPACE',durationMs:60},{type:'key',key:'VK_SPACE',durationMs:60}]}},...(valid?[previous]:[])]));
 files.set('lion-session-handoff.json',JSON.stringify({session:'lion-adapter-test',sourceSession:'old-one',sourceStopId:'stop',entryId:'entry',predecessorSession:'old-two',predecessorStopId:'previous',reviewed:true,createdAt:9900}));
 const o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);assert.equal(f.inputs.filter(x=>x.kind==='down'&&x.key==='VK_SPACE').length,valid?2:0,JSON.stringify(r));}
});

test('glide corrections reject turns greater than 150 before input',async()=>{
 const f=setup({action:'glideForward',holds:1,relativeDx:151}),o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);assert.equal(r.moves,0);assert.equal(f.inputs.length,0);
});

test('cautious air travel retains the 30 percent floor and two-hold limit',async()=>{
 const air={session:'s',timestamp:1000,frameId:1,map:null,hud:{world:false,groundControls:false,climbing:false,health:{current:682,max:1363}},ocr:[row('Lumina',1682,257),row('Amber',1690,347),row('Kaeya',1694,437),row('Lisa',1690,540),row('Trial',1800,509),row('Space',1730,1026)]};
 assert.equal(guard.air(air,1000,'s'),false);assert.ok(guard.air(air,1000,'s',0.3));assert.equal(guard.air({...air,hud:{...air.hud,health:{current:400,max:1363}}},1000,'s',0.3),false);
 const f=setup({action:'carefulGlide',holds:3}),o=await f.adapter.observe('lion-adapter-test',5),r=await f.adapter.runLionVisualMove(o,f.observe);assert.equal(f.inputs.length,0);assert.equal(r.moves,0);
});
