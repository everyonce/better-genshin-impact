function actOneObjectiveRows(rows, expected) {
    // Close crystal approach also requires the cropped height/distance reading.
    if (!expected || expected === 'Investigate what Paimon has found') return null;
    var candidates = rows.filter(function (r) { return r.x >= 65 && r.x < 695 && r.y >= 230 && r.y < 315; });
    function normalized(s) { return String(s).toLowerCase().replace(/\s+/g, ''); }
    return candidates.some(function (r) { return normalized(r.text) === normalized(expected); }) ? candidates : null;
}
function actOneEnemyBarSize(w,h) { return w>=2 && w<=300 && h>=3 && h<=12 && w/h>=0.15; }
function actOneEnemyBarAnchored(bar, rows, level) {
    if (!bar || !Array.isArray(rows)) return false;
    return rows.some(function (r) {
        // The enemy level is displayed above its health bar. Normalize common
        // OCR confusions, but require level 1 so the player's Lv.3 label cannot anchor it.
        var label=String(r.text||'').toUpperCase().replace(/\s+/g,'').replace(/[.|]/g,'');
        if (level===4 ? !/^LV4$/.test(label) : level===5 ? !/^LV5$/.test(label) : !/^LV[1IL]$/.test(label)) return false;
        var labelX=Number(r.x)+Number(r.width)/2, labelY=Number(r.y)+Number(r.height)/2;
        return Number.isFinite(labelX) && Number.isFinite(labelY) &&
            Math.abs(labelX-Number(bar.x))<=150 && Number(bar.y)-labelY>=8 && Number(bar.y)-labelY<=50;
    });
}
function actOneHealth(rows) {
    var match=rows.map(function(r){return r.text;}).join(' ').match(/\b(0|[1-9]\d{0,4})\s*\/\s*(0|[1-9]\d{0,4})\b/);
    if(!match) return null;
    var current=Number(match[1]),max=Number(match[2]);
    return max>0 && current<=max ? {current:current,max:max} : null;
}
function actOneFullHealthRows(rows, scaledRows) {
    var candidates=(rows||[]).filter(function(r){return r.x>=880&&r.x<=1050&&r.y>=990&&r.y<=1030&&/^\s*(?:0|[1-9]\d{0,4})\s*\/\s*(?:0|[1-9]\d{0,4})\s*$/.test(r.text)&&actOneHealth([r]);});
    if(candidates.length!==1) return null;
    var candidate=candidates[0],full=actOneHealth([candidate]);
    if(full.current/full.max>=0.6) return [candidate];
    if(arguments.length<2) return null;
    var scaled=actOneHealth(scaledRows||[]);
    return scaled&&scaled.current===full.current&&scaled.max===full.max ? [candidate] : [];
}
function actOneMergeControlCropRows(fullRows, cropRows, x, y) {
    var mapped=(cropRows||[]).map(function(r){return {text:String(r.text||''),x:x+Number(r.x)/3,y:y+Number(r.y)/3,width:Number(r.width)/3,height:Number(r.height)/3};});
    return (fullRows||[]).concat(mapped);
}
function actOneGroundControlEvidence(rows) {
    var controls=(rows||[]).filter(function(r){return /^(E|Q|Space)$/.test(String(r.text||'').trim())&&r.x>1500&&r.x<1880&&r.y>=990&&r.y<=1045;});
    return controls.some(function(r){return /^(E|Q)$/.test(String(r.text||'').trim());})&&
        !controls.some(function(r){return String(r.text||'').trim()==='Space';});
}
function actOneNeedsControlCrop(rows) {
    var bottom=(rows||[]).filter(function(r){return /^(X|Space|E|Q)$/.test(String(r.text||'').trim())&&r.x>1500&&r.x<1880&&r.y>=990&&r.y<=1045;});
    var climb=bottom.some(function(r){return String(r.text||'').trim()==='X';})&&bottom.some(function(r){return String(r.text||'').trim()==='Space';});
    return !climb&&!actOneGroundControlEvidence(rows);
}
function actOneDialogueReady(rows, choice) {
    var speakers=['Paimon','Amber','Jean','Lisa','Kaeya','Venti'];
    function isSpeaker(r) { return speakers.indexOf(String(r.text||'').trim())>=0; }
    var auto=(rows||[]).some(function(r){return /^Auto$/i.test(String(r.text||'').trim())&&r.x>=0&&r.x<350&&r.y>=0&&r.y<150;});
    var knownSpeaker=(rows||[]).some(function(r){return isSpeaker(r)&&r.x>=600&&r.x<=1200&&r.y>=820&&r.y<900;});
    var longSubtitle=(rows||[]).some(function(r){return r.x>200&&r.x<1550&&r.y>790&&r.y<990&&String(r.text||'').trim().length>8;});
    var shortSubtitle=knownSpeaker&&(rows||[]).some(function(r){
        var text=String(r.text||'').trim();
        return !isSpeaker(r)&&r.x>200&&r.x<1550&&r.y>=880&&r.y<990&&text.length>0&&text.length<=8;
    });
    return !!(auto&&(longSubtitle||shortSubtitle)&&!choice);
}
function actOneNavigateQuestState(rows) {
    rows=rows||[];
    function exact(text) { return rows.filter(function(r){return String(r.text||'').trim()===text;}); }
    var journal=exact('In Progress').filter(function(r){return r.x>=0&&r.x<350&&r.y>=0&&r.y<100;});
    var selected=exact('City of Freedom').filter(function(r){return r.x>=140&&r.x<500&&r.y>=240&&r.y<330;});
    var objective=exact('Go to the location designated by Amber').filter(function(r){return r.x>=850&&r.x<1500&&r.y>=230&&r.y<300;});
    var coachFull=exact('Click to navigate to quest objective').filter(function(r){return r.x>=1400&&r.x<1900&&r.y>=900&&r.y<1000;});
    var coachFirst=exact('Click to navigate to quest').filter(function(r){return r.x>=1400&&r.x<1900&&r.y>=900&&r.y<970;});
    var coachSecond=exact('objective').filter(function(r){return r.x>=1400&&r.x<1900&&r.y>=930&&r.y<1000;});
    var coach=coachFull.length===1 || (coachFull.length===0&&coachFirst.length===1&&coachSecond.length===1&&coachSecond[0].y>coachFirst[0].y);
    var navigateAll=exact('Navigate');
    var navigate=navigateAll.filter(function(r){return r.x>=1500&&r.x<1850&&r.y>=980&&r.y<1060;});
    return journal.length===1&&selected.length===1&&objective.length===1&&coach&&navigateAll.length===1&&navigate.length===1;
}
function actOneNavigateQuestButton(observation, now) {
    if(!observation||!observation.hud||!observation.hud.journal||observation.hud.tutorialStep!=='navigateQuest'||
       !Number.isFinite(observation.timestamp)||!Number.isFinite(now)||now<observation.timestamp||now-observation.timestamp>1000||
       !actOneNavigateQuestState(observation.ocr)) return null;
    var buttons=(observation.ocr||[]).filter(function(r){return String(r.text||'').trim()==='Navigate'&&r.x>=1500&&r.x<1850&&r.y>=980&&r.y<1060;});
    return buttons.length===1?buttons[0]:null;
}
function actOneTrackQuestState(rows) {
    rows=rows||[];
    function exact(text) { return rows.filter(function(r){return String(r.text||'').trim()===text;}); }
    var prompt=exact('Press Left Alt to show the cursor and').filter(function(r){return r.x>=700&&r.x<1300&&r.y>=130&&r.y<220;});
    var key=exact('Left Alt').filter(function(r){return r.x>=550&&r.x<800&&r.y>=170&&r.y<250;});
    var clickText=exact('click here to navigate to the quest').filter(function(r){return r.x>=700&&r.x<1300&&r.y>=180&&r.y<250;});
    var coachObjective=exact('objective').filter(function(r){return r.x>=850&&r.x<1200&&r.y>=210&&r.y<280;});
    var questAll=exact('Go to the location designated by Amber');
    var quest=questAll.filter(function(r){return r.x>=40&&r.x<650&&r.y>=210&&r.y<300;});
    return prompt.length===1&&key.length===1&&clickText.length===1&&coachObjective.length===1&&questAll.length===1&&quest.length===1&&
        clickText[0].y>=prompt[0].y&&coachObjective[0].y>clickText[0].y;
}
function actOneTrackQuestTarget(observation, now) {
    if(!observation||!observation.hud||observation.hud.tutorialStep!=='trackQuest'||
       !Number.isFinite(observation.timestamp)||!Number.isFinite(now)||now<observation.timestamp||now-observation.timestamp>1000||
       !actOneTrackQuestState(observation.ocr)) return null;
      var targets=(observation.ocr||[]).filter(function(r){return String(r.text||'').trim()==='Go to the location designated by Amber'&&r.x>=80&&r.x<650&&r.y>=230&&r.y<290&&r.width>=250&&r.height>=18;});
      if(targets.length!==1) return null;
      // The highlighted gold quest icon is the clickable tracking control. The
      // text row itself is not a reliable hit target (a live center click did
      // not advance the coachmark). Keep the derived point inside the observed
      // icon column and the 1920x1080 normalized game surface.
      var point={x:Math.round(targets[0].x-22),y:Math.round(targets[0].y+targets[0].height/2)};
      return point.x>=35&&point.x<=75&&point.y>=230&&point.y<=290&&point.x<1920&&point.y<1080?point:null;
}
function actOneGlideForwardState(rows,pos,hp,screen) {
    rows=rows||[];screen=screen||{};
    var cue=rows.filter(function(r){return String(r.text||'').trim()==='Press W to move forward'&&r.x>=760&&r.x<1200&&r.y>=170&&r.y<250;});
    var objective=rows.filter(function(r){return String(r.text||'').trim()==='Meet Amber at the fountain plaza'&&r.x>=40&&r.x<650&&r.y>=230&&r.y<340;});
    var ledge=pos&&pos.map==='Teyvat'&&Number.isFinite(pos.x)&&Number.isFinite(pos.y)&&Math.hypot(pos.x+779.988,pos.y-2298.464)<=8;
    var safeHp=hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max>0&&hp.current>=0&&hp.current<=hp.max&&hp.current/hp.max>=0.6;
    return !!(cue.length===1&&objective.length===1&&ledge&&safeHp&&screen.world===true&&
        !screen.auto&&!screen.journal&&!screen.bigMap&&!screen.dialogueReady&&!screen.choice&&!screen.objectiveChanged&&
        (!screen.tutorialStep||screen.tutorialStep==='glideForward'));
}
async function actOneGlideForward(observation,now,ops) {
    if(!observation||!Number.isFinite(observation.timestamp)||!Number.isFinite(now)||now<observation.timestamp||now-observation.timestamp>1000||
       !observation.hud||!actOneGlideForwardState(observation.ocr,observation.map,observation.hud.health,observation.hud))
        throw new Error('Fresh safe fountain-plaza glide cue required');
    ops.checkStop();await ops.forward(500);return 'glideForward';
}
function actOneGlideOpenState(rows,pos,hp,screen) {
    rows=rows||[];screen=screen||{};
    var cue=rows.filter(function(r){return String(r.text||'').trim()==='Press Space while in mid-air to glide'&&r.x>=760&&r.x<1200&&r.y>=170&&r.y<250;});
    var objective=rows.filter(function(r){return String(r.text||'').trim()==='Meet Amber at the fountain plaza'&&r.x>=40&&r.x<650&&r.y>=230&&r.y<340;});
    var ledge=pos&&pos.map==='Teyvat'&&Number.isFinite(pos.x)&&Number.isFinite(pos.y)&&Math.hypot(pos.x+779.988,pos.y-2298.464)<=10;
    var safeHp=hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max>0&&hp.current>=0&&hp.current<=hp.max&&hp.current/hp.max>=0.6;
    return !!(cue.length===1&&objective.length===1&&ledge&&safeHp&&screen.world===true&&
        !screen.auto&&!screen.journal&&!screen.bigMap&&!screen.dialogueReady&&!screen.choice&&!screen.objectiveChanged&&
        (!screen.tutorialStep||screen.tutorialStep==='glideOpen'));
}
function actOneAerialBossLabels(rows) {
    rows=rows||[];
    var boss=rows.filter(function(r){return String(r.text||'').trim()==='Stormterror'&&r.x>=800&&r.x<1100&&r.y>=0&&r.y<42;});
    var subtitle=rows.filter(function(r){return String(r.text||'').trim()==='Howling Hurricane of Mondstadt'&&r.x>=700&&r.x<1400&&r.y>=35&&r.y<78;});
    return boss.length===1&&subtitle.length===1;
}
function actOneAerialBossState(rows,map,hp,screen,barFraction) {
    screen=screen||{};
    var safeHp=hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max>0&&hp.current>=0&&hp.current<=hp.max&&hp.current/hp.max>=0.6&&!screen.lowHealth;
    return !!(actOneAerialBossLabels(rows)&&map===null&&safeHp&&Number.isFinite(barFraction)&&barFraction>0&&barFraction<=1&&
        !screen.journal&&!screen.bigMap&&!screen.dialogueReady&&!screen.choice&&!screen.objectiveChanged);
}
function actOneFalconWaypointTarget() { return {x:-1122.173,y:2197.455}; }
function actOneFalconWaypointReady(observation,now) {
    var h=observation&&observation.hud,hp=h&&h.health;
    return !!(observation&&Number.isFinite(observation.timestamp)&&Number.isFinite(now)&&now>=observation.timestamp&&now-observation.timestamp<=1000&&
        h&&h.world===true&&Array.isArray(h.objectives)&&h.objectives.indexOf('Meet Amber at the temple')>=0&&
        hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max>0&&hp.current>=0&&hp.current<=hp.max&&hp.current/hp.max>=0.6&&!h.lowHealth&&
        !h.journal&&!h.bigMap&&!h.dialogueReady&&!h.choice&&!h.climbing&&!h.tutorialStep&&!h.objectiveChanged);
}
function actOneFullMapState(rows) {
    rows=rows||[];
    var footer=rows.filter(function(r){return String(r.text||'').trim()==='Teyvat'&&r.x>1500&&r.y>930&&r.y<1020;});
    var resin=rows.filter(function(r){return /^200\s*\/\s*200$/.test(String(r.text||'').trim())&&r.x>1500&&r.y<100;});
    var places=['Mondstadt','Cider Lake','Whispering Woods','Starfell Lake'];
    var geo=places.filter(function(name){return rows.some(function(r){return String(r.text||'').trim()===name&&r.x>=800&&r.x<1600&&r.y>=40&&r.y<380;});});
    return footer.length===1&&resin.length===1&&geo.length>=2;
}
function actOneNavigationMapAnchor(request,lastAccepted) {
    if(request&&request.mission==='navigation'&&lastAccepted&&Number.isFinite(lastAccepted.x)&&Number.isFinite(lastAccepted.y))
        return {x:lastAccepted.x,y:lastAccepted.y,maxDistance:25,source:'lastAccepted'};
    var first=request&&request.mission==='navigation'&&request.waypoints&&request.waypoints[0];
    if(!first||first.map!=='Teyvat'||!Number.isFinite(first.x)||!Number.isFinite(first.y)) return null;
    return {x:first.x,y:first.y,maxDistance:150,source:'firstWaypoint'};
}
function actOneAcceptNavigationPosition(request,lastAccepted,candidate) {
    var anchor=actOneNavigationMapAnchor(request,lastAccepted);
    if(!anchor||!candidate||!Number.isFinite(Number(candidate.x))||!Number.isFinite(Number(candidate.y))) return null;
    var x=Number(candidate.x),y=Number(candidate.y);
    return Math.hypot(x-anchor.x,y-anchor.y)<=anchor.maxDistance?{x:x,y:y,map:'Teyvat'}:null;
}
function actOneNamedInteractionVisible(rows,objective) {
    rows=rows||[];
    function inZone(r) { return Number(r.x)>=1150&&Number(r.x)<=1550&&Number(r.y)>=300&&Number(r.y)<=800; }
    var speaker=String(objective||'').replace(/^Talk to /,'');
    var namedSpeaker=['Amber','Kaeya','Lisa'].indexOf(speaker)>=0&&rows.some(function(r){return String(r.text||'').trim()===speaker&&inZone(r);});
    var templeFull=rows.some(function(r){return ['Temple of the Falcon','Temple of the Wolf','Temple of the Lion'].indexOf(String(r.text||'').trim())>=0&&inZone(r);});
    if(['Talk to Amber','Talk to Kaeya','Talk to Lisa'].indexOf(objective)>=0) return namedSpeaker;
    if(objective==='Enter the temple') { if(templeFull) return true; }
    else return false;
    var heads=rows.filter(function(r){return String(r.text||'').trim()==='Temple of the'&&inZone(r);});
    var tails=rows.filter(function(r){return ['Falcon','Wolf','Lion'].indexOf(String(r.text||'').trim())>=0&&inZone(r);});
    var pairs=[];
    heads.forEach(function(a){tails.forEach(function(b){var gap=Number(b.y)-(Number(a.y)+Number(a.height));
        if(Math.abs(Number(a.x)-Number(b.x))<=30&&gap>=-15&&gap<=20)pairs.push([a,b]);});});
    return pairs.length===1;
}
function actOneResolveInteractionObjective(requestObjective,objectiveRows) {
    if(['Talk to Amber','Talk to Kaeya','Talk to Lisa','Enter the temple'].indexOf(requestObjective)>=0) return requestObjective;
    var matches=(objectiveRows||[]).filter(function(r){return ['Talk to Amber','Talk to Kaeya','Talk to Lisa','Enter the temple'].indexOf(String(r.text||'').trim())>=0;});
    return matches.length===1?String(matches[0].text||'').trim():null;
}
function actOneShouldReadInteractionCrop(rows,objective,screen) {
    screen=screen||{};
    var hp=screen.health,target=actOneNamedInteractionVisible(rows,objective);
    var safeHp=hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max>0&&hp.current>=0&&hp.current<=hp.max&&hp.current/hp.max>=0.6;
    var existingF=(rows||[]).some(function(r){return String(r.text||'').trim()==='F'&&Number(r.x)>=1080&&Number(r.x)<=1170&&Number(r.y)>=490&&Number(r.y)<=590;});
    return !!((['Talk to Amber','Talk to Kaeya','Talk to Lisa','Enter the temple'].indexOf(objective)>=0)&&screen.objective===objective&&target&&screen.world===true&&screen.position===true&&safeHp&&
        !screen.auto&&!screen.journal&&!screen.bigMap&&!screen.dialogueReady&&!screen.choice&&!screen.climbing&&!screen.objectiveChanged&&!screen.tutorialStep&&!existingF);
}
function actOneInteractionCropF(cropRows,x,y) {
    var mapped=actOneMergeControlCropRows([],cropRows,x,y);
    var matches=mapped.filter(function(r){return String(r.text||'').trim()==='F'&&r.x>=1080&&r.x<=1170&&r.y>=490&&r.y<=590;});
    return matches.length===1?matches[0]:null;
}
function actOneFalconStartTarget(observation,now) {
    return actOneTempleStartTarget(observation,now,'Falcon');
}
function actOneTempleStartTarget(observation,now,temple) {
    var spec={Falcon:{title:'Deep Within the Temple of the Falcon',level:4},Wolf:{title:'Deep Within the Temple of the Wolf',level:5}}[temple];
    if(!spec)return null;
    var h=observation&&observation.hud,rows=observation&&observation.ocr||[];
    if(!observation||!Number.isFinite(observation.timestamp)||!Number.isFinite(now)||now<observation.timestamp||now-observation.timestamp>1000||
       !h||h.world!==false||observation.map!==null||h.journal||h.bigMap||h.dialogueReady||h.choice||h.tutorialStep) return null;
    function exact(text) { return rows.filter(function(r){return String(r.text||'').trim()===text;}); }
    var header=exact('Domain Entrance').filter(function(r){return r.x>=70&&r.x<250&&r.y>=0&&r.y<70;});
    var left=exact(spec.title).filter(function(r){return r.x>=0&&r.x<550&&r.y>=120&&r.y<205;});
    var selected=exact(spec.title).filter(function(r){return r.x>=900&&r.x<1850&&r.y>=110&&r.y<205;});
    var level=exact('Recommended Party Level: '+spec.level).filter(function(r){return r.x>=0&&r.x<500&&r.y>=180&&r.y<245;});
    var starts=exact('Start').filter(function(r){return r.x>=1550&&r.x<1900&&r.y>=950&&r.y<1070;});
    var allStarts=exact('Start');
    var wrong=rows.some(function(r){return String(r.text||'').trim()==='Windy Cliff'&&r.x>=900&&r.x<1850&&r.y>=100&&r.y<215;});
    if(header.length!==1||left.length!==1||selected.length!==1||level.length!==1||starts.length!==1||allStarts.length!==1||wrong) return null;
    var row=starts[0],x=Math.round(Number(row.x)+Number(row.width)/2),y=Math.round(Number(row.y)+Number(row.height)/2);
    return Number.isFinite(x)&&Number.isFinite(y)&&x>=1550&&x<1900&&y>=950&&y<1070?{x:x,y:y,label:spec.title}:null;
}
function actOneFalconPartyTarget(o,now) {
    if(!o||!o.hud||o.hud.world!==false||o.map!==null||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||o.hud.journal||o.hud.bigMap||o.hud.dialogueReady||o.hud.choice) return null;
    var rows=o.ocr||[];
    function one(label,x0,x1,y0,y1){var a=rows.filter(function(r){return r.text.trim()===label&&r.x>=x0&&r.x<x1&&r.y>=y0&&r.y<y1;});return a.length===1?a[0]:null;}
    if(!one('Party Setup',50,400,0,100)||!one('Lumina',300,600,250,390)||!one('Amber',650,900,280,420)||!one('Team Standing By',50,500,950,1080)) return null;
    var row=one('Start',1550,1850,950,1070);
    if(!row||rows.filter(function(r){return r.text.trim()==='Start';}).length!==1) return null;
    var x=Math.round(row.x+row.width/2),y=Math.round(row.y+row.height/2);
    return Number.isFinite(x)&&Number.isFinite(y)?{x:x,y:y}:null;
}
function actOneWolfPartyTarget(o,now,reports,session) {
    var target=actOneFalconPartyTarget(o,now);
    if(!target||!Number.isFinite(now)||!o||o.session!==session||!Array.isArray(reports)||typeof session!=='string'||!session) return null;
    function step(r) { return r&&r.details&&r.details.result&&r.details.result.step; }
    var entries=reports.filter(function(r){return r&&r.session===session&&r.mission==='questStep'&&r.status==='completed'&&step(r)==='wolfStart'&&r.details&&r.details.result.label==='Deep Within the Temple of the Wolf';});
    if(entries.length!==1) return null;
    var entry=entries[0],events=entry.details.inputEvents;
    if(!Number.isFinite(entry.timestamp)||entry.timestamp>o.timestamp||!Array.isArray(events)) return null;
    var proof=events.filter(function(e){return e&&e.type==='wolfDomainStart'&&e.label==='Deep Within the Temple of the Wolf'&&Number.isFinite(e.startedAt)&&e.startedAt<=entry.timestamp;});
    if(proof.length!==1) return null;
    var startAt=proof[0].startedAt,proofIndex=events.indexOf(proof[0]);
    function stateInput(e) { return !e||typeof e!=='object'||e.type!=='controllerRevision'; }
    for(var i=proofIndex+1;i<events.length;i++) if(stateInput(events[i])) return null;
    for(var r=0;r<reports.length;r++) {
        var row=reports[r];
        if(!row||row.session!==session||row.status==='started'||row.status==='running') continue;
        if(Number.isFinite(row.timestamp)&&row.timestamp>=entry.timestamp&&!Array.isArray(row.details&&row.details.inputEvents)) return null;
        if(!Array.isArray(row.details&&row.details.inputEvents)) continue;
        for(var j=0;j<row.details.inputEvents.length;j++) {
            var e=row.details.inputEvents[j];
            if(row===entry&&e===proof[0]) continue;
            if(stateInput(e)&&(!Number.isFinite(e.startedAt)||e.startedAt>startAt)) return null;
        }
    }
    return target;
}
function actOneWolfEntryHud(o,now) {
    var h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
    return !!(o&&Number.isFinite(now)&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&o.map===null&&h&&h.world===false&&h.groundControls&&!h.climbing&&!h.journal&&!h.bigMap&&!h.dialogueReady&&!h.choice&&!h.tutorialStep&&
      hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max>0&&hp.current<=hp.max&&hp.current/hp.max>=0.6&&
      rows.some(function(r){return r.text.trim()==='Lumina'&&r.x>1550&&r.y>300&&r.y<600;})&&
      rows.some(function(r){return r.text.trim()==='Amber'&&r.x>1550&&r.y>300&&r.y<600;})&&
      !rows.some(function(r){return r.text.trim()==='Trial'||r.text.trim()==='Kaeya'&&r.x>1550&&r.y>300&&r.y<600;}));
}
function actOneWolfDomainHud(o,now,minRatio) {
    if(minRatio===undefined)minRatio=0.6;
    var h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
    return !!(o&&Number.isFinite(now)&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&o.map===null&&h&&h.world===false&&h.groundControls&&!h.climbing&&!h.journal&&!h.bigMap&&!h.dialogueReady&&!h.choice&&!h.tutorialStep&&
      hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max>0&&hp.current<=hp.max&&hp.current/hp.max>=minRatio&&
      rows.some(function(r){return r.text.trim()==='Kaeya'&&r.x>1550&&r.y>300&&r.y<600;})&&
      rows.some(function(r){return r.text.trim()==='Trial'&&r.x>1700&&r.y>300&&r.y<600;}));
}
function actOneFalconPyroInfo(rows) {
    if(rows.some(function(r){return r.x>580&&r.x<700&&r.y>750&&r.y<840&&r.text.trim()==='Use Pyro Skills to ignite combustible objects.';})) return true;
    return rows.some(function(r){return r.x>350&&r.x<550&&r.y>750&&r.y<820&&/^Amber has the ability to aim and shoot\. While aiming, her arrows will$/.test(r.text.trim());})&&
      rows.some(function(r){return r.x>350&&r.x<550&&r.y>810&&r.y<870&&/^accumulate charge\. Once fully charged, the arrow will be imbued with Pyro\.?$/.test(r.text.trim());});
}
function actOneFalconInfo(rows) {
    if(actOneFalconPyroInfo(rows)) return true;
    if(rows.some(function(r){return r.x>380&&r.x<500&&r.y>760&&r.y<820&&r.text.trim()==="Opponents' wooden shields are attributed to Dendro, which can be ignited";})&&rows.some(function(r){return r.x>580&&r.x<710&&r.y>810&&r.y<870&&r.text.trim()==='with Pyro Skills, rendering them defenseless.';})) return true;
    if(rows.some(function(r){return r.x>500&&r.x<650&&r.y>760&&r.y<840&&r.text.trim()==='Green symbolizes Dendro, which can be ignited by Pyro.';})) return true;
    return rows.some(function(r){return r.x>350&&r.x<470&&r.y>760&&r.y<820&&r.text.trim()==='Use Elemental Sight to see the elemental attributes of different objects. Each';})&&
      rows.some(function(r){return r.x>720&&r.x<820&&r.y>810&&r.y<870&&r.text.trim()==='element has its own color.';});
}
function actOneFalconAimHud(o,now,minRatio) {
    if(!o||!o.hud||o.hud.groundControls||!o.ocr.some(function(r){return r.text.trim()==='R'&&r.x>1680&&r.x<1770&&r.y>1010&&r.y<1055;})) return false;
    var copy=Object.assign({},o,{hud:Object.assign({},o.hud,{groundControls:true})});
    return actOneFalconDomainHud(copy,now,minRatio);
}
function actOneFalconDomainHud(o,now,minRatio) {
    if(minRatio===undefined) minRatio=0.6;
    var h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
    return !!(o&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&o.map===null&&h&&h.world===false&&h.groundControls&&!h.climbing&&!h.journal&&!h.bigMap&&!h.dialogueReady&&!h.choice&&!h.tutorialStep&&!h.objectiveChanged&&
      hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max>0&&hp.current<=hp.max&&hp.current/hp.max>=minRatio&&
      rows.some(function(r){return /^[A\u00c1]mber$/.test(r.text.trim())&&r.x>1550&&r.y>300&&r.y<600;})&&
      (rows.some(function(r){return r.text.trim()==='Trial'&&r.x>1700&&r.y>300&&r.y<600;})||
       rows.some(function(r){return /^Leaving in \d+ second\(s\)$/.test(r.text.trim())&&r.x>650&&r.x<1000&&r.y>920&&r.y<990;})));
}
function actOneFalconContinueTarget(o,now) {
    var h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
    if(!o||!Number.isFinite(o.timestamp)||!Number.isFinite(now)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!h||h.world!==false||
       h.journal||h.bigMap||h.dialogueReady||h.choice||h.climbing) return null;
    var targets=rows.filter(function(r){return r.text.trim()==='Continue Challenge'&&r.x>750&&r.x<1000&&r.y>380&&r.y<460;});
    var leaves=rows.filter(function(r){return r.text.trim()==='Leave Domain?'&&r.y>620&&r.y<700;});
    return targets.length===1&&leaves.length===1?targets[0]:null;
}
function actOneValidateFalconResume(evidence,priorReports,currentReports,currentSession,rdpSession,observation,now) {
    var fields=['fromSession','toSession','priorEntryId','priorPauseId','verifiedAt','rdpSessionId'];
    if(!evidence||Object.keys(evidence).length!==fields.length||Object.keys(evidence).some(function(k){return fields.indexOf(k)<0;})||
       !/^[A-Za-z0-9_-]{1,80}$/.test(evidence.fromSession||'')||!/^[A-Za-z0-9_-]{1,80}$/.test(evidence.toSession||'')||
       evidence.fromSession===evidence.toSession||evidence.toSession!==currentSession||rdpSession!==5||evidence.rdpSessionId!==5||
       typeof evidence.priorEntryId!=='string'||typeof evidence.priorPauseId!=='string'||evidence.priorEntryId===evidence.priorPauseId||
       !Number.isFinite(evidence.verifiedAt)||evidence.verifiedAt>now||now-evidence.verifiedAt>300000||
       !Array.isArray(priorReports)||!Array.isArray(currentReports)||!actOneFalconContinueTarget(observation,now)) return null;
    function entryFor(id) { var found=priorReports.filter(function(r){return r&&r.id===id&&r.session===evidence.fromSession&&r.status!=='started'&&r.status!=='running';});return found.length===1?found[0]:null; }
    var entry=entryFor(evidence.priorEntryId),pause=entryFor(evidence.priorPauseId);
    function step(r) { return r&&r.details&&r.details.result&&r.details.result.step; }
    function hasKey(r,key) { return !!(r.details&&Array.isArray(r.details.inputEvents)&&r.details.inputEvents.some(function(e){return e&&e.type==='key'&&e.key===key;})); }
    var entryOk=entry&&entry.mission==='questStep'&&entry.status==='completed'&&step(entry)==='falconPartyStart'&&
        Number.isFinite(entry.timestamp)&&entry.timestamp<=evidence.verifiedAt&&evidence.verifiedAt-entry.timestamp<=7200000&&
        entry.details&&Array.isArray(entry.details.inputEvents)&&entry.details.inputEvents.some(function(e){return e&&e.type==='falconPartyStart';});
    var pauseOk=entryOk&&pause&&pause.mission==='questStep'&&Number.isFinite(pause.timestamp)&&pause.timestamp>=entry.timestamp&&
        pause.timestamp<=evidence.verifiedAt&&evidence.verifiedAt-pause.timestamp<=7200000&&hasKey(pause,'VK_ESCAPE')&&
        ((pause.status==='completed'&&step(pause)==='falconPause')||(pause.status==='stopped'&&step(pause)==='falconCombat'&&pause.details.result.paused===true));
    var alreadyUsed=currentReports.some(function(r){return r&&r.session===currentSession&&r.mission==='questStep'&&r.status==='completed'&&step(r)==='falconResume';});
    if(!entryOk||!pauseOk||alreadyUsed) return null;
    return {fromSession:evidence.fromSession,toSession:evidence.toSession,priorEntryId:entry.id,priorPauseId:pause.id,verifiedAt:evidence.verifiedAt};
}
async function actOneGlideOpen(observation,now,ops) {
    if(!observation||!Number.isFinite(observation.timestamp)||!Number.isFinite(now)||now<observation.timestamp||now-observation.timestamp>1000||
        !observation.hud||!actOneGlideOpenState(observation.ocr,observation.map,observation.hud.health,observation.hud))
        throw new Error('Fresh safe glide-open cue required');
    ops.checkStop();await ops.pressSpace(60);return 'glideOpen';
}
async function actOneAltClick(target, ops) {
    if(!target||!ops) throw new Error('OCR-derived quest target required');
    ops.checkStop();
    try {
        ops.keyDown('VK_LMENU'); ops.checkStop();
          var deadline=ops.now()+200;
        while(ops.now()<deadline){await ops.sleep(Math.min(20,deadline-ops.now()));ops.checkStop();}
        ops.click(target.x,target.y);
        deadline=ops.now()+60;
        while(ops.now()<deadline){await ops.sleep(Math.min(20,deadline-ops.now()));ops.checkStop();}
    } finally { ops.release(); }
}
if (typeof module !== 'undefined' && module.exports) module.exports = { objectiveRows: actOneObjectiveRows, enemyBarSize:actOneEnemyBarSize, enemyBarAnchored:actOneEnemyBarAnchored, health:actOneHealth, fullHealthRows:actOneFullHealthRows, dialogueReady:actOneDialogueReady, navigateQuestState:actOneNavigateQuestState, navigateQuestButton:actOneNavigateQuestButton, trackQuestState:actOneTrackQuestState, trackQuestTarget:actOneTrackQuestTarget, altClick:actOneAltClick, mergeControlCropRows:actOneMergeControlCropRows, groundControlEvidence:actOneGroundControlEvidence, needsControlCrop:actOneNeedsControlCrop, glideForwardState:actOneGlideForwardState, glideForward:actOneGlideForward, glideOpenState:actOneGlideOpenState, glideOpen:actOneGlideOpen, aerialBossLabels:actOneAerialBossLabels, aerialBossState:actOneAerialBossState, falconWaypointTarget:actOneFalconWaypointTarget, falconWaypointReady:actOneFalconWaypointReady, fullMapState:actOneFullMapState, navigationMapAnchor:actOneNavigationMapAnchor, acceptNavigationPosition:actOneAcceptNavigationPosition, namedInteractionVisible:actOneNamedInteractionVisible, resolveInteractionObjective:actOneResolveInteractionObjective, shouldReadInteractionCrop:actOneShouldReadInteractionCrop, interactionCropF:actOneInteractionCropF, falconStartTarget:actOneFalconStartTarget, falconPartyTarget:actOneFalconPartyTarget, wolfPartyTarget:actOneWolfPartyTarget, wolfEntryHud:actOneWolfEntryHud, wolfDomainHud:actOneWolfDomainHud, falconDomainHud:actOneFalconDomainHud, falconAimHud:actOneFalconAimHud, falconPyroInfo:actOneFalconPyroInfo, falconContinueTarget:actOneFalconContinueTarget, validateFalconResume:actOneValidateFalconResume };

