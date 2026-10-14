(function(root){
 'use strict';
 function plan(p,request,now){
  return !!(p&&p.reviewed===true&&!p.usedAt&&p.session===request.session&&p.frameId===request.expectedFrameId&&Number.isInteger(p.witnessFrameId)&&p.witnessFrameId<p.frameId&&
   Number.isFinite(p.createdAt)&&now>=p.createdAt&&now-p.createdAt<=120000&&['base','climb'].includes(p.mode)&&Array.isArray(p.actions)&&p.actions.length>0&&p.actions.length<=4&&
   p.actions.every(a=>a.type==='look'?Number.isInteger(a.dx)&&Math.abs(a.dx)<=750&&Number.isInteger(a.dy)&&Math.abs(a.dy)<=500:
    a.type==='key'&&['VK_W','VK_A','VK_S','VK_D','VK_SPACE'].includes(a.key)&&Number.isInteger(a.ms)&&a.ms>=30&&a.ms<=800&&(a.key!=='VK_SPACE'||p.mode==='base'&&a.ms===60))&&
   p.actions.reduce((n,a)=>n+(a.ms||0),0)<=2400);
 }
 function field(o,w,now,session,mode){
  const h=o&&o.hud,m=o&&o.map,hp=h&&h.health,wm=w&&w.map;
  return !!(o&&o.session===session&&now>=o.timestamp&&now-o.timestamp<=1000&&wm&&m&&m.map==='Teyvat'&&wm.map==='Teyvat'&&Math.hypot(m.x-wm.x,m.y-wm.y)<=8&&
   Math.hypot(m.x+846,m.y-2214)<25&&h&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.bigMap&&!h.journal&&hp&&hp.max===1700&&hp.current===1700&&h.enemyBarDiagnostic&&!(h.enemyBars||[]).length&&
   (mode==='climb'?h.climbing:h.world&&h.groundControls&&!h.climbing)&&
   (h.objectives||[]).slice(0,2).join('').normalize('NFD').replace(/[^A-Za-z]/g,'')==='SolvethemysteryGotoKaeyaattheKnightsofFavoniusHQforahint');
 }
 root.ActTwoVisual={plan,field};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoVisual;
})(typeof globalThis!=='undefined'?globalThis:this);
