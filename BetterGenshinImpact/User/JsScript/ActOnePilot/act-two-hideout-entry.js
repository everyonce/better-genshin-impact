(function(root){
 'use strict';
 function entryTarget(o,now,session){
  const h=o&&o.hud,rows=o&&o.ocr||[];
  if(!o||o.session!==session||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!h||h.world||h.health||h.groundControls||h.climbing||h.auto||h.dialogueReady||h.choice||h.journal||h.bigMap)return null;
  const unique=(text,x0,x1,y0,y1)=>rows.filter(r=>String(r.text).trim()===text&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1);
  if(unique('Domain Entrance',120,160,20,45).length!==1||unique('The Reward for Courage Is Flight',40,75,140,180).length!==1||unique('The Reward for Courage Is Flight',1250,1300,135,175).length!==1||unique('Recommended Party Level: 4',40,80,195,225).length!==1||unique('Recommended Elements',920,960,385,420).length!==1||unique('Possible Rewards',920,960,440,475).length!==1||!rows.some(r=>/^UID:\s*693306810$/.test(r.text)&&r.x>1600&&r.y>1030))return null;
  const starts=unique('Start',1660,1710,980,1025);if(starts.length!==1)return null;
  return {x:Math.round(starts[0].x+starts[0].width/2),y:Math.round(starts[0].y+starts[0].height/2),label:'The Reward for Courage Is Flight'};
 }
 function partyTarget(o,now,session,reports){
  const h=o&&o.hud,rows=o&&o.ocr||[];
  if(!o||o.session!==session||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!h||h.world||h.health||h.auto||h.dialogueReady||h.choice||h.journal||h.bigMap||!Array.isArray(reports))return null;
  const one=(text,x0,x1,y0,y1)=>rows.filter(r=>String(r.text).trim().replace(/\s/g,'')===text.replace(/\s/g,'')&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1).length===1;
  if(!one('Recommended Elements',100,155,20,55)||!one('Team Standing By',100,150,990,1040)||!one('Quick Setup',1240,1300,990,1040)||!rows.some(r=>/^(?:UID|JID):\s*693306810$/.test(r.text)&&r.x>1600&&r.y>1030))return null;
  for(const [name,level,x0,x1,y0,y1] of [['Lumina',17,370,550,280,365],['Amber',7,720,850,320,390],['Kaeya',20,1050,1200,255,335],['Lisa',2,1390,1520,245,325]])if(!one(name,x0,x1,y0,y1)||!one('Lv.'+level,x0,x1,y0,y1))return null;
  const prior=reports.filter(r=>r&&r.session===session&&r.mission==='questStep'&&r.status==='completed'&&r.details&&r.details.result&&r.details.result.step==='actTwoHideoutStart'&&Number.isFinite(r.timestamp)&&r.timestamp<=o.timestamp&&now-r.timestamp<=300000&&Array.isArray(r.details.inputEvents)&&r.details.inputEvents.filter(e=>e.type==='actTwoHideoutStart').length===1).pop();
  if(!prior||reports.some(r=>r&&r.session===session&&r.timestamp>=prior.timestamp&&r.details&&Array.isArray(r.details.inputEvents)&&r.details.inputEvents.some(e=>e.type==='actTwoHideoutPartyStart')))return null;
  const a=rows.filter(r=>r.text.trim()==='Start'&&r.x>=1640&&r.x<=1700&&r.y>=990&&r.y<=1030);return a.length===1?{x:Math.round(a[0].x+a[0].width/2),y:Math.round(a[0].y+a[0].height/2)}:null;
 }
 function tutorialTarget(o,now,session){
  const h=o&&o.hud,rows=o&&o.ocr||[],hp=h&&h.health;
  if(!o||o.session!==session||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||!h||h.auto||h.dialogueReady||h.choice||h.journal||h.bigMap||h.climbing||!hp||hp.max!==2764||hp.current!==2764)return null;
  const line=rows.filter(r=>r.text==='Use the nearby Wind Currents to keep yourself afloat while evading enemy'&&r.x>=380&&r.x<=450&&r.y>=770&&r.y<=810),end=rows.filter(r=>r.text==='attacks.'&&r.x>=890&&r.x<=940&&r.y>=815&&r.y<=850);
  const bombs=rows.filter(r=>r.text==='While gliding, you can drop bombs. Defeat all opponents this way.'&&r.x>=460&&r.x<=510&&r.y>=770&&r.y<=810);
  const wind=line.length===1&&end.length===1;
  if((!wind&&bombs.length!==1)||!rows.some(r=>r.text==='Lumina'&&r.x>1600&&r.y>=380&&r.y<=440)||!rows.some(r=>/^UID:\s*693306810$/.test(r.text)&&r.x>1600&&r.y>1030))return null;
  return {x:960,y:1020,label:wind?'Wind Currents aerial combat tutorial':'Gliding bomb attack tutorial'};
 }
 root.ActTwoHideoutEntry={entryTarget,partyTarget,tutorialTarget};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoHideoutEntry;
})(typeof globalThis!=='undefined'?globalThis:this);
