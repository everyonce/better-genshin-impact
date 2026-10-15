(function(root){
'use strict';
function title(rows){const r=(rows||[]).filter(x=>x.x>1300&&x.x<1800&&x.y>110&&x.y<180);return r.some(x=>x.text==='Delicious Chicken-Mushroom Skewer')||r.some(x=>x.text==='Delicious Chicken-Mushroom')&&r.some(x=>x.text==='Skewer');}
function target(o,now,session,used){
 if(!o||o.session!==session||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!o.hud||o.hud.world||o.hud.bigMap||o.hud.dialogueReady||o.hud.climbing)return null;
 const rows=o.ocr||[],find=(t,x1,x2,y1,y2)=>rows.filter(r=>r.text===t&&r.x>x1&&r.x<x2&&r.y>y1&&r.y<y2),one=(...a)=>find(...a).length===1;
 if(!one('Food',100,250,0,80)||!title(rows)||!rows.some(r=>r.x>1600&&r.y>1020&&/^(?:UID)?[: ]*693306810$/.test(r.text)))return null;
 const confirm=find('Confirm',1100,1260,730,800),use=find('Use',1600,1800,980,1040);
 if(!confirm.length&&use.length===1&&!used)return {action:'open',x:Math.round(use[0].x+use[0].width/2),y:Math.round(use[0].y+use[0].height/2)};
 if(confirm.length!==1||!one('Amount to use',600,900,590,670))return null;
 if(used&&one('Cancel',650,850,730,800))return {action:'close',key:'VK_ESCAPE'};
 if(one('Traveler',800,1000,240,320)&&[730,870,1010,1160].every(x=>rows.filter(r=>/^Lv\./.test(r.text)&&r.x>=x&&r.x<=x+40&&r.y>=480&&r.y<=525).length===1))return {action:'selectKaeya',x:1045,y:440};
 if(one('Kaeya',800,1000,240,320)&&o.hud.foodQuantity&&o.hud.foodQuantity.value===1&&o.hud.foodQuantity.frameId===o.frameId)return {action:'useOneSkewer',x:Math.round(confirm[0].x+confirm[0].width/2),y:Math.round(confirm[0].y+confirm[0].height/2)};
 return null;
}
root.ActTwoSkewer={title,target};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoSkewer;
})(typeof globalThis!=='undefined'?globalThis:this);
