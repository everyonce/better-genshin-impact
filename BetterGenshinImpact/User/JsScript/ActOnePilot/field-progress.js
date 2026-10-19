(function(root){
 'use strict';
 const movement=p=>!!(p&&['actions','climb'].includes(p.mode)&&(p.actions||[]).some(a=>a.type==='key'&&['VK_W','VK_A','VK_S','VK_D'].includes(a.key)));
 const angle=(a,b)=>Number.isFinite(a)&&Number.isFinite(b)?Math.abs((a-b+540)%360-180):null;
 function snapshot(o){return {session:o.session,frameId:o.frameId,timestamp:o.timestamp,map:o.map,climbing:!!o.hud.climbing,ground:!!o.hud.groundControls,objectives:o.hud.objectives||[],image:o.screenshotPath};}
 function near(a,b){return a&&b&&a.map&&b.map&&a.map.map===b.map.map&&Math.hypot(a.map.x-b.map.x,a.map.y-b.map.y)<=3;}
 function groundStalled(e){
  if(!e.end||!e.start.map||!e.end.map||e.start.map.map!==e.end.map.map)return false;
  const ms=(e.actions||[]).filter(a=>a.type==='key'&&['VK_W','VK_A','VK_S','VK_D'].includes(a.key)).reduce((n,a)=>n+a.ms,0);
  const minimum=Math.max(1.25,Math.min(8,ms*.002));
  return Math.hypot(e.start.map.x-e.end.map.x,e.start.map.y-e.end.map.y)<minimum;
 }
 function elevation(a,b){
  const parse=s=>{const values=s.objectives.filter(t=>/^Higher \d+m$/.test(t.trim()));return values.length===1?Number(values[0].match(/\d+/)[0]):null;};
  const x=parse(a),y=parse(b),names=s=>s.objectives.filter(t=>!/^Higher \d+m$/.test(t.trim()));
  return x!==null&&y!==null&&x-y>=1&&JSON.stringify(names(a))===JSON.stringify(names(b))&&names(a).length>0;
 }
 function reviewedProgress(p,entry,w){
  const r=p.progressReview,a=entry.start,b=snapshot(w);
  if(!r||r.fromFrame!==a.frameId||r.toFrame!==b.frameId||typeof r.landmark!=='string'||r.landmark.trim().length<12)return false;
  let delta=angle(a.map&&a.map.cameraAngle,b.map&&b.map.cameraAngle);
  const c=r.cameraEvidence;
  if(delta===null&&c&&c.method==='native-GIA-saved-image'&&c.session===w.session&&Array.isArray(c.frames)&&c.frames.length===2&&c.frames[0].frame===a.frameId&&c.frames[1].frame===b.frameId&&c.frames.every(f=>Number.isFinite(f.angle)&&f.angle>=0&&f.angle<=360&&typeof f.sha256==='string'&&/^[a-f0-9]{64}$/i.test(f.sha256)))delta=angle(c.frames[0].angle,c.frames[1].angle);
  if(r.kind==='vertical-landmark')return delta!==null&&delta<=8&&Number.isFinite(r.beforeY)&&Number.isFinite(r.afterY)&&r.beforeY>=0&&r.beforeY<=1080&&r.afterY>=0&&r.afterY<=1080&&r.afterY-r.beforeY>=12&&r.cameraUnchanged===true;
  if(r.kind==='lateral-climb'){
   // A completed sideways-only batch may approach the same target without gaining height.
   // This does not authorize upward climbing, changed direction, or an uncertain prior batch.
   const side=actions=>Array.isArray(actions)&&actions.length>0&&actions.length<=4&&actions.every(v=>v.type==='key'&&['VK_A','VK_D'].includes(v.key)&&v.key===actions[0].key&&Number.isInteger(v.ms)&&v.ms>=30&&v.ms<=600);
   const distance=s=>{const rows=s.objectives.filter(t=>/^Lower \d+m$/.test(t.trim()));return rows.length===1?Number(rows[0].match(/\d+/)[0]):null;};
   const names=s=>s.objectives.filter(t=>!/^Lower \d+m$/.test(t.trim()));
   const before=distance(a),after=distance(b);
   return !!(entry.end&&entry.end.frameId<=b.frameId&&b.timestamp>=entry.end.timestamp&&b.timestamp-entry.end.timestamp<=600000&&distance(entry.end)===after&&entry.mode==='climb'&&p.mode==='climb'&&side(entry.actions)&&side(p.actions)&&entry.actions[0].key===p.actions[0].key&&a.climbing&&b.climbing&&!a.ground&&!b.ground&&before!==null&&after!==null&&before-after>=1&&before-after<=8&&JSON.stringify(names(a))===JSON.stringify(names(b))&&names(a).length===1&&names(a)[0]==="Enter Raptor's Hideout"&&delta!==null&&delta<=8&&r.visibleContinuousWall===true);
  }
  if(r.kind==='different-approach')return delta!==null&&r.visibleTraversableExit===true&&typeof r.description==='string'&&r.description.trim().length>=24&&delta>=30;
  return false;
 }
 function rejection(history,p,w){
  if(!movement(p))return null;
  if(p.mode==='climb'&&p.actions.some(a=>a.type==='key'&&a.key==='VK_W')&&(w.hud.objectives||[]).some(t=>String(t).replace(/\s/g,'')==="EnterRaptor'sHideout")&&(w.hud.objectives||[]).some(t=>/^Lower \d+m$/.test(t.trim())))return 'Hideout ascent passed entrance elevation; inspect landing or supported recovery';
  if(!history||history.version!==1||!Array.isArray(history.entries))return 'Progress history unavailable; inspect before movement';
  const b=snapshot(w);
  for(const e of history.entries.slice().reverse()){
   if(e.noMovementVerified===true&&e.actualMovementInputs===0&&e.movementEvidenceSource==='owned-controller-input-events')continue;
   if(e.start.session!==w.session||!near(e.end||e.start,b))continue;
   if(w.timestamp<e.start.timestamp)return 'Progress history is newer than witness';
   // A freshly observed mount is a new state after a completed ground batch.
   // Permit one600ms stamina-revealing probe; its climb entry then blocks repeats.
   const stamina=w.hud&&w.hud.climbStamina,mountDelta=angle(e.end&&e.end.map&&e.end.map.cameraAngle,b.map&&b.map.cameraAngle);
   if(e.mode==='actions'&&e.end&&e.end.ground&&!e.end.climbing&&p.mode==='climb'&&p.climbProbe===true&&p.actions.length===1&&p.actions[0].key==='VK_W'&&p.actions[0].ms===600&&b.climbing&&!b.ground&&w.hud.health&&w.hud.health.current===4015&&w.hud.health.max===4015&&stamina&&stamina.source==='same-frame-yellow-arc'&&stamina.pixels===null&&stamina.rawPixels===0&&b.timestamp>=e.end.timestamp&&b.timestamp-e.end.timestamp<=600000&&Number.isFinite(mountDelta)&&mountDelta<=8)return null;
   // A single600ms probe only reveals stamina. Allow one2-4-step measurement
   // batch, then require actual vertical evidence; its longer entry cannot repeat.
   if(e.mode==='climb'&&e.end&&e.end.frameId===b.frameId&&e.start.climbing&&e.end.climbing&&Array.isArray(e.actions)&&e.actions.length===1&&e.actions[0].key==='VK_W'&&e.actions[0].ms===600&&p.mode==='climb'&&p.climbProbe!==true&&p.actions.length>=2&&p.actions.length<=4&&p.actions.every(a=>a.type==='key'&&a.key==='VK_W'&&a.ms===600)&&b.climbing&&!b.ground&&w.hud.health&&w.hud.health.current===4015&&w.hud.health.max===4015&&stamina&&stamina.source==='same-frame-yellow-arc'&&Number.isFinite(stamina.pixels)&&stamina.pixels>=180&&stamina.boxes&&stamina.boxes.length&&Math.max(...stamina.boxes.map(v=>v.y+v.height))-Math.min(...stamina.boxes.map(v=>v.y))>=45&&Number.isFinite(mountDelta)&&mountDelta<=8)return null;
   if(e.mode==='climb'||p.mode==='climb'){
    // Horizontal position cannot establish vertical progress. Unknown is protective.
    if(elevation(e.start,b)||reviewedProgress(p,e,w))return null;
    return 'Climb progress unverified near recent attempt; require vertical landmark/elevation or reviewed different approach';
   }
   const d=angle(e.start.map&&e.start.map.cameraAngle,b.map&&b.map.cameraAngle);
   if((!e.end||groundStalled(e))&&(d===null||d<=15)&&!reviewedProgress(p,e,w))return 'Ground progress stalled near recent attempt; inspect a visible traversable exit';
  }
  return null;
 }
 function begin(history,p,w,id){if(!movement(p))return history;return {version:1,entries:history.entries.concat([{requestId:id,mode:p.mode,start:snapshot(w),end:null,actions:p.actions,progressReview:p.progressReview||null}]).slice(-16)};}
 function finish(history,id,o,events){const e=history.entries.find(v=>v.requestId===id);if(e&&o&&o.hud&&o.hud.world)e.end=snapshot(o);if(e&&o&&o.session===e.start.session&&o.frameId>=e.start.frameId&&o.timestamp>=e.start.timestamp&&Array.isArray(events)){e.actualMovementInputs=events.filter(v=>v&&v.type==='key'&&['VK_W','VK_A','VK_S','VK_D'].includes(v.key)).length;e.noMovementVerified=e.actualMovementInputs===0;e.movementEvidenceSource='owned-controller-input-events';}return history;}
 root.FieldProgress={movement,snapshot,elevation,rejection,begin,finish};if(typeof module!=='undefined'&&module.exports)module.exports=root.FieldProgress;
})(typeof globalThis!=='undefined'?globalThis:this);
