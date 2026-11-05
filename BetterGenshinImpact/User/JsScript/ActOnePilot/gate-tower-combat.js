(function(root){
 'use strict';
 // Only the surveyed Mondstadt platform has a verified elevated target and clear firing lane.
 function pose(o){
  const p=o&&o.map;
  return !!(p&&p.map==='Teyvat'&&Math.hypot(p.x+1186.1875,p.y-2206.267578125)<=5.5&&
   Number.isFinite(p.cameraAngle)&&Math.abs((p.cameraAngle-292.5+540)%360-180)<=12);
 }
 function base(o,api){
  const h=o&&o.hud,p=h&&h.health,s=h&&h.captureStamp,now=api.now();
  return !!(pose(o)&&!o.fastSample&&!o.mapPositionInherited&&o.session===api.session&&api.original(o)&&
   Number.isInteger(o.frameId)&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&
   s&&s.session===o.session&&s.frameId===o.frameId&&s.source==='game-capture-start'&&Number.isInteger(s.capturedAt)&&
   s.capturedAt<=o.timestamp&&now-s.capturedAt<=2000&&h.world===true&&h.groundControls===true&&h.climbing===false&&
   !h.auto&&!h.loading&&!h.swimming&&!h.interact&&!h.choice&&!h.journal&&!h.bigMap&&!h.lowHealth&&!h.unknownHud&&
   !h.dialogueReady&&!h.tutorialStep&&Array.isArray(h.objectives)&&h.objectives.every(t=>typeof t==='string'&&!t.trim())&&
   p&&Number.isInteger(p.current)&&Number.isInteger(p.max)&&p.max>0&&p.current>=p.max*.90&&p.current<=p.max);
 }
 function row(o,text,x1,x2,y1,y2){
  return (o.ocr||[]).filter(r=>String(r.text).trim()===text&&r.x>=x1&&r.x<=x2&&r.y>=y1&&r.y<=y2).length;
 }
 // The active party member lacks its switch key. Require the other member's actual key as positive evidence.
 function party(o,active){
  const k2=row(o,'2',1840,1900,330,410),k3=row(o,'3',1840,1900,420,480);
  return row(o,'Amber',1640,1810,330,410)===1&&row(o,'Kaeya',1640,1810,420,480)===1&&
   (active==='Kaeya'?k2===1&&k3===0&&o.hud.health.max===4015:k3===1&&k2===0&&o.hud.health.max!==4015);
 }
 function bar(o){
  const bars=o&&o.hud&&o.hud.enemyBars,visible=Array.isArray(bars)&&bars.length===1&&bars[0];
  if(!visible||visible.damageTrail)return null;
  // A nearly defeated archer can expose only a red tip. Use the native detector's independently
  // located level/rail, or the same ground capture's level, and always measure the actual red fill.
  const rail=visible.depletedRail,b=rail?rail.remainingRed:visible;
  if(!b||![b.x,b.y,b.width,b.height,b.rectangularity].every(Number.isFinite)||b.x<780||b.x>1150||
     b.y<120||b.y>270||b.width<2||b.width>110||b.height<3||b.height>9||b.rectangularity<.8||b.rectangularity>1.05)return null;
  if(!rail&&b.width>=16&&b.width/b.height>=3.5)return b;
  const labels=rail?[rail.level]:(o.ocr||[]);
  return labels.filter(r=>r&&/^Lv[.,]?\s*1$/i.test(String(r.text).trim())&&
   Math.abs(r.x+r.width/2-b.x)<=100&&b.y-(r.y+r.height/2)>=6&&b.y-(r.y+r.height/2)<=50).length===1?b:null;
 }
 function scan(o,state,count){
  const h=o.hud,s=h.enemyBarObservation,d=h.enemyBarDiagnostic;
  return !!(s&&d&&!d.overloaded&&s.version===1&&s.kind==='normal-ground-enemy-observation-v1'&&s.state===state&&
   s.session===o.session&&s.frameId===o.frameId&&s.capturedAt===h.captureStamp.capturedAt&&
   s.candidateCount===count&&s.acceptedCount===count&&Array.isArray(d.fieldCandidates)&&d.fieldCandidates.length===count&&
   Array.isArray(h.enemyBars)&&h.enemyBars.length===count);
 }
 function candidate(o,api){return base(o,api)&&party(o,'Kaeya')&&!!bar(o);}
 function samePose(a,b){
  return pose(a)&&pose(b)&&Math.hypot(a.map.x-b.map.x,a.map.y-b.map.y)<=1.25&&
   Math.abs((a.map.cameraAngle-b.map.cameraAngle+540)%360-180)<=4;
 }
 function associated(a,b,limit){
  return !!(a&&b&&Math.abs((a.x-a.width/2)-(b.x-b.width/2))<=limit&&Math.abs(a.y-b.y)<=limit&&Math.abs(a.height-b.height)<=2);
 }
 // Different character models can shift the camera slightly on a switch. Impact uses the same Amber pose.
 function feedback(before,after,api){
  if(!base(after,api)||!party(after,'Amber')||!samePose(before,after)||before.hud.health.max!==after.hud.health.max)return 'unconfirmed';
  if(scan(after,'clear',0)&&api.rewards(before,after).some(r=>/^(?:Obtained\s+)?Character EXP\s*(?:[×x+·]\s*)?[1-9][0-9]{0,4}$/i.test(r.text.trim())))return 'defeat';
  const a=bar(before),b=bar(after);
  if(scan(after,'threat',1)&&associated(a,b,12)&&a.height===b.height&&a.width-b.width>=Math.max(8,a.width*.12))return 'damage';
  return 'unconfirmed';
 }
 // One normal arrow per request. Only fresh measured impact can permit a later request to fire again.
 async function run(initial,index,api){
  const result={assessment:'unconfirmed',restored:false,switched:false},turns=[];
  let current=initial;
  async function fresh(delay){
   api.checkStop();const earliest=api.now();await api.sleep(delay);const next=await api.observe(),s=next&&next.hud&&next.hud.captureStamp;
   if(!s||s.source!=='game-capture-start'||s.session!==initial.session||s.frameId!==next.frameId||next.session!==initial.session||
      !Number.isInteger(next.frameId)||next.frameId<=current.frameId||!Number.isInteger(s.capturedAt)||s.capturedAt<earliest||
      s.capturedAt<=current.hud.captureStamp.capturedAt)
    throw Error('New tower observation required');
   current=next;return current;
  }
  function budget(ms){api.checkStop();if(api.deadline-api.now()<ms)throw Error('Tower shot deadline reached');}
  try{
   budget(7000);
   if(!candidate(current,api))throw Error('Healthy Kaeya and one surveyed tower target required');
   await fresh(100);
   if(!candidate(current,api)||!scan(current,'threat',1)||!samePose(initial,current)||!associated(bar(initial),bar(current),32))
    throw Error('Tower hostile did not repeat on the independent ground scan');
   const kaeya=current;await api.key('VK_2',current);result.switched=true;
   for(let probe=0;probe<3;probe++){await fresh(probe?150:400);if(base(current,api)&&party(current,'Amber'))break;}
   budget(5200);
   if(!base(current,api)||!party(current,'Amber')||!samePose(kaeya,current)||!scan(current,'threat',1)||!associated(bar(kaeya),bar(current),60))
    throw Error('Healthy active Amber and the same elevated hostile required');
   const before=current,turn={actionId:api.actionId(index),beforeFrameId:before.frameId,beforeHealth:before.hud.health,
    beforeBars:[bar(before)],nativeAttempted:true,nativeReturned:false,startedAt:api.now()};turns.push(turn);
   try{Object.assign(turn,await api.fire(before,index));}finally{turn.finishedAt=api.now();}
   if(turn.nativeReturned!==true)throw Error('Native Amber shot did not return');
   for(let probe=0;probe<3;probe++){
    await fresh(probe?180:350);result.assessment=feedback(before,current,api);
    if(result.assessment!=='unconfirmed'||!base(current,api)||!party(current,'Amber')||!samePose(before,current))break;
   }
   turn.afterFrameId=current.frameId;turn.afterHealth=current.hud.health;turn.afterBars=bar(current)?[bar(current)]:[];
   turn.assessment={status:result.assessment,evidence:result.assessment==='damage'?'same_target_red_fill_loss':
    result.assessment==='defeat'?'new_character_exp_and_clear_ground':null};
   result.impactFrameId=current.frameId;
  }catch(e){result.error=String(e&&e.message||e);}
  finally{
   if(result.switched){try{
    await fresh(100);
    if(base(current,api)&&party(current,'Amber')){await api.key('VK_3',current);await fresh(400);}
    result.restored=base(current,api)&&party(current,'Kaeya');
   }catch(e){result.error=result.error||String(e&&e.message||e);}}
  }
  return {current,turns,result};
 }
 root.GateTowerCombat={candidate,base,party,bar,scan,samePose,feedback,run};
 if(typeof module!=='undefined'&&module.exports)module.exports=root.GateTowerCombat;
})(typeof globalThis!=='undefined'?globalThis:this);
