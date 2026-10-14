(function(root){
 'use strict';
 function target(o,now,p,r){
  if(!o||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!o.hud||o.hud.world||o.hud.dialogueReady||
   !p||!r||p.session!==r.session||p.frameId!==r.expectedFrameId||p.consumed||p.reviewed!==true||!Number.isFinite(p.createdAt)||now<p.createdAt||now-p.createdAt>60000)return null;
  const labels={attributes:'Attributes',weapons:'Weapons',artifacts:'Artifacts',talents:'Talents',level:'Level Up',fastEquip:'Fast Equip'};
  const label=labels[p.action],rows=o.ocr||[];
  if(!label||rows.filter(q=>String(q.text||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim()==='Cryo / Kaeya'&&q.x>=100&&q.x<400&&q.y<90).length!==1)return null;
  const matches=rows.filter(q=>String(q.text||'').trim()===label&&(p.action==='level'||p.action==='fastEquip'?q.x>1400&&q.y>950:q.x>80&&q.x<400&&q.y>90&&q.y<750));
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
