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
        async function stop(reason) {
            var result={ status: 'stopped', reason: reason, nextWaypointIndex: waypointIndex, inputMs: totalInputMs, turns: turns, movements: movements, jumpRecoveries: jumpRecoveries, climbSteps:climbSteps, climbReleases:climbReleases };
            if(/health|stalled|deadline/i.test(reason)&&typeof api.pauseWorldInventory==='function') {
                current=await observe();
                if(await api.pauseWorldInventory()) {for(var pausePoll=0;pausePoll<4;pausePoll++){await api.sleep(500);current=await observe();result.pausedInventory=(current.ocr||[]).some(function(r){return /^(Food|Weapons|Artifacts|Character Development Items|Materials|Gadgets|Quest|Precious Items|Furnishings)$/.test(String(r.text||'').trim())&&r.x>100&&r.x<500&&r.y<80;});if(result.pausedInventory)break;}}
            }
            return result;
        }
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
                if(hasTargetF(current)&&['Talk to Amber','Talk to Kaeya','Talk to Lisa'].indexOf(request.objective)>=0&&hasTargetName(current,[request.objective.slice(8)])) return stop('Interaction available');
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
                    ['Go to the Knights of Favonius Headquarters','Enter the Knights of Favonius Headquarters','Talk to Amber','Talk to Kaeya','Talk to Lisa','Enter the temple'].indexOf(request.objective)>=0?2:5;
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
            if(current.map===null&&current.hud.groundControls&&current.hud.health&&!current.hud.dialogueReady&&!current.hud.choice&&
                (current.ocr||[]).some(function(r){return /^Leaving in \d+ second\(s\)$/.test(r.text.trim())&&r.x>650&&r.x<1000&&r.y>920&&r.y<990;}))
                return {status:'completed',reason:'completed_domain_returned',presses:presses,inputMs:inputMs};
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
        if(name==='enterGame') {
            var target=actOneEnterGameTarget(observation,api.now());
            if(!target) return {status:'stopped',step:name,reason:'Fresh exact English title screen required',clicks:0,frameId:observation&&observation.frameId||null};
            var inputStarted=api.now(),clickProof;
            try {
                api.checkStop();api.requireInputReady();
                clickProof=api.startGame();
            } catch(e) {
                return {status:'stopped',step:name,reason:String(e&&e.message||e),clicks:0,frameId:observation.frameId};
            }
            var polls=0,current=observation,deadline=api.now()+10000;
            while(api.now()<deadline&&polls<20) {
                api.checkStop();await api.sleep(Math.min(500,deadline-api.now()));current=await observe();polls++;
                if(actOneEnterGameAuthPrompt(current&&current.ocr))
                    return {status:'stopped',step:name,reason:'Authentication or verification prompt appeared; inspect manually',clicks:1,
                        inputMs:Math.max(0,api.now()-inputStarted),polls:polls,frameId:current.frameId||null,postState:'authPrompt'};
                if(current&&current.hud&&current.hud.world===true)
                    return {status:'completed',step:name,reason:'Game world HUD observed after title entry',clicks:1,inputMs:Math.max(0,api.now()-inputStarted),
                        polls:polls,frameId:current.frameId||null,postState:'worldHud',target:clickProof};
                if(actOneEnterGameLoading(current&&current.ocr))
                    return {status:'completed',step:name,reason:'Loading screen observed after title entry',clicks:1,inputMs:Math.max(0,api.now()-inputStarted),
                        polls:polls,frameId:current.frameId||null,postState:'loading',target:clickProof};
                if(!actOneEnterGameTarget(current,api.now()))
                    return {status:'completed',step:name,reason:'Title screen changed after one entry click; inspect fresh scene',clicks:1,
                        inputMs:Math.max(0,api.now()-inputStarted),polls:polls,frameId:current&&current.frameId||null,postState:'titleCleared',target:clickProof};
            }
            return {status:'stopped',step:name,reason:'Title screen remained after bounded single click; no retry sent',clicks:1,
                inputMs:Math.max(0,api.now()-inputStarted),polls:polls,frameId:current&&current.frameId||null,postState:'titleUnchanged',target:clickProof};
        }
        if(name==='falconEngage') {
            api.falconContinue();await api.sleep(500);var next=await observe(),hp0=next.hud.health;
            for(var i=0;i<3;i++){if(!hp0||!next.hud.health||hp0.current-next.hud.health.current>hp0.max*0.1||(next.hud.enemyBars||[]).length)break;await api.falconMove('VK_W',800);await api.sleep(200);next=await observe();}
            var paused=false;
            for(var p=0;p<3;p++){await api.falconPause();await api.sleep(600);next=await observe();paused=next.ocr.some(function(r){return r.text.trim()==='Continue Challenge';});if(paused||!next.hud.health)break;}
            return {status:paused?'completed':'stopped',reason:paused?'Bounded approach to enemy room; pause verified':'Domain pause not confirmed',step:name,paused:paused,frameId:next.frameId};
        }
        if(name==='falconRanged') {
            var current=observation,hp0=current.hud.health,shots=0,reason='Ranged shot limit',started=api.now();
            try {
                // The first shot is authorized at the operator-verified crosshair.
                while(shots<5&&api.now()-started<20000){
                    api.checkStop();var hp=current.hud.health;
                    if(!hp0||!hp||hp.current/hp.max<0.6||hp0.current-hp.current>hp0.max*0.2){reason='Ranged health guard';break;}
                    if(shots>0){
                        var bars=current.hud.enemyBars||[];if(!bars.length){reason='No fresh ranged target';break;}
                        for(var a=0;a<2;a++) {bars=current.hud.enemyBars||[];if(!bars.length)break;bars.sort(function(x,y){return Math.abs(x.x-960)-Math.abs(y.x-960);});await api.falconRangedAction('aim',bars[0]);await api.sleep(150);current=await observe();}
                        if(!(current.hud.enemyBars||[]).some(function(b){return Math.abs(b.x-960)<55&&Math.abs(b.y+45-540)<60;})){reason='Ranged aim did not settle';break;}
                    }
                    await api.sleep(1800);current=await observe();
                    if(api.now()-started>=20000){reason='Ranged time limit';break;}
                    hp=current.hud.health;if(!hp||hp.current/hp.max<0.6||hp0.current-hp.current>hp0.max*0.2){reason='Ranged health guard';break;}
                    await api.falconRangedAction('fire');shots++;await api.sleep(1000);current=await observe();
                }
            }catch(e){reason=String(e&&e.message||e);}
            api.checkStop();current=await observe();
            try {await api.falconRangedAction('exit');await api.sleep(350);current=await observe();}catch(e){}
            for(var p=0;p<3&&current.hud.health;p++){await api.falconPause();await api.sleep(600);current=await observe();if(current.ocr.some(function(r){return r.text.trim()==='Continue Challenge';}))break;}
            return {status:'stopped',reason:reason,step:name,shots:shots,paused:current.ocr.some(function(r){return r.text.trim()==='Continue Challenge';}),elapsedMs:api.now()-started,frameId:current.frameId};
        }
        if(/^falconAim(Left|Right|Up|Down)(Fine)?$/.test(name)){api.falconAdjustAim(name);await api.sleep(180);var next=await observe();return {status:'completed',reason:'Bounded aimed camera correction',step:name,frameId:next.frameId};}
        if(name==='falconSelectAmber'||name==='falconSelectTraveler') {await api.falconSelectAmber();await api.sleep(500);var next=await observe();return {status:'completed',reason:'Selected domain character; inspect HP',step:name,frameId:next.frameId};}
        if(/^falcon(FoodTab|CancelFood|SelectEgg|SelectMadame|CloseInventory|UseEgg|ReviveTraveler|UseMadame|FeedTraveler|FeedAmber|SelectAmberFood)$/.test(name)) {await api.falconInventoryAction(name);await api.sleep(500);var next=await observe();return {status:'completed',reason:'Inventory action finished; inspect scene',step:name,frameId:next.frameId};}
        if(name==='falconContinue'||name==='falconInventory') {api.falconContinue();await api.sleep(500);var next=await observe();if(name==='falconInventory'){await api.falconInventory();await api.sleep(600);next=await observe();}return {status:'completed',reason:'Domain menu action finished; inspect scene',step:name,frameId:next.frameId};}
        if(name==='falconResume') {var proof=api.falconResume();await api.sleep(500);var next=await observe();return {status:'completed',reason:'Verified Falcon restart handoff; inspect fresh domain scene',step:name,provenance:proof,frameId:next.frameId};}
        if(name==='falconCombat'||name==='falconAmberCombat') return runFalconCombat(observation,api,observe,name);
        if(name==='falconPause') {await api.falconPause();await api.sleep(350);var next=await observe();return {status:'completed',reason:'Requested pause for domain controller repair',step:name,frameId:next.frameId};}
        if(name==='falconLookDown'||name==='falconLookUp') {api.falconPitch(name==='falconLookDown'?250:-250);await api.sleep(180);var next=await observe();return {status:'completed',reason:'Bounded Falcon pitch finished',step:name,frameId:next.frameId};}
        if(name==='falconSight') {await api.falconSight();await api.sleep(300);var next=await observe();return {status:'completed',reason:'Elemental Sight activated; inspect scene',step:name,frameId:next.frameId};}
        if(name==='falconFireAim'||name==='falconExitAim') {await api.falconAimAction(name.slice(6));await api.sleep(name==='falconFireAim'?1600:450);var next=await observe();return {status:'completed',reason:'Bounded Falcon aimed action finished; inspect scene',step:name,frameId:next.frameId};}
        if(name==='falconEnterAim') {await api.falconEnterAim();await api.sleep(450);var next=await observe();return {status:'completed',reason:'Falcon aim requested; inspect scene',step:name,frameId:next.frameId};}
        if(name==='falconRewardInteract') {await api.falconRewardInteract();await api.sleep(800);var next=await observe();return {status:'completed',reason:'Domain reward or exit interaction; inspect outcome',step:name,frameId:next.frameId};}
        if(name==='falconCrystalStrike') {await api.falconCrystalStrike();await api.sleep(700);var next=await observe();return {status:'completed',reason:'Single crystal attack; inspect progress',step:name,frameId:next.frameId};}
        if(name==='falconWindJump') {await api.falconWindJump();await api.sleep(1800);var next=await observe();return {status:'completed',reason:'Wind-current double jump requested; inspect gliding state',step:name,frameId:next.frameId};}
        if(name==='falconGlideForward') {var next=observation;for(var g=0;g<12;g++){await api.falconGlideForward();await api.sleep(100);next=await observe();if(next.hud.groundControls)break;}return {status:'completed',reason:'Bounded Falcon glide finished; inspect landing',step:name,frameId:next.frameId};}
        if(name==='falconDismissPyro'||name==='falconDismissTutorial') {await api.falconDismissPyro();await api.sleep(500);var next=await observe();return {status:'completed',reason:'Recognized Falcon tutorial advance clicked; inspect scene',step:name,frameId:next.frameId};}
        if(/^falconLook(Right|Left)(Fine|Wide)?$/.test(name)) {api.falconRotate((name.indexOf('Right')>=0?1:-1)*(name.endsWith('Fine')?100:name.endsWith('Wide')?750:250));await api.sleep(180);var next=await observe();return {status:'completed',reason:'Bounded Falcon camera turn',step:name,frameId:next.frameId};}
        if(name==='falconOpenDoor') {api.checkStop();var t=api.now();await api.falconOpenDoor();var ms=api.now()-t;await api.sleep(900);var next=await observe();return {status:'completed',reason:'Opened Falcon door; inspect scene',step:name,inputMs:ms,frameId:next.frameId};}
        if(name==='falconConsoleApproach'||name==='falconCorridorAdvance'||name==='falconForward'||name==='falconLeft'||name==='falconRight') {
            var sequence=name==='falconCorridorAdvance'?[['VK_W',800],['VK_W',800],['VK_W',800]]:name==='falconConsoleApproach'?[['VK_W',800],['VK_W',800],['VK_A',600]]:
                [[name==='falconLeft'?'VK_A':name==='falconRight'?'VK_D':'VK_W',800]];
            var hp0=observation.hud.health,inputMs=0,current=observation;
            for(var i=0;i<sequence.length;i++) {
                api.checkStop();
                if(current.hud.interact&&!(current.ocr||[]).some(function(r){return r.text.trim()==='Common Chest'&&r.x>1150&&r.y>400&&r.y<700;})) return {status:'stopped',reason:'Domain interaction available',step:name,frameId:current.frameId,inputMs:inputMs};
                if(!hp0||!current.hud.health||hp0.current-current.hud.health.current>hp0.max*0.1) return {status:'stopped',reason:'Domain health evidence changed',step:name,inputMs:inputMs};
                var t0=api.now();await api.falconMove(sequence[i][0],sequence[i][1]);inputMs+=api.now()-t0;
                await api.sleep(180);current=await observe();
            }
            return {status:'completed',reason:'Bounded Falcon movement finished; inspect scene',step:name,frameId:current.frameId,inputMs:inputMs};
        }
        if(name==='fieldCombat') {
            var began=api.now(),reason='Native combat returned; inspect enemies',current=observation,paused=false,prepared=false;
            try {await api.fieldFightPrepare();prepared=true;await api.sleep(700);current=await observe();for(var f=0;f<4&&!current.hud.world;f++){await api.sleep(350);current=await observe();}await api.fieldSelectTraveler();await api.sleep(500);current=await observe();await api.fieldNativeFight();}
            catch(e){reason=String(e&&e.message||e);}
            current=await observe();if(prepared&&await api.pauseWorldInventory()){for(var p=0;p<4;p++){await api.sleep(500);current=await observe();paused=current.ocr.some(function(r){return r.text.trim()==='Food'&&r.x>100&&r.x<300&&r.y<80;});if(paused)break;}}
            return {status:'stopped',reason:reason,step:name,pausedInventory:paused,elapsedMs:api.now()-began,frameId:current.frameId};
        }
        if(name==='focusGame') return {status:'completed',step:name,reason:'Game focus recovered; inspect fresh scene',frameId:observation&&observation.frameId};
        if(['wolfForward','wolfForwardFine','wolfLeft','wolfRight','wolfLookLeft','wolfLookRight','wolfLookDown','wolfLookUp','wolfPause'].indexOf(name)>=0) {await api.wolfDomainAction();await api.sleep(name==='wolfPause'?600:180);var next=await observe();return {status:'completed',step:name,reason:'Bounded Wolf domain action; inspect fresh scene',frameId:next.frameId};}
        if(name==='wolfContinue') {api.wolfContinue();await api.sleep(450);var next=await observe();return {status:'completed',step:name,reason:'Wolf challenge resumed; inspect scene',frameId:next.frameId};}
        if(name==='wolfCombat')return ActOneCombat.runWolf(observation,api,observe);
        if(name==='wolfOpeningDialogue') {
            var current=observation,presses=0,unknown=0;
            for(var d=0;d<12;d++) {
                var h=current.hud||{};
                if(h.choice) return {status:'stopped',step:name,reason:'Inspect Wolf dialogue choice',presses:presses,frameId:current.frameId};
                if(h.health&&h.groundControls) return {status:'completed',step:name,reason:'Wolf dialogue returned to domain HUD',presses:presses,frameId:current.frameId};
                if(h.dialogueReady) {await api.wolfAdvanceDialogue();presses++;unknown=0;}
                else if(++unknown>4) return {status:'stopped',step:name,reason:'Unrecognized dialogue transition',presses:presses,frameId:current.frameId};
                await api.sleep(650);current=await observe();
            }
            return {status:'stopped',step:name,reason:'Bounded Wolf dialogue limit',presses:presses,frameId:current.frameId};
        }
        if(name==='wolfEntryApproach') {
            var current=observation,hp0=current.hud&&current.hud.health,moves=0;
            for(var i=0;i<4;i++) {
                var h=current.hud||{},hp=h.health;
                if(h.interact||h.dialogueReady||h.choice||h.tutorialStep) return {status:'completed',step:name,reason:'Wolf entrance interaction or dialogue reached',moves:moves,frameId:current.frameId};
                if(!hp0||!hp||hp0.current-hp.current>hp0.max*0.1) return {status:'stopped',step:name,reason:'Wolf approach health changed',moves:moves,frameId:current.frameId};
                await api.wolfEntryForward();moves++;await api.sleep(180);current=await observe();
            }
            return {status:'completed',step:name,reason:'Bounded Wolf entrance approach finished; inspect scene',moves:moves,frameId:current.frameId};
        }
        if(name==='wolfStart'){var label=api.startWolfDomain();await api.sleep(800);var next=await observe();return {status:'completed',step:name,label:label,reason:'Wolf entrance Start clicked; inspect party setup',frameId:next.frameId};}
        if(name==='wolfPartyStart'){api.checkStop();var click0=api.now();api.startWolfParty();var clickMs=api.now()-click0;await api.sleep(800);var next=await observe();return {status:'completed',reason:'Wolf party Start clicked; inspect loading or domain',step:name,clicks:1,inputMs:clickMs,frameId:next.frameId};}
        if(name==='wolfDoorInteract') {for(var d=0;d<2;d++){var action=await api.wolfDoorAction();await api.sleep(action==='scroll'?400:1000);var next=await observe();if(action==='interact')return {status:'completed',step:name,reason:'Selected Wolf entrance interaction',frameId:next.frameId};}return {status:'stopped',step:name,reason:'Wolf row selection did not settle'};}
        if(name==='wolfFalconWaypoint') {await api.wolfFalconWaypoint();var next=await observe();return {status:'completed',step:name,reason:'Native teleport to unlocked Falcon waypoint returned; inspect arrival',frameId:next.frameId};}
        if(name==='fieldRetreatToStatue') {await api.fieldRetreatToStatue();var next=await observe();return {status:'completed',step:name,reason:'Native teleport to unlocked Statue returned; inspect world and healing',frameId:next.frameId};}
        if(name==='worldInventory') {var opened=await api.pauseWorldInventory(),next=observation,paused=false;if(opened){for(var p=0;p<4;p++){await api.sleep(500);next=await observe();paused=next.ocr.some(function(r){return /^(Food|Weapons)$/.test(r.text.trim())&&r.x>100&&r.x<300&&r.y<80;});if(paused)break;}}return {status:paused?'completed':'stopped',step:name,pausedInventory:paused,frameId:next.frameId};}
        if(name==='mapBindingProbe') return {status:'completed',step:name,api:api.mapBindingProbe()};
        if(name==='nativeFightProbe') return {status:'completed',step:name,api:api.nativeFightProbe()};
        if(name==='journalInventory') {await api.journalInventory();await api.sleep(600);var next=await observe();return {status:'completed',reason:'Opened inventory from temple quest journal; inspect food',step:name,frameId:next.frameId};}
        if(name==='falconPartyStart') { api.checkStop();var click0=api.now();api.startFalconParty();var clickMs=api.now()-click0;await api.sleep(800);var next=await observe();return {status:'completed',reason:'Falcon party Start clicked; inspect loading or domain',step:name,clicks:1,inputMs:clickMs,frameId:next.frameId}; }
        if(name==='falconStart') return runFalconStart(observation,api,observe);
        if(name==='falconWaypoint') return runFalconWaypoint(observation,api,observe);
        if(name==='headquartersWall') return runHeadquartersWall(observation,api,observe);
        if(name==='headquartersStairWall') return runHeadquartersWall(observation,api,observe,{x:-821.37,y:2273.58,minAngle:175,maxAngle:225,step:name});
        if(name==='headquartersStairRail') return runHeadquartersWall(observation,api,observe,{x:-815.45,y:2277.52,minAngle:225,maxAngle:280,step:name});
        return {status:'stopped',reason:'Unsupported quest step: '+name,step:name,frameId:observation&&observation.frameId||null,inputMs:0};
    }
    async function runFalconCombat(initial,api,observe,name) {
        name=name||'falconCombat';
        var began=api.now(),current=initial,actions=0,reason='Combat action limit',lastSkill=-10000,missing=0,hp0=null,scans=0,stable=0,lastWidth=null,approaches=0;
        try {
            api.falconContinue();await api.sleep(450);current=await observe();
            await api.falconCombatKey(name==='falconAmberCombat'?'VK_2':'VK_1');actions++;await api.sleep(500);current=await observe();hp0=current.hud.health;
            if(hp0&&hp0.current/hp0.max>=0.6&&(current.hud.enemyBars||[]).length){await api.falconCombatKey('VK_Q');actions++;await api.sleep(800);current=await observe();}
            while(actions<30&&api.now()-began<30000) {
                api.checkStop();var h=current.hud,hp=h&&h.health;
                if(!hp||!hp0||hp.current/hp.max<0.6||hp0.current-hp.current>hp0.max*0.2) {reason='Combat health guard';break;}
                if(!h.enemyBars||!h.enemyBars.length) {
                    if(++missing>2) {
                        if(scans<4&&typeof api.falconCombatScan==='function') {await api.falconCombatScan(scans===0);scans++;actions++;missing=0;}
                        else {reason='Enemy evidence absent; inspect completion or camera';break;}
                    }
                    await api.sleep(200);current=await observe();continue;
                }
                missing=0;
                var width=Math.max.apply(null,h.enemyBars.map(function(b){return b.width;}));
                stable=lastWidth!==null&&width>=lastWidth-1?stable+1:0;lastWidth=width;
                if(stable>=5&&typeof api.falconCombatApproach==='function'){
                    if(approaches>=3){reason='No damage progress after bounded approaches';break;}
                    await api.falconCombatApproach();approaches++;actions++;stable=0;lastWidth=null;await api.sleep(200);current=await observe();continue;
                }
                var skill=api.now()-lastSkill>=8500;
                await api.falconCombatKey(skill?'VK_E':'VK_LBUTTON');actions++;
                if(skill) lastSkill=api.now();
                await api.sleep(skill?250:180);current=await observe();
            }
            if(reason==='Combat action limit'&&actions<30&&api.now()-began>=30000) reason='Combat time limit';
        } catch(e) {reason=String(e&&e.message||e);}
        api.checkStop();current=await observe();
        var paused=false;
        if(current.hud&&current.hud.health&&current.map===null&&!current.hud.journal&&!current.hud.bigMap) {
            for(var pauseAttempt=0;pauseAttempt<3;pauseAttempt++){
                await api.falconPause();await api.sleep(600);current=await observe();
                paused=current.ocr.some(function(r){return r.text.trim()==='Continue Challenge';});
                if(paused||!current.hud.health)break;
            }
        }
        return {status:'stopped',reason:reason,step:name,actions:actions,paused:paused,elapsedMs:api.now()-began,frameId:current.frameId};
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
