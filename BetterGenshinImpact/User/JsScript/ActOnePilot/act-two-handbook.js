(function(root){
 'use strict';
 function target(o,now,context,inspectNext){
  if(!o||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!o.hud||o.hud.world||o.hud.dialogueReady)return null;
  const rows=o.ocr||[],has=(t,x0,x1,y0,y1)=>rows.filter(r=>String(r.text||'').trim()===t&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1).length===1;
  if(context&&context.rewardExp===200&&context.session===o.session&&context.frameId<o.frameId&&now>=context.createdAt&&now-context.createdAt<=120000&&
    has('Obtained',800,950,250,320)&&has('Adventure',800,950,570,630)&&has('EXP',800,950,610,660)&&has('200',800,950,530,590)&&has('Click anywhere in the blank area to continue',600,800,700,790))return {action:'continue',x:960,y:800};
  if(context&&context.session===o.session&&context.frameId<o.frameId&&now>=context.createdAt&&now-context.createdAt<=120000&&
    has('Obtained',800,950,250,320)&&has('Adventure',800,950,570,630)&&has('EXP',800,950,610,660)&&
    has('100',800,950,530,590)&&(has('5000',950,1100,530,590)||has("Lucky Dog's",950,1100,570,625)&&has('Hourglass',950,1100,610,660))&&has('Click anywhere in the blank area to continue',600,800,700,790))
      return {action:'continue',x:960,y:800};
  if(inspectNext){
   if(has('Chapter 1',1300,1450,150,230)&&has('Experience',200,280,200,270)&&has('Investigation Progress',380,480,240,320)&&has('Open 15 chests',850,950,260,350)&&has('13/15',850,950,320,370))return {action:'next',x:1548,y:203};
   return null;
  }
  if(has('Chapter 2',1300,1450,150,230)&&has('Experience',200,280,200,270)&&has('Investigation Progress',380,480,240,320)){
   const claims=rows.filter(r=>r.text==='Claim'&&r.x>=1430&&r.x<=1510&&r.y>=290&&r.y<=800).sort((a,b)=>a.y-b.y);
   for(const r of claims){
    const weapon=has('Enhance a weapon to Lv. 10',850,950,r.y-40,r.y+10)&&has('1/1',850,950,r.y+10,r.y+60);
    const waypoints=has('Activate 6 Teleport',850,950,r.y-50,r.y-10)&&has('Waypoints',850,950,r.y-15,r.y+25)&&has('6/6',850,950,r.y+15,r.y+70);
    const equipment=has('Equip 4 artifacts on a single',850,950,r.y-50,r.y-10)&&has('character',850,950,r.y-15,r.y+25)&&has('1/1',850,950,r.y+15,r.y+70);
    const cooking=has('Cook 5 dishes',850,950,r.y-40,r.y+10)&&has('5/5',850,950,r.y+10,r.y+60);
    if((weapon||waypoints||equipment||cooking)&&Number.isFinite(r.width)&&Number.isFinite(r.height))return {action:'claim',objective:cooking?'Cook 5 dishes':equipment?'Equip 4 artifacts on a single character':weapon?'Enhance a weapon to Lv. 10':'Activate 6 Teleport Waypoints',rewardExp:200,x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)};
   }
   if(claims.length===0)return {action:'close',x:1666,y:236};
   return null;
  }
  if(!has('Chapter 1',1300,1450,150,230)||!has('Experience',200,280,200,270)||!has('Investigation Progress',380,480,240,320))return null;
  const claims=rows.filter(r=>r.text==='Claim'&&r.x>=1430&&r.x<=1510&&r.y>=290&&r.y<=480).sort((a,b)=>a.y-b.y);
  for(const r of claims){
   const first=has('Visit the Statue of The Seven',850,950,r.y-50,r.y-10)&&has('at Windrise',850,950,r.y-15,r.y+25)&&has('1/1',850,950,r.y+15,r.y+70);
   const second=has('Activate 3 Teleport',850,950,r.y-50,r.y-10)&&has('Waypoints',850,950,r.y-15,r.y+25)&&has('3/3',850,950,r.y+15,r.y+70);
   const third=has('Upgrade the Statues of The',850,950,r.y-50,r.y-10)&&has('Seven in Mondstadt to Lv. 2',850,950,r.y-15,r.y+25)&&has('1/1',850,950,r.y+15,r.y+70);
   if((first||second||third)&&Number.isFinite(r.width)&&Number.isFinite(r.height))return {action:'claim',objective:third?'Upgrade the Statues of The Seven in Mondstadt to Lv. 2':first?'Visit the Statue of The Seven at Windrise':'Activate 3 Teleport Waypoints',x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)};
  }
  if(claims.length===0&&has('Open 15 chests',850,950,260,570))return {action:'close',x:1666,y:236};
  return null;
 }
 root.ActTwoHandbook={target};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoHandbook;
})(typeof globalThis!=='undefined'?globalThis:this);
