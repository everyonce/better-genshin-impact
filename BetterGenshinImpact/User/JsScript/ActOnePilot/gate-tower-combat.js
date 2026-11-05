(function(root){
 'use strict';
 // Only the surveyed Mondstadt platform has a verified elevated target and clear firing lane.
 // Both ends of the firing lane were measured in live captures of the same elevated platform.
 function firingLane(p){
  if(!p||p.map!=='Teyvat')return false;
  const dx=-1186.1875+1181.3418,dy=2206.2676-2194.7031;
  const t=Math.max(0,Math.min(1,((p.x+1181.3418)*dx+(p.y-2194.7031)*dy)/(dx*dx+dy*dy)));
  return Math.hypot(p.x+1181.3418-t*dx,p.y-2194.7031-t*dy)<=3.5;
 }
 function pose(o){
  const p=o&&o.map;
  return !!(p&&p.map==='Teyvat'&&(firingLane(p)||Math.hypot(p.x+1186.1875,p.y-2206.267578125)<=5.5)&&
   Number.isFinite(p.cameraAngle));
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
 // The active slot's key is dim. If full OCR misses a benched key as well, the two named
 // rows must independently match the measured active/benched layout of this English party.
 function party(o,active){
  const k2=row(o,'2',1840,1900,330,410),k3=row(o,'3',1840,1900,420,480);
  if(row(o,'Amber',1640,1810,330,410)!==1||row(o,'Kaeya',1640,1810,420,480)!==1)return false;
  if(active==='Kaeya')return o.hud.health.max===4015&&k3===0&&(k2===1||k2===0&&
   row(o,'Amber',1683,1700,340,352)===1&&row(o,'Kaeya',1658,1678,443,456)===1);
  return o.hud.health.max!==4015&&k2===0&&(k3===1||k3===0&&o.hud.health.max===1809&&
   row(o,'Amber',1656,1674,350,363)===1&&row(o,'Kaeya',1686,1705,428,442)===1);
 }
 function bar(o){
  const bars=o&&o.hud&&o.hud.enemyBars,visible=Array.isArray(bars)&&bars.length===1&&bars[0];
  if(!visible||visible.damageTrail)return null;
  // A nearly defeated archer can expose only a red tip. Use the native detector's independently
  // located level/rail, or the same ground capture's level, and always measure the actual red fill.
  const rail=visible.depletedRail,b=rail?rail.remainingRed:visible;
  if(!b||![b.x,b.y,b.width,b.height,b.rectangularity].every(Number.isFinite)||b.x<780||b.x>1280||
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
 function candidate(o,api){
  if(!base(o,api)||!party(o,'Kaeya')&&!party(o,'Amber'))return false;
  const b=bar(o),yaw=(o.map.cameraAngle-292.5+540)%360-180;
  if(api.aimed&&b&&firingLane(o.map)&&Math.abs(yaw)<=38&&b.y<=265)return true;
  if(!b||Math.hypot(o.map.x+1186.1875,o.map.y-2206.267578125)>3||yaw< -19||yaw>12)return false;
  // The post-hit 278-degree view still presents the same high platform to the right.
  return yaw>=-12&&b.x<=1150||Math.abs(b.x-(1036-7*yaw))<=90;
 }
 // The verified 64-to-41 hit started at 292.5 degrees with red left edge x=1004.
 // A damaged bar gets shorter from the right; its left edge remains the projection reference.
 function firingError(o){
  const b=bar(o);
  return b?{yaw:(o.map.cameraAngle-292.5+540)%360-180,x:b.x-b.width/2-1004}:null;
 }
 function aligned(o){
  const e=firingError(o);return !!(e&&Math.abs(e.yaw)<=5&&Math.abs(e.x)<=60);
 }
 function sameTurningTarget(before,after){
  const a=bar(before),b=bar(after);
  if(!a||!b||!recoilPose(before,after)||Math.abs(a.width-b.width)>6||Math.abs(a.y-b.y)>28)return false;
  const yaw=(after.map.cameraAngle-before.map.cameraAngle+540)%360-180;
  const travel=-Math.sign(yaw)*((b.x-b.width/2)-(a.x-a.width/2));
  return Math.abs(a.height-b.height)<=3&&travel>=-22&&travel<=Math.abs(yaw)*25+28;
 }
 function samePose(a,b){
  return pose(a)&&pose(b)&&Math.hypot(a.map.x-b.map.x,a.map.y-b.map.y)<=1.25&&
   Math.abs((a.map.cameraAngle-b.map.cameraAngle+540)%360-180)<=4;
 }
 function associated(a,b,limit){
  return !!(a&&b&&Math.abs((a.x-a.width/2)-(b.x-b.width/2))<=limit&&Math.abs(a.y-b.y)<=limit&&Math.abs(a.height-b.height)<=2);
 }
 // A normal shot visibly rotated the camera 11–14.5 degrees without moving Amber.
 // Credit moving-screen damage only when its red edge follows that turn AND the gold fill
 // touches it and reconstructs the former bar length on the very same native shot.
 function recoilPose(before,after){
  return pose(before)&&pose(after)&&Math.hypot(before.map.x-after.map.x,before.map.y-after.map.y)<=1.25&&
   Math.abs((after.map.cameraAngle-before.map.cameraAngle+540)%360-180)<=18;
 }
 function recoilDamage(before,after,id){
  const a=bar(before),b=bar(after),g=b&&b.towerDamageTail;
  if(!a||!b||!g||typeof id!=='string'||g.actionId!==id||!recoilPose(before,after)||
     ![g.x,g.y,g.width,g.height,g.rectangularity].every(Number.isFinite))return false;
  const dyaw=(after.map.cameraAngle-before.map.cameraAngle+540)%360-180;
  const x0=a.x-a.width/2,x1=b.x-b.width/2,gap=g.x-g.width/2-(x1+b.width);
  return Math.abs(x1-x0+7*dyaw)<=24&&Math.abs(a.y-b.y)<=12&&Math.abs(a.height-b.height)<=2&&
   a.width-b.width>=Math.max(8,a.width*.12)&&g.width>=16&&g.rectangularity>=.85&&g.rectangularity<=1.05&&
   gap>=0&&gap<=3&&Math.abs(g.y-b.y)<=2&&Math.abs(g.height-b.height)<=2&&
   Math.abs(a.width-(b.width+gap+g.width))<=Math.max(8,a.width*.14);
 }
 // Different character models can shift the camera slightly on a switch. Impact uses the same Amber pose.
 function feedback(before,after,api,id){
  if(!base(after,api)||!party(after,'Amber')||Math.hypot(before.map.x-after.map.x,before.map.y-after.map.y)>1.25||before.hud.health.max!==after.hud.health.max)return 'unconfirmed';
  if(scan(after,'clear',0)&&api.rewards(before,after).some(r=>/^(?:Obtained\s+)?Character EXP\s*(?:[×x+·]\s*)?[1-9][0-9]{0,4}$/i.test(r.text.trim())))return 'defeat';
  if(!recoilPose(before,after))return 'unconfirmed';
  if(scan(after,'threat',1)&&recoilDamage(before,after,id))return 'damage';
  if(!samePose(before,after))return 'unconfirmed';
  const a=bar(before),b=bar(after);
  if(scan(after,'threat',1)&&associated(a,b,12)&&a.height===b.height&&a.width-b.width>=Math.max(8,a.width*.12))return 'damage';
  return 'unconfirmed';
 }
 // Bow aiming uses the center reticle. Follow the level label or the left edge of the full rail,
 // since the center of the remaining red fill moves sideways as the archer takes damage.
 function aimTarget(frame, priorWidth){
  const regions=frame.hud.bowAimBars||[], labels=(frame.ocr||[]).filter(r=>/^Lv[.,]?\s*1$/i.test(r.text.trim()));
  const choices=regions.map(b=>{
   const nearby=labels.filter(r=>Math.abs(r.x+r.width/2-b.left-32)<48&&b.y-r.y-r.height/2>4&&b.y-r.y-r.height/2<55);
   const full=Math.max(priorWidth||66,b.width);
   return {x:nearby.length===1?nearby[0].x+nearby[0].width/2:b.left+full/2,
    y:b.y+55,barY:b.y,width:b.width,full:full,label:nearby.length===1};
  });
  const named=choices.filter(c=>c.label);
  return named.length===1?named[0]:choices.length===1?choices[0]:null;
 }
 function aimMode(frame){
  const h=frame.hud,rows=frame.ocr||[];
  return !h.bigMap&&!h.journal&&!h.choice&&!h.auto&&!h.groundControls&&
   rows.some(r=>r.text.trim()==='R'&&r.x>1640&&r.x<1810&&r.y>975&&r.y<1060);
 }
 // Toggle the bow sight, correct both screen axes and release only when the target is under the reticle.
 // Keep the returned observations and real control timings together for the combat receipt.
 async function aimedVolley(initial,api){
  let frame=initial,entered=false,attempted=false,lastMove=null,since=0,full=Math.max(66,bar(initial).width);
  const trace={samples:[],shots:[]},gain={x:1.6,y:.6};
  const start=api.now(),end=api.deadline-3200;
  async function sample(delay){
   api.checkStop();await api.sleep(delay);const next=await api.observe(),s=next.hud.captureStamp;
   if(next.session!==initial.session||next.frameId<=frame.frameId||!s||s.capturedAt<=frame.hud.captureStamp.capturedAt||
      !api.original(next)||api.now()-next.timestamp>1200)throw Error('Lost current bow capture');
   frame=next;return frame;
  }
  try{
   await api.key('VK_R',frame);entered=true;since=api.now();await sample(350);
   let missing=0,groundRetries=0,emptyAfterShot=0;
   while(api.now()<end&&trace.samples.length<22){
    const hp=frame.hud.health;
    if(!hp||hp.max!==initial.hud.health.max||hp.current<hp.max*.65)throw Error('Amber health unavailable in bow sight');
    const sight=aimMode(frame),target=aimTarget(frame,full);
    const entry={frameId:frame.frameId,sight:sight,hp:hp.current,target:target};trace.samples.push(entry);
    if(!sight){
     if(base(frame,api)&&party(frame,'Amber')&&target&&groundRetries++<2){
      // Enemy attacks can knock Amber out of aiming. Re-enter only from her actual ground HUD.
      await api.key('VK_R',frame);since=api.now();lastMove=null;await sample(300);continue;
     }
     if(trace.shots.length)break;
     throw Error('Amber bow sight not confirmed');
    }
    if(!target){
     if(trace.shots.length){if(++emptyAfterShot>=2)break;await sample(160);continue;}
     if(++missing>3)throw Error('Elevated target unavailable in bow sight');
     api.look(0,-110,frame);entry.searchDy=-110;await sample(150);continue;
    }
    emptyAfterShot=0;missing=0;full=Math.max(full,target.width);
    const error={x:target.x-960,y:target.y-540};
    if(lastMove){
     for(const axis of ['x','y']){
      const observed=(lastMove.error[axis]-error[axis])/lastMove.delta[axis];
      if(Math.abs(lastMove.delta[axis])>=12&&observed>.15&&observed<5)gain[axis]=observed;
     }
    }
    lastMove=null;
    if(Math.abs(error.x)>12||Math.abs(error.y)>14){
     const clip=(value,limit)=>Math.max(-limit,Math.min(limit,Math.round(value)));
     const delta={x:clip(error.x/gain.x,175),y:clip(error.y/gain.y,155)};
     api.look(delta.x,delta.y,frame);entry.delta=delta;lastMove={error,delta};await sample(145);continue;
    }
    if(api.now()-since<1500){await sample(Math.min(450,1500-(api.now()-since)));continue;}
    if(trace.shots.length===3)break;
    const shot={frameId:frame.frameId,width:target.width,startedAt:api.now()};
    await api.shoot(frame);shot.finishedAt=api.now();attempted=true;trace.shots.push(shot);since=shot.finishedAt;
    await sample(300);
   }
  }catch(e){trace.error=String(e&&e.message||e);}
  finally{
   if(entered){
    // R is a toggle. An enemy stagger may already have closed the sight.
    if(aimMode(frame)){await api.key('VK_R',frame);await api.sleep(200);}
   }
  }
  return {nativeReturned:attempted,nativeMs:api.now()-start,aim:trace};
 }
 // Select Amber and bind the shot to the same stationary hostile; the live adapter uses the bow sight.
 async function run(initial,index,api){
  const result={assessment:'unconfirmed',restored:false,switched:false},turns=[];
  let current=initial,restoreActiveAmber=false;
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
   if(!candidate(current,api))throw Error('Healthy recognized party member and one surveyed tower target required');
   const startAvatar=party(current,'Kaeya')?'Kaeya':'Amber';result.startedAs=startAvatar;
   // The red rail vanishes briefly during the enemy's attack. Reacquire the same
   // hostile at the same pose before switching; an empty capture never permits a shot.
   let repeated=false;
   for(let probe=0;probe<(api.aimed?4:1);probe++){
    await fresh(probe?150:100);
    if(!base(current,api)||initial.hud.health.max!==current.hud.health.max||!samePose(initial,current))break;
    if(!party(current,startAvatar))continue;
    repeated=candidate(current,api)&&scan(current,'threat',1)&&associated(bar(initial),bar(current),40);
    if(repeated||bar(current)&&!associated(bar(initial),bar(current),40))break;
   }
   if(!repeated)throw Error('Tower hostile did not repeat on the independent ground scan');
   const anchor=current;
   if(startAvatar==='Kaeya'){
    await api.key('VK_2',current);result.switched=true;
    for(let probe=0;probe<3;probe++){await fresh(probe?150:400);if(base(current,api)&&party(current,'Amber'))break;}
    if(base(current,api)&&party(current,'Amber')&&row(current,'3',1840,1900,420,480)===0){
     // Repeat the geometric fallback after the switch animation on a second real capture.
     const selected=current;await fresh(120);
     if(!samePose(selected,current)||!scan(selected,'threat',1)||!associated(bar(selected),bar(current),18))
      throw Error('Selected Amber and tower target did not repeat');
    }
   }else{restoreActiveAmber=true;}
   budget(5200);
   if(api.aimed){
    for(let probe=0;probe<3&&!bar(current)&&base(current,api)&&party(current,'Amber')&&samePose(anchor,current);probe++)await fresh(140);
   }
   if(!base(current,api)||!party(current,'Amber')||!samePose(anchor,current)||!scan(current,'threat',1)||!associated(bar(anchor),bar(current),60))
    throw Error('Healthy active Amber and the same elevated hostile required');
   if(!api.aimed&&!aligned(current)){
    result.alignment=[];
    for(let attempt=0;attempt<2&&!aligned(current);attempt++){
     budget(6200);
     const before=current,e=firingError(before),coarse=Math.abs(e.yaw)>3;
     // Use the shared navigation heading convention for the coarse return and a small
     // visual trim confined to four degrees around the observed successful direction.
     const error=coarse?e.yaw:e.yaw-Math.max(-4,Math.min(4,e.yaw+e.x/12));
     if(Math.abs(error)<1.5||Math.abs(error)>19)throw Error('Tower target outside the verified firing projection');
     const command=Math.max(-16,Math.min(16,error)),trace={beforeFrameId:before.frameId,yawError:e.yaw,leftError:e.x,requestedDegrees:-command};
     result.alignment.push(trace);trace.dx=await api.turn(command,before);
     await fresh(260);trace.afterFrameId=current.frameId;
     if(!candidate(current,api)||!party(current,'Amber')||current.hud.health.max!==before.hud.health.max||
        !scan(current,'threat',1)||!sameTurningTarget(before,current))
      throw Error('Fresh healthy Amber and continuous tower target required after camera turn');
     const seen=firingError(current);trace.observedYawError=seen.yaw;trace.observedLeftError=seen.x;
     if(!aligned(current)&&(coarse?Math.abs(seen.yaw)>Math.abs(e.yaw)-2:Math.abs(seen.x)>Math.abs(e.x)-8))
      throw Error('Tower camera turn did not improve the measured alignment');
    }
    if(!aligned(current))throw Error('Tower target stayed outside the verified firing projection');
    const alignedFrame=current;await fresh(120);
    if(!candidate(current,api)||!party(current,'Amber')||!scan(current,'threat',1)||!samePose(alignedFrame,current)||
       !associated(bar(alignedFrame),bar(current),25)||!aligned(current)||current.hud.health.max!==alignedFrame.hud.health.max)
     throw Error('Calibrated tower firing alignment did not repeat on a new capture');
    budget(5200);
   }
   const before=current,turn={actionId:api.actionId(index),beforeFrameId:before.frameId,beforeHealth:before.hud.health,
    beforeBars:[bar(before)],nativeAttempted:true,nativeReturned:false,startedAt:api.now()};turns.push(turn);
   try{Object.assign(turn,await api.fire(before,index));}finally{turn.finishedAt=api.now();}
   if(turn.nativeReturned!==true)throw Error(turn.aim&&turn.aim.error||'Native Amber shot did not return');
   for(let probe=0;probe<3;probe++){
    await fresh(probe?180:350);result.assessment=feedback(before,current,api,turn.actionId);
    if(result.assessment!=='unconfirmed'||!base(current,api)||!recoilPose(before,current)||before.hud.health.max!==current.hud.health.max)break;
   }
   turn.afterFrameId=current.frameId;turn.afterHealth=current.hud.health;turn.afterBars=bar(current)?[bar(current)]:[];
   turn.assessment={status:result.assessment,evidence:result.assessment==='damage'?
    (recoilDamage(before,current,turn.actionId)?'tracked_red_fill_and_adjacent_gold_tail':'same_target_red_fill_loss'):
    result.assessment==='defeat'?'new_character_exp_and_clear_ground':null};
   result.impactFrameId=current.frameId;
  }catch(e){result.error=String(e&&e.message||e);}
  finally{
   if(result.switched||restoreActiveAmber){try{
    // An impact animation can hide the active name in one capture. Only observe until a
    // healthy named party member is visible again; never send a roster key on an ambiguous frame.
    for(let probe=0;probe<3;probe++){
     await fresh(probe?150:100);
     if(!base(current,api)||party(current,'Amber')||party(current,'Kaeya'))break;
    }
    if(base(current,api)&&party(current,'Amber')){
     await api.key('VK_3',current);
     for(let probe=0;probe<3;probe++){await fresh(probe?150:400);if(base(current,api)&&party(current,'Kaeya'))break;}
    }
    result.restored=base(current,api)&&party(current,'Kaeya');
   }catch(e){result.error=result.error||String(e&&e.message||e);}}
  }
  return {current,turns,result};
 }
 root.GateTowerCombat={candidate,base,party,bar,scan,samePose,aligned,aimMode,aimTarget,aimedVolley,feedback,run};
 if(typeof module!=='undefined'&&module.exports)module.exports=root.GateTowerCombat;
})(typeof globalThis!=='undefined'?globalThis:this);
