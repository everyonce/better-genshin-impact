(function(root){
 'use strict';
 function target(o,now,p,r,witness){
  if(!o||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!o.hud||o.hud.world||o.hud.dialogueReady||
   !p||!r||p.session!==r.session||p.frameId!==r.expectedFrameId||p.consumed||p.reviewed!==true||!Number.isFinite(p.createdAt)||now<p.createdAt||now-p.createdAt>60000)return null;
  if(p.action==='weaponBack'){
   const rows=o.ocr||[];
   if(!rows.some(q=>String(q.text).replace(/^[- ]+/,'')==="Sword / Traveler's Handy Sword"&&q.x>100&&q.y<80)||!rows.some(q=>q.text==='65286'&&q.x>1600&&q.y<80)||!rows.some(q=>q.text==='102'&&q.x>1750&&q.y>200&&q.y<310))return null;
   return {key:'VK_ESCAPE',action:p.action};
  }
  if(p.action==='confirmWeaponPreview'){
   const rows=o.ocr||[],one=(text,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).trim()===text&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   const oreWitness=witness&&witness.session===r.session&&witness.frameId===p.witnessFrameId&&witness.timestamp<=o.timestamp&&o.timestamp-witness.timestamp<=600000&&(witness.ocr||[]).some(q=>q.text==='Fine Enhancement Ore'&&q.x>1180&&q.y>170&&q.y<240);
   const material=one('Fine Enhancement Ore',1180,1630,170,240)&&one('ed (1/40)',1630,1800,680,750)||oreWitness&&one('21/36',1180,1270,900,950)&&one('Enhancement Materials Consumed (1/40)',1200,1850,680,750);
   if(!one('Base EXP',30,200,15,80)||!material||!one('36',60,120,220,270)||!one('Lv. 10 +10',1100,1400,100,190)||!one('+41475',1400,1650,120,180)||!one('4200',1300,1450,980,1040)||!one('69486',1600,1800,15,80)||!one('Enhance',1600,1850,980,1040)||!one('102',1750,1870,220,290))return null;
   return {x:1730,y:1020,action:p.action};
  }
  if(p.action==='addFineOre'||p.action==='topUpFineOre'){
   const rows=o.ocr||[],one=(text,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).trim()===text&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   const topUp=p.action==='topUpFineOre';
   if(!one('Base EXP',30,200,15,80)||!one('Fine Enhancement Ore',1180,1630,170,240)||!one('36',60,120,220,270)||!one(topUp?'+32000':'+2000',1450,1600,120,180)||!one(topUp?'3200':'200',1300,1430,980,1040))return null;
   return {x:98,y:180,clicks:topUp?6:15,action:p.action};
  }
  if(p.action==='selectFineOre'){
   const rows=o.ocr||[],one=(text,x0,x1,y0,y1)=>rows.filter(q=>(String(q.text).trim()===text||text==='Enhancement Materials Consumed (0/40)'&&q.text==='Enhancement Materials Consumed (0740)')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('Base EXP',30,200,15,80)||!one('36',60,120,220,270)||!one('Enhancement Materials Consumed (0/40)',1200,1850,680,750))return null;
   return {x:98,y:180,action:p.action};
  }
  if(p.action==='weaponMaterials'){
   const rows=o.ocr||[],one=(text,x0,x1,y0,y1)=>rows.filter(q=>(String(q.text).trim()===text||text==='Enhancement Materials Consumed (0/40)'&&q.text==='Enhancement Materials Consumed (0740)')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one("Sword / Traveler's Handy Sword",100,600,15,80)||!one('Lv. 10',1100,1350,100,200)||!one('69',1800,1900,200,290)||!one('Enhancement Materials Consumed (0/40)',1200,1850,680,750))return null;
   return {x:1226,y:865,action:p.action};
  }
  if(p.action==='previewLevelMaterials'||p.action==='confirmLevelPreview'||p.action==='closeLevelResult'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).trim()===t&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(p.action==='closeLevelResult'){
    if(rows.filter(q=>/^Kaeya[ /I]+Level Up$/.test(String(q.text).trim())&&q.x>100&&q.x<400&&q.y<80).length!==1||!one('65706',1650,1790,15,80)||!rows.some(q=>/^Lv\.\s*16$/.test(q.text)&&q.x>1100&&q.x<1650&&q.y>100&&q.y<220)||!one('2,184',1700,1900,220,310))return null;
    return {key:'VK_ESCAPE',action:p.action};
   }
   if(p.action==='confirmLevelPreview'){
    const title=rows.filter(q=>String(q.text).replace(/[^A-Za-z]/g,'')==='KaeyaLevelUp'&&q.x>=100&&q.x<=400&&q.y>=15&&q.y<=80);
    const exp=one('+44000 4215/5700',1600,1900,120,180)||(one('+44000',1600,1700,120,180)&&one('4215/5700',1720,1800,120,180));
    if(title.length!==1||!one('74506',1650,1790,15,80)||!one('Lv. 10 +6',1100,1400,100,175)||!exp||!one('2,184',1700,1900,220,280)||!one('34',1380,1450,700,760)||!one('2',1520,1575,700,760)||!one('8800',1300,1430,980,1040)||!one('Level Up',1600,1830,980,1050))return null;
    return {x:1730,y:1020,action:p.action};
   }
   if(!one('Kaeya / Level Up',100,400,15,80)||!one('Lv. 10',1100,1300,100,175)||!one('74506',1650,1790,15,80)||!one('Select EXP materials',1300,1800,650,730)||!one('Auto Add',1650,1850,870,950))return null;
   return {x:1760,y:917,action:p.action};
  }
  if(p.action==='equip'||p.action==='back'){
   const rows=o.ocr||[],one=(text,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).trim()===text&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!witness||witness.session!==r.session||witness.frameId!==p.witnessFrameId||witness.timestamp>o.timestamp||o.timestamp-witness.timestamp>600000||!(witness.ocr||[]).some(q=>q.text==='Cryo / Kaeya'&&q.x>100&&q.x<400&&q.y<90)||!(witness.ocr||[]).some(q=>q.text==='Fast Equip'&&q.x>1400&&q.y>950)||!one('Fast Equip',100,350,15,80)||!one('Recommended Plan',30,400,100,160)||!one('Attribute Preview',450,800,490,550))return null;
   if(p.action==='back')return {action:'back',key:'VK_ESCAPE'};
   if(!one('1,700',1480,1650,550,610)||!one('1,829',1700,1880,550,610)||!one('102',1480,1650,610,680)||!one('119',1700,1880,610,680)||!one('No Set Bonus',480,750,430,490)||!one('Equip',1600,1820,970,1050))return null;
   const q=rows.find(q=>q.text==='Equip'&&q.x>1600&&q.y>970);return {x:Math.round(q.x+q.width/2),y:Math.round(q.y+q.height/2),action:'equip'};
  }
  const labels={attributes:'Attributes',weapons:'Weapons',artifacts:'Artifacts',talents:'Talents',level:'Level Up',fastEquip:'Fast Equip',enhanceWeapon:'Enhance',close:'Attributes'};
  const label=labels[p.action],rows=o.ocr||[];
  const exactCharacter=rows.filter(q=>String(q.text||'').trim()==='Kaeya'&&q.x>=1400&&q.x<=1700&&q.y>=100&&q.y<=180).length===1;
  if(!label||rows.filter(q=>(/^Cryo\s*\/\s*Kaeya$/.test(String(q.text||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim())||exactCharacter&&/^Cryo\s*\/\s*Keya$/.test(String(q.text||'').trim()))&&q.x>=100&&q.x<400&&q.y<90).length!==1)return null;
  if(p.action==='close'&&rows.some(q=>q.text.trim()==='Attributes'&&q.x>80&&q.x<400&&q.y>90&&q.y<200)&&rows.some(q=>/^(Level Up|Switch)$/.test(q.text)&&q.x>1400&&q.y>950))return {action:'close',key:'VK_ESCAPE'};
  if(p.action==='enhanceWeapon'&&!rows.some(q=>q.text==="Traveler's Handy Sword"&&q.x>1400&&q.y>100&&q.y<190))return null;
  const matches=rows.filter(q=>(p.action==='artifacts'?String(q.text||'').trim().replace(/\s+\d{1,2}$/,''):String(q.text||'').trim())===label&&(p.action==='level'||p.action==='fastEquip'||p.action==='enhanceWeapon'?q.x>1400&&q.y>950:q.x>80&&q.x<400&&q.y>90&&q.y<750));
  if(matches.length!==1)return null;const q=matches[0];
  return Number.isFinite(q.width)&&Number.isFinite(q.height)?{x:Math.round(q.x+q.width/2),y:Math.round(q.y+q.height/2),action:p.action}:null;
 }
 function upgradeReady(o,now,session,amount){
  const p=o&&o.hud&&o.hud.kaeyaLevel;
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&p&&p.frameId===o.frameId&&
   o.map===null&&!o.hud.world&&!o.hud.dialogueReady&&p.amount===amount&&p.requiredMora===amount*1000&&
   p.lowTierStock===26&&p.midTierStock===3&&p.highTierStock===0&&p.mora===68395&&
   (o.ocr||[]).filter(q=>/^KaeyaLeve[lt]Up$/.test(String(q.text||'').replace(/[^A-Za-z]/g,''))&&q.x>100&&q.x<400&&q.y<90).length===1);
 }
 root.ActTwoTeam={target,upgradeReady};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoTeam;
})(typeof globalThis!=='undefined'?globalThis:this);
