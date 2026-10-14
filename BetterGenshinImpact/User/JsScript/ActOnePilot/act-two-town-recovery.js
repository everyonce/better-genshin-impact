(function(root){
 'use strict';
 function ready(o,now,session){
  const h=o&&o.hud,m=o&&o.map,hp=h&&h.health,rows=o&&o.ocr||[];
  const objective=(h&&h.objectives||[]).map(t=>String(t).replace(/\s/g,''));
  const witnessed=m&&m.map==='Teyvat'&&(
   Math.hypot(m.x+925.867,m.y-2217.009)<4&&objective.includes('TalktoWagnertheblacksmith')||
   Math.hypot(m.x+1128.578,m.y-2210.419)<2&&objective.includes('CollectthreeIronChunksandgivethemtoWagner'));
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&
   witnessed&&h&&h.climbing===true&&!h.dialogueReady&&!h.choice&&
   hp&&hp.max===1700&&hp.current>=1530&&!(h.enemyBars||[]).length&&
   rows.some(r=>r.text==='X'&&r.x>1550&&r.y>980)&&rows.some(r=>r.text==='Space'&&r.x>1650&&r.y>980));
 }
 root.ActTwoTownRecovery={ready};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoTownRecovery;
})(typeof globalThis!=='undefined'?globalThis:this);
