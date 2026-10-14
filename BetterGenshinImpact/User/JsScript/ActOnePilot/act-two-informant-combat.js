(function(root){
 'use strict';
 function ready(o,now,session){
  const h=o&&o.hud,m=o&&o.map,hp=h&&h.health,rows=o&&o.ocr||[];
  const text=rows.filter(r=>r.x<700&&r.y>=230&&r.y<360).sort((a,b)=>a.y-b.y||a.x-b.x).map(r=>r.text).join('').replace(/[^a-z]/gi,'').toLowerCase();
  const ids=rows.filter(r=>r.x>1600&&r.y>1040&&/^(?:UID)?[: ]*\d{9}$/.test(String(r.text).trim()));
  return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&
   m&&m.map==='Teyvat'&&Math.hypot(m.x+1135,m.y-2305)<45&&h&&h.world&&h.groundControls&&!h.climbing&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&
   (text.includes('defeattheopponentsattackingtheinformant')||(h.objectives||[]).includes('Defeat the opponents attacking the informant'))&&ids.length&&ids.every(r=>/693306810$/.test(String(r.text).trim()))&&
   hp&&hp.max===1700&&hp.current>=1190&&hp.current<=hp.max&&h.enemyBarDiagnostic&&Array.isArray(h.enemyBars));
 }
 async function run(initial,api,observe){
  let current=initial,baseline=null,empty=0,lastSkill=-Infinity,moves=0;
  const began=api.now(),session=initial.session,result={status:'stopped',step:'actTwoInformantCombat',attacks:0,skills:0,approaches:0,cycles:0,questComplete:false};
  try{
   for(let i=0;i<14&&api.now()-began<25000;i++){
    api.checkStop();
    if(!ready(current,api.now(),session)){result.reason='Encounter objective, account, health, position or controls changed';break;}
    if(baseline===null)baseline=current.hud.health.current;
    if(baseline-current.hud.health.current>255){result.reason='Health dropped more than 15 percent; pause for recovery';break;}
    const closeEnemy=(current.ocr||[]).some(r=>/^Lv\.\s*5$/.test(String(r.text).trim())&&r.x>400&&r.x<1550&&r.y>300&&r.y<800);
    if(!current.hud.enemyBars.length&&!closeEnemy){
     if(++empty>=2){result.reason='No enemy bars in two fresh frames; inspect objective';break;}
     await api.sleep(200);current=await observe();continue;
    }
    empty=0;result.cycles++;
    // This witnessed encounter is already in melee range. Bar width is remaining
    // health, not distance; let native melee targeting handle nearby attackers.
    if(api.now()-lastSkill>=6500){await api.key('VK_E',60,current);lastSkill=api.now();result.skills++;await api.sleep(450);}
    else {for(let hit=0;hit<3;hit++){await api.key('VK_LBUTTON',60,current);result.attacks++;await api.sleep(200);}}
    current=await observe();
   }
   result.reason=result.reason||'Finite combat cycle budget reached';
   result.fieldFrameId=current.frameId;result.fieldHealth=current.hud&&current.hud.health;
   return result;
  }finally{await api.release();}
 }
 root.ActTwoInformantCombat={ready,run};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoInformantCombat;
})(typeof globalThis!=='undefined'?globalThis:this);
