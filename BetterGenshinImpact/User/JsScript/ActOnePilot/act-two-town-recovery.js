(function(root){
 'use strict';
 function ready(o,now,session){
  const h=o&&o.hud,m=o&&o.map,hp=h&&h.health,rows=o&&o.ocr||[];
  const objective=(h&&h.objectives||[]).map(t=>String(t).replace(/\s/g,''));
  const witnessed=m&&m.map==='Teyvat'&&(
   Math.hypot(m.x+1123.299,m.y-2219.727)<2&&objective.includes('Meetwiththeinformantatthedesignatedlocation')||
   Math.hypot(m.x+925.867,m.y-2217.009)<4&&objective.includes('TalktoWagnertheblacksmith')||
   Math.hypot(m.x+915.793,m.y-2228.845)<2&&objective.includes('TalktoKaeya')||
   Math.hypot(m.x+922.104,m.y-2245.118)<2&&objective.includes('TalktoKaeya')||
   Math.hypot(m.x+906.555,m.y-2233.586)<2&&objective.includes('TalktoKaeya')||
   Math.hypot(m.x+842.186,m.y-2269.859)<2&&objective.includes('TalktoKaeya')||
   Math.hypot(m.x+866.867,m.y-2247.623)<2&&objective.includes('TalktoKaeyaatthemeetingspot')||
   Math.hypot(m.x+881.195,m.y-2241.363)<2&&objective.includes('TalktoKaeyaatthemeetingspot')||
   Math.hypot(m.x+1128.578,m.y-2210.419)<2&&objective.includes('CollectthreeIronChunksandgivethemtoWagner'));
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&
   witnessed&&h&&h.climbing===true&&!h.dialogueReady&&!h.choice&&
   hp&&hp.max===1700&&hp.current>=1530&&!(h.enemyBars||[]).length&&
   rows.some(r=>r.text==='X'&&r.x>1550&&r.y>980)&&rows.some(r=>r.text==='Space'&&r.x>1650&&r.y>980));
 }
 function wallReady(o,now,session){
  const h=o&&o.hud,m=o&&o.map,hp=h&&h.health;
  const clueWall=!!(m&&[[-866.869,2247.621],[-852.076,2277.981],[-844.859,2202.299],[-846.299,2208.395],[-850.861,2221.586]].some(p=>Math.hypot(m.x-p[0],m.y-p[1])<3)&&h&&
   (h.objectives||[]).slice(0,2).join('').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s/g,'').replace('HQforlahint)','HQforahint)')==='Solvethemystery(GotoKaeyaattheKnightsofFavoniusHQforahint)');
  return !!(o&&o.session===session&&now>=o.timestamp&&now-o.timestamp<=1000&&h&&m&&m.map==='Teyvat'&&
   (clueWall||[[-873.807,2270.801],[-847.871,2268.357],[-845.066,2276.975],[-814.559,2319.845],[-790.848,2290.881]].some(p=>Math.hypot(m.x-p[0],m.y-p[1])<5)&&
    (h.objectives||[]).some(t=>String(t).replace(/[^A-Za-z]/g,'')==='TalktoKaeya')||
    [[-864.371,2240.93],[-824.875,2198.704],[-807.387,2194.526]].some(p=>Math.hypot(m.x-p[0],m.y-p[1])<3)&&(h.objectives||[]).includes('Talk to Kaeya at the meeting spot')||
    [[-824.711,2211.251],[-792.623,2231.871]].some(p=>Math.hypot(m.x-p[0],m.y-p[1])<3)&&(h.objectives||[]).includes('Report to Kaeya'))&&h&&!h.dialogueReady&&!h.choice&&
   (h.climbing||h.groundControls)&&hp&&hp.max===1700&&hp.current>=(clueWall?1190:1530)&&h.enemyBarDiagnostic&&!(h.enemyBars||[]).length);
 }
 function railReady(o,now,session){
  const h=o&&o.hud,m=o&&o.map;
  const bench=!!(o&&o.session===session&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&m.map==='Teyvat'&&Math.hypot(m.x+844.18,m.y-2221.09)<1&&m.cameraAngle>=195&&m.cameraAngle<=210&&h&&h.groundControls&&!h.climbing&&!h.dialogueReady&&!h.choice&&h.health&&h.health.max===1700&&h.health.current===1700&&h.enemyBarDiagnostic&&!(h.enemyBars||[]).length&&
   (h.objectives||[]).slice(0,2).join('').replace(/\s/g,'')==='Solvethemystery(GotoKaeyaattheKnightsofFavoniusHQforahint)');
  const counter=!!(o&&o.session===session&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&m.map==='Teyvat'&&Math.hypot(m.x+886.68,m.y-2240.32)<2&&m.cameraAngle>=220&&m.cameraAngle<=245&&h&&h.groundControls&&!h.climbing&&!h.dialogueReady&&!h.choice&&h.health&&h.health.max===1700&&h.health.current>=1190&&h.enemyBarDiagnostic&&!(h.enemyBars||[]).length&&
   (h.objectives||[]).slice(0,2).join('').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s/g,'').replace('HQforlahint)','HQforahint)')==='Solvethemystery(GotoKaeyaattheKnightsofFavoniusHQforahint)'&&(o.ocr||[]).some(r=>r.text==='Cook'&&r.x>1150&&r.y>500&&r.y<600));
  const clueRail=!!(wallReady(o,now,session)&&h.groundControls&&!h.climbing&&[[-852.076,2277.981],[-850.678,2221.551]].some(p=>Math.hypot(m.x-p[0],m.y-p[1])<2)&&m.cameraAngle>=150&&m.cameraAngle<=180&&
   (h.objectives||[])[0]==='Solve the mystery (Go to Kaeya at the Knights of Favonius');
  return bench||counter||clueRail||!!(wallReady(o,now,session)&&o.hud.groundControls&&!o.hud.climbing&&
  Math.hypot(o.map.x+864.3,o.map.y-2240.82)<2&&o.map.cameraAngle>=170&&o.map.cameraAngle<=195&&
  (o.hud.objectives||[]).includes('Talk to Kaeya at the meeting spot'));}
 root.ActTwoTownRecovery={ready,wallReady,railReady};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoTownRecovery;
})(typeof globalThis!=='undefined'?globalThis:this);
