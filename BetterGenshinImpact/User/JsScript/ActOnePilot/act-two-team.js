(function(root){
 'use strict';
 function target(o,now,p,r,witness){
  if(!o||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!o.hud||o.hud.world||o.hud.dialogueReady||
   !p||!r||p.session!==r.session||p.frameId!==r.expectedFrameId||p.consumed||p.reviewed!==true||!Number.isFinite(p.createdAt)||now<p.createdAt||now-p.createdAt>60000)return null;
  if(p.action==='equip'||p.action==='back'){
   const rows=o.ocr||[],one=(text,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).trim()===text&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!witness||witness.session!==r.session||witness.frameId!==p.witnessFrameId||witness.timestamp>o.timestamp||o.timestamp-witness.timestamp>600000||!(witness.ocr||[]).some(q=>q.text==='Cryo / Kaeya'&&q.x>100&&q.x<400&&q.y<90)||!(witness.ocr||[]).some(q=>q.text==='Fast Equip'&&q.x>1400&&q.y>950)||!one('Fast Equip',100,350,15,80)||!one('Recommended Plan',30,400,100,160)||!one('Attribute Preview',450,800,490,550))return null;
   if(p.action==='back')return {action:'back',key:'VK_ESCAPE'};
   if(!one('1,700',1480,1650,550,610)||!one('1,829',1700,1880,550,610)||!one('102',1480,1650,610,680)||!one('119',1700,1880,610,680)||!one('No Set Bonus',480,750,430,490)||!one('Equip',1600,1820,970,1050))return null;
   const q=rows.find(q=>q.text==='Equip'&&q.x>1600&&q.y>970);return {x:Math.round(q.x+q.width/2),y:Math.round(q.y+q.height/2),action:'equip'};
  }
  const labels={attributes:'Attributes',weapons:'Weapons',artifacts:'Artifacts',talents:'Talents',level:'Level Up',fastEquip:'Fast Equip',close:'Attributes'};
  const label=labels[p.action],rows=o.ocr||[];
  if(!label||rows.filter(q=>/^Cryo\s*\/\s*Kaeya$/.test(String(q.text||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim())&&q.x>=100&&q.x<400&&q.y<90).length!==1)return null;
  if(p.action==='close'&&rows.some(q=>q.text.trim()==='Attributes'&&q.x>80&&q.x<400&&q.y>90&&q.y<200)&&rows.some(q=>/^(Level Up|Switch)$/.test(q.text)&&q.x>1400&&q.y>950))return {action:'close',key:'VK_ESCAPE'};
  const matches=rows.filter(q=>(p.action==='artifacts'?String(q.text||'').trim().replace(/\s+\d{1,2}$/,''):String(q.text||'').trim())===label&&(p.action==='level'||p.action==='fastEquip'?q.x>1400&&q.y>950:q.x>80&&q.x<400&&q.y>90&&q.y<750));
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
