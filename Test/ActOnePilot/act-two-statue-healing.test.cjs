const test=require('node:test'),assert=require('node:assert/strict'),m=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('lower health healing approach is only the nearby known Statue, without enemies, within ten seconds',()=>{const r={objective:'Explore for Adventure Rank',deadlineMs:10000,waypoints:[{map:'Teyvat',x:-1265.917,y:1928.381}]},o={map:{map:'Teyvat',x:-1266.35,y:1934.03},hud:{world:true,groundControls:true,enemyBars:[],health:{current:1539,max:2635}}};assert.equal(m.statueHealingApproach(r,o),true);for(const patch of [{deadlineMs:10001},{waypoints:[{map:'Teyvat',x:-1220,y:2315}]},{objective:'Defeat the attacking monsters'}])assert.equal(m.statueHealingApproach({...r,...patch},o),false);for(const patch of [{health:{current:0,max:2635}},{health:{current:2636,max:2635}},{enemyBars:[{}]},{climbing:true},{health:{current:-1,max:2635}}])assert.equal(m.statueHealingApproach(r,{...o,hud:{...o.hud,...patch}}),false);assert.equal(m.statueHealingApproach(r,{...o,map:{...o.map,x:-1250}}),false);});

test('Statue result confirms only fresh full health on original account',()=>{
 const fs=require('fs'),vm=require('vm'),c={};vm.runInNewContext(fs.readFileSync('BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js','utf8'),c);
 const o={session:'s',timestamp:1000,hud:{world:true,groundControls:true,health:{current:2635,max:2635}},ocr:[{text:'693306810',x:1732,y:1050}]};assert.equal(c.actOneStatueHealingVerified(o,1000,'s'),true);assert.equal(c.actOneStatueHealingVerified({...o,hud:{...o.hud,health:{current:2330,max:2635}}},1000,'s'),false);assert.equal(c.actOneStatueHealingVerified(o,2001,'s'),false);assert.equal(c.actOneStatueHealingVerified(o,1000,'other'),false);assert.equal(c.actOneStatueHealingVerified({...o,ocr:[]},1000,'s'),false);
 for(const hud of [undefined,null,{}, {world:true,groundControls:true,health:null}])assert.equal(c.actOneStatueHealingVerified({...o,hud},1000,'s'),false);
});

test('recorded emergency arrival is permitted only for healing, including below combat floor',()=>{const r={objective:'Explore for Adventure Rank',deadlineMs:10000,waypoints:[{map:'Teyvat',x:-1265.917,y:1928.381}]},o={map:{map:'Teyvat',x:-1266.3516,y:1934.0313},hud:{world:true,groundControls:true,enemyBars:[],health:{current:750,max:2635}}};assert.equal(m.statueHealingApproach(r,o),true);assert.equal(m.statueHealingApproach({...r,objective:'Defeat all opponents'},o),false);});


// Run the installed mission branch and interaction resolver with physical input boundaries mocked.
function starfellOpenerMission() {
 const fs=require('fs'),path=require('path'),vm=require('vm');
 const pilot=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
 const context={file:{readTextSync:name=>{
  assert.equal(name,'act-two-interaction.js');return fs.readFileSync(path.join(pilot,name),'utf8');
 }}};
 vm.runInNewContext(fs.readFileSync(path.join(pilot,'mission.js'),'utf8'),context);
 return context.ActOneMission;
}

// The selected nearby Statue is synthetic; 2211/4015 is the retained real selection's HP.
function starfellOpenerField(current=2211,max=4015) {
 return {session:'low-health-starfell',frameId:4,timestamp:10000,
  map:{map:'Teyvat',x:-1324.474,y:2566.115,cameraAngle:180},
  hud:{world:true,groundControls:true,climbing:false,auto:false,dialogueReady:false,choice:false,
   health:{current,max},enemyBars:[],objectives:[]},
  ocr:[{text:'Statue of The Seven',x:1200,y:510,height:24},
   {text:'F',x:1120,y:510,height:24},{text:'693306810',x:1732,y:1050}]};
}

// Keep the original inventory wrapper seam explicit; this is not a live wrapper/UID qualification.
async function runStarfellOpener(field,{repeat=false,refuseWrapper=false}={}) {
 const mission=starfellOpenerMission(),calls=[],initial={session:field.session,frameId:3,hud:{inventory:true}};
 const observe=async()=>{
  calls.push(['observe']);return repeat?field:{...field,frameId:5,hud:{...field.hud,dialogueReady:true}};
 };
 const api={
  runActTwoNavigationWithPause:async(source,reader,callback)=>{
   assert.equal(source,initial);assert.equal(reader,observe);calls.push(['wrapper']);
   if(refuseWrapper)throw Error('Fresh original-account inventory required');
   return callback(field);
  },
  checkStop:()=>{},sleep:async ms=>calls.push(['sleep',ms]),
  keyPress:async key=>calls.push(['key',key]),
  forward:async ms=>calls.push(['forward',ms]),rotate:async dx=>calls.push(['rotate',dx]),
 };
 return {result:await mission.runQuestStep('actTwoStarfellStatueOpen',initial,api,observe),calls};
}

