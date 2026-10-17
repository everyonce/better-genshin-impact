(function(root){
'use strict';
function permit(o,w,p,r,now,inventory,kind){
 const h=w&&w.hud,hp=h&&h.health,m=w&&w.map;
 const practice=!!(p&&p.practice===true&&m&&m.map==='Teyvat'&&Math.hypot(m.x+1265.917,m.y-1928.381)<=8&&hp&&hp.current===hp.max&&Array.isArray(h.enemyBars)&&!h.enemyBars.length&&!(h.objectives||[]).length);
 const encounter=!!(p&&p.practice!==true&&h&&(h.objectives||[]).some(t=>String(t).replace(/[\s-]/g,'')==='Defeatallopponents6/7'));
 return !!(inventory&&w&&o&&o.session===r.session&&p&&p.reviewed===true&&!p.usedAt&&p.session===r.session&&p.frameId===r.expectedFrameId&&p.witnessFrameId===w.frameId&&w.frameId<p.frameId&&now>=p.createdAt&&now-p.createdAt<=120000&&w.session===r.session&&now>=w.timestamp&&now-w.timestamp<=600000&&h.world&&h.groundControls&&!h.climbing&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.bigMap&&!h.journal&&hp&&([2635,4015].includes(hp.max)||kind==='map'&&[2372,2451].includes(hp.max))&&hp.current>0&&hp.current<=hp.max&&(practice||encounter)&&((w.ocr||[]).some(x=>x.text==='Lumina'&&x.x>1650&&x.y>=240&&x.y<=300)||(p.partyReviewed===true&&p.practice!==true&&(w.ocr||[]).some(x=>x.text==='Kaeya'&&x.x>1650&&x.y>=430&&x.y<=485)&&['1','2','4'].every((n,i)=>(w.ocr||[]).some(x=>x.text===n&&x.x>1850&&Math.abs(x.y-[262,353,532][i])<20))))&&((w.ocr||[]).some(x=>x.text==='1'&&x.x>1850&&x.y>=240&&x.y<=300)||kind==='map'&&p.partyReviewed===true&&(w.ocr||[]).some(x=>x.text==='Lumina'&&x.x>1650&&x.y>=240&&x.y<=300)&&(w.ocr||[]).some(x=>x.text==='Kaeya'&&x.x>1650&&x.y>=430&&x.y<=485)||kind==='map'&&[2372,2451].includes(hp.max)&&['2','3','4'].every((n,i)=>(w.ocr||[]).some(x=>x.text===n&&x.x>1850&&Math.abs(x.y-[353,445,532][i])<20)))&&(w.ocr||[]).some(x=>/693306810$/.test(x.text)&&x.x>1600&&x.y>1020));
}
root.ActTwoEmergencySwitch={permit};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoEmergencySwitch;
})(typeof globalThis!=='undefined'?globalThis:this);
