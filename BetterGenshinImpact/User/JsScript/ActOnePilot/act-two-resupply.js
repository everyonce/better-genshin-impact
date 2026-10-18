var ActTwoResupply=(function(){
 function target(o,now){
  if(!o||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||!o.hud||o.hud.world||o.hud.health||o.hud.dialogueReady)return null;
  var r=o.ocr||[];function one(t,x1,x2,y1,y2){return r.filter(a=>String(a.text).trim()===t&&a.x>=x1&&a.x<=x2&&a.y>=y1&&a.y<=y2).length===1;}
  if(one('Obtained',800,1100,250,330)&&one('Chicken-Mushroom Skewer',730,1200,340,410)&&one('Click anywhere in the blank area to continue',600,800,710,790))return {action:'continue',x:960,y:800};
  if(one('Restaurant',100,300,10,80)&&one('108050',1600,1800,10,80)&&one("Fisherman's Toast",1300,1800,100,180)&&one('Owned: 1',1450,1650,900,960)&&!r.some(a=>a.text==='Chicken-Mushroom Skewer'))return {action:'close',x:1840,y:48};
  if(one('Item to purchase',750,1150,230,310)&&one('Chicken-Mushroom Skewer',730,1230,320,380)&&one('Qty.',900,1020,480,530)&&one('Left Today: 5',850,1100,620,675)&&one('Cost',830,950,670,725)&&one('110300',1600,1800,10,80)&&one('Purchase',1070,1300,740,820)&&one('Cancel',680,850,740,820)){
   if(one('1',920,1000,530,580)&&one('450',940,1100,670,725)&&one('5',1200,1250,580,625))return {action:'setFive',x:1178,y:602};
   if(one('5',920,1000,525,580)&&one('2250',940,1100,670,725))return {action:'buyFive',x:1180,y:780,cost:{mora:2250,quantity:5,item:'Chicken-Mushroom Skewer'}};
   return null;
  }
  if(!one('Restaurant',100,300,10,80)||!one('110300',1600,1800,10,80)||!one('Chicken-Mushroom Skewer',200,700,230,280)||!one('450',200,350,280,330)||!one('Purchase up to 5/5',980,1250,230,285))return null;
  if(one('Teyvat Fried Egg',1300,1700,100,180)&&one('Owned: 7',1450,1650,900,960))return {action:'selectSkewer',x:500,y:280};
  if(one('Chicken-Mushroom Skewer',1300,1800,100,180)&&!r.some(a=>/^Owned:/.test(a.text))&&one('Purchase',1550,1800,970,1050))return {action:'openPurchase',x:1700,y:1018};
  return null;
 }
 return {target:target};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=ActTwoResupply;
