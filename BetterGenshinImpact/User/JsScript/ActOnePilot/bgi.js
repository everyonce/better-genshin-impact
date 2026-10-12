function actOneObjectiveRows(rows, expected) {
    // Close crystal approach also requires the cropped height/distance reading.
    if (!expected || expected === 'Investigate what Paimon has found') return null;
    var candidates = rows.filter(function (r) { return r.x >= 65 && r.x < 695 && r.y >= 230 && r.y < 315; });
    function normalized(s) { return String(s).toLowerCase().replace(/\s+/g, ''); }
    return candidates.some(function (r) { return normalized(r.text) === normalized(expected); }) ? candidates : null;
}
function actOneEnterGameAuthPrompt(rows) {
    return (rows || []).some(function (r) {
        var text = String(r.text || '').trim();
        return /\b(?:log\s*in|login|sign\s*in|password|verification\s*code|security\s*code|captcha|two[- ]factor|authentication|authenticating|enter your email|verify your account|account verification)\b/i.test(text);
    });
}
function actOneEnterGameUnknownUi(rows) {
    return (rows || []).some(function (r) {
        return /\b(?:update required|updating|confirm|cancel|retry|accept|agree|terms of service|privacy policy|network error|connection failed|maintenance)\b/i.test(String(r.text || '').trim());
    });
}
function actOneEnterGameTitleFrame(observation, now) {
    if (!observation || !Number.isFinite(observation.timestamp) || !Number.isFinite(now) || now < observation.timestamp || now - observation.timestamp > 1000 ||
        observation.map !== null || !observation.hud || observation.hud.world !== false || observation.hud.journal || observation.hud.bigMap ||
        observation.hud.dialogueReady || observation.hud.choice || actOneEnterGameAuthPrompt(observation.ocr) || actOneEnterGameUnknownUi(observation.ocr)) return null;
    var rows = observation.ocr || [];
    function exact(text, bounds) {
        return rows.filter(function (r) {
            return String(r.text || '').trim() === text && r.x >= bounds.x0 && r.x <= bounds.x1 && r.y >= bounds.y0 && r.y <= bounds.y1 &&
                r.width >= bounds.w0 && r.width <= bounds.w1 && r.height >= bounds.h0 && r.height <= bounds.h1;
        });
    }
    var start = exact('START GAME', {x0:700,x1:1200,y0:420,y1:560,w0:300,w1:500,h0:45,h1:90});
    // This verified title capture clips the initial S and returns a smaller
    // OCR box. Accept only that exact text and its measured title geometry.
    var clippedStart = exact('TART GAME', {x0:800,x1:840,y0:452,y1:492,w0:320,w1:360,h0:60,h1:78});
    start = start.concat(clippedStart);
    if (start.length !== 1) return null;
    var startX=start[0].x+start[0].width/2, startY=start[0].y+start[0].height/2;
    return Math.abs(startX-960)<=40 && startY>=475 && startY<=535 ? start[0] : null;
}
function actOneEnterGameTarget(observation, now) {
    if (!actOneEnterGameTitleFrame(observation, now)) return null;
    var rows = observation.ocr || [];
    function exact(text, bounds) {
        return rows.filter(function (r) {
            return String(r.text || '').trim() === text && r.x >= bounds.x0 && r.x <= bounds.x1 && r.y >= bounds.y0 && r.y <= bounds.y1 &&
                r.width >= bounds.w0 && r.width <= bounds.w1 && r.height >= bounds.h0 && r.height <= bounds.h1;
        });
    }
    var begin = exact('CLICK TO BEGIN', {x0:800,x1:1150,y0:540,y1:620,w0:150,w1:300,h0:20,h1:50});
    if (begin.length !== 1) return null;
    var beginX=begin[0].x+begin[0].width/2, beginY=begin[0].y+begin[0].height/2;
    if (Math.abs(beginX-960)>40 || beginY<570 || beginY>605) return null;
    return {x:Math.floor(begin[0].x+begin[0].width/2), y:Math.floor(begin[0].y+begin[0].height/2), label:'CLICK TO BEGIN'};
}
function actOneEnterWorldTarget(observation, now) {
    if (!observation || !Number.isFinite(observation.timestamp) || !Number.isFinite(now) || now < observation.timestamp || now-observation.timestamp>1000 ||
        observation.map!==null || !observation.hud || observation.hud.world!==false || observation.hud.health || observation.hud.journal ||
        observation.hud.bigMap || observation.hud.dialogueReady || observation.hud.choice || actOneEnterGameAuthPrompt(observation.ocr) ||
        actOneEnterGameUnknownUi(observation.ocr)) return null;
    var rows=observation.ocr||[];
    if(rows.some(function(r){var t=String(r.text||'').trim();return t==='START GAME'||t==='TART GAME'||t==='America';})) return null;
    var matches=rows.filter(function(r){return String(r.text||'').trim()==='CLICK TO BEGIN';});
    if(matches.length!==1) return null;
    var r=matches[0],x=Number(r.x),y=Number(r.y),w=Number(r.width),h=Number(r.height);
    if(x<800||x>1150||y<990||y>1040||w<150||w>300||h<20||h>50) return null;
    var cx=x+w/2,cy=y+h/2;
    if(Math.abs(cx-960)>45||cy<1005||cy>1035) return null;
    return {x:Math.floor(cx),y:Math.floor(cy),label:'CLICK TO BEGIN'};
}
function actOneEnterGameLoading(rows) {
    return (rows || []).some(function (r) { return /\b(?:loading|entering|preparing|connecting)\b/i.test(String(r.text || '').trim()); });
}
function actOneWindowedGameReady(observation, now) {
    var h=observation&&observation.hud,hp=h&&h.health,p=observation&&observation.map;
    return !!(observation&&Number.isFinite(observation.timestamp)&&Number.isFinite(now)&&now>=observation.timestamp&&now-observation.timestamp<=1000&&
        h&&h.world===true&&p&&p.map==='Teyvat'&&Number.isFinite(p.x)&&Number.isFinite(p.y)&&
        hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max>0&&hp.current>=0&&hp.current<=hp.max&&hp.current/hp.max>=0.6&&
        !h.lowHealth&&!h.journal&&!h.bigMap&&!h.dialogueReady&&!h.choice&&!h.objectiveChanged&&!h.climbing&&!h.tutorialStep&&
        !(h.enemyBars&&h.enemyBars.length));
}
function actOneWindowModeDecision(info, expectedSession) {
    if(!info||info.isRemoteDesktopSession!==true||!Number.isInteger(expectedSession)||expectedSession<=1||info.windowsSessionId!==expectedSession||
        info.isForeground!==true||info.isMinimized!==false||!info.desktop||!info.desktop.virtualBounds||
        info.desktop.virtualBounds.width!==2560||info.desktop.virtualBounds.height!==1440||!info.gameWindow) return null;
    var g=info.gameWindow;
    if(info.fillsDesktop===true&&g.clientWidth===2560&&g.clientHeight===1440) return 'toggle';
    if(info.fillsDesktop===false&&g.clientWidth===1920&&g.clientHeight===1080) return 'noop';
    return null;
}
async function actOneWindowedGameChord(ops) {
    var began=ops.now(),actionError=null,releaseError=null;
    try {
        ops.keyDown('VK_MENU');ops.checkStop();
        ops.keyDown('VK_RETURN');ops.checkStop();
        await ops.sleep(80);ops.checkStop();
    } catch(e) { actionError=e; }
    finally {
        try { ops.keyUp('VK_RETURN'); } catch(e) { releaseError=e; }
        try { ops.keyUp('VK_MENU'); } catch(e) { if(!releaseError)releaseError=e; }
    }
    if(actionError) throw actionError;
    if(releaseError) throw releaseError;
    return {holdMs:Math.max(80,ops.now()-began),keys:['VK_MENU','VK_RETURN']};
}
function actOneEnemyBarSize(w,h) { return w>=2 && w<=300 && h>=3 && h<=12 && w/h>=0.15; }
function actOneEnemyLevelToken(text,level) {
    var label=String(text||'').toUpperCase().replace(/\s+/g,'');
    if(level===5) return label.replace(/[.|]/g,'').replace(/^LV,([1-9])$/,'LV$1');
    return label.replace(/[.|]/g,'');
}
function actOneEnemyBarAnchored(bar, rows, level) {
    if (!bar || !Array.isArray(rows)) return false;
    return rows.some(function (r) {
        // The enemy level is displayed above its health bar. Normalize common
        // OCR confusions, but require level 1 so the player's Lv.3 label cannot anchor it.
        var label=actOneEnemyLevelToken(r.text,level);
        if (level===4 ? !/^LV4$/.test(label) : level===5 ? !/^LV5$/.test(label) : !/^LV[1IL]$/.test(label)) return false;
        var labelX=Number(r.x)+Number(r.width)/2, labelY=Number(r.y)+Number(r.height)/2;
        return Number.isFinite(labelX) && Number.isFinite(labelY) &&
            Math.abs(labelX-Number(bar.x))<=150 && Number(bar.y)-labelY>=8 && Number(bar.y)-labelY<=50;
    });
}
function actOneEnemyBarDiagnosticAnchored(bar,diagnostic,level) {
    if(!bar||!diagnostic||diagnostic.level!==level||!Array.isArray(diagnostic.localReads))return false;
    var matches=diagnostic.localReads.filter(function(read){
        var b=read&&read.bar;
        return b&&[b.x,b.y,b.width,b.height].every(Number.isFinite)&&
            Math.abs(b.x-bar.x)<=1&&Math.abs(b.y-bar.y)<=1&&Math.abs(b.width-bar.width)<=1&&Math.abs(b.height-bar.height)<=1;
    });
    return matches.length===1&&matches[0].anchored===true&&actOneEnemyBarAnchored(bar,matches[0].rows,level);
}
function actOneHealth(rows) {
    var match=rows.map(function(r){return r.text;}).join(' ').match(/\b(0|[1-9]\d{0,4})\s*\/\s*(0|[1-9]\d{0,4})\b/);
    if(!match) return null;
    var current=Number(match[1]),max=Number(match[2]);
    return max>0 && current<=max ? {current:current,max:max} : null;
}
function actOneFullHealthCandidate(rows) {
    var candidates=(rows||[]).filter(function(r){return r.x>=880&&r.x<=1050&&r.y>=990&&r.y<=1030&&/^\s*(?:0|[1-9]\d{0,4})\s*\/\s*(?:0|[1-9]\d{0,4})\s*$/.test(r.text)&&actOneHealth([r]);});
    return candidates.length===1?candidates[0]:null;
}
function actOneNumericHealthHalves(leftRows,rightRows) {
    var left=(leftRows||[]).filter(function(r){return /^\s*(?:0|[1-9]\d{0,4})\s*$/.test(String(r.text||''));});
    var right=(rightRows||[]).filter(function(r){return /^\s*(?:0|[1-9]\d{0,4})\s*$/.test(String(r.text||''));});
    if(left.length!==1||right.length!==1) return null;
    var candidate={text:left[0].text.trim()+'/'+right[0].text.trim()},parsed=actOneHealth([candidate]);
    return parsed?{row:candidate,health:parsed}:null;
}
function actOneCorroboratedFullHealth(rows,leftRows,rightRows) {
    var full=actOneFullHealthCandidate(rows),halves=actOneNumericHealthHalves(leftRows,rightRows);
    if(!full||!halves) return null;
    var parsed=actOneHealth([full]);
    return parsed&&parsed.current===halves.health.current&&parsed.max===halves.health.max?full:null;
}
function actOneFullHealthRows(rows, scaledRows) {
    var candidate=actOneFullHealthCandidate(rows);
    if(!candidate) return null;
    var full=actOneHealth([candidate]);
    if(full.current/full.max>=0.6) return [candidate];
    if(arguments.length<2) return null;
    var scaled=actOneHealth(scaledRows||[]);
    return scaled&&scaled.current===full.current&&scaled.max===full.max ? [candidate] : [];
}
function actOneMergeControlCropRows(fullRows, cropRows, x, y) {
    var mapped=(cropRows||[]).map(function(r){return {text:String(r.text||''),x:x+Number(r.x)/3,y:y+Number(r.y)/3,width:Number(r.width)/3,height:Number(r.height)/3};});
    var merged=(fullRows||[]).slice();
    mapped.forEach(function(crop){
        // Full-frame OCR and its enlarged control crop can read the same label.
        // Collapse only geometrically overlapping copies of the exact text;
        // separate controls and disagreeing reads remain ambiguous.
        var duplicate=merged.some(function(full){
            if(String(full.text||'').trim()!==crop.text.trim())return false;
            var values=[full.x,full.y,full.width,full.height,crop.x,crop.y,crop.width,crop.height];
            if(!values.every(Number.isFinite)||full.width<=0||full.height<=0||crop.width<=0||crop.height<=0)return false;
            if(Math.abs(full.x+full.width/2-crop.x-crop.width/2)>8||Math.abs(full.y+full.height/2-crop.y-crop.height/2)>8)return false;
            var w=Math.max(0,Math.min(full.x+full.width,crop.x+crop.width)-Math.max(full.x,crop.x)),
                h=Math.max(0,Math.min(full.y+full.height,crop.y+crop.height)-Math.max(full.y,crop.y));
            return w*h>=0.75*Math.min(full.width*full.height,crop.width*crop.height);
        });
        if(!duplicate)merged.push(crop);
    });
    return merged;
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
function actOneWolfReturnToEntranceReady(observation,now) {
    var h=observation&&observation.hud,hp=h&&h.health,p=observation&&observation.map,rows=observation&&observation.ocr||[];
    if(!observation||!Number.isFinite(observation.timestamp)||!Number.isFinite(now)||now<observation.timestamp||now-observation.timestamp>1000||
       !h||h.world!==true||!p||p.map!=='Teyvat'||!Number.isFinite(p.x)||!Number.isFinite(p.y)||
       !hp||!Number.isFinite(hp.current)||!Number.isFinite(hp.max)||hp.max<=0||hp.current<0||hp.current>hp.max||hp.current/hp.max<0.6||h.lowHealth||
       !Array.isArray(h.objectives)||h.objectives.indexOf('Enter the temple')<0||h.journal||h.bigMap||h.climbing||h.dialogueReady||h.choice||h.tutorialStep||h.objectiveChanged||h.auto||
       h.enemyBars&&h.enemyBars.length) return false;
    var roster=rows.filter(function(r){return r.x>1550&&r.y>300&&r.y<600;});
    var starter=roster.some(function(r){return r.text.trim()==='Lumina'||r.text.trim()==='Amber';});
    var wolfTrial=roster.some(function(r){return r.text.trim()==='Kaeya'||r.text.trim()==='Trial';})||rows.some(function(r){return r.text.trim()==='Trial';});
    return starter&&!wolfTrial;
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
function actOneShouldReadStatueInteractionCrop(rows,screen) {
    rows=rows||[];screen=screen||{};
    var statues=rows.filter(function(r){return String(r.text||'').trim()==='Statue of The Seven';});
    var target=statues.length===1&&Number(statues[0].x)>=1180&&Number(statues[0].x)<=1250&&
        Number(statues[0].y)>=500&&Number(statues[0].y)<=545&&Number(statues[0].width)>=250&&
        Number(statues[0].width)<=310&&Number(statues[0].height)>=20&&Number(statues[0].height)<=38;
    var existingF=rows.some(function(r){return String(r.text||'').trim()==='F'&&Number(r.x)>=1080&&Number(r.x)<=1170&&Number(r.y)>=490&&Number(r.y)<=590;});
    return !!(target&&screen.groundControls===true&&screen.auto===false&&screen.journal===false&&
        screen.bigMap===false&&screen.dialogueReady===false&&screen.choice===false&&screen.climbing===false&&
        screen.objectiveChanged===false&&!screen.tutorialStep&&!existingF);
}
function actOneInteractionCropF(cropRows,x,y) {
    var mapped=actOneMergeControlCropRows([],cropRows,x,y);
    var matches=mapped.filter(function(r){return String(r.text||'').trim()==='F'&&r.x>=1080&&r.x<=1170&&r.y>=490&&r.y<=590;});
    return matches.length===1?matches[0]:null;
}
function actOneWolfOpenDoorF(observation,now) {
    var h=observation&&observation.hud,rows=observation&&observation.ocr||[];
    if(!observation||!Number.isFinite(now)||!Number.isFinite(observation.timestamp)||now<observation.timestamp||now-observation.timestamp>1000||
       observation.map!==null||!h||h.world!==false||h.groundControls!==true||h.climbing!==false||h.auto!==false||h.journal!==false||
       h.bigMap!==false||h.dialogueReady!==false||h.choice!==false||h.objectiveChanged!==false||h.tutorialStep||h.loading===true||
       h.unknownHud===true||h.interact!==true||!Array.isArray(h.enemyBars)||h.enemyBars.length!==0||
       !h.health||!Number.isFinite(h.health.current)||h.health.max!==1427||h.health.current/h.health.max<0.6||h.health.current>h.health.max) return null;
    var kaeya=rows.filter(function(r){return String(r.text||'').trim()==='Kaeya'&&r.x>1550&&r.x<1800&&r.y>300&&r.y<600;}),
        trial=rows.filter(function(r){return String(r.text||'').trim()==='Trial'&&r.x>1700&&r.x<1900&&r.y>300&&r.y<600;}),
        doors=rows.filter(function(r){return String(r.text||'').trim()==='Open Door'&&r.x>=1150&&r.x<=1400&&r.y>=480&&r.y<=600&&r.width>=100&&r.width<=300&&r.height>=20&&r.height<=50;}),
        fkeys=rows.filter(function(r){return String(r.text||'').trim()==='F'&&r.x>=1050&&r.x<=1180&&r.y>=490&&r.y<=590&&r.width>=15&&r.width<=100&&r.height>=15&&r.height<=60;});
    if(kaeya.length!==1||trial.length!==1||doors.length!==1||fkeys.length!==1||
       Math.abs((fkeys[0].y+fkeys[0].height/2)-(doors[0].y+doors[0].height/2))>24)return null;
    return {label:'Open Door',prompt:doors[0],key:fkeys[0],x:Math.round(fkeys[0].x+fkeys[0].width/2),y:Math.round(fkeys[0].y+fkeys[0].height/2)};
}
function actOneShouldReadWolfOpenDoorCrop(rows,screen) {
    rows=rows||[];screen=screen||{};
    var doors=rows.filter(function(r){return String(r.text||'').trim()==='Open Door'&&r.x>=1150&&r.x<=1400&&r.y>=480&&r.y<=600&&r.width>=100&&r.width<=300&&r.height>=20&&r.height<=50;}),
        existingF=rows.some(function(r){return String(r.text||'').trim()==='F'&&r.x>=1050&&r.x<=1180&&r.y>=490&&r.y<=590;});
    var hp=screen.health;
    return !!(doors.length===1&&!existingF&&screen.world===false&&screen.groundControls===true&&screen.auto===false&&
        screen.journal===false&&screen.bigMap===false&&screen.dialogueReady===false&&screen.choice===false&&screen.climbing===false&&
        screen.objectiveChanged===false&&!screen.tutorialStep&&screen.loading!==true&&screen.unknownHud!==true&&
        hp&&Number.isFinite(hp.current)&&hp.max===1427&&hp.current/hp.max>=0.6&&hp.current<=hp.max&&
        rows.filter(function(r){return String(r.text||'').trim()==='Kaeya'&&r.x>1550&&r.x<1800&&r.y>300&&r.y<600;}).length===1&&
        rows.filter(function(r){return String(r.text||'').trim()==='Trial'&&r.x>1700&&r.x<1900&&r.y>300&&r.y<600;}).length===1);
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
function actOneWolfKaeyaSkillReady(o,now) {
    var hp=o&&o.hud&&o.hud.health;
    return actOneWolfDomainHud(o,now)&&!!hp&&hp.max===1427;
}
function actOneWolfChestReady(o,now) {
    var h=o&&o.hud,rows=o&&o.ocr||[];
    if(!actOneWolfKaeyaSkillReady(o,now)||h.auto||h.loading||h.unknownHud||h.objectiveChanged||h.interact!==true||(h.enemyBars||[]).length) return false;
    var keys=rows.filter(function(r){return String(r.text||'').trim()==='F'&&r.x>1000&&r.x<1180&&r.y>400&&r.y<720;}),
        chests=rows.filter(function(r){return String(r.text||'').trim()==='Common Chest'&&r.x>1150&&r.x<1600&&r.y>400&&r.y<720;});
    return keys.length===1&&chests.length===1;
}
function actOneWolfLootTarget(o,now,baseline) {
    var h=o&&o.hud,rows=o&&o.ocr||[];
    if(!actOneWolfKaeyaSkillReady(o,now)||h.auto||h.loading||h.unknownHud||h.objectiveChanged||h.interact!==true) return null;
    if(baseline&&(!Number.isFinite(baseline.current)||baseline.max!==1427||baseline.current-h.health.current>baseline.max*0.05)) return null;
    var keys=rows.filter(function(r){return String(r.text||'').trim()==='F'&&r.x>1000&&r.x<1180&&r.y>400&&r.y<720;});
    if(keys.length!==1) return null;
    var key=keys[0],selected=rows.filter(function(r){
        var text=String(r.text||'').trim().replace(/\u2019/g,"'");
        return /^(Fowl|Adventurer's Flower|Wanderer's Advice)$/.test(text)&&r.x>1150&&r.x<1600&&Math.abs(r.y-key.y)<=24;
    });
    return selected.length===1?String(selected[0].text).trim():null;
}
function actOneWolfDefensiveCryoReady(o,now) {
    var h=o&&o.hud,hp=h&&h.health;
    return actOneWolfDomainHud(o,now,0)&&!h.auto&&!h.loading&&!h.unknownHud&&!h.objectiveChanged&&
        !!hp&&hp.max===1427&&hp.current>0;
}
function actOneWolfAdvanceState(o,now,baseline) {
    var h=o&&o.hud,hp=h&&h.health;
    if(!actOneWolfDomainHud(o,now,0)) return {ok:false,reason:'Fresh valid Wolf trial HUD unavailable'};
    if(!hp||!Number.isFinite(hp.current)||!Number.isFinite(hp.max)||hp.max<=0) return {ok:false,reason:'Wolf health unavailable or nonnumeric'};
    if(hp.current/hp.max<0.6) return {ok:false,reason:'Wolf health below 60%'};
    if(baseline&&(baseline.current-hp.current>baseline.max*0.05)) return {ok:false,reason:'Wolf health dropped more than 5%'};
    if(h.interact) return {ok:false,reason:'Wolf interaction available'};
    if(h.enemyBars&&h.enemyBars.length) return {ok:false,reason:'Wolf enemy bars detected'};
    if(h.dialogueReady||h.choice) return {ok:false,reason:'Wolf dialogue or choice detected'};
    if(h.tutorialStep||h.objectiveChanged||h.auto||h.unknownHud) return {ok:false,reason:'Wolf tutorial or unknown HUD state'};
    if(h.groundControls!==true||h.climbing) return {ok:false,reason:'Wolf character is not confirmed grounded'};
    return {ok:true,health:{current:hp.current,max:hp.max}};
}
function actOneWolfPauseHud(o,now) {
    // Pausing remains available below the movement/combat health threshold.
    // Prefer full character proof; the separate fallback is pause-only and
    // requires the same fresh safe HUD plus exact Trial and captured max HP.
    return !!(actOneWolfDomainHud(o,now,0)&&o.hud.health.current>0||actOneWolfPauseOnlyHud(o,now));
}
function actOneWolfPauseOnlyHud(o,now) {
    var h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
    var grounded=!!(o&&Number.isFinite(now)&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&
      o.map===null&&h&&h.world===false&&h.groundControls===true&&!h.climbing&&!h.journal&&!h.bigMap&&
      !h.dialogueReady&&!h.choice&&!h.tutorialStep&&!h.auto&&!h.loading&&!h.unknownHud&&!h.objectiveChanged&&
      hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max===1427&&hp.current>0&&hp.current<=hp.max&&
      rows.some(function(r){return String(r.text||'').trim()==='Trial'&&r.x>1700&&r.x<1900&&r.y>300&&r.y<600;}));
    return grounded||actOneWolfAirPauseOnlyHud(o,now);
}
function actOneWolfBurstRecoveryBase(o,now,minRatio) {
    var h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
    minRatio=minRatio===undefined?0.3:minRatio;
    return !!(o&&Number.isFinite(now)&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&o.map===null&&
      h&&h.world===false&&h.groundControls===true&&h.climbing===false&&
      h.journal===false&&h.bigMap===false&&h.auto===false&&h.loading!==true&&h.unknownHud!==true&&
      h.objectiveChanged===false&&h.dialogueReady===false&&h.choice===false&&h.tutorialStep===null&&h.interact===false&&
      hp&&hp.max===1427&&Number.isFinite(hp.current)&&hp.current>0&&hp.current<=hp.max&&hp.current/hp.max>=minRatio&&
      !rows.some(function(r){return r.text&&(/^(Party Setup|Domain Entrance)$/.test(r.text.trim())||
        /\b(loading|entering|connecting|preparing)\b/i.test(r.text.trim()));}));
}
function actOneWolfBurstRecoveryActiveHud(o,now,minRatio) {
    if(!actOneWolfBurstRecoveryBase(o,now,minRatio)) return false;
    var rows=o.ocr||[],kaeya=rows.filter(function(r){return String(r.text||'').trim()==='Kaeya'&&r.x>1550&&r.y>300&&r.y<600;}),
      trial=rows.filter(function(r){return String(r.text||'').trim()==='Trial'&&r.x>1700&&r.y>300&&r.y<600;});
    return kaeya.length===1&&trial.length===1;
}
function actOneWolfBurstRecoveryQHud(o,now,minRatio) {
    if(!actOneWolfBurstRecoveryActiveHud(o,now,minRatio)) return false;
    var q=(o.ocr||[]).filter(function(r){return String(r.text||'').trim()==='Q'&&r.x>1500&&r.x<1880&&r.y>=990&&r.y<=1045;});
    return q.length===1;
}
function actOneWolfAirPauseOnlyHud(o,now) {
    var h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr;
    if(!o||!Number.isFinite(now)||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||
       o.map!==null||!h||h.world!==false||h.groundControls!==false||h.climbing!==false||
       h.auto||h.loading||h.unknownHud||h.objectiveChanged||
       h.dialogueReady!==false||h.choice!==false||h.journal!==false||h.bigMap!==false||h.tutorialStep!==null||
       !Array.isArray(rows)||
       !hp||!Number.isFinite(hp.current)||!Number.isFinite(hp.max)||hp.max!==1427||hp.current<=0||hp.current>hp.max) return false;
    var kaeya=rows.filter(function(r){return String(r.text||'').trim()==='Kaeya';});
    var trial=rows.filter(function(r){return String(r.text||'').trim()==='Trial';});
    var space=rows.filter(function(r){return String(r.text||'').trim()==='Space';});
    return kaeya.length===1&&kaeya[0].x>1550&&kaeya[0].x<1800&&kaeya[0].y>300&&kaeya[0].y<600&&
        trial.length===1&&trial[0].x>1700&&trial[0].x<1900&&trial[0].y>300&&trial[0].y<600&&
        space.length===1&&space[0].x>1600&&space[0].x<1880&&space[0].y>=990&&space[0].y<=1045;
}
function actOneWolfExitFlameProof(reports,active,session,now) {
    if(!Array.isArray(reports)||typeof session!=='string'||!session||!Number.isFinite(now)||!active||active.session!==session||
       !Number.isInteger(active.frameId)||!Number.isFinite(active.timestamp)||active.timestamp>now||
       !actOneWolfEntryProven(reports,session)) return null;
    var activeHud=active.hud||{},hp=activeHud.health,activeRows=active.ocr||[];
    if(active.map!==null||activeHud.world!==false||activeHud.groundControls!==true||activeHud.climbing!==false||
       activeHud.journal!==false||activeHud.bigMap!==false||activeHud.dialogueReady!==false||activeHud.choice!==false||
       activeHud.auto!==false||activeHud.loading===true||activeHud.unknownHud===true||activeHud.objectiveChanged===true||
       activeHud.tutorialStep||activeHud.interact!==false||!Array.isArray(activeHud.enemyBars)||activeHud.enemyBars.length!==0||
       !hp||hp.max!==1427||!Number.isFinite(hp.current)||hp.current/hp.max<0.6||hp.current>hp.max||
       activeRows.filter(function(r){return r&&String(r.text||'').trim()==='Kaeya'&&r.x>1550&&r.x<1800&&r.y>300&&r.y<600;}).length!==1||
       activeRows.filter(function(r){return r&&String(r.text||'').trim()==='Trial'&&r.x>1700&&r.x<1900&&r.y>300&&r.y<600;}).length!==1) return null;
    var moves=reports.filter(function(r){return r&&r.session===session&&r.mission==='questStep'&&r.status==='completed'&&
        r.details&&r.details.result&&r.details.result.step==='wolfForward'&&Number.isFinite(r.timestamp);});
    if(!moves.length)return null;
    moves.sort(function(a,b){return a.timestamp-b.timestamp;});
    var move=moves[moves.length-1],moveResult=move.details.result,moveEvents=move.details.inputEvents||[];
    if(moves.length>1&&moves[moves.length-2].timestamp===move.timestamp||moveResult.frameId!==active.frameId||
       move.frameId!==moveResult.frameId||!Number.isFinite(move.timestamp)||move.timestamp<active.timestamp||move.timestamp-active.timestamp>1000) return null;
    var forward=moveEvents.filter(function(e){return e&&e.type==='key'&&e.key==='VK_W'&&Number.isFinite(e.startedAt)&&Number.isFinite(e.finishedAt)&&
       Number.isInteger(e.durationMs)&&e.durationMs>0&&e.durationMs<=800;});
    if(forward.length!==1||forward[0].finishedAt>active.timestamp||active.timestamp-forward[0].finishedAt>1000)return null;
    var pauses=reports.filter(function(r){return r&&r.session===session&&r.mission==='questStep'&&r.status==='completed'&&r.details&&
        r.details.result&&r.details.result.step==='wolfPause'&&r.details.result.pauseVerified===true&&
        Number.isInteger(r.frameId)&&Number.isInteger(r.details.result.frameId)&&r.frameId===r.details.result.frameId&&
        r.frameId>active.frameId&&Number.isFinite(r.timestamp)&&r.timestamp>=move.timestamp;});
    if(pauses.length!==1)return null;
    var pause=pauses[0],pauseResult=pause.details.result,pauseEvents=pause.details.inputEvents||[];
    var escapes=pauseEvents.filter(function(e){return e&&e.type==='key'&&e.key==='VK_ESCAPE'&&Number.isFinite(e.startedAt)&&Number.isFinite(e.finishedAt);});
    if(escapes.length!==1||escapes[0].startedAt<active.timestamp||escapes[0].startedAt<forward[0].finishedAt||
       escapes[0].finishedAt<escapes[0].startedAt||pause.timestamp<escapes[0].finishedAt||pause.timestamp-escapes[0].finishedAt>1000)return null;
    var priorStateInput=false;
    reports.forEach(function(r){
        if(!r||r.session!==session||!Array.isArray(r.details&&r.details.inputEvents))return;
        r.details.inputEvents.forEach(function(e){
            if(!e||!Number.isFinite(e.startedAt)||e.startedAt<forward[0].startedAt)return;
            if(e===forward[0]||e===escapes[0]||['controllerRevision','observe','observation'].indexOf(e.type)>=0)return;
            priorStateInput=true;
        });
    });
    if(priorStateInput)return null;
    if(reports.some(function(r){return r&&r.session===session&&r.mission==='questStep'&&r.details&&Array.isArray(r.details.inputEvents)&&
        r.details.inputEvents.some(function(e){return e&&(e.type==='wolfExitFlameContinue'||e.type==='wolfExitFlameForward');});})) return null;
    return {movementId:move.id||null,activeFrameId:active.frameId,pauseId:pause.id||null,pauseFrameId:pauseResult.frameId,
        pauseTimestamp:pause.timestamp,health:{current:hp.current,max:hp.max},continuedAt:escapes[0].startedAt};
}
function actOneWolfWindCue(rows) {
    rows=rows||[];
    var allSpace=rows.filter(function(r){return String(r.text||'').trim()==='Space';}),
        allFirst=rows.filter(function(r){return String(r.text||'').trim()==='Tap Space twice in a wind current to';}),
        allSecond=rows.filter(function(r){return String(r.text||'').trim()==='ride it up';});
    var space=allSpace.filter(function(r){return r.x>=640&&r.x<=770&&r.y>=175&&r.y<=245&&r.width>=70&&r.width<=120&&r.height>=30&&r.height<=55;}),
        first=allFirst.filter(function(r){return r.x>=750&&r.x<=1280&&r.y>=170&&r.y<=245&&r.width>=400&&r.width<=520&&r.height>=20&&r.height<=45;}),
        second=allSecond.filter(function(r){return r.x>=900&&r.x<=1120&&r.y>=195&&r.y<=255&&r.width>=90&&r.width<=160&&r.height>=20&&r.height<=45;});
    return allSpace.length===1&&allFirst.length===1&&allSecond.length===1&&space.length===1&&first.length===1&&second.length===1;
}
function actOneWolfWindWitnessState(o,session) {
    var h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
    return !!(o&&o.session===session&&Number.isInteger(o.frameId)&&Number.isFinite(o.timestamp)&&o.map===null&&h&&h.world===false&&
       h.groundControls===true&&h.climbing===false&&h.auto===false&&h.journal===false&&h.bigMap===false&&h.dialogueReady===false&&
       h.choice===false&&h.objectiveChanged===false&&h.interact===false&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&
       hp&&Number.isFinite(hp.current)&&hp.max===1427&&hp.current/hp.max>=0.6&&hp.current<=hp.max&&actOneWolfWindCue(rows)&&
       rows.filter(function(r){return String(r.text||'').trim()==='Kaeya'&&r.x>1550&&r.x<1800&&r.y>300&&r.y<600;}).length===1&&
       rows.filter(function(r){return String(r.text||'').trim()==='Trial'&&r.x>1700&&r.x<1900&&r.y>300&&r.y<600;}).length===1);
}
function actOneWolfWindActiveState(o,now) {
    var h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
    return !!(o&&Number.isFinite(now)&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&o.map===null&&h&&
       h.world===false&&h.groundControls===true&&h.climbing===false&&h.auto===false&&h.journal===false&&h.bigMap===false&&
       h.dialogueReady===false&&h.choice===false&&!h.tutorialStep&&h.objectiveChanged===false&&h.interact===false&&
       !h.loading&&!h.unknownHud&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&hp&&
       Number.isFinite(hp.current)&&hp.max===1427&&hp.current/hp.max>=0.6&&hp.current<=hp.max&&
       rows.filter(function(r){return String(r.text||'').trim()==='Kaeya'&&r.x>1550&&r.x<1800&&r.y>300&&r.y<600;}).length===1&&
       rows.filter(function(r){return String(r.text||'').trim()==='Trial'&&r.x>1700&&r.x<1900&&r.y>300&&r.y<600;}).length===1&&
       !actOneDialogueReady(rows,h.choice));
}
function actOneWolfWindRideGroundState(o) {
    var h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
    return !!(o&&o.map===null&&h&&h.world===false&&h.groundControls===true&&h.climbing===false&&
       h.auto===false&&h.journal===false&&h.bigMap===false&&h.dialogueReady===false&&h.choice===false&&
       h.objectiveChanged===false&&!h.tutorialStep&&!h.loading&&!h.unknownHud&&h.interact===false&&
       Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&hp&&Number.isFinite(hp.current)&&hp.max===1427&&
       hp.current/hp.max>=0.6&&hp.current<=hp.max&&
       rows.filter(function(r){return String(r.text||'').trim()==='Kaeya'&&r.x>1550&&r.x<1800&&r.y>300&&r.y<600;}).length===1&&
       rows.filter(function(r){return String(r.text||'').trim()==='Trial'&&r.x>1700&&r.x<1900&&r.y>300&&r.y<600;}).length===1);
}
function actOneWolfGlideState(o,now) {
    if(!o||!Number.isFinite(now)||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000)return null;
    var h=o.hud,hp=h&&h.health;
    if(!hp||!Number.isFinite(hp.current)||hp.max!==1427||hp.current/hp.max<0.6||hp.current>hp.max)return null;
    if(actOneWolfAirPauseOnlyHud(o,now)&&h.interact===false&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0)return 'airborne';
    if(actOneWolfWindRideGroundState(o))return 'grounded';
    return null;
}
function actOneWolfWindRideProof(reports,active,session) {
    if(!Array.isArray(reports)||typeof session!=='string'||!session||!active||active.session!==session||
       !Number.isInteger(active.frameId)||!Number.isFinite(active.timestamp)||!actOneWolfWindRideGroundState(active)||!actOneWolfEntryProven(reports,session))return null;
    var terminal=reports.filter(function(r){return r&&r.session===session&&r.mission==='questStep'&&r.status==='completed'&&r.id&&r.details&&r.details.result;});
    var moves=terminal.filter(function(r){return r.details.result.step==='wolfAdvance'&&r.frameId===active.frameId&&r.details.result.frameId===active.frameId;});
    if(moves.length!==1)return null;
    var move=moves[0],ev=move.details.inputEvents||[],walks=ev.filter(function(e){return e&&e.type==='key'&&e.key==='VK_W';});
    if(!Number.isFinite(move.timestamp)||walks.length<1||walks.length>4||walks.some(function(e){return e.durationMs!==500||!Number.isFinite(e.startedAt)||!Number.isFinite(e.finishedAt)||e.finishedAt<e.startedAt;}))return null;
    if(ev.some(function(e){return e&&['controllerRevision','observe','observation'].indexOf(e.type)<0&&walks.indexOf(e)<0;}))return null;
    var pauses=terminal.filter(function(r){return r.details.result.step==='wolfPause'&&r.details.result.pauseVerified===true&&
        Number.isFinite(r.timestamp)&&Number.isInteger(r.frameId)&&r.frameId===r.details.result.frameId&&r.frameId>active.frameId;});
    if(pauses.length!==1)return null;
    var pause=pauses[0],escapes=(pause.details.inputEvents||[]).filter(function(e){return e&&e.type==='key'&&e.key==='VK_ESCAPE'&&
        e.durationMs===60&&Number.isFinite(e.startedAt)&&Number.isFinite(e.finishedAt)&&e.finishedAt>=e.startedAt;});
    if(escapes.length!==1)return null;
    var start=Math.min.apply(null,walks.map(function(e){return e.startedAt;})),lastWalkFinish=Math.max.apply(null,walks.map(function(e){return e.finishedAt;})),escape=escapes[0];
    if(escape.startedAt<start||escape.startedAt<lastWalkFinish||pause.timestamp<escape.finishedAt)return null;
    for(var i=0;i<reports.length;i++) {
        var r=reports[i];if(!r||r.session!==session||!Array.isArray(r.details&&r.details.inputEvents))continue;
        for(var j=0;j<r.details.inputEvents.length;j++) {
            var e=r.details.inputEvents[j];if(!e||!Number.isFinite(e.startedAt)||e.startedAt<start)continue;
            if(walks.indexOf(e)>=0||e===escape||['controllerRevision','observe','observation'].indexOf(e.type)>=0)continue;
            return null;
        }
    }
    return {activeFrameId:active.frameId,moveId:move.id,pauseId:pause.id,pauseFrameId:pause.frameId,health:{current:active.hud.health.current,max:1427}};
}
function actOneWolfWindWitnessProof(reports,witness,session,now) {
    if(!Array.isArray(reports)||typeof session!=='string'||!session||!Number.isFinite(now)||!actOneWolfEntryProven(reports,session)||
       !actOneWolfWindWitnessState(witness,session)||witness.timestamp>now)return null;
    var terminal=reports.filter(function(r){return r&&r.session===session&&['completed','stopped','failed'].indexOf(r.status)>=0&&r.id;});
    function uniqueTerminal(id) {return terminal.filter(function(r){return r.id===id;}).length===1;}
    var failed=terminal.filter(function(r){return r.mission==='questStep'&&r.status==='stopped'&&r.details&&r.details.result&&
       r.details.result.step==='wolfPause'&&r.details.result.pauseVerified===false&&r.frameId===witness.frameId&&
       r.details.result.frameId===witness.frameId&&Number.isFinite(r.timestamp)&&r.timestamp>=witness.timestamp;});
    if(failed.length!==1||!uniqueTerminal(failed[0].id))return null;
    var failedPause=failed[0],failedEvents=failedPause.details.inputEvents||[];
    var failedEscapes=failedEvents.filter(function(e){return e&&e.type==='key'&&e.key==='VK_ESCAPE'&&e.durationMs===60&&
        Number.isFinite(e.startedAt)&&Number.isFinite(e.finishedAt)&&e.finishedAt>=e.startedAt;});
    if(failedEscapes.length!==1)return null;
    var pauses=terminal.filter(function(r){return r.mission==='questStep'&&r.status==='completed'&&r.details&&r.details.result&&
        r.details.result.step==='wolfPause'&&r.details.result.pauseVerified===true&&Number.isInteger(r.frameId)&&
        r.frameId===r.details.result.frameId&&r.frameId>witness.frameId&&Number.isFinite(r.timestamp);});
    pauses.sort(function(a,b){return a.timestamp-b.timestamp;});
    if(!pauses.length||!pauses.every(function(r){return uniqueTerminal(r.id);}))return null;
    var latestPause=pauses[pauses.length-1];
    var allowedLooks=['wolfLookRight','wolfLookLeft','wolfLookDown','wolfLookUp'];
    for(var i=0;i<reports.length;i++) {
        var report=reports[i];
        if(!report||report.session!==session||!Array.isArray(report.details&&report.details.inputEvents))continue;
        for(var j=0;j<report.details.inputEvents.length;j++) {
            var e=report.details.inputEvents[j];
            if(!e) return null;
            if(['controllerRevision','observe','observation','wolfResumeProof'].indexOf(e.type)>=0)continue;
            if(!Number.isFinite(e.startedAt))return null;
            if(e.startedAt<witness.timestamp)continue;
            if(e.startedAt>now)return null;
            if(e.type==='key'&&e.key==='VK_ESCAPE'&&report.mission==='questStep'&&['completed','stopped'].indexOf(report.status)>=0&&
               report.details.result&&report.details.result.step==='wolfPause'&&e.durationMs===60&&Number.isFinite(e.finishedAt)&&e.finishedAt>=e.startedAt)continue;
            if(e.type==='wolfContinue'&&report.mission==='questStep'&&report.status==='completed'&&report.details.result&&
               report.details.result.step==='wolfContinue')continue;
            if(e.type==='rotate'&&report.mission==='questStep'&&report.status==='completed'&&report.details.result&&
               allowedLooks.indexOf(report.details.result.step)>=0&&Number.isFinite(e.dx)&&Number.isFinite(e.dy)&&
               Math.abs(e.dx)<=250&&Math.abs(e.dy)<=250&&(e.dx!==0||e.dy!==0))continue;
            return null;
        }
    }
    return {witnessFrameId:witness.frameId,failedPauseId:failedPause.id,latestPauseId:latestPause.id,
        latestPauseFrameId:latestPause.frameId,health:{current:witness.hud.health.current,max:witness.hud.health.max}};
}
function actOneWorldInventoryPauseReady(o,now) {
    var h=o&&o.hud,p=o&&o.map,hp=h&&h.health;
    if(!o||!Number.isFinite(o.timestamp)||!Number.isFinite(now)||now<o.timestamp||now-o.timestamp>1000||
        !p||p.map!=='Teyvat'||!Number.isFinite(p.x)||!Number.isFinite(p.y)||!h||h.groundControls!==true||
        h.auto||h.climbing||h.journal||h.bigMap||h.dialogueReady||h.choice||h.tutorialStep) return false;
    if(!hp) {
        // This fallback authorizes only opening the inventory to pause/heal.
        // Uncorroborated HP never authorizes movement or combat.
        var candidates=(o.ocr||[]).filter(function(r){return r.x>=880&&r.x<=1050&&r.y>=990&&r.y<=1030&&
            /^\s*(?:0|[1-9]\d{0,4})\s*\/\s*(?:0|[1-9]\d{0,4})\s*$/.test(r.text)&&actOneHealth([r]);});
        if(candidates.length!==1) return false;
        hp=actOneHealth(candidates);
    }
    return !!(hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.current>0&&hp.max>0&&hp.current<=hp.max);
}
function actOneWolfInfoKind(rows) {
    function exactCaption(row,text) { var value=String(row&&row.text||'').trim();return value===text||value===text+'.'; }
    var wet=rows.filter(function(r){return exactCaption(r,'If there is water around, opponents may become Wet');});
    var cryo=rows.filter(function(r){return exactCaption(r,'Cryo skills can freeze water, Hydro opponents, or opponents that are Wet');});
    var reaction=rows.filter(function(r){return exactCaption(r,'Utilize this elemental reaction to gain an advantage over your opponents');});
    var flamethrower=rows.filter(function(r){return exactCaption(r,"A flamethrower's core is what gives it the energy to shoot fire");});
    var hydroFirst=rows.filter(function(r){return exactCaption(r,'The blue stone in the center of the room is Hydro Amber. Breaking it will');});
    var hydroSecond=rows.filter(function(r){return exactCaption(r,'make it rain, making everything in its range Wet');});
    var disableFirst=rows.filter(function(r){return String(r&&r.text||'').trim()==="Use Cryo Skills to temporarily disable flamethrowers' cores and stop them";});
    var disableSecond=rows.filter(function(r){return exactCaption(r,'from shooting fire');});
    if(hydroFirst.length||hydroSecond.length) {
        if(hydroFirst.length!==1||hydroSecond.length!==1||wet.length||cryo.length||reaction.length||flamethrower.length||disableFirst.length||disableSecond.length)return null;
        var h1=hydroFirst[0],h2=hydroSecond[0];
        if(h1.x>410&&h1.x<465&&h1.y>770&&h1.y<805&&h1.width>1000&&h1.width<1090&&h1.height>28&&h1.height<45&&
           h2.x>580&&h2.x<640&&h2.y>805&&h2.y<850&&h2.width>650&&h2.width<750&&h2.height>22&&h2.height<40)return 'hydroAmber';
        return null;
    }
    if(disableFirst.length===1&&disableSecond.length===1&&!wet.length&&!cryo.length&&!reaction.length&&!flamethrower.length) {
        var d1=disableFirst[0],d2=disableSecond[0];
        if(d1.x>400&&d1.x<460&&d1.y>770&&d1.y<800&&d1.width>1040&&d1.width<1120&&d1.height>28&&d1.height<45&&
           d2.x>790&&d2.x<850&&d2.y>805&&d2.y<840&&d2.width>250&&d2.width<310&&d2.height>28&&d2.height<45) return 'disableFlamethrower';
    }
    if(flamethrower.length===1&&!wet.length&&!cryo.length&&!reaction.length&&!disableFirst.length&&!disableSecond.length) {
        var f=flamethrower[0];if(f.x>480&&f.x<525&&f.y>770&&f.y<800&&f.width>870&&f.width<940&&f.height>28&&f.height<45)return 'flamethrower';
    }
    if(wet.length===1&&!cryo.length&&!reaction.length&&!flamethrower.length&&!disableFirst.length&&!disableSecond.length) {
        var w=wet[0];if(w.x>535&&w.x<595&&w.y>760&&w.y<800&&w.width>750&&w.width<820&&w.height>35&&w.height<55)return 'wet';
    }
    if(!wet.length&&!flamethrower.length&&!disableFirst.length&&!disableSecond.length&&cryo.length===1&&reaction.length===1) {
        var c=cryo[0],r=reaction[0];
        if(c.x>390&&c.x<460&&c.y>770&&c.y<805&&c.width>1020&&c.width<1120&&c.height>25&&c.height<50&&
           r.x>395&&r.x<465&&r.y>805&&r.y<850&&r.width>1010&&r.width<1120&&r.height>30&&r.height<60)return 'freeze';
    }
    return null;
}
function actOneWolfInfoState(o,now) {
    var h=o&&o.hud,hp=h&&h.health,kind=actOneWolfInfoKind(o&&o.ocr||[]);
    if(!o||!Number.isFinite(now)||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!h||
       h.world!==false||h.journal||h.bigMap||h.dialogueReady||h.choice||!kind) return false;
    if(hp===null) {
        return h.groundControls===false&&h.climbing===false&&h.auto===false&&h.tutorialStep==='wolfInfo'&&
            h.loading!==true&&h.unknownHud!==true&&h.objectiveChanged!==true&&!actOneEnterGameLoading(o.ocr||[]);
    }
    if(!hp) return false;
    return !!(Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.current>0&&hp.max>0&&hp.current<=hp.max);
}
function actOneWolfApproachEnemyTarget(o,now) {
    var h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
    if(!actOneWolfDomainHud(o,now)||!h||h.world!==false||h.groundControls!==true||h.climbing!==false||h.auto!==false||
       h.journal!==false||h.bigMap!==false||h.dialogueReady!==false||h.choice!==false||h.objectiveChanged!==false||
       h.tutorialStep||h.loading===true||h.unknownHud===true||h.interact!==false||!hp||hp.max!==1427||
       !Array.isArray(h.enemyBars)||h.enemyBars.length!==1)return null;
    var bars=h.enemyBars.filter(function(b){return b&&Number.isFinite(b.x)&&Number.isFinite(b.y)&&Number.isFinite(b.width)&&Number.isFinite(b.height)&&
        b.width>0&&b.height>0&&actOneEnemyBarSize(b.width,b.height)&&b.x>=800&&b.x<=1300&&b.y>=250&&b.y<=650&&
        (actOneEnemyBarAnchored(b,rows,5)||actOneEnemyBarDiagnosticAnchored(b,h.enemyBarDiagnostic,5));});
    return bars.length===1?bars[0]:null;
}
function actOneWolfHydroApproachProof(reports,source,session) {
    if(!Array.isArray(reports)||typeof session!=='string'||!session||!source||source.session!==session||!Number.isInteger(source.frameId)||
       !Number.isFinite(source.timestamp)||source.map!==null||!source.hud||source.hud.world!==false||source.hud.tutorialStep!=='wolfInfo'||
       actOneWolfInfoKind(source.ocr||[])!=='hydroAmber'||!actOneWolfEntryProven(reports,session))return null;
    var terminal=reports.filter(function(r){return r&&r.session===session&&r.id&&['completed','stopped','failed'].indexOf(r.status)>=0;});
    var receipts=terminal.filter(function(r){return r.mission==='recover'&&r.status==='completed'&&Number.isFinite(r.timestamp)&&
        Array.isArray(r.details&&r.details.inputEvents)&&r.details.inputEvents.some(function(e){return e&&e.type==='wolfInfoRecoveryDismiss'&&
            e.frameId===source.frameId&&Number.isFinite(e.startedAt);});});
    if(receipts.length!==1||terminal.filter(function(r){return r.id===receipts[0].id;}).length!==1)return null;
    var receipt=receipts[0],dismissals=receipt.details.inputEvents.filter(function(e){return e&&e.type==='wolfInfoRecoveryDismiss'&&e.frameId===source.frameId&&Number.isFinite(e.startedAt);});
    if(dismissals.length!==1)return null;
    var dismissal=dismissals[0],pauses=terminal.filter(function(r){return r.mission==='questStep'&&r.status==='completed'&&r.details&&r.details.result&&
        r.details.result.step==='wolfPause'&&r.details.result.pauseVerified===true&&Number.isFinite(r.timestamp)&&Number.isInteger(r.frameId)&&
        r.frameId===r.details.result.frameId&&r.frameId>source.frameId;});
    var pauseCandidates=[];
    pauses.forEach(function(p){var escapes=(p.details.inputEvents||[]).filter(function(e){return e&&e.type==='key'&&e.key==='VK_ESCAPE'&&e.durationMs===60&&
            Number.isFinite(e.startedAt)&&Number.isFinite(e.finishedAt)&&e.finishedAt>=e.startedAt&&e.startedAt>=dismissal.startedAt&&p.timestamp>=e.finishedAt;});
        if(escapes.length===1)pauseCandidates.push({report:p,event:escapes[0]});});
    if(pauseCandidates.length!==1||dismissal.startedAt<source.timestamp||receipt.timestamp<dismissal.startedAt)return null;
    var pause=pauseCandidates[0],metadata=['controllerRevision','observe','observation','wolfResumeProof'];
    for(var i=0;i<reports.length;i++) {
        var report=reports[i];if(!report||report.session!==session)continue;
        var evs=report.details&&report.details.inputEvents;if(!Array.isArray(evs))continue;
        for(var j=0;j<evs.length;j++) {
            var e=evs[j];if(e===dismissal||e===pause.event||metadata.indexOf(e&&e.type)>=0)continue;
            var began=Number.isFinite(e&&e.startedAt)?e.startedAt:Number.isFinite(report.timestamp)?report.timestamp:null,
                ended=Number.isFinite(e&&e.finishedAt)?e.finishedAt:began;
            if(began===null) return null;
            if(ended>=dismissal.startedAt&&began<=pause.report.timestamp)return null;
            if(began>pause.event.finishedAt)return null;
        }
    }
    return {receiptId:receipt.id,hydroFrameId:source.frameId,dismissedAt:dismissal.startedAt,pauseId:pause.report.id,pauseFrameId:pause.report.frameId,
        pauseAt:pause.report.timestamp,escapeFinishedAt:pause.event.finishedAt};
}
function actOneWolfApproachHistory(reports,proof,session) {
    if(!Array.isArray(reports)||!proof||typeof session!=='string'||!session)return null;
    var terminal=reports.filter(function(r){return r&&r.session===session&&r.id&&['completed','stopped','failed'].indexOf(r.status)>=0;}),attempts=[];
    terminal.forEach(function(r){if(r.mission==='questStep'&&r.details&&r.details.result&&r.details.result.step==='wolfApproachEnemy')attempts.push(r);});
    var duplicateIds={};
    for(var i=0;i<attempts.length;i++){var id=attempts[i].id;if(duplicateIds[id])return null;duplicateIds[id]=true;}
    attempts.sort(function(a,b){return (a.timestamp||0)-(b.timestamp||0);});
    var continuations=[],moves=[],pauseEvents=[],canonicalEscapes=[],linkedMoveKeys=[];
    terminal.forEach(function(r){var evs=r.details&&r.details.inputEvents;if(!Array.isArray(evs))return;
        evs.forEach(function(e){if(e&&e.type==='wolfApproachEnemyContinue')continuations.push({report:r,event:e});
            else if(e&&e.type==='wolfApproachEnemyMove')moves.push({report:r,event:e});
            else if(r.details&&r.details.result&&r.details.result.step==='wolfPause'&&r.timestamp>proof.pauseAt&&e&&e.type==='key'&&e.key==='VK_ESCAPE') {
                var pauseEvent={report:r,event:e};pauseEvents.push(pauseEvent);canonicalEscapes.push(pauseEvent);
            }});});
    if(continuations.length!==attempts.length||moves.length>attempts.length)return null;
    var usedMoves=0,latestPauseFrame=proof.pauseFrameId,latestPauseAt=proof.pauseAt,previousPauseAt=proof.pauseAt;
    for(var a=0;a<attempts.length;a++) {
        var report=attempts[a],result=report.details.result,evs=report.details.inputEvents||[],cs=evs.filter(function(e){return e&&e.type==='wolfApproachEnemyContinue';}),
            ms=evs.filter(function(e){return e&&e.type==='wolfApproachEnemyMove';}),keyEvents=evs.filter(function(e){return e&&e.type==='key'&&e.key==='VK_W';});
        if(report.status!=='stopped'||result.continueAttempts!==1||result.moveAttempts!==ms.length||ms.length>1||cs.length!==1||
           !Number.isFinite(report.timestamp)||!Number.isInteger(report.frameId)||cs[0].hydroFrameId!==proof.hydroFrameId||cs[0].hydroReceiptId!==proof.receiptId||
           !Number.isFinite(cs[0].startedAt)||cs[0].startedAt<previousPauseAt||cs[0].frameId<latestPauseFrame||
           (evs.filter(function(e){return e&&e.type==='controllerRevision';}).length>1))return null;
        if(evs.some(function(e){return e!==cs[0]&&ms.indexOf(e)<0&&keyEvents.indexOf(e)<0&&e.type!=='controllerRevision';}))return null;
        continuations=continuations.filter(function(v){return v.report!==report||v.event!==cs[0];});
        var moveFinished=cs[0].startedAt;
        if(ms.length) {
            var move=ms[0];if(move.key!=='VK_W'||move.durationMs!==500||move.hydroFrameId!==proof.hydroFrameId||move.hydroReceiptId!==proof.receiptId||
                move.frameId<cs[0].frameId||!Number.isFinite(move.startedAt)||!Number.isFinite(move.finishedAt)||move.startedAt<cs[0].startedAt||
                move.finishedAt<move.startedAt||keyEvents.length!==1)return null;
            var keyEvent=keyEvents[0];
            if(keyEvent.durationMs!==500||keyEvent.frameId!==move.frameId||!Number.isFinite(keyEvent.startedAt)||!Number.isFinite(keyEvent.finishedAt)||
               keyEvent.startedAt<move.startedAt||keyEvent.startedAt-move.startedAt>100||keyEvent.finishedAt<keyEvent.startedAt||move.finishedAt<keyEvent.finishedAt)return null;
            linkedMoveKeys.push({report:report,event:keyEvent});
            usedMoves++;moveFinished=move.finishedAt;
        } else if(keyEvents.length)return null;
        var nextStart=Infinity;
        if(a+1<attempts.length) {
            var laterEvents=attempts[a+1].details.inputEvents||[],laterContinue=laterEvents.filter(function(e){return e&&e.type==='wolfApproachEnemyContinue';});
            if(laterContinue.length!==1||!Number.isFinite(laterContinue[0].startedAt))return null;
            nextStart=laterContinue[0].startedAt;
        }
        var following=pauseEvents.filter(function(p){return p.event.startedAt>=moveFinished&&p.event.startedAt<nextStart;});
        if(following.length!==1)return null;
        var pause=following[0],esc=pause.event,pr=pause.report,prResult=pr.details.result;
        if(pr.status!=='completed'||prResult.pauseVerified!==true||!Number.isFinite(pr.timestamp)||!Number.isInteger(pr.frameId)||pr.frameId!==prResult.frameId||
           !Number.isFinite(esc.finishedAt)||esc.durationMs!==60||esc.finishedAt<esc.startedAt||pr.timestamp<esc.finishedAt)return null;
        previousPauseAt=pr.timestamp;latestPauseAt=pr.timestamp;latestPauseFrame=pr.frameId;
        pauseEvents=pauseEvents.filter(function(p){return p!==pause;});
    }
    if(continuations.length||moves.length!==usedMoves||pauseEvents.length)return null;
    for(var r=0;r<reports.length;r++) {
        var rep=reports[r],inputs=rep&&rep.details&&rep.details.inputEvents;if(!rep||rep.session!==session||!Array.isArray(inputs))continue;
        for(var e=0;e<inputs.length;e++) {
            var item=inputs[e],when=Number.isFinite(item&&item.startedAt)?item.startedAt:Number.isFinite(rep.timestamp)?rep.timestamp:null;
            if(when===null||when<=proof.pauseAt)continue;
            if(item.type==='controllerRevision'||item.type==='observe'||item.type==='observation'||item.type==='wolfResumeProof')continue;
            if(item.type==='wolfApproachEnemyContinue'||item.type==='wolfApproachEnemyMove')continue;
            if(item.type==='key'&&item.key==='VK_W'&&linkedMoveKeys.some(function(k){return k.report===rep&&k.event===item;}))continue;
            if(item.type==='key'&&item.key==='VK_ESCAPE'&&item.durationMs===60&&canonicalEscapes.some(function(p){return p.report===rep&&p.event===item;}))continue;
            return null;
        }
    }
    return {attemptCount:attempts.length,moveCount:usedMoves,latestPauseFrameId:latestPauseFrame,latestPauseAt:latestPauseAt};
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
function actOneWolfInventoryContinueTarget(o,now) {
    return actOneFalconContinueTarget(o,now);
}
function actOneWolfResumeSeedTarget(o,now) {
    var h=o&&o.hud,rows=o&&o.ocr||[];
    if(!o||!Number.isFinite(o.timestamp)||!Number.isFinite(now)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!h||h.world!==false||
       h.auto!==false||h.dialogueReady||h.choice||h.climbing||h.loading||h.unknownHud||h.objectiveChanged) return null;
    var targets=rows.filter(function(r){return r.text.trim()==='Continue Challenge'&&r.x>750&&r.x<1000&&r.y>380&&r.y<460;}),
        leaves=rows.filter(function(r){return r.text.trim()==='Leave Domain?'&&r.x>750&&r.x<1000&&r.y>620&&r.y<700;});
    return targets.length===1&&leaves.length===1?targets[0]:null;
}
function actOneWolfRecoveryPauseTarget(o,now) {
    var h=o&&o.hud;
    if(!h||h.journal||h.bigMap||h.auto!==false||h.climbing===true||h.loading===true||h.unknownHud===true||h.objectiveChanged===true) return null;
    return actOneWolfResumeSeedTarget(o,now);
}
function actOneWolfRecoveryActiveHud(o,now) {
    var h=o&&o.hud,hp=h&&h.health;
    return !!(actOneWolfDomainHud(o,now,0)&&h.auto!==true&&h.loading!==true&&h.unknownHud!==true&&h.objectiveChanged!==true&&
        hp&&Number.isFinite(hp.current)&&hp.current>0);
}
function actOneWolfFoodInventoryReady(o,now) {
    var h=o&&o.hud,rows=o&&o.ocr||[];
    if(!o||!Number.isFinite(o.timestamp)||!Number.isFinite(now)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!h||h.world!==false||
       h.climbing||h.dialogueReady||h.choice||h.bigMap||h.loading||rows.some(function(r){return r.text.trim()==='Confirm';})) return false;
    var food=rows.filter(function(r){return r.text.trim()==='Food'&&r.x>120&&r.x<280&&r.y<70;});
    return food.length===1;
}
function actOneWolfFoodGridReady(o,now) {
    if(!actOneWolfFoodInventoryReady(o,now)) return false;
    var rows=o.ocr||[],sweet=rows.filter(function(r){return String(r.text||'').trim()==='Sweet Madame'&&r.x>1300&&r.x<1650&&r.y>110&&r.y<180;}),
        amount=rows.filter(function(r){return String(r.text||'').trim()==='Amount to use';}),
        use=rows.filter(function(r){return ['Use','Use Again'].indexOf(String(r.text||'').trim())>=0&&r.x>1600&&r.y>980;});
    return sweet.length===1&&amount.length===0&&use.length===1;
}
function actOneKnownSafeFoodBoundary(o,now) {
    var h=o&&o.hud,rows=o&&o.ocr||[];
    if(!o||!Number.isFinite(o.timestamp)||!Number.isFinite(now)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!h||h.world!==false||
       h.climbing||h.dialogueReady||h.choice||h.bigMap||h.loading) return false;
    function exact(text){return rows.filter(function(r){return String(r.text||'').trim()===text;});}
    var food=exact('Food').filter(function(r){return r.x>120&&r.x<230&&r.y>=0&&r.y<70;});
    var foodNames=['Sweet Madame','Teyvat Fried Egg'];
    var allItems=rows.filter(function(r){return foodNames.indexOf(String(r.text||'').trim())>=0;});
    var item=allItems.filter(function(r){return r.x>1300&&r.x<1650&&r.y>110&&r.y<180;});
    var headings=rows.filter(function(r){return ['Traveler','Kaeya'].indexOf(String(r.text||'').trim())>=0;});
    var heading=headings.filter(function(r){return r.x>800&&r.x<1000&&r.y>240&&r.y<320;});
    var amount=exact('Amount to use').filter(function(r){return r.x>600&&r.x<900&&r.y>590&&r.y<670;});
    var confirm=exact('Confirm').filter(function(r){return r.x>1100&&r.x<1260&&r.y>730&&r.y<800;});
    var cancel=exact('Cancel').filter(function(r){return r.x>650&&r.x<850&&r.y>730&&r.y<800;});
    return food.length===1&&allItems.length===1&&item.length===1&&headings.length===1&&heading.length===1&&exact('Amount to use').length===1&&amount.length===1&&confirm.length===1&&cancel.length<=1&&exact('Confirm').length===1&&exact('Cancel').length===cancel.length;
}
function actOneWolfKaeyaFoodTarget(o,now) {
    if(!actOneKnownSafeFoodBoundary(o,now)) return null;
    var rows=o.ocr||[],madame=rows.filter(function(r){return String(r.text||'').trim()==='Sweet Madame'&&r.x>1300&&r.x<1650&&r.y>110&&r.y<180;}),traveler=rows.filter(function(r){return String(r.text||'').trim()==='Traveler'&&r.x>800&&r.x<1000&&r.y>240&&r.y<320;});
    return madame.length===1&&traveler.length===1?{x:1115,y:440}:null;
}
function actOneWolfKaeyaFoodSelected(o,now) {
    if(!actOneKnownSafeFoodBoundary(o,now)) return false;
    return (o.ocr||[]).filter(function(r){return String(r.text||'').trim()==='Kaeya'&&r.x>800&&r.x<1000&&r.y>240&&r.y<320;}).length===1;
}
function actOneWolfFeedKaeyaTarget(o,now) {
    if(!o||!Number.isFinite(o.timestamp)||!Number.isFinite(now)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||
       !o.hud||o.hud.world!==false||o.hud.climbing||o.hud.dialogueReady||o.hud.choice||o.hud.bigMap||o.hud.loading||
       !actOneKnownSafeFoodBoundary(o,now)||!o.hud.foodQuantity||o.hud.foodQuantity.value!==1||o.hud.foodQuantity.frameId!==o.frameId) return null;
    var rows=o.ocr||[];
    var madame=rows.filter(function(r){return String(r.text||'').trim()==='Sweet Madame'&&r.x>1300&&r.x<1650&&r.y>110&&r.y<180;});
    var kaeya=rows.filter(function(r){return String(r.text||'').trim()==='Kaeya'&&r.x>800&&r.x<1000&&r.y>240&&r.y<320;});
    var confirm=rows.filter(function(r){return String(r.text||'').trim()==='Confirm'&&r.x>1100&&r.x<1260&&r.y>730&&r.y<800;});
    return madame.length===1&&kaeya.length===1&&confirm.length===1?
        {x:Math.round(confirm[0].x+confirm[0].width/2),y:Math.round(confirm[0].y+confirm[0].height/2)}:null;
}
function actOneWolfRecoveryFoodSafe(o,now) {
    var h=o&&o.hud,hp=h&&h.health;
    if(!o||!Number.isFinite(o.timestamp)||!Number.isFinite(now)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!h||h.world!==false||
       h.journal||h.bigMap||h.dialogueReady||h.choice||h.climbing||h.auto===true||h.loading===true||h.unknownHud===true||h.objectiveChanged===true||h.tutorialStep) return false;
    if(hp===undefined||hp!==null&&(!Number.isFinite(hp.current)||!Number.isFinite(hp.max)||hp.max<=0||hp.current<=0||hp.current>hp.max)) return false;
    return true;
}
function actOneWolfRecoveryFoodUseTarget(o,now) {
    if(!actOneWolfRecoveryFoodSafe(o,now)||!actOneWolfFoodGridReady(o,now)) return null;
    var rows=o.ocr||[],uses=rows.filter(function(r){return String(r.text||'').trim()==='Use'&&r.x>1600&&r.y>980;}),again=rows.filter(function(r){return String(r.text||'').trim()==='Use Again';});
    if(uses.length!==1||again.length!==0) return null;
    var x=Math.round(uses[0].x+uses[0].width/2),y=Math.round(uses[0].y+uses[0].height/2);
    return Number.isFinite(x)&&Number.isFinite(y)&&x>1600&&x<1900&&y>980&&y<1070?{x:x,y:y}:null;
}
function actOneValidateFalconResume(evidence,priorReports,currentReports,currentSession,rdpSession,observation,now) {
    var fields=['fromSession','toSession','priorEntryId','priorPauseId','verifiedAt','rdpSessionId'];
    if(!evidence||Object.keys(evidence).length!==fields.length||Object.keys(evidence).some(function(k){return fields.indexOf(k)<0;})||
       !/^[A-Za-z0-9_-]{1,80}$/.test(evidence.fromSession||'')||!/^[A-Za-z0-9_-]{1,80}$/.test(evidence.toSession||'')||
       evidence.fromSession===evidence.toSession||evidence.toSession!==currentSession||!Number.isInteger(rdpSession)||rdpSession<=0||evidence.rdpSessionId!==rdpSession||
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
function actOneWolfResumeGameInput(event) {
    return !!(event&&typeof event==='object'&&event.type&&event.type!=='controllerRevision'&&Number.isFinite(event.startedAt));
}
function actOneWolfPartyEntryChain(reports,partyEntry,session) {
    if(!Array.isArray(reports)||!partyEntry||!Array.isArray(partyEntry.details&&partyEntry.details.inputEvents)) return false;
    var completedParties=reports.filter(function(r){return r&&r.session===session&&r.mission==='questStep'&&r.status==='completed'&&r.details&&r.details.result&&r.details.result.step==='wolfPartyStart';});
    var partyResult=partyEntry.details.result||{},partyEvents=partyEntry.details.inputEvents.filter(function(e){return e&&e.type==='wolfPartyStart';});
    if(completedParties.length!==1||completedParties[0]!==partyEntry||partyEntry.session!==session||partyEntry.mission!=='questStep'||partyEntry.status!=='completed'||
       partyResult.step!=='wolfPartyStart'||partyResult.label!==undefined&&partyResult.label!=='Deep Within the Temple of the Wolf'||partyEvents.length!==1) return false;
    var party=partyEvents[0];
    if(party.label!==undefined&&party.label!=='Deep Within the Temple of the Wolf'||!Number.isFinite(party.startedAt)||!Number.isInteger(party.frameId)||party.frameId<0||
       !Number.isInteger(party.x)||party.x<1550||party.x>1850||!Number.isInteger(party.y)||party.y<950||party.y>1070||
       !Number.isFinite(partyEntry.timestamp)||party.startedAt>partyEntry.timestamp) return false;
    var starts=reports.filter(function(r){return r&&r.session===session&&r.mission==='questStep'&&r.status==='completed'&&r.details&&r.details.result&&r.details.result.step==='wolfStart';});
    if(starts.length!==1) return false;
    var startEntry=starts[0],startResult=startEntry.details.result,startEvents=startEntry.details.inputEvents;
    if(startResult.label!=='Deep Within the Temple of the Wolf'||!Array.isArray(startEvents)||!Number.isFinite(startEntry.timestamp)) return false;
    var domainStarts=startEvents.filter(function(e){return e&&e.type==='wolfDomainStart';});
    if(domainStarts.length!==1) return false;
    var start=domainStarts[0],startAt=start.startedAt,partyAt=party.startedAt;
    if(start.label!=='Deep Within the Temple of the Wolf'||!Number.isFinite(startAt)||!Number.isInteger(start.frameId)||start.frameId<0||
       !Number.isInteger(start.x)||start.x<1550||start.x>1900||!Number.isInteger(start.y)||start.y<950||start.y>1070||
       startAt>startEntry.timestamp||startEntry.timestamp>partyAt||startAt>=partyAt||party.frameId<=start.frameId||
       partyEntry.timestamp<partyAt||partyEntry.timestamp<startEntry.timestamp) return false;
    function readOnlyEvent(e) { return e&&['controllerRevision','observe','observation'].indexOf(e.type)>=0; }
    for(var i=0;i<reports.length;i++) {
        var report=reports[i];if(!report||report.session!==session) continue;
        var events=report.details&&report.details.inputEvents;
        if(!Array.isArray(events)) {
            if(report!==startEntry&&report!==partyEntry&&report.timestamp>=startAt&&report.timestamp<=partyAt&&
               report.id!==startEntry.id&&report.id!==partyEntry.id&&report.mission!=='observe') return false;
            continue;
        }
        for(var j=0;j<events.length;j++) {
            var event=events[j];
            if(event===start||event===party||readOnlyEvent(event)) continue;
            if(!event||typeof event.type!=='string'||!Number.isFinite(event.startedAt)) {
                if(Number.isFinite(report.timestamp)&&report.timestamp>=startAt&&report.timestamp<=partyAt) return false;
                continue;
            }
            if(event.startedAt>=startAt&&event.startedAt<=partyAt) return false;
        }
    }
    return true;
}
function actOneWolfResumeReceiptChain(reports,entry,identity,depth,visited) {
    if(depth>8||!entry||entry.status!=='completed'||entry.mission!=='questStep'||!entry.details||!entry.details.result||!Array.isArray(entry.details.inputEvents)) return false;
    var result=entry.details.result,events=entry.details.inputEvents.filter(function(e){return e&&e.type==='wolfResumeProof';});
    if(result.step!=='wolfResume'||result.verified!==true||result.toSession!==entry.session||events.length!==1||!Number.isFinite(entry.timestamp)) return false;
    var event=events[0],fields=['fromSession','toSession','priorEntryId','priorPauseId','betterGiProcessId','rdpSessionId','gameProcessId','verifiedAt'];
    for(var i=0;i<fields.length;i++) if(event[fields[i]]!==result[fields[i]]) return false;
    if(event.verified!==true||!Number.isFinite(result.verifiedAt)||!Number.isFinite(event.recordedAt)||result.verifiedAt>event.recordedAt||event.recordedAt>entry.timestamp||
       result.betterGiProcessId!==identity.betterGiProcessId||result.rdpSessionId!==identity.rdpSessionId||result.gameProcessId!==identity.gameProcessId||
       !/^[A-Za-z0-9_-]{1,80}$/.test(result.fromSession||'')||result.fromSession===entry.session||
       !/^[A-Za-z0-9_-]{1,100}$/.test(result.priorEntryId||'')||!/^[A-Za-z0-9_-]{1,100}$/.test(result.priorPauseId||'')||result.priorEntryId===result.priorPauseId) return false;
    var key=entry.session+'/'+entry.id;
    if(visited[key]) return false;
    visited[key]=true;
    var parent=reports.filter(function(r){return r&&r.session===result.fromSession&&r.id===result.priorEntryId&&r.mission==='questStep'&&r.status!=='started'&&r.status!=='running';});
    var pause=reports.filter(function(r){return r&&r.session===result.fromSession&&r.id===result.priorPauseId&&r.mission==='questStep'&&r.status!=='started'&&r.status!=='running';});
    var priorEscapes=pause.length===1&&pause[0].details&&Array.isArray(pause[0].details.inputEvents)?pause[0].details.inputEvents.filter(function(e){return e&&e.type==='key'&&e.key==='VK_ESCAPE'&&Number.isFinite(e.startedAt);}):[];
    if(parent.length!==1||pause.length!==1||priorEscapes.length!==1||priorEscapes[0].startedAt>result.verifiedAt||!Number.isFinite(pause[0].timestamp)||pause[0].timestamp>result.verifiedAt||
       !actOneWolfEntryPauseChain(reports,parent[0],pause[0],identity,depth+1,visited)) return false;
    return true;
}
function actOneWolfEntryPauseChain(reports,entry,pause,identity,depth,visited) {
    var pauseResult=pause&&pause.details&&pause.details.result;
    var combatPause=pauseResult&&pauseResult.step==='wolfCombat'&&pause.status==='stopped'&&pauseResult.pauseVerified===true;
    if(depth>8||!entry||!pause||entry.session!==pause.session||pause.status!=='completed'&&pause.status!=='stopped'||
       !pause.details||!pauseResult||pauseResult.step!=='wolfPause'&&!combatPause||!Number.isFinite(entry.timestamp)||!Number.isFinite(pause.timestamp)||
       pause.timestamp<entry.timestamp||!Array.isArray(pause.details.inputEvents)) return false;
    var escapes=pause.details.inputEvents.filter(function(e){return e&&e.type==='key'&&e.key==='VK_ESCAPE'&&Number.isFinite(e.startedAt);});
    if(escapes.length!==1) return false;
    var escape=escapes[0];
    if(combatPause&&pause.timestamp<escape.startedAt) return false;
    for(var i=0;i<reports.length;i++) {
        var report=reports[i],events=report&&report.details&&report.details.inputEvents;
        if(!report||report.session!==pause.session||!Array.isArray(events)) continue;
        for(var j=0;j<events.length;j++) {
            var e=events[j];if(report===pause&&e===escape) continue;
            if(actOneWolfResumeGameInput(e)&&e.startedAt>=escape.startedAt) return false;
        }
    }
    if(entry.details&&entry.details.result&&entry.details.result.step==='wolfPartyStart')
        return entry.status==='completed'&&actOneWolfPartyEntryChain(reports,entry,entry.session);
    return actOneWolfResumeReceiptChain(reports,entry,identity,depth,visited);
}
function actOneValidateWolfResume(evidence,priorReports,currentReports,currentSession,rdpSession,observation,now,windowInfo) {
    var fields=['fromSession','toSession','priorEntryId','priorPauseId','betterGiProcessId','rdpSessionId','gameProcessId','verifiedAt'];
    if(!evidence||Object.keys(evidence).length!==fields.length||Object.keys(evidence).some(function(k){return fields.indexOf(k)<0;})||
       !/^[A-Za-z0-9_-]{1,80}$/.test(evidence.fromSession||'')||!/^[A-Za-z0-9_-]{1,80}$/.test(evidence.toSession||'')||
       evidence.fromSession===evidence.toSession||evidence.toSession!==currentSession||
       typeof evidence.priorEntryId!=='string'||typeof evidence.priorPauseId!=='string'||!evidence.priorEntryId||!evidence.priorPauseId||evidence.priorEntryId===evidence.priorPauseId||
       !Number.isInteger(evidence.betterGiProcessId)||evidence.betterGiProcessId<=0||!Number.isInteger(evidence.gameProcessId)||evidence.gameProcessId<=0||
       !Number.isInteger(evidence.rdpSessionId)||!Number.isInteger(rdpSession)||rdpSession<=1||evidence.rdpSessionId!==rdpSession||
       !Number.isFinite(evidence.verifiedAt)||evidence.verifiedAt>now||now-evidence.verifiedAt>30000||
       !Array.isArray(priorReports)||!Array.isArray(currentReports)||!actOneFalconContinueTarget(observation,now)||!windowInfo||
       windowInfo.betterGiProcessId!==evidence.betterGiProcessId||windowInfo.gameProcessId!==evidence.gameProcessId||
       windowInfo.windowsSessionId!==rdpSession||windowInfo.isRemoteDesktopSession!==true||windowInfo.isForeground!==true||windowInfo.isMinimized!==false) return null;
    function one(id) { var found=priorReports.filter(function(r){return r&&r.id===id&&r.session===evidence.fromSession&&r.mission==='questStep'&&r.status!=='started'&&r.status!=='running';});return found.length===1?found[0]:null; }
    function step(r) { return r&&r.details&&r.details.result&&r.details.result.step; }
    var entry=one(evidence.priorEntryId),pause=one(evidence.priorPauseId);
    if(!entry||!pause||!actOneWolfEntryPauseChain(priorReports,entry,pause,{betterGiProcessId:evidence.betterGiProcessId,rdpSessionId:evidence.rdpSessionId,gameProcessId:evidence.gameProcessId},0,{})||
       pause.timestamp>evidence.verifiedAt||!evidence.priorPauseId) return null;
    var escapes=pause.details.inputEvents.filter(function(e){return e&&e.type==='key'&&e.key==='VK_ESCAPE'&&Number.isFinite(e.startedAt);});
    if(escapes[0].startedAt>evidence.verifiedAt) return null;
    for(var i=0;i<priorReports.length;i++) {
        var report=priorReports[i],events=report&&report.details&&report.details.inputEvents;
        if(!Array.isArray(events)) continue;
        for(var j=0;j<events.length;j++) {
            var e=events[j];if(report===pause&&e===escapes[0]) continue;
            if(actOneWolfResumeGameInput(e)&&e.startedAt>=escapes[0].startedAt) return null;
        }
    }
    if(currentReports.some(function(r){return r&&r.session===currentSession&&r.mission==='questStep'&&r.details&&r.details.inputEvents&&
        r.details.inputEvents.some(function(e){return e&&e.type==='wolfResumeProof';});})) return null;
    return {verified:true,fromSession:evidence.fromSession,toSession:evidence.toSession,priorEntryId:entry.id,priorPauseId:pause.id,
        betterGiProcessId:evidence.betterGiProcessId,rdpSessionId:evidence.rdpSessionId,gameProcessId:evidence.gameProcessId,verifiedAt:evidence.verifiedAt};
}
function actOneWolfEntryProof(reports,session) {
    if(!Array.isArray(reports)||typeof session!=='string'||!session) return {verified:false,reason:'invalid-history-or-session'};
    var parties=reports.filter(function(r){return r&&r.session===session&&r.mission==='questStep'&&r.status==='completed'&&r.details&&r.details.result&&r.details.result.step==='wolfPartyStart';});
    if(parties.length>1) return {verified:false,reason:'duplicate-completed-party-start'};
    if(parties.length===1) {
        var party=parties[0],result=party.details.result,events=party.details.inputEvents||[],partyEvents=events.filter(function(e){return e&&e.type==='wolfPartyStart';});
        if(result.label!==undefined&&result.label!=='Deep Within the Temple of the Wolf') return {verified:false,reason:'party-result-label-mismatch'};
        if(partyEvents.length!==1) return {verified:false,reason:'party-start-event-missing-or-ambiguous'};
        if(partyEvents[0].label==='Deep Within the Temple of the Wolf'&&Number.isFinite(partyEvents[0].startedAt))
            return {verified:true,reason:'labeled-wolf-party-start',entryId:party.id||null};
        if(partyEvents[0].label!==undefined) return {verified:false,reason:'party-event-label-mismatch'};
        return actOneWolfPartyEntryChain(reports,party,session)?
            {verified:true,reason:'legacy-party-start-linked-to-exact-wolf-entrance',entryId:party.id||null}:
            {verified:false,reason:'legacy-party-start-chain-invalid'};
    }
    var resumes=reports.filter(function(r){return r&&r.session===session&&r.mission==='questStep'&&r.status==='completed'&&r.details&&r.details.result&&r.details.result.step==='wolfResume';});
    if(resumes.length>1) return {verified:false,reason:'duplicate-wolf-resume-proof'};
    if(resumes.length===1) {
        var resume=resumes[0],result=resume.details.result,events=resume.details.inputEvents||[];
        if(result.verified===true&&result.toSession===session&&events.some(function(e){return e&&e.type==='wolfResumeProof'&&e.verified===true&&e.toSession===session&&
            e.fromSession===result.fromSession&&e.priorEntryId===result.priorEntryId&&e.priorPauseId===result.priorPauseId&&
            e.betterGiProcessId===result.betterGiProcessId&&e.rdpSessionId===result.rdpSessionId&&e.gameProcessId===result.gameProcessId&&e.verifiedAt===result.verifiedAt;}))
            return {verified:true,reason:'verified-wolf-resume',entryId:resume.id||null};
        return {verified:false,reason:'wolf-resume-proof-invalid'};
    }
    return {verified:false,reason:'no-completed-wolf-entry'};
}
function actOneWolfEntryProven(reports,session) {
    return actOneWolfEntryProof(reports,session).verified;
}
function actOneWolfLookDelta(step,amount,hasAmount) {
    var directions={wolfLookRight:[1,0],wolfLookLeft:[-1,0],wolfLookDown:[0,1],wolfLookUp:[0,-1]};
    var direction=directions[step];
    if(!direction) {
        if(hasAmount) throw new Error('lookAmount is only valid for Wolf look steps');
        return null;
    }
    if(!hasAmount) amount=250;
    if(!Number.isInteger(amount)||amount<16||amount>250) throw new Error('Invalid Wolf lookAmount; expected an integer from 16 to 250');
    return {dx:direction[0]*amount,dy:direction[1]*amount};
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
if (typeof module !== 'undefined' && module.exports) module.exports = { enterGameTitleFrame:actOneEnterGameTitleFrame, enterGameTarget:actOneEnterGameTarget, enterWorldTarget:actOneEnterWorldTarget, enterGameAuthPrompt:actOneEnterGameAuthPrompt, enterGameUnknownUi:actOneEnterGameUnknownUi, enterGameLoading:actOneEnterGameLoading, windowedGameReady:actOneWindowedGameReady, windowModeDecision:actOneWindowModeDecision, windowedGameChord:actOneWindowedGameChord, objectiveRows: actOneObjectiveRows, enemyBarSize:actOneEnemyBarSize, enemyBarAnchored:actOneEnemyBarAnchored, health:actOneHealth, fullHealthRows:actOneFullHealthRows, corroboratedFullHealth:actOneCorroboratedFullHealth, numericHealthHalves:actOneNumericHealthHalves, dialogueReady:actOneDialogueReady, navigateQuestState:actOneNavigateQuestState, navigateQuestButton:actOneNavigateQuestButton, trackQuestState:actOneTrackQuestState, trackQuestTarget:actOneTrackQuestTarget, altClick:actOneAltClick, mergeControlCropRows:actOneMergeControlCropRows, groundControlEvidence:actOneGroundControlEvidence, needsControlCrop:actOneNeedsControlCrop, glideForwardState:actOneGlideForwardState, glideForward:actOneGlideForward, glideOpenState:actOneGlideOpenState, glideOpen:actOneGlideOpen, aerialBossLabels:actOneAerialBossLabels, aerialBossState:actOneAerialBossState, falconWaypointTarget:actOneFalconWaypointTarget, falconWaypointReady:actOneFalconWaypointReady, fullMapState:actOneFullMapState, navigationMapAnchor:actOneNavigationMapAnchor, acceptNavigationPosition:actOneAcceptNavigationPosition, namedInteractionVisible:actOneNamedInteractionVisible, resolveInteractionObjective:actOneResolveInteractionObjective, shouldReadInteractionCrop:actOneShouldReadInteractionCrop, shouldReadStatueInteractionCrop:actOneShouldReadStatueInteractionCrop, interactionCropF:actOneInteractionCropF, shouldReadWolfOpenDoorCrop:actOneShouldReadWolfOpenDoorCrop, wolfOpenDoorF:actOneWolfOpenDoorF, falconStartTarget:actOneFalconStartTarget, falconPartyTarget:actOneFalconPartyTarget, wolfPartyTarget:actOneWolfPartyTarget, wolfEntryHud:actOneWolfEntryHud, wolfDomainHud:actOneWolfDomainHud, wolfPauseOnlyHud:actOneWolfPauseOnlyHud, wolfExitFlameProof:actOneWolfExitFlameProof, wolfKaeyaSkillReady:actOneWolfKaeyaSkillReady, wolfDefensiveCryoReady:actOneWolfDefensiveCryoReady, wolfAdvanceState:actOneWolfAdvanceState, wolfReturnToEntranceReady:actOneWolfReturnToEntranceReady, falconDomainHud:actOneFalconDomainHud, falconAimHud:actOneFalconAimHud, falconPyroInfo:actOneFalconPyroInfo, falconContinueTarget:actOneFalconContinueTarget, wolfInventoryContinueTarget:actOneWolfInventoryContinueTarget, wolfFoodInventoryReady:actOneWolfFoodInventoryReady, wolfFoodGridReady:actOneWolfFoodGridReady, knownSafeFoodBoundary:actOneKnownSafeFoodBoundary, wolfKaeyaFoodTarget:actOneWolfKaeyaFoodTarget, wolfKaeyaFoodSelected:actOneWolfKaeyaFoodSelected, wolfFeedKaeyaTarget:actOneWolfFeedKaeyaTarget, validateFalconResume:actOneValidateFalconResume, validateWolfResume:actOneValidateWolfResume, wolfEntryProven:actOneWolfEntryProven, wolfEntryProof:actOneWolfEntryProof, wolfLookDelta:actOneWolfLookDelta };
if (typeof module !== 'undefined' && module.exports) Object.assign(module.exports,{wolfAirPauseOnlyHud:actOneWolfAirPauseOnlyHud,wolfWindRideGroundState:actOneWolfWindRideGroundState,wolfWindRideProof:actOneWolfWindRideProof,wolfGlideState:actOneWolfGlideState});

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
if (typeof module !== 'undefined' && module.exports) Object.assign(module.exports,{wolfInfoState:actOneWolfInfoState,wolfInfoKind:actOneWolfInfoKind});
if (typeof module !== 'undefined' && module.exports) Object.assign(module.exports,{wolfRecoveryPauseTarget:actOneWolfRecoveryPauseTarget,wolfRecoveryActiveHud:actOneWolfRecoveryActiveHud});
if (typeof module !== 'undefined' && module.exports) Object.assign(module.exports,{wolfRecoveryFoodSafe:actOneWolfRecoveryFoodSafe,wolfRecoveryFoodUseTarget:actOneWolfRecoveryFoodUseTarget});
if (typeof module !== 'undefined' && module.exports) Object.assign(module.exports,{wolfChestReady:actOneWolfChestReady});
if (typeof module !== 'undefined' && module.exports) Object.assign(module.exports,{wolfLootTarget:actOneWolfLootTarget});
if (typeof module !== 'undefined' && module.exports) Object.assign(module.exports,{wolfWindCue:actOneWolfWindCue,wolfWindWitnessState:actOneWolfWindWitnessState,wolfWindWitnessProof:actOneWolfWindWitnessProof,wolfWindActiveState:actOneWolfWindActiveState});
if (typeof module !== 'undefined' && module.exports) Object.assign(module.exports,{wolfApproachEnemyTarget:actOneWolfApproachEnemyTarget,wolfHydroApproachProof:actOneWolfHydroApproachProof,wolfApproachHistory:actOneWolfApproachHistory});

function createActOneAdapter(sessionId) {
    var expectedSession = Number(sessionId), held = null, request = null, events = [], lastObservation = null, navLastAcceptedPosition = null, heartbeat = null, focusRecoveryAttempted = false, wolfInfoAttempted = false, wolfContinueAttempted = false, wolfInventoryContinueAttempted = false, wolfInventoryOpenAttempted = false, wolfKaeyaFoodAttempted = false, wolfFeedKaeyaAttempted = false, wolfRecoveryFoodUseAttempted=false, wolfRecoveryFoodSelectAttempted=false, wolfRecoveryFoodFeedAttempted=false, wolfRecoveryFoodCloseAttempted=false, wolfExitFlameAttempted=false, wolfWindContinueAttempted=false, wolfWindSpaceAttempted=false, wolfWindRideContinueAttempted=false, wolfWindRideSpaceAttempted=false, wolfGlideContinueAttempted=false, wolfGlideMoves=0, wolfGlideLastMoveFrame=null, wolfGlideBaseline=null, wolfDefensiveCryoAttempted = false, wolfAimCryoAttempted = false, wolfCloseFoodAttempted = false, wolfCloseFoodCompletedAt = null, wolfCloseFoodLookAttempted = false, wolfCloseFoodForwardAttempted = false, wolfCloseFoodSkillAttempted = false, wolfTurretSkillAttempted = false, wolfTurretForwardAttempted = false, wolfTurretSkillFinishedAt = null, wolfTurretBaseline = null, wolfConsoleContinueAttempted=false, wolfConsoleInteractAttempted=false, wolfApproachContinueAttempted=false, wolfApproachMoveAttempted=false, wolfApproachHydroFrame=null, wolfApproachHydroReceiptId=null, wolfCombatSeekForwards=0,wolfCombatSeekTurns=0,wolfCombatSeekFrames=[],wolfBurstContinueAttempted=false,wolfBurstQAttempted=false,wolfBurstPauseAttempted=false,ocrPrimitiveMs=0,ocrReadCount=0;
    function dispose(v) { if (v && typeof v.dispose === 'function') v.dispose(); }
    function sessionReady() {
        if (genshin.isRemoteDesktopSession !== true || !Number.isInteger(expectedSession) || expectedSession <= 1 || Number(genshin.windowsSessionId) !== expectedSession) throw new Error('The pinned verified RDP child session above Windows session 1 is required');
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
    function wolfWindEvidence(o) {
        if(!request||!request.session||!/^[A-Za-z0-9_-]{1,80}$/.test(request.session))return null;
        var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
        var witnessReports=reports.filter(function(r){return r&&r.session===request.session&&r.mission==='questStep'&&r.status==='stopped'&&
            r.details&&r.details.result&&r.details.result.step==='wolfPause'&&r.details.result.pauseVerified===false&&
            Number.isInteger(r.frameId)&&r.frameId===r.details.result.frameId;});
        if(witnessReports.length!==1)return null;
        var frame=witnessReports[0].frameId,path='observations/'+request.session+'/frame-'+String(frame).padStart(4,'0')+'.json';
        if(!file.isExists(path))return null;
        var witness=JSON.parse(file.readTextSync(path));
        var proof=actOneWolfWindWitnessProof(reports,witness,request.session,Date.now());
        if(!proof||!o||o.frameId<proof.latestPauseFrameId)return null;
        return {proof:proof,witness:witness,reports:reports};
    }
    function wolfWindRideCheckpoint(reports) {
        if(!request||!request.session||!/^[A-Za-z0-9_-]{1,80}$/.test(request.session))return null;
        reports=reports||JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
        var moves=reports.filter(function(r){return r&&r.session===request.session&&r.mission==='questStep'&&r.status==='completed'&&
            r.details&&r.details.result&&r.details.result.step==='wolfAdvance'&&Number.isInteger(r.details.result.frameId)&&r.frameId===r.details.result.frameId;});
        if(!moves.length)return null;
        moves.sort(function(a,b){return Number(a.timestamp)-Number(b.timestamp);});
        var move=moves[moves.length-1],frame=move.frameId,path='observations/'+request.session+'/frame-'+String(frame).padStart(4,'0')+'.json';
        if(!file.isExists(path))return null;
        var active=JSON.parse(file.readTextSync(path)),proof=actOneWolfWindRideProof(reports,active,request.session);
        return proof?{active:active,proof:proof,reports:reports}:null;
    }
    function wolfWindRideCheckpointUsed(reports,proof) {
        return reports.some(function(r){return r&&r.session===request.session&&Array.isArray(r.details&&r.details.inputEvents)&&
            r.details.inputEvents.some(function(e){return e&&e.type==='wolfWindRideContinue'&&
                (e.moveId===proof.moveId&&e.activeFrameId===proof.activeFrameId||
                 e.moveId==null&&e.frameId===proof.pauseFrameId);});});
    }
    function wolfApproachEnemyCheckpoint(reports) {
        if(!request||!request.session||!/^[A-Za-z0-9_-]{1,80}$/.test(request.session))return null;
        reports=reports||JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
        var terminal=reports.filter(function(r){return r&&r.session===request.session&&r.mission==='recover'&&r.status==='completed'&&r.id&&
            Array.isArray(r.details&&r.details.inputEvents);}),dismissals=[];
        terminal.forEach(function(r){r.details.inputEvents.forEach(function(e){if(e&&e.type==='wolfInfoRecoveryDismiss'&&Number.isInteger(e.frameId)&&Number.isFinite(e.startedAt))
            dismissals.push({report:r,event:e});});});
        dismissals.sort(function(a,b){return b.event.startedAt-a.event.startedAt;});
        if(!dismissals.length||dismissals.length>1&&dismissals[0].event.startedAt===dismissals[1].event.startedAt)return null;
        var candidate=dismissals[0],frame=candidate.event.frameId,path='observations/'+request.session+'/frame-'+String(frame).padStart(4,'0')+'.json';
        if(!file.isExists(path))return null;
        var source=JSON.parse(file.readTextSync(path)),dismissAt=candidate.event.startedAt,initialPauses=[];
        reports.forEach(function(r){if(!r||r.session!==request.session||r.mission!=='questStep'||r.status!=='completed'||!r.details||!r.details.result||
            r.details.result.step!=='wolfPause'||r.details.result.pauseVerified!==true||!Number.isFinite(r.timestamp)||!Number.isInteger(r.frameId)||!Array.isArray(r.details.inputEvents))return;
            r.details.inputEvents.forEach(function(e){if(e&&e.type==='key'&&e.key==='VK_ESCAPE'&&e.durationMs===60&&Number.isFinite(e.startedAt)&&
                Number.isFinite(e.finishedAt)&&e.startedAt>=dismissAt&&r.timestamp>=e.finishedAt)initialPauses.push({report:r,event:e});});});
        initialPauses.sort(function(a,b){return a.event.startedAt-b.event.startedAt;});
        if(!initialPauses.length)return null;
        var firstPause=initialPauses[0].report,baseReports=reports.filter(function(r){return r&&r.session===request.session&&
            (r.timestamp===undefined||r.timestamp<=firstPause.timestamp);});
        var proof=actOneWolfHydroApproachProof(baseReports,source,request.session);
        if(!proof)return null;
        var history=actOneWolfApproachHistory(reports,proof,request.session);
        return history?{proof:proof,history:history,source:source,reports:reports}:null;
    }
    function wolfRecoveryFoodReports() { return JSON.parse(file.readTextSync('reports/'+request.session+'.json')); }
    var wolfChestAttempted=false,wolfLootCount=0,wolfLootFrame=null,enemyBarDiagnostic=null;
    function wolfRecoveryFoodEventUsed(reports,type) {
        return reports.some(function(r){return r&&r.session===request.session&&r.mission==='recover'&&Array.isArray(r.details&&r.details.inputEvents)&&
            r.details.inputEvents.some(function(e){return e&&e.type===type;});})||events.some(function(e){return e&&e.type===type;});
    }
    function wolfRecoveryFoodStageFor(o) {
        if(!request||request.mission!=='recover'||!o||o.session!==request.session||!lastObservation||o.frameId!==lastObservation.frameId||
           o.timestamp!==lastObservation.timestamp||!actOneWolfRecoveryFoodSafe(o,Date.now())) return null;
        var reports=wolfRecoveryFoodReports();
        if(!actOneWolfEntryProven(reports,request.session)) return null;
        var usedFood=wolfRecoveryFoodEventUsed(reports,'wolfRecoveryFoodFeedKaeya'),closed=wolfRecoveryFoodEventUsed(reports,'wolfRecoveryFoodClose');
        var foodPage=actOneWolfFoodInventoryReady(o,Date.now()),modal=actOneKnownSafeFoodBoundary(o,Date.now());
        if(usedFood) return !closed&&foodPage?'close':null;
        if(closed) return null;
        var usedButton=wolfRecoveryFoodEventUsed(reports,'wolfRecoveryFoodUse');
        var useTarget=actOneWolfRecoveryFoodUseTarget(o,Date.now());
        if(!usedButton) return useTarget?'use':null;
        var selectedKaeya=wolfRecoveryFoodEventUsed(reports,'wolfRecoveryFoodSelectKaeya');
        var selectTarget=actOneWolfKaeyaFoodTarget(o,Date.now());
        if(!selectedKaeya) return selectTarget?'selectKaeya':null;
        var fedKaeya=wolfRecoveryFoodEventUsed(reports,'wolfRecoveryFoodFeedKaeya');
        var feedTarget=actOneWolfFeedKaeyaTarget(o,Date.now());
        if(!fedKaeya) return feedTarget?'feedKaeya':null;
        return null;
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
        var found,rows=[],ocrStart=Date.now();
        try { found=img.findMulti(RecognitionObject.Ocr(x, y, w, h)); }
        finally { ocrPrimitiveMs+=Date.now()-ocrStart;ocrReadCount++; }
        try {
            for (var i = 0; i < found.count; i++) {
                var r = found[i]; rows.push({ text: String(r.text), x: Number(r.x), y: Number(r.y), width: Number(r.width), height: Number(r.height) });
            }
        } finally { if(found){for (var j = 0; j < found.count; j++) dispose(found[j]); dispose(found);} }
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
        function textRows(rows) { return (rows||[]).slice(0,4).map(function(r){return String(r.text||'').trim().slice(0,32);}); }
        var fullHpRows=(fullRows||[]).filter(function(r){return r.x>=880&&r.x<=1050&&r.y>=990&&r.y<=1030;});
        var diagnostic={fullRow:textRows(fullHpRows),primary:[],left:[],right:[],decision:'pending'};
        function output(rows,decision,forceDiagnostic) {
            var hp=actOneHealth(rows),needs=!!forceDiagnostic||!hp||hp.current/hp.max<0.6||diagnostic.fullRow.length>0&&decision.indexOf('conflict')>=0;
            diagnostic.decision=decision;
            return {rows:rows,diagnostic:needs?diagnostic:null};
        }
        var fullResult=actOneFullHealthRows(fullRows);
        if(fullResult!==null) return output(fullResult,'full-frame-confirmed',false);
        var result = scaledRows(img, 900, 990, 125, 40);
        diagnostic.primary=textRows(result);
        fullResult=actOneFullHealthRows(fullRows,result);
        if(fullResult!==null) {
            if(fullResult.length) return output(fullResult,'primary-scaled-confirmed',true);
            // Conflicting primary scaled OCR can be rescued only when both
            // independently read halves exactly corroborate the full-frame row.
            var conflictLeft=scaledRows(img,893,998,65,25),conflictRight=scaledRows(img,967,998,65,25);
            diagnostic.left=textRows(conflictLeft);diagnostic.right=textRows(conflictRight);
            var corroborated=actOneCorroboratedFullHealth(fullRows,conflictLeft,conflictRight);
            return output(corroborated?[corroborated]:[],corroborated?'halves-agree-after-primary-conflict':'conflict-halves-disagree-or-missing',true);
        }
        if (actOneHealth(result)) return output(result,'primary-scaled-readable',false);
        // Read both numeric halves independently when OCR mistakes the slash for 1.
        var left = scaledRows(img, 893, 998, 65, 25).filter(function (r) { return /^\d{1,5}$/.test(r.text.trim()); });
        var right = scaledRows(img, 967, 998, 65, 25).filter(function (r) { return /^\d{1,5}$/.test(r.text.trim()); });
        diagnostic.left=textRows(left);diagnostic.right=textRows(right);
        var halves=actOneNumericHealthHalves(left,right);
        if(halves) return output([halves.row],'independent-halves-fallback',false);
        return output(result,'health-unresolved',false);
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
        enemyBarDiagnostic={level:level||1,candidates:0,localReads:[],greenMask:null};
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
            enemyBarDiagnostic.candidates=candidates.length;
            // Full-frame OCR is cheap. If it misses the small green enemy label,
            // inspect at most four local crops around the most bar-like candidates.
            for(var c=0;c<candidates.length;c++) if(actOneEnemyBarAnchored(candidates[c],rows,level)) bars.push(candidates[c]);
            var fallbackCount=0;
            for(var f=0;f<candidates.length && fallbackCount<4;f++) {
                var candidate=candidates[f];
                if(bars.some(function(v){return Math.hypot(v.x-candidate.x,v.y-candidate.y)<2;})) continue;
                fallbackCount++;
                // Keep the complete level label in view when the bar is very low
                // or an effect overlaps it. The previous 45px crop ended above
                // the label on knocked-down enemies.
                var cx=Math.max(0,Math.min(1920-300,Math.round(candidate.x-150)));
                var cy=Math.max(0,Math.min(1080-90,Math.round(candidate.y-70)));
                var local=scaledRows(img,cx,cy,300,90).map(function(r){return {text:r.text,x:cx+Number(r.x)/3,y:cy+Number(r.y)/3,width:Number(r.width)/3,height:Number(r.height)/3};});
                var anchored=actOneEnemyBarAnchored(candidate,local,level);
                enemyBarDiagnostic.localReads.push({bar:candidate,anchored:anchored,rows:local.map(function(r){return {text:r.text,x:r.x,y:r.y,width:r.width,height:r.height};})});
                if(anchored) bars.push(candidate);
            }
            if(level===5) {
                var greenCandidates=candidates.filter(function(candidate){return candidate.width>=50&&candidate.height>=6&&
                    !bars.some(function(v){return Math.hypot(v.x-candidate.x,v.y-candidate.y)<2;});});
                greenCandidates.sort(function(a,b){return b.width-a.width;});
                if(greenCandidates.length) {
                    var greenCandidate=greenCandidates[0],greenCrop=null,greenMask=null,greenBgr=null,greenMat=null,greenScaled=null,greenRows=[];
                    var gx=Math.max(0,Math.min(1920-240,Math.round(greenCandidate.x-120)));
                    var gy=Math.max(0,Math.min(900-70,Math.round(greenCandidate.y-78)));
                    try {
                        greenCrop=img.deriveCrop(gx,gy,240,70);
                        greenMask=greenCrop.srcMat.inRange(new OpenCvSharp.OpenCvSharp.Scalar(20,110,40),new OpenCvSharp.OpenCvSharp.Scalar(130,230,190));
                        greenBgr=greenMask.cvtColor(OpenCvSharp.OpenCvSharp.ColorConversionCodes.GRAY2BGR,0);
                        greenMat=greenBgr.resize(new OpenCvSharp.OpenCvSharp.Size(720,210));
                        greenScaled=new ImageRegion(greenMat,0,0);
                        greenMat=null;
                        greenRows=readRows(greenScaled,0,0,720,210).map(function(r){return {text:r.text,x:gx+Number(r.x)/3,y:gy+Number(r.y)/3,width:Number(r.width)/3,height:Number(r.height)/3};});
                        var levelRows=greenRows.filter(function(r){return /^LV[1-9]$/.test(actOneEnemyLevelToken(r.text,5));});
                        var greenAnchored=levelRows.length===1&&/^LV5$/.test(actOneEnemyLevelToken(levelRows[0].text,5))&&
                            Math.abs((Number(levelRows[0].x)+Number(levelRows[0].width)/2)-greenCandidate.x)<=150&&
                            greenCandidate.y-(Number(levelRows[0].y)+Number(levelRows[0].height)/2)>=8&&
                            greenCandidate.y-(Number(levelRows[0].y)+Number(levelRows[0].height)/2)<=50;
                        enemyBarDiagnostic.greenMask={attempted:true,bar:greenCandidate,rows:greenRows.filter(function(r){return r.y<900;}).map(function(r){return {text:String(r.text||'').slice(0,32),x:r.x,y:r.y,width:r.width,height:r.height};}),anchored:greenAnchored};
                        if(greenAnchored) bars.push(greenCandidate);
                    } finally {dispose(greenScaled);dispose(greenMat);dispose(greenBgr);dispose(greenMask);dispose(greenCrop);}
                }
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
    function wolfTurretReady(o,baseline) {
        o=o||lastObservation;
        if(!request||request.mission!=='questStep'||request.step!=='wolfTurretPass'||!o||o.session!==request.session) return {ok:false,reason:'Exact Wolf turret request and session required'};
        if(!actOneWolfKaeyaSkillReady(o,Date.now())) return {ok:false,reason:'Fresh Trial Kaeya max HP 1427 required'};
        var advance=actOneWolfAdvanceState(o,Date.now(),baseline);
        if(!advance.ok) return advance;
        var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
        if(!actOneWolfEntryProven(reports,request.session)) return {ok:false,reason:'Same-session Wolf entry required'};
        return advance;
    }
    function wolfBurstRecoveryPriorQ() {
        if(!request||typeof request.session!=='string'||!/^[A-Za-z0-9_-]{1,80}$/.test(request.session)) return true;
        var markerPath='reports/'+request.session+'.wolfBurstRecoveryQAttempt.json';
        try { if(file.isExists(markerPath)) return true; } catch(markerReadError) { return true; }
        var history=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
        return Array.isArray(history)&&history.some(function(row){
            if(!row||row.session!==request.session||row.mission!=='questStep'||!row.details) return false;
            var result=row.details.result,step=result&&result.step;
            if(step==='wolfBurstRecovery'&&result.burstAttempted===true) return true;
            return Array.isArray(row.details.inputEvents)&&row.details.inputEvents.some(function(e){
                return e&&e.type==='wolfBurstRecoveryQAttempt'||step==='wolfBurstRecovery'&&e&&e.type==='key'&&e.key==='VK_Q';
            });
        });
    }
    function wolfBurstRecoveryPersistQAttempt(o) {
        if(!request||typeof request.session!=='string'||!/^[A-Za-z0-9_-]{1,80}$/.test(request.session)||!o||!Number.isInteger(o.frameId))
            throw new Error('Path-safe Wolf session and fresh frame required for durable Q-attempt marker');
        var path='reports/'+request.session+'.wolfBurstRecoveryQAttempt.json';
        if(wolfBurstRecoveryPriorQ()) throw new Error('Wolf Q attempt is already recorded for this session');
        var marker={session:request.session,type:'wolfBurstRecoveryQAttempt',frameId:o.frameId,attemptedAt:Date.now()},source=JSON.stringify(marker);
        if(!file.writeTextSync(path,source)) throw new Error('Could not persist Wolf Q-attempt marker; no Q input sent');
        if(!file.isExists(path)) throw new Error('Wolf Q-attempt marker write could not be verified; no Q input sent');
        var saved=JSON.parse(file.readTextSync(path));
        if(!saved||saved.session!==marker.session||saved.type!==marker.type||saved.frameId!==marker.frameId||saved.attemptedAt!==marker.attemptedAt)
            throw new Error('Wolf Q-attempt marker verification failed; no Q input sent');
        return marker;
    }
    function wolfBurstRecoveryCurrent(o) {
        return !!(request&&request.mission==='questStep'&&request.step==='wolfBurstRecovery'&&o&&o.session===request.session&&
            lastObservation&&o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&
            Number.isInteger(o.frameId)&&Number.isFinite(Number(o.timestamp))&&Date.now()>=Number(o.timestamp)&&Date.now()-o.timestamp<=1000);
    }
    return {
        setHeartbeat: function (callback) {heartbeat=callback;},
        heartbeat: function (_,force) {if(heartbeat)heartbeat(force===true);},
        now: function () { return Date.now(); }, sleep: function (ms) { return sleep(ms); }, checkStop: checkStop,
        beginMission: function (value) {
            wolfChestAttempted=false;
            wolfLootCount=0;wolfLootFrame=null;
            request = value; events = []; navLastAcceptedPosition = null; focusRecoveryAttempted = false; wolfInfoAttempted = false; wolfContinueAttempted=false; wolfInventoryContinueAttempted=false; wolfInventoryOpenAttempted=false; wolfKaeyaFoodAttempted=false; wolfFeedKaeyaAttempted=false; wolfRecoveryFoodUseAttempted=false;wolfRecoveryFoodSelectAttempted=false;wolfRecoveryFoodFeedAttempted=false;wolfRecoveryFoodCloseAttempted=false;wolfExitFlameAttempted=false;wolfWindContinueAttempted=false;wolfWindSpaceAttempted=false;wolfWindRideContinueAttempted=false;wolfWindRideSpaceAttempted=false;wolfGlideContinueAttempted=false;wolfGlideMoves=0;wolfGlideLastMoveFrame=null;wolfGlideBaseline=null;wolfDefensiveCryoAttempted=false;wolfAimCryoAttempted=false;wolfCloseFoodAttempted=false;wolfCloseFoodCompletedAt=null;wolfCloseFoodLookAttempted=false;wolfCloseFoodForwardAttempted=false;wolfCloseFoodSkillAttempted=false;wolfTurretSkillAttempted=false;wolfTurretForwardAttempted=false;wolfTurretSkillFinishedAt=null;wolfTurretBaseline=null;wolfConsoleContinueAttempted=false;wolfConsoleInteractAttempted=false;wolfApproachContinueAttempted=false;wolfApproachMoveAttempted=false;wolfApproachHydroFrame=null;wolfApproachHydroReceiptId=null;wolfCombatSeekForwards=0;wolfCombatSeekTurns=0;wolfCombatSeekFrames=[];wolfBurstContinueAttempted=false;wolfBurstQAttempted=false;wolfBurstPauseAttempted=false;
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
        seedObservation: function (value) {
            ready();
            if(!request||request.mission!=='questStep'||typeof request.step!=='string'||request.step.indexOf('wolf')!==0||!value||
               value.session!==request.session||value.frameId!==request.expectedFrameId||!Number.isFinite(value.timestamp)||
               Date.now()<value.timestamp||Date.now()-value.timestamp>1000||value.map!==null||!value.hud||value.hud.world!==false)
                throw new Error('Fresh exact Wolf observation required to seed adapter state');
            if(request.step==='wolfContinue') {
                if(!actOneWolfResumeSeedTarget(value,Date.now())) throw new Error('Exact unique Wolf Continue and Leave menu required');
                var pauseReports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
                if(!actOneWolfEntryProven(pauseReports,request.session)) throw new Error('Same-session Wolf entry required');
            } else {
                var hp=value.hud.health;
                if(!hp||!Number.isFinite(hp.current)||!Number.isFinite(hp.max)||hp.max<=0||hp.current<=0||hp.current>hp.max)
                    throw new Error('Positive numeric HP required to seed an active Wolf step');
            }
            lastObservation=JSON.parse(JSON.stringify(value));
            return true;
        },
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
            if(!actOneWorldInventoryPauseReady(o,Date.now())) return false;
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
        wolfReturnToEntranceReady: function (o) { return actOneWolfReturnToEntranceReady(o||lastObservation,Date.now()); },
        wolfReturnToEntrance: async function () {
            checkStop();ready();var o=lastObservation,h=o&&o.hud,p=o&&o.map;
            if(!request||request.mission!=='questStep'||request.step!=='wolfReturnToEntrance'||!actOneWolfReturnToEntranceReady(o,Date.now())) throw new Error('Fresh safe starter-party world HUD with Enter the temple objective required');
            var target={x:-1642.421,y:2163.664};
            await boundedKey('VK_M',60);await sleep(200);checkStop();
            events.push({type:'wolfReturnTeleport',x:target.x,y:target.y,frameId:o.frameId,sourceX:p.x,sourceY:p.y,startedAt:Date.now()});
            await genshin.tp(target.x,target.y,false);checkStop();
            return target;
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
        wolfResume: function () {
            checkStop();ready();
            if(!request||request.mission!=='questStep'||request.step!=='wolfResume'||!actOneFalconContinueTarget(lastObservation,Date.now()))
                throw new Error('Fresh exact Wolf pause menu required');
            if(typeof genshin.GetGameWindowInfo!=='function') throw new Error('Game window identity API unavailable');
            var marker=JSON.parse(file.readTextSync('wolf-resume.json'));
            if(!marker||!/^[A-Za-z0-9_-]{1,80}$/.test(marker.fromSession||'')) throw new Error('Invalid prior Wolf session marker');
            var currentPath='reports/'+request.session+'.jsonl';
            function jsonl(path) { return file.isExists(path)?file.readTextSync(path).split(/\r?\n/).filter(function(line){return line.trim().length>0;}).map(function(line){return JSON.parse(line);}):[]; }
            var prior=[],chainSessions={},chainOk=true;
            function loadResumeChain(session,entryId,pauseId,depth) {
                if(depth>8||!/^[A-Za-z0-9_-]{1,80}$/.test(session||'')||!/^[A-Za-z0-9_-]{1,100}$/.test(entryId||'')||
                   !/^[A-Za-z0-9_-]{1,100}$/.test(pauseId||'')||chainSessions[session]) { chainOk=false;return; }
                chainSessions[session]=true;
                var path='reports/'+session+'.jsonl';if(!file.isExists(path)) { chainOk=false;return; }
                var rows=jsonl(path);prior=prior.concat(rows);
                var entries=rows.filter(function(r){return r&&r.session===session&&r.id===entryId&&r.mission==='questStep'&&r.status!=='started'&&r.status!=='running';});
                var pauses=rows.filter(function(r){return r&&r.session===session&&r.id===pauseId&&r.mission==='questStep'&&r.status!=='started'&&r.status!=='running';});
                if(entries.length!==1||pauses.length!==1) { chainOk=false;return; }
                var result=entries[0].details&&entries[0].details.result;
                if(result&&result.step==='wolfResume') loadResumeChain(result.fromSession,result.priorEntryId,result.priorPauseId,depth+1);
            }
            loadResumeChain(marker.fromSession,marker.priorEntryId,marker.priorPauseId,0);
            if(!chainOk) throw new Error('Wolf resume proof chain unavailable or cyclic');
            var current=jsonl(currentPath),info=JSON.parse(genshin.GetGameWindowInfo());
            var proof=actOneValidateWolfResume(marker,prior,current,request.session,expectedSession,lastObservation,Date.now(),info);
            if(!proof) throw new Error('Verified same-game Wolf restart handoff required');
            events.push({type:'wolfResumeProof',verified:true,fromSession:proof.fromSession,toSession:proof.toSession,priorEntryId:proof.priorEntryId,
                priorPauseId:proof.priorPauseId,betterGiProcessId:proof.betterGiProcessId,rdpSessionId:proof.rdpSessionId,
                gameProcessId:proof.gameProcessId,verifiedAt:proof.verifiedAt,recordedAt:Date.now()});
            return proof;
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
        startGame: function (phase) {
            checkStop();ready();
            phase=phase||request&&request.step;
            var isTitle=phase==='enterGame'&&request&&request.step==='enterGame';
            var isDoor=phase==='enterWorld'&&request&&
                (request.step==='enterWorld'||request.step==='enterGame'&&events.some(function(e){return e.type==='enterGame';}));
            var target=isTitle?actOneEnterGameTarget(lastObservation,Date.now()):isDoor?actOneEnterWorldTarget(lastObservation,Date.now()):null;
            if(!request||request.mission!=='questStep'||!target||events.some(function(e){return e.type===phase;}))
                throw new Error('Fresh exact title or door entry screen required');
            events.push({type:phase,frameId:lastObservation.frameId,x:target.x,y:target.y,label:target.label,startedAt:Date.now()});
            click(target.x,target.y);checkStop();
            return {phase:phase,x:target.x,y:target.y,label:target.label,frameId:lastObservation.frameId};
        },
        windowInfo: function () {
            checkStop();
            if(!request||request.mission!=='questStep'||['windowInfo','windowedGame'].indexOf(request.step)<0) throw new Error('Read-only windowInfo quest step required');
            if(typeof genshin.GetGameWindowInfo!=='function') throw new Error('Game window info API unavailable');
            return JSON.parse(genshin.GetGameWindowInfo());
        },
        windowedGame: async function () {
            checkStop();
            if(!request||request.mission!=='questStep'||request.step!=='windowedGame'||!actOneWindowedGameReady(lastObservation,Date.now()))
                throw new Error('Fresh safe world HUD required for window mode change');
            if(typeof genshin.GetGameWindowInfo!=='function') throw new Error('Game window info API unavailable');
            var info=JSON.parse(genshin.GetGameWindowInfo()),decision=actOneWindowModeDecision(info,expectedSession);
            if(decision==='noop') {
                var noop={type:'windowedGameNoop',frameId:lastObservation.frameId,clientWidth:info.gameWindow.clientWidth,clientHeight:info.gameWindow.clientHeight,
                    fillsDesktop:info.fillsDesktop,startedAt:Date.now()};events.push(noop);
                return {action:'noop',info:info};
            }
            if(decision!=='toggle') throw new Error('Window change requires a foreground 2560x1440 RDP fullscreen game window');
            var event={type:'windowedGameToggle',frameId:lastObservation.frameId,desktopWidth:2560,desktopHeight:1440,startedAt:Date.now(),holdMs:0};
            events.push(event);
            try {
                var chord=await actOneWindowedGameChord({now:Date.now,sleep:sleep,checkStop:checkStop,keyDown:keyDown,keyUp:keyUp});
                event.holdMs=chord.holdMs;event.finishedAt=Date.now();
                return {action:'altEnter',before:info,holdMs:chord.holdMs};
            } catch(e) {
                event.finishedAt=Date.now();event.error=String(e&&e.message||e);throw e;
            }
        },
        wolfDomainHud: function (o) { return actOneWolfDomainHud(o||lastObservation,Date.now(),0); },
        wolfKaeyaSkillReady: function (o) { return actOneWolfKaeyaSkillReady(o||lastObservation,Date.now()); },
        wolfDefensiveCryoReady: function (o) { return actOneWolfDefensiveCryoReady(o||lastObservation,Date.now()); },
        wolfDefensiveCryo: async function () {
            checkStop();var o=lastObservation;
            if(wolfDefensiveCryoAttempted||!request||request.mission!=='questStep'||request.step!=='wolfDefensiveCryo'||!o||o.session!==request.session||!actOneWolfDefensiveCryoReady(o,Date.now()))
                throw new Error('Fresh living Kaeya Trial HUD required for one defensive Cryo attempt');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session Wolf entry required');
            wolfDefensiveCryoAttempted=true;
            return boundedKey('VK_E',60);
        },
        wolfAimCryoReady: function (o) {
            o=o||lastObservation;
            if(!request||request.mission!=='questStep'||request.step!=='wolfAimCryo'||!o||o.session!==request.session||
               !actOneWolfKaeyaSkillReady(o,Date.now())||!actOneWolfDefensiveCryoReady(o,Date.now())||o.hud.health.current/o.hud.health.max<0.6) return false;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            return actOneWolfEntryProven(reports,request.session);
        },
        wolfAimCryo: async function () {
            checkStop();var o=lastObservation;
            if(wolfAimCryoAttempted||!this.wolfAimCryoReady(o)) throw new Error('Fresh healthy Trial Kaeya HUD and same-session Wolf entry required for one aim Cryo sequence');
            wolfAimCryoAttempted=true;
            events.push({type:'rotate',dx:250,dy:0,frameId:o.frameId,startedAt:Date.now()});moveMouseBy(250,0);
            var forward={type:'wolfAimCryoForward',frameId:o.frameId,startedAt:Date.now()};events.push(forward);
            try { await boundedKey('VK_W',60);forward.finishedAt=Date.now(); }
            catch(e) {forward.finishedAt=Date.now();forward.error=String(e&&e.message||e);throw e;}
            var skill={type:'wolfAimCryoSkill',frameId:o.frameId,startedAt:Date.now()};events.push(skill);
            try { await boundedKey('VK_E',60);skill.finishedAt=Date.now(); }
            catch(e) {skill.finishedAt=Date.now();skill.error=String(e&&e.message||e);throw e;}
        },
        wolfCloseFoodCryoReady: function (o) { return actOneWolfFoodGridReady(o||lastObservation,Date.now()); },
        wolfCloseFoodCryoAction: async function (kind) {
            checkStop();var o=lastObservation,h=o&&o.hud,hp=h&&h.health;
            if(!request||request.mission!=='questStep'||request.step!=='wolfCloseFoodCryo'||!o||o.session!==request.session||Date.now()-o.timestamp>1000)
                throw new Error('Fresh Wolf food recovery request required');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session Wolf entry required');
            if(kind==='close') {
                if(wolfCloseFoodAttempted||!actOneWolfFoodGridReady(o,Date.now())) throw new Error('Fresh exact Wolf food grid required before one close');
                wolfCloseFoodAttempted=true;events.push({type:'wolfCloseFood',frameId:o.frameId,startedAt:Date.now()});
                await boundedKey('VK_ESCAPE',60);wolfCloseFoodCompletedAt=Date.now();return;
            }
            if(!wolfCloseFoodAttempted||!Number.isFinite(wolfCloseFoodCompletedAt)||!o||!Number.isFinite(o.timestamp)||o.timestamp<=wolfCloseFoodCompletedAt||
               !actOneWolfDefensiveCryoReady(o,Date.now())) throw new Error('Fresh post-close living grounded Kaeya Trial HUD required');
            if(kind==='look') {
                if(wolfCloseFoodLookAttempted) throw new Error('Wolf recovery look already attempted');
                wolfCloseFoodLookAttempted=true;events.push({type:'rotate',dx:250,dy:0,frameId:o.frameId,startedAt:Date.now()});moveMouseBy(250,0);return;
            }
            if(kind==='forward') {
                if(wolfCloseFoodForwardAttempted||!wolfCloseFoodLookAttempted||hp.current/hp.max<0.6) throw new Error('Fresh look and 60% HP required for one orientation step');
                wolfCloseFoodForwardAttempted=true;return boundedKey('VK_W',60);
            }
            if(kind==='skill') {
                if(wolfCloseFoodSkillAttempted||hp.current/hp.max>=0.6&&(!wolfCloseFoodLookAttempted||!wolfCloseFoodForwardAttempted)) throw new Error('Defensive Cryo already attempted or orientation incomplete');
                wolfCloseFoodSkillAttempted=true;return boundedKey('VK_E',60);
            }
            throw new Error('Unsupported Wolf food recovery action');
        },
        wolfTurretPassReady: wolfTurretReady,
        wolfTurretPassCast: async function () {
            checkStop();var o=lastObservation,guard=wolfTurretReady(o,null);
            if(wolfTurretSkillAttempted||!guard.ok) throw new Error(guard.reason||'Wolf turret skill already attempted');
            wolfTurretSkillAttempted=true;wolfTurretBaseline={current:o.hud.health.current,max:o.hud.health.max};
            var event={type:'wolfTurretPassCast',frameId:o.frameId,startedAt:Date.now()};events.push(event);
            try { await boundedKey('VK_E',60);event.finishedAt=Date.now();wolfTurretSkillFinishedAt=event.finishedAt; }
            catch(e) {event.finishedAt=Date.now();event.error=String(e&&e.message||e);throw e;}
        },
        wolfTurretPassForward: async function (durationMs) {
            checkStop();
            if(!request||request.mission!=='questStep'||request.step!=='wolfTurretPass') throw new Error('Exact Wolf turret request required');
            throw new Error('Wolf turret passage movement is disabled until core shutdown is verified');
        },
        wolfDismissInfo: function () {
            checkStop();var o=lastObservation;
            if(wolfInfoAttempted||!request||request.mission!=='questStep'||request.step!=='wolfInfo'||!actOneWolfInfoState(o,Date.now())) throw new Error('Fresh exact Wolf tutorial required');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session Wolf entry required');
            wolfInfoAttempted=true;
            events.push({type:'wolfInfoTutorialDismiss',frameId:o.frameId,x:960,y:900,startedAt:Date.now()});click(960,900);
        },
        wolfInfoReady: function () {
            checkStop();var o=lastObservation;
            if(!request||request.mission!=='recover'||!o||o.session!==request.session||!actOneWolfInfoState(o,Date.now())) return false;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            return actOneWolfEntryProven(reports,request.session);
        },
        recoverWolfInfo: function () {
            checkStop();var o=lastObservation;
            if(wolfInfoAttempted||!request||request.mission!=='recover'||!o||o.session!==request.session||!actOneWolfInfoState(o,Date.now()))
                throw new Error('Fresh exact Wolf tutorial required for recovery');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session Wolf entry required for recovery');
            wolfInfoAttempted=true;
            events.push({type:'wolfInfoRecoveryDismiss',frameId:o.frameId,x:960,y:900,startedAt:Date.now()});click(960,900);
        },
        wolfExitFlameReady: function (o) {
            checkStop();o=o||lastObservation;
            if(!request||request.mission!=='questStep'||request.step!=='wolfExitFlame'||wolfExitFlameAttempted||!o||
               o.session!==request.session||!lastObservation||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp||
               !actOneWolfResumeSeedTarget(o,Date.now())) return false;
            if(!/^[A-Za-z0-9_-]{1,80}$/.test(request.session)) return false;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(reports.some(function(r){return r&&r.session===request.session&&r.mission==='questStep'&&r.details&&Array.isArray(r.details.inputEvents)&&
                r.details.inputEvents.some(function(e){return e&&(e.type==='wolfExitFlameContinue'||e.type==='wolfExitFlameForward');});})) return false;
            var frame=reports.filter(function(r){return r&&r.session===request.session&&r.mission==='questStep'&&r.status==='completed'&&
                r.details&&r.details.result&&r.details.result.step==='wolfForward'&&Number.isInteger(r.details.result.frameId);})
                .map(function(r){return r.details.result.frameId;}).sort(function(a,b){return b-a;})[0];
            var framePath='observations/'+request.session+'/frame-'+String(frame).padStart(4,'0')+'.json';
            if(!Number.isInteger(frame)||!file.isExists(framePath)) return false;
            var active=JSON.parse(file.readTextSync(framePath));
            var proof=actOneWolfExitFlameProof(reports,active,request.session,Date.now());
            return !!(proof&&o.frameId>proof.pauseFrameId&&o.timestamp>=proof.pauseTimestamp&&Date.now()>=proof.pauseTimestamp);
        },
        wolfExitFlame: async function () {
            checkStop();var o=lastObservation,target=actOneWolfResumeSeedTarget(o,Date.now());
            if(wolfExitFlameAttempted||!request||request.mission!=='questStep'||request.step!=='wolfExitFlame'||!target||!this.wolfExitFlameReady(o))
                throw new Error('Fresh exact paused Wolf flame-exit proof required');
            wolfExitFlameAttempted=true;
            var x=Math.round(target.x+target.width/2),y=Math.round(target.y+target.height/2);
            events.push({type:'wolfExitFlameContinue',frameId:o.frameId,x:x,y:y,startedAt:Date.now()});click(x,y);
            await sleep(120);checkStop();
            var event={type:'wolfExitFlameForward',frameId:o.frameId,durationMs:300,startedAt:Date.now()};events.push(event);
            try { await boundedKey('VK_W',300);event.finishedAt=Date.now(); }
            catch(e) {event.finishedAt=Date.now();event.error=String(e&&e.message||e);throw e;}
        },
        wolfWindTakeoffReady: function (o) {
            checkStop();o=o||lastObservation;
            if(!request||request.mission!=='questStep'||request.step!=='wolfWindTakeoff'||wolfWindContinueAttempted||wolfWindSpaceAttempted||
               !o||o.session!==request.session||!lastObservation||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp||
               !actOneWolfResumeSeedTarget(o,Date.now()))return false;
            var evidence=wolfWindEvidence(o);
            return !!evidence;
        },
        wolfWindTakeoffContinue: function () {
            checkStop();var o=lastObservation,target=actOneWolfResumeSeedTarget(o,Date.now());
            if(wolfWindContinueAttempted||!request||request.mission!=='questStep'||request.step!=='wolfWindTakeoff'||!target||!this.wolfWindTakeoffReady(o))
                throw new Error('Fresh exact Wolf pause and uninterrupted wind witness required');
            wolfWindContinueAttempted=true;
            events.push({type:'wolfWindTakeoffContinue',frameId:o.frameId,x:Math.round(target.x+target.width/2),y:Math.round(target.y+target.height/2),startedAt:Date.now()});
            click(Math.round(target.x+target.width/2),Math.round(target.y+target.height/2));
        },
        wolfWindTakeoffActiveReady: function (o) {
            checkStop();o=o||lastObservation;
            if(!request||request.mission!=='questStep'||request.step!=='wolfWindTakeoff'||!wolfWindContinueAttempted||wolfWindSpaceAttempted||
               !o||o.session!==request.session||!lastObservation||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp||
               o.frameId<=0||!actOneWolfWindActiveState(o,Date.now()))return false;
            var evidence=wolfWindEvidence(o);
            return !!(evidence&&o.frameId>evidence.proof.latestPauseFrameId);
        },
        wolfWindTakeoffPulses: async function (o) {
            checkStop();o=o||lastObservation;
            if(wolfWindSpaceAttempted||!this.wolfWindTakeoffActiveReady(o))throw new Error('Fresh safe grounded Wolf HUD after Continue required');
            wolfWindSpaceAttempted=true;
            for(var pulse=1;pulse<=2;pulse++) {
                checkStop();
                events.push({type:'wolfWindTakeoffSpace',pulse:pulse,frameId:o.frameId,startedAt:Date.now()});
                await boundedKey('VK_SPACE',60);
                if(pulse===1)await sleep(220);
            }
        },
        wolfWindRideReady: function (o) {
            checkStop();o=o||lastObservation;
            if(wolfWindRideContinueAttempted||!request||request.mission!=='questStep'||request.step!=='wolfWindRide'||!o||
               o.session!==request.session||!lastObservation||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp||
               !actOneWolfResumeSeedTarget(o,Date.now()))return false;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            var checkpoint=wolfWindRideCheckpoint(reports);
            return !!(actOneWolfEntryProven(reports,request.session)&&checkpoint&&o.frameId>=checkpoint.proof.pauseFrameId&&
                !wolfWindRideCheckpointUsed(reports,checkpoint.proof)&&!events.some(function(e){return e&&e.type==='wolfWindRideContinue'&&
                    e.moveId===checkpoint.proof.moveId&&e.activeFrameId===checkpoint.proof.activeFrameId;}));
        },
        wolfWindRideContinue: function () {
            checkStop();var o=lastObservation,target=actOneWolfResumeSeedTarget(o,Date.now());
            if(wolfWindRideContinueAttempted||!request||request.mission!=='questStep'||request.step!=='wolfWindRide'||!target||!this.wolfWindRideReady(o))
                throw new Error('Fresh exact Wolf pause and latest grounded wind-base proof required');
            wolfWindRideContinueAttempted=true;
            var x=Math.round(target.x+target.width/2),y=Math.round(target.y+target.height/2);
            var proof=wolfWindRideCheckpoint();
            if(!proof)throw new Error('Latest grounded Wolf checkpoint proof required');
            events.push({type:'wolfWindRideContinue',frameId:o.frameId,moveId:proof.proof.moveId,activeFrameId:proof.proof.activeFrameId,
                pauseFrameId:proof.proof.pauseFrameId,x:x,y:y,startedAt:Date.now()});click(x,y);
        },
        wolfWindRideActiveReady: function (o) {
            checkStop();o=o||lastObservation;
            if(!request||request.mission!=='questStep'||request.step!=='wolfWindRide'||!wolfWindRideContinueAttempted||
               !o||o.session!==request.session||!lastObservation||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp||
               !Number.isFinite(o.timestamp)||Date.now()<o.timestamp||Date.now()-o.timestamp>1000||!actOneWolfWindRideGroundState(o))return false;
            var checkpoint=wolfWindRideCheckpoint();
            return !!(checkpoint&&actOneWolfEntryProven(checkpoint.reports,request.session)&&o.frameId>checkpoint.proof.pauseFrameId);
        },
        wolfWindRideJump: async function (o) {
            checkStop();o=o||lastObservation;
            if(wolfWindRideSpaceAttempted||!this.wolfWindRideActiveReady(o))throw new Error('Fresh grounded Trial Kaeya after Continue required for one wind jump');
            wolfWindRideSpaceAttempted=true;
            for(var pulse=1;pulse<=2;pulse++) {
                checkStop();events.push({type:'wolfWindRideSpace',pulse:pulse,frameId:o.frameId,startedAt:Date.now()});
                await boundedKey('VK_SPACE',60);if(pulse===1)await sleep(220);
            }
        },
        wolfWindRideAirborne: function (o) {
            checkStop();o=o||lastObservation;
            if(!request||request.mission!=='questStep'||request.step!=='wolfWindRide'||!wolfWindRideSpaceAttempted||!o||
               o.session!==request.session||!lastObservation||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp)return false;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            return actOneWolfEntryProven(reports,request.session)&&actOneWolfAirPauseOnlyHud(o,Date.now());
        },
        wolfApproachEnemyReady: function (o) {
            checkStop();o=o||lastObservation;
            if(!request||request.mission!=='questStep'||request.step!=='wolfApproachEnemy'||wolfApproachContinueAttempted||wolfApproachMoveAttempted||!o||
               o.session!==request.session||!lastObservation||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp||
               !actOneWolfResumeSeedTarget(o,Date.now())||o.hud.journal!==false||o.hud.bigMap!==false)return false;
            var checkpoint=wolfApproachEnemyCheckpoint();
            return !!(checkpoint&&checkpoint.history.moveCount===0&&o.frameId>=checkpoint.history.latestPauseFrameId);
        },
        wolfApproachEnemyContinue: function () {
            checkStop();var o=lastObservation,target=actOneWolfResumeSeedTarget(o,Date.now()),checkpoint=wolfApproachEnemyCheckpoint();
            if(wolfApproachContinueAttempted||wolfApproachMoveAttempted||!request||request.mission!=='questStep'||request.step!=='wolfApproachEnemy'||
               !target||!checkpoint||!this.wolfApproachEnemyReady(o))throw new Error('Fresh canonical Wolf pause and unused Hydro checkpoint required');
            wolfApproachContinueAttempted=true;wolfApproachHydroFrame=checkpoint.proof.hydroFrameId;wolfApproachHydroReceiptId=checkpoint.proof.receiptId;
            var x=Math.round(target.x+target.width/2),y=Math.round(target.y+target.height/2);
            events.push({type:'wolfApproachEnemyContinue',frameId:o.frameId,x:x,y:y,hydroFrameId:wolfApproachHydroFrame,hydroReceiptId:wolfApproachHydroReceiptId,startedAt:Date.now()});click(x,y);
        },
        wolfApproachEnemyTarget: function (o) {
            checkStop();o=o||lastObservation;
            if(!request||request.mission!=='questStep'||request.step!=='wolfApproachEnemy'||!wolfApproachContinueAttempted||wolfApproachMoveAttempted||!o||
               o.session!==request.session||!lastObservation||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp)return null;
            var checkpoint=wolfApproachEnemyCheckpoint();
            if(!checkpoint||checkpoint.history.moveCount!==0||o.frameId<checkpoint.history.latestPauseFrameId||
               checkpoint.proof.hydroFrameId!==wolfApproachHydroFrame||checkpoint.proof.receiptId!==wolfApproachHydroReceiptId)return null;
            return actOneWolfApproachEnemyTarget(o,Date.now());
        },
        wolfApproachEnemyMove: async function (o) {
            checkStop();o=o||lastObservation;var bar=this.wolfApproachEnemyTarget(o);
            if(wolfApproachMoveAttempted||!bar)throw new Error('Fresh safe grounded Trial Kaeya and one anchored enemy bar required');
            wolfApproachMoveAttempted=true;
            var event={type:'wolfApproachEnemyMove',key:'VK_W',durationMs:500,frameId:o.frameId,bar:bar,hydroFrameId:wolfApproachHydroFrame,
                hydroReceiptId:wolfApproachHydroReceiptId,startedAt:Date.now()};events.push(event);
            try {await boundedKey('VK_W',500);event.finishedAt=Date.now();}
            catch(e){event.finishedAt=Date.now();event.error=String(e&&e.message||e);throw e;}
        },
        wolfConsoleInteractReady: function (o) {
            checkStop();o=o||lastObservation;
            if(!request||request.mission!=='questStep'||request.step!=='wolfConsoleInteract'||!wolfConsoleContinueAttempted||wolfConsoleInteractAttempted||!o||
               o.session!==request.session||!lastObservation||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp||
               !actOneWolfDomainHud(o,Date.now())||!o.hud.health||o.hud.health.max!==1427) return false;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            return actOneWolfEntryProven(reports,request.session)&&!!actOneWolfOpenDoorF(o,Date.now());
        },
        wolfConsoleContinueReady: function (o) {
            checkStop();o=o||lastObservation;
            if(!request||request.mission!=='questStep'||request.step!=='wolfConsoleInteract'||wolfConsoleContinueAttempted||wolfConsoleInteractAttempted||!o||
               o.session!==request.session||!lastObservation||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp||
               !actOneWolfResumeSeedTarget(o,Date.now())||o.hud.journal!==false||o.hud.bigMap!==false) return false;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            return actOneWolfEntryProven(reports,request.session);
        },
        wolfConsoleInteractTarget: function (o) {
            checkStop();o=o||lastObservation;
            if(!request||request.mission!=='questStep'||request.step!=='wolfConsoleInteract'||!wolfConsoleContinueAttempted||wolfConsoleInteractAttempted||!o||
               o.session!==request.session||!lastObservation||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp||
               !actOneWolfDomainHud(o,Date.now())||!o.hud.health||o.hud.health.max!==1427) return null;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            return actOneWolfEntryProven(reports,request.session)?actOneWolfOpenDoorF(o,Date.now()):null;
        },
        wolfConsoleContinue: function () {
            checkStop();var o=lastObservation,target=actOneWolfResumeSeedTarget(o,Date.now());
            if(wolfConsoleContinueAttempted||wolfConsoleInteractAttempted||!request||request.mission!=='questStep'||request.step!=='wolfConsoleInteract'||
               !target||!this.wolfConsoleContinueReady(o)) throw new Error('Fresh exact Wolf pause and same-session entry required');
            wolfConsoleContinueAttempted=true;var x=Math.round(target.x+target.width/2),y=Math.round(target.y+target.height/2);
            events.push({type:'wolfConsoleContinue',frameId:o.frameId,x:x,y:y,startedAt:Date.now()});click(x,y);
        },
        wolfConsolePressF: async function (o) {
            checkStop();o=o||lastObservation;var target=actOneWolfOpenDoorF(o,Date.now());
            if(wolfConsoleInteractAttempted||!wolfConsoleContinueAttempted||!request||request.mission!=='questStep'||request.step!=='wolfConsoleInteract'||
               !this.wolfConsoleInteractReady(o)||!target) throw new Error('Fresh aligned Open Door and F prompt required for one interaction');
            wolfConsoleInteractAttempted=true;var event={type:'wolfConsoleInteract',label:target.label,frameId:o.frameId,x:target.x,y:target.y,startedAt:Date.now()};events.push(event);
            try {await boundedKey('VK_F',60);event.finishedAt=Date.now();}
            catch(e) {event.finishedAt=Date.now();event.error=String(e&&e.message||e);throw e;}
        },
        wolfGlideForwardReady: function (o) {
            checkStop();o=o||lastObservation;
            if(wolfGlideContinueAttempted||!request||request.mission!=='questStep'||request.step!=='wolfGlideForward'||!o||
               o.session!==request.session||!lastObservation||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp||
               !actOneWolfResumeSeedTarget(o,Date.now()))return false;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            return actOneWolfEntryProven(reports,request.session);
        },
        wolfGlideForwardContinue: function () {
            checkStop();var o=lastObservation,target=actOneWolfResumeSeedTarget(o,Date.now());
            if(wolfGlideContinueAttempted||!request||request.mission!=='questStep'||request.step!=='wolfGlideForward'||!target||!this.wolfGlideForwardReady(o))
                throw new Error('Fresh exact Wolf pause and same-session entry required');
            wolfGlideContinueAttempted=true;var x=Math.round(target.x+target.width/2),y=Math.round(target.y+target.height/2);
            events.push({type:'wolfGlideForwardContinue',frameId:o.frameId,x:x,y:y,startedAt:Date.now()});click(x,y);
        },
        wolfGlideState: function (o) {
            checkStop();o=o||lastObservation;
            if(!request||request.mission!=='questStep'||request.step!=='wolfGlideForward'||!wolfGlideContinueAttempted||!o||
               o.session!==request.session||!lastObservation||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp)return null;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session))return null;
            var state=actOneWolfGlideState(o,Date.now());if(!state)return null;
            var hp=o.hud.health;
            if(wolfGlideBaseline&&wolfGlideBaseline.current-hp.current>wolfGlideBaseline.max*0.05)return null;
            if(state==='airborne'&&!wolfGlideBaseline)wolfGlideBaseline={current:hp.current,max:hp.max};
            return state;
        },
        wolfGlideForwardMove: async function (o) {
            checkStop();o=o||lastObservation;
            if(wolfGlideMoves>=4||!request||request.mission!=='questStep'||request.step!=='wolfGlideForward'||!this.wolfGlideState(o)||wolfGlideLastMoveFrame===o.frameId||
               actOneWolfGlideState(o,Date.now())!=='airborne'||!wolfGlideBaseline)
                throw new Error('Fresh safe airborne Trial Kaeya required for one bounded glide hold');
            wolfGlideMoves++;wolfGlideLastMoveFrame=o.frameId;var event={type:'wolfGlideForwardMove',attempt:wolfGlideMoves,frameId:o.frameId,durationMs:400,
                health:{current:o.hud.health.current,max:o.hud.health.max},startedAt:Date.now()};events.push(event);
            try {await boundedKey('VK_W',400);event.finishedAt=Date.now();}
            catch(e){event.finishedAt=Date.now();event.error=String(e&&e.message||e);throw e;}
            return wolfGlideMoves;
        },
        wolfPauseRecoveryReady: function (o) {
            checkStop();o=o||lastObservation;
            if(!request||request.mission!=='recover'||!o||o.session!==request.session||!lastObservation||o.frameId!==lastObservation.frameId||
               o.timestamp!==lastObservation.timestamp||!actOneWolfRecoveryPauseTarget(o,Date.now())) return false;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)||reports.some(function(r){return r&&r.session===request.session&&r.mission==='recover'&&
                Array.isArray(r.details&&r.details.inputEvents)&&r.details.inputEvents.some(function(e){return e&&e.type==='wolfPauseRecoveryContinue';});})) return false;
            return true;
        },
        recoverWolfPauseMenuContinue: function () {
            checkStop();var o=lastObservation,target=actOneWolfRecoveryPauseTarget(o,Date.now());
            if(wolfContinueAttempted||!request||request.mission!=='recover'||!o||o.session!==request.session||!target)
                throw new Error('Fresh unique Wolf pause menu required for recovery Continue');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)||reports.some(function(r){return r&&r.session===request.session&&r.mission==='recover'&&
                Array.isArray(r.details&&r.details.inputEvents)&&r.details.inputEvents.some(function(e){return e&&e.type==='wolfPauseRecoveryContinue';});}))
                throw new Error('Same-session Wolf entry required and recovery Continue must be unused');
            wolfContinueAttempted=true;
            var x=Math.round(target.x+target.width/2),y=Math.round(target.y+target.height/2);
            events.push({type:'wolfPauseRecoveryContinue',frameId:o.frameId,x:x,y:y,startedAt:Date.now()});click(x,y);
        },
        wolfPauseRecoveryActiveReady: function (o) {
            checkStop();o=o||lastObservation;
            return !!(request&&request.mission==='recover'&&wolfContinueAttempted&&o&&o.session===request.session&&lastObservation&&
                o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&actOneWolfRecoveryActiveHud(o,Date.now()));
        },
        wolfRecoveryFoodStage: function (o) { checkStop();return wolfRecoveryFoodStageFor(o||lastObservation); },
        recoverWolfFoodAction: async function (stage) {
            checkStop();var o=lastObservation,actual=wolfRecoveryFoodStageFor(o);
            if(!request||request.mission!=='recover'||!o||o.session!==request.session||stage!==actual)
                throw new Error('Fresh same-session Wolf Food state required for one recovery action');
            var reports=wolfRecoveryFoodReports(),event=null,target=null;
            if(stage==='use') {
                if(wolfRecoveryFoodUseAttempted) throw new Error('Wolf Food Use already attempted');
                target=actOneWolfRecoveryFoodUseTarget(o,Date.now());if(!target)throw new Error('Fresh unique Sweet Madame Use button required');
                wolfRecoveryFoodUseAttempted=true;event={type:'wolfRecoveryFoodUse',frameId:o.frameId,x:target.x,y:target.y,startedAt:Date.now()};events.push(event);click(target.x,target.y);return;
            }
            if(stage==='selectKaeya') {
                if(wolfRecoveryFoodSelectAttempted) throw new Error('Wolf Food Kaeya selection already attempted');
                target=actOneWolfKaeyaFoodTarget(o,Date.now());if(!target)throw new Error('Fresh Traveler Sweet Madame modal required');
                wolfRecoveryFoodSelectAttempted=true;event={type:'wolfRecoveryFoodSelectKaeya',frameId:o.frameId,x:target.x,y:target.y,startedAt:Date.now()};events.push(event);click(target.x,target.y);return;
            }
            if(stage==='feedKaeya') {
                if(wolfRecoveryFoodFeedAttempted) throw new Error('Wolf Kaeya food confirmation already attempted');
                target=actOneWolfFeedKaeyaTarget(o,Date.now());if(!target)throw new Error('Fresh Kaeya quantity-one Sweet Madame modal required');
                wolfRecoveryFoodFeedAttempted=true;event={type:'wolfRecoveryFoodFeedKaeya',frameId:o.frameId,x:target.x,y:target.y,quantity:1,quantitySource:o.hud.foodQuantity.source,startedAt:Date.now()};
                events.push(event);click(target.x,target.y);return;
            }
            if(stage==='close') {
                if(wolfRecoveryFoodCloseAttempted) throw new Error('Wolf Food close already attempted');
                if(!wolfRecoveryFoodEventUsed(reports,'wolfRecoveryFoodFeedKaeya')||!actOneWolfRecoveryFoodSafe(o,Date.now())||
                   !actOneWolfFoodInventoryReady(o,Date.now())) throw new Error('Prior food attempt and exact Food inventory without Confirm required before close');
                wolfRecoveryFoodCloseAttempted=true;event={type:'wolfRecoveryFoodClose',key:'VK_ESCAPE',frameId:o.frameId,startedAt:Date.now()};events.push(event);
                await boundedKey('VK_ESCAPE',60);return;
            }
            throw new Error('Unsupported Wolf Food recovery stage');
        },
        wolfRecoveryFoodActiveReady: function (o) {
            checkStop();o=o||lastObservation;
            var reports=request&&request.session?wolfRecoveryFoodReports():[];
            return !!(request&&request.mission==='recover'&&o&&o.session===request.session&&lastObservation&&o.frameId===lastObservation.frameId&&
                o.timestamp===lastObservation.timestamp&&(wolfRecoveryFoodCloseAttempted||wolfRecoveryFoodEventUsed(reports,'wolfRecoveryFoodClose'))&&
                actOneWolfEntryProven(reports,request.session)&&actOneWolfRecoveryActiveHud(o,Date.now()));
        },
        wolfDomainAction: async function () {
            checkStop();
            var actions={wolfForward:['VK_W',800],wolfForwardFine:['VK_W',200],wolfAdvance:['VK_W',500],wolfLeft:['VK_A',600],wolfRight:['VK_D',600],wolfPause:['VK_ESCAPE',60]};
            var action=request&&actions[request.step];
            var pause=request&&request.step==='wolfPause';
            if(!request||request.mission!=='questStep'||(!action&&!/^wolfLook(Right|Left|Down|Up)$/.test(request.step))) throw new Error('Fresh safe Wolf trial HUD required');
            var lookDelta=actOneWolfLookDelta(request.step,request.lookAmount,Object.prototype.hasOwnProperty.call(request,'lookAmount'));
            if(
                !(pause?actOneWolfPauseHud(lastObservation,Date.now()):actOneWolfDomainHud(lastObservation,Date.now()))) throw new Error('Fresh safe Wolf trial HUD required');
            if(request.step==='wolfAdvance') { var advance=actOneWolfAdvanceState(lastObservation,Date.now());if(!advance.ok)throw new Error(advance.reason); }
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session Wolf entry required');
            if(lastObservation.hud.interact&&request.step!=='wolfPause') throw new Error('Inspect available Wolf interaction before moving');
            if(action&&request.step!=='wolfPause'&&(lastObservation.hud.enemyBars||[]).length)throw new Error('Enemy acquired; use bounded Wolf combat');
            if(action)return boundedKey(action[0],action[1]);
            var dx=lookDelta.dx,dy=lookDelta.dy;events.push({type:'rotate',dx:dx,dy:dy,startedAt:Date.now()});moveMouseBy(dx,dy);
        },
        wolfKaeyaSkillSelect: async function () {
            checkStop();
            if(!request||request.mission!=='questStep'||request.step!=='wolfKaeyaSkill'||!actOneWolfDomainHud(lastObservation,Date.now()))
                throw new Error('Fresh safe Wolf trial HUD required before selecting Kaeya');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session Wolf entry required');
            return boundedKey('VK_3',60);
        },
        wolfKaeyaSkillCast: async function () {
            checkStop();
            if(!request||request.mission!=='questStep'||request.step!=='wolfKaeyaSkill'||!actOneWolfKaeyaSkillReady(lastObservation,Date.now()))
                throw new Error('Fresh Wolf trial with captured Kaeya max HP 1427 required before skill');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session Wolf entry required');
            return boundedKey('VK_E',60);
        },
        wolfInventoryContinueReady: function (o) { return !!actOneWolfInventoryContinueTarget(o||lastObservation,Date.now()); },
        wolfFoodInventoryReady: function (o) { return actOneWolfFoodInventoryReady(o||lastObservation,Date.now()); },
        wolfChestReady: function (o) { return actOneWolfChestReady(o||lastObservation,Date.now()); },
        wolfChestContinueReady: function (o) { return !!actOneWolfResumeSeedTarget(o||lastObservation,Date.now()); },
        wolfChestInteract: async function () {
            checkStop();var o=lastObservation;
            if(wolfChestAttempted||!request||request.mission!=='questStep'||request.step!=='wolfChestInteract'||!o||o.session!==request.session||!actOneWolfChestReady(o,Date.now()))
                throw new Error('Fresh healthy Trial Kaeya and unique Common Chest interaction required');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session Wolf entry required before opening a chest');
            wolfChestAttempted=true;
            return boundedKey('VK_F',60);
        },
        wolfLootContinueReady: function (o) { return !!actOneWolfResumeSeedTarget(o||lastObservation,Date.now()); },
        wolfLootReady: function (o,baseline) { return !!actOneWolfLootTarget(o||lastObservation,Date.now(),baseline); },
        wolfLootInteract: async function (baseline) {
            checkStop();var o=lastObservation,name=actOneWolfLootTarget(o,Date.now(),baseline);
            if(wolfLootCount>=4||!request||request.mission!=='questStep'||request.step!=='wolfLootInteract'||!o||o.session!==request.session||o.frameId===wolfLootFrame||!name)
                throw new Error('Fresh selected known Wolf chest loot and bounded pickup required');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session Wolf entry required before collecting loot');
            wolfLootCount++;wolfLootFrame=o.frameId;events.push({type:'wolfLootInteract',name:name,frameId:o.frameId,startedAt:Date.now()});
            await boundedKey('VK_F',60);return name;
        },
        wolfKaeyaFoodReady: function (o) { return !!actOneWolfKaeyaFoodTarget(o||lastObservation,Date.now()); },
        wolfKaeyaFoodSelected: function (o) { return actOneWolfKaeyaFoodSelected(o||lastObservation,Date.now()); },
        wolfFeedKaeyaReady: function (o) { return !!actOneWolfFeedKaeyaTarget(o||lastObservation,Date.now()); },
        wolfFeedKaeya: function () {
            checkStop();var o=lastObservation,target=actOneWolfFeedKaeyaTarget(o,Date.now());
            if(wolfFeedKaeyaAttempted||!request||request.mission!=='questStep'||request.step!=='wolfFeedKaeya'||!o||o.session!==request.session||!target)
                throw new Error('Fresh Kaeya Sweet Madame modal with quantity-one crop required');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session Wolf entry required');
            wolfFeedKaeyaAttempted=true;
            events.push({type:'wolfFeedKaeya',frameId:o.frameId,x:target.x,y:target.y,quantity:1,quantitySource:o.hud.foodQuantity.source,startedAt:Date.now()});
            click(target.x,target.y);
        },
        wolfSelectKaeyaFood: function () {
            checkStop();var o=lastObservation,target=actOneWolfKaeyaFoodTarget(o,Date.now());
            if(wolfKaeyaFoodAttempted||!request||request.mission!=='questStep'||request.step!=='wolfSelectKaeyaFood'||!o||o.session!==request.session||!target)
                throw new Error('Fresh known Sweet Madame and Traveler food modal required');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session Wolf entry required');
            wolfKaeyaFoodAttempted=true;
            events.push({type:'wolfSelectKaeyaFood',frameId:o.frameId,x:target.x,y:target.y,startedAt:Date.now()});
            click(target.x,target.y);
        },
        wolfInventoryContinue: function () {
            checkStop();var o=lastObservation,target=actOneWolfInventoryContinueTarget(o,Date.now());
            if(wolfInventoryContinueAttempted||!request||request.mission!=='questStep'||request.step!=='wolfInventoryRecover'||!o||o.session!==request.session||!target)
                throw new Error('Fresh exact Wolf pause menu required for inventory recovery');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session Wolf entry required');
            wolfInventoryContinueAttempted=true;
            events.push({type:'wolfContinue',frameId:o.frameId,x:Math.round(target.x+target.width/2),y:Math.round(target.y+target.height/2),startedAt:Date.now()});
            click(Math.round(target.x+target.width/2),Math.round(target.y+target.height/2));
        },
        wolfInventoryOpen: async function () {
            checkStop();var o=lastObservation,continued=events.some(function(e){return e&&e.type==='wolfContinue';});
            if(wolfInventoryOpenAttempted||!wolfInventoryContinueAttempted||!continued||!request||request.mission!=='questStep'||request.step!=='wolfInventoryRecover'||
               !o||o.session!==request.session||Date.now()-o.timestamp>1000||!actOneWolfInventoryContinueTarget(o,Date.now()))
                throw new Error('Immediate verified Wolf Continue required before opening inventory');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session Wolf entry required');
            wolfInventoryOpenAttempted=true;
            events.push({type:'wolfInventoryOpen',frameId:o.frameId,startedAt:Date.now()});
            return boundedKey('VK_B',60);
        },
        wolfContinue: function () {
            checkStop();var target=actOneWolfResumeSeedTarget(lastObservation,Date.now());
            if(wolfContinueAttempted||!request||request.mission!=='questStep'||['wolfContinue','wolfChestInteract','wolfLootInteract'].indexOf(request.step)<0||!target)throw new Error('Fresh unique Wolf pause menu required');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session))throw new Error('Same-session Wolf entry required');
            wolfContinueAttempted=true;events.push({type:'wolfContinue',frameId:lastObservation.frameId,startedAt:Date.now()});click(Math.round(target.x+target.width/2),Math.round(target.y+target.height/2));
        },
        wolfCombatKey: async function(key) {
            checkStop();
            if(!request||request.mission!=='questStep'||request.step!=='wolfCombat'||!actOneWolfDomainHud(lastObservation,Date.now())||['VK_3','VK_E','VK_LBUTTON'].indexOf(key)<0||!(lastObservation.hud.enemyBars||[]).length)throw new Error('Fresh healthy Wolf trial and enemy evidence required');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session))throw new Error('Same-session Wolf entry required');
            return boundedKey(key,60);
        },
        wolfBurstContinueReady: function(o) {
            checkStop();o=o||lastObservation;
            if(wolfBurstContinueAttempted||wolfBurstQAttempted||wolfBurstRecoveryPriorQ()||!wolfBurstRecoveryCurrent(o)||
               !actOneWolfResumeSeedTarget(o,Date.now())) return false;
            var pauseHud=o.hud;
            if(!pauseHud||pauseHud.world!==false||pauseHud.journal!==false||pauseHud.bigMap!==false||pauseHud.auto!==false||
               pauseHud.dialogueReady!==false||pauseHud.choice!==false||pauseHud.objectiveChanged!==false||pauseHud.tutorialStep!==null||
               pauseHud.loading===true||pauseHud.unknownHud===true||pauseHud.climbing===true) return false;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            return actOneWolfEntryProven(reports,request.session);
        },
        wolfBurstRecoveryContinue: function() {
            checkStop();var o=lastObservation,target=actOneWolfResumeSeedTarget(o,Date.now());
            if(!this.wolfBurstContinueReady(o)||!target) throw new Error('Fresh same-session exact Wolf pause required before burst recovery Continue');
            wolfBurstContinueAttempted=true;
            var event={type:'wolfBurstRecoveryContinue',frameId:o.frameId,x:Math.round(target.x+target.width/2),
                y:Math.round(target.y+target.height/2),startedAt:Date.now()};events.push(event);click(event.x,event.y);event.finishedAt=Date.now();
        },
        wolfBurstRecoveryRetrySafe: function(o) {
            checkStop();o=o||lastObservation;
            if(!wolfBurstContinueAttempted||wolfBurstQAttempted||wolfBurstRecoveryPriorQ()||!wolfBurstRecoveryCurrent(o)||
               !actOneWolfBurstRecoveryBase(o,Date.now(),0.3)) return false;
            var rows=o.ocr||[],kaeya=rows.filter(function(r){return String(r.text||'').trim()==='Kaeya'&&r.x>1550&&r.y>300&&r.y<600;}),
                trial=rows.filter(function(r){return String(r.text||'').trim()==='Trial'&&r.x>1700&&r.y>300&&r.y<600;});
            return kaeya.length!==1||trial.length!==1;
        },
        wolfBurstRecoveryQReady: function(o) {
            checkStop();o=o||lastObservation;
            if(!wolfBurstContinueAttempted||wolfBurstQAttempted||wolfBurstRecoveryPriorQ()||!wolfBurstRecoveryCurrent(o)||
               !actOneWolfBurstRecoveryQHud(o,Date.now(),0.3)) return false;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            return actOneWolfEntryProven(reports,request.session);
        },
        wolfBurstRecoveryQ: async function() {
            checkStop();var o=lastObservation;
            if(!this.wolfBurstRecoveryQReady(o)) throw new Error('Fresh safe Wolf HUD and one-shot burst recovery authorization required');
            wolfBurstQAttempted=true;
            wolfBurstRecoveryPersistQAttempt(o);
            var event={type:'wolfBurstRecoveryQAttempt',key:'VK_Q',frameId:o.frameId,startedAt:Date.now()};events.push(event);
            try {await boundedKey('VK_Q',60);} finally {event.finishedAt=Date.now();}
        },
        wolfBurstRecoveryPauseReady: function(o) {
            checkStop();o=o||lastObservation;
            return !!(wolfBurstContinueAttempted&&wolfBurstQAttempted&&!wolfBurstPauseAttempted&&wolfBurstRecoveryCurrent(o)&&
                actOneWolfBurstRecoveryActiveHud(o,Date.now(),0));
        },
        wolfBurstRecoveryEscape: async function() {
            checkStop();var o=lastObservation;
            if(!this.wolfBurstRecoveryPauseReady(o)) throw new Error('Fresh unambiguous Wolf HUD required before explicit recovery pause');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session Wolf entry required');
            wolfBurstPauseAttempted=true;
            var event={type:'wolfBurstRecoveryEscape',key:'VK_ESCAPE',frameId:o.frameId,startedAt:Date.now()};events.push(event);
            try {await boundedKey('VK_ESCAPE',60);} finally {event.finishedAt=Date.now();}
        },
        wolfBurstRecoveryPauseVerified: function(o) {
            checkStop();o=o||lastObservation;
            if(!wolfBurstPauseAttempted||!wolfBurstRecoveryCurrent(o)||!actOneWolfResumeSeedTarget(o,Date.now())) return false;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            return actOneWolfEntryProven(reports,request.session);
        },
        wolfCombatSeek: async function(kind,frameId,dx,durationMs) {
            checkStop();var o=lastObservation,h=o&&o.hud,bars=h&&h.enemyBars||[],hp=h&&h.health;
            var target=bars.length===1?bars[0]:null,barSizeOk=target&&Number.isFinite(Number(target.width))&&Number.isFinite(Number(target.height))&&
                (actOneEnemyBarSize(Number(target.width),Number(target.height))||
                 (Number(target.width)>=2&&Number(target.width)<=300&&Number(target.height)>12&&Number(target.height)<=20));
            var targetAnchored=!!(barSizeOk&&Number.isFinite(Number(target.x))&&Number.isFinite(Number(target.y))&&
                (actOneEnemyBarAnchored(target,o.ocr||[],5)||actOneEnemyBarDiagnosticAnchored(target,h.enemyBarDiagnostic,5)));
            if(!request||request.mission!=='questStep'||request.step!=='wolfCombat'||!o||o.session!==request.session||
               o.frameId!==frameId||!Number.isFinite(Number(o.timestamp))||Date.now()<Number(o.timestamp)||Date.now()-o.timestamp>1000||
               !actOneWolfDomainHud(o,Date.now())||!h||h.auto===true||h.loading===true||h.unknownHud===true||h.objectiveChanged===true||
               h.world!==false||h.climbing!==false||h.auto!==false||h.journal!==false||h.bigMap!==false||h.dialogueReady!==false||
               h.choice!==false||h.objectiveChanged!==false||h.interact!==false||h.tutorialStep||
               (o.ocr||[]).some(function(r){return r.text&&(/^(Party Setup|Domain Entrance)$/.test(r.text.trim())||
                 /\b(loading|entering|connecting|preparing)\b/i.test(r.text.trim()));})||!hp||hp.max!==1427||
               !Array.isArray(bars)||bars.length!==1||!targetAnchored||
               target.x<600||target.x>1350||target.y<250||target.y>650||wolfCombatSeekFrames.indexOf(frameId)>=0)
                throw new Error('Fresh unique Wolf target and Trial Kaeya evidence required for bounded approach');
            var event={type:'wolfCombatSeek',kind:kind,frameId:frameId,startedAt:Date.now()};
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session))throw new Error('Same-session Wolf entry required');
            if(kind==='forward') {
                if(wolfCombatSeekForwards>=4||target.x<850||target.x>1070||durationMs!==250)
                    throw new Error('Centered Wolf target and remaining 250 ms approach allowance required');
                wolfCombatSeekForwards++;event.durationMs=250;events.push(event);
                try {await boundedKey('VK_W',250);} finally {event.finishedAt=Date.now();wolfCombatSeekFrames.push(frameId);}
                return;
            }
            if(kind==='turn') {
                if(wolfCombatSeekTurns>=2||target.x>=850&&target.x<=1070||!Number.isInteger(dx)||dx===0||Math.abs(dx)>32||
                   Math.sign(dx)!==Math.sign(target.x-960)||durationMs!==0)
                    throw new Error('Valid bounded Wolf camera correction required');
                wolfCombatSeekTurns++;event.dx=dx;event.dy=0;events.push(event);
                try {ready();moveMouseBy(dx,0);checkStop();} finally {event.finishedAt=Date.now();wolfCombatSeekFrames.push(frameId);}
                return;
            }
            throw new Error('Unsupported bounded Wolf approach action');
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
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session Wolf entry required');
            return boundedKey('VK_SPACE',60);
        },
        wolfEntryForward: async function () {
            checkStop();
            if(!request||request.mission!=='questStep'||request.step!=='wolfEntryApproach'||!actOneWolfEntryHud(lastObservation,Date.now())||lastObservation.hud.interact) throw new Error('Fresh safe Wolf entrance HUD required');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session verified Wolf entry required');
            await boundedKey('VK_W',800);
        },
        startWolfParty: function () {
            checkStop();ready();
            if(!request||request.mission!=='questStep'||request.step!=='wolfPartyStart') throw new Error('Wolf party start request required');
            var reports=file.readTextSync('reports/'+request.session+'.jsonl').split(/\r?\n/).filter(function(line){return line.trim().length>0;}).map(function(line){return JSON.parse(line);});
            var target=actOneWolfPartyTarget(lastObservation,Date.now(),reports,request.session);
            if(!target) throw new Error('Fresh Wolf party setup and uninterrupted same-session entrance required');
            // actOneWolfPartyTarget admits this click only after a same-session
            // exact Wolf entrance receipt and uninterrupted party transition.
            // Preserve that validated domain identity in the durable event.
            events.push({type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:lastObservation.frameId,x:target.x,y:target.y,startedAt:Date.now()});
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
            enemyBarDiagnostic=null;ocrPrimitiveMs=0;ocrReadCount=0;
            var t0 = Date.now(), img = captureGameRegion(), captureMs = Date.now() - t0;
            try {
                if (Number(img.width) !== 1920 || Number(img.height) !== 1080) throw new Error('1920x1080 capture required');
                var o0 = Date.now(), rows = readRows(img, 0, 0, 1920, 1080);
                var fullOcrMs = Date.now() - o0, health0 = Date.now(), healthRead = readHealth(img, rows), healthRows = healthRead.rows;
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
                if(actOneWolfInfoKind(rows)) tutorialStep='wolfInfo';
                if(actOneFalconInfo(rows)) tutorialStep='falconInfo';
                if (/Press R to enter\/exit aiming mode/i.test(text) && /Use Amber to defeat the airborne/i.test(text)) tutorialStep = 'enterAim';
                if (/Move cursor to aim. Try attacking the floating Anemo Slime/i.test(text) && /Use Amber to defeat the airborne/i.test(text)) tutorialStep = 'aimSlime';
                if (/Press R again to exit aiming mode/i.test(text) && /Go to the location designated by Amber/i.test(text)) tutorialStep = 'exitAim';
                var combatObjective = objectiveRows.some(function(r){return ['Defeat the nearby hilichurls','Clear out the nearby hilichurl camp'].indexOf(r.text.trim())>=0;});
                if(journal&&actOneNavigateQuestState(rows)) tutorialStep='navigateQuest';
                var trackQuest=actOneTrackQuestState(rows);
                if(trackQuest) tutorialStep='trackQuest';
                var recoverWolfAnchor=rows.some(function(r){return (r.text.trim()==='Lumina'||r.text.trim()==='Amber')&&r.x>1550&&r.y>300&&r.y<600;});
                var recoverWolfProven=false;
                if(request&&request.mission==='recover'&&!tutorialStep&&!actOneWolfInfoKind(rows)&&!pos&&hp&&hp.max>0&&hp.current>0&&hp.current<=hp.max&&
                   !auto&&!journal&&!bigMap&&!choice&&!actOneDialogueReady(rows,choice)&&!actOneEnterGameLoading(rows)&&recoverWolfAnchor) {
                    try { recoverWolfProven=actOneWolfEntryProven(JSON.parse(file.readTextSync('reports/'+request.session+'.json')),request.session); } catch (proofReadError) { recoverWolfProven=false; }
                }
                var recoverWolfSafe=!!recoverWolfProven;
                var recoverWolfFoodDomainRequest=!!(request&&request.mission==='recover'&&(wolfContinueAttempted||wolfRecoveryFoodCloseAttempted));
                var safeWorldCandidate=!!pos&&!!hp&&!auto&&!journal&&!bigMap;
                if(!tutorialStep&&actOneGlideForwardState(rows,pos,hp,{world:safeWorldCandidate,auto:auto,journal:journal,bigMap:bigMap,
                    dialogueReady:actOneDialogueReady(rows,choice),choice:auto&&choice,objectiveChanged:/objective updated|quest completed/i.test(text)})) tutorialStep='glideForward';
                if(!tutorialStep&&actOneGlideOpenState(rows,pos,hp,{world:safeWorldCandidate,auto:auto,journal:journal,bigMap:bigMap,
                    dialogueReady:actOneDialogueReady(rows,choice),choice:auto&&choice,objectiveChanged:/objective updated|quest completed/i.test(text)})) tutorialStep='glideOpen';
                var controlOcrMs=0;
                if((pos||(request&&request.mission==='questStep'&&/^(falcon|wolf)/.test(request.step))||recoverWolfSafe||recoverWolfFoodDomainRequest)&&hp&&!auto&&!journal&&!bigMap&&!(auto&&choice)&&!tutorialStep&&
                   (!request||request.mission!=='recover'||recoverWolfSafe)&&actOneNeedsControlCrop(rows)) {
                    var control0=Date.now(),controlLocal=scaledRows(img,1520,985,390,80);
                    rows=actOneMergeControlCropRows(rows,controlLocal,1520,985);
                    controlOcrMs=Date.now()-control0;ocrMs=Date.now()-o0;
                }
                var wolfPartyRequest=request&&request.mission==='questStep'&&
                    (request.step==='wolfEntryApproach'||/^wolf(Combat|BurstRecovery|Forward|ForwardFine|Advance|Left|Right|LookRight|LookLeft|LookDown|LookUp|Pause|Continue|Info|OpeningDialogue|KaeyaSkill|ChestInteract|LootInteract|WindTakeoff|WindRide|GlideForward|ConsoleInteract|ApproachEnemy)$/.test(request.step));
                wolfPartyRequest=wolfPartyRequest||recoverWolfSafe||recoverWolfFoodDomainRequest;
                var falconPartyRequest=request&&request.mission==='questStep'&&/^falcon/.test(request.step);
                var wolfPartyAllowed=!auto&&!journal&&!bigMap&&!choice&&!tutorialStep&&!actOneDialogueReady(rows,choice);
                if(!pos&&hp&&!auto&&!journal&&!bigMap&&(falconPartyRequest||wolfPartyRequest)&&(!wolfPartyRequest||wolfPartyAllowed)) {
                    var falconPartyMissing=falconPartyRequest&&(!rows.some(function(r){return /^[A\u00c1]mber$/.test(r.text.trim())&&r.x>1550&&r.y>300&&r.y<600;})||
                        !rows.some(function(r){return r.text.trim()==='Trial'&&r.x>1700&&r.y>300&&r.y<600;}));
                    var wolfEntryRequest=request.step==='wolfEntryApproach';
                    var wolfRequired=wolfEntryRequest?['Lumina','Amber']:['Kaeya','Trial'];
                    var wolfMissing=wolfPartyRequest&&wolfRequired.some(function(name){
                        return !rows.some(function(r){return r.text.trim()===name&&r.x>(name==='Trial'?1700:1550)&&r.y>300&&r.y<600;});
                    });
                    if(falconPartyMissing||wolfMissing) {
                        var partyRows=scaledRows(img,1630,330,230,wolfPartyRequest?300:160);
                        rows=actOneMergeControlCropRows(rows,partyRows,1630,330);ocrMs=Date.now()-o0;
                    }
                }
                var climbing=rows.some(function(r){return r.text.trim()==='X' && r.x>1500 && r.y>990;}) && rows.some(function(r){return r.text.trim()==='Space' && r.x>1600 && r.y>990;});
                var dialogueReady=actOneDialogueReady(rows,choice), objectiveChanged=/objective updated|quest completed/i.test(text),aerialBoss=null,interactionOcrMs=0;
                var interactionScreen={objective:interactionObjective,world:!!(!trackQuest&&pos&&hp&&!auto&&!journal&&!bigMap&&!dialogueReady&&!(auto&&choice)),
                    position:!!pos,health:hp,auto:auto,journal:journal,bigMap:bigMap,dialogueReady:dialogueReady,choice:auto&&choice,
                    climbing:climbing,objectiveChanged:objectiveChanged,tutorialStep:tutorialStep};
                var statueInteractionScreen={auto:auto,journal:journal,bigMap:bigMap,dialogueReady:dialogueReady,choice:choice,
                    climbing:climbing,objectiveChanged:objectiveChanged,tutorialStep:tutorialStep,groundControls:actOneGroundControlEvidence(rows)};
                if(actOneShouldReadInteractionCrop(rows,interactionObjective,interactionScreen)||
                   actOneShouldReadStatueInteractionCrop(rows,statueInteractionScreen)) {
                    var interaction0=Date.now(),interactionLocal=scaledRows(img,1080,490,90,100);
                    var interactionF=actOneInteractionCropF(interactionLocal,1080,490);
                    if(interactionF) rows=rows.concat([interactionF]);
                    interactionOcrMs=Date.now()-interaction0;ocrMs=Date.now()-o0;
                }
                var wolfOpenDoorScreen={world:false,groundControls:actOneGroundControlEvidence(rows),auto:auto,journal:journal,bigMap:bigMap,
                    dialogueReady:dialogueReady,choice:auto&&choice,climbing:climbing,objectiveChanged:objectiveChanged,tutorialStep:tutorialStep,
                    loading:actOneEnterGameLoading(rows),unknownHud:false,health:hp};
                var wolfOpenDoorRequest=!!(request&&request.mission==='questStep'&&request.step==='wolfConsoleInteract'&&pos===null&&hp&&!auto&&!journal&&!bigMap&&!tutorialStep);
                if(wolfOpenDoorRequest) {
                    try {wolfOpenDoorRequest=actOneWolfEntryProven(JSON.parse(file.readTextSync('reports/'+request.session+'.json')),request.session);} catch(wolfDoorProofError) {wolfOpenDoorRequest=false;}
                }
                if(wolfOpenDoorRequest&&actOneShouldReadWolfOpenDoorCrop(rows,wolfOpenDoorScreen)) {
                    var wolfDoorOcr0=Date.now(),wolfDoorLocal=scaledRows(img,1080,490,90,100);
                    var wolfDoorF=actOneInteractionCropF(wolfDoorLocal,1080,490);
                    if(wolfDoorF) rows=rows.concat([wolfDoorF]);
                    interactionOcrMs+=Date.now()-wolfDoorOcr0;ocrMs=Date.now()-o0;
                }
                var aerialBossVisible=!pos&&actOneAerialBossLabels(rows)&&!auto&&!journal&&!bigMap&&!dialogueReady&&!(auto&&choice);
                if(aerialBossVisible) {
                    var aerialFraction=readAerialBossBar(img);
                    var aerialScreen={journal:journal,bigMap:bigMap,dialogueReady:dialogueReady,choice:auto&&choice,objectiveChanged:objectiveChanged,
                        lowHealth:!hp||hp.max<=0||hp.current>hp.max||hp.current/hp.max<0.6};
                    if(actOneAerialBossState(rows,null,hp,aerialScreen,aerialFraction)) aerialBoss={barFraction:aerialFraction};
                }
                var foodQuantity=null;
                var recoverFoodModal=false;
                if(request&&request.mission==='recover'&&pos===null) {
                    try {
                        var recoveryFoodReports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
                        recoverFoodModal=actOneWolfEntryProven(recoveryFoodReports,request.session)&&
                            actOneWolfRecoveryFoodSafe({timestamp:Date.now(),map:null,hud:{world:false,health:hp,journal:journal,bigMap:bigMap,
                                dialogueReady:dialogueReady,choice:auto&&choice,climbing:climbing,auto:auto,tutorialStep:tutorialStep,
                                objectiveChanged:objectiveChanged},ocr:rows},Date.now())&&
                            actOneKnownSafeFoodBoundary({timestamp:Date.now(),map:null,hud:{world:false},ocr:rows},Date.now())&&
                            rows.filter(function(r){return r.text.trim()==='Kaeya'&&r.x>800&&r.x<1000&&r.y>240&&r.y<320;}).length===1;
                    } catch(recoveryFoodError) { recoverFoodModal=false; }
                }
                if((request&&request.mission==='questStep'&&request.step==='wolfFeedKaeya'||recoverFoodModal)&&pos===null&&
                   rows.filter(function(r){return r.text.trim()==='Kaeya'&&r.x>800&&r.x<1000&&r.y>240&&r.y<320;}).length===1&&
                   rows.filter(function(r){return r.text.trim()==='Sweet Madame'&&r.x>1300&&r.x<1650&&r.y>110&&r.y<180;}).length===1&&
                   actOneKnownSafeFoodBoundary({timestamp:Date.now(),map:null,hud:{world:false},ocr:rows},Date.now())) {
                    var quantityRows=scaledRows(img,1105,590,80,80).map(function(r){return {text:String(r.text||'').trim(),
                        x:1105+Number(r.x)/3,y:590+Number(r.y)/3,width:Number(r.width)/3,height:Number(r.height)/3};});
                    var digits=quantityRows.filter(function(r){return /^\d+$/.test(r.text);});
                    if(digits.length===1&&digits[0].text==='1'&&digits[0].x>1125&&digits[0].x<1165&&digits[0].y>605&&digits[0].y<655)
                        foodQuantity={value:1,source:'scaled-same-frame',frameId:frame,x:digits[0].x,y:digits[0].y};
                }
                var hud = { foodQuantity:foodQuantity, auto:auto, climbing:climbing, groundControls:actOneGroundControlEvidence(rows), enemyBars: combatObjective ? readEnemyBars(img, rows) : request&&/^falcon(Combat|AmberCombat|Ranged|Engage)$/.test(request.step) ? readEnemyBars(img,rows,4) : request&&request.mission==='questStep'&&/^wolf(Combat|Forward|ForwardFine|Advance|Right|Left|LookRight|LookLeft|LookDown|LookUp|Pause|Continue|Info|OpeningDialogue|KaeyaSkill|TurretPass|ChestInteract|LootInteract|ConsoleInteract|ApproachEnemy)$/.test(request.step)&&hp&&!auto&&!journal&&!bigMap ? readEnemyBars(img,rows,5) : [], aerialBossVisible:aerialBossVisible, aerialBoss:aerialBoss, slimeTarget: tutorialStep === 'aimSlime' ? readSlime(img) : null, tutorialStep: tutorialStep, characterAcquired: acquired.length === 1 ? acquired[0].text.trim() : null, dialogueReady: dialogueReady, choice: auto && choice, journal: journal, bigMap: bigMap,
                    objectiveChanged: /objective updated|quest completed/i.test(text), health: hp, healthOcr: healthRows.map(function (r) { return r.text; }), healthDiagnostic:healthRead.diagnostic,
                    healthPct: hp && hp.max > 0 ? hp.current / hp.max : null,
                    lowHealth: !hp || hp.max <= 0 || hp.current > hp.max || hp.current / hp.max < 0.6,
                    world: !trackQuest && !!pos && !!hp && !auto && !journal && !bigMap,
                    interact: rows.some(function (r) { return (/^F$/.test(r.text.trim()) && r.x > 850 && r.y > 300 && r.y < 800) || (/^Teleport[- ]Waypoint$/i.test(r.text.trim()) && r.x>1100 && r.y>400 && r.y<700); }),
                    objectives: objectiveRows.map(function (r) { return r.text; }) };
                if (pos && request && request.objective === 'Investigate what Paimon has found') hud.worldMarker = readMarker(img);
                hud.enemyBarDiagnostic=enemyBarDiagnostic;
                ready();
                lastObservation = { session: session, frameId: frame, timestamp: Date.now(), capturedAt: t0, screenshotPath: png, ocr: rows, map: trackQuest ? null : pos, mapDiagnostic:mapDiagnostic, hud: hud,
                    // ocrMs is a legacy cumulative window and can overlap later PNG/map work on fallback paths.
                    // ocrFindMultiMs times only OCR findMulti calls; it excludes image preparation and postprocessing.
                    timings: { mapDiagnostic:mapDiagnostic, captureMs: captureMs, ocrMs: ocrMs, ocrFindMultiMs:ocrPrimitiveMs, ocrReadCount:ocrReadCount, fullOcrMs: fullOcrMs, healthOcrMs: healthOcrMs, objectiveOcrMs: objectiveOcrMs, controlOcrMs:controlOcrMs, interactionOcrMs:interactionOcrMs, objectiveSource: reusedObjectiveRows ? 'fullFrame' : 'crop', pngWriteMs: pngMs, mapMs: mapMs, totalMs: Date.now() - t0 } };
                return lastObservation;
            } finally { dispose(img); }
        }
    };
}
