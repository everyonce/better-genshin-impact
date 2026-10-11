function actOneObjectiveRows(rows, expected) {
    // Close crystal approach also requires the cropped height/distance reading.
    if (!expected || expected === 'Investigate what Paimon has found') return null;
    var candidates = rows.filter(function (r) { return r.x >= 65 && r.x < 695 && r.y >= 230 && r.y < 315; });
    function normalized(s) { return String(s).toLowerCase().replace(/\s+/g, ''); }
    return candidates.some(function (r) { return normalized(r.text) === normalized(expected); }) ? candidates : null;
}
function actOneEnemyBarSize(w,h) { return w>=2 && w<=300 && h>=3 && h<=12 && w/h>=0.15; }
function actOneEnemyBarAnchored(bar, rows) {
    if (!bar || !Array.isArray(rows)) return false;
    return rows.some(function (r) {
        // The enemy level is displayed above its health bar. Normalize common
        // OCR confusions, but require level 1 so the player's Lv.3 label cannot anchor it.
        var label=String(r.text||'').toUpperCase().replace(/\s+/g,'').replace(/[.|]/g,'');
        if (!/^LV[1IL]$/.test(label)) return false;
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
if (typeof module !== 'undefined' && module.exports) module.exports = { objectiveRows: actOneObjectiveRows, enemyBarSize:actOneEnemyBarSize, enemyBarAnchored:actOneEnemyBarAnchored, health:actOneHealth, fullHealthRows:actOneFullHealthRows, dialogueReady:actOneDialogueReady, navigateQuestState:actOneNavigateQuestState, navigateQuestButton:actOneNavigateQuestButton, trackQuestState:actOneTrackQuestState, trackQuestTarget:actOneTrackQuestTarget, altClick:actOneAltClick };

function createActOneAdapter(sessionId) {
    var expectedSession = Number(sessionId), held = null, request = null, events = [], lastObservation = null;
    function dispose(v) { if (v && typeof v.dispose === 'function') v.dispose(); }
    function sessionReady() {
        if (genshin.isRemoteDesktopSession !== true || Number(genshin.windowsSessionId) !== expectedSession || expectedSession !== 5) throw new Error('RDP session 5 required');
    }
    function ready() { sessionReady(); if (genshin.isGameForeground !== true) throw new Error('Game lost foreground focus'); }
    function release() { if (held) { var k = held; held = null; keyUp(k); } }
    function checkStop() {
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
    function readEnemyBars(img, rows) {
        var crop=img.deriveCrop(350,100,1250,800),mask=null;
        try {
            mask=crop.srcMat.inRange(new OpenCvSharp.OpenCvSharp.Scalar(75,75,230),new OpenCvSharp.OpenCvSharp.Scalar(110,110,255));
            var contours=mask.findContoursAsArray(OpenCvSharp.OpenCvSharp.RetrievalModes.External,OpenCvSharp.OpenCvSharp.ContourApproximationModes.ApproxSimple),candidates=[],bars=[];
            for(var i=0;i<contours.length;i++) {
                var b=OpenCvSharp.OpenCvSharp.Cv2.boundingRect(contours[i]),w=Number(b.width),h=Number(b.height);
                // A nearly defeated enemy has a very short red segment. Requiring
                // a wide bar made the controller lose the target before the final hit.
                var bar={x:350+Number(b.x)+w/2,y:100+Number(b.y)+h/2,width:w,height:h};
                if(actOneEnemyBarSize(w,h)) candidates.push(bar);
            }
            candidates.sort(function(a,b){return b.height-a.height;});
            // Full-frame OCR is cheap. If it misses the small green enemy label,
            // inspect at most four local crops around the most bar-like candidates.
            for(var c=0;c<candidates.length;c++) if(actOneEnemyBarAnchored(candidates[c],rows)) bars.push(candidates[c]);
            var fallbackCount=0;
            for(var f=0;bars.length===0 && f<candidates.length && fallbackCount<4;f++) {
                var candidate=candidates[f];
                if(bars.some(function(v){return Math.hypot(v.x-candidate.x,v.y-candidate.y)<2;})) continue;
                fallbackCount++;
                var cx=Math.max(0,Math.min(1920-240,Math.round(candidate.x-70)));
                var cy=Math.max(0,Math.min(1080-45,Math.round(candidate.y-50)));
                var local=scaledRows(img,cx,cy,240,45).map(function(r){return {text:r.text,x:cx+Number(r.x)/3,y:cy+Number(r.y)/3,width:Number(r.width)/3,height:Number(r.height)/3};});
                if(actOneEnemyBarAnchored(candidate,local)) bars.push(candidate);
            }
            return bars;
        } finally {dispose(mask);dispose(crop);}
    }
    function requireCombat() {
        checkStop();
        if(!request || ['Defeat the nearby hilichurls','Clear out the nearby hilichurl camp'].indexOf(request.objective)<0 || !lastObservation || Date.now()-lastObservation.timestamp > 1000 || !lastObservation.hud.world || lastObservation.hud.lowHealth || lastObservation.hud.objectives.indexOf(request.objective) < 0) throw new Error('Fresh recognized combat objective required');
    }
    return {
        now: function () { return Date.now(); }, sleep: function (ms) { return sleep(ms); }, checkStop: checkStop,
        beginMission: function (value) {
            request = value; events = [];
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
            // Verified two-character pilot roster: Traveler is the first portrait.
            events.push({type:'healTraveler',x:118,y:160,startedAt:Date.now()});click(118,160);
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
            if (!lastObservation || Date.now()-lastObservation.timestamp > 1000 || ['switchAmber','enterAim','exitAim','aimSlime','navigateQuest','trackQuest'].indexOf(lastObservation.hud.tutorialStep) < 0) throw new Error('Fresh recognized tutorial required');
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
        write: function (p, t) { if (!file.writeTextSync(p, t)) throw new Error('Cannot write ' + p); },
        observe: async function (session, frame) {
            ready();
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
                var pngMs = Date.now() - p0, map0 = Date.now(), pos = null;
                try {
                    var mp = genshin.getPositionFromMap('Teyvat', 0);
                    if (mp && Number.isFinite(Number(mp.x)) && Number.isFinite(Number(mp.y))) pos = { x: Number(mp.x), y: Number(mp.y), map: 'Teyvat', cameraAngle: Number(genshin.getCameraOrientation()) };
                } catch (_) { }
                var mapMs = Date.now() - map0, text = rows.map(function (r) { return r.text; }).join(' ');
                var hp = actOneHealth(healthRows);
                var auto = rows.some(function (r) { return /^Auto$/i.test(r.text.trim()) && r.x < 350 && r.y < 150; });
                var choice = rows.some(function (r) { return r.x > 1000 && r.y > 430 && r.y < 790 && r.text.trim().length > 6; });
                var journal = rows.some(function (r) { return /^In Progress$/i.test(r.text.trim()) && r.y < 100; });
                var bigMap = /Exploration Progress|Starfell Valley/.test(text) && !pos && !journal;
                var acquired = /Obtained New Character/.test(text) && /Click anywhere in the blank area to continue/.test(text) ? rows.filter(function(r) { return ['Amber','Kaeya','Lisa'].indexOf(r.text.trim()) >= 0 && r.x < 500 && r.y > 500 && r.y < 700; }) : [];
                var tutorialStep = /Press 2 to switch to Amber/i.test(text) && /Use Amber to defeat the airborne/i.test(text) ? 'switchAmber' : null;
                if (/Press R to enter\/exit aiming mode/i.test(text) && /Use Amber to defeat the airborne/i.test(text)) tutorialStep = 'enterAim';
                if (/Move cursor to aim. Try attacking the floating Anemo Slime/i.test(text) && /Use Amber to defeat the airborne/i.test(text)) tutorialStep = 'aimSlime';
                if (/Press R again to exit aiming mode/i.test(text) && /Go to the location designated by Amber/i.test(text)) tutorialStep = 'exitAim';
                var combatObjective = objectiveRows.some(function(r){return ['Defeat the nearby hilichurls','Clear out the nearby hilichurl camp'].indexOf(r.text.trim())>=0;});
                if(journal&&actOneNavigateQuestState(rows)) tutorialStep='navigateQuest';
                var trackQuest=actOneTrackQuestState(rows);
                if(trackQuest) tutorialStep='trackQuest';
                var climbing=rows.some(function(r){return r.text.trim()==='X' && r.x>1500 && r.y>990;}) && rows.some(function(r){return r.text.trim()==='Space' && r.x>1600 && r.y>990;});
                var hud = { climbing:climbing, enemyBars: combatObjective ? readEnemyBars(img, rows) : [], slimeTarget: tutorialStep === 'aimSlime' ? readSlime(img) : null, tutorialStep: tutorialStep, characterAcquired: acquired.length === 1 ? acquired[0].text.trim() : null, dialogueReady: actOneDialogueReady(rows, choice), choice: auto && choice, journal: journal, bigMap: bigMap,
                    objectiveChanged: /objective updated|quest completed/i.test(text), health: hp, healthOcr: healthRows.map(function (r) { return r.text; }),
                    healthPct: hp && hp.max > 0 ? hp.current / hp.max : null,
                    lowHealth: !hp || hp.max <= 0 || hp.current > hp.max || hp.current / hp.max < 0.6,
                    world: !trackQuest && !!pos && !!hp && !auto && !journal && !bigMap,
                    interact: rows.some(function (r) { return (/^F$/.test(r.text.trim()) && r.x > 850 && r.y > 300 && r.y < 800) || (/^Teleport[- ]Waypoint$/i.test(r.text.trim()) && r.x>1100 && r.y>400 && r.y<700); }),
                    objectives: objectiveRows.map(function (r) { return r.text; }) };
                if (pos && request && request.objective === 'Investigate what Paimon has found') hud.worldMarker = readMarker(img);
                ready();
                lastObservation = { frameId: frame, timestamp: Date.now(), capturedAt: t0, screenshotPath: png, ocr: rows, map: trackQuest ? null : pos, hud: hud,
                    timings: { captureMs: captureMs, ocrMs: ocrMs, fullOcrMs: fullOcrMs, healthOcrMs: healthOcrMs, objectiveOcrMs: objectiveOcrMs, objectiveSource: reusedObjectiveRows ? 'fullFrame' : 'crop', pngWriteMs: pngMs, mapMs: mapMs, totalMs: Date.now() - t0 } };
                return lastObservation;
            } finally { dispose(img); }
        }
    };
}
