const test=require('node:test');
const assert=require('node:assert/strict');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

test('Falcon level-four enemy bars require Lv.4 while default enemy-bar behavior remains Lv.1',()=>{
  const bar={x:900,y:500,width:120,height:8};
  const lv4={text:'Lv.4',x:880,y:460,width:40,height:20};
  const lv1={text:'Lv.1',x:880,y:460,width:40,height:20};
  assert.equal(bgi.enemyBarAnchored(bar,[lv4],4),true);
  assert.equal(bgi.enemyBarAnchored(bar,[lv4]),false);
  assert.equal(bgi.enemyBarAnchored(bar,[lv1]),true);
  assert.equal(bgi.enemyBarAnchored(bar,[lv1],4),false);
});

function frame({health={current:1000,max:1000},enemyBars=[{x:900,y:500,width:120,height:8}],ocr=[],...patch}={}) {
  return {frameId:1,map:null,ocr,hud:{health,enemyBars,journal:false,bigMap:false,...patch}};
}
function harness({observed=()=>frame(),observeAdvance=0,pauseText='Continue Challenge',pauseResponses=null,stopAt=Infinity}={}) {
  let now=1000,observations=0,checks=0,pauseCalls=0;const keys=[],scans=[],events=[];
  const api={now:()=>now,sleep:async ms=>{now+=ms;events.push(['sleep',ms]);},
    checkStop:()=>{checks++;events.push('guard');if(checks>=stopAt)throw new Error('Stop requested');},
    falconContinue:()=>events.push('continue'),
    falconCombatKey:async key=>{keys.push({key,at:now});events.push(['key',key]);},
    falconCombatScan:async first=>{scans.push(first);events.push(['scan',first]);},
    falconPause:async()=>{pauseCalls++;events.push('pause');}};
  const observe=async()=>{observations++;now+=observeAdvance;events.push('observe');
    if(pauseCalls){const p=pauseResponses?pauseResponses[Math.min(pauseCalls-1,pauseResponses.length-1)]:{text:pauseText};
      return frame({health:Object.prototype.hasOwnProperty.call(p,'health')?p.health:{current:1000,max:1000},ocr:p.text?[{text:p.text}]:[]});}
    return observed(observations);};
  return {api,observe,keys,scans,events,get observations(){return observations;},run:()=>mission.runQuestStep('falconCombat',frame(),api,observe)};
}

test('Falcon combat stops after repeated missing enemy evidence',async()=>{
  const h=harness({observed:()=>frame({enemyBars:[]})});
  const result=await h.run();
  assert.equal(result.status,'stopped');assert.match(result.reason,/Enemy evidence absent/);
  assert.equal(result.actions,5);assert.deepEqual(h.keys.map(x=>x.key),['VK_1']);
  assert.equal(result.paused,true);
});

test('Falcon combat stops for low HP before further attacks',async()=>{
  const h=harness({observed:n=>frame({health:n>=2?{current:550,max:1000}:{current:1000,max:1000}})});
  const result=await h.run();
  assert.equal(result.reason,'Combat health guard');assert.equal(result.actions,1);
  assert.deepEqual(h.keys.map(x=>x.key),['VK_1']);
});

test('opening burst follows the fresh safe enemy guard and is omitted for missing or unsafe targets',async()=>{
  const safe=harness();await safe.run();
  assert.deepEqual(safe.keys.slice(0,2).map(x=>x.key),['VK_1','VK_Q']);
  const missing=harness({observed:()=>frame({enemyBars:[]})});await missing.run();
  assert.deepEqual(missing.keys.map(x=>x.key),['VK_1']);
  const unsafe=harness({observed:n=>frame({health:n===2?{current:550,max:1000}:{current:1000,max:1000}})});await unsafe.run();
  assert.deepEqual(unsafe.keys.map(x=>x.key),['VK_1']);
});

test('Falcon combat uses at most four bounded camera scans then stops without enemy evidence',async()=>{
  const h=harness({observed:()=>frame({enemyBars:[]})});
  const result=await h.run();
  assert.equal(result.reason,'Enemy evidence absent; inspect completion or camera');
  assert.deepEqual(h.scans,[true,false,false,false]);
  assert.equal(result.actions,5,'one character select plus four counted scan actions');
  assert.equal(result.paused,true);
});

test('Falcon combat enforces its health guard immediately after a scan',async()=>{
  const h=harness({observed:n=>frame({health:n>=5?{current:750,max:1000}:{current:1000,max:1000},enemyBars:[]})});
  const result=await h.run();
  assert.equal(result.reason,'Combat health guard');
  assert.deepEqual(h.scans,[true]);
  assert.equal(result.actions,2,'character select and one bounded scan only');
});

test('Falcon combat schedules skills by elapsed time and stays within the 30-action cap',async()=>{
  const timed=harness({observeAdvance:1600});
  const paced=await timed.run();
  const skills=timed.keys.filter(x=>x.key==='VK_E');
  assert.ok(skills.length>=2,'skill cadence should repeat after its interval');
  for(let i=1;i<skills.length;i++)assert.ok(skills[i].at-skills[i-1].at>=8500);
  assert.ok(paced.actions<=30);assert.equal(paced.status,'stopped');

  const capped=harness();
  const result=await capped.run();
  assert.equal(result.actions,30);assert.equal(capped.keys.length,30);
  assert.equal(result.reason,'Combat action limit');
});

test('pause is reported only when the fresh post-pause OCR says Continue Challenge',async()=>{
  const confirmed=await harness({observed:()=>frame({enemyBars:[]}),pauseText:'Continue Challenge'}).run();
  const ambiguous=await harness({observed:()=>frame({enemyBars:[]}),pauseText:'Leave Domain?'}).run();
  assert.equal(confirmed.paused,true);assert.equal(ambiguous.paused,false);
});

test('pause retries after an ignored Escape and stops after three unsuccessful attempts',async()=>{
  const recovered=harness({observed:()=>frame({enemyBars:[]}),pauseResponses:[{text:'Not paused'},{text:'Continue Challenge'}]});
  const recoveredResult=await recovered.run();
  assert.equal(recovered.events.filter(x=>x==='pause').length,2);assert.equal(recoveredResult.paused,true);
  const exhausted=harness({observed:()=>frame({enemyBars:[]}),pauseResponses:[{text:'Still active'}]});
  const exhaustedResult=await exhausted.run();
  assert.equal(exhausted.events.filter(x=>x==='pause').length,3);assert.equal(exhaustedResult.paused,false);
});

test('pause retry stops immediately when health evidence disappears',async()=>{
  const h=harness({observed:()=>frame({enemyBars:[]}),pauseResponses:[{text:'',health:null}]});
  const result=await h.run();
  assert.equal(h.events.filter(x=>x==='pause').length,1);assert.equal(result.paused,false);
});

test('stop-guard exceptions escape without invoking the pause action',async()=>{
  const h=harness({stopAt:1});
  await assert.rejects(h.run(),/Stop requested/);
  assert.equal(h.events.includes('pause'),false);
  assert.deepEqual(h.keys.map(x=>x.key),['VK_1','VK_Q'],'the guarded opening burst precedes the first loop stop check');
});
