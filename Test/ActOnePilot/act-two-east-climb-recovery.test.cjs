const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const runtime=path.resolve(__dirname,'../../artifacts/release-r18/BetterGI-English-win-x64/User/JsScript/ActOnePilot/mission.js');
const {climb,ground:land}=require('./act-two-east-climb-recovery.fixture.json');
for(const file of [root,...(fs.existsSync(runtime)?[runtime]:[])]) {
  const m=require(file),label=file===root?'source':'hotloaded runtime';
  test(`${label}: recorded low east wall admits one bounded release`,()=>{
    assert(m.reviewedClimbRelease(climb,null,climb.timestamp+500,5000));
    assert(m.settledClimbLanding(land,climb.session,climb.hud.health.current,land.timestamp+500));
  });
  test(`${label}: wall recovery rejects changed terrain, damage, threats, account, stale state, and low reserve`,()=>{
    const no=(o,now=climb.timestamp+500,remaining=5000)=>assert(!m.reviewedClimbRelease(o,null,now,remaining));
    no({...climb,map:{...climb.map,x:climb.map.x+2}});
    no({...climb,map:{...climb.map,cameraAngle:90}});
    no({...climb,hud:{...climb.hud,health:{...climb.hud.health,current:3500}}});
    no({...climb,hud:{...climb.hud,enemyBars:[{}]}});
    no({...climb,ocr:[]});
    no({...climb,session:null});
    no(climb,climb.timestamp+1001);
    no(climb,climb.timestamp+500,3999);
    assert(!m.settledClimbLanding({...land,hud:{...land.hud,climbing:true,groundControls:false}},climb.session,3942,land.timestamp+500));
    assert(!m.settledClimbLanding({...land,hud:{...land.hud,health:{...land.hud.health,current:3941}}},climb.session,3942,land.timestamp+500));
    assert(!m.settledClimbLanding(land,'other',3942,land.timestamp+500));
  });
}
