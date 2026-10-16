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
 async function course(api,initialLook){
  if(initialLook&&(!Number.isInteger(initialLook.dx)||Math.abs(initialLook.dx)>750||!Number.isInteger(initialLook.dy)||Math.abs(initialLook.dy)>500))throw Error('Course camera bound');
  const began=api.now(),r={samples:[],moves:0,passageCandidate:false,reason:'Course deadline'};let firstDistance=null,nearest=Infinity,forward=false,previous=null,previousAt=0,nearMissing=0,entryPolls=0;
  try{
   for(let i=0;i<12&&api.now()-began<8000;i++){
    api.check();const s=await api.sample();r.samples.push(s);
    if(s&&!s.valid&&!forward&&r.moves===0&&entryPolls<2){entryPolls++;await api.sleep(100);continue;}
    if(!s||!s.valid||!s.space||!s.health||s.health.max!==4015||s.health.current<4015*.9||s.health.current>4015){r.reason='Flight or health proof lost';break;}
    if(initialLook&&(initialLook.dx||initialLook.dy)){api.check();await api.look(initialLook.dx,initialLook.dy);initialLook=null;await api.sleep(180);continue;}
    const m=s.marker,d=s.distance;
    if((!m||!Number.isFinite(d))&&!forward&&r.moves===0&&entryPolls<2){entryPolls++;await api.sleep(100);continue;}
    if(nearest<=6&&m&&Number.isFinite(d)&&d>nearest+15){r.passageCandidate=true;r.reason='Near-target then distance transition; verify passage';break;}
    if(!Number.isFinite(d)&&nearMissing<2&&nearest<=10&&previous&&api.now()-previousAt<=1000){
     if(m&&Math.abs(m.x-960)<=45&&m.y>=220&&m.y<=780&&Math.hypot(m.x-previous.x,m.y-previous.y)<=120&&forward&&nearMissing===0){nearMissing++;r.nearReacquisition=true;await api.sleep(100);continue;}
     if(!m&&nearest<=6){api.release();forward=false;nearMissing++;r.nearReacquisition=true;await api.sleep(100);continue;}
    }
    if(!m||m.x<400||m.x>1520||m.y<220||m.y>780||!Number.isFinite(d)||d<0||d>100){r.reason='Target unavailable or outside flight corridor';break;}
    if(firstDistance===null)firstDistance=d;
    nearest=Math.min(nearest,d);previous=m;previousAt=api.now();
    if(r.moves>=4&&d>=firstDistance-2){r.reason='No measured approach after four steps';break;}
    if(Math.abs(m.x-960)>35){api.check();await api.look(Math.max(-60,Math.min(60,Math.round((m.x-960)*.35))),0);await api.sleep(100);continue;}
    api.check();if(!forward){api.forwardDown();forward=true;}await api.sleep(400);r.moves++;
   }
  }catch(e){r.reason=String(e.message||e);}
  finally{api.release();r.elapsedMs=api.now()-began;r.nearestDistance=Number.isFinite(nearest)?nearest:null;api.check();await api.pause();r.quickPause=true;}
  return r;
 }
 async function segment(api,p){
  if(!p||!Number.isInteger(p.holds)||p.holds<1||p.holds>4||!Number.isInteger(p.dx)||Math.abs(p.dx)>750||!Number.isInteger(p.dy)||Math.abs(p.dy)>500)throw Error('Reviewed flight segment bounds');
  const began=api.now(),r={samples:[],flightMs:0,moves:0,stationary:p.stationary===true};let moving=null;
  const valid=s=>s&&s.valid&&s.space&&s.health&&s.health.max===4015&&s.health.current>=4015*.9&&s.health.current<=4015;
  try{
   api.check();let s=await api.sample();r.samples.push(s);
   for(let i=0;i<2&&!valid(s);i++){await api.sleep(100);api.check();s=await api.sample();r.samples.push(s);}
   if(!valid(s))throw Error('Fresh flight health/account/objective proof required');
   if(p.dx||p.dy){api.check();await api.look(p.dx,p.dy);await api.sleep(180);api.check();s=await api.sample();r.samples.push(s);if(!valid(s))throw Error('Flight proof lost after camera correction');}
   moving=api.now();api.check();api.forwardDown();r.moves=p.stationary?0:1;
   while(api.now()-moving<p.holds*600&&api.now()-began<6000){await api.sleep(Math.min(150,p.holds*600-(api.now()-moving)));api.check();s=await api.sample();r.samples.push(s);if(!valid(s))throw Error('Flight or health proof lost');}
   r.flightMs=api.now()-moving;r.reason='Reviewed finite wind-ring acquisition ended; verify position and ascent';
  }catch(e){r.reason=String(e.message||e);}
  finally{api.release();if(moving!==null)r.flightMs=api.now()-moving;r.elapsedMs=api.now()-began;api.check();await api.pause();r.quickPause=true;}
  return r;
 }
 root.ActTwoExamLaunch={run,recover,fly,course,segment};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoExamLaunch;
})(typeof globalThis!=='undefined'?globalThis:this);
