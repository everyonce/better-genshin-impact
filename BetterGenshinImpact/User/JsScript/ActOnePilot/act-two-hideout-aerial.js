(function(root){
 'use strict';
 function state(o,now,session,healthFloor=2488){
  const h=o&&o.hud,r=o&&o.ocr||[],hp=h&&h.health;
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&o.map===null&&h&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&!h.climbing&&!h.groundControls&&hp&&hp.max===2764&&hp.current>=healthFloor&&hp.current<=2764&&r.some(x=>x.text==='Lumina'&&x.x>1600&&x.y>380&&x.y<440)&&r.some(x=>/^UID:\s*693306810$/.test(x.text)&&x.x>1600&&x.y>1030)&&r.some(x=>x.text==='Space'&&x.x>1750&&x.y>1000)&&!r.some(x=>/Wind Currents|While gliding|Revive|Retry|Leave Domain/.test(x.text)));
 }
 function fieldFrame(o,session){return state(o,o&&o.timestamp,session,1)?o.frameId:null;}
 function plan(p,request,now){
  return !!(p&&p.reviewed===true&&p.session===request.session&&p.frameId===request.expectedFrameId&&!p.usedAt&&Number.isFinite(p.createdAt)&&now>=p.createdAt&&now-p.createdAt<=120000&&['inspect','move','drop','bomb'].includes(p.mode)&&Number.isInteger(p.ms)&&p.ms>=0&&p.ms<=800&&['VK_W','VK_A','VK_S','VK_D'].includes(p.key)&&Number.isInteger(p.dx)&&Math.abs(p.dx)<=500&&Number.isInteger(p.dy)&&Math.abs(p.dy)<=400&&(p.mode!=='bomb'||p.flightReviewed===true)&&(p.mode!=='drop'||p.edgeReviewed===true&&p.key==='VK_W'&&p.ms>=200&&p.ms<=600));
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
 async function run(p,api){
  const result={mode:p.mode,inputs:0,flightAssessment:'not-assessed',visibleWings:'not-assessed',ascent:'not-assessed',bombOutcome:'not-assessed'};
  try{
   api.check();if(p.dx||p.dy){await api.look(p.dx,p.dy);await api.sleep(180);result.inputs++;}
   if(p.mode==='move'){await api.key(p.key,p.ms);result.inputs++;}
   if(p.mode==='drop'){result.drop=await drop(p,api);result.inputs+=result.drop.deployPresses+1;}
   if(p.mode==='bomb'){await api.bomb();result.inputs++;}
   await api.sleep(120);
  }catch(e){if(e.dropResult)result.drop=e.dropResult;e.aerialResult=result;throw e;}finally{api.release();}
  return result;
 }
 root.ActTwoHideoutAerial={state,fieldFrame,plan,run,drop};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoHideoutAerial;
})(typeof globalThis!=='undefined'?globalThis:this);
