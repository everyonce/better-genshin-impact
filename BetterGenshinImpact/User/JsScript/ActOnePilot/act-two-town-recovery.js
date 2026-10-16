(function(root){
 'use strict';
 function ready(o,now,session){
  const h=o&&o.hud,m=o&&o.map,hp=h&&h.health,rows=o&&o.ocr||[];
  const objective=(h&&h.objectives||[]).map(t=>String(t).replace(/\s/g,''));
  const cathedralAmberDrop=m&&m.map==='Teyvat'&&Math.hypot(m.x+700.953125,m.y-2342.443359375)<2&&objective.includes('TalktoAmber')&&rows.some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(String(r.text).trim()));
  const cathedralDrop=m&&m.map==='Teyvat'&&[[-840.9844,2256.0557],[-847.2910,2267.1914],[-845.8223,2296.9619],[-838.0781,2319.6611],[-825.0898,2317.3877]].some(p=>Math.hypot(m.x-p[0],m.y-p[1])<2)&&objective.includes('GotothedoorofMondstadtCathedral')&&rows.some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(String(r.text).trim()));
  const amberStair=m&&m.map==='Teyvat'&&[[-809.506,2309.961],[-775.756,2293.423]].some(p=>Math.hypot(m.x-p[0],m.y-p[1])<2)&&objective.includes('TalktoAmber');
  const cyrusStair=m&&m.map==='Teyvat'&&Math.hypot(m.x+830.3945,m.y-2195.9316)<2&&objective.includes('TalktoCyrus');
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
   (witnessed||amberStair||cyrusStair||cathedralDrop||cathedralAmberDrop)&&h&&h.climbing===true&&!h.dialogueReady&&!h.choice&&
   hp&&((cathedralDrop||cathedralAmberDrop)?hp.max===4015&&hp.current>=4015*.9&&hp.current<=4015:cyrusStair?hp.max===2635&&hp.current===2635:amberStair?hp.max===2313&&hp.current===2313:hp.max===1700&&hp.current>=1530)&&!(h.enemyBars||[]).length&&
   rows.some(r=>r.text==='X'&&r.x>1550&&r.y>980)&&rows.some(r=>r.text==='Space'&&r.x>1650&&r.y>980));
 }
 function wallReady(o,now,session){
  const h=o&&o.hud,m=o&&o.map,hp=h&&h.health;
  // Recorded10091: low city retaining rail, with the paved landing visible above.
  const cathedralRail=!!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&m.map==='Teyvat'&&[[-864.4141,2259.3975],[-841.1699,2243.4766]].some(p=>Math.hypot(m.x-p[0],m.y-p[1])<3)&&m.cameraAngle>=169&&m.cameraAngle<=189&&h&&h.world&&h.climbing&&!h.groundControls&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.bigMap&&!h.journal&&hp&&hp.max===4015&&hp.current>=4015*.9&&hp.current<=4015&&h.enemyBarDiagnostic&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='GotothedoorofMondstadtCathedral')&&['X','Space'].every(t=>(o.ocr||[]).some(r=>r.text===t&&r.x>1550&&r.y>980))&&(o.ocr||[]).some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(String(r.text).trim())));
  if(cathedralRail)return true;
  const amberRail=m&&m.map==='Teyvat'&&[[-756.959,2273.944],[-727.434,2277.426],[-708.416,2286.529]].some(p=>Math.hypot(m.x-p[0],m.y-p[1])<5)&&h&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='TalktoAmber');
  const clueWall=!!(m&&[[-866.869,2247.621],[-852.076,2277.981],[-844.859,2202.299],[-846.299,2208.395],[-850.861,2221.586]].some(p=>Math.hypot(m.x-p[0],m.y-p[1])<3)&&h&&
   (h.objectives||[]).slice(0,2).join('').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s/g,'').replace('HQforlahint)','HQforahint)')==='Solvethemystery(GotoKaeyaattheKnightsofFavoniusHQforahint)');
  return !!(o&&o.session===session&&now>=o.timestamp&&now-o.timestamp<=1000&&h&&m&&m.map==='Teyvat'&&
   (amberRail||clueWall||[[-873.807,2270.801],[-847.871,2268.357],[-845.066,2276.975],[-814.559,2319.845],[-790.848,2290.881]].some(p=>Math.hypot(m.x-p[0],m.y-p[1])<5)&&
    (h.objectives||[]).some(t=>String(t).replace(/[^A-Za-z]/g,'')==='TalktoKaeya')||
    [[-864.371,2240.93],[-824.875,2198.704],[-807.387,2194.526]].some(p=>Math.hypot(m.x-p[0],m.y-p[1])<3)&&(h.objectives||[]).includes('Talk to Kaeya at the meeting spot')||
    [[-824.711,2211.251],[-792.623,2231.871]].some(p=>Math.hypot(m.x-p[0],m.y-p[1])<3)&&(h.objectives||[]).includes('Report to Kaeya'))&&h&&!h.dialogueReady&&!h.choice&&
   (h.climbing||h.groundControls)&&hp&&(amberRail?hp.max===2313&&hp.current===2313:hp.max===1700&&hp.current>=(clueWall?1190:1530))&&h.enemyBarDiagnostic&&!(h.enemyBars||[]).length);
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