test('Starfell recovery opens for recorded 2211/4015 and one living Kaeya HP without healing claims',async()=>{
 for(const current of [2211,1,4015]) {
  const {result,calls}=await runStarfellOpener(starfellOpenerField(current));
  assert.deepEqual(calls,[['wrapper'],['key','VK_F'],['sleep',900],['observe']]);
  assert.equal(result.status,'stopped');assert.equal(result.moves,0);assert.equal(result.turns,0);
  assert.equal(result.fieldFrameId,5);assert.equal(result.healthVerified,undefined);
 }
});

test('Starfell recovery rejects dead noninteger nonfinite overmax and wrong-character health',async()=>{
 const fields=[0,-1,1.5,NaN,Infinity,-Infinity,'2211',null,undefined,4016].map(n=>{const field=starfellOpenerField();field.hud.health.current=n;return field;});
 fields.push(starfellOpenerField(2211,4014),starfellOpenerField(2211,2764));
 const absent=starfellOpenerField();absent.hud.health=null;fields.push(absent);
 for(const field of fields) {
  const {result,calls}=await runStarfellOpener(field);
  assert.deepEqual(calls,[['wrapper']]);assert.equal(result.status,'stopped');
  assert.equal(result.reason,'Fresh selected Starfell Statue interaction required');
 }
});

test('Starfell Amber retains its original exact seventy-percent floor',async()=>{
 for(const [current,allowed] of [[1,false],[1213,false],[1733*.7,true],[1214,true],[1733,true]]) {
  const {calls}=await runStarfellOpener(starfellOpenerField(current,1733));
  assert.deepEqual(calls.filter(row=>row[0]==='key'),allowed?[['key','VK_F']]:[]);
 }
});

test('Starfell low-health entry retains every existing non-health approach and selection gate',async()=>{
 const base=starfellOpenerField(1),fields=[];
 for(const key of ['world','groundControls'])fields.push({...base,hud:{...base.hud,[key]:false}});
 for(const key of ['climbing','auto','dialogueReady','choice'])fields.push({...base,hud:{...base.hud,[key]:true}});
 for(const enemyBars of [undefined,null,[{}]])fields.push({...base,hud:{...base.hud,enemyBars}});
 fields.push({...base,hud:{...base.hud,objectives:['Another quest']}},
  {...base,map:{...base.map,map:'Unknown'}},{...base,map:{...base.map,x:-1323.474+15}},
  {...base,map:{...base.map,x:NaN}},{...base,map:null});
 for(const field of fields)assert.deepEqual((await runStarfellOpener(field)).calls,[['wrapper']]);
 const unselected={...base,ocr:base.ocr.filter(row=>row.text!=='F')};
 const missing=await runStarfellOpener(unselected,{repeat:true});
 assert.deepEqual(missing.calls.filter(row=>['key','forward','rotate'].includes(row[0])),[]);
 const tooFar={...base,map:{...base.map,x:-1323.474-3.01}};
 assert.deepEqual((await runStarfellOpener(tooFar)).calls,[['wrapper']]);
});

test('Starfell low-health approach still has four W500 moves or eight bounded turns and no fallback input',async()=>{
 // Retained arrival coordinates, with synthetic alignment and repeated observations to exhaust each existing cap.
 const base=starfellOpenerField(1),map={map:'Teyvat',x:-1329.8359375,y:2564.1923828125,cameraAngle:0};
 const dx=-1323.474-map.x,dy=2566.115-map.y;
 map.cameraAngle=(Math.atan2(-dy,-dx)*180/Math.PI+360)%360;
 const aligned={...base,map,ocr:base.ocr.filter(row=>row.text==='693306810')};
 const moved=await runStarfellOpener(aligned,{repeat:true});
 assert.deepEqual(moved.calls.filter(row=>['key','forward','rotate'].includes(row[0])),
  Array.from({length:4},()=>['forward',500]));
 assert.equal(moved.result.moves,4);assert.equal(moved.result.turns,0);
 const turned=await runStarfellOpener({...aligned,map:{...map,cameraAngle:(map.cameraAngle+180)%360}},{repeat:true});
 const inputs=turned.calls.filter(row=>['key','forward','rotate'].includes(row[0]));
 assert.equal(inputs.length,8);assert(inputs.every(row=>row[0]==='rotate'&&Number.isInteger(row[1])&&Math.abs(row[1])<=250));
 assert.equal(turned.result.moves,0);assert.equal(turned.result.turns,8);
});

test('Starfell low health cannot bypass the original inventory wrapper refusal',async()=>{
 await assert.rejects(runStarfellOpener(starfellOpenerField(2211),{refuseWrapper:true}),
  /Fresh original-account inventory required/);
});
