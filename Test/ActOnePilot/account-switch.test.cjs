const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const context={};vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8'),context);
const observation=()=>({timestamp:1000,ocr:[{text:'UID: 665976391',x:1686,y:1048},{text:'Click to claim your daily Blessing of the Welkin Moon rewards',x:460,y:836}]});
const permit=()=>({session:'test',frameId:1,reviewed:true,currentUid:'665976391',expectedUid:'693306810',createdAt:1000});
const request={session:'test',expectedFrameId:1};
test('saved-account expansion requires the exact measured chooser and selected masked account',()=>{
 const o={timestamp:1000,ocr:[{text:'HOYOVERSE',x:818,y:376},{text:'Start game',x:888,y:617},{text:'Log in to another account',x:800,y:694},{text:'ex****le@example.com',x:781,y:478}]};
 const p={action:'expandSavedAccounts',userLabel:'ex****le@example.com'};
 assert.equal(context.actOneSavedAccountTarget(o,1000,p).x,1200);
 assert.equal(context.actOneSavedAccountTarget(o,2001,p),null);
 assert.equal(context.actOneSavedAccountTarget(o,1000,{...p,action:'claim'}),null);
 assert.equal(context.actOneSavedAccountTarget(o,1000,{...p,userLabel:'other****'}),null);
 assert.equal(context.actOneSavedAccountTarget({...o,ocr:o.ocr.slice(1)},1000,p),null);
});
test('saved account selection targets its unique label away from removal controls; start requires the selected identity',()=>{
 const o={timestamp:1000,ocr:[{text:'HOYOVERSE',x:816,y:375},{text:'ex****le@example.com',x:784,y:636,width:215,height:30},{text:'Log in to another account',x:824,y:824}]};
 const p={action:'selectSavedAccount',userLabel:'ex****le@example.com'};
 assert.equal(context.actOneSavedAccountTarget(o,1000,p).x,892);
 assert.equal(context.actOneSavedAccountTarget({...o,ocr:[...o.ocr,o.ocr[1]]},1000,p),null);
 assert.equal(context.actOneSavedAccountTarget(o,1000,{...p,action:'startSavedAccount'}),null);
 const selected={timestamp:1000,ocr:[o.ocr[0],{text:p.userLabel,x:781,y:478},{text:'Start game',x:888,y:617},{text:'Log in to another account',x:800,y:694}]};
 assert.equal(context.actOneSavedAccountTarget(selected,1000,{...p,action:'startSavedAccount'}).y,632);
 assert.equal(context.actOneSavedAccountTarget(selected,1000,{...p,action:'startSavedAccount',userLabel:'wrong****@example.com'}),null);
});
test('account UI click settles pointer before press and guarantees release on cancellation',async()=>{
 for(const fail of [false,true]){
  const events=[];const ops={checkStop(){},ready(){},move:(x,y)=>events.push([x,y]),down:()=>events.push('down'),up:()=>events.push('up'),sleep:async ms=>{events.push(ms);if(fail&&ms===100)throw Error('cancel');}};
  if(fail)await assert.rejects(context.actOneAccountUiClick(ops,{x:1088,y:590}),/cancel/);else await context.actOneAccountUiClick(ops,{x:1088,y:590});
  assert.deepEqual(events,[[1088,590],120,'down',100,'up']);
 }
});
test('switch confirmation rejects unrelated OK dialogs, authentication, stale or ambiguous evidence',()=>{
 const o={timestamp:1000,ocr:[{text:'Are you sure you want to switch',x:726,y:459,width:407,height:28},{text:'accounts?',x:722,y:492,width:139,height:35},{text:'Cancel',x:788,y:576,width:91,height:29},{text:'OK',x:1064,y:572,width:47,height:35}]};
 assert.equal(context.actOneAccountConfirmTarget(o,1000).x,1088);
 for(const mutate of [o=>o.timestamp=0,o=>o.ocr.shift(),o=>o.ocr.push(o.ocr[3]),o=>o.ocr.push({text:'Password'}),o=>o.ocr[3].x=100]){
  const copy=JSON.parse(JSON.stringify(o));mutate(copy);assert.equal(context.actOneAccountConfirmTarget(copy,1001),null);
 }
});
test('title logout requires exact fresh title and reviewed masked user binding',()=>{
 const o={timestamp:1000,map:null,hud:{world:false},ocr:[{text:'START GAME',x:763,y:478,width:390,height:57},{text:'User ex****le@example.com',x:769,y:1005}]};
 const p={...permit(),userLabel:'User ex****le@example.com'};
 assert.equal(context.actOneAccountTitleTarget(o,1000,p,request).x,1824);
 for(const change of [{consumed:true},{session:'other'},{frameId:2},{reviewed:false},{userLabel:'User other****@example.com'},{createdAt:-60000}])assert.equal(context.actOneAccountTitleTarget(o,1000,{...p,...change},request),null);
 assert.equal(context.actOneAccountTitleTarget({...o,timestamp:0},1001,p,request),null);
 assert.equal(context.actOneAccountTitleTarget({...o,ocr:[...o.ocr,{text:'Password'}]},1000,p,request),null);
});
test('account close requires fresh mismatched UID, exact reward and one-use request-bound permit',()=>{
 assert.equal(context.actOneAccountSwitchCloseReady(observation(),1000,permit(),request),true);
 for(const mutate of [p=>p.consumed=true,p=>p.reviewed=false,p=>p.frameId=2,p=>p.session='other',p=>p.expectedUid=p.currentUid,p=>p.currentUid='123456789',p=>p.createdAt=-60000]){
  const p=permit();mutate(p);assert.equal(context.actOneAccountSwitchCloseReady(observation(),1000,p,request),false);
 }
 for(const mutate of [o=>o.timestamp=-1,o=>o.timestamp=1001,o=>o.ocr.pop(),o=>o.ocr.push(o.ocr[0]),o=>o.ocr[0].text='UID: 693306810']) {
  const o=observation();mutate(o);assert.equal(context.actOneAccountSwitchCloseReady(o,1000,permit(),request),false);
 }
});
test('normal close chord releases both keys on success and cancellation without claiming reward',async()=>{
 for(const failAt of [0,1,2,3]){
  const events=[];let checks=0;
  const ops={checkStop(){if(++checks===failAt)throw Error('cancel');},ready(){},keyDown:k=>events.push('down:'+k),keyUp:k=>events.push('up:'+k),sleep:async()=>{if(failAt===3)throw Error('cancel');}};
  if(failAt)await assert.rejects(context.actOneAccountSwitchCloseChord(ops),/cancel/);else await context.actOneAccountSwitchCloseChord(ops);
  assert.deepEqual(events.slice(-2),['up:VK_F4','up:VK_MENU']);
  assert.ok(events.every(e=>/VK_MENU|VK_F4/.test(e)));
 }
});
