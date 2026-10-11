const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');

async function runMain({failFocus=false,sessionId=6,remote=true}={}) {
  let now=100000,polls=0,releases=0,focuses=0,callback=null;
  const files=new Map(),states=[],sleeps=[],captures=[];
  const write=(p,t)=>{files.set(p,t);if(p==='controller-status.json')states.push(JSON.parse(t));return true;};
  const api={now:()=>now,focusGame:async()=>{focuses++;if(failFocus)throw Error('No RDP game focus');},
    setHeartbeat:fn=>{callback=fn;},heartbeat:(_,force)=>callback(force),
    observe:async(session,n)=>{captures.push([session,n]);return {timestamp:now,screenshotPath:`${session}/${n}.png`,hud:{world:false},ocr:[]};},
    write,append:(p,t)=>write(p,(files.get(p)||'')+t),wasSeen:(s,id)=>files.has(`receipts/${s}/${id}.json`),
    beginMission:()=>{},events:()=>[],release:()=>{releases++;}};
  const source={
    'engine.js':fs.readFileSync(path.join(root,'engine.js'),'utf8'),
    'bgi.js':'function createActOneAdapter(){return testAdapter;}',
    'mission.js':'var ActOneMission={};','combat.js':'var ActOneCombat={};','recovery.js':'var ActOneRecovery={};'
  };
  const context=vm.createContext({testAdapter:api,Date:{now:()=>now},Math,Number,JSON,Object,Error,
    genshin:{isRemoteDesktopSession:remote,windowsSessionId:sessionId,betterGiProcessId:1234,width:1920,height:1080},
    settings:{enableInput:false},dispatcher:{clearAllTriggers:()=>{}},getGameMetrics:()=>[1920,1080,1],setGameMetrics:()=>{},log:{info:()=>{}},
    file:{readTextSync:p=>source[p]??files.get(p),writeTextSync:write,createDirectory:()=>true,isExists:p=>files.has(p)},
    sleep:async ms=>{sleeps.push(ms);polls++;if(polls>3)throw Error('Listener did not honor explicit stop');
      now+=polls===1?7200000:polls===2?30*24*3600000:ms;
      const latest=JSON.parse(files.get('observation.json'));
      write('request.json',JSON.stringify({id:`request-${polls}`,session:latest.session,expectedFrameId:latest.frameId,createdAt:now,mission:polls===3?'stop':'observe'}));}
  });
  let error=null;try{await vm.runInContext(fs.readFileSync(path.join(root,'main.js'),'utf8'),context);}catch(e){error=e;}
  return {files,states,polls,releases,focuses,captures,error};
}

test('actual main listener survives two hours and a month idle, then honors explicit stop',async()=>{
  const h=await runMain();assert.equal(h.error,null);assert.equal(h.polls,3);assert.equal(h.focuses,1);
  assert.equal(new Set(h.captures.map(c=>c[0])).size,1,'no periodic session restart');
  assert.ok(h.states.some(s=>s.heartbeatAt>=30*24*3600000&&s.state==='idle'));
  assert.equal(h.states.at(-1).state,'stopped');assert.equal(h.states.at(-1).processId,1234);
  assert.ok(h.releases>=3);assert.equal(JSON.parse(h.files.get('receipt.json')).status,'stopped');
});

test('initial focus failure publishes faulted state and releases keys without accepting work',async()=>{
  const h=await runMain({failFocus:true});assert.match(h.error.message,/No RDP game focus/);
  assert.equal(h.polls,0);assert.equal(h.captures.length,0);assert.equal(h.releases,1);
  assert.equal(h.states.at(-1).state,'faulted');assert.match(h.states.at(-1).error,/focus/);
});

test('main accepts session 6 and rejects non-RDP, console, and session 0 before accepting work',async()=>{
  const allowed=await runMain();
  assert.equal(allowed.error,null);
  assert.equal(allowed.states[0].windowsSessionId,6);
  assert.equal(allowed.states[0].remoteDesktop,true);
  for(const options of [{remote:false},{sessionId:1,remote:true},{sessionId:0}]) {
    const rejected=await runMain(options);
    assert.match(rejected.error.message,/verified RDP child session above Windows session 1/);
    assert.equal(rejected.captures.length,0);
  }
});
