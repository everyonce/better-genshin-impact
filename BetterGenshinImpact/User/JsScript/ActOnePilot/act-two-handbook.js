(function(root){
 'use strict';
 function target(o,now,context,inspectNext){
  if(!o||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!o.hud||o.hud.world||o.hud.dialogueReady)return null;
  const rows=o.ocr||[],has=(t,x0,x1,y0,y1)=>rows.filter(r=>String(r.text||'').trim()===t&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1).length===1;
  if(context&&context.chapterReward===true&&context.session===o.session&&context.frameId<o.frameId&&now>=context.createdAt&&now-context.createdAt<=120000&&has('Obtained',800,950,250,320)&&has('Primogem',650,800,580,640)&&has('50',700,800,540,590)&&has('10000',800,950,540,590)&&has('Mora',800,950,580,640)&&has("Hero's Wit",950,1100,580,640)&&has("Lucky Dog's",1100,1250,580,640)&&has('Clover',1100,1250,610,660)&&has('Click anywhere in the blank area to continue',600,800,700,790))return {action:'continue',x:960,y:800};
  if(context&&context.rewardExp===200&&context.session===o.session&&context.frameId<o.frameId&&now>=context.createdAt&&now-context.createdAt<=120000&&
    has('Obtained',800,950,250,320)&&has('Adventure',800,950,570,630)&&has('EXP',800,950,610,660)&&has('200',800,950,530,590)&&has('Click anywhere in the blank area to continue',600,800,700,790))return {action:'continue',x:960,y:800};
  if(context&&context.session===o.session&&context.frameId<o.frameId&&now>=context.createdAt&&now-context.createdAt<=120000&&
    has('Obtained',800,950,250,320)&&has('Adventure',800,950,570,630)&&has('EXP',800,950,610,660)&&
    has('100',800,950,530,590)&&(has('5000',950,1100,530,590)||has("Lucky Dog's",950,1100,570,625)&&(has('Hourglass',950,1100,610,660)||has('Silver Circlet',950,1100,610,660)))&&has('Click anywhere in the blank area to continue',600,800,700,790))
      return {action:'continue',x:960,y:800};
  if(inspectNext==='closeRecovery'&&has('Experience',220,300,220,260)&&has('Domains',220,300,320,370)&&has('Enemies',220,300,410,470)&&has('Guide',220,300,510,570)&&has('X',1630,1670,195,230))return {action:'closeRecovery',x:1666,y:236};
  if(inspectNext==='experienceScroll'&&has('Chapter 2',1300,1450,150,230)&&has('Experience',200,280,200,270)&&has('Investigation Progress',380,480,240,320)&&has('4/8',500,600,330,420)&&((has('Open 30 chests',850,950,400,460)&&has('18/30',850,950,440,495)&&has('Enhance a weapon to Lv. 10',850,950,770,830))||(has('Open 30 chests',850,950,345,395)&&has('18/30',850,950,390,440)&&has('Enhance a weapon to Lv. 10',850,950,720,770)&&has('Equip 4 artifacts on a single',850,950,830,880))))return {action:'scrollExperience',x:1000,y:650,scroll:-8};
  if(inspectNext==='experienceScroll'&&has('Chapter 2',1300,1450,150,230)&&has('Experience',200,280,200,270)&&has('Investigation Progress',380,480,240,320)&&has('4/8',500,600,330,420)&&has('Open 30 chests',850,950,260,310)&&has('18/30',850,950,300,350)&&has('Enhance a weapon to Lv. 10',850,950,630,690)&&has('Equip 4 artifacts on a single',850,950,745,795)&&has('character',850,950,780,830))return {action:'scrollExperience',x:1000,y:650,scroll:-8};
  if(inspectNext==='experienceScroll'&&has('Chapter 2',1300,1450,150,230)&&has('Experience',200,280,200,270)&&has('Investigation Progress',380,480,240,320)&&has('4/8',500,600,330,420)&&has('Upgrade the Statues of The',850,950,230,270)&&has('Seven in Mondstadt to Lv. 4',850,950,260,310)&&has('Hunt down a Cryo Abyss',850,950,345,390)&&has('Mage',850,950,385,420)&&has('Activate 6 Teleport',850,950,720,765)&&has('Waypoints',850,950,755,800)&&has('6/6',850,950,790,835))return {action:'scrollExperience',x:1000,y:650,scroll:-8};
  if(inspectNext==='enemyCategory'&&has('Enemies',220,300,410,470)&&has('All',390,440,180,220)&&has('Easy',390,440,285,325)&&has('Elite Enemies',390,440,345,385)&&has('Boss Enemies',390,440,400,450))return {action:'selectEliteEnemies',x:489,y:373};
  if(inspectNext==='enemyCategory'&&has('Enemies',220,300,410,470)&&has('All',390,440,180,220)&&has('Cancel',1400,1450,800,840)&&has('Navigation',1370,1410,830,870))return {action:'inspectEnemyCategory',x:695,y:204};
  if(inspectNext==='enemyScroll'&&has('Enemies',220,300,410,470)&&has('All',390,440,180,220)&&has('Cancel',1400,1450,800,840)&&has('Navigation',1370,1410,830,870))return {action:'scrollEnemies',x:690,y:690,scroll:-8};
  if(inspectNext==='enemyScroll'&&has('Enemies',220,300,410,470)&&has('Elite Enemies',390,450,180,220)&&has('Abyss Mage',1020,1080,245,295)&&has('Galesong Hill, Mondstadt',1020,1080,305,340)&&has('Lv. 10',630,660,805,835)&&has('Navigate',1370,1410,810,855))return {action:'navigateAbyssMage',x:1443,y:841};
  if(inspectNext==='enemyScroll'&&has('Enemies',220,300,410,470)&&has('Elite Enemies',390,450,180,220)&&has('Secret Source Automaton:',1020,1080,240,285)&&has('Hunter-Seeker',1020,1080,285,335)&&has('Lv. 10',630,660,805,835)&&has('Lv. 18',810,845,800,835)&&has('Navigate',1370,1410,810,855))return {action:'inspectBlueAbyssIcon',x:682,y:758};
  if(inspectNext==='enemyScroll'&&has('Enemies',220,300,410,470)&&has('Elite Enemies',390,450,180,220)&&has('Navigate',1370,1410,810,855))return {action:'scrollEliteEnemies',x:690,y:690,scroll:-8};
  if(inspectNext==='panelScroll'&&has('Thorny Crown of the',1470,1510,0,25)&&has('Mountain Wind',1470,1510,25,60)&&has('Navigate',1600,1640,980,1010))return {action:'inspectArtifactRequirements',x:1720,y:700,scroll:-8};
  if(inspectNext==='artifact'&&has('Domain: Artifacts',420,500,210,260)&&has('Thorny Crown of the',760,800,420,450)&&has('Mountain Wind',760,800,450,485)&&has('Mondstadt',760,800,485,525))return {action:'locateArtifactDomain',x:1550,y:476};
  if(inspectNext==='rift'&&has('Domain: Talent',420,500,380,420)&&has('Forsaken Rift',760,800,770,820)&&has('Mondstadt',760,800,815,850)&&has('Discover Reward',1080,1110,750,790))return {action:'locateForsakenRift',x:1557,y:812};
  if(inspectNext==='scrollDomains'&&has('Experience',220,300,220,260)&&has('Domains',220,300,320,370)&&has('Domain: Talent',420,500,380,420)&&has('Spiral Abyss',420,500,510,570))return {action:'scrollDomains',x:1400,y:750,scroll:-8};
  if(['talent','weapon','enemies'].includes(inspectNext)){
   if(!has('Experience',220,300,220,260)||!has('Domains',220,300,320,370)||!has('Enemies',220,300,410,470))return null;
   const label=inspectNext==='talent'?'Domain: Talent':inspectNext==='weapon'?'Domain: Weapon':'Enemies';
   const candidates=rows.filter(r=>String(r.text).trim()===label&&r.x>=(inspectNext==='enemies'?220:420)&&r.x<=(inspectNext==='enemies'?300:500)&&r.y>=250&&r.y<=470&&Number.isFinite(r.width)&&Number.isFinite(r.height));
   if(candidates.length!==1)return null;const r=candidates[0];return {action:'inspect'+inspectNext,x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)};
  }
  if(inspectNext==='experience'){
   if(has('Domains',220,300,320,370)&&has('Domain: Artifacts',420,500,210,260)&&has('Spiral Abyss',420,500,510,570)&&has('Experience',220,300,220,260))return {action:'inspectExperience',x:295,y:241};
   return null;
  }
  if(inspectNext==='domains'){
   if(has('Experience',220,300,220,260)&&has('Domains',220,300,320,370)&&has('Enemies',220,300,410,470)&&has('All',390,440,180,220))return {action:'inspectDomains',x:295,y:344};
   const tab=rows.filter(r=>r.text==='Domains'&&r.x>=220&&r.x<=300&&r.y>=320&&r.y<=370);
   if(has('Chapter 2',1300,1450,150,230)&&has('Experience',200,280,200,270)&&has('Investigation Progress',380,480,240,320)&&tab.length===1)return {action:'inspectDomains',x:295,y:344};
   return null;
  }
  if(inspectNext==='mage'){
   if(has('Chapter 2',1300,1450,150,230)&&has('Experience',200,280,200,270)&&has('Investigation Progress',380,480,240,320)&&has('4/8',500,600,330,420)&&has('Hunt down a Cryo Abyss',850,950,640,700)&&has('Mage',850,950,680,725)&&has('0/1',850,950,710,750)&&(has('15/30',850,950,450,490)||has('18/30',850,950,440,500)))return {action:'locate',objective:'Cryo Abyss Mage',x:1508,y:701};
   return null;
  }
  if(inspectNext==='previous'){
   if(has('Chapter 3',1300,1450,150,230)&&has('Chapter 3',800,1000,460,530)&&has('Experience',200,280,200,270)&&has('Unlocks at Adventure Rank 10',780,900,540,620))return {action:'previous',x:1288,y:203};
   if(has('Chapter 2',1300,1450,150,230)&&has('Experience',200,280,200,270)&&has('Investigation Progress',380,480,240,320)&&has('Open 30 chests',850,950,400,460)&&has('15/30',850,950,450,490))return {action:'previous',x:1288,y:203};
   return null;
  }
  if(inspectNext){
   if(has('Chapter 2',1300,1450,150,230)&&has('Experience',200,280,200,270)&&has('Investigation Progress',380,480,240,320)&&has('4/8',500,600,330,420)&&has('Open 30 chests',850,950,400,460)&&has('15/30',850,950,450,490))return {action:'next',x:1548,y:203};
   if(has('Chapter 1',1300,1450,150,230)&&has('Experience',200,280,200,270)&&has('Investigation Progress',380,480,240,320)&&has('4/4',500,600,330,420)&&has('Rewards claimed',450,600,810,880)&&has('Open 15 chests',850,950,520,590)&&has('15/15',850,950,570,620))return {action:'next',x:1548,y:203};
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
  if(has('4/4',500,600,330,420)&&has('Open 15 chests',850,950,520,590)&&has('15/15',850,950,570,620)&&has('10000',600,700,600,680)&&has('50',400,500,720,780)&&has('Claim',500,600,810,880))return {action:'claim',objective:'Chapter 1 completion',chapterReward:true,x:555,y:850};
  const claims=rows.filter(r=>r.text==='Claim'&&r.x>=1430&&r.x<=1510&&r.y>=290&&r.y<=480).sort((a,b)=>a.y-b.y);
  for(const r of claims){
   const first=has('Visit the Statue of The Seven',850,950,r.y-50,r.y-10)&&has('at Windrise',850,950,r.y-15,r.y+25)&&has('1/1',850,950,r.y+15,r.y+70);
   const second=has('Activate 3 Teleport',850,950,r.y-50,r.y-10)&&has('Waypoints',850,950,r.y-15,r.y+25)&&has('3/3',850,950,r.y+15,r.y+70);
   const third=has('Upgrade the Statues of The',850,950,r.y-50,r.y-10)&&has('Seven in Mondstadt to Lv. 2',850,950,r.y-15,r.y+25)&&has('1/1',850,950,r.y+15,r.y+70);
   const chests=has('Open 15 chests',850,950,r.y-40,r.y+10)&&has('15/15',850,950,r.y+10,r.y+60);
   if((first||second||third||chests)&&Number.isFinite(r.width)&&Number.isFinite(r.height))return {action:'claim',objective:chests?'Open 15 chests':third?'Upgrade the Statues of The Seven in Mondstadt to Lv. 2':first?'Visit the Statue of The Seven at Windrise':'Activate 3 Teleport Waypoints',x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)};
  }
  if(claims.length===0&&has('Open 15 chests',850,950,260,570))return {action:'close',x:1666,y:236};
  return null;
 }
 root.ActTwoHandbook={target};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoHandbook;
})(typeof globalThis!=='undefined'?globalThis:this);
