const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const now=2000000,from='mv43445y-sx3ltha70de',to='new-session',entryId='6f2273a130ac4dbe82197265564af55e',startId='061794e0948e4ad8a3187b11aa55e934',pauseId='45cc290bef76424cbd705d6acbe994b1';
const row=(text,x,y,width=180,height=30)=>({text,x,y,width,height});
function marker(p={}){return {fromSession:from,toSession:to,priorEntryId:entryId,priorPauseId:pauseId,betterGiProcessId:26568,rdpSessionId:7,gameProcessId:44796,verifiedAt:now-50,...p};}
function info(p={}){return {betterGiProcessId:26568,gameProcessId:44796,windowsSessionId:7,isRemoteDesktopSession:true,isForeground:true,isMinimized:false,...p};}
function pauseScreen(p={}){return {timestamp:now-100,frameId:40,map:null,ocr:[row('Continue Challenge',790,410),row('Leave Domain?',800,650)],hud:{world:false,health:null,journal:false,bigMap:false,dialogueReady:false,choice:false,climbing:false,...p}};}
function receipts(p=[]){
 const start={session:from,id:startId,mission:'questStep',status:'completed',timestamp:now-10800100,details:{result:{step:'wolfStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[{type:'wolfDomainStart',label:'Deep Within the Temple of the Wolf',startedAt:now-10800200}]}};
 const entry={session:from,id:entryId,mission:'questStep',status:'completed',timestamp:now-10800000,details:{result:{step:'wolfPartyStart'},inputEvents:[{type:'wolfPartyStart',frameId:22,x:1705,y:1019,startedAt:now-10800050}]}};
 const pause={session:from,id:pauseId,mission:'questStep',status:'stopped',timestamp:now-1000,details:{result:{step:'wolfPause',pauseVerified:false},inputEvents:[{type:'key',key:'VK_ESCAPE',startedAt:now-900}]}};
 return [start,entry,pause,...p];
}
test('real unlabeled Wolf party receipt is linked to the earlier exact Wolf entrance before accepting fresh resume',()=>{
 const proof=bgi.validateWolfResume(marker(),receipts(),[],to,7,pauseScreen(),now,info());
 assert.deepEqual(proof,{verified:true,fromSession:from,toSession:to,priorEntryId:entryId,priorPauseId:pauseId,betterGiProcessId:26568,rdpSessionId:7,gameProcessId:44796,verifiedAt:now-50});
 assert.equal(bgi.wolfEntryProven([{session:to,mission:'questStep',status:'completed',details:{result:{step:'wolfResume',...proof},inputEvents:[{type:'wolfResumeProof',...proof}]}}],to),true);
});
test('Wolf resume rejects wrong endpoints, processes, sessions, stale marker, reused proof, and non-pause/world screens',()=>{
 const prior=receipts();
 for(const [e,s,r,o,w] of [
  [marker({fromSession:'bad/../../path'}),to,7,pauseScreen(),info()],
  [marker({toSession:'elsewhere'}),to,7,pauseScreen(),info()],
  [marker({betterGiProcessId:999}),to,7,pauseScreen(),info()],
  [marker({gameProcessId:999}),to,7,pauseScreen(),info()],
  [marker({rdpSessionId:8}),to,7,pauseScreen(),info()],
  [marker({verifiedAt:now-30001}),to,7,pauseScreen(),info()],
  [marker(),from,7,pauseScreen(),info()],
  [marker(),to,6,pauseScreen(),info()],
  [marker(),to,7,{...pauseScreen(),timestamp:now-1001},info()],
  [marker(),to,7,pauseScreen({world:true}),info()],
  [marker(),to,7,{...pauseScreen(),ocr:[row('Continue Challenge',500,410),row('Leave Domain?',800,650)]},info()],
  [marker(),to,7,pauseScreen(),info({isForeground:false})],
  [marker(),to,7,pauseScreen(),info({isMinimized:true})],
 ])assert.equal(bgi.validateWolfResume(e,prior,[],s,r,o,now,w),null);
 assert.equal(bgi.validateWolfResume(marker(),prior,[{session:to,mission:'questStep',status:'completed',details:{result:{step:'wolfResume'},inputEvents:[{type:'wolfResumeProof'}]}}],to,7,pauseScreen(),now,info()),null);
});
test('Wolf resume rejects missing/tampered prior entry or pause proof and any later prior-session input',()=>{
 const good=receipts();
 const forgedEntry=structuredClone(good);forgedEntry[1].details.inputEvents=[];
 const forgedPause=structuredClone(good);forgedPause[2].details.inputEvents=[];
 const wrongTemple=structuredClone(good);wrongTemple[0].details.result.label='Deep Within the Temple of the Falcon';
 const laterStartInput={session:from,id:'intervening',mission:'questStep',status:'completed',details:{result:{step:'wolfLookRight'},inputEvents:[{type:'rotate',startedAt:now-10800100}]}};
 const lateAction={session:from,id:'later',mission:'questStep',status:'completed',details:{result:{step:'wolfContinue'},inputEvents:[{type:'wolfContinue',startedAt:now-800}]}};
 for(const prior of [good.slice(2),forgedEntry,forgedPause,wrongTemple,[good[0],{...good[1],details:{...good[1].details,inputEvents:[{type:'wolfPartyStart',frameId:22,x:1200,y:1019,startedAt:now-10800050}]}},good[2]],[...good,laterStartInput],[...good,lateAction]])assert.equal(bgi.validateWolfResume(marker(),prior,[],to,7,pauseScreen(),now,info()),null);
});
test('a verified prior Wolf resume is recursively tied to its original entry, pause, and same process identity',()=>{
 const middle='middle-session',first=receipts();
 first[2].timestamp=now-20000;first[2].details.inputEvents[0].startedAt=now-19900;
 const originalProof={verified:true,fromSession:from,toSession:middle,priorEntryId:entryId,priorPauseId:pauseId,
  betterGiProcessId:26568,rdpSessionId:7,gameProcessId:44796,verifiedAt:now-15000};
 const firstResume={session:middle,id:'resume-one',mission:'questStep',status:'completed',timestamp:now-9000,
  details:{result:{step:'wolfResume',...originalProof},inputEvents:[{type:'wolfResumeProof',...originalProof,recordedAt:now-14900}]}};
 const middlePause={session:middle,id:'pause-two',mission:'questStep',status:'completed',timestamp:now-1000,
  details:{result:{step:'wolfPause'},inputEvents:[{type:'key',key:'VK_ESCAPE',startedAt:now-900}]}};
 const multi=marker({fromSession:middle,priorEntryId:'resume-one',priorPauseId:'pause-two'});
 const history=[...first,firstResume,middlePause];
 assert.equal(bgi.validateWolfResume(multi,history,[],to,7,pauseScreen(),now,info()).verified,true);
 const wrongIdentity=structuredClone(history);wrongIdentity[3].details.result.gameProcessId=999;wrongIdentity[3].details.inputEvents[0].gameProcessId=999;
 assert.equal(bgi.validateWolfResume(multi,wrongIdentity,[],to,7,pauseScreen(),now,info()),null);
 const tamperedEvent=structuredClone(history);tamperedEvent[3].details.inputEvents[0].priorPauseId='forged-pause';
 assert.equal(bgi.validateWolfResume(multi,tamperedEvent,[],to,7,pauseScreen(),now,info()),null);
 assert.equal(bgi.validateWolfResume(multi,history.slice(3),[],to,7,pauseScreen(),now,info()),null,'the chain must reach the original exact temple entry');
});
test('actual-style JSONL started and terminal rows resolve each multihop receipt without dropping provenance rows',()=>{
 const middle='mv43vy9k-49h671h8wwj',oldPauseId='idle-safety-wolfPause-mv43445y-sx3ltha70de-1';
 const rootStartId='mission-061794e0948e4ad8a3187b11aa55e934',rootEntryId='mission-6f2273a130ac4dbe82197265564af55e';
 const resumeId='mission-73f850ffb2b9442db98e2ffedccff55c',currentPauseId='mission-faa1dba9823a4e50883ea82ad58da98a';
 function pair(session,id,mission,status,time,details){return [
  {session,id,mission,status:'started',timestamp:time-5,frameId:31,details:null},
  {session,id,mission,status,timestamp:time,frameId:32,details}
 ];}
 const start=pair(from,rootStartId,'questStep','completed',now-40000,{result:{step:'wolfStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[{type:'wolfDomainStart',label:'Deep Within the Temple of the Wolf',startedAt:now-40100}]});
 const party=pair(from,rootEntryId,'questStep','completed',now-35000,{result:{step:'wolfPartyStart'},inputEvents:[{type:'wolfPartyStart',frameId:22,x:1705,y:1019,startedAt:now-35100}]});
 const passive=[{session:from,id:'observe-revision',mission:'observe',status:'completed',timestamp:now-37000,frameId:23,details:{result:{},inputEvents:[{type:'observe',startedAt:now-39000},{type:'controllerRevision',startedAt:now-38000}]}}];
 const oldPause=pair(from,oldPauseId,'questStep','completed',now-30000,{result:{step:'wolfPause'},inputEvents:[{type:'key',key:'VK_ESCAPE',startedAt:now-29900}]});
 const priorProof={verified:true,fromSession:from,toSession:middle,priorEntryId:rootEntryId,priorPauseId:oldPauseId,
  betterGiProcessId:26568,rdpSessionId:7,gameProcessId:44796,verifiedAt:now-21000};
 const resume=pair(middle,resumeId,'questStep','completed',now-19500,{result:{step:'wolfResume',...priorProof},inputEvents:[{type:'wolfResumeProof',...priorProof,recordedAt:now-19800}]});
 const latestPause=pair(middle,currentPauseId,'questStep','completed',now-1000,{result:{step:'wolfPause'},inputEvents:[{type:'key',key:'VK_ESCAPE',startedAt:now-900}]});
 const marker2=marker({fromSession:middle,priorEntryId:resumeId,priorPauseId:currentPauseId});
 const realish=[...start,...party,...passive,...oldPause,...resume,...latestPause];
 const result=bgi.validateWolfResume(marker2,realish,[],to,7,pauseScreen(),now,info());
 assert.equal(result.verified,true);
 assert.equal(result.priorEntryId,resumeId);
 assert.equal(bgi.validateWolfResume(marker2,realish.concat([resume[1]]),[],to,7,pauseScreen(),now,info()),null,'duplicate terminal receipts remain ambiguous');
});
test('wolfResume mission reports provenance only and sends no input',async()=>{
 let calls=0;const proof={verified:true,fromSession:from,toSession:to,priorEntryId:entryId,priorPauseId:pauseId,betterGiProcessId:26568,rdpSessionId:7,gameProcessId:44796,verifiedAt:now-50};
 const result=await mission.runQuestStep('wolfResume',pauseScreen(),{checkStop(){calls++;},wolfResume(){calls++;return proof;}},async()=>{throw Error('resume must not observe or input');});
 assert.equal(result.status,'completed');assert.equal(result.step,'wolfResume');assert.equal(result.verified,true);assert.equal(calls,2);
});
test('live adapter validates marker and full JSONL histories, reads window identity, and emits proof without input',async()=>{
 const packageDir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot'),history=receipts();let clock=now;const inputs=[];
 const context={Date:class extends Date{static now(){return clock;}},genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0,GetGameWindowInfo:()=>JSON.stringify(info())},
 file:{isExists:p=>p==='wolf-resume.json'||p==='reports/'+from+'.jsonl'||p==='reports/new-session.jsonl',readTextSync:p=>p==='wolf-resume.json'?JSON.stringify(marker({verifiedAt:clock})):p==='reports/'+from+'.jsonl'?history.map(x=>JSON.stringify(x)).join('\n'):'',writeTextSync:()=>true,writeImageSync:()=>true},
 RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(){this.width=1920;this.height=1080;}findMulti(){const a=[row('Continue Challenge',790,410),row('Leave Domain?',800,650)].map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
 OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}}}},captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=[row('Continue Challenge',790,410),row('Leave Domain?',800,650)];a.count=a.length;return a;},deriveCrop:()=>({srcMat:{resize:()=>({})},dispose(){}}),dispose(){}}),
 sleep:async()=>{},click:()=>inputs.push('click'),keyDown:()=>inputs.push('down'),keyUp:()=>inputs.push('up'),moveMouseBy:()=>inputs.push('move'),log:{info(){}}};
 vm.runInNewContext(fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8'),context);const adapter=context.createActOneAdapter(7);
 adapter.beginMission({mission:'questStep',step:'wolfResume',session:to,createdAt:clock});const observation=await adapter.observe(to,41);const proof=adapter.wolfResume();
 assert.equal(observation.frameId,41);assert.equal(proof.verified,true);assert.deepEqual(inputs,[]);
 const event=adapter.events().find(e=>e.type==='wolfResumeProof');assert.equal(event.priorEntryId,entryId);assert.equal(event.gameProcessId,44796);assert.equal(event.verified,true);
 const report={session:to,mission:'questStep',status:'completed',details:{result:{step:'wolfResume',...proof},inputEvents:[event]}};assert.equal(bgi.wolfEntryProven([report],to),true);
});
