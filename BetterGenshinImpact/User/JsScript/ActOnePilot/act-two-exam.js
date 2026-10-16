(function(root){
 'use strict';
 function recoveryTarget(o,now,session){
  const rows=o&&o.ocr||[],h=o&&o.hud,hp=h&&h.health;
  const one=(text,x0,x1,y0,y1)=>rows.filter(r=>r.text===text&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1);
  if(!o||o.session!==session||now<o.timestamp||now-o.timestamp>1000||!hp||![2451,4015].includes(hp.max)||hp.current<hp.max*.9||hp.current>hp.max||!rows.some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(r.text))||one('Abandon Challenge',700,850,250,330).length!==1||one('Abandon Challenge?',750,900,470,550).length!==1||one('Cancel',650,850,700,790).length!==1)return null;
  const c=one('Confirm',1050,1250,700,790);return c.length===1?{x:c[0].x+c[0].width/2,y:c[0].y+c[0].height/2}:null;
 }
 function plan(p,r,now){return !!(p&&p.reviewed===true&&(p.stationary===undefined||p.stationary===true&&['launch','flight'].includes(p.mode)&&!p.backward)&&(p.backward===undefined||p.backward===true&&p.mode==='flight')&&!p.usedAt&&p.session===r.session&&p.frameId===r.expectedFrameId&&Number.isInteger(p.witnessFrameId)&&p.witnessFrameId<p.frameId&&now>=p.createdAt&&now-p.createdAt<=120000&&['inspect','ground','launch','open','flight','course','abandonInspect'].includes(p.mode)&&Number.isInteger(p.dx)&&Math.abs(p.dx)<=750&&Number.isInteger(p.dy)&&Math.abs(p.dy)<=500&&Number.isInteger(p.holds)&&p.holds>=0&&p.holds<=4&&(!['inspect','abandonInspect'].includes(p.mode)||p.holds===0));}
 function state(o,now,session){
  const h=o&&o.hud,hp=h&&h.health,m=o&&o.map,rows=o&&o.ocr||[];
  const objective=rows.some(r=>r.x<650&&r.y>=230&&r.y<=350&&['Followtherouteandflytothefinish','Reachthetargetlocationwithin180seconds'].includes(String(r.text).replace(/[^A-Za-z0-9]/g,'')));
  const timers=rows.filter(r=>r.x>=850&&r.x<=1100&&r.y>=20&&r.y<=100&&/^\d{1,2}:\d{2}$/.test(String(r.text).trim()));
  const timer=timers.length===1?timers[0].text.trim().split(':').reduce((a,b)=>a*60+Number(b),0):null;
  if(!o||o.session!==session||!Number.isInteger(o.frameId)||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||!h||h.auto||h.choice||h.dialogueReady||h.journal||h.bigMap||h.climbing||!hp||![4015,2451].includes(hp.max)||hp.current<hp.max*.9||hp.current>hp.max||!objective||timer===null||timer<5||timer>180||!rows.some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(r.text))||!Array.isArray(h.enemyBars)||h.enemyBars.length)return null;
  if(m&&(!Number.isFinite(m.x)||!Number.isFinite(m.y)||m.map!=='Teyvat'||m.x< -1450||m.x> -1000||m.y<1680||m.y>2050))return null;
  if(h.groundControls&&h.world)return {kind:'groundOrFalling',timer};
  if(h.groundControls===false&&rows.some(r=>r.text==='Space'&&r.x>=1600&&r.y>=980))return {kind:'airborne',timer};
  return null;
 }
 async function run(initial,p,api,observe){
  let current=initial;const began=api.now(),result={status:'stopped',mode:p.mode,moves:0,launchAttempted:false,questComplete:false};
  function safe(kind){const s=state(current,api.now(),initial.session);if(!s||kind&&s.kind!==kind||api.now()-began>20000)throw new Error('Exam phase, timer, health or deadline changed');api.check();return s;}
  try{
   safe(p.mode==='abandonInspect'?null:['flight','course'].includes(p.mode)?'airborne':'groundOrFalling');
   if(p.mode==='abandonInspect'){await api.key('VK_P',60,current);await api.sleep(450);current=await observe();result.modalInspection=true;result.reason='Challenge recovery inspection';result.fieldFrameId=current.frameId;return result;}
   if(p.dx||p.dy){await api.look(p.dx,p.dy,current);await api.sleep(180);current=await observe();safe(['flight','course'].includes(p.mode)?'airborne':'groundOrFalling');}
   if(p.mode==='launch'){
    safe('groundOrFalling');result.launchAttempted=true;
    if(!current.map||Math.hypot(current.map.x+1309.11914,current.map.y-1722.0918)>3)throw Error('Reviewed exam start platform required for takeoff');
    if(typeof api.launch!=='function')throw Error('Fast local takeoff adapter required');
    result.deployment=await api.launch(p.stationary===true);current=await observe();
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
 function fastState(sample,rows){
  const hp=sample&&sample.health;
  if(!sample||!sample.space||!hp||hp.max!==4015||hp.current<4015*.9||hp.current>4015)return false;
  if(!rows.some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(r.text)))return false;
  if(!rows.some(r=>r.x<750&&r.y>=230&&r.y<=350&&String(r.text).replace(/[^A-Za-z0-9]/g,'')==='Reachthetargetlocationwithin180seconds'))return false;
  const ts=rows.filter(r=>r.x>=850&&r.x<=1100&&r.y>=20&&r.y<=100&&/^\d{1,2}:\d{2}$/.test(r.text.trim()));
  if(ts.length!==1)return false;
  const t=ts[0].text.trim().split(':').reduce((a,b)=>a*60+Number(b),0);
  return t>=12&&t<=180;
 }
 function distance(rows){const hits=rows.map(r=>String(r.text).replace(/\s/g,'')).filter(t=>/^\d{1,3}m$/.test(t));return hits.length===1&&parseInt(hits[0],10)<=100?parseInt(hits[0],10):null;}
 function distanceCrop(marker){if(!marker||!Number.isFinite(marker.x)||!Number.isFinite(marker.y))return null;const box={x:Math.round(marker.x-35),y:Math.round(marker.y+18),width:70,height:32};return box.x>=0&&box.y>=0&&box.x+70<=1920&&box.y+32<=1080?box:null;}
 root.ActTwoExam={plan,state,run,recoveryTarget,fastState,distance,distanceCrop};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoExam;
})(typeof globalThis!=='undefined'?globalThis:this);
