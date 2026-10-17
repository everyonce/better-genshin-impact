function actTwoUntrackedRegionalGround(h){return !!(h&&h.groundControls&&!h.climbing&&h.health&&Number.isFinite(h.health.current)&&h.health.current>=4015*.7&&h.health.current<=4015&&h.health.max===4015&&Array.isArray(h.enemyBars)&&h.enemyBars.every(b=>b&&[b.x,b.y,b.width,b.height,b.rectangularity].every(Number.isFinite)&&b.x>=350&&b.x<=1600&&b.y>=100&&b.y<=900&&b.width>=2&&b.width<=300&&b.height>=3&&b.height<=20&&b.rectangularity>=.8&&b.rectangularity<=1.05)&&Array.isArray(h.objectives)&&h.objectives.every(t=>String(t).replace(/[^A-Za-z]/g,'').length<=5));}
function actTwoHideoutClimbMap(o,now,session){
 var h=o&&o.hud,r=o&&o.ocr||[];
 return !!(o&&o.session===session&&now>=o.timestamp&&now-o.timestamp<=1000&&h&&h.climbing&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&h.health&&h.health.current===4015&&h.health.max===4015&&Array.isArray(h.enemyBars)&&!h.enemyBars.length&&(h.objectives||[]).some(t=>t.replace(/\s/g,'')==="EnterRaptor'sHideout")&&actTwoOriginalAccount(r)&&r.some(t=>t.text==='X'&&t.x>1550&&t.y>980)&&r.some(t=>t.text==='Space'&&t.x>1650&&t.y>980));
}
function actTwoRepairHideoutObjective(rows,hud){
    var exact="Enter Raptor's Hideout";
    if(!hud||!Array.isArray(hud.objectives)||(rows||[]).filter(r=>r.text===exact&&r.x>=50&&r.x<=120&&r.y>=240&&r.y<=280).length!==1)return;
    hud.objectives=hud.objectives.map(t=>String(t).normalize('NFD').replace(/[\u0300-\u036f]/g,'')===exact?exact:t);
}
function actTwoRegionalCombatStrategy(avatar,o){var raptor=(o&&o.hud&&o.hud.objectives||[]).some(function(t){return String(t).replace(/\s/g,'')==='Defeattheambush';});return avatar==='Lumina'?(raptor?'English Raptor Anemo':'English Ley Line Anemo'):(raptor?'English Raptor Kaeya':'English Ley Line Defense');}
function actTwoRegionalWorldEvidence(rows,hud){
    return !!(hud&&hud.groundControls&&!hud.climbing&&!hud.auto&&!hud.journal&&!hud.bigMap&&!hud.dialogueReady&&!hud.choice&&hud.health&&hud.health.current>0&&hud.health.current<=hud.health.max&&hud.health.max>0&&((hud.objectives||[]).some(function(t){return ['Defeattheambush','LookforthemarksleftbyRaptor',"EnterRaptor'sHideout"].indexOf(String(t).replace(/\s/g,''))>=0;})||actTwoUntrackedRegionalGround(hud))&&actTwoOriginalAccount(rows)&&(rows||[]).filter(function(r){return /^(Lumina|Amber|Kaeya|Lisa)$/.test(r.text)&&r.x>=1650&&r.y>=240&&r.y<=580;}).length>=2);
}
function actTwoRegionalObservationPlan(request,p){return !!(request&&request.mission==='questStep'&&request.step==='actTwoField'&&p&&p.session===request.session&&p.frameId===request.expectedFrameId&&p.visualPositionReviewed===true&&['actions','combat'].indexOf(p.mode)>=0&&Number.isInteger(p.regionMapFrameId)&&p.regionMapFrameId<p.frameId);}
function actTwoFieldEntrySettled(o){var h=o&&o.hud,p=h&&h.health;return !!(h&&h.world===true&&p&&Number.isFinite(p.current)&&Number.isFinite(p.max)&&p.max>0);}
function actTwoAmbushQuestAnchor(rows) {
    return (rows||[]).find(function(r){return String(r.text||'').replace(/\s/g,'')==='Defeattheambush'&&r.x>=30&&r.x<=100&&r.y>=240&&r.y<=275;})||null;
}
function actTwoAmbushQuestRows(rows, objectiveRows, distanceRows) {
    var anchor=actTwoAmbushQuestAnchor(rows);if(!anchor)return objectiveRows;
    var distances=(distanceRows||[]).filter(function(r){return /^\d{1,3}m[./]?$/.test(String(r.text||'').trim())&&r.x>=75&&r.x<=185&&r.y>=278&&r.y<=310;});
    var unique=distances.map(function(r){return parseInt(r.text,10);}).filter(function(v,i,a){return a.indexOf(v)===i;});
    if(unique.length!==1||unique[0]<1||unique[0]>600)return objectiveRows;
    return [anchor,{text:String(unique[0])+'m',x:distances[0].x,y:distances[0].y,width:distances[0].width,height:distances[0].height}];
}
function actTwoSceneMarkerCandidate(x,y) {return Number.isFinite(x)&&Number.isFinite(y)&&x>=320&&x<=1720&&y>=150&&y<=930&&!(x>=1540&&y>=220&&y<=650);}
function actTwoAmberFinalChoice(rows) {
    if (!Array.isArray(rows)) return false;
    function one(text,x1,x2,y1,y2) { return rows.filter(function(r){return r.text.trim()===text&&r.x>=x1&&r.x<=x2&&r.y>=y1&&r.y<=y2;}).length===1; }
    return one('Auto',80,180,20,70)&&one('Amber',850,1050,830,900)&&
        one('Just keep thinking about that license. Ready...',500,800,900,950)&&
        one('...Go!',1250,1450,750,815)&&one('F',1180,1250,750,820)&&
        one('UID: 693306810',1600,1800,1030,1080);
}
function actTwoCyrusRows(rows){
    if(!Array.isArray(rows)||!rows.some(function(r){return r.text==="Branch Master, Adventurers' Guild"&&r.x>=730&&r.x<=800&&r.y>=890&&r.y<=920;}))return rows;
    var names=rows.filter(function(r){return /^(rus|yrus)$/.test(r.text)&&r.x>=900&&r.x<=1010&&r.y>=850&&r.y<=880;});
    return names.length===1?rows.map(function(r){return r===names[0]?Object.assign({},r,{text:'Cyrus',sourceText:r.text}):r;}):rows;
}
function actTwoAutoCropNeeded(rows){return Array.isArray(rows)&&!rows.some(function(r){return r.text==='Auto'&&r.x<350&&r.y<150;})&&rows.some(function(r){return /^(Kaeya|Paimon|Amber|Lisa|Jean|Venti|Cyrus|Vile|Lynn|Jack|Farrah)$/.test(r.text)&&r.x>=600&&r.x<=1200&&r.y>=820&&r.y<900;});}
function actTwoIndoorSafe(o,now,session){var h=o&&o.hud;return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&actTwoOriginalAccount(o.ocr)&&h&&h.groundControls&&!h.climbing&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&h.health&&h.health.current>=1530&&h.health.max===1700&&!(h.enemyBars||[]).length&&(h.objectives.indexOf('Talk to Kaeya')>=0||o.ocr.some(function(r){return r.text==='Talk to Kaeya'&&r.x>=65&&r.x<=100&&r.y>=240&&r.y<=280;})));}
function actTwoOriginalAccount(rows) {
    var identities=(rows||[]).filter(function(r){return r.x>1600&&r.y>1030&&/^(?:UID)?[: ]*\d{9}(?:C?ape)?$/.test(String(r.text||'').trim());});
    return identities.length>0&&identities.every(function(r){return /693306810(?:C?ape)?$/.test(String(r.text||'').trim());});
}
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
function actOneReconnectTarget(observation, now) {
    if (!observation || !Number.isFinite(observation.timestamp) || !Number.isFinite(now) ||
        now < observation.timestamp || now-observation.timestamp > 1000 ||
        actOneEnterGameAuthPrompt(observation.ocr)) return null;
    var rows=observation.ocr||[];
    function exact(text,x,y,w,h) {
        var matches=rows.filter(function(r){return String(r.text||'').trim()===text;});
        if(matches.length!==1)return null;
        var r=matches[0];
        return Number.isFinite(r.x)&&Number.isFinite(r.y)&&Number.isFinite(r.width)&&Number.isFinite(r.height)&&
            Math.abs(r.x-x)<=30&&Math.abs(r.y-y)<=25&&Math.abs(r.width-w)<=45&&Math.abs(r.height-h)<=15?r:null;
    }
    if(!exact('You have disconnected',736,278,447,43)||!exact('Connection timed out',799,490,321,37))return null;
    var confirm=exact('Confirm',909,734,134,43);
    return confirm?{x:Math.round(confirm.x+confirm.width/2),y:Math.round(confirm.y+confirm.height/2)}:null;
}
function actOneAccountSwitchCloseReady(observation, now, permit, request) {
    if(!observation||!request||!permit||permit.reviewed!==true||permit.consumed===true||
        permit.session!==request.session||permit.frameId!==request.expectedFrameId||
        !/^[0-9]{9}$/.test(permit.currentUid)||!/^[0-9]{9}$/.test(permit.expectedUid)||permit.currentUid===permit.expectedUid||
        !Number.isFinite(permit.createdAt)||now<permit.createdAt||now-permit.createdAt>60000||
        !Number.isFinite(observation.timestamp)||now<observation.timestamp||now-observation.timestamp>1000)return false;
    var rows=observation.ocr||[];
    var uid=rows.filter(function(r){return /^UID\s*:\s*[0-9]{9}$/.test(String(r.text||'').trim())&&r.x>1600&&r.y>1000;});
    return uid.length===1&&uid[0].text.replace(/\s/g,'')==='UID:'+permit.currentUid&&
        rows.some(function(r){return r.text==='Click to claim your daily Blessing of the Welkin Moon rewards'&&r.x>400&&r.x<600&&r.y>800&&r.y<880;});
}
async function actOneAccountSwitchCloseChord(ops) {
    try {
        ops.checkStop();ops.ready();ops.keyDown('VK_MENU');
        ops.checkStop();ops.ready();ops.keyDown('VK_F4');await ops.sleep(80);
    } finally {
        try {ops.keyUp('VK_F4');} finally {ops.keyUp('VK_MENU');}
    }
}
function actOneAccountTitleTarget(observation, now, permit, request) {
    if(!actOneEnterGameTitleFrame(observation,now)||!permit||!request||permit.reviewed!==true||permit.consumed===true||
        permit.session!==request.session||permit.frameId!==request.expectedFrameId||
        !Number.isFinite(permit.createdAt)||now<permit.createdAt||now-permit.createdAt>60000||
        typeof permit.userLabel!=='string'||!/^User .+\*.+$/.test(permit.userLabel))return null;
    var users=(observation.ocr||[]).filter(function(r){return r.text===permit.userLabel&&r.x>600&&r.x<1200&&r.y>990&&r.y<1040;});
    return users.length===1?{x:1824,y:985}:null;
}
function actOneAccountConfirmTarget(observation, now) {
    if(!observation||!Number.isFinite(observation.timestamp)||now<observation.timestamp||now-observation.timestamp>1000||
        actOneEnterGameAuthPrompt(observation.ocr))return null;
    var rows=observation.ocr||[];
    function exact(text,x,y,w,h){var found=rows.filter(function(r){return r.text===text;});if(found.length!==1)return null;
        var r=found[0];return Math.abs(r.x-x)<25&&Math.abs(r.y-y)<20&&Math.abs(r.width-w)<40&&Math.abs(r.height-h)<15?r:null;}
    if(!exact('Are you sure you want to switch',726,459,407,28)||!exact('accounts?',722,492,139,35)||!exact('Cancel',788,576,91,29))return null;
    var ok=exact('OK',1064,572,47,35);return ok?{x:Math.round(ok.x+ok.width/2),y:Math.round(ok.y+ok.height/2)}:null;
}
async function actOneAccountUiClick(ops,target) {
    ops.checkStop();ops.ready();ops.move(target.x,target.y);await ops.sleep(120);
    try {ops.checkStop();ops.ready();ops.down();await ops.sleep(100);}
    finally {ops.up();}
}
function actOneSavedAccountTarget(observation,now,permit) {
    if(!observation||!Number.isFinite(observation.timestamp)||now<observation.timestamp||now-observation.timestamp>1000||!permit)return null;
    var rows=observation.ocr||[];
    function exact(text,x0,x1,y0,y1){var matches=rows.filter(function(r){return r.text===text&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1;});return matches.length===1?matches[0]:null;}
    if(!exact('HOYOVERSE',780,850,350,420)||typeof permit.userLabel!=='string'||!/^[^\s]*\*[^\s]*@[^\s]+$/.test(permit.userLabel))return null;
    if(permit.action==='selectSavedAccount') {
        if(!exact('Log in to another account',770,860,800,860))return null;
        var selected=exact(permit.userLabel,750,850,530,780);
        if(!selected||!Number.isFinite(selected.width)||selected.width<100||selected.width>400||!Number.isFinite(selected.height)||selected.height<15||selected.height>50)return null;
        return {x:Math.round(selected.x+selected.width/2),y:Math.round(selected.y+selected.height/2)};
    }
    var start=exact('Start game',850,950,590,650);
    if(!start||!exact('Log in to another account',770,850,670,730)||!exact(permit.userLabel,750,850,450,520))return null;
    if(permit.action==='startSavedAccount')return {x:960,y:632};
    return permit.action==='expandSavedAccounts'?{x:1200,y:496}:null;
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
function actOneWagnerChoiceTutorial(rows) {
    function one(text,x0,x1,y0,y1){return (rows||[]).filter(function(r){return r.text.trim()===text&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1;}).length===1;}
    return one('Use the scroll wheel orW S keys to',780,850,170,210)&&one('switch options',900,970,205,240)&&
        one("I've got the Iron Chunks.",1290,1360,700,750)&&one('F',1180,1250,700,750)&&one('Wagner',860,920,830,880);
}
function actOneEnemyBarSize(w,h) { return w>=2 && w<=300 && h>=3 && h<=12 && w/h>=0.15; }
function actOneOutdoorEnemyBarCandidate(bar,rows) {
    if(!bar||![bar.x,bar.y,bar.width,bar.height].every(Number.isFinite))return false;
    if(bar.width>=16&&bar.width/bar.height>=3.5&&
       (!Number.isFinite(bar.rectangularity)||bar.rectangularity>=0.8))return true;
    // Tiny red leaf pixels cannot establish a threat. Keep a nearly depleted
    // bar when a nearby enemy level from this same capture anchors it.
    return (rows||[]).some(function(r){
        var label=String(r.text||'').toUpperCase().replace(/[\s.|,]/g,'');
        var x=Number(r.x)+Number(r.width)/2,y=Number(r.y)+Number(r.height)/2;
        return /^LV(?:[1-9][0-9]?|I|L)$/.test(label)&&Number.isFinite(x)&&Number.isFinite(y)&&
            Math.abs(x-bar.x)<=150&&bar.y-y>=8&&bar.y-y<=50;
    });
}
function actOneLisaObjective(text) {
    // Full-frame OCR sometimes adds accents to the exact English objective.
    // Preserve the letters before ignoring punctuation and spacing.
    return String(text||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]/g,'')==='meetlisaatthetemple';
}
function actOneStatueHealingVerified(o,now,session) {
    var h=o&&o.hud,hp=h&&h.health;
    return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&h&&h.world&&h.groundControls&&!h.climbing&&!h.dialogueReady&&!h.choice&&hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max>0&&hp.current===hp.max&&(o.ocr||[]).some(function(r){return /^(?:UID)?[: ]*693306810$/.test(String(r.text).trim())&&r.x>1600&&r.y>1030;}));
}
function actOneStatueHealingPortraits(rows) {
    var portraits=[118,298];
    var third=(rows||[]).filter(function(r){return /^Lv\.?\s*[1-9][0-9]?$/.test(String(r.text||'').trim())&&
        r.x>=430&&r.x<=510&&r.y>=210&&r.y<=255&&r.width>=30&&r.width<=90&&r.height>=15&&r.height<=40;});
    if(third.length===1)portraits.push(478);
    return portraits;
}
function actOneLisaLockedTemplePanel(o,now,session){
    if(!o||o.session!==session||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||
       !o.hud||o.hud.world||o.hud.health||o.hud.auto||o.hud.dialogueReady||!Array.isArray(o.ocr))return false;
    function one(text,x0,x1,y0,y1){return o.ocr.filter(function(r){return r.text.trim()===text&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1;}).length===1;}
    return one('Temple of the Lion',1450,1550,0,60)&&one('Possible Rewards',1400,1500,480,540)&&
        one('to activate waypoint',1500,1650,930,970)&&one('Navigate',1550,1700,970,1035);
}
function actOneLisaUnlockedTemplePanel(o,now,session){
    if(!o||o.session!==session||!Number.isFinite(now)||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||
       !o.hud||o.hud.world||o.hud.health||o.hud.auto||o.hud.dialogueReady||!Array.isArray(o.ocr))return false;
    function one(text,x0,x1,y0,y1){return o.ocr.filter(function(r){return String(r.text||'').trim()===text&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1;}).length===1;}
    return one('Temple of the Lion',1450,1550,0,60)&&one('Possible Rewards',1400,1500,480,540)&&
        one('Deep Within the Temple of',1400,1550,535,580)&&one('the Lion',1400,1550,570,620)&&
        one('Teleport',1550,1750,970,1035)&&!o.ocr.some(function(r){return /to activate waypoint|^Navigate$/.test(String(r.text||'').trim());});
}
function actOneLocalPauseProof(o,now,session) {
    if(!o||o.session!==session||!Number.isInteger(o.frameId)||!Number.isFinite(o.timestamp)||!Number.isFinite(now)||
       now<o.timestamp||now-o.timestamp>1000||!o.hud||!Array.isArray(o.ocr))return null;
    var rows=o.ocr,h=o.hud;
    if(actOneLisaUnlockedTemplePanel(o,now,session))return {kind:'map',evidence:rows.filter(function(r){return r.text.trim()==='Temple of the Lion'||r.text.trim()==='Teleport';})};
    if(actOneLisaLockedTemplePanel(o,now,session))return {kind:'map',evidence:rows.filter(function(r){return r.text.trim()==='Temple of the Lion'||r.text.trim()==='to activate waypoint';})};
    function matches(text,x0,x1,y0,y1){return rows.filter(function(r){return String(r.text||'').trim()===text&&
        r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1;});}
    var headers=rows.filter(function(r){return ['Food','Weapons','Artifacts','Character Development Items','Materials','Gadgets','Quest','Precious Items','Furnishings'].indexOf(String(r.text||'').trim())>=0&&
        r.x>=100&&r.x<=250&&r.y>=15&&r.y<=70;});
    var capacity=rows.filter(function(r){var label=String(r.text||'').trim(),typed=headers.length===1&&label.startsWith(headers[0].text.trim()+' ')&&/^\d+\/\d+$/.test(label.slice(headers[0].text.trim().length+1));
        return (/^Inventory capacity\s+\d+\/\d+$/i.test(label)||typed)&&r.x>=1450&&r.x<=1810&&r.y>=15&&r.y<=75;});
    if(headers.length===1&&capacity.length===1&&!h.auto&&!h.dialogueReady)
        return {kind:'inventory',evidence:[headers[0],capacity[0]]};
    var journal=matches('In Progress',100,350,15,80),archon=matches('Archon Quests',80,450,90,160);
    if(h.journal===true&&journal.length===1&&archon.length===1)
        return {kind:'journal',evidence:[journal[0],archon[0]]};
    var continues=matches('Continue Challenge',750,1000,535,620),leaves=matches('Leave Domain?',750,1000,620,700);
    var lower=matches('Lower Difficulty',800,900,500,570),upperContinue=matches('Continue Challenge',800,900,380,450);
    if(upperContinue.length===1&&lower.length===1&&leaves.length===1&&!h.auto&&!h.dialogueReady)
        return {kind:'domain',evidence:[upperContinue[0],lower[0],leaves[0]]};
    if(continues.length===1&&leaves.length===1&&!h.auto&&!h.dialogueReady)
        return {kind:'domain',evidence:[continues[0],leaves[0]]};
    var loweredContinue=matches('Continue Challenge',800,900,450,500),loweredLeave=matches('Leave Domain?',800,950,565,620);
    if(loweredContinue.length===1&&loweredLeave.length===1&&lower.length===0&&!h.auto&&!h.dialogueReady&&!h.world&&!h.health&&o.map===null)
        return {kind:'domain',evidence:[loweredContinue[0],loweredLeave[0]]};
    if(!h.auto&&!h.dialogueReady&&!h.world&&!h.health) {
        var rank=matches('Adventure Rank',0,900,0,900),worldLevel=matches('World Level',0,900,0,900);
        // The hovered rank-help tooltip repeats this label. Keep the profile row,
        // while still rejecting duplicate labels within that actual profile row.
        if(rank.length>1)rank=rank.filter(function(r){return r.x>=300&&r.x<=550&&r.y>=150&&r.y<=195;});
        var menuLabels=['Shop','Party Setup','Friends','Characters'].map(function(t){return matches(t,0,1000,100,1000);}).filter(function(a){return a.length===1;});
        if(!h.bigMap&&!h.journal&&rank.length===1&&worldLevel.length===1&&menuLabels.length>=2)
            return {kind:'menu',evidence:[rank[0],worldLevel[0],menuLabels[0][0],menuLabels[1][0]]};
        var party=matches('Party Setup',0,600,0,150),deploy=matches('Deploy',1450,1850,900,1050);
        if(party.length===1&&deploy.length===1)return {kind:'party',evidence:[party[0],deploy[0]]};
        var region=rows.filter(function(r){return /^(Starfell Valley|Starfell Valleyale|Cape OStarfell Valley|C?Galesong Hill|Windwail Highland|Brightcrown Mountains)$/.test(String(r.text||'').trim())&&r.x>=1450&&r.x<=1810&&r.y>=950&&r.y<=1030;});
        var exploration=rows.filter(function(r){return /^T?Exploration Progress:\s*\d+(?:\.\d+)?%$/.test(String(r.text||'').trim())&&r.x>=1450&&r.x<=1810&&r.y>=995&&r.y<=1050;});
        if(h.bigMap===true&&region.length===1&&exploration.length===1)return {kind:'map',evidence:[region[0],exploration[0]]};
        if(h.bigMap===true&&actOneFullMapState(rows))return {kind:'map',evidence:rows.filter(function(r){
            return /^(Windrise|Falcon Coast|Mondstadt|Teyvat|200\s*\/\s*200|Touch Statues of The Seven to reveal areas on your Map)$/.test(String(r.text||'').trim());})};
    }
    return null;
}
function actOneLocalPauseInputReady(o,now,session) {
    if(!o||o.session!==session||!Number.isInteger(o.frameId)||!Number.isFinite(o.timestamp)||!Number.isFinite(now)||
       now<o.timestamp||now-o.timestamp>1000||!o.hud||!Array.isArray(o.ocr)||actOneLocalPauseProof(o,now,session))return false;
    var h=o.hud,rows=o.ocr,hp=h.health;
    var completedExit=h.groundControls===true&&rows.filter(function(r){return /^Leaving in \d+ second\(s\)$/.test(r.text.trim())&&r.x>=650&&r.x<=1000&&r.y>=920&&r.y<=990;}).length===1&&
        rows.filter(function(r){return r.text.trim()==='F'&&r.x>=1080&&r.x<=1160&&r.y>=480&&r.y<=590;}).length===1;
    if(h.auto||h.journal||h.bigMap||h.dialogueReady||h.choice||h.loading||h.unknownHud===true||h.tutorialStep||
       actOneEnterGameAuthPrompt(rows)||actOneEnterGameUnknownUi(rows)||rows.some(function(r){var t=String(r.text||'').trim();return /^(Food|Inventory capacity|Domain Entrance|Party Setup|Continue Challenge)/i.test(t)||/^Leave Domain\?/i.test(t)&&!(completedExit&&r.x>=1150&&r.x<=1450&&r.y>=480&&r.y<=590);}))return false;
    // Pausing needs recognizable live-game HUD evidence, not combat readiness.
    // A missing objective, slot number, HP reading, or E/Q label must not block it.
    var party=rows.some(function(r){return /^(Lumina|Traveler|Amber|Kaeya|Lisa)$/.test(String(r.text||'').trim())&&r.x>=1550&&r.x<=1810&&r.y>=280&&r.y<=650;});
    var controls=rows.some(function(r){return /^(R|E|Q)$/.test(String(r.text||'').trim())&&r.x>=1520&&r.x<=1810&&r.y>=985&&r.y<=1045;});
    // Climbing replaces attack controls with X/Space. These paired controls
    // permit only pausing, including when the health crop is unresolved.
    controls=controls||(h.climbing===true&&
        rows.filter(function(r){return String(r.text||'').trim()==='X'&&r.x>=1580&&r.x<=1635&&r.y>=1010&&r.y<=1060;}).length===1&&
        rows.filter(function(r){return String(r.text||'').trim()==='Space'&&r.x>=1660&&r.x<=1780&&r.y>=1010&&r.y<=1060;}).length===1);
    controls=controls||(h.world===true&&h.groundControls===false&&!h.climbing&&rows.some(function(r){return String(r.text||'').trim()==='Space'&&r.x>=1660&&r.x<=1780&&r.y>=1010&&r.y<=1060;})&&rows.some(function(r){return /693306810$/.test(String(r.text||''))&&r.x>=1600&&r.y>=1040;}));
    var health=hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max>0&&hp.current>=0&&hp.current<=hp.max;
    // Any two independent HUD signals establish a pause-only field. In
    // particular, losing party-name OCR must not keep a recognizable field live.
    return !!(party&&(controls||health)||controls&&health);
}
function actOneKaeyaPartyLabel(text) {
    return String(text||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim()==='Kaeya';
}
function actOneLionFieldWorld(o,now,session,minRatio,allowStatuePrompt,expectedObjective) {
    var h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
    if(!o||o.session!==session||!Number.isInteger(o.frameId)||!Number.isFinite(o.timestamp)||!Number.isFinite(now)||now<o.timestamp||now-o.timestamp>1000||
       !h||h.groundControls!==true||h.climbing!==false||h.auto!==false||h.journal!==false||h.bigMap!==false||
       h.dialogueReady!==false||h.choice!==false||h.tutorialStep||h.objectiveChanged||h.unknownHud||
       !hp||!Number.isFinite(hp.current)||!Number.isFinite(hp.max)||hp.max<=0||hp.current<=0||hp.current>hp.max||hp.current/hp.max<minRatio||
       rows.some(function(r){return String(r.text||'').trim()==='Trial';}))return false;
    if(expectedObjective!==undefined&&['Meet Lisa at the temple','Talk to Lisa','Enter the temple'].indexOf(expectedObjective)<0)return false;
    var objective=(h.objectives||[]).filter(expectedObjective&&expectedObjective!=='Meet Lisa at the temple'?
        function(s){return String(s||'').trim()===expectedObjective;}:allowStatuePrompt===true?
        function(s){return actOneLisaObjective(s)||['Talk to Lisa','Enter the temple'].indexOf(String(s||'').trim())>=0;}:actOneLisaObjective);
    // Recorded field OCR added a macron to Kaeya. Remove combining accents
    // only; keep the exact spelling, unique name row, geometry, and slot proof.
    var kaeya=rows.filter(function(r){return actOneKaeyaPartyLabel(r.text)&&r.x>=1600&&r.x<=1800&&r.y>=460&&r.y<=540;});
    var slot=rows.filter(function(r){return String(r.text||'').trim()==='3'&&r.x>=1850&&r.x<=1890&&r.y>=460&&r.y<=540;});
    var statueFallback=allowStatuePrompt===true&&slot.length===0&&Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&
        rows.filter(function(r){return String(r.text||'').trim()==='Amber'&&r.x>=1600&&r.x<=1800&&r.y>=350&&r.y<=460;}).length===1&&
        rows.filter(function(r){return String(r.text||'').trim()==='Statue of The Seven'&&r.x>=1150&&r.x<=1280&&
            r.y>=490&&r.y<=555&&r.width>=240&&r.width<=310&&r.height>=20&&r.height<=40;}).length===1&&
        rows.filter(function(r){return String(r.text||'').trim()==='F'&&r.x>=1080&&r.x<=1170&&r.y>=490&&r.y<=590;}).length===1;
    // Selected Kaeya's gray slot digit is unreadable in recorded R17 captures.
    // The verified owned Lv.6 profile, two other party names and Amber's slot form
    // an independent identity check; never synthesize the missing digit.
    var selectedKaeya=[1288,1363,1186,1379,1459].indexOf(hp.max)>=0&&slot.length===0&&
        !rows.some(function(r){return /^\d$/.test(String(r.text||'').trim())&&r.x>=1850&&r.x<=1890&&r.y>=460&&r.y<=540;})&&
        rows.filter(function(r){return r.text.trim()==='Lumina'&&r.x>=1600&&r.x<=1800&&r.y>=280&&r.y<=350;}).length===1&&
        rows.filter(function(r){return r.text.trim()==='Amber'&&r.x>=1600&&r.x<=1800&&r.y>=350&&r.y<=460;}).length===1&&
        rows.filter(function(r){return r.text.trim()==='2'&&r.x>=1850&&r.x<=1890&&r.y>=350&&r.y<=460;}).length===1;
    return objective.length===1&&kaeya.length===1&&(slot.length===1||statueFallback||selectedKaeya);
}
function actOneLisaAirfield(o,now,session) {
    var h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
    if(!o||o.session!==session||!Number.isInteger(o.frameId)||!Number.isFinite(now)||!Number.isFinite(o.timestamp)||
       now<o.timestamp||now-o.timestamp>1000||!h||h.groundControls!==false||h.climbing!==false||
       h.auto||h.journal||h.bigMap||h.dialogueReady||h.choice||h.loading||h.unknownHud||h.objectiveChanged||h.tutorialStep||
       !hp||hp.max!==1288||!Number.isFinite(hp.current)||hp.current<0.6*hp.max||hp.current>hp.max||
       (h.objectives||[]).filter(actOneLisaObjective).length!==1||rows.some(function(r){return r.text.trim()==='Trial';}))return false;
    return ['Lumina','Amber','Kaeya'].every(function(name){return rows.filter(function(r){return r.text.trim()===name&&r.x>=1600&&r.x<=1800&&r.y>=280&&r.y<=540;}).length===1;})&&
        rows.filter(function(r){return r.text.trim()==='Space'&&r.x>=1600&&r.x<=1880&&r.y>=990&&r.y<=1060;}).length===1;
}
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
        if (level===4 ? !/^LV4$/.test(label) : level===5 ? !/^LV5$/.test(label) : [10,11,12,13,14].indexOf(level)>=0 ? label!=='LV'+level : !/^LV[1IL]$/.test(label)) return false;
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
function actOneMergeMissingLisaParty(fullRows,cropRows) {
    function label(text){return actOneKaeyaPartyLabel(text)?'Kaeya':String(text||'').trim()==='Amber'?'Amber':null;}
    var missing=['Amber','Kaeya'].filter(function(name){return !fullRows.some(function(r){
        return label(r.text)===name&&r.x>=1550&&r.x<=1800&&r.y>=300&&r.y<=600;
    });});
    // This band is read only to repair a missing name. Re-adding a name that
    // was already recognized can create a duplicate when OCR box widths differ.
    return actOneMergeControlCropRows(fullRows,(cropRows||[]).filter(function(r){
        return missing.indexOf(label(r.text))>=0;
    }),1630,330);
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
function actOneLisaSilentSubtitle(rows, counts) {
    var anchors=(rows||[]).filter(function(r){return !/^UID:/.test(r.text.trim());});
    return anchors.length===2&&anchors.filter(function(r){return r.text.trim()==='Auto'&&r.x>=0&&r.x<350&&r.y>=0&&r.y<150;}).length===1&&
        anchors.filter(function(r){return r.text.trim()==='Lisa'&&r.x>=850&&r.x<=1000&&r.y>=840&&r.y<900;}).length===1&&
        Array.isArray(counts)&&counts.length===4&&counts.every(Number.isInteger)&&
        counts.slice(0,3).every(function(n){return n>=14&&n<=24;})&&counts[3]===counts[0]+counts[1]+counts[2];
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
function actOneLionFalconWaypointReady(observation,now,session) {
    var h=observation&&observation.hud,hp=h&&h.health,p=observation&&observation.map;
    var exactObjective=Array.isArray(h&&h.objectives)&&h.objectives.some(actOneLisaObjective);
    return !!(observation&&observation.session===session&&typeof session==='string'&&session.length>0&&
        Number.isInteger(observation.frameId)&&Number.isFinite(observation.timestamp)&&Number.isFinite(now)&&now>=observation.timestamp&&now-observation.timestamp<=1000&&
        h&&h.world===true&&p&&p.map==='Teyvat'&&Number.isFinite(p.x)&&Number.isFinite(p.y)&&exactObjective&&
        hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max>0&&hp.current>=0&&hp.current<=hp.max&&hp.current/hp.max>=0.6&&!h.lowHealth&&
        !h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&!h.climbing&&!h.tutorialStep&&!h.objectiveChanged);
}
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
function actTwoMapResinCropNeeded(rows) {
    return !actOneFullMapState(rows)&&rows.some(function(r){return /200\s*\/\s*200$/.test(String(r.text||'').trim())&&r.x>1500&&r.y<100;})&&
        rows.some(function(r){return /^T[o\u00F3]uchStatuesofTheSeventorevealareasonyourMap(?:Gok?)?$/.test(String(r.text||'').replace(/\s/g,''))&&r.x>=1100&&r.y>=1010;});
}
function actOneFullMapState(rows) {
    rows=rows||[];
    var footer=rows.filter(function(r){return String(r.text||'').trim()==='Teyvat'&&r.x>1500&&r.y>930&&r.y<1020;});
    var resin=rows.filter(function(r){return /^200\s*\/\s*200$/.test(String(r.text||'').trim())&&r.x>1500&&r.y<100;});
    var places=['Mondstadt','Cider Lake','Whispering Woods','Starfell Lake'];
    var geo=places.filter(function(name){return rows.some(function(r){return String(r.text||'').trim()===name&&r.x>=800&&r.x<1600&&r.y>=40&&r.y<380;});});
    var unrevealed=rows.filter(function(r){return /^T[o\u00F3]uchStatuesofTheSeventorevealareasonyourMap(?:Gok?)?$/.test(String(r.text||'').replace(/\s/g,''))&&
        r.x>=1100&&r.x<=1250&&r.y>=1010&&r.y<=1040&&r.width>=500&&r.width<=750;});
    var windrise=rows.filter(function(r){return String(r.text||'').trim()==='Windrise'&&r.x>=500&&r.x<=1800&&r.y>=100&&r.y<=850;});
    var mondstadt=rows.filter(function(r){return String(r.text||'').trim()==='Mondstadt'&&r.x>=200&&r.x<=1700&&r.y>=0&&r.y<=900;});
    var falconCoast=rows.filter(function(r){return String(r.text||'').trim()==='Falcon Coast'&&r.x>=1200&&r.x<=1800&&r.y>=350&&r.y<=850;});
    return resin.length===1&&(footer.length===1&&geo.length>=2||
        unrevealed.length===1&&windrise.length===1&&(mondstadt.length===1||falconCoast.length===1));
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
function actOneShouldReadLionInteractionCrop(rows,screen){
    rows=rows||[];screen=screen||{};var hp=screen.health;
    var completedChest=rows.filter(function(r){return r.text.trim()==='Precious Chest'&&r.x>=1150&&r.x<=1450&&r.y>=480&&r.y<=590;}).length===1&&
        rows.filter(function(r){return /^Leaving in \d+ second\(s\)$/.test(r.text.trim())&&r.x>=650&&r.x<=1000&&r.y>=920&&r.y<=990;}).length===1&&
        rows.filter(function(r){return r.text.trim()==='Kaeya'&&r.x>=1600&&r.x<=1810&&r.y>=460&&r.y<=540;}).length===1;
    return !!(screen.world===false&&screen.groundControls===true&&!screen.auto&&!screen.journal&&!screen.bigMap&&
        !screen.dialogueReady&&!screen.choice&&!screen.climbing&&!screen.objectiveChanged&&!screen.tutorialStep&&!screen.loading&&
        hp&&[1196,1363,1459,1288,1379,1186].indexOf(hp.max)>=0&&hp.current/hp.max>=0.6&&hp.current<=hp.max&&
        rows.filter(function(r){return /^(Open Door|Start|Common Chest|Exquisite Chest|Precious Chest)$/.test(String(r.text||'').trim())&&r.x>=1150&&r.x<=1450&&r.y>=480&&r.y<=590;}).length===1&&
        !rows.some(function(r){return String(r.text||'').trim()==='F'&&r.x>=1080&&r.x<=1160&&r.y>=480&&r.y<=590;})&&
        (completedChest||rows.filter(function(r){return String(r.text||'').trim()==='Trial'&&r.x>=1750&&r.x<=1895&&r.y>=495&&r.y<=540;}).length===1&&
        rows.filter(function(r){return String(r.text||'').trim()==='Lisa'&&r.x>=1600&&r.x<=1810&&r.y>=525&&r.y<=580;}).length===1));
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
function actOneLionEntry() {
    return eval(file.readTextSync('lion-entry.js')+'\nActOneLionEntry;');
}
function actOneLionStartTarget(o,now) {
    return actOneLionEntry().startTarget(o,now);
}
function actOneLionPartyTarget(o,now,reports,session,currentRequestId) {
    return actOneLionEntry().partyTarget(o,now,reports,session,currentRequestId);
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
function actOneWolfReviveItemModalVisible(o) {
    return !!((o&&o.ocr)||[]).some(function(r){return String(r.text||'').trim()==='Use revival item';});
}
function actOneWolfReviveEggTarget(o,now) {
    var h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
    if(!o||!Number.isFinite(now)||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!h||
       h.world!==false||typeof h.groundControls!=='boolean'||h.climbing!==false||h.journal!==false||h.bigMap!==false||h.dialogueReady!==false||
       h.choice!==false||h.auto!==false||h.tutorialStep!==null||h.loading===true||h.unknownHud===true||h.objectiveChanged===true||
       h.interact===true||hp&&(hp.max!==1055||!Number.isFinite(hp.current)||hp.current<=0||hp.current>hp.max)||
       (h.enemyBars||[]).length!==0||!actOneWolfReviveItemModalVisible(o)) return null;
    function exact(text){return rows.filter(function(r){return String(r.text||'').trim()===text;});}
    function one(text,x1,x2,y1,y2,w1,w2,h1,h2) {
        var all=exact(text),inZone=all.filter(function(r){return Number(r.x)>=x1&&Number(r.x)<=x2&&Number(r.y)>=y1&&Number(r.y)<=y2&&
            Number(r.width)>=w1&&Number(r.width)<=w2&&Number(r.height)>=h1&&Number(r.height)<=h2;});
        return all.length===1&&inZone.length===1?inZone[0]:null;
    }
    var stockRows=rows.filter(function(r){return /^[1-9]\d?$/.test(String(r.text||'').trim())&&r.x>=920&&r.x<=990&&r.y>=405&&r.y<=465;});
    var stock=stockRows.length===1?String(stockRows[0].text).trim():null;
    var title=one('Use revival item',760,1150,195,290,290,390,35,70),count=stock&&one(stock,920,990,405,465,10,35,14,30),
        egg=one('Teyvat Fried Egg',800,1120,445,525,220,315,30,65),
        description=one('Revives a character and restores 100 HP.',650,1260,510,585,490,620,20,45),
        cancel=one('Cancel',650,870,750,840,80,170,28,62),confirm=one('Confirm',1080,1320,750,840,95,170,28,62);
    var kaeya=rows.filter(function(r){return String(r.text||'').trim()==='Kaeya'&&r.x>1550&&r.x<1800&&r.y>300&&r.y<600;}),
        amber=rows.filter(function(r){return String(r.text||'').trim()==='Amber'&&r.x>1550&&r.x<1800&&r.y>300&&r.y<600;}),
        trial=rows.filter(function(r){return String(r.text||'').trim()==='Trial'&&r.x>1700&&r.x<1900&&r.y>300&&r.y<600;});
    return title&&count&&egg&&description&&cancel&&confirm&&kaeya.length===1&&amber.length===1&&trial.length===1?
        {x:Math.round(confirm.x+confirm.width/2),y:Math.round(confirm.y+confirm.height/2),label:'Teyvat Fried Egg',quantity:1,inventoryStock:Number(stock)}:null;
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
    if(actOneWolfReviveItemModalVisible(o)) return false;
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
    var healthFloor=actOneWolfRecoveryTravelHud(o,now)?0.3:0.6;
    if(hp.current/hp.max<healthFloor) return {ok:false,reason:'Wolf health below '+Math.round(healthFloor*100)+'%'};
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
    if(actOneWolfReviveItemModalVisible(o)) return false;
    var grounded=!!(o&&Number.isFinite(now)&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&
      o.map===null&&h&&h.world===false&&h.groundControls===true&&!h.climbing&&!h.journal&&!h.bigMap&&
      !h.dialogueReady&&!h.choice&&!h.tutorialStep&&!h.auto&&!h.loading&&!h.unknownHud&&!h.objectiveChanged&&
      hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max===1427&&hp.current>0&&hp.current<=hp.max&&
      rows.some(function(r){return String(r.text||'').trim()==='Trial'&&r.x>1700&&r.x<1900&&r.y>300&&r.y<600;}));
    return grounded||actOneWolfAirPauseOnlyHud(o,now);
}
function actOneWolfDeadTrialPauseOnlyHud(o,now,session) {
    var h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
    if(!o||typeof session!=='string'||!session||o.session!==session||!Number.isFinite(now)||
       !Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!h||h.world!==false||
       h.climbing!==false||h.journal!==false||h.bigMap!==false||h.dialogueReady!==false||h.choice!==false||
       h.tutorialStep!==null||h.auto!==false||h.loading===true||h.unknownHud===true||h.objectiveChanged===true||
       !hp||!Number.isFinite(hp.current)||!Number.isFinite(hp.max)||hp.max!==1055||hp.current<=0||hp.current>hp.max) return false;
    var kaeya=rows.filter(function(r){return String(r.text||'').trim()==='Kaeya'&&r.x>1550&&r.x<1800&&r.y>300&&r.y<600;});
    var amber=rows.filter(function(r){return String(r.text||'').trim()==='Amber'&&r.x>1550&&r.x<1800&&r.y>300&&r.y<600;});
    var controls=rows.filter(function(r){return /^(R|E|Q)$/.test(String(r.text||'').trim())&&r.x>1500&&r.x<1880&&r.y>=990&&r.y<=1045;});
    var menuOrLoading=rows.some(function(r){var text=String(r.text||'').trim();return /^(Continue Challenge|Leave Domain\?|Party Setup|Domain Entrance|Start Game|Log In|Retry|Exit Domain|Use revival item)$/i.test(text)||
        /\b(loading|entering|connecting|preparing)\b/i.test(text);});
    return !menuOrLoading&&kaeya.length===1&&amber.length===1&&controls.length>=1&&controls.length<=3&&
        ['R','E','Q'].every(function(label){return controls.filter(function(r){return String(r.text||'').trim()===label;}).length<=1;});
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
function actOneWolfRecoveryTravelHud(o,now) {
    if(!actOneWolfBurstRecoveryActiveHud(o,now,0.3)) return false;
    var h=o.hud,diagnostic=h.enemyBarDiagnostic;
    return !!(Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&diagnostic&&diagnostic.level===5&&
        diagnostic.candidates===0&&Array.isArray(diagnostic.localReads)&&diagnostic.localReads.length===0);
}
function actOneWolfSpikeActive(o,now,body,minRatio) {
    if(!actOneWolfDomainHud(o,now,minRatio===undefined?0.01:minRatio))return false;
    var h=o.hud,hp=h.health,d=h.enemyBarDiagnostic;
    if(hp.current<=0||h.auto||h.loading||h.unknownHud||h.objectiveChanged||h.interact||
       !Array.isArray(h.enemyBars)||h.enemyBars.length||!d||d.level!==5||d.candidates!==0||
       !Array.isArray(d.localReads)||d.localReads.length)return false;
    return body==='kaeya'?hp.max===1427:body==='amber'?hp.max===1055:[1427,1055,1213].indexOf(hp.max)>=0;
}
function actOneWolfSpikeSurface(metrics) {
    var names=['iceLeft','iceRight','floorLeftIce','floorRightIce','floorLeftStone','floorRightStone','spikeLeft','spikeRight'];
    if(!metrics||names.some(function(k){return !Number.isFinite(metrics[k])||metrics[k]<0||metrics[k]>1;}))return null;
    // Blue paving also matches the broad ice mask; the masks are not exclusive.
    var floor=metrics.floorLeftStone>=0.8&&metrics.floorRightStone>=0.8;
    var lip=Number.isFinite(metrics.frontLeftStone)&&Number.isFinite(metrics.frontRightStone)&&
        metrics.frontLeftStone>=0.6&&metrics.frontLeftStone<=1&&metrics.frontRightStone>=0.6&&metrics.frontRightStone<=1&&
        metrics.iceLeft<=0.12&&metrics.iceRight<=0.12&&metrics.floorLeftIce>=0.7&&metrics.floorRightIce>=0.7;
    var kaeyaLip=Number.isFinite(metrics.frontLeftStone)&&Number.isFinite(metrics.frontRightStone)&&
        metrics.frontLeftStone>=0.75&&metrics.frontLeftStone<=1&&metrics.frontRightStone>=0.75&&metrics.frontRightStone<=1&&
        metrics.floorLeftStone>=0.3&&metrics.floorRightStone>=0.3&&metrics.floorLeftIce<=0.3&&metrics.floorRightIce<=0.3;
    var firstLanding=floor&&Number.isFinite(metrics.frontLeftStone)&&Number.isFinite(metrics.frontRightStone)&&
        metrics.frontLeftStone>=0.5&&metrics.frontLeftStone<=1&&metrics.frontRightStone>=0.5&&metrics.frontRightStone<=1&&
        metrics.iceLeft<0.7&&metrics.iceRight<0.7;
    return {metrics:metrics,ice:metrics.iceLeft>=0.7&&metrics.iceRight>=0.7,solidFloor:floor,landingLip:lip,kaeyaLandingLip:kaeyaLip,firstLanding:firstLanding,
        startBank:floor&&metrics.iceLeft<=0.12&&metrics.iceRight<=0.12&&metrics.spikeLeft>=0.22&&metrics.spikeRight>=0.22};
}
function actOneWolfCryoCooldownRemaining(o) {
    var rows=o&&o.ocr||[],matches=rows.filter(function(r){
        var text=String(r&&r.text||'').trim(),seconds=Number(text);
        return r&&r.x>1660&&r.x<1740&&r.y>970&&r.y<1015&&r.width>=30&&r.width<=45&&r.height>=16&&r.height<=28&&
            /^(?:0\.[1-9]|[1-5]\.[0-9]|6\.0)$/.test(text)&&Number.isFinite(seconds)&&seconds>0&&seconds<=6;
    });
    return matches.length===1?Number(matches[0].text.trim()):null;
}
function actOneWolfBankApproachReady(o,request,permit,now) {
    if(!request||request.mission!=='questStep'||request.step!=='wolfForwardFine'||
       !permit||permit.kind!=='wolfBankApproach'||permit.usedAt||permit.session!==request.session||
       !Number.isInteger(request.expectedFrameId)||permit.frameId!==request.expectedFrameId||
       !Number.isInteger(permit.witnessFrameId)||permit.witnessFrameId<0||permit.witnessFrameId>permit.frameId||
       !Number.isFinite(permit.createdAt)||now<permit.createdAt||now-permit.createdAt>120000||
       !o||o.session!==request.session||!Number.isInteger(o.frameId)||o.frameId<request.expectedFrameId||
       !actOneWolfSpikeActive(o,now,'kaeya',0.01))return false;
    var hp=o.hud.health,m=o.hud.wolfSpikeSurface&&o.hud.wolfSpikeSurface.metrics,b=permit.health;
    // Blue paving varies within the stone mask. The root's one-use bank witness,
    // unchanged HP and 200 ms cap authorize this approach; masks are corroboration.
    return !!(b&&b.max===1427&&Number.isInteger(b.current)&&b.current>0&&b.current<=1427&&
       hp.current===b.current&&hp.max===b.max&&m&&
       ['floorLeftStone','floorRightStone'].every(function(k){
           return Number.isFinite(m[k])&&m[k]>=0.65&&m[k]<=1;
       }));
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
    var underwaterSpikes=rows.filter(function(r){return exactCaption(r,'Underwater spikes make the area too dangerous to swim through');});
    var cryoWaterFirst=rows.filter(function(r){return exactCaption(r,"Kaeya's Cryo skill can freeze the surface of water, creating a safe passage");});
    var cryoWaterSecond=rows.filter(function(r){return exactCaption(r,'across');});
    var cryo=rows.filter(function(r){return exactCaption(r,'Cryo skills can freeze water, Hydro opponents, or opponents that are Wet');});
    var reaction=rows.filter(function(r){return exactCaption(r,'Utilize this elemental reaction to gain an advantage over your opponents');});
    var flamethrower=rows.filter(function(r){return exactCaption(r,"A flamethrower's core is what gives it the energy to shoot fire");});
    var hydroFirst=rows.filter(function(r){return exactCaption(r,'The blue stone in the center of the room is Hydro Amber. Breaking it will');});
    var hydroSecond=rows.filter(function(r){return exactCaption(r,'make it rain, making everything in its range Wet');});
    var disableFirst=rows.filter(function(r){return String(r&&r.text||'').trim()==="Use Cryo Skills to temporarily disable flamethrowers' cores and stop them";});
    var disableSecond=rows.filter(function(r){return exactCaption(r,'from shooting fire');});
    if(cryoWaterFirst.length||cryoWaterSecond.length) {
        if(cryoWaterFirst.length!==1||cryoWaterSecond.length!==1||wet.length||underwaterSpikes.length||cryo.length||reaction.length||flamethrower.length||hydroFirst.length||hydroSecond.length||disableFirst.length||disableSecond.length)return null;
        var cf=cryoWaterFirst[0],cs=cryoWaterSecond[0];
        if(cf.x>390&&cf.x<450&&cf.y>760&&cf.y<800&&cf.width>1020&&cf.width<1120&&cf.height>30&&cf.height<55&&
           cs.x>880&&cs.x<935&&cs.y>805&&cs.y<845&&cs.width>75&&cs.width<130&&cs.height>15&&cs.height<35)return 'cryoWaterPassage';
        return null;
    }
    if(underwaterSpikes.length) {
        if(underwaterSpikes.length!==1||wet.length||cryo.length||reaction.length||flamethrower.length||hydroFirst.length||hydroSecond.length||disableFirst.length||disableSecond.length)return null;
        var u=underwaterSpikes[0];
        if(u.x>450&&u.x<510&&u.y>760&&u.y<805&&u.width>900&&u.width<1000&&u.height>28&&u.height<50)return 'underwaterSpikes';
        return null;
    }
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
    if(kind==='underwaterSpikes'&&(h.groundControls!==false||h.climbing!==false||h.auto!==false||h.loading===true||h.unknownHud===true||h.objectiveChanged===true))return false;
    if(kind==='cryoWaterPassage'&&(h.world!==false||h.groundControls===undefined||h.climbing!==false||h.auto!==false||h.tutorialStep!=='wolfInfo'||
       h.loading===true||h.unknownHud===true||h.objectiveChanged!==false||actOneEnterGameLoading(o.ocr||[])))return false;
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
function actOneLisaSkillInfo(o,now,session) {
    var h=o&&o.hud,rows=o&&o.ocr||[];
    function one(text,x0,x1,y0,y1){return rows.filter(function(r){return String(r.text||'').trim()===text&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1;}).length===1;}
    var hp=h&&h.health,diagnostic=h&&h.healthDiagnostic;
    // The dimmed tutorial can drop the HP slash. Only corroborate this exact
    // trial maximum with the independent right-hand HP crop; never alter HUD HP.
    if(!hp&&diagnostic&&Array.isArray(diagnostic.primary)&&diagnostic.primary.length===1&&
       Array.isArray(diagnostic.right)&&diagnostic.right.length===1&&diagnostic.right[0]==='1196'&&
       /^(?:[7-9]\d{2}|1[01]\d{2})1196$/.test(diagnostic.primary[0]))
        hp={current:Number(diagnostic.primary[0].slice(0,-4)),max:1196};
    var partyProof=one('Trial',1750,1895,495,540)||one('Lumina',1600,1810,240,290)&&
        one('Amber',1600,1810,325,390)&&one('Kaeya',1600,1810,410,475);
    return !!(o&&o.session===session&&Number.isFinite(o.timestamp)&&now>=o.timestamp&&now-o.timestamp<=1000&&o.map===null&&h&&
        h.world===false&&!h.journal&&!h.bigMap&&!h.dialogueReady&&!h.choice&&!h.auto&&!h.climbing&&
        hp&&hp.max===1196&&hp.current>=718&&hp.current<=1196&&
        (one("Lisa's Elemental Skill can be unleashed by pressing, or charged by holding.",380,460,760,820)||
         one('When the skill is fully charged, releasing it unleashes an area attack, dealing',380,460,760,820)&&
         (one('massive Electro DMG.',760,830,810,860)||one('massive Electro DMG',760,830,810,860)))&&
        one('Lisa',1600,1810,525,580)&&partyProof);
}
function actOneLionBubblePrompt(o) {
    var rows=o&&o.ocr||[];
    return rows.filter(function(r){return r.text.trim()==='Space'&&r.x>=1300&&r.x<=1500&&r.y>=500&&r.y<=700;}).length===1&&
        rows.filter(function(r){return r.text.trim()==='Large Hydro Slime'&&r.x>=750&&r.x<=1000&&r.y>=10&&r.y<=60;}).length===1;
}
function actOneFalconInfo(rows) {
    if(actOneFalconPyroInfo(rows)) return true;
    if(rows.some(function(r){return r.x>380&&r.x<500&&r.y>760&&r.y<820&&r.text.trim()==="Opponents' wooden shields are attributed to Dendro, which can be ignited";})&&rows.some(function(r){return r.x>580&&r.x<710&&r.y>810&&r.y<870&&r.text.trim()==='with Pyro Skills, rendering them defenseless.';})) return true;
    if(rows.some(function(r){return r.x>500&&r.x<650&&r.y>760&&r.y<840&&r.text.trim()==='Green symbolizes Dendro, which can be ignited by Pyro.';})) return true;
    return rows.some(function(r){return r.x>350&&r.x<470&&r.y>760&&r.y<820&&r.text.trim()==='Use Elemental Sight to see the elemental attributes of different objects. Each';})&&
      rows.some(function(r){return r.x>720&&r.x<820&&r.y>810&&r.y<870&&r.text.trim()==='element has its own color.';});
}
function actOneAdventureRankInfo(rows) {
    var second=['...You can obtain Adventure EXP from these activities and increase your',
        'Adventure Rank. More challenges andopportunities will also open up to you','as your Adventure Rank increases.'];
    if(second.every(function(t,i){return rows.filter(function(r){return r.text.trim()===t&&r.x>=380&&r.x<=950&&r.y>=775+i*33&&r.y<=800+i*33;}).length===1;}))return true;
    var lines=['There are various ways to obtain Adventure EXP and raise your Adventure',
        'Rank. Whether it be completing various Quests, looking for chests',
        'completing investigations in your Adventurer Handbook, revitalizing Ley Line','Blossoms...'];
    return lines.every(function(t,i){return rows.filter(function(r){return r.text.trim()===t&&r.x>=380&&r.x<=950&&r.y>=775+i*33&&r.y<=800+i*33;}).length===1;});
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
function actOneWolfCharacterMenuVisible(o,now) {
    var h=o&&o.hud,rows=o&&o.ocr||[];
    if(!o||!Number.isFinite(o.timestamp)||!Number.isFinite(now)||now<o.timestamp||now-o.timestamp>1000||
       o.map!==null||!h||h.world!==false||h.auto||h.loading||h.bigMap||h.dialogueReady||h.choice)return false;
    return ['Attributes','Weapons','Artifacts','Talents','Constellation'].every(function(label){
        return rows.filter(function(r){
            var text=String(r.text||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim();
            if(label==='Talents')text=text.replace(/^Falents(?=[^A-Za-z]|$)/,'Talents');
            return new RegExp('^'+label+'(?:[^A-Za-z].*)?$').test(text)&&r.x>=40&&r.x<400&&r.y>=80&&r.y<750;
        }).length===1;
    });
}
function actOneWolfAmberLevelPanelVisible(o,now) {return actOneStarterLevelPanelVisible(o,now,'Amber');}
function actOneStarterLevelPanelVisible(o,now,character) {
    var h=o&&o.hud,rows=o&&o.ocr||[];
    if(!o||!Number.isFinite(o.timestamp)||!Number.isFinite(now)||now<o.timestamp||now-o.timestamp>1000||
       o.map!==null||!h||h.world!==false||h.auto||h.loading||h.bigMap||h.dialogueReady||h.choice)return false;
    function unique(label,x0,x1,y0,y1){return rows.filter(function(r){return String(r.text||'').replace(/[\s']/g,'')===label.replace(/\s/g,'')&&r.x>=x0&&r.x<x1&&r.y>=y0&&r.y<y1;}).length===1;}
    var title=rows.filter(function(r){return r.x>=120&&r.x<500&&r.y>=0&&r.y<90;}).sort(function(a,b){return a.x-b.x;})
        .map(function(r){return String(r.text||'');}).join('').replace(/[^A-Za-z]/g,'');
    return (title===character+'LevelUp'||character==='Kaeya'&&title==='KaeyaLevetUp')&&unique('Select EXP materials',1300,1800,620,730)&&
        unique('Amount to use',1100,1400,870,955)&&unique('Required',1100,1300,980,1040)&&
        unique('Level Up',1600,1850,970,1040)&&unique('Base HP',1100,1300,220,280);
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
    var headings=rows.filter(function(r){return ['Traveler','Kaeya','Amber'].indexOf(String(r.text||'').trim())>=0;});
    var heading=headings.filter(function(r){return r.x>800&&r.x<1000&&r.y>240&&r.y<320;});
    var amount=exact('Amount to use').filter(function(r){return r.x>600&&r.x<900&&r.y>590&&r.y<670;});
    var confirm=exact('Confirm').filter(function(r){return r.x>1100&&r.x<1260&&r.y>730&&r.y<800;});
    var cancel=exact('Cancel').filter(function(r){return r.x>650&&r.x<850&&r.y>730&&r.y<800;});
    return food.length===1&&allItems.length===1&&item.length===1&&headings.length===1&&heading.length===1&&exact('Amount to use').length===1&&amount.length===1&&confirm.length===1&&cancel.length<=1&&exact('Confirm').length===1&&exact('Cancel').length===cancel.length;
}
function actOneWolfKaeyaFoodTarget(o,now) {
    if(!actOneKnownSafeFoodBoundary(o,now)) return null;
    var rows=o.ocr||[],madame=rows.filter(function(r){return String(r.text||'').trim()==='Sweet Madame'&&r.x>1300&&r.x<1650&&r.y>110&&r.y<180;}),traveler=rows.filter(function(r){return String(r.text||'').trim()==='Traveler'&&r.x>800&&r.x<1000&&r.y>240&&r.y<320;});
    var fourCards=[730,870,1010,1160].every(function(x){return rows.filter(function(r){return /^Lv\./.test(String(r.text).trim())&&r.x>=x&&r.x<=x+40&&r.y>=480&&r.y<=525;}).length===1;});
    return madame.length===1&&traveler.length===1?{x:fourCards?1045:1115,y:440}:null;
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
    if(event&&event.type==='focusGameRecovery')return !(event.resultingFocus===false&&event.ready===false&&
       Number.isFinite(event.startedAt)&&Number.isFinite(event.finishedAt)&&event.finishedAt>=event.startedAt&&
       typeof event.error==='string'&&/No scripted input was sent\.$/.test(event.error));
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
    var event=events[0],fields=['fromSession','toSession','priorEntryId','priorPauseId','betterGiProcessId','rdpSessionId','gameProcessId','verifiedAt','priorBetterGiProcessId'];
    for(var i=0;i<fields.length;i++) if(event[fields[i]]!==result[fields[i]]) return false;
    if(event.verified!==true||!Number.isFinite(result.verifiedAt)||!Number.isFinite(event.recordedAt)||result.verifiedAt>event.recordedAt||event.recordedAt>entry.timestamp||
       result.betterGiProcessId!==identity.betterGiProcessId||result.rdpSessionId!==identity.rdpSessionId||result.gameProcessId!==identity.gameProcessId||
       result.priorBetterGiProcessId!==undefined&&(!Number.isInteger(result.priorBetterGiProcessId)||result.priorBetterGiProcessId<=0)||
       !/^[A-Za-z0-9_-]{1,80}$/.test(result.fromSession||'')||result.fromSession===entry.session||
       !/^[A-Za-z0-9_-]{1,100}$/.test(result.priorEntryId||'')||!/^[A-Za-z0-9_-]{1,100}$/.test(result.priorPauseId||'')||result.priorEntryId===result.priorPauseId) return false;
    var key=entry.session+'/'+entry.id;
    if(visited[key]) return false;
    visited[key]=true;
    var parent=reports.filter(function(r){return r&&r.session===result.fromSession&&r.id===result.priorEntryId&&r.mission==='questStep'&&r.status!=='started'&&r.status!=='running';});
    var pause=reports.filter(function(r){return r&&r.session===result.fromSession&&r.id===result.priorPauseId&&r.mission==='questStep'&&r.status!=='started'&&r.status!=='running';});
    var priorEscapes=pause.length===1&&pause[0].details&&Array.isArray(pause[0].details.inputEvents)?pause[0].details.inputEvents.filter(function(e){return e&&e.type==='key'&&e.key==='VK_ESCAPE'&&Number.isFinite(e.startedAt);}):[];
    if(parent.length!==1||pause.length!==1||priorEscapes.length!==1||priorEscapes[0].startedAt>result.verifiedAt||!Number.isFinite(pause[0].timestamp)||pause[0].timestamp>result.verifiedAt||
       !actOneWolfEntryPauseChain(reports,parent[0],pause[0],{betterGiProcessId:result.priorBetterGiProcessId===undefined?identity.betterGiProcessId:result.priorBetterGiProcessId,
           rdpSessionId:identity.rdpSessionId,gameProcessId:identity.gameProcessId},depth+1,visited)) return false;
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
            if(actOneWolfResumeGameInput(e)&&(!Number.isFinite(e.startedAt)||e.startedAt>=escape.startedAt)) return false;
        }
    }
    if(entry.details&&entry.details.result&&entry.details.result.step==='wolfPartyStart')
        return entry.status==='completed'&&actOneWolfPartyEntryChain(reports,entry,entry.session);
    return actOneWolfResumeReceiptChain(reports,entry,identity,depth,visited);
}
function actOneValidateWolfResume(evidence,priorReports,currentReports,currentSession,rdpSession,observation,now,windowInfo) {
    var fields=['fromSession','toSession','priorEntryId','priorPauseId','betterGiProcessId','rdpSessionId','gameProcessId','verifiedAt'];
    if(evidence&&Object.prototype.hasOwnProperty.call(evidence,'priorBetterGiProcessId')) {
        if(!Number.isInteger(evidence.priorBetterGiProcessId)||evidence.priorBetterGiProcessId<=0)return null;
        fields.push('priorBetterGiProcessId');
    }
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
    if(!entry||!pause||!actOneWolfEntryPauseChain(priorReports,entry,pause,{betterGiProcessId:evidence.priorBetterGiProcessId===undefined?evidence.betterGiProcessId:evidence.priorBetterGiProcessId,rdpSessionId:evidence.rdpSessionId,gameProcessId:evidence.gameProcessId},0,{})||
       pause.timestamp>evidence.verifiedAt||!evidence.priorPauseId) return null;
    var escapes=pause.details.inputEvents.filter(function(e){return e&&e.type==='key'&&e.key==='VK_ESCAPE'&&Number.isFinite(e.startedAt);});
    if(escapes[0].startedAt>evidence.verifiedAt) return null;
    for(var i=0;i<priorReports.length;i++) {
        var report=priorReports[i],events=report&&report.details&&report.details.inputEvents;
        if(!Array.isArray(events)) continue;
        for(var j=0;j<events.length;j++) {
            var e=events[j];if(report===pause&&e===escapes[0]) continue;
            if(actOneWolfResumeGameInput(e)&&(!Number.isFinite(e.startedAt)||e.startedAt>=escapes[0].startedAt)) return null;
        }
    }
    if(currentReports.some(function(r){return r&&r.session===currentSession&&r.mission==='questStep'&&r.details&&r.details.inputEvents&&
        r.details.inputEvents.some(function(e){return e&&e.type==='wolfResumeProof';});})) return null;
    var proof={verified:true,fromSession:evidence.fromSession,toSession:evidence.toSession,priorEntryId:entry.id,priorPauseId:pause.id,
        betterGiProcessId:evidence.betterGiProcessId,rdpSessionId:evidence.rdpSessionId,gameProcessId:evidence.gameProcessId,verifiedAt:evidence.verifiedAt};
    if(evidence.priorBetterGiProcessId!==undefined)proof.priorBetterGiProcessId=evidence.priorBetterGiProcessId;
    return proof;
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
            e.betterGiProcessId===result.betterGiProcessId&&e.priorBetterGiProcessId===result.priorBetterGiProcessId&&e.rdpSessionId===result.rdpSessionId&&e.gameProcessId===result.gameProcessId&&e.verifiedAt===result.verifiedAt;}))
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
        while(true){var remaining=deadline-ops.now();if(remaining<=0)break;await ops.sleep(Math.min(20,remaining));ops.checkStop();}
        ops.click(target.x,target.y);
        deadline=ops.now()+60;
        while(true){var remaining=deadline-ops.now();if(remaining<=0)break;await ops.sleep(Math.min(20,remaining));ops.checkStop();}
    } finally { ops.release(); }
}
if (typeof module !== 'undefined' && module.exports) module.exports = { autoCropNeeded:actTwoAutoCropNeeded, indoorSafe:actTwoIndoorSafe, originalAccount:actTwoOriginalAccount, enterGameTitleFrame:actOneEnterGameTitleFrame, enterGameTarget:actOneEnterGameTarget, enterWorldTarget:actOneEnterWorldTarget, enterGameAuthPrompt:actOneEnterGameAuthPrompt, enterGameUnknownUi:actOneEnterGameUnknownUi, enterGameLoading:actOneEnterGameLoading, windowedGameReady:actOneWindowedGameReady, windowModeDecision:actOneWindowModeDecision, windowedGameChord:actOneWindowedGameChord, objectiveRows: actOneObjectiveRows, enemyBarSize:actOneEnemyBarSize, enemyBarAnchored:actOneEnemyBarAnchored, health:actOneHealth, fullHealthRows:actOneFullHealthRows, corroboratedFullHealth:actOneCorroboratedFullHealth, numericHealthHalves:actOneNumericHealthHalves, dialogueReady:actOneDialogueReady, navigateQuestState:actOneNavigateQuestState, navigateQuestButton:actOneNavigateQuestButton, trackQuestState:actOneTrackQuestState, trackQuestTarget:actOneTrackQuestTarget, altClick:actOneAltClick, mergeControlCropRows:actOneMergeControlCropRows, groundControlEvidence:actOneGroundControlEvidence, needsControlCrop:actOneNeedsControlCrop, glideForwardState:actOneGlideForwardState, glideForward:actOneGlideForward, glideOpenState:actOneGlideOpenState, glideOpen:actOneGlideOpen, aerialBossLabels:actOneAerialBossLabels, aerialBossState:actOneAerialBossState, falconWaypointTarget:actOneFalconWaypointTarget, falconWaypointReady:actOneFalconWaypointReady, fullMapState:actOneFullMapState, navigationMapAnchor:actOneNavigationMapAnchor, acceptNavigationPosition:actOneAcceptNavigationPosition, namedInteractionVisible:actOneNamedInteractionVisible, resolveInteractionObjective:actOneResolveInteractionObjective, shouldReadInteractionCrop:actOneShouldReadInteractionCrop, shouldReadStatueInteractionCrop:actOneShouldReadStatueInteractionCrop, interactionCropF:actOneInteractionCropF, shouldReadWolfOpenDoorCrop:actOneShouldReadWolfOpenDoorCrop, wolfOpenDoorF:actOneWolfOpenDoorF, falconStartTarget:actOneFalconStartTarget, falconPartyTarget:actOneFalconPartyTarget, wolfPartyTarget:actOneWolfPartyTarget, wolfEntryHud:actOneWolfEntryHud, wolfDomainHud:actOneWolfDomainHud, wolfPauseOnlyHud:actOneWolfPauseOnlyHud, wolfDeadTrialPauseOnlyHud:actOneWolfDeadTrialPauseOnlyHud, wolfReviveItemModalVisible:actOneWolfReviveItemModalVisible, wolfReviveEggTarget:actOneWolfReviveEggTarget, wolfExitFlameProof:actOneWolfExitFlameProof, wolfKaeyaSkillReady:actOneWolfKaeyaSkillReady, wolfDefensiveCryoReady:actOneWolfDefensiveCryoReady, wolfAdvanceState:actOneWolfAdvanceState, wolfReturnToEntranceReady:actOneWolfReturnToEntranceReady, falconDomainHud:actOneFalconDomainHud, falconAimHud:actOneFalconAimHud, falconPyroInfo:actOneFalconPyroInfo, falconContinueTarget:actOneFalconContinueTarget, wolfInventoryContinueTarget:actOneWolfInventoryContinueTarget, wolfFoodInventoryReady:actOneWolfFoodInventoryReady, wolfFoodGridReady:actOneWolfFoodGridReady, knownSafeFoodBoundary:actOneKnownSafeFoodBoundary, wolfKaeyaFoodTarget:actOneWolfKaeyaFoodTarget, wolfKaeyaFoodSelected:actOneWolfKaeyaFoodSelected, wolfFeedKaeyaTarget:actOneWolfFeedKaeyaTarget, validateFalconResume:actOneValidateFalconResume, validateWolfResume:actOneValidateWolfResume, wolfEntryProven:actOneWolfEntryProven, wolfEntryProof:actOneWolfEntryProof, wolfLookDelta:actOneWolfLookDelta };
if (typeof module !== 'undefined' && module.exports) Object.assign(module.exports,{wolfAirPauseOnlyHud:actOneWolfAirPauseOnlyHud,wolfWindRideGroundState:actOneWolfWindRideGroundState,wolfWindRideProof:actOneWolfWindRideProof,wolfGlideState:actOneWolfGlideState});
if (typeof module !== 'undefined' && module.exports) Object.assign(module.exports,{wolfRecoveryTravelHud:actOneWolfRecoveryTravelHud,wolfBankApproachReady:actOneWolfBankApproachReady,wolfCharacterMenuVisible:actOneWolfCharacterMenuVisible,wolfAmberLevelPanelVisible:actOneWolfAmberLevelPanelVisible});

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
if (typeof module !== 'undefined' && module.exports) Object.assign(module.exports,{wolfApproachEnemyTarget:actOneWolfApproachEnemyTarget,wolfHydroApproachProof:actOneWolfHydroApproachProof,wolfApproachHistory:actOneWolfApproachHistory,wolfCryoCooldownRemaining:actOneWolfCryoCooldownRemaining,wolfSpikeActive:actOneWolfSpikeActive,wolfSpikeSurface:actOneWolfSpikeSurface});

function actOneWolfClosingDialogueState(o, now, session) {
    var h=o&&o.hud,rows=o&&o.ocr||[];
    if(!o||o.session!==session||!Number.isInteger(o.frameId)||!Number.isFinite(o.timestamp)||
       now<o.timestamp||now-o.timestamp>1000||o.map!==null||!h||h.world!==false||h.auto!==true||
       h.dialogueReady!==true||h.choice!==false||h.health!==null||h.journal||h.bigMap||h.tutorialStep||
       !Array.isArray(h.enemyBars)||h.enemyBars.length) return false;
    return rows.some(function(r){return r&&String(r.text||'').trim()==='Auto'&&r.x>=0&&r.x<300&&r.y>=0&&r.y<100;})&&
        rows.some(function(r){return r&&['Kaeya','Paimon'].indexOf(String(r.text||'').trim())>=0&&r.x>600&&r.x<1200&&r.y>830&&r.y<900;})&&
        rows.some(function(r){return r&&String(r.text||'').trim().length>5&&r.x>100&&r.x<1800&&r.y>=900&&r.y<1000;});
}
if(typeof module!=='undefined'&&module.exports) Object.assign(module.exports,{wolfClosingDialogueState:actOneWolfClosingDialogueState});
if(typeof module!=='undefined'&&module.exports) Object.assign(module.exports,{lionFalconWaypointReady:actOneLionFalconWaypointReady});

function createActOneAdapter(sessionId) {
    var pauseProtectionActive=false,pauseProtectionObserver=null,pauseProtectionKeys=Object.create(null),pauseProtectionLastInputFrame=-1,pauseProtectionLastStatusAt=-Infinity;
    function loadLocalPause(){
        var protector=eval(file.readTextSync('local-pause.js')+'\nActOneLocalPause;');
        if(!protector||typeof protector.ensure!=='function')throw new Error('Local verified-pause protector is required before unpausing');
        return protector;
    }
    function lionLiveContext(o){
        var guard=eval(file.readTextSync('lion-live-guard.js')+'\nActOneLionLiveGuard;');
        var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json')),handoff=null;
        if(file.isExists('lion-session-handoff.json')){
            var candidate=JSON.parse(file.readTextSync('lion-session-handoff.json'));
            if(candidate.session===request.session){
                if(!/^[a-z0-9]+-[a-z0-9]+$/.test(candidate.sourceSession))throw new Error('Invalid Lion source session');
                handoff=candidate;reports=reports.concat(JSON.parse(file.readTextSync('reports/'+candidate.sourceSession+'.json')));
                if(candidate.predecessorSession){
                    if(!/^[a-z0-9]+-[a-z0-9]+$/.test(candidate.predecessorSession))throw new Error('Invalid Lion predecessor');
                    reports=reports.concat(JSON.parse(file.readTextSync('reports/'+candidate.predecessorSession+'.json')));
                }
            }
        }
        return {guard:guard,reports:reports,handoff:handoff,entry:function(frame){return guard.entry(reports,request.session,frame,handoff);}};
    }
    async function finishWithLocalPause(protector,api,initial,observe,afterFrame,result,operationError,pauseSeed){
        if(api&&typeof api.actTwoHideoutTutorialReady==='function'&&api.actTwoHideoutTutorialReady(lastObservation)){release();result=result||{status:'stopped',reason:operationError};result.menuHeld='Recognized Raptor aerial tutorial; inspect before continuing';result.pauseVerified=false;result.frameId=lastObservation.frameId;return result;}
        pauseProtectionActive=true;pauseProtectionObserver=observe;
        events.push({type:'pauseProtectionStarted',frameId:initial.frameId,startedAt:Date.now()});
        var proof=null;
        async function pending(info){try{await api.pausePending(info);}catch(e){/* Keep ownership if status persistence fails. */}}
        var protectorStarted=Date.now(),protectorAttempts=0;
        while(!proof){
            if(++protectorAttempts>3 || Date.now()-protectorStarted>=65000){
                release();pauseProtectionActive=false;
                var exhausted=new Error('Pause protection exhausted: pause is UNVERIFIED; operator intervention required');
                exhausted.code='PAUSE_PROTECTION_EXHAUSTED';throw exhausted;
            }
            try{
                var candidate=await protector.ensure({session:request.session,afterFrameId:afterFrame,initialObservation:protectorAttempts===1?pauseSeed:null,maxWaitMs:(request.mission==='questStep'&&['actTwoMapClose','actTwoRecover','actTwoExam','actTwoField','actTwoHideoutAerial'].indexOf(request.step)>=0||request.mission==='navigation'&&request.objective==='Explore for Adventure Rank')?12000:60000},api);
                if(candidate&&candidate.conversationActive===true&&candidate.session===request.session&&lastObservation&&
                    candidate.frameId===lastObservation.frameId&&candidate.timestamp===lastObservation.timestamp&&api.pauseDialogueHandoff(lastObservation)){
                    release();pauseProtectionActive=false;
                    events.push({type:'pauseProtectionDialogueHandoff',frameId:lastObservation.frameId,startedAt:Date.now()});
                    result=result||{status:'stopped',reason:operationError};result.pauseVerified=false;result.conversationActive=true;result.frameId=lastObservation.frameId;return result;
                }
                var visible=actOneLocalPauseProof(lastObservation,Date.now(),request.session);
                if(candidate&&candidate.verified===true&&Object.isFrozen(candidate)&&Object.isFrozen(candidate.evidence)&&
                   candidate.session===request.session&&lastObservation&&candidate.pauseFrameId===lastObservation.frameId&&
                   candidate.timestamp===lastObservation.timestamp&&candidate.pauseFrameId>afterFrame&&visible&&candidate.kind===visible.kind)proof=candidate;
                else await pending({phase:'pause-proof-invalid',error:'Fresh immutable pause proof did not match the last capture'});
            }catch(e){
                await pending({phase:'pause-protector-error',error:String(e&&e.message||e)});
                if(e&&(e.code==='PAUSE_PROTECTION_EXHAUSTED'||e.code==='CAPTURE_STORAGE_BLOCKED')){release();pauseProtectionActive=false;throw e;}
            }
            if(!proof){try{await sleep(250);}catch(e){await pending({phase:'pause-wait-error',error:String(e&&e.message||e)});}}
        }
        pauseProtectionActive=false;
        events.push({type:'pauseProtectionVerified',kind:proof.kind,frameId:proof.pauseFrameId,startedAt:Date.now()});
        result=result||{status:'stopped',step:request.step,reason:operationError||'Runner failed after unpausing'};
        result.pauseVerified=true;result.pauseProof=proof;result.frameId=proof.pauseFrameId;
        return result;
    }
    var lionFieldState={closed:false,selected:false,fought:false,returnedAmber:false,paused:false,lastInputFrame:-1,observer:null,chartedProbePending:false,chartedProbeAnchor:null,climbReleaseArmed:false,climbReleaseAttempted:false};
    var lisaRecoveryState={closed:false,mapOpened:false,teleported:false,lastInputFrame:-1,observer:null};
    function lisaRecoveryCurrent(o){return !!(request&&request.mission==='questStep'&&request.step==='lisaStatueRecovery'&&o&&lastObservation&&
        o.session===request.session&&o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&o.frameId>lisaRecoveryState.lastInputFrame);}
    var lisaClimbReleaseDefinition=null;
    function lisaClimbReleaseModule(){
        if(!lisaClimbReleaseDefinition)lisaClimbReleaseDefinition=eval(file.readTextSync('lisa-climb-release.js')+'\nActOneLisaClimbRelease;');
        if(!lisaClimbReleaseDefinition||typeof lisaClimbReleaseDefinition.ready!=='function')throw new Error('Lisa climb release guard is required before inventory close');
        return lisaClimbReleaseDefinition;
    }
    function lionFieldModule(){return eval(file.readTextSync('lion-field-combat.js')+'\nActOneLionFieldCombat;');}
    function lionFieldCurrent(o){return !!(request&&request.mission==='questStep'&&['lionFieldCombat','lionFieldProbe'].indexOf(request.step)>=0&&o&&lastObservation&&
        o.session===request.session&&o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&o.frameId>lionFieldState.lastInputFrame);}
    function chartedWindriseEvidence(){
        try{
            if(!request||request.mission!=='questStep'||request.step!=='lionFieldProbe')return null;
            var marker=JSON.parse(file.readTextSync('windrise-charted.json'));
            if(!marker||marker.kind!=='windriseCharted'||marker.session!==request.session||marker.witnessVerified!==true||
               !Number.isInteger(marker.revealFrameId)||marker.revealFrameId>=request.expectedFrameId||
               !Number.isFinite(marker.createdAt)||marker.createdAt>Date.now())return null;
            var prefix='observations/'+request.session+'/frame-'+String(marker.revealFrameId).padStart(4,'0');
            if(!file.isExists(prefix+'.png'))return null;
            var map=JSON.parse(file.readTextSync(prefix+'.json'));
            var proof=actOneLocalPauseProof(map,map.timestamp,request.session);
            if(!map||map.frameId!==marker.revealFrameId||map.timestamp>marker.createdAt||!proof||proof.kind!=='map'||
               map.ocr.filter(function(r){return r.text.trim()==='Windrise'&&r.x>=850&&r.x<=1050&&r.y>=400&&r.y<=500;}).length!==1)return null;
            // This proves that the region was revealed, not that its unlock animation was paused.
            return {frameId:map.frameId,x:-1265.917,y:1928.381};
        }catch(e){return null;}
    }
    function pausedNavigationProbeAnchor(){
        if(!request||request.step!=='lionFieldProbe'||!file.isExists('paused-lisa-position-probe.json'))return null;
        var marker=JSON.parse(file.readTextSync('paused-lisa-position-probe.json'));
        if(!marker||typeof marker.receiptId!=='string'||!/^mission-[a-f0-9]{32}$/.test(marker.receiptId))
            throw new Error('Invalid paused navigation probe receipt');
        var receipt=JSON.parse(file.readTextSync('receipts/'+request.session+'/'+marker.receiptId+'.json'));
        var result=receipt&&receipt.details&&receipt.details.result,proof=result&&result.pauseProof;
        if(!result||!Number.isInteger(result.fieldFrameId)||!proof||!Number.isInteger(proof.pauseFrameId))
            throw new Error('Missing paused navigation probe evidence');
        var fieldPrefix='observations/'+request.session+'/frame-'+String(result.fieldFrameId).padStart(4,'0');
        var pausePrefix='observations/'+request.session+'/frame-'+String(proof.pauseFrameId).padStart(4,'0');
        if(!file.isExists(fieldPrefix+'.png')||!file.isExists(pausePrefix+'.png'))throw new Error('Saved navigation and pause images required');
        var field=JSON.parse(file.readTextSync(fieldPrefix+'.json')),paused=JSON.parse(file.readTextSync(pausePrefix+'.json'));
        var validator=eval(file.readTextSync('paused-navigation-anchor.js')+'\nActOnePausedNavigationAnchor;');
        var anchor=validator.seed(request,marker,receipt,field,paused,Date.now());
        if(!anchor)throw new Error('Verified paused Lisa position probe marker required');
        if(marker.releaseClimb!==undefined&&typeof marker.releaseClimb!=='boolean')throw new Error('Invalid Lisa climb release flag');
        if(marker.releaseClimb===true){
            var sourcePrefix='observations/'+request.session+'/frame-'+String(proof.sourceFrameId).padStart(4,'0');
            if(result.navigationStatus!=='stopped'||result.reason!=='Lisa navigation refuses climbing'||
               !file.isExists(sourcePrefix+'.png'))throw new Error('Verified paused navigation climb witness required');
            var climbSource=JSON.parse(file.readTextSync(sourcePrefix+'.json'));
            if(!climbSource||climbSource.frameId!==proof.sourceFrameId||climbSource.frameId<=field.frameId||
               climbSource.timestamp<field.timestamp||climbSource.timestamp>proof.timestamp||
               !climbSource.map||climbSource.map.map!=='Teyvat'||![climbSource.map.x,climbSource.map.y].every(Number.isFinite)||
               Math.hypot(climbSource.map.x-field.map.x,climbSource.map.y-field.map.y)>5||
               !climbSource.hud||!climbSource.hud.health||climbSource.hud.health.current!==field.hud.health.current||
               climbSource.hud.health.max!==field.hud.health.max||
               !lisaClimbReleaseModule().ready(climbSource,climbSource.timestamp,request.session,
                   {armed:true,releaseAttempted:false,lastInputFrame:field.frameId}))throw new Error('Saved adjacent-ledge climb evidence is invalid');
            anchor.releaseClimb=true;anchor.climbWitnessFrameId=climbSource.frameId;
            anchor.climbWitnessPosition={x:climbSource.map.x,y:climbSource.map.y};
        }
        marker.usedAt=Date.now();
        if(!file.writeTextSync('paused-lisa-position-probe.json',JSON.stringify(marker)))throw new Error('Cannot consume paused position probe marker');
        var consumed=JSON.parse(file.readTextSync('paused-lisa-position-probe.json'));
        if(consumed.usedAt!==marker.usedAt||consumed.receiptId!==marker.receiptId||consumed.session!==marker.session||consumed.frameId!==marker.frameId||consumed.releaseClimb!==marker.releaseClimb)
            throw new Error('Paused position probe consumption readback failed');
        anchor.receiptId=marker.receiptId;
        return anchor;
    }
    var windriseState={used:false,moves:0,turns:0,interactions:0,paused:false,pauseOnly:false,lastInputFrame:-1,observer:null,plan:null};
    var windriseDefinition=null;
    var lisaNavigationState={active:false,lastInputFrame:-1,lastField:null};
    function lisaNavigationRequest(){return !!(request&&request.mission==='navigation'&&request.objective==='Meet Lisa at the temple');}
    function lisaNavigationPermit(){
        try{
            if(!lisaNavigationRequest())return null;
            var p=JSON.parse(file.readTextSync('lisa-navigation-witness.json')),now=Date.now();
            if(!p||p.kind!=='chartedLisaNavigation'||p.usedAt||p.session!==request.session||p.frameId!==request.expectedFrameId||
               p.witnessVerified!==true||!Number.isInteger(p.witnessFrameId)||p.witnessFrameId>=p.frameId||
               !Number.isFinite(p.createdAt)||p.createdAt>now||now-p.createdAt>120000)return null;
            var prefix='observations/'+request.session+'/frame-'+String(p.witnessFrameId).padStart(4,'0');
            if(!file.isExists(prefix+'.png'))return null;
            var witness=JSON.parse(file.readTextSync(prefix+'.json')),m=witness.map;
            if(!witness||witness.frameId!==p.witnessFrameId||!actOneLionFieldWorld(witness,witness.timestamp,request.session,0.6)||
               !m||m.map!=='Teyvat'||![m.x,m.y,m.cameraAngle].every(Number.isFinite)||
               Math.hypot(m.x+1265.917,m.y-1928.381)>500||now-witness.timestamp>120000||p.createdAt<witness.timestamp||
               !Array.isArray(witness.hud.enemyBars)||(witness.hud.enemyBars.length&&p.evade!==true))return null;
            var first=request.waypoints&&request.waypoints[0];
            if(!first||first.map!=='Teyvat'||Math.hypot(first.x-m.x,first.y-m.y)>5)return null;
            return {permit:p,witness:witness};
        }catch(e){return null;}
    }
    function lisaNavigationInputReady(o){
        return !!(lisaNavigationRequest()&&lisaNavigationState.active&&o&&lastObservation&&o.session===request.session&&
            o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&o.frameId>lisaNavigationState.lastInputFrame&&
            actOneLionFieldWorld(o,Date.now(),request.session,0.6)&&o.map&&o.map.map==='Teyvat'&&
            [o.map.x,o.map.y,o.map.cameraAngle].every(Number.isFinite)&&Array.isArray(o.hud.enemyBars)&&
            (!o.hud.enemyBars.length||Date.now()<lisaNavigationState.evadeUntil));
    }
    var statueDialogueDefinition=null,statueDialogueSource=null,statueDialogueState={advanceAttempted:false,leaveAttempted:false,lastInputFrame:-1};
    function statueDialogueModule(){
        // A pending pause can adopt a corrected pure UI policy without killing
        // its guard or restarting the elevated child. Pin the returned policy
        // for each action; input ownership and attempt bounds stay in this adapter.
        var source=file.readTextSync('statue-dialogue.js');
        if(!statueDialogueDefinition||source!==statueDialogueSource){
            var candidate=eval(source+'\nActOneStatueDialogue;');
            if(!candidate||typeof candidate.action!=='function')throw new Error('Statue dialogue resolver is required before the interaction');
            statueDialogueDefinition=candidate;statueDialogueSource=source;
        }
        if(!statueDialogueDefinition||typeof statueDialogueDefinition.action!=='function')throw new Error('Statue dialogue resolver is required before the interaction');
        return statueDialogueDefinition;
    }
    function windriseModule(){
        if(!windriseDefinition)windriseDefinition=eval(file.readTextSync('windrise-reveal.js')+'\nActOneWindriseReveal;');
        return windriseDefinition;
    }
    function windrisePermit() {
        try {
            var p=JSON.parse(file.readTextSync('windrise-reveal.json')),now=Date.now();
            if(!request||request.mission!=='questStep'||request.step!=='windriseReveal'||!p||p.kind!=='windriseReveal'||p.usedAt||
               p.session!==request.session||p.frameId!==request.expectedFrameId||!Number.isInteger(p.witnessFrameId)||p.witnessFrameId>p.frameId||p.witnessVerified!==true||
               !Number.isFinite(p.createdAt)||now<p.createdAt||now-p.createdAt>120000||!Number.isInteger(p.lastKnownFrameId)||
               p.lastKnownFrameId>=p.witnessFrameId||p.lastKnownFrameId<1)return null;
            if(p.action==='forward'||p.action==='retreat'){if(!Number.isInteger(p.holds)||p.holds<1||p.holds>24)return null;}
            else if(p.action==='look'){if(!Number.isInteger(p.dx)||Math.abs(p.dx)>250||p.dx===0)return null;}
            else if(p.action==='interact'){}
            else return null;
            var prefix='observations/'+p.session+'/frame-'+String(p.witnessFrameId).padStart(4,'0');
            if(!file.isExists(prefix+'.png')||!file.isExists(prefix+'.json'))return null;
            var witness=JSON.parse(file.readTextSync(prefix+'.json'));
            var witnessModule=windriseModule(),witnessGate=p.action==='retreat'?witnessModule.retreatReady:p.action==='interact'?witnessModule.statueInteractReady:witnessModule.fieldReady;
            if(witness.session!==p.session||witness.frameId!==p.witnessFrameId||typeof witnessGate!=='function'||!witnessGate(witness,witness.timestamp,p.session)||
               p.createdAt<witness.timestamp||now-witness.timestamp>120000)return null;
            if(p.witnessFrameId<p.frameId){
                var pausePrefix='observations/'+p.session+'/frame-'+String(p.frameId).padStart(4,'0');
                if(!file.isExists(pausePrefix+'.png')||!file.isExists(pausePrefix+'.json'))return null;
                var pauseSource=JSON.parse(file.readTextSync(pausePrefix+'.json'));
                if(pauseSource.frameId!==p.frameId||pauseSource.timestamp<witness.timestamp||p.createdAt<pauseSource.timestamp||
                   !actOneLocalPauseProof(pauseSource,pauseSource.timestamp,p.session))return null;
            }
            if(p.navigationReceiptId!==undefined){
                // A completed navigation receipt supplies historical location only.
                // The fresh witnessed HUD and per-hold checks still authorize every input.
                if(!/^mission-[a-f0-9]{32}$/.test(p.navigationReceiptId)||
                   ['forward','retreat','look'].indexOf(p.action)<0||
                   (p.action==='retreat'&&p.holds>2)||(p.action==='forward'&&p.holds>12))return null;
                var receipt=JSON.parse(file.readTextSync('receipts/'+p.session+'/'+p.navigationReceiptId+'.json'));
                var result=receipt&&receipt.details&&receipt.details.result,proof=result&&result.pauseProof;
                if(!result||result.fieldFrameId!==p.lastKnownFrameId||!proof||!Number.isInteger(proof.pauseFrameId))return null;
                var fieldPrefix='observations/'+p.session+'/frame-'+String(p.lastKnownFrameId).padStart(4,'0');
                var pausePrefix='observations/'+p.session+'/frame-'+String(proof.pauseFrameId).padStart(4,'0');
                if(!file.isExists(fieldPrefix+'.png')||!file.isExists(pausePrefix+'.png'))return null;
                var savedField=JSON.parse(file.readTextSync(fieldPrefix+'.json'));
                var savedPause=JSON.parse(file.readTextSync(pausePrefix+'.json'));
                var validator=eval(file.readTextSync('paused-navigation-anchor.js')+'\nActOnePausedNavigationAnchor;');
                var marker={kind:'pausedLisaPositionProbe',session:p.session,frameId:p.frameId,witnessVerified:true,
                    receiptId:p.navigationReceiptId,createdAt:p.createdAt};
                if(!validator.seed(request,marker,receipt,savedField,savedPause,now))return null;
                return p;
            }
            var known=JSON.parse(file.readTextSync('observations/'+p.session+'/frame-'+String(p.lastKnownFrameId).padStart(4,'0')+'.json'));
            if(known.session!==p.session||known.frameId!==p.lastKnownFrameId||!known.map||known.map.map!=='Teyvat'||
               !Number.isFinite(known.map.x)||!Number.isFinite(known.map.y)||Math.hypot(known.map.x+1124.705,known.map.y-2080.445)>10||
               !known.hud||!known.hud.health||known.hud.health.max!==1186)return null;
            return p;
        } catch(_){return null;}
    }
    function windriseCurrent(o) {
        return !!(request&&request.mission==='questStep'&&request.step==='windriseReveal'&&o&&lastObservation&&o.session===request.session&&
            o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&o.frameId>windriseState.lastInputFrame);
    }
    var worldInventoryCloseAttempted=false;
    var expectedSession = Number(sessionId), held = null, request = null, events = [], lastObservation = null, navLastAcceptedPosition = null, heartbeat = null, focusRecoveryAttempted = false, wolfInfoAttempted = false, lionDomainStartAttempted=false, lionPartyStartAttempted=false, lionFalconWaypointAttempted=false, wolfContinueAttempted = false, wolfInventoryContinueAttempted = false, wolfInventoryOpenAttempted = false, wolfKaeyaFoodAttempted = false, wolfFeedKaeyaAttempted = false, wolfRecoveryFoodUseAttempted=false, wolfRecoveryFoodSelectAttempted=false, wolfRecoveryFoodFeedAttempted=false, wolfRecoveryFoodCloseAttempted=false, wolfExitFlameAttempted=false, wolfWindContinueAttempted=false, wolfWindSpaceAttempted=false, wolfWindRideContinueAttempted=false, wolfWindRideSpaceAttempted=false, wolfGlideContinueAttempted=false, wolfGlideMoves=0, wolfGlideLastMoveFrame=null, wolfGlideBaseline=null, wolfDefensiveCryoAttempted = false, wolfAimCryoAttempted = false, wolfCloseFoodAttempted = false, wolfCloseFoodCompletedAt = null, wolfCloseFoodLookAttempted = false, wolfCloseFoodForwardAttempted = false, wolfCloseFoodSkillAttempted = false, wolfTurretSkillAttempted = false, wolfTurretForwardAttempted = false, wolfTurretSkillFinishedAt = null, wolfTurretBaseline = null, wolfConsoleContinueAttempted=false, wolfConsoleInteractAttempted=false, wolfApproachContinueAttempted=false, wolfApproachMoveAttempted=false, wolfApproachHydroFrame=null,wolfApproachHydroReceiptId=null,wolfCombatSeekForwards=0,wolfCombatSeekTurns=0,wolfCombatSeekFrames=[],wolfBurstContinueAttempted=false,wolfBurstQAttempted=false,wolfBurstPauseAttempted=false,wolfCryoContinueAttempted=false,wolfCryoResumeConfirmedAt=null,wolfCryoBaseline=null,wolfCryoSkillAttempted=false,wolfCryoPauseAttempted=false,wolfCryoWaitMs=6500,wolfCryoWaitPlan=null,wolfReviveContinueAttempted=false,wolfReviveContinueFrame=null,wolfReviveSelectAttempted=false,wolfReviveAmberBaseline=null,wolfReviveRecoverySelectAttempted=false,wolfReviveRecoveryConfirmAttempted=false,wolfReviveRecoverySelectFrame=null,wolfReviveRecoveryConfirmFrame=null,wolfReviveRecoveryAmberBaseline=null,ocrPrimitiveMs=0,ocrReadCount=0;
    function dispose(v) { if (v && typeof v.dispose === 'function') v.dispose(); }
    var wolfCryoLastInputFrame = null;
    var wolfSpikeState={continued:false,selectedKaeya:false,cast:false,selectedAmber:false,moves:0,paused:false,lastInputFrame:-1,pauseFrame:null,readyAt:null,amberBaseline:null,kaeyaBaseline:null,iceVerified:false,bankVerified:false,reuseSource:null,usingExistingIce:false,jumpAttempted:false,crossingCharacter:'amber'};
    function newWolfSecondState() {
        return {continued:false,selectedKaeya:false,cast:false,selectedAmber:false,moves:0,paused:false,
            lastInputFrame:-1,pauseFrame:null,readyAt:null,kaeyaBaseline:null,amberBaseline:null,
            iceVerified:false,lastAlignedFrame:null,alignmentConfirmedFrame:null,crossingCharacter:'amber',bankPosition:null,
            approachLimit:0,approaches:0,bridgeFloorMin:0.9};
    }
    var wolfSecondState=newWolfSecondState(),wolfCharactersStage=0,wolfCharactersLastFrame=-1;
    var wolfWitnessState={continued:false,acted:false,paused:false,lastInputFrame:-1,permit:null,baseline:null};
    var wolfClosingState={begun:false,inputs:0,lastFrame:-1,lastFinishedAt:null};
    function wolfClosingPermit(o) {
        try {
            var p=JSON.parse(file.readTextSync('wolf-closing-dialogue.json'));
            if(!request||request.mission!=='recover'||!p||p.kind!=='wolfClosingDialogue'||p.session!==request.session||
               p.frameId!==request.expectedFrameId||p.usedAt||!Number.isInteger(p.witnessFrameId)||p.witnessFrameId!==p.frameId||
               !Number.isFinite(p.createdAt)||Date.now()<p.createdAt||Date.now()-p.createdAt>120000||
               typeof p.strikeRequestId!=='string'||!/^mission-[a-f0-9]{32}$/.test(p.strikeRequestId))return null;
            var prefix='observations/'+request.session+'/frame-'+String(p.witnessFrameId).padStart(4,'0');
            if(!file.isExists(prefix+'.png'))return null;
            var witness=JSON.parse(file.readTextSync(prefix+'.json'));
            if(!witness||witness.frameId!==p.witnessFrameId||witness.timestamp>Date.now()||!actOneWolfClosingDialogueState(witness,witness.timestamp,request.session)||
               !(witness.ocr||[]).some(function(r){return String(r.text||'').trim()==='Bravo! What a performance!'&&r.y>=900&&r.y<1000;}))return null;
            var history=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(history,request.session))return null;
            var receipt=JSON.parse(file.readTextSync('receipts/'+request.session+'/'+p.strikeRequestId+'.json'));
            var matches=history.filter(function(r){return r&&r.id===p.strikeRequestId&&r.session===request.session&&r.status===receipt.status;});
            if(matches.length!==1||JSON.stringify(matches[0].details)!==JSON.stringify(receipt.details))return null;
            var result=receipt.details&&receipt.details.result,events=receipt.details&&receipt.details.inputEvents||[];
            var strikes=events.filter(function(e){return e&&e.type==='wolfWitnessAction'&&e.action==='strike';});
            var keys=events.filter(function(e){return e&&e.type==='key';});
            if(receipt.id!==p.strikeRequestId||receipt.mission!=='questStep'||receipt.session!==request.session||['stopped','completed'].indexOf(receipt.status)<0||!result||
               result.step!=='wolfWitnessAction'||result.action!=='strike'||result.actionAttempts!==1||strikes.length!==1||keys.length!==1)return null;
            var strike=strikes[0],key=keys[0];
            if(strike.rootDirected!==true||!Number.isInteger(strike.frameId)||strike.frameId<0||key.key!=='VK_LBUTTON'||key.durationMs!==60||key.frameId!==strike.frameId||
               !Number.isFinite(strike.startedAt)||!Number.isFinite(strike.finishedAt)||strike.finishedAt<strike.startedAt||
               !Number.isFinite(key.startedAt)||!Number.isFinite(key.finishedAt)||key.finishedAt<key.startedAt||key.startedAt<strike.startedAt||key.finishedAt>strike.finishedAt||
               witness.frameId<=strike.frameId||witness.timestamp<=strike.finishedAt)return null;
            if(history.some(function(r){return r&&r.session===request.session&&Array.isArray(r.details&&r.details.inputEvents)&&
                r.details.inputEvents.some(function(e){return e&&e.type!=='controllerRevision'&&Number.isFinite(e.startedAt)&&e.startedAt>strike.finishedAt;});}))return null;
            return p;
        }catch(e){return null;}
    }
    function wolfClosingContinuationPermit(o) {
        try {
            var p=JSON.parse(file.readTextSync('wolf-closing-dialogue.json'));
            if(!request||request.mission!=='recover'||!p||p.kind!=='wolfClosingDialogueContinue'||p.session!==request.session||
               p.frameId!==request.expectedFrameId||p.witnessFrameId!==p.frameId||p.usedAt||
               !Number.isFinite(p.createdAt)||Date.now()<p.createdAt||Date.now()-p.createdAt>120000||
               typeof p.priorRecoveryId!=='string'||!/^mission-[a-f0-9]{32}$/.test(p.priorRecoveryId))return null;
            var prefix='observations/'+request.session+'/frame-'+String(p.witnessFrameId).padStart(4,'0');
            if(!file.isExists(prefix+'.png'))return null;
            var witness=JSON.parse(file.readTextSync(prefix+'.json'));
            function exactChoice(value) {
                var h=value&&value.hud,rows=value&&value.ocr||[];
                return !!(value&&value.session===request.session&&value.map===null&&h&&h.auto===true&&h.choice===true&&h.health===null&&
                    !h.journal&&!h.bigMap&&!h.tutorialStep&&rows.some(function(r){return String(r.text||'').trim()==='Kaeya'&&r.x>600&&r.x<1200&&r.y>830&&r.y<900;})&&
                    rows.filter(function(r){return String(r.text||'').trim()==="Thanks, that's nice of you to say..."&&r.x>1000&&r.y>430&&r.y<830;}).length===1);
            }
            if(!witness||witness.frameId!==p.witnessFrameId||!Number.isFinite(witness.timestamp)||witness.timestamp>Date.now()||!exactChoice(witness)||!exactChoice(o)||
               !o||o.frameId<=p.frameId||!Number.isFinite(o.timestamp)||Date.now()<o.timestamp||Date.now()-o.timestamp>1000)return null;
            var history=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(history,request.session))return null;
            var receipt=JSON.parse(file.readTextSync('receipts/'+request.session+'/'+p.priorRecoveryId+'.json'));
            var matches=history.filter(function(r){return r&&r.id===p.priorRecoveryId&&r.session===request.session&&r.status===receipt.status;});
            var result=receipt.details&&receipt.details.result,events=receipt.details&&receipt.details.inputEvents||[];
            var advances=events.filter(function(e){return e&&e.type==='wolfClosingDialogueAdvance';}),keys=events.filter(function(e){return e&&e.type==='key';});
            if(receipt.id!==p.priorRecoveryId||receipt.session!==request.session||receipt.mission!=='recover'||receipt.status!=='completed'||
               matches.length!==1||JSON.stringify(matches[0].details)!==JSON.stringify(receipt.details)||!result||result.rootDirected!==true||
               result.questComplete!==false||!Number.isInteger(result.closingDialogueAttempts)||result.closingDialogueAttempts<1||result.closingDialogueAttempts>16||
               advances.length!==result.closingDialogueAttempts||keys.length!==advances.length||
               events.some(function(e){return !e||['controllerRevision','wolfClosingDialogueAdvance','key'].indexOf(e.type)<0;}))return null;
            var lastAt=-Infinity,lastFrame=-1;
            for(var i=0;i<advances.length;i++) {
                var a=advances[i],k=keys[i];
                if(a.rootDirected!==true||!Number.isInteger(a.frameId)||a.frameId<=lastFrame||a.frameId>=witness.frameId||
                   k.key!=='VK_SPACE'||k.durationMs!==60||(k.frameId!==undefined&&k.frameId!==a.frameId)||
                   !Number.isFinite(a.startedAt)||!Number.isFinite(a.finishedAt)||a.finishedAt<a.startedAt||
                   !Number.isFinite(k.startedAt)||!Number.isFinite(k.finishedAt)||k.finishedAt<k.startedAt||k.startedAt<a.startedAt||k.finishedAt>a.finishedAt||
                   a.startedAt<lastAt)return null;
                lastAt=a.finishedAt;lastFrame=a.frameId;
            }
            if(witness.timestamp<=lastAt||history.some(function(r){return r&&r.session===request.session&&Array.isArray(r.details&&r.details.inputEvents)&&
                r.details.inputEvents.some(function(e){return e&&e.type!=='controllerRevision'&&Number.isFinite(e.startedAt)&&e.startedAt>lastAt;});}))return null;
            return p;
        }catch(e){return null;}
    }
    function sessionReady() {
        if (genshin.isRemoteDesktopSession !== true || !Number.isInteger(expectedSession) || expectedSession <= 1 || Number(genshin.windowsSessionId) !== expectedSession) throw new Error('The pinned verified RDP child session above Windows session 1 is required');
    }
    function ready() { sessionReady(); if (genshin.isGameForeground !== true) throw new Error('Game lost foreground focus'); }
    function release() { if (held) { var k = held; keyUp(k); held = null; } }
    function checkStop() {
        if(heartbeat)heartbeat(false);
        ready();
        if (!pauseProtectionActive && request && file.isExists('stop.json')) {
            var stop = JSON.parse(file.readTextSync('stop.json'));
            if (stop.session === request.session && stop.createdAt >= request.createdAt) { release(); throw new Error('Stop requested'); }
        }
    }
    function wolfSpikeCurrent(o) {
        return !!(request&&request.mission==='questStep'&&request.step==='wolfSpikeCrossFirst'&&o&&o.session===request.session&&
            lastObservation&&o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&Number.isInteger(o.frameId)&&
            o.frameId>=0&&Number.isFinite(o.timestamp)&&Date.now()>=o.timestamp&&Date.now()-o.timestamp<=1000);
    }
    function wolfSpikeEntry() {
        try{return actOneWolfEntryProven(JSON.parse(file.readTextSync('reports/'+request.session+'.json')),request.session);}catch(e){return false;}
    }
    function wolfSecondCurrent(o) {
        return !!(request&&request.mission==='questStep'&&request.step==='wolfSpikeCrossSecond'&&o&&o.session===request.session&&
            lastObservation&&o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&Number.isInteger(o.frameId)&&
            o.frameId>=0&&Number.isFinite(o.timestamp)&&Date.now()>=o.timestamp&&Date.now()-o.timestamp<=1000);
    }
    function wolfCharactersCurrent(o) {
        return !!(request&&request.mission==='questStep'&&request.step==='wolfCharactersOpen'&&o&&o.session===request.session&&
            lastObservation&&o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&Number.isInteger(o.frameId)&&
            o.frameId>=request.expectedFrameId&&Number.isFinite(o.timestamp)&&Date.now()>=o.timestamp&&Date.now()-o.timestamp<=1000);
    }
    function wolfWitnessCurrent(o) {
        return !!(request&&request.mission==='questStep'&&request.step==='wolfWitnessAction'&&o&&o.session===request.session&&
            lastObservation&&o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&Number.isInteger(o.frameId)&&
            o.frameId>=request.expectedFrameId&&Number.isFinite(o.timestamp)&&Date.now()>=o.timestamp&&Date.now()-o.timestamp<=1000);
    }
    function wolfWitnessPermit() {
        try {
            var p=JSON.parse(file.readTextSync('wolf-witness-action.json'));
            if(!request||!p||p.kind!=='wolfWitnessAction'||p.session!==request.session||p.frameId!==request.expectedFrameId||p.usedAt||
               !Number.isInteger(p.witnessFrameId)||p.witnessFrameId<0||p.witnessFrameId>=p.frameId||
               !Number.isFinite(p.createdAt)||Date.now()<p.createdAt||Date.now()-p.createdAt>120000||
               ['forwardFine','forwardBounded','leftFine','rightFine','lookLeft','lookRight','jumpForward','strike'].indexOf(p.action)<0)return null;
            var prefix='observations/'+request.session+'/frame-'+String(p.witnessFrameId).padStart(4,'0');
            if(!file.isExists(prefix+'.png'))return null;
            var witness=JSON.parse(file.readTextSync(prefix+'.json')),h=witness&&witness.hud,hp=h&&h.health;
            if(!witness||witness.session!==request.session||witness.frameId!==p.witnessFrameId||
               !actOneWolfDomainHud(witness,witness.timestamp,0.01)||h.auto||h.loading||h.unknownHud||h.objectiveChanged||h.interact||
               !Array.isArray(h.enemyBars)||h.enemyBars.length||!hp||hp.current<=0)return null;
            return {permit:p,baseline:{current:hp.current,max:hp.max}};
        }catch(e){return null;}
    }
    function wolfWitnessActive(o,unchanged) {
        var h=o&&o.hud,hp=h&&h.health,d=h&&h.enemyBarDiagnostic;
        return !!(wolfWitnessState.continued&&wolfWitnessCurrent(o)&&o.frameId>wolfWitnessState.lastInputFrame&&wolfSpikeEntry()&&
            actOneWolfDomainHud(o,Date.now(),0.01)&&!h.auto&&!h.loading&&!h.unknownHud&&!h.objectiveChanged&&!h.interact&&
            Array.isArray(h.enemyBars)&&h.enemyBars.length===0&&d&&d.level===5&&d.candidates===0&&Array.isArray(d.localReads)&&d.localReads.length===0&&
            hp&&hp.current>0&&(!unchanged||hp.current===wolfWitnessState.baseline.current&&hp.max===wolfWitnessState.baseline.max));
    }
    function wolfWitnessJumpAligned(o) {
        var m=o&&o.hud&&o.hud.wolfSpikeSurface&&o.hud.wolfSpikeSurface.metrics;
        return !!(m&&['witnessLandingLeft','witnessLandingRight'].every(function(k){return Number.isFinite(m[k])&&m[k]>=0.7&&m[k]<=1;}));
    }
    function wolfReviveCurrent(o) {
        return !!(request&&request.mission==='questStep'&&request.step==='wolfReviveKaeyaPrompt'&&o&&o.session===request.session&&
            lastObservation&&o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&Number.isInteger(o.frameId)&&
            o.frameId>=request.expectedFrameId&&Number.isFinite(o.timestamp)&&Date.now()>=o.timestamp&&Date.now()-o.timestamp<=1000);
    }
    function wolfReviveEntry() {
        try{return actOneWolfEntryProven(JSON.parse(file.readTextSync('reports/'+request.session+'.json')),request.session);}catch(e){return false;}
    }
    function wolfRevivePermit() {
        try {
            var p=JSON.parse(file.readTextSync('wolf-revive-kaeya.json'));
            return p&&p.kind==='reviveTrialKaeya'&&p.session===request.session&&p.frameId===request.expectedFrameId&&
                !Object.prototype.hasOwnProperty.call(p,'usedAt')&&Number.isFinite(p.createdAt)&&Date.now()>=p.createdAt&&Date.now()-p.createdAt<=120000?p:null;
        } catch(e){return null;}
    }
    function wolfReviveActiveReady(o) {
        if(!wolfReviveContinueAttempted||!wolfReviveCurrent(o)||o.frameId<=wolfReviveContinueFrame||!wolfReviveEntry()||
           !actOneWolfDeadTrialPauseOnlyHud(o,Date.now(),request.session)||o.hud.groundControls!==true)return false;
        var hp=o.hud.health;
        if(!hp||hp.max!==1055||hp.current<=0)return false;
        if(!wolfReviveAmberBaseline)wolfReviveAmberBaseline={current:hp.current,max:hp.max};
        return hp.max===wolfReviveAmberBaseline.max&&hp.current===wolfReviveAmberBaseline.current;
    }
    function wolfReviveRecoveryCurrent(o) {
        return !!(request&&request.mission==='recover'&&expectedSession===7&&genshin.isRemoteDesktopSession===true&&Number(genshin.windowsSessionId)===7&&
            o&&o.session===request.session&&lastObservation&&o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&
            Number.isInteger(o.frameId)&&Number.isInteger(request.expectedFrameId)&&o.frameId>=request.expectedFrameId&&
            Number.isFinite(o.timestamp)&&Date.now()>=o.timestamp&&Date.now()-o.timestamp<=1000);
    }
    function wolfReviveRecoveryEntry() {
        try{return actOneWolfEntryProven(JSON.parse(file.readTextSync('reports/'+request.session+'.json')),request.session);}catch(e){return false;}
    }
    function wolfReviveRecoveryPromptReceipt() {
        try {
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            var matches=reports.filter(function(r){return r&&r.session===request.session&&r.mission==='questStep'&&
                ['completed','stopped'].indexOf(r.status)>=0&&r.details&&r.details.result&&r.details.result.step==='wolfReviveKaeyaPrompt';});
            var permit=JSON.parse(file.readTextSync('wolf-revive-kaeya-recovery.json'));
            if(Object.prototype.hasOwnProperty.call(permit,'promptRequestId')) {
                if(typeof permit.promptRequestId!=='string'||!permit.promptRequestId||permit.promptRequestId.length>80)return false;
                matches=matches.filter(function(r){return r.id===permit.promptRequestId;});
            }
            if(matches.length!==1)return false;
            var report=matches[0],result=report.details.result,ev=report.details.inputEvents||[];
            if(reports.some(function(r){return r&&r.id!==report.id&&r.session===request.session&&r.mission==='questStep'&&
                ['completed','stopped'].indexOf(r.status)>=0&&r.details&&r.details.result&&
                r.details.result.step==='wolfReviveKaeyaPrompt'&&Number.isFinite(r.timestamp)&&r.timestamp>=report.timestamp;}))return false;
            if(result.continueAttempts!==1||result.selectionAttempts!==1||result.promptRequested!==true||result.questComplete!==false||!Number.isInteger(result.frameId))return false;
            var continues=ev.filter(function(e){return e&&e.type==='wolfReviveKaeyaContinue'&&Number.isInteger(e.frameId)&&Number.isFinite(e.startedAt);});
            var selects=ev.filter(function(e){return e&&e.type==='wolfReviveKaeyaSelect'&&e.key==='VK_3'&&Number.isInteger(e.frameId)&&
                Number.isFinite(e.startedAt)&&Number.isFinite(e.finishedAt)&&e.finishedAt>=e.startedAt;});
            var keys=ev.filter(function(e){return e&&e.type==='key'&&e.key==='VK_3';});
            if(continues.length!==1||selects.length!==1||keys.length!==1)return false;
            var s=selects[0],k=keys[0];
            var valid=s.frameId===k.frameId&&k.durationMs===60&&Number.isFinite(k.startedAt)&&Number.isFinite(k.finishedAt)&&k.finishedAt>=k.startedAt&&
                k.startedAt>=s.startedAt&&k.finishedAt<=s.finishedAt&&continues[0].frameId<s.frameId&&
                Number.isFinite(report.timestamp)&&report.timestamp>=s.finishedAt&&result.frameId>=s.frameId;
            return valid?report:null;
        } catch(e){return false;}
    }
    function wolfReviveRecoveryPrefix() {return !!wolfReviveRecoveryPromptReceipt();}
    function wolfReviveRecoveryPermit() {
        try {
            var p=JSON.parse(file.readTextSync('wolf-revive-kaeya-recovery.json'));
            return p&&p.kind==='reviveTrialKaeyaRecovery'&&p.session===request.session&&p.frameId===request.expectedFrameId&&
                !Object.prototype.hasOwnProperty.call(p,'usedAt')&&Number.isFinite(p.createdAt)&&Date.now()>=p.createdAt&&Date.now()-p.createdAt<=120000?p:null;
        } catch(e){return null;}
    }
    function wolfReviveRecoverySelectionReceipt(permit) {
        try {
            if(!permit||!Number.isFinite(permit.usedAt)||!permit.requestId||permit.confirmationAttemptedAt!==undefined)return null;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            var matches=reports.filter(function(r){return r&&r.id===permit.requestId&&r.session===request.session&&r.mission==='recover'&&r.status==='failed'&&r.details&&Array.isArray(r.details.inputEvents);});
            if(matches.length!==1)return null;
            var report=matches[0],result=report.details.result,events=report.details.inputEvents;
            if(!result||result.reviveSelectionAttempts!==1||result.reviveConfirmAttempts!==0||
               result.reviveModalVerified!==false||result.questComplete!==false||!Number.isInteger(report.frameId))return null;
            var selects=events.filter(function(e){return e&&e.type==='wolfReviveKaeyaRecoverySelect'&&e.key==='VK_3';});
            var keys=events.filter(function(e){return e&&e.type==='key'&&e.key==='VK_3';});
            var confirms=events.filter(function(e){return e&&e.type==='wolfReviveKaeyaRecoveryConfirm';});
            if(selects.length!==1||keys.length!==1||confirms.length!==0)return null;
            var s=selects[0],k=keys[0];
            if(!Number.isInteger(s.frameId)||s.frameId!==k.frameId||k.durationMs!==60||!Number.isFinite(s.startedAt)||
               !Number.isFinite(k.startedAt)||!Number.isFinite(k.finishedAt)||k.startedAt<s.startedAt||k.finishedAt<k.startedAt||
               !Number.isFinite(report.timestamp)||report.timestamp<k.finishedAt||report.frameId<s.frameId)return null;
            if(events.some(function(e){return e&&Number.isFinite(e.startedAt)&&e.startedAt>s.startedAt&&
                ['wolfReviveKaeyaRecoverySelect','wolfReviveKaeyaRecoveryConfirm','wolfReviveKaeyaContinue','wolfReviveKaeyaSelect','key','click','rotate'].indexOf(e.type)>=0&&
                !(e===k);}))return null;
            if(reports.some(function(r){return r&&r!==report&&r.session===request.session&&Number.isFinite(r.timestamp)&&r.timestamp>=report.timestamp&&
                Array.isArray(r.details&&r.details.inputEvents)&&r.details.inputEvents.some(function(e){return !e||e.type!=='controllerRevision';});}))return null;
            if(!file.isExists('receipts/'+request.session+'/'+report.id+'.json'))return null;
            var receipt=JSON.parse(file.readTextSync('receipts/'+request.session+'/'+report.id+'.json'));
            if(!receipt||receipt.id!==report.id||receipt.session!==report.session||receipt.mission!==report.mission||receipt.status!==report.status||
               receipt.frameId!==report.frameId||receipt.timestamp!==report.timestamp||JSON.stringify(receipt.details)!==JSON.stringify(report.details))return null;
            return report;
        } catch(e){return null;}
    }
    function wolfReviveRecoverySafeAmber(o) {
        return wolfReviveRecoveryCurrent(o)&&wolfReviveRecoveryEntry()&&actOneWolfDeadTrialPauseOnlyHud(o,Date.now(),request.session)&&
            o.hud.groundControls===true&&o.hud.interact===false&&(o.hud.enemyBars||[]).length===0;
    }
    function wolfReviveRecoverySafeKaeya(o) {
        var hp=o&&o.hud&&o.hud.health,rows=o&&o.ocr||[];
        return wolfReviveRecoveryCurrent(o)&&wolfReviveRecoveryEntry()&&actOneWolfDomainHud(o,Date.now(),0)&&o.hud.groundControls===true&&
            o.hud.climbing===false&&o.hud.auto===false&&o.hud.loading!==true&&o.hud.unknownHud!==true&&o.hud.objectiveChanged===false&&
            o.hud.interact===false&&(o.hud.enemyBars||[]).length===0&&hp&&hp.max===1427&&hp.current===100&&
            rows.filter(function(r){return String(r.text||'').trim()==='Amber'&&r.x>1550&&r.x<1800&&r.y>300&&r.y<600;}).length===1&&
            rows.filter(function(r){return String(r.text||'').trim()==='Kaeya'&&r.x>1550&&r.x<1800&&r.y>300&&r.y<600;}).length===1&&
            rows.filter(function(r){return String(r.text||'').trim()==='Trial'&&r.x>1700&&r.x<1900&&r.y>300&&r.y<600;}).length===1;
    }
    function wolfSecondPermit() {
        try {
            var p=JSON.parse(file.readTextSync('wolf-spike-second.json'));
            if(!p||p.kind!=='secondSpikeBank'||p.session!==request.session||p.frameId!==request.expectedFrameId||
                Object.prototype.hasOwnProperty.call(p,'crossingCharacter')&&['amber','kaeya'].indexOf(p.crossingCharacter)<0||
                Object.prototype.hasOwnProperty.call(p,'bankPosition')&&(['lip','iceBridge','platform'].indexOf(p.bankPosition)<0||
                    !Number.isInteger(p.witnessFrameId)||p.witnessFrameId<0||p.witnessFrameId>=p.frameId)||
                p.usedAt||!Number.isFinite(p.createdAt)||Date.now()<p.createdAt||Date.now()-p.createdAt>120000)return null;
            if(Object.prototype.hasOwnProperty.call(p,'approachMoves')&&(!Number.isInteger(p.approachMoves)||
               p.approachMoves<1||p.approachMoves>2||p.crossingCharacter!=='kaeya'||['lip','platform'].indexOf(p.bankPosition)<0))return null;
            if(p.bankPosition==='platform'&&(!Number.isInteger(p.approachMoves)||p.crossingCharacter!=='kaeya'))return null;
            p.refreshedIceProof=false;
            if(p.bankPosition==='iceBridge') {
                if(p.crossingCharacter!=='kaeya'||typeof p.priorCrossingRequest!=='string'||!/^mission-[a-f0-9]{32}$/.test(p.priorCrossingRequest))return null;
                var matches=JSON.parse(file.readTextSync('reports/'+request.session+'.json')).filter(function(r){return r&&r.id===p.priorCrossingRequest&&
                    r.session===request.session&&r.mission==='questStep'&&r.status==='stopped'&&r.frameId===p.frameId;});
                if(matches.length!==1)return null;
                var parent=matches[0],result=parent.details&&parent.details.result,keys=parent.details&&parent.details.inputEvents;
                if(!result||result.step!=='wolfSpikeCrossSecond'||result.frameId!==p.frameId||result.pauseVerified!==true||
                    result.crossingCharacter!=='kaeya'||!result.kaeyaHealth||result.kaeyaHealth.max!==1427||
                    !Number.isFinite(result.kaeyaHealth.current)||result.kaeyaHealth.current<=0||!Array.isArray(keys))return null;
                var actual=keys.filter(function(e){return e&&e.type==='key';});
                var original=result.iceEffectVerified===true&&actual.length===5&&actual[0].key==='VK_3'&&actual[0].durationMs===60&&
                    actual[1].key==='VK_E'&&actual[1].durationMs===60&&actual[2].key==='VK_W'&&actual[2].durationMs===600&&
                    actual[3].key==='VK_W'&&actual[3].durationMs===600&&actual[4].key==='VK_ESCAPE'&&actual[4].durationMs===60&&
                    actual[4].frameId===p.witnessFrameId;
                if(!original) {
                    if(result.iceEffectVerified!==false||result.skillAttempts!==1||result.movementAttempts!==0||actual.length!==2||
                       actual[0].key!=='VK_E'||actual[0].durationMs!==60||actual[1].key!=='VK_ESCAPE'||actual[1].durationMs!==60||
                       actual[1].frameId!==p.witnessFrameId||!Number.isInteger(p.iceProofFrameId)||p.iceProofFrameId<=actual[0].frameId||
                       p.iceProofFrameId>=actual[1].frameId)return null;
                    var receipt=JSON.parse(file.readTextSync('receipts/'+request.session+'/'+parent.id+'.json'));
                    if(receipt.id!==parent.id||receipt.session!==parent.session||receipt.mission!==parent.mission||receipt.status!==parent.status||
                       receipt.frameId!==parent.frameId||receipt.timestamp!==parent.timestamp||JSON.stringify(receipt.details)!==JSON.stringify(parent.details))return null;
                    var proof=JSON.parse(file.readTextSync('observations/'+request.session+'/frame-'+String(p.iceProofFrameId).padStart(4,'0')+'.json'));
                    var pm=proof&&proof.hud&&proof.hud.wolfSpikeSurface&&proof.hud.wolfSpikeSurface.metrics,ph=proof&&proof.hud&&proof.hud.health;
                    if(!proof||proof.session!==request.session||proof.frameId!==p.iceProofFrameId||!Number.isFinite(proof.timestamp)||
                       !Number.isFinite(actual[0].finishedAt)||!Number.isFinite(actual[1].startedAt)||proof.timestamp<=actual[0].finishedAt||
                       proof.timestamp>=actual[1].startedAt||proof.timestamp-actual[0].finishedAt>10000||
                       !actOneWolfSpikeActive(proof,proof.timestamp,'kaeya',0.01)||!ph||ph.current!==result.kaeyaHealth.current||ph.max!==1427||
                       !pm||!['iceLeft','iceRight'].every(function(k){return Number.isFinite(pm[k])&&pm[k]>=0.7&&pm[k]<=1;})||
                       !['floorLeftIce','floorRightIce'].every(function(k){return Number.isFinite(pm[k])&&pm[k]>=0.9&&pm[k]<=1;})||
                       !(actOneWolfCryoCooldownRemaining(proof)>=4))return null;
                    p.refreshedIceProof=true;
                }
                p.verifiedKaeyaHealth={current:result.kaeyaHealth.current,max:result.kaeyaHealth.max};
            }
            return p;
        } catch(e){return null;}
    }
    function wolfSecondPlatformFloor(m) {
        // At the witnessed left edge, the y800 probe crosses the destination
        // bank's rim. Use the visible right-hand landing and platform surface
        // together for the fixed, short centering move.
        return !!m&&['boardRightSupport','boardFarRightSupport','underfootRightSupport'].every(function(k){
            return Number.isFinite(m[k])&&m[k]>=(k==='underfootRightSupport'?0.9:0.8)&&m[k]<=1;
        });
    }
    function wolfSecondSurface(o) {
        var s=actOneWolfSpikeSurface(o&&o.hud&&o.hud.wolfSpikeSurface&&o.hud.wolfSpikeSurface.metrics),m=s&&s.metrics;
        // The lip witness is explicit for this episode: the older y800 probes
        // look into the pit here. It does not relax floor checks elsewhere.
        if(s&&wolfSecondState.bankPosition==='lip'&&m&&
            Number.isFinite(m.underfootLeftStone)&&Number.isFinite(m.underfootRightStone)&&
            m.underfootLeftStone>=0.8&&m.underfootLeftStone<=1&&m.underfootRightStone>=0.8&&m.underfootRightStone<=1)
            s.solidFloor=true;
        if(s&&wolfSecondState.bankPosition==='platform'&&wolfSecondPlatformFloor(m))s.solidFloor=true;
        return s;
    }
    function wolfSecondActiveReady(o,body,minRatio) {
        if(!wolfSecondState.continued||!wolfSecondCurrent(o)||o.frameId<=wolfSecondState.lastInputFrame||!wolfSpikeEntry()||
            !actOneWolfSpikeActive(o,Date.now(),body,Math.max(0.01,minRatio||0)))return false;
        var surface=wolfSecondSurface(o),hp=o.hud.health;
        var bridge=surface&&wolfSecondState.bankPosition==='iceBridge'&&surface.metrics.floorLeftIce>=wolfSecondState.bridgeFloorMin&&surface.metrics.floorRightIce>=wolfSecondState.bridgeFloorMin;
        if(!surface||!wolfSecondState.cast&&surface.solidFloor!==true&&!bridge)return false;
        if(body==='kaeya') {
            var kb=wolfSecondState.kaeyaBaseline;
            if(kb&&(kb.max!==hp.max||kb.current!==hp.current))return false;
            if(!kb)wolfSecondState.kaeyaBaseline={current:hp.current,max:hp.max};
        }
        if(body==='amber') {
            var ab=wolfSecondState.amberBaseline;
            if(ab&&(ab.max!==hp.max||ab.current-hp.current>ab.max*0.05))return false;
            if(!ab)wolfSecondState.amberBaseline={current:hp.current,max:hp.max};
        }
        return true;
    }
    function wolfSecondBlockAligned(o) {
        var s=wolfSecondSurface(o),m=s&&s.metrics;
        if(wolfSecondState.bankPosition==='iceBridge')return !!(s&&m&&m.floorLeftIce>=wolfSecondState.bridgeFloorMin&&m.floorRightIce>=wolfSecondState.bridgeFloorMin);
        if(wolfSecondState.bankPosition==='lip') {
            return !!(s&&s.solidFloor&&m&&['boardLeftStone','boardMidStone','boardRightStone','boardFarRightStone'].every(function(k){
                return Number.isFinite(m[k])&&m[k]>=0&&m[k]<=1;
            })&&m.boardLeftStone>=0.5&&m.boardMidStone>=0.2&&m.boardRightStone<=0.05&&m.boardFarRightStone<=0.05);
        }
        return !!(s&&s.solidFloor&&m&&Number.isFinite(m.platformLeftStone)&&Number.isFinite(m.platformRightStone)&&
            m.platformLeftStone>=0.15&&m.platformLeftStone<=1&&m.platformRightStone>=0.15&&m.platformRightStone<=1);
    }
    async function wolfSecondKey(key,duration,guard) {
        checkStop();var o=lastObservation;
        if(!wolfSecondCurrent(o)||o.frameId<=wolfSecondState.lastInputFrame||!guard(o))
            throw new Error('Fresh verified second-pit phase required before bounded input');
        wolfSecondState.lastInputFrame=o.frameId;
        await boundedKey(key,duration,o.frameId);
    }
    function wolfSpikePermit() {
        try {
            var permit=JSON.parse(file.readTextSync('wolf-spike-first.json'));
            return permit&&(permit.kind==='firstSpikeBank'||permit.kind==='firstSpikeLanding'&&permit.crossingCharacter==='kaeya'&&
                typeof permit.priorLandingMission==='string'&&/^mission-[a-f0-9]{32}$/.test(permit.priorLandingMission))&&
                permit.session===request.session&&permit.frameId===request.expectedFrameId&&
                (permit.crossingCharacter===undefined||permit.crossingCharacter==='kaeya')&&
                !permit.usedAt&&Number.isFinite(permit.createdAt)&&Date.now()>=permit.createdAt&&Date.now()-permit.createdAt<=120000?permit:null;
        } catch(e){return null;}
    }
    async function wolfSpikeKey(key,duration,guard) {
        checkStop();var o=lastObservation;
        if(!wolfSpikeCurrent(o)||o.frameId<=wolfSpikeState.lastInputFrame||!guard(o))throw new Error('Fresh verified spike phase required before bounded input');
        wolfSpikeState.lastInputFrame=o.frameId;
        await boundedKey(key,duration,o.frameId);
    }
    function wolfSpikeReusableIceProof(o) {
        try {
            var source=wolfSpikeState.reuseSource;
            if(!source||typeof source.missionId!=='string'||!/^mission-[a-f0-9]{32}$/.test(source.missionId)||
               !Number.isInteger(source.frameId)||source.frameId<1||source.frameId>=request.expectedFrameId)return false;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            var prior=reports.filter(function(r){return r&&r.id===source.missionId&&r.session===request.session&&r.status==='stopped';});
            if(prior.length!==1)return false;
            var row=prior[0],result=row.details&&row.details.result,input=row.details&&row.details.inputEvents||[];
            if(!result||result.step!=='wolfSpikeCrossFirst'||result.skillAttempts!==1||result.movementAttempts!==0||
               result.pauseVerified!==true||row.frameId<=source.frameId||row.frameId>=request.expectedFrameId)return false;
            var skills=input.filter(function(e){return e&&e.type==='key'&&e.key==='VK_E';});
            if(skills.length!==1||!Number.isFinite(skills[0].finishedAt))return false;
            var receipt=JSON.parse(file.readTextSync('receipts/'+request.session+'/'+source.missionId+'.json'));
            if(receipt.id!==row.id||receipt.session!==row.session||receipt.status!==row.status||receipt.frameId!==row.frameId||
               JSON.stringify(receipt.details)!==JSON.stringify(row.details))return false;
            var witness=JSON.parse(file.readTextSync('observations/'+request.session+'/frame-'+String(source.frameId).padStart(4,'0')+'.json'));
            if(witness.session!==request.session||witness.frameId!==source.frameId||witness.timestamp<=skills[0].finishedAt||
               !witness.hud||!witness.hud.wolfSpikeSurface||witness.hud.wolfSpikeSurface.ice!==true||
               !witness.hud.health||witness.hud.health.max!==1427||!Number.isFinite(witness.hud.health.current)||
               witness.hud.health.current<=0||!o||!o.hud||!o.hud.health||o.hud.health.current!==witness.hud.health.current)return false;
            for(var i=0;i<reports.length;i++) {
                var eventsAfter=reports[i].details&&reports[i].details.inputEvents||[];
                for(var j=0;j<eventsAfter.length;j++) {
                    var event=eventsAfter[j];
                    if(!event)return false;
                    if(event.type==='wolfResumeProof')continue;
                    if(!Number.isFinite(event.startedAt))return false;
                    if(event.startedAt<=skills[0].startedAt)continue;
                    if(['controllerRevision','wolfSpikeCooldownPlan','wolfSpikeContinue'].indexOf(event.type)>=0)continue;
                    if(event.type==='key'&&['VK_3','VK_2','VK_ESCAPE'].indexOf(event.key)>=0)continue;
                    return false;
                }
            }
            return true;
        } catch(e){return false;}
    }
    function wolfSpikeActiveReady(o,body,minRatio) {
        if(!wolfSpikeState.continued||!wolfSpikeCurrent(o)||o.frameId<=wolfSpikeState.lastInputFrame||!wolfSpikeEntry()||
           !actOneWolfSpikeActive(o,Date.now(),body,Math.max(0.01,minRatio||0)))return false;
        if(!wolfSpikeState.cast&&!wolfSpikeState.usingExistingIce) {
            var surface=o.hud.wolfSpikeSurface;
            if(!surface||surface.solidFloor!==true)return false;
            if(!wolfSpikeState.bankVerified) {
                if(surface.startBank!==true)return false;
                wolfSpikeState.bankVerified=true;
            }
        }
        if(body==='kaeya') {
            var kaeyaHp=o.hud.health,kaeyaBaseline=wolfSpikeState.kaeyaBaseline;
            if(kaeyaBaseline&&(kaeyaHp.max!==kaeyaBaseline.max||kaeyaBaseline.current-kaeyaHp.current>kaeyaBaseline.max*0.05))return false;
            if(!kaeyaBaseline)wolfSpikeState.kaeyaBaseline={current:kaeyaHp.current,max:kaeyaHp.max};
        }
        if(body==='amber') {
            var hp=o.hud.health,baseline=wolfSpikeState.amberBaseline;
            if(baseline&&(hp.max!==baseline.max||baseline.current-hp.current>baseline.max*0.05))return false;
            if(!baseline)wolfSpikeState.amberBaseline={current:hp.current,max:hp.max};
        }
        return true;
    }
    function wolfSpikeLocalFinishReady(o) {
        if(wolfSpikeState.crossingCharacter!=='kaeya'||wolfSpikeState.landingContinuation===true||
           wolfSpikeState.landingContinuationSource||wolfSpikeState.moves!==2||wolfSpikeState.selectedAmber||
           wolfSpikeState.jumpAttempted||!wolfSpikeState.iceVerified||
           !(wolfSpikeState.cast||wolfSpikeState.usingExistingIce)||!wolfSpikeActiveReady(o,'kaeya',0.01))return false;
        var hp=o.hud.health,baseline=wolfSpikeState.kaeyaBaseline;
        var surface=actOneWolfSpikeSurface(o.hud.wolfSpikeSurface&&o.hud.wolfSpikeSurface.metrics);
        return !!(baseline&&hp.current===baseline.current&&hp.max===baseline.max&&surface&&
            surface.kaeyaLandingLip===true&&surface.firstLanding!==true);
    }
    function wolfSpikeLandingContinuationProof(o) {
        try {
            var id=wolfSpikeState.landingContinuationSource;
            if(typeof id!=='string'||!/^mission-[a-f0-9]{32}$/.test(id))return false;
            var rows=JSON.parse(file.readTextSync('reports/'+request.session+'.json')).filter(function(r){return r&&r.id===id&&r.session===request.session&&r.status==='stopped';});
            if(rows.length!==1)return false;
            var row=rows[0],r=row.details&&row.details.result,events=row.details&&row.details.inputEvents||[];
            if(row.mission!=='questStep'||!r||r.status!=='stopped'||r.step!=='wolfSpikeCrossFirst'||r.pauseVerified!==true||
               r.landingVerified!==false||r.iceEffectVerified!==true||r.questComplete!==false||r.continueAttempts!==1||r.pauseAttempts!==1||r.crossingCharacter!=='kaeya'||
               r.jumpAttempts!==0||r.lastFrameId!==row.frameId||row.frameId!==request.expectedFrameId)return false;
            var initial=r.skillAttempts===1&&r.characterSelectionAttempts===1&&r.movementAttempts===2;
            var finished=r.skillAttempts===0&&r.characterSelectionAttempts===0&&r.movementAttempts===1&&
                r.landingContinuation===true&&r.existingIceReused===true;
            if(!initial&&!finished)return false;
            var receipt=JSON.parse(file.readTextSync('receipts/'+request.session+'/'+id+'.json'));
            if(receipt.id!==id||receipt.session!==request.session||receipt.status!==row.status||receipt.frameId!==row.frameId||
               JSON.stringify(receipt.details)!==JSON.stringify(row.details))return false;
            if(events.some(function(e){return !e||['controllerRevision','wolfSpikeContinue','wolfSpikeCooldownPlan','key'].indexOf(e.type)<0;}))return false;
            var continues=events.filter(function(e){return e.type==='wolfSpikeContinue';}),keys=events.filter(function(e){return e.type==='key';});
            if(continues.length!==1||keys.length!==(initial?5:2)||!Number.isInteger(continues[0].frameId)||
               !Number.isFinite(continues[0].finishedAt))return false;
            var expected=initial?['VK_3','VK_E','VK_W','VK_W','VK_ESCAPE']:['VK_W','VK_ESCAPE'];
            var durations=initial?[60,60,800,800,60]:[200,60];
            var lastFrame=continues[0].frameId,lastAt=continues[0].finishedAt;
            for(var i=0;i<keys.length;i++) {
                var k=keys[i];
                if(k.key!==expected[i]||k.durationMs!==durations[i]||!Number.isInteger(k.frameId)||k.frameId<=lastFrame||
                   !Number.isFinite(k.startedAt)||!Number.isFinite(k.finishedAt)||k.finishedAt<k.startedAt||k.startedAt<lastAt)return false;
                lastFrame=k.frameId;lastAt=k.finishedAt;
            }
            if(row.frameId<=lastFrame||!Number.isFinite(row.timestamp)||row.timestamp<lastAt)return false;
            var witness=JSON.parse(file.readTextSync('observations/'+request.session+'/frame-'+String(lastFrame).padStart(4,'0')+'.json'));
            if(!Number.isFinite(witness.timestamp)||witness.timestamp<keys[keys.length-2].finishedAt||witness.timestamp>keys[keys.length-1].startedAt)return false;
            var hp=witness.hud&&witness.hud.health,nowHp=o.hud&&o.hud.health;
            var surface=actOneWolfSpikeSurface(witness.hud&&witness.hud.wolfSpikeSurface&&witness.hud.wolfSpikeSurface.metrics);
            return witness.session===request.session&&witness.frameId===lastFrame&&hp&&nowHp&&hp.max===1427&&
                hp.current===nowHp.current&&nowHp.max===hp.max&&surface&&
                (initial?surface.kaeyaLandingLip===true:surface.firstLanding===true);
        }catch(e){return false;}
    }
    function wolfCryoWaitCurrent(o) {
        return !!(request&&request.mission==='questStep'&&request.step==='wolfCryoWait'&&o&&o.session===request.session&&
            lastObservation&&o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&Number.isInteger(o.frameId)&&
            Number.isFinite(Number(o.timestamp))&&Date.now()>=Number(o.timestamp)&&Date.now()-o.timestamp<=1000);
    }
    function wolfCryoWaitActive(o,stampResume) {
        if(!wolfCryoContinueAttempted||!wolfCryoWaitCurrent(o)||!Number.isInteger(wolfCryoLastInputFrame)||
           o.frameId<=wolfCryoLastInputFrame||!actOneWolfRecoveryTravelHud(o,Date.now()))return false;
        var hp=o.hud.health;
        if(wolfCryoBaseline&&wolfCryoBaseline.current-hp.current>wolfCryoBaseline.max*0.05)return false;
        if(!wolfCryoBaseline)wolfCryoBaseline={current:Number(hp.current),max:Number(hp.max)};
        if(wolfCryoResumeConfirmedAt===null&&stampResume)wolfCryoResumeConfirmedAt=Date.now();
        return true;
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
    async function boundedKey(key, ms, frameId) {
        // A failed earlier key-up must be retried before a new key can replace
        // the held-key record, including during failure cleanup.
        checkStop(); release(); held = key;
        var event = { type: 'key', key: key, durationMs: ms, startedAt: Date.now() }; events.push(event);
        if(Number.isInteger(frameId)&&frameId>=0)event.frameId=frameId;
        try {
            keyDown(key);
            var deadline = Date.now() + ms;
            while (true) {
                var remaining = deadline - Date.now();
                if (remaining <= 0) break;
                await sleep(Math.min(50, remaining)); checkStop();
            }
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
    function readWolfSpikeSurface(img,includePlatform) {
        function fraction(x,y,w,h,lower,upper) {
            var crop=null,mask=null;
            try {
                crop=img.deriveCrop(x,y,w,h);
                mask=crop.srcMat.inRange(new OpenCvSharp.OpenCvSharp.Scalar(lower[0],lower[1],lower[2]),
                    new OpenCvSharp.OpenCvSharp.Scalar(upper[0],upper[1],upper[2]));
                return Number(OpenCvSharp.OpenCvSharp.Cv2.countNonZero(mask))/(w*h);
            } finally {dispose(mask);dispose(crop);}
        }
        function supportFraction(x,y,w,h) {
            // Bright blue paving overlaps the ice range. Measure the exact
            // union, subtracting its intersection rather than summing masks.
            return Math.max(0,Math.min(1,
                fraction(x,y,w,h,[65,60,25],[175,160,140])+
                fraction(x,y,w,h,[150,135,90],[255,255,255])-
                fraction(x,y,w,h,[150,135,90],[175,160,140])));
        }
        try {
            var iceLo=[150,135,90],iceHi=[255,255,255],stoneLo=[65,60,25],stoneHi=[175,160,140],redLo=[0,0,90],redHi=[85,85,255];
            var metrics={
                iceLeft:fraction(700,660,160,100,iceLo,iceHi),iceRight:fraction(1100,660,160,100,iceLo,iceHi),
                floorLeftIce:fraction(700,800,120,60,iceLo,iceHi),floorRightIce:fraction(1160,800,120,60,iceLo,iceHi),
                floorLeftStone:fraction(700,800,120,60,stoneLo,stoneHi),floorRightStone:fraction(1160,800,120,60,stoneLo,stoneHi),
                frontLeftStone:fraction(700,660,160,100,stoneLo,stoneHi),frontRightStone:fraction(1100,660,160,100,stoneLo,stoneHi),
                spikeLeft:fraction(600,590,180,120,redLo,redHi),spikeRight:fraction(1120,590,180,120,redLo,redHi)};
            if(includePlatform) {
                metrics.platformLeftStone=fraction(750,520,160,60,stoneLo,stoneHi);
                metrics.platformRightStone=fraction(1050,520,160,60,stoneLo,stoneHi);
                metrics.boardLeftStone=fraction(750,580,120,40,stoneLo,stoneHi);
                metrics.boardMidStone=fraction(940,580,120,40,stoneLo,stoneHi);
                metrics.boardRightStone=fraction(1130,580,120,40,stoneLo,stoneHi);
                metrics.boardFarRightStone=fraction(1320,580,120,40,stoneLo,stoneHi);
                metrics.underfootLeftStone=fraction(700,940,120,30,stoneLo,stoneHi);
                metrics.underfootRightStone=fraction(1160,940,120,30,stoneLo,stoneHi);
                metrics.boardRightSupport=supportFraction(1130,580,120,40);
                metrics.boardFarRightSupport=supportFraction(1320,580,120,40);
                metrics.underfootRightSupport=supportFraction(1160,940,120,30);
                metrics.witnessLandingLeft=fraction(750,570,130,60,[105,95,60],[180,160,125]);
                metrics.witnessLandingRight=fraction(1080,570,130,60,[105,95,60],[180,160,125]);
            }
            return actOneWolfSpikeSurface(metrics);
        } catch(e){return {unavailable:true,reason:'Spike surface probe unavailable'};}
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
            if(!corroborated&&conflictLeft.length===1&&/^\d{2,4}1$/.test(conflictLeft[0].text.trim())){
                // The slash can join the current-HP digits as a trailing 1.
                // Read a narrower independent crop; do not trim OCR into HP.
                var narrowLeft=scaledRows(img,905,998,42,25);
                diagnostic.narrowLeft=textRows(narrowLeft);
                corroborated=actOneCorroboratedFullHealth(fullRows,narrowLeft,conflictRight);
            }
            return output(corroborated?[corroborated]:[],corroborated?'halves-agree-after-primary-conflict':'conflict-halves-disagree-or-missing',true);
        }
        if (actOneHealth(result)) return output(result,'primary-scaled-readable',false);
        // Read both numeric halves independently when OCR mistakes the slash for 1.
        var left = scaledRows(img, 893, 998, 65, 25).filter(function (r) { return /^\d{1,5}$/.test(r.text.trim()); });
        var right = scaledRows(img, 967, 998, 65, 25).filter(function (r) { return /^\d{1,5}$/.test(r.text.trim()); });
        diagnostic.left=textRows(left);diagnostic.right=textRows(right);
        var halves=actOneNumericHealthHalves(left,right);
        if(!halves&&left.length===1&&/^\d{2,4}1$/.test(left[0].text.trim())){
            var narrow=scaledRows(img,905,998,42,25).filter(function(r){return /^\d{1,5}$/.test(r.text.trim());});
            diagnostic.narrowLeft=textRows(narrow);halves=actOneNumericHealthHalves(narrow,right);
        }
        if(halves) return output([halves.row],'independent-halves-fallback',false);
        return output(result,'health-unresolved',false);
    }
    function readMarker(img,finalTrial) {
        var templates = ['assets/quest-marker.png', 'assets/quest-marker-near.png'], matches = [];if((request&&request.step==='actTwoExam'||finalTrial===true))templates.push('assets/exam-target.png');
        for (var t = 0; t < templates.length; t++) {
            var mat = file.readImageMatSync(templates[t]), ro = null, found = null;
            try {
                ro = RecognitionObject.TemplateMatch(mat, 320, 150, 1400, (request&&request.step==='actTwoExam'||finalTrial===true)?780:630); ro.threshold = 0.82; ro.use3Channels = true;
                found = img.findMulti(ro);
                for (var j = 0; j < found.count; j++) {
                    var point = { x: Number(found[j].x) + Number(found[j].width) / 2, y: Number(found[j].y) + Number(found[j].height) / 2 };
                    if (actTwoSceneMarkerCandidate(point.x,point.y)&&!matches.some(function (m) { return Math.hypot(m.x-point.x,m.y-point.y) < 30; })) matches.push(point);
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
    function readEnemyBars(img, rows, level, nativeAcquisition) {
        enemyBarDiagnostic={level:level||1,candidates:0,localReads:[],greenMask:null};
        var top=nativeAcquisition===true?30:100;
        var left=nativeAcquisition===true||level===12||level===13?0:350;
        var crop=img.deriveCrop(left,top,nativeAcquisition===true||level===12||level===13?1920:1250,900-top),mask=null;
        try {
            mask=crop.srcMat.inRange(new OpenCvSharp.OpenCvSharp.Scalar(75,75,230),new OpenCvSharp.OpenCvSharp.Scalar(110,110,255));
            var contours=mask.findContoursAsArray(OpenCvSharp.OpenCvSharp.RetrievalModes.External,OpenCvSharp.OpenCvSharp.ContourApproximationModes.ApproxSimple),candidates=[],bars=[];
            for(var i=0;i<contours.length;i++) {
                var b=OpenCvSharp.OpenCvSharp.Cv2.boundingRect(contours[i]),w=Number(b.width),h=Number(b.height);
                // A nearly defeated enemy has a very short red segment. Requiring
                // a wide bar made the controller lose the target before the final hit.
                var bar={x:left+Number(b.x)+w/2,y:top+Number(b.y)+h/2,width:w,height:h};
                if(level==='any'&&request&&(request.mission==='navigation'&&["Go to the exam point","Talk to Amber","Check the suspicious location and eliminate any threats","Explore for Adventure Rank","Purchase Fisherman's Toast",'Offer the Anemoculus to the Statue','Give the Chicken-Mushroom Skewer to Lynn','Speak to Lynn','Talk to Katheryne for more details','Talk to Wagner the blacksmith','Collect three Iron Chunks and give them to Wagner','Talk to Kaeya','Talk to Kaeya at the meeting spot','Report to Kaeya','Meet with the informant at the designated location','Talk to the informant','Solve the mystery (Go to Kaeya at the Knights of Favonius HQ for a hint)',"Go to the Adventurers' Guild and listen to their report"].indexOf(request.objective)>=0||/^actTwo/.test(request.step||''))&&typeof OpenCvSharp.OpenCvSharp.Cv2.contourArea==='function')
                    bar.rectangularity=Number(OpenCvSharp.OpenCvSharp.Cv2.contourArea(contours[i],false))/Math.max(1,(w-1)*(h-1));
                if(actOneEnemyBarSize(w,h)||((level===4||level===5||level===10||level===11||level===12||level===13||level===14||level==='any')&&w>=2&&w<=300&&h>12&&h<=20)||nativeAcquisition===true&&w>=30&&w<=300&&h>20&&h<=32&&w/h>=3.5) candidates.push(bar);
            }
            candidates.sort(function(a,b){return b.height-a.height;});
            enemyBarDiagnostic.candidates=candidates.length;
            // Uncharted outdoor walking must stop for a visible red bar even when
            // OCR misses the enemy level. These candidates never authorize combat.
            if(level==='any'){
                var outdoor=candidates.filter(function(bar){return (nativeAcquisition!==true||bar.x>=350&&bar.x<=1600&&bar.height<=20)&&actOneOutdoorEnemyBarCandidate(bar,rows);});
                // The rounded ends occupy much of a depleted short bar. Two
                // recorded Lv.5 bars scored .731/.765 rather than .8. Recover
                // only small near-rectangles with a same-image exact level anchor.
                if(nativeAcquisition===true){
                    var depletedReads=0;
                    for(var d=0;d<candidates.length&&depletedReads<2;d++){
                        var cb=candidates[d];
                        var edge=cb.x<350||cb.x>1600;
                        var small=cb.width<=64&&cb.height<=9&&cb.rectangularity>=.7&&cb.rectangularity<.8;
                        var close=cb.width>=30&&cb.height>20&&cb.height<=32;
                        if(outdoor.indexOf(cb)>=0||cb.width<16||cb.width>300||cb.height<3||cb.height>32||cb.width/cb.height<3.5||!(small||(edge||close)&&cb.rectangularity>=.8&&cb.rectangularity<=1.05))continue;
                        depletedReads++;
                        var aw=edge||close?240:128,ah=close?80:edge?50:38;
                        var ax=Math.max(0,Math.min(1920-aw,Math.round(cb.x-(edge?30:10)))),ay=Math.max(0,Math.min(1080-ah,Math.round(cb.y-ah)));
                        var ar=scaledRows(img,ax,ay,aw,ah).map(function(r){return {text:r.text,x:ax+Number(r.x)/3,y:ay+Number(r.y)/3,width:Number(r.width)/3,height:Number(r.height)/3};});
                        var anchor=ar.filter(function(r){return actOneEnemyBarAnchored(cb,[r],5);});
                        enemyBarDiagnostic.localReads.push({bar:cb,rows:ar,anchored:anchor.length===1,depleted:small,edge:edge,close:close});
                        if(anchor.length===1){cb.levelAnchor=anchor[0];outdoor.push(cb);}
                    }
                }
                return outdoor;
            }
            // Full-frame OCR is cheap. If it misses the small green enemy label,
            // inspect at most four local crops around the most bar-like candidates.
            for(var c=0;c<candidates.length;c++) if(actOneEnemyBarAnchored(candidates[c],rows,level)) bars.push(candidates[c]);
            var fallbackCount=0,tightLabelAttempted=false;
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
                // Recorded distant Lv.4 labels disappear in the background-heavy
                // OCR crop. One tight color crop recovers their exact level; keep
                // larger and depleted bars on the existing recognition paths.
                if(!anchored&&level===4&&!tightLabelAttempted&&candidate.width>=50&&candidate.width<=90&&candidate.height>=3&&candidate.height<=6){
                    tightLabelAttempted=true;
                    var tx=Math.max(0,Math.min(1920-64,Math.round(candidate.x-32)));
                    var ty=Math.max(0,Math.min(1080-28,Math.round(candidate.y-30)));
                    var tight=scaledRows(img,tx,ty,64,28).map(function(r){return {text:r.text,x:tx+Number(r.x)/3,y:ty+Number(r.y)/3,width:Number(r.width)/3,height:Number(r.height)/3};});
                    anchored=actOneEnemyBarAnchored(candidate,tight,level);
                    enemyBarDiagnostic.tightLabel={bar:candidate,crop:{x:tx,y:ty,width:64,height:28,scale:3},rows:tight,anchored:anchored};
                }
                if(anchored) bars.push(candidate);
            }
            if(level===4||level===5) {
                var greenCandidates=candidates.filter(function(candidate){return candidate.width>=(level===4?2:50)&&candidate.height>=(level===4?3:6)&&
                    !bars.some(function(v){return Math.hypot(v.x-candidate.x,v.y-candidate.y)<2;});});
                greenCandidates.sort(function(a,b){return b.width-a.width;});
                if(greenCandidates.length) {
                    var greenCandidate=greenCandidates[0],greenCrop=null,greenMask=null,greenBgr=null,greenMat=null,greenScaled=null,greenRows=[];
                    var gx=Math.max(0,Math.min(1920-240,Math.round(greenCandidate.x-120)));
                    var gy=Math.max(0,Math.min(900-70,Math.round(greenCandidate.y-78)));
                    // Distant Lv.4 labels can end only 4px above the red bar.
                    // The old crop ended 8px above it, cutting off their baseline.
                    // Extend downward without changing the exact-level anchor.
                    var greenHeight=level===4?90:70;
                    try {
                        greenCrop=img.deriveCrop(gx,gy,240,greenHeight);
                        greenMask=level===4
                            ?greenCrop.srcMat.inRange(new OpenCvSharp.OpenCvSharp.Scalar(150,150,150),new OpenCvSharp.OpenCvSharp.Scalar(255,255,255))
                            :greenCrop.srcMat.inRange(new OpenCvSharp.OpenCvSharp.Scalar(20,110,40),new OpenCvSharp.OpenCvSharp.Scalar(130,230,190));
                        greenBgr=greenMask.cvtColor(OpenCvSharp.OpenCvSharp.ColorConversionCodes.GRAY2BGR,0);
                        greenMat=greenBgr.resize(new OpenCvSharp.OpenCvSharp.Size(720,greenHeight*3));
                        greenScaled=new ImageRegion(greenMat,0,0);
                        greenMat=null;
                        greenRows=readRows(greenScaled,0,0,720,greenHeight*3).map(function(r){return {text:r.text,x:gx+Number(r.x)/3,y:gy+Number(r.y)/3,width:Number(r.width)/3,height:Number(r.height)/3};});
                        var levelRows=greenRows.filter(function(r){return /^LV[1-9]$/.test(actOneEnemyLevelToken(r.text,level));});
                        var greenAnchored=levelRows.length===1&&actOneEnemyLevelToken(levelRows[0].text,level)==='LV'+level&&
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
    var wolfRecoveryContinueAttempted=false,wolfRecoveryBegun=false,wolfRecoveryPauseAttempted=false,
        wolfRecoveryStartedAt=null,wolfRecoveryInitialHp=null,wolfRecoveryLastHp=null,
        wolfRecoveryActions={VK_3:0,VK_E:0,VK_LBUTTON:0},wolfRecoveryPauseFrame=null,wolfRecoveryAfterResumeFrame=null,
        wolfRecoveryLastInputFrame=null,wolfRecoveryLastEAt=-Infinity,wolfRecoveryLastAttackAt=-Infinity;
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
            pauseProtectionActive=false;pauseProtectionObserver=null;pauseProtectionKeys=Object.create(null);pauseProtectionLastInputFrame=-1;pauseProtectionLastStatusAt=-Infinity;
            lionFieldState={closed:false,selected:false,fought:false,returnedAmber:false,paused:false,lastInputFrame:-1,observer:null,chartedProbePending:false,chartedProbeAnchor:null,climbReleaseArmed:false,climbReleaseAttempted:false};
            lisaRecoveryState={closed:false,mapOpened:false,teleported:false,lastInputFrame:-1,observer:null};
            lisaClimbReleaseDefinition=null;
            windriseState={used:false,moves:0,turns:0,interactions:0,paused:false,pauseOnly:false,lastInputFrame:-1,observer:null,plan:null};
            statueDialogueState={advanceAttempted:false,leaveAttempted:false,lastInputFrame:-1};
            lisaNavigationState={active:false,lastInputFrame:-1,lastField:null};
            worldInventoryCloseAttempted=false;
            lionDomainStartAttempted=false;lionPartyStartAttempted=false;lionFalconWaypointAttempted=false;
            wolfClosingState={begun:false,inputs:0,lastFrame:-1,lastFinishedAt:null};
            wolfChestAttempted=false;
            wolfLootCount=0;wolfLootFrame=null;
            request = value; events = []; navLastAcceptedPosition = null; focusRecoveryAttempted = false; wolfInfoAttempted = false; wolfContinueAttempted=false; wolfInventoryContinueAttempted=false; wolfInventoryOpenAttempted=false; wolfKaeyaFoodAttempted=false; wolfFeedKaeyaAttempted=false; wolfRecoveryFoodUseAttempted=false;wolfRecoveryFoodSelectAttempted=false;wolfRecoveryFoodFeedAttempted=false;wolfRecoveryFoodCloseAttempted=false;wolfExitFlameAttempted=false;wolfWindContinueAttempted=false;wolfWindSpaceAttempted=false;wolfWindRideContinueAttempted=false;wolfWindRideSpaceAttempted=false;wolfGlideContinueAttempted=false;wolfGlideMoves=0;wolfGlideLastMoveFrame=null;wolfGlideBaseline=null;wolfDefensiveCryoAttempted=false;wolfAimCryoAttempted=false;wolfCloseFoodAttempted=false;wolfCloseFoodCompletedAt=null;wolfCloseFoodLookAttempted=false;wolfCloseFoodForwardAttempted=false;wolfCloseFoodSkillAttempted=false;wolfTurretSkillAttempted=false;wolfTurretForwardAttempted=false;wolfTurretSkillFinishedAt=null;wolfTurretBaseline=null;wolfConsoleContinueAttempted=false;wolfConsoleInteractAttempted=false;wolfApproachContinueAttempted=false;wolfApproachMoveAttempted=false;wolfApproachHydroFrame=null;wolfApproachHydroReceiptId=null;wolfCombatSeekForwards=0;wolfCombatSeekTurns=0;wolfCombatSeekFrames=[];wolfBurstContinueAttempted=false;wolfBurstQAttempted=false;wolfBurstPauseAttempted=false;wolfCryoContinueAttempted=false;wolfCryoResumeConfirmedAt=null;wolfCryoBaseline=null;wolfCryoSkillAttempted=false;wolfCryoPauseAttempted=false;wolfCryoWaitMs=6500;wolfCryoWaitPlan=null;wolfRecoveryContinueAttempted=false;wolfRecoveryBegun=false;wolfRecoveryPauseAttempted=false;wolfRecoveryStartedAt=null;wolfRecoveryInitialHp=null;wolfRecoveryLastHp=null;wolfRecoveryActions={VK_3:0,VK_E:0,VK_LBUTTON:0};wolfRecoveryPauseFrame=null;wolfRecoveryAfterResumeFrame=null;wolfRecoveryLastInputFrame=null;wolfRecoveryLastEAt=-Infinity;wolfRecoveryLastAttackAt=-Infinity;
            wolfCryoLastInputFrame = null;
            wolfReviveContinueAttempted=false;wolfReviveContinueFrame=null;wolfReviveSelectAttempted=false;wolfReviveAmberBaseline=null;
            wolfReviveRecoverySelectAttempted=false;wolfReviveRecoveryConfirmAttempted=false;wolfReviveRecoverySelectFrame=null;
            wolfReviveRecoveryConfirmFrame=null;wolfReviveRecoveryAmberBaseline=null;
            wolfSecondState=newWolfSecondState();
            wolfCharactersStage=0;wolfCharactersLastFrame=-1;
            wolfWitnessState={continued:false,acted:false,paused:false,lastInputFrame:-1,permit:null,baseline:null};
            wolfSpikeState={continued:false,selectedKaeya:false,cast:false,selectedAmber:false,moves:0,paused:false,lastInputFrame:-1,pauseFrame:null,readyAt:null,amberBaseline:null,kaeyaBaseline:null,iceVerified:false,bankVerified:false,reuseSource:null,usingExistingIce:false,jumpAttempted:false,crossingCharacter:'amber'};
            var revision = {}, names = ['main.js','engine.js','bgi.js','mission.js','combat.js','recovery.js'];
            if(value.mission==='questStep'&&['actTwoMagePrep','actTwoMageBurst','actTwoMageFinish','actTwoMageNative','actTwoMageRetreat'].includes(value.step))names.push('act-two-mage.js','world-inventory.js','local-pause.js');
            if(value.mission==='questStep'&&value.step==='actTwoField')names.push('act-two-field.js','world-inventory.js','local-pause.js');
            if(value.mission==='questStep'&&['actTwoNativeCombat','actTwoNativeGroup','actTwoNativeFinish','actTwoNativeDeadlineProbe'].indexOf(value.step)>=0)names.push('act-two-native-combat.js','world-inventory.js','local-pause.js');
            if(value.mission==='questStep'&&value.step==='actTwoInformantCombat')names.push('act-two-informant-combat.js','world-inventory.js','local-pause.js');
            if(value.mission==='navigation'&&value.objective==='Meet Lisa at the temple')names.push('world-inventory.js','local-pause.js');
            if(value.mission==='questStep'&&value.step==='windriseReveal')names.push('windrise-reveal.js','world-inventory.js','local-pause.js','statue-dialogue.js','paused-navigation-anchor.js');
            if(value.mission==='questStep'&&['lionFieldCombat','lionFieldProbe'].indexOf(value.step)>=0)names.push('lion-field-combat.js','world-inventory.js','local-pause.js');
            if(value.mission==='questStep'&&value.step==='lionFieldProbe')names.push('paused-navigation-anchor.js','lisa-climb-release.js');
            if(value.mission==='questStep'&&value.step==='lisaStatueRecovery')names.push('lisa-statue-recovery.js','world-inventory.js','local-pause.js');
            if(value.mission==='questStep'&&value.step==='worldInventoryClose')names.push('world-inventory.js');
            if(value.mission==='questStep'&&(value.step==='lionStart'||value.step==='lionPartyStart'))names.push('lion-entry.js');
            if(value.mission==='questStep'&&value.step==='wolfSpikeCrossFirst')names.push('wolf-spike.js');
            if(value.mission==='questStep'&&value.step==='wolfSpikeCrossSecond')names.push('wolf-second-spike.js');
            if(value.mission==='questStep'&&value.step==='wolfWitnessAction')names.push('wolf-witness-action.js');
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
            if(request.step==='wolfContinue'||request.step==='wolfReviveKaeyaPrompt') {
                if(!actOneWolfResumeSeedTarget(value,Date.now())) throw new Error('Exact unique Wolf Continue and Leave menu required');
                var pauseReports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
                if(!actOneWolfEntryProven(pauseReports,request.session)) throw new Error('Same-session Wolf entry required');
                if(request.step==='wolfReviveKaeyaPrompt'&&!wolfRevivePermit()) throw new Error('Fresh unused Kaeya revival permit required');
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
        lionFalconWaypointReady: function (o) {
            checkStop();o=o||lastObservation;
            return !!(!lionFalconWaypointAttempted&&request&&request.mission==='questStep'&&['lionFalconWaypoint','lisaWolfWaypoint'].indexOf(request.step)>=0&&
                lastObservation&&o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&
                actOneLionFalconWaypointReady(o,Date.now(),request.session));
        },
        teleportLionFalconWaypoint: async function () {
            checkStop();ready();var o=lastObservation,target=request&&request.step==='lisaWolfWaypoint'?{x:-1642.421,y:2163.664}:actOneFalconWaypointTarget();
            if(!this.lionFalconWaypointReady(o))throw new Error('Fresh safe same-session Lisa objective required for Falcon waypoint');
            lionFalconWaypointAttempted=true;
            await boundedKey('VK_M',60);await sleep(200);checkStop();
            var event={type:request.step,x:target.x,y:target.y,frameId:o.frameId,session:request.session,startedAt:Date.now()};events.push(event);
            await genshin.tp(target.x,target.y,false);event.finishedAt=Date.now();checkStop();
            return {x:target.x,y:target.y,frameId:o.frameId,session:request.session};
        },
        falconDismissPyro: async function () {
            checkStop();var o=lastObservation;
            if(!request||!/^falconDismiss(Pyro|Tutorial)$/.test(request.step)||!o||Date.now()-o.timestamp>1000||o.map!==null||!(actOneFalconInfo(o.ocr)||request.step==='falconDismissTutorial'&&actOneAdventureRankInfo(o.ocr))||o.hud.journal||o.hud.bigMap||o.hud.dialogueReady) throw new Error('Fresh recognized English tutorial required');
            events.push({type:'falconPyroTutorialDismiss',x:960,y:1018,frameId:o.frameId,startedAt:Date.now()});
            click(960,1018);
        },
        falconEnterAim: async function () {
            checkStop();if(!request||request.step!=='falconEnterAim'||!actOneFalconDomainHud(lastObservation,Date.now())) throw new Error('Fresh Falcon trial ground HUD required');
            return boundedKey('VK_R',60);
        },
        falconSelectAmber: async function () {
            // A stationary party switch is recovery, including away from an
            // injured character. Movement and combat keep their own HP floors.
            checkStop();if(!request||request.mission!=='questStep'||!/^falconSelect(Amber|Traveler)$/.test(request.step)||!actOneFalconDomainHud(lastObservation,Date.now(),0.01)||
               lastObservation.hud.auto||lastObservation.hud.loading||lastObservation.hud.unknownHud) throw new Error('Fresh living domain HUD required before a recovery party switch');
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
        runWindriseReveal: async function(initial,observe) {
            var protector=loadLocalPause(),current=initial,result=null,operationError=null;
            var inventoryGate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            var closeAttempted=false,startedInField=actOneLocalPauseInputReady(initial,Date.now(),request.session);
            windriseState.observer=observe;
            try{
                var initialPermit=windrisePermit();
                if(initialPermit&&initialPermit.action==='interact')statueDialogueModule();
                if(inventoryGate(initial,Date.now(),request.session)){
                    if(!windrisePermit())throw new Error('Fresh reviewed field witness and paused source required before inventory close');
                    checkStop();closeAttempted=true;windriseState.lastInputFrame=initial.frameId;
                    var closeEvent={type:'windriseInventoryClose',key:'VK_ESCAPE',frameId:initial.frameId,startedAt:Date.now()};events.push(closeEvent);
                    try{await boundedKey('VK_ESCAPE',60,initial.frameId);}finally{closeEvent.finishedAt=Date.now();}
                    for(var poll=0;poll<6;poll++){
                        await sleep(150);current=await observe();
                        // A fading inventory can be neither a recognizable menu
                        // nor a readable field. Wait for field evidence, without
                        // repeating Escape or any movement during the transition.
                        if(windriseModule().fieldPauseReady(current,Date.now(),request.session))break;
                    }
                }
                result=await windriseModule().run(current,this,observe);
            }catch(e){operationError=String(e&&e.message||e);}
            if(closeAttempted||startedInField){
                if(result&&Number.isInteger(result.frameId))result.fieldFrameId=result.frameId;
                result=await finishWithLocalPause(protector,this,initial,observe,Math.max(initial.frameId,windriseState.lastInputFrame),result,operationError);
                result.pausedInventory=result.pauseProof.kind==='inventory';
                return result;
            }
            if(operationError)throw new Error(operationError);
            return result;
        },
        runActTwoSkewer: async function(initial,observe){
            var guard=eval(file.readTextSync('act-two-skewer.js')+'\nActTwoSkewer;'),current=initial,used=false,result={status:'stopped',foodUseAttempts:0,healingVerified:false};
            if(request.step!=='actTwoSkewer')throw new Error('Exact skewer healing request required');
            for(var i=0;i<5;i++){
                checkStop();ready();var target=guard.target(current,Date.now(),request.session,used);if(!target)break;
                events.push({type:'actTwoSkewer',action:target.action,quantity:target.action==='useOneSkewer'?1:null,frameId:current.frameId,startedAt:Date.now()});
                if(target.key)await boundedKey(target.key,60,current.frameId);else await actOneAccountUiClick({checkStop:checkStop,ready:ready,move:moveMouseTo,down:leftButtonDown,up:leftButtonUp,sleep:sleep},target);
                if(target.action==='useOneSkewer'){used=true;result.foodUseAttempts=1;}
                await sleep(500);current=await observe();if(used&&actOneLocalPauseProof(current,Date.now(),request.session)&&!guard.target(current,Date.now(),request.session,true))break;
            }
            result.frameId=current.frameId;result.pauseVerified=!!actOneLocalPauseProof(current,Date.now(),request.session);result.reason=used?'One skewer used; verify healing from HUD':'No food consumed; exact modal evidence unavailable';return result;
        },
        runActTwoHeal: async function(initial,observe){
            if(request&&request.mission==='questStep'&&request.step==='actTwoHealClose'){
                if(initial.session!==request.session||!actTwoOriginalAccount(initial.ocr||[])||!actOneKnownSafeFoodBoundary(initial,Date.now()))throw new Error('Fresh original-account food modal required');
                await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(500);var closed=await observe();
                return {status:'completed',step:request.step,frameId:closed.frameId,pauseVerified:!!actOneLocalPauseProof(closed,Date.now(),request.session),foodUseAttempted:false};
            }
            if(!request||request.mission!=='questStep'||request.step!=='actTwoHeal')throw new Error('Exact healing request required');
            var helper=eval(file.readTextSync('act-two-heal.js')+'\nActTwoHeal;');
            return helper.run(initial,{session:request.session,now:Date.now,original:function(o){return actTwoOriginalAccount(o.ocr||[]);},
                selected:function(o){return actOneWolfKaeyaFoodSelected(o,Date.now());},
                selectTarget:function(o){return actOneWolfKaeyaFoodTarget(o,Date.now());},
                feedTarget:function(o){return actOneWolfFeedKaeyaTarget(o,Date.now());},sleep:sleep,
                paused:function(o){return !!actOneLocalPauseProof(o,Date.now(),request.session);},
                click:async function(target,o,action){
                    checkStop();ready();if(!lastObservation||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp||Date.now()-o.timestamp>1000)throw new Error('Healing frame changed');
                    var event={type:'actTwoHeal',action:action,frameId:o.frameId,startedAt:Date.now()};events.push(event);
                    if(action==='useOneSweetMadame')event.quantity=1;
                    try{await actOneAccountUiClick({checkStop:checkStop,ready:ready,move:moveMouseTo,down:leftButtonDown,up:leftButtonUp,sleep:sleep},target);}finally{event.finishedAt=Date.now();}
                }},observe);
        },
        runActTwoQuestItems: async function(initial,observe){
            var proof=actOneLocalPauseProof(initial,Date.now(),request.session),rows=initial.ocr||[],target=null,action=null;
            if(rows.some(function(r){return r.text==='Treasure Clue (I)'&&r.x>700&&r.x<900&&r.y<80;})&&
                rows.some(function(r){return r.text==='Three six-armed giants reside'&&r.x>700&&r.y>100&&r.y<160;})&&
                rows.some(function(r){return r.text==='One, the treasure.'&&r.x>700&&r.y>230&&r.y<280;})){
                await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(500);var closed=await observe();
                return {status:'completed',step:request.step,action:'closeClue',frameId:closed.frameId,pauseVerified:!!actOneLocalPauseProof(closed,Date.now(),request.session),questComplete:false};
            }
            if(!proof||proof.kind!=='inventory')throw new Error('Fresh quest-items tutorial and inventory required');
            if(actTwoOriginalAccount(rows)&&['Go to the quest tab to','check the clues regarding','the treasure'].every(function(t){return rows.some(function(r){return r.text===t&&r.x>=1000&&r.x<=1300&&r.y>=90&&r.y<=160;});})){target={x:1152,y:47};action='questTab';}
            else if(rows.some(function(r){return r.text==='Quest'&&r.x<250&&r.y<80;})&&
                rows.some(function(r){return r.text==='Crimson Crystal'&&r.x>1300&&r.y>100&&r.y<180;})&&
                rows.some(function(r){return r.text==='Select the clues you have'&&r.x>380&&r.x<450&&r.y>250&&r.y<310;})&&
                rows.some(function(r){return r.text==='obtained'&&r.x>450&&r.x<550&&r.y>=295&&r.y<340;})){target={x:327,y:190};action='selectClue';}
            else if(rows.some(function(r){return r.text==='Treasure Clue (I)'&&r.x>1300&&r.y>100&&r.y<180;})){
                var read=rows.filter(function(r){return r.text==='Read'&&r.x>1600&&r.x<1750&&r.y>980&&r.y<1040;});
                if(read.length===1){target={x:Math.round(read[0].x+read[0].width/2),y:Math.round(read[0].y+read[0].height/2)};action='readClue';}
            }
            if(!target)throw new Error('Recognized treasure-clue tutorial stage required');
            checkStop();ready();events.push({type:'actTwoQuestItems',action:action,frameId:initial.frameId,startedAt:Date.now()});click(target.x,target.y);await sleep(650);
            var current=await observe();return {status:'completed',step:request.step,action:action,frameId:current.frameId,pauseVerified:!!actOneLocalPauseProof(current,Date.now(),request.session),questComplete:false};
        },
        runActTwoMageRetreat: async function(initial,observe){
            var inventory=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            if(request.step!=='actTwoMageRetreat'||!inventory(initial,Date.now(),request.session))throw new Error('Fresh inventory required for mage retreat');
            var current=initial,result={status:'stopped',recoveryInputs:0},error=null;
            function safe(o){var h=o.hud,m=o.map;return actTwoOriginalAccount(o.ocr)&&h.world&&!h.climbing&&!h.auto&&!h.dialogueReady&&!h.choice&&h.health&&h.health.current>0&&[1363,1186,2313].includes(h.health.max)&&m&&m.map==='Teyvat'&&Math.hypot(m.x+1567,m.y-2236)<20;}
            try{
                await boundedKey('VK_ESCAPE',60,initial.frameId);
                for(var poll=0;poll<2;poll++){await sleep(200);current=await observe();if(current.hud.health)break;}
                if(!safe(current))throw new Error('Fresh living mage encounter required for retreat');
                if(current.ocr.some(function(r){return r.text==='Space'&&r.x>1200&&r.x<1500&&r.y>450&&r.y<650;})){
                    for(var thaw=0;thaw<4;thaw++){await boundedKey('VK_SPACE',60,current.frameId);result.recoveryInputs++;await sleep(120);}
                    current=await observe();
                }
                for(var key of ['VK_S','VK_D']){if(!safe(current))throw new Error('Retreat field changed');await boundedKey(key,700,current.frameId);result.recoveryInputs++;await sleep(200);current=await observe();}
                result.fieldFrameId=current.frameId;result.fieldHealth=current.hud.health;
            }catch(e){error=String(e&&e.message||e);result.reason=error;}finally{release();}
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error);
        },
        runActTwoMageNative: async function(initial,observe){
            var inventory=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            if(request.step!=='actTwoMageNative'||!inventory(initial,Date.now(),request.session))throw new Error('Fresh inventory required for bounded mage rotation');
            var current=initial,result={status:'stopped',nativeFightAttempted:false},error=null;
            try{
                await boundedKey('VK_ESCAPE',60,initial.frameId);
                for(var poll=0;poll<2;poll++){await sleep(250);current=await observe();if(current.hud.health)break;}
                var h=current.hud,m=current.map;
                if(!actTwoOriginalAccount(current.ocr)||!h.world||!h.groundControls||h.climbing||h.auto||h.dialogueReady||h.choice||!h.health||h.health.max!==2313||h.health.current<1967||!m||m.map!=='Teyvat'||Math.hypot(m.x+1563,m.y-2233)>20||!h.enemyBars||!h.enemyBars.length)throw new Error('Healthy Kaeya and close mage encounter required');
                result.nativeFightAttempted=true;events.push({type:'actTwoMageNativeFight',strategy:STARTER_TRIAL_STRATEGY,timeoutMs:8000,frameId:current.frameId,startedAt:Date.now()});
                try{await runStarterTrialAutoFight({createLinkedCancellationTokenSource:function(){return dispatcher.GetLinkedCancellationTokenSource();},createAutoFightParam:function(name){return new AutoFightParam(name);},runAutoFightTask:function(param,token){return dispatcher.RunAutoFightTask(param,token);}},function(){checkStop();ready();},{sleep:sleep,timeoutMs:8000});}
                catch(e){if(e.name!=='NativeFightTimeoutError')throw e;result.boundedTimeout=true;}
                release();await sleep(200);current=await observe();result.fieldFrameId=current.frameId;result.fieldHealth=current.hud.health;
            }catch(e){error=String(e&&e.message||e);result.reason=error;}finally{release();}
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error);
        },
        runActTwoMageBurst: async function(initial,observe){
            var inventory=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;'),guard=eval(file.readTextSync('act-two-mage.js')+'\nActTwoMage;');
            var pyro=eval(file.readTextSync('act-two-cyrus-pyro.js')+'\nActTwoCyrusPyro;'),original=function(o){return actTwoOriginalAccount(o.ocr||[]);};
            if(request.step!=='actTwoMageBurst'||!inventory(initial,Date.now(),request.session))throw new Error('Fresh inventory for mage burst required');
            var current=initial,result={status:'stopped',bursts:0,skills:0},error=null;
            try{
                await boundedKey('VK_ESCAPE',60,initial.frameId);
                for(var poll=0;poll<2;poll++){await sleep(150);current=await observe();if(guard.burst(current,Date.now(),request.session)||current.hud.health)break;}
                if(pyro.preparation(current,Date.now(),request.session,original)){
                    result=await pyro.run(current,{now:Date.now,session:request.session,original:original,sleep:sleep,observe:observe,release:release,key:async function(k,ms,o){await boundedKey(k,ms,o.frameId);}});
                    current=result.current;delete result.current;
                    result.fieldFrameId=current.frameId;
                }else{
                if(!actTwoOriginalAccount(current.ocr)||!guard.burst(current,Date.now(),request.session))throw new Error('Fresh healthy Amber and close level13 mage required');
                await boundedKey('VK_Q',60,current.frameId);result.bursts++;await sleep(650);current=await observe();
                if(actTwoOriginalAccount(current.ocr)&&guard.burst(current,Date.now(),request.session)){await boundedKey('VK_E',60,current.frameId);result.skills++;}
                await sleep(300);current=await observe();
                result.fieldFrameId=current.frameId;result.fieldHealth=current.hud.health;result.reason='Single Pyro burst cycle ended; inspect shield';
                }
            }catch(e){error=String(e&&e.message||e);result.reason=error;}finally{release();}
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error);
        },
        runActTwoMagePrep: async function(initial,observe){
            var inventory=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;'),guard=eval(file.readTextSync('act-two-mage.js')+'\nActTwoMage;');
            if(!['actTwoMagePrep','actTwoMageFinish'].includes(request.step)||!inventory(initial,Date.now(),request.session))throw new Error('Fresh inventory for mage preparation required');
            var finish=request.step==='actTwoMageFinish',allowed=finish?guard.switchToKaeya:guard.preparation;
            var current=initial,result={status:'stopped',selectionAttempted:false},error=null;
            try{
                await boundedKey('VK_ESCAPE',60,initial.frameId);
                for(var poll=0;poll<2;poll++){await sleep(150);current=await observe();if(allowed(current,Date.now(),request.session)||current.hud.health)break;}
                if(!actTwoOriginalAccount(current.ocr)||!allowed(current,Date.now(),request.session))throw new Error('Fresh mage approach and exact party slot required');
                await boundedKey(finish?'VK_3':'VK_2',60,current.frameId);result.selectionAttempted=true;await sleep(600);current=await observe();
                result.fieldFrameId=current.frameId;result.fieldHealth=current.hud.health;result.reason=(finish?'Kaeya':'Amber')+' selected once; inspect before attacks';
            }catch(e){error=String(e&&e.message||e);result.reason=error;}finally{release();}
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error);
        },
        runActTwoNativeCombat: async function(initial,observe){
            var gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            var native=eval(file.readTextSync('act-two-native-combat.js')+'\nActTwoNativeCombat;');
            if(['actTwoNativeCombat','actTwoNativeGroup','actTwoNativeFinish','actTwoNativeDeadlineProbe'].indexOf(request.step)<0||!gate(initial,Date.now(),request.session)||!actTwoOriginalAccount(initial.ocr||[]))throw new Error('Fresh original-account inventory required');
            var finishing=request.step==='actTwoNativeFinish',permit=null,prior=null,witness=null;
            if(finishing){permit=JSON.parse(file.readTextSync('act-two-native-finish-request.json'));if(!/^mission-[a-f0-9]{32}$/.test(permit.priorId))throw new Error('Invalid prior combat receipt');prior=JSON.parse(file.readTextSync('receipts/'+request.session+'/'+permit.priorId+'.json'));var wf=prior.details&&prior.details.result&&prior.details.result.afterFrameId;if(!Number.isInteger(wf))throw new Error('Missing prior combat frame');witness=JSON.parse(file.readTextSync('observations/'+request.session+'/frame-'+String(wf).padStart(4,'0')+'.json'));}
            var probing=request.step==='actTwoNativeDeadlineProbe',group=!probing&&request.step!=='actTwoNativeCombat',current=initial,result={status:'stopped',nativeGroup:group,nativeAttempted:false,damageConfirmed:false,defeatConfirmed:false},error=null;
            var acquisition=eval(file.readTextSync('act-two-combat-acquisition.js')+'\nActTwoCombatAcquisition;'),ambushWitness=null,defenseParam=null,acquisitionImage=null,acquisitionImageAt=null;
            if(group&&!finishing){
                for(var wf=initial.frameId-1;wf>Math.max(0,initial.frameId-32);wf--){
                    var wp='observations/'+request.session+'/frame-'+String(wf).padStart(4,'0')+'.json';
                    if(!file.isExists(wp))continue;
                    var candidate=JSON.parse(file.readTextSync(wp));
                    if(candidate.hud&&candidate.hud.world){if(acquisition.pausedWitness(candidate,initial,Date.now(),function(o){return actTwoOriginalAccount(o.ocr||[]);}))ambushWitness=candidate;break;}
                }
                if(ambushWitness)defenseParam=native.targetingParam(new AutoFightParam('English Cyrus Defense'),true);
            }
            function original(o){return actTwoOriginalAccount(o.ocr||[]);}
            function eligible(o){if(o&&o.acquisition)return acquisition.eligible(o,initial,ambushWitness,Date.now());if(probing)return native.deadlineProbe(o,Date.now(),request.session,original);return finishing?native.finish(o,witness,prior,permit,request,Date.now(),original):native.encounter(o,Date.now(),request.session,original,group);}
            function acquire(){
                checkStop();ready();var capturedAt=Date.now(),img=captureGameRegion();
                try{
                    if(Number(img.width)!==1920||Number(img.height)!==1080)throw new Error('1920x1080 acquisition required');
                    var data=acquisition.read(img,{health:function(im){return actOneHealth(readHealth(im,[]).rows);},rows:readRows,controls:function(im){return actOneMergeControlCropRows([],scaledRows(im,1520,985,390,80),1520,985);},ground:actOneGroundControlEvidence,bars:function(im){return readEnemyBars(im,[],'any',true);}});
                    var mp=genshin.getPositionFromMap('Teyvat',host.toSingle(ambushWitness.map.x),host.toSingle(ambushWitness.map.y));
                    data.map=mp&&Number.isFinite(Number(mp.x))&&Number.isFinite(Number(mp.y))?{x:Number(mp.x),y:Number(mp.y),map:'Teyvat',cameraAngle:Number(genshin.getCameraOrientation())}:null;
                    data.session=request.session;data.frameId=null;data.timestamp=capturedAt;data.acquisition=true;data.accountPauseFrameId=initial.frameId;
                    data.hud.enemyBarDiagnostic=JSON.parse(JSON.stringify(enemyBarDiagnostic));
                    data.elapsedMs=Date.now()-capturedAt;events.push({type:'actTwoNativeAcquisition',startedAt:capturedAt,finishedAt:Date.now(),evidence:data});
                    return data;
                }finally{dispose(acquisitionImage);acquisitionImage=img;acquisitionImageAt=capturedAt;}
            }
            try{
                await boundedKey('VK_ESCAPE',60,initial.frameId);
                if(ambushWitness){await sleep(550);current=acquire();result.acquisition=current;}
                else for(var poll=0;poll<3;poll++){await sleep(poll===0?450:150);current=await observe();if(eligible(current)||native.entrySettled(current))break;}
                if(!eligible(current))throw new Error('Fresh grounded Kaeya health and one close enemy bar required');
                for(var alignmentAttempt=0;alignmentAttempt<2&&current.acquisition&&!acquisition.stationaryReady(current.hud.enemyBars);alignmentAttempt++){
                    checkStop();ready();var alignDx=acquisition.cameraDelta(current.hud.enemyBars);
                    events.push({type:'actTwoNativeCameraAlignment',dx:alignDx,dy:0,startedAt:Date.now()});
                    moveMouseBy(alignDx,0);await sleep(180);current=acquire();result.alignedAcquisition=current;
                    if(!eligible(current))throw new Error('Fresh encounter required after camera alignment');
                }
                if(group&&!finishing&&acquisition.ambushObjective(current.hud.objectives)&&
                   !acquisition.stationaryReady(current.acquisition?current.hud.enemyBars:native.targets(current)))throw new Error('Centered or close verified enemy required for stationary combat');
                checkStop();ready();
                if(finishing){permit.usedAt=Date.now();var saved=JSON.stringify(permit);if(!file.writeTextSync('act-two-native-finish-request.json',saved)||file.readTextSync('act-two-native-finish-request.json')!==saved)throw new Error('Finishing permission consumption failed');result.finishing=true;}
                result.beforeFrameId=current.frameId;result.beforeHealth=current.hud.health;result.beforeBars=current.acquisition?acquisition.framingTargets(current.hud.enemyBars):native.targets(current);result.nativeAttempted=true;
                async function runChunk(o,index){
                    var rotation=probing?'凯亚 '+Array(200).fill('wait(0.05)').join(', '):group&&!finishing?(acquisition.ambushObjective(o.hud.objectives)?native.ambushStrategy:native.groupStrategy):native.strategy;
                    var defensive=group&&!finishing&&acquisition.ambushObjective(o.hud.objectives);
                    if(defensive&&!acquisition.stationaryReady(o.acquisition?o.hud.enemyBars:native.targets(o)))throw new Error('Centered or close verified enemy required for stationary combat');
                    var event={type:'actTwoNativeCombat',engine:defensive?'AutoFightTask':'RunCombatScript',strategy:defensive?'English Cyrus Defense':rotation,chunkIndex:index,frameId:o.frameId,startedAt:Date.now()};events.push(event);
                    try{return await native.chunk({
                        createCancellation:function(){return dispatcher.GetLinkedCancellationTokenSource();},
                        armDeadline:function(cts,ms){cts.CancelAfter(ms);},
                        run:function(script,token){if(defensive)return dispatcher.RunAutoFightTask(defenseParam||native.targetingParam(new AutoFightParam('English Cyrus Defense'),true),token);return dispatcher.RunCombatScript(script,script===native.ambushStrategy?null:'凯亚',token);},
                        release:function(){release();try{keyUp('VK_W');}finally{try{keyUp('VK_E');}finally{try{keyUp('VK_Q');}finally{try{keyUp('VK_3');}finally{try{keyUp('VK_D');}finally{leftButtonUp();rightButtonUp();}}}}}}
                    },function(){checkStop();ready();},{now:Date.now,sleep:sleep,timeoutMs:4000,strategy:rotation,sampleAfterMs:900,sample:defensive?async function(){
                        var sampled=await observe(),hp=sampled.hud&&sampled.hud.health;
                        if(!result.midFightObservations)result.midFightObservations=[];
                        result.midFightObservations.push({frameId:sampled.frameId,health:hp,map:sampled.map});
                        if(sampled.session!==request.session||!original(sampled)||Date.now()-sampled.timestamp>1000||!hp||hp.max!==2635||hp.current<hp.max*.9||hp.current>hp.max)throw new Error('Native sampled health or session guard failed');
                    }:null});}
                    finally{event.finishedAt=Date.now();result.nativeInvocationMs=(result.nativeInvocationMs||0)+event.finishedAt-event.startedAt;}
                }
                if(group&&!finishing&&!ambushWitness){
                    var batch=await native.sequence(current,{now:Date.now,sleep:sleep,eligible:eligible,run:runChunk,observe:observe});
                    current=batch.current;result.chunks=batch.turns;result.nativeReturned=batch.turns.every(function(t){return t.nativeReturned;});result.nativeMs=batch.turns.reduce(function(n,t){return n+t.nativeMs;},0);result.reason=batch.reason;
                }else if(ambushWitness){
                    var localStarted=Date.now();result.localChunks=[];result.nativeMs=0;
                    for(var localTurn=0;localTurn<3;localTurn++){
                        var localChunk=await runChunk(current,localTurn);result.localChunks.push(localChunk);result.nativeMs+=localChunk.nativeMs;result.nativeReturned=true;
                        if(localTurn===2||Date.now()-localStarted>=10000)break;
                        await sleep(150);current=acquire();
                        if(!eligible(current)){result.continuationStop='Fresh target, objective, health or position changed';break;}
                        for(var localAlign=0;localAlign<2&&!acquisition.stationaryReady(current.hud.enemyBars);localAlign++){
                            checkStop();ready();var localDx=acquisition.cameraDelta(current.hud.enemyBars);
                            events.push({type:'actTwoNativeCameraAlignment',dx:localDx,dy:0,startedAt:Date.now(),continuation:true});
                            moveMouseBy(localDx,0);await sleep(180);current=acquire();if(!eligible(current))break;
                        }
                        if(!eligible(current)||!acquisition.stationaryReady(current.hud.enemyBars)){result.continuationStop='No fresh close target after bounded reacquisition';break;}
                    }
                    await sleep(150);current=await observe();result.localElapsedMs=Date.now()-localStarted;
                    result.reason='Bounded local combat sequence ended; inspect rewards and remaining enemies';
                }else{Object.assign(result,await runChunk(current,0));await sleep(150);current=await observe();result.reason='One native rotation returned; independently inspect damage and rewards';}
                result.afterFrameId=current.frameId;result.afterHealth=current.hud.health;result.afterBars=native.targets(current);
            }catch(e){error=String(e&&e.message||e);result.reason=error;if(current&&current.acquisition&&current.hud.world&&Date.now()-current.timestamp<=1000){await boundedKey('VK_B',60,null);result.acquisitionPauseRequested=true;await sleep(650);}}
            finally{release();if(Number.isFinite(result.nativeInvocationMs))result.nativeMs=result.nativeInvocationMs;}
            try{
                var pausedResult=await finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error,
                    !error&&result.nativeReturned?native.pauseSeed(current,lastObservation,Date.now(),request.session):null);
                if(acquisitionImage&&pausedResult.pauseVerified){
                    var acquisitionPath='observations/acq-'+request.id.slice(-12)+'/frame-0001.png';
                    pausedResult.exactImage={path:acquisitionPath,capturedAt:acquisitionImageAt,saved:file.writeImageSync(acquisitionPath,acquisitionImage.srcMat)};
                }
                return pausedResult;
            }finally{dispose(acquisitionImage);}
        },
        runActTwoPauseProbe: async function(initial,observe){
            var gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            if(request.step!=='actTwoPauseProbe'||!gate(initial,Date.now(),request.session)||!actTwoOriginalAccount(initial.ocr))throw new Error('Fresh original-account Inventory required');
            var current=initial,error=null,result={status:'stopped',step:request.step,nativeAttempted:false};
            try{
                await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(550);current=await observe();
                var h=current.hud,m=current.map;
                if(!actTwoOriginalAccount(current.ocr)||!h.world||!h.groundControls||h.climbing||h.journal||h.bigMap||h.dialogueReady||h.choice||
                   !h.health||h.health.current!==2635||h.health.max!==2635||(h.enemyBars||[]).length||!m||m.map!=='Teyvat'||Math.hypot(m.x+1265.917,m.y-1928.381)>8)throw new Error('Full-health safe Statue field required');
                result.fieldFrameId=current.frameId;result.fieldHealth=h.health;result.handoffStartedAt=Date.now();
            }catch(e){error=String(e&&e.message||e);result.reason=error;}finally{release();}
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error,error?null:current);
        },
        runActTwoEmergencyMap: async function(initial,observe){
            var g=eval(file.readTextSync('act-two-emergency-switch.js')+'\nActTwoEmergencySwitch;'),gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            var p=JSON.parse(file.readTextSync('act-two-recovery-request.json')),w=JSON.parse(file.readTextSync('observations/'+request.session+'/frame-'+String(p.witnessFrameId).padStart(4,'0')+'.json'));
            if(!g.permit(initial,w,p,request,Date.now(),gate(initial,Date.now(),request.session),'map'))throw new Error('Fresh verified Inventory and active-event recovery witness required');
            p.usedAt=Date.now();file.writeTextSync('act-two-recovery-request.json',JSON.stringify(p));
            var result={status:'stopped',recoveryOnly:true},error=null,start=Date.now();
            try{
                await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(600);await boundedKey('VK_M',60,initial.frameId);result.unpauseToMapKeyMs=Date.now()-start;await sleep(750);
                var current=await observe();result.frameId=current.frameId;result.mapOpened=!!(current.hud.bigMap&&actTwoOriginalAccount(current.ocr));
                if(result.mapOpened){result.status='completed';result.reason='Emergency map verified; select existing recovery waypoint';return result;}
                error='Map did not open; stop and restore Inventory';
            }catch(e){error=String(e&&e.message||e);}finally{release();}
            result.reason=error;return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error,lastObservation&&lastObservation.hud.world&&Date.now()-lastObservation.timestamp<=1000?lastObservation:null);
        },
        runActTwoEmergencySwitch: async function(initial,observe){
            var g=eval(file.readTextSync('act-two-emergency-switch.js')+'\nActTwoEmergencySwitch;'),gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            var p=JSON.parse(file.readTextSync('act-two-recovery-request.json')),w=JSON.parse(file.readTextSync('observations/'+request.session+'/frame-'+String(p.witnessFrameId).padStart(4,'0')+'.json'));
            if(!g.permit(initial,w,p,request,Date.now(),gate(initial,Date.now(),request.session)))throw new Error('Fresh verified Inventory and active final-event recovery witness required');
            p.usedAt=Date.now();file.writeTextSync('act-two-recovery-request.json',JSON.stringify(p));
            var result={status:'stopped',recoveryOnly:true},error=null;
            try{
                await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(600);checkStop();ready();
                var ng=eval(file.readTextSync('act-two-native-combat.js')+'\nActTwoNativeCombat;'),param=ng.targetingParam(new AutoFightParam('English Ley Line Recovery'),true);param.Timeout=2;
                Object.assign(result,await ng.chunk({createCancellation:function(){return dispatcher.GetLinkedCancellationTokenSource();},armDeadline:function(cts,ms){cts.CancelAfter(ms);},run:function(script,token){return dispatcher.RunAutoFightTask(param,token);},release:function(){release();keyUp('VK_1');keyUp('VK_S');keyUp('VK_W');keyUp('VK_SHIFT');leftButtonUp();rightButtonUp();}},function(){checkStop();ready();},{now:Date.now,sleep:sleep,timeoutMs:3000}));
                var current=await observe();result.fieldFrameId=current.frameId;result.health=current.hud.health;result.switchVerified=!!(current.hud.world&&current.hud.health&&current.hud.health.max===2451);
                result.reason=result.switchVerified?'Native switch to Traveler verified':'Native switch returned; inspect active character';
            }catch(e){error=String(e&&e.message||e);result.reason=error;}finally{release();keyUp('VK_1');keyUp('VK_S');keyUp('VK_W');rightButtonUp();}
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error,lastObservation&&lastObservation.hud.world&&Date.now()-lastObservation.timestamp<=1000?lastObservation:null);
        },
        actTwoExamRecoveryReady:function(o){return !!eval(file.readTextSync('act-two-exam.js')+'\nActTwoExam;').recoveryTarget(o,Date.now(),request.session);},
        runActTwoExamRecovery:async function(initial,observe){
            var target=eval(file.readTextSync('act-two-exam.js')+'\nActTwoExam;').recoveryTarget(initial,Date.now(),request.session);
            if(request.step!=='actTwoRecover'||!target)throw new Error('Exact challenge abandonment confirmation required');
            checkStop();ready();events.push({type:'actTwoExamAbandon',frameId:initial.frameId,startedAt:Date.now()});click(Math.round(target.x),Math.round(target.y));await sleep(700);
            var current=await observe();return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,{status:'stopped',abandonAttempted:true,questComplete:false},null);
        },
        takeFinalTrialPlan:function(field,resume){
            var p;try{p=JSON.parse(file.readTextSync('act-two-final-trial-request.json'));}catch(e){return false;}
            if(!p||p.frameId!==request.expectedFrameId||p.session!==request.session||p.usedAt)return false;
            var g=eval(file.readTextSync('act-two-final-trial.js')+'\nActTwoFinalTrial;');
            var startResume=resume===true&&p.resumeStart===true;
            if(request.step!==(resume?'actTwoFinalTrial':'actTwoAmberTalk')||p.resumeTop!==(resume&&!startResume?true:undefined)||p.enabled!==true||!Number.isFinite(p.createdAt)||Date.now()<p.createdAt||Date.now()-p.createdAt>120000||!g.safe(field,Date.now(),request.session)||(resume&&!startResume?!g.resumePosition(field.map):Math.hypot(field.map.x+772.97,field.map.y-2242.88)>0.65))throw Error('Prepared final trial plan and exact start required');
            p.usedAt=Date.now();p.requestId=request.id;var s=JSON.stringify(p);if(!file.writeTextSync('act-two-final-trial-request.json',s)||file.readTextSync('act-two-final-trial-request.json')!==s)throw Error('Final trial plan consumption failed');
            if(p.stepOffFromReviewedEdge===true&&(!resume||startResume||Math.hypot(field.map.x+777.990234375,field.map.y-2240.9111328125)>.4))throw Error('Exact reviewed outer edge required');request.finalTrialStepOff=p.stepOffFromReviewedEdge===true;request.finalTrialPrepareOnly=p.inspectBeforeLaunch===true;events.push({type:'finalTrialPlan',frameId:field.frameId,startedAt:Date.now()});return startResume?'start':true;
        },
        runActTwoFinalTrial:async function(initial,observe,dialogue,resume){
            var trial=eval(file.readTextSync('act-two-final-trial.js')+'\nActTwoFinalTrial;'),launch=eval(file.readTextSync('act-two-exam-launch.js')+'\nActTwoExamLaunch;'),guard=eval(file.readTextSync('act-two-exam.js')+'\nActTwoExam;');
            var lastFast=null,keyEvent=null,headerVerified=false;
            function stopKeys(){try{keyUp('VK_SPACE');}finally{release();if(keyEvent){keyEvent.finishedAt=Date.now();keyEvent=null;}}}
            function checked(){checkStop();ready();}
            function forwardDown(){checked();release();held='VK_W';keyEvent={type:'key',key:'VK_W',startedAt:Date.now(),frameId:lastObservation.frameId,finalTrial:true};events.push(keyEvent);keyDown('VK_W');}
            async function look(dx,dy){checked();if(Math.abs(dx)>750||Math.abs(dy)>500)throw Error('Final trial camera bound');events.push({type:'finalTrialLook',dx:dx,dy:dy,startedAt:Date.now()});moveMouseBy(dx,dy);}
            async function sample(markers){
                checked();var began=Date.now(),img=captureGameRegion();
                try{
                    if(Number(img.width)!==1920||Number(img.height)!==1080)return{valid:false};
                    var rows=readRows(img,1550,975,350,85),hp=actOneHealth(readHealth(img,[]).rows),s={valid:false,groundControls:rows.some(r=>r.text==='E'||r.text==='Q'),climbing:rows.some(r=>r.text==='X'),space:rows.some(r=>r.text==='Space')&&!rows.some(r=>['E','Q','X'].includes(r.text)),health:hp,rows:rows,capturedAt:began};
                    if(!headerVerified||!markers){s.header=readRows(img,50,235,700,100).concat(readRows(img,850,25,250,70),actOneMergeControlCropRows([],scaledRows(img,1660,1040,240,40),1660,1040));s.timer=trial.timer({ocr:s.header});
                        s.valid=!!(hp&&hp.max===4015&&hp.current>=3614&&hp.current<=4015&&s.header.some(r=>r.x>1600&&r.y>1020&&/693306810$/.test(r.text))&&s.timer>=3&&s.timer<=60&&s.header.some(r=>r.x<750&&r.y>=230&&r.y<=350&&['Reachthetargetlocationwithin60','Reachthetargetlocationwithin60seconds'].includes(r.text.replace(/[^A-Za-z0-9]/g,''))));headerVerified=s.valid;
                    }else s.valid=!!(hp&&hp.max===4015&&hp.current>=3614&&hp.current<=4015);
                    if(markers){s.marker=readMarker(img,true);s.distance=null;if(s.marker){var dc=guard.distanceCrop(s.marker);s.distanceRows=dc?readRows(img,dc.x,dc.y,dc.width,dc.height):[];s.distance=guard.distance(s.distanceRows);if(s.distance===null){s.distanceRows=scaledRows(img,Math.round(s.marker.x-55),Math.round(s.marker.y+12),110,65);s.distance=guard.distance(s.distanceRows);}}}
                    s.elapsedMs=Date.now()-began;return s;
                }finally{if(lastFast)dispose(lastFast);lastFast=img;}
            }
            function fastApi(markers){return{now:Date.now,check:checked,sleep:sleep,release:stopKeys,forwardDown:forwardDown,look:look,pressSpace:async()=>{checked();var e={type:'key',key:'VK_SPACE',durationMs:60,startedAt:Date.now(),frameId:lastObservation.frameId,finalTrial:true};events.push(e);try{keyDown('VK_SPACE');await sleep(60);checked();}finally{keyUp('VK_SPACE');e.finishedAt=Date.now();}},sample:()=>sample(markers),pause:async()=>{stopKeys();}};}
            try{
                var outcome=await trial.run(initial,{resume:resume===true,prepareOnly:request.finalTrialPrepareOnly===true,stepOff:request.finalTrialStepOff===true,wallJump:async()=>{var a=fastApi(false);try{a.forwardDown();await a.pressSpace();await sleep(800);checked();}finally{stopKeys();}},now:Date.now,check:checked,sleep:sleep,release:stopKeys,observe:observe,look:look,key:async(k,ms)=>{checked();if(!['VK_SPACE','VK_W'].includes(k)||ms<30||ms>800)throw Error('Final trial input bound');await boundedKey(k,ms,lastObservation.frameId);},
                    launch:async()=>{headerVerified=false;var r=request.finalTrialStepOff===true?await launch.recover(fastApi(false)):await launch.run(fastApi(false),false);delete r.quickPause;r.pauseDeferredToOwner=true;return r;},
                    course:async()=>{headerVerified=false;var r=await launch.course(fastApi(true));delete r.quickPause;r.pauseDeferredToOwner=true;return r;}});
                outcome.dialogue=dialogue;return outcome;
            }finally{stopKeys();if(lastFast)dispose(lastFast);}
        },
        runActTwoExam: async function(initial,observe){
            var guard=eval(file.readTextSync('act-two-exam.js')+'\nActTwoExam;'),gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            var p=JSON.parse(file.readTextSync('act-two-exam-request.json')),current=initial,attempted=false,result={status:'stopped'},error=null;
            if(request.step!=='actTwoExam'||!(gate(initial,Date.now(),request.session)||guard.journalReady(initial,Date.now(),request.session))||!guard.plan(p,request,Date.now()))throw new Error('Fresh inventory and reviewed exam plan required');
            var w=JSON.parse(file.readTextSync('observations/'+request.session+'/frame-'+String(p.witnessFrameId).padStart(4,'0')+'.json'));
            if(w.frameId!==p.witnessFrameId||(p.mode!=='inspect'&&Date.now()-w.timestamp>600000)||!(guard.state(w,w.timestamp,request.session)||p.afterTrial===true&&guard.afterTrial(w,w.timestamp,request.session,p.mode==='ground')))throw new Error('Reviewed exam witness required');
            if(guard.guildArrival(w.ocr)&&!(p.afterTrial===true&&p.mode==='flight'&&p.stationary===true))throw Error('Guild landing permits observation-only drift');
            p.usedAt=Date.now();var saved=JSON.stringify(p);if(!file.writeTextSync('act-two-exam-request.json',saved)||file.readTextSync('act-two-exam-request.json')!==saved)throw new Error('Exam plan consumption failed');
            var fastCaptures=[];
            async function runFastTakeoff(recover,flightKey,flightMs,stationary,fastPlan){
                        var launch=eval(file.readTextSync('act-two-exam-launch.js')+'\nActTwoExamLaunch;'),forwardEvent=null,courseVerified=false;
                        function releaseLaunch(){try{keyUp('VK_SPACE');}finally{release();if(forwardEvent){forwardEvent.finishedAt=Date.now();forwardEvent=null;}}}
                        return launch[fastPlan?'segment':flightKey==='COURSE'?'course':flightKey?'fly':recover?'recover':'run']({now:Date.now,check:function(){checkStop();ready();},sleep:sleep,release:releaseLaunch,
                            forwardDown:function(){checkStop();ready();release();if(flightKey==='HOVER')return;held=flightKey==='COURSE'?'VK_W':flightKey||'VK_W';forwardEvent={type:'key',key:held,startedAt:Date.now(),frameId:current.frameId,examLaunch:true};events.push(forwardEvent);keyDown(held);},
                            look:async function(dx,dy){checkStop();ready();events.push({type:'examCourseLook',dx:dx,dy:dy,startedAt:Date.now()});moveMouseBy(dx,dy);},
                            pressSpace:async function(){checkStop();ready();var e={type:'key',key:'VK_SPACE',durationMs:60,startedAt:Date.now(),frameId:current.frameId,examLaunch:true};events.push(e);try{keyDown('VK_SPACE');await sleep(60);checkStop();ready();}finally{keyUp('VK_SPACE');e.finishedAt=Date.now();}},
                            sample:async function(){
                                checkStop();ready();var began=Date.now(),img=captureGameRegion();
                                try{
                                    if(Number(img.width)!==1920||Number(img.height)!==1080)return{valid:false};
                                    var rows=readRows(img,1550,975,350,85),v={valid:true,groundControls:rows.some(function(r){return r.text==='E'||r.text==='Q';}),climbing:rows.some(function(r){return r.text==='X';}),space:rows.some(function(r){return r.text==='Space'&&r.x>=1600&&r.y>=980;})&&!rows.some(function(r){return ['E','Q','X'].indexOf(r.text)>=0;}),rows:rows,capturedAt:began};
                                    if(flightKey==='COURSE'||fastPlan){
                                        v.health=actOneHealth(readHealth(img,[]).rows);v.marker=readMarker(img);v.distance=null;
                                        if(v.marker){var dc=guard.distanceCrop(v.marker);v.distanceRows=dc?readRows(img,dc.x,dc.y,dc.width,dc.height):[];v.distance=guard.distance(v.distanceRows);if(v.distance===null){v.distanceRows=scaledRows(img,Math.round(v.marker.x-55),Math.round(v.marker.y+12),110,65);v.distance=guard.distance(v.distanceRows);}}
                                        if(!courseVerified){v.header=readRows(img,50,235,700,p.afterTrial?150:100).concat(readRows(img,850,25,250,70),actOneMergeControlCropRows([],scaledRows(img,1660,1040,240,40),1660,1040));v.valid=guard.fastState(v,v.header,p.afterTrial===true);courseVerified=v.valid;}
                                    }
                                    v.elapsedMs=Date.now()-began;return v;
                                }finally{if(recover)fastCaptures.push(img);else if(flightKey==='COURSE'||fastPlan){if(fastCaptures.length)dispose(fastCaptures.pop());fastCaptures.push(img);}else dispose(img);}
                            },
                            pause:async function(){checkStop();ready();await boundedKey('VK_B',60,current.frameId);await sleep(450);}},fastPlan|| (flightKey==='COURSE'?{dx:p.dx,dy:p.dy}:flightKey?flightMs:stationary));
                    }
                        try{
                checkStop();ready();attempted=true;await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(p.mode==='open'?250:450);
                if(p.mode==='course'){
                    result={status:'stopped',questComplete:false,mode:'course',course:await runFastTakeoff(false,'COURSE',8000)};result.reason=result.course.reason;
                    current=await observe();var courseDone=await finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,null);
                    if(fastCaptures.length){var coursePath='observations/'+request.session+'/frame-'+String(240000000+initial.frameId)+'.png';file.writeImageSync(coursePath,fastCaptures[0].srcMat);result.fastImagePath=coursePath;}
                    return courseDone;
                }
                if(p.mode==='flight'&&p.holds>0){
                    result={status:'stopped',questComplete:false,mode:'flight',flight:await runFastTakeoff(false,p.stationary?'HOVER':p.left?'VK_A':p.backward?'VK_S':'VK_W',p.holds*600,false,p)};result.reason=result.flight.reason;
                    current=await observe();var segmentDone=await finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,null);
                    if(fastCaptures.length){var segmentPath='observations/'+request.session+'/frame-'+String(240000000+initial.frameId)+'.png';file.writeImageSync(segmentPath,fastCaptures[0].srcMat);result.fastImagePath=segmentPath;}
                    return segmentDone;
                }
                if(p.mode==='open'){
                    result={status:'stopped',questComplete:false,mode:'open',deployment:await runFastTakeoff(true)};
                    current=await observe();result.fieldFrameId=current.frameId;result.reason=result.deployment.opened?'Glider controls verified by fast recovery':'Recovery unverified; immediate pause requested';
                    var recovered=await finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,null);result.fastImages=[];for(var fi=0;fi<fastCaptures.length;fi++){var fp='observations/'+request.session+'/frame-'+String(230000000+initial.frameId*10+fi)+'.png';file.writeImageSync(fp,fastCaptures[fi].srcMat);result.fastImages.push(fp);}return recovered;
                }
                current=await observe();
                for(var poll=0;poll<3&&!guard.state(current,Date.now(),request.session);poll++){await sleep(150);current=await observe();}
                result=await guard.run(current,p,{now:Date.now,check:function(){checkStop();ready();},sleep:sleep,release:release,
                    course:async function(){return runFastTakeoff(false,'COURSE',8000);},
                    fly:async function(key,ms){return runFastTakeoff(false,key,ms);},
                    launch:async function(stationary){return runFastTakeoff(false,null,null,stationary);},
                    key:async function(k,ms,o){checkStop();ready();await boundedKey(k,ms,o.frameId);},
                    look:async function(dx,dy,o){checkStop();ready();events.push({type:'actTwoExamLook',dx:dx,dy:dy,frameId:o.frameId,startedAt:Date.now()});moveMouseBy(dx,dy);}},observe);
            }catch(e){error=String(e.message||e);result.reason=error;}finally{release();for(var fd=0;fd<fastCaptures.length;fd++)dispose(fastCaptures[fd]);}
            if(result.modalInspection&&lastObservation&&guard.recoveryTarget(lastObservation,Date.now(),request.session)){result.menuHeld='Challenge recovery inspection';result.frameId=lastObservation.frameId;return result;}
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error);
        },
        actTwoHideoutExitConfirmTarget:function(o){
            if(!o||o.session!==request.session||Date.now()-o.timestamp>1000||Date.now()<o.timestamp)return null;
            var r=o.ocr||[],one=function(t,x0,x1,y0,y1){return r.filter(x=>x.text===t&&x.x>=x0&&x.x<=x1&&x.y>=y0&&x.y<=y1);};
            if(one('Hint',880,950,250,310).length!==1||one('Leave Domain?',800,870,470,530).length!==1||one('Cancel',700,760,710,780).length!==1||!r.some(x=>/^UID:\s*693306810$/.test(x.text)&&x.x>1600&&x.y>1030))return null;
            var c=one('Confirm',1080,1150,710,780);return c.length===1?{x:Math.round(c[0].x+c[0].width/2),y:Math.round(c[0].y+c[0].height/2)}:null;
        },
        runActTwoHideoutExitConfirm:async function(initial,observe){
            var t=this.actTwoHideoutExitConfirmTarget(initial);if(!['actTwoRecover','actTwoHideoutExitInspect'].includes(request.step)||!t)throw Error('Fresh exact Leave Domain confirmation required');
            var e={type:'hideoutExitConfirm',frameId:initial.frameId,startedAt:Date.now()};events.push(e);
            try{checkStop();ready();await actOneAccountUiClick({checkStop:checkStop,ready:ready,move:moveMouseTo,down:leftButtonDown,up:leftButtonUp,sleep:sleep},t);await sleep(1000);var o=await observe();if(this.actTwoHideoutExitConfirmTarget(o))return {status:'stopped',step:request.step,exitAttempted:true,pauseVerified:false,frameId:o.frameId,reason:'Exit confirmation unchanged after one held click; no retry or pause loop'};for(var i=0;i<10&&!o.hud.world&&!o.hud.dialogueReady;i++){await sleep(500);o=await observe();}e.finishedAt=Date.now();
                return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,{status:'completed',step:request.step,exitAttempted:true,fieldFrameId:o.frameId},null);
            }finally{release();}
        },
        runActTwoHideoutExit:async function(initial,observe){
            var g=eval(file.readTextSync('act-two-hideout-aerial.js')+'\nActTwoHideoutAerial;'),gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;'),o=initial;
            if(request.step!=='actTwoHideoutExitInspect'||!gate(initial,Date.now(),request.session))throw Error('Fresh inventory required for hideout exit inspection');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!reports.some(r=>r.session===request.session&&r.status==='completed'&&r.details&&r.details.inputEvents&&r.details.inputEvents.some(e=>e.type==='actTwoHideoutTutorial'&&e.label==='Gliding bomb attack tutorial')))throw Error('Completed hideout tutorial provenance required');
            var result={status:'stopped',step:request.step,exitAttempted:false},error=null;
            try{checkStop();ready();await boundedKey('VK_ESCAPE',60,o.frameId);await sleep(600);o=await observe();for(var i=0;i<2&&!g.state(o,Date.now(),request.session,1);i++){await sleep(150);o=await observe();}
                if(!g.state(o,Date.now(),request.session,1))throw Error('Fresh special domain HUD required for exit inspection');
                checkStop();ready();await boundedKey('VK_ESCAPE',60,o.frameId);await sleep(600);o=await observe();if(this.actTwoHideoutExitConfirmTarget(o))return this.runActTwoHideoutExitConfirm(o,observe);var proof=actOneLocalPauseProof(o,Date.now(),request.session);
                if(proof&&proof.kind==='domain'){result.pauseVerified=true;result.pauseProof=proof;result.frameId=o.frameId;result.reason='Domain exit controls inspected; no exit confirmation sent';return result;}
            }catch(e){error=String(e.message||e);result.reason=error;}finally{release();}
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error);
        },
        runActTwoHideoutAerial:async function(initial,observe){
            var g=eval(file.readTextSync('act-two-hideout-aerial.js')+'\nActTwoHideoutAerial;'),gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;'),p=JSON.parse(file.readTextSync('act-two-hideout-aerial-request.json')),result={status:'stopped'},error=null;
            if(request.step!=='actTwoHideoutAerial'||!gate(initial,Date.now(),request.session)||!g.plan(p,request,Date.now()))throw Error('Fresh inventory and reviewed one-use aerial plan required');
            var w=JSON.parse(file.readTextSync('observations/'+request.session+'/frame-'+String(p.witnessFrameId).padStart(4,'0')+'.json'));
            if(!g.state(w,w.timestamp,request.session)||Date.now()-w.timestamp>120000)throw Error('Reviewed special aerial HUD witness required');
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!reports.some(r=>r.session===request.session&&r.status==='completed'&&r.details&&r.details.inputEvents&&r.details.inputEvents.some(e=>e.type==='actTwoHideoutTutorial'&&e.label==='Gliding bomb attack tutorial')))throw Error('Completed hideout aerial tutorial provenance required');
            p.usedAt=Date.now();var saved=JSON.stringify(p);if(!file.writeTextSync('act-two-hideout-aerial-request.json',saved)||file.readTextSync('act-two-hideout-aerial-request.json')!==saved)throw Error('Aerial plan consumption failed');
            var phaseImages=[];function checked(){checkStop();ready();}
            function fastSample(){checked();var at=Date.now(),img=captureGameRegion();try{var hp=actOneHealth(readHealth(img,[]).rows),matches={};for(var kind of ['flight','jump']){var mat=file.readImageMatSync('assets/hideout-'+kind+'-control.png'),ro=null,found=null;try{ro=RecognitionObject.TemplateMatch(mat,1650,945,210,80);ro.threshold=.85;ro.use3Channels=false;found=img.findMulti(ro);matches[kind]=found.count>0;}finally{if(found){for(var i=0;i<found.count;i++)dispose(found[i]);dispose(found);}if(ro)dispose(ro.templateImageGreyMat);dispose(mat);}}var v={capturedAt:at,elapsedMs:Date.now()-at,health:hp,flying:matches.flight,jumping:matches.jump,valid:Date.now()-at<=800&&Number(img.width)===1920&&Number(img.height)===1080&&hp&&hp.max===2764&&hp.current>=2488&&hp.current<=2764&&(matches.flight!==matches.jump)};phaseImages.push({label:matches.flight?'flight-control':matches.jump?'jump-control':'unknown-control',at:at,image:img});img=null;return v;}finally{dispose(img);}}

            try{checked();await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(350);var current=await observe();
                for(var fade=0;fade<2&&!g.state(current,Date.now(),request.session);fade++){await sleep(150);current=await observe();}
                if(!g.state(current,Date.now(),request.session))throw Error('Fresh special aerial HUD lost');
                result=await g.run(p,{check:checked,sleep:sleep,release:release,key:async(k,ms)=>{checked();await boundedKey(k,ms,current.frameId);},look:async(dx,dy)=>{checked();events.push({type:'hideoutAerialLook',dx:dx,dy:dy,frameId:current.frameId,startedAt:Date.now()});moveMouseBy(dx,dy);},
                    sample:fastSample,space:async()=>{checked();await boundedKey('VK_SPACE',60,current.frameId);},pause:async()=>{checked();await boundedKey('VK_B',60,current.frameId);await sleep(500);},
                    bomb:async()=>{var proof=fastSample();if(!proof.valid||!proof.flying)throw Error('Fresh positive flight control required before reviewed bomb');var e={type:'hideoutAerialBomb',frameId:current.frameId,startedAt:Date.now()};events.push(e);try{checked();leftButtonDown();await sleep(60);checked();}finally{leftButtonUp();e.finishedAt=Date.now();}}});
                result.beforeActionFieldFrameId=current.frameId;current=await observe();result.fieldFrameId=g.fieldFrame(current,request.session);result.status='stopped';result.reason='Single reviewed aerial action ended; inspect body and effect';
            }catch(e){error=String(e.message||e);result=e.aerialResult||result;result.reason=error;}finally{release();}
            try{var finished=await finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error,current&&Date.now()-current.timestamp<=1000?current:null);finished.phaseImages=[];for(var pi=0;pi<phaseImages.length;pi++){var fp='observations/'+request.session+'/frame-'+String(250000000+initial.frameId*10+pi)+'.png';if(!file.writeImageSync(fp,phaseImages[pi].image.srcMat))throw Error('Phase capture storage refused');finished.phaseImages.push({path:fp,label:phaseImages[pi].label,capturedAt:phaseImages[pi].at});}return finished;}finally{for(var pi=0;pi<phaseImages.length;pi++)dispose(phaseImages[pi].image);}
        },
        actTwoHideoutTutorialReady:function(o){return !!eval(file.readTextSync('act-two-hideout-entry.js')+'\nActTwoHideoutEntry;').tutorialTarget(o,Date.now(),request.session);},
        runActTwoHideoutTutorial:async function(initial,observe){
            var guard=eval(file.readTextSync('act-two-hideout-entry.js')+'\nActTwoHideoutEntry;'),target=guard.tutorialTarget(initial,Date.now(),request.session);
            if(request.step!=='actTwoRecover'||!target)throw new Error('Fresh exact Wind Currents tutorial required');
            checkStop();ready();release();var event={type:'actTwoHideoutTutorial',label:target.label,frameId:initial.frameId,startedAt:Date.now()};events.push(event);
            try{await actOneAccountUiClick({checkStop:checkStop,ready:ready,move:moveMouseTo,down:leftButtonDown,up:leftButtonUp,sleep:sleep},target);await sleep(500);var next=await observe();event.finishedAt=Date.now();
                var result={status:'completed',step:request.step,inputs:1,fieldFrameId:next.frameId,reason:'Exact aerial tutorial clicked once; inspect actual controls',pauseVerified:false};
                if(guard.tutorialTarget(next,Date.now(),request.session)){result.status='stopped';result.reason=guard.tutorialTarget(next,Date.now(),request.session).label===target.label?'Tutorial unchanged after one click; no repeated input':'Next aerial tutorial page; inspect before continuing';return result;}
                return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,null);
            }finally{release();}
        },
        actTwoHideoutEntryReady:function(o){return !!eval(file.readTextSync('act-two-hideout-entry.js')+'\nActTwoHideoutEntry;').entryTarget(o,Date.now(),request.session);},
        runActTwoHideoutParty:async function(initial,observe){
            var guard=eval(file.readTextSync('act-two-hideout-entry.js')+'\nActTwoHideoutEntry;'),reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json')),target=guard.partyTarget(initial,Date.now(),request.session,reports);
            if(request.step!=='actTwoHideoutPartyStart'||!target)throw new Error('Fresh verified Raptor party and recent entrance provenance required');
            checkStop();ready();release();var event={type:'actTwoHideoutPartyStart',frameId:initial.frameId,startedAt:Date.now()};events.push(event);
            try{click(target.x,target.y);var next=initial,began=Date.now();do{await sleep(600);next=await observe();if(next.hud.auto||next.hud.dialogueReady||next.hud.choice||next.hud.health)break;}while(Date.now()-began<15000);event.finishedAt=Date.now();
                return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,{status:'completed',step:request.step,inputs:1,fieldFrameId:next.frameId,reason:'Raptor party Start clicked once; inspect domain mechanics'},null);
            }finally{release();}
        },
        runActTwoHideoutEntry:async function(initial,observe,recover){
            var guard=eval(file.readTextSync('act-two-hideout-entry.js')+'\nActTwoHideoutEntry;'),target=guard.entryTarget(initial,Date.now(),request.session);
            if(!target||request.step!==(recover?'actTwoRecover':'actTwoHideoutStart'))throw new Error('Fresh exact Raptor hideout entrance required');
            checkStop();ready();release();var event={type:recover?'actTwoHideoutEntranceRecovery':'actTwoHideoutStart',frameId:initial.frameId,startedAt:Date.now()};events.push(event);
            try{if(recover)await boundedKey('VK_ESCAPE',60,initial.frameId);else click(target.x,target.y);await sleep(800);var next=await observe();event.finishedAt=Date.now();
                var result={status:'completed',step:request.step,inputs:1,frameId:next.frameId,reason:recover?'Entrance closed once; verify independent inventory pause':'Hideout Start clicked once; inspect party or loading',pauseVerified:false};
                if(recover)return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,null);
                return result;
            }finally{release();}
        },
        runActTwoField: async function(initial,observe){
            var gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;'),guard=eval(file.readTextSync('act-two-field.js')+'\nActTwoField;');
            var p=JSON.parse(file.readTextSync('act-two-field-request.json'));
            if(request.step!=='actTwoField'||!gate(initial,Date.now(),request.session)||!guard.plan(p,request,Date.now()))throw new Error('Fresh inventory and one-use reviewed field plan required');
            var witness=JSON.parse(file.readTextSync('observations/'+request.session+'/frame-'+String(p.witnessFrameId).padStart(4,'0')+'.json'));
            delete p.regionWitness;
            if(p.regionMapFrameId){p.regionWitness=JSON.parse(file.readTextSync('observations/'+request.session+'/frame-'+String(p.regionMapFrameId).padStart(4,'0')+'.json'));if(p.regionWitness.frameId!==p.regionMapFrameId||!(guard.regionalMap(p.regionWitness,Date.now(),request.session)||(p.nativeCombat===true||guard.eventReposition(p))&&guard.leyLine(witness)))throw new Error('Fresh regional map witness required');}
            if(witness.session!==request.session||witness.frameId!==p.witnessFrameId||!(p.recoverySwitch===true?guard.switchReady(witness,witness,witness.timestamp,request.session,p.actions[0].key):guard.ready(witness,witness,witness.timestamp,request.session,p.mode==='climb'||p.mode==='releaseClimb',!!p.regionWitness,guard.cameraPlan(p),p.mode==='releaseClimb',p.regionWitness,true,(p.mode==='combat'&&[4,10,12,13,'any'].includes(p.enemyLevel)||guard.eventReposition(p)&&guard.leyLine(witness)),p.climbProbe===true,p.landingReviewed===true)))throw new Error('Original field witness required');
            p.usedAt=Date.now();p.requestId=request.id;var saved=JSON.stringify(p);
            if(!file.writeTextSync('act-two-field-request.json',saved)||file.readTextSync('act-two-field-request.json')!==saved)throw new Error('Field plan consumption failed');
            var current=initial,result=null,error=null;
            function fieldReady(o){return p.recoverySwitch===true?guard.switchReady(o,witness,Date.now(),request.session,p.actions[0].key):guard.ready(o,witness,Date.now(),request.session,p.mode==='climb'||p.mode==='releaseClimb',p.visualPositionReviewed,guard.cameraPlan(p),p.mode==='releaseClimb',p.regionWitness,false,(p.mode==='combat'&&[4,10,12,13,'any'].includes(p.enemyLevel)||guard.eventReposition(p)&&guard.leyLine(witness)),p.climbProbe===true,p.landingReviewed===true);}
            function safe(o){if(!fieldReady(o))throw new Error(guard.failureReason(o,witness,Date.now(),request.session));checkStop();ready();}
            try{
                await boundedKey('VK_ESCAPE',60,initial.frameId);
                for(var poll=0;poll<5;poll++){await sleep(poll===0?800:150);current=await observe();if(fieldReady(current))break;if(!p.recoverySwitch&&guard.failureReason(current,witness,Date.now(),request.session)==='health_below_minimum'){release();if(poll===0&&guard.healthReread(current,witness,p,Date.now(),request.session))continue;throw new Error('health_below_minimum');}if(actTwoFieldEntrySettled(current))break;}
                safe(current);
                result=await guard.run(current,witness,p,{now:Date.now,checkStop:checkStop,sleep:sleep,release:release,
                    nativeCombat:async function(o){
                        safe(o);if(p.nativeCombat!==true||![10,13].includes(p.enemyLevel)||!p.regionWitness||!guard.nativeHealth(p.nativeAvatar,o.hud.health.max)||o.hud.health.current<o.hud.health.max*.7||!(guard.combatTargets(o,p).length||guard.leyLine(witness)))throw new Error('Reviewed Lv13 native combat required');
                        var ng=eval(file.readTextSync('act-two-native-combat.js')+'\nActTwoNativeCombat;');
                        var param=ng.targetingParam(new AutoFightParam(actTwoRegionalCombatStrategy(p.nativeAvatar,o)),false),ev={type:'actTwoRegionalNativeCombat',engine:'AutoFightTask',frameId:o.frameId,startedAt:Date.now()};param.Timeout=6;events.push(ev);
                        try{return await ng.chunk({createCancellation:function(){return dispatcher.GetLinkedCancellationTokenSource();},armDeadline:function(cts,ms){cts.CancelAfter(ms);},run:function(script,token){return dispatcher.RunAutoFightTask(param,token);},release:function(){release();keyUp('VK_E');keyUp('VK_Q');keyUp('VK_3');keyUp('VK_S');keyUp('VK_W');keyUp('VK_SHIFT');leftButtonUp();rightButtonUp();}},function(){checkStop();ready();},{now:Date.now,sleep:sleep,timeoutMs:8000,sampleAfterMs:2500,sample:async function(){var sample=await observe(),hp=sample.hud&&sample.hud.health;if(!sample.hud.groundControls||sample.hud.climbing||!hp||hp.max!==o.hud.health.max||hp.current<hp.max*.5||!actTwoOriginalAccount(sample.ocr||[]))throw new Error('Native ley line sampled health or account changed');}});}
                        finally{ev.finishedAt=Date.now();}
                    },
                    key:async function(k,ms,o){safe(o);await boundedKey(k,ms,o.frameId);},
                    action:async function(a,o){safe(o);if(a.type==='look'){events.push({type:'actTwoFieldLook',dx:a.dx,dy:a.dy,frameId:o.frameId,startedAt:Date.now()});moveMouseBy(a.dx,a.dy);}else await boundedKey(a.key,a.ms,o.frameId);}
                },observe);
            }catch(e){error=String(e&&e.message||e);result=e.fieldResult||result||{status:'stopped'};result.reason=error;}finally{release();}
            if(!error&&eval(file.readTextSync('act-two-hideout-entry.js')+'\nActTwoHideoutEntry;').entryHandoff(lastObservation,Date.now(),request.session)){result.menuHeld='Raptor hideout entrance inspection';result.pauseVerified=false;result.frameId=lastObservation.frameId;return result;}
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result||{status:'stopped',reason:error},error,lastObservation&&lastObservation.hud.world&&Date.now()-lastObservation.timestamp<=1000?lastObservation:null);
        },
        runActTwoWindriseSlime: async function(initial,observe){
            var gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            if(!gate(initial,Date.now(),request.session)||request.step!=='actTwoWindriseSlime')throw new Error('Fresh inventory for witnessed Windrise slime required');
            var current=initial,result={status:'stopped',skills:0,attacks:0},error=null;
            function safe(o){return o&&o.session===request.session&&Date.now()>=o.timestamp&&Date.now()-o.timestamp<=1000&&actTwoOriginalAccount(o.ocr)&&o.map&&Math.hypot(o.map.x+1266.36,o.map.y-1976.31)<8&&o.hud.world&&o.hud.groundControls&&!o.hud.climbing&&!o.hud.auto&&!o.hud.choice&&o.hud.health&&o.hud.health.max===1700&&o.hud.health.current>=1450&&!(o.hud.objectives||[]).length;}
            try{
                await boundedKey('VK_ESCAPE',60,initial.frameId);for(var p=0;p<5;p++){await sleep(150);current=await observe();if(safe(current))break;}
                if(!safe(current))throw new Error('Witnessed slime field changed');
                await boundedKey('VK_E',60,current.frameId);result.skills++;await sleep(450);current=await observe();
                for(var cycle=0;cycle<2;cycle++){
                    if(!safe(current))break;
                    for(var hit=0;hit<3;hit++){if(!safe(current))break;await boundedKey('VK_LBUTTON',60,current.frameId);result.attacks++;await sleep(200);}
                    current=await observe();
                }
                result.fieldFrameId=current.frameId;result.reason='One Cryo skill and at most six melee strikes; inspect encounter';
            }catch(e){error=String(e&&e.message||e);}finally{release();}
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error);
        },
        runActTwoInformantCombat: async function(initial,observe){
            var gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            if(!gate(initial,Date.now(),request.session)||request.step!=='actTwoInformantCombat')throw new Error('Fresh inventory and exact informant combat request required');
            var guard=eval(file.readTextSync('act-two-informant-combat.js')+'\nActTwoInformantCombat;'),current=initial,result=null,error=null;
            try{
                await boundedKey('VK_ESCAPE',60,current.frameId);
                for(var i=0;i<5;i++){await sleep(150);current=await observe();if(guard.ready(current,Date.now(),request.session))break;if(current.hud.world&&current.hud.health&&current.hud.health.current<1190)break;}
                result=await guard.run(current,{now:Date.now,checkStop:checkStop,sleep:sleep,release:release,
                    key:async function(k,ms,o){if(!guard.ready(o,Date.now(),request.session))throw new Error('Combat evidence expired');await boundedKey(k,ms,o.frameId);},
                    turn:async function(dx,o){if(!guard.ready(o,Date.now(),request.session))throw new Error('Combat turn evidence expired');checkStop();ready();events.push({type:'informantCombatTurn',dx:dx,frameId:o.frameId,startedAt:Date.now()});moveMouseBy(dx,0);}
                },observe);
            }catch(e){error=String(e&&e.message||e);}
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error);
        },
        runActTwoOre: async function(initial,observe){
            var guard=eval(file.readTextSync('act-two-ore.js')+'\nActTwoOre;'),p=JSON.parse(file.readTextSync('act-two-ore-request.json'));
            if(!guard.plan(p,request,Date.now()))throw new Error('Fresh reviewed bounded ore plan required');
            p.usedAt=Date.now();p.requestId=request.id;var saved=JSON.stringify(p);
            if(!file.writeTextSync('act-two-ore-request.json',saved)||file.readTextSync('act-two-ore-request.json')!==saved)throw new Error('Ore plan consumption failed');
            return this.runActTwoNavigationWithPause(initial,observe,async function(current){
                var result={status:'completed',actions:0,pickupAttempts:0};
                for(var i=0;i<p.actions.length;i++){
                    if(!guard.ready(current,Date.now(),request.session))throw new Error('Fresh safe ore field required');
                    var a=p.actions[i];
                    for(var burst=0;burst<(a.key==='VK_LBUTTON'?3:1);burst++){
                        if(!guard.ready(current,Date.now(),request.session))throw new Error('Ore action observation expired');
                        await boundedKey(a.key,a.ms,current.frameId);result.actions++;
                        if(a.key==='VK_LBUTTON'&&burst<2)await sleep(220);
                    }
                    await sleep(500);current=await observe();
                    if(guard.ready(current,Date.now(),request.session)&&guard.pickup(current)){
                        await boundedKey('VK_F',60,current.frameId);result.pickupAttempts++;await sleep(500);current=await observe();
                    }
                }
                result.fieldFrameId=current.frameId;result.health=current.hud.health;return result;
            });
        },
        closeActTwoForge: async function(initial){
            var rows=initial.ocr||[];
            function one(t,x0,x1,y0,y1){return rows.filter(function(r){return r.text===t&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1;}).length===1;}
            if(initial.session!==request.session||Date.now()-initial.timestamp>1000||!one('Forge',100,200,15,80)||!one('Materials',100,230,100,180)||!one('Forge Queues (0/2)',400,500,100,180))throw new Error('Fresh idle Forge menu required');
            await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(700);return true;
        },
        runActTwoClueCamera: async function(initial,observe){
            return this.runActTwoNavigationWithPause(initial,observe,async function(current){
                var h=current.hud,m=current.map,up=request.step==='actTwoWindmillLookUp',anchor=up?[-841.795,2215.524]:[-854.314,2211.413];
                if(['actTwoClueCamera','actTwoWindmillLookUp'].indexOf(request.step)<0||Math.hypot(m.x-anchor[0],m.y-anchor[1])>3||!h.health||h.health.current!==1700||
                    (h.objectives||[]).slice(0,2).join('').replace(/\s/g,'')!=='Solvethemystery(GotoKaeyaattheKnightsofFavoniusHQforahint)')throw new Error('Witnessed windmill camera position required');
                for(var n=0;n<3;n++){checkStop();ready();events.push({type:'actTwoClueCamera',dy:up?-500:500,frameId:current.frameId,startedAt:Date.now()});moveMouseBy(0,up?-500:500);await sleep(180);}
                await sleep(350);var after=await observe();return {status:'completed',step:request.step,fieldFrameId:after.frameId};
            });
        },
        runActTwoMapClose: async function(initial,observe){
            var proof=actOneLocalPauseProof(initial,Date.now(),request.session);
            var zoomedMap=initial&&initial.session===request.session&&Date.now()>=initial.timestamp&&Date.now()-initial.timestamp<=1000&&initial.hud.bigMap&&!initial.hud.world&&!initial.hud.dialogueReady&&
                ['Mondstadt','Cider Lake','Windrise'].every(function(name){return (initial.ocr||[]).filter(function(r){return r.text===name;}).length===1;});
            var riftPanel=initial&&initial.session===request.session&&Date.now()>=initial.timestamp&&Date.now()-initial.timestamp<=1000&&!initial.hud.world&&!initial.hud.dialogueReady&&[['Forsaken Rift',1480,15],['Domain unlocks at Adventure Rank 25',1463,868],['Navigate',1620,987]].every(function(a){return (initial.ocr||[]).some(function(r){return r.text===a[0]&&Math.abs(r.x-a[1])<15&&Math.abs(r.y-a[2])<15;});});
            var artifactPanel=initial&&initial.session===request.session&&Date.now()>=initial.timestamp&&Date.now()-initial.timestamp<=1000&&!initial.hud.world&&!initial.hud.dialogueReady&&[['Thorny Crown of the',1485,0],['Mountain Wind',1485,33],['Navigate',1617,983]].every(function(a){return (initial.ocr||[]).some(function(r){return r.text===a[0]&&Math.abs(r.x-a[1])<15&&Math.abs(r.y-a[2])<15;});});
            if((!proof||proof.kind!=='map')&&!zoomedMap&&!riftPanel&&!artifactPanel)throw new Error('Fresh verified map required');
            await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(500);
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,{status:'completed',step:request.step},null);
        },
        runActTwoTownRecovery: async function(initial,observe){
            var gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            if(!gate(initial,Date.now(),request.session))throw new Error('Fresh inventory required for town pillar recovery');
            var guard=eval(file.readTextSync('act-two-town-recovery.js')+'\nActTwoTownRecovery;'),current=initial,result={status:'stopped',step:request.step,dropSent:false},error=null;
            var climb=request.step==='actTwoTownClimb',rail=request.step==='actTwoTownRail',ready=rail?guard.railReady:climb?guard.wallReady:guard.ready;
            try{
                await boundedKey('VK_ESCAPE',60,current.frameId);
                for(var i=0;i<5;i++){await sleep(200);current=await observe();if(ready(current,Date.now(),request.session))break;}
                if(!ready(current,Date.now(),request.session))throw new Error('Exact witnessed short climb required');
                if(rail){await boundedKey('VK_SPACE',60,current.frameId);await boundedKey('VK_W',600);result.railJumpSent=true;await sleep(750);current=await observe();}
                else if(climb){
                    if(!current.hud.climbing)throw new Error('Witnessed wall climb must already be active');
                    result.climbHolds=0;
                    for(var hold=0;hold<6&&current.hud.climbing;hold++){
                        if(!ready(current,Date.now(),request.session)){await sleep(150);current=await observe();}
                        if(!ready(current,Date.now(),request.session))throw new Error('Wall climb evidence changed');
                        await boundedKey('VK_W',600,current.frameId);result.climbHolds++;await sleep(250);current=await observe();
                    }
                }else{await boundedKey('VK_X',60,current.frameId);result.dropSent=true;await sleep(800);current=await observe();}
                // E/Q controls also appear during a fall; they do not prove a landing.
                result.groundControlsVisible=current.hud.groundControls===true&&!current.hud.climbing;result.grounded=null;result.fieldFrameId=current.frameId;result.health=current.hud.health;result.status='stopped';
            }catch(e){error=String(e&&e.message||e);result.reason=error;}
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error);
        },
        runActTwoDaytime: async function(initial,observe){
            var inventory=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;'),guard=eval(file.readTextSync('act-two-clock.js')+'\nActTwoClock;');
            if(request.step!=='actTwoDaytime'||!inventory(initial,Date.now(),request.session))throw new Error('Fresh inventory required for daytime NPC check');
            var current=initial,result={status:'stopped',timeSetAttempted:false},error=null;
            try{
                await boundedKey('VK_ESCAPE',60,initial.frameId);
                for(var poll=0;poll<3;poll++){await sleep(150);current=await observe();if(guard.ready(current,Date.now(),request.session))break;}
                if(!guard.ready(current,Date.now(),request.session))throw new Error('Fresh safe quest-giver terrace required; ageMs='+String(Date.now()-current.timestamp));
                checkStop();ready();result.timeSetAttempted=true;
                events.push({type:'actTwoDaytime',hour:8,minute:0,frameId:current.frameId,startedAt:Date.now()});
                await genshin.setTime(8,0,false);release();await sleep(600);current=await observe();
                result.fieldFrameId=current.frameId;result.reason='Native time adjustment attempted once; verify NPC and daylight';
            }catch(e){error=String(e&&e.message||e);result.reason=error;}finally{release();}
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error);
        },
        runActTwoMenu: async function(initial,observe){
            var key=request.step==='actTwoHandbook'?'VK_F1':request.step==='actTwoCharacter'?'VK_C':request.step==='actTwoWorldMap'?'VK_M':request.step==='actTwoJournalOpen'?'VK_J':request.step==='actTwoAccountMenu'?'VK_ESCAPE':null;
            var gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            var priorProof=actOneLocalPauseProof(initial,Date.now(),request.session);
            if(!key||!(gate(initial,Date.now(),request.session)||request.step==='actTwoJournalOpen'&&priorProof&&priorProof.kind==='menu'))throw new Error('Fresh inventory or reviewed menu required before Act II menu');
            var current=initial,error=null;
            try{
                await boundedKey('VK_ESCAPE',60,initial.frameId);
                function climbingMap(o){return request.step==='actTwoWorldMap'&&o.hud.world&&o.hud.climbing&&o.map&&Math.hypot(o.map.x+846,o.map.y-2214)<25&&o.hud.health&&o.hud.health.current===1700&&o.hud.health.max===1700&&
                    (o.hud.objectives||[]).slice(0,2).join('').replace(/[^A-Za-z]/g,'')==='SolvethemysteryGotoKaeyaattheKnightsofFavoniusHQforahint';}
                function examMapEscape(o){var h=o&&o.hud,m=o&&o.map;return request.step==='actTwoWorldMap'&&h&&h.world&&h.climbing&&m&&m.map==='Teyvat'&&m.x>=-1500&&m.x<=-1100&&m.y>=1600&&m.y<=1950&&h.health&&h.health.current===2313&&h.health.max===2313&&(h.objectives||[]).some(t=>String(t).replace(/\s/g,'')==='Gototheexampoint');}
                function windriseMapEscape(o){var h=o&&o.hud,m=o&&o.map;return request.step==='actTwoWorldMap'&&h&&h.world&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.bigMap&&!h.journal&&m&&m.map==='Teyvat'&&Math.hypot(m.x+1243.71,m.y-1867.27)<4&&h.health&&h.health.max===1829&&h.health.current>=1281&&!(h.objectives||[]).some(function(t){return String(t).replace(/[^A-Za-z]/g,'').length>5;});}
                function northShoreMapEscape(o){var h=o&&o.hud,m=o&&o.map;return request.step==='actTwoWorldMap'&&h&&h.world&&!h.auto&&!h.dialogueReady&&!h.choice&&!h.bigMap&&!h.journal&&m&&m.map==='Teyvat'&&Math.hypot(m.x+724.97,m.y-2398.16)<5&&h.health&&h.health.max===2313&&h.health.current===2313&&!(h.objectives||[]).some(function(t){return String(t).replace(/[^A-Za-z]/g,'').length>5;});}
                for(var i=0;i<5;i++){await sleep(200);current=await observe();if(current.hud.world&&current.hud.groundControls||climbingMap(current)||windriseMapEscape(current)||examMapEscape(current)||northShoreMapEscape(current)||request.step==='actTwoWorldMap'&&actTwoHideoutClimbMap(current,Date.now(),request.session))break;}
                if((!current.hud.world&&!(request.step==='actTwoWorldMap'&&actTwoHideoutClimbMap(current,Date.now(),request.session)))||!(current.hud.groundControls||climbingMap(current)||windriseMapEscape(current)||examMapEscape(current)||northShoreMapEscape(current)||request.step==='actTwoWorldMap'&&actTwoHideoutClimbMap(current,Date.now(),request.session))||((current.hud.enemyBars||[]).length&&!(request.step==='actTwoCharacter'&&current.hud.health&&current.hud.health.current>0&&(current.hud.objectives||[]).some(t=>/^Defeatallopponents[0-6]\/7$/.test(String(t).replace(/\s/g,'')))))||
                    !(current.ocr||[]).some(function(r){return /^(?:UID)?[: ]*693306810$/.test(String(r.text||'').trim())&&r.x>1600&&r.y>1020;}))
                    throw new Error('Fresh original account in safe field required');
                await boundedKey(key,60,current.frameId);await sleep(750);current=await observe();
                if(!current.hud.world)return {status:'completed',step:request.step,menuOpened:true,pauseVerified:false,frameId:current.frameId};
                error='Menu did not open';
            }catch(e){error=String(e&&e.message||e);}
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,{status:'stopped',reason:error},error);
        },
        runActTwoNativeRoute: async function(initial,observe){
            var began=Date.now(),nativeStart=null,event=null,current=initial,attempted=false,error=null,result={status:'stopped',step:request.step,questComplete:false};
            try{
                var routeGuard=eval(file.readTextSync('act-two-native-route.js')+'\nActTwoNativeRoute;');
                var p=JSON.parse(file.readTextSync('act-two-native-route-plan.json'));
                var gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
                if(request.step!=='actTwoNativeRoute'||!gate(initial,Date.now(),request.session)||!routeGuard.plan(p,request,Date.now()))throw new Error('Fresh reviewed bounded native route required');
                var witness=JSON.parse(file.readTextSync('observations/'+request.session+'/frame-'+String(p.witnessFrameId).padStart(4,'0')+'.json'));
                if(!actTwoOriginalAccount(witness.ocr)||!routeGuard.field(witness,witness,witness.timestamp,request.session,p.region)||Math.hypot(p.route.positions[0].x-witness.map.x,p.route.positions[0].y-witness.map.y)>30)throw new Error('Safe nearby town route witness required');
                if(typeof pathingScript.RunForQuestBounded!=='function')throw new Error('Bounded native pathing runtime required');
                p.usedAt=Date.now();var saved=JSON.stringify(p);if(!file.writeTextSync('act-two-native-route-plan.json',saved)||file.readTextSync('act-two-native-route-plan.json')!==saved)throw new Error('Native route consumption failed');
                attempted=true;await boundedKey('VK_ESCAPE',60,current.frameId);
                function readyField(o){return actTwoOriginalAccount(o.ocr)&&routeGuard.field(o,witness,Date.now(),request.session,p.region);}
                for(var poll=0;poll<3;poll++){await sleep(poll?200:450);current=await observe();if(readyField(current))break;}
                if(!readyField(current))throw new Error('Fresh full-health grounded town field required');
                nativeStart=current;event={type:'actTwoNativeRoute',frameId:current.frameId,timeoutMs:p.timeoutMs,startedAt:Date.now(),rootReviewed:true};events.push(event);
                try{await routeGuard.run({createCancellation:function(){return dispatcher.GetLinkedCancellationTokenSource();},run:function(json,timeout,token){return pathingScript.RunForQuestBounded(json,timeout,token);}},function(){checkStop();ready();},sleep,p.route,p.timeoutMs);}
                finally{event.finishedAt=Date.now();}
                await sleep(300);current=await observe();result.fieldFrameId=current.frameId;
            }catch(e){error=String(e&&e.message||e);result.reason=error;}finally{release();}
            if(attempted){
                var finished=await finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error);
                if(nativeStart&&event&&finished.pauseProof){
                    var endFrame=JSON.parse(file.readTextSync('observations/'+request.session+'/frame-'+String(finished.pauseProof.sourceFrameId).padStart(4,'0')+'.json'));
                    finished.travel=routeGuard.telemetry(nativeStart,endFrame,p.region,event.finishedAt-event.startedAt,Date.now()-began);
                }
                return finished;
            }
            if(error)throw new Error(error);return result;
        },
        runActTwoVisual: async function(initial,observe){
            var current=initial,attempted=false,error=null,result={status:'stopped',step:request.step,actions:0,questComplete:false};
            try{
                var guard=eval(file.readTextSync('act-two-visual.js')+'\nActTwoVisual;'),p=JSON.parse(file.readTextSync('act-two-visual-plan.json'));
                var gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
                if(request.step!=='actTwoVisual'||!gate(initial,Date.now(),request.session)||!guard.plan(p,request,Date.now()))throw new Error('Fresh one-use reviewed visual plan required');
                var witness=JSON.parse(file.readTextSync('observations/'+request.session+'/frame-'+String(p.witnessFrameId).padStart(4,'0')+'.json'));
                if(witness.session!==request.session||!actTwoOriginalAccount(witness.ocr)||!guard.field(witness,witness,witness.timestamp,request.session,p.mode))throw new Error('Matching safe windmill witness required');
                p.usedAt=Date.now();var saved=JSON.stringify(p);if(!file.writeTextSync('act-two-visual-plan.json',saved)||file.readTextSync('act-two-visual-plan.json')!==saved)throw new Error('Visual plan consumption failed');
                attempted=true;await boundedKey('VK_ESCAPE',60,current.frameId);
                function safe(o){return actTwoOriginalAccount(o.ocr||[])&&guard.field(o,witness,Date.now(),request.session,p.mode);}
                for(var poll=0;poll<5;poll++){await sleep(200);current=await observe();if(safe(current))break;}
                for(var i=0;i<p.actions.length;i++){
                    checkStop();ready();if(!safe(current))throw new Error('Visual plan field evidence changed');
                    var a=p.actions[i];events.push({type:'actTwoVisual',action:a,witnessFrameId:witness.frameId,frameId:current.frameId,startedAt:Date.now(),rootReviewed:true});
                    if(a.type==='key')await boundedKey(a.key,a.ms,current.frameId);else moveMouseBy(a.dx,a.dy);
                    result.actions++;await sleep(300);current=await observe();
                }
                result.fieldFrameId=current.frameId;
            }catch(e){error=String(e&&e.message||e);result.reason=error;}finally{release();}
            if(attempted)return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,error);
            if(error)throw new Error(error);return result;
        },
        runActTwoIndoorMove: async function(initial,observe){
            var current=initial,attempted=false,error=null,result={status:'stopped',step:request.step,moves:0,questComplete:false};
            function safe(o){return actTwoIndoorSafe(o,Date.now(),request.session);}
            try{
                var p=JSON.parse(file.readTextSync('act-two-indoor-move.json')),gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
                if(!p||!/^mission-[a-f0-9]{32}$/.test(p.entryReceiptId||''))throw new Error('Owned entry receipt identifier required');
                var entry=JSON.parse(file.readTextSync('receipts/'+request.session+'/'+p.entryReceiptId+'.json'));
                if(!gate(initial,Date.now(),request.session)||!p||p.session!==request.session||p.frameId!==request.expectedFrameId||p.usedAt||p.reviewed!==true||!Number.isFinite(p.createdAt)||Date.now()-p.createdAt>120000||Date.now()<p.createdAt||!Array.isArray(p.actions)||p.actions.length<1||p.actions.length>5||
                    p.actions.some(function(a){return ['VK_W','VK_A','VK_S','VK_D','VK_F'].indexOf(a.key)<0||!Number.isInteger(a.ms)||a.ms<30||a.ms>800||a.key==='VK_F'&&a.ms!==60;})||
                    entry.session!==request.session||entry.details.result.step!=='actTwoHqEnter'||!entry.details.result.entryAttempted||!entry.details.result.pauseVerified)throw new Error('Fresh reviewed indoor plan and verified HQ entry required');
                p.usedAt=Date.now();var saved=JSON.stringify(p);if(!file.writeTextSync('act-two-indoor-move.json',saved)||file.readTextSync('act-two-indoor-move.json')!==saved)throw new Error('Indoor plan consumption failed');
                attempted=true;await boundedKey('VK_ESCAPE',60,current.frameId);await sleep(350);current=await observe();
                for(var poll=0;poll<3&&!safe(current);poll++){await sleep(200);current=await observe();}
                for(var i=0;i<p.actions.length;i++){
                    checkStop();ready();if(!safe(current))throw new Error('Indoor objective, account, health or controls changed');
                    var a=p.actions[i],rows=current.ocr||[];
                    if(a.key==='VK_F'){
                        var interaction=eval(file.readTextSync('act-two-interaction.js')+'\nActTwoInteraction;'),selection=interaction.selection(rows,'Kaeya');
                        if(selection==='next'){
                            events.push({type:'actTwoSelectKaeya',scroll:-1,frameId:current.frameId,startedAt:Date.now()});verticalScroll(-1);await sleep(250);current=await observe();
                            if(!safe(current))throw new Error('Unsafe frame after interaction selection');
                            selection=interaction.selection(current.ocr,'Kaeya');
                        }
                        if(selection!=='selected')throw new Error('Kaeya must align with the selected F prompt');
                    }
                    await boundedKey(a.key,a.ms,current.frameId);result.moves++;await sleep(a.key==='VK_F'?800:250);current=await observe();
                    if(current.hud.dialogueReady||current.hud.choice)break;
                }
                result.reason='Reviewed indoor input budget completed';
            }catch(e){error=String(e&&e.message||e);result.reason=error;}
            result.fieldFrameId=current.frameId;
            if(current.hud.dialogueReady||current.hud.choice){result.conversationActive=true;result.pauseVerified=false;return result;}
            if(attempted)return finishWithLocalPause(loadLocalPause(),this,initial,observe,current.frameId,result,error);
            return result;
        },
        runActTwoToast: async function(initial,observe){
            checkStop();ready();var helper=eval(file.readTextSync('act-two-toast.js')+'\nActTwoToast;'),target=helper.target(initial,Date.now());
            if(request.step!=='actTwoToast'||initial.session!==request.session||!actTwoOriginalAccount(initial.ocr)||!target)throw new Error('Fresh exact Fisherman toast stage required');
            events.push({type:'actTwoToast',action:target.action,cost:target.cost||null,frameId:initial.frameId,startedAt:Date.now()});click(target.x,target.y);await sleep(650);var after=await observe(),result={status:'stopped',action:target.action,frameId:after.frameId,questComplete:false};
            if(target.action==='close'){for(var poll=0;poll<5&&!after.hud.world&&!after.hud.dialogueReady&&!after.hud.choice;poll++){await sleep(300);after=await observe();}return this.finishActTwoDialogue(initial,observe,result);}return result;
        },
        runActTwoStatue: async function(initial,observe){
            checkStop();ready();
            if(!initial||initial.session!==request.session||!Number.isFinite(initial.timestamp)||Date.now()<initial.timestamp||Date.now()-initial.timestamp>1000||!actTwoOriginalAccount(initial.ocr)||initial.hud.world||initial.hud.health)throw new Error('Fresh original-account Statue dialogue required');
            var rows=initial.ocr||[];
            function one(text,x1,x2,y1,y2){return rows.filter(function(r){return r.text.trim()===text&&r.x>=x1&&r.x<=x2&&r.y>=y1&&r.y<=y2;}).length===1;}
            if(one('Worship Statue',1300,1500,170,230)&&one('Anemoculus 0/2',1700,1900,170,230)&&one('Current Stamina Limit: 107/240',1400,1800,320,370)&&one('Required Anemoculus',1450,1750,820,880)&&one('Owned',1400,1530,870,910)&&one('2',1400,1530,900,950)&&one('Offer All',1650,1800,980,1040)){
                events.push({type:'actTwoStatueOffer',cost:{anemoculus:2},frameId:initial.frameId,startedAt:Date.now()});click(1740,1018);await sleep(900);var offeredTwo=await observe();return {status:'stopped',action:'offerTwo',frameId:offeredTwo.frameId,offeringAttempted:true,questComplete:false};
            }
            if((one('Anemoculus 0/2',1700,1900,170,230)&&one('Current Stamina Limit: 107/240',1400,1800,320,370)||one('Anemoculus 0/4',1700,1900,170,230)&&one('Current Stamina Limit: 114/240',1400,1800,320,370)&&one('0',1400,1530,900,950))&&one('Required Anemoculus',1450,1750,820,880)){
                await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(700);var closed=await observe();return this.finishActTwoDialogue(initial,observe,{status:'completed',action:'closeUpgradedStatue',frameId:closed.frameId,questComplete:false});
            }
            if(one('Worship Statue',1300,1500,170,230)&&one('Anemoculus 0/1',1700,1900,170,230)&&one("Statue's Rewards",1450,1700,230,290)&&one('Required Anemoculus',1450,1700,820,880)&&one('Owned',1400,1530,870,910)&&one('1',1400,1530,910,950)&&one('Offer',1380,1530,980,1040)){
                events.push({type:'actTwoStatueOffer',cost:{anemoculus:1},frameId:initial.frameId,startedAt:Date.now()});click(1468,1018);await sleep(900);var offered=await observe();return {status:'stopped',action:'offerOne',frameId:offered.frameId,offeringAttempted:true,questComplete:false};
            }
            if(request.step==='actTwoStatueHeal'){
                if(rows.some(function(r){return /^Statue.s Blessing$/.test(r.text.trim())&&r.x>1400&&r.y<100;})){
                    var healed=initial;for(var healPass=0;healPass<3;healPass++){for(var healPoll=0;healPoll<4&&!healed.ocr.some(function(r){return /Click on the character portrait to restore HP/.test(r.text);});healPoll++){await sleep(250);healed=await observe();}await this.healTravelerAtStatue();await sleep(500);healed=await observe();}
                    await boundedKey('VK_ESCAPE',60,healed.frameId);await sleep(500);var closedHeal=await observe();
                    for(var settle=0;settle<4&&!closedHeal.hud.world;settle++){await sleep(250);closedHeal=await observe();}
                    return this.finishActTwoDialogue(initial,observe,{status:'stopped',action:'healStarterParty',healingConfirmed:actOneStatueHealingVerified(closedHeal,Date.now(),request.session),health:closedHeal.hud.health,fieldFrameId:closedHeal.frameId});
                }
                if(rows.some(function(r){return /^Statue.s Blessing$/.test(r.text.trim())&&r.x>1100&&r.y>400&&r.y<850;})){
                    this.chooseStatueBlessing();await sleep(700);var panel=await observe();return {status:'stopped',action:'blessing',frameId:panel.frameId};
                }
            }
            var speaker=rows.filter(function(r){return r.text==='Statue of The Seven'&&r.x>=750&&r.x<=1000&&r.y>=830&&r.y<=900;}),auto=rows.some(function(r){return r.text==='Auto'&&r.x<200&&r.y<80;});
            if(speaker.length!==1||!auto)throw new Error('Exact Statue speaker required');
            var worship=rows.filter(function(r){return r.text==='Worship Statue'&&r.x>1200&&r.y>430&&r.y<830;}),action;
            if(worship.length===1){click(Math.round(worship[0].x+worship[0].width/2),Math.round(worship[0].y+worship[0].height/2));action='worship';}
            else if(!initial.hud.choice){await boundedKey('VK_SPACE',60,initial.frameId);action='advance';}
            else return {status:'stopped',reason:'Inspect Statue choices'};
            events.push({type:'actTwoStatue',action:action,frameId:initial.frameId,startedAt:Date.now()});
            await sleep(700);var after=await observe();return {status:'stopped',action:action,frameId:after.frameId,questComplete:false};
        },
        runActTwoCooking: async function(initial,observe){
            checkStop();ready();var gate=eval(file.readTextSync('act-two-cooking.js')+'\nActTwoCooking;'),target=gate.target(initial,Date.now());
            if(request.step!=='actTwoCooking'||!actTwoOriginalAccount(initial.ocr)||!target)throw new Error('Fresh exact Chicken-Mushroom Skewer cooking stage required');
            var event={type:'actTwoCooking',action:target.action,frameId:initial.frameId,startedAt:Date.now(),samples:0,stopPressed:false};events.push(event);
            click(target.x,target.y);
            if(target.action==='manual'){
                var state={peak:null,candidate:null,stable:0},deadline=Date.now()+9000;
                try{
                    await sleep(150);
                    while(Date.now()<deadline){
                        checkStop();ready();var image=null,crop=null,mask=null,count=0;
                        try{image=captureGameRegion();if(Number(image.width)!==1920||Number(image.height)!==1080)throw new Error('Cooking capture dimensions changed');crop=image.deriveCrop(600,660,730,190);mask=crop.srcMat.inRange(new OpenCvSharp.OpenCvSharp.Scalar(64,192,255),new OpenCvSharp.OpenCvSharp.Scalar(64,192,255));count=Number(OpenCvSharp.OpenCvSharp.Cv2.countNonZero(mask));}
                        finally{dispose(mask);dispose(crop);dispose(image);}
                        event.samples++;event.lastColorCount=count;
                        if(gate.peak(state,count)){checkStop();ready();await boundedKey('VK_SPACE',60);event.stopPressed=true;event.peak=state.peak;break;}
                        await sleep(30);
                    }
                }finally{release();event.finishedAt=Date.now();}
            }
            await sleep(600);var after=await observe(),result={status:'stopped',action:target.action,frameId:after.frameId,stopPressed:event.stopPressed,samples:event.samples,reason:'One cooking UI action; verify next stage',questComplete:false};
            if(target.action==='exit'&&after.hud.world)return this.finishActTwoDialogue(initial,observe,result);return result;
        },
        selectActTwoLynn: async function(){
            checkStop();ready();var o=lastObservation,rows=o.ocr||[],lynn=rows.filter(function(r){return r.text==='Lynn'&&r.x>=1200&&r.x<=1400&&r.y>=480&&r.y<=520;}),f=rows.filter(function(r){return r.text==='F'&&r.x>=1080&&r.x<=1170&&r.y>=540&&r.y<=590;});
            if(request.step!=='actTwoLynnTalk'||!actTwoOriginalAccount(rows)||!o.hud.world||!o.hud.health||lynn.length!==1||f.length!==1||!rows.some(function(r){return r.text==='Cook'&&r.x>=1200&&r.x<=1400&&Math.abs(r.y+r.height/2-f[0].y-f[0].height/2)<25;}))return false;
            events.push({type:'actTwoLynnSelect',scroll:1,frameId:o.frameId,startedAt:Date.now()});verticalScroll(1);return true;
        },
        selectActTwoCook: async function(){
            checkStop();ready();var o=lastObservation,rows=o.ocr||[],selection=eval(file.readTextSync('act-two-interaction.js')+'\nActTwoInteraction;').selection(rows,'Cook');
            var goodHunter=o.map&&o.map.map==='Teyvat'&&Math.hypot(o.map.x+886.7,o.map.y-2240.3)<=8&&o.hud.health&&o.hud.health.max===2313&&o.hud.health.current>=1967;
            if(request.step!=='actTwoCookOpen'||!actTwoOriginalAccount(rows)||!o.hud.world||!o.hud.health||o.hud.health.current!==1700&&!goodHunter||!selection)throw new Error('Fresh exact Cook interaction required');
            if(selection==='next'){events.push({type:'actTwoCookSelect',scroll:-1,frameId:o.frameId,startedAt:Date.now()});verticalScroll(-1);}
        },
        runActTwoNavigationWithPause: async function(initial,observe,navigate){
            var protector=loadLocalPause(),attempted=false,current=initial,result=null,error=null;
            try{
                var gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
                var guildTalk=request.mission==='questStep'&&['actTwoFieldInspect','actTwoFinalTrial','actTwoLionInspect','actTwoStatueSelectKaeya','actTwoChallengeStart','actTwoAmberTalk','actTwoWindriseOculus','actTwoSaraOpen','actTwoStatueOpen','actTwoMushroom','actTwoCookOpen','actTwoLynnTalk','actTwoVileTalk','actTwoKaeyaReport','actTwoJackTalk','actTwoCyrusTalk','actTwoGuildTalk','actTwoWagnerTalk','actTwoKaeyaTalk','actTwoWaypoint','actTwoHqEnter'].indexOf(request.step)>=0;
                var oreWork=request.mission==='questStep'&&['actTwoOre','actTwoClueCamera','actTwoWindmillLookUp'].indexOf(request.step)>=0;
                if(!(guildTalk||oreWork||request.mission==='navigation'&&["Go to the exam point","Talk to Amber","Check the suspicious location and eliminate any threats","Explore for Adventure Rank","Purchase Fisherman's Toast",'Offer the Anemoculus to the Statue','Give the Chicken-Mushroom Skewer to Lynn','Speak to Lynn','Talk to Katheryne for more details','Talk to Wagner the blacksmith','Collect three Iron Chunks and give them to Wagner','Talk to Kaeya','Talk to Kaeya at the meeting spot','Report to Kaeya','Meet with the informant at the designated location','Talk to the informant','Solve the mystery (Go to Kaeya at the Knights of Favonius HQ for a hint)',"Go to the Adventurers' Guild and listen to their report"].indexOf(request.objective)>=0)||
                    typeof navigate!=='function'||!gate(initial,Date.now(),request.session))
                    throw new Error('Fresh inventory and bounded Guild navigation required');
                checkStop();attempted=true;
                await boundedKey('VK_ESCAPE',60,initial.frameId);
                for(var poll=0;poll<5;poll++){
                    await sleep(200);current=await observe();
                    if(current.hud.world&&current.hud.groundControls)break;
                }
                if(!actTwoOriginalAccount(current.ocr)||!current.hud.world||!current.hud.groundControls||current.hud.climbing||
                    (current.hud.enemyBars||[]).length||!current.map)throw new Error('Original account and safe Guild field required');
                navLastAcceptedPosition={x:current.map.x,y:current.map.y};
                result=await navigate(current);
                if(request.step==='actTwoLionInspect'&&result.entranceOpened&&lastObservation&&!lastObservation.hud.world&&!lastObservation.hud.health){result.pauseVerified=false;result.menuHeld='Lion entrance inspection';return result;}
                if(request.step==='actTwoCookOpen'&&result.cookingOpened&&lastObservation&&!lastObservation.hud.world&&!lastObservation.hud.health){result.pauseVerified=false;result.menuHeld='Cooking inspection';return result;}
                if(guildTalk&&eval(file.readTextSync('act-two-rank-rewards.js')+'\nActTwoRankRewards;').target(lastObservation,Date.now())){
                    result.pauseVerified=false;result.menuHeld='Adventure Rank rewards';return result;
                }
                if(lastObservation&&(lastObservation.hud.dialogueReady||lastObservation.hud.choice)){
                    result.pauseVerified=false;result.conversationActive=true;return result;
                }
            }catch(e){error=String(e&&e.message||e);}
            if(attempted){
                result=result||{status:'stopped',reason:error};result.navigationStatus=result.status;result.questComplete=false;
                return await finishWithLocalPause(protector,this,initial,observe,initial.frameId,result,error);
            }
            if(error)throw new Error(error);return result;
        },
        actTwoJournalRecoveryReady: function(o){
            var guard=eval(file.readTextSync('act-two-journal-recovery.js')+'\nActTwoJournalRecovery;');
            return guard.ready(o,Date.now(),request.session,actTwoOriginalAccount(o&&o.ocr||[]));
        },
        runActTwoJournalRecovery: async function(initial,observe){
            if(request.step==='actTwoRecover'&&initial&&initial.session===request.session&&Date.now()>=initial.timestamp&&Date.now()-initial.timestamp<=1000&&actTwoOriginalAccount(initial.ocr)&&initial.hud.auto&&(initial.hud.choice||initial.hud.dialogueReady)&&!initial.hud.health&&!initial.hud.groundControls&&
                initial.ocr.some(function(r){return r.text==='Cyrus'&&r.x>=900&&r.x<=1010&&r.y>=850&&r.y<=880;})&&initial.ocr.some(function(r){return r.text==="Branch Master, Adventurers' Guild"&&r.x>=730&&r.x<=800&&r.y>=890&&r.y<=920;})){
                var recoveryMission=eval(file.readTextSync('mission.js')+'\nActOneMission;');
                return this.finishActTwoDialogue(initial,observe,await recoveryMission.runDialogue(this,observe));
            }
            if(request.step!=='actTwoRecover'||!this.actTwoJournalRecoveryReady(initial))throw new Error('Fresh original-account Cyrus journal required for recovery');
            checkStop();ready();release();
            var event={type:'actTwoJournalRecovery',frameId:initial.frameId,startedAt:Date.now()};events.push(event);
            try{await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(650);}
            finally{release();event.finishedAt=Date.now();}
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,{status:'completed',step:request.step,journalCloseAttempts:1,questComplete:false},null);
        },
        finishActTwoDialogue: async function(initial,observe,result){
            if(lastObservation&&(this.pauseProof(lastObservation)||lastObservation.hud.world||actOneLocalPauseInputReady(lastObservation,Date.now(),request.session)))
                return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,result,null);
            result.pauseVerified=false;result.conversationActive=!!(lastObservation&&(lastObservation.hud.dialogueReady||lastObservation.hud.choice));return result;
        },
        runLisaNavigationWithPause: async function(initial,observe,navigate){
            var protector=loadLocalPause(),closeAttempted=false,startedInField=actOneLocalPauseInputReady(initial,Date.now(),request.session);
            var current=initial,result=null,operationError=null;
            try{
                if(!lisaNavigationRequest()||typeof navigate!=='function')throw new Error('Exact Lisa navigation callback required');
                var reviewed=lisaNavigationPermit(),inventoryGate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
                if(!reviewed||!inventoryGate(initial,Date.now(),request.session))throw new Error('Fresh charted GPS witness and Food inventory required for Lisa navigation');
                var p=reviewed.permit;p.usedAt=Date.now();p.requestId=request.id;var source=JSON.stringify(p);
                if(!file.writeTextSync('lisa-navigation-witness.json',source)||file.readTextSync('lisa-navigation-witness.json')!==source)
                    throw new Error('Navigation witness consumption not verified; no input sent');
                if(!inventoryGate(initial,Date.now(),request.session))throw new Error('Inventory source expired before navigation close');
                checkStop();lisaNavigationState.active=true;closeAttempted=true;lisaNavigationState.lastInputFrame=initial.frameId;
                lisaNavigationState.evadeUntil=p.evade===true?Date.now()+20000:0;
                navLastAcceptedPosition={x:reviewed.witness.map.x,y:reviewed.witness.map.y};
                var event={type:'lisaNavigationInventoryClose',rootDirected:true,witnessFrameId:reviewed.witness.frameId,frameId:initial.frameId,startedAt:Date.now()};events.push(event);
                try{await boundedKey('VK_ESCAPE',60,initial.frameId);}finally{event.finishedAt=Date.now();}
                for(var poll=0;poll<6;poll++){
                    await sleep(150);current=await observe();
                    if(lisaNavigationInputReady(current))break;
                }
                if(!lisaNavigationInputReady(current))throw new Error('Fresh grounded charted Lisa field unavailable after inventory close');
                lisaNavigationState.lastField=current;
                result=await navigate(current);
            }catch(e){operationError=String(e&&e.message||e);}
            if(closeAttempted||startedInField){
                result=result||{status:'stopped',reason:operationError||'Lisa navigation unavailable'};
                result.navigationStatus=result.status;result.destinationReached=result.status==='arrived';result.questComplete=false;
                result.step='lisaNavigation';
                var field=lisaNavigationState.lastField;
                if(field){result.fieldFrameId=field.frameId;result.fieldPosition=field.map;result.fieldHealth=field.hud.health;}
                result=await finishWithLocalPause(protector,this,initial,observe,Math.max(initial.frameId,lisaNavigationState.lastInputFrame),result,operationError);
                // The finite request completed safely; navigationStatus separately records arrival or stop.
                result.status='completed';return result;
            }
            if(operationError)throw new Error(operationError);
            return result;
        },
        lisaNavigationEnemyAllowed: function(){return lisaNavigationRequest()&&lisaNavigationState.active&&Date.now()<lisaNavigationState.evadeUntil;},
        runLisaClimb: async function(initial,observe){
            var current=initial,protector=loadLocalPause(),attempted=false,error=null,holds=0,dropSent=false,lastFrame=initial.frameId;
            var guard=lisaClimbReleaseModule(),result={status:'stopped',step:'lisaClimb',questComplete:false};
            try{
                checkStop();ready();
                var gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
                var permit=JSON.parse(file.readTextSync('lisa-climb-witness.json')),now=Date.now();
                var climbKey=permit.action==='descend'?'VK_S':'VK_W';
                var holdLimit=permit.action==='descend'?2:8;
                if(!request||request.step!=='lisaClimb'||!gate(current,now,request.session)||
                   permit.session!==request.session||permit.frameId!==request.expectedFrameId||permit.reviewed!==true||permit.usedAt||
                   !Number.isInteger(permit.witnessFrameId)||permit.witnessFrameId>=request.expectedFrameId||
                   !Number.isFinite(permit.createdAt)||now<permit.createdAt||now-permit.createdAt>120000)
                    throw new Error('Fresh reviewed climbing witness and paused inventory required');
                var prefix='observations/'+request.session+'/frame-'+String(permit.witnessFrameId).padStart(4,'0');
                var witness=JSON.parse(file.readTextSync(prefix+'.json'));
                // A rejected local GPS fix cannot locate the player. The strict
                // climbing HUD can still authorize this bounded ledge recovery;
                // do not promote the rejected coordinate into navigation evidence.
                if(witness.map===null&&witness.timings&&witness.timings.mapDiagnostic&&
                   ['Root-witnessed uncharted approach; no map coordinate inferred','Local candidate rejected'].indexOf(witness.timings.mapDiagnostic.reason)>=0){
                    var climbWitness=Object.assign({},witness,{hud:Object.assign({},witness.hud,{world:true})});
                    if(guard.ready(climbWitness,witness.timestamp,request.session,{armed:true,releaseAttempted:false,lastInputFrame:-1,
                       allowEnemyEscape:permit.action==='drop'}))witness=climbWitness;
                }
                if(!file.isExists(prefix+'.png')||now<witness.timestamp||now-witness.timestamp>600000||
                   !guard.ready(witness,witness.timestamp,request.session,{armed:true,releaseAttempted:false,lastInputFrame:-1,allowEnemyEscape:permit.action==='drop'}))
                    throw new Error('Recorded safe Lisa climbing HUD required');
                permit.usedAt=now;if(!file.writeTextSync('lisa-climb-witness.json',JSON.stringify(permit)))throw new Error('Climb witness consumption failed');
                attempted=true;await boundedKey('VK_ESCAPE',60,current.frameId);await sleep(250);current=await observe();
                for(var settle=0;settle<3&&!current.hud.climbing&&!current.hud.groundControls;settle++){
                    await sleep(200);current=await observe();
                }
                var baseline=witness.hud.health;
                if(permit.action==='drop'){
                    if(!guard.ready(current,Date.now(),request.session,{armed:true,releaseAttempted:false,lastInputFrame:lastFrame,allowEnemyEscape:true}))
                        throw new Error('Fresh healthy enemy-free climbing HUD required for reviewed ledge drop');
                    lastFrame=current.frameId;events.push({type:'lisaReviewedLedgeDrop',frameId:lastFrame,key:'VK_X',durationMs:60,startedAt:Date.now()});
                    await boundedKey('VK_X',60,lastFrame);dropSent=true;await sleep(700);current=await observe();holdLimit=0;
                }
                for(var i=0;i<holdLimit;i++){
                    checkStop();ready();
                    if(current.hud.climbing!==true){result.reason=current.hud.groundControls?'Climbing ended; inspect fresh terrain':'Climbing HUD unresolved; no further input';break;}
                    if(!guard.ready(current,Date.now(),request.session,{armed:true,releaseAttempted:false,lastInputFrame:lastFrame})||
                       current.hud.health.max!==baseline.max||baseline.current-current.hud.health.current>baseline.max*0.1)
                        throw new Error('Fresh healthy enemy-free climbing HUD required before each hold');
                    lastFrame=current.frameId;
                    events.push({type:'lisaClimbHold',key:climbKey,frameId:lastFrame,durationMs:800,startedAt:Date.now()});
                    await boundedKey(climbKey,800,lastFrame);holds++;await sleep(200);current=await observe();
                }
                var grounded=current.hud.climbing===false&&current.hud.groundControls===true;
                if(grounded){result.status='completed';result.reason=permit.action==='drop'?'Reviewed drop ended on grounded HUD':'Climbing ended; inspect fresh terrain';}
                else result.reason=result.reason||'Climb budget reached; inspect stamina before any continuation';
                result.fieldFrameId=current.frameId;result.fieldPosition=current.map;result.fieldHealth=current.hud.health;
                result.climbing=current.hud.climbing;result.groundControls=current.hud.groundControls;
            }catch(e){error=String(e&&e.message||e);result.reason=error;}
            result.holds=holds;result.dropSent=dropSent;result.inputMs=holds*800+(dropSent?60:0);
            result.inputBudgetMs=permit&&permit.action==='drop'?60:holdLimit*800;
            if(attempted)return await finishWithLocalPause(protector,this,initial,observe,lastFrame,result,error);
            return result;
        },
        runLisaTeamClose: async function(initial,observe){
            var current=initial,protector=loadLocalPause(),attempted=false,error=null;
            var domain=initial.map===null&&file.isExists('reports/'+request.session+'.json')&&lionLiveContext(initial).entry(initial);
            try{
                for(var i=0;i<2;i++){
                    checkStop();ready();
                    for(var menuSettle=0;menuSettle<3&&!actOneStarterLevelPanelVisible(current,Date.now(),'Kaeya')&&!actOneStarterLevelPanelVisible(current,Date.now(),'Lumina')&&!actOneWolfCharacterMenuVisible(current,Date.now());menuSettle++){
                        await sleep(250);current=await observe();
                    }
                    var level=actOneStarterLevelPanelVisible(current,Date.now(),'Kaeya')||actOneStarterLevelPanelVisible(current,Date.now(),'Lumina');
                    if(!request||request.step!=='lisaTeamClose'||(!level&&!actOneWolfCharacterMenuVisible(current,Date.now())))
                        throw new Error('Verified character or level menu required for close');
                    attempted=true;await boundedKey('VK_ESCAPE',60,current.frameId);await sleep(500);current=await observe();
                    if(!level)break;
                }
                if(domain)return await finishWithLocalPause(protector,this,initial,observe,current.frameId,
                    {status:'completed',step:'lisaTeamClose',fieldFrameId:current.frameId,fieldHealth:current.hud.health,questComplete:false},null);
                for(var poll=0;poll<3&&(!current.hud.world||!current.hud.groundControls);poll++){await sleep(200);current=await observe();}
                if(!actOneLocalPauseInputReady(current,Date.now(),request.session)||!current.hud.world||
                    !current.hud.groundControls||!current.hud.health||current.hud.health.current<=0)
                    throw new Error('Fresh living field required after character menu');
                var amber=current.ocr.filter(function(r){return r.text.trim()==='Amber'&&r.x>1600&&r.y>350&&r.y<460;});
                if(amber.length!==1)throw new Error('Owned Amber slot label required');
                events.push({type:'lisaTeamReturnAmber',frameId:current.frameId,startedAt:Date.now()});
                await boundedKey('VK_2',60,current.frameId);await sleep(350);current=await observe();
                if(!current.hud.world||!current.hud.health||current.hud.health.current/current.hud.health.max<0.6)
                    throw new Error('Fresh healthy field required before map');
                await boundedKey('VK_M',60,current.frameId);await sleep(500);current=await observe();
                var proof=actOneLocalPauseProof(current,Date.now(),request.session);
                if(proof&&proof.kind==='map')return {status:'completed',step:'lisaTeamClose',pauseVerified:true,pauseProof:proof,questComplete:false,frameId:current.frameId};
                throw new Error('Map transition unverified');
            }catch(e){error=String(e&&e.message||e);}
            if(attempted)return await finishWithLocalPause(protector,this,initial,observe,initial.frameId,
                {status:'stopped',step:'lisaTeamClose',reason:error,questComplete:false},error);
            return {status:'stopped',step:'lisaTeamClose',reason:error};
        },
        runLisaKaeyaLevel: async function(initial,observe){
            var current=initial,before=initial.hud&&initial.hud.kaeyaLevel;
            if(file.isExists('lion-kaeya-level.json')){
                var permit=JSON.parse(file.readTextSync('lion-kaeya-level.json'));
                var traveler=permit.character==='Lumina',character=traveler?'Lumina':'Kaeya',books=traveler?2:1,stock=traveler?3:4,mora=traveler?16995:17195;
                function lowBookPanel(o,amount){var v=o&&o.hud&&o.hud.kaeyaLevel;return !!(o.session===request.session&&
                    actOneStarterLevelPanelVisible(o,Date.now(),character)&&v&&v.frameId===o.frameId&&v.amount===amount&&
                    v.requiredMora===amount*200&&v.lowTierStock===stock&&v.midTierStock===0&&v.highTierStock===0&&v.mora===mora);}
                if(!request||request.step!=='lisaKaeyaLevel'||!permit||permit.session!==request.session||
                   permit.frameId!==request.expectedFrameId||permit.reviewed!==true||permit.usedAt||permit.character!==undefined&&['Kaeya','Lumina'].indexOf(permit.character)<0||
                   Date.now()<permit.createdAt||Date.now()-permit.createdAt>120000||!Number.isFinite(permit.createdAt)||
                   !lionLiveContext(initial).entry(initial)||!lowBookPanel(initial,0))
                    return {status:'stopped',step:'lisaKaeyaLevel',reason:'Exact reviewed one-book Lion upgrade required',resourceSpendAttempted:false};
                permit.usedAt=Date.now();var saved=JSON.stringify(permit);
                if(!file.writeTextSync('lion-kaeya-level.json',saved)||file.readTextSync('lion-kaeya-level.json')!==saved)throw new Error('Level permit consumption failed');
                for(var book=1;book<=books;book++){
                    checkStop();ready();events.push({type:'lionCharacterAddXp',character:character,book:"Wanderer's Advice",amount:book,frameId:current.frameId,startedAt:Date.now()});
                    click(1595,917);await sleep(250);current=await observe();
                    if(!lowBookPanel(current,book))return {status:'stopped',step:'lisaKaeyaLevel',reason:'Exact reviewed book cost not verified',resourceSpendAttempted:false};
                }
                checkStop();ready();events.push({type:'lionCharacterConfirmXp',character:character,book:"Wanderer's Advice",books:books,mora:books*200,frameId:current.frameId,startedAt:Date.now()});
                click(1730,1020);await sleep(1000);current=await observe();
                return {status:'completed',step:'lisaKaeyaLevel',character:character,resourceSpendAttempted:true,booksBudget:books,moraBudget:books*200,
                    moraBefore:before.mora,frameId:current.frameId,questComplete:false,upgradeVerified:false};
            }
            function valid(o,amount){var p=o&&o.hud&&o.hud.kaeyaLevel;return !!(request&&request.step==='lisaKaeyaLevel'&&
                o.session===request.session&&actOneStarterLevelPanelVisible(o,Date.now(),'Kaeya')&&p&&
                p.frameId===o.frameId&&p.amount===amount&&p.requiredMora===amount*1000&&p.midTierStock===2&&p.mora>=2000);}
            if(!valid(current,0))return {status:'stopped',step:'lisaKaeyaLevel',reason:'Verified Kaeya EXP panel with two books and zero selected required',resourceSpendAttempted:false};
            for(var i=1;i<=2;i++){
                checkStop();ready();if(!valid(current,i-1))throw new Error('EXP selection changed before input');
                events.push({type:'lisaKaeyaAddXp',amount:i,frameId:current.frameId,startedAt:Date.now()});
                click(1595,917);await sleep(250);current=await observe();
                if(!valid(current,i))return {status:'stopped',step:'lisaKaeyaLevel',reason:'EXP selection not verified; no resources spent',resourceSpendAttempted:false};
            }
            checkStop();ready();events.push({type:'lisaKaeyaConfirmXp',books:2,mora:2000,frameId:current.frameId,startedAt:Date.now()});
            click(1730,1020);await sleep(1000);current=await observe();
            return {status:'completed',step:'lisaKaeyaLevel',resourceSpendAttempted:true,booksBudget:2,moraBudget:2000,
                moraBefore:before.mora,frameId:current.frameId,questComplete:false,upgradeVerified:false};
        },
        runLisaWeaponChoice: async function(initial,observe){
            checkStop();ready();
            var p=JSON.parse(file.readTextSync('lisa-weapon-choice.json')),now=Date.now(),rows=initial.ocr||[],h=initial.hud;
            function unique(text,x0,x1,y0,y1){return rows.filter(function(r){return r.text.trim()===text&&r.x>=x0&&r.x<x1&&r.y>=y0&&r.y<y1;});}
            if(!request||request.step!=='lisaWeaponChoice'||!p||p.session!==request.session||initial.session!==request.session||
               p.frameId!==request.expectedFrameId||p.reviewed!==true||p.usedAt||!Number.isFinite(p.createdAt)||now<p.createdAt||now-p.createdAt>120000||
               now<initial.timestamp||now-initial.timestamp>1000||initial.map!==null||!h||h.world||h.auto||h.dialogueReady||h.choice||h.bigMap||
               unique('Weapon Selection',100,450,0,90).length!==1||unique('Base ATK',1400,1700,180,280).length!==1)
                return {status:'stopped',step:'lisaWeaponChoice',reason:'Fresh reviewed weapon-selection permit required',resourcesSpent:false};
            var x,y;
            if(p.action==='back'){
                x=null;y=null;
            }else if(p.action==='inspectFirst'&&unique('Equipped: Kaeya',1450,1850,890,980).length===1&&unique('Dull Blade',1400,1800,100,180).length===1){
                // First card was root-reviewed in the current paused selection.
                x=100;y=205;
            }else if(p.action==='equip'&&['Cool Steel','Harbinger of Dawn',"Traveler's Handy Sword",'Skyrider Sword'].indexOf(p.name)>=0&&
                unique(p.name,1400,1900,100,180).length===1&&Number.isInteger(p.baseAttack)&&p.baseAttack>23&&p.baseAttack<=50&&
                unique(String(p.baseAttack),1740,1900,200,280).length===1&&!rows.some(function(r){return /^Equipped:/.test(r.text.trim());})){
                var buttons=unique('Switch',1450,1680,950,1040);
                if(buttons.length!==1)return {status:'stopped',step:'lisaWeaponChoice',reason:'Unique unequipped sword Switch required',resourcesSpent:false};
                x=Math.round(buttons[0].x+buttons[0].width/2);y=Math.round(buttons[0].y+buttons[0].height/2);
            }else return {status:'stopped',step:'lisaWeaponChoice',reason:'Reviewed reversible equipment action did not match',resourcesSpent:false};
            p.usedAt=now;var saved=JSON.stringify(p);
            if(!file.writeTextSync('lisa-weapon-choice.json',saved)||file.readTextSync('lisa-weapon-choice.json')!==saved)throw new Error('Equipment permit consumption failed');
            checkStop();ready();events.push({type:'lisaWeaponChoice',action:p.action,name:p.name||null,frameId:initial.frameId,startedAt:Date.now()});
            if(p.action==='back')await boundedKey('VK_ESCAPE',60,initial.frameId);else click(x,y);
            await sleep(500);var current=await observe();
            return {status:'completed',step:'lisaWeaponChoice',action:p.action,resourcesSpent:false,questComplete:false,frameId:current.frameId,
                equippedVerified:p.action==='equip'&&current.ocr.some(function(r){return r.text.trim()==='Equipped: Kaeya'&&r.x>=1450&&r.y>=890&&r.y<980;})&&
                    current.ocr.some(function(r){return r.text.trim()===p.name&&r.x>=1400&&r.y>=100&&r.y<180;})};
        },
        runLisaWeaponSwitch: async function(initial,observe){
            var current=initial,panels=[];
            for(var i=0;i<2;i++){
                checkStop();ready();
                var label=i===0?'Weapons':'Switch';
                if(!request||request.step!=='lisaWeaponSwitch'||current.session!==request.session||
                   !actOneWolfCharacterMenuVisible(current,Date.now())||
                   current.ocr.filter(function(r){return /^Cryo\s*[/I]\s*Kaeya$/.test(r.text.trim())&&r.x>=100&&r.x<400&&r.y<90;}).length!==1)
                    return {status:'stopped',step:'lisaWeaponSwitch',reason:'Fresh selected Kaeya menu required',panels:panels,resourcesSpent:false};
                var matches=current.ocr.filter(function(r){return r.text.trim()===label&&
                    (i===0?r.x>=100&&r.x<400&&r.y>=170&&r.y<260:r.x>=1450&&r.x<1650&&r.y>=950&&r.y<1040);});
                if(matches.length!==1)return {status:'stopped',step:'lisaWeaponSwitch',reason:'Unique '+label+' control required',panels:panels,resourcesSpent:false};
                if(i===1&&!current.ocr.some(function(r){return r.text.trim()==='Base ATK'&&r.x>=1400&&r.y>=180&&r.y<300;}))
                    return {status:'stopped',step:'lisaWeaponSwitch',reason:'Weapon details required',panels:panels,resourcesSpent:false};
                var target=matches[0];events.push({type:'lisaWeaponInspect',label:label,frameId:current.frameId,startedAt:Date.now()});
                click(Math.round(target.x+target.width/2),Math.round(target.y+target.height/2));await sleep(500);current=await observe();
                panels.push({label:label,frameId:current.frameId});
            }
            return {status:'completed',step:'lisaWeaponSwitch',panels:panels,resourcesSpent:false,questComplete:false,frameId:current.frameId};
        },
        runLisaTeamReview: async function(initial,observe){
            var current=initial,panels=[];
            if(file.isExists('lion-menu-review.json')){
                var menuPermit=JSON.parse(file.readTextSync('lion-menu-review.json'));
                if(menuPermit.frameId===request.expectedFrameId&&menuPermit.session===request.session){
                    checkStop();ready();
                    function menuOne(text,x0,x1,y0,y1){return initial.ocr.filter(function(r){return r.text.trim()===text&&r.x>=x0&&r.x<x1&&r.y>=y0&&r.y<y1;}).length===1;}
                    var artifactMenu=initial.session===request.session&&initial.map===null&&initial.hud.world===false&&!initial.hud.auto&&!initial.hud.dialogueReady&&!initial.hud.choice&&!initial.hud.bigMap&&Date.now()>=initial.timestamp&&Date.now()-initial.timestamp<=1000&&
                        menuOne('Compare',1600,1800,20,80)&&menuOne('Set Filter',100,450,970,1040)&&
                        ['Flower of Life','Plume of Death','Sands of Eon','Goblet of Eonothem','Circlet of Logos'].some(function(t){return menuOne(t,1400,1850,160,210);});
                    var weaponEnhancement=initial.session===request.session&&initial.map===null&&initial.hud.world===false&&Date.now()>=initial.timestamp&&Date.now()-initial.timestamp<=1000&&
                        initial.ocr.filter(function(r){return /^Sword [/%] Traveler's Handy Sword$/.test(r.text.trim())&&r.x>=100&&r.x<=650&&r.y>=15&&r.y<=80;}).length===1&&menuOne('Details',80,320,110,180)&&menuOne('Refine',80,320,250,330)&&menuOne('Required',1100,1350,980,1050);
                    var weaponMaterials=initial.session===request.session&&initial.map===null&&initial.hud.world===false&&Date.now()>=initial.timestamp&&Date.now()-initial.timestamp<=1000&&menuOne('Base EXP',30,180,20,80)&&menuOne('Required',1100,1350,980,1050)&&menuOne('Enhance',1600,1850,980,1050);
                    if(request.step!=='lisaTeamReview'||menuPermit.reviewed!==true||menuPermit.usedAt||
                       !Number.isFinite(menuPermit.createdAt)||Date.now()<menuPermit.createdAt||Date.now()-menuPermit.createdAt>120000||
                       !(lionLiveContext(initial).entry(initial)||JSON.parse(file.readTextSync('reports/'+request.session+'.json')).some(function(r){return r.session===request.session&&r.status==='completed'&&r.timestamp<=initial.timestamp&&r.details&&r.details.result&&r.details.result.characterMenuVerified===true;}))||!(actOneWolfCharacterMenuVisible(initial,Date.now())||artifactMenu||weaponEnhancement||weaponMaterials)||
                       ['inspect','equip','back','addOre','enhanceWeapon'].indexOf(menuPermit.action)<0||!Array.isArray(menuPermit.evidence)||menuPermit.evidence.length<3||menuPermit.evidence.length>6||
                       !menuPermit.evidence.every(function(e){return typeof e.text==='string'&&Number.isInteger(e.x)&&Number.isInteger(e.y)&&initial.ocr.filter(function(r){return r.text.trim()===e.text&&Math.abs(r.x-e.x)<=12&&Math.abs(r.y-e.y)<=12;}).length===1;})||
                       !Number.isInteger(menuPermit.x)||!Number.isInteger(menuPermit.y)||menuPermit.x<40||menuPermit.x>1850||menuPermit.y<20||menuPermit.y>1040)
                        return {status:'stopped',step:'lisaTeamReview',reason:'Fresh exact reviewed character equipment menu required',resourcesSpent:false};
                    var inspectButton=!weaponEnhancement&&!weaponMaterials&&initial.ocr.filter(function(r){return ['Switch','Enhance','Fast Equip'].indexOf(r.text.trim())>=0&&r.x>1400&&r.y>950&&menuPermit.x>=r.x&&menuPermit.x<=r.x+r.width&&menuPermit.y>=r.y&&menuPermit.y<=r.y+r.height;}).length===1;
                    var equipButton=artifactMenu&&initial.ocr.filter(function(r){return r.text.trim()==='Equip'&&r.x>1400&&r.y>950&&menuPermit.x>=r.x&&menuPermit.x<=r.x+r.width&&menuPermit.y>=r.y&&menuPermit.y<=r.y+r.height;}).length===1;
                    if(!(menuPermit.action==='inspect'&&((weaponMaterials?menuPermit.x<300&&menuPermit.y>=110&&menuPermit.y<=260:menuPermit.x<1300)||inspectButton)||menuPermit.action==='enhanceWeapon'&&weaponMaterials&&menuPermit.x===1740&&menuPermit.y===1020&&(menuOne('Fine Enhancement Ore',1150,1650,160,240)||menuOne('6/11',1180,1300,900,950)&&menuOne('Enhancement Materials Consumed (1/40)',1200,1850,670,740))&&menuOne('+12000',1400,1600,120,180)&&menuOne('1200',1300,1450,980,1050)&&menuOne('16595',1600,1800,15,80)&&menuOne('0/275',1750,1900,120,190)&&(menuOne('ed (1/40)',1600,1850,670,740)||menuOne('Enhancement Materials Consumed (1/40)',1200,1850,670,740))||menuPermit.action==='equip'&&equipButton||menuPermit.action==='addOre'&&weaponMaterials&&menuOne('Fine Enhancement Ore',1150,1650,160,240)&&menuPermit.x===99&&menuPermit.y===180||menuPermit.action==='back'&&(artifactMenu||weaponEnhancement||weaponMaterials)&&menuPermit.x===1840&&menuPermit.y===47))
                        return {status:'stopped',step:'lisaTeamReview',reason:'Inspection is limited to character icons and left or center equipment panels',resourcesSpent:false};
                    menuPermit.usedAt=Date.now();var menuSaved=JSON.stringify(menuPermit);
                    if(!file.writeTextSync('lion-menu-review.json',menuSaved)||file.readTextSync('lion-menu-review.json')!==menuSaved)throw new Error('Menu permit consumption failed');
                    checkStop();ready();events.push({type:'lionReviewedEquipmentMenu',action:menuPermit.action,x:menuPermit.x,y:menuPermit.y,evidence:menuPermit.evidence,frameId:initial.frameId,startedAt:Date.now()});
                    if(menuPermit.action==='addOre'){
                        for(var oreIndex=0;oreIndex<5;oreIndex++){
                            checkStop();ready();
                            if(current.session!==request.session||Date.now()-current.timestamp>1000||current.hud.world||current.ocr.filter(function(r){return r.text.trim()==='Fine Enhancement Ore'&&r.x>1150&&r.y>160&&r.y<240;}).length!==1)throw new Error('Fresh reviewed ore selection lost');
                            click(99,180);await sleep(250);current=await observe();
                        }
                    }else{click(menuPermit.x,menuPermit.y);await sleep(500);current=await observe();}
                    return {status:'completed',step:'lisaTeamReview',action:menuPermit.action,resourcesSpent:menuPermit.action==='enhanceWeapon'?'attempted':false,questComplete:false,frameId:current.frameId};
                }
            }
            var domain=initial.map===null&&file.isExists('reports/'+request.session+'.json')&&lionLiveContext(initial).entry(initial);
            var labels=domain?['Level Up']:['Weapons','Artifacts','Talents','Attributes','Level Up'];
            for(var i=0;i<labels.length;i++){
                checkStop();ready();
                if(!request||request.step!=='lisaTeamReview'||!actOneWolfCharacterMenuVisible(current,Date.now())||
                   !(current.ocr.filter(function(r){return /^Cryo\s*\/\s*Kaeya$/.test(r.text.trim())&&r.x>=100&&r.x<400&&r.y<90;}).length===1||
                     domain&&current.ocr.filter(function(r){return ['Kaeya','Lumina'].indexOf(r.text.trim())>=0&&r.x>=1400&&r.x<1800&&r.y>=100&&r.y<180;}).length===1))
                    return {status:'stopped',step:'lisaTeamReview',reason:'Fresh selected Kaeya character menu required',panels:panels,resourcesSpent:false};
                var label=labels[i];
                var matches=current.ocr.filter(function(r){var text=r.text.normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim();return new RegExp('^'+label+'(?:[^A-Za-z].*)?$').test(text)&&
                    (label==='Level Up'?r.x>1400&&r.y>900:r.x>=40&&r.x<400&&r.y>=80&&r.y<750);});
                if(matches.length!==1)return {status:'stopped',step:'lisaTeamReview',reason:'Unique '+label+' control required',panels:panels,resourcesSpent:false};
                var target=matches[0];events.push({type:'lisaTeamReview',label:label,frameId:current.frameId,startedAt:Date.now()});
                click(Math.round(target.x+target.width/2),Math.round(target.y+target.height/2));await sleep(500);current=await observe();
                panels.push({label:label,frameId:current.frameId});
            }
            return {status:'completed',step:'lisaTeamReview',panels:panels,resourcesSpent:false,questComplete:false,frameId:current.frameId};
        },
        runLisaTeamInspect: async function(initial,observe){
            var protector=loadLocalPause(),current=initial,attempted=false,operationError=null;
            var proof=request&&actOneLocalPauseProof(initial,Date.now(),request.session);
            function inspectionField(o){
                var h=o&&o.hud,hp=h&&h.health,m=o&&o.map;
                var atStatue=m&&m.map==='Teyvat'&&Number.isFinite(m.x)&&Number.isFinite(m.y)&&Math.hypot(m.x+1323.474,m.y-2566.115)<20;
                // Opening the menu does not select a party slot. Require actual
                // field/quest/health evidence, not OCR of the selected grey keycap.
                return !!(o&&o.session===request.session&&Date.now()-o.timestamp>=0&&Date.now()-o.timestamp<=1000&&
                    actOneLocalPauseInputReady(o,Date.now(),request.session)&&h.groundControls===true&&!h.climbing&&
                    (h.objectives||[]).filter(function(t){return actOneLisaObjective(t)||['Talk to Lisa','Enter the temple'].indexOf(String(t).trim())>=0;}).length===1&&hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&
                    hp.max>0&&hp.current>0&&hp.current<=hp.max&&(hp.current/hp.max>=0.6||atStatue)&&
                    Array.isArray(h.enemyBars)&&!h.enemyBars.length&&!o.ocr.some(function(r){return r.text.trim()==='Trial';}));
            }
            if(!request||request.mission!=='questStep'||request.step!=='lisaTeamInspect'||!proof||['inventory','journal'].indexOf(proof.kind)<0)
                return {status:'stopped',step:'lisaTeamInspect',reason:'Fresh safe inventory required',characterMenuVerified:false};
            try{
                if(initial.map===null&&file.isExists('reports/'+request.session+'.json')&&lionLiveContext(initial).entry(initial)){
                    // Switching between two pause menus must not wait for a
                    // full field OCR while adjacent enemies are attacking.
                    checkStop();ready();attempted=true;
                    await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(400);
                    checkStop();ready();await boundedKey('VK_C',60,initial.frameId);await sleep(500);
                    for(var domainMenuPoll=0;domainMenuPoll<4;domainMenuPoll++){
                        current=await observe();
                        if(actOneWolfCharacterMenuVisible(current,Date.now())){
                            release();return {status:'completed',step:'lisaTeamInspect',characterMenuVerified:true,
                                pauseVerified:true,pauseKind:'characterMenu',frameId:current.frameId,questComplete:false,resourcesSpent:false};
                        }
                        await sleep(200);
                    }
                    throw new Error('Lion character menu did not become recognizable');
                }
                checkStop();ready();attempted=true;await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(350);
                for(var poll=0;poll<4;poll++){
                    current=await observe();
                    if(inspectionField(current))break;
                    await sleep(150);
                }
                if(!inspectionField(current))
                    throw new Error('Fresh safe Lisa field required before character inspection');
                checkStop();ready();
                events.push({type:'lisaTeamInspect',frameId:current.frameId,startedAt:Date.now()});
                await boundedKey('VK_C',60,current.frameId);await sleep(500);
                for(var menuPoll=0;menuPoll<4;menuPoll++){
                    current=await observe();
                    if(actOneWolfCharacterMenuVisible(current,Date.now())){
                        release();return {status:'completed',step:'lisaTeamInspect',characterMenuVerified:true,
                            pauseVerified:true,pauseKind:'characterMenu',frameId:current.frameId,questComplete:false,resourcesSpent:false};
                    }
                    await sleep(200);
                }
                throw new Error('Character menu did not become recognizable');
            }catch(e){operationError=String(e&&e.message||e);}
            if(attempted)return await finishWithLocalPause(protector,this,initial,observe,initial.frameId,
                {status:'stopped',step:'lisaTeamInspect',characterMenuVerified:false,questComplete:false},operationError);
        },
        runLionVisualMove: async function(initial,observe){
            var context=lionLiveContext(initial),guard=context.guard,protector=loadLocalPause();
            var current=initial,attempted=false,result={status:'stopped',step:'lionVisualMove',moves:0,turns:0,questComplete:false},error=null;
            try{
                var proof=actOneLocalPauseProof(initial,Date.now(),request.session),p=JSON.parse(file.readTextSync('lion-visual-move.json'));
                var action=p.action||'walk',careful=/^careful/.test(action),wind=action==='windLaunch'||action==='carefulWind',glide=action==='glideForward'||action==='carefulGlide',door=(action==='openDoor'||action==='openChest'||action==='activateMechanism'),electro=action==='electroAttack',trial=action==='electroTrial',basic=action==='normalBurst',selectKaeya=action==='selectKaeya'||action==='selectTraveler'||action==='selectLisa'||action==='selectAmber',rescueCryo=action==='kaeyaRescueCombat'||action==='travelerRescueCombat'||action==='amberRescueCombat',cryo=action==='amberRescueCombat'||action==='travelerRescueCombat'||action==='kaeyaRescueCombat'||action==='kaeyaCombat'||action==='lisaCombat'||action==='travelerCombat'||action==='amberCombat',rescueBurst=action==='lisaRescueBurst',nativeFight=action==='nativeCombat',loot=action==='collectLoot';
                function rescueReady(o,now){return guard.living(o,now,request.session)&&o.hud.health.max===1196&&o.hud.health.current>=240;}
                function rescueCryoReady(o,now){return guard.living(o,now,request.session)&&(action==='amberRescueCombat'?[1186]:action==='travelerRescueCombat'?[1288,1363]:[1379,1459]).indexOf(o.hud.health.max)>=0&&o.hud.health.current>=(action==='travelerRescueCombat'?50:Math.ceil(o.hud.health.max*0.1));}
                function movementReady(o){return rescueCryo?rescueCryoReady(o,Date.now()):rescueBurst?rescueReady(o,Date.now()):probe?(guard.field(o,Date.now(),request.session)||guard.air(o,Date.now(),request.session)):glide?guard.air(o,Date.now(),request.session,careful?0.3:undefined):careful?guard.combat(o,Date.now(),request.session):selectKaeya?guard.living(o,Date.now(),request.session):cryo||nativeFight||action==='carefulWalk'||action==='jumpForward'?guard.combat(o,Date.now(),request.session):guard.field(o,Date.now(),request.session);}
                var moveKey=p.moveKey||'VK_W';
                var moveMs=p.moveMs===undefined?800:p.moveMs;
                var pitch=p.relativeDy===undefined?0:p.relativeDy;
                var upperDock=p.dockProfile==='upper';
                var activatedDock=action==='carefulDisembarkActive';
                var probe=action==='probe',disembark=action==='disembarkPlatform'||action==='carefulDisembark'||activatedDock,board=action==='boardPlatform'||action==='carefulBoard'||disembark,jump=action==='jumpForward'||board;
                if(!request||request.mission!=='questStep'||request.step!=='lionVisualMove'||!proof||['inventory','journal'].indexOf(proof.kind)<0||
                  !context.entry(initial)||!p||p.session!==request.session||p.frameId!==request.expectedFrameId||
                  p.reviewed!==true||p.usedAt||!Number.isFinite(p.createdAt)||Date.now()<p.createdAt||Date.now()-p.createdAt>120000||
                  !Number.isInteger(p.relativeDx)||Math.abs(p.relativeDx)>750||!Number.isInteger(p.holds)||p.holds<0||p.holds>8||
                  !Number.isInteger(pitch)||Math.abs(pitch)>350||pitch!==0&&(action!=='probe'||p.relativeDx!==0||p.holds!==0)||
                  p.dockProfile!==undefined&&['first','upper'].indexOf(p.dockProfile)<0||upperDock&&action!=='boardPlatform'||
                  ['VK_W','VK_A','VK_S','VK_D'].indexOf(moveKey)<0||action!=='walk'&&!glide&&moveKey!=='VK_W'||
                  [200,400,800].indexOf(moveMs)<0||moveMs!==800&&(['walk','carefulWalk'].indexOf(action)<0&&!glide||p.holds>2)||
                  action==='carefulWalk'&&p.holds>2||
                  p.dodgeBefore!==undefined&&typeof p.dodgeBefore!=='boolean'||p.dodgeBefore===true&&(!(cryo||selectKaeya)||rescueCryo||p.combatReviewed!==true)||
                  ['walk','carefulWalk','jumpForward','boardPlatform','disembarkPlatform','carefulBoard','carefulDisembark','carefulDisembarkActive','carefulWind','carefulGlide','probe','windLaunch','glideForward','openDoor','openChest','activateMechanism','electroAttack','electroTrial','normalBurst','selectKaeya','selectTraveler','selectLisa','selectAmber','amberRescueCombat','travelerRescueCombat','kaeyaRescueCombat','kaeyaCombat','lisaCombat','travelerCombat','amberCombat','lisaRescueBurst','nativeCombat','collectLoot'].indexOf(action)<0||(jump||probe||wind||door||electro||trial||basic||selectKaeya||cryo||rescueBurst||nativeFight||loot)&&(p.holds!==0||p.relativeDx!==0&&['travelerRescueCombat','amberRescueCombat'].indexOf(action)<0)||glide&&(p.holds<1||p.holds>(careful?2:4)||Math.abs(p.relativeDx)>150)||
                  (electro||trial||basic||cryo||rescueBurst||nativeFight)&&p.combatReviewed!==true||!jump&&!probe&&!wind&&!door&&!electro&&!trial&&!basic&&!selectKaeya&&!cryo&&!rescueBurst&&!nativeFight&&!loot&&p.holds===0&&p.relativeDx===0||!Number.isInteger(p.witnessFrameId)||p.witnessFrameId>=p.frameId)
                    throw new Error('Fresh reviewed Lion movement permit and entry required');
                var prefix='observations/'+request.session+'/frame-'+String(p.witnessFrameId).padStart(4,'0'),w=JSON.parse(file.readTextSync(prefix+'.json'));
                if(!file.isExists(prefix+'.png')||Date.now()-w.timestamp>600000||!context.entry(w)||!probe&&!(rescueCryo?rescueCryoReady(w,w.timestamp):rescueBurst?rescueReady(w,w.timestamp):glide?guard.air(w,w.timestamp,request.session,careful?0.3:undefined):careful?guard.combat(w,w.timestamp,request.session):selectKaeya?guard.living(w,w.timestamp,request.session):cryo||nativeFight||jump||action==='carefulWalk'?guard.combat(w,w.timestamp,request.session):guard.field(w,w.timestamp,request.session)))
                    throw new Error('Saved healthy Lion domain witness required');
                if(activatedDock&&!context.reports.some(function(r){return r.session===request.session&&r.status==='completed'&&r.timestamp<=initial.timestamp&&r.details&&r.details.result&&r.details.result.interactionAttempted==='activateMechanism';}))
                    throw new Error('Current-session mechanism interaction receipt required');
                if(wind){
                  if(p.windTutorialFrameId===0){
                    var learned=context.reports.some(function(r){
                        var rr=r&&r.details&&r.details.result,es=r&&r.details&&r.details.inputEvents;
                        return (r.session===request.session||context.handoff&&[context.handoff.sourceSession,context.handoff.predecessorSession].indexOf(r.session)>=0)&&r.status==='completed'&&r.timestamp<=initial.timestamp&&
                            rr&&rr.step==='lionVisualMove'&&rr.airborneVerified===true&&rr.gliderAttempted===true&&Array.isArray(es)&&
                            es.filter(function(e){return e.type==='key'&&e.key==='VK_SPACE'&&e.durationMs===60;}).length===2;
                    });
                    if(!learned)throw new Error('Entry-validated session chain wind launch receipt required');
                  }else{
                    if(!Number.isInteger(p.windTutorialFrameId)||p.windTutorialFrameId>=p.frameId)throw new Error('Recorded wind tutorial required');
                    var tutorialPrefix='observations/'+request.session+'/frame-'+String(p.windTutorialFrameId).padStart(4,'0');
                    var tutorial=JSON.parse(file.readTextSync(tutorialPrefix+'.json'));
                    if(!file.isExists(tutorialPrefix+'.png')||Date.now()-tutorial.timestamp>600000||!context.entry(tutorial)||
                       !['Tap Space twice in a wind current to','ride it up'].every(function(text){return tutorial.ocr.filter(function(r){return r.text.trim()===text&&r.x>=750&&r.x<=1350&&r.y>=170&&r.y<=250;}).length===1;}))
                        throw new Error('Matching same-session wind tutorial witness required');
                  }
                }
                p.usedAt=Date.now();var saved=JSON.stringify(p);
                if(!file.writeTextSync('lion-visual-move.json',saved)||file.readTextSync('lion-visual-move.json')!==saved)throw new Error('Lion permit consumption failed');
                attempted=true;await boundedKey('VK_ESCAPE',60,current.frameId);await sleep(350);current=await observe();
                for(var poll=0;poll<3&&!movementReady(current);poll++){await sleep(150);current=await observe();}
                var started=Date.now(),hp=current.hud.health;
                if(!movementReady(current))throw new Error('Fresh healthy Lion HUD required');
                if((selectKaeya||cryo)&&actOneLionBubblePrompt(current)){
                    result.bubbleReleasePresses=0;
                    for(var escapeBubble=0;escapeBubble<6;escapeBubble++){
                        checkStop();ready();await boundedKey('VK_SPACE',60,current.frameId);result.bubbleReleasePresses++;await sleep(120);
                    }
                    current=await observe();
                    if(!movementReady(current)||actOneLionBubblePrompt(current))throw new Error('Bubble release or fresh combat HUD not verified');
                }
                if(board){
                    // Only for the two explicitly reviewed dock geometries:
                    // blue entrance paving or the upper dock's green-lit border.
                    // Poll locally: a screenshot followed by a remote command is
                    // too old for this moving platform.
                    var dockDeadline=Date.now()+15000,dockHits=0,docked=false,lastDockAt=0;
                    result.dockSamples=[];
                    while(Date.now()<dockDeadline){
                        checkStop();ready();
                        if(Date.now()-current.timestamp>600&&!(dockHits===1&&Date.now()-current.timestamp<850))current=await observe();
                        if(!(careful?guard.combat(current,Date.now(),request.session):guard.field(current,Date.now(),request.session))||current.hud.health.max!==hp.max||current.hud.health.current<hp.current)
                            throw new Error('Fresh healthy stationary dock HUD required');
                        var dockImage=null,dockAt=Date.now(),fractions=[];
                        try{
                            dockImage=captureGameRegion();
                            if(Number(dockImage.width)!==1920||Number(dockImage.height)!==1080)throw new Error('Dock capture geometry changed');
                            for(var dockX of (upperDock?[740,1300]:activatedDock?[740]:disembark?[650]:[740,1100])){
                                var dockCrop=null,dockHsv=null,dockMask=null;
                                try{
                                    dockCrop=dockImage.deriveCrop(dockX,upperDock?(dockX===740?800:785):activatedDock?430:disembark?350:770,upperDock?60:activatedDock?60:disembark?85:80,upperDock?16:disembark?80:30);
                                    dockHsv=dockCrop.srcMat.cvtColor(OpenCvSharp.OpenCvSharp.ColorConversionCodes.BGR2HSV,0);
                                    dockMask=dockHsv.inRange(upperDock?new OpenCvSharp.OpenCvSharp.Scalar(65,45,40):activatedDock?new OpenCvSharp.OpenCvSharp.Scalar(80,40,160):disembark?new OpenCvSharp.OpenCvSharp.Scalar(20,150,160):new OpenCvSharp.OpenCvSharp.Scalar(103,64,70),upperDock?new OpenCvSharp.OpenCvSharp.Scalar(85,255,140):activatedDock?new OpenCvSharp.OpenCvSharp.Scalar(100,255,255):disembark?new OpenCvSharp.OpenCvSharp.Scalar(33,255,255):new OpenCvSharp.OpenCvSharp.Scalar(125,255,255));
                                    fractions.push(Number(OpenCvSharp.OpenCvSharp.Cv2.countNonZero(dockMask))/(upperDock?960:activatedDock?4800:disembark?6800:2400));
                                }finally{dispose(dockMask);dispose(dockHsv);dispose(dockCrop);}
                            }
                        }finally{dispose(dockImage);}
                        checkStop();ready();
                        var dockFresh=Date.now()-dockAt<=250&&(careful?guard.combat(current,Date.now(),request.session):guard.field(current,Date.now(),request.session));
                        dockHits=dockFresh&&fractions.every(function(v){return Number.isFinite(v)&&v>=(upperDock?0.65:activatedDock?0.18:disembark?0.025:0.60)&&v<=1;})?(dockAt-lastDockAt<=300?dockHits+1:1):0;
                        lastDockAt=dockAt;result.dockSamples.push({at:dockAt,fractions:fractions,fresh:dockFresh});
                        if(dockHits>=2){docked=true;result.dockVerifiedAt=Date.now();break;}
                        await sleep(100);
                    }
                    if(!docked)throw new Error('No freshly docked platform within bounded wait');
                    await boundedKey('VK_W',disembark?600:400,current.frameId);result.moves=1;result.boardStepAttempted=true;result.disembarkAttempted=disembark;
                    await sleep(500);current=await observe();
                }
                if(jump&&!board){
                    var jumpEvent={type:'lionPlatformJump',keys:['VK_W','VK_SPACE'],durationMs:800,spaceDurationMs:60,frameId:current.frameId,startedAt:Date.now(),keysReleased:false};
                    events.push(jumpEvent);var jumpSpaceHeld=false;
                    try {
                        checkStop();ready();release();held='VK_W';keyDown('VK_W');
                        jumpSpaceHeld=true;keyDown('VK_SPACE');result.jumpAttempted=true;
                        var jumpDeadline=Date.now()+800,jumpSpaceDeadline=Date.now()+60;
                        while(Date.now()<jumpDeadline){
                            await sleep(Math.max(1,Math.min(50,jumpDeadline-Date.now(),jumpSpaceHeld?jumpSpaceDeadline-Date.now():50)));
                            checkStop();ready();
                            if(jumpSpaceHeld&&Date.now()>=jumpSpaceDeadline){keyUp('VK_SPACE');jumpSpaceHeld=false;}
                        }
                        result.moves=1;
                    } finally {
                        try {if(jumpSpaceHeld){keyUp('VK_SPACE');jumpSpaceHeld=false;}}
                        finally {release();jumpEvent.finishedAt=Date.now();jumpEvent.keysReleased=!jumpSpaceHeld&&held===null;}
                    }
                    await sleep(600);current=await observe();
                }
                if(loot){
                    result.pickupAttempts=[];
                    for(var pickup=0;pickup<4;pickup++){
                        if(!guard.field(current,Date.now(),request.session))break;
                        var lootKeys=current.ocr.filter(function(r){return r.text.trim()==='F'&&r.x>=1080&&r.x<=1160&&r.y>=350&&r.y<=700;});
                        if(lootKeys.length!==1)break;
                        var lootLabels=current.ocr.filter(function(r){return ['Fowl',"Wanderer's Advice","Adventurer's Flower"].indexOf(r.text.trim())>=0&&r.x>=1150&&r.x<=1510&&Math.abs(r.y-lootKeys[0].y)<=15;});
                        if(lootLabels.length!==1||result.pickupAttempts.indexOf(lootLabels[0].text)>=0)break;
                        await boundedKey('VK_F',60,current.frameId);result.pickupAttempts.push(lootLabels[0].text);await sleep(350);current=await observe();
                    }
                }
                if(nativeFight){
                    result.nativeFightAttempted=true;
                    var fightEvent={type:'lionDomainNativeFight',strategy:'English Lion Trial',timeoutMs:15000,frameId:current.frameId,startedAt:Date.now()};events.push(fightEvent);
                    try{await runStarterTrialAutoFight({createLinkedCancellationTokenSource:function(){return dispatcher.GetLinkedCancellationTokenSource();},
                        createAutoFightParam:function(){return new AutoFightParam('English Lion Trial');},runAutoFightTask:function(param,token){return dispatcher.RunAutoFightTask(param,token);}},
                        function(){checkStop();ready();},{sleep:sleep});}catch(fightError){result.nativeFightOutcome=String(fightError.message||fightError);}finally{fightEvent.finishedAt=Date.now();release();}
                    await sleep(250);current=await observe();
                }
                if(rescueBurst){
                    checkStop();ready();await boundedKey('VK_Q',60,current.frameId);result.burstAttempted=true;
                    await sleep(450);current=await observe();
                }
                if(selectKaeya){
                    if(p.dodgeBefore===true){checkStop();ready();await boundedKey('VK_SHIFT',80,current.frameId);result.dodgeAttempted=true;await sleep(120);}
                    await boundedKey(action==='selectTraveler'?'VK_1':action==='selectLisa'?'VK_4':action==='selectAmber'?'VK_2':'VK_3',p.dodgeBefore===true?150:60,current.frameId);
                    result.characterSelectionAttempted=action==='selectTraveler'?'Traveler':action==='selectLisa'?'Lisa':action==='selectAmber'?'Amber':'Kaeya';
                    await sleep(350);current=await observe();
                    var selectedMax=current.hud.health&&current.hud.health.max;
                    result.characterSelectionVerified=guard.living(current,Date.now(),request.session)&&
                        (action==='selectTraveler'?[1288,1363].indexOf(selectedMax)>=0:action==='selectLisa'?selectedMax===1196:action==='selectAmber'?selectedMax===1186:[1379,1459].indexOf(selectedMax)>=0);
                    if(p.dodgeBefore===true&&!result.characterSelectionVerified)throw new Error('Reviewed dodge switch did not verify target character');
                }
                if(door){
                    if(action==='activateMechanism'){
                        var mechanismDeadline=Date.now()+15000;
                        while(!current.ocr.some(function(r){return r.text.trim()==='Start'&&r.x>=1150&&r.x<=1450&&r.y>=480&&r.y<=590;})&&Date.now()<mechanismDeadline){
                            checkStop();ready();await sleep(150);current=await observe();
                            if(!guard.field(current,Date.now(),request.session)||current.hud.health.current<hp.current)throw new Error('Healthy stationary mechanism wait required');
                        }
                    }
                    if(current.ocr.filter(function(r){return (action==='openChest'?/^(Common|Exquisite|Precious) Chest$/.test(r.text.trim()):r.text.trim()===(action==='activateMechanism'?'Start':'Open Door'))&&r.x>=1150&&r.x<=1450&&r.y>=480&&r.y<=590;}).length!==1||
                       current.ocr.filter(function(r){return r.text.trim()==='F'&&r.x>=1080&&r.x<=1160&&r.y>=480&&r.y<=590;}).length!==1)
                        throw new Error('Fresh exact Lion interaction label and F prompt required');
                    await boundedKey('VK_F',60,current.frameId);result.interactionAttempted=action;result.doorInteractionAttempted=action==='openDoor';await sleep(500);current=await observe();
                }
                if(electro){
                    if(hp.max!==1196)throw new Error('Fresh Lisa trial required for reviewed Electro attack');
                    result.attacks=0;result.skillAttempted=true;
                    await boundedKey('VK_E',3000,current.frameId);await sleep(250);current=await observe();
                    for(var attack=0;attack<4;attack++){
                        if(!guard.field(current,Date.now(),request.session)||current.hud.health.max!==hp.max||hp.current-current.hud.health.current>hp.max*0.1||Date.now()-started>20000)
                            throw new Error('Electro health, HUD or deadline stopped attack');
                        checkStop();ready();await boundedKey('VK_LBUTTON',60,current.frameId);result.attacks++;await sleep(250);current=await observe();
                    }
                }
                if(trial||basic||cryo){
                    function trialReady(){return (rescueCryo?rescueCryoReady(current,Date.now()):cryo?guard.combat(current,Date.now(),request.session):guard.field(current,Date.now(),request.session))&&current.hud.health.max===(cryo?hp.max:1196)&&hp.current-current.hud.health.current<=hp.max*0.1;}
                    function cooldown(){var values=current.ocr.filter(function(r){return /^\d{1,2}(\.\d)?$/.test(r.text.trim())&&r.x>=1660&&r.x<=1740&&r.y>=950&&r.y<=1010;});return values.length?Math.max.apply(null,values.map(function(r){return Number(r.text);})):0;}
                    result.attacks=0;
                    if(basic){
                        var countRows=current.ocr.filter(function(r){return /^Opponents Defeated: [0-3]\/4$/.test(r.text.trim())&&r.x>=65&&r.x<=500&&r.y>=230&&r.y<=280;});
                        var timeRows=current.ocr.filter(function(r){return /^Time Remaining: (?:[1-9]|1[0-5])s$/.test(r.text.trim())&&r.x>=65&&r.x<=500&&r.y>=280&&r.y<=330;});
                        if(countRows.length!==1||timeRows.length!==1)throw new Error('Fresh active four-enemy challenge count and timer required');
                        result.challengeBefore={count:countRows[0].text,timer:timeRows[0].text,frameId:current.frameId};
                    }
                    if(cryo){
                        if(action==='kaeyaRescueCombat'){checkStop();ready();await boundedKey('VK_W',600,current.frameId);result.moves++;await sleep(100);}
                        if((action==='lisaCombat'?hp.max!==1196:(action==='amberCombat'||action==='amberRescueCombat')?hp.max!==1186:(action==='travelerCombat'||action==='travelerRescueCombat')?[1288,1363].indexOf(hp.max)<0:[1379,1459].indexOf(hp.max)<0)||p.combatReviewed!==true)throw new Error('Fresh matching character and visually reviewed combat required');
                        if(p.dodgeBefore===true){checkStop();ready();await boundedKey('VK_SHIFT',80,current.frameId);result.dodgeAttempted=true;await sleep(120);}
                        await boundedKey('VK_Q',p.dodgeBefore===true?150:60,current.frameId);result.burstAttempted=true;await sleep(p.dodgeBefore===true?650:400);
                        checkStop();ready();await boundedKey('VK_E',action==='lisaCombat'?3000:(action==='travelerCombat'||action==='travelerRescueCombat')?2000:p.dodgeBefore===true?150:60,current.frameId);result.skillAttempted=true;await sleep(350);current=await observe();
                    }
                    if(trial){
                    for(var cdPoll=0;cdPoll<10&&cooldown()>0;cdPoll++){
                        if(!trialReady())throw new Error('Trial health or HUD stopped cooldown wait');
                        await sleep(600);current=await observe();
                    }
                    if(!trialReady()||cooldown()>0)throw new Error('Fresh ready Lisa skill required for trial');
                    result.attacks=0;result.tapAttempted=true;
                    await boundedKey('VK_E',60,current.frameId);await sleep(1400);current=await observe();
                    if(!trialReady()||cooldown()>0)throw new Error('Trial health or skill cooldown stopped charge');
                    result.skillAttempted=true;await boundedKey('VK_E',3000,current.frameId);await sleep(250);current=await observe();
                    }
                    for(var burst=0;burst<3;burst++){
                        if(!trialReady()||Date.now()-started>30000)throw new Error('Trial health, HUD or deadline stopped burst');
                        // One reviewed 1.44-second burst; verify health between
                        // bursts instead of spending the challenge on four OCRs.
                        for(var hit=0;hit<4;hit++){checkStop();ready();await boundedKey('VK_LBUTTON',60,current.frameId);result.attacks++;await sleep(300);}
                        current=await observe();
                    }
                }
                if(p.relativeDx){checkStop();ready();events.push({type:'lionVisualTurn',dx:p.relativeDx,frameId:current.frameId,startedAt:Date.now()});moveMouseBy(p.relativeDx,0);result.turns++;await sleep(180);current=await observe();}
                if(pitch){checkStop();ready();if(!movementReady(current))throw new Error('Fresh healthy Lion camera HUD required');events.push({type:'lionVisualPitch',dy:pitch,frameId:current.frameId,startedAt:Date.now()});moveMouseBy(0,pitch);result.turns++;await sleep(180);current=await observe();}
                if(wind){
                    if(!(careful?guard.combat(current,Date.now(),request.session):guard.field(current,Date.now(),request.session)))throw new Error('Fresh healthy party wind launch required');
                    // Jump retains E/Q on the live HUD. Execute the tutorial's
                    // bounded double tap before capture latency can end the jump.
                    await boundedKey('VK_SPACE',60,current.frameId);result.jumpAttempted=true;await sleep(150);
                    await boundedKey('VK_SPACE',60,current.frameId);result.gliderAttempted=true;await sleep(350);current=await observe();
                    for(var rise=0;rise<6&&guard.air(current,Date.now(),request.session,careful?0.3:undefined);rise++){await sleep(600);current=await observe();}
                    result.airborneVerified=guard.air(current,Date.now(),request.session,careful?0.3:undefined);
                }
                while(result.moves<p.holds){
                    checkStop();ready();
                    if(glide&&(careful?guard.combat(current,Date.now(),request.session):guard.field(current,Date.now(),request.session))){result.landingVerified=true;break;}
                    // OCR persistence/pinning can outlive the freshness window.
                    // Reobserve without input; never relax the final gate.
                    for(var refresh=0;refresh<2&&!movementReady(current)&&
                        current.hud.health&&(glide||current.hud.groundControls===true)&&!current.hud.climbing&&
                        !current.hud.dialogueReady&&!current.hud.choice&&!current.hud.tutorialStep;refresh++){
                        await sleep(150);current=await observe();
                    }
                    if(glide&&(careful?guard.combat(current,Date.now(),request.session):guard.field(current,Date.now(),request.session))){result.landingVerified=true;break;}
                    if(!movementReady(current)||Date.now()-started>25000||current.hud.health.max!==hp.max||hp.current-current.hud.health.current>hp.max*0.1)
                        throw new Error('Lion state, health or deadline stopped movement; observationAgeMs='+String(Date.now()-current.timestamp));
                    if(current.hud.interact){result.reason='Interaction reached';break;}
                    await boundedKey(moveKey,moveMs,current.frameId);result.moves++;await sleep(150);current=await observe();
                }
                result.status='completed';result.reason=result.reason||'Bounded Lion approach ended; inspect terrain';
            }catch(e){error=String(e&&e.message||e);result.reason=error;}
            release();
            // Automatic NPC dialogue first hides the HUD, then displays text.
            // Settle that transition before asking a pause-only watchdog to act.
            for(var transitionPoll=0;attempted&&transitionPoll<6&&!current.hud.health&&!current.hud.dialogueReady&&!current.hud.choice;transitionPoll++){
                await sleep(400);current=await observe();
            }
            result.fieldFrameId=current.frameId;result.fieldHealth=current.hud.health;
            if(current.hud.dialogueReady||current.hud.choice){result.dialoguePending=true;result.pauseVerified=false;return result;}
            if(attempted)return await finishWithLocalPause(protector,this,initial,observe,current.frameId,result,error);
            return result;
        },
        runLionLocalPause: async function(initial,observe){
            if(!request||request.mission!=='questStep'||request.step!=='lionLocalPause'||initial.session!==request.session)
                throw new Error('Pinned Lion pause request required');
            if(!lionLiveContext(initial).entry(initial)||initial.map!==null)throw new Error('Verified current Lion entry required');
            if(file.isExists('lion-exit-review.json')){
                var p=JSON.parse(file.readTextSync('lion-exit-review.json'));
                if(p.session===request.session&&p.frameId===request.expectedFrameId&&p.reviewed===true&&!p.usedAt&&Number.isFinite(p.createdAt)&&Date.now()>=p.createdAt&&Date.now()-p.createdAt<=120000){
                    var o=initial;
                    if(p.action==='cancelDifficulty'||p.action==='confirmLowerDifficulty'){
                        var confirmLower=p.action==='confirmLowerDifficulty';
                        if(confirmLower&&(p.userApproved!==true||p.scope!=='Temple of the Lion'))throw new Error('Explicit temple-only difficulty approval required');
                        var expectedDifficulty=['Are you sure you want to lower the difficulty','and exit this challenge?','The next time you start this challenge, you will','start at the lower difficulty. After switching,','you will be unable to reset this to its original','difficulty.'];
                        if(Date.now()-o.timestamp>1000||!expectedDifficulty.every(function(t){return o.ocr.filter(function(r){return r.text.trim()===t&&r.x>=550&&r.x<=1000&&r.y>=390&&r.y<=640;}).length===1;})||
                           o.ocr.filter(function(r){return r.text.trim()==='Cancel'&&r.x>=700&&r.x<=780&&r.y>=720&&r.y<=780;}).length!==1||
                           confirmLower&&o.ocr.filter(function(r){return r.text.trim()==='Confirm'&&r.x>=1100&&r.x<=1200&&r.y>=720&&r.y<=780;}).length!==1)throw new Error('Exact paused difficulty confirmation required');
                        p.usedAt=Date.now();var cancelSaved=JSON.stringify(p);if(!file.writeTextSync('lion-exit-review.json',cancelSaved)||file.readTextSync('lion-exit-review.json')!==cancelSaved)throw new Error('Difficulty review consumption failed');
                        checkStop();ready();events.push({type:confirmLower?'lionDifficultyLowerConfirmed':'lionDifficultyCancel',frameId:o.frameId,startedAt:Date.now()});
                        if(confirmLower)events.push({type:'lionLeaveDomain',reason:'user-approved-temple-difficulty',frameId:o.frameId,startedAt:Date.now()});
                        click(confirmLower?1180:770,755);await sleep(500);o=await observe();
                        if(confirmLower){
                            for(var difficultyExitPoll=0;difficultyExitPoll<12&&!o.hud.health&&!actOneLocalPauseProof(o,Date.now(),request.session);difficultyExitPoll++){checkStop();await sleep(500);o=await observe();}
                            return await finishWithLocalPause(loadLocalPause(),this,initial,observe,o.frameId,
                                {status:'completed',step:'lionLocalPause',difficultyChangeAttempted:true,leaveDomainAttempted:true,fieldFrameId:o.frameId,questComplete:false},null);
                        }
                        return {status:'completed',step:'lionLocalPause',difficultyCancelled:true,pauseProof:actOneLocalPauseProof(o,Date.now(),request.session),frameId:o.frameId,questComplete:false};
                    }
                    var exitInitialProof=actOneLocalPauseProof(o,Date.now(),request.session);
                    if(p.action==='continue'&&exitInitialProof&&exitInitialProof.kind==='domain'){
                        var continueRows=exitInitialProof.evidence.filter(function(r){return r.text.trim()==='Continue Challenge';});
                        if(continueRows.length!==1)throw new Error('Exact continue domain control required');
                        p.usedAt=Date.now();var continueSaved=JSON.stringify(p);if(!file.writeTextSync('lion-exit-review.json',continueSaved)||file.readTextSync('lion-exit-review.json')!==continueSaved)throw new Error('Continue review consumption failed');
                        var continueRow=continueRows[0];checkStop();ready();events.push({type:'lionContinueDomain',frameId:o.frameId,startedAt:Date.now()});
                        try{click(Math.round(continueRow.x+continueRow.width/2),Math.round(continueRow.y+continueRow.height/2));await sleep(600);o=await observe();}finally{release();}
                        return await finishWithLocalPause(loadLocalPause(),this,initial,observe,o.frameId,
                            {status:'completed',step:'lionLocalPause',continueDomainAttempted:true,fieldFrameId:o.frameId,questComplete:false},null);
                    }
                    if(p.action==='leave'&&exitInitialProof&&exitInitialProof.kind==='domain'){
                        var leaveRows=o.ocr.filter(function(r){return r.text.trim()==='Leave Domain?'&&r.x>=750&&r.x<=1000&&r.y>=620&&r.y<=700;});
                        if(leaveRows.length!==1)throw new Error('Exact leave domain control required');
                        p.usedAt=Date.now();var leaveSaved=JSON.stringify(p);if(!file.writeTextSync('lion-exit-review.json',leaveSaved)||file.readTextSync('lion-exit-review.json')!==leaveSaved)throw new Error('Exit review consumption failed');
                        checkStop();ready();events.push({type:'lionLeaveDomain',frameId:o.frameId,startedAt:Date.now()});click(960,655);await sleep(500);o=await observe();
                        for(var exitPoll=0;exitPoll<12&&!o.hud.health&&!actOneLocalPauseProof(o,Date.now(),request.session);exitPoll++){checkStop();await sleep(500);o=await observe();}
                        return await finishWithLocalPause(loadLocalPause(),this,initial,observe,o.frameId,
                            {status:'completed',step:'lionLocalPause',leaveDomainAttempted:true,fieldFrameId:o.frameId,questComplete:false},null);
                    }
                    if(p.action==='lowerDifficulty'&&exitInitialProof&&exitInitialProof.kind==='domain'){
                        var lowerRows=o.ocr.filter(function(r){return r.text.trim()==='Lower Difficulty'&&r.x>=800&&r.x<=900&&r.y>=500&&r.y<=570;});
                        if(lowerRows.length!==1)throw new Error('Exact lower difficulty control required');
                        p.usedAt=Date.now();var lowerSaved=JSON.stringify(p);if(!file.writeTextSync('lion-exit-review.json',lowerSaved)||file.readTextSync('lion-exit-review.json')!==lowerSaved)throw new Error('Difficulty review consumption failed');
                        checkStop();ready();events.push({type:'lionDifficultyInspect',frameId:o.frameId,startedAt:Date.now()});click(960,540);await sleep(500);o=await observe();
                        return {status:'completed',step:'lionLocalPause',difficultyInspectAttempted:true,frameId:o.frameId,questComplete:false};
                    }
                    if(p.action==='open'&&(actOneWolfCharacterMenuVisible(o,Date.now())||exitInitialProof&&exitInitialProof.kind==='inventory')){
                        p.usedAt=Date.now();var value=JSON.stringify(p);if(!file.writeTextSync('lion-exit-review.json',value)||file.readTextSync('lion-exit-review.json')!==value)throw new Error('Exit review consumption failed');
                        try{checkStop();ready();await boundedKey('VK_ESCAPE',60,o.frameId);await sleep(600);o=await observe();
                            if(o.hud.groundControls===true&&o.hud.health&&o.hud.health.current>0){checkStop();ready();await boundedKey('VK_ESCAPE',60,o.frameId);await sleep(600);o=await observe();}}
                        finally{release();}
                        var proof=actOneLocalPauseProof(o,Date.now(),request.session);
                        if(proof&&proof.kind==='domain')return {status:'completed',step:'lionLocalPause',pauseVerified:true,pauseProof:proof,frameId:o.frameId,questComplete:false};
                        return await finishWithLocalPause(loadLocalPause(),this,initial,observe,o.frameId,{status:'stopped',step:'lionLocalPause',questComplete:false},null);
                    }
                }
            }
            return await finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,
                {status:'completed',step:'lionLocalPause',questComplete:false},null);
        },
        runLisaVisualMove: async function(initial,observe){
            var protector=loadLocalPause(),gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            var current=initial,attempted=false,error=null,started=Date.now();
            var result={status:'stopped',step:'lisaVisualMove',moves:0,turns:0,questComplete:false};
            try{
                var p=JSON.parse(file.readTextSync('lisa-visual-move.json'));
                var expectedObjective=p.objective===undefined?'Meet Lisa at the temple':p.objective;
                function fieldReady(o,now,session,ratio){return actOneLionFieldWorld(o,now,session,ratio,false,expectedObjective);}
                // A root-reviewed relative turn does not depend on compass/GPS
                // estimates, which can disagree with the visible map boundary.
                var relative=Object.prototype.hasOwnProperty.call(p,'relativeDx');
                var moveKey=p.moveKey===undefined?'VK_W':p.moveKey;
                var validDirection=relative?(!Object.prototype.hasOwnProperty.call(p,'heading')&&
                    Number.isInteger(p.relativeDx)&&Math.abs(p.relativeDx)<=750):
                    (Number.isFinite(p.heading)&&p.heading>=0&&p.heading<360);
                if(!request||request.step!=='lisaVisualMove'||!gate(initial,Date.now(),request.session)||
                   !p||p.session!==request.session||p.frameId!==request.expectedFrameId||p.reviewed!==true||p.usedAt||
                   !Number.isFinite(p.createdAt)||Date.now()<p.createdAt||Date.now()-p.createdAt>120000||
                   !Number.isInteger(p.holds)||p.holds<0||p.holds>8||!validDirection||
                   ['Meet Lisa at the temple','Talk to Lisa','Enter the temple'].indexOf(expectedObjective)<0||
                   ['VK_W','VK_A','VK_S','VK_D'].indexOf(moveKey)<0||(!relative&&moveKey!=='VK_W')||
                   (p.holds===0&&(!relative||p.relativeDx===0))||
                   !Number.isInteger(p.witnessFrameId)||p.witnessFrameId>=p.frameId)throw new Error('Fresh reviewed visual movement permit required');
                var prefix='observations/'+request.session+'/frame-'+String(p.witnessFrameId).padStart(4,'0');
                var witness=JSON.parse(file.readTextSync(prefix+'.json'));
                if(!file.isExists(prefix+'.png')||Date.now()-witness.timestamp>600000||
                   !fieldReady(witness,witness.timestamp,request.session,0.6))throw new Error('Saved owned Lisa field witness required');
                p.usedAt=Date.now();var saved=JSON.stringify(p);
                if(!file.writeTextSync('lisa-visual-move.json',saved)||file.readTextSync('lisa-visual-move.json')!==saved)throw new Error('Visual permit consumption failed');
                attempted=true;await boundedKey('VK_ESCAPE',60,current.frameId);await sleep(350);current=await observe();
                for(var poll=0;poll<3&&!fieldReady(current,Date.now(),request.session,0.6);poll++){await sleep(150);current=await observe();}
                var baseline=current.hud.health;
                while(result.moves<p.holds||relative&&result.turns===0&&p.relativeDx!==0){
                    checkStop();ready();
                    for(var settle=0;settle<2&&!fieldReady(current,Date.now(),request.session,0.6)&&
                        current.hud.climbing===false&&!current.hud.auto&&!current.hud.journal&&!current.hud.bigMap&&
                        !current.hud.dialogueReady&&!current.hud.choice&&current.hud.health&&
                        current.hud.health.current/current.hud.health.max>=0.6;settle++){
                        await sleep(150);current=await observe();checkStop();
                    }
                    if(Date.now()-started>25000||!fieldReady(current,Date.now(),request.session,0.6)||
                       !baseline||current.hud.health.max!==baseline.max||baseline.current-current.hud.health.current>baseline.max*0.1)
                        throw new Error('Visual movement deadline, health, objective or grounded guard stopped');
                    if(relative&&result.turns===0&&p.relativeDx!==0){
                        events.push({type:'lisaVisualRelativeTurn',dx:p.relativeDx,frameId:current.frameId,startedAt:Date.now()});
                        moveMouseBy(p.relativeDx,0);result.turns++;await sleep(180);current=await observe();continue;
                    }
                    var angle=relative?0:Number(genshin.getCameraOrientation()),diff=relative?0:(angle-p.heading+540)%360-180;
                    if(!Number.isFinite(angle))throw new Error('Fresh compass unavailable');
                    if(Math.abs(diff)>8){
                        if(++result.turns>8)throw new Error('Visual heading did not converge');
                        var dx=Math.max(-750,Math.min(750,Math.round(-8*diff)));
                        events.push({type:'lisaVisualTurn',dx:dx,heading:p.heading,frameId:current.frameId,startedAt:Date.now()});
                        moveMouseBy(dx,0);await sleep(180);current=await observe();continue;
                    }
                    events.push({type:'lisaVisualForward',key:moveKey,heading:relative?null:p.heading,relative:relative,durationMs:800,frameId:current.frameId,startedAt:Date.now()});
                    await boundedKey(moveKey,800,current.frameId);result.moves++;await sleep(150);current=await observe();
                }
                result.status='completed';result.reason='Reviewed visual movement budget completed; inspect terrain';
            }catch(e){error=String(e&&e.message||e);result.reason=error;}
            result.fieldFrameId=current.frameId;result.fieldHealth=current.hud.health;result.inputMs=result.moves*800;
            if(attempted)return await finishWithLocalPause(protector,this,initial,observe,current.frameId,result,error);
            return result;
        },
        runLisaGlide: async function(initial,observe){
            var protector=loadLocalPause(),gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            var current=initial,attempted=false,error=null,started=Date.now();
            var result={status:'stopped',step:'lisaGlide',moves:0,launchAttempted:false,questComplete:false};
            try{
                var p=JSON.parse(file.readTextSync('lisa-glide.json'));
                if(!request||request.step!=='lisaGlide'||!gate(initial,Date.now(),request.session)||!p||
                   p.session!==request.session||p.frameId!==request.expectedFrameId||p.reviewed!==true||p.usedAt||
                   !Number.isFinite(p.createdAt)||Date.now()<p.createdAt||Date.now()-p.createdAt>120000||
                   ['launch','continue'].indexOf(p.action)<0||!Number.isInteger(p.relativeDx)||Math.abs(p.relativeDx)>750||
                   !Number.isInteger(p.holds)||p.holds<0||p.holds>8||!Number.isInteger(p.witnessFrameId)||p.witnessFrameId>=p.frameId)
                    throw new Error('Fresh reviewed glide permit required');
                var prefix='observations/'+request.session+'/frame-'+String(p.witnessFrameId).padStart(4,'0');
                var w=JSON.parse(file.readTextSync(prefix+'.json'));
                if(!file.isExists(prefix+'.png')||Date.now()-w.timestamp>600000||
                   !(p.action==='launch'?actOneLionFieldWorld(w,w.timestamp,request.session,0.6):actOneLisaAirfield(w,w.timestamp,request.session)))
                    throw new Error('Owned reviewed launch or airborne witness required');
                p.usedAt=Date.now();var saved=JSON.stringify(p);
                if(!file.writeTextSync('lisa-glide.json',saved)||file.readTextSync('lisa-glide.json')!==saved)throw new Error('Glide permit consumption failed');
                attempted=true;checkStop();ready();await boundedKey('VK_ESCAPE',60,current.frameId);await sleep(350);current=await observe();
                for(var poll=0;poll<3&&!actOneLionFieldWorld(current,Date.now(),request.session,0.6)&&!actOneLisaAirfield(current,Date.now(),request.session);poll++){await sleep(150);current=await observe();}
                if(!(p.action==='launch'?actOneLionFieldWorld(current,Date.now(),request.session,0.6):actOneLisaAirfield(current,Date.now(),request.session)))
                    throw new Error('Fresh matching launch or airborne HUD required');
                var hp=current.hud.health;
                if(p.relativeDx){checkStop();ready();events.push({type:'lisaGlideTurn',dx:p.relativeDx,frameId:current.frameId,startedAt:Date.now()});moveMouseBy(p.relativeDx,0);await sleep(180);current=await observe();}
                if(p.action==='launch'){
                    if(!actOneLionFieldWorld(current,Date.now(),request.session,0.6)||current.hud.health.max!==1288)throw new Error('Fresh owned Traveler launch required');
                    result.launchAttempted=true;events.push({type:'lisaGlideLaunch',frameId:current.frameId,startedAt:Date.now()});
                    await boundedKey('VK_SPACE',60,current.frameId);await sleep(150);
                    await boundedKey('VK_W',800,current.frameId);await sleep(100);
                    await boundedKey('VK_SPACE',60,current.frameId);await sleep(250);current=await observe();
                }
                while(result.moves<p.holds&&actOneLisaAirfield(current,Date.now(),request.session)){
                    checkStop();ready();if(Date.now()-started>25000||hp.current-current.hud.health.current>hp.max*0.1)throw new Error('Glide deadline or health loss stopped');
                    await boundedKey('VK_W',800,current.frameId);result.moves++;await sleep(150);current=await observe();
                }
                result.airborneVerified=actOneLisaAirfield(current,Date.now(),request.session);
                result.groundVerified=actOneLionFieldWorld(current,Date.now(),request.session,0.6);
                result.status=result.airborneVerified||result.groundVerified?'completed':'stopped';result.reason='Bounded descent ended; inspect airborne or landing evidence';
            }catch(e){error=String(e&&e.message||e);result.reason=error;}
            result.fieldFrameId=current.frameId;result.fieldHealth=current.hud.health;
            if(attempted)return await finishWithLocalPause(protector,this,initial,observe,current.frameId,result,error);
            return result;
        },
        runLisaCloseThreat: async function(initial,observe){
            var protector=loadLocalPause(),gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            var cameraOnly=request&&request.step==='lisaLookDown';
            if(!request||request.mission!=='questStep'||['lisaCloseThreat','lisaLookDown'].indexOf(request.step)<0||!gate(initial,Date.now(),request.session))
                return {status:'stopped',step:'lisaCloseThreat',reason:'Fresh Food inventory required',questComplete:false};
            var current=initial,result={status:'stopped',step:request.step,attacks:0,questComplete:false},error=null;
            try{
                checkStop();ready();await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(350);current=await observe();
                for(var poll=0;poll<3&&!actOneLionFieldWorld(current,Date.now(),request.session,cameraOnly?0.6:0.4);poll++){await sleep(150);current=await observe();}
                var hp=current.hud.health;
                // Root requested this bounded recovery after viewing the nearby
                // threat. Its almost empty bar/level can be occluded by Kaeya;
                // plain melee needs the fresh safe player HUD, not readable enemy text.
                if(!actOneLionFieldWorld(current,Date.now(),request.session,cameraOnly?0.6:0.4)||!hp||!cameraOnly&&hp.max!==1379)
                    throw new Error('Fresh living owned Kaeya and exact Lisa field required');
                var baseline=hp.current;
                if(cameraOnly){checkStop();ready();events.push({type:'lisaCameraPitch',dy:500,frameId:current.frameId,startedAt:Date.now()});moveMouseBy(0,500);await sleep(300);current=await observe();}
                for(var i=0;i<(cameraOnly?0:4);i++){
                    if(!actOneLionFieldWorld(current,Date.now(),request.session,0.4)||current.hud.health.max!==1379||baseline-current.hud.health.current>137)
                        throw new Error('Close-threat health/ground guard stopped');
                    checkStop();ready();await boundedKey('VK_LBUTTON',60,current.frameId);result.attacks++;await sleep(160);
                    current=await observe();
                }
                result.status='completed';result.reason=cameraOnly?'One downward camera adjustment; inspect terrain':'Four bounded melee presses; inspect threat outcome';
            }catch(e){error=String(e&&e.message||e);result.reason=error;}
            result.fieldFrameId=current.frameId;result.fieldHealth=current.hud.health;
            return await finishWithLocalPause(protector,this,initial,observe,current.frameId,result,error);
        },
        runLisaTravelAmber: async function(initial,observe){
            var h=initial.hud,rows=initial.ocr,protector=loadLocalPause();
            var traveler=request&&request.step==='lisaTravelTraveler',label=traveler?'Lumina':'Amber',slot=traveler?'1':'2',y0=traveler?280:350,y1=traveler?350:460;
            if(!request||['lisaTravelAmber','lisaTravelTraveler'].indexOf(request.step)<0||!actOneLocalPauseInputReady(initial,Date.now(),request.session)||
               !h.world||!h.groundControls||h.climbing||!h.health||h.health.current/h.health.max<0.4||h.enemyBars.length||
               rows.filter(function(r){return r.text.trim()==='Meet Lisa at the temple';}).length!==1||
               rows.filter(function(r){return r.text.trim()===label&&r.x>=1600&&r.y>=y0&&r.y<=y1;}).length!==1||
               rows.filter(function(r){return r.text.trim()===slot&&r.x>=1830&&r.x<=1900&&r.y>=y0&&r.y<=y1;}).length!==1)
                return {status:'stopped',step:'lisaTravelAmber',reason:'Fresh safe Lisa field and explicit Amber slot required',questComplete:false};
            var result=null,error=null;
            try{
                checkStop();ready();await boundedKey(traveler?'VK_1':'VK_2',60,initial.frameId);await sleep(1200);
                var current=await observe();
                var selected=current.hud.health&&current.hud.health.max===(traveler?1288:1186)&&
                    !current.ocr.some(function(r){return /Cannot switch character now/i.test(r.text);});
                result={status:selected?'completed':'stopped',step:request.step,selected:selected,
                    reason:selected?'Requested character verified by owned health identity':'Character switch was not verified',fieldFrameId:current.frameId,fieldPosition:current.map,
                    fieldHealth:current.hud.health,questComplete:false};
            }catch(e){error=String(e&&e.message||e);}
            return await finishWithLocalPause(protector,this,initial,observe,initial.frameId,result,error);
        },
        runLisaTempleTeleport: async function(initial,observe){
            var protector=loadLocalPause(),result=null,error=null;
            if(!request||request.mission!=='questStep'||request.step!=='lisaTempleTeleport'||
               !actOneLisaUnlockedTemplePanel(initial,Date.now(),request.session))
                return {status:'stopped',step:'lisaTempleTeleport',teleportAttempted:false,reason:'Fresh unlocked Lion temple panel required',questComplete:false};
            try{
                checkStop();ready();var target=initial.ocr.filter(function(r){return r.text.trim()==='Teleport'&&r.x>=1550&&r.x<=1750&&r.y>=970&&r.y<=1035;})[0];
                events.push({type:'lisaTempleTeleport',frameId:initial.frameId,startedAt:Date.now()});
                click(Math.round(target.x+target.width/2),Math.round(target.y+target.height/2));
                var current=null,arrived=false;
                for(var poll=0;poll<20;poll++){
                    checkStop();await sleep(500);current=await observe();
                    if(actOneLionFieldWorld(current,Date.now(),request.session,0,true)&&
                       current.hud.objectives.indexOf('Enter the temple')>=0&&current.ocr.some(function(r){return r.text.trim()==='Temple of the Lion'&&r.x>1050&&r.x<1600&&r.y>400&&r.y<700;})){arrived=true;break;}
                }
                result={status:arrived?'completed':'stopped',step:'lisaTempleTeleport',teleportAttempted:true,arrivalVerified:arrived,
                    fieldFrameId:current&&current.frameId,fieldHealth:current&&current.hud.health,questComplete:false};
            }catch(e){error=String(e&&e.message||e);}
            return await finishWithLocalPause(protector,this,initial,observe,initial.frameId,result,error);
        },
        runLisaTempleMapInspect: async function(initial,observe){
            var protector=loadLocalPause(),proof=actOneLocalPauseProof(initial,Date.now(),request.session);
            if(request&&request.mission==='questStep'&&request.step==='lisaTempleMapInspect'&&actOneLisaLockedTemplePanel(initial,Date.now(),request.session)){
                checkStop();ready();await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(350);
                return await finishWithLocalPause(protector,this,initial,observe,initial.frameId,
                    {status:'completed',step:'lisaTempleMapInspect',lockedTemplePanelClosed:true,questComplete:false},null);
            }
            if(!request||request.mission!=='questStep'||request.step!=='lisaTempleMapInspect'||
               !proof||proof.kind!=='map'||!initial.ocr.some(function(r){return /^(Starfell Valley|Galesong Hill)$/.test(r.text.trim());}))
                return {status:'stopped',step:'lisaTempleMapInspect',reason:'Fresh Mondstadt regional map required',mapClickAttempted:false,questComplete:false};
            var result=null,error=null,started=Date.now();
            try{
                checkStop();ready();
                // Fixed Temple of the Lion point, from the installed native tp.json (id 22).
                // Inspect only: an unopened domain must never be assumed teleportable.
                if(!initial.ocr.some(function(r){return r.text.trim()==='Temple of the Lion';}))
                    await genshin.clickMapPoint(-1436.901,1659.013);
                await sleep(500);
                var current=await observe();
                var labels=current.ocr.filter(function(r){return r.text.trim()==='Temple of the Lion'&&r.x>=1200&&r.x<=1550&&r.y>=500&&r.y<=950;});
                if(labels.length===1&&actOneLocalPauseProof(current,Date.now(),request.session)){
                    checkStop();ready();click(Math.round(labels[0].x+labels[0].width/2),Math.round(labels[0].y+labels[0].height/2));
                    await sleep(500);current=await observe();
                }
                result={status:'completed',step:'lisaTempleMapInspect',mapClickAttempted:true,
                    inspectionFrameId:current.frameId,nativeMapMs:Date.now()-started,questComplete:false};
                if(actOneLisaLockedTemplePanel(current,Date.now(),request.session)){
                    result.waypointLocked=true;checkStop();ready();await boundedKey('VK_ESCAPE',60,current.frameId);await sleep(350);
                }
            }catch(e){error=String(e&&e.message||e);}
            return await finishWithLocalPause(protector,this,initial,observe,initial.frameId,result,error);
        },
        runLisaWindriseTeleport: async function(initial,observe){
            var protector=loadLocalPause(),current=initial,attempted=false,result=null,operationError=null;
            var actTwoTeleport=request&&['actTwoGateTeleport','actTwoCityTeleport','actTwoWindriseTeleport','actTwoLionTeleport','actTwoNorthTeleport'].indexOf(request.step)>=0,city=request&&request.step==='actTwoCityTeleport',lion=request&&request.step==='actTwoLionTeleport',north=request&&request.step==='actTwoNorthTeleport',destination=request&&request.step==='actTwoGateTeleport'?{x:-1122.173,y:2197.455}:city?{x:-867.68,y:2281.38}:lion?{x:-1436.901,y:1659.013}:north?{x:-1508.909,y:2298.307}:{x:-1265.917,y:1928.381};
            var rows=initial&&initial.ocr||[],proof=actOneLocalPauseProof(initial,Date.now(),request.session);
            if(!request||request.mission!=='questStep'||(!actTwoTeleport&&request.step!=='lisaWindriseTeleport')||actTwoTeleport&&!actTwoOriginalAccount(rows)||
               !proof||proof.kind!=='map'||
               !rows.some(function(r){return /^(Starfell Valley|Starfell Valleyale|Galesong Hill)$/.test(r.text.trim())||actTwoTeleport&&r.text.trim()==='Windwail Highland';}))
                return {status:'stopped',step:'lisaWindriseTeleport',reason:'Fresh Windrise regional map required',teleportAttempted:false,questComplete:false};
            var lastInputFrame=initial.frameId,event=null;
            try{
                checkStop();ready();attempted=true;
                event={type:request.step,frameId:initial.frameId,x:destination.x,y:destination.y,startedAt:Date.now()};events.push(event);
                try{await genshin.tp(destination.x,destination.y,false);}finally{event.finishedAt=Date.now();}
                var arrived=false;
                for(var poll=0;poll<8;poll++){
                    checkStop();await sleep(350);current=await observe();
                    if((actTwoTeleport?actTwoOriginalAccount(current.ocr)&&current.hud.world&&current.hud.groundControls&&current.hud.health&&!current.hud.climbing:actOneLionFalconWaypointReady(current,Date.now(),request.session))&&current.map&&
                       Math.hypot(current.map.x-destination.x,current.map.y-destination.y)<=20){arrived=true;break;}
                    if(actOneLocalPauseProof(current,Date.now(),request.session))break;
                }
                result={status:arrived?'completed':'stopped',step:request.step,teleportAttempted:true,
                    destinationReached:arrived,questComplete:false,reason:arrived?'Unlocked waypoint arrival verified':'Waypoint arrival not verified',
                    fieldFrameId:arrived?current.frameId:null,fieldPosition:arrived?current.map:null,fieldHealth:arrived?current.hud.health:null,
                    nativeTeleportMs:event.finishedAt-event.startedAt};
            }catch(e){operationError=String(e&&e.message||e);}
            if(attempted)return await finishWithLocalPause(protector,this,initial,observe,lastInputFrame,result,operationError);
            return result;
        },
        runLisaStatueRecovery: async function(initial,observe){
            var protector=loadLocalPause();
            var runner=eval(file.readTextSync('lisa-statue-recovery.js')+'\nActOneLisaStatueRecovery;');
            if(!runner||typeof runner.run!=='function')throw new Error('Lisa Statue recovery runner required before inventory close');
            lisaRecoveryState.healingRunner=eval(file.readTextSync('recovery.js')+'\nActOneRecovery;');
            if(!lisaRecoveryState.healingRunner||typeof lisaRecoveryState.healingRunner.run!=='function'||
               typeof lisaRecoveryState.healingRunner.hasStatueHealingPanel!=='function')throw new Error('Existing Statue healing runner required before inventory close');
            statueDialogueModule();
            lisaRecoveryState.observer=observe;
            var startedInField=actOneLocalPauseInputReady(initial,Date.now(),request.session),result=null,operationError=null;
            try{result=await runner.run(initial,this,observe);}catch(e){operationError=String(e&&e.message||e);}
            if(lisaRecoveryState.closed||startedInField){
                if(result&&Number.isInteger(result.frameId)&&!Number.isInteger(result.fieldFrameId))result.fieldFrameId=result.frameId;
                result=await finishWithLocalPause(protector,this,initial,observe,Math.max(initial.frameId,lisaRecoveryState.lastInputFrame),result,operationError);
            }else if(operationError)throw new Error(operationError);
            return result;
        },
        lisaRecoveryInventoryReady: function(o){
            checkStop();ready();
            if(!lisaRecoveryCurrent(o)||lisaRecoveryState.closed)return false;
            var proof=actOneLocalPauseProof(o,Date.now(),request.session);
            if(proof&&proof.kind==='journal'){
                var knownLisa=o.ocr.filter(function(r){return r.text.trim()==='Sparks Amongst the Pages'&&r.x>=800&&r.x<=1400&&r.y>=95&&r.y<=180;}).length===1&&
                    o.ocr.filter(function(r){return r.text.trim()==='Meet Lisa at the temple'&&r.x>=800&&r.x<=1400&&r.y>=220&&r.y<=290;}).length===1&&
                    o.ocr.filter(function(r){return r.text.trim()==='Navigation'&&r.x>=1550&&r.x<=1770&&r.y>=1000&&r.y<=1040;}).length===1;
                var journalRows=knownLisa?o.ocr.filter(function(r){return !(r.text.trim()==='Cancel'&&r.x>=1580&&r.x<=1760&&r.y>=975&&r.y<=1010); }):o.ocr;
                return !actOneEnterGameAuthPrompt(journalRows)&&!actOneEnterGameUnknownUi(journalRows);
            }
            var gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            return !!(gate(o,Date.now(),request.session)&&o.ocr.filter(function(r){return r.text.trim()==='Food'&&r.x>=100&&r.x<=250&&r.y>=15&&r.y<=70;}).length===1);
        },
        lisaRecoveryInitialMapReady: function(o){
            checkStop();ready();
            if(!lisaRecoveryCurrent(o)||lisaRecoveryState.closed||lisaRecoveryState.mapOpened||
                actOneEnterGameAuthPrompt(o.ocr)||actOneEnterGameUnknownUi(o.ocr))return false;
            var proof=actOneLocalPauseProof(o,Date.now(),request.session);
            return !!(proof&&proof.kind==='map'&&(actOneFullMapState(o.ocr)||proof.evidence.some(function(r){return /^(Starfell Valley|Galesong Hill)$/.test(r.text.trim());})));
        },
        lisaRecoveryAdoptMap: function(o){
            if(!this.lisaRecoveryInitialMapReady(o))throw new Error('Fresh verified Starfell or Galesong map required');
            // Ownership is armed before the native teleport may return to the world.
            lisaRecoveryState.closed=true;lisaRecoveryState.mapOpened=true;
            events.push({type:'lisaRecoveryAdoptPausedMap',frameId:o.frameId,startedAt:Date.now(),inputSent:false});
        },
        lisaRecoveryCloseInventory: async function(o){
            if(!this.lisaRecoveryInventoryReady(o))throw new Error('Fresh exact Food inventory or verified quest journal required for Lisa recovery');
            lisaRecoveryState.closed=true;lisaRecoveryState.lastInputFrame=o.frameId;
            var e={type:'lisaRecoveryInventoryClose',frameId:o.frameId,startedAt:Date.now()};events.push(e);
            try{await boundedKey('VK_ESCAPE',60,o.frameId);}finally{e.finishedAt=Date.now();}
        },
        lisaRecoveryFieldReady: function(o){
            checkStop();ready();
            return !!(lisaRecoveryState.closed&&lisaRecoveryCurrent(o)&&o.hud.world===true&&actOneLionFieldWorld(o,Date.now(),request.session,0,true)&&
                !actOneEnterGameAuthPrompt(o.ocr)&&!actOneEnterGameUnknownUi(o.ocr));
        },
        lisaRecoveryMapOpenReady: function(o){
            checkStop();ready();
            if(this.lisaRecoveryFieldReady(o))return true;
            // Opening the map is a pause-only recovery action. An unreadable HP
            // crop must not block it when the grounded owned party and exact
            // Lisa objective are independently visible. Never infer health.
            if(!lisaRecoveryState.closed||!lisaRecoveryCurrent(o)||!actOneLocalPauseInputReady(o,Date.now(),request.session)||
               !o.hud||o.hud.health!==null||o.hud.groundControls!==true||o.hud.climbing!==false)return false;
            function one(text,y0,y1){return o.ocr.filter(function(r){return r.text.trim()===text&&r.x>=1600&&r.x<=1800&&r.y>=y0&&r.y<=y1;}).length===1;}
            return one('Lumina',280,350)&&one('Kaeya',460,540)&&o.ocr.filter(function(r){return r.text.trim()==='3'&&r.x>=1850&&r.x<=1890&&r.y>=460&&r.y<=540;}).length===1&&
                !o.ocr.some(function(r){return r.text.trim()==='Trial';})&&
                (o.hud.objectives||[]).filter(function(s){return actOneLisaObjective(s)||['Talk to Lisa','Enter the temple'].indexOf(String(s||'').trim())>=0;}).length===1;
        },
        lisaRecoveryOpenMap: async function(o){
            if((lisaRecoveryState.mapInputs||0)>=3||lisaRecoveryState.teleported||!this.lisaRecoveryMapOpenReady(o))throw new Error('Fresh owned grounded Lisa overworld required before bounded recovery map input');
            lisaRecoveryState.mapInputs=(lisaRecoveryState.mapInputs||0)+1;
            lisaRecoveryState.mapOpened=true;lisaRecoveryState.lastInputFrame=o.frameId;
            var e={type:'lisaRecoveryMapOpen',frameId:o.frameId,startedAt:Date.now()};events.push(e);
            try{await boundedKey('VK_M',60,o.frameId);}finally{e.finishedAt=Date.now();}
        },
        lisaRecoveryMapReady: function(o){
            checkStop();ready();
            if(!lisaRecoveryState.closed||!lisaRecoveryState.mapOpened||!lisaRecoveryCurrent(o)||
                actOneEnterGameAuthPrompt(o.ocr)||actOneEnterGameUnknownUi(o.ocr))return false;
            var proof=actOneLocalPauseProof(o,Date.now(),request.session);
            return !!(proof&&proof.kind==='map'&&(actOneFullMapState(o.ocr)||proof.evidence.some(function(r){return /^(Starfell Valley|Galesong Hill)$/.test(r.text.trim());})));
        },
        lisaRecoveryTeleport: async function(o){
            if(lisaRecoveryState.teleported||!this.lisaRecoveryMapReady(o))throw new Error('Fresh Starfell or Galesong map required for one fixed Statue teleport');
            lisaRecoveryState.teleported=true;lisaRecoveryState.lastInputFrame=o.frameId;
            var e={type:'lisaRecoveryTeleport',frameId:o.frameId,x:-1323.474,y:2566.115,startedAt:Date.now()};events.push(e);
            try{await genshin.tp(-1323.474,2566.115,false);checkStop();ready();}finally{e.finishedAt=Date.now();}
        },
        lisaRecoveryAtStatue: function(o){
            if(!lisaRecoveryState.teleported||!this.lisaRecoveryFieldReady(o)||!o.map||o.map.map!=='Teyvat'||
                !Number.isFinite(o.map.x)||!Number.isFinite(o.map.y)||Math.hypot(o.map.x+1323.474,o.map.y-2566.115)>20||
                !Array.isArray(o.hud.enemyBars)||o.hud.enemyBars.length)return false;
            return true;
        },
        lisaRecoveryHealAtStatue: async function(initial,observe){
            var base=this,runner=lisaRecoveryState.healingRunner;
            if(!runner||!base.lisaRecoveryAtStatue(initial)||Math.hypot(initial.map.x+1323.474,initial.map.y-2566.115)>=15)
                throw new Error('Fresh safe Starfell field required before Statue approach');
            lisaRecoveryState.healing=true;lisaRecoveryState.interactions=0;
            lisaRecoveryState.healingAdvances=0;lisaRecoveryState.blessingAttempted=false;
            lisaRecoveryState.heals=0;lisaRecoveryState.healingEscapes=0;
            var moves=0,turns=0,lastField=initial;
            function current(){
                checkStop();ready();var o=lastObservation;
                if(!lisaRecoveryCurrent(o)||Date.now()<o.timestamp||Date.now()-o.timestamp>1000||
                   actOneEnterGameAuthPrompt(o.ocr)||actOneEnterGameUnknownUi(o.ocr))throw new Error('Fresh same-session Statue screen required');
                return o;
            }
            function field(){
                var o=current();if(!base.lisaRecoveryAtStatue(o)||Math.hypot(o.map.x+1323.474,o.map.y-2566.115)>=15)
                    throw new Error('Safe grounded Starfell field required before movement');
                lastField=o;return o;
            }
            function dialogue(o){
                var state={session:request.session,armed:true,interactionAttempted:lisaRecoveryState.interactions===1,
                    lastInputFrame:lisaRecoveryState.lastInputFrame,advanceAttempted:false,leaveAttempted:false,allowSilentOpening:true};
                return statueDialogueModule().action(o,Date.now(),request.session,state);
            }
            function panel(o){return lisaRecoveryState.interactions===1&&runner.hasStatueHealingPanel(o)&&
                !o.hud.auto&&!o.hud.journal&&!o.hud.bigMap&&!o.hud.world;}
            function mark(o,type){lisaRecoveryState.lastInputFrame=o.frameId;
                events.push({type:type,frameId:o.frameId,startedAt:Date.now()});}
            var scoped={now:base.now,checkStop:base.checkStop,sleep:base.sleep,release:base.release,statuePassiveHealPolls:0,statueInteractionPolls:4,
                rotate:function(dx){var o=field();if(!Number.isInteger(dx)||Math.abs(dx)>250||turns>=12)
                        throw new Error('Statue turn bound exceeded');turns++;mark(o,'lisaStatueApproachTurn');return base.rotate(dx);},
                forward:function(ms){var o=field();if(!Number.isInteger(ms)||ms<1||ms>500||moves>=4)
                        throw new Error('Statue movement bound exceeded');moves++;mark(o,'lisaStatueApproachMove');return base.forward(ms);},
                keyPress:async function(key){
                    var o=current();
                    if(key==='VK_F'){
                        if(lisaRecoveryState.interactions||!base.lisaRecoveryAtStatue(o)||Math.hypot(o.map.x+1323.474,o.map.y-2566.115)>3)
                            throw new Error('One fresh close Statue interaction required');
                        // Observation already merges the independently scaled F crop from this capture.
                        var fPrompt=null;
                        var projection=Object.assign({},o,{hud:Object.assign({},o.hud,{world:false})});
                        if(!runner.safeStatueInteraction(projection,Date.now(),fPrompt))throw new Error('Exact Statue label and same-frame F prompt required');
                        lisaRecoveryState.interactions=1;mark(o,'lisaStatueHealingInteract');
                    }else if(key==='VK_SPACE'){
                        var action=dialogue(o);
                        if(!action||action.kind!=='advance'||lisaRecoveryState.healingAdvances>=1)
                            throw new Error('One verified Statue opening advance required');
                        lisaRecoveryState.healingAdvances++;mark(o,'lisaStatueHealingAdvance');
                    }else if(key==='VK_ESCAPE'){
                        if(!panel(o)||lisaRecoveryState.healingEscapes>=1)throw new Error('One verified Statue panel close required');
                        lisaRecoveryState.healingEscapes++;mark(o,'lisaStatueHealingClose');
                    }else throw new Error('Unrelated key rejected by Statue healing scope');
                    await boundedKey(key,60,o.frameId);
                },
                chooseStatueBlessing:function(){var o=current(),action=dialogue(o);
                    if(!action||action.kind!=='leave'||lisaRecoveryState.blessingAttempted)throw new Error('Exact Statue Blessing and Leave choices required');
                    lisaRecoveryState.blessingAttempted=true;mark(o,'lisaStatueHealingBlessing');return base.chooseStatueBlessing();},
                healTravelerAtStatue:function(){var o=current();if(!panel(o)||lisaRecoveryState.heals>=5)
                        throw new Error('Verified restorative Statue panel and bounded healing required');
                    lisaRecoveryState.heals++;mark(o,'lisaStatueHealingPortraits');return base.healTravelerAtStatue();},
                pauseCombat:async function(){var o=field();mark(o,'lisaStatueHealingPause');return base.pauseCombat();},
                teleportStarfellStatue:function(){throw new Error('Second teleport rejected by Statue healing scope');}
            };
            async function trackedObserve(){var o=await observe();
                // A missing grey selected-slot glyph must not discard the verified
                // Statue approach. Retry observation only; every movement still
                // requires a complete fresh field and a newly recognized GPS fix.
                for(var retry=0;retry<2&&lisaRecoveryState.interactions===0&&(!base.lisaRecoveryAtStatue(o)||
                    o.map&&Math.hypot(o.map.x+1323.474,o.map.y-2566.115)<=3&&
                    !runner.safeStatueInteraction(Object.assign({},o,{hud:Object.assign({},o.hud,{world:false})}),Date.now(),null))&&
                    o.hud&&o.hud.groundControls===true&&o.hud.climbing===false&&!o.hud.auto&&!o.hud.dialogueReady&&
                    !o.hud.choice&&!o.hud.journal&&!o.hud.bigMap&&o.hud.health&&o.hud.health.current>0&&
                    Array.isArray(o.hud.enemyBars)&&!o.hud.enemyBars.length&&
                    (o.hud.objectives||[]).some(actOneLisaObjective);retry++){
                    checkStop();await sleep(150);o=await observe();
                }
                if(base.lisaRecoveryAtStatue(o))lastField=o;return o;}
            var out=await runner.run(initial,scoped,trackedObserve);
            var hp=lastField&&lastField.hud.health;
            var healingVerified=out.status==='completed'||out.reason==='Statue healing applied'&&out.health&&hp&&
                out.health.current===hp.current&&out.health.max===hp.max;
            // The outer guardian verifies pause after the journal transition. A delayed
            // journal must not erase already witnessed healing or trigger another heal.
            return {recovered:healingVerified&&hp&&lastField.frameId>initial.frameId&&hp.current/hp.max>=0.95,health:hp||null,
                fieldFrameId:lastField&&lastField.frameId,fieldPosition:lastField&&lastField.map,reason:out.reason,moves:moves,turns:turns};
        },
        runLionFieldCombat: async function(initial,observe){
            // Load the mandatory protector before any inventory close is permitted.
            var protector=loadLocalPause();
            var startedInField=actOneLocalPauseInputReady(initial,Date.now(),request.session);
            lionFieldState.observer=observe;var result=null,operationError=null;
            try{result=await lionFieldModule().run(initial,this,observe);}
            catch(e){operationError=String(e&&e.message||e);}
            if(lionFieldState.closed||startedInField) {
                if(result)result.step=request.step;
                if(result&&Number.isInteger(result.frameId))result.fieldFrameId=result.frameId;
                result=await finishWithLocalPause(protector,this,initial,observe,Math.max(initial.frameId,lionFieldState.lastInputFrame),result,operationError);
            } else if(operationError)throw new Error(operationError);
            return result;
        },
        pauseDialogueHandoff: function(o){
            return !!(request&&(/^actTwo/.test(request.step||'')||request.mission==='navigation'&&request.objective==='Explore for Adventure Rank'&&(o.ocr||[]).some(r=>r.text==='I am Otto of the Knights of Favonius.'&&r.y>=910&&r.y<=970)||request.mission==='navigation'&&/^(?:Talk to Kaeya(?: at the meeting spot)?|Report to Kaeya|Talk to the informant)$/.test(request.objective||''))&&
                o&&o.session===request.session&&Date.now()>=o.timestamp&&Date.now()-o.timestamp<=1000&&actTwoOriginalAccount(o.ocr)&&o.hud&&
                o.hud.auto&&!o.hud.health&&!o.hud.groundControls&&(o.hud.dialogueReady||o.hud.choice)&&
                (o.ocr||[]).some(function(r){return /^(Kaeya|Paimon|Amber|Lisa|Jean|Venti|Cyrus|Vile|Lynn|Jack|Otto|Farrah|Knight of Favonius)$/.test(r.text)&&r.x>=600&&r.x<=1200&&r.y>=820&&r.y<900;}));
        },
        pauseObserve: function(){
            if(!pauseProtectionActive||!pauseProtectionObserver)throw new Error('Armed local pause observer required');
            return pauseProtectionObserver();
        },
        pauseProof: function(o){
            var proof=actOneLocalPauseProof(o,Date.now(),request&&request.session);
            // Unlocking a statue temporarily displays the map and then returns to the world.
            // That transition is not a durable pause; wait for the field and open a real menu.
            if(proof&&proof.kind==='map'&&request&&request.step==='windriseReveal'&&windriseState.plan&&
               windriseState.plan.action==='interact'&&windriseState.interactions===1)return null;
            return proof;
        },
        pauseResolveKnownUi: async function(o){
            if(pauseProtectionActive&&request&&request.mission==='questStep'&&['actTwoMapClose','actTwoRecover'].indexOf(request.step)>=0&&o&&lastObservation&&o.session===request.session&&o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&this.actTwoHandbookRecoveryReady(o)&&!events.some(function(e){return e.type==='actTwoHandbookSafetyClose';})){
                checkStop();ready();release();pauseProtectionLastInputFrame=o.frameId;var event={type:'actTwoHandbookSafetyClose',frameId:o.frameId,startedAt:Date.now()};events.push(event);try{await boundedKey('VK_ESCAPE',60,o.frameId);await sleep(650);return true;}finally{event.finishedAt=Date.now();}
            }
            if(pauseProtectionActive&&request&&request.mission==='questStep'&&
               ['lionVisualMove','lionLocalPause'].indexOf(request.step)>=0&&o&&lastObservation&&
               o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&
               actOneLisaSkillInfo(o,Date.now(),request.session)&&
               !events.some(function(e){return e.type==='lionSkillTutorialDismiss'&&e.slide===o.ocr.filter(function(r){return r.y>=760&&r.y<=810;}).map(function(r){return r.text;}).join('|');})&&lionLiveContext(o).entry(o)){
                checkStop();ready();release();
                if(!actOneLisaSkillInfo(o,Date.now(),request.session))return false;
                events.push({type:'lionSkillTutorialDismiss',slide:o.ocr.filter(function(r){return r.y>=760&&r.y<=810;}).map(function(r){return r.text;}).join('|'),frameId:o.frameId,x:960,y:1018,startedAt:Date.now()});
                pauseProtectionLastInputFrame=o.frameId;click(960,1018);await sleep(500);return true;
            }
            var windrise=request&&request.step==='windriseReveal'&&windriseState.used&&windriseState.plan&&
                windriseState.plan.action==='interact'&&windriseState.interactions===1;
            var healing=request&&request.step==='lisaStatueRecovery'&&lisaRecoveryState.healing&&lisaRecoveryState.interactions===1;
            if(!pauseProtectionActive||!request||request.mission!=='questStep'||(!windrise&&!healing)||
               !o||!lastObservation||o.session!==request.session||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp)return false;
            // A broken replacement UI policy cannot block ordinary world pause keys.
            if(o.hud.world===true||o.hud.groundControls===true||o.hud.health)return false;
            if(healing&&lisaRecoveryCurrent(o)&&Date.now()>=o.timestamp&&Date.now()-o.timestamp<=1000&&
               lisaRecoveryState.healingRunner.hasStatueHealingPanel(o,true)&&!o.hud.auto&&!o.hud.journal&&!o.hud.bigMap&&!o.hud.world&&
               !actOneEnterGameAuthPrompt(o.ocr)&&!actOneEnterGameUnknownUi(o.ocr)&&
               (lisaRecoveryState.guardianPanelEscapes||0)<2){
                checkStop();ready();release();lisaRecoveryState.guardianPanelEscapes=(lisaRecoveryState.guardianPanelEscapes||0)+1;
                lisaRecoveryState.lastInputFrame=o.frameId;pauseProtectionLastInputFrame=o.frameId;
                var closing={type:'lisaStatueSafetyClose',frameId:o.frameId,startedAt:Date.now()};events.push(closing);
                try{await boundedKey('VK_ESCAPE',60,o.frameId);return true;}finally{closing.finishedAt=Date.now();}
            }
            var state={session:request.session,armed:true,interactionAttempted:true,
                lastInputFrame:Math.max(healing?lisaRecoveryState.lastInputFrame:windriseState.lastInputFrame,statueDialogueState.lastInputFrame),
                advanceAttempted:statueDialogueState.advanceAttempted,leaveAttempted:statueDialogueState.leaveAttempted,allowSilentOpening:!!healing};
            var resolver=statueDialogueModule(),action=resolver.action(o,Date.now(),request.session,state);
            if(!action)return false;
            checkStop();release();
            // Consume the attempt before persistence/input. A throwing write or input cannot replay it.
            if(action.kind==='advance')statueDialogueState.advanceAttempted=true;
            else if(action.kind==='leave')statueDialogueState.leaveAttempted=true;
            else throw new Error('Unknown statue UI action');
            statueDialogueState.lastInputFrame=o.frameId;pauseProtectionLastInputFrame=o.frameId;
            var marker={session:request.session,requestId:request.id,frameId:o.frameId,kind:action.kind,
                advanceAttempted:statueDialogueState.advanceAttempted,leaveAttempted:statueDialogueState.leaveAttempted,attemptedAt:Date.now()};
            var markerPath='reports/'+request.session+'.statue-dialogue-actions.json',source=JSON.stringify(marker);
            if(!file.writeTextSync(markerPath,source)||file.readTextSync(markerPath)!==source)throw new Error('Statue UI attempt persistence not verified; no input sent');
            // Persistence can take time; require the same fresh screen again before sending anything.
            if(!resolver.action(o,Date.now(),request.session,state))throw new Error('Statue dialogue expired before input');
            var prefix=healing?'lisa':'windrise';
            var event={type:action.kind==='advance'?prefix+'StatueDialogueAdvance':prefix+'StatueLeave',frameId:o.frameId,startedAt:Date.now()};events.push(event);
            try{
                checkStop();
                if(action.kind==='advance')await boundedKey('VK_SPACE',60,o.frameId);
                else {event.x=action.x;event.y=action.y;click(action.x,action.y);}
                return true;
            }finally{event.finishedAt=Date.now();}
        },
        pauseInputReady: function(o){
            ready();return !!(pauseProtectionActive&&request&&o&&lastObservation&&o.session===request.session&&
                o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&o.frameId>pauseProtectionLastInputFrame&&
                actOneLocalPauseInputReady(o,Date.now(),request.session));
        },
        pauseKey: async function(o,key){
            if(['VK_B','VK_J','VK_ESCAPE'].indexOf(key)<0||pauseProtectionKeys[key]||!this.pauseInputReady(o))
                throw new Error('Fresh pinned active-game HUD and unused pause-only key required');
            pauseProtectionKeys[key]=true;pauseProtectionLastInputFrame=o.frameId;
            var event={type:'pauseProtectionKey',key:key,durationMs:60,frameId:o.frameId,startedAt:Date.now()};events.push(event);
            try{await boundedKey(key,60,o.frameId);}finally{event.finishedAt=Date.now();}
        },
        pauseRecoverFocus: async function(){
            if(!pauseProtectionActive)throw new Error('Local pause protection is not armed');
            sessionReady();if(genshin.isGameForeground!==true)await genshin.focusGame();ready();
        },
        pausePending: function(info){
            if(heartbeat)heartbeat(false);var now=Date.now();
            if(now-pauseProtectionLastStatusAt<2000)return;
            pauseProtectionLastStatusAt=now;
            file.writeTextSync('pause-protection.json',JSON.stringify({session:request&&request.session,requestId:request&&request.id,
                state:'pause-pending',frameId:lastObservation&&lastObservation.frameId,updatedAt:now,details:info||null}));
        },
        lionFieldProbeOnly: function(){return !!(request&&request.step==='lionFieldProbe');},
        lionFieldInventoryReady: function(o){
            checkStop();ready();var gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            if(!lionFieldCurrent(o)||lionFieldState.closed)return false;
            var proof=actOneLocalPauseProof(o,Date.now(),request.session);
            var windriseMap=request.step==='lionFieldProbe'&&proof&&proof.kind==='map'&&o.ocr.filter(function(r){
                return r.text.trim()==='Windrise'&&r.x>=850&&r.x<=1050&&r.y>=400&&r.y<=500;}).length===1;
            return !!windriseMap||!!gate(o,Date.now(),request.session)&&
                o.ocr.some(function(r){return r.text.trim()==='Food'&&r.x>=100&&r.x<=250&&r.y>=15&&r.y<=70;});
        },
        lionFieldCloseInventory: async function(o){
            if(!this.lionFieldInventoryReady(o))throw new Error('Fresh exact Food inventory or Windrise map probe required');
            var mapProof=actOneLocalPauseProof(o,Date.now(),request.session);
            var closingMap=!!(mapProof&&mapProof.kind==='map'),charted=closingMap?null:chartedWindriseEvidence();
            var navigationAnchor=closingMap?null:pausedNavigationProbeAnchor();
            if(!this.lionFieldInventoryReady(o))throw new Error('Food inventory aged during paused position probe validation');
            lionFieldState.closed=true;lionFieldState.lastInputFrame=o.frameId;
            lionFieldState.chartedProbeAnchor=navigationAnchor||{x:-1265.917,y:1928.381,maxDistance:80};
            lionFieldState.chartedProbePending=closingMap||!!charted||!!navigationAnchor;
            lionFieldState.climbReleaseArmed=!!(navigationAnchor&&navigationAnchor.releaseClimb===true);
            var event={type:closingMap?'lionFieldMapClose':'lionFieldInventoryClose',frameId:o.frameId,startedAt:Date.now()};
            if(charted)event.chartedRevealFrame=charted.frameId;
            if(navigationAnchor){event.pausedNavigationWitnessFrame=navigationAnchor.witnessFrameId;event.pausedNavigationReceiptId=navigationAnchor.receiptId;}
            events.push(event);
            try{await boundedKey('VK_ESCAPE',60,o.frameId);await sleep(300);checkStop();}finally{event.finishedAt=Date.now();}
        },
        lionFieldReleaseClimbReady: function(o){
            checkStop();ready();
            return !!(request&&request.step==='lionFieldProbe'&&lionFieldState.closed&&lionFieldState.climbReleaseArmed&&
                !lionFieldState.climbReleaseAttempted&&lionFieldCurrent(o)&&
                lisaClimbReleaseModule().ready(o,Date.now(),request.session,{armed:true,releaseAttempted:false,lastInputFrame:lionFieldState.lastInputFrame}));
        },
        lionFieldReleaseClimb: async function(o){
            if(!this.lionFieldReleaseClimbReady(o))throw new Error('Fresh witnessed Lisa climb controls required for one drop');
            var originalState={armed:true,releaseAttempted:false,lastInputFrame:lionFieldState.lastInputFrame};
            var expectedPosition=lionFieldState.chartedProbeAnchor.climbWitnessPosition;
            // The requested map is pinned by the API argument; native Point2f has only x/y.
            var fixedPosition=genshin.getPositionFromMap('Teyvat',host.toSingle(expectedPosition.x),host.toSingle(expectedPosition.y));
            var fixedX=fixedPosition?Number(fixedPosition.x):NaN,fixedY=fixedPosition?Number(fixedPosition.y):NaN;
            if(!fixedPosition||![fixedX,fixedY].every(Number.isFinite)||
               Math.hypot(fixedX-expectedPosition.x,fixedY-expectedPosition.y)>3)
                throw new Error('Fresh climb position did not match the reviewed adjacent ledge; no drop input sent');
            if(!this.lionFieldReleaseClimbReady(o))throw new Error('Lisa climb controls expired during position verification');
            lionFieldState.climbReleaseAttempted=true;lionFieldState.lastInputFrame=o.frameId;
            var marker={session:request.session,requestId:request.id,frameId:o.frameId,releaseAttempted:true,
                witnessFrameId:lionFieldState.chartedProbeAnchor.climbWitnessFrameId,attemptedAt:Date.now()};
            var path='reports/'+request.session+'.lisa-climb-release.json',source=JSON.stringify(marker);
            if(!file.writeTextSync(path,source)||file.readTextSync(path)!==source)throw new Error('Lisa climb release attempt persistence failed; no drop input sent');
            checkStop();ready();release();
            if(!lastObservation||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp||
               !lisaClimbReleaseModule().ready(o,Date.now(),request.session,originalState))throw new Error('Lisa climb controls expired before drop input');
            var event={type:'lisaClimbRelease',key:'VK_X',durationMs:60,frameId:o.frameId,
                position:{map:'Teyvat',x:fixedX,y:fixedY},startedAt:Date.now()};events.push(event);
            try{await boundedKey('VK_X',60,o.frameId);}finally{event.finishedAt=Date.now();}
        },
        lionFieldReady: function(o){checkStop();ready();return lionFieldState.closed&&lionFieldCurrent(o)&&actOneLionFieldWorld(o,Date.now(),request.session,0.6);},
        lionFieldSelectKaeya: async function(o){
            if(lionFieldState.selected||!this.lionFieldReady(o))throw new Error('Fresh Lisa field and owned Kaeya slot 3 required');
            lionFieldState.selected=true;lionFieldState.lastInputFrame=o.frameId;
            var event={type:'lionFieldKaeyaSelectAttempt',key:'VK_3',frameId:o.frameId,startedAt:Date.now()};events.push(event);
            try{await boundedKey('VK_3',60,o.frameId);}finally{event.finishedAt=Date.now();}
        },
        lionFieldFight: async function(o){
            if(!lionFieldState.selected||lionFieldState.fought||!this.lionFieldReady(o)||!Array.isArray(o.hud.enemyBars)||!o.hud.enemyBars.length)
                throw new Error('Fresh Lisa enemy bar after one Kaeya selection attempt required');
            lionFieldState.fought=true;lionFieldState.lastInputFrame=o.frameId;
            var event={type:'lionFieldNativeFight',strategy:'English Starter Trials',timeoutMs:15000,frameId:o.frameId,startedAt:Date.now()};events.push(event);
            try{return await runStarterTrialAutoFight({createLinkedCancellationTokenSource:function(){return dispatcher.GetLinkedCancellationTokenSource();},
                createAutoFightParam:function(name){return new AutoFightParam(name);},runAutoFightTask:function(param,token){return dispatcher.RunAutoFightTask(param,token);}},
                function(){checkStop();ready();},{sleep:sleep});}finally{event.finishedAt=Date.now();}
        },
        lionFieldReacquire: async function(o){
            if(!lionFieldState.selected||lionFieldState.scanned||lionFieldState.fought||!this.lionFieldReady(o))return false;
            lionFieldState.scanned=true;lionFieldState.lastInputFrame=o.frameId;
            events.push({type:'lionFieldReacquire',frameId:o.frameId,dx:200,startedAt:Date.now()});
            checkStop();ready();moveMouseBy(200,0);await sleep(300);return true;
        },
        lionFieldReturnAmber: async function(o){
            checkStop();ready();var amber=o&&o.ocr.filter(function(r){return r.text.trim()==='Amber'&&r.x>=1550&&r.x<=1800&&r.y>=380&&r.y<=450;});
            if(!lionFieldState.selected||lionFieldState.returnedAmber||!lionFieldCurrent(o)||!actOneLionFieldWorld(o,Date.now(),request.session,0)||!amber||amber.length!==1)
                throw new Error('Fresh Lisa field and unique Amber slot 2 required for return attempt');
            lionFieldState.returnedAmber=true;lionFieldState.lastInputFrame=o.frameId;
            var event={type:'lionFieldAmberReturnAttempt',key:'VK_2',frameId:o.frameId,startedAt:Date.now()};events.push(event);
            try{await boundedKey('VK_2',60,o.frameId);}finally{event.finishedAt=Date.now();}
        },
        lionFieldPause: async function(o){
            checkStop();ready();if(!lionFieldState.closed||lionFieldState.paused||!lionFieldCurrent(o)||!lionFieldState.observer||
                !actOneLionFieldWorld(o,Date.now(),request.session,0))return false;
            lionFieldState.paused=true;lionFieldState.lastInputFrame=o.frameId;
            var event={type:'lionFieldInventoryPause',frameId:o.frameId,startedAt:Date.now()};events.push(event);
            try{await boundedKey('VK_B',60,o.frameId);}finally{event.finishedAt=Date.now();}
            var gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            for(var p=0;p<4;p++){await sleep(400);var after=await lionFieldState.observer();if(gate(after,Date.now(),request.session)&&
                after.ocr.some(function(r){return r.text.trim()==='Food'&&r.x>=100&&r.x<=250&&r.y>=15&&r.y<=70;}))return true;}
            return false;
        },
        windriseRevealPlan: function(){var p=windrisePermit();if(!p)throw new Error('Unused root-witnessed Windrise permit required');return p.action==='forward'||p.action==='retreat'?{action:p.action,holds:p.holds}:{action:p.action,dx:p.dx};},
        windriseRevealReady: function(o) {
            var guardStarted=Date.now();checkStop();ready();var p=windriseState.plan||windrisePermit(),m=windriseModule(),guardNow=Date.now();
            var currentFrameValid=windriseCurrent(o),fieldReady=p&&p.action==='retreat'?m.retreatReady(o,guardNow,request.session):m.fieldReady(o,guardNow,request.session);
            var accepted=!windriseState.pauseOnly&&currentFrameValid&&fieldReady;
            if(!accepted)events.push({type:'windriseRevealGuardRejected',frameId:o&&o.frameId,ageMs:o&&Number.isFinite(o.timestamp)?guardNow-o.timestamp:null,
                currentFrameValid:currentFrameValid,fieldReady:fieldReady,guardMs:Date.now()-guardStarted});
            return accepted;
        },
        windriseRevealStatueReady: function(o) {
            checkStop();ready();return windriseCurrent(o)&&windriseModule().statueInteractReady(o,Date.now(),request.session);
        },
        windriseRevealConsumePermit: function(o) {
            checkStop();ready();var p=windrisePermit();
            if(windriseState.used||!p||!this.windriseRevealReady(o))return false;
            if(p.witnessFrameId<p.frameId){
                var witnessed=JSON.parse(file.readTextSync('observations/'+p.session+'/frame-'+String(p.witnessFrameId).padStart(4,'0')+'.json'));
                var expectedAngle=witnessed.hud&&witnessed.hud.compassAngle,actualAngle=o.hud&&o.hud.compassAngle;
                if(!Number.isFinite(expectedAngle)||!Number.isFinite(actualAngle)||Math.abs((actualAngle-expectedAngle+540)%360-180)>5)return false;
            }
            p.usedAt=Date.now();p.requestId=request.id;var saved=JSON.stringify(p);
            if(!file.writeTextSync('windrise-reveal.json',saved)||file.readTextSync('windrise-reveal.json')!==saved)throw new Error('Windrise permit consumption not verified; no input sent');
            windriseState.used=true;windriseState.plan=p;
            events.push({type:'windriseRevealPermit',rootDirected:true,witnessFrameId:p.witnessFrameId,lastKnownFrameId:p.lastKnownFrameId,startedAt:Date.now()});return true;
        },
        windriseRevealConsumePausePermit: function(o) {
            checkStop();ready();var p=windrisePermit();
            if(windriseState.used||!p||!windriseCurrent(o)||!windriseModule().fieldPauseReady(o,Date.now(),request.session))return false;
            p.usedAt=Date.now();p.requestId=request.id;p.pauseOnly=true;var saved=JSON.stringify(p);
            if(!file.writeTextSync('windrise-reveal.json',saved)||file.readTextSync('windrise-reveal.json')!==saved)throw new Error('Windrise pause permit consumption not verified; no input sent');
            windriseState.used=true;windriseState.plan=p;windriseState.pauseOnly=true;
            events.push({type:'windriseRevealPermit',rootDirected:true,pauseOnly:true,witnessFrameId:p.witnessFrameId,lastKnownFrameId:p.lastKnownFrameId,startedAt:Date.now()});return true;
        },
        windriseRevealAction: async function(action,amount) {
            checkStop();ready();var o=lastObservation,p=windriseState.plan;
            if(!windriseState.used||!p||!this.windriseRevealReady(o)||action!==p.action||
               ((action==='forward'||action==='retreat')&&(amount!==500||windriseState.moves>=p.holds))||
               (action==='look'&&(amount!==p.dx||windriseState.turns>=1))||
               (action==='interact'&&(amount!==60||windriseState.interactions>=1||!this.windriseRevealStatueReady(o))))throw new Error('Fresh bounded root-witnessed field action required');
            windriseState.lastInputFrame=o.frameId;if(action==='forward'||action==='retreat')windriseState.moves++;else if(action==='look')windriseState.turns++;else windriseState.interactions++;
            var event={type:'windriseRevealAction',rootDirected:true,action:action,amount:amount,frameId:o.frameId,startedAt:Date.now()};events.push(event);
            try{
                if(action==='forward'||action==='retreat')await boundedKey(action==='forward'?'VK_W':'VK_S',500,o.frameId);
                else if(action==='interact'){await boundedKey('VK_F',60,o.frameId);await sleep(800);checkStop();}
                else moveMouseBy(amount,0);
            }finally{event.finishedAt=Date.now();}
        },
        windriseRevealPause: async function(o) {
            checkStop();ready();
            if(!windriseState.used||windriseState.paused||!windriseCurrent(o)||!windriseModule().fieldPauseReady(o,Date.now(),request.session)||!windriseState.observer)return false;
            windriseState.paused=true;windriseState.lastInputFrame=o.frameId;
            var event={type:'windriseRevealPause',frameId:o.frameId,startedAt:Date.now()};events.push(event);
            try{await boundedKey('VK_B',60,o.frameId);}finally{event.finishedAt=Date.now();}
            for(var poll=0;poll<4;poll++){await sleep(400);var after=await windriseState.observer();
                var gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
                if(gate(after,Date.now(),request.session))return true;
            }
            return false;
        },
        worldInventoryCloseReady: function(o) {
            checkStop();o=o||lastObservation;
            if(worldInventoryCloseAttempted||!request||request.mission!=='questStep'||request.step!=='worldInventoryClose'||
               !o||!lastObservation||o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp)return false;
            var gate=eval(file.readTextSync('world-inventory.js')+'\nactOneWorldInventoryClosePermission;');
            return !!gate(o,Date.now(),request.session);
        },
        closeWorldInventory: async function() {
            checkStop();ready();var o=lastObservation;
            if(!this.worldInventoryCloseReady(o))throw new Error('Fresh exact ordinary inventory required; no Escape sent');
            worldInventoryCloseAttempted=true;
            var event={type:'worldInventoryClose',frameId:o.frameId,startedAt:Date.now()};events.push(event);
            try{await boundedKey('VK_ESCAPE',60,o.frameId);}finally{event.finishedAt=Date.now();}
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
            if(!request||request.step!==name||!o||Date.now()-o.timestamp>1000||o.map!==null||!rows.some(function(r){return (/^(Weapons|Food)$/.test(r.text.trim())||name==='falconFoodTab'&&r.text.trim()==='Quest')&&r.x>120&&r.x<280&&r.y<70;})) throw new Error('Fresh recognized inventory required');
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
                var title=name==='falconFeedAmber'?'Amber':name==='falconSelectAmberFood'&&rows.some(function(r){return r.text.trim()==='Kaeya'&&r.x>800&&r.x<1050&&r.y>250&&r.y<320;})?'Kaeya':'Traveler';
                var confirms=rows.filter(function(r){return r.text.trim()==='Confirm'&&r.x>1100&&r.x<1250&&r.y>730&&r.y<790;});
                if(confirms.length!==1||!rows.some(function(r){return r.text.trim()===title&&r.x>800&&r.x<1050&&r.y>250&&r.y<320;})||!rows.some(function(r){return r.text.trim()==='Amount to use'&&r.x>600&&r.y>600&&r.y<660;})||!rows.some(function(r){return r.text.trim()===(name==='falconReviveTraveler'?'Teyvat Fried Egg':'Sweet Madame')&&r.x>1300&&r.y<180;})) throw new Error('Exact healing food and character confirmation required');
                events.push({type:name,character:title,startedAt:Date.now()});
                if(name==='falconSelectAmberFood') {
                    var fourParty=rows.filter(function(r){return /^Lv\.(?:\s*(7|16|2))?$/.test(r.text)&&r.y>=490&&r.y<=530&&r.x>=700&&r.x<=1250;});
                    if(fourParty.length===4)click(903,440);else click(1045,440);
                }
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
            var proofEvent={type:'wolfResumeProof',verified:true,fromSession:proof.fromSession,toSession:proof.toSession,priorEntryId:proof.priorEntryId,
                priorPauseId:proof.priorPauseId,betterGiProcessId:proof.betterGiProcessId,rdpSessionId:proof.rdpSessionId,
                gameProcessId:proof.gameProcessId,verifiedAt:proof.verifiedAt,recordedAt:Date.now()};
            if(proof.priorBetterGiProcessId!==undefined)proofEvent.priorBetterGiProcessId=proof.priorBetterGiProcessId;
            events.push(proofEvent);
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
        lionStartReady: function (o) {checkStop();return !!(request&&request.mission==='questStep'&&request.step==='lionStart'&&!lionDomainStartAttempted&&actOneLionStartTarget(o||lastObservation,Date.now()));},
        lionPartyReady: function (o) {
            checkStop();if(!request||request.mission!=='questStep'||request.step!=='lionPartyStart'||lionPartyStartAttempted)return false;
            var reports=file.readTextSync('reports/'+request.session+'.jsonl').split(/\r?\n/).filter(function(line){return line.trim().length>0;}).map(function(line){return JSON.parse(line);});
            return !!actOneLionPartyTarget(o||lastObservation,Date.now(),reports,request.session,request.id);
        },
        startLionDomain: function () {
            checkStop();ready();var target=actOneLionStartTarget(lastObservation,Date.now());
            if(!request||request.mission!=='questStep'||request.step!=='lionStart'||lionDomainStartAttempted||!target)throw new Error('Fresh exact Lion Domain Entrance required');
            lionDomainStartAttempted=true;
            events.push({type:'lionDomainStart',frameId:lastObservation.frameId,label:'Deep Within the Temple of the Lion',x:target.x,y:target.y,startedAt:Date.now()});
            click(target.x,target.y);checkStop();return target.label;
        },
        startLionParty: function () {
            checkStop();ready();
            if(!request||request.mission!=='questStep'||request.step!=='lionPartyStart'||lionPartyStartAttempted)throw new Error('Lion party start request required');
            var reports=file.readTextSync('reports/'+request.session+'.jsonl').split(/\r?\n/).filter(function(line){return line.trim().length>0;}).map(function(line){return JSON.parse(line);});
            var target=actOneLionPartyTarget(lastObservation,Date.now(),reports,request.session,request.id);
            if(!target)throw new Error('Fresh Lion party setup and uninterrupted same-session entrance required');
            lionPartyStartAttempted=true;
            events.push({type:'lionPartyStart',label:'Deep Within the Temple of the Lion',frameId:lastObservation.frameId,x:target.x,y:target.y,startedAt:Date.now()});
            click(target.x,target.y);checkStop();
        },
        startWolfDomain: function () {
            checkStop();ready();var target=actOneTempleStartTarget(lastObservation,Date.now(),'Wolf');
            if(!request||request.mission!=='questStep'||request.step!=='wolfStart'||!target)throw new Error('Fresh exact level-5 Wolf Domain Entrance required');
            events.push({type:'wolfDomainStart',frameId:lastObservation.frameId,label:target.label,x:target.x,y:target.y,startedAt:Date.now()});
            click(target.x,target.y);checkStop();return target.label;
        },
        runActTwoKaeyaLevel: async function(initial,observe){
            var gate=eval(file.readTextSync('act-two-team.js')+'\nActTwoTeam;'),p=JSON.parse(file.readTextSync('act-two-team-request.json')),current=initial;
            if(!p||p.action!=='upgrade'||p.reviewed!==true||p.consumed||p.session!==request.session||p.frameId!==request.expectedFrameId||
                !Number.isInteger(p.startAmount)||p.startAmount<0||p.startAmount>2||
                !Number.isFinite(p.createdAt)||Date.now()<p.createdAt||Date.now()-p.createdAt>60000||!gate.upgradeReady(current,Date.now(),request.session,p.startAmount))
                throw new Error('Exact reviewed three-book Kaeya budget required');
            p.consumed=true;var encoded=JSON.stringify(p);if(!file.writeTextSync('act-two-team-request.json',encoded)||file.readTextSync('act-two-team-request.json')!==encoded)throw new Error('Upgrade plan consumption failed');
            for(var amount=p.startAmount+1;amount<=3;amount++){
                if(!gate.upgradeReady(current,Date.now(),request.session,amount-1))throw new Error('Upgrade selection changed; no spend');
                await actOneAccountUiClick({checkStop:checkStop,ready:ready,move:moveMouseTo,down:leftButtonDown,up:leftButtonUp,sleep:sleep},{x:1595,y:917});
                await sleep(250);current=await observe();
                if(!gate.upgradeReady(current,Date.now(),request.session,amount))throw new Error('Three-book cost not verified; no spend');
            }
            var event={type:'actTwoCharacterUpgrade',character:'Kaeya',book:"Adventurer's Experience",books:3,mora:3000,frameId:current.frameId,startedAt:Date.now()};events.push(event);
            try{await actOneAccountUiClick({checkStop:checkStop,ready:ready,move:moveMouseTo,down:leftButtonDown,up:leftButtonUp,sleep:sleep},{x:1730,y:1020});}
            finally{event.finishedAt=Date.now();}
            await sleep(900);current=await observe();return {status:'completed',step:request.step,spendAttempted:true,booksBudget:3,moraBudget:3000,upgradeVerified:false,frameId:current.frameId};
        },
        actTwoRecoveryMapReady: function(o){checkStop();ready();return eval(file.readTextSync('act-two-team.js')+'\nActTwoTeam;').recoveryMapReady(o,Date.now(),request.session);},
        actTwoTeamUi: async function(){
            checkStop();ready();var gate=eval(file.readTextSync('act-two-team.js')+'\nActTwoTeam;'),plan=JSON.parse(file.readTextSync('act-two-team-request.json'));
            var witness=plan.witnessFrameId?JSON.parse(file.readTextSync('observations/'+request.session+'/frame-'+plan.witnessFrameId+'.json')):null;
            var target=gate.target(lastObservation,Date.now(),plan,request,witness);if(!target)throw new Error('Fresh exact reviewed Kaeya menu required');
            plan.consumed=true;var encoded=JSON.stringify(plan);if(!file.writeTextSync('act-two-team-request.json',encoded)||file.readTextSync('act-two-team-request.json')!==encoded)throw new Error('Menu plan consumption failed');
            var event={type:'actTwoTeamUi',action:target.action,frameId:lastObservation.frameId,startedAt:Date.now()};events.push(event);
            try{if(target.key)await boundedKey(target.key,60,lastObservation.frameId);else for(var menuClick=0;menuClick<(target.action==='addFineOre'?15:target.action==='topUpFineOre'?6:target.action==='luminaReserve'?4:1);menuClick++){checkStop();ready();await actOneAccountUiClick({checkStop:checkStop,ready:ready,move:moveMouseTo,down:leftButtonDown,up:leftButtonUp,sleep:sleep},target);event.clicks=(event.clicks||0)+1;if(target.clicks)await sleep(100);}}
            finally{event.finishedAt=Date.now();}return target.action;
        },
        actTwoHandbookRecoveryReady:function(o){return !!eval(file.readTextSync('act-two-handbook.js')+'\nActTwoHandbook;').target(o,Date.now(),null,'closeRecovery');},
        runActTwoHandbookRecovery:async function(initial,observe){
            if(request.step!=='actTwoRecover'||!this.actTwoHandbookRecoveryReady(initial))throw new Error('Fresh exact Handbook required');
            checkStop();ready();await boundedKey('VK_ESCAPE',60,initial.frameId);await sleep(650);
            return finishWithLocalPause(loadLocalPause(),this,initial,observe,initial.frameId,{status:'completed',handbookClosed:true,questComplete:false},null);
        },
        actTwoHandbookClaim: async function(inspectNext){
            checkStop();ready();var gate=eval(file.readTextSync('act-two-handbook.js')+'\nActTwoHandbook;');
            var context=file.isExists('act-two-handbook-claim.json')?JSON.parse(file.readTextSync('act-two-handbook-claim.json')):null;
            var target=gate.target(lastObservation,Date.now(),context,inspectNext);if(!target)throw new Error('Fresh completed Handbook objective required');
            var event={type:'actTwoHandbookClaim',action:target.action,objective:target.objective,frameId:lastObservation.frameId,startedAt:Date.now(),ocr:lastObservation.ocr};events.push(event);
            file.writeTextSync('act-two-handbook-claim.json',target.action==='claim'?JSON.stringify({session:request.session,frameId:lastObservation.frameId,createdAt:Date.now(),rewardExp:target.chapterReward?0:target.rewardExp||100,chapterReward:target.chapterReward===true}):'null');
            try{if(target.scroll===-8){moveMouseTo(target.x,target.y);for(var tick=0;tick<8;tick++){checkStop();ready();verticalScroll(-1);await sleep(100);}}else await actOneAccountUiClick({checkStop:checkStop,ready:ready,move:moveMouseTo,down:leftButtonDown,up:leftButtonUp,sleep:sleep},target);}
            finally{event.finishedAt=Date.now();}return target;
        },
        actTwoRankReturnReady: function(){
            checkStop();ready();return eval(file.readTextSync('act-two-rank-rewards.js')+'\nActTwoRankRewards;').returnVisit(lastObservation,Date.now(),request.session);
        },
        actTwoRankReward: async function(){
            checkStop();ready();var gate=eval(file.readTextSync('act-two-rank-rewards.js')+'\nActTwoRankRewards;');
            var context=file.isExists('act-two-rank-claim.json')?JSON.parse(file.readTextSync('act-two-rank-claim.json')):null;
            var target=gate.target(lastObservation,Date.now(),context);if(!target)throw new Error('Fresh original-account rank reward menu required');
            var event={type:'actTwoRankReward',action:target.action,frameId:lastObservation.frameId,startedAt:Date.now(),ocr:lastObservation.ocr};events.push(event);
            if(target.action==='claim')file.writeTextSync('act-two-rank-claim.json',JSON.stringify({session:request.session,frameId:lastObservation.frameId,createdAt:Date.now()}));
            else file.writeTextSync('act-two-rank-claim.json','null');
            try{await actOneAccountUiClick({checkStop:checkStop,ready:ready,move:moveMouseTo,down:leftButtonDown,up:leftButtonUp,sleep:sleep},target);}
            finally{event.finishedAt=Date.now();}
            return target.action;
        },
        actTwoMap: async function () {
            checkStop();ready();var plan=JSON.parse(file.readTextSync('act-two-map-request.json'));
            var gate=eval(file.readTextSync('act-two-map.js')+'\nActTwoMap;');
            var target=gate.target(lastObservation,Date.now(),plan,request);
            if(!request||request.mission!=='questStep'||request.step!=='actTwoMap'||!target)throw new Error('Fresh exact reviewed map target required');
            plan.consumed=true;if(!file.writeTextSync('act-two-map-request.json',JSON.stringify(plan)))throw new Error('Cannot consume map plan');
            var event={type:'actTwoMap',action:plan.action,frameId:lastObservation.frameId,startedAt:Date.now()};events.push(event);
            try {await actOneAccountUiClick({checkStop:checkStop,ready:ready,move:moveMouseTo,down:leftButtonDown,up:leftButtonUp,sleep:sleep},target);}
            finally {event.finishedAt=Date.now();}
            checkStop();return plan.action;
        },
        actTwoJournal: async function () {
            checkStop();ready();var plan=JSON.parse(file.readTextSync('act-two-journal-request.json'));
            var gate=eval(file.readTextSync('act-two-journal.js')+'\nActTwoJournal;');
            var target=gate.target(lastObservation,Date.now(),plan,request);
            if(!request||request.mission!=='questStep'||request.step!=='actTwoJournal'||!target)throw new Error('Fresh exact authorized journal target and one-use plan required');
            plan.consumed=true;if(!file.writeTextSync('act-two-journal-request.json',JSON.stringify(plan)))throw new Error('Cannot consume journal plan');
            var event={type:'actTwoJournal',action:plan.action,quest:plan.quest,frameId:lastObservation.frameId,startedAt:Date.now()};events.push(event);
            try {if(target.scroll===-2){checkStop();ready();moveMouseTo(target.x,target.y);verticalScroll(-2);}else await actOneAccountUiClick({checkStop:checkStop,ready:ready,move:moveMouseTo,down:leftButtonDown,up:leftButtonUp,sleep:sleep},target);}
            finally {event.finishedAt=Date.now();}
            checkStop();
        },
        accountSavedUi: async function () {
            checkStop();ready();var permit=JSON.parse(file.readTextSync('account-saved-ui.json'));
            var target=actOneSavedAccountTarget(lastObservation,Date.now(),permit);
            if(!request||request.mission!=='questStep'||request.step!=='accountSavedUi'||!target||
                permit.reviewed!==true||permit.consumed===true||permit.session!==request.session||permit.frameId!==request.expectedFrameId||
                !Number.isFinite(permit.createdAt)||Date.now()<permit.createdAt||Date.now()-permit.createdAt>60000)throw new Error('Fresh exact saved-account UI and one-use permit required');
            permit.consumed=true;if(!file.writeTextSync('account-saved-ui.json',JSON.stringify(permit)))throw new Error('Cannot consume saved-account permit');
            var event={type:'accountSavedUi',action:permit.action,frameId:lastObservation.frameId,x:target.x,y:target.y,startedAt:Date.now()};events.push(event);
            try {await actOneAccountUiClick({checkStop:checkStop,ready:ready,move:moveMouseTo,down:leftButtonDown,up:leftButtonUp,sleep:sleep},target);}
            finally {event.finishedAt=Date.now();}
            checkStop();
        },
        accountSwitchConfirm: async function () {
            checkStop();ready();
            var permit=JSON.parse(file.readTextSync('account-title-switch.json'));
            var target=actOneAccountConfirmTarget(lastObservation,Date.now());
            if(!request||request.mission!=='questStep'||request.step!=='accountSwitchConfirm'||!target||permit.action!=='confirm'||
                permit.reviewed!==true||permit.consumed===true||permit.session!==request.session||permit.frameId!==request.expectedFrameId||
                !Number.isFinite(permit.createdAt)||Date.now()<permit.createdAt||Date.now()-permit.createdAt>60000)throw new Error('Fresh exact switch-account confirmation and one-use permit required');
            permit.consumed=true;if(!file.writeTextSync('account-title-switch.json',JSON.stringify(permit)))throw new Error('Cannot consume account switch permit');
            var event={type:'accountSwitchConfirm',frameId:lastObservation.frameId,x:target.x,y:target.y,startedAt:Date.now()};events.push(event);
            try {await actOneAccountUiClick({checkStop:checkStop,ready:ready,move:moveMouseTo,down:leftButtonDown,up:leftButtonUp,sleep:sleep},target);}
            finally {event.finishedAt=Date.now();}
            checkStop();
        },
        accountSwitchTitle: function () {
            checkStop();ready();
            var permit=JSON.parse(file.readTextSync('account-title-switch.json'));
            var target=actOneAccountTitleTarget(lastObservation,Date.now(),permit,request);
            if(!request||request.mission!=='questStep'||request.step!=='accountSwitchTitle'||!target)throw new Error('Fresh reviewed title/account logout control required');
            permit.consumed=true;if(!file.writeTextSync('account-title-switch.json',JSON.stringify(permit)))throw new Error('Cannot consume account switch permit');
            var event={type:'accountSwitchTitle',frameId:lastObservation.frameId,x:target.x,y:target.y,startedAt:Date.now()};events.push(event);
            click(target.x,target.y);event.finishedAt=Date.now();checkStop();
        },
        accountSwitchClose: async function () {
            checkStop();ready();
            var permit=JSON.parse(file.readTextSync('account-switch.json'));
            if(!request||request.mission!=='questStep'||request.step!=='accountSwitchClose'||
                !actOneAccountSwitchCloseReady(lastObservation,Date.now(),permit,request))throw new Error('Fresh exact mismatched-account reward screen and one-use reviewed permit required');
            permit.consumed=true;
            if(!file.writeTextSync('account-switch.json',JSON.stringify(permit)))throw new Error('Cannot consume account-switch permit');
            var event={type:'accountSwitchClose',frameId:lastObservation.frameId,expectedUid:permit.expectedUid,currentUid:permit.currentUid,startedAt:Date.now()};events.push(event);
            try {await actOneAccountSwitchCloseChord({checkStop:checkStop,ready:ready,keyDown:keyDown,keyUp:keyUp,sleep:sleep});}
            finally {event.finishedAt=Date.now();}
        },
        reconnectGame: function () {
            checkStop();ready();
            var target=actOneReconnectTarget(lastObservation,Date.now());
            if(!request||request.mission!=='questStep'||request.step!=='reconnectGame'||!target||
                events.some(function(e){return e.type==='reconnectGame';}))throw new Error('Fresh exact connection-timeout dialog required; one click only');
            var event={type:'reconnectGame',frameId:lastObservation.frameId,x:target.x,y:target.y,startedAt:Date.now()};
            events.push(event);click(target.x,target.y);event.finishedAt=Date.now();checkStop();
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
        runWolfWitnessAction: function(initial,observe) {
            var run=eval(file.readTextSync('wolf-witness-action.js')+'\nActOneWolfWitnessAction.run;');
            return run(initial,this,observe);
        },
        wolfWitnessBaselineHealth: function() {
            checkStop();var proof=wolfWitnessPermit();
            return proof?proof.baseline:null;
        },
        wolfWitnessContinueReady: function(o) {
            checkStop();return !wolfWitnessState.continued&&wolfWitnessCurrent(o)&&wolfSpikeEntry()&&
                !!actOneWolfResumeSeedTarget(o,Date.now())&&!!wolfWitnessPermit();
        },
        wolfWitnessContinue: function() {
            checkStop();var o=lastObservation,target=actOneWolfResumeSeedTarget(o,Date.now()),proof=wolfWitnessPermit();
            if(!this.wolfWitnessContinueReady(o)||!target||!proof)throw new Error('Fresh canonical Wolf pause and unused witnessed action permit required');
            var p=proof.permit;p.usedAt=Date.now();p.requestId=request.id;
            if(!file.writeTextSync('wolf-witness-action.json',JSON.stringify(p)))throw new Error('Cannot consume witnessed action permit');
            var saved=JSON.parse(file.readTextSync('wolf-witness-action.json'));
            if(saved.usedAt!==p.usedAt||saved.requestId!==request.id)throw new Error('Witnessed action permit consumption unverified');
            wolfWitnessState.permit=p;wolfWitnessState.baseline=proof.baseline;wolfWitnessState.continued=true;wolfWitnessState.lastInputFrame=o.frameId;
            var e={type:'wolfWitnessContinue',action:p.action,witnessFrameId:p.witnessFrameId,frameId:o.frameId,startedAt:Date.now()};events.push(e);
            try{click(Math.round(target.x+target.width/2),Math.round(target.y+target.height/2));}finally{e.finishedAt=Date.now();}
        },
        wolfWitnessActiveReady: function(o) {
            checkStop();return wolfWitnessActive(o,true)&&(wolfWitnessState.acted||wolfWitnessState.permit.action!=='jumpForward'||wolfWitnessJumpAligned(o));
        },
        wolfWitnessActionName: function() {checkStop();return wolfWitnessState.permit&&wolfWitnessState.permit.action;},
        wolfWitnessAction: async function() {
            checkStop();var o=lastObservation,p=wolfWitnessState.permit;
            if(wolfWitnessState.acted||!p||!wolfWitnessActive(o,true)||p.action==='jumpForward'&&!wolfWitnessJumpAligned(o))
                throw new Error('Fresh unchanged living Wolf HUD and visible landing alignment required before one witnessed action');
            wolfWitnessState.acted=true;wolfWitnessState.lastInputFrame=o.frameId;
            var e={type:'wolfWitnessAction',action:p.action,frameId:o.frameId,startedAt:Date.now(),rootDirected:true};events.push(e);
            try {
                var key={forwardFine:'VK_W',forwardBounded:'VK_W',leftFine:'VK_A',rightFine:'VK_D',strike:'VK_LBUTTON'}[p.action];
                if(key)await boundedKey(key,p.action==='strike'?60:p.action==='forwardBounded'?800:200,o.frameId);
                else if(p.action==='lookLeft'||p.action==='lookRight') {
                    var dx=p.action==='lookLeft'?-250:250;events.push({type:'rotate',dx:dx,frameId:o.frameId,startedAt:Date.now()});moveMouseBy(dx,0);
                } else if(p.action==='jumpForward') {
                    var forward={type:'key',key:'VK_W',durationMs:600,frameId:o.frameId,startedAt:Date.now()},jump={type:'key',key:'VK_SPACE',durationMs:60,frameId:o.frameId,startedAt:Date.now()};
                    events.push(forward);events.push(jump);held='VK_W';
                    try {
                        keyDown('VK_W');
                        try {keyDown('VK_SPACE');await sleep(60);checkStop();}finally{keyUp('VK_SPACE');jump.finishedAt=Date.now();}
                        var end=forward.startedAt+600;
                        while(true){var remaining=end-Date.now();if(remaining<=0)break;await sleep(Math.min(50,remaining));checkStop();}
                    }finally{release();forward.finishedAt=Date.now();}
                } else throw new Error('Unknown witnessed action');
            }finally{e.finishedAt=Date.now();}
        },
        wolfWitnessPauseReady: function(o) {checkStop();return !wolfWitnessState.paused&&wolfWitnessActive(o,false);},
        wolfWitnessEscape: async function() {
            checkStop();var o=lastObservation;
            if(!this.wolfWitnessPauseReady(o))throw new Error('Fresh living grounded Wolf HUD required for witnessed action cleanup');
            wolfWitnessState.paused=true;wolfWitnessState.lastInputFrame=o.frameId;
            var e={type:'wolfWitnessEscape',frameId:o.frameId,startedAt:Date.now()};events.push(e);
            try{await boundedKey('VK_ESCAPE',60,o.frameId);}finally{e.finishedAt=Date.now();}
        },
        wolfWitnessPauseVerified: function(o) {
            checkStop();return wolfWitnessState.paused&&wolfWitnessCurrent(o)&&o.frameId>wolfWitnessState.lastInputFrame&&
                !!actOneWolfRecoveryPauseTarget(o,Date.now());
        },
        wolfCharacterRecoveryPlan: function(o) {
            checkStop();o=o||lastObservation;
            if(!request||request.mission!=='recover'||!o||o.session!==request.session||!lastObservation||
               o.frameId!==lastObservation.frameId||o.timestamp!==lastObservation.timestamp||!Number.isInteger(o.frameId)||
               o.frameId<request.expectedFrameId||!wolfSpikeEntry())return null;
            var p;try{p=JSON.parse(file.readTextSync('character-menu-action.json'));}catch(e){return null;}
            if(!p||p.kind!=='wolfCharacterMenu'||p.session!==request.session||p.frameId!==request.expectedFrameId||p.usedAt||
               !Number.isFinite(p.createdAt)||Date.now()<p.createdAt||Date.now()-p.createdAt>120000)return null;
            if(['addXpOne','confirmXpOne','closeLevel'].indexOf(p.action)>=0) {
                if(p.expectedCharacter!=='Amber'||!actOneWolfAmberLevelPanelVisible(o,Date.now()))return null;
                if(p.action==='closeLevel')return {action:p.action,permit:p,key:'VK_ESCAPE',selected:'Amber'};
                var panel=o.hud.wolfAmberLevel;
                if(!panel||panel.frameId!==o.frameId||p.materialBudget!==1||p.moraBudget!==1000||
                   !Number.isInteger(panel.midTierStock)||panel.midTierStock<1||!Number.isInteger(panel.mora)||panel.mora<1000)return null;
                if(p.action==='addXpOne'&&panel.amount===0&&panel.requiredMora===0)
                    return {action:p.action,permit:p,x:1595,y:917,selected:'Amber'};
                if(p.action==='confirmXpOne'&&panel.amount===1&&panel.requiredMora===1000)
                    return {action:p.action,permit:p,x:1730,y:1020,selected:'Amber'};
                return null;
            }
            if(!actOneWolfCharacterMenuVisible(o,Date.now()))return null;
            var names=o.ocr.filter(function(r){return ['Kaeya','Amber','Lumina'].indexOf(String(r.text||'').trim())>=0&&r.x>1400&&r.x<1850&&r.y>=100&&r.y<190;});
            if(!p||p.kind!=='wolfCharacterMenu'||p.session!==request.session||p.frameId!==request.expectedFrameId||p.usedAt||
               !Number.isFinite(p.createdAt)||Date.now()<p.createdAt||Date.now()-p.createdAt>120000||names.length!==1||
               p.expectedCharacter!==String(names[0].text||'').trim()||['selectAmber','openLevel','close'].indexOf(p.action)<0)return null;
            if(p.action==='close')return {action:p.action,permit:p,key:'VK_ESCAPE',selected:p.expectedCharacter};
            if(p.action==='selectAmber') {
                if(p.expectedCharacter==='Amber'||!['Q','E'].every(function(label){return o.ocr.filter(function(r){
                    return String(r.text||'').trim()===label&&r.y>=0&&r.y<90&&r.x>400&&r.x<1500;}).length===1;}))return null;
                return {action:p.action,permit:p,x:960,y:48,selected:p.expectedCharacter};
            }
            var buttons=o.ocr.filter(function(r){return String(r.text||'').trim()==='Level Up'&&r.x>1400&&r.x<1850&&r.y>900&&r.y<1035;});
            if(p.expectedCharacter!=='Amber'||buttons.length!==1)return null;
            return {action:p.action,permit:p,x:Math.round(buttons[0].x+buttons[0].width/2),y:Math.round(buttons[0].y+buttons[0].height/2),selected:'Amber'};
        },
        wolfCharacterRecoveryAction: async function() {
            checkStop();var plan=this.wolfCharacterRecoveryPlan(lastObservation);
            if(!plan)throw new Error('Fresh exact character menu and unused matching action permit required');
            plan.permit.usedAt=Date.now();plan.permit.requestId=request.id;
            if(!file.writeTextSync('character-menu-action.json',JSON.stringify(plan.permit)))throw new Error('Cannot consume character-menu action permit');
            var saved=JSON.parse(file.readTextSync('character-menu-action.json'));
            if(saved.requestId!==request.id||saved.usedAt!==plan.permit.usedAt)throw new Error('Character-menu action permit consumption unverified');
            var event={type:'wolfCharacterRecoveryAction',action:plan.action,selectedBefore:plan.selected,frameId:lastObservation.frameId,startedAt:Date.now()};events.push(event);
            try{if(plan.key)await boundedKey(plan.key,60,lastObservation.frameId);else click(plan.x,plan.y);}finally{event.finishedAt=Date.now();}
        },
        wolfCharactersFoodCloseReady: function(o) {
            checkStop();o=o||lastObservation;
            return wolfCharactersStage===0&&wolfCharactersCurrent(o)&&wolfSpikeEntry()&&actOneWolfFoodInventoryReady(o,Date.now())&&
                !o.ocr.some(function(r){return String(r.text||'').trim()==='Amount to use';});
        },
        wolfCharactersPauseContinueReady: function(o) {
            checkStop();o=o||lastObservation;
            return wolfCharactersStage===0&&wolfCharactersCurrent(o)&&wolfSpikeEntry()&&!!actOneWolfResumeSeedTarget(o,Date.now());
        },
        wolfCharactersPauseContinue: function() {
            checkStop();var o=lastObservation,target=actOneWolfResumeSeedTarget(o,Date.now());
            if(!this.wolfCharactersPauseContinueReady(o)||!target)throw new Error('Fresh exact Wolf pause required before character-menu preparation');
            wolfCharactersStage=1;wolfCharactersLastFrame=o.frameId;
            var event={type:'wolfCharactersContinue',frameId:o.frameId,x:Math.round(target.x+target.width/2),y:Math.round(target.y+target.height/2),startedAt:Date.now()};events.push(event);
            try{click(event.x,event.y);}finally{event.finishedAt=Date.now();}
        },
        wolfCharactersFoodClose: async function() {
            checkStop();var o=lastObservation;
            if(!this.wolfCharactersFoodCloseReady(o))throw new Error('Fresh exact Wolf food grid and entry proof required before character-menu preparation');
            wolfCharactersStage=1;wolfCharactersLastFrame=o.frameId;
            events.push({type:'wolfCharactersCloseInventory',frameId:o.frameId,startedAt:Date.now()});
            await boundedKey('VK_ESCAPE',60,o.frameId);
        },
        wolfCharactersOpenReady: function(o) {
            checkStop();o=o||lastObservation;
            return wolfCharactersStage===1&&wolfCharactersCurrent(o)&&o.frameId>wolfCharactersLastFrame&&wolfSpikeEntry()&&
                actOneWolfSpikeActive(o,Date.now(),'kaeya',0.01);
        },
        wolfCharactersOpen: async function() {
            checkStop();var o=lastObservation;
            if(!this.wolfCharactersOpenReady(o))throw new Error('Fresh living grounded Kaeya HUD without enemies required before character menu');
            wolfCharactersStage=2;wolfCharactersLastFrame=o.frameId;
            events.push({type:'wolfCharactersOpen',frameId:o.frameId,startedAt:Date.now()});
            await boundedKey('VK_C',60,o.frameId);
        },
        wolfCharactersMenuVisible: function(o) {
            checkStop();o=o||lastObservation;
            return wolfCharactersStage===2&&wolfCharactersCurrent(o)&&o.frameId>wolfCharactersLastFrame&&
                actOneWolfCharacterMenuVisible(o,Date.now());
        },
        runWolfSecondSpike: function(initial,observe) {
            var run=eval(file.readTextSync('wolf-second-spike.js')+'\nActOneWolfSecondSpike.runWolfSecondSpike;');
            return run(initial,this,observe);
        },
        wolfSecondContinueReady: function(o) {
            checkStop();o=o||lastObservation;
            return !wolfSecondState.continued&&wolfSecondCurrent(o)&&o.frameId>wolfSecondState.lastInputFrame&&
                !!actOneWolfResumeSeedTarget(o,Date.now())&&wolfSpikeEntry()&&!!wolfSecondPermit();
        },
        wolfSecondCrossingCharacter: function() {
            checkStop();var permit=wolfSecondPermit();
            if(!permit)throw new Error('Unused same-session second-bank permit required for crossing choice');
            return permit.crossingCharacter||'amber';
        },
        wolfSecondApproachPlan: function() {
            checkStop();
            if(wolfSecondState.continued)return wolfSecondState.approachLimit;
            var permit=wolfSecondPermit();
            if(!permit)throw new Error('Unused same-session second-bank permit required for approach plan');
            return permit.approachMoves||0;
        },
        wolfSecondContinue: function() {
            checkStop();var o=lastObservation,target=actOneWolfResumeSeedTarget(o,Date.now()),permit=wolfSecondPermit();
            if(wolfSecondState.continued||!wolfSecondCurrent(o)||o.frameId<=wolfSecondState.lastInputFrame||!target||!wolfSpikeEntry()||!permit)
                throw new Error('Fresh canonical Wolf pause and unused second-bank permit required');
            permit.usedAt=Date.now();permit.requestId=request.id;
            if(!file.writeTextSync('wolf-spike-second.json',JSON.stringify(permit)))throw new Error('Cannot consume second-bank permit');
            wolfSecondState.continued=true;wolfSecondState.lastInputFrame=o.frameId;
            wolfSecondState.crossingCharacter=permit.crossingCharacter||'amber';wolfSecondState.bankPosition=permit.bankPosition||null;
            wolfSecondState.approachLimit=permit.approachMoves||0;
            wolfSecondState.bridgeFloorMin=permit.refreshedIceProof===true?0.88:0.9;
            if(permit.bankPosition==='iceBridge')wolfSecondState.kaeyaBaseline={current:permit.verifiedKaeyaHealth.current,max:permit.verifiedKaeyaHealth.max};
            var event={type:'wolfSecondContinue',frameId:o.frameId,startedAt:Date.now()};events.push(event);
            try{click(Math.round(target.x+target.width/2),Math.round(target.y+target.height/2));}finally{event.finishedAt=Date.now();}
        },
        wolfRevivePromptContinueReady: function(o) {
            checkStop();o=o||lastObservation;
            return !wolfReviveContinueAttempted&&wolfReviveCurrent(o)&&!!actOneWolfResumeSeedTarget(o,Date.now())&&wolfReviveEntry()&&!!wolfRevivePermit();
        },
        wolfRevivePromptContinue: function() {
            checkStop();var o=lastObservation,target=actOneWolfResumeSeedTarget(o,Date.now()),permit=wolfRevivePermit();
            if(wolfReviveContinueAttempted||!wolfReviveCurrent(o)||!target||!wolfReviveEntry()||!permit)
                throw new Error('Fresh canonical Wolf pause, entry proof, and unused revival permit required');
            permit.usedAt=Date.now();permit.requestId=request.id;
            if(!file.writeTextSync('wolf-revive-kaeya.json',JSON.stringify(permit)))throw new Error('Cannot consume Kaeya revival permit');
            wolfReviveContinueAttempted=true;wolfReviveContinueFrame=o.frameId;
            var event={type:'wolfReviveKaeyaContinue',frameId:o.frameId,x:Math.round(target.x+target.width/2),y:Math.round(target.y+target.height/2),startedAt:Date.now()};events.push(event);
            try{click(event.x,event.y);}finally{event.finishedAt=Date.now();}
        },
        wolfRevivePromptSelectReady: function(o) {
            checkStop();o=o||lastObservation;
            return !wolfReviveSelectAttempted&&wolfReviveActiveReady(o);
        },
        wolfRevivePromptSelect: async function(o) {
            checkStop();o=o||lastObservation;
            if(wolfReviveSelectAttempted||!wolfReviveActiveReady(o)||o.frameId<=wolfReviveContinueFrame)
                throw new Error('Fresh living Amber grounded HUD after one Continue required');
            wolfReviveSelectAttempted=true;
            var event={type:'wolfReviveKaeyaSelect',key:'VK_3',frameId:o.frameId,startedAt:Date.now()};events.push(event);
            try{await boundedKey('VK_3',60,o.frameId);}finally{event.finishedAt=Date.now();}
        },
        wolfSecondActiveReady: function(o,body,minRatio) {
            checkStop();return wolfSecondActiveReady(o||lastObservation,body,minRatio);
        },
        wolfSecondSelectKaeya: async function() {
            if(wolfSecondState.selectedKaeya||wolfSecondState.cast||wolfSecondState.moves)throw new Error('Second-pit Kaeya selection already used');
            if(['iceBridge','platform'].indexOf(wolfSecondState.bankPosition)>=0) {
                if(!wolfSecondActiveReady(lastObservation,'kaeya',0.01))throw new Error('Fresh unchanged selected Kaeya required before the witnessed continuation');
                wolfSecondState.selectedKaeya=true;return;
            }
            await wolfSecondKey('VK_3',60,function(o){return wolfSecondActiveReady(o,'any',0.01);});
            wolfSecondState.selectedKaeya=true;
        },
        wolfSecondSelectionSettleMs: function() {return ['iceBridge','platform'].indexOf(wolfSecondState.bankPosition)>=0?0:350;},
        wolfSecondApproach: async function(ms) {
            checkStop();var o=lastObservation,s=wolfSecondSurface(o),m=s&&s.metrics;
            if(ms!==200||wolfSecondState.approachLimit<1||wolfSecondState.approachLimit>2||
               wolfSecondState.approaches>=wolfSecondState.approachLimit||wolfSecondState.approaches>=2||
               wolfSecondState.crossingCharacter!=='kaeya'||['lip','platform'].indexOf(wolfSecondState.bankPosition)<0||
               !wolfSecondState.selectedKaeya||wolfSecondState.selectedAmber||wolfSecondState.cast||wolfSecondState.moves||
               !wolfSecondActiveReady(o,'kaeya',0.01)||!s||s.solidFloor!==true||!m||
               !(wolfSecondState.bankPosition==='platform'?wolfSecondPlatformFloor(m):['underfootLeftStone','underfootRightStone']
                   .every(function(k){return Number.isFinite(m[k])&&m[k]>=0.8&&m[k]<=1;})))
                throw new Error('Fresh unchanged Kaeya on witnessed stone required for at most two 200ms approach holds');
            wolfSecondState.approaches++;
            await wolfSecondKey(wolfSecondState.bankPosition==='platform'?'VK_D':'VK_W',200,function(value){return wolfSecondActiveReady(value,'kaeya',0.01);});
        },
        wolfSecondCooldownPlan: function(o) {
            checkStop();o=o||lastObservation;
            if(!wolfSecondState.selectedKaeya||wolfSecondState.cast||wolfSecondState.approachLimit>0||wolfSecondState.readyAt!==null||
                !wolfSecondActiveReady(o,'kaeya',0.01))throw new Error('Fresh unchanged Kaeya floor state required for cooldown plan');
            var remaining=actOneWolfCryoCooldownRemaining(o);
            var bridge=wolfSecondState.bankPosition==='iceBridge';
            if(bridge&&remaining===null&&o.ocr.filter(function(r){return String(r.text||'').trim()==='E'&&r.x>1600&&r.y>1000;}).length!==1)
                throw new Error('Exact Kaeya E control or countdown required on the existing ice bridge');
            var wait=remaining===null?(bridge?300:6500):Math.min(6500,Math.ceil(remaining*1000)+300);
            wolfSecondState.readyAt=Date.now()+wait;
            events.push({type:'wolfSecondCooldownPlan',frameId:o.frameId,waitMs:wait,startedAt:Date.now()});
            return wait;
        },
        wolfSecondAlignedReady: function(o) {
            checkStop();o=o||lastObservation;
            if(!wolfSecondState.selectedKaeya||wolfSecondState.cast||!wolfSecondActiveReady(o,'kaeya',0.01)||!wolfSecondBlockAligned(o)) {
                wolfSecondState.lastAlignedFrame=null;wolfSecondState.alignmentConfirmedFrame=null;return false;
            }
            if(wolfSecondState.bankPosition==='iceBridge') {
                // The immutable parent identifies this static ice checkpoint.
                // The fresh post-cooldown frame rechecks both feet probes and HP.
                wolfSecondState.lastAlignedFrame=o.frameId;wolfSecondState.alignmentConfirmedFrame=o.frameId;return true;
            }
            if(wolfSecondState.lastAlignedFrame!==null&&o.frameId===wolfSecondState.lastAlignedFrame+1)
                wolfSecondState.alignmentConfirmedFrame=o.frameId;
            wolfSecondState.lastAlignedFrame=o.frameId;
            return wolfSecondState.alignmentConfirmedFrame===o.frameId;
        },
        wolfSecondCast: async function() {
            if(wolfSecondState.cast||!wolfSecondState.selectedKaeya||wolfSecondState.approachLimit>0)throw new Error('Second-pit ice skill already used, Kaeya unselected, or approach-only permit');
            await wolfSecondKey('VK_E',60,function(o){return wolfSecondActiveReady(o,'kaeya',0.01)&&
                wolfSecondState.readyAt!==null&&Date.now()>=wolfSecondState.readyAt&&actOneWolfCryoCooldownRemaining(o)===null&&
                wolfSecondState.alignmentConfirmedFrame===o.frameId&&wolfSecondBlockAligned(o);});
            wolfSecondState.cast=true;
        },
        wolfSecondIceReady: function(o) {
            checkStop();o=o||lastObservation;
            var surface=wolfSecondSurface(o);
            var valid=wolfSecondState.cast&&!wolfSecondState.selectedAmber&&wolfSecondActiveReady(o,'kaeya',0.01)&&
                surface&&surface.ice===true;
            if(valid&&wolfSecondState.bankPosition==='iceBridge') {
                var remaining=actOneWolfCryoCooldownRemaining(o);
                valid=remaining!==null&&remaining>=4;
            }
            if(valid)wolfSecondState.iceVerified=true;
            return !!valid;
        },
        wolfSecondSelectAmber: async function() {
            if(wolfSecondState.crossingCharacter!=='amber'||wolfSecondState.selectedAmber||wolfSecondState.moves||!wolfSecondState.iceVerified)
                throw new Error('Second-pit positive ice proof required before single Amber selection');
            await wolfSecondKey('VK_2',60,function(o){var surface=wolfSecondSurface(o);
                return wolfSecondActiveReady(o,'kaeya',0.01)&&surface&&surface.ice===true;});
            wolfSecondState.selectedAmber=true;
        },
        wolfSecondMove: async function() {
            var kaeya=wolfSecondState.crossingCharacter==='kaeya';
            if(!(kaeya?wolfSecondState.selectedKaeya&&!wolfSecondState.selectedAmber:wolfSecondState.selectedAmber)||
                !wolfSecondState.iceVerified||wolfSecondState.moves>=3)
                throw new Error('Second-pit movement limit, selected character, or ice proof failed');
            await wolfSecondKey('VK_W',600,function(o){var surface=wolfSecondSurface(o);
                return wolfSecondActiveReady(o,kaeya?'kaeya':'amber',kaeya?0.01:0.6)&&surface&&
                    (surface.ice===true||wolfSecondState.moves>0&&surface.solidFloor===true);});
            wolfSecondState.moves++;
        },
        wolfSecondFloorReached: function(o) {
            checkStop();o=o||lastObservation;
            var surface=wolfSecondSurface(o);
            // A floor checkpoint can be the moving block or original bank. It is not far-bank/quest proof.
            var kaeya=wolfSecondState.crossingCharacter==='kaeya';
            return !!(wolfSecondState.moves>0&&(kaeya?wolfSecondState.selectedKaeya&&!wolfSecondState.selectedAmber:wolfSecondState.selectedAmber)&&
                wolfSecondActiveReady(o,kaeya?'kaeya':'amber',kaeya?0.01:0.6)&&
                surface&&surface.solidFloor===true);
        },
        wolfSecondPauseReady: function(o) {
            checkStop();o=o||lastObservation;
            return wolfSecondState.continued&&!wolfSecondState.paused&&wolfSecondCurrent(o)&&o.frameId>wolfSecondState.lastInputFrame&&
                wolfSpikeEntry()&&actOneWolfSpikeActive(o,Date.now(),'any',0.01);
        },
        wolfSecondEscape: async function() {
            var o=lastObservation;
            if(!wolfSecondState.continued||wolfSecondState.paused||!wolfSecondCurrent(o)||o.frameId<=wolfSecondState.lastInputFrame||
                !wolfSpikeEntry()||!actOneWolfSpikeActive(o,Date.now(),'any',0.01))throw new Error('Fresh living Wolf HUD required for second-pit cleanup Escape');
            await wolfSecondKey('VK_ESCAPE',60,function(value){return actOneWolfSpikeActive(value,Date.now(),'any',0.01);});
            wolfSecondState.paused=true;wolfSecondState.pauseFrame=o.frameId;
        },
        wolfSecondPauseVerified: function(o) {
            checkStop();o=o||lastObservation;
            return wolfSecondState.paused&&wolfSecondCurrent(o)&&Number.isInteger(wolfSecondState.pauseFrame)&&
                o.frameId>wolfSecondState.pauseFrame&&!!actOneWolfRecoveryPauseTarget(o,Date.now());
        },
        runWolfSpike: function(initial,observe) {
            var run=eval(file.readTextSync('wolf-spike.js')+'\nActOneWolfSpike.runWolfSpike;');
            return run(initial,this,observe);
        },
        wolfSpikeContinueReady: function(o) {
            checkStop();o=o||lastObservation;
            return !wolfSpikeState.continued&&wolfSpikeCurrent(o)&&o.frameId>wolfSpikeState.lastInputFrame&&
                !!actOneWolfResumeSeedTarget(o,Date.now())&&wolfSpikeEntry()&&!!wolfSpikePermit();
        },
        wolfSpikeContinue: function() {
            checkStop();var o=lastObservation,target=actOneWolfResumeSeedTarget(o,Date.now()),permit=wolfSpikePermit();
            if(wolfSpikeState.continued||!wolfSpikeCurrent(o)||o.frameId<=wolfSpikeState.lastInputFrame||!target||!wolfSpikeEntry()||!permit)
                throw new Error('Fresh canonical Wolf pause and unused first-bank permit required');
            permit.usedAt=Date.now();permit.requestId=request.id;
            if(!file.writeTextSync('wolf-spike-first.json',JSON.stringify(permit)))throw new Error('Cannot consume first-bank permit');
            wolfSpikeState.continued=true;wolfSpikeState.lastInputFrame=o.frameId;
            wolfSpikeState.crossingCharacter=permit.crossingCharacter==='kaeya'?'kaeya':'amber';
            wolfSpikeState.landingContinuationSource=permit.kind==='firstSpikeLanding'?permit.priorLandingMission:null;
            wolfSpikeState.reuseSource=permit.priorIceMission&&Number.isInteger(permit.priorIceFrame)?{missionId:permit.priorIceMission,frameId:permit.priorIceFrame}:null;
            var e={type:'wolfSpikeContinue',frameId:o.frameId,startedAt:Date.now()};events.push(e);
            try{click(Math.round(target.x+target.width/2),Math.round(target.y+target.height/2));}finally{e.finishedAt=Date.now();}
        },
        wolfSpikeExistingIceReady: function(o) {
            checkStop();o=o||lastObservation;
            var surface=o&&o.hud&&o.hud.wolfSpikeSurface,metrics=surface&&surface.metrics;
            if(wolfSpikeState.landingContinuationSource&&wolfSpikeState.continued&&!wolfSpikeState.selectedKaeya&&!wolfSpikeState.cast&&
               !wolfSpikeState.selectedAmber&&wolfSpikeState.moves===0&&wolfSpikeCurrent(o)&&o.frameId>wolfSpikeState.lastInputFrame&&
               wolfSpikeEntry()&&actOneWolfSpikeActive(o,Date.now(),'kaeya',0.01)&&surface&&
               (surface.kaeyaLandingLip===true||surface.solidFloor===true)&&wolfSpikeLandingContinuationProof(o)) {
                wolfSpikeState.landingContinuation=true;wolfSpikeState.usingExistingIce=true;
                wolfSpikeState.bankVerified=true;wolfSpikeState.iceVerified=true;return true;
            }
            var readyIce=wolfSpikeState.continued&&!wolfSpikeState.selectedKaeya&&!wolfSpikeState.cast&&!wolfSpikeState.selectedAmber&&
                wolfSpikeState.moves===0&&wolfSpikeCurrent(o)&&o.frameId>wolfSpikeState.lastInputFrame&&wolfSpikeEntry()&&
                actOneWolfSpikeActive(o,Date.now(),'kaeya',0.01)&&surface&&surface.ice===true&&metrics&&
                metrics.floorLeftStone>=0.7&&metrics.floorRightStone>=0.7&&metrics.floorLeftIce<=0.15&&metrics.floorRightIce<=0.15&&
                wolfSpikeReusableIceProof(o);
            if(readyIce){wolfSpikeState.usingExistingIce=true;wolfSpikeState.bankVerified=true;wolfSpikeState.iceVerified=true;}
            return readyIce===true;
        },
        wolfSpikeBankWaitReady: function(o) {
            checkStop();o=o||lastObservation;
            var surface=o&&o.hud&&o.hud.wolfSpikeSurface,metrics=surface&&surface.metrics;
            return wolfSpikeState.continued&&!wolfSpikeState.selectedKaeya&&!wolfSpikeState.cast&&wolfSpikeState.moves===0&&
                wolfSpikeCurrent(o)&&o.frameId>wolfSpikeState.lastInputFrame&&wolfSpikeEntry()&&actOneWolfSpikeActive(o,Date.now(),'any',0.01)&&
                !!(surface&&surface.solidFloor===true&&metrics&&metrics.iceLeft<=0.12&&metrics.iceRight<=0.12);
        },
        wolfSpikeActiveReady: function(o,body,minRatio) {checkStop();return wolfSpikeActiveReady(o||lastObservation,body,minRatio);},
        wolfSpikeSelectKaeya: async function() {
            checkStop();var o=lastObservation;
            if(wolfSpikeState.selectedKaeya||!wolfSpikeActiveReady(o,'any',0.01))throw new Error('Fresh first-bank living party required for one Kaeya switch');
            wolfSpikeState.selectedKaeya=true;
            await wolfSpikeKey('VK_3',60,function(value){return actOneWolfSpikeActive(value,Date.now(),'any',0.01)&&wolfSpikeState.bankVerified&&value.hud.wolfSpikeSurface.solidFloor===true;});
        },
        wolfSpikeCooldownPlan: function(o) {
            checkStop();o=o||lastObservation;
            if(!wolfSpikeState.selectedKaeya||wolfSpikeState.readyAt!==null||!wolfSpikeActiveReady(o,'kaeya',0.01))return null;
            var remaining=actOneWolfCryoCooldownRemaining(o),waitMs=remaining===null?6500:Math.min(6500,Math.ceil(remaining*1000)+300);
            wolfSpikeState.readyAt=Date.now()+waitMs;
            events.push({type:'wolfSpikeCooldownPlan',frameId:o.frameId,waitMs:waitMs,source:remaining===null?'fixedActiveFallback':'capturedRemaining',startedAt:Date.now()});
            return waitMs;
        },
        wolfSpikeCast: async function() {
            checkStop();var o=lastObservation;
            if(wolfSpikeState.cast||!wolfSpikeState.selectedKaeya||wolfSpikeState.readyAt===null||Date.now()<wolfSpikeState.readyAt||
               !wolfSpikeActiveReady(o,'kaeya',0.01)||actOneWolfCryoCooldownRemaining(o)!==null)
                throw new Error('Fresh Kaeya on the first bank and expired cooldown required before one E');
            wolfSpikeState.cast=true;
            await wolfSpikeKey('VK_E',60,function(value){return actOneWolfSpikeActive(value,Date.now(),'kaeya',0.01)&&wolfSpikeState.bankVerified&&value.hud.wolfSpikeSurface.solidFloor===true;});
        },
        wolfSpikeIceReady: function(o) {
            checkStop();o=o||lastObservation;
            var positive=wolfSpikeState.cast&&wolfSpikeActiveReady(o,'kaeya',0.01)&&o.hud.wolfSpikeSurface&&o.hud.wolfSpikeSurface.ice===true;
            if(positive)wolfSpikeState.iceVerified=true;
            return positive===true;
        },
        wolfSpikeSelectAmber: async function() {
            checkStop();var o=lastObservation;
            if(wolfSpikeState.crossingCharacter==='kaeya'||wolfSpikeState.selectedAmber||!wolfSpikeState.iceVerified||!wolfSpikeActiveReady(o,'kaeya',0.01)||
               !o.hud.wolfSpikeSurface||o.hud.wolfSpikeSurface.ice!==true)throw new Error('Fresh positive first-pit ice required before one Amber switch');
            wolfSpikeState.selectedAmber=true;
            await wolfSpikeKey('VK_2',60,function(value){return actOneWolfSpikeActive(value,Date.now(),'kaeya',0.01)&&value.hud.wolfSpikeSurface.ice===true;});
        },
        wolfSpikeCrossingPlan: function() {
            checkStop();
            if(!wolfSpikeState.iceVerified||!wolfSpikeActiveReady(lastObservation,'kaeya',0.01))
                throw new Error('Fresh living Kaeya and verified first-pit ice required before choosing the permitted crossing');
            if(wolfSpikeState.landingContinuation===true)return {character:'kaeya',minRatio:0.01,moveMs:200,maxMoves:1,landingContinuation:true};
            return wolfSpikeState.crossingCharacter==='kaeya'?
                {character:'kaeya',minRatio:0.01,moveMs:800,maxMoves:2}:
                {character:'amber',minRatio:0.6,moveMs:500,maxMoves:3};
        },
        wolfSpikeMove: async function(ms) {
            checkStop();var o=lastObservation,surface=o&&o.hud&&o.hud.wolfSpikeSurface;
            var kaeya=wolfSpikeState.crossingCharacter==='kaeya',body=kaeya?'kaeya':'amber',minRatio=kaeya?0.01:0.6;
            var continuation=wolfSpikeState.landingContinuation===true;
            if(ms!==(continuation?200:kaeya?800:500)||(!kaeya&&!wolfSpikeState.selectedAmber)||(kaeya&&wolfSpikeState.selectedAmber)||
               !wolfSpikeState.iceVerified||wolfSpikeState.moves>=(continuation?1:kaeya?2:3)||
               !wolfSpikeActiveReady(o,body,minRatio)||!surface||!(continuation?
                   surface.kaeyaLandingLip===true||surface.solidFloor===true:surface.ice===true||wolfSpikeState.moves>0&&surface.solidFloor===true))
                throw new Error('Fresh permitted crossing character on verified ice or landing required before bounded W');
            wolfSpikeState.moves++;
            await wolfSpikeKey('VK_W',ms,function(value){return actOneWolfSpikeActive(value,Date.now(),body,minRatio);});
        },
        wolfSpikeFinishReady: function(o) {
            checkStop();return wolfSpikeLocalFinishReady(o||lastObservation);
        },
        wolfSpikeFinish: async function() {
            checkStop();var o=lastObservation;
            if(!wolfSpikeLocalFinishReady(o))throw new Error('Fresh unchanged-health Kaeya at the first landing lip required after two W800 inputs');
            wolfSpikeState.moves++;
            await wolfSpikeKey('VK_W',200,function(value){
                var hp=value.hud.health,baseline=wolfSpikeState.kaeyaBaseline;
                var surface=actOneWolfSpikeSurface(value.hud.wolfSpikeSurface&&value.hud.wolfSpikeSurface.metrics);
                return actOneWolfSpikeActive(value,Date.now(),'kaeya',0.01)&&baseline&&
                    hp.current===baseline.current&&hp.max===baseline.max&&surface&&surface.kaeyaLandingLip===true;
            });
        },
        wolfSpikeLipReady: function(o) {
            checkStop();o=o||lastObservation;
            return !wolfSpikeState.jumpAttempted&&wolfSpikeState.iceVerified&&wolfSpikeState.selectedAmber&&wolfSpikeState.moves>=3&&
                wolfSpikeActiveReady(o,'amber',0.6)&&!!(o.hud.wolfSpikeSurface&&o.hud.wolfSpikeSurface.landingLip===true);
        },
        wolfSpikeLandingJump: async function() {
            checkStop();var o=lastObservation;
            if(wolfSpikeState.jumpAttempted||!wolfSpikeState.iceVerified||!wolfSpikeState.selectedAmber||wolfSpikeState.moves<3||
               !wolfSpikeActiveReady(o,'amber',0.6)||!o.hud.wolfSpikeSurface||o.hud.wolfSpikeSurface.landingLip!==true)
                throw new Error('Fresh healthy Amber at the verified first-pit landing lip required before one jump');
            wolfSpikeState.jumpAttempted=true;wolfSpikeState.lastInputFrame=o.frameId;
            var e={type:'wolfSpikeLandingJump',keys:['VK_W','VK_SPACE'],durationMs:500,spaceDurationMs:60,frameId:o.frameId,startedAt:Date.now(),keysReleased:false};
            events.push(e);var spaceHeld=false,releaseOk=false;
            try {
                held='VK_W';keyDown('VK_W');checkStop();spaceHeld=true;keyDown('VK_SPACE');
                var deadline=Date.now()+500,spaceDeadline=Date.now()+60;
                while(Date.now()<deadline) {
                    var remaining=deadline-Date.now();
                    if(spaceHeld)remaining=Math.min(remaining,spaceDeadline-Date.now());
                    await sleep(Math.max(1,Math.min(50,remaining)));checkStop();
                    if(spaceHeld&&Date.now()>=spaceDeadline){keyUp('VK_SPACE');spaceHeld=false;}
                }
            } finally {
                try {if(spaceHeld){keyUp('VK_SPACE');spaceHeld=false;}}
                finally {release();releaseOk=true;e.finishedAt=Date.now();e.keysReleased=releaseOk&&!spaceHeld&&held===null;}
            }
        },
        wolfSpikeLandingReady: function(o) {
            checkStop();o=o||lastObservation;
            var kaeya=wolfSpikeState.crossingCharacter==='kaeya';
            return wolfSpikeState.iceVerified&&wolfSpikeState.moves>=(wolfSpikeState.landingContinuation===true?0:kaeya?2:3)&&wolfSpikeActiveReady(o,kaeya?'kaeya':'amber',kaeya?0.01:0.6)&&
                !!(o.hud.wolfSpikeSurface&&o.hud.wolfSpikeSurface.firstLanding===true);
        },
        wolfSpikePauseReady: function(o) {
            checkStop();o=o||lastObservation;
            return wolfSpikeState.continued&&!wolfSpikeState.paused&&wolfSpikeCurrent(o)&&o.frameId>wolfSpikeState.lastInputFrame&&
                wolfSpikeEntry()&&actOneWolfSpikeActive(o,Date.now(),'any',0.01);
        },
        wolfSpikeEscape: async function() {
            checkStop();var o=lastObservation;
            if(!wolfSpikeState.continued||wolfSpikeState.paused||!wolfSpikeCurrent(o)||o.frameId<=wolfSpikeState.lastInputFrame||
               !wolfSpikeEntry()||!actOneWolfSpikeActive(o,Date.now(),'any',0.01))throw new Error('Fresh living Wolf HUD required before spike cleanup Escape');
            wolfSpikeState.paused=true;wolfSpikeState.pauseFrame=o.frameId;
            await wolfSpikeKey('VK_ESCAPE',60,function(value){return actOneWolfSpikeActive(value,Date.now(),'any',0.01);});
        },
        wolfSpikePauseVerified: function(o) {
            checkStop();o=o||lastObservation;
            return wolfSpikeState.paused&&wolfSpikeCurrent(o)&&Number.isInteger(wolfSpikeState.pauseFrame)&&
                o.frameId>wolfSpikeState.pauseFrame&&!!actOneWolfRecoveryPauseTarget(o,Date.now());
        },
        wolfRecoveryTravelReady: function(o) {return actOneWolfRecoveryTravelHud(o||lastObservation,Date.now());},
        wolfCryoWaitContinueReady: function(o) {
            checkStop();o=o||lastObservation;
            if(wolfCryoContinueAttempted||!wolfCryoWaitCurrent(o)||
               (wolfCryoLastInputFrame!==null&&o.frameId<=wolfCryoLastInputFrame)||!actOneWolfResumeSeedTarget(o,Date.now()))return false;
            var h=o.hud;
            if(!h||h.world!==false||h.journal!==false||h.bigMap!==false||h.auto!==false||h.dialogueReady!==false||h.choice!==false||
               h.objectiveChanged!==false||h.tutorialStep!==null||h.loading===true||h.unknownHud===true||h.climbing===true)return false;
            return actOneWolfEntryProven(JSON.parse(file.readTextSync('reports/'+request.session+'.json')),request.session);
        },
        wolfCryoWaitContinue: function() {
            checkStop();var o=lastObservation,target=actOneWolfResumeSeedTarget(o,Date.now());
            if(!this.wolfCryoWaitContinueReady(o)||!target)throw new Error('Fresh exact same-session Wolf pause required before Cryo wait Continue');
            wolfCryoContinueAttempted=true;
            wolfCryoLastInputFrame=o.frameId;
            var e={type:'wolfCryoWaitContinue',frameId:o.frameId,x:Math.round(target.x+target.width/2),y:Math.round(target.y+target.height/2),startedAt:Date.now()};
            events.push(e);try{click(e.x,e.y);}finally{e.finishedAt=Date.now();}
        },
        wolfCryoWaitActiveReady: function(o) {checkStop();return wolfCryoWaitActive(o||lastObservation,true);},
        wolfCryoWaitCooldownPlan: function(o) {
            checkStop();o=o||lastObservation;
            if(wolfCryoWaitPlan||!wolfCryoWaitActive(o,true)||!Number.isFinite(wolfCryoResumeConfirmedAt))return null;
            var remaining=actOneWolfCryoCooldownRemaining(o),source=remaining===null?'fixedActiveFallback':'capturedRemaining';
            wolfCryoWaitMs=remaining===null?6500:Math.round(remaining*1000)+300;
            wolfCryoWaitPlan={source:source,capturedRemainingSeconds:remaining,waitMs:wolfCryoWaitMs,
                confirmedAt:wolfCryoResumeConfirmedAt,frameId:o.frameId};
            events.push({type:'wolfCryoWaitPlan',source:source,capturedRemainingSeconds:remaining,waitMs:wolfCryoWaitMs,frameId:o.frameId,startedAt:Date.now()});
            return Object.assign({},wolfCryoWaitPlan);
        },
        wolfCryoWaitCooldownElapsed: function(o) {
            checkStop();o=o||lastObservation;
            return wolfCryoWaitActive(o,true)&&Number.isFinite(wolfCryoResumeConfirmedAt)&&wolfCryoWaitPlan!==null&&
                Date.now()-wolfCryoResumeConfirmedAt>=wolfCryoWaitMs;
        },
        wolfCryoWaitCast: async function() {
            checkStop();var o=lastObservation;
            if(wolfCryoSkillAttempted||!this.wolfCryoWaitCooldownElapsed(o))throw new Error('Fresh safe Wolf HUD and the selected active-time cooldown plan are required before one Cryo attempt');
            wolfCryoSkillAttempted=true;
            wolfCryoLastInputFrame=o.frameId;
            var e={type:'wolfCryoWaitSkill',key:'VK_E',frameId:o.frameId,startedAt:Date.now()};events.push(e);
            try{await boundedKey('VK_E',60);}finally{e.finishedAt=Date.now();}
        },
        wolfCryoWaitPauseReady: function(o) {
            checkStop();o=o||lastObservation;
            return !!(wolfCryoContinueAttempted&&!wolfCryoPauseAttempted&&wolfCryoWaitCurrent(o)&&
                Number.isInteger(wolfCryoLastInputFrame)&&o.frameId>wolfCryoLastInputFrame&&
                actOneWolfBurstRecoveryActiveHud(o,Date.now(),0.00001)&&
                actOneWolfEntryProven(JSON.parse(file.readTextSync('reports/'+request.session+'.json')),request.session));
        },
        wolfCryoWaitEscape: async function() {
            checkStop();var o=lastObservation;
            if(!this.wolfCryoWaitPauseReady(o))throw new Error('Fresh safe same-session active Wolf HUD required before explicit pause');
            wolfCryoPauseAttempted=true;
            wolfCryoLastInputFrame=o.frameId;
            var e={type:'wolfCryoWaitEscape',key:'VK_ESCAPE',frameId:o.frameId,startedAt:Date.now()};events.push(e);
            try{await boundedKey('VK_ESCAPE',60);}finally{e.finishedAt=Date.now();}
        },
        wolfCryoWaitPauseVerified: function(o) {
            checkStop();o=o||lastObservation;
            if(!wolfCryoPauseAttempted||!wolfCryoWaitCurrent(o)||!Number.isInteger(wolfCryoLastInputFrame)||
               o.frameId<=wolfCryoLastInputFrame||!actOneWolfRecoveryPauseTarget(o,Date.now()))return false;
            return actOneWolfEntryProven(JSON.parse(file.readTextSync('reports/'+request.session+'.json')),request.session);
        },
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
        wolfReviveRecoveryReady: function(o) {
            checkStop();o=o||lastObservation;
            if(wolfReviveRecoverySelectAttempted||!request||request.mission!=='recover'||!wolfReviveRecoveryCurrent(o)||
               !wolfReviveRecoverySafeAmber(o)||!wolfReviveRecoveryEntry()||!wolfReviveRecoveryPrefix()||!wolfReviveRecoveryPermit())return false;
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            return !reports.some(function(r){return r&&r.session===request.session&&r.mission==='recover'&&Array.isArray(r.details&&r.details.inputEvents)&&
                r.details.inputEvents.some(function(e){return e&&['wolfReviveKaeyaRecoverySelect','wolfReviveKaeyaRecoveryConfirm'].indexOf(e.type)>=0;});});
        },
        wolfReviveRecoveryConfirmOnlyReady: function(o) {
            checkStop();o=o||lastObservation;
            if(!request||request.mission!=='recover'||!wolfReviveRecoveryCurrent(o)||!wolfReviveRecoveryEntry()||
               !wolfReviveRecoveryPrefix()||!actOneWolfReviveEggTarget(o,Date.now()))return false;
            var permit;try{permit=JSON.parse(file.readTextSync('wolf-revive-kaeya-recovery.json'));}catch(e){return false;}
            var report=wolfReviveRecoverySelectionReceipt(permit);
            return !!(permit&&permit.kind==='reviveTrialKaeyaRecovery'&&permit.session===request.session&&Number.isFinite(permit.frameId)&&
                permit.requestId!==request.id&&permit.confirmationAttemptedAt===undefined&&report&&o.frameId>report.frameId&&o.frameId>=request.expectedFrameId);
        },
        wolfReviveRecoveryOpenModalReady: function(o) {
            checkStop();o=o||lastObservation;
            if(!request||request.mission!=='recover'||!wolfReviveRecoveryCurrent(o)||!wolfReviveRecoveryEntry()||
               !actOneWolfReviveEggTarget(o,Date.now()))return false;
            var permit=wolfReviveRecoveryPermit(),prompt=wolfReviveRecoveryPromptReceipt();
            if(!permit||!prompt||permit.promptRequestId!==prompt.id||!Number.isInteger(prompt.frameId)||
               prompt.frameId>request.expectedFrameId||prompt.frameId<0)return false;
            try {
                var receiptPath='receipts/'+request.session+'/'+prompt.id+'.json';
                if(!file.isExists(receiptPath))return false;
                var receipt=JSON.parse(file.readTextSync(receiptPath));
                if(!receipt||receipt.id!==prompt.id||receipt.session!==prompt.session||receipt.mission!==prompt.mission||
                   receipt.status!==prompt.status||receipt.frameId!==prompt.frameId||receipt.timestamp!==prompt.timestamp||
                   JSON.stringify(receipt.details)!==JSON.stringify(prompt.details))return false;
                var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
                return !reports.some(function(r){return r&&r!==prompt&&r.id!==prompt.id&&r.session===request.session&&
                    Number.isFinite(r.timestamp)&&r.timestamp>=prompt.timestamp&&Array.isArray(r.details&&r.details.inputEvents)&&
                    r.details.inputEvents.some(function(e){return !e||e.type!=='controllerRevision';});});
            } catch(e){return false;}
        },
        wolfReviveRecoverySelect: async function(o) {
            checkStop();o=o||lastObservation;var permit=wolfReviveRecoveryPermit();
            if(wolfReviveRecoverySelectAttempted||!this.wolfReviveRecoveryReady(o)||!permit)
                throw new Error('Fresh living Amber HUD, witnessed revival prefix, entry proof, and unused recovery permit required');
            permit.usedAt=Date.now();permit.requestId=request.id;
            if(!file.writeTextSync('wolf-revive-kaeya-recovery.json',JSON.stringify(permit))||!file.isExists('wolf-revive-kaeya-recovery.json'))
                throw new Error('Cannot consume Kaeya recovery permit');
            var saved=JSON.parse(file.readTextSync('wolf-revive-kaeya-recovery.json'));
            if(!saved||saved.kind!=='reviveTrialKaeyaRecovery'||saved.session!==request.session||saved.frameId!==request.expectedFrameId||
               saved.requestId!==request.id||saved.usedAt!==permit.usedAt)throw new Error('Recovery permit consumption was not verified');
            wolfReviveRecoverySelectAttempted=true;wolfReviveRecoverySelectFrame=o.frameId;
            wolfReviveRecoveryAmberBaseline={current:o.hud.health.current,max:o.hud.health.max};
            var e={type:'wolfReviveKaeyaRecoverySelect',key:'VK_3',frameId:o.frameId,startedAt:Date.now()};events.push(e);
            try{await boundedKey('VK_3',60,o.frameId);}finally{e.finishedAt=Date.now();}
        },
        wolfReviveRecoveryModalReady: function(o) {
            checkStop();o=o||lastObservation;
            return !!(wolfReviveRecoverySelectAttempted&&!wolfReviveRecoveryConfirmAttempted&&wolfReviveRecoveryCurrent(o)&&
                o.frameId>wolfReviveRecoverySelectFrame&&actOneWolfReviveEggTarget(o,Date.now()));
        },
        wolfReviveRecoveryConfirm: function(o) {
            checkStop();o=o||lastObservation;var target=actOneWolfReviveEggTarget(o,Date.now());
            var priorPermit=null,confirmOnly=false,openModal=false;
            try{priorPermit=JSON.parse(file.readTextSync('wolf-revive-kaeya-recovery.json'));}catch(e){}
            confirmOnly=this.wolfReviveRecoveryConfirmOnlyReady(o);
            openModal=this.wolfReviveRecoveryOpenModalReady(o);
            if((!wolfReviveRecoverySelectAttempted&&!confirmOnly&&!openModal)||wolfReviveRecoveryConfirmAttempted||!wolfReviveRecoveryCurrent(o)||
               o.frameId<=wolfReviveRecoverySelectFrame||!target)throw new Error('Fresh exact Teyvat Fried Egg revival modal and available stock required');
            if(!priorPermit||priorPermit.session!==request.session||priorPermit.kind!=='reviveTrialKaeyaRecovery'||
               priorPermit.confirmationAttemptedAt!==undefined||(!confirmOnly&&!openModal&&priorPermit.requestId!==request.id))
                throw new Error('Unconsumed one-shot revival confirmation marker required');
            if(openModal) {
                priorPermit.usedAt=Date.now();priorPermit.requestId=request.id;
                var hp=o.hud&&o.hud.health;
                if(hp&&hp.max===1055&&hp.current>0)wolfReviveRecoveryAmberBaseline={current:hp.current,max:hp.max};
            }
            priorPermit.confirmationAttemptedAt=Date.now();priorPermit.confirmationRequestId=request.id;
            if(!file.writeTextSync('wolf-revive-kaeya-recovery.json',JSON.stringify(priorPermit)))throw new Error('Cannot persist one-shot confirmation marker');
            var savedPermit=JSON.parse(file.readTextSync('wolf-revive-kaeya-recovery.json'));
            if(!savedPermit||savedPermit.confirmationRequestId!==request.id||savedPermit.confirmationAttemptedAt!==priorPermit.confirmationAttemptedAt||
               (openModal&&(savedPermit.usedAt!==priorPermit.usedAt||savedPermit.requestId!==request.id)))
                throw new Error('Confirmation marker consumption was not verified');
            wolfReviveRecoveryConfirmAttempted=true;wolfReviveRecoveryConfirmFrame=o.frameId;
            var e={type:'wolfReviveKaeyaRecoveryConfirm',label:target.label,quantity:target.quantity,inventoryStock:target.inventoryStock,frameId:o.frameId,x:target.x,y:target.y,startedAt:Date.now()};events.push(e);
            try{click(target.x,target.y);}finally{e.finishedAt=Date.now();}
        },
        wolfReviveRecoveryOutcome: function(o) {
            checkStop();o=o||lastObservation;
            if(!wolfReviveRecoveryConfirmAttempted||!wolfReviveRecoveryCurrent(o)||o.frameId<=wolfReviveRecoveryConfirmFrame||
               actOneWolfReviveItemModalVisible(o))return null;
            if(wolfReviveRecoverySafeKaeya(o))return 'revived';
            var hp=o.hud&&o.hud.health;
            if(wolfReviveRecoverySafeAmber(o)&&wolfReviveRecoveryAmberBaseline&&hp&&hp.max===wolfReviveRecoveryAmberBaseline.max&&
               hp.current===wolfReviveRecoveryAmberBaseline.current)return 'amber';
            return null;
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
            var pauseHudReady=pause&&(actOneWolfPauseHud(lastObservation,Date.now())||
                lastObservation&&lastObservation.session===request.session&&actOneWolfDeadTrialPauseOnlyHud(lastObservation,Date.now(),request.session));
            var bankPermit=null,bankReady=false;
            if(request.step==='wolfForwardFine') {
                try {bankPermit=JSON.parse(file.readTextSync('wolf-bank-approach.json'));}
                catch(e) {bankPermit=null;}
                bankReady=actOneWolfBankApproachReady(lastObservation,request,bankPermit,Date.now());
            }
            if(!(pause?pauseHudReady:actOneWolfDomainHud(lastObservation,Date.now())||actOneWolfRecoveryTravelHud(lastObservation,Date.now())||bankReady))
                throw new Error('Fresh safe Wolf trial HUD required');
            if(request.step==='wolfAdvance') { var advance=actOneWolfAdvanceState(lastObservation,Date.now());if(!advance.ok)throw new Error(advance.reason); }
            var reports=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
            if(!actOneWolfEntryProven(reports,request.session)) throw new Error('Same-session Wolf entry required');
            if(lastObservation.hud.interact&&request.step!=='wolfPause') throw new Error('Inspect available Wolf interaction before moving');
            if(action&&request.step!=='wolfPause'&&(lastObservation.hud.enemyBars||[]).length)throw new Error('Enemy acquired; use bounded Wolf combat');
            if(bankReady) {
                bankPermit.usedAt=Date.now();bankPermit.requestId=request.id;
                if(!file.writeTextSync('wolf-bank-approach.json',JSON.stringify(bankPermit)))throw new Error('Cannot consume bank approach permit');
            }
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
        wolfRecoveryCombatCurrent: function(o) {
            checkStop();o=o||lastObservation;
            return !!(request&&request.mission==='questStep'&&request.step==='wolfRecoveryCombat'&&o&&o.session===request.session&&
                lastObservation&&o.frameId===lastObservation.frameId&&o.timestamp===lastObservation.timestamp&&Number.isInteger(o.frameId)&&
                Number.isFinite(Number(o.timestamp))&&Date.now()>=Number(o.timestamp)&&Date.now()-o.timestamp<=1000);
        },
        wolfRecoveryCombatContinueReady: function(o) {
            checkStop();o=o||lastObservation;
            if(wolfRecoveryContinueAttempted||wolfRecoveryBegun||!this.wolfRecoveryCombatCurrent(o)||!actOneWolfResumeSeedTarget(o,Date.now())) return false;
            var h=o.hud;
            if(!h||h.world!==false||h.journal!==false||h.bigMap!==false||h.auto!==false||h.dialogueReady!==false||h.choice!==false||
               h.objectiveChanged!==false||h.tutorialStep!==null||h.loading===true||h.unknownHud===true||h.climbing===true) return false;
            return actOneWolfEntryProven(JSON.parse(file.readTextSync('reports/'+request.session+'.json')),request.session);
        },
        wolfRecoveryCombatContinue: function() {
            checkStop();var o=lastObservation,target=actOneWolfResumeSeedTarget(o,Date.now());
            if(!this.wolfRecoveryCombatContinueReady(o)||!target) throw new Error('Fresh exact same-session Wolf pause required');
            wolfRecoveryContinueAttempted=true;
            var e={type:'wolfRecoveryCombatContinue',frameId:o.frameId,x:Math.round(target.x+target.width/2),y:Math.round(target.y+target.height/2),startedAt:Date.now()};
            events.push(e);try{click(e.x,e.y);}finally{e.finishedAt=Date.now();}
        },
        wolfRecoveryCombatActiveReady: function(o) {
            checkStop();o=o||lastObservation;
            if(!wolfRecoveryContinueAttempted||!this.wolfRecoveryCombatCurrent(o)||!actOneWolfBurstRecoveryActiveHud(o,Date.now(),0.3)) return false;
            var rows=o.ocr||[];
            if(rows.filter(function(r){return String(r.text||'').trim()==='Kaeya'&&r.x>1550&&r.y>300&&r.y<600;}).length!==1||
               rows.filter(function(r){return String(r.text||'').trim()==='Trial'&&r.x>1700&&r.y>300&&r.y<600;}).length!==1) return false;
            return actOneWolfEntryProven(JSON.parse(file.readTextSync('reports/'+request.session+'.json')),request.session);
        },
        wolfRecoveryCombatBegin: function(o) {
            if(wolfRecoveryBegun||!this.wolfRecoveryCombatActiveReady(o)) throw new Error('Fresh active Trial Kaeya HUD required to begin recovery');
            wolfRecoveryBegun=true;wolfRecoveryStartedAt=Date.now();wolfRecoveryInitialHp=Number(o.hud.health.current);
            wolfRecoveryLastHp=wolfRecoveryInitialHp;wolfRecoveryAfterResumeFrame=o.frameId;
        },
        wolfRecoveryCombatKey: async function(key) {
            checkStop();var o=lastObservation,h=o&&o.hud,hp=h&&h.health,rows=o&&o.ocr||[];
            if(!wolfRecoveryBegun||!this.wolfRecoveryCombatActiveReady(o)||['VK_3','VK_E','VK_LBUTTON'].indexOf(key)<0||
               !Array.isArray(h.enemyBars)||!h.enemyBars.length||!hp||hp.max!==1427||
               wolfRecoveryActions.VK_3+wolfRecoveryActions.VK_E+wolfRecoveryActions.VK_LBUTTON>=30||
               Date.now()-wolfRecoveryStartedAt>=20000||wolfRecoveryInitialHp-Number(hp.current)>1427*0.2||wolfRecoveryLastInputFrame===o.frameId)
                throw new Error('Recovery action exceeded fresh HUD, health, time, or action guards');
            if(key==='VK_3') throw new Error('Recovery cannot change party after Trial Kaeya was verified');
            if(Number(hp.current)/1427<0.3) throw new Error('Wolf recovery health below 30%');
            if(key==='VK_E'&&Date.now()-wolfRecoveryLastEAt<6500||key==='VK_LBUTTON'&&Date.now()-wolfRecoveryLastAttackAt<250)
                throw new Error('Recovery combat key cooldown has not elapsed');
            if((key==='VK_E'||key==='VK_LBUTTON')&&!rows.some(function(r){return String(r.text||'').trim()==='Kaeya'&&r.x>1550&&r.y>300&&r.y<600;}))
                throw new Error('Exact Kaeya Trial identity required for combat input');
            var e={type:'wolfRecoveryCombatKey',key:key,frameId:o.frameId,startedAt:Date.now()};
            wolfRecoveryActions[key]++;events.push(e);wolfRecoveryLastHp=Number(hp.current);wolfRecoveryLastInputFrame=o.frameId;
            if(key==='VK_E')wolfRecoveryLastEAt=Date.now();else wolfRecoveryLastAttackAt=Date.now();
            try{await boundedKey(key,60);}finally{e.finishedAt=Date.now();}
        },
        wolfRecoveryCombatPauseReady: function(o) {
            checkStop();o=o||lastObservation;
            return !!(wolfRecoveryContinueAttempted&&!wolfRecoveryPauseAttempted&&this.wolfRecoveryCombatCurrent(o)&&
                actOneWolfBurstRecoveryActiveHud(o,Date.now(),0));
        },
        wolfRecoveryCombatEscape: async function() {
            checkStop();var o=lastObservation;
            if(!this.wolfRecoveryCombatPauseReady(o)) throw new Error('Fresh safe active Wolf HUD required before explicit Escape');
            if(!actOneWolfEntryProven(JSON.parse(file.readTextSync('reports/'+request.session+'.json')),request.session)) throw new Error('Same-session Wolf entry required');
            if(wolfRecoveryLastInputFrame===o.frameId) throw new Error('Fresh frame required before recovery Escape');
            wolfRecoveryLastHp=Number(o.hud.health.current);
            wolfRecoveryPauseAttempted=true;wolfRecoveryPauseFrame=o.frameId;wolfRecoveryLastInputFrame=o.frameId;
            var e={type:'wolfRecoveryCombatEscape',key:'VK_ESCAPE',frameId:o.frameId,startedAt:Date.now()};events.push(e);
            try{await boundedKey('VK_ESCAPE',60);}finally{e.finishedAt=Date.now();}
        },
        wolfRecoveryCombatPauseVerified: function(o) {
            checkStop();o=o||lastObservation;
            var verified=!!(wolfRecoveryPauseAttempted&&this.wolfRecoveryCombatCurrent(o)&&actOneWolfResumeSeedTarget(o,Date.now())&&
                actOneWolfEntryProven(JSON.parse(file.readTextSync('reports/'+request.session+'.json')),request.session));
            if(verified) wolfRecoveryPauseFrame=o.frameId;
            return verified;
        },
        wolfRecoveryCombatStats: function() {var hp=lastObservation&&lastObservation.hud&&lastObservation.hud.health;
            if(hp&&Number.isFinite(Number(hp.current))&&Number(hp.current)>0&&hp.max===1427) wolfRecoveryLastHp=Number(hp.current);
            return {hpInitial:wolfRecoveryInitialHp,hpLast:wolfRecoveryLastHp,maxHp:1427,
            continueAttempts:wolfRecoveryContinueAttempted?1:0,actionCounts:{VK_3:wolfRecoveryActions.VK_3,VK_E:wolfRecoveryActions.VK_E,VK_LBUTTON:wolfRecoveryActions.VK_LBUTTON},
            afterResumeFrame:wolfRecoveryAfterResumeFrame,pauseFrame:wolfRecoveryPauseFrame};},
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
        wolfClosingCharacterRecoveryReady: function(o) {
            checkStop();var h=o&&o.hud,rows=o&&o.ocr||[];
            if(!request||request.mission!=='recover'||!o||o.session!==request.session||!lastObservation||o.frameId!==lastObservation.frameId||
               !Number.isFinite(o.timestamp)||Date.now()<o.timestamp||Date.now()-o.timestamp>1000||o.map!==null||!h||h.characterAcquired!=='Kaeya'||
               h.auto||h.choice||h.dialogueReady||h.journal||h.bigMap||
               rows.filter(function(r){return String(r.text||'').trim()==='Obtained New Character'&&r.x>100&&r.x<550&&r.y>500&&r.y<580;}).length!==1||
               rows.filter(function(r){return String(r.text||'').trim()==='Kaeya'&&r.x>100&&r.x<500&&r.y>560&&r.y<670;}).length!==1||
               !rows.some(function(r){return String(r.text||'').trim()==='Click anywhere in the blank area to continue'&&r.x>600&&r.x<1250&&r.y>990&&r.y<1040;})||
               file.isExists('reports/'+request.session+'.wolfKaeyaAcquisitionContinue.json'))return false;
            try {
                var history=JSON.parse(file.readTextSync('reports/'+request.session+'.json'));
                if(!actOneWolfEntryProven(history,request.session))return false;
                return history.some(function(r){var result=r&&r.details&&r.details.result,events=r&&r.details&&r.details.inputEvents;
                    if(!r||r.session!==request.session||r.mission!=='recover'||r.status!=='completed'||!result||result.closingDialogueContinuation!==true||
                       result.rootDirected!==true||result.questComplete!==false||!Array.isArray(events)||
                       events.filter(function(e){return e&&e.type==='wolfClosingDialogueContinuation'&&e.rootDirected===true;}).length!==1||
                       !Number.isFinite(r.timestamp)||r.timestamp>o.timestamp||typeof r.id!=='string'||!/^mission-[a-f0-9]{32}$/.test(r.id))return false;
                    var saved=JSON.parse(file.readTextSync('receipts/'+request.session+'/'+r.id+'.json'));
                    if(saved.id!==r.id||saved.status!==r.status||JSON.stringify(saved.details)!==JSON.stringify(r.details))return false;
                    return !history.some(function(later){return later&&later.session===request.session&&Array.isArray(later.details&&later.details.inputEvents)&&
                        later.details.inputEvents.some(function(e){return e&&e.type!=='controllerRevision'&&Number.isFinite(e.startedAt)&&e.startedAt>r.timestamp;});});
                });
            }catch(e){return false;}
        },
        wolfClosingCharacterRecoveryContinue: function() {
            checkStop();var o=lastObservation;
            if(!this.wolfClosingCharacterRecoveryReady(o))throw new Error('Fresh witnessed Kaeya acquisition after Wolf closing required');
            var path='reports/'+request.session+'.wolfKaeyaAcquisitionContinue.json',marker={session:request.session,frameId:o.frameId,attemptedAt:Date.now()};
            if(!file.writeTextSync(path,JSON.stringify(marker))||JSON.stringify(JSON.parse(file.readTextSync(path)))!==JSON.stringify(marker))throw new Error('Acquisition continuation persistence failed');
            return this.continueCharacter();
        },
        wolfClosingDialogueContinuationReady: function(o) {checkStop();return !!wolfClosingContinuationPermit(o);},
        runWolfClosingDialogueContinuation: async function(initial,observe) {
            checkStop();var p=wolfClosingContinuationPermit(lastObservation);
            if(!p||!initial||initial.frameId!==lastObservation.frameId)throw new Error('Fresh witnessed closing choice and completed dialogue receipt required');
            p.usedAt=Date.now();p.usedFrameId=initial.frameId;
            if(!file.writeTextSync('wolf-closing-dialogue.json',JSON.stringify(p)))throw new Error('Closing continuation permit persistence failed');
            var saved=JSON.parse(file.readTextSync('wolf-closing-dialogue.json'));
            if(saved.usedAt!==p.usedAt||saved.usedFrameId!==p.usedFrameId||saved.priorRecoveryId!==p.priorRecoveryId)throw new Error('Closing continuation permit readback failed');
            events.push({type:'wolfClosingDialogueContinuation',frameId:initial.frameId,startedAt:Date.now(),rootDirected:true});
            var run=eval(file.readTextSync('mission.js')+'\nActOneMission.runDialogue;');
            return await run(this,observe,{deadlineMs:60000,maxPresses:40});
        },
        wolfClosingDialogueRecoveryReady: function(o) {
            checkStop();
            return !!(request&&request.mission==='recover'&&o&&lastObservation&&o.frameId===lastObservation.frameId&&
                o.timestamp===lastObservation.timestamp&&actOneWolfClosingDialogueState(o,Date.now(),request.session)&&
                (wolfClosingState.begun?wolfClosingState.inputs<16&&o.frameId>wolfClosingState.lastFrame&&o.timestamp>wolfClosingState.lastFinishedAt:
                    o.frameId>request.expectedFrameId&&wolfClosingPermit(o)));
        },
        wolfClosingDialogueRecoveryAdvance: async function() {
            checkStop();var o=lastObservation;
            if(!this.wolfClosingDialogueRecoveryReady(o))throw new Error('Fresh witnessed Wolf closing dialogue required');
            if(!wolfClosingState.begun) {
                var p=wolfClosingPermit(o);p.usedAt=Date.now();p.usedFrameId=o.frameId;
                if(!file.writeTextSync('wolf-closing-dialogue.json',JSON.stringify(p)))throw new Error('Closing-dialogue permit persistence failed');
                var saved=JSON.parse(file.readTextSync('wolf-closing-dialogue.json'));
                if(saved.usedAt!==p.usedAt||saved.usedFrameId!==o.frameId||saved.strikeRequestId!==p.strikeRequestId)throw new Error('Closing-dialogue permit readback failed');
                wolfClosingState.begun=true;
            }
            wolfClosingState.inputs++;wolfClosingState.lastFrame=o.frameId;
            var e={type:'wolfClosingDialogueAdvance',frameId:o.frameId,startedAt:Date.now(),rootDirected:true};events.push(e);
            try{return await boundedKey('VK_SPACE',60);}
            finally{
                e.finishedAt=Date.now();wolfClosingState.lastFinishedAt=e.finishedAt;
                events.forEach(function(k){if(k&&k.type==='key'&&k.key==='VK_SPACE'&&k.frameId===undefined&&
                    k.startedAt>=e.startedAt&&k.finishedAt<=e.finishedAt)k.frameId=o.frameId;});
                release();
            }
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
        healTravelerAtStatue: async function () {
            checkStop();
            if(!lastObservation || Date.now()-lastObservation.timestamp>1000 ||
               !lastObservation.ocr.some(function(r){return /Click on the character portrait to restore HP/.test(r.text) && r.y<100;}) ||
               !lastObservation.ocr.some(function(r){return /^Statue.s Blessing$/.test(r.text.trim()) && r.x>1400 && r.y<100;}) ||
               !lastObservation.ocr.some(function(r){return /Restorative Power:\s*[1-9][0-9]*\s*\//.test(r.text);})) throw new Error('Fresh Statue healing panel required');
            // The recorded starter roster has Traveler, Amber, then Kaeya.
            // Heal the third portrait only when its card is present in this panel.
            var portraits=actOneStatueHealingPortraits(lastObservation.ocr);
            events.push({type:'healStarterParty',portraits:portraits,y:160,startedAt:Date.now()});
            for(var portraitIndex=0;portraitIndex<portraits.length;portraitIndex++){
                if(portraitIndex){await sleep(300);checkStop();}
                if(request.step==='actTwoStatueHeal')await actOneAccountUiClick({checkStop:checkStop,ready:ready,move:moveMouseTo,down:leftButtonDown,up:leftButtonUp,sleep:sleep},{x:portraits[portraitIndex],y:160});else click(portraits[portraitIndex],160);
            }
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
            if(lastObservation&&lastObservation.hud.tutorialStep==='wagnerChoice'){
                if(Date.now()-lastObservation.timestamp>1000||!actOneWagnerChoiceTutorial(lastObservation.ocr))throw new Error('Fresh exact Wagner choice tutorial required');
                await boundedKey('VK_F',60,lastObservation.frameId);return 'wagnerChoice';
            }
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
            if(lisaNavigationRequest()){
                if(!lisaNavigationInputReady(lastObservation))throw new Error('Fresh protected Lisa navigation field required before rotation');
                lisaNavigationState.lastInputFrame=lastObservation.frameId;
            }
            events.push({ type: 'rotate', dx: dx, frameId:lastObservation&&lastObservation.frameId, startedAt: Date.now() }); moveMouseBy(dx, 0);
        },
        forward: async function (ms) {
            if (!Number.isInteger(ms) || ms < 1 || ms > 800) throw new Error('Invalid movement duration');
            if(lisaNavigationRequest()){
                checkStop();if(!lisaNavigationInputReady(lastObservation))throw new Error('Fresh protected Lisa navigation field required before forward input');
                lisaNavigationState.lastInputFrame=lastObservation.frameId;
                lisaNavigationState.moves=(lisaNavigationState.moves||0)+1;
                if(lisaNavigationState.moves%3===1){
                    events.push({type:'lisaNavigationSprint',frameId:lastObservation.frameId,durationMs:80,startedAt:Date.now()});
                    await boundedKey('VK_SHIFT',80,lastObservation.frameId);
                }
            }
            return boundedKey('VK_W', ms,lastObservation&&lastObservation.frameId);
        },
        descendClimb: function (ms) { if (!Number.isInteger(ms) || ms < 1 || ms > 800) throw new Error('Invalid climb descent duration'); return boundedKey('VK_S', ms); },
        pinObservation: function (session, frame) {
            try { file.pinCaptureEvidence(session, frame); }
            catch(error){var blocked=new Error('Capture evidence pin failed: '+String(error));blocked.code='CAPTURE_STORAGE_BLOCKED';throw blocked;}
        },
        write: function (p, t) { if (!file.writeTextSync(p, t)) {var e=new Error('Cannot write ' + p);e.code='CAPTURE_STORAGE_BLOCKED';throw e;} },
        append: function (p,t) {if(!file.writeTextSync(p,t,true)){var e=new Error('Cannot append '+p);e.code='CAPTURE_STORAGE_BLOCKED';throw e;}},
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
                if(typeof genshin.GetGameWindowInfo==='function') {
                    try {focusEvent.windowBefore=JSON.parse(genshin.GetGameWindowInfo());}
                    catch(e) {focusEvent.windowInfoError=String(e&&e.message||e);}
                }
                events.push(focusEvent);
                var focusError = null, readyError = null;
                try { await genshin.focusGame(); } catch (e) { focusError = e; }
                focusEvent.resultingFocus = genshin.isGameForeground === true;
                try { ready(); } catch (e) { readyError = e; }
                focusEvent.ready = !readyError;
                focusEvent.finishedAt = Date.now();
                focusEvent.error = focusError ? String(focusError&&focusError.message||focusError) : readyError ? String(readyError&&readyError.message||readyError) : null;
                if(typeof genshin.GetGameWindowInfo==='function') {
                    try {focusEvent.windowAfter=JSON.parse(genshin.GetGameWindowInfo());}
                    catch(e) {focusEvent.windowInfoAfterError=String(e&&e.message||e);}
                }
                if (focusError) throw focusError;
                if (readyError) throw readyError;
            } else ready();
            enemyBarDiagnostic=null;ocrPrimitiveMs=0;ocrReadCount=0;
            var t0 = Date.now(), img = captureGameRegion(), captureMs = Date.now() - t0;
            try {
                if (Number(img.width) !== 1920 || Number(img.height) !== 1080) throw new Error('1920x1080 capture required');
                var o0 = Date.now(), rows = readRows(img, 0, 0, 1920, 1080);
                if(request&&request.step==='actTwoCooking'){
                    rows=actOneMergeControlCropRows(rows,scaledRows(img,1310,120,490,110),1310,120);
                    rows=actOneMergeControlCropRows(rows,scaledRows(img,1330,680,220,35),1330,680);
                    rows=actOneMergeControlCropRows(rows,scaledRows(img,75,295,130,35),75,295);
                    rows=actOneMergeControlCropRows(rows,scaledRows(img,80,525,200,35),80,525);
                }
                if(request&&/^actTwo/.test(request.step||''))rows=actTwoCyrusRows(rows);
                if(request&&(/^actTwo/.test(request.step||'')||request.mission==='navigation')&&
                    actTwoAutoCropNeeded(rows))
                    rows=actOneMergeControlCropRows(rows,scaledRows(img,90,20,100,65),90,20);
                if(actTwoMapResinCropNeeded(rows))rows=actOneMergeControlCropRows(rows,scaledRows(img,1615,25,140,45),1615,25);
                if(request&&(request.mission==='navigation'&&['Explore for Adventure Rank','Talk to Kaeya','Speak to Lynn','Give the Chicken-Mushroom Skewer to Lynn','Talk to Amber','Go to the exam point'].indexOf(request.objective)>=0||/^actTwo/.test(request.step||''))&&!actTwoOriginalAccount(rows)){
                    rows=actOneMergeControlCropRows(rows,scaledRows(img,1680,1040,/^actTwo(?:WorldMap|MapClose|CityTeleport|WindriseTeleport|LionTeleport|NorthTeleport)$/.test(request.step||'')?190:240,40),1680,1040);
                }
                var fullOcrMs = Date.now() - o0,reviveStockOcrMs=0;
                if(request&&request.mission==='recover'&&actOneWolfReviveItemModalVisible({ocr:rows})&&
                   rows.some(function(r){return String(r.text||'').trim()==='Teyvat Fried Egg';})&&
                   rows.some(function(r){return String(r.text||'').trim()==='Revives a character and restores 100 HP.';})) {
                    // The star above the stock number can merge into the full OCR row.
                    // Read only the digit band from this same capture; keep the raw row.
                    var stock0=Date.now(),stockCrop=scaledRows(img,930,438,65,27);
                    rows=actOneMergeControlCropRows(rows,stockCrop,930,438);reviveStockOcrMs=Date.now()-stock0;
                }
                var health0 = Date.now(), healthRead = readHealth(img, rows), healthRows = healthRead.rows;
                var healthOcrMs = Date.now() - health0, objective0 = Date.now();
                var reusedObjectiveRows = actOneObjectiveRows(rows, request && request.objective);
                var objectiveRows = reusedObjectiveRows || readRows(img, 65, 230, 630, 85);
                if(request&&request.mission==='navigation'&&request.objective==='Talk to Kaeya'&&
                   !objectiveRows.some(function(r){return String(r.text).replace(/\s/g,'')==='TalktoKaeya';})&&actOneHealth(healthRows)){
                    // White tracked text overlaps cyan NPC labels at Good Hunter.
                    // Reread the same capture with the cyan pixels excluded.
                    var questCrop=null,questMask=null,questBgr=null,questMat=null,questScaled=null;
                    try{
                        questCrop=img.deriveCrop(65,240,300,40);
                        questMask=questCrop.srcMat.inRange(new OpenCvSharp.OpenCvSharp.Scalar(210,210,210),new OpenCvSharp.OpenCvSharp.Scalar(255,255,255));
                        questBgr=questMask.cvtColor(OpenCvSharp.OpenCvSharp.ColorConversionCodes.GRAY2BGR,0);
                        questMat=questBgr.resize(new OpenCvSharp.OpenCvSharp.Size(900,120));
                        questScaled=new ImageRegion(questMat,0,0);questMat=null;
                        var whiteQuestRows=readRows(questScaled,0,0,900,120).map(function(r){return {text:r.text,x:65+r.x/3,y:240+r.y/3,width:r.width/3,height:r.height/3};});
                        objectiveRows=objectiveRows.concat(whiteQuestRows);rows=rows.concat(whiteQuestRows);
                    }finally{dispose(questScaled);dispose(questMat);dispose(questBgr);dispose(questMask);dispose(questCrop);}
                }
                if(request&&/^actTwo/.test(request.step||'')&&actOneHealth(healthRows)&&actTwoAmbushQuestAnchor(rows.concat(objectiveRows))){
                    // The same capture's exact tracked title associates this small yellow distance band.
                    var ambushDistanceRows=scaledRows(img,75,278,110,32).map(function(r){return {text:r.text,x:75+r.x/3,y:278+r.y/3,width:r.width/3,height:r.height/3};});
                    objectiveRows=actTwoAmbushQuestRows(rows.concat(objectiveRows),objectiveRows,ambushDistanceRows);
                }
                var objectiveOcrMs = Date.now() - objective0;
                var ocrMs = Date.now() - o0;
                var p0 = Date.now(), png = 'observations/' + session + '/frame-' + String(frame).padStart(4, '0') + '.png';
                if (!file.writeImageSync(png, img.srcMat)) {var blocked=new Error('PNG write failed: capture storage is blocked');blocked.code='CAPTURE_STORAGE_BLOCKED';throw blocked;}
                var pngMs = Date.now() - p0, map0 = Date.now(), pos = null, mapDiagnostic = null;
                try {
                    var mp,regionalObservation=false;
                    if(request&&request.step==='actTwoField'){try{regionalObservation=actTwoRegionalObservationPlan(request,JSON.parse(file.readTextSync('act-two-field-request.json')));}catch(regionalReadError){regionalObservation=false;}}
                    if(regionalObservation){mapDiagnostic={reason:'Reviewed regional field plan; minimap matching intentionally omitted'};}
                    else if(request&&request.mission==='questStep'&&['windriseReveal','lionFieldCombat','lionFieldProbe','lisaStatueRecovery','lisaVisualMove','lisaGlide','lisaCloseThreat','lionVisualMove','lionLocalPause'].indexOf(request.step)>=0) {
                        mapDiagnostic={reason:'Root-witnessed uncharted approach; no map coordinate inferred'};
                        // Wait for the complete same-capture field HUD below. A fading
                        // inventory can expose HP before the owned-party slot is readable.
                    } else if(request&&request.mission==='navigation') {
                        var navAnchor=actOneNavigationMapAnchor(request,navLastAcceptedPosition);
                        var gpsAllowed=!lisaNavigationRequest()||lisaNavigationState.active&&actOneHealth(healthRows)&&
                            !rows.some(function(r){return r.text.trim()==='Auto';});
                        if(navAnchor&&gpsAllowed) {
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
                // The recorded three-dot Lisa subtitle is omitted even by
                // enlarged OCR. Require its three separated white dot patches
                // and an otherwise dark surrounding strip in this capture.
                var lisaSilentSubtitle=false;
                if(request&&request.mission==='dialogue'&&auto&&!actOneDialogueReady(rows,false)&&
                   rows.filter(function(r){return r.text.trim()==='Lisa'&&r.x>=850&&r.x<=1000&&r.y>=840&&r.y<900;}).length===1){
                    var silentCounts=[];
                    for(var patch of [[946,932,8,8],[956,932,8,8],[966,932,8,8],[935,930,48,12]]){
                        var silentCrop=null,silentMask=null;
                        try{silentCrop=img.deriveCrop(patch[0],patch[1],patch[2],patch[3]);
                            silentMask=silentCrop.srcMat.inRange(new OpenCvSharp.OpenCvSharp.Scalar(221,221,221),new OpenCvSharp.OpenCvSharp.Scalar(255,255,255));
                            silentCounts.push(Number(OpenCvSharp.OpenCvSharp.Cv2.countNonZero(silentMask)));
                        }finally{dispose(silentMask);dispose(silentCrop);}
                    }
                    lisaSilentSubtitle=actOneLisaSilentSubtitle(rows,silentCounts);
                }
                var interactionObjective=actOneResolveInteractionObjective(request&&request.objective,objectiveRows);
                var choice = rows.some(function (r) { return r.x > 1000 && r.y > 430 && r.y < 830 && r.text.trim().length > 6; }) || actTwoAmberFinalChoice(rows);
                var journal = rows.some(function (r) { return /^In Progress$/i.test(r.text.trim()) && r.y < 100; });
                var bigMap = !pos && !journal && (/Exploration Progress|Starfell Valley/.test(text) || actOneFullMapState(rows));
                var acquired = /Obtained New Character/.test(text) && /Click anywhere in the blank area to continue/.test(text) ? rows.filter(function(r) { return ['Amber','Kaeya','Lisa'].indexOf(r.text.trim()) >= 0 && r.x < 500 && r.y > 500 && r.y < 700; }) : [];
                var tutorialStep = /Press 2 to switch to Amber/i.test(text) && /Use Amber to defeat the airborne/i.test(text) ? 'switchAmber' : null;
                if(actOneWagnerChoiceTutorial(rows))tutorialStep='wagnerChoice';
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
                var windriseControlRequest=request&&request.mission==='questStep'&&['windriseReveal','lionFieldCombat','lionFieldProbe','lisaStatueRecovery','lisaVisualMove','lisaGlide','lisaCloseThreat'].indexOf(request.step)>=0&&
                    objectiveRows.some(function(r){return actOneLisaObjective(r.text);});
                if((pos||regionalObservation||(request&&request.mission==='questStep'&&/^(falcon|wolf)/.test(request.step))||windriseControlRequest||recoverWolfSafe||recoverWolfFoodDomainRequest)&&hp&&!auto&&!journal&&!bigMap&&!(auto&&choice)&&!tutorialStep&&
                   (!request||request.mission!=='recover'||recoverWolfSafe)&&actOneNeedsControlCrop(rows)) {
                    var control0=Date.now(),controlLocal=scaledRows(img,1520,985,390,80);
                    rows=actOneMergeControlCropRows(rows,controlLocal,1520,985);
                    controlOcrMs=Date.now()-control0;ocrMs=Date.now()-o0;
                }
                var wolfPartyRequest=request&&request.mission==='questStep'&&
                    (request.step==='wolfEntryApproach'||/^wolf(Combat|RecoveryCombat|BurstRecovery|CryoWait|CharactersOpen|WitnessAction|SpikeCrossFirst|SpikeCrossSecond|ReviveKaeyaPrompt|DefensiveCryo|Forward|ForwardFine|Advance|Left|Right|LookRight|LookLeft|LookDown|LookUp|Pause|Continue|Info|OpeningDialogue|KaeyaSkill|ChestInteract|LootInteract|WindTakeoff|WindRide|GlideForward|ConsoleInteract|ApproachEnemy)$/.test(request.step));
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
                if(request&&(request.mission==='observe'||request.mission==='questStep'&&['windriseReveal','worldInventoryClose','lionFieldCombat','lionFieldProbe','lisaStatueRecovery','lisaTeamInspect','lisaClimb','lisaVisualMove','lisaGlide','lisaCloseThreat'].indexOf(request.step)>=0||lisaNavigationRequest())&&
                   objectiveRows.some(function(r){return actOneLisaObjective(r.text)||request.step==='lisaStatueRecovery'&&['Talk to Lisa','Enter the temple'].indexOf(r.text.trim())>=0;})&&
                   hp&&!auto&&!journal&&!bigMap&&!choice&&!tutorialStep&&
                   ['Amber','Kaeya'].some(function(name){return !rows.some(function(r){return (name==='Kaeya'?actOneKaeyaPartyLabel(r.text):r.text.trim()===name)&&r.x>=1550&&r.x<=1800&&r.y>=300&&r.y<=600;});})) {
                    // Bright terrain can hide a party name in full-frame OCR. Repair only
                    // with exact labels read from this same captured party band.
                    var windrisePartyRows=scaledRows(img,1630,330,230,300);
                    rows=actOneMergeMissingLisaParty(rows,windrisePartyRows);ocrMs=Date.now()-o0;
                    if(!rows.some(function(r){return r.text.trim()==='Amber'&&r.x>=1550&&r.x<=1800&&r.y>=300&&r.y<=600;})) {
                        // Keep the adjacent Pyro portrait icon outside Amber's label crop.
                        var windriseAmberRows=scaledRows(img,1650,390,100,45);
                        rows=actOneMergeControlCropRows(rows,windriseAmberRows,1650,390);ocrMs=Date.now()-o0;
                    }
                }
                if(request&&(request.mission==='observe'||request.mission==='questStep'&&['lionFieldCombat','lionFieldProbe','lisaStatueRecovery','lisaTeamInspect','lisaClimb','lisaVisualMove','lisaGlide','lisaCloseThreat'].indexOf(request.step)>=0||lisaNavigationRequest())&&
                   objectiveRows.some(function(r){return actOneLisaObjective(r.text)||request.step==='lisaStatueRecovery'&&['Talk to Lisa','Enter the temple'].indexOf(r.text.trim())>=0;})&&hp&&!auto&&!journal&&!bigMap&&!choice&&!tutorialStep&&
                   rows.some(function(r){return actOneKaeyaPartyLabel(r.text)&&r.x>=1600&&r.x<=1800&&r.y>=460&&r.y<=540;})&&
                   !rows.some(function(r){return r.text.trim()==='3'&&r.x>=1850&&r.x<=1890&&r.y>=460&&r.y<=540;})) {
                    // The active character's grey slot number is easily lost in full OCR.
                    // Read the same capture rather than assuming the selected party slot.
                    var lionSlotRows=scaledRows(img,1845,475,60,65);
                    rows=actOneMergeControlCropRows(rows,lionSlotRows,1845,475);ocrMs=Date.now()-o0;
                }
                if(request&&request.step==='lisaStatueRecovery'&&hp&&!auto&&!journal&&!bigMap&&
                   objectiveRows.some(function(r){return ['Talk to Lisa','Enter the temple'].indexOf(r.text.trim())>=0;})&&
                   !rows.some(function(r){return r.text.trim()==='Lumina'&&r.x>=1600&&r.x<=1800&&r.y>=280&&r.y<=350;})){
                    var recoveryLuminaRows=scaledRows(img,1650,280,140,70).filter(function(r){return r.text.trim()==='Lumina';});
                    rows=actOneMergeControlCropRows(rows,recoveryLuminaRows,1650,280);ocrMs=Date.now()-o0;
                }
                if(request&&request.mission==='questStep'&&['lionVisualMove','lionLocalPause'].indexOf(request.step)>=0&&
                   !pos&&hp&&!auto&&!journal&&!bigMap&&!tutorialStep){
                    var lionLiveRows=scaledRows(img,1630,240,275,370);
                    // Recover missing labels only. Enlarging the same image can
                    // shift a short name enough to evade geometric deduplication.
                    lionLiveRows=lionLiveRows.filter(function(crop){
                        var label=String(crop.text||'').trim();
                        return ['Lumina','Amber','Kaeya','Lisa','Trial','4'].indexOf(label)<0||!rows.some(function(full){
                            return String(full.text||'').trim()===label&&full.x>=1630&&full.x<=1905&&full.y>=240&&full.y<=610;
                        });
                    });
                    rows=actOneMergeControlCropRows(rows,lionLiveRows,1630,240);ocrMs=Date.now()-o0;
                    if(!rows.some(function(r){return r.text.trim()==='Amber'&&r.x>=1600&&r.x<=1810&&r.y>=325&&r.y<=390;})){
                        var lionAmberName=scaledRows(img,1640,335,140,55).filter(function(r){return r.text.trim()==='Amber';});
                        rows=actOneMergeControlCropRows(rows,lionAmberName,1640,335);ocrMs=Date.now()-o0;
                    }
                    if(hp.max===1196&&!rows.some(function(r){return r.text.trim()==='4'&&r.x>=1850&&r.y>=530&&r.y<=590;})){
                        var lionTrialSlot=scaledRows(img,1845,525,60,65);
                        rows=actOneMergeControlCropRows(rows,lionTrialSlot,1845,525);ocrMs=Date.now()-o0;
                    }
                    if(!actOneGroundControlEvidence(rows)){
                        var lionControls=scaledRows(img,1630,990,240,65);
                        rows=actOneMergeControlCropRows(rows,lionControls,1630,990);ocrMs=Date.now()-o0;
                    }
                    if(request.step==='lionVisualMove'){
                        var lionSkill=scaledRows(img,1650,945,100,110);
                        rows=actOneMergeControlCropRows(rows,lionSkill,1650,945);ocrMs=Date.now()-o0;
                    }
                }
                var climbing=rows.some(function(r){return r.text.trim()==='X' && r.x>1500 && r.y>990;}) && rows.some(function(r){return r.text.trim()==='Space' && r.x>1600 && r.y>990;});
                var dialogueReady=actOneDialogueReady(rows,choice)||lisaSilentSubtitle&&!choice, objectiveChanged=/objective updated|quest completed/i.test(text),aerialBoss=null,interactionOcrMs=0,cooldownOcrMs=0;
                if(request&&request.mission==='questStep'&&['wolfCryoWait','wolfSpikeCrossFirst','wolfSpikeCrossSecond'].indexOf(request.step)>=0&&!pos&&hp&&hp.max===1427&&hp.current>0&&
                   !auto&&!journal&&!bigMap&&!dialogueReady&&!choice&&!climbing&&!tutorialStep&&!objectiveChanged&&
                   actOneGroundControlEvidence(rows)&&actOneWolfCryoCooldownRemaining({ocr:rows})===null) {
                    var cooldown0=Date.now(),cooldownLocal=scaledRows(img,1660,960,80,60);
                    rows=actOneMergeControlCropRows(rows,cooldownLocal,1660,960);
                    cooldownOcrMs=Date.now()-cooldown0;ocrMs=Date.now()-o0;
                }
                var interactionScreen={objective:interactionObjective,world:!!(!trackQuest&&pos&&hp&&!auto&&!journal&&!bigMap&&!dialogueReady&&!(auto&&choice)),
                    position:!!pos,health:hp,auto:auto,journal:journal,bigMap:bigMap,dialogueReady:dialogueReady,choice:auto&&choice,
                    climbing:climbing,objectiveChanged:objectiveChanged,tutorialStep:tutorialStep};
                if(request&&request.step==='actTwoField'&&hp&&!auto&&!journal&&!bigMap&&rows.some(function(r){return r.x>=1150&&r.x<=1500&&r.y>=450&&r.y<=620;})&&!rows.some(function(r){return r.text==='F'&&r.x>=1080&&r.x<=1170&&r.y>=450&&r.y<=620;})){
                    rows=actOneMergeControlCropRows(rows,scaledRows(img,1080,450,90,180),1080,450);
                }
                var statueInteractionScreen={auto:auto,journal:journal,bigMap:bigMap,dialogueReady:dialogueReady,choice:auto&&choice,
                    climbing:climbing,objectiveChanged:objectiveChanged,tutorialStep:tutorialStep,groundControls:actOneGroundControlEvidence(rows)};
                if(actOneShouldReadInteractionCrop(rows,interactionObjective,interactionScreen)||
                   actOneShouldReadStatueInteractionCrop(rows,statueInteractionScreen)||
                   request&&['actTwoAmberTalk','actTwoWindriseOculus','actTwoSaraOpen','actTwoStatueOpen','actTwoMushroom','actTwoCookOpen','actTwoLynnTalk','actTwoVileTalk','actTwoJackTalk','actTwoCyrusTalk','actTwoKaeyaReport'].indexOf(request.step)>=0&&hp&&!auto&&!journal&&!bigMap&&rows.some(function(r){return (request.step==='actTwoMushroom'?r.text==='Mushroom':request.step==='actTwoCookOpen'?/^(Lynn|Cook)$/.test(r.text):r.text===(request.step==='actTwoAmberTalk'?'Amber':request.step==='actTwoLynnTalk'?'Lynn':request.step==='actTwoVileTalk'?'Vile':request.step==='actTwoJackTalk'?'Jack':request.step==='actTwoCyrusTalk'?'Cyrus':'Kaeya'))&&r.x>=1150&&r.x<=1500&&r.y>=480&&r.y<=600;})&&!rows.some(function(r){return r.text==='F'&&r.x>=1080&&r.x<=1170&&r.y>=480&&r.y<=600;})||
                   request&&request.step==='actTwoHqEnter'&&hp&&!auto&&!journal&&!bigMap&&rows.some(function(r){return /Headquarters/.test(r.text)&&r.x>=1200&&r.x<=1500&&r.y>=495&&r.y<=580;})) {
                    var interaction0=Date.now(),interactionTop=request&&(request.step==='actTwoLynnTalk'||request.step==='actTwoCookOpen'||request.step==='actTwoMushroom')?470:490,interactionLocal=scaledRows(img,1080,interactionTop,90,request&&(request.step==='actTwoLynnTalk'||request.step==='actTwoCookOpen'||request.step==='actTwoMushroom')?120:100);
                    var interactionF=actOneInteractionCropF(interactionLocal,1080,interactionTop);
                    if(!interactionF&&request&&(request.step==='actTwoLynnTalk'||request.step==='actTwoCookOpen'||request.step==='actTwoMushroom')){
                        var lynnF=actOneMergeControlCropRows([],interactionLocal,1080,interactionTop).filter(function(r){return r.text==='F'&&r.x>=1080&&r.x<=1170&&r.y>=480&&r.y<=590;});
                        if(lynnF.length===1)interactionF=lynnF[0];
                    }
                    if(interactionF) rows=rows.concat([interactionF]);
                    if(request&&request.step==='actTwoHqEnter')rows=actOneMergeControlCropRows(rows,scaledRows(img,1200,495,360,85),1200,495);
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
                if(request&&request.mission==='questStep'&&request.step==='lionVisualMove'&&pos===null&&actOneShouldReadLionInteractionCrop(rows,wolfOpenDoorScreen)){
                    var lionInteraction0=Date.now(),lionInteractionLocal=scaledRows(img,1080,490,90,100);
                    var lionInteractionF=actOneInteractionCropF(lionInteractionLocal,1080,490);
                    if(lionInteractionF)rows=rows.concat([lionInteractionF]);
                    interactionOcrMs+=Date.now()-lionInteraction0;ocrMs=Date.now()-o0;
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
                if((request&&request.mission==='questStep'&&['wolfFeedKaeya','actTwoHeal'].indexOf(request.step)>=0||recoverFoodModal)&&pos===null&&
                   rows.filter(function(r){return r.text.trim()==='Kaeya'&&r.x>800&&r.x<1000&&r.y>240&&r.y<320;}).length===1&&
                   rows.filter(function(r){return r.text.trim()==='Sweet Madame'&&r.x>1300&&r.x<1650&&r.y>110&&r.y<180;}).length===1&&
                   actOneKnownSafeFoodBoundary({timestamp:Date.now(),map:null,hud:{world:false},ocr:rows},Date.now())) {
                    var quantityRows=scaledRows(img,1105,590,80,80).map(function(r){return {text:String(r.text||'').trim(),
                        x:1105+Number(r.x)/3,y:590+Number(r.y)/3,width:Number(r.width)/3,height:Number(r.height)/3};});
                    var digits=quantityRows.filter(function(r){return /^\d+$/.test(r.text);});
                    if(digits.length===1&&digits[0].text==='1'&&digits[0].x>1125&&digits[0].x<1165&&digits[0].y>605&&digits[0].y<655)
                        foodQuantity={value:1,source:'scaled-same-frame',frameId:frame,x:digits[0].x,y:digits[0].y};
                }
                if(request&&request.step==='actTwoSkewer'&&pos===null&&rows.some(function(r){return r.text==='Kaeya'&&r.x>800&&r.x<1000&&r.y>240&&r.y<320;})&&rows.some(function(r){return r.text==='Amount to use'&&r.x>600&&r.x<900&&r.y>590&&r.y<670;})&&eval(file.readTextSync('act-two-skewer.js')+'\nActTwoSkewer;').title(rows)){
                    var skewerDigits=scaledRows(img,1105,590,80,80).filter(function(r){return /^\d+$/.test(String(r.text).trim());});
                    if(skewerDigits.length===1&&String(skewerDigits[0].text).trim()==='1'&&skewerDigits[0].x/3+1105>1125&&skewerDigits[0].x/3+1105<1165&&skewerDigits[0].y/3+590>605&&skewerDigits[0].y/3+590<655)foodQuantity={value:1,source:'scaled-same-frame',frameId:frame};
                }
                var hud = { foodQuantity:foodQuantity, auto:auto, climbing:climbing, groundControls:actOneGroundControlEvidence(rows), enemyBars: combatObjective ? readEnemyBars(img, rows) : request&&/^falcon(Combat|AmberCombat|Ranged|Engage)$/.test(request.step) ? readEnemyBars(img,rows,4) : request&&request.mission==='questStep'&&/^wolf(Combat|RecoveryCombat|CryoWait|CharactersOpen|WitnessAction|SpikeCrossFirst|SpikeCrossSecond|PlatformObserve|DefensiveCryo|Forward|ForwardFine|Advance|Right|Left|LookRight|LookLeft|LookDown|LookUp|Pause|Continue|Info|OpeningDialogue|KaeyaSkill|TurretPass|ChestInteract|LootInteract|ConsoleInteract|ApproachEnemy)$/.test(request.step)&&hp&&!auto&&!journal&&!bigMap ? readEnemyBars(img,rows,5) : [], aerialBossVisible:aerialBossVisible, aerialBoss:aerialBoss, slimeTarget: tutorialStep === 'aimSlime' ? readSlime(img) : null, tutorialStep: tutorialStep, characterAcquired: acquired.length === 1 ? acquired[0].text.trim() : null, dialogueReady: dialogueReady, choice: auto && choice, journal: journal, bigMap: bigMap,
                    objectiveChanged: /objective updated|quest completed/i.test(text), health: hp, healthOcr: healthRows.map(function (r) { return r.text; }), healthDiagnostic:healthRead.diagnostic,
                    healthPct: hp && hp.max > 0 ? hp.current / hp.max : null,
                    lowHealth: !hp || hp.max <= 0 || hp.current > hp.max || hp.current / hp.max < 0.6,
                    world: !trackQuest && !!pos && !!hp && !auto && !journal && !bigMap,
                    interact: rows.some(function (r) { return (/^F$/.test(r.text.trim()) && r.x > 850 && r.y > 300 && r.y < 800) || (/^Teleport[- ]Waypoint$/i.test(r.text.trim()) && r.x>1100 && r.y>400 && r.y<700); }),
                    objectives: objectiveRows.map(function (r) { return r.text; }) };
                if (pos && request && (request.objective === 'Investigate what Paimon has found'||request.step==='actTwoExam')) hud.worldMarker = readMarker(img);
                if(regionalObservation&&!actTwoRegionalWorldEvidence(rows,hud)&&hud.groundControls&&!hud.auto&&!hud.bigMap&&!hud.journal&&(actTwoAmbushQuestAnchor(rows)||actTwoUntrackedRegionalGround(hud)||rows.some(r=>r.text==="Enter Raptor's Hideout"&&r.x>=50&&r.x<=120&&r.y>=240&&r.y<=280))){
                    rows=actOneMergeControlCropRows(rows,scaledRows(img,1640,240,250,350),1640,240);
                }
                if(regionalObservation)actTwoRepairHideoutObjective(rows,hud);
                if(regionalObservation&&actTwoRegionalWorldEvidence(rows,hud))hud.world=true;
                hud.enemyBarDiagnostic=enemyBarDiagnostic;
                var spikeSurfaceMs=0;
                if(request&&request.step==='actTwoField'&&climbing){var staminaReader=eval(file.readTextSync('climb-stamina.js')+'\nActTwoClimbStamina;');hud.climbStamina=staminaReader.read(img,OpenCvSharp.OpenCvSharp);}
                if(request&&request.mission==='questStep'&&['wolfSpikeCrossFirst','wolfSpikeCrossSecond','wolfForwardFine','wolfPlatformObserve','wolfWitnessAction'].indexOf(request.step)>=0&&
                   (request.step==='wolfWitnessAction'?actOneWolfDomainHud({timestamp:Date.now(),map:trackQuest?null:pos,hud:hud,ocr:rows},Date.now(),0.01):
                    actOneWolfSpikeActive({timestamp:Date.now(),map:trackQuest?null:pos,hud:hud,ocr:rows},Date.now(),'any',0.01))) {
                    var spikeSurface0=Date.now();hud.wolfSpikeSurface=readWolfSpikeSurface(img,['wolfSpikeCrossSecond','wolfPlatformObserve','wolfWitnessAction'].indexOf(request.step)>=0);spikeSurfaceMs=Date.now()-spikeSurface0;
                }
                var levelPanelOcrMs=0;
                if(request&&request.mission==='recover'&&actOneWolfAmberLevelPanelVisible({timestamp:Date.now(),map:trackQuest?null:pos,hud:hud,ocr:rows},Date.now())) {
                    var levelPanel0=Date.now();
                    function panelNumber(x,y,w,h) {
                        var numeric=scaledRows(img,x,y,w,h).map(function(r){return String(r.text||'').trim();}).filter(function(t){return /^\d[\d,]*$/.test(t);});
                        return numeric.length===1?Number(numeric[0].replace(/,/g,'')):null;
                    }
                    hud.wolfAmberLevel={frameId:frame,amount:panelNumber(1480,895,65,45),requiredMora:panelNumber(1315,995,100,45),
                        midTierStock:panelNumber(1480,832,65,28),mora:panelNumber(1665,24,110,47)};
                    levelPanelOcrMs=Date.now()-levelPanel0;
                }
                ready();
                if(request&&['lisaKaeyaLevel','actTwoKaeyaLevel'].indexOf(request.step)>=0&&['Kaeya','Lumina'].some(function(name){return actOneStarterLevelPanelVisible({timestamp:Date.now(),map:trackQuest?null:pos,hud:hud,ocr:rows},Date.now(),name);})){
                    function kaeyaPanelNumber(x,y,w,h){var values=scaledRows(img,x,y,w,h).map(function(r){return r.text.trim();}).filter(function(t){return /^\d[\d,]*$/.test(t);});
                        return values.length===1?Number(values[0].replace(/,/g,'')):null;}
                    hud.kaeyaLevel={frameId:frame,amount:kaeyaPanelNumber(1480,895,65,45),requiredMora:kaeyaPanelNumber(1315,995,100,45),
                        lowTierStock:kaeyaPanelNumber(1350,832,65,28),midTierStock:kaeyaPanelNumber(1480,832,65,28),
                        highTierStock:kaeyaPanelNumber(1610,832,65,28),mora:kaeyaPanelNumber(1665,24,110,47)};
                }
                if(request&&(request.mission==='observe'&&objectiveRows.some(function(r){return actOneLisaObjective(r.text);})||request.mission==='navigation'&&["Go to the exam point","Talk to Amber","Check the suspicious location and eliminate any threats","Explore for Adventure Rank","Purchase Fisherman's Toast",'Offer the Anemoculus to the Statue','Give the Chicken-Mushroom Skewer to Lynn','Speak to Lynn','Talk to Katheryne for more details','Talk to Wagner the blacksmith','Collect three Iron Chunks and give them to Wagner','Talk to Kaeya','Talk to Kaeya at the meeting spot','Report to Kaeya','Meet with the informant at the designated location','Talk to the informant','Solve the mystery (Go to Kaeya at the Knights of Favonius HQ for a hint)',"Go to the Adventurers' Guild and listen to their report"].indexOf(request.objective)>=0||request.mission==='questStep'&&['actTwoDaytime','actTwoMageNative','actTwoMageFinish','actTwoMageBurst','actTwoMagePrep','actTwoNativeCombat','actTwoNativeGroup','actTwoNativeFinish','actTwoNativeDeadlineProbe','actTwoField','actTwoFieldInspect','actTwoMapClose','actTwoLaunchPractice','actTwoVisual','actTwoNativeRoute','actTwoInformantCombat','actTwoOre','actTwoTownRecovery','actTwoTownClimb','actTwoTownRail','actTwoWaypoint','actTwoKaeyaTalk','actTwoKaeyaReport','actTwoJackTalk','actTwoCyrusTalk','actTwoVileTalk','actTwoLynnTalk','windriseReveal','lionFieldCombat','lionFieldProbe','lisaStatueRecovery','lisaTeamInspect','lisaClimb','lisaVisualMove','lisaGlide','lisaCloseThreat'].indexOf(request.step)>=0||lisaNavigationRequest())&&hp&&!auto&&!journal&&!bigMap) {
                    var fieldLevel=request.step==='actTwoMageBurst'||['actTwoFieldInspect','actTwoMapClose'].indexOf(request.step)>=0&&actTwoAmbushQuestAnchor(objectiveRows)?13:'any';
                    if(request.step==='actTwoField'){
                        try{fieldLevel=eval(file.readTextSync('act-two-field.js')+'\nActTwoField;').enemyLevel(JSON.parse(file.readTextSync('act-two-field-request.json')),request);}catch(fieldLevelError){fieldLevel='any';}
                    }
                    hud.enemyBars=readEnemyBars(img,rows,request.step==='actTwoInformantCombat'?5:fieldLevel);hud.enemyBarDiagnostic=enemyBarDiagnostic;
                    hud.compassAngle=Number(genshin.getCameraOrientation());
                }
                if(request&&request.mission==='questStep'&&['lionFieldCombat','lionFieldProbe','lisaStatueRecovery'].indexOf(request.step)>=0)
                    hud.world=actOneLionFieldWorld({session:session,frameId:frame,timestamp:Date.now(),hud:hud,ocr:rows},Date.now(),session,0,request.step==='lisaStatueRecovery');
                if(request&&request.step==='lisaStatueRecovery'&&lisaRecoveryState.teleported&&hud.world===true&&
                   hud.groundControls===true&&hud.climbing===false&&!hud.dialogueReady&&!hud.choice&&!hud.tutorialStep){
                    var recoveryMap0=Date.now();
                    try{
                        var recoveryPosition=genshin.getPositionFromMap('Teyvat',host.toSingle(-1323.474),host.toSingle(2566.115));
                        if(recoveryPosition&&Number.isFinite(Number(recoveryPosition.x))&&Number.isFinite(Number(recoveryPosition.y))&&
                           Math.hypot(Number(recoveryPosition.x)+1323.474,Number(recoveryPosition.y)-2566.115)<=20){
                            pos={x:Number(recoveryPosition.x),y:Number(recoveryPosition.y),map:'Teyvat',cameraAngle:Number(genshin.getCameraOrientation())};
                            mapDiagnostic={reason:'Starfell recovery anchor accepted'};
                        }else mapDiagnostic={reason:'Starfell recovery anchor rejected'};
                    }catch(recoveryMapError){mapDiagnostic={reason:String(recoveryMapError&&recoveryMapError.message||recoveryMapError)};}
                    mapMs+=Date.now()-recoveryMap0;ready();
                }
                if(request&&request.step==='lionFieldProbe'&&lionFieldState.climbReleaseArmed&&!lionFieldState.climbReleaseAttempted){
                    var climbHud=Object.assign({},hud,{world:true});
                    if(lisaClimbReleaseModule().ready({session:session,frameId:frame,timestamp:Date.now(),hud:climbHud,ocr:rows},Date.now(),session,
                        {armed:true,releaseAttempted:false,lastInputFrame:lionFieldState.lastInputFrame}))hud.world=true;
                }
                if(request&&request.mission==='questStep'&&request.step==='lionFieldProbe'&&
                   lionFieldState.chartedProbePending&&hud.world===true&&hud.groundControls===true&&hud.climbing===false){
                    lionFieldState.chartedProbePending=false;
                    var chartedMap0=Date.now(),statueAnchor=lionFieldState.chartedProbeAnchor||{x:-1265.917,y:1928.381,maxDistance:80};
                    try{
                        var chartedPosition=genshin.getPositionFromMap('Teyvat',host.toSingle(statueAnchor.x),host.toSingle(statueAnchor.y));
                        if(chartedPosition&&Number.isFinite(Number(chartedPosition.x))&&Number.isFinite(Number(chartedPosition.y))&&
                           Math.hypot(Number(chartedPosition.x)-statueAnchor.x,Number(chartedPosition.y)-statueAnchor.y)<=statueAnchor.maxDistance){
                            pos={x:Number(chartedPosition.x),y:Number(chartedPosition.y),map:'Teyvat',cameraAngle:Number(genshin.getCameraOrientation())};
                            mapDiagnostic={reason:'Charted Windrise local candidate accepted',anchor:statueAnchor};
                        }else mapDiagnostic={reason:'Charted Windrise candidate rejected',anchor:statueAnchor,
                            candidate:chartedPosition?{x:Number(chartedPosition.x),y:Number(chartedPosition.y)}:null};
                    }catch(chartedMapError){mapDiagnostic={reason:String(chartedMapError&&chartedMapError.message||chartedMapError)};}
                    mapMs+=Date.now()-chartedMap0;
                    ready();
                }
                lastObservation = { session: session, frameId: frame, timestamp: Date.now(), capturedAt: t0, screenshotPath: png, ocr: rows, map: trackQuest ? null : pos, mapDiagnostic:mapDiagnostic, hud: hud,
                    // ocrMs is a legacy cumulative window and can overlap later PNG/map work on fallback paths.
                    // ocrFindMultiMs times only OCR findMulti calls; it excludes image preparation and postprocessing.
                    timings: { mapDiagnostic:mapDiagnostic, captureMs: captureMs, ocrMs: ocrMs, ocrFindMultiMs:ocrPrimitiveMs, ocrReadCount:ocrReadCount, fullOcrMs: fullOcrMs, reviveStockOcrMs:reviveStockOcrMs, healthOcrMs: healthOcrMs, objectiveOcrMs: objectiveOcrMs, controlOcrMs:controlOcrMs, cooldownOcrMs:cooldownOcrMs, spikeSurfaceMs:spikeSurfaceMs, levelPanelOcrMs:levelPanelOcrMs, interactionOcrMs:interactionOcrMs, objectiveSource: reusedObjectiveRows ? 'fullFrame' : 'crop', pngWriteMs: pngMs, mapMs: mapMs, totalMs: Date.now() - t0 } };
                if(lisaNavigationRequest()&&lisaNavigationInputReady(lastObservation))lisaNavigationState.lastField=lastObservation;
                return lastObservation;
            } finally { dispose(img); }
        }
    };
}

if(typeof module!=='undefined'&&module.exports) module.exports.amberFinalChoice=actTwoAmberFinalChoice;
