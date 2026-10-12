const test=require('node:test');const assert=require('node:assert/strict');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const now=2000000,from='old-session',middle='earlier-resume',native='native-resume',to='script-restart',entryId='wolf-party',pauseId='old-pause';
const row=(text,x,y)=>({text,x,y,width:180,height:30});
function marker(p={}){return {fromSession:middle,toSession:native,priorEntryId:'resume-old',priorPauseId:'pause-old-mid',betterGiProcessId:40000,priorBetterGiProcessId:26568,rdpSessionId:7,gameProcessId:44796,verifiedAt:now-50,...p};}
function info(p={}){return {betterGiProcessId:40000,gameProcessId:44796,windowsSessionId:7,isRemoteDesktopSession:true,isForeground:true,isMinimized:false,...p};}
function screen(){return {timestamp:now-100,frameId:40,map:null,ocr:[row('Continue Challenge',790,410),row('Leave Domain?',800,650)],hud:{world:false,health:null,journal:false,bigMap:false,dialogueReady:false,choice:false,climbing:false}};}
function originalHistory(){return [
 {session:from,id:'wolf-start',mission:'questStep',status:'completed',timestamp:now-50000,details:{result:{step:'wolfStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[{type:'wolfDomainStart',label:'Deep Within the Temple of the Wolf',frameId:21,x:1731,y:1017,startedAt:now-50100}]}},
 {session:from,id:entryId,mission:'questStep',status:'completed',timestamp:now-49000,details:{result:{step:'wolfPartyStart'},inputEvents:[{type:'wolfPartyStart',frameId:22,x:1705,y:1019,startedAt:now-49050}]}},
 {session:from,id:pauseId,mission:'questStep',status:'stopped',timestamp:now-40000,details:{result:{step:'wolfPause'},inputEvents:[{type:'key',key:'VK_ESCAPE',startedAt:now-40100}]}}
];}
function priorTransition(){
 const proof={verified:true,fromSession:from,toSession:middle,priorEntryId:entryId,priorPauseId:pauseId,betterGiProcessId:26568,rdpSessionId:7,gameProcessId:44796,verifiedAt:now-30000};
 const resume={session:middle,id:'resume-old',mission:'questStep',status:'completed',timestamp:now-29000,details:{result:{step:'wolfResume',...proof},inputEvents:[{type:'wolfResumeProof',...proof,recordedAt:now-29900}]}};
 const pause={session:middle,id:'pause-old-mid',mission:'questStep',status:'completed',timestamp:now-1000,details:{result:{step:'wolfPause'},inputEvents:[{type:'key',key:'VK_ESCAPE',startedAt:now-900}]}};
 return {proof,resume,pause,history:[...originalHistory(),resume,pause]};
}

test('mission result preserves native PID bridge so the actual result and event establish entry',async()=>{
 const {history}=priorTransition(),proof=bgi.validateWolfResume(marker(),history,[],native,7,screen(),now,info());
 const result=await mission.runQuestStep('wolfResume',screen(),{checkStop(){},wolfResume(){return proof;}},async()=>{throw Error('resume cannot send input');});
 assert.equal(result.priorBetterGiProcessId,26568);
 const receipt={session:native,id:'native-mission-result',mission:'questStep',status:'completed',timestamp:now,details:{result,inputEvents:[{type:'wolfResumeProof',...proof,recordedAt:now}]}};
 assert.equal(bgi.wolfEntryProven([receipt],native),true);
});
test('native resume accepts an explicit prior BetterGI PID and binds it to recursive history',()=>{
 const {history}=priorTransition();
 assert.equal(bgi.wolfEntryProven(history,from),true,'fixture must establish original temple entry');
 const proof=bgi.validateWolfResume(marker(),history,[],native,7,screen(),now,info());
 assert.ok(proof,'explicit prior PID must validate');
 assert.equal(proof.verified,true);assert.equal(proof.betterGiProcessId,40000);assert.equal(proof.priorBetterGiProcessId,26568);
 const receipt={session:native,mission:'questStep',status:'completed',timestamp:now,details:{result:{step:'wolfResume',...proof},inputEvents:[{type:'wolfResumeProof',...proof,recordedAt:now}]}};
 assert.equal(bgi.wolfEntryProven([receipt],native),true);
 for(const bad of [undefined,0,-1,'26568',99999]){
  const e=marker();if(bad===undefined)delete e.priorBetterGiProcessId;else e.priorBetterGiProcessId=bad;
  assert.equal(bgi.validateWolfResume(e,history,[],native,7,screen(),now,info()),null,`reject prior PID ${String(bad)}`);
 }
 const forged=marker({priorBetterGiProcessId:99999});
 assert.equal(bgi.validateWolfResume(forged,history,[],native,7,screen(),now,info()),null,'a marker cannot relabel the historical resume PID');
 const mismatch={session:native,id:'resume-mismatch',mission:'questStep',status:'completed',timestamp:now,
  details:{result:{step:'wolfResume',...proof},inputEvents:[{type:'wolfResumeProof',...proof,priorBetterGiProcessId:99999,recordedAt:now}]}};
 assert.equal(bgi.wolfEntryProven([mismatch],native),false,'event and result prior PID must agree');
});
test('recursive proof requires the event and result prior PID to match exactly',()=>{
 const {history}=priorTransition();
 for(const mutate of [h=>h[3].details.result.priorBetterGiProcessId=26569,h=>h[3].details.inputEvents[0].priorBetterGiProcessId=26569]){
  const bad=history.map(r=>structuredClone(r));mutate(bad);
  assert.equal(bgi.validateWolfResume(marker(),bad,[],native,7,screen(),now,info()),null);
 }
});
test('a failed focus recovery after the pause is inert only with complete no-input evidence',()=>{
 const {history}=priorTransition();
 const failed={session:middle,id:'focus-failed',mission:'observe',status:'completed',timestamp:now-800,
  details:{result:null,inputEvents:[{type:'focusGameRecovery',resultingFocus:false,ready:false,startedAt:now-850,finishedAt:now-800,error:'Could not focus the bound game window. No scripted input was sent.'}]}};
 const clean=[...history,failed];
 assert.equal(bgi.validateWolfResume(marker(),clean,[],native,7,screen(),now,info()).verified,true);
 const bad=[];
 for(const change of [e=>delete e.finishedAt,e=>e.resultingFocus=true,e=>e.ready=true,e=>e.finishedAt=e.startedAt-1,
  e=>e.error='Error: Focus recovery failed.',e=>e.startedAt=undefined]){
  const rows=structuredClone(clean);change(rows[rows.length-1].details.inputEvents[0]);bad.push(rows);
 }
 const scripted=structuredClone(clean);scripted.push({session:middle,id:'late-key',mission:'questStep',status:'completed',timestamp:now-700,
  details:{result:{step:'wolfForward'},inputEvents:[{type:'key',key:'VK_W',startedAt:now-700}]}});bad.push(scripted);
 for(const rows of bad)assert.equal(bgi.validateWolfResume(marker(),rows,[],native,7,screen(),now,info()),null,JSON.stringify(rows.at(-1).details.inputEvents));
});
test('a later script-only restart keeps PID 40000 and traverses the earlier native PID bridge',()=>{
 const {history}=priorTransition();
 const nativeProof={verified:true,fromSession:middle,toSession:native,priorEntryId:'resume-old',priorPauseId:'pause-old-mid',betterGiProcessId:40000,priorBetterGiProcessId:26568,rdpSessionId:7,gameProcessId:44796,verifiedAt:now-500};
 const nativeReceipt={session:native,id:'resume-native',mission:'questStep',status:'completed',timestamp:now-400,details:{result:{step:'wolfResume',...nativeProof},inputEvents:[{type:'wolfResumeProof',...nativeProof,recordedAt:now-450}]}};
 const nativePause={session:native,id:'pause-native',mission:'questStep',status:'completed',timestamp:now-100,details:{result:{step:'wolfPause'},inputEvents:[{type:'key',key:'VK_ESCAPE',startedAt:now-90}]}};
 const all=[...history,nativeReceipt,nativePause];
 const later={fromSession:native,toSession:'after-script-restart',priorEntryId:'resume-native',priorPauseId:'pause-native',betterGiProcessId:40000,rdpSessionId:7,gameProcessId:44796,verifiedAt:now-50};
 const result=bgi.validateWolfResume(later,all,[],later.toSession,7,screen(),now,info());
 assert.equal(result.verified,true);assert.equal(result.betterGiProcessId,40000);assert.equal('priorBetterGiProcessId' in result,false);
 for(const [e,s,r,w] of [[later,later.toSession,8,info({windowsSessionId:8})],
  [later,later.toSession,7,info({gameProcessId:999})],
  [later,later.toSession,7,info({isRemoteDesktopSession:false})],
  [later,later.toSession,7,info({isForeground:false})],
  [{...later,fromSession:'wrong-session'},later.toSession,7,info()],
  [{...later,toSession:'wrong-session'},later.toSession,7,info()]])
  assert.equal(bgi.validateWolfResume(e,all,[],s,r,screen(),now,w),null);
});
