const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const context={};
for(const file of ['bgi.js','mission.js'])vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot',file),'utf8'),context);
// Geometry transcribed from the real RDP capture mv84sfhv-svbkocioqk/frame-0001.
const sample=()=>({timestamp:1000,frameId:1,ocr:[
 {text:'You have disconnected',x:736,y:278,width:447,height:43},
 {text:'Connection timed out',x:799,y:490,width:321,height:37},
 {text:'Confirm',x:909,y:734,width:134,height:43}]});
test('reconnect accepts measured timeout and rejects stale, future, ambiguous, auth and unrelated dialogs',()=>{
 assert.equal(context.actOneReconnectTarget(sample(),1000).x,976);
 for(const mutate of [o=>o.timestamp=-1,o=>o.timestamp=1001,o=>o.ocr.push(o.ocr[2]),o=>o.ocr.push({text:'Password'}),o=>o.ocr[1].text='Maintenance',o=>o.ocr[2].x=100,o=>o.ocr[2].width=NaN]) {
  const o=sample();mutate(o);assert.equal(context.actOneReconnectTarget(o,1000),null);
 }
});
test('reconnect sends one confirmation, settles, observes once and never claims connected',async()=>{
 let clicks=0,observations=0,now=1000;
 const api={now:()=>now,checkStop(){},requireInputReady(){},reconnectGame(){clicks++;},sleep:async ms=>{now+=ms;}};
 const result=await context.ActOneMission.runQuestStep('reconnectGame',sample(),api,async()=>{observations++;return {frameId:2};});
 assert.equal(clicks,1);assert.equal(observations,1);assert.equal(now,1800);assert.equal(result.reconnectionVerified,false);
 const bad=sample();bad.ocr=[];
 assert.equal((await context.ActOneMission.runQuestStep('reconnectGame',bad,api,async()=>{throw Error('unexpected');})).clicks,0);
});
test('focus failure and cancellation prevent reconnect input',async()=>{
 for(const guard of ['checkStop','requireInputReady']) {
  let clicks=0;
  const api={now:()=>1000,checkStop(){},requireInputReady(){},reconnectGame(){clicks++;}};
  api[guard]=()=>{throw Error('guard');};
  await assert.rejects(context.ActOneMission.runQuestStep('reconnectGame',sample(),api,async()=>{}),/guard/);
  assert.equal(clicks,0);
 }
});
