(function(root){
 'use strict';
 const anchor={x:-867.23413,y:1992.874,map:'Teyvat'}; // tp.json5 tranPosition; map7292 reviewed.
 function candidate(p,previous){return !!(p&&p.map==='Teyvat'&&Number.isFinite(p.x)&&Number.isFinite(p.y)&&Math.hypot(p.x-anchor.x,p.y-anchor.y)<=35&&(!previous||Math.hypot(p.x-previous.x,p.y-previous.y)<=2));}
 function safe(o,now,session){const h=o&&o.hud;return !!(o&&o.session===session&&now>=o.timestamp&&now-o.timestamp<=1000&&h&&h.world&&h.groundControls&&!h.climbing&&!h.auto&&!h.bigMap&&!h.journal&&!h.dialogueReady&&!h.choice&&h.health&&h.health.current===4015&&h.health.max===4015&&h.enemyBarDiagnostic&&h.enemyBarDiagnostic.level==='any'&&Array.isArray(h.enemyBars)&&!h.enemyBars.length&&!(h.objectives||[]).length&&(o.ocr||[]).some(r=>/^(?:UID)?[: ]*693306810$/.test(String(r.text).trim())&&r.x>1600&&r.y>1020));}
 async function run(initial,api){let o=initial;const began=api.now(),result={status:'stopped',localizationVerified:false,positionPairPlausible:false,navigationAuthorized:false,movementInputs:0,anchor,method:'SIFT',samples:[]};
  function check(){api.check();if(api.now()-began>9000||!safe(o,api.now(),initial.session))throw Error('Localization budget or safe field changed');}
  try{
   check();let at=api.now();const seed=await api.seed(anchor);result.seed={candidate:seed,elapsedMs:api.now()-at};
   // Seeding only constrains the native search. It never establishes current position.
   if(api.now()-at>4000)throw Error('Native anchor seed too slow');
   o=await api.observe();check();
   for(let i=0;i<2;i++){
    at=api.now();const p=await api.read();result.samples.push({candidate:p,startedAt:at,elapsedMs:api.now()-at,guardFrameId:o.frameId});
    if(api.now()-at>4000||!candidate(p,i?result.samples[0].candidate:null))throw Error('SIFT position unknown, outside known anchor or discontinuous');
    o=await api.observe();check();
   }
   result.positionPairPlausible=true;result.position=result.samples[1].candidate;result.reason='Two stationary SIFT positions agree near anchor; independent spatial verification still required';
  }catch(e){result.reason=String(e.message||e);}finally{await api.release();}
  result.fieldFrameId=o.frameId;result.health=o.hud&&o.hud.health;result.exposureMs=api.now()-began;return result;
 }
 root.LocalizationProbe={anchor,candidate,safe,run};if(typeof module!=='undefined'&&module.exports)module.exports=root.LocalizationProbe;
})(typeof globalThis!=='undefined'?globalThis:this);
