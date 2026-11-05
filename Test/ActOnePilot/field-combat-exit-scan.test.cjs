const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('field combat uses a full-width scan on direct entry and final protection', () => {
  const context = {};
  const adapter = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
  vm.runInNewContext(fs.readFileSync(adapter, 'utf8'), context);
  const scan = context.actOneRequestsGroundObservation;
  const combat = {mission:'questStep', step:'actTwoFieldCombat'};
  assert.equal(scan(combat, false, false), false);
  assert.equal(scan(combat, false, true), true);
  const direct={...combat,entryScene:'world',expectedFrameId:7};
  assert.equal(scan(direct,false,false,8),true);
  assert.equal(scan(direct,false,false,9),false);
  assert.equal(scan(direct,true,false,8),false);
  assert.equal(scan(combat, true, true), false);
  assert.equal(scan({mission:'questStep', step:'actTwoNativeCombat'}, false, true), false);
  assert.equal(scan({mission:'observe'}, false, false), true);
  assert.equal(scan({mission:'navigation', objective:'Explore for Adventure Rank', requireMeasuredGround:true}, false, false), true);
  assert.equal(scan({mission:'navigation', objective:'Explore for Adventure Rank'}, false, false), false);
});

test('native heartbeat advertises direct world entry for the running script session', () => {
  const script=fs.readFileSync(path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot/main.js'),'utf8');
  const source=script.slice(script.indexOf('    function heartbeat('),script.indexOf('    function checkStartupStop('));
  let status;
  const context={session:'current-session',lastHeartbeat:0,runner:{getState:()=>({state:'idle',frameId:7,activeRequestId:null})},
      genshin:{betterGiProcessId:123,windowsSessionId:3,isRemoteDesktopSession:true},safetyFault:null,failure:null,
      file:{writeTextSync:(_path,content)=>{status=JSON.parse(content);return true;}}};
  vm.runInNewContext(source+';heartbeat(true)',context);
  assert.equal(status.session,'current-session');assert.equal(status.frameId,7);assert.equal(status.fieldCombatWorldEntry,true);
});
