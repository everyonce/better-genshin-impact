var ActOneMission = (function () {
    function normalize(degrees) { return (degrees % 360 + 360) % 360; }
    function bearing(from, to) { return normalize(Math.atan2(-(to.y - from.y), -(to.x - from.x)) * 180 / Math.PI); }
    function clean(s) { return String(s).toLowerCase().replace(/[^a-z0-9 ]/g, '').replace(/\s+/g, '').trim(); }
    function objectiveMatches(value, expected) {
        var a = clean(value), b = clean(expected);
        if (a === b) return true;
        if (b.length < 12 || Math.abs(a.length - b.length) > 1) return false;
        var i = 0, j = 0, errors = 0;
        while (i < a.length && j < b.length) {
            if (a[i] === b[j]) { i++; j++; continue; }
            if (++errors > 1) return false;
            if (a.length >= b.length) i++;
            if (b.length >= a.length) j++;
        }
        return errors + (a.length - i) + (b.length - j) <= 1;
    }
    function hasObjective(current, expected) {
        return !!(current && current.hud && Array.isArray(current.hud.objectives) &&
            current.hud.objectives.some(function (s) { return objectiveMatches(s, expected); }));
    }
    function validHealth(health) {
        return !!(health && Number.isFinite(health.current) && Number.isFinite(health.max) &&
            health.max > 0 && health.current >= 0 && health.current <= health.max);
    }
    function hasObjectiveText(current) {
        return !!(current && current.hud && Array.isArray(current.hud.objectives) &&
            current.hud.objectives.some(function (s) { return clean(s).length > 0; }));
    }
    function safeTransientFrame(current) {
        var h=current&&current.hud, hp=h&&h.health;
        return !!(current&&current.map&&h&&!h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&!h.objectiveChanged&&
            (!validHealth(hp)||(!h.lowHealth&&hp.current/hp.max>=0.6)));
    }
    function hasNewQuestToast(current) {
        var objectives = current && current.hud && current.hud.objectives;
        if (Array.isArray(objectives) && objectives.some(function (s) { return clean(s) === clean('New Quest'); })) return true;
        return !!((current && current.ocr || []).some(function (r) {
            return clean(r.text) === clean('New Quest') && Number(r.x) >= 0 && Number(r.x) <= 750 && Number(r.y) >= 0 && Number(r.y) <= 400;
        }));
    }
    function safeToastWorld(current) {
        var h = current && current.hud, hp = h && h.health;
        return !!(current && current.map && h && h.world && !h.objectiveChanged && !h.lowHealth &&
            validHealth(hp) && hp.current / hp.max >= 0.6);
    }
    function isDressingRoomUnlock(current) {
        var h=current&&current.hud,rows=current&&current.ocr||[];
        if(!h||current.map!==null||h.world===true||h.journal||h.bigMap||h.dialogueReady||h.choice) return false;
        var dressingTitle=rows.filter(function(r){return String(r.text||'').trim()==='Dressing Room'&&r.x>=740&&r.x<1200&&r.y>=480&&r.y<570;});
        var dressingFirst=rows.filter(function(r){return String(r.text||'').trim()==='Dressing Room unlocked. Collect unique wind'&&r.x>=620&&r.x<1300&&r.y>=555&&r.y<625;});
        var dressingSecond=rows.filter(function(r){return String(r.text||'').trim()==='gliders and outfits to alter the appearance of'&&r.x>=620&&r.x<1300&&r.y>=590&&r.y<655;});
        var dressingThird=rows.filter(function(r){return String(r.text||'').trim()==='your characters.'&&r.x>=780&&r.x<1150&&r.y>=625&&r.y<690;});
        var miliastraTitle=rows.filter(function(r){return String(r.text||'').trim()==='Miliastra Wonderland - Unlock'&&r.x>=620&&r.x<1300&&r.y>=480&&r.y<570;});
        var miliastraFirst=rows.filter(function(r){return String(r.text||'').trim()==='Enter the Miliastra Wonderland and dive into a'&&r.x>=620&&r.x<1300&&r.y>=555&&r.y<625;});
        var miliastraSecond=rows.filter(function(r){return String(r.text||'').trim()==='world of creativity and discovery!'&&r.x>=700&&r.x<1250&&r.y>=590&&r.y<655;});
        return dressingTitle.length===1&&dressingFirst.length===1&&dressingSecond.length===1&&dressingThird.length===1||
            miliastraTitle.length===1&&miliastraFirst.length===1&&miliastraSecond.length===1;
    }
    async function runNavigation(request, observation, api, observe) {
        var began = api.now(), initialHealth = observation.hud.health, totalInputMs = 0, turns = 0, movements = 0;
        var current = observation, afterForward = null, stalled = 0, turnAttempts = 0, jumpRecoveries = 0, climbReleases=0, climbSteps=0, climbEpisodeSteps=0, climbLimit=null, climbIsVerified=false, waypointIndex=0;
        function stop(reason) { return { status: 'stopped', reason: reason, nextWaypointIndex: waypointIndex, inputMs: totalInputMs, turns: turns, movements: movements, jumpRecoveries: jumpRecoveries, climbSteps:climbSteps, climbReleases:climbReleases }; }
        function hasTargetName(o,names) {
            var rows=o&&Array.isArray(o.ocr)?o.ocr:[];
            function inZone(r) { return r.x>=1150&&r.x<=1550&&r.y>=300&&r.y<=800; }
            if(rows.some(function(r){return names.indexOf(String(r.text||'').trim())>=0&&inZone(r);})) return true;
            if(names.indexOf('Temple of the Falcon')>=0||names.indexOf('Temple of the Wolf')>=0||names.indexOf('Temple of the Lion')>=0) {
                var heads=rows.filter(function(r){return String(r.text||'').trim()==='Temple of the'&&inZone(r);});
                var tails=rows.filter(function(r){return ['Falcon','Wolf','Lion'].indexOf(String(r.text||'').trim())>=0&&inZone(r);});
                var pairs=[];
                heads.forEach(function(a){tails.forEach(function(b){var gap=b.y-(a.y+a.height);if(Math.abs(a.x-b.x)<=30&&gap>=-15&&gap<=20)pairs.push([a,b]);});});
                return pairs.length===1;
            }
            return false;
        }
        function hasTargetF(o) {
            return !!(o&&o.hud&&o.hud.interact&&Array.isArray(o.ocr)&&o.ocr.some(function(r){return String(r.text||'').trim()==='F'&&r.x>=1080&&r.x<=1170&&r.y>=490&&r.y<=590;}));
        }
        function plausibleMap(o,target) {
            var p=o&&o.map;
            return !!(p&&p.map===target.map&&Number.isFinite(p.x)&&Number.isFinite(p.y)&&
                Math.hypot(target.x-p.x,target.y-p.y)<=150&&
                (!afterForward||Math.hypot(p.x-afterForward.x,p.y-afterForward.y)<=25));
        }
        if(['Defeat the nearby hilichurls','Clear out the nearby hilichurl camp'].indexOf(request.objective)>=0) {
            for(var resumePoll=0;resumePoll<6 && !current.hud.world && !current.hud.dialogueReady && !current.hud.choice;resumePoll++){api.checkStop();await api.sleep(350);current=await observe();}
        }
        for (var w = 0; w < request.waypoints.length; w++) {
            waypointIndex = w;
            var target = request.waypoints[w];
            while (true) {
                api.checkStop();
                if (api.now() - began >= request.deadlineMs) return stop('Navigation deadline reached');
                if (climbSteps >= 12 && current && current.hud && !current.hud.climbing) return stop('Navigation-wide climb hold limit reached');
                if (!safeTransientFrame(current)) return stop('Dialogue, objective, low-health, or missing navigation evidence');
                for (var transientRetry=0; transientRetry<2 && (!validHealth(current.hud.health) ||
                    (!hasObjective(current, request.objective) && !hasNewQuestToast(current))); transientRetry++) {
                    if (api.now()-began>=request.deadlineMs) return stop('Navigation deadline reached during evidence retry');
                    await api.sleep(180); api.checkStop(); current=await observe();
                    if (!safeTransientFrame(current))
                        return stop('Dialogue, objective, low-health, or missing navigation evidence');
                }
                if (!validHealth(current.hud.health)) return stop('Fresh health evidence unavailable');
                if (api.now()-began>=request.deadlineMs) return stop('Navigation deadline reached during evidence retry');
                if (!current.hud.world) return stop('Dialogue, objective, low-health, or missing navigation evidence');
                if (!hasObjective(current, request.objective)) {
                    if (!hasNewQuestToast(current)) return stop('Expected objective not visible');
                    var toastDeadline = Math.min(api.now() + 8000, began + request.deadlineMs);
                    while (!hasObjective(current, request.objective)) {
                        api.checkStop();
                        if (!safeToastWorld(current)) return stop('Unsafe state while waiting for New Quest toast');
                        if (!hasNewQuestToast(current) && hasObjectiveText(current)) return stop('New Quest toast cleared with unrelated objective');
                        var toastWait = toastDeadline - api.now();
                        if (toastWait <= 0) return stop('New Quest toast did not clear');
                        await api.sleep(Math.min(350, toastWait));
                        current = await observe();
                        if (!safeToastWorld(current)) return stop('Unsafe state while waiting for New Quest toast');
                    }
                    if (api.now() - began >= request.deadlineMs) return stop('Navigation deadline reached');
                }
                if (!current.map || !current.hud.world || current.hud.objectiveChanged || current.hud.lowHealth ||
                    !validHealth(current.hud.health) || current.hud.health.current/current.hud.health.max<0.6)
                    return stop('Dialogue, objective, low-health, or missing navigation evidence');
                if (!hasObjective(current, request.objective)) return stop('Expected objective not visible');
                if (!validHealth(current.hud.health)) return stop('Fresh health evidence unavailable');
                if (!validHealth(initialHealth)) initialHealth = current.hud.health;
                if (initialHealth.current - current.hud.health.current > initialHealth.max * 0.1) return stop('Health dropped more than 10% of maximum during mission');
                for(var coordinateRetry=0;coordinateRetry<2&&!plausibleMap(current,target);coordinateRetry++) {
                    if(request.deadlineMs-(api.now()-began)<180) return stop('Navigation deadline reached during map coordinate retry');
                    await api.sleep(180);api.checkStop();var coordinateFrame=await observe();
                    if(!safeTransientFrame(coordinateFrame)||!coordinateFrame.hud.world||!validHealth(coordinateFrame.hud.health)||
                       coordinateFrame.hud.health.current/coordinateFrame.hud.health.max<0.6)
                        return stop('Unsafe HUD during map coordinate retry');
                    if(!hasObjective(coordinateFrame,request.objective)) return stop('Objective changed during map coordinate retry');
                    if(initialHealth.current-coordinateFrame.hud.health.current>initialHealth.max*0.1)
                        return stop('Health dropped more than 10% during map coordinate retry');
                    current=coordinateFrame;
                }
                if(!plausibleMap(current,target)) {
                    if(current&&current.map&&current.map.map!==target.map) return stop('Waypoint map does not match current map');
                    if(afterForward&&current&&current.map&&Math.hypot(current.map.x-afterForward.x,current.map.y-afterForward.y)>25) return stop('Map position jumped');
                    return stop('Waypoint farther than the allowed local segment');
                }
                if(current.hud.interact&&request.objective==='Enter the Knights of Favonius Headquarters') return stop('Interaction available');
                if(hasTargetF(current)&&request.objective==='Talk to Amber'&&hasTargetName(current,['Amber'])) return stop('Interaction available');
                if(hasTargetF(current)&&request.objective==='Enter the temple'&&hasTargetName(current,['Temple of the Falcon','Temple of the Wolf','Temple of the Lion'])) return stop('Interaction available');
                if(current.hud.climbing) {
                    if(['Go to the Knights of Favonius Headquarters','Enter the Knights of Favonius Headquarters'].indexOf(request.objective)>=0) return stop('Unexpected climbing on headquarters approach');
                    var cityWallRetreat=request.objective==='Go to the location designated by Amber' &&
                        Math.hypot(current.map.x+849.9,current.map.y-2285)<4 && target.x<=-860;
                    if(cityWallRetreat) {
                        if(climbReleases>=1 || !api.releaseClimb) return stop('City wall retreat did not clear climbing');
                        if(request.deadlineMs-(api.now()-began)<1000) return stop('Navigation deadline reached before wall retreat');
                        var retreatStart=api.now();await api.releaseClimb();totalInputMs+=api.now()-retreatStart;
                        climbReleases++;afterForward=null;stalled=0;current=await observe();continue;
                    }
                    var verifiedCliff=(request.objective==='Defeat the nearby hilichurls' && Math.hypot(current.map.x+1128.5,current.map.y-2217)<5) ||
                        (request.objective==='Clear out the nearby hilichurl camp' &&
                            (Math.hypot(current.map.x+1154.8,current.map.y-2429.3)<5 || Math.hypot(current.map.x+1117.1,current.map.y-2203.8)<5));
                    if(climbLimit===null) {
                        climbIsVerified=verifiedCliff;
                        climbLimit=climbIsVerified?(request.objective==='Clear out the nearby hilichurl camp'?6:12):6;
                    }
                    if(climbIsVerified && climbEpisodeSteps>=climbLimit) return stop('Bounded cliff climb did not reach the top');
                    if(!climbIsVerified && climbSteps>=12) return stop('Navigation-wide climb hold limit reached');
                    if(climbEpisodeSteps>=climbLimit) return stop(climbIsVerified?'Bounded cliff climb did not reach the top':'Bounded ledge climb did not reach the top');
                    if(request.deadlineMs-(api.now()-began)<1000) return stop('Navigation deadline reached before ledge recovery');
                    var climbStart=api.now();await api.forward(800);totalInputMs+=api.now()-climbStart;climbSteps++;climbEpisodeSteps++;await api.sleep(200);current=await observe();afterForward=null;stalled=0;continue;
                }
                // A fresh non-climbing observation ends the current ledge episode;
                // the request-wide counter remains so repeated ledges stay bounded.
                climbLimit=null;climbEpisodeSteps=0;climbIsVerified=false;
                if (request.objective === 'Defeat the nearby hilichurls' && Math.hypot(current.map.x+1148,current.map.y-2193)<40 && current.hud.enemyBars && current.hud.enemyBars.length) return stop('Enemy acquired');
                if (request.objective === 'Clear out the nearby hilichurl camp' && current.hud.enemyBars && current.hud.enemyBars.length) return stop('Enemy acquired');
                if (current.map.map !== target.map) return stop('Waypoint map does not match current map');
                var distance = Math.hypot(target.x - current.map.x, target.y - current.map.y);
                var investigating = clean(request.objective) === clean('Investigate what Paimon has found');
                if (investigating && current.hud.interact) return stop('Interaction available');
                var arrivalRadius=request.objective==='Clear out the nearby hilichurl camp'?3:
                    ['Go to the Knights of Favonius Headquarters','Enter the Knights of Favonius Headquarters','Talk to Amber','Enter the temple'].indexOf(request.objective)>=0?2:5;
                if (!investigating && distance <= arrivalRadius) break;
                if (distance > 150) return stop('Waypoint farther than the allowed local segment');
                if (afterForward) {
                    var moved = Math.hypot(current.map.x - afterForward.x, current.map.y - afterForward.y);
                    if (moved > 25) return stop('Map position jumped');
                    stalled = moved < 0.5 ? stalled + 1 : 0; afterForward = null;
                    if (stalled >= 3) {
                        var crystalStep = clean(request.objective) === clean('Investigate what Paimon has found') && distance < 12 &&
                            current.hud.objectives.some(function (s) { return /Higher\s+[1-9]m/i.test(s); });
                        var verifiedRoadLedge=request.objective==='Defeat the nearby hilichurls' && distance<30 && Math.hypot(current.map.x+1161,current.map.y-2400)<4;
                        var amberStoneBase=request.objective==='Talk to Amber'&&distance<12&&current.hud.climbing!==true&&current.hud.groundControls===true&&
                            Math.hypot(current.map.x+1159.818,current.map.y-2137.488)<=2;
                        if ((!crystalStep && !verifiedRoadLedge&&!amberStoneBase) || jumpRecoveries >= 1) return stop('Map coordinates stalled');
                        if (request.deadlineMs - (api.now() - began) < 1000) return stop('Navigation deadline reached before recovery');
                        var jumpStart = api.now(); await api.keyPress('VK_SPACE'); await api.sleep(100); await api.forward(500);
                        totalInputMs += api.now() - jumpStart; jumpRecoveries++; movements++; stalled = 0;
                        await api.sleep(150); current = await observe(); continue;
                    }
                }
                var angle = current.map.cameraAngle;
                if (!Number.isFinite(angle)) return stop('Fresh camera orientation unavailable');
                var markerApproach = investigating && distance < 15;
                if (markerApproach && !current.hud.worldMarker) return stop('Unique crystal marker unavailable');
                var markerError = markerApproach ? current.hud.worldMarker.x - 960 : 0;
                var diff = markerApproach ? -markerError * 0.08 : (angle - bearing(current.map, target) + 540) % 360 - 180;
                var magnitude = Math.abs(diff), ratio = 8;
                if (magnitude > 8) {
                    if (++turnAttempts > 16) return stop('Camera did not converge');
                    var rotateStart = api.now(); await api.rotate(Math.max(-750, Math.min(750, Math.round(-ratio * diff))));
                    totalInputMs += api.now() - rotateStart; turns++;
                    await api.sleep(180); current = await observe(); continue;
                }
                turnAttempts = 0;
                var held = Math.floor(Math.min(markerApproach || distance < 10 ? 250 : 800, request.deadlineMs - (api.now() - began)));
                if (held <= 0) return stop('Navigation deadline reached');
                afterForward = { x: current.map.x, y: current.map.y };
                var inputStarted = api.now(); await api.forward(held); totalInputMs += api.now() - inputStarted; movements++;
                await api.sleep(150); current = await observe();
            }
        }
        return { status: 'arrived', nextWaypointIndex: request.waypoints.length, inputMs: totalInputMs, turns: turns, movements: movements, jumpRecoveries: jumpRecoveries, climbSteps:climbSteps, climbReleases:climbReleases };
    }
    function selectDialogueChoice(current) {
        if (!current.hud.choice) return null;
        var rows = current.ocr || [], speakers = ['Amber', 'Paimon', 'Jean', 'Lisa', 'Kaeya', 'Venti'];
        var known = rows.some(function (r) { return speakers.indexOf(r.text.trim()) >= 0 && r.x > 600 && r.x < 1200 && r.y >= 830 && r.y < 900; });
        var options = rows.filter(function (r) { return r.x > 1000 && r.x < 1800 && r.y > 430 && r.y < 830 && r.text.trim().length > 6; }).sort(function (a,b) { return a.y-b.y || a.x-b.x; });
        var allowed = ["Good thing the dragon didn't notice", "Is talking to dragons normal?"];
        if (options.length < 1 || options.length > 8) return null;
        if (options.some(function (r) { return /purchase|buy|spend|primogem|genesis crystal|intertwined fate|acquaint fate|delete|discard|consume|exchange|resin|pay\b/i.test(r.text); })) return null;
        var preferred = options.filter(function (r) { return allowed.indexOf(r.text.trim()) >= 0; });
        if (preferred.length === 1) return preferred[0].text.trim();
        if (!known) return null;
        return options[0].text.trim();
    }
    async function runDialogue(api, observe) {
        var began = api.now(), presses = 0, inputMs = 0, current = await observe(), unknown = 0, tutorialSteps = Object.create(null);
        while (api.now() - began < 60000 && presses < 40) {
            api.checkStop();
            if (isDressingRoomUnlock(current)) {
                // This exact unlock overlay is a noninteractive transition. It
                // consumes neither an action nor the generic unknown-frame budget.
                unknown=0;
                await api.sleep(1000);current=await observe();continue;
            }
            if (current.hud.tutorialStep) {
                if ((tutorialSteps[current.hud.tutorialStep] || 0) >= (current.hud.tutorialStep === 'aimSlime' ? 12 : 1)) return {status:'stopped',reason:'tutorial_did_not_advance',presses:presses,inputMs:inputMs};
                tutorialSteps[current.hud.tutorialStep] = (tutorialSteps[current.hud.tutorialStep] || 0) + 1;
                var tutorialStart = api.now(); var tutorialAction = await api.advanceTutorial(); inputMs += api.now()-tutorialStart; presses++;
                await api.sleep(tutorialAction === 'glideOpen' ? 250 : current.hud.tutorialStep === 'aimSlime' && tutorialAction !== 'shot' ? 250 : 1000);
                current = await observe();
                if (tutorialAction === 'glideOpen') {
                    var glideHealth=current&&current.hud&&current.hud.health;
                    var handoffReady=!!(current&&current.map&&current.map.map==='Teyvat'&&current.hud&&current.hud.world&&
                        !current.hud.dialogueReady&&!current.hud.choice&&!current.hud.journal&&!current.hud.bigMap&&
                        !current.hud.objectiveChanged&&!current.hud.lowHealth&&!current.hud.climbing&&!current.hud.tutorialStep&&
                        validHealth(glideHealth)&&glideHealth.current/glideHealth.max>=0.6&&
                        hasObjective(current,'Meet Amber at the fountain plaza'));
                    if (!handoffReady) return {status:'stopped',reason:'glide_open_handoff_evidence_not_safe',presses:presses,inputMs:inputMs,
                        tutorial:{action:tutorialAction,frameId:current&&current.frameId||null},navigation:null,handoff:false};
                    var navigation=await runNavigation({objective:'Meet Amber at the fountain plaza',deadlineMs:30000,
                        waypoints:[{map:'Teyvat',x:-879,y:2263}]},current,api,observe);
                    var navigationPresses=(navigation.turns||0)+(navigation.movements||0)+(navigation.jumpRecoveries||0)+
                        (navigation.climbSteps||0)+(navigation.climbReleases||0);
                    inputMs+=navigation.inputMs||0;
                    return {status:navigation.status==='arrived'?'completed':'stopped',
                        reason:navigation.status==='arrived'?'glide_open_navigation_arrived':navigation.reason,
                        presses:presses+navigationPresses,tutorialPresses:presses,inputMs:inputMs,tutorial:{action:tutorialAction,frameId:current.frameId},
                        navigation:navigation,handoff:true};
                }
                continue;
            }
            if (current.hud.characterAcquired) {
                var acquiredStart = api.now(); await api.continueCharacter(); inputMs += api.now()-acquiredStart; presses++;
                await api.sleep(900); current = await observe(); continue;
            }
            if (current.hud.world) return { status: 'completed', reason: 'world_returned', presses: presses, inputMs: inputMs };
            if (current.hud.choice) {
                var choice = selectDialogueChoice(current);
                if (!choice) return { status: 'stopped', reason: 'dialogue_choice', presses: presses, inputMs: inputMs };
                var choiceStart = api.now(); await api.chooseChoice(choice); inputMs += api.now() - choiceStart; presses++;
                await api.sleep(650); current = await observe(); continue;
            }
            if (!current.hud.dialogueReady) {
                if (++unknown >= 6) return { status: 'stopped', reason: 'unrecognized_dialogue_state', presses: presses, inputMs: inputMs };
                await api.sleep(1000); current = await observe(); continue;
            }
            unknown = 0;
            var t0 = api.now(); await api.keyPress('VK_SPACE'); inputMs += api.now() - t0; presses++;
            await api.sleep(650); current = await observe();
        }
        return { status: 'stopped', reason: 'dialogue_limit_reached', presses: presses, inputMs: inputMs };
    }
    async function runQuestStep(name, observation, api, observe) {
        if(name==='falconLookRight'||name==='falconLookLeft') {api.falconRotate(name==='falconLookRight'?250:-250);await api.sleep(180);var next=await observe();return {status:'completed',reason:'Bounded Falcon camera turn',step:name,frameId:next.frameId};}
        if(name==='falconOpenDoor') {api.checkStop();var t=api.now();await api.falconOpenDoor();var ms=api.now()-t;await api.sleep(900);var next=await observe();return {status:'completed',reason:'Opened Falcon door; inspect scene',step:name,inputMs:ms,frameId:next.frameId};}
        if(name==='falconConsoleApproach'||name==='falconForward'||name==='falconLeft'||name==='falconRight') {
            var sequence=name==='falconConsoleApproach'?[['VK_W',800],['VK_W',800],['VK_A',600]]:
                [[name==='falconLeft'?'VK_A':name==='falconRight'?'VK_D':'VK_W',800]];
            var hp0=observation.hud.health,inputMs=0,current=observation;
            for(var i=0;i<sequence.length;i++) {
                api.checkStop();
                if(current.hud.interact) return {status:'stopped',reason:'Domain interaction available',step:name,frameId:current.frameId,inputMs:inputMs};
                if(!hp0||!current.hud.health||hp0.current-current.hud.health.current>hp0.max*0.1) return {status:'stopped',reason:'Domain health evidence changed',step:name,inputMs:inputMs};
                var t0=api.now();await api.falconMove(sequence[i][0],sequence[i][1]);inputMs+=api.now()-t0;
                await api.sleep(180);current=await observe();
            }
            return {status:'completed',reason:'Bounded Falcon movement finished; inspect scene',step:name,frameId:current.frameId,inputMs:inputMs};
        }
        if(name==='falconPartyStart') { api.checkStop();var click0=api.now();api.startFalconParty();var clickMs=api.now()-click0;await api.sleep(800);var next=await observe();return {status:'completed',reason:'Falcon party Start clicked; inspect loading or domain',step:name,clicks:1,inputMs:clickMs,frameId:next.frameId}; }
        if(name==='falconStart') return runFalconStart(observation,api,observe);
        if(name==='falconWaypoint') return runFalconWaypoint(observation,api,observe);
        if(name==='headquartersWall') return runHeadquartersWall(observation,api,observe);
        if(name==='headquartersStairWall') return runHeadquartersWall(observation,api,observe,{x:-821.37,y:2273.58,minAngle:175,maxAngle:225,step:name});
        if(name==='headquartersStairRail') return runHeadquartersWall(observation,api,observe,{x:-815.45,y:2277.52,minAngle:225,maxAngle:280,step:name});
        return {status:'stopped',reason:'Unsupported quest step: '+name,step:name,frameId:observation&&observation.frameId||null,inputMs:0};
    }
    async function runFalconStart(initial,api,observe) {
        var clickStarted=api.now(),label,inputMs=0;
        try { api.checkStop(); label=api.startFalconDomain(); inputMs=Math.max(0,api.now()-clickStarted); }
        catch(e) { return {status:'stopped',reason:String(e&&e.message||e),step:'falconStart',frameId:initial&&initial.frameId||null,inputMs:Math.max(0,api.now()-clickStarted),clicks:0}; }
        await api.sleep(800); api.checkStop();
        var current=await observe();
        return {status:'completed',reason:'Falcon Domain Start clicked; fresh screen observed',step:'falconStart',label:label,
            frameId:current&&current.frameId||null,inputMs:inputMs,clicks:1};
    }
    async function runFalconWaypoint(initial,api,observe) {
        var objective='Meet Amber at the temple',target={x:-1122.173,y:2197.455},inputMs=0,polls=0,teleported=false,nativeTeleportMs=0;
        function exactObjective(o) { return !!(o&&o.hud&&Array.isArray(o.hud.objectives)&&o.hud.objectives.some(function(s){return clean(s)===clean(objective);})); }
        function result(status,reason,current) { return {status:status,reason:reason,step:'falconWaypoint',frameId:current&&current.frameId||null,
            polls:polls,teleported:teleported,inputMs:inputMs,nativeTeleportMs:nativeTeleportMs}; }
        function healthState(h) {
            var hp=h&&h.health;
            if(!validHealth(hp)) return 'unknown';
            return hp.current/hp.max>=0.6&&!h.lowHealth?'safe':'low';
        }
        function terminalUnsafe(o) {
            var h=o&&o.hud;
            if(!h) return 'HUD unavailable';
            if(h.journal||h.bigMap||h.dialogueReady||h.choice||h.climbing||h.tutorialStep||h.objectiveChanged) return 'Unexpected UI or state during Falcon waypoint';
            if(healthState(h)==='low') return 'Health below 60% during Falcon waypoint';
            return null;
        }
        function safeToastFrame(o) {
            var h=o&&o.hud;
            return !!(h&&h.world===true&&!h.journal&&!h.bigMap&&!h.dialogueReady&&!h.choice&&!h.climbing&&!h.tutorialStep&&
                !h.objectiveChanged&&healthState(h)==='safe');
        }
        function arrived(o) {
            var h=o&&o.hud,p=o&&o.map;
            return !!(h&&h.world===true&&!terminalUnsafe(o)&&healthState(h)==='safe'&&exactObjective(o)&&
                p&&p.map==='Teyvat'&&Number.isFinite(p.x)&&Number.isFinite(p.y)&&Math.hypot(p.x-target.x,p.y-target.y)<=25);
        }
        if(!initial||!initial.hud||initial.hud.world!==true||!exactObjective(initial)||terminalUnsafe(initial)||healthState(initial.hud)!=='safe')
            return result('stopped','Falcon waypoint requires the exact objective and safe world HUD',initial);
        api.checkStop();
        var teleportStarted=api.now();
        try { await api.teleportFalconWaypoint(); teleported=true; }
        catch(e) { nativeTeleportMs=Math.max(0,api.now()-teleportStarted); return result('stopped',String(e&&e.message||e),initial); }
        nativeTeleportMs=Math.max(0,api.now()-teleportStarted);
        // The pre-teleport frame can never verify arrival, even if its native
        // map coordinates happen to match the destination.
        var deadline=api.now()+15000;
        api.checkStop();
        var current=await observe();polls++;
        var toastDeadline=null;
        while(true) {
            api.checkStop();
            var unsafe=terminalUnsafe(current);
            if(unsafe) return result('stopped',unsafe,current);
            if(!exactObjective(current)) {
                var toast=hasNewQuestToast(current),remaining=deadline-api.now(),waitMs;
                if(toast) {
                    if(!safeToastFrame(current)) return result('stopped','Unsafe state while waiting for Falcon New Quest toast',current);
                    if(toastDeadline===null) toastDeadline=Math.min(api.now()+8000,deadline);
                    remaining=toastDeadline-api.now();
                    if(remaining<=0) return result('stopped','Falcon New Quest toast did not clear',current);
                    waitMs=Math.min(350,remaining);
                } else if(hasObjectiveText(current)) {
                    return result('stopped',toastDeadline===null?'Objective changed during Falcon waypoint':'Falcon New Quest toast cleared with unrelated objective',current);
                } else {
                    if(remaining<=0) break;
                    waitMs=Math.min(350,remaining);
                }
                await api.sleep(waitMs);api.checkStop();current=await observe();polls++;
                if(toastDeadline!==null&&!exactObjective(current)&&!hasNewQuestToast(current)&&hasObjectiveText(current))
                    return result('stopped','Falcon New Quest toast cleared with unrelated objective',current);
                continue;
            }
            if(arrived(current)) return result('completed','Falcon waypoint arrival verified',current);
            var remaining=deadline-api.now();
            if(remaining<=0) break;
            await api.sleep(Math.min(500,remaining)); api.checkStop();
            current=await observe();polls++;
        }
        return result('stopped','Falcon waypoint loading or arrival verification timed out',current);
    }
    async function runHeadquartersWall(initial,api,observe,policy) {
        policy=policy||{x:-795.5,y:2282.95,minAngle:110,maxAngle:190,step:'headquartersWall'};
        var objective='Go to the Knights of Favonius Headquarters',anchor=policy;
        var began=api.now(),deadline=began+20000,holds=0,inputMs=0,grounded=0;
        var initialHealth=initial&&initial.hud&&initial.hud.health;
        function result(status,reason,frame) {
            return {status:status,reason:reason,step:policy.step,holds:holds,inputMs:inputMs,
                frameId:frame&&frame.frameId||null};
        }
        function safe(current,first) {
            var h=current&&current.hud,hp=h&&h.health,p=current&&current.map;
            return !!(current&&p&&p.map==='Teyvat'&&Number.isFinite(p.x)&&Number.isFinite(p.y)&&
                Math.hypot(p.x-anchor.x,p.y-anchor.y)<=(first?5:10)&&h&&h.world===true&&
                !h.dialogueReady&&!h.choice&&!h.journal&&!h.bigMap&&!h.tutorialStep&&!h.objectiveChanged&&!h.lowHealth&&
                validHealth(hp)&&hp.current/hp.max>=0.6&&Array.isArray(h.objectives)&&h.objectives.indexOf(objective)>=0);
        }
        if(!initial||!initial.hud||!initial.hud.climbing||!safe(initial,true)||
            !Number.isFinite(initial.map.cameraAngle)||initial.map.cameraAngle<policy.minAngle||initial.map.cameraAngle>policy.maxAngle)
            return result('stopped','headquarters wall recovery requires exact location, objective, heading, climbing, and safe HUD',initial);
        if(!validHealth(initialHealth)) return result('stopped','headquarters wall recovery health unavailable',initial);
        var healthBaseline={current:initialHealth.current,max:initialHealth.max},current=initial;
        while(true) {
            api.checkStop();
            if(api.now()>=deadline) return result('stopped','headquarters wall recovery deadline reached',current);
            if(!safe(current,false)) return result('stopped','unsafe or changed evidence during headquarters wall recovery',current);
            var hp=current.hud.health;
            if(healthBaseline.current-hp.current>healthBaseline.max*0.1)
                return result('stopped','health dropped more than 10% during headquarters wall recovery',current);
            if(current.hud.climbing) {
                if(holds>=12) return result('stopped','headquarters wall climb reached twelve holds',current);
                if(deadline-api.now()<1000) return result('stopped','headquarters wall deadline reached before hold',current);
                api.checkStop();var started=api.now();await api.forward(800);inputMs+=Math.max(0,api.now()-started);holds++;
                await api.sleep(200);current=await observe();grounded=0;continue;
            }
            if(current.hud.groundControls!==true)
                return result('stopped','ground controls unavailable after headquarters wall climb',current);
            grounded++;
            if(grounded>=3) return result('completed','headquarters wall cleared; three grounded observations confirmed',current);
            if(deadline-api.now()<200) return result('stopped','headquarters wall deadline reached during ground confirmation',current);
            await api.sleep(200);current=await observe();
            if(current&&current.hud&&current.hud.climbing) grounded=0;
        }
    }
    return { runNavigation: runNavigation, runDialogue: runDialogue, runQuestStep:runQuestStep, bearing: bearing, objectiveMatches: objectiveMatches, selectDialogueChoice: selectDialogueChoice };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = ActOneMission;
