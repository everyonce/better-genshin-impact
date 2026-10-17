(function(root){
 'use strict';
 function ready(o,now,session){
  if(!o||o.session!==session||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||!o.hud||o.hud.world||o.hud.health||o.hud.choice||o.hud.dialogueReady)return false;
  const rows=o.ocr||[],has=(text,x0,x1,y0,y1)=>rows.filter(r=>String(r.text).trim()===text&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1).length===1;
  return has('Souvenir Shop',100,350,10,80)&&has('Exchange',1400,1850,950,1040)&&rows.some(r=>r.x>1600&&r.y>1030&&/^(?:UID)?[: ]*693306810$/.test(String(r.text).trim()))&&['Agnidus Agate Sliver','Varunada Lazurite Sliver','Vayuda Turquoise Sliver'].every(t=>has(t,80,600,90,600))&&!rows.some(r=>/^(Confirm|Cancel|Quantity|Purchase)$/.test(String(r.text).trim()));
 }
 root.ActTwoSouvenir={ready};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoSouvenir;
})(typeof globalThis!=='undefined'?globalThis:this);
