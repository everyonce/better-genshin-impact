(function(root){
 'use strict';
 function ready(o,now,session){
  const h=o&&o.hud,m=o&&o.map,ids=(o&&o.ocr||[]).filter(r=>r.x>1600&&r.y>1030&&/^(?:UID)?[: ]*\d{9}$/.test(String(r.text).trim()));
  return !!(o&&o.session===session&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&m.map==='Teyvat'&&Math.hypot(m.x+831.36,m.y-2189.45)<8&&h&&h.world&&h.groundControls&&!h.climbing&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.bigMap&&!h.journal&&h.health&&h.health.current===2313&&h.health.max===2313&&h.enemyBarDiagnostic&&Array.isArray(h.enemyBars)&&!h.enemyBars.length&&!(h.objectives||[]).length&&ids.length&&ids.every(r=>/693306810$/.test(String(r.text).trim())));
 }
 root.ActTwoClock={ready};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoClock;
})(typeof globalThis!=='undefined'?globalThis:this);
