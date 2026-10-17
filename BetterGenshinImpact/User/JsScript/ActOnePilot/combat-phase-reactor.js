(function(root){
'use strict';
function eligible(o,session,now){const h=o&&o.hud,hp=h&&h.health;return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&h&&h.world&&h.groundControls&&!h.climbing&&!h.bigMap&&!h.journal&&!h.auto&&!h.dialogueReady&&!h.choice&&hp&&hp.max===4015&&hp.current>=hp.max*.85&&hp.current<=hp.max&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Defeatallopponents6/7')&&(o.ocr||[]).some(r=>/693306810$/.test(r.text)&&r.x>1600&&r.y>1020));}
function sameTarget(before,after){
 const a=before&&before.hud&&before.hud.combatTargetState,b=after&&after.hud&&after.hud.combatTargetState;
 if(!a||!b||!a.target||!b.target||a.level!==13||b.level!==13||b.tracking==='ambiguous'||before.session!==after.session||after.frameId<=before.frameId||after.timestamp<before.timestamp||after.timestamp-before.timestamp>3500)return false;
 const ratio=b.target.width/a.target.width;
 // The final opponent is unique; require a fresh exact-level bar on every frame.
 // Permit measured zoom near a rock, never re-use a historical target as input evidence.
 return ratio>=.45&&ratio<=2.2&&Math.abs(b.target.x-a.target.x)<=800&&Math.abs(b.target.y-a.target.y)<=300;
}
async function run(initial,api){
 const start=api.now(),session=initial.session,result={status:'stopped',phaseReactor:true,skills:0,avoids:0,turns:0,frames:[],nativeMs:0,observationMs:0,avoidHoldMs:0,stationaryReads:0,reacquisitions:0,healthBefore:initial.hud.health};
 let current=initial,lastSkill=-Infinity,lastTracked=null,lastAction=null,absentReads=0,reacquireReads=0;
 async function observe(){await api.sleep(150);const t=api.now();current=await api.observe();result.observationMs+=api.now()-t;}
 try{for(let step=0;step<8&&api.now()-start<12000;step++){
  api.checkStop();if(!eligible(current,session,api.now())||!api.safe(current)){result.reason='phase_reactor_health_session_or_field_guard';break;}
  const state=current.hud.combatTargetState,target=state&&state.target;
  result.frames.push({frameId:current.frameId,phase:state&&state.phase||'unknown',tracking:state&&state.tracking||'missing',charge:state&&state.charge||'unknown',health:current.hud.health,target:target||null,shield:state&&state.shield||null});
  if(!target||state.level!==13){
   // One input-free reacquisition after our own camera turn. No blind movement.
   if(lastAction==='look'&&lastTracked&&state&&state.tracking==='missing'&&reacquireReads===0&&current.hud.health.current===lastTracked.hud.health.current){reacquireReads++;result.stationaryReads++;await observe();continue;}
   result.reason=state&&state.tracking==='ambiguous'?'phase_reactor_target_ambiguous':'phase_reactor_target_unknown';break;
  }
  if(lastTracked&&!sameTarget(lastTracked,current)){result.reason='phase_reactor_target_discontinuity';break;}
  if(lastAction==='look'&&lastTracked){
   result.reacquisitions++;
   if(Math.abs(target.x-960)>Math.abs(lastTracked.hud.combatTargetState.target.x-960)+150){result.reason='phase_reactor_camera_not_converging';break;}
  }
  lastTracked=current;lastAction=null;reacquireReads=0;
  if(Math.abs(target.x-960)>200){
   if(result.turns>=2){result.reason='phase_reactor_alignment_bound';break;}
   await api.look(current,Math.round(Math.max(-250,Math.min(250,(target.x-960)*.65))));result.turns++;lastAction='look';
  }else if(state.phase==='charging-shield'&&target.width>=55&&api.now()-lastSkill>=6500){
   if(result.skills>=2){result.reason='phase_reactor_reaction_bound';break;}
   lastSkill=api.now();const out=await api.cast(current);result.skills++;result.nativeMs+=out.nativeMs||0;
   if(out.nativeReturned!==true){result.reason='phase_reactor_native_return_unconfirmed';break;}
   lastAction='cast';absentReads=0;
  }else{
   // A tracked target with no charge is not permission to strafe or attack.
   if(state.charge==='ambiguous'){result.reason='phase_reactor_charge_ambiguous';break;}
   if(absentReads>=2||current.hud.health.current<initial.hud.health.current){result.reason='phase_reactor_no_charge_observed';break;}
   absentReads++;result.stationaryReads++;lastAction='observe';
  }
  await observe();
 }
 result.fieldFrameId=current.frameId;result.health=current.hud&&current.hud.health;result.reason=result.reason||'phase_reactor_time_or_observation_bound';result.elapsedMs=api.now()-start;result.defeatConfirmed=false;return result;
 }finally{api.release();}
}
const api={eligible,sameTarget,run};root.CombatPhaseReactor=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
