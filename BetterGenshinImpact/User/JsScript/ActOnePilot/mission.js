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
        var title=rows.filter(function(r){return String(r.text||'').trim()==='Dressing Room'&&r.x>=740&&r.x<1200&&r.y>=480&&r.y<570;});
        var first=rows.filter(function(r){return String(r.text||'').trim()==='Dressing Room unlocked. Collect unique wind'&&r.x>=620&&r.x<1300&&r.y>=555&&r.y<625;});
        var second=rows.filter(function(r){return String(r.text||'').trim()==='gliders and outfits to alter the appearance of'&&r.x>=620&&r.x<1300&&r.y>=590&&r.y<655;});
        var third=rows.filter(function(r){return String(r.text||'').trim()==='your characters.'&&r.x>=780&&r.x<1150&&r.y>=625&&r.y<690;});
        return title.length===1&&first.length===1&&second.length===1&&third.length===1;
    }
    async function runNavigation(request, observation, api, observe) {
        var began = api.now(), initialHealth = observation.hud.health, totalInputMs = 0, turns = 0, movements = 0;
        var current = observation, afterForward = null, stalled = 0, turnAttempts = 0, jumpRecoveries = 0, climbReleases=0, climbSteps=0, climbEpisodeSteps=0, climbLimit=null, climbIsVerified=false, waypointIndex=0;
        function stop(reason) { return { status: 'stopped', reason: reason, nextWaypointIndex: waypointIndex, inputMs: totalInputMs, turns: turns, movements: movements, jumpRecoveries: jumpRecoveries, climbSteps:climbSteps, climbReleases:climbReleases }; }
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
                if(current.hud.climbing) {
                    if(request.objective==='Go to the Knights of Favonius Headquarters') return stop('Unexpected climbing on headquarters approach');
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
                    request.objective==='Go to the Knights of Favonius Headquarters'?2:5;
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
                        if ((!crystalStep && !verifiedRoadLedge) || jumpRecoveries >= 1) return stop('Map coordinates stalled');
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
        if(name==='headquartersWall') return runHeadquartersWall(observation,api,observe);
        if(name==='headquartersStairWall') return runHeadquartersWall(observation,api,observe,{x:-821.37,y:2273.58,minAngle:175,maxAngle:225,step:name});
        if(name==='headquartersStairRail') return runHeadquartersWall(observation,api,observe,{x:-815.45,y:2277.52,minAngle:225,maxAngle:280,step:name});
        return {status:'stopped',reason:'Unsupported quest step: '+name,step:name,frameId:observation&&observation.frameId||null,inputMs:0};
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
