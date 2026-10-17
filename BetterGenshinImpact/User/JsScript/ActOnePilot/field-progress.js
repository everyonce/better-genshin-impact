(function(root){
 'use strict';
 const movement=p=>!!(p&&['actions','climb'].includes(p.mode)&&(p.actions||[]).some(a=>a.type==='key'&&['VK_W','VK_A','VK_S','VK_D'].includes(a.key)));
 const angle=(a,b)=>Number.isFinite(a)&&Number.isFinite(b)?Math.abs((a-b+540)%360-180):null;
 function snapshot(o){return {session:o.session,frameId:o.frameId,timestamp:o.timestamp,map:o.map,climbing:!!o.hud.climbing,ground:!!o.hud.groundControls,objectives:o.hud.objectives||[],image:o.screenshotPath};}
 function near(a,b){return a&&b&&a.map&&b.map&&a.map.map===b.map.map&&Math.hypot(a.map.x-b.map.x,a.map.y-b.map.y)<=3;}
 function elevation(a,b){
  const parse=s=>{const values=s.objectives.filter(t=>/^Higher \d+m$/.test(t.trim()));return values.length===1?Number(values[0].match(/\d+/)[0]):null;};
  const x=parse(a),y=parse(b),names=s=>s.objectives.filter(t=>!/^Higher \d+m$/.test(t.trim()));
  return x!==null&&y!==null&&x-y>=1&&JSON.stringify(names(a))===JSON.stringify(names(b))&&names(a).length>0;
 }
 function reviewedProgress(p,entry,w){
  const r=p.progressReview,a=entry.start,b=snapshot(w);
  if(!r||r.fromFrame!==a.frameId||r.toFrame!==b.frameId||typeof r.landmark!=='string'||r.landmark.trim().length<12)return false;
  if(r.kind==='vertical-landmark')return angle(a.map&&a.map.cameraAngle,b.map&&b.map.cameraAngle)!==null&&angle(a.map.cameraAngle,b.map.cameraAngle)<=8&&Number.isFinite(r.beforeY)&&Number.isFinite(r.afterY)&&r.beforeY>=0&&r.beforeY<=1080&&r.afterY>=0&&r.afterY<=1080&&r.afterY-r.beforeY>=12&&r.cameraUnchanged===true;
  if(r.kind==='different-approach')return r.visibleTraversableExit===true&&typeof r.description==='string'&&r.description.trim().length>=24&&angle(a.map&&a.map.cameraAngle,b.map&&b.map.cameraAngle)>=30;
  return false;
 }
 function rejection(history,p,w){
  if(!movement(p))return null;
  if(!history||history.version!==1||!Array.isArray(history.entries))return 'Progress history unavailable; inspect before movement';
  const b=snapshot(w);
  for(const e of history.entries.slice().reverse()){
   if(e.start.session!==w.session||!near(e.end||e.start,b))continue;
   if(w.timestamp<e.start.timestamp)return 'Progress history is newer than witness';
   if(e.mode==='climb'||p.mode==='climb'){
    // Horizontal position cannot establish vertical progress. Unknown is protective.
    if(elevation(e.start,b)||reviewedProgress(p,e,w))return null;
    return 'Climb progress unverified near recent attempt; require vertical landmark/elevation or reviewed different approach';
   }
   const d=angle(e.start.map&&e.start.map.cameraAngle,b.map&&b.map.cameraAngle);
   if(near(e.start,e.end||e.start)&&(d===null||d<=15)&&!reviewedProgress(p,e,w))return 'Ground progress stalled near recent attempt; inspect a visible traversable exit';
  }
  return null;
 }
 function begin(history,p,w,id){if(!movement(p))return history;return {version:1,entries:history.entries.concat([{requestId:id,mode:p.mode,start:snapshot(w),end:null,actions:p.actions,progressReview:p.progressReview||null}]).slice(-16)};}
 function finish(history,id,o){const e=history.entries.find(v=>v.requestId===id);if(e&&o&&o.hud&&o.hud.world)e.end=snapshot(o);return history;}
 root.FieldProgress={movement,snapshot,elevation,rejection,begin,finish};if(typeof module!=='undefined'&&module.exports)module.exports=root.FieldProgress;
})(typeof globalThis!=='undefined'?globalThis:this);
