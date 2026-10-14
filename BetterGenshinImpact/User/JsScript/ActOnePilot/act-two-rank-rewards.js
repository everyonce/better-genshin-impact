(function(root){
 'use strict';
 function target(o,now,context){
  if(!o||!Number.isFinite(now)||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||
   !o.hud||o.hud.world||o.hud.health||o.hud.dialogueReady||o.hud.choice)return null;
  const rows=o.ocr||[];
  function exact(text,x0,x1,y0,y1){const a=rows.filter(r=>String(r.text||'').trim()===text&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1);return a.length===1?a[0]:null;}
  if(context&&context.session===o.session&&context.frameId<o.frameId&&now>=context.createdAt&&now-context.createdAt<=120000&&
   exact('Obtained',800,950,240,320)&&exact('Obtained Rewards',750,950,330,410)&&
   exact('Click anywhere in the blank area to continue',600,800,700,790))return {x:960,y:800,action:'continue'};
  if(!exact('UID: 693306810',1650,1750,1030,1080)||!exact('Adventure Rank',1350,1450,0,70)||!exact('Rewards',1400,1550,350,440))return null;
  if(exact('Rewards Claimed',1400,1550,975,1035))return {x:1862,y:35,action:'close'};
  const claim=exact('Claim Rewards',1400,1500,975,1035);
  return claim&&Number.isFinite(claim.width)&&Number.isFinite(claim.height)?{x:Math.round(claim.x+claim.width/2),y:Math.round(claim.y+claim.height/2),action:'claim'}:null;
 }
 root.ActTwoRankRewards={target};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoRankRewards;
})(typeof globalThis!=='undefined'?globalThis:this);
