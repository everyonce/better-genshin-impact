(function(root){
 'use strict';
 function recoveryTarget(o,now,session){
  const rows=o&&o.ocr||[],h=o&&o.hud,hp=h&&h.health;
  const one=(text,x0,x1,y0,y1)=>rows.filter(r=>r.text===text&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1);
  if(!o||o.session!==session||now<o.timestamp||now-o.timestamp>1000||!hp||![2451,4015].includes(hp.max)||hp.current<hp.max*.9||hp.current>hp.max||!rows.some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(r.text))||one('Abandon Challenge',700,850,250,330).length!==1||one('Abandon Challenge?',750,900,470,550).length!==1||one('Cancel',650,850,700,790).length!==1)return null;
  const c=one('Confirm',1050,1250,700,790);return c.length===1?{x:c[0].x+c[0].width/2,y:c[0].y+c[0].height/2}:null;
 }
 function afterTrial(o,now,session,ground){
  const h=o&&o.hud,m=o&&o.map,rows=o&&o.ocr||[],hp=h&&h.health;
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&m&&m.map==='Teyvat'&&m.x>=-900&&m.x<=-670&&m.y>=2230&&m.y<=2380&&h&&h.world&&(ground===true?h.groundControls===true:h.groundControls===false)&&!h.climbing&&!h.auto&&!h.choice&&!h.dialogueReady&&!h.bigMap&&!h.journal&&Array.isArray(h.enemyBars)&&!h.enemyBars.length&&hp&&hp.max===4015&&hp.current>=4015*.9&&hp.current<=4015&&rows.some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(r.text))&&(ground===true||rows.some(r=>r.text==='Space'&&r.x>=1600&&r.y>=980))&&(rows.some(r=>String(r.text).trim()==='Talk to Amber'&&r.x<650&&r.y>=230&&r.y<=350)||ground===true&&Math.hypot(m.x+772.97,m.y-2242.88)<=5&&rows.filter(r=>r.x<650&&r.y>=230&&r.y<=350).map(r=>r.text).join('').replace(/[^A-Za-z]/g,'').includes('Followtherouteandflytothefinishlineintime'))&&!rows.some(r=>r.text.includes('Abandon Challenge')||r.x>=850&&r.x<=1100&&r.y>=20&&r.y<=100&&/^\d{1,2}:\d{2}$/.test(r.text.trim())));
 }
 function plan(p,r,now){return !!(p&&p.reviewed===true&&(p.afterTrial===undefined||p.afterTrial===true&&['flight','ground'].includes(p.mode))&&(p.left===undefined||p.left===true&&p.mode==='flight'&&!p.stationary&&!p.backward)&&(p.stationary===undefined||p.stationary===true&&['launch','flight'].includes(p.mode)&&!p.backward)&&(p.backward===undefined||p.backward===true&&p.mode==='flight')&&!p.usedAt&&p.session===r.session&&p.frameId===r.expectedFrameId&&Number.isInteger(p.witnessFrameId)&&p.witnessFrameId<p.frameId&&now>=p.createdAt&&now-p.createdAt<=120000&&['inspect','ground','launch','stepDown','open','flight','course','abandonInspect'].includes(p.mode)&&Number.isInteger(p.dx)&&Math.abs(p.dx)<=750&&Number.isInteger(p.dy)&&Math.abs(p.dy)<=500&&Number.isInteger(p.holds)&&p.holds>=0&&p.holds<=4&&(p.mode!=='stepDown'||p.holds===0)&&(!['inspect','abandonInspect'].includes(p.mode)||p.holds===0)&&(p.mode!=='inspect'||p.dx===0&&p.dy===0));}
 function state(o,now,session){
  const h=o&&o.hud,hp=h&&h.health,m=o&&o.map,rows=o&&o.ocr||[];
  const objective=rows.some(r=>r.x<650&&r.y>=230&&r.y<=350&&['Followtherouteandflytothefinish','Reachthetargetlocationwithin60','Reachthetargetlocationwithin60seconds','Reachthetargetlocationwithin60Reachsthetargetlocationwithin60seconds','Reachthetargetlocationwithin180seconds','Reachthetargetlocationwithin180Reachthetargetlocationwithin180seconds'].includes(String(r.text).replace(/[^A-Za-z0-9]/g,'')));
  const timers=rows.filter(r=>r.x>=850&&r.x<=1100&&r.y>=20&&r.y<=100&&/^\d{1,2}:\d{2}$/.test(String(r.text).trim()));
  const timer=timers.length===1?timers[0].text.trim().split(':').reduce((a,b)=>a*60+Number(b),0):null;
  if(!o||o.session!==session||!Number.isInteger(o.frameId)||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||!h||h.auto||h.choice||h.dialogueReady||h.journal||h.bigMap||h.climbing||!hp||![4015,2451].includes(hp.max)||hp.current<hp.max*.9||hp.current>hp.max||!objective||timer===null||timer<5||timer>180||!rows.some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(r.text))||!Array.isArray(h.enemyBars)||h.enemyBars.length)return null;
  const finalWindmill=timer<=60&&h.groundControls===false&&rows.some(r=>r.text==='Space'&&r.x>=1600&&r.y>=980)&&rows.some(r=>r.x<650&&r.y>=230&&r.y<=350&&String(r.text).replace(/[^A-Za-z0-9]/g,'')==='Reachthetargetlocationwithin60seconds')&&m&&Math.hypot(m.x+820.7734375,m.y-2225.33203125)<=20;
  if(m&&(!Number.isFinite(m.x)||!Number.isFinite(m.y)||m.map!=='Teyvat'||!(m.x>=-1450&&m.x<=-1000&&m.y>=1680&&m.y<=2050||m.x>=-900&&m.x<=-670&&m.y>=2230&&m.y<=2380||finalWindmill)))return null;
  if(h.groundControls&&h.world)return {kind:'groundOrFalling',timer};
  if(h.groundControls===false&&rows.some(r=>r.text==='Space'&&r.x>=1600&&r.y>=980))return {kind:'airborne',timer};
  return null;
 }
 async function run(initial,p,api,observe){
  let current=initial;const began=api.now(),result={status:'stopped',mode:p.mode,moves:0,launchAttempted:false,questComplete:false};
  function safe(kind){const s=p.afterTrial===true&&p.mode==='ground'?(afterTrial(current,api.now(),initial.session,true)?{kind:'groundOrFalling'}:null):state(current,api.now(),initial.session);if(!s||kind&&s.kind!==kind||api.now()-began>20000)throw new Error('Exam phase, timer, health or deadline changed');api.check();return s;}
  try{
   safe(['inspect','abandonInspect'].includes(p.mode)?null:['flight','course'].includes(p.mode)?'airborne':'groundOrFalling');
   if(p.mode==='abandonInspect'){await api.key('VK_P',60,current);await api.sleep(450);current=await observe();result.modalInspection=true;result.reason='Challenge recovery inspection';result.fieldFrameId=current.frameId;return result;}
   if(p.dx||p.dy){await api.look(p.dx,p.dy,current);await api.sleep(180);current=await observe();safe(['flight','course'].includes(p.mode)?'airborne':'groundOrFalling');}
   if(p.mode==='launch'||p.mode==='stepDown'){
    safe('groundOrFalling');result.launchAttempted=true;
    const anchors=p.mode==='stepDown'?[[-701.28516,2347.00391],[-772.97266,2242.87988],[-777.04102,2241.99414]]:[[-1309.11914,1722.0918],[-751.44141,2306.28320]];
    const towerClearance=p.mode==='stepDown'&&current.map&&Math.hypot(current.map.x+777.359375,current.map.y-2240.9375)<=0.5&&current.map.cameraAngle>=335&&current.map.cameraAngle<=355;
    if(!current.map||!(towerClearance||anchors.some(p=>Math.hypot(current.map.x-p[0],current.map.y-p[1])<=(p[0]===-777.04102?0.75:3))))throw Error('Reviewed exam start platform required for takeoff');
    if(typeof api.launch!=='function')throw Error('Fast local takeoff adapter required');
    result.deployment=await api.launch(p.stationary===true);current=await observe();
    if(p.mode==='stepDown'){result.reason='Reviewed low cathedral railing crossing ended; verify ground and health';result.fieldFrameId=current.frameId;return result;}
    if(!result.deployment.opened){result.reason='Deployment unverified; immediate pause requested';result.fieldFrameId=current.frameId;return result;}
   }
   if(p.mode==='open'){safe('groundOrFalling');await api.key('VK_SPACE',60,current);await api.sleep(250);current=await observe();}
   if(p.mode==='course'){safe('airborne');result.course=await api.course();result.reason=result.course.reason;result.fieldFrameId=current.frameId;return result;}
   if(p.mode==='flight'&&p.holds>0&&typeof api.fly==='function'){
    safe('airborne');result.flight=await api.fly(p.stationary===true?'HOVER':p.backward===true?'VK_S':'VK_W',p.holds*600);result.moves=p.holds;
    current=await observe();result.fieldFrameId=current.frameId;result.phase=state(current,api.now(),initial.session);result.health=current.hud.health;result.reason='Bounded continuous flight ended; inspect checkpoint';return result;
   }
   for(let i=0;i<p.holds;i++){
    safe(p.mode==='flight'||p.mode==='launch'||p.mode==='open'?'airborne':'groundOrFalling');
    const marker=current.hud.worldMarker;
    if((p.mode==='flight'||p.mode==='launch'||p.mode==='open')&&marker&&Number.isFinite(marker.x)&&Math.abs(marker.x-960)>70){
     await api.look(Math.max(-100,Math.min(100,Math.round((marker.x-960)*.45))),0,current);await api.sleep(150);current=await observe();safe('airborne');
    }
    await api.key('VK_W',600,current);result.moves++;await api.sleep(150);current=await observe();
   }
   result.reason='Bounded exam segment ended; inspect fresh phase';
  }catch(e){result.reason=String(e.message||e);}
  finally{api.release();}
  result.fieldFrameId=current.frameId;result.phase=state(current,api.now(),initial.session);result.health=current.hud.health;return result;
 }
 function fastState(sample,rows,completed){
  const hp=sample&&sample.health;
  if(!sample||!sample.space||!hp||hp.max!==4015||hp.current<4015*.9||hp.current>4015)return false;
  if(!rows.some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(r.text)))return false;
  if(completed===true)return rows.some(r=>String(r.text).trim()==='Talk to Amber'&&r.x<650&&r.y>=230&&r.y<=350)&&!rows.some(r=>r.text.includes('Abandon Challenge')||r.x>=850&&r.x<=1100&&r.y>=20&&r.y<=100&&/^\d{1,2}:\d{2}$/.test(r.text.trim()));
  if(!rows.some(r=>r.x<750&&r.y>=230&&r.y<=350&&['Reachthetargetlocationwithin180seconds','Reachthetargetlocationwithin60','Reachthetargetlocationwithin60seconds'].includes(String(r.text).replace(/[^A-Za-z0-9]/g,''))))return false;
  const ts=rows.filter(r=>r.x>=850&&r.x<=1100&&r.y>=20&&r.y<=100&&/^\d{1,2}:\d{2}$/.test(r.text.trim()));
  if(ts.length!==1)return false;
  const t=ts[0].text.trim().split(':').reduce((a,b)=>a*60+Number(b),0);
  const finalStage=rows.some(r=>r.x<750&&r.y>=230&&r.y<=350&&['Reachthetargetlocationwithin60','Reachthetargetlocationwithin60seconds'].includes(String(r.text).replace(/[^A-Za-z0-9]/g,'')));return t>=(finalStage?5:12)&&t<=(finalStage?60:180);
 }
 function distance(rows){const hits=rows.map(r=>String(r.text).replace(/\s/g,'')).filter(t=>/^\d{1,3}m$/.test(t));return hits.length===1&&parseInt(hits[0],10)<=100?parseInt(hits[0],10):null;}
 function distanceCrop(marker){if(!marker||!Number.isFinite(marker.x)||!Number.isFinite(marker.y))return null;const box={x:Math.round(marker.x-35),y:Math.round(marker.y+18),width:70,height:32};return box.x>=0&&box.y>=0&&box.x+70<=1920&&box.y+32<=1080?box:null;}
 root.ActTwoExam={plan,state,run,recoveryTarget,fastState,distance,distanceCrop,afterTrial};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoExam;
})(typeof globalThis!=='undefined'?globalThis:this);