var STARTER_TRIAL_STRATEGY = 'English Starter Trials';
var DEFAULT_TIMEOUT_MS = 15_000;
var DEFAULT_POLL_MS = 50;

class NativeFightTimeoutError extends Error {
  constructor(timeoutMs) {
    super(`Native AutoFight cooperative timeout after ${timeoutMs} ms`);
    this.name = 'NativeFightTimeoutError';
    this.timeoutMs = timeoutMs;
  }
}

/**
 * Run the starter TXT strategy under linked cancellation and a local stop guard.
 * Cancellation is cooperative: this waits for native AutoFight to unwind before
 * returning or throwing, so an unresponsive native task can outlive the deadline.
 */
async function runStarterTrialAutoFight(native, checkStop, {
  timeoutMs = DEFAULT_TIMEOUT_MS,
  pollMs = DEFAULT_POLL_MS,
  now = Date.now,
  sleep = ms => new Promise(resolve => setTimeout(resolve, ms)),
} = {}) {
  if (!native || typeof native.createLinkedCancellationTokenSource !== 'function'
      || typeof native.createAutoFightParam !== 'function'
      || typeof native.runAutoFightTask !== 'function') {
    throw new TypeError('Native AutoFight adapter is incomplete');
  }
  if (typeof checkStop !== 'function') throw new TypeError('checkStop must be a function');
  if (!(timeoutMs > 0) || !(pollMs > 0)) throw new RangeError('timeoutMs and pollMs must be positive');

  // Fail closed before constructing task state or starting any native work.
  checkStop();
  const cts = native.createLinkedCancellationTokenSource();
  let fightPromise;
  let monitorPromise;
  let monitorStopped = false;
  let cancellationRequested = false;
  const cancel = () => {
    if (!cancellationRequested) {
      cancellationRequested = true;
      cts.Cancel();
    }
  };

  try {
    const param = native.createAutoFightParam(STARTER_TRIAL_STRATEGY);
    param.Timeout = 15;
    param.PickDropsAfterFightEnabled = false;
    const startedAt = now();

    fightPromise = Promise.resolve().then(() => native.runAutoFightTask(param, cts.Token));
    monitorPromise = (async () => {
      while (!monitorStopped) {
        await sleep(pollMs);
        if (monitorStopped) return;
        checkStop();
        if (now() - startedAt >= timeoutMs) throw new NativeFightTimeoutError(timeoutMs);
      }
    })();

    return await Promise.race([fightPromise, monitorPromise]);
  } catch (error) {
    try { cancel(); } catch { /* Preserve the original stop, timeout, or native error. */ }
    throw error;
  } finally {
    monitorStopped = true;
    try { cancel(); } catch { /* Continue through native unwind and disposal. */ }
    try {
      if (fightPromise) await fightPromise.catch(() => {});
    } finally {
      try {
        if (monitorPromise) await monitorPromise.catch(() => {});
      } finally {
        cts.Dispose();
      }
    }
  }
}


