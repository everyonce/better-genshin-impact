var ActTwoCooking=(function(){
 function target(o,now){
  if(!o||now<o.timestamp||now-o.timestamp>1000||!o.hud||o.hud.world||o.hud.dialogueReady||o.hud.health)return null;
  var rows=o.ocr||[];function one(text,x1,x2,y1,y2){var a=rows.filter(function(r){return (r.text===text||/^\d+\/1$/.test(text)&&String(r.text).replace(/\s/g,'')===text)&&r.x>=x1&&r.x<=x2&&r.y>=y1&&r.y<=y2;});return a.length===1?a[0]:null;}
  if(one('Character Selection',100,400,0,80)&&one('Amber',140,300,330,370)&&one('No Character Bonus',140,400,370,410))return {x:240,y:365,action:'selectAmber'};
  if(one('Perfect',850,1100,240,300)&&one('Obtained',800,1100,350,430)&&one('Confirm',850,1100,860,930)&&!rows.some(function(r){return /Choose amount|Cancel|Purchase/.test(r.text);}))return {x:960,y:905,action:'confirmAutoResult'};
  if(one('Perfect',850,1100,240,300)&&[1,2,3,4,5].some(n=>one('Proficiency '+n+' / 5',800,1150,290,340))&&one('Obtained',800,1100,350,430)&&one('Confirm',850,1100,860,930))return {x:960,y:905,action:'confirm'};
  if(!one('Cook',100,300,0,80))return null;
  var dish=one('Chicken-Mushro',65,220,285,310)&&one('om Skewer',65,220,305,330);
  if(dish&&one('Amber',1650,1850,285,340)&&one('No Character Bonus',1500,1850,340,430)&&one('2/1',75,160,525,555)&&one('16/1',175,270,525,555)&&one('Choose amount to cook',700,1200,270,330)&&one('2',1220,1280,560,620)&&one('Confirm',1100,1280,720,790)&&one('Cancel',680,850,720,790)){
   if(one('1',920,1000,430,480))return {x:1315,y:590,action:'quantityTwo'};
   if(one('2',920,1000,430,480))return {x:1180,y:758,action:'cookTwo',cost:{mushroom:2,fowl:2,quantity:2}};
   return null;
  }
  if(rows.some(function(r){return r.text==='Choose amount to cook'||r.text==='Confirm'&&r.y>=720&&r.y<=790||r.text==='Cancel'&&r.y>=720&&r.y<=790;}))return null;
  if(dish&&one('Amber',1650,1850,285,340)&&one('No Character Bonus',1500,1850,340,430)&&one('Auto Cook',700,1000,970,1040)&&one('Cooking ingredients required',65,400,400,450)&&one('2/1',75,160,525,555)&&one('16/1',175,270,525,555)&&one('Owned',65,170,340,390)&&one('0',175,210,340,390))return {x:790,y:1015,action:'openAutoCook'};
  if(dish&&one('Cook Manually',800,1100,970,1040)&&one('Kaeya',1650,1850,285,340)&&one('Select Character',1500,1850,100,160))return {x:1840,y:175,action:'character'};
  var ingredients=[[1,3],[5,14],[4,13],[3,12]].some(pair=>one(pair[0]+'/1',75,160,525,555)&&one(pair[1]+'/1',175,270,525,555));
  if(dish&&one('Amber',1650,1850,285,340)&&one('No Character Bonus',1500,1850,340,430)&&one('Cook Manually',800,1100,970,1040)&&one('Cooking ingredients required',65,400,400,450)&&ingredients)return {x:960,y:1015,action:'manual',cost:{mushroom:1,fowl:1}};
  if(!one('Chicken-Mushroom Skewer',1300,1800,110,170))return null;
  if(one('Proficiency: 5/5',1300,1600,400,470)&&one('Owned: 2',1300,1500,180,230)&&one('0/1',1330,1420,675,720)&&one('14/1',1430,1450,675,720))return {x:1840,y:48,action:'exit'};
  var button=one('Cook',1550,1800,970,1040);
  if(button&&one('Ingredients',1300,1500,550,620)&&[0,1,2,3,4,5].some(n=>one('Proficiency: '+n+'/5',1300,1600,400,470)))return {x:1700,y:1015,action:'prepare'};
  return null;
 }
 function peak(state,count){
  if(state.peak!==null)return count<=state.peak-300;
  if(count<=600){state.candidate=null;state.stable=0;return false;}
  if(state.candidate!==null&&Math.abs(count-state.candidate)<=20){state.candidate=Math.max(count,state.candidate);state.stable++;if(state.stable>=3)state.peak=state.candidate;}
  else{state.candidate=count;state.stable=1;}return false;
 }
 return {target:target,peak:peak};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=ActTwoCooking;
