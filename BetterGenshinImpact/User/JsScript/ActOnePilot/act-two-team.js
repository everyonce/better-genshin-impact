(function(root){
 'use strict';
 function target(o,now,p,r,witness){
  if(!o||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!o.hud||o.hud.world||o.hud.dialogueReady||
   !p||!r||p.session!==r.session||p.frameId!==r.expectedFrameId||p.consumed||p.reviewed!==true||!Number.isFinite(p.createdAt)||now<p.createdAt||now-p.createdAt>60000)return null;
  if(p.action==='amberBowResultBack'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('UID: 693306810',1600,1900,1030,1080))return null;
   const result=one('Bow / Recurve Bow',100,450,15,80)&&one('102003',1600,1800,15,80)&&one('Lv. 16',1100,1600,120,210)&&one('16.0%',1700,1900,290,370);
   const selected=one('Weapon Selection',100,450,15,80)&&(one('Recurve Bow',1400,1800,100,180)||one('Recurve Bow-',1400,1800,100,180))&&one('76',1750,1900,200,280)&&one('Equipped: Amber',1500,1800,900,970);
   return result||selected?{key:'VK_ESCAPE',action:p.action}:null;
  }
  if(p.action==='amberBowConfirm'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!witness||witness.session!==r.session||witness.frameId!==p.witnessFrameId||witness.timestamp>o.timestamp||o.timestamp-witness.timestamp>600000||!(witness.ocr||[]).some(q=>q.text==='Fine Enhancement Ore'&&q.x>=1180&&q.x<=1630&&q.y>=170&&q.y<=240)||!one('Bow / Recurve Bow',100,450,15,80)||!one('105203',1600,1800,15,80)||!one('+32000',1400,1650,120,180)||!one('0/275',1700,1900,120,180)||!one('16/45',1180,1280,880,950)||!one('16.0%',1700,1900,290,350)||!one('Enhancement Materials Consumed (1/40)',1200,1850,680,750)||!one('3200',1300,1430,980,1040)||!one('Enhance',1600,1850,980,1040)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   return {x:1730,y:1020,action:p.action};
  }
  if(p.action==='amberBowMaterialBack'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('Base EXP',30,300,15,80)||!one('105203',1600,1800,15,80)||!one('Fine Enhancement Ore',1180,1630,170,240)||!one('45',190,270,220,270)||!one('+32000',1400,1650,120,180)||!one('3200',1300,1430,980,1040)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   return {key:'VK_ESCAPE',action:p.action};
  }
  if(p.action==='amberBowAddFine'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('Base EXP',30,300,15,80)||!one('105203',1600,1800,15,80)||!one('Fine Enhancement Ore',1180,1630,170,240)||!one('45',190,270,220,270)||!one('+2000',1400,1650,120,180)||!one('200',1300,1430,980,1040)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   return {x:235,y:180,action:'addFineOre',clicks:15};
  }
  if(p.action==='amberBowSelectFine'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('Base EXP',30,300,15,80)||!one('105203',1600,1800,15,80)||!one('0/275',1700,1900,120,180)||!one('38',1750,1900,220,280)||!one('10.2%',1700,1900,290,350)||!one('Enhancement Materials Consumed (0/40)',1200,1850,680,750)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   return {x:235,y:180,action:p.action};
  }
  if(p.action==='amberBowMaterials'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('Bow / Recurve Bow',100,450,15,80)||!one('105203',1600,1800,15,80)||!one('0/275',1700,1900,120,180)||!one('38',1750,1900,220,280)||!one('Enhancement Materials Consumed (0/40)',1200,1850,680,750)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   return {x:1195,y:845,action:p.action};
  }
  if(['amberEquipBow','amberBowBack','amberEnhanceBow'].includes(p.action)){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('Weapon Selection',100,450,15,80)||!one('Recurve Bow',1400,1800,100,180)||!one('38',1750,1900,200,280)||!one('10.2%',1700,1900,250,310)||!one('Refinement Rank 1',1400,1800,390,450)||!one('UID: 693306810',1600,1900,1030,1080)||!witness||witness.session!==r.session||witness.frameId!==p.witnessFrameId||witness.timestamp>o.timestamp||o.timestamp-witness.timestamp>600000||!(witness.ocr||[]).some(q=>String(q.text).replace(/\s/g,'')==='Pyro/Amber'&&q.x>=100&&q.x<=400&&q.y<90))return null;
   const equipped=one('Equipped: Amber',1500,1800,900,970);
   if(p.action==='amberBowBack')return equipped?{key:'VK_ESCAPE',action:p.action}:null;
   if(p.action==='amberEnhanceBow')return equipped&&one('Enhance',1600,1850,970,1040)?{x:1770,y:1008,action:p.action}:null;
   return !equipped&&one('Switch',1450,1650,970,1040)?{x:1550,y:1008,action:p.action}:null;
  }
  if(p.action==='amberInspectBow'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('Weapon Selection',100,450,15,80)||!one("Hunter's Bow",1400,1800,100,180)||!one('Equipped: Amber',1500,1800,900,970)||!one('23',1750,1900,200,280)||!one('Quality',100,350,970,1050)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   return {x:100,y:210,action:p.action};
  }
  if(p.action==='amberEquip'||p.action==='amberEquipBack'){
   const rows=o.ocr||[],one=(text,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===text.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!witness||witness.session!==r.session||witness.frameId!==p.witnessFrameId||witness.timestamp>o.timestamp||o.timestamp-witness.timestamp>600000||!(witness.ocr||[]).some(q=>String(q.text).replace(/\s/g,'')==='Pyro/Amber'&&q.x>=100&&q.x<=400&&q.y<90)||!one('UID: 693306810',1600,1900,1030,1080)||!one('Fast Equip',100,350,0,80)||!one('Recommended Plan',30,400,100,160)||!one('Attribute Preview',450,800,490,550))return null;
   if(p.action==='amberEquipBack')return {key:'VK_ESCAPE',action:p.action};
   if(!one('No Set Bonus',480,760,430,490)||!one('1,383',1480,1650,550,610)||!one('1,512',1700,1880,550,610)||!one('56',1480,1650,610,680)||!one('73',1700,1880,610,680)||!one('88',1480,1650,680,740)||!one('88',1700,1880,680,740)||!one('Equip',1600,1820,970,1050))return null;
   return {x:1715,y:1020,action:p.action};
  }
  if(p.action==='amberConfirm'){
   const rows=o.ocr||[],one=(text,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===text.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('Amber / Level Up',100,400,15,80)||!one('UID: 693306810',1600,1900,1030,1080)||!one('108203',1600,1800,15,80)||!one('Lv. 7 +3',1100,1400,100,180)||!one('+15000 3152/3725',1600,1900,120,180)||!one('1,186',1450,1600,220,280)||!one('1,383',1700,1900,220,280)||!one('3',1480,1540,880,950)||!one('3',1520,1580,700,760)||!one('3000',1300,1430,980,1040)||!one('Level Up',1600,1830,980,1050))return null;
   return {x:1730,y:1020,action:p.action};
  }
  if(['selectAmber','amberAttributes','amberWeapons','amberArtifacts','amberClose','amberWeaponSwitch','amberFastEquip','amberLevel','amberPreview','amberBack'].includes(p.action)){
   const rows=o.ocr||[],one=(text,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===text.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('UID: 693306810',1600,1900,1030,1080))return null;
   if(p.action==='selectAmber')return one('Cryo / Kaeya',100,400,15,80)&&one('Artifact Details',1400,1850,270,340)&&one('Fast Equip',1400,1650,970,1040)?{x:912,y:47,action:p.action}:null;
   if(p.action==='amberPreview'||p.action==='amberBack'){
    if(!one('Amber / Level Up',100,400,15,80))return null;
    if(p.action==='amberBack')return {key:'VK_ESCAPE',action:p.action};
    return (one('Lv. 7',1100,1400,100,180)||one('Lv.7',1100,1400,100,180))&&one('108203',1600,1800,15,80)&&one('Auto Add',1650,1850,870,950)?{x:1760,y:917,action:p.action}:null;
   }
   if(!one('Pyro / Amber',100,400,15,80))return null;
   if(p.action==='amberClose')return one('Attributes',100,400,100,190)&&one('Level Up',1500,1850,970,1040)?{key:'VK_ESCAPE',action:'close'}:null;
   const labels={amberAttributes:'Attributes',amberWeapons:'Weapons',amberArtifacts:'Artifacts',amberWeaponSwitch:'Switch',amberFastEquip:'Fast Equip',amberLevel:'Level Up'},label=labels[p.action],found=rows.filter(q=>String(q.text).normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim().replace(/\s+\d{1,2}$/,'')===label&&(['amberAttributes','amberWeapons','amberArtifacts'].includes(p.action)?q.x>=100&&q.x<=400&&q.y>=100&&q.y<=750:q.x>=1400&&q.x<=1850&&q.y>=970&&q.y<=1040));
   if(found.length!==1)return null;const q=found[0];return {x:Math.round(q.x+q.width/2),y:Math.round(q.y+q.height/2),action:p.action};
  }
  if(p.action==='luminaAmbushBack'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('Lumina / Level Up',100,400,15,80)||!one('Lv.17',1100,1650,100,220)||!one('103604',1600,1800,15,80)||!one('2,116',1700,1900,220,310)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   return {key:'VK_ESCAPE',action:p.action};
  }
  if(p.action==='luminaAmbushConfirm'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('Lumina / Level Up',100,400,15,80)||!one('Lv. 13 +4',1100,1400,100,180)||!one('+40000 4656/8050',1600,1900,120,180)||!one('111604',1600,1800,15,80)||!one('8',1480,1540,880,950)||!one('8000',1300,1450,980,1040)||!one('2,116',1700,1900,220,280)||!one('Level Up',1600,1850,980,1040)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   return {x:1730,y:1020,action:p.action};
  }
  if(p.action==='luminaAmbushPreview'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('Lumina / Level Up',100,400,15,80)||!one('Lv. 13',1100,1400,100,180)||!one('4656/8050',1600,1900,120,180)||!one('111604',1600,1800,15,80)||!one('Auto Add',1650,1850,870,950)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   return {x:1760,y:917,action:p.action};
  }
  if(p.action==='luminaRecoveryConfirm'||p.action==='luminaRecoveryBack'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!(one('Lumina / Level Up',100,400,15,80)||one('Lumina / evel Up',100,400,15,80))||!one('UID: 693306810',1600,1900,1030,1080))return null;
   if(p.action==='luminaRecoveryBack')return one('101357',1600,1800,15,80)&&one('Lv. 13',1100,1650,100,220)&&one('1,815',1700,1900,220,310)?{key:'VK_ESCAPE',action:p.action}:null;
   if(!one('102357',1600,1800,15,80)||!one('Lv. 12 +1',1100,1400,100,180)||!one('+50006841/7225',1600,1900,120,180)||!one('1,815',1700,1900,220,280)||!one('1000',1300,1450,980,1040)||!one('Level Up',1600,1850,980,1040))return null;
   return {x:1730,y:1020,action:p.action};
  }
  if(p.action==='luminaRecoveryAdd'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).trim()===t&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('Lumina / Level Up',100,400,15,80)||!one('102357',1600,1800,15,80)||!one('6841/7225',1700,1900,120,180)||!one('Lv. 12',1100,1350,100,180)||!one('Amount to use',1100,1400,880,950)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   return {x:1615,y:917,action:p.action};
  }
  if(p.action==='luminaEquip'||p.action==='luminaEquipBack'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).trim()===t&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!witness||witness.session!==r.session||witness.frameId!==p.witnessFrameId||witness.timestamp>o.timestamp||o.timestamp-witness.timestamp>600000||!(witness.ocr||[]).some(q=>q.text==='Anemo / Lumina'&&q.x>100&&q.x<400&&q.y<80)||!one('Fast Equip',100,400,15,80)||!one('Lucky Dog',480,760,430,500)||!one('1,740',1480,1650,550,620)||!one('2,372',1700,1880,550,620)||!one('57',1480,1650,610,680)||!one('89',1700,1880,610,680)||!one('109',1480,1650,680,740)||!one('213',1700,1880,680,740)||!one('Equip',1600,1820,970,1050)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   return p.action==='luminaEquipBack'?{key:'VK_ESCAPE',action:p.action}:{x:1715,y:1020,action:p.action};
  }
  if(p.action==='selectKaeya'){
   const rows=o.ocr||[];if(rows.filter(q=>q.text==='Anemo / Lumina'&&q.x>100&&q.x<400&&q.y<80).length!==1||!rows.some(q=>q.text==='UID: 693306810'&&q.x>1600&&q.y>1030)||!rows.some(q=>q.text==='Attributes'&&q.x>100&&q.x<400&&q.y>100&&q.y<190))return null;
   return {x:1008,y:47,action:p.action};
  }
  if(p.action==='selectLumina'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).trim()===t&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!(one('Cryo / Kaeya',100,400,15,80)||one('Cryo  Kaeya',100,400,15,80))||!one('Kaeya',1400,1700,100,180)||!one('Attributes',100,400,100,190)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   return {x:815,y:47,action:p.action};
  }
  if(p.action==='luminaResultBack'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('Lumina / Level Up',100,400,15,80)||!one('102151',1600,1800,15,80)||!one('Lv. 12',1100,1650,100,220)||!one('1,740',1700,1900,220,310)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   return {key:'VK_ESCAPE',action:p.action};
  }
  if(['luminaWeapons','luminaArtifacts','luminaAttributes','luminaFastEquip','luminaClose','luminaRecoveryMap'].includes(p.action)){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).trim()===t&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('Anemo / Lumina',100,400,15,80)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   const label={luminaWeapons:'Weapons',luminaArtifacts:'Artifacts',luminaAttributes:'Attributes',luminaFastEquip:'Fast Equip',luminaClose:'Attributes',luminaRecoveryMap:'Attributes'}[p.action],q=rows.filter(q=>String(q.text).trim().replace(/[.\s]+\d{1,2}$/,'')===label&&(p.action==='luminaFastEquip'?q.x>1400&&q.y>950:q.x>80&&q.x<400&&q.y>90&&q.y<750));
   if(q.length!==1)return null;if((p.action==='luminaClose'||p.action==='luminaRecoveryMap'))return {key:'VK_ESCAPE',action:p.action};
   return {x:Math.round(q[0].x+q[0].width/2),y:Math.round(q[0].y+q[0].height/2),action:p.action};
  }
  if(p.action==='luminaConfirm'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(rows.filter(q=>/^Lumina\s*\/\s*Level Up$/.test(q.text)&&q.x>100&&q.x<400&&q.y>15&&q.y<80).length!==1||!one('108151',1600,1800,15,80)||!one('+30000 1978/3725',1600,1900,120,180)||!one('1,740',1700,1900,220,280)||!one('20',1380,1450,700,760)||!one('2',1500,1580,700,760)||!one('6000',1300,1450,980,1040)||!one('Level Up',1600,1850,980,1040)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   return {x:1730,y:1020,action:p.action};
  }
  if(p.action==='luminaReserve'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!witness||witness.session!==r.session||witness.frameId!==p.witnessFrameId||witness.timestamp>o.timestamp||o.timestamp-witness.timestamp>600000||!(witness.ocr||[]).some(q=>q.text==='Lumina / Level Up'&&q.x>100&&q.x<400&&q.y<80)||!one('108151',1600,1800,15,80)||!one('+50000 1978/3725',1600,1900,120,180)||!one('10000',1300,1450,980,1040)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   return {x:1430,y:917,clicks:4,action:p.action};
  }
  if(p.action==='luminaPreview'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(rows.filter(q=>/^Lumina\s*\/\s*Level Up$/.test(q.text)&&q.x>100&&q.x<400&&q.y>15&&q.y<80).length!==1||!one('108151',1600,1800,15,80)||!one('1978/3725',1700,1900,120,180)||!one('Select EXP materials',1300,1800,650,730)||!one('Auto Add',1650,1850,870,950)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   return {x:1760,y:917,action:p.action};
  }
  if(p.action==='luminaLevel'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).replace(/\s/g,'')===t.replace(/\s/g,'')&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!one('Anemo / Lumina',100,400,15,80)||!one('Lumina',1400,1700,100,180)||!(one('4656/8050',1650,1850,200,260)&&one('Level 13 / 20',1400,1700,200,260)||one('1978/3725',1650,1850,200,260)||one('6841/7225',1650,1850,200,260)&&one('Level 12 / 20',1400,1700,200,260))||!one('Attributes',100,400,100,190)||!(one('UID: 693306810',1600,1900,1030,1080)||witness&&witness.session===r.session&&witness.frameId===p.witnessFrameId&&witness.timestamp<=o.timestamp&&o.timestamp-witness.timestamp<=600000&&(witness.ocr||[]).some(q=>q.text==='UID: 693306810'&&q.x>1600&&q.y>1030))||!one('Level Up',1500,1800,970,1040))return null;
   return {x:1665,y:1008,action:p.action};
  }
  if(p.action==='confirmLevel20'||p.action==='closeLevel20'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).trim()===t&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!rows.some(q=>/^Kaeya[ /AI]+Leve[l]? Up$/.test(q.text)&&q.x>100&&q.x<400&&q.y<80)||!one('UID: 693306810',1600,1900,1030,1080))return null;
   if(p.action==='closeLevel20')return one('99823',1600,1800,15,80)&&rows.some(q=>/^Lv\.\s*20(?: MAX)?$/.test(q.text)&&q.x>1100&&q.y>100&&q.y<220)&&one('2,506',1700,1900,220,310)?{key:'VK_ESCAPE',action:p.action}:null;
   if(!one('109223',1600,1800,15,80)||!rows.some(q=>/^Lv\.\s*16 \+4 MAX$/i.test(q.text)&&q.x>1100&&q.x<1400&&q.y>100&&q.y<180)||!one('+46789 2186/10750',1600,1900,120,180)||!one('2,506',1700,1900,220,280)||!one('9400',1300,1430,980,1040)||!one('Level Up',1600,1830,980,1050))return null;
   return {x:1730,y:1020,action:p.action};
  }
  if(p.action==='previewLevel20'){
   const rows=o.ocr||[],one=(t,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).trim()===t&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!rows.some(q=>/^Kaeya[ /AI]+Leve[l]? Up$/.test(q.text)&&q.x>100&&q.x<400&&q.y<80)||!rows.some(q=>/^Lv\.\s*16$/.test(q.text)&&q.x>1100&&q.x<1300&&q.y>100&&q.y<180)||!one('109223',1600,1800,15,80)||!one('2,184',1700,1900,220,280)||!one('Auto Add',1650,1850,870,950))return null;
   return {x:1760,y:917,action:p.action};
  }
  if(p.action==='artifactEquip'||p.action==='artifactBack'){
   const rows=o.ocr||[],one=(text,x0,x1,y0,y1)=>rows.filter(q=>String(q.text).trim()===text&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   if(!witness||witness.session!==r.session||witness.frameId!==p.witnessFrameId||witness.timestamp>o.timestamp||o.timestamp-witness.timestamp>600000||!(witness.ocr||[]).some(q=>q.text==='Cryo / Kaeya'&&q.x>100&&q.x<400&&q.y<90))return null;
   if(!one("Traveling Doctor's",1400,1600,100,170)||!one('Handkerchief',1400,1600,150,210)||!one('Circlet of Logos',1400,1700,200,250)||!one('DEF',1400,1550,250,300)||!one('3.9%',1700,1900,250,300)||!one('Set Filter',200,400,970,1050))return null;
   if(p.action==='artifactBack')return {action:p.action,key:'VK_ESCAPE'};
   if(!one('Equip',1450,1650,970,1050)||rows.some(q=>/Equipped|Remove/.test(q.text)))return null;
   return {action:p.action,x:1555,y:1010};
  }
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
   const starter=one('1,700',1480,1650,550,610)&&one('1,829',1700,1880,550,610)&&one('102',1480,1650,610,680)&&one('119',1700,1880,610,680)&&one('No Set Bonus',480,750,430,490);
   const doctor=one('2,313',1480,1650,550,610)&&one('2,313',1700,1880,550,610)&&one('161',1480,1650,610,680)&&one('168',1700,1880,610,680)&&one('165',1480,1650,680,730)&&one('176',1700,1880,680,730)&&one('Traveling Doctor',480,760,430,490)&&one('2-Piece Set',1600,1900,430,490)&&one('20.0%',1700,1880,840,900);
   const adventurer=one('2,635',1480,1650,550,610)&&one('4,015',1700,1880,550,610)&&one('175',1480,1650,610,680)&&one('175',1700,1880,610,680)&&one('207',1480,1650,680,730)&&one('201',1700,1880,680,730)&&one('Adventurer',480,760,430,490)&&one('2-Piece Set',1600,1900,430,490)&&one('20.0%',1480,1650,840,900)&&one('0.0%',1700,1880,840,900);
   if((!starter&&!doctor&&!adventurer)||!one('Equip',1600,1820,970,1050))return null;
   const q=rows.find(q=>q.text==='Equip'&&q.x>1600&&q.y>970);return {x:Math.round(q.x+q.width/2),y:Math.round(q.y+q.height/2),action:'equip'};
  }
  if(p.action==='inspectEmptySands'){
   const rows=o.ocr||[],one=(text,x0,x1,y0,y1)=>rows.filter(q=>String(q.text||'').trim()===text&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   return one('Cryo / Kaeya',100,400,0,90)&&rows.some(q=>/^Artifacts\s+2$/.test(String(q.text||'').trim())&&q.x>=100&&q.x<=400&&q.y>=245&&q.y<=315)&&one('Fast Equip',1400,1600,970,1040)&&one('Switch',1600,1800,970,1040)&&one('Adventurer',1400,1600,360,425)&&one('UID: 693306810',1600,1900,1030,1080)?{action:p.action,x:1460,y:610}:null;
  }
  if(p.action==='inspectSandsTab'){
   const rows=o.ocr||[],one=(text,x0,x1,y0,y1)=>rows.filter(q=>String(q.text||'').trim()===text&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   return one("Adventurer's Flower",1400,1650,100,170)&&one('Flower of Life',1400,1650,160,210)&&one('Set Filter',200,400,970,1050)&&one('Equipped: Kaeya',1500,1700,900,970)&&one('UID: 693306810',1600,1900,1030,1080)?{action:p.action,x:310,y:47}:null;
  }
  if(p.action==='dismissArtifactTip'){
   const rows=o.ocr||[],one=(text,x0,x1,y0,y1)=>rows.filter(q=>String(q.text||'').trim()===text&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   return one("Berserker's Timepiece",1400,1650,100,170)&&rows.some(q=>String(q.text||'').startsWith('When you view an artifact in the Character Menu')&&q.x>=400&&q.x<=600&&q.y>=760&&q.y<=820)&&rows.some(q=>String(q.text||'').startsWith('This function can be toggled on and off')&&q.x>=500&&q.x<=700&&q.y>=820&&q.y<=875)&&one('UID: 693306810',1600,1900,1030,1080)?{action:p.action,x:960,y:750}:null;
  }
  if(p.action==='inspectUnusedSands'){
   const rows=o.ocr||[],one=(text,x0,x1,y0,y1)=>rows.filter(q=>String(q.text||'').trim()===text&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   return rows.filter(q=>String(q.text||'').replace(/\s/g,'')==='SandsofEon'&&q.x>=1400&&q.x<=1650&&q.y>=160&&q.y<=210).length===1&&one('Equipped: Lumina',1500,1700,900,970)&&one('Equip',1450,1650,970,1050)&&one('Set Filter',200,400,970,1050)&&rows.filter(q=>String(q.text||'').replace(/\s/g,'')==='UID:693306810'&&q.x>=1600&&q.x<=1900&&q.y>=1030&&q.y<=1080).length===1?{action:p.action,x:240,y:195}:null;
  }
  if(p.action==='equipUnusedSands'){
   const rows=o.ocr||[],one=(text,x0,x1,y0,y1)=>rows.filter(q=>String(q.text||'').trim()===text&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   return one("Lucky Dog's Hourglass",1400,1650,100,170)&&one('Sands of Eon',1400,1650,160,210)&&one('5.2%',1700,1850,190,250)&&one('Equip',1450,1650,970,1050)&&one('Set Filter',200,400,970,1050)&&!rows.some(q=>/^Equipped:/.test(String(q.text||'')))&&rows.filter(q=>String(q.text||'').replace(/\s/g,'')==='UID:693306810'&&q.x>=1600&&q.x<=1900&&q.y>=1030&&q.y<=1080).length===1?{action:p.action,x:1555,y:1010}:null;
  }
  if(p.action==='backFromEquippedSands'){
   const rows=o.ocr||[],one=(text,x0,x1,y0,y1)=>rows.filter(q=>String(q.text||'').trim()===text&&q.x>=x0&&q.x<=x1&&q.y>=y0&&q.y<=y1).length===1;
   return one("Lucky Dog's Hourglass",1400,1650,100,170)&&rows.filter(q=>/^Sands [oQ]f Eon$/.test(String(q.text||''))&&q.x>=1400&&q.x<=1650&&q.y>=160&&q.y<=210).length===1&&one('Equipped: Kaeya',1500,1700,900,970)&&one('Remove',1450,1650,970,1050)&&rows.filter(q=>String(q.text||'').replace(/\s/g,'')==='UID:693306810'&&q.x>=1600&&q.x<=1900&&q.y>=1030&&q.y<=1080).length===1?{action:p.action,key:'VK_ESCAPE'}:null;
  }
  const labels={attributes:'Attributes',weapons:'Weapons',artifacts:'Artifacts',artifactPicker:'Artifacts',talents:'Talents',level:'Level Up',fastEquip:'Fast Equip',enhanceWeapon:'Enhance',close:'Attributes'};
  const label=labels[p.action],rows=o.ocr||[];
  const exactCharacter=rows.filter(q=>String(q.text||'').trim()==='Kaeya'&&q.x>=1400&&q.x<=1700&&q.y>=100&&q.y<=180).length===1;
  if(!label||rows.filter(q=>(/^Cryo\s*\/\s*Kaeya$/.test(String(q.text||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim())||exactCharacter&&/^Cryo\s*[/iI]\s*(?:Kaeya|Keya|Kaea)$/.test(String(q.text||'').trim()))&&q.x>=100&&q.x<400&&q.y<90).length!==1)return null;
  if(p.action==='artifactPicker')return rows.some(q=>q.text==='Fast Equip'&&q.x>1400&&q.y>950)&&rows.some(q=>q.text==='Traveling Doctor'&&q.x>1400&&q.y>350&&q.y<450)&&rows.some(q=>q.text==='Artifact Details'&&q.x>1400&&q.y>270&&q.y<340)?{action:p.action,x:740,y:780}:null;
  if(p.action==='close'&&rows.some(q=>q.text.trim()==='Attributes'&&q.x>80&&q.x<400&&q.y>90&&q.y<200)&&rows.some(q=>/^(Level Up|Switch|Ascend)$/.test(q.text)&&q.x>1400&&q.y>950))return {action:'close',key:'VK_ESCAPE'};
  if(p.action==='enhanceWeapon'&&!rows.some(q=>q.text==="Traveler's Handy Sword"&&q.x>1400&&q.y>100&&q.y<190))return null;
  const matches=rows.filter(q=>(p.action==='artifacts'?String(q.text||'').normalize('NFKC').trim().replace(/\s+\d{1,2}$/,''):String(q.text||'').trim())===label&&(p.action==='level'||p.action==='fastEquip'||p.action==='enhanceWeapon'?q.x>1400&&q.y>950:q.x>80&&q.x<400&&q.y>90&&q.y<750));
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
 function recoveryMapReady(o,now,session){return !!(o&&o.session===session&&now>=o.timestamp&&now-o.timestamp<=1000&&o.hud&&o.hud.world&&o.hud.groundControls&&!o.hud.climbing&&!o.hud.dialogueReady&&!o.hud.auto&&!o.hud.choice&&(o.ocr||[]).some(q=>/^(?:UID)?[: ]*693306810$/.test(q.text)&&q.x>1600&&q.y>1030));}
 root.ActTwoTeam={target,upgradeReady,recoveryMapReady};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoTeam;
})(typeof globalThis!=='undefined'?globalThis:this);
