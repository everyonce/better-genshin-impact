(function(root){
 'use strict';
 function ambushObjective(rows){
  const expected='defeattheattackingmonsters';
  return (rows||[]).some(t=>{
   const text=String(t).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z]/g,'');
   if(text.length!==expected.length||!text.startsWith('defeatthe'))return false;
   let differences=0;for(let i=9;i<expected.length;i++)if(text[i]!==expected[i]&&++differences>2)return false;
   return true;
  });
 }
 function anchored(b){const a=b&&b.levelAnchor;return !!(a&&String(a.text).toUpperCase().replace(/[\s.|,]/g,'')==='LV5'&&[a.x,a.y,a.width,a.height].every(Number.isFinite)&&a.width>0&&a.height>0&&Math.abs(a.x+a.width/2-b.x)<=150&&b.y-a.y-a.height/2>=8&&b.y-a.y-a.height/2<=50);}
 function depletedBar(b){return !!(anchored(b)&&b.width>=16&&b.width<=64&&b.height>=3&&b.height<=9&&b.width/b.height>=3.5&&b.rectangularity>=.7&&b.rectangularity<.8);}
 function closeBar(b){return anchored(b)&&b.width>=30&&b.width<=300&&b.height>20&&b.height<=32&&b.width/b.height>=3.5&&b.rectangularity>=.8&&b.rectangularity<=1.05;}
 function targets(bars){return (bars||[]).filter(b=>[b.x,b.y,b.width,b.height,b.rectangularity].every(Number.isFinite)&&b.x>=350&&b.x<=1600&&b.y>=30&&b.y<=900&&b.width>=16&&b.width<=300&&b.height>=3&&(b.height<=20||closeBar(b))&&b.width/b.height>=3.5&&(b.rectangularity>=.8||depletedBar(b))&&b.rectangularity<=1.05);}
 function framingTargets(bars){return (bars||[]).filter(b=>targets([b]).length||[b.x,b.y,b.width,b.height,b.rectangularity].every(Number.isFinite)&&b.x>=0&&b.x<=1920&&b.y>=30&&b.y<=900&&b.width>=16&&b.width<=300&&b.height>=3&&(b.height<=20||closeBar(b))&&b.width/b.height>=3.5&&b.rectangularity>=.8&&b.rectangularity<=1.05&&anchored(b));}
 function centered(bars){return targets(bars).some(b=>Math.abs(b.x-960)<=180);}
 function stationaryReady(bars){return centered(bars)||framingTargets(bars).some(b=>b.width>=30&&b.height>=10);}
 function cameraDelta(bars){const barsByCenter=framingTargets(bars).sort((a,b)=>Math.abs(a.x-960)-Math.abs(b.x-960));if(!barsByCenter.length||centered(bars))return 0;return Math.max(-200,Math.min(200,Math.round((barsByCenter[0].x-960)*.45)));}
 function pausedWitness(w,initial,now,original){return !!(w&&initial&&w.session===initial.session&&w.frameId<initial.frameId&&now>=w.timestamp&&now-w.timestamp<=600000&&original(w)&&w.map&&w.map.map==='Teyvat'&&Math.hypot(w.map.x+1220,w.map.y-2315)<=35&&w.hud&&w.hud.world&&w.hud.health&&w.hud.health.max===2635&&ambushObjective(w.hud.objectives));}
 function eligible(o,initial,w,now){
  const h=o&&o.hud,p=o&&o.map,hp=h&&h.health;
  return !!(o&&initial&&w&&o.acquisition===true&&o.session===initial.session&&o.accountPauseFrameId===initial.frameId&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&h&&h.world===true&&h.groundControls===true&&!h.climbing&&!h.menu&&hp&&hp.max===2635&&hp.current>=hp.max*.9&&hp.current<=hp.max&&p&&p.map==='Teyvat'&&Math.hypot(p.x+1220,p.y-2315)<=35&&Math.hypot(p.x-w.map.x,p.y-w.map.y)<=12&&ambushObjective(h.objectives)&&framingTargets(h.enemyBars).length>=1&&framingTargets(h.enemyBars).length<=5&&(h.enemyBars||[]).length<=5);
 }
 function read(img,api){
  // One same-image read. No full-screen OCR, PNG encoding or exposed retry.
  const hp=api.health(img),objective=api.rows(img,65,230,630,85),controls=api.controls(img),header=api.rows(img,100,20,350,70);
  const menu=header.some(r=>/^(Food|Weapons|Artifacts|Character Development Items|Materials|Gadgets|Quest|Precious Items|Furnishings|In Progress)$/.test(String(r.text).trim()));
  const ground=api.ground(controls),bars=api.bars(img);
  return {ocr:objective.concat(controls,header),hud:{world:!!hp&&ground&&!menu,groundControls:ground,climbing:controls.some(r=>r.text==='Space'),menu:menu,health:hp,enemyBars:bars,objectives:objective.map(r=>String(r.text).trim())}};
 }
 root.ActTwoCombatAcquisition={ambushObjective,framingTargets,stationaryReady,centered,cameraDelta,depletedBar,targets,pausedWitness,eligible,read};
 if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoCombatAcquisition;
})(typeof globalThis!=='undefined'?globalThis:this);