if (typeof module !== 'undefined' && module.exports) Object.assign(module.exports,{templeStartTarget:actOneTempleStartTarget,DEFAULT_POLL_MS:DEFAULT_POLL_MS,DEFAULT_TIMEOUT_MS:DEFAULT_TIMEOUT_MS,NativeFightTimeoutError:NativeFightTimeoutError,STARTER_TRIAL_STRATEGY:STARTER_TRIAL_STRATEGY,runStarterTrialAutoFight:runStarterTrialAutoFight});

function createActOneAdapter(sessionId) {
    var expectedSession = Number(sessionId), held = null, request = null, events = [], lastObservation = null, navLastAcceptedPosition = null, heartbeat = null, focusRecoveryAttempted = false;
    function dispose(v) { if (v && typeof v.dispose === 'function') v.dispose(); }
    function sessionReady() {
        if (genshin.isRemoteDesktopSession !== true || Number(genshin.windowsSessionId) !== expectedSession || expectedSession !== 5) throw new Error('RDP session 5 required');
    }
    function ready() { sessionReady(); if (genshin.isGameForeground !== true) throw new Error('Game lost foreground focus'); }
    function release() { if (held) { var k = held; held = null; keyUp(k); } }
    function checkStop() {
        if(heartbeat)heartbeat(false);
        ready();
        if (request && file.isExists('stop.json')) {
            var stop = JSON.parse(file.readTextSync('stop.json'));
            if (stop.session === request.session && stop.createdAt >= request.createdAt) { release(); throw new Error('Stop requested'); }
        }
    }
    async function boundedKey(key, ms) {
        checkStop(); held = key;
        var event = { type: 'key', key: key, durationMs: ms, startedAt: Date.now() }; events.push(event);
        try {
            keyDown(key);
            var deadline = Date.now() + ms;
            while (Date.now() < deadline) { await sleep(Math.min(50, deadline - Date.now())); checkStop(); }
        } finally { release(); event.finishedAt = Date.now(); }
    }
    function readRows(img, x, y, w, h) {
        var found = img.findMulti(RecognitionObject.Ocr(x, y, w, h)), rows = [];
        try {
            for (var i = 0; i < found.count; i++) {
                var r = found[i]; rows.push({ text: String(r.text), x: Number(r.x), y: Number(r.y), width: Number(r.width), height: Number(r.height) });
            }
        } finally { for (var j = 0; j < found.count; j++) dispose(found[j]); dispose(found); }
        return rows;
    }
    function scaledRows(img, x, y, w, h) {
        var crop = img.deriveCrop(x, y, w, h), scaled = null;
        try {
            var mat = crop.srcMat.resize(new OpenCvSharp.OpenCvSharp.Size(w * 3, h * 3));
            scaled = new ImageRegion(mat, 0, 0);
            return readRows(scaled, 0, 0, w * 3, h * 3);
        } finally { dispose(scaled); dispose(crop); }
    }
    function readHealth(img, fullRows) {
        var fullResult=actOneFullHealthRows(fullRows);
        if(fullResult!==null) return fullResult;
        var result = scaledRows(img, 900, 990, 125, 40);
        fullResult=actOneFullHealthRows(fullRows,result);
        if(fullResult!==null) return fullResult;
        if (actOneHealth(result)) return result;
        // Read both numeric halves independently when OCR mistakes the slash for 1.
        var left = scaledRows(img, 893, 998, 65, 25).filter(function (r) { return /^\d{1,5}$/.test(r.text.trim()); });
        var right = scaledRows(img, 967, 998, 65, 25).filter(function (r) { return /^\d{1,5}$/.test(r.text.trim()); });
        if (left.length === 1 && right.length === 1) return [{ text: left[0].text.trim() + '/' + right[0].text.trim() }];
        return result;
    }
    function readMarker(img) {
        var templates = ['assets/quest-marker.png', 'assets/quest-marker-near.png'], matches = [];
        for (var t = 0; t < templates.length; t++) {
            var mat = file.readImageMatSync(templates[t]), ro = null, found = null;
            try {
                ro = RecognitionObject.TemplateMatch(mat, 320, 150, 1400, 630); ro.threshold = 0.82; ro.use3Channels = true;
                found = img.findMulti(ro);
                for (var j = 0; j < found.count; j++) {
                    var point = { x: Number(found[j].x) + Number(found[j].width) / 2, y: Number(found[j].y) + Number(found[j].height) / 2 };
                    if (!matches.some(function (m) { return Math.hypot(m.x-point.x,m.y-point.y) < 30; })) matches.push(point);
                }
            } finally {
                if (found) { for (var i = 0; i < found.count; i++) dispose(found[i]); dispose(found); }
                if (ro) dispose(ro.templateImageGreyMat); dispose(mat);
            }
        }
        return matches.length === 1 ? matches[0] : null;
    }
    function readSlime(img) {
        var crop=img.deriveCrop(400,250,1150,600),hsv=null,mask=null;
        try {
            hsv=crop.srcMat.cvtColor(OpenCvSharp.OpenCvSharp.ColorConversionCodes.BGR2HSV,0);
            mask=hsv.inRange(new OpenCvSharp.OpenCvSharp.Scalar(65,35,140),new OpenCvSharp.OpenCvSharp.Scalar(100,160,255));
            var contours=mask.findContoursAsArray(OpenCvSharp.OpenCvSharp.RetrievalModes.External,OpenCvSharp.OpenCvSharp.ContourApproximationModes.ApproxSimple),matches=[];
            for(var i=0;i<contours.length;i++) {
                var box=OpenCvSharp.OpenCvSharp.Cv2.boundingRect(contours[i]),area=Number(OpenCvSharp.OpenCvSharp.Cv2.contourArea(contours[i],false));
                var w=Number(box.width),h=Number(box.height);
                if(w>=40&&w<=160&&h>=35&&h<=140&&area>1500&&area/(w*h)>0.5) matches.push({x:400+Number(box.x)+w/2,y:250+Number(box.y)+h/2,width:w,height:h,area:area});
            }
            return matches.length===1?matches[0]:null;
        } finally {dispose(mask);dispose(hsv);dispose(crop);}
    }
    function readEnemyBars(img, rows, level) {
        var crop=img.deriveCrop(350,100,1250,800),mask=null;
        try {
            mask=crop.srcMat.inRange(new OpenCvSharp.OpenCvSharp.Scalar(75,75,230),new OpenCvSharp.OpenCvSharp.Scalar(110,110,255));
            var contours=mask.findContoursAsArray(OpenCvSharp.OpenCvSharp.RetrievalModes.External,OpenCvSharp.OpenCvSharp.ContourApproximationModes.ApproxSimple),candidates=[],bars=[];
            for(var i=0;i<contours.length;i++) {
                var b=OpenCvSharp.OpenCvSharp.Cv2.boundingRect(contours[i]),w=Number(b.width),h=Number(b.height);
                // A nearly defeated enemy has a very short red segment. Requiring
                // a wide bar made the controller lose the target before the final hit.
                var bar={x:350+Number(b.x)+w/2,y:100+Number(b.y)+h/2,width:w,height:h};
                if(actOneEnemyBarSize(w,h)||((level===4||level===5)&&w>=2&&w<=300&&h>12&&h<=20)) candidates.push(bar);
            }
            candidates.sort(function(a,b){return b.height-a.height;});
            // Full-frame OCR is cheap. If it misses the small green enemy label,
            // inspect at most four local crops around the most bar-like candidates.
            for(var c=0;c<candidates.length;c++) if(actOneEnemyBarAnchored(candidates[c],rows,level)) bars.push(candidates[c]);
            var fallbackCount=0;
            for(var f=0;bars.length===0 && f<candidates.length && fallbackCount<4;f++) {
                var candidate=candidates[f];
                if(bars.some(function(v){return Math.hypot(v.x-candidate.x,v.y-candidate.y)<2;})) continue;
                fallbackCount++;
                var cx=Math.max(0,Math.min(1920-240,Math.round(candidate.x-70)));
                var cy=Math.max(0,Math.min(1080-45,Math.round(candidate.y-50)));
                var local=scaledRows(img,cx,cy,240,45).map(function(r){return {text:r.text,x:cx+Number(r.x)/3,y:cy+Number(r.y)/3,width:Number(r.width)/3,height:Number(r.height)/3};});
                if(actOneEnemyBarAnchored(candidate,local,level)) bars.push(candidate);
            }
            return bars;
        } finally {dispose(mask);dispose(crop);}
    }
    function readAerialBossBar(img) {
        var crop=img.deriveCrop(718,80,482,16),mask=null;
        try {
            mask=crop.srcMat.inRange(new OpenCvSharp.OpenCvSharp.Scalar(75,75,230),new OpenCvSharp.OpenCvSharp.Scalar(110,110,255));
            var contours=mask.findContoursAsArray(OpenCvSharp.OpenCvSharp.RetrievalModes.External,OpenCvSharp.OpenCvSharp.ContourApproximationModes.ApproxSimple);
            var widest=0;
            for(var i=0;i<contours.length;i++) {
                var b=OpenCvSharp.OpenCvSharp.Cv2.boundingRect(contours[i]),w=Number(b.width),h=Number(b.height);
                if(w>=4&&w<=480&&h>=2&&h<=16&&w/h>=5&&w>widest) widest=w;
            }
            return widest>0?Math.max(0,Math.min(1,widest/478)):null;
        } finally {dispose(mask);dispose(crop);}
    }
    function requireCombat() {
        checkStop();
        if(!request || ['Defeat the nearby hilichurls','Clear out the nearby hilichurl camp'].indexOf(request.objective)<0 || !lastObservation || Date.now()-lastObservation.timestamp > 1000 || !lastObservation.hud.world || lastObservation.hud.lowHealth || lastObservation.hud.objectives.indexOf(request.objective) < 0) throw new Error('Fresh recognized combat objective required');
    }
    function requireAerial() {
        checkStop();
        var o=lastObservation,h=o&&o.hud,hp=h&&h.health;
        if(!request||request.objective!=='Stormterror aerial encounter'||!o||Date.now()-o.timestamp>1000||
            h.aerialBossVisible!==true||!h.aerialBoss||h.journal||h.bigMap||h.dialogueReady||h.choice||h.objectiveChanged||h.lowHealth||
            !hp||!Number.isFinite(hp.current)||!Number.isFinite(hp.max)||hp.max<=0||hp.current<0||hp.current/hp.max<0.6||o.map!==null)
            throw new Error('Fresh recognized Stormterror aerial screen required');
    }
    return {
        setHeartbeat: function (callback) {heartbeat=callback;},
        heartbeat: function (_,force) {if(heartbeat)heartbeat(force===true);},
        now: function () { return Date.now(); }, sleep: function (ms) { return sleep(ms); }, checkStop: checkStop,
        beginMission: function (value) {
            request = value; events = []; navLastAcceptedPosition = null; focusRecoveryAttempted = false;
            var revision = {}, names = ['main.js','engine.js','bgi.js','mission.js','combat.js','recovery.js'];
            for(var i=0;i<names.length;i++) {
                var source=file.readTextSync(names[i]), hash=2166136261;
                for(var c=0;c<source.length;c++) hash=Math.imul(hash^source.charCodeAt(c),16777619)>>>0;
                revision[names[i]]=hash.toString(16);
                var path='revisions/'+revision[names[i]]+'/'+names[i]+'.txt';
                if(!file.isExists(path) && !file.writeTextSync(path,source)) throw new Error('Cannot preserve controller revision');
            }
            events.push({type:'controllerRevision',files:revision,startedAt:Date.now()});
        }, events: function () { return events; },
        focusGame: async function () { sessionReady(); await genshin.focusGame(); ready(); },
        requireInputReady: ready, keyPress: async function (key) {
            var closingJournal=key==='VK_ESCAPE' && lastObservation && lastObservation.hud.journal;
            await boundedKey(key,60);
            if(closingJournal) await sleep(500);
        }, release: release,
        teleportStarfellStatue: async function () {
            checkStop();
            events.push({type:'teleportRecovery',x:-1323.474,y:2566.115,startedAt:Date.now()});
            // Shipped tp.json Goddess id 7: the Statue unlocked in Bird's Eye View.
            await genshin.tp(-1323.474,2566.115,false); checkStop();
        },
        teleportFalconWaypoint: async function () {
            checkStop(); ready();
            if(!request||request.mission!=='questStep'||request.step!=='falconWaypoint'||!actOneFalconWaypointReady(lastObservation,Date.now()))
                throw new Error('Fresh safe Falcon waypoint objective required');
            var target=actOneFalconWaypointTarget();
            events.push({type:'teleportFalconWaypoint',x:target.x,y:target.y,frameId:lastObservation.frameId,startedAt:Date.now()});
            await genshin.tp(target.x,target.y,false); checkStop();
        },
        falconDismissPyro: async function () {
            checkStop();var o=lastObservation;
            if(!request||!/^falconDismiss(Pyro|Tutorial)$/.test(request.step)||!o||Date.now()-o.timestamp>1000||o.map!==null||!actOneFalconInfo(o.ocr)||o.hud.journal||o.hud.bigMap||o.hud.dialogueReady) throw new Error('Fresh recognized English Falcon tutorial required');
            events.push({type:'falconPyroTutorialDismiss',x:960,y:1018,frameId:o.frameId,startedAt:Date.now()});
            click(960,1018);
        },
        falconEnterAim: async function () {
            checkStop();if(!request||request.step!=='falconEnterAim'||!actOneFalconDomainHud(lastObservation,Date.now())) throw new Error('Fresh Falcon trial ground HUD required');
            return boundedKey('VK_R',60);
        },
        falconSelectAmber: async function () {
            checkStop();if(!request||!/^falconSelect(Amber|Traveler)$/.test(request.step)||!actOneFalconDomainHud(lastObservation,Date.now(),request.step==='falconSelectTraveler'?0.01:0.6)) throw new Error('Fresh Falcon trial HUD required');
            return boundedKey(request.step==='falconSelectTraveler'?'VK_1':'VK_2',60);
        },
        falconPause: async function () {
            checkStop();if(!request||!/^falcon(Pause|Combat|AmberCombat|Ranged|Engage)$/.test(request.step)||!lastObservation||Date.now()-lastObservation.timestamp>1000||lastObservation.map!==null||lastObservation.hud.journal||lastObservation.hud.bigMap||!lastObservation.hud.health) throw new Error('Fresh domain health evidence required to pause');
            return boundedKey('VK_ESCAPE',60);
        },
        falconContinue: function () {
            checkStop();var o=lastObservation,rows=o&&o.ocr||[];
            var target=rows.filter(function(r){return r.text.trim()==='Continue Challenge'&&r.x>750&&r.x<1000&&r.y>380&&r.y<460;});
            if(!request||['falconCombat','falconAmberCombat','falconInventory','falconContinue','falconEngage'].indexOf(request.step)<0||!o||Date.now()-o.timestamp>1000||target.length!==1||!rows.some(function(r){return r.text.trim()==='Leave Domain?'&&r.y>620&&r.y<700;})) throw new Error('Fresh domain pause menu required');
            var r=target[0];events.push({type:'falconContinue',frameId:o.frameId,startedAt:Date.now()});click(Math.round(r.x+r.width/2),Math.round(r.y+r.height/2));
        },
        falconInventory: async function () {
            checkStop();if(!request||request.step!=='falconInventory'||!actOneFalconDomainHud(lastObservation,Date.now(),0.2)) throw new Error('Fresh domain HUD required for food inventory');
            return boundedKey('VK_B',60);
        },
        journalInventory: async function () {
            checkStop();var o=lastObservation;
            if(!request||request.step!=='journalInventory'||!o||Date.now()-o.timestamp>1000||!o.hud.journal||!o.ocr.some(function(r){return /^(Crash Course|Sparks Amongst the Pages)$/.test(r.text.trim())&&r.x>800&&r.y<180;})) throw new Error('Fresh selected Act I temple journal required');
            await boundedKey('VK_ESCAPE',60);await sleep(400);checkStop();await boundedKey('VK_B',60);
        },
        pauseWorldInventory: async function () {
            checkStop();var o=lastObservation,h=o&&o.hud;
            if(!o||Date.now()-o.timestamp>1000||!h||!h.world||!h.health||h.health.current<=0||h.climbing||h.journal||h.bigMap||h.dialogueReady||h.choice||h.tutorialStep) return false;
            await boundedKey('VK_B',60);return true;
        },
        mapBindingProbe: function () {
            checkStop();var o=lastObservation;
            if(!o||Date.now()-o.timestamp>1000||!o.hud.health||o.hud.journal||o.hud.bigMap||o.hud.climbing)throw new Error('Fresh grounded HUD required for read-only map probe');
            var results={single:typeof host.toSingle};
            var probes={integer:function(){return genshin.getPositionFromMap('Teyvat',-1121,2191);},fraction:function(){return genshin.getPositionFromMap('Teyvat',-1120.64,2190.84);},single:function(){return genshin.getPositionFromMap('Teyvat',host.toSingle(-1120.64),host.toSingle(2190.84));}};
            Object.keys(probes).forEach(function(k){checkStop();try{var p=probes[k]();results[k]=p?{x:Number(p.x),y:Number(p.y)}:null;}catch(e){results[k]={error:String(e.message||e)};}});
            return results;
        },
        nativeFightProbe: function () {
            checkStop();var param=new AutoFightParam('English Starter Trials');
            return {runUpper:typeof dispatcher.RunAutoFightTask,runLower:typeof dispatcher.runAutoFightTask,linkedUpper:typeof dispatcher.GetLinkedCancellationTokenSource,linkedLower:typeof dispatcher.getLinkedCancellationTokenSource,timeoutUpper:param.Timeout,timeoutLower:param.timeout};
        },
        fieldFightPrepare: async function () {
            checkStop();var o=lastObservation;
            if(!request||request.step!=='fieldCombat'||!o||Date.now()-o.timestamp>1000||o.map!==null||!o.ocr.some(function(r){return r.text.trim()==='Food'&&r.x>100&&r.x<300&&r.y<80;})||o.ocr.some(function(r){return r.text.trim()==='Confirm';}))throw new Error('Fresh food inventory without confirmation required');
            await boundedKey('VK_ESCAPE',60);
        },
        fieldRetreatToStatue: async function () {
            checkStop();var o=lastObservation;
            if(!request||request.step!=='fieldRetreatToStatue'||!o||Date.now()-o.timestamp>1000||o.map!==null||!o.ocr.some(function(r){return r.text.trim()==='Food'&&r.x>100&&r.x<300&&r.y<80;})||o.ocr.some(function(r){return r.text.trim()==='Confirm';}))throw new Error('Fresh food inventory required for verified Statue retreat');
            await boundedKey('VK_ESCAPE',60);await sleep(400);await boundedKey('VK_M',60);await sleep(200);checkStop();await genshin.tp(-1323.474,2566.115,false);checkStop();
        },
        wolfDoorAction: async function () {
            checkStop();var o=lastObservation,h=o&&o.hud,p=o&&o.map,rows=o&&o.ocr||[];
            if(!request||request.step!=='wolfDoorInteract'||!o||Date.now()-o.timestamp>1000||!h.world||!p||Math.hypot(p.x+1642.421,p.y-2163.664)>15||h.dialogueReady||h.choice||h.climbing||h.objectives.indexOf('Enter the temple')<0)throw new Error('Fresh Wolf entrance objective and position required');
            var doors=rows.filter(function(r){return r.text.trim()==='Temple of the Wolf'&&r.x>1150&&r.x<1550&&r.y>400&&r.y<700;}),fs=rows.filter(function(r){return r.text.trim()==='F'&&r.x>1080&&r.x<1170&&r.y>400&&r.y<700;});
            if(doors.length!==1||!fs.length)throw new Error('Exact Wolf interaction row required');
            var fy=fs[0].y+fs[0].height/2,dy=doors[0].y+doors[0].height/2;
            if(Math.abs(fy-dy)<25){await boundedKey('VK_F',60);return 'interact';}
            if(dy-fy>40&&dy-fy<100&&rows.some(function(r){return r.text.trim()==='Kaeya'&&Math.abs(r.y+r.height/2-fy)<25;})){events.push({type:'wolfDoorSelect',scroll:-1,startedAt:Date.now()});verticalScroll(-1);return 'scroll';}
            throw new Error('Ambiguous Wolf interaction selection');
        },
        wolfFalconWaypoint: async function () {
            checkStop();var o=lastObservation,h=o&&o.hud,hp=h&&h.health;
            if(!request||request.step!=='wolfFalconWaypoint'||!o||Date.now()-o.timestamp>1000||!h.world||!hp||hp.current/hp.max<0.6||h.climbing||h.dialogueReady||h.choice||h.objectives.indexOf('Meet Kaeya at the temple')<0)throw new Error('Fresh safe Kaeya world objective required');
            await boundedKey('VK_M',60);await sleep(200);checkStop();await genshin.tp(-1122.173,2197.455,false);checkStop();
        },
        fieldSelectTraveler: async function () {
            checkStop();var o=lastObservation,h=o&&o.hud;
            if(!request||request.step!=='fieldCombat'||!o||Date.now()-o.timestamp>1000||!h.world||!h.health||h.climbing||h.dialogueReady||h.choice||h.objectives.indexOf('Meet Kaeya at the temple')<0||o.ocr.some(function(r){return /^(Food|Weapons|Inventory capacity)/.test(r.text.trim())&&r.y<80;}))throw new Error('Fresh Kaeya approach world HUD required');
            await boundedKey('VK_1',60);
        },
        fieldNativeFight: async function () {
            checkStop();var o=lastObservation,h=o&&o.hud,hp=h&&h.health;
            if(!request||request.step!=='fieldCombat'||!o||Date.now()-o.timestamp>1000||!h.world||!hp||hp.current/hp.max<0.9||h.climbing||h.dialogueReady||h.choice||h.objectives.indexOf('Meet Kaeya at the temple')<0||o.ocr.some(function(r){return /^(Food|Weapons|Inventory capacity)/.test(r.text.trim())&&r.y<80;}))throw new Error('Fresh healed Kaeya approach HUD required');
            events.push({type:'nativeAutoFight',strategy:'English Starter Trials',timeoutMs:15000,frameId:o.frameId,startedAt:Date.now()});
            return runStarterTrialAutoFight({createLinkedCancellationTokenSource:function(){return dispatcher.GetLinkedCancellationTokenSource();},createAutoFightParam:function(name){return new AutoFightParam(name);},runAutoFightTask:function(param,token){return dispatcher.RunAutoFightTask(param,token);}},checkStop,{sleep:sleep});
        },
        falconInventoryAction: async function (name) {
            checkStop();var o=lastObservation,rows=o&&o.ocr||[];
            if(!request||request.step!==name||!o||Date.now()-o.timestamp>1000||o.map!==null||!rows.some(function(r){return /^(Weapons|Food)$/.test(r.text.trim())&&r.x>120&&r.x<280&&r.y<70;})) throw new Error('Fresh recognized inventory required');
            if(name==='falconFoodTab'){events.push({type:'falconFoodTab',x:864,y:48,startedAt:Date.now()});click(864,48);return;}
            if(name==='falconCancelFood') {var cancel=rows.filter(function(r){return r.text.trim()==='Cancel'&&r.x>650&&r.x<850&&r.y>730&&r.y<800;});if(cancel.length!==1)throw new Error('Exact food Cancel required');click(Math.round(cancel[0].x+cancel[0].width/2),Math.round(cancel[0].y+cancel[0].height/2));return;}
            if(name==='falconSelectEgg') {if(rows.some(function(r){return r.text.trim()==='Confirm';})||!rows.some(function(r){return r.text.trim()==='Sweet Madame'&&r.x>1300&&r.y<180;}))throw new Error('Verified food grid required');events.push({type:name,x:325,y:180,startedAt:Date.now()});click(325,180);return;}
            if(name==='falconSelectMadame') {if(rows.some(function(r){return r.text.trim()==='Confirm';})||!rows.some(function(r){return r.text.trim()==='Teyvat Fried Egg'&&r.x>1300&&r.y<180;}))throw new Error('Verified food grid required');events.push({type:name,x:178,y:180,startedAt:Date.now()});click(178,180);return;}
            if(name==='falconUseMadame'||name==='falconUseEgg') {
                var target=rows.filter(function(r){return r.text.trim()==='Use'&&r.x>1600&&r.y>980;});
                if(target.length!==1||rows.some(function(r){return r.text.trim()==='Confirm';})||!rows.some(function(r){return r.text.trim()===(name==='falconUseEgg'?'Teyvat Fried Egg':'Sweet Madame')&&r.x>1300&&r.y>110&&r.y<180;})) throw new Error('Selected Sweet Madame and Use required');
                var r=target[0];events.push({type:name,startedAt:Date.now()});click(Math.round(r.x+r.width/2),Math.round(r.y+r.height/2));return;
            }
            if(/^falcon(ReviveTraveler|FeedTraveler|FeedAmber|SelectAmberFood)$/.test(name)) {
                var title=name==='falconFeedAmber'?'Amber':'Traveler';
                var confirms=rows.filter(function(r){return r.text.trim()==='Confirm'&&r.x>1100&&r.x<1250&&r.y>730&&r.y<790;});
                if(confirms.length!==1||!rows.some(function(r){return r.text.trim()===title&&r.x>800&&r.x<1050&&r.y>250&&r.y<320;})||!rows.some(function(r){return r.text.trim()==='Amount to use'&&r.x>600&&r.y>600&&r.y<660;})||!rows.some(function(r){return r.text.trim()===(name==='falconReviveTraveler'?'Teyvat Fried Egg':'Sweet Madame')&&r.x>1300&&r.y<180;})) throw new Error('Exact healing food and character confirmation required');
                events.push({type:name,character:title,startedAt:Date.now()});
                if(name==='falconSelectAmberFood') click(1045,440);
                else {var target=confirms[0];click(Math.round(target.x+target.width/2),Math.round(target.y+target.height/2));}
                return;
            }
            if(name==='falconCloseInventory') return boundedKey('VK_ESCAPE',60);
            throw new Error('Unsupported inventory action');
        },
        falconResume: function () {
            checkStop();
            if(!request||request.step!=='falconResume'||!file.isExists('falcon-resume.json')) throw new Error('Explicit Falcon resume evidence required');
            var e=JSON.parse(file.readTextSync('falcon-resume.json'));
            if(!/^[A-Za-z0-9_-]{1,80}$/.test(e.fromSession||'')) throw new Error('Invalid prior session');
            var prior=JSON.parse(file.readTextSync('reports/'+e.fromSession+'.json'));
            var current=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            var proof=actOneValidateFalconResume(e,prior,current,request.session,expectedSession,lastObservation,Date.now());
            if(!proof) throw new Error('Verified Falcon restart handoff required');
            var target=actOneFalconContinueTarget(lastObservation,Date.now());
            events.push({type:'falconResume',provenance:proof,frameId:lastObservation.frameId,startedAt:Date.now()});
            click(Math.round(target.x+target.width/2),Math.round(target.y+target.height/2));return proof;
        },
        falconCombatKey: async function(key) {
            checkStop();var switching=key==='VK_1'||key==='VK_2';
            if(!request||!/^falcon(Combat|AmberCombat)$/.test(request.step)||!actOneFalconDomainHud(lastObservation,Date.now(),switching?0.2:0.6)||['VK_1','VK_2','VK_E','VK_Q','VK_LBUTTON'].indexOf(key)<0) throw new Error('Fresh safe Falcon combat HUD required');
            return boundedKey(key,key==='VK_E'?1000:60);
        },
        falconCombatScan: async function(first) {
            checkStop();if(!request||!/^falcon(Combat|AmberCombat)$/.test(request.step)||!actOneFalconDomainHud(lastObservation,Date.now())) throw new Error('Fresh Falcon HUD required for combat scan');
            if(first) return boundedKey('VK_W',600);
            events.push({type:'falconCombatScan',dx:750,frameId:lastObservation.frameId,startedAt:Date.now()});moveMouseBy(750,0);
        },
        falconCombatApproach: async function () {
            checkStop();if(!request||!/^falcon(Combat|AmberCombat)$/.test(request.step)||!actOneFalconDomainHud(lastObservation,Date.now())||!(lastObservation.hud.enemyBars||[]).some(function(b){return Math.abs(b.x-960)<200;})) throw new Error('Fresh centered enemy required for combat approach');
            return boundedKey('VK_W',600);
        },
        falconSight: async function () {
            checkStop();var o=lastObservation;
            if(!request||request.step!=='falconSight'||!actOneFalconDomainHud(o,Date.now())||!o.ocr.some(function(r){return r.x>650&&r.x<800&&r.y>170&&r.y<225&&r.text.trim()==='Click and hold the scroll wheel to activate';})||!o.ocr.some(function(r){return r.y>205&&r.y<255&&r.text.trim()==='Elemental Sight';})) throw new Error('Fresh Falcon Elemental Sight instruction required');
            return boundedKey('VK_MBUTTON',800);
        },
        falconAimAction: async function (kind) {
            checkStop();if(!request||request.step!=='falcon'+kind||!actOneFalconAimHud(lastObservation,Date.now())) throw new Error('Fresh Falcon aimed trial HUD required');
            if(kind==='FireAim') return boundedKey('VK_LBUTTON',60);
            if(kind==='ExitAim') return boundedKey('VK_R',60);
            throw new Error('Unsupported Falcon aim action');
        },
        falconAdjustAim: function (name) {
            checkStop();if(!request||request.step!==name||!/^falconAim(Left|Right|Up|Down)(Fine)?$/.test(name)||!actOneFalconAimHud(lastObservation,Date.now())) throw new Error('Fresh Falcon aimed HUD required');
            var n=name.endsWith('Fine')?25:100,dx=name.indexOf('Left')>=0?-n:name.indexOf('Right')>=0?n:0,dy=name.indexOf('Up')>=0?-n:name.indexOf('Down')>=0?n:0;
            events.push({type:'falconAdjustAim',dx:dx,dy:dy,frameId:lastObservation.frameId,startedAt:Date.now()});moveMouseBy(dx,dy);
        },
        falconRangedAction: async function(kind,target) {
            checkStop();var o=lastObservation;
            if(!request||request.step!=='falconRanged'||!actOneFalconAimHud(o,Date.now(),kind==='exit'?0.01:0.6)) throw new Error('Fresh safe aimed Falcon HUD required');
            if(kind==='exit') return boundedKey('VK_R',60);
            if(kind==='fire') return boundedKey('VK_LBUTTON',60);
            if(kind==='aim') {
                if(!target||!o.hud.enemyBars.some(function(b){return b.x===target.x&&b.y===target.y;})) throw new Error('Fresh enemy bar required');
                var dx=Math.max(-150,Math.min(150,Math.round((target.x-960)/1.6))),dy=Math.max(-100,Math.min(100,Math.round((target.y+45-540)/0.6)));
                events.push({type:'falconRangedAim',dx:dx,dy:dy,frameId:o.frameId,startedAt:Date.now()});moveMouseBy(dx,dy);return;
            }
            throw new Error('Unsupported ranged action');
        },
        falconOpenDoor: async function () {
            checkStop();
            if(!request||request.step!=='falconOpenDoor'||!actOneFalconDomainHud(lastObservation,Date.now())||!lastObservation.hud.interact||
                !lastObservation.ocr.some(function(r){return r.text.trim()==='Open Door'&&r.x>1150&&r.x<1550&&r.y>400&&r.y<700;})) throw new Error('Fresh Falcon Open Door prompt required');
            return boundedKey('VK_F',60);
        },
        falconRotate: function (dx) {
            checkStop();if(!request||request.mission!=='questStep'||!/^falconLook/.test(request.step)||!actOneFalconDomainHud(lastObservation,Date.now())||!Number.isInteger(dx)||[100,250,750].indexOf(Math.abs(dx))<0) throw new Error('Fresh Falcon HUD and bounded look required');
            events.push({type:'falconLook',dx:dx,frameId:lastObservation.frameId,startedAt:Date.now()});moveMouseBy(dx,0);
        },
        falconPitch: function(dy) {
            checkStop();if(!request||!/^falconLook(Down|Up)$/.test(request.step)||!actOneFalconDomainHud(lastObservation,Date.now())||Math.abs(dy)!==250) throw new Error('Fresh Falcon HUD and bounded pitch required');
            events.push({type:'falconPitch',dy:dy,frameId:lastObservation.frameId,startedAt:Date.now()});moveMouseBy(0,dy);
        },
        falconRewardInteract: async function () {
            checkStop();var o=lastObservation;
            if(!request||request.step!=='falconRewardInteract'||!actOneFalconDomainHud(o,Date.now())||!o.ocr.some(function(r){return /^(Precious Chest|Leave Domain\??|Adventurer's(?: Experience)?|Fine Enhancement(?: Ore)?)$/.test(r.text.trim())&&r.x>1150&&r.x<1600&&r.y>400&&r.y<700;})) throw new Error('Fresh Falcon reward or exit interaction required');
            return boundedKey('VK_F',60);
        },
        falconCrystalStrike: async function () {
            checkStop();if(!request||request.step!=='falconCrystalStrike'||!actOneFalconDomainHud(lastObservation,Date.now())) throw new Error('Fresh Falcon HUD required for crystal attack');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!reports.some(function(r){return r.status==='completed'&&r.details&&r.details.result&&r.details.result.step==='falconGlideForward';})) throw new Error('Falcon glide progression required before crystal attack');
            return boundedKey('VK_LBUTTON',60);
        },
        falconWindJump: async function () {
            checkStop();
            if(!request||request.step!=='falconWindJump'||!actOneFalconDomainHud(lastObservation,Date.now())) throw new Error('Fresh Falcon ground HUD required for wind jump');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!reports.some(function(r){return r.status==='completed'&&r.details&&r.details.result&&r.details.result.step==='falconFireAim'&&Number.isFinite(r.timestamp)&&r.timestamp<=Date.now()&&Date.now()-r.timestamp<600000;})) throw new Error('Recent Falcon Pyro shot required');
            await boundedKey('VK_SPACE',60);await sleep(220);checkStop();await boundedKey('VK_SPACE',60);
        },
        falconGlideForward: async function () {
            checkStop();var o=lastObservation;
            var flying=o&&o.hud&&!o.hud.groundControls&&o.ocr.some(function(r){return r.text.trim()==='Space'&&r.x>1650&&r.x<1780&&r.y>1000;});
            var copy=o&&Object.assign({},o,{hud:Object.assign({},o.hud,{groundControls:true})});
            if(!request||request.step!=='falconGlideForward'||!flying||!actOneFalconDomainHud(copy,Date.now())) throw new Error('Fresh Falcon gliding HUD required');
            await boundedKey('VK_W',800);
        },
        falconMove: async function (key,ms) {
            checkStop();
            if(!request||request.mission!=='questStep'||!/^falcon/.test(request.step)||!actOneFalconDomainHud(lastObservation,Date.now())) throw new Error('Fresh safe Falcon trial HUD required');
            if(['VK_W','VK_A','VK_S','VK_D'].indexOf(key)<0||!Number.isInteger(ms)||ms<1||ms>800) throw new Error('Invalid bounded domain movement');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!reports.some(function(r){return r.status==='completed'&&r.details&&r.details.result&&['falconPartyStart','falconResume'].indexOf(r.details.result.step)>=0;})) throw new Error('Verified Falcon entry or restart handoff in this session required');
            return boundedKey(key,ms);
        },
        startFalconParty: function () {
            checkStop();
            var target=actOneFalconPartyTarget(lastObservation,Date.now());
            if(!request||request.step!=='falconPartyStart'||!target) throw new Error('Fresh verified Falcon party setup required');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            var prior=reports.filter(function(r){return r.status==='completed'&&r.mission==='questStep'&&r.details&&r.details.result&&r.details.result.step==='falconStart';}).pop();
            if(!prior||Date.now()-prior.timestamp>300000) throw new Error('Recent verified Falcon entrance selection required');
            events.push({type:'falconPartyStart',frameId:lastObservation.frameId,x:target.x,y:target.y,startedAt:Date.now()});
            click(target.x,target.y);
        },
        startWolfDomain: function () {
            checkStop();ready();var target=actOneTempleStartTarget(lastObservation,Date.now(),'Wolf');
            if(!request||request.mission!=='questStep'||request.step!=='wolfStart'||!target)throw new Error('Fresh exact level-5 Wolf Domain Entrance required');
            events.push({type:'wolfDomainStart',frameId:lastObservation.frameId,label:target.label,x:target.x,y:target.y,startedAt:Date.now()});
            click(target.x,target.y);checkStop();return target.label;
        },
        wolfDomainAction: async function () {
            checkStop();
            var actions={wolfForward:['VK_W',800],wolfForwardFine:['VK_W',200],wolfLeft:['VK_A',600],wolfRight:['VK_D',600],wolfPause:['VK_ESCAPE',60]};
            var action=request&&actions[request.step];
            if(!request||request.mission!=='questStep'||(!action&&!/^wolfLook(Right|Left|Down|Up)$/.test(request.step))||!actOneWolfDomainHud(lastObservation,Date.now())) throw new Error('Fresh safe Wolf trial HUD required');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!reports.some(function(r){return r.session===request.session&&r.status==='completed'&&r.details&&r.details.result&&r.details.result.step==='wolfPartyStart';})) throw new Error('Same-session Wolf entry required');
            if(lastObservation.hud.interact&&request.step!=='wolfPause') throw new Error('Inspect available Wolf interaction before moving');
            if(action&&request.step!=='wolfPause'&&(lastObservation.hud.enemyBars||[]).length)throw new Error('Enemy acquired; use bounded Wolf combat');
            if(action)return boundedKey(action[0],action[1]);
            var dx=request.step==='wolfLookRight'?250:request.step==='wolfLookLeft'?-250:0,dy=request.step==='wolfLookDown'?250:request.step==='wolfLookUp'?-250:0;events.push({type:'rotate',dx:dx,dy:dy,startedAt:Date.now()});moveMouseBy(dx,dy);
        },
        wolfContinue: function () {
            checkStop();var target=actOneFalconContinueTarget(lastObservation,Date.now());
            if(!request||request.mission!=='questStep'||request.step!=='wolfContinue'||!target)throw new Error('Fresh Wolf pause menu required');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!reports.some(function(r){return r.session===request.session&&r.status==='completed'&&r.details&&r.details.result&&r.details.result.step==='wolfPartyStart';}))throw new Error('Same-session Wolf entry required');
            events.push({type:'wolfContinue',frameId:lastObservation.frameId,startedAt:Date.now()});click(Math.round(target.x+target.width/2),Math.round(target.y+target.height/2));
        },
        wolfCombatKey: async function(key) {
            checkStop();
            if(!request||request.mission!=='questStep'||request.step!=='wolfCombat'||!actOneWolfDomainHud(lastObservation,Date.now())||['VK_3','VK_E','VK_LBUTTON'].indexOf(key)<0||!(lastObservation.hud.enemyBars||[]).length)throw new Error('Fresh healthy Wolf trial and enemy evidence required');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!reports.some(function(r){return r.session===request.session&&r.status==='completed'&&r.details&&r.details.result&&r.details.result.step==='wolfPartyStart';}))throw new Error('Same-session Wolf entry required');
            return boundedKey(key,60);
        },
        wolfPauseCombat: async function() {
            checkStop();
            if(!request||request.step!=='wolfCombat'||!actOneWolfDomainHud(lastObservation,Date.now(),0)||!lastObservation.hud.health||lastObservation.hud.health.current<=0)throw new Error('Fresh Wolf HUD required to pause combat');
            return boundedKey('VK_ESCAPE',60);
        },
        wolfAdvanceDialogue: async function () {
            checkStop();var o=lastObservation,h=o&&o.hud;
            if(!request||request.mission!=='questStep'||request.step!=='wolfOpeningDialogue'||!o||Date.now()-o.timestamp>1000||o.map!==null||!h.dialogueReady||h.choice||h.journal||h.bigMap||!(o.ocr||[]).some(function(r){return r.text.trim()==='Kaeya'&&r.x>600&&r.x<1200&&r.y>830&&r.y<900;})) throw new Error('Fresh Wolf Kaeya opening dialogue required');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!reports.some(function(r){return r.session===request.session&&r.status==='completed'&&r.details&&r.details.result&&r.details.result.step==='wolfPartyStart';})) throw new Error('Same-session Wolf entry required');
            return boundedKey('VK_SPACE',60);
        },
        wolfEntryForward: async function () {
            checkStop();
            if(!request||request.mission!=='questStep'||request.step!=='wolfEntryApproach'||!actOneWolfEntryHud(lastObservation,Date.now())||lastObservation.hud.interact) throw new Error('Fresh safe Wolf entrance HUD required');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!reports.some(function(r){return r.session===request.session&&r.status==='completed'&&r.details&&r.details.result&&r.details.result.step==='wolfPartyStart';})) throw new Error('Same-session verified Wolf entry required');
            await boundedKey('VK_W',800);
        },
        startWolfParty: function () {
            checkStop();ready();
            if(!request||request.mission!=='questStep'||request.step!=='wolfPartyStart') throw new Error('Wolf party start request required');
            var reports=file.readTextSync('reports/'+request.session+'.jsonl').split(/\r?\n/).filter(function(line){return line.trim().length>0;}).map(function(line){return JSON.parse(line);});
            var target=actOneWolfPartyTarget(lastObservation,Date.now(),reports,request.session);
            if(!target) throw new Error('Fresh Wolf party setup and uninterrupted same-session entrance required');
            events.push({type:'wolfPartyStart',frameId:lastObservation.frameId,x:target.x,y:target.y,startedAt:Date.now()});
            click(target.x,target.y);checkStop();
        },
        startFalconDomain: function () {
            checkStop(); ready();
            var target=actOneFalconStartTarget(lastObservation,Date.now());
            if(!request||request.mission!=='questStep'||request.step!=='falconStart'||!target)
                throw new Error('Fresh exact Falcon Domain Entrance screen required');
            events.push({type:'falconDomainStart',frameId:lastObservation.frameId,label:target.label,x:target.x,y:target.y,startedAt:Date.now()});
            click(target.x,target.y); checkStop();
            return target.label;
        },
        chooseStatueBlessing: function () {
            checkStop();
            if(!lastObservation || Date.now()-lastObservation.timestamp>1000) throw new Error('Fresh Statue menu required');
            var choices=lastObservation.ocr.filter(function(r){return /^Statue.s Blessing$/i.test(r.text.trim()) && r.x>1100 && r.y>400 && r.y<850;});
            if(choices.length!==1) throw new Error('Unique Statue blessing option required');
            var r=choices[0];events.push({type:'statueBlessing',startedAt:Date.now()});click(Math.round(r.x+r.width/2),Math.round(r.y+r.height/2));
        },
        healTravelerAtStatue: function () {
            checkStop();
            if(!lastObservation || Date.now()-lastObservation.timestamp>1000 ||
               !lastObservation.ocr.some(function(r){return /Click on the character portrait to restore HP/.test(r.text) && r.y<100;}) ||
               !lastObservation.ocr.some(function(r){return /^Statue.s Blessing$/.test(r.text.trim()) && r.x>1400 && r.y<100;}) ||
               !lastObservation.ocr.some(function(r){return /Restorative Power:\s*[1-9][0-9]*\s*\//.test(r.text);})) throw new Error('Fresh Statue healing panel required');
            // Verified starter roster: Traveler first, Amber second (frame898).
            // Restore both so switching active character cannot strand recovery at 50%.
            events.push({type:'healStarterParty',portraits:[118,298],y:160,startedAt:Date.now()});click(118,160);click(298,160);
        },
        pauseCombat: async function () {
            checkStop();
            if (!lastObservation || Date.now()-lastObservation.timestamp > 1000 || !lastObservation.hud.world) return false;
            // Pausing must remain available below the attack health threshold.
            await boundedKey('VK_J',60); await sleep(700); return true;
        },
        combatLook: function (dx) {requireCombat();if(!Number.isInteger(dx)||Math.abs(dx)>250) throw new Error('Invalid combat scan');events.push({type:'combatLook',dx:dx,startedAt:Date.now()});moveMouseBy(dx,0);},
        selectTraveler: function () { requireCombat(); return boundedKey('VK_1',60); },
        combatAttack: function () { requireCombat(); return boundedKey('VK_LBUTTON',60); },
        fireAerial: function (ms) { requireAerial();if(!Number.isInteger(ms)||ms<1||ms>800) throw new Error('Invalid aerial fire duration');events.push({type:'aerialFire',durationMs:ms,frameId:lastObservation.frameId,startedAt:Date.now()});ready();return boundedKey('VK_LBUTTON',ms); },
        combatSkill: function () { requireCombat(); return boundedKey('VK_E',1000); },
        combatBurst: function () { requireCombat(); return boundedKey('VK_Q',60); },
        combatAdvance: function () { requireCombat(); return boundedKey('VK_W',250); },
        selectAmber: function () { requireCombat(); return boundedKey('VK_2',60); },
        releaseClimb: async function () {
            checkStop();
            if(!lastObservation || Date.now()-lastObservation.timestamp>1000 || !lastObservation.hud.climbing) throw new Error('Fresh climbing controls required');
            await boundedKey('VK_X',60);await sleep(250);await boundedKey('VK_S',250);await sleep(150);
        },
        advanceTutorial: async function () {
            checkStop();
            if (!lastObservation || Date.now()-lastObservation.timestamp > 1000 || ['switchAmber','enterAim','exitAim','aimSlime','navigateQuest','trackQuest','glideForward','glideOpen'].indexOf(lastObservation.hud.tutorialStep) < 0) throw new Error('Fresh recognized tutorial required');
            if (lastObservation.hud.tutorialStep === 'navigateQuest') {
                var button=actOneNavigateQuestButton(lastObservation,Date.now());
                if(!button) throw new Error('Fresh unique City of Freedom Navigate coachmark required');
                var x=Math.round(button.x+button.width/2),y=Math.round(button.y+button.height/2);
                events.push({type:'tutorialNavigateQuest',frameId:lastObservation.frameId,x:x,y:y,startedAt:Date.now()});
                click(x,y); return 'clicked';
            }
            if (lastObservation.hud.tutorialStep === 'trackQuest') {
                  var targetPoint=actOneTrackQuestTarget(lastObservation,Date.now());
                  if(!targetPoint) throw new Error('Fresh Amber quest-tracking coachmark and icon target required');
                  var tx=targetPoint.x,ty=targetPoint.y;
                events.push({type:'tutorialTrackQuest',frameId:lastObservation.frameId,x:tx,y:ty,startedAt:Date.now()});
                await actOneAltClick({x:tx,y:ty},{now:Date.now,sleep:sleep,checkStop:checkStop,
                    keyDown:function(key){held=key;keyDown(key);},click:click,release:release});
                return 'clicked';
            }
            if (lastObservation.hud.tutorialStep === 'glideForward') {
                events.push({type:'tutorialGlideForward',frameId:lastObservation.frameId,durationMs:500,startedAt:Date.now()});
                return actOneGlideForward(lastObservation,Date.now(),{checkStop:checkStop,forward:function(ms){return boundedKey('VK_W',ms);}});
            }
            if (lastObservation.hud.tutorialStep === 'glideOpen') {
                events.push({type:'tutorialGlideOpen',frameId:lastObservation.frameId,durationMs:60,startedAt:Date.now()});
                return actOneGlideOpen(lastObservation,Date.now(),{checkStop:checkStop,pressSpace:function(ms){return boundedKey('VK_SPACE',ms);}});
            }
            if (lastObservation.hud.tutorialStep === 'aimSlime') {
                var target = lastObservation.hud.slimeTarget;
                if (!target) throw new Error('Unique airborne slime unavailable');
                var ex=target.x-960,ey=target.y-540;
                if (Math.abs(ex)<=18 && Math.abs(ey)<=18) { await boundedKey('VK_LBUTTON',60); return 'shot'; }
                var dx=Math.max(-150,Math.min(150,Math.round(ex*0.5))),dy=Math.max(-150,Math.min(150,Math.round(ey*0.9)));
                events.push({type:'aim',dx:dx,dy:dy,target:target,frameId:lastObservation.frameId,startedAt:Date.now()});
                moveMouseBy(dx,dy); return;
            }
            return boundedKey(lastObservation.hud.tutorialStep === 'switchAmber' ? 'VK_2' : 'VK_R',60);
        },
        continueCharacter: function () {
            checkStop();
            if (!lastObservation || Date.now()-lastObservation.timestamp > 1000 || !lastObservation.hud.characterAcquired) throw new Error('Fresh character acquisition screen required');
            events.push({type:'characterAcquiredContinue',character:lastObservation.hud.characterAcquired,frameId:lastObservation.frameId,startedAt:Date.now()});
            click(1700,900);
        },
        chooseChoice: function (label) {
            checkStop();
            if (!lastObservation || Date.now() - lastObservation.timestamp > 1000 || !lastObservation.hud.choice) throw new Error('Fresh dialogue choice required');
            var matches = lastObservation.ocr.filter(function (r) { return r.text.trim() === label && r.x > 1000 && r.y > 430 && r.y < 830; });
            if (matches.length !== 1) throw new Error('Dialogue option is ambiguous');
            var row = matches[0]; events.push({ type: 'dialogueChoice', label: label, frameId: lastObservation.frameId, startedAt: Date.now() });
            click(Math.round(row.x + row.width / 2), Math.round(row.y + row.height / 2));
        },
        rotate: function (dx) {
            checkStop(); if (!Number.isInteger(dx) || Math.abs(dx) > 750) throw new Error('Invalid rotation');
            events.push({ type: 'rotate', dx: dx, startedAt: Date.now() }); moveMouseBy(dx, 0);
        },
        forward: function (ms) { if (!Number.isInteger(ms) || ms < 1 || ms > 800) throw new Error('Invalid movement duration'); return boundedKey('VK_W', ms); },
        descendClimb: function (ms) { if (!Number.isInteger(ms) || ms < 1 || ms > 800) throw new Error('Invalid climb descent duration'); return boundedKey('VK_S', ms); },
        write: function (p, t) { if (!file.writeTextSync(p, t)) throw new Error('Cannot write ' + p); },
        append: function (p,t) {if(!file.writeTextSync(p,t,true))throw new Error('Cannot append '+p);},
        wasSeen: function (session,id) {return file.isExists('receipts/'+session+'/'+id+'.json');},
        observe: async function (session, frame) {
            var focusRecovery = request && request.mission === 'questStep' && request.step === 'focusGame' &&
                request.session === session && Number.isInteger(frame) && frame > 0;
            if (focusRecovery && !focusRecoveryAttempted) {
                sessionReady();
                if (request && file.isExists('stop.json')) {
                    var focusStop = JSON.parse(file.readTextSync('stop.json'));
                    if (focusStop.session === request.session && focusStop.createdAt >= request.createdAt) { release(); throw new Error('Stop requested'); }
                }
                focusRecoveryAttempted = true;
                var focusEvent = {type:'focusGameRecovery',frame:frame,startedAt:Date.now(),resultingFocus:null,ready:false,error:null};
                events.push(focusEvent);
                var focusError = null, readyError = null;
                try { await genshin.focusGame(); } catch (e) { focusError = e; }
                focusEvent.resultingFocus = genshin.isGameForeground === true;
                try { ready(); } catch (e) { readyError = e; }
                focusEvent.ready = !readyError;
                focusEvent.finishedAt = Date.now();
                focusEvent.error = focusError ? String(focusError&&focusError.message||focusError) : readyError ? String(readyError&&readyError.message||readyError) : null;
                if (focusError) throw focusError;
                if (readyError) throw readyError;
            } else ready();
            var t0 = Date.now(), img = captureGameRegion(), captureMs = Date.now() - t0;
            try {
                if (Number(img.width) !== 1920 || Number(img.height) !== 1080) throw new Error('1920x1080 capture required');
                var o0 = Date.now(), rows = readRows(img, 0, 0, 1920, 1080);
                var fullOcrMs = Date.now() - o0, health0 = Date.now(), healthRows = readHealth(img, rows);
                var healthOcrMs = Date.now() - health0, objective0 = Date.now();
                var reusedObjectiveRows = actOneObjectiveRows(rows, request && request.objective);
                var objectiveRows = reusedObjectiveRows || readRows(img, 65, 230, 630, 85);
                var objectiveOcrMs = Date.now() - objective0;
                var ocrMs = Date.now() - o0;
                var p0 = Date.now(), png = 'observations/' + session + '/frame-' + String(frame).padStart(4, '0') + '.png';
                if (!file.writeImageSync(png, img.srcMat)) throw new Error('PNG write failed');
                var pngMs = Date.now() - p0, map0 = Date.now(), pos = null, mapDiagnostic = null;
                try {
                    var mp;
                    if(request&&request.mission==='navigation') {
                        var navAnchor=actOneNavigationMapAnchor(request,navLastAcceptedPosition);
                        if(navAnchor) {
                            mp=genshin.getPositionFromMap('Teyvat',host.toSingle(navAnchor.x),host.toSingle(navAnchor.y));
                            var accepted=actOneAcceptNavigationPosition(request,navLastAcceptedPosition,mp);
                            if(!accepted)mapDiagnostic={reason:'Local candidate rejected',anchor:navAnchor,candidate:mp?{x:Number(mp.x),y:Number(mp.y)}:null};
                            if(accepted) { navLastAcceptedPosition={x:accepted.x,y:accepted.y};pos={x:accepted.x,y:accepted.y,map:'Teyvat',cameraAngle:Number(genshin.getCameraOrientation())}; }
                        }
                    } else {
                        mp=genshin.getPositionFromMap('Teyvat',0);
                        if(mp&&Number.isFinite(Number(mp.x))&&Number.isFinite(Number(mp.y))) pos={x:Number(mp.x),y:Number(mp.y),map:'Teyvat',cameraAngle:Number(genshin.getCameraOrientation())};
                    }
                } catch (mapError) { mapDiagnostic={reason:String(mapError&&mapError.message||mapError)}; }
                var mapMs = Date.now() - map0, text = rows.map(function (r) { return r.text; }).join(' ');
                var hp = actOneHealth(healthRows);
                var auto = rows.some(function (r) { return /^Auto$/i.test(r.text.trim()) && r.x < 350 && r.y < 150; });
                var interactionObjective=actOneResolveInteractionObjective(request&&request.objective,objectiveRows);
                var choice = rows.some(function (r) { return r.x > 1000 && r.y > 430 && r.y < 790 && r.text.trim().length > 6; });
                var journal = rows.some(function (r) { return /^In Progress$/i.test(r.text.trim()) && r.y < 100; });
                var bigMap = !pos && !journal && (/Exploration Progress|Starfell Valley/.test(text) || actOneFullMapState(rows));
                var acquired = /Obtained New Character/.test(text) && /Click anywhere in the blank area to continue/.test(text) ? rows.filter(function(r) { return ['Amber','Kaeya','Lisa'].indexOf(r.text.trim()) >= 0 && r.x < 500 && r.y > 500 && r.y < 700; }) : [];
                var tutorialStep = /Press 2 to switch to Amber/i.test(text) && /Use Amber to defeat the airborne/i.test(text) ? 'switchAmber' : null;
                if(actOneFalconInfo(rows)) tutorialStep='falconInfo';
                if (/Press R to enter\/exit aiming mode/i.test(text) && /Use Amber to defeat the airborne/i.test(text)) tutorialStep = 'enterAim';
                if (/Move cursor to aim. Try attacking the floating Anemo Slime/i.test(text) && /Use Amber to defeat the airborne/i.test(text)) tutorialStep = 'aimSlime';
                if (/Press R again to exit aiming mode/i.test(text) && /Go to the location designated by Amber/i.test(text)) tutorialStep = 'exitAim';
                var combatObjective = objectiveRows.some(function(r){return ['Defeat the nearby hilichurls','Clear out the nearby hilichurl camp'].indexOf(r.text.trim())>=0;});
                if(journal&&actOneNavigateQuestState(rows)) tutorialStep='navigateQuest';
                var trackQuest=actOneTrackQuestState(rows);
                if(trackQuest) tutorialStep='trackQuest';
                var safeWorldCandidate=!!pos&&!!hp&&!auto&&!journal&&!bigMap;
                if(!tutorialStep&&actOneGlideForwardState(rows,pos,hp,{world:safeWorldCandidate,auto:auto,journal:journal,bigMap:bigMap,
                    dialogueReady:actOneDialogueReady(rows,choice),choice:auto&&choice,objectiveChanged:/objective updated|quest completed/i.test(text)})) tutorialStep='glideForward';
                if(!tutorialStep&&actOneGlideOpenState(rows,pos,hp,{world:safeWorldCandidate,auto:auto,journal:journal,bigMap:bigMap,
                    dialogueReady:actOneDialogueReady(rows,choice),choice:auto&&choice,objectiveChanged:/objective updated|quest completed/i.test(text)})) tutorialStep='glideOpen';
                var controlOcrMs=0;
                if((pos||(request&&request.mission==='questStep'&&/^(falcon|wolf)/.test(request.step)))&&hp&&!auto&&!journal&&!bigMap&&!(auto&&choice)&&!tutorialStep&&actOneNeedsControlCrop(rows)) {
                    var control0=Date.now(),controlLocal=scaledRows(img,1520,985,390,80);
                    rows=actOneMergeControlCropRows(rows,controlLocal,1520,985);
                    controlOcrMs=Date.now()-control0;ocrMs=Date.now()-o0;
                }
                if(!pos&&hp&&!auto&&!journal&&!bigMap&&request&&request.mission==='questStep'&&/^falcon/.test(request.step)&&
                    (!rows.some(function(r){return /^[A\u00c1]mber$/.test(r.text.trim())&&r.x>1550&&r.y>300&&r.y<600;})||
                    !rows.some(function(r){return r.text.trim()==='Trial'&&r.x>1700&&r.y>300&&r.y<600;}))) {
                    var trialRows=scaledRows(img,1630,330,230,160);rows=actOneMergeControlCropRows(rows,trialRows,1630,330);ocrMs=Date.now()-o0;
                }
                var climbing=rows.some(function(r){return r.text.trim()==='X' && r.x>1500 && r.y>990;}) && rows.some(function(r){return r.text.trim()==='Space' && r.x>1600 && r.y>990;});
                var dialogueReady=actOneDialogueReady(rows,choice), objectiveChanged=/objective updated|quest completed/i.test(text),aerialBoss=null,interactionOcrMs=0;
                var interactionScreen={objective:interactionObjective,world:!!(!trackQuest&&pos&&hp&&!auto&&!journal&&!bigMap&&!dialogueReady&&!(auto&&choice)),
                    position:!!pos,health:hp,auto:auto,journal:journal,bigMap:bigMap,dialogueReady:dialogueReady,choice:auto&&choice,
                    climbing:climbing,objectiveChanged:objectiveChanged,tutorialStep:tutorialStep};
                if(actOneShouldReadInteractionCrop(rows,interactionObjective,interactionScreen)) {
                    var interaction0=Date.now(),interactionLocal=scaledRows(img,1080,490,90,100);
                    var interactionF=actOneInteractionCropF(interactionLocal,1080,490);
                    if(interactionF) rows=rows.concat([interactionF]);
                    interactionOcrMs=Date.now()-interaction0;ocrMs=Date.now()-o0;
                }
                var aerialBossVisible=!pos&&actOneAerialBossLabels(rows)&&!auto&&!journal&&!bigMap&&!dialogueReady&&!(auto&&choice);
                if(aerialBossVisible) {
                    var aerialFraction=readAerialBossBar(img);
                    var aerialScreen={journal:journal,bigMap:bigMap,dialogueReady:dialogueReady,choice:auto&&choice,objectiveChanged:objectiveChanged,
                        lowHealth:!hp||hp.max<=0||hp.current>hp.max||hp.current/hp.max<0.6};
                    if(actOneAerialBossState(rows,null,hp,aerialScreen,aerialFraction)) aerialBoss={barFraction:aerialFraction};
                }
                var hud = { climbing:climbing, groundControls:actOneGroundControlEvidence(rows), enemyBars: combatObjective ? readEnemyBars(img, rows) : request&&/^falcon(Combat|AmberCombat|Ranged|Engage)$/.test(request.step) ? readEnemyBars(img,rows,4) : request&&/^wolf(Combat|Forward|Right|Left)/.test(request.step)&&hp&&!auto&&!journal&&!bigMap ? readEnemyBars(img,rows,5) : [], aerialBossVisible:aerialBossVisible,aerialBoss:aerialBoss, slimeTarget: tutorialStep === 'aimSlime' ? readSlime(img) : null, tutorialStep: tutorialStep, characterAcquired: acquired.length === 1 ? acquired[0].text.trim() : null, dialogueReady: dialogueReady, choice: auto && choice, journal: journal, bigMap: bigMap,
                    objectiveChanged: /objective updated|quest completed/i.test(text), health: hp, healthOcr: healthRows.map(function (r) { return r.text; }),
                    healthPct: hp && hp.max > 0 ? hp.current / hp.max : null,
                    lowHealth: !hp || hp.max <= 0 || hp.current > hp.max || hp.current / hp.max < 0.6,
                    world: !trackQuest && !!pos && !!hp && !auto && !journal && !bigMap,
                    interact: rows.some(function (r) { return (/^F$/.test(r.text.trim()) && r.x > 850 && r.y > 300 && r.y < 800) || (/^Teleport[- ]Waypoint$/i.test(r.text.trim()) && r.x>1100 && r.y>400 && r.y<700); }),
                    objectives: objectiveRows.map(function (r) { return r.text; }) };
                if (pos && request && request.objective === 'Investigate what Paimon has found') hud.worldMarker = readMarker(img);
                ready();
                lastObservation = { session: session, frameId: frame, timestamp: Date.now(), capturedAt: t0, screenshotPath: png, ocr: rows, map: trackQuest ? null : pos, mapDiagnostic:mapDiagnostic, hud: hud,
                    timings: { mapDiagnostic:mapDiagnostic, captureMs: captureMs, ocrMs: ocrMs, fullOcrMs: fullOcrMs, healthOcrMs: healthOcrMs, objectiveOcrMs: objectiveOcrMs, controlOcrMs:controlOcrMs, interactionOcrMs:interactionOcrMs, objectiveSource: reusedObjectiveRows ? 'fullFrame' : 'crop', pngWriteMs: pngMs, mapMs: mapMs, totalMs: Date.now() - t0 } };
                return lastObservation;
            } finally { dispose(img); }
        }
    };
}
