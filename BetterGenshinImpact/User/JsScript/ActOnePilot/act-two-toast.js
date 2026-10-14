var ActTwoToast=(function(){
 function target(o,now){
  if(!o||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||!o.hud||o.hud.world||o.hud.health||o.hud.dialogueReady)return null;
  var rows=o.ocr||[];function one(text,x1,x2,y1,y2){var a=rows.filter(function(r){return r.text.trim()===text&&r.x>=x1&&r.x<=x2&&r.y>=y1&&r.y<=y2;});return a.length===1?a[0]:null;}
  if(one('Obtained',800,1100,250,330)&&one("Fisherman's Toast",800,1150,340,410)&&one('Owned: 1',1450,1650,900,960)&&one('Click anywhere in the blank area to continue',600,800,710,790))return {action:'continue',x:960,y:800};
  if(one('Item to purchase',750,1150,230,310)&&one("Fisherman's Toast",730,1100,320,380)&&one('Qty.',900,1020,480,530)&&one('1',920,1000,530,580)&&one('Left Today: 5',850,1100,620,675)&&one('Cost',830,950,670,725)&&one('1025',940,1100,670,725)&&one('71120',1650,1800,10,80)&&one('Purchase',1070,1300,740,820)&&one('Cancel',680,850,740,820))return {action:'buyOne',x:1180,y:780,cost:{mora:1025,quantity:1}};
  if(!one('Restaurant',100,300,10,80))return null;
  if(one("Fisherman's Toast",1300,1750,100,180)&&one('Owned: 1',1450,1650,900,960)&&one('Purchase up to 4/5',980,1250,340,410)&&one('70095',1650,1800,10,80))return {action:'close',x:1840,y:48};
  if(one('Teyvat Fried Egg',1300,1650,100,180)&&one("Fisherman's Toast",200,600,340,410)&&one('1025',200,350,400,450))return {action:'selectToast',x:500,y:400};
  if(one("Fisherman's Toast",1300,1750,100,180)&&one('1025',200,350,400,450)&&one('Purchase',1550,1800,970,1050)&&one('Purchase up to 5/5',980,1250,340,410))return {action:'openPurchase',x:1700,y:1018};
  return null;
 }
 return {target:target};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=ActTwoToast;
