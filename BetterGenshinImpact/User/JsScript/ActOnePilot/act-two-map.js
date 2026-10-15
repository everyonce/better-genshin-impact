(function(root){
 'use strict';
 function target(o,now,p,r){
  const magePin=o&&o.ocr&&[['Hunt down a Cryo Abyss',1490,0],['Mage',1490,30],['Total Pins 0/350',1440,910],['Confirm',1620,980]].every(a=>o.ocr.filter(q=>String(q.text||'').trim()===a[0]&&Math.abs(q.x-a[1])<30&&Math.abs(q.y-a[2])<30).length===1);
  const pinPanel=magePin||o&&o.ocr&&o.ocr.some(q=>q.text==='Custom Pin (Click to edit'&&q.x>1450&&q.y<40)&&o.ocr.some(q=>q.text==='Total Pins 0/350'&&q.x>1400&&q.y>880);
  const cityPanel=pinPanel||o&&o.ocr&&o.ocr.some(q=>String(q.text||'').trim()==='Mondstadt, Mondstadt'&&q.x>=1430&&q.x<=1550&&q.y>=80&&q.y<=140)&&o.ocr.some(q=>q.text==='Teleport Waypoint'&&q.x>=1450&&q.y>=0&&q.y<=70);
  const starsnatchPanel=o&&o.ocr&&o.ocr.some(q=>String(q.text||'').trim()==='Starsnatch Cliff, Mondstadt'&&q.x>=1430&&q.x<=1550&&q.y>=80&&q.y<=140)&&o.ocr.some(q=>q.text==='Teleport Waypoint'&&q.x>=1450&&q.y>=0&&q.y<=70);
  const blossomPanel=o&&o.ocr&&[['Ley Line Outcrop:',1492,6],['Blossom of Revelation',1488,34],['Windwail Highland, Mondstadt',1474,103],['Treasure Collection Cost 20',1454,413]].every(a=>o.ocr.filter(q=>String(q.text||'').trim()===a[0]&&Math.abs(q.x-a[1])<=8&&Math.abs(q.y-a[2])<=8).length===1);
  if(!o||!o.hud||o.hud.bigMap!==true&&!cityPanel&&!starsnatchPanel&&!blossomPanel||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||
   !p||!r||p.reviewed!==true||p.consumed===true||p.session!==r.session||p.frameId!==r.expectedFrameId||
   !Number.isFinite(p.createdAt)||now<p.createdAt||now-p.createdAt>60000)return null;
  const rows=o.ocr||[];
  if(pinPanel&&p.action!=='closeUnconfirmedPin')return null;
  function exact(text,x0,x1,y0,y1){const a=rows.filter(q=>String(q.text||'').trim()===text&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1);return a.length===1?a[0]:null;}
  if(p.action==='closeUnconfirmedPin'&&pinPanel&&exact('X',1840,1870,0,30))return {x:1876,y:34};
  if(p.action==='closeInspectedWaypoint'&&starsnatchPanel&&exact('X',1840,1870,0,30)&&exact('Teleport',1500,1800,960,1040))return {x:1876,y:34};
  if(blossomPanel&&p.action==='navigateBlossom'){
   const q=exact('Navigate',1500,1800,960,1040);if(q&&Number.isFinite(q.width)&&Number.isFinite(q.height))return {x:Math.round(q.x+q.width/2),y:Math.round(q.y+q.height/2)};
  }
  if(blossomPanel&&p.action==='closeBlossomPanel'&&exact('X',1840,1870,0,30))return {x:1876,y:34};
  if(p.action==='inspectEastBlueMarker'||p.action==='zoomRegionalMap'||p.action==='inspectBlossomIcon'){
   // Inspection only: this reviewed marker is not yet classified as a reward.
   const blossom=p.action==='inspectBlossomIcon',anchors=blossom?[['Mondstadt',980,373,149],['Cider Lake',1004,139,149],['Windrise',1405,765,124]]:[['Mondstadt',962,417,129],['Cider Lake',980,250,127],['Windrise',1270,701,105]];
   if(!anchors.every(a=>{const q=exact(a[0],a[1]-3,a[1]+3,a[2]-3,a[2]+3);return q&&Number.isFinite(q.width)&&Math.abs(q.width-a[3])<=4;}))return null;
   return blossom?{x:956,y:969}:p.action==='zoomRegionalMap'?{x:48,y:444}:{x:1458,y:522};
  }
  if(p.action==='zoomCity'&&exact('Mondstadt',800,950,350,460)&&exact('Cider Lake',800,1000,200,300)&&exact('+',25,55,420,460))return {x:48,y:444};
  if(p.action==='restoreCityZoom'&&exact('Mondstadt',810,850,340,380)&&exact('Cider Lake',840,880,110,150)&&exact('Windrise',1240,1270,730,780))return {x:48,y:635};
  if(p.action==='translatedGateWaypoint'||p.action==='translatedCityWaypoint'){
   // The map recenters on the player. Three independently spaced labels must
   // agree on a translation of the recorded map, with unchanged text scale.
   const city=p.action==='translatedCityWaypoint',anchors=city?[['Mondstadt',690,445,125],['Windrise',993,720,111],['Cider Lake',705,273,131]]:[['Mondstadt',916,411,129],['Windrise',1222,689,107],['Cider Lake',936,244,123]],deltas=[];
   for(const a of anchors){
    const found=rows.filter(q=>String(q.text||'').trim()===a[0]);
    if(found.length!==1||!Number.isFinite(found[0].width)||Math.abs(found[0].width-a[3])>6)return null;
    deltas.push({x:found[0].x-a[1],y:found[0].y-a[2]});
   }
   if(deltas.some(d=>!Number.isFinite(d.x)||!Number.isFinite(d.y)||Math.abs(d.x)>300||Math.abs(d.y)>300||Math.abs(d.x-deltas[0].x)>5||Math.abs(d.y-deltas[0].y)>5))return null;
   return {x:Math.round((city?790:1181)+deltas.reduce((s,d)=>s+d.x,0)/3),y:Math.round((city?552:574)+deltas.reduce((s,d)=>s+d.y,0)/3)};
  }
  if(p.action==='mondstadtGateWaypoint'&&exact('Mondstadt',810,860,375,425)&&exact('Windrise',1110,1170,650,720)&&exact('Cider Lake',830,890,210,270))return {x:1099,y:560};
  if(p.action==='cityWaypoint'&&exact('Mondstadt',915,935,395,435)&&exact('Windrise',1210,1250,675,725)&&exact('Cider Lake',935,965,225,275))return {x:1025,y:516};
  if(p.action==='chooseWaypoint'){
   const waypoint=exact('Teleport Waypoint',1200,1700,500,850);
   if(waypoint&&(exact('Temple of the Falcon',1200,1700,700,900)||exact("Adventurers' Guild",1200,1700,700,900))&&Number.isFinite(waypoint.width)&&Number.isFinite(waypoint.height))return {x:Math.round(waypoint.x+waypoint.width/2),y:Math.round(waypoint.y+waypoint.height/2)};
  }
  if(p.action==='teleport'&&exact('Teleport Waypoint',1450,1800,0,70)&&(exact('Starfell Valley, Mondstadt',1430,1550,80,140)||exact('Mondstadt, Mondstadt',1430,1550,80,140))&&!rows.some(q=>/activate waypoint|not yet unlocked/i.test(q.text||''))){
   const button=exact('Teleport',1500,1800,960,1040);if(button&&Number.isFinite(button.width)&&Number.isFinite(button.height))return {x:Math.round(button.x+button.width/2),y:Math.round(button.y+button.height/2)};
  }
  return null;
 }
 root.ActTwoMap={target};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoMap;
})(typeof globalThis!=='undefined'?globalThis:this);
