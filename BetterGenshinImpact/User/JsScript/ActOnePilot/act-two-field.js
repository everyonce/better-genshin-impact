(function(root){
 'use strict';
 function enemyLevel(p,r){return p&&r&&p.session===r.session&&p.frameId===r.expectedFrameId&&p.mode==='combat'&&[4,5,'any'].includes(p.enemyLevel||4)?p.enemyLevel||4:'any';}
 function combatTargets(o,p){
  const h=o&&o.hud,level=p.enemyLevel||4;
  if(!h||!h.enemyBarDiagnostic||h.enemyBarDiagnostic.level!==level||![4,5,'any'].includes(level))return [];
  return (h.enemyBars||[]).filter(b=>level!=='any'||Number.isFinite(b.rectangularity)&&b.rectangularity>=0.8&&b.rectangularity<=1.05&&b.width>=2&&b.width<=300&&b.height>=3&&b.height<=20&&b.x>=350&&b.x<=1600&&b.y>=100&&b.y<=900);
 }
 function interaction(o,name){
  if(!['Teleport Waypoint','Fowl',"Traveling Doctor's Handkerchief",'Common Chest','Exquisite Chest','Precious Chest','Firm Arrowhead','Damaged Mask','Slime Condensate','Wanderer\'s Advice','Adventurer\'s Experience','Adventurer\'s Tail Feather','Fine Enhancement Ore','Enhancement Ore','Traveling Doctor\'s Silver Lotus','Traveling Doctor\'s Owl Feather','Lucky Dog\'s Eagle Feather'].includes(name))return false;
  const rows=o&&o.ocr||[],f=rows.filter(r=>r.text==='F'&&r.x>=1080&&r.x<=1170&&r.y>=430&&r.y<=650),near=rows.filter(r=>r.x>=1150&&r.x<=1500&&r.y>=430&&r.y<=650);
  const text=r=>String(r.text).replace(/^\d{1,2}\s*/,''),labels=near.filter(r=>text(r)===name);
  for(const a of near)for(const b of near)if(a!==b&&text(a)+' '+text(b)===name&&Math.abs(a.x-b.x)<30&&b.y-a.y-a.height>=-8&&b.y-a.y-a.height<=15)labels.push({y:a.y,height:b.y+b.height-a.y});
  return f.length===1&&labels.length===1&&Math.abs(f[0].y+f[0].height/2-labels[0].y-labels[0].height/2)<25;
 }
 function plan(p,r,now){return !!(p&&p.reviewed===true&&!p.usedAt&&p.session===r.session&&p.frameId===r.expectedFrameId&&Number.isInteger(p.witnessFrameId)&&p.witnessFrameId<p.frameId&&Number.isFinite(p.createdAt)&&now>=p.createdAt&&now-p.createdAt<=120000&&['actions','combat','climb'].includes(p.mode)&&Array.isArray(p.actions)&&p.actions.length<=4&&(p.mode!=='climb'||p.actions.every(a=>a.type==='look'||a.type==='key'&&['VK_W','VK_A','VK_S','VK_D'].includes(a.key)&&a.ms<=600))&&p.actions.every(a=>a.type==='look'?Number.isInteger(a.dx)&&Math.abs(a.dx)<=750&&Number.isInteger(a.dy)&&Math.abs(a.dy)<=500:a.type==='key'&&['VK_W','VK_A','VK_S','VK_D','VK_SPACE','VK_F','VK_LBUTTON','VK_E'].includes(a.key)&&Number.isInteger(a.ms)&&a.ms>=30&&a.ms<=800&&(!['VK_SPACE','VK_F','VK_LBUTTON','VK_E'].includes(a.key)||a.ms===60)&&(!['VK_LBUTTON','VK_E'].includes(a.key)||a.target==='Breakable rocks'))&&p.actions.reduce((s,a)=>s+(a.ms||0),0)<=2400);}
 function cameraPlan(p){return !!(p&&p.mode==='actions'&&p.actions.length>0&&p.actions.every(a=>a.type==='look'));}
 function ready(o,w,now,session,climb,visualPositionReviewed,cameraOnly){
  const h=o&&o.hud,m=o&&o.map,hp=h&&h.health,wm=w&&w.map,ids=(o&&o.ocr||[]).filter(r=>r.x>1600&&r.y>1020&&/^(?:UID)?[: ]*\d{9}$/.test(String(r.text).trim()));
  const controls=h&&(climb?h.climbing&&(o.ocr||[]).some(r=>r.text==='X'&&r.x>1550&&r.y>980)&&(o.ocr||[]).some(r=>r.text==='Space'&&r.x>1650&&r.y>980):h.groundControls&&!h.climbing);
  const examField=(!climb||m&&Math.hypot(m.x+1342.426,m.y-1691.34)<=8&&hp&&hp.current===2313&&hp.max===2313)&&m&&m.x>=-1500&&m.x<=-1200&&m.y>=1600&&m.y<=1950&&h&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Gototheexampoint');
  const position=visualPositionReviewed===true
   ?w&&w.session===session&&Number.isFinite(w.timestamp)&&now>=w.timestamp&&now-w.timestamp<=600000&&wm&&wm.map==='Teyvat'&&wm.x>=-1600&&wm.x<=-700&&wm.y>=1700&&wm.y<=2700
   :wm&&m&&m.map==='Teyvat'&&wm.map==='Teyvat'&&m.x>=-1600&&m.x<=-700&&(m.y>=1700||examField)&&m.y<=2700&&Math.hypot(m.x-wm.x,m.y-wm.y)<=12;
  const cityCamera=cameraOnly===true&&!climb&&m&&m.x>=-900&&m.x<=-700&&m.y>=2200&&m.y<=2450&&h&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='TalktoAmber');
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&position&&h&&h.world&&controls&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.bigMap&&!h.journal&&hp&&[1700,1829,2313].includes(hp.max)&&hp.current>=hp.max*0.7&&hp.current<=hp.max&&h.enemyBarDiagnostic&&Array.isArray(h.enemyBars)&&(!climb||!h.enemyBars.length)&&(examField||cityCamera||!(h.objectives||[]).some(t=>String(t).replace(/[^A-Za-z]/g,'').length>5))&&ids.length>0&&ids.every(r=>/693306810$/.test(String(r.text).trim())));
 }
 async function run(initial,w,p,api,observe){
  let current=initial,lastSkill=-Infinity,empty=0;const began=api.now(),baseline=initial.hud.health.current,result={status:'stopped',actions:0,skills:0,attacks:0};
  function safe(){return ready(current,w,api.now(),initial.session,p.mode==='climb',p.visualPositionReviewed,cameraPlan(p))&&current.hud.health.max===initial.hud.health.max&&baseline-current.hud.health.current<=initial.hud.health.max*0.15;}
  try{
   for(const a of p.actions){
    const repeats=a.key==='VK_LBUTTON'&&a.target==='Breakable rocks'?3:1;
    for(let strike=0;strike<repeats;strike++){api.checkStop();if(!safe()||a.key==='VK_F'&&!interaction(current,a.target)||['VK_LBUTTON','VK_E'].includes(a.key)&&current.hud.enemyBars.length)throw new Error('Field action evidence changed');await api.action(a,current);result.actions++;if(repeats===3)result.obstacleStrikes=(result.obstacleStrikes||0)+1;await api.sleep(a.key==='VK_F'?600:200);}
    current=await observe();
   }
   if(p.mode==='combat')for(let cycle=0;cycle<12&&api.now()-began<20000;cycle++){
    api.checkStop();if(!safe()||![4,5,'any'].includes(p.enemyLevel||4)||current.hud.enemyBarDiagnostic.level!==(p.enemyLevel||4)){result.reason='Combat health, location or level evidence changed';break;}
    if(!combatTargets(current,p).length){if(++empty>=2){result.reason='No eligible enemy bars in two observations';break;}await api.sleep(200);current=await observe();continue;}empty=0;
    if(api.now()-lastSkill>=6500){await api.key('VK_E',60,current);lastSkill=api.now();result.skills++;await api.sleep(450);}
    else for(let hit=0;hit<3;hit++){if(!safe())break;await api.key('VK_LBUTTON',60,current);result.attacks++;await api.sleep(200);}
    current=await observe();
   }
   result.reason=result.reason||'Bounded field batch ended; inspect outcome';result.fieldFrameId=current.frameId;result.health=current.hud.health;return result;
  }catch(error){error.fieldResult=result;throw error;}finally{await api.release();}
 }
 root.ActTwoField={cameraPlan,plan,ready,run,interaction,enemyLevel,combatTargets};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoField;
})(typeof globalThis!=='undefined'?globalThis:this);
