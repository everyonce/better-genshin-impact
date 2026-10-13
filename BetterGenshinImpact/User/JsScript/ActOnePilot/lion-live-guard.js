var ActOneLionLiveGuard=(function(){
  var TITLE='Deep Within the Temple of the Lion';
  function entry(reports,session,o,handoff){
    if(!o||o.session!==session||!Number.isFinite(o.timestamp)||!Array.isArray(reports))return false;
    var receiptSession=session;
    if(handoff){
      if(handoff.session!==session||handoff.reviewed!==true||handoff.sourceSession===session||
        !Number.isFinite(handoff.createdAt)||handoff.createdAt>o.timestamp||o.timestamp-handoff.createdAt>86400000)return false;
      var stops=reports.filter(r=>r&&r.session===handoff.sourceSession&&r.id===handoff.sourceStopId&&r.status==='failed'&&
        r.timestamp<=handoff.createdAt&&r.details&&r.details.reason==='Pause protection exhausted: pause is UNVERIFIED; operator intervention required');
      if(stops.length!==1||reports.some(r=>r&&r.session===handoff.sourceSession&&r.timestamp>stops[0].timestamp))return false;
      receiptSession=handoff.sourceSession;
    }
    var found=reports.filter(r=>r&&r.session===receiptSession&&(!handoff||r.id===handoff.entryId)&&r.status==='completed'&&r.mission==='questStep'&&
      r.details&&r.details.result&&r.details.result.step==='lionPartyStart'&&r.details.result.label===TITLE);
    if(found.length!==1)return false;
    var r=found[0],es=r.details.inputEvents;
    if(!Number.isFinite(r.timestamp)||r.timestamp>o.timestamp||!Array.isArray(es))return false;
    var starts=es.filter(e=>e&&e.type==='lionPartyStart'&&e.label===TITLE);
    if(starts.length!==1||!Number.isFinite(starts[0].startedAt)||starts[0].startedAt>r.timestamp)return false;
    return !reports.some(other=>other&&(other.session===session||other.session===receiptSession)&&Array.isArray(other.details&&other.details.inputEvents)&&
      other.details.inputEvents.some(e=>e&&e.startedAt>r.timestamp&&e.startedAt<=o.timestamp&&
        /teleport|DomainStart|PartyStart|LeaveDomain|ReturnToEntrance/i.test(e.type)));
  }
  function field(o,now,session,minimum){
    var h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
    if(!o||o.session!==session||!Number.isInteger(o.frameId)||!Number.isFinite(o.timestamp)||!Number.isFinite(now)||
      now<o.timestamp||now-o.timestamp>1000||o.map!==null||!h||h.world!==false||h.groundControls!==true||h.climbing!==false||
      h.auto||h.journal||h.bigMap||h.dialogueReady||h.choice||h.tutorialStep||h.objectiveChanged||h.unknownHud||
      !hp||!Number.isFinite(hp.current)||!Number.isFinite(hp.max)||hp.max<=0||hp.current/hp.max<(minimum===0.01?0.01:0.6)||hp.current>hp.max)return false;
    function one(s,x0,x1,y0,y1){return rows.filter(r=>String(r.text||'').trim()===s&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1).length===1;}
    var starter=one('Lumina',1600,1810,280,340)&&one('Amber',1600,1810,380,440)&&
      one('Kaeya',1600,1810,460,540)&&one('3',1850,1895,460,540);
    var trial=[1196,1379,1186,1288].indexOf(hp.max)>=0&&one('Lumina',1600,1810,240,290)&&one('Amber',1600,1810,325,390)&&
      one('Kaeya',1600,1810,410,475)&&one('Lisa',1600,1810,525,580)&&
      one('Trial',1750,1895,495,540)&&(one('4',1850,1895,530,590)||
        one('1',1850,1895,240,295)&&one('2',1850,1895,325,395)&&one('3',1850,1895,410,480));
    return starter||trial;
  }
  function air(o,now,session){
    if(!o||!o.hud||o.hud.groundControls!==false)return false;
    var grounded=Object.assign({},o,{hud:Object.assign({},o.hud,{groundControls:true})});
    return field(grounded,now,session)&&(o.ocr||[]).filter(r=>String(r.text||'').trim()==='Space'&&r.x>=1600&&r.x<=1890&&r.y>=990&&r.y<=1060).length===1;
  }
  return {entry:entry,field:field,air:air,living:function(o,now,session){return field(o,now,session,0.01);}};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=ActOneLionLiveGuard;
