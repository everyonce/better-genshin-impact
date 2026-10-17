(function(root){
 'use strict';
 function timer(o){const r=(o&&o.ocr||[]).filter(r=>r.x>=850&&r.x<=1100&&r.y>=20&&r.y<=100&&/^\d{1,2}:\d{2}$/.test(r.text.trim()));return r.length===1?r[0].text.trim().split(':').reduce((a,b)=>a*60+Number(b),0):null;}
 function safe(o,now,session){const h=o&&o.hud,m=o&&o.map,hp=h&&h.health;return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1200&&m&&m.map==='Teyvat'&&Math.hypot(m.x+774,m.y-2242)<12&&h&&h.world&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.bigMap&&!h.journal&&hp&&hp.max===4015&&hp.current>=3614&&hp.current<=4015&&Array.isArray(h.enemyBars)&&!h.enemyBars.length&&(o.ocr||[]).some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(r.text)));}
 function resumePosition(m){return !!(m&&m.map==='Teyvat'&&(Math.hypot(m.x+777.990234375,m.y-2240.7216796875)<=.4||Math.hypot(m.x+777.41015625,m.y-2240.8388671875)<=.25||Math.hypot(m.x+777.384765625,m.y-2241.134765625)<=.2));}
 async function run(initial,api){
  const began=api.now(),session=initial.session,r={status:'stopped',questComplete:false,stages:[],wallJumps:0,climbHolds:0,courses:[]};let current=initial;
  const check=()=>{api.check();if(api.now()-began>55000)throw Error('Final trial local deadline');};
  async function observe(){check();current=await api.observe();return current;}
  function ground(){check();if(!safe(current,api.now(),session)||!current.hud.groundControls||current.hud.climbing)throw Error('Fresh healthy final-stage ground required');}
  function stage(name,seconds){r.stages.push({name,elapsedMs:api.now()-began,frameId:current.frameId,timer:seconds===undefined?timer(current):seconds,map:current.map});}
  try{
   if(!api.resume){
   ground();if(Math.hypot(current.map.x+772.97,current.map.y-2242.88)>0.65)throw Error('Final start is outside prepared geometry');stage('dialogueExit');
   for(let n=0;n<4&&timer(current)===null;n++){await api.sleep(150);await observe();ground();}
   if(timer(current)===null||timer(current)<45||timer(current)>60)throw Error('Early final-stage timer required');stage('timerReady');
   const dx=Math.round(((13-current.map.cameraAngle+540)%360-180)*10);if(Math.abs(dx)>750)throw Error('Start heading exceeds reviewed correction');
   if(dx){await api.look(dx,0);await api.sleep(180);await observe();ground();}
   for(let n=0;n<2;n++){
    ground();if(Math.hypot(current.map.x+775,current.map.y-2242)>4)throw Error('Parapet approach changed');
    await api.wallJump();r.wallJumps++;await api.sleep(200);await observe();
    if(current.hud.climbing)break;
   }
   if(!current.hud.climbing)throw Error('No positively observed parapet grip');stage('grip');
   for(let n=0;n<4&&current.hud.climbing;n++){
    check();if(!safe(current,api.now(),session)||Math.hypot(current.map.x+777,current.map.y-2242)>2)throw Error('Climb geometry or health changed');
    await api.key('VK_W',600);r.climbHolds++;await api.sleep(200);await observe();
   }
   ground();if(!r.climbHolds||(Math.hypot(current.map.x+777.04102,current.map.y-2241.99414)>0.8&&!resumePosition(current.map)))throw Error('Mantle did not reach proven takeoff clearance');stage('clearance');
   }else{ground();if(!resumePosition(current.map)||timer(current)<20||timer(current)>60)throw Error('Reviewed resume top and timer required');stage('resumeTop');}
   if(api.prepareOnly){r.reason='Prepared parapet; inspect standing or falling before launch';r.fieldFrameId=current.frameId;r.health=current.hud.health;return r;}
   const turn=Math.round(((10-current.map.cameraAngle+540)%360-180)*10);if(Math.abs(turn)>750)throw Error('Takeoff heading exceeds correction');
   await api.look(turn,300);await api.sleep(180);ground();
   if(resumePosition(current.map)&&Math.hypot(current.map.x+777.990234375,current.map.y-2240.7216796875)>.4){
    // One released-input step from the recorded adjacent parapet, never OCR-held forward.
    await api.key('VK_W',150);await api.sleep(180);await observe();ground();
    if(Math.hypot(current.map.x+777.990234375,current.map.y-2240.7216796875)>.4)throw Error('Short parapet step did not reach proven launch position');
    stage('resumeClearance');
   }
   if(api.stepOff){ground();if(Math.hypot(current.map.x+777.990234375,current.map.y-2240.9111328125)>.4)throw Error('Reviewed outer edge required');await api.key('VK_W',300);api.release();await api.sleep(150);r.stepOff=true;}
   r.deployment=await api.launch();const ds=(r.deployment.recovery||r.deployment).samples||[];stage('deployment',ds.length?ds[ds.length-1].timer:null);
   if(!r.deployment.opened)throw Error('Glider not positively verified; no course input');
   for(let n=0;n<5&&api.now()-began<52000;n++){
    check();const c=await api.course();r.courses.push(c);
    const first=(c.samples||[]).find(s=>s&&Number.isFinite(s.timer)),last=(c.samples||[]).slice(-1)[0];
    r.stages.push({name:'course'+(n+1),elapsedMs:api.now()-began,timer:first?first.timer:null,nearestDistance:c.nearestDistance,reason:c.reason});
    if(!r.offAxisTransition&&c.reason==='Target unavailable or outside flight corridor'&&c.nearestDistance<=10&&last&&last.valid&&last.space&&last.marker&&last.distance===null&&(last.marker.x<500||last.marker.x>1420)){
     r.offAxisTransition=true;continue;
    }
    if(c.reason==='Flight or health proof lost'){
     await observe();if(current.hud.dialogueReady||current.hud.choice||!timer(current)){r.reason='Final trial phase changed';break;}
     if(n===0&&safe(current,api.now(),session))throw Error('Unexpected ground after deployment');
     // One observation-only continuation accommodates the verified wind-ring control fade.
     if(r.transitionPoll)throw Error('Repeated missing flight controls');r.transitionPoll=true;await api.sleep(150);continue;
    }
    if(c.reason!=='Course deadline'&&!c.passageCandidate&&!c.nearReacquisition){r.reason=c.reason;break;}
   }
   await observe();stage('end');r.fieldFrameId=current.frameId;r.health=current.hud.health;r.reason=r.reason||'Bounded final trial local sequence ended';
  }catch(e){r.reason=String(e.message||e);}
  finally{api.release();r.elapsedMs=api.now()-began;}
  return r;
 }
 root.ActTwoFinalTrial={run,safe,timer,resumePosition};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoFinalTrial;
})(typeof globalThis!=='undefined'?globalThis:this);
