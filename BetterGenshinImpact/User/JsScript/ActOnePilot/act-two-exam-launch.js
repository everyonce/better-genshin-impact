(function(root){
 'use strict';
 async function run(api,stationary){
  const began=api.now(),r={jumpPresses:0,deployPresses:0,opened:false,samples:[]};
  try{
   api.check();if(!stationary)api.forwardDown();
   await api.pressSpace();r.jumpPresses++;await api.sleep(stationary?300:550);
   api.check();if(api.now()-began>900)throw Error('Takeoff timing exceeded before deployment');
   await api.pressSpace();r.deployPresses++;await api.sleep(100);
   for(let i=0;i<3;i++){
    api.check();const s=await api.sample();r.samples.push(s);
    if(!s||!s.valid)break;
    if(s.space){r.opened=true;break;}
    await api.sleep(80);
   }
  }catch(e){r.reason=String(e.message||e);}
  finally{api.release();r.elapsedMs=api.now()-began;}
  // Unknown deployment must pause immediately, before full-frame OCR or PNG I/O.
  if(!r.opened){api.check();await api.pause();r.quickPause=true;}
  return r;
 }
 async function recover(api){
  const began=api.now(),r={deployPresses:0,opened:false,samples:[]};
  try{
   api.check();let before=await api.sample();r.samples.push(before);
   for(let fade=0;fade<2&&before&&before.valid&&!before.space&&!before.groundControls&&!before.climbing;fade++){
    await api.sleep(100);api.check();before=await api.sample();r.samples.push(before);
   }
   if(before&&before.valid&&before.space)r.opened=true;
   else if(before&&before.valid&&before.groundControls&&!before.climbing){
    api.check();await api.pressSpace();r.deployPresses=1;await api.sleep(100);
    api.check();const after=await api.sample();r.samples.push(after);r.opened=!!(after&&after.valid&&after.space);
   }
  }catch(e){r.reason=String(e.message||e);}
  finally{api.release();r.elapsedMs=api.now()-began;}
  if(!r.opened){api.check();await api.pause();r.quickPause=true;}
  return r;
 }
 async function fly(api,duration){
  if(!Number.isInteger(duration)||duration<600||duration>2400)throw Error('Flight duration bound');
  const began=api.now(),r={opened:true,samples:[],flightMs:0};
  try{api.check();api.forwardDown();while(api.now()-began<duration){await api.sleep(Math.min(200,duration-(api.now()-began)));api.check();const s=await api.sample();r.samples.push(s);if(!s||!s.valid||!s.space){r.opened=false;break;}}}
  catch(e){r.opened=false;r.reason=String(e.message||e);}
  finally{api.release();r.flightMs=api.now()-began;}
  if(!r.opened){api.check();await api.pause();r.quickPause=true;}
  return r;
 }
 async function course(api){
  const began=api.now(),r={samples:[],moves:0,passageCandidate:false,reason:'Course deadline'};let firstDistance=null,nearest=Infinity,forward=false;
  try{
   for(let i=0;i<12&&api.now()-began<8000;i++){
    api.check();const s=await api.sample();r.samples.push(s);
    if(!s||!s.valid||!s.space||!s.health||s.health.max!==4015||s.health.current<4015*.9||s.health.current>4015){r.reason='Flight or health proof lost';break;}
    const m=s.marker,d=s.distance;
    if(!m||m.x<600||m.x>1320||m.y<220||m.y>780||!Number.isFinite(d)||d<0||d>100){r.reason='Target unavailable or outside flight corridor';break;}
    if(firstDistance===null)firstDistance=d;
    if(nearest<=6&&d>nearest+15){r.passageCandidate=true;r.reason='Near-target then distance transition; verify passage';break;}
    nearest=Math.min(nearest,d);
    if(r.moves>=4&&d>=firstDistance-2){r.reason='No measured approach after four steps';break;}
    if(Math.abs(m.x-960)>35){api.check();await api.look(Math.max(-60,Math.min(60,Math.round((m.x-960)*.35))),0);await api.sleep(100);continue;}
    api.check();if(!forward){api.forwardDown();forward=true;}await api.sleep(400);r.moves++;
   }
  }catch(e){r.reason=String(e.message||e);}
  finally{api.release();r.elapsedMs=api.now()-began;r.nearestDistance=Number.isFinite(nearest)?nearest:null;api.check();await api.pause();r.quickPause=true;}
  return r;
 }
 root.ActTwoExamLaunch={run,recover,fly,course};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoExamLaunch;
})(typeof globalThis!=='undefined'?globalThis:this);
