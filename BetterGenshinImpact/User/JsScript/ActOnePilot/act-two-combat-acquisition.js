(function(root){
 'use strict';
 function targets(bars){return (bars||[]).filter(b=>[b.x,b.y,b.width,b.height,b.rectangularity].every(Number.isFinite)&&b.x>=350&&b.x<=1600&&b.y>=30&&b.y<=900&&b.width>=16&&b.width<=300&&b.height>=3&&b.height<=20&&b.width/b.height>=3.5&&b.rectangularity>=.8&&b.rectangularity<=1.05);}
 function pausedWitness(w,initial,now,original){return !!(w&&initial&&w.session===initial.session&&w.frameId<initial.frameId&&now>=w.timestamp&&now-w.timestamp<=600000&&original(w)&&w.map&&w.map.map==='Teyvat'&&Math.hypot(w.map.x+1220,w.map.y-2315)<=35&&w.hud&&w.hud.world&&w.hud.health&&w.hud.health.max===2635&&(w.hud.objectives||[]).includes('Defeat the attacking monsters'));}
 function eligible(o,initial,w,now){
  const h=o&&o.hud,p=o&&o.map,hp=h&&h.health;
  return !!(o&&initial&&w&&o.acquisition===true&&o.session===initial.session&&o.accountPauseFrameId===initial.frameId&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&h&&h.world===true&&h.groundControls===true&&!h.climbing&&!h.menu&&hp&&hp.max===2635&&hp.current>=hp.max*.9&&hp.current<=hp.max&&p&&p.map==='Teyvat'&&Math.hypot(p.x+1220,p.y-2315)<=35&&Math.hypot(p.x-w.map.x,p.y-w.map.y)<=12&&(h.objectives||[]).includes('Defeat the attacking monsters')&&targets(h.enemyBars).length>=1&&targets(h.enemyBars).length<=5&&(h.enemyBars||[]).length<=5);
 }
 function read(img,api){
  // One same-image read. No full-screen OCR, PNG encoding or exposed retry.
  const hp=api.health(img),objective=api.rows(img,65,230,630,85),controls=api.controls(img),header=api.rows(img,100,20,350,70);
  const menu=header.some(r=>/^(Food|Weapons|Artifacts|Character Development Items|Materials|Gadgets|Quest|Precious Items|Furnishings|In Progress)$/.test(String(r.text).trim()));
  const ground=api.ground(controls),bars=api.bars(img);
  return {ocr:objective.concat(controls,header),hud:{world:!!hp&&ground&&!menu,groundControls:ground,climbing:controls.some(r=>r.text==='Space'),menu:menu,health:hp,enemyBars:bars,objectives:objective.map(r=>String(r.text).trim())}};
 }
 root.ActTwoCombatAcquisition={targets,pausedWitness,eligible,read};
 if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoCombatAcquisition;
})(typeof globalThis!=='undefined'?globalThis:this);
