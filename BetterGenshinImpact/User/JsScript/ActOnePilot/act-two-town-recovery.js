(function(root){
 'use strict';
 function ready(o,now,session){
  const h=o&&o.hud,m=o&&o.map,hp=h&&h.health,rows=o&&o.ocr||[];
  const objective=(h&&h.objectives||[]).map(t=>String(t).replace(/\s/g,''));
  const witnessed=m&&m.map==='Teyvat'&&(
   Math.hypot(m.x+925.867,m.y-2217.009)<4&&objective.includes('TalktoWagnertheblacksmith')||
   Math.hypot(m.x+915.793,m.y-2228.845)<2&&objective.includes('TalktoKaeya')||
   Math.hypot(m.x+922.104,m.y-2245.118)<2&&objective.includes('TalktoKaeya')||
   Math.hypot(m.x+906.555,m.y-2233.586)<2&&objective.includes('TalktoKaeya')||
   Math.hypot(m.x+842.186,m.y-2269.859)<2&&objective.includes('TalktoKaeya')||
   Math.hypot(m.x+1128.578,m.y-2210.419)<2&&objective.includes('CollectthreeIronChunksandgivethemtoWagner'));
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&
   witnessed&&h&&h.climbing===true&&!h.dialogueReady&&!h.choice&&
   hp&&hp.max===1700&&hp.current>=1530&&!(h.enemyBars||[]).length&&
   rows.some(r=>r.text==='X'&&r.x>1550&&r.y>980)&&rows.some(r=>r.text==='Space'&&r.x>1650&&r.y>980));
 }
 function wallReady(o,now,session){
  const h=o&&o.hud,m=o&&o.map,hp=h&&h.health;
  return !!(o&&o.session===session&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&m.map==='Teyvat'&&
   (Math.hypot(m.x+873.807,m.y-2270.801)<5||Math.hypot(m.x+847.871,m.y-2268.357)<5)&&h&&!h.dialogueReady&&!h.choice&&
   (h.climbing||h.groundControls)&&hp&&hp.max===1700&&hp.current>=1530&&h.enemyBarDiagnostic&&!(h.enemyBars||[]).length&&
   (h.objectives||[]).some(t=>String(t).replace(/[^A-Za-z]/g,'')==='TalktoKaeya'));
 }
 root.ActTwoTownRecovery={ready,wallReady};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoTownRecovery;
})(typeof globalThis!=='undefined'?globalThis:this);
