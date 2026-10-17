(function(root){
 'use strict';
 // Fixed, previously exercised lower-wall phases only. No mount, release or ladder travel.
 const phases=[{"name":"middle-ascent","before":{"x":-843.115234375,"y":2209.794921875,"heading":322,"climbing":true,"height":23,"sourceFrame":19591,"minimumArcHeight":58},"after":{"x":-843.232421875,"y":2209.9150390625,"heading":316.5,"climbing":true,"height":20,"sourceFrame":19599},"mode":"climb","actions":[{"type":"key","key":"VK_W","ms":600},{"type":"key","key":"VK_W","ms":600},{"type":"key","key":"VK_W","ms":600},{"type":"key","key":"VK_W","ms":600}]},{"name":"upper-ascent","before":{"x":-843.232421875,"y":2209.9150390625,"heading":316.5,"climbing":true,"height":20,"sourceFrame":19599,"minimumArcHeight":56},"after":{"x":-843.19921875,"y":2209.88671875,"heading":315.5,"climbing":true,"height":17,"sourceFrame":19607},"mode":"climb","actions":[{"type":"key","key":"VK_W","ms":600},{"type":"key","key":"VK_W","ms":600},{"type":"key","key":"VK_W","ms":600},{"type":"key","key":"VK_W","ms":600}]},{"name":"support-approach","before":{"x":-843.19921875,"y":2209.88671875,"heading":315.5,"climbing":true,"height":17,"sourceFrame":19607,"minimumArcHeight":51},"after":{"x":-843.216796875,"y":2209.9091796875,"heading":315.5,"climbing":true,"height":14,"sourceFrame":19615},"mode":"climb","actions":[{"type":"key","key":"VK_W","ms":600},{"type":"key","key":"VK_W","ms":600},{"type":"key","key":"VK_W","ms":600},{"type":"look","dx":0,"dy":500}]},{"name":"support-rise","before":{"x":-843.216796875,"y":2209.9091796875,"heading":315.5,"climbing":true,"height":14,"sourceFrame":19615,"minimumArcHeight":46},"after":{"x":-843.22265625,"y":2209.916015625,"heading":315.5,"climbing":true,"height":14,"sourceFrame":19620},"mode":"climb","actions":[{"type":"key","key":"VK_W","ms":600}]},{"name":"support-sidestep","before":{"x":-843.22265625,"y":2209.916015625,"heading":315.5,"climbing":true,"height":14,"sourceFrame":19620,"minimumArcHeight":45},"after":{"x":-843.46875,"y":2209.6875,"heading":314,"climbing":true,"height":14,"sourceFrame":19625},"mode":"climb","actions":[{"type":"key","key":"VK_D","ms":600}]},{"name":"balcony-rise","before":{"x":-843.650390625,"y":2209.533203125,"heading":314,"climbing":true,"height":14,"sourceFrame":19636,"minimumArcHeight":43},"after":{"x":-843.65625,"y":2209.5380859375,"heading":291.5,"climbing":true,"height":12,"sourceFrame":19644},"mode":"climb","actions":[{"type":"key","key":"VK_W","ms":600},{"type":"key","key":"VK_W","ms":600},{"type":"key","key":"VK_W","ms":600},{"type":"key","key":"VK_W","ms":600}]},{"name":"balcony-align","before":{"x":-843.65625,"y":2209.5380859375,"heading":291.5,"climbing":true,"height":12,"sourceFrame":19644,"minimumArcHeight":37},"after":{"x":-843.466796875,"y":2209.8154296875,"heading":292,"climbing":true,"height":10,"sourceFrame":19651},"mode":"climb","actions":[{"type":"key","key":"VK_W","ms":600},{"type":"key","key":"VK_W","ms":600},{"type":"key","key":"VK_A","ms":600}]}];
 const deadlineMs=90000;
 const angle=(a,b)=>Math.abs((a-b+540)%360-180);
 function height(o){const t=(o&&o.hud&&o.hud.objectives||[]).map(v=>String(v).replace(/\s/g,'')).find(v=>/^Higher\d+m$/.test(v));return t?Number(t.match(/\d+/)[0]):null;}
 function arcHeight(o){const a=o&&o.hud&&o.hud.climbStamina,b=a&&a.boxes;if(!a||a.source!=='same-frame-yellow-arc'||!Number.isFinite(a.pixels)||a.pixels<180||!Array.isArray(b)||!b.length||!b.every(v=>[v.x,v.y,v.width,v.height].every(Number.isFinite)&&v.width>0&&v.height>0))return null;return Math.max(...b.map(v=>v.y+v.height))-Math.min(...b.map(v=>v.y));}
 function pose(o,e){const m=o&&o.map,h=height(o);return !!(m&&h!==null&&Number.isFinite(m.cameraAngle)&&Math.hypot(m.x-e.x,m.y-e.y)<=.75&&angle(m.cameraAngle,e.heading)<=15&&Math.abs(h-e.height)<=1);}
 function base(o,session,now){const h=o&&o.hud,m=o&&o.map,hp=h&&h.health;return !!(o&&o.session===session&&Number.isInteger(o.frameId)&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&m.map==='Teyvat'&&Number.isFinite(m.x)&&Number.isFinite(m.y)&&Math.hypot(m.x+843.2,m.y-2209.8)<=1.2&&h&&h.world===true&&h.climbing===true&&!h.groundControls&&!h.auto&&!h.choice&&!h.dialogueReady&&!h.bigMap&&!h.journal&&hp&&hp.current===4015&&hp.max===4015&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Lookforthelocationintheriddle')&&(o.ocr||[]).some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(String(r.text).trim())));}
 function entry(o,now,session){return base(o,session,now)&&pose(o,phases[0].before)&&arcHeight(o)>=phases[0].before.minimumArcHeight-2;}
 function plan(p,r,now){return !!(p&&r&&r.step==='actTwoLowerClimb'&&p.recipe==='lower-climb-seven-v1'&&p.reviewed===true&&!p.usedAt&&p.session===r.session&&p.frameId===r.expectedFrameId&&Number.isInteger(p.witnessFrameId)&&p.witnessFrameId<p.frameId&&Number.isFinite(p.createdAt)&&now>=p.createdAt&&now-p.createdAt<=120000&&Object.keys(p).every(k=>['recipe','reviewed','session','frameId','witnessFrameId','createdAt'].includes(k)));}
 async function run(initial,witness,api){
  let current=initial,rereads=0,phase=null,outcomeUnverified=false;const started=api.now(),session=initial.session;
  const result={status:'stopped',step:'actTwoLowerClimb',actions:0,attemptedActions:0,phases:[],timings:[],rereads:0,liveValidation:'pending'};
  function emit(reason,start,extra){const e=Object.assign({waitReason:reason,startedAt:start,finishedAt:api.now(),durationMs:api.now()-start,phase:phase&&phase.name,frameId:current&&current.frameId},extra||{});result.timings.push(e);if(api.event)api.event(e);}
  function check(){api.check();if(api.now()-started>=deadlineMs)throw Error('local_deadline');}
  function envelope(o){const h=height(o),m=o&&o.map,a=phase.before,b=phase.after;return h!==null&&h>=Math.min(a.height,b.height)-1&&h<=Math.max(a.height,b.height)+1&&m&&Math.min(Math.hypot(m.x-a.x,m.y-a.y),Math.hypot(m.x-b.x,m.y-b.y))<=.75&&Math.min(angle(m.cameraAngle,a.heading),angle(m.cameraAngle,b.heading))<=15;}
  async function observe(reason){check();const before=current,start=api.now();current=await api.observe();emit(reason,start);check();if(!current||current.session!==session||current.frameId<=before.frameId||current.timestamp<before.timestamp)throw Error('observation_continuity');}
  async function validate(expected,minArc){
   check();if(!base(current,session,api.now())||!envelope(current)||expected&&!pose(current,expected))throw Error('phase_or_field_guard');
   const a=current.hud.climbStamina;
   if(a&&a.source==='same-frame-yellow-arc'&&a.pixels===null&&Number.isFinite(a.rawPixels)&&a.rawPixels>=0&&rereads===0){
    const prior=current,start=api.now();rereads++;result.rereads=rereads;await api.release();await api.sleep(150);await observe('recognition_reread');emit('recognition_ambiguity',start);
    if(!base(current,session,api.now())||!envelope(current)||expected&&!pose(current,expected)||Math.hypot(current.map.x-prior.map.x,current.map.y-prior.map.y)>.25||angle(current.map.cameraAngle,prior.map.cameraAngle)>3||height(current)!==height(prior))throw Error('reread_continuity');
   }
   check();const measured=arcHeight(current);
   if(measured===null||minArc&&measured<minArc||!api.safe(current,witness))throw Error('stamina_or_field_guard');
  }
  try{
   if(!base(initial,session,api.now())||!pose(initial,phases[0].before))throw Error('lower_climb_entry_guard');
   for(const p of phases){
    phase=p;const phaseStart=api.now(),floor=p.before.minimumArcHeight-(p.before.minimumArcHeight>=47?2:0);
    await validate(p.before,floor);emit('local_phase_transition',phaseStart,{boundary:'start'});
    for(const action of p.actions){
     await validate(null,null);const before=current,inputStart=api.now();result.attemptedActions++;outcomeUnverified=true;
     try{await api.action(action,current);result.actions++;}finally{await api.release();}
     emit('input',inputStart,{action:action,sourceFrameId:before.frameId});
     const settle=api.now();await api.sleep(200);emit('input_settle',settle);await observe('recognition');await validate(null,null);outcomeUnverified=false;
    }
    await validate(p.after,null);result.phases.push({name:p.name,fieldFrameId:current.frameId,elapsedMs:api.now()-phaseStart});
   }
   result.reason='fresh_visual_landing_review_required';emit('visual_review_required',api.now());
  }catch(error){result.reason=String(error&&error.message||error);result.failureEvidence={frameId:current&&current.frameId,screenshotPath:current&&current.screenshotPath,map:current&&current.map,hud:current&&current.hud,uncertainAction:result.attemptedActions!==result.actions,outcomeUnverified:outcomeUnverified};emit('guard_failure',api.now(),{reason:result.reason});}
  finally{await api.release();result.fieldFrameId=current&&current.frameId;result.health=current&&current.hud&&current.hud.health;result.elapsedMs=api.now()-started;}
  return result;
 }
 root.ActTwoLowerClimb={entry,plan,run};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoLowerClimb;
})(typeof globalThis!=='undefined'?globalThis:this);
