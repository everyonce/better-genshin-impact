(function(root){
 'use strict';
 function ready(o,now,session){
  const h=o&&o.hud,m=o&&o.map;
  const site=h&&m&&(h.groundControls&&!h.climbing&&Math.hypot(m.x+1266.35,m.y-1934.03)<=2||h.climbing&&!h.groundControls&&Math.abs(m.cameraAngle-202)<=8&&Math.hypot(m.x+1266.05078125,m.y-1892.8818359375)<=.6&&(o.ocr||[]).some(r=>r.text==='X'&&r.x>1550&&r.y>980)&&(o.ocr||[]).some(r=>r.text==='Space'&&r.x>1650&&r.y>980));
  return !!(o&&o.session===session&&now>=o.timestamp&&now-o.timestamp<=1000&&h&&h.world&&site&&!h.auto&&!h.choice&&!h.journal&&!h.bigMap&&h.health&&h.health.current===4015&&h.health.max===4015&&Array.isArray(h.enemyBars)&&!h.enemyBars.length&&m&&m.map==='Teyvat'&&(h.objectives||[]).some(t=>t.replace(/\s/g,'')==='Followtherouteandflytothefinishlineintime')&&(o.ocr||[]).some(r=>/693306810$/.test(r.text)&&r.x>1600&&r.y>1020));
 }
 async function run(api,launch,drop){
  const r={dropPresses:0,landingSamples:[],groundControlsConfirmed:false};
  try{
   if(drop){api.check();await api.drop();r.dropPresses++;api.release();await api.sleep(150);}
   r.deployment=drop?await launch.recover(api):await launch.run(api,true);
   if(r.deployment.opened){
    let grounds=0;
    for(let i=0;i<10;i++){api.release();await api.sleep(100);api.check();const s=await api.sample();r.landingSamples.push(s);if(!s||!s.valid)break;grounds=s.groundControls&&!s.climbing&&!s.space?grounds+1:0;if(grounds>=2){r.groundControlsConfirmed=true;break;}}
   }
  }finally{api.release();}
  return r;
 }
 root.ActTwoLaunchPractice={ready,run};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoLaunchPractice;
})(typeof globalThis!=='undefined'?globalThis:this);
