(function(root){
 'use strict';
 const objective='Collect three Iron Chunks and give them to Wagner';
 function ready(o,now,session){
  const h=o&&o.hud,m=o&&o.map,hp=h&&h.health;
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&
   m&&m.map==='Teyvat'&&Math.hypot(m.x+1137,m.y-2235)<15&&h.world&&h.groundControls&&!h.climbing&&!h.auto&&!h.dialogueReady&&!h.choice&&
   hp&&hp.max===1700&&hp.current>=1615&&h.enemyBarDiagnostic&&!(h.enemyBars||[]).length&&
   (h.objectives||[]).includes(objective));
 }
 function plan(p,r,now){return !!(p&&p.reviewed===true&&!p.usedAt&&p.session===r.session&&p.frameId===r.expectedFrameId&&
  Number.isFinite(p.createdAt)&&now>=p.createdAt&&now-p.createdAt<=60000&&Array.isArray(p.actions)&&p.actions.length>0&&p.actions.length<=8&&
  p.actions.every(a=>a&&['VK_W','VK_A','VK_S','VK_D','VK_SPACE','VK_LBUTTON','VK_E'].includes(a.key)&&Number.isInteger(a.ms)&&a.ms>=60&&a.ms<=400&&
   (!['VK_SPACE','VK_LBUTTON','VK_E'].includes(a.key)||a.ms===60)));}
 function pickup(o){const rows=o.ocr||[];return rows.some(r=>r.text==='F'&&r.x>1050&&r.x<1260&&r.y>300&&r.y<800)&&
  rows.some(r=>r.text==='Iron Chunk'&&r.x>1100&&r.x<1600&&r.y>300&&r.y<800);}
 root.ActTwoOre={ready,plan,pickup};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoOre;
})(typeof globalThis!=='undefined'?globalThis:this);
