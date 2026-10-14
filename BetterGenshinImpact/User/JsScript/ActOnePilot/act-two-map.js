(function(root){
 'use strict';
 function target(o,now,p,r){
  if(!o||!o.hud||o.hud.bigMap!==true||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||
   !p||!r||p.reviewed!==true||p.consumed===true||p.session!==r.session||p.frameId!==r.expectedFrameId||
   !Number.isFinite(p.createdAt)||now<p.createdAt||now-p.createdAt>60000)return null;
  const rows=o.ocr||[];
  function exact(text,x0,x1,y0,y1){const a=rows.filter(q=>String(q.text||'').trim()===text&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1);return a.length===1?a[0]:null;}
  if(p.action==='mondstadtGateWaypoint'&&exact('Mondstadt',810,860,375,425)&&exact('Windrise',1110,1170,650,720)&&exact('Cider Lake',830,890,210,270))return {x:1099,y:560};
  if(p.action==='chooseWaypoint'){
   const waypoint=exact('Teleport Waypoint',1200,1700,500,850);
   if(waypoint&&exact('Temple of the Falcon',1200,1700,700,900)&&Number.isFinite(waypoint.width)&&Number.isFinite(waypoint.height))return {x:Math.round(waypoint.x+waypoint.width/2),y:Math.round(waypoint.y+waypoint.height/2)};
  }
  if(p.action==='teleport'&&exact('Teleport Waypoint',1450,1800,0,70)&&exact('Starfell Valley, Mondstadt',1430,1550,80,140)&&!rows.some(q=>/activate waypoint|not yet unlocked/i.test(q.text||''))){
   const button=exact('Teleport',1500,1800,960,1040);if(button&&Number.isFinite(button.width)&&Number.isFinite(button.height))return {x:Math.round(button.x+button.width/2),y:Math.round(button.y+button.height/2)};
  }
  return null;
 }
 root.ActTwoMap={target};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoMap;
})(typeof globalThis!=='undefined'?globalThis:this);
