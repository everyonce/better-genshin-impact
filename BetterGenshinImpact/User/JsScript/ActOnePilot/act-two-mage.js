(function(root){
 'use strict';
 function preparation(o,now,session){
  const h=o&&o.hud,m=o&&o.map,hp=h&&h.health,rows=o&&o.ocr||[];
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&m.map==='Teyvat'&&Number.isFinite(m.x)&&Number.isFinite(m.y)&&Math.hypot(m.x+1570,m.y-2240)<65&&h&&h.world&&h.groundControls&&!h.climbing&&!h.dialogueReady&&!h.choice&&!h.bigMap&&!h.journal&&h.enemyBarDiagnostic&&Array.isArray(h.enemyBars)&&!h.enemyBars.length&&Array.isArray(h.objectives)&&!h.objectives.length&&hp&&hp.max===2313&&hp.current>=1967&&hp.current<=hp.max&&rows.filter(r=>r.text==='Amber'&&r.x>=1650&&r.x<=1800&&r.y>=330&&r.y<=400).length===1&&rows.filter(r=>r.text==='2'&&r.x>=1840&&r.x<=1900&&r.y>=330&&r.y<=400).length===1);
 }
 function burst(o,now,session){
  const h=o&&o.hud,m=o&&o.map,hp=h&&h.health,rows=o&&o.ocr||[];
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&m.map==='Teyvat'&&Math.hypot(m.x+1562.52,m.y-2233.04)<12&&h&&h.world&&h.groundControls&&!h.climbing&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&hp&&hp.max===1186&&hp.current>=712&&hp.current<=1186&&h.enemyBarDiagnostic&&h.enemyBarDiagnostic.level===13&&h.enemyBars&&h.enemyBars.length&&rows.some(r=>r.text==='Amber'&&r.x>=1650&&r.x<=1685&&r.y>=330&&r.y<=400));
 }
 function switchToKaeya(o,now,session){
  const h=o&&o.hud,m=o&&o.map,rows=o&&o.ocr||[];
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&m.map==='Teyvat'&&Math.hypot(m.x+1562.52,m.y-2233.04)<12&&h&&h.world&&h.groundControls&&!h.climbing&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&h.health&&h.health.max===1186&&h.health.current>0&&h.health.current<=1186&&rows.some(r=>r.text==='Amber'&&r.x>=1650&&r.x<=1685&&r.y>=330&&r.y<=400)&&rows.some(r=>r.text==='Kaeya'&&r.x>=1650&&r.x<=1780&&r.y>=430&&r.y<=480)&&rows.some(r=>r.text==='3'&&r.x>=1840&&r.x<=1900&&r.y>=430&&r.y<=480));
 }
 root.ActTwoMage={preparation,burst,switchToKaeya};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoMage;
})(typeof globalThis!=='undefined'?globalThis:this);


