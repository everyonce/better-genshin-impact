(function(root){
 'use strict';
 function roadDefense(o,w,now,session){
  const h=o&&o.hud,p=h&&h.health,m=o&&o.map,k=w&&w.hud,wm=w&&w.map;
  return !!(o&&w&&o.session===session&&w.session===session&&now>=w.timestamp&&now-w.timestamp<=600000&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&wm&&m.map==='Teyvat'&&wm.map==='Teyvat'&&Math.hypot(wm.x+1409.45,wm.y-1587.87)<=2&&Math.hypot(m.x-wm.x,m.y-wm.y)<=8&&h&&k&&h.world&&h.groundControls&&!h.climbing&&p&&p.max===4015&&p.current>=p.max*.85&&k.health&&k.health.max===4015&&k.health.current>=4015*.85&&Array.isArray(k.enemyBars)&&k.enemyBars.length>=1&&k.enemyBars.length<=2&&k.enemyBars.every(b=>b.width>=20&&b.height>=8)&&Array.isArray(h.enemyBars)&&h.enemyBars.length<=2&&h.enemyBarDiagnostic&&h.enemyBarDiagnostic.level==='any'&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Lookforthelocationintheriddle')&&(k.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Lookforthelocationintheriddle'));
 }
 function cyrusObjective(o){const h=o&&o.hud,m=o&&o.map,rows=h&&h.objectives||[];return !!(m&&m.map==='Teyvat'&&Math.hypot(m.x+1220,m.y-2315)<=35&&rows.some(t=>String(t).replace(/\s/g,'')==='Defeattheattackingmonsters'))||rows.some(t=>/^Checkthesuspiciouslocation.{0,1}andeliminateanythre?a?ts/.test(String(t).normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^A-Za-z]/g,'')))||!!(m&&m.map==='Teyvat'&&Math.hypot(m.x+1125,m.y-2230)<=50&&rows.includes('Quest area reached')&&rows.some(t=>/^\([0-2]\/3\)$/.test(t)));}
 function failureReason(o,w,now,session){
  if(!o||o.session!==session)return 'session_mismatch';
  if(!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000)return 'stale_frame';
  const h=o.hud,hp=h&&h.health;
  if(h&&h.world&&hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max>0&&hp.current>=0&&hp.current<hp.max*0.7)return 'health_below_minimum';
  if(cyrusObjective(w)&&!cyrusObjective(o))return 'objective_mismatch';
  if(h&&h.world!==true)return 'field_world_not_verified';
  if(h&&leyLine(o)&&(h.objectives||[]).some(t=>/^Lv/.test(String(t))&&!leyLineEnemyLabel(o,t)))return 'field_level_label_missing_same_frame_bar_anchor';
  return 'field_guards_not_met';
 }
 function enemyLevel(p,r){return p&&r&&p.session===r.session&&p.frameId===r.expectedFrameId&&p.mode==='combat'&&[4,5,10,11,12,13,14,'any'].includes(p.enemyLevel||4)?p.enemyLevel||4:'any';}
 function combatTargets(o,p){
  const h=o&&o.hud,level=p.enemyLevel||4;
  if(!h||!h.enemyBarDiagnostic||h.enemyBarDiagnostic.level!==level||![4,5,10,11,12,13,14,'any'].includes(level))return [];
  const bars=(h.enemyBars||[]).filter(b=>level!=='any'||Number.isFinite(b.rectangularity)&&b.rectangularity>=0.8&&b.rectangularity<=1.05&&b.width>=2&&b.width<=300&&b.height>=3&&b.height<=20&&b.x>=350&&b.x<=1600&&b.y>=100&&b.y<=900);
  if(!bars.length&&level==='any'&&cyrusObjective(o))return(o.ocr||[]).filter(r=>/^Lv\.\s*12$/.test(String(r.text).trim())&&r.x>=350&&r.x<=1600&&r.y>=200&&r.y<=800);
  return bars;
 }
 function nativeHealth(avatar,max){return avatar==='Lumina'?[1363,2372,2451,2764].includes(max):[2635,4015].includes(max);}
 function switchReady(o,w,now,session,key){
  const h=o&&o.hud,hp=h&&h.health;
  return !!(o&&w&&o.session===session&&w.session===session&&now>=o.timestamp&&now-o.timestamp<=1000&&now>=w.timestamp&&now-w.timestamp<=600000&&(leyLine(w)||raptorAmbushObjective(w)||key==='VK_3'&&h&&w.hud&&(w.hud.objectives||[]).some(t=>t.replace(/\s/g,'')==="EnterRaptor'sHideout")&&(h.objectives||[]).some(t=>t.replace(/\s/g,'')==="EnterRaptor'sHideout")&&hp&&hp.current>=hp.max*.7&&Array.isArray(h.enemyBars)&&!h.enemyBars.length)&&h&&h.world&&h.groundControls&&!h.climbing&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.bigMap&&!h.journal&&hp&&(key==='VK_3'?[2372,2451,2764].includes(hp.max)&&hp.current>=hp.max*.7:[2635,4015].includes(hp.max)&&hp.current>=hp.max*.5)&&(o.ocr||[]).some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(r.text))&&(w.ocr||[]).some(r=>(key==='VK_3'?r.text==='Kaeya'&&r.x>1600&&r.y>=420&&r.y<=485:r.text==='Lumina'&&r.x>1650&&r.y>=240&&r.y<=300)));
 }
 function leyLineCount(o){const t=(o&&o.hud&&o.hud.objectives||[]).map(t=>String(t).replace(/\s/g,'')).find(t=>/^Defeatallopponents[0-7]\/7$/.test(t));return t?Number(t.match(/([0-7])\/7$/)[1]):null;}
 function leyLine(o){return !!o&&(o.hud&&o.hud.objectives||[]).some(t=>/^Defeatallopponents[0-6]\/7$/.test(String(t).replace(/\s/g,'')));}
 function leyLineEnemyLabel(o,text){
  if(!/^Lv[.,]?\s*13$/.test(String(text).trim())||!leyLine(o))return false;
  return (o.ocr||[]).some(r=>(r.text===text||/^Lv[.,]?$/.test(String(r.text).trim()))&&r.x>=350&&r.x<=1600&&r.y>=100&&r.y<=850&&r.width>=20&&r.width<=130&&r.height>=10&&r.height<=45&&(o.hud.enemyBars||[]).some(b=>Math.abs(b.x-r.x-r.width/2)<=35&&b.y-r.y-r.height>=-5&&b.y-r.y-r.height<=25&&b.width>=20&&b.width<=250&&b.height>=3&&b.height<=20));
 }
 function interaction(o,name){
  if(name==="Raptor's Hideout"&&!(o&&o.hud&&o.hud.objectives||[]).some(t=>String(t).replace(/\s/g,'')==="EnterRaptor'sHideout"))return false;
  if(['Broken-off Branch','Fabric Piece','Elemental Mark'].includes(name)&&!(o&&o.hud&&o.hud.objectives||[]).some(t=>/^LookforcluestotrackRaptor\([0-2]\/3\)$/.test(String(t).replace(/\s/g,''))))return false;
  if(!["Raptor's Hideout",'Broken-off Branch','Fabric Piece','Elemental Mark','Touch the Ley Line opening','Teleport Waypoint','Fowl',"Adventurer's Pocket Watch","Berserker's Timepiece",'Silver Sword',"Traveling Doctor's Handkerchief",'Common Chest','Exquisite Chest','Precious Chest','Firm Arrowhead','Damaged Mask','Slime Condensate','Wanderer\'s Advice','Adventurer\'s Experience','Adventurer\'s Tail Feather',"Traveling Doctor's Pocket Watch","Traveling Doctor's Medicine Pot",'Fine Enhancement Ore','Enhancement Ore','Traveling Doctor\'s Silver Lotus','Traveling Doctor\'s Owl Feather','Lucky Dog\'s Eagle Feather'].includes(name))return false;
  const rows=o&&o.ocr||[],f=rows.filter(r=>r.text==='F'&&r.x>=1080&&r.x<=1170&&r.y>=380&&r.y<=710),near=rows.filter(r=>r.x>=1150&&r.x<=1500&&r.y>=380&&r.y<=710);
  const text=r=>String(r.text).replace(/^\d{1,2}\s*/,''),labels=near.filter(r=>text(r)===name);
  for(const a of near)for(const b of near)if(a!==b&&text(a)+' '+text(b)===name&&Math.abs(a.x-b.x)<30&&b.y-a.y-a.height>=-8&&b.y-a.y-a.height<=15)labels.push({y:a.y,height:b.y+b.height-a.y});
  return f.length===1&&labels.length===1&&Math.abs(f[0].y+f[0].height/2-labels[0].y-labels[0].height/2)<25;
 }
 function diagnosticPlan(p){
  if(p.singleTargetDiagnostic===undefined)return true;
  const a=p.targetAnchor;
  return p.singleTargetDiagnostic===true&&p.mode==='combat'&&p.enemyLevel===4&&!p.regionMapFrameId&&!p.visualPositionReviewed&&Array.isArray(p.actions)&&p.actions.length===0&&a&&[a.x,a.y,a.width,a.height].every(Number.isFinite)&&a.x>=350&&a.x<=1600&&a.y>=100&&a.y<=900&&a.width>=2&&a.width<=300&&a.height>=3&&a.height<=20;
 }
 function eventReposition(p){return !!(p&&p.eventReposition===true&&p.regionMapFrameId&&p.mode==='actions'&&Array.isArray(p.actions)&&p.actions.length>0&&p.actions.length<=3&&p.actions.every(a=>a.type==='look'||a.type==='key'&&['VK_W','VK_A','VK_S','VK_D'].includes(a.key))&&p.actions.reduce((n,a)=>n+(a.ms||0),0)<=2000);}
 function raptorApproach(p){return p.raptorApproach===true&&p.mode==='combat'&&[13,'any'].includes(p.enemyLevel)&&p.regionMapFrameId&&Array.isArray(p.actions)&&p.actions.length>0&&p.actions.length<=3&&p.actions.every(a=>a.type==='look'&&Math.abs(a.dx)<=750&&Math.abs(a.dy)<=100||a.type==='key'&&a.key==='VK_W'&&a.ms<=600)&&p.actions.reduce((n,a)=>n+(a.ms||0),0)<=1200;}
 function thornHop(p){return !!(p&&p.thornHop===true&&p.mode==='actions'&&p.visualPositionReviewed===true&&p.regionMapFrameId&&Array.isArray(p.actions)&&p.actions.length===2&&p.actions[0].type==='key'&&p.actions[0].key==='VK_SPACE'&&p.actions[0].ms===60&&p.actions[0].target==='Reviewed low thorn barrier'&&p.actions[1].type==='key'&&p.actions[1].key==='VK_W'&&p.actions[1].ms===600);}
 function plan(p,r,now){if(p&&p.recoverySwitch===true)return !!(p.reviewed===true&&!p.usedAt&&p.session===r.session&&p.frameId===r.expectedFrameId&&p.witnessFrameId<p.frameId&&Number.isInteger(p.witnessFrameId)&&now>=p.createdAt&&now-p.createdAt<=120000&&p.mode==='actions'&&Array.isArray(p.actions)&&p.actions.length===1&&p.actions[0].type==='key'&&['VK_1','VK_3'].includes(p.actions[0].key)&&p.actions[0].ms===60);return !!(p&&(p.thornPyro===undefined||['inspect','fire'].includes(p.thornPyro)&&p.mode==='actions'&&p.visualPositionReviewed===true&&p.regionMapFrameId&&p.thornReviewed===true&&Array.isArray(p.actions)&&p.actions.length===0&&p.aimOffset&&Number.isInteger(p.aimOffset.dx)&&Math.abs(p.aimOffset.dx)<=200&&Number.isInteger(p.aimOffset.dy)&&Math.abs(p.aimOffset.dy)<=200)&&(p.thornHop===undefined||thornHop(p))&&(p.nativeSearch===undefined||p.nativeSearch===true&&p.nativeCombat===true&&p.enemyLevel===13)&&(p.nativeWindows===undefined||Number.isInteger(p.nativeWindows)&&p.nativeWindows>=1&&p.nativeWindows<=3&&p.nativeCombat===true&&p.enemyLevel===13)&&(p.convergingTravel===undefined||p.convergingTravel===true&&p.mode==='actions'&&p.regionMapFrameId&&Array.isArray(p.actions)&&p.actions.every(a=>a.type==='look'||a.type==='key'&&a.key==='VK_W'))&&(p.raptorPursuit===undefined||p.raptorPursuit===true&&p.mode==='combat'&&p.enemyLevel===13&&p.regionMapFrameId&&Array.isArray(p.actions)&&p.actions.length===0)&&(p.climbProbe===undefined||p.climbProbe===true&&p.mode==='climb'&&p.actions&&p.actions.length===1&&p.actions[0].type==='key'&&p.actions[0].key==='VK_W'&&p.actions[0].ms===600)&&(p.shieldProbe===undefined||p.shieldProbe===true&&p.shieldReviewed===true&&p.nativeCombat===true&&p.nativeAvatar==='Kaeya'&&p.enemyLevel===13)&&(p.phaseReact===undefined||p.phaseReact===true&&p.nativeCombat===true&&p.nativeAvatar==='Kaeya'&&p.enemyLevel===13&&!p.shieldProbe&&(!p.nativeWindows||p.nativeWindows===1))&&(p.shortCryo===undefined)&&(p.eventReposition===undefined||eventReposition(p))&&(p.nativeCombat===undefined||p.nativeCombat===true&&p.regionMapFrameId&&p.mode==='combat'&&[10,13].includes(p.enemyLevel)&&Array.isArray(p.actions)&&p.actions.length===0)&&diagnosticPlan(p)&&p.reviewed===true&&(p.raptorApproach===undefined||raptorApproach(p))&&(!p.regionMapFrameId||Number.isInteger(p.regionMapFrameId)&&p.regionMapFrameId<p.frameId&&p.visualPositionReviewed===true&&Array.isArray(p.actions)&&(p.mode==='loot'&&p.actions.length===0||p.mode==='combat'&&(([4,12,'any'].includes(p.enemyLevel)||p.enemyLevel===13&&(p.raptorApproach===true||p.raptorPursuit===true))||[10,13].includes(p.enemyLevel)&&p.nativeCombat===true)&&(p.actions.length===0||raptorApproach(p))||thornHop(p)||p.mode==='actions'&&p.actions.every(a=>a.type==='look'||a.type==='key'&&['VK_W','VK_A','VK_S','VK_D'].includes(a.key))||p.mode==='climb'&&p.actions.length<=4&&p.actions.every(a=>a.type==='key'&&['VK_W','VK_A','VK_D'].includes(a.key)&&a.ms<=600)||p.mode==='releaseClimb'&&p.landingReviewed===true&&p.actions.length===1&&p.actions[0].type==='key'&&p.actions[0].key==='VK_X'&&p.actions[0].ms===60||p.mode==='actions'&&p.actions.length===1&&p.actions[0].type==='key'&&p.actions[0].key==='VK_F'&&p.actions[0].ms===60&&["Raptor's Hideout",'Broken-off Branch','Fabric Piece','Elemental Mark','Teleport Waypoint','Touch the Ley Line opening'].includes(p.actions[0].target)))&&!p.usedAt&&p.session===r.session&&p.frameId===r.expectedFrameId&&Number.isInteger(p.witnessFrameId)&&p.witnessFrameId<p.frameId&&Number.isFinite(p.createdAt)&&now>=p.createdAt&&now-p.createdAt<=120000&&['actions','combat','climb','releaseClimb','loot'].includes(p.mode)&&Array.isArray(p.actions)&&p.actions.length<=(p.regionMapFrameId?8:4)&&(p.mode!=='loot'||p.actions.length===0)&&(p.mode!=='releaseClimb'||p.actions.length===1&&p.actions[0].type==='key'&&p.actions[0].key==='VK_X'&&p.actions[0].ms===60)&&(p.mode!=='climb'||p.actions.every(a=>a.type==='look'||a.type==='key'&&['VK_W','VK_A','VK_S','VK_D'].includes(a.key)&&a.ms<=600))&&p.actions.every(a=>a.type==='look'?Number.isInteger(a.dx)&&Math.abs(a.dx)<=750&&Number.isInteger(a.dy)&&Math.abs(a.dy)<=500:a.type==='key'&&['VK_W','VK_A','VK_S','VK_D','VK_SPACE','VK_F','VK_LBUTTON','VK_E','VK_X'].includes(a.key)&&(a.key!=='VK_X'||p.mode==='releaseClimb')&&Number.isInteger(a.ms)&&a.ms>=30&&a.ms<=800&&(!['VK_SPACE','VK_F','VK_LBUTTON','VK_E'].includes(a.key)||a.ms===60)&&(!['VK_LBUTTON','VK_E'].includes(a.key)||['Breakable rocks','Explosive Barrel'].includes(a.target)))&&p.actions.reduce((s,a)=>s+(a.ms||0),0)<=(p.regionMapFrameId?6400:2400));}
 function windmillField(o){const h=o&&o.hud,m=o&&o.map;return !!(h&&m&&m.map==='Teyvat'&&Math.hypot(m.x+845.67,m.y-2214)<=8&&(h.objectives||[]).some(t=>t.replace(/\s/g,'')==='Lookforthelocationintheriddle'));}
 function retiredWindmillCrossing(o,a){const m=o&&o.map;if(!windmillField(o)||!m||!o.hud.groundControls||o.hud.climbing||!Number.isFinite(m.cameraAngle)||!a||a.type!=='key')return false;return a.key==='VK_W'&&Math.hypot(m.x+846.298828125,m.y-2217.3564453125)<=2&&Math.abs((m.cameraAngle+180)%360-180)<=35||a.key==='VK_D'&&Math.hypot(m.x+847.677734375,m.y-2218.259765625)<=1&&Math.abs((m.cameraAngle-332+540)%360-180)<=15;}
 function windmillGroundStable(a,b){const h=a&&a.hud,k=b&&b.hud,m=a&&a.map,n=b&&b.map,dist=o=>{const t=(o.hud.objectives||[]).find(t=>/^Higher \d+m$/.test(t.trim()));return t?Number(t.match(/\d+/)[0]):null;};return !!(windmillField(a)&&windmillField(b)&&a.session===b.session&&b.frameId>a.frameId&&b.timestamp-a.timestamp>=700&&b.timestamp-a.timestamp<=3000&&h.world&&k.world&&h.groundControls&&k.groundControls&&!h.climbing&&!k.climbing&&h.health&&k.health&&h.health.max===4015&&k.health.max===4015&&h.health.current===4015&&k.health.current===4015&&Array.isArray(h.enemyBars)&&!h.enemyBars.length&&Array.isArray(k.enemyBars)&&!k.enemyBars.length&&Math.hypot(m.x-n.x,m.y-n.y)<=.5&&dist(a)!==null&&dist(b)!==null&&Math.abs(dist(a)-dist(b))<=1);}
 function originalWitnessFailure(w,p,r,now){
  if(!w)return 'missing_witness';
  if(w.session!==r.session)return 'witness_session_mismatch';
  if(w.frameId!==p.witnessFrameId||w.frameId>=p.frameId)return 'witness_frame_mismatch';
  if(!Number.isFinite(w.timestamp)||now<w.timestamp||now-w.timestamp>600000)return 'witness_not_recent';
  if(w.map&&Math.hypot(w.map.x+1421.293,w.map.y-1457.724)<=.75&&p.mode==='actions'&&!cameraPlan(p)&&!(p.actions.length===1&&p.actions[0].type==='key'&&p.actions[0].key==='VK_W'&&p.actions[0].ms===600))return 'waypoint_base_requires_one_mount';
  if(p.actions&&p.actions.some(a=>retiredWindmillCrossing(w,a)))return 'retired_windmill_ladder_crossing';
  const ok=p.recoverySwitch===true?switchReady(w,w,w.timestamp,r.session,p.actions[0].key):ready(w,w,w.timestamp,r.session,p.mode==='climb'||p.mode==='releaseClimb',!!p.regionWitness,cameraPlan(p),p.mode==='releaseClimb',p.regionWitness,true,(p.mode==='combat'&&[4,10,12,13,'any'].includes(p.enemyLevel)||eventReposition(p)&&leyLine(w)),p.climbProbe===true,p.landingReviewed===true);
  if(ok)return null;
  if(!w.hud||w.hud.world!==true)return 'witness_not_verified_world';
  if(!w.hud.health||w.hud.health.current<w.hud.health.max*.7)return 'witness_health_guard';
  return 'witness_field_conditions';
 }
 function cameraPlan(p){return !!(p&&p.mode==='actions'&&p.actions.length>0&&p.actions.every(a=>a.type==='look'));}
 function healthReread(o,w,p,now,session){
  const h=o&&o.hud,m=o&&o.map,wh=w&&w.hud,wm=w&&w.map;
  if(!cameraPlan(p)||!h||!h.groundControls||h.climbing||!wh||!wh.health||wh.health.current!==4015||wh.health.max!==4015||!h.health||h.health.max!==4015||failureReason(o,w,now,session)!=='health_below_minimum'||!m||!wm||Math.hypot(m.x+765.35,m.y-2262.39)>2||Math.hypot(m.x-wm.x,m.y-wm.y)>.5||!Array.isArray(h.enemyBars)||h.enemyBars.length)return false;
  // Only authorize a stationary measurement. The actual low observation remains unsafe.
  return ready(Object.assign({},o,{hud:Object.assign({},h,{health:wh.health})}),w,now,session,false,false,true);
 }
 function raptorFrozen(o){const r=o&&o.ocr||[];return raptorAmbushObjective(o)&&r.some(t=>t.text==='Frozen'&&t.x>=600&&t.x<=1200&&t.y>=250&&t.y<=650)&&r.some(t=>t.text==='Space'&&t.x>=1250&&t.x<=1550&&t.y>=450&&t.y<=750);}
 function raptorAmbushObjective(o){return (o&&o.hud&&o.hud.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Defeattheambush');}
 function raptorSoundObjective(o){const normalize=t=>String(t).replace(/\s/g,'').replace(/^Inyestigate/,'Investigate');return (o&&o.hud&&o.hud.objectives||[]).some(t=>normalize(t)==='Investigatethestrangesoundupahead')||(o&&o.ocr||[]).filter(r=>r.x>=50&&r.x<=600&&r.y>=240&&r.y<=350).sort((a,b)=>a.y-b.y).map(r=>normalize(r.text)).join('').includes('Investigatethestrangesoundupahead');}
 function raptorRegionalMap(o,now,session){
  if(!o||o.session!==session||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>600000||!o.hud||!o.hud.bigMap||o.hud.world)return false;
  const rows=o.ocr||[],deltas=[];
  for(const a of [['Mondstadt',858,189,135,28],['Whispering Woods',1066,151,229,29],['Windrise',1210,514,118,34]]){const found=rows.filter(q=>q.text.replace(/\s/g,'')===a[0].replace(/\s/g,''));if(found.length!==1||!Number.isFinite(found[0].width)||!Number.isFinite(found[0].height)||Math.abs(found[0].width-a[3])>12||Math.abs(found[0].height-a[4])>12)return false;deltas.push({x:found[0].x-a[1]+(found[0].width-a[3])/2,y:found[0].y-a[2]+(found[0].height-a[4])/2});}
  return deltas.every(d=>Math.abs(d.x)<=120&&Math.abs(d.y)<=120&&Math.abs(d.x-deltas[0].x)<=5&&Math.abs(d.y-deltas[0].y)<=5)&&rows.some(r=>r.x>1600&&r.y>1030&&/^(?:UID)?[: ]*693306810$/.test(r.text.trim()));
 }
 function blossomRoadMap(o,now,session){
  if(!o||o.session!==session||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>600000||!o.hud||!o.hud.bigMap||o.hud.world)return false;
  const rows=o.ocr||[],d=[];
  for(const a of [['Mondstadt',932,42,137,28],['Whispering Woods',1141,4,232,29],['Windrise',1288,369,115,29]]){const q=rows.filter(v=>v.text.replace(/\s/g,'')===a[0].replace(/\s/g,''));if(q.length!==1||![q[0].x,q[0].y,q[0].width,q[0].height].every(Number.isFinite)||Math.abs(q[0].width-a[3])>10||Math.abs(q[0].height-a[4])>8)return false;d.push({x:q[0].x+(q[0].width-a[3])/2-a[1],y:q[0].y+(q[0].height-a[4])/2-a[2]});}
  return d.every(v=>Math.abs(v.x)<=80&&Math.abs(v.y)<=40&&Math.abs(v.x-d[0].x)<=5&&Math.abs(v.y-d[0].y)<=5)&&rows.some(v=>v.x>1600&&v.y>1030&&/^(?:UID)?[: ]*693306810$/.test(v.text.trim()));
 }
 function regionalMap(o,now,session,maxAge){
  if(blossomRoadMap(o,now,session))return true;
  if(raptorRegionalMap(o,now,session))return true;
  if(!o||o.session!==session||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>(maxAge===1800000?1800000:600000)||!o.hud||!o.hud.bigMap||o.hud.world)return false;
  const rows=o.ocr||[],southern=rows.some(r=>r.text==='Falcon Coast');
  const roadScale=rows.some(r=>String(r.text).replace(/\s/g,'')==='WhisperingWoods'&&Math.abs(r.width-273)<=4);
  const wideRoad=rows.some(r=>String(r.text).replace(/\s/g,'')==='WhisperingWoods'&&Math.abs(r.width-225)<=6);
  const westRoad=!rows.some(r=>String(r.text).replace(/\s/g,'')==='WhisperingWoods')&&rows.some(r=>r.text==='Mondstadt'&&r.y<80);
  const centered=westRoad||wideRoad;
  const anchors=wideRoad?[['Mondstadt',1050,175,133,28],['Whispering Woods',1246,139,225,29],['Windrise',1385,484,112,29]]:westRoad?[['Mondstadt',917,21,167,40],['Windrise',1410,476,133,35],['Elemental Trial',1574,794,173,27]]:roadScale?[['Mondstadt',724,109,157],['Whispering Woods',1018,52,273],['Windrise',1210,558,133]]:southern?[['Windrise',937,444,139],['Thousand Winds',1394,89,239],['Falcon Coast',1522,674,194]]:[['Mondstadt',708,165,151],['Whispering Woods',964,115,251],['Windrise',1131,553,126]],deltas=[];
  for(const a of anchors){const found=rows.filter(r=>String(r.text).replace(/\s/g,'')===a[0].replace(/\s/g,''));if(found.length!==1||!Number.isFinite(found[0].width)||Math.abs(found[0].width-a[3])>(centered?12:6))return false;deltas.push({x:found[0].x-a[1]+(centered?(found[0].width-a[3])/2:0),y:found[0].y-a[2]+(centered?(found[0].height-a[4])/2:0)});}
  return deltas.every(d=>Number.isFinite(d.x)&&Number.isFinite(d.y)&&Math.abs(d.x)<=350&&Math.abs(d.y)<=250&&Math.abs(d.x-deltas[0].x)<=6&&Math.abs(d.y-deltas[0].y)<=8)&&rows.some(r=>r.x>1600&&r.y>1020&&/^(?:UID)?[: ]*693306810$/.test(String(r.text).trim()));
 }
 function ready(o,w,now,session,climb,visualPositionReviewed,cameraOnly,releaseClimb,regionWitness,witnessOnly,regionalCombat,climbProbe,landingReviewed){
  const h=o&&o.hud,m=o&&o.map,hp=h&&h.health,wm=w&&w.map,ids=(o&&o.ocr||[]).filter(r=>r.x>1600&&r.y>1020&&/^(?:UID)?[: ]*\d{9}$/.test(String(r.text).trim()));
  const cameraClimb=cameraOnly===true&&h&&h.climbing&&hp&&hp.current>=hp.max*.9&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0;
  const controls=h&&((climb||cameraClimb)?h.climbing&&(o.ocr||[]).some(r=>r.text==='X'&&r.x>1550&&r.y>980)&&(o.ocr||[]).some(r=>r.text==='Space'&&r.x>1650&&r.y>980):h.groundControls&&!h.climbing);
  const shelfClimb=climb===true&&m&&(Math.hypot(m.x+1328.140625,m.y-1670.00293)<=2&&h&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==="FollowAmber'sinstructionsandtaketheexamagain")||Math.hypot(m.x+1368.7461,m.y-1671.1387)<=6||Math.hypot(m.x+1341.7891,m.y-1680.3379)<=3||Math.hypot(m.x+1313.8145,m.y-1667.4736)<=6)&&hp&&hp.max===4015&&hp.current>=hp.max*.9&&h&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(climbProbe===true||h.climbStamina&&h.climbStamina.source==='same-frame-yellow-arc'&&Number.isFinite(h.climbStamina.pixels)&&h.climbStamina.pixels>=180&&h.climbStamina.boxes&&Math.max(...h.climbStamina.boxes.map(b=>b.y+b.height))-Math.min(...h.climbStamina.boxes.map(b=>b.y))>=45);
  const reviewedBaseRelease=releaseClimb===true&&climb&&landingReviewed===true&&m&&wm&&Math.hypot(m.x-wm.x,m.y-wm.y)<=2&&hp&&hp.max===4015&&hp.current>=hp.max*.9&&h&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0;
  const examRoadRelease=releaseClimb===true&&climb&&m&&(Math.hypot(m.x+1372.0547,m.y-1499.4004)<=2||Math.hypot(m.x+1332.4551,m.y-1682.5059)<=2)&&hp&&hp.max===4015&&hp.current>=hp.max*.9&&h&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0;
  const examField=(reviewedBaseRelease||shelfClimb||examRoadRelease||!climb||m&&(releaseClimb===true?Math.hypot(m.x+1207.2227,m.y-1660.873)<=3:Math.hypot(m.x+1342.426,m.y-1691.34)<=8)&&hp&&hp.current===2313&&hp.max===2313)&&m&&m.x>=-1500&&m.x<=-1200&&(m.y>=1600||(!climb||examRoadRelease)&&m.x<=-1300&&m.y>=1450)&&m.y<=1950&&h&&(h.objectives||[]).some(t=>['Gototheexampoint',"FollowAmber'sinstructionsandtaketheexamagain"].includes(String(t).replace(/\s/g,'')));
  const hqRoofRest=releaseClimb===true&&climb===true&&landingReviewed===true&&m&&m.map==='Teyvat'&&Math.hypot(m.x+764.8965,m.y-2269.4844)<=.5&&hp&&hp.max===4015&&hp.current===4015&&h&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Followtherouteandflytothefinishlineintime')&&(h.objectives||[]).some(t=>/^Higher (27|28)m$/.test(String(t).trim()));
  const hqRoofLedge=!climb&&m&&m.map==='Teyvat'&&(Math.hypot(m.x+763.3262,m.y-2251.7539)<=.6&&(h.objectives||[]).some(t=>String(t).trim()==='Lower 13m')||Math.hypot(m.x+763.4004,m.y-2256.5801)<=.7&&(h.objectives||[]).some(t=>String(t).trim()==='Lower 17m')||Math.hypot(m.x+763.3965,m.y-2258.4707)<=1&&(h.objectives||[]).some(t=>String(t).trim()==='Lower 18m')||Math.hypot(m.x+751.434,m.y-2262.328)<=.5&&(h.objectives||[]).some(t=>String(t).trim()==='Lower 32m')&&interaction(o,'Teleport Waypoint')||Math.hypot(m.x+750.744,m.y-2262.138)<=.5&&(h.objectives||[]).some(t=>String(t).trim()==='Lower 29m')||Math.hypot(m.x+764.99,m.y-2268.88)<=.3&&(h.objectives||[]).some(t=>String(t).trim()==='Lower 26m')||Math.hypot(m.x+765.27,m.y-2270.23)<=.6||Math.hypot(m.x+764.91,m.y-2269.43)<=.4&&(h.objectives||[]).some(t=>String(t).trim()==='Higher 27m'))&&hp&&hp.max===4015&&hp.current>=3614&&h&&h.groundControls&&!h.climbing&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Followtherouteandflytothefinishlineintime');
  const hqRoofClimb=climb===true&&releaseClimb!==true&&m&&m.map==='Teyvat'&&(Math.hypot(m.x+765.49,m.y-2270.39)<=2||Math.hypot(m.x+750.744,m.y-2262.138)<=2)&&hp&&hp.max===4015&&hp.current>=3614&&h&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Followtherouteandflytothefinishlineintime')&&(climbProbe===true||h.climbStamina&&h.climbStamina.source==='same-frame-yellow-arc'&&Number.isFinite(h.climbStamina.pixels)&&h.climbStamina.pixels>=180&&h.climbStamina.boxes&&h.climbStamina.boxes.length&&Math.max(...h.climbStamina.boxes.map(b=>b.y+b.height))-Math.min(...h.climbStamina.boxes.map(b=>b.y))>=45);
  const windriseLowClimb=climb===true&&releaseClimb!==true&&m&&m.map==='Teyvat'&&Math.hypot(m.x+1266.05078125,m.y-1892.8818359375)<=.7&&hp&&hp.max===4015&&hp.current===4015&&h&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).some(t=>["FollowAmber'sinstructionsandtaketheexamagain","Followtherouteandflytothefinishlineintime"].includes(String(t).replace(/\s/g,'')))&&(climbProbe===true||h.climbStamina&&h.climbStamina.source==='same-frame-yellow-arc'&&h.climbStamina.pixels>=180);
  const lowCityTree=releaseClimb===true&&m&&Math.hypot(m.x+929.096,m.y-2222.957)<2&&hp&&hp.current===2313&&hp.max===2313&&h&&!(h.objectives||[]).length;
  const plateauTreeRelease=releaseClimb===true&&climb&&m&&Math.hypot(m.x+1434.979,m.y-2375.973)<=2&&hp&&hp.current===2635&&hp.max===2635&&h&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Defeattheattackingmonsters');
  const campRockRelease=releaseClimb===true&&climb&&m&&Math.hypot(m.x+1235.4863,m.y-2302.3857)<=2&&hp&&hp.max===2635&&hp.current>=hp.max*.9&&h&&Array.isArray(h.enemyBars)&&h.enemyBars.length<=2&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Defeattheattackingmonsters');
  const cyrusLowLedge=climb&&m&&Math.hypot(m.x+1123.295,m.y-2302.307)<=6&&hp&&hp.max===2635&&hp.current===2635&&h&&cyrusObjective(o)&&(h.objectives||[]).includes('(1/3)');
  const mageAmber=!climb&&m&&Math.hypot(m.x+1570,m.y-2240)<65&&hp&&hp.max===1186&&(o.ocr||[]).some(r=>r.text==='Amber'&&r.x>=1650&&r.x<=1685&&r.y>=330&&r.y<=400);
  const combatMinimum=.7;
  const hideoutClimb=climb===true&&releaseClimb!==true&&visualPositionReviewed===true&&h&&h.climbing&&hp&&hp.max===4015&&hp.current===4015&&Array.isArray(h.enemyBars)&&!h.enemyBars.length&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==="EnterRaptor'sHideout")&&(climbProbe===true&&h.climbStamina&&h.climbStamina.pixels===null||h.climbStamina&&h.climbStamina.source==='same-frame-yellow-arc'&&Number.isFinite(h.climbStamina.pixels)&&h.climbStamina.pixels>=180&&h.climbStamina.boxes&&h.climbStamina.boxes.length&&Math.max(...h.climbStamina.boxes.map(b=>b.y+b.height))-Math.min(...h.climbStamina.boxes.map(b=>b.y))>=45);
  const regional=visualPositionReviewed===true&&(!climb||releaseClimb===true||hideoutClimb)&&(regionalMap(regionWitness,now,session)||regionalCombat===true&&leyLine(w)&&w.session===session);
  const raptorEncounter=regional&&regionalCombat===true&&!climb&&h&&hp&&[2372,2451,2764,4015].includes(hp.max)&&hp.current>=hp.max*.7&&(raptorAmbushObjective(o)||raptorSoundObjective(o)&&(h.objectives||[]).some(t=>/^Quest area reach[e\uFFFD]d$/.test(t)));
  const raptorTravel=regional&&(!climb||hideoutClimb||releaseClimb===true&&landingReviewed===true)&&regionalCombat!==true&&h&&hp&&hp.max===4015&&hp.current>=((h.objectives||[]).some(t=>t.replace(/\s/g,'')==='LookforRaptor')?hp.max*.85:3614)&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(raptorSoundObjective(o)||raptorAmbushObjective(o)&&(h.objectives||[]).some(t=>/^(?:[1-9]\d|[1-5]\d{2}|600)m[./]?$/.test(t.trim()))||(h.objectives||[]).some(t=>['TrackRaptor','LookforRaptor','LookforthemarksleftbyRaptor',"EnterRaptor'sHideout"].includes(t.replace(/\s/g,''))||/^LookforcluestotrackRaptor\([0-2]\/3\)$/.test(t.replace(/\s/g,''))));
  const marksRelease=regional&&releaseClimb===true&&landingReviewed===true&&climb&&h&&h.climbing&&hp&&hp.max===4015&&hp.current>=hp.max*.9&&(h.objectives||[]).some(t=>['LookforthemarksleftbyRaptor',"EnterRaptor'sHideout"].includes(String(t).replace(/\s/g,'')));
  const regionalRelease=regional&&releaseClimb===true&&hp&&(hp.current===hp.max||marksRelease)&&h&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0;
  if(regional&&releaseClimb&&!regionalRelease)return false;
  if(regional&&regionalCombat===true&&h&&h.enemyBarDiagnostic&&[10,13].includes(h.enemyBarDiagnostic.level)&&(!hp||![1363,2372,2451,2764,2635,4015].includes(hp.max)))return false;
  if(regionWitness&&(!regional||!h||!hp||hp.current<hp.max*(regionalCombat===true?combatMinimum:0.85)||regionalCombat===true&&(![1363,2313,2372,2451,2764,2635,4015].includes(hp.max)||!witnessOnly&&(!h.enemyBarDiagnostic||![4,10,12,13,'any'].includes(h.enemyBarDiagnostic.level)))||regionalCombat!==true&&h.enemyBars.length))return false;
  const waypointBase=m&&m.map==='Teyvat'&&hp&&hp.max===4015&&hp.current===4015&&h&&Array.isArray(h.enemyBars)&&!h.enemyBars.length&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Lookforthelocationintheriddle');
  const waypointMount=waypointBase&&!climb&&Math.hypot(m.x+1421.293,m.y-1457.724)<=.75;
  const waypointClimb=waypointBase&&climb&&!releaseClimb&&Math.hypot(m.x+1432.63,m.y-1464.61)<=18&&((climbProbe===true&&Math.hypot(m.x+1421.293,m.y-1457.724)<=1&&h.climbStamina&&h.climbStamina.pixels===null)||h.climbStamina&&h.climbStamina.source==='same-frame-yellow-arc'&&Number.isFinite(h.climbStamina.pixels)&&h.climbStamina.pixels>=180&&h.climbStamina.boxes&&Math.max(...h.climbStamina.boxes.map(b=>b.y+b.height))-Math.min(...h.climbStamina.boxes.map(b=>b.y))>=45);
  const coastalCamera=cameraOnly===true&&!climb&&m&&m.x>=-1660&&m.x< -1600&&m.y>=2600&&m.y<=2700&&hp&&hp.max===4015&&hp.current===4015&&h&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&Array.isArray(h.objectives)&&h.objectives.length===0;
  const position=visualPositionReviewed===true
   ?w&&w.session===session&&Number.isFinite(w.timestamp)&&now>=w.timestamp&&now-w.timestamp<=600000&&(regional||wm&&wm.map==='Teyvat'&&wm.x>=-1600&&wm.x<=-700&&wm.y>=1700&&wm.y<=2700)
   :wm&&m&&m.map==='Teyvat'&&wm.map==='Teyvat'&&(m.x>=-1600||coastalCamera)&&m.x<=-700&&(m.y>=1700||examField||waypointClimb||!climb&&m.x>=-1500&&m.x<=-1300&&m.y>=1450)&&m.y<=2700&&Math.hypot(m.x-wm.x,m.y-wm.y)<=12;
  const cyrusThreats=!climb&&m&&m.x>=-1500&&m.x<=-1050&&m.y>=2150&&m.y<=2500&&h&&cyrusObjective(o);
  const examFinishApproach=!climb&&m&&m.map==='Teyvat'&&Math.hypot(m.x+1436.9785,m.y-1877.1553)<=25&&hp&&hp.max===4015&&hp.current>=4015*.9&&h&&h.groundControls&&!h.climbing&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='TalktoAmber');
  const riddleContext=m&&m.map==='Teyvat'&&Math.hypot(m.x+845.67,m.y-2214)<=8&&hp&&hp.max===4015&&hp.current===4015&&h&&Array.isArray(h.enemyBars)&&!h.enemyBars.length&&(h.objectives||[]).some(t=>t.replace(/\s/g,'')==='Lookforthelocationintheriddle');
  const riddleRest=riddleContext&&climb===true&&releaseClimb===true&&landingReviewed===true&&((Math.hypot(m.x+843.2734375,m.y-2209.984375)<=.4&&(h.objectives||[]).some(t=>/^Higher 10m$/.test(t.trim())))||(Math.hypot(m.x+844.81640625,m.y-2216.763671875)<=.75&&(h.objectives||[]).some(t=>/^Higher (6|7|8|9|10)m$/.test(t.trim()))||(Math.hypot(m.x+846.974609375,m.y-2217.439453125)<=.4&&(h.objectives||[]).some(t=>/^Higher 6m$/.test(t.trim())))));
  const riddleBalcony=riddleContext&&!climb&&h.groundControls&&!h.climbing&&(h.objectives||[]).some(t=>/^Higher (8|9|10|11|12)m$/.test(t.trim()));
  const riddleMount=riddleContext&&!climb&&(Math.hypot(m.x+844.1621,m.y-2208.541)<=1||Math.hypot(m.x+842.8887,m.y-2209.2979)<=.6);
  const riddleClimb=riddleContext&&climb===true&&releaseClimb!==true&&((climbProbe===true&&((Math.hypot(m.x+842.9141,m.y-2209.6914)<=.4&&(h.objectives||[]).some(t=>/^Higher (26|27)m$/.test(t.trim())))||(Math.hypot(m.x+844.84375,m.y-2216.8994140625)<=.3&&(h.objectives||[]).some(t=>/^Higher 8m$/.test(t.trim()))))&&h.climbStamina&&h.climbStamina.source==='same-frame-yellow-arc'&&h.climbStamina.pixels===null&&h.climbStamina.rawPixels===0)||h.climbStamina&&h.climbStamina.source==='same-frame-yellow-arc'&&Number.isFinite(h.climbStamina.pixels)&&h.climbStamina.pixels>=180&&h.climbStamina.boxes&&h.climbStamina.boxes.length&&Math.max(...h.climbStamina.boxes.map(b=>b.y+b.height))-Math.min(...h.climbStamina.boxes.map(b=>b.y))>=(Math.hypot(m.x+843.46875,m.y-2209.6875)<=1.5&&(h.objectives||[]).some(t=>/^Higher (?:[5-9]|1[0-4])m$/.test(t.trim()))?32:45));
  const mysteryChest=!climb&&m&&Math.hypot(m.x+774.82,m.y-2239.49)<=4&&hp&&hp.max===4015&&hp.current===4015&&h&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).slice(0,2).join('').replace(/[^A-Za-z]/g,'')==='SolvethemysteryGotoKaeyaattheKnightsofFavoniusHQforahint'&&['Common Chest','Silver Sword',"Wanderer's Advice","Adventurer's Experience",'Fine Enhancement Ore','Enhancement Ore',"Traveling Doctor's Silver Lotus","Traveling Doctor's Owl Feather","Lucky Dog's Eagle Feather"].some(name=>interaction(o,name));
  const mysteryCamera=cameraOnly===true&&!climb&&m&&m.x>=-900&&m.x<=-700&&m.y>=2200&&m.y<=2450&&hp&&hp.max===4015&&hp.current===4015&&h&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(['SolvethemysteryGotoKaeyaattheKnightsofFavoniusHQforahint'].includes((h.objectives||[]).slice(0,2).join('').replace(/[^A-Za-z]/g,''))||(h.objectives||[]).some(t=>t==='Look for the location in the riddle'));
  const cityCamera=cameraOnly===true&&!climb&&m&&m.x>=-900&&m.x<=-700&&m.y>=2200&&m.y<=2450&&h&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='TalktoAmber'||hp&&hp.max===4015&&hp.current>=3614&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&String(t).replace(/\s/g,'')==='Followtherouteandflytothefinishlineintime');
  const explorationCamera=cameraOnly===true&&!climb&&m&&m.map==='Teyvat'&&m.x>=-1500&&m.x<=-1300&&m.y>=1450&&m.y<=1700&&h&&hp&&hp.max===4015&&hp.current===4015&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Lookforthelocationintheriddle');
  const cyrusTravelCamera=cameraOnly===true&&!climb&&m&&m.x>=-1260&&m.x<=-1100&&m.y>=2190&&m.y<=2360&&hp&&hp.current===2635&&hp.max===2635&&h&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Defeattheattackingmonsters');
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&position&&(!releaseClimb||riddleRest||hqRoofRest||regionalRelease||examField||lowCityTree||cyrusLowLedge||plateauTreeRelease||campRockRelease)&&h&&(h.world||regionalRelease&&landingReviewed===true&&hp.max===4015||marksRelease||hideoutClimb||cameraClimb&&cameraOnly===true&&regional&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==="EnterRaptor'sHideout"))&&controls&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.bigMap&&!h.journal&&hp&&([1363,1700,1829,2313,2372,2451,2764,2635,4015].includes(hp.max)||mageAmber)&&hp.current>=hp.max*combatMinimum&&hp.current<=hp.max&&(h.enemyBarDiagnostic||regional&&witnessOnly===true)&&Array.isArray(h.enemyBars)&&(!climb||!h.enemyBars.length||campRockRelease)&&(waypointMount||waypointClimb||explorationCamera||regionalCombat===true&&!climb&&roadDefense(o,w,now,session)||raptorEncounter||raptorTravel||windriseLowClimb||hqRoofRest||hqRoofLedge||hqRoofClimb||examField||examFinishApproach||riddleRest||riddleBalcony||riddleMount||riddleClimb||mysteryChest||mysteryCamera||cityCamera||cyrusTravelCamera||cyrusThreats||cyrusLowLedge||plateauTreeRelease||campRockRelease||regional&&regionalCombat===true&&(h.objectives||[]).every(t=>/^(?:Defeatallopponents(?:[0-7]\/7)?|OpponentsDefeated:?\d+\/\d+|\(?\d+\/\d+\)?)$/.test(String(t).replace(/\s/g,''))||leyLineEnemyLabel(o,t))||!(h.objectives||[]).some(t=>String(t).replace(/[^A-Za-z]/g,'').length>5))&&ids.length>0&&ids.every(r=>/693306810$/.test(String(r.text).trim())));
 }
 // Diagnostic fallback: red-only contours do not identify the full health-track
 // width, so perspective changes cannot safely be interpreted as damage.
 async function runSingleTargetDiagnostic(initial,w,p,api,observe){
  let current=initial,previous=p.targetAnchor,steps=0,turns=0;
  const began=api.now(),baseline=initial.hud.health.current;
  const result={status:'stopped',actions:0,skills:0,attacks:0,approachSteps:0,diagnostic:true,damageConfirmed:false,defeatConfirmed:false,frames:[]};
  function record(){result.frames.push({frameId:current.frameId,health:current.hud.health,bars:combatTargets(current,p),map:current.map});}
  function target(){
   if(!ready(current,w,api.now(),initial.session,false,false,false,false,null,false,false)||current.hud.health.max!==initial.hud.health.max||current.hud.health.current<baseline){result.reason='Diagnostic health or fresh field evidence changed';return null;}
   const bars=combatTargets(current,p);
   if(bars.length!==1){result.reason='Diagnostic target identity lost or ambiguous';return null;}
   const b=bars[0];
   if(!b||![b.x,b.y,b.width,b.height].every(Number.isFinite)||b.x<350||b.x>1600||b.y<100||b.y>900||b.width<2||b.width>300||b.height<3||b.height>20||Math.abs(b.x-previous.x)>200||Math.abs(b.y-previous.y)>100||b.height/previous.height>2||b.height/previous.height<0.5){result.reason='Diagnostic target continuity lost';return null;}
   previous=b;return b;
  }
  try{
   while(api.now()-began<15000){
    api.checkStop();record();const b=target();if(!b)break;
    if(Math.abs(b.x-960)>140){
     if(turns++>=2){result.reason='Diagnostic alignment bound reached';break;}
     await api.action({type:'look',dx:Math.max(-100,Math.min(100,Math.round((b.x-960)*0.5))),dy:0},current);result.actions++;
    }else if(b.height<6){
     if(steps>=4){result.reason='Diagnostic range bound reached without close target';break;}
     await api.key('VK_W',400,current);steps++;result.actions++;result.approachSteps=steps;
    }else{
     result.beforeBurstFrameId=current.frameId;
     // One burst only, with a fresh observation and identity/health/range check
     // between every strike. Never continue based on a disappearing red bar.
     for(let hit=0;hit<3&&api.now()-began<15000;hit++){
      api.checkStop();const t=target();if(!t)break;
      if(t.height<6||Math.abs(t.x-960)>140){result.reason='Diagnostic close range lost';break;}
      await api.key('VK_LBUTTON',60,current);result.attacks++;await api.sleep(200);current=await observe();record();
     }
     result.afterBurstFrameId=current.frameId;
     result.reason=result.reason||'One diagnostic burst ended; damage unconfirmed, pause for retained frame review';break;
    }
    await api.sleep(200);current=await observe();
   }
   result.reason=result.reason||'Diagnostic time bound reached';result.fieldFrameId=current.frameId;result.health=current.hud.health;return result;
  }finally{await api.release();}
 }
 async function run(initial,w,p,api,observe){
  if(p.singleTargetDiagnostic===true){if(!diagnosticPlan(p))throw new Error('Invalid single target diagnostic plan');return runSingleTargetDiagnostic(initial,w,p,api,observe);}
  let current=initial,lastSkill=-Infinity,empty=0;const began=api.now(),baseline=initial.hud.health.current,result={status:'stopped',actions:0,skills:0,attacks:0};
  if(p.regionWitness){result.positionSource='reviewed visual ground and regional map';result.minimapPositionVerified=false;result.regionMapFrameId=p.regionWitness.frameId;}
  const distance=o=>{const t=(o.hud.objectives||[]).find(t=>/^\d+m[./]?$/.test(t.trim()));return t?Number(t.match(/\d+/)[0]):null;};let priorDistance=distance(initial),stalledSteps=0;
  function safe(){if(p.recoverySwitch===true)return switchReady(current,w,api.now(),initial.session,p.actions[0].key);return ready(current,w,api.now(),initial.session,p.mode==='climb'||p.mode==='releaseClimb',p.visualPositionReviewed,cameraPlan(p),p.mode==='releaseClimb',p.regionWitness,false,(p.mode==='combat'&&[4,10,12,13,'any'].includes(p.enemyLevel)||eventReposition(p)&&leyLine(w)),p.climbProbe===true,p.landingReviewed===true)&&current.hud.health.max===initial.hud.health.max&&baseline-current.hud.health.current<=initial.hud.health.max*0.15;}
  try{
   if(p.thornPyro!==undefined){if(!safe()||typeof api.thornPyro!=='function')throw Error('Fresh reviewed thorn approach required');return await api.thornPyro(current,p);}
   if(p.thornHop===true){if(!thornHop(p)||!safe())throw new Error('Fresh reviewed thorn hop required');api.checkStop();await api.key('VK_SPACE',60,current);result.actions++;await api.sleep(100);api.checkStop();if(!safe())throw new Error('Thorn hop start expired');await api.key('VK_W',600,current);result.actions++;await api.sleep(700);current=await observe();result.fieldFrameId=current.frameId;result.health=current.hud.health;result.reason='Single reviewed thorn hop ended; inspect landing';return result;}
   if(p.convergingTravel===true){if((!raptorAmbushObjective(current)||priorDistance===null)&&raptorAmbushObjective(w)&&distance(w)!==null&&current.hud.world&&!current.hud.climbing&&current.hud.health.current===current.hud.health.max&&!(current.hud.enemyBars||[]).length){api.checkStop();await api.sleep(250);current=await observe();priorDistance=distance(current);result.questTextRereads=1;}if(!raptorAmbushObjective(current)||priorDistance===null)throw new Error('Converging travel requires exact ambush distance');result.routeDistances=[priorDistance];}
   if(p.raptorApproach===true&&(!raptorApproach(p)||!(raptorSoundObjective(w)||raptorAmbushObjective(w))||p.actions.some(a=>a.type!=='look')&&!combatTargets(current,p).length))throw new Error('Reviewed visible Raptor approach required');
   if(p.phaseReact===true){if(leyLineCount(w)!==6||typeof api.phaseReact!=='function')throw Error('Exact final-event local phase reactor required');return await api.phaseReact(current);}
   if(p.nativeCombat===true){
    const windows=p.nativeWindows||1;
    if(!Number.isInteger(windows)||windows<1||windows>3||windows>1&&(!raptorAmbushObjective(current)||p.enemyLevel!==13))throw new Error('Bounded native windows require exact Raptor ambush');
    result.nativeWindows=[];
    for(let window=0;window<windows;window++){
     while(p.nativeSearch===true&&safe()&&raptorAmbushObjective(current)&&!combatTargets(current,p).length&&(result.targetSearchTurns||0)<3){
      api.checkStop();await api.action({type:'look',dx:600,dy:0},current);result.targetSearchTurns=(result.targetSearchTurns||0)+1;await api.sleep(150);current=await observe();
     }
     if(window>0&&(!safe()||!raptorAmbushObjective(current)||!combatTargets(current,p).length)){result.reason='Native continuation health, objective or target changed';break;}
    if(safe()&&raptorFrozen(current)){
     // Four bounded release taps finish within one fresh-frame window. Reread
     // once after the escape, instead of standing through four full OCR scans.
     for(let tap=0;tap<4;tap++){api.checkStop();await api.key('VK_SPACE',60,current);result.frozenBreaks=(result.frozenBreaks||0)+1;await api.sleep(100);}
     current=await observe();if(raptorFrozen(current))throw new Error('Native frozen escape bound reached');
    }
    if(!safe()||!nativeHealth(p.nativeAvatar,current.hud.health.max)||current.hud.health.current<current.hud.health.max*.7||![10,13].includes(p.enemyLevel)||!(combatTargets(current,p).length||leyLine(w))||typeof api.nativeCombat!=='function')throw new Error('Fresh healthy regional Lv13 native encounter required');
    const before={frameId:current.frameId,timestamp:current.timestamp,health:current.hud.health,bars:combatTargets(current,p)};
    if(p.shieldProbe===true&&(windows!==1||leyLineCount(w)!==6||p.shieldReviewed!==true||p.nativeAvatar!=='Kaeya'||current.hud.health.current<current.hud.health.max*.85||combatTargets(current,p).length!==1||Math.abs(combatTargets(current,p)[0].x-960)>260||combatTargets(current,p)[0].width<20))throw new Error('Shield probe requires healthy Kaeya and one fresh centered close Lv13 target');result.shieldProbe=p.shieldProbe===true;result.nativeAttempted=true;const chunk=await api.nativeCombat(current);Object.assign(result,chunk);await api.sleep(150);current=await observe();
    result.nativeWindows.push({before:before,after:{frameId:current.frameId,timestamp:current.timestamp,health:current.hud.health,bars:combatTargets(current,p)},nativeReturned:chunk.nativeReturned===true,nativeMs:chunk.nativeMs||0});
    if(chunk.nativeReturned!==true&&windows>1){result.reason='Native return unconfirmed';break;}
    }
    result.nativeMs=result.nativeWindows.reduce((sum,w)=>sum+w.nativeMs,0);
    result.opponentsBefore=leyLineCount(w);result.opponentsAfter=leyLineCount(current);result.killsConfirmed=result.opponentsBefore!==null&&result.opponentsAfter!==null?Math.max(0,result.opponentsAfter-result.opponentsBefore):null;result.defeatConfirmed=result.killsConfirmed>0;result.fieldFrameId=current.frameId;result.health=current.hud.health;result.reason=result.reason||'Bounded native rotations ended; inspect quest progress';return result;
   }
   for(const a of p.actions){
    if(retiredWindmillCrossing(current,a))throw new Error('Retired windmill ladder crossing; inspect a safe endpoint');
    if(p.raptorApproach===true){
     while(safe()&&raptorFrozen(current)&&(result.frozenBreaks||0)<4){api.checkStop();await api.key('VK_SPACE',60,current);result.frozenBreaks=(result.frozenBreaks||0)+1;await api.sleep(200);current=await observe();}
     if(raptorFrozen(current))throw new Error('Frozen approach escape bound reached');
    }
    if(a.key==='VK_F'&&(a.target==='Touch the Ley Line opening'||['Broken-off Branch','Fabric Piece','Elemental Mark'].includes(a.target)&&interaction(w,a.target))&&safe()&&!interaction(current,a.target)){await api.sleep(250);current=await observe();}
    const repeats=a.key==='VK_LBUTTON'&&a.target==='Breakable rocks'?3:1;
    for(let strike=0;strike<repeats;strike++){api.checkStop();if(!safe()||a.key==='VK_F'&&!interaction(current,a.target)||['VK_LBUTTON','VK_E'].includes(a.key)&&a.target==='Breakable rocks'&&current.hud.enemyBars.length||a.target==='Explosive Barrel'&&!(a.key==='VK_E'&&current.map&&Math.hypot(current.map.x+1125,current.map.y-2220)<45&&cyrusObjective(current)))throw new Error('Field action evidence changed');await api.action(a,current);result.actions++;if(repeats===3)result.obstacleStrikes=(result.obstacleStrikes||0)+1;await api.sleep(a.key==='VK_F'||a.key==='VK_X'?600:200);}
    current=await observe();
    if((windmillField(w)||windmillField(initial)||windmillField(current))&&a.type==='key'&&['VK_W','VK_A','VK_S','VK_D','VK_X'].includes(a.key)&&!current.hud.climbing){const landing=current;await api.sleep(800);api.checkStop();current=await observe();result.groundSettled=windmillGroundStable(landing,current);result.groundSettlementFrames=[landing.frameId,current.frameId];if(!result.groundSettled){result.reason='Windmill ground endpoint did not settle safely';break;}}
    if(p.convergingTravel===true&&a.key==='VK_W'){const next=distance(current);result.routeDistances.push(next);if(!raptorAmbushObjective(current)||next===null){result.reason='Travel objective or distance changed';break;}if(next>priorDistance+2){result.reason='Travel distance increased';break;}stalledSteps=next>=priorDistance?stalledSteps+1:0;priorDistance=next;if(stalledSteps>=2){result.reason='Travel distance stalled for two steps';break;}}
   }
   if(p.recoverySwitch===true&&current.hud.health&&current.hud.health.max===initial.hud.health.max){
    await api.sleep(200);current=await observe();
    if(switchReady(current,w,api.now(),initial.session,p.actions[0].key)){await api.action(p.actions[0],current);result.actions++;result.switchRetries=1;await api.sleep(450);current=await observe();}
   }
   if(p.recoverySwitch===true)result.switchVerified=!!(current.hud.health&&current.hud.health.max!==initial.hud.health.max);
   if(p.mode==='loot')for(let pickup=0;pickup<8&&api.now()-began<15000;pickup++){
    api.checkStop();if(!safe()||current.hud.enemyBars.length){result.reason='Loot field evidence changed';break;}
    const target=['Fowl',"Adventurer's Pocket Watch","Berserker's Timepiece",'Silver Sword',"Traveling Doctor's Handkerchief",'Firm Arrowhead','Damaged Mask','Slime Condensate',"Wanderer's Advice","Adventurer's Experience","Adventurer's Tail Feather","Traveling Doctor's Pocket Watch","Traveling Doctor's Medicine Pot",'Fine Enhancement Ore','Enhancement Ore',"Traveling Doctor's Silver Lotus","Traveling Doctor's Owl Feather","Lucky Dog's Eagle Feather"].find(name=>interaction(current,name));
    if(!target){result.reason='No eligible selected loot';break;}
    await api.key('VK_F',60,current);result.actions++;(result.lootTargets||(result.lootTargets=[])).push(target);await api.sleep(450);current=await observe();
   }
   if(p.mode==='combat')for(let cycle=0;cycle<(roadDefense(initial,w,initial.timestamp,initial.session)?6:12)&&api.now()-began<(roadDefense(initial,w,initial.timestamp,initial.session)?8000:20000);cycle++){
    api.checkStop();if(!safe()||![4,5,10,11,12,13,14,'any'].includes(p.enemyLevel||4)||current.hud.enemyBarDiagnostic.level!==(p.enemyLevel||4)){result.reason='Combat health, location or level evidence changed';break;}
    if(raptorFrozen(current)){if((result.frozenBreaks||0)>=4){result.reason='Frozen escape bound reached';break;}await api.key('VK_SPACE',60,current);result.frozenBreaks=(result.frozenBreaks||0)+1;await api.sleep(200);current=await observe();continue;}
    if(!combatTargets(current,p).length){if(++empty>=2){result.reason='missing_target';break;}await api.sleep(200);current=await observe();continue;}empty=0;
    if(p.raptorPursuit===true){
     if(!raptorAmbushObjective(current)){result.reason='Raptor pursuit objective changed';break;}
     const target=combatTargets(current,p).slice().sort((a,b)=>Math.abs(a.x-960)-Math.abs(b.x-960))[0];
     if(Math.abs(target.x-960)>160){
      if((result.aimCorrections||0)>=4){result.reason='Raptor aim bound reached';break;}
      await api.action({type:'look',dx:Math.max(-750,Math.min(750,Math.round((target.x-960)*1.35))),dy:0},current);result.aimCorrections=(result.aimCorrections||0)+1;await api.sleep(150);current=await observe();continue;
     }
     if(target.height<9){
      if((result.approachSteps||0)>=4){result.reason='Raptor approach bound reached';break;}
      await api.action({type:'key',key:'VK_W',ms:600},current);result.approachSteps=(result.approachSteps||0)+1;await api.sleep(150);current=await observe();continue;
     }
    }
    if((cycle===0||p.raptorPursuit===true&&!result.burstAttempts)&&(cyrusObjective(current)||p.regionWitness&&p.visualPositionReviewed===true)){await api.key('VK_Q',60,current);result.burstAttempts=1;await api.sleep(600);current=await observe();continue;}
    if(api.now()-lastSkill>=6500){await api.key('VK_E',60,current);lastSkill=api.now();result.skills++;await api.sleep(450);}
    else for(let hit=0;hit<3;hit++){if(!safe())break;await api.key('VK_LBUTTON',60,current);result.attacks++;await api.sleep(200);}
    current=await observe();
   }
   result.reason=result.reason||'Bounded field batch ended; inspect outcome';result.fieldFrameId=current.frameId;result.health=current.hud.health;return result;
  }catch(error){error.fieldResult=result;throw error;}finally{await api.release();}
 }
 root.ActTwoField={roadDefense,windmillField,retiredWindmillCrossing,windmillGroundStable,originalWitnessFailure,raptorFrozen,healthReread,eventReposition,nativeHealth,switchReady,leyLineCount,leyLine,failureReason,regionalMap,cameraPlan,plan,ready,run,interaction,enemyLevel,combatTargets};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoField;
})(typeof globalThis!=='undefined'?globalThis:this);
