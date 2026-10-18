(function(root){
 'use strict';
 function state(o,now,session,healthFloor=2488){
  const h=o&&o.hud,r=o&&o.ocr||[],hp=h&&h.health;
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&o.map===null&&h&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&!h.climbing&&!h.groundControls&&hp&&hp.max===2764&&hp.current>=healthFloor&&hp.current<=2764&&r.some(x=>x.text==='Lumina'&&x.x>1600&&x.y>380&&x.y<440)&&r.some(x=>/^(?:UID)?[: ]*693306810$/.test(x.text)&&x.x>1600&&x.y>1030)&&!r.some(x=>x.x>1600&&x.y>1030&&/^(?:UID)?[: ]*\d{9}$/.test(x.text)&&!/693306810$/.test(x.text))&&r.some(x=>x.text==='Space'&&((x.x>1750&&x.x<1870)||(x.x>1650&&x.x<1750))&&x.y>1000&&x.y<1050)&&!r.some(x=>/Wind Currents|While gliding|Revive|Retry|Leave Domain/.test(x.text)));
 }
 function fieldFrame(o,session){return state(o,o&&o.timestamp,session,1)?o.frameId:null;}
 function plan(p,request,now){
  return !!(p&&(p.bombFollowup===undefined||bombFollowupPlan(p))&&p.reviewed===true&&p.session===request.session&&p.frameId===request.expectedFrameId&&!p.usedAt&&Number.isFinite(p.createdAt)&&now>=p.createdAt&&now-p.createdAt<=120000&&['inspect','move','drop','bomb','currentProbe','flightBomb'].includes(p.mode)&&(p.mode!=='flightBomb'||bombFollowupPlan(p)&&p.ms===0&&p.dx===0&&p.dy===0)&&Number.isInteger(p.ms)&&p.ms>=0&&p.ms<=800&&['VK_W','VK_A','VK_S','VK_D'].includes(p.key)&&Number.isInteger(p.dx)&&Math.abs(p.dx)<=500&&Number.isInteger(p.dy)&&Math.abs(p.dy)<=400&&(p.mode!=='currentProbe'||p.currentReviewed===true&&typeof p.currentLandmark==='string'&&p.currentLandmark.trim().length>=24&&p.ms===0&&p.dx===0&&p.dy===0)&&(p.mode!=='bomb'||p.flightReviewed===true)&&(p.mode!=='drop'||p.edgeReviewed===true&&p.key==='VK_W'&&p.ms>=200&&p.ms<=600));
 }
 async function drop(p,api){
  const r={deployPresses:0,samples:[],flightControlDetected:null};
  try{api.check();await api.key('VK_W',p.ms);api.release();await api.sleep(100);let sample=await api.sample();r.samples.push(sample);
   if(!sample||!sample.valid)throw Error('Unknown HUD after reviewed edge step');
   if(!sample.flying){await api.space();r.deployPresses=1;await api.sleep(180);sample=await api.sample();r.samples.push(sample);}
   r.flightControlDetected=sample&&sample.valid?sample.flying===true:null;r.reason=r.flightControlDetected?'Flight control detected; inspect actual wings':'No positive flight control after one deployment; no replay';
  }catch(e){e.dropResult=r;throw e;}finally{api.release();await api.pause();r.quickPause=true;}
  return r;
 }
 async function currentProbe(p,api){
  const now=api.now||Date.now,r={presses:0,samples:[],timeline:[],flightControlDetected:false,visibleWings:'requires-image-review',bombs:0};
  async function press(label){api.check();const e={label,startedAt:now()};r.timeline.push(e);await api.space();r.presses++;e.finishedAt=now();}
  try{
   api.check();const before=await api.sample();r.samples.push(before);
   if(!before||!before.valid||!before.jumping||before.flying)throw Error('Current probe requires fresh jump control before any Space');
   await press('jump');const released=now();await api.sleep(350);api.check();
   r.releaseToDeployMs=now()-released;
   if(r.releaseToDeployMs<300||r.releaseToDeployMs>550)throw Error('Deployment timing window missed; no second press');
   await press('deploy');await api.sleep(180);const after=await api.sample();r.samples.push(after);
   r.flightControlDetected=!!(after&&after.valid&&after.flying&&!after.jumping);
   r.reason=r.flightControlDetected?'Flight control detected; review visible wings before any bomb':'No positive flight control; do not repeat this current probe';
   if(p.bombFollowup===true){
    if(!r.flightControlDetected)throw Error('No flight; local bomb followup refused');
    r.bombSequence=await flightBomb(p,api);r.bombs=r.bombSequence.presses;
   }
  }catch(e){if(e.bombSequence)r.bombSequence=e.bombSequence;e.currentProbeResult=r;throw e;}finally{api.release();await api.pause();r.quickPause=true;}
  return r;
 }
 async function bomb(api){
  api.check();const before=await api.sample();
  if(!before||!before.valid||!before.flying||before.jumping)throw Error('Fresh positive flight control required before reviewed bomb');
  try{api.check();await api.key('VK_E',60);await api.sleep(350);return {key:'VK_E',presses:1,damage:'requires-image-review'};}finally{api.release();}
 }
 function bombFollowupPlan(p){
  return !!(p&&p.bombFollowup===true&&['currentProbe','flightBomb'].includes(p.mode)&&p.flightReviewed===true&&typeof p.bombTargetLandmark==='string'&&p.bombTargetLandmark.trim().length>=24&&Array.isArray(p.flightActions)&&p.flightActions.length<=3&&p.flightActions.every(a=>a&&['VK_W','VK_A','VK_S','VK_D'].includes(a.key)&&Number.isInteger(a.ms)&&a.ms>=0&&a.ms<=800)&&p.flightActions.reduce((n,a)=>n+a.ms,0)<=1600);
 }
 async function flightBomb(p,api){
  if(!bombFollowupPlan(p))throw Error('Reviewed bounded bomb followup required');
  const now=api.now||Date.now,began=now(),r={presses:0,movements:0,samples:[],damage:'requires-image-review',deadlineMs:5000};
  async function fresh(){api.check();if(now()-began>3500)throw Error('Bomb input deadline reached');const s=await api.sample();r.samples.push(s);if(!s||!s.valid||!s.flying||s.jumping)throw Error('Flight or health guard lost; no further input');if(now()-began>3500)throw Error('Bomb sample deadline reached');return s;}
  try{
   for(const a of p.flightActions){await fresh();await api.key(a.key,a.ms);api.release();r.movements++;await api.sleep(100);}
   await fresh();r.attack=await bomb(Object.assign({},api,{check:function(){api.check();if(now()-began>3500)throw Error('Bomb input deadline reached');}}));r.presses=1;await api.sleep(450);
   api.check();r.samples.push(await api.sample());r.elapsedMs=now()-began;r.reason='One local E action and immediate result captured; pause for evidence review';
   if(r.elapsedMs>5000)r.reason='Local deadline exceeded after result capture; no replay';
  }catch(e){r.elapsedMs=now()-began;r.reason=String(e.message||e);e.bombSequence=r;throw e;}finally{api.release();}
  return r;
 }
 async function run(p,api){
  const result={status:'stopped',mode:p.mode,inputs:0,flightAssessment:'not-assessed',visibleWings:'not-assessed',ascent:'not-assessed',bombOutcome:'not-assessed'};
  try{
   api.check();if(p.dx||p.dy){await api.look(p.dx,p.dy);await api.sleep(180);result.inputs++;}
   if(p.mode==='move'){await api.key(p.key,p.ms);result.inputs++;}
   if(p.mode==='drop'){result.drop=await drop(p,api);result.inputs+=result.drop.deployPresses+1;}
   if(p.mode==='currentProbe'){result.currentProbe=await currentProbe(p,api);result.inputs+=result.currentProbe.presses;}
   if(p.mode==='flightBomb'){try{result.bombSequence=await flightBomb(p,api);result.inputs+=result.bombSequence.movements+result.bombSequence.presses;}finally{api.release();await api.pause();result.quickPause=true;}}
   if(p.mode==='bomb'){await api.bomb();result.inputs++;}
   await api.sleep(120);
  }catch(e){if(e.bombSequence){result.bombSequence=e.bombSequence;result.inputs+=e.bombSequence.movements+e.bombSequence.presses;}if(e.dropResult)result.drop=e.dropResult;if(e.currentProbeResult)result.currentProbe=e.currentProbeResult;e.aerialResult=result;throw e;}finally{api.release();}
  return result;
 }
 root.ActTwoHideoutAerial={state,fieldFrame,plan,run,drop,currentProbe,bomb,bombFollowupPlan,flightBomb};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoHideoutAerial;
})(typeof globalThis!=='undefined'?globalThis:this);
