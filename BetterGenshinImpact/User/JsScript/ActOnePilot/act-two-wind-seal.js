(function(root){
 'use strict';
 function fresh(o,now,session){return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000);}
 function eye(o){const r=o&&o.ocr||[];return r.some(t=>t.text.trim()==='Eye of the Storm'&&t.x>=800&&t.x<=900&&t.y<=45)&&r.some(t=>t.text.trim()==='Restless Pure Elemental'&&t.x>=800&&t.x<=900&&t.y>=40&&t.y<=75)&&r.some(t=>/^Lv\.?\s*9$/.test(t.text.trim())&&t.x>=680&&t.x<=730&&t.y>=65&&t.y<=100);}
 function ground(o,now,session){const h=o&&o.hud,p=h&&h.health;return !!(fresh(o,now,session)&&eye(o)&&h.world&&h.groundControls&&!h.climbing&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&p&&p.max===4015&&p.current===4015&&(o.ocr||[]).some(t=>/693306810$/.test(t.text.trim())&&t.x>1600&&t.y>1020));}
 function panel(o,now,session){const h=o&&o.hud,r=o&&o.ocr||[],has=(text,x0,x1,y0,y1)=>r.some(t=>t.text.trim().replace(/\s/g,'')===text.replace(/\s/g,'')&&t.x>=x0&&t.x<=x1&&t.y>=y0&&t.y<=y1);return !!(fresh(o,now,session)&&h&&!h.world&&!h.groundControls&&!h.health&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.bigMap&&has('Tutorials / All',100,200,20,60)&&has('Eye of the Storm',100,200,240,285)&&has('Eye of the Storm',1100,1250,630,690)&&r.some(t=>/693306810$/.test(t.text.trim())&&t.x>1600&&t.y>1020));}
 function recoveryPanel(o,now,session){
  if(panel(o,now,session))return true;
  const r=o&&o.ocr||[],h=o&&o.hud,has=(text,x0,x1,y0,y1)=>r.some(t=>t.text.trim().replace(/\s/g,'')===text.replace(/\s/g,'')&&t.x>=x0&&t.x<=x1&&t.y>=y0&&t.y<=y1);
  return !!(fresh(o,now,session)&&h&&!h.world&&!h.groundControls&&!h.health&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.bigMap&&has('Tutorials / All',100,200,20,60)&&has('Eye of the Storm',100,200,240,285)&&has('About Hydro',1100,1250,630,690)&&r.some(t=>/693306810$/.test(t.text.trim())&&t.x>1600&&t.y>1020));
 }
 async function recoverStudy(initial,api){
  if(!recoveryPanel(initial,api.now(),initial.session))throw Error('Fresh exact observed tutorial archive required');
  const result={status:'completed',windSealTutorialClosed:false,tutorialPages:[{frameId:initial.frameId,rows:initial.ocr}],actions:0};
  try{
   api.checkStop();await api.key('VK_ESCAPE',60,initial);result.actions++;await api.sleep(450);const o=await api.observe();
   result.windSealTutorialClosed=true;result.fieldFrameId=o.frameId;result.health=o.hud&&o.hud.health;return result;
  }finally{await api.release();}
 }

 async function study(initial,api){
  if(!ground(initial,api.now(),initial.session))throw Error('Fresh full-health Lv9 Eye of the Storm required');
  let o=initial;const result={status:'stopped',windSealStudy:true,tutorialOpened:false,actions:0};
  try{
   api.checkStop();await api.key('VK_G',60,o);result.actions++;await api.sleep(500);o=await api.observe();
   result.tutorialFrameId=o.frameId;result.tutorialRows=o.ocr;
   if(!panel(o,api.now(),initial.session))throw Error('Eye tutorial panel not recognized; no further tutorial input');
   result.tutorialOpened=true;api.checkStop();await api.key('VK_ESCAPE',60,o);result.actions++;await api.sleep(450);o=await api.observe();
   result.fieldFrameId=o.frameId;result.health=o.hud&&o.hud.health;result.reason='Eye tutorial captured and closed; inspect retained mechanics before combat';return result;
  }finally{await api.release();}
 }
 root.ActTwoWindSeal={fresh,eye,ground,panel,recoveryPanel,study,recoverStudy};if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoWindSeal;
})(typeof globalThis!=='undefined'?globalThis:this);
