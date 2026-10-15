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
        if(expected==='Check the suspicious location and eliminate any threats'&&current&&current.hud&&Array.isArray(current.hud.objectives)&&clean(current.hud.objectives.join(' ')).indexOf(clean(expected))===0)return true;
        if(expected==='Solve the mystery (Go to Kaeya at the Knights of Favonius HQ for a hint)'&&current&&current.hud&&Array.isArray(current.hud.objectives)&&objectiveMatches(current.hud.objectives.slice(0,2).join(' '),expected))return true;
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
    async function runNavigation(request, observation, api, observe, protectedLisa) {
        var exploring=request&&request.objective==='Explore for Adventure Rank';
        // Exploration is an explicitly requested, bounded errand. Ambient NPC
        // labels (or an independently tracked quest) are not its objective.
        function navigationObjective(o){return exploring||hasObjective(o,request.objective);}
        if(exploring&&(!Array.isArray(request.waypoints)||request.waypoints.some(function(p){return !p||p.map!=='Teyvat'||!Number.isFinite(p.x)||!Number.isFinite(p.y)||p.x< -1600||p.x> -700||(p.y<1700&&!(p.x>=-1500&&p.x<=-1300&&p.y>=1450))||p.y>2700;})))return {status:'stopped',reason:'Exploration limited to bounded starter Mondstadt region'};
        var amberCity=request&&request.objective==='Talk to Amber'&&Array.isArray(request.waypoints)&&request.waypoints.length>0&&request.waypoints.every(p=>p.map==='Teyvat'&&p.x>=-900&&p.x<=-700&&p.y>=2200&&p.y<=2450);
        var guildObjective=amberCity||request&&["Go to the exam point","Check the suspicious location and eliminate any threats","Explore for Adventure Rank","Purchase Fisherman's Toast",'Offer the Anemoculus to the Statue','Give the Chicken-Mushroom Skewer to Lynn','Speak to Lynn','Talk to Katheryne for more details','Talk to Wagner the blacksmith','Collect three Iron Chunks and give them to Wagner','Talk to Kaeya','Talk to Kaeya at the meeting spot','Report to Kaeya','Meet with the informant at the designated location','Talk to the informant','Solve the mystery (Go to Kaeya at the Knights of Favonius HQ for a hint)',"Go to the Adventurers' Guild and listen to their report"].indexOf(request.objective)>=0;
        if(guildObjective&&!protectedLisa){
            if(!Number.isInteger(request.deadlineMs)||request.deadlineMs<1000||request.deadlineMs>45000||
                !Array.isArray(request.waypoints)||request.waypoints.length<1||request.waypoints.length>4||
                typeof api.runActTwoNavigationWithPause!=='function')
                return {status:'stopped',reason:'Finite Act II navigation and pause wrapper required'};
            return api.runActTwoNavigationWithPause(observation,observe,function(field){return runNavigation(request,field,api,observe,true);});
        }
        var lisaObjective=request&&request.objective==='Meet Lisa at the temple';
        if(lisaObjective&&!protectedLisa) {
            if(!Number.isInteger(request.deadlineMs)||request.deadlineMs<1000||request.deadlineMs>90000||
               !Array.isArray(request.waypoints)||request.waypoints.length<1||request.waypoints.length>10)
                return {status:'stopped',reason:'Lisa navigation requires one finite route batch within 90 seconds'};
            if(typeof api.runLisaNavigationWithPause!=='function')
                return {status:'stopped',reason:'Verified Lisa navigation pause wrapper unavailable'};
            return api.runLisaNavigationWithPause(observation,observe,function(fieldObservation){
                return runNavigation(request,fieldObservation,api,observe,true);
            });
        }
        var began = api.now(), initialHealth = observation.hud.health, totalInputMs = 0, turns = 0, movements = 0;
        var current = observation, afterForward = null, stalled = 0, turnAttempts = 0, jumpRecoveries = 0, climbReleases=0, climbSteps=0, climbEpisodeSteps=0, climbLimit=null, climbIsVerified=false, waypointIndex=0;
        function lisaGrounded(current) {
            return !lisaObjective || !!(current&&current.hud&&current.hud.groundControls===true&&current.hud.climbing!==true);
        }
        function lisaUnsafe(current) {
            return lisaObjective && (!lisaGrounded(current)||((current.hud.enemyBars||[]).length>0&&
                !(typeof api.lisaNavigationEnemyAllowed==='function'&&api.lisaNavigationEnemyAllowed())));
        }
        function lisaUnsafeReason(current) {
            return lisaObjective && (current&&current.hud&&current.hud.climbing===true?'Lisa navigation refuses climbing':
                current&&current.hud&&current.hud.groundControls!==true?'Lisa navigation requires confirmed ground controls':
                'Enemy bar present during Lisa navigation');
        }
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
                if(exploring&&current.hud.health&&current.hud.health.current/current.hud.health.max<0.85)return stop('Exploration health threshold reached');
                if(guildObjective&&(current.hud.groundControls!==true||current.hud.climbing||(current.hud.enemyBars||[]).length))
                    return stop('Guild approach requires safe grounded travel');
                if(lisaUnsafe(current)) return stop(lisaUnsafeReason(current));
                for (var transientRetry=0; transientRetry<2 && (!validHealth(current.hud.health) ||
                    (!navigationObjective(current) && !hasNewQuestToast(current))); transientRetry++) {
                    if (api.now()-began>=request.deadlineMs) return stop('Navigation deadline reached during evidence retry');
                    await api.sleep(180); api.checkStop(); current=await observe();
                    if (!safeTransientFrame(current))
                        return stop('Dialogue, objective, low-health, or missing navigation evidence');
                }
                if (!validHealth(current.hud.health)) return stop('Fresh health evidence unavailable');
                if (api.now()-began>=request.deadlineMs) return stop('Navigation deadline reached during evidence retry');
                if (!current.hud.world) return stop('Dialogue, objective, low-health, or missing navigation evidence');
                if (!navigationObjective(current)) {
                    if (!hasNewQuestToast(current)) return stop('Expected objective not visible');
                    var toastDeadline = Math.min(api.now() + 8000, began + request.deadlineMs);
                    while (!navigationObjective(current)) {
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
                if (!navigationObjective(current)) return stop('Expected objective not visible');
                if (!validHealth(current.hud.health)) return stop('Fresh health evidence unavailable');
                if (!validHealth(initialHealth)) initialHealth = current.hud.health;
                if (initialHealth.current - current.hud.health.current > initialHealth.max * 0.1) return stop('Health dropped more than 10% of maximum during mission');
                for(var coordinateRetry=0;coordinateRetry<2&&!plausibleMap(current,target);coordinateRetry++) {
                    if(request.deadlineMs-(api.now()-began)<180) return stop('Navigation deadline reached during map coordinate retry');
                    await api.sleep(180);api.checkStop();var coordinateFrame=await observe();
                    if(lisaUnsafe(coordinateFrame)) return stop(lisaUnsafeReason(coordinateFrame));
                    if(!safeTransientFrame(coordinateFrame)||!coordinateFrame.hud.world||!validHealth(coordinateFrame.hud.health)||
                       coordinateFrame.hud.health.current/coordinateFrame.hud.health.max<0.6)
                        return stop('Unsafe HUD during map coordinate retry');
                    if(!navigationObjective(coordinateFrame)) return stop('Objective changed during map coordinate retry');
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
                if(guildObjective&&hasTargetF(current)&&hasTargetName(current,[request.objective==='Offer the Anemoculus to the Statue'?'Statue of The Seven':request.objective==='Speak to Lynn'?'Lynn':request.objective==='Talk to the informant'?'Vile':/^(?:Talk to Kaeya(?: at the meeting spot)?|Report to Kaeya)$/.test(request.objective)?'Kaeya':request.objective==="Go to the Adventurers' Guild and listen to their report"?'Cyrus':request.objective==='Talk to Wagner the blacksmith'?'Wagner':'Katheryne']))return stop('Town quest interaction available');
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
                var arrivalRadius=(request.objective==='Offer the Anemoculus to the Statue'||request.objective==='Talk to the informant'||request.objective==='Speak to Lynn'||request.objective==='Give the Chicken-Mushroom Skewer to Lynn')?0.5:guildObjective?2:request.objective==='Clear out the nearby hilichurl camp'?3:
                    ['Go to the Knights of Favonius Headquarters','Enter the Knights of Favonius Headquarters','Talk to Amber','Talk to Kaeya','Talk to Lisa','Enter the temple'].indexOf(request.objective)>=0?2:5;
                if (!investigating && distance <= arrivalRadius) break;
                if (distance > 150) return stop('Waypoint farther than the allowed local segment');
                if (afterForward) {
                    var moved = Math.hypot(current.map.x - afterForward.x, current.map.y - afterForward.y);
                    if (moved > 25) return stop('Map position jumped');
                    stalled = moved < 0.5 ? stalled + 1 : 0; afterForward = null;
                    if (stalled >= 3) {
                        if(lisaObjective) return stop('Lisa navigation disables jump recovery');
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
                if (magnitude > (/^Talk to Kaeya/.test(request.objective)?3:8)) {
                    if (++turnAttempts > 16) return stop('Camera did not converge');
                    if(lisaUnsafe(current)) return stop(lisaUnsafeReason(current));
                    var rotateStart = api.now(); await api.rotate(Math.max(-750, Math.min(750, Math.round(-ratio * diff))));
                    totalInputMs += api.now() - rotateStart; turns++;
                    await api.sleep(180); current = await observe(); continue;
                }
                turnAttempts = 0;
                var held = Math.floor(Math.min(request.objective==='Talk to the informant'&&distance<3?100:markerApproach || distance < 10 ? 250 : 800, request.deadlineMs - (api.now() - began)));
                if (held <= 0) return stop('Navigation deadline reached');
                if(lisaUnsafe(current)) return stop(lisaUnsafeReason(current));
                afterForward = { x: current.map.x, y: current.map.y };
                var inputStarted = api.now(); await api.forward(held); totalInputMs += api.now() - inputStarted; movements++;
                await api.sleep(150); current = await observe();
            }
        }
        return { status: 'arrived', nextWaypointIndex: request.waypoints.length, inputMs: totalInputMs, turns: turns, movements: movements, jumpRecoveries: jumpRecoveries, climbSteps:climbSteps, climbReleases:climbReleases };
    }
    function selectDialogueChoice(current) {
        if (!current.hud.choice) return null;
        var rows = current.ocr || [], speakers = ['Amber', 'Paimon', 'Jean', 'Lisa', 'Kaeya', 'Venti', 'Katheryne', 'Wagner', 'Cyrus', 'Vile', 'Lynn', 'Jack'];
        var known = rows.some(function (r) { return speakers.indexOf(r.text.trim()) >= 0 && r.x > 600 && r.x < 1200 && r.y >= 830 && r.y < 900; });
        if(!known)known=rows.some(function(r){return r.text==='yrus'&&r.x>=900&&r.x<=1000&&r.y>=850&&r.y<=880;})&&rows.some(function(r){return r.text==="Branch Master, Adventurers' Guild"&&r.x>=740&&r.x<=800&&r.y>=890&&r.y<=920;});
        var options = rows.filter(function (r) { return r.x > 1000 && r.x < 1800 && r.y > 430 && r.y < 830 && r.text.trim().length > 6; }).sort(function (a,b) { return a.y-b.y || a.x-b.x; });
        var allowed = ["Good thing the dragon didn't notice", "Is talking to dragons normal?"];
        if (options.length < 1 || options.length > 8) return null;
        if (options.some(function (r) { return /purchase|buy|spend|primogem|genesis crystal|intertwined fate|acquaint fate|delete|discard|consume|exchange|resin|pay\b/i.test(r.text); })) return null;
        if(rows.some(function(r){return r.text==='Sara'&&r.x>800&&r.x<1100&&r.y>830&&r.y<900;})){
            var food=options.filter(function(r){return r.text==='Can I get food to-go?';});return food.length===1?food[0].text:null;
        }
        var preferred = options.filter(function (r) { return allowed.indexOf(r.text.trim()) >= 0; });
        if (preferred.length === 1) return preferred[0].text.trim();
        if (!known) return null;
        return options[0].text.trim();
    }
    async function runDialogue(api, observe, options) {
        options=options||{};
        var deadlineMs=Number.isInteger(options.deadlineMs)&&options.deadlineMs>=1000?Math.min(60000,options.deadlineMs):60000;
        var maxPresses=Number.isInteger(options.maxPresses)&&options.maxPresses>=1?Math.min(40,options.maxPresses):40;
        var began = api.now(), presses = 0, inputMs = 0, current = await observe(), unknown = 0, tutorialSteps = Object.create(null);
        while (api.now() - began < deadlineMs && presses < maxPresses) {
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
    async function pollEntryWorld(current,api,observe,options) {
        options=options||{};
        var began=options.began===undefined?api.now():options.began;
        var deadline=options.deadline===undefined?api.now()+30000:options.deadline;
        var polls=0,sawLoading=false,doorClicked=options.doorClicked===true,doorProof=options.doorProof||null;
        function result(status,reason,postState) {
            var titleClicked=options.titleClicked===true;
            return {status:status,step:options.step||'enterGame',reason:reason,clicks:(titleClicked?1:0)+(doorClicked?1:0),
                phaseClicks:{title:titleClicked?1:0,door:doorClicked?1:0},inputMs:Math.max(0,api.now()-began),
                preflightObservations:options.preflightObservations||0,polls:polls,frameId:current&&current.frameId||null,postState:postState,
                target:doorClicked?doorProof:options.titleProof||null};
        }
        while(api.now()<deadline&&polls<40) {
            api.checkStop();await api.sleep(Math.min(500,deadline-api.now()));current=await observe();polls++;
            if(actOneEnterGameAuthPrompt(current&&current.ocr)) return result('stopped','Authentication or verification prompt appeared; inspect manually','authPrompt');
            if(current&&current.hud&&current.hud.world===true) return result('completed','Game world HUD observed after entry','worldHud');
            if(actOneEnterGameUnknownUi(current&&current.ocr)||current&&current.hud&&
                (current.hud.journal||current.hud.bigMap||current.hud.dialogueReady||current.hud.choice)||current&&current.map!==null)
                return result('stopped','Unknown UI appeared after entry; inspect manually','unknownUi');
            if(actOneEnterGameLoading(current&&current.ocr)) sawLoading=true;
            if(options.autoDoor&&!doorClicked&&actOneEnterWorldTarget(current,api.now())) {
                try {api.checkStop();api.requireInputReady();doorProof=api.startGame('enterWorld');doorClicked=true;}
                catch(e) {return result('stopped',String(e&&e.message||e),'doorClickRejected');}
            }
        }
        var doorVisible=actOneEnterWorldTarget(current,api.now()),titleVisible=actOneEnterGameTitleFrame(current,api.now());
        return result('stopped','World HUD not observed before bounded post-click deadline; no retry sent',
            doorClicked?'doorUnverified':doorVisible?'doorPromptUnclicked':sawLoading?'loadingUnverified':titleVisible?'titlePromptUnverified':'titleClearedUnverified');
    }
    async function runQuestStep(name, observation, api, observe) {
        if(name==='actTwoLionInspectClose'){
            var er=observation.ocr||[];
            if(!Number.isFinite(observation.timestamp)||api.now()<observation.timestamp||api.now()-observation.timestamp>1000||!['Domain Entrance','Domain unlocks at Adventure Rank 16'].every(t=>er.filter(r=>r.text===t).length===1)||er.filter(r=>r.text==='Elemental Trial: Vaporize').length!==2)return {status:'stopped',reason:'Exact locked Elemental Trial entrance required'};
            await api.keyPress('VK_ESCAPE');await api.sleep(700);var closed=await observe();return api.finishActTwoDialogue(observation,observe,{status:'completed',step:name,fieldFrameId:closed.frameId});
        }
        if(name==='actTwoLionInspect')return api.runActTwoNavigationWithPause(observation,observe,async function(field){
            var current=field,moves=0;
            for(var n=0;n<4;n++){
                var h=current.hud,m=current.map,rows=current.ocr||[];
                if(!m||m.map!=='Teyvat'||Math.hypot(m.x+1427.426,m.y-1661.825)>12||!h.world||!h.groundControls||h.climbing||!h.health||h.health.max!==2313||h.health.current<1967||(h.enemyBars||[]).length||(h.objectives||[]).length||!Number.isFinite(current.timestamp)||api.now()-current.timestamp>1000||api.now()<current.timestamp)return {status:'stopped',reason:'Fresh healthy Lion entrance ground required',moves:moves};
                var labels=rows.filter(r=>r.text==='Temple of the Lion'&&r.x>=1150&&r.x<=1500&&r.y>=450&&r.y<=620),prompts=rows.filter(r=>r.text==='F'&&r.x>=1080&&r.x<=1170&&r.y>=450&&r.y<=620);
                if(labels.length===1&&prompts.length===1&&Math.abs(labels[0].y+labels[0].height/2-prompts[0].y-prompts[0].height/2)<25){await api.keyPress('VK_F');await api.sleep(900);current=await observe();return {status:'completed',reason:'Lion entrance opened for inspection; no trial started',moves:moves,entranceOpened:true,frameId:current.frameId};}
                if(n===3||Math.abs(m.cameraAngle-18)>20||h.interact)return {status:'stopped',reason:'Entrance inspection requires reviewed alignment',moves:moves};
                await api.forward(600);moves++;await api.sleep(250);current=await observe();
            }
        });
        if(name==='actTwoNativeCombat'||name==='actTwoNativeGroup'||name==='actTwoNativeFinish')return api.runActTwoNativeCombat(observation,observe);
        if(name==='actTwoField')return api.runActTwoField(observation,observe);
        if(name==='actTwoMagePrep')return api.runActTwoMagePrep(observation,observe);
        if(name==='actTwoMageFinish')return api.runActTwoMagePrep(observation,observe);
        if(name==='actTwoMageNative')return api.runActTwoMageNative(observation,observe);
        if(name==='actTwoMageRetreat')return api.runActTwoMageRetreat(observation,observe);
        if(name==='actTwoMageBurst')return api.runActTwoMageBurst(observation,observe);
        if(name==='actTwoWindriseSlime')return api.runActTwoWindriseSlime(observation,observe);
        if(name==='actTwoWindriseOculus')return api.runActTwoNavigationWithPause(observation,observe,async function(field){
            if(!field.map||Math.hypot(field.map.x+1265.26,field.map.y-1974.11)>3||!field.hud.health||field.hud.health.current!==1700||field.hud.health.max!==1700||hasObjectiveText(field)||Math.abs(field.map.cameraAngle-299.5)>15)return {status:'stopped',reason:'Exact healthy Windrise boulder approach required'};
            if(field.map.cameraAngle>295){await api.rotate(-110);await api.sleep(200);field=await observe();if(!field.hud.world||!field.hud.groundControls||field.hud.climbing)return {status:'stopped',reason:'Boulder alignment changed'};}
            await api.keyPress('VK_SPACE');await api.forward(650);await api.sleep(550);var after=await observe();return {status:'stopped',step:name,frameId:after.frameId,reason:'Single low-boulder jump; inspect Anemoculus pickup'};
        });
        if(name==='actTwoToast')return api.runActTwoToast(observation,observe);
        if(name==='actTwoSaraOpen')return api.runActTwoNavigationWithPause(observation,observe,async function(field){
            var rows=field.ocr||[],labels=rows.filter(function(r){return r.text==='Sara'&&r.x>1200&&r.x<1400&&r.y>480&&r.y<600;}),prompts=rows.filter(function(r){return r.text==='F'&&r.x>1080&&r.x<1170&&r.y>480&&r.y<600;});
            if(!hasObjective(field,"Purchase Fisherman's Toast")||!field.map||Math.hypot(field.map.x+887,field.map.y-2240)>4||labels.length!==1||prompts.length!==1||Math.abs(labels[0].y+labels[0].height/2-prompts[0].y-prompts[0].height/2)>=25)return {status:'stopped',reason:'Exact selected Sara prerequisite interaction required'};
            await api.keyPress('VK_F');await api.sleep(900);var after=await observe();
            for(var poll=0;poll<6&&!after.hud.dialogueReady&&!after.hud.choice;poll++){api.checkStop();await api.sleep(300);after=await observe();}
            return {status:'stopped',step:name,frameId:after.frameId,reason:'Sara opened; inspect quest dialogue'};
        });
        if(name==='actTwoStatueOpen')return api.runActTwoNavigationWithPause(observation,observe,async function(field){
            var rows=field.ocr||[],selection=eval(file.readTextSync('act-two-interaction.js')+'\nActTwoInteraction;');
            if((!hasObjective(field,'Offer the Anemoculus to the Statue')&&!hasObjective(field,'Check the suspicious location and eliminate any threats')&&(field.hud.objectives||[]).length)||!field.map||Math.hypot(field.map.x+1265.917,field.map.y-1928.381)>8||selection.selection(rows,'Statue of The Seven')!=='selected')return {status:'stopped',reason:'Fresh selected Windrise Statue interaction required'};
            await api.keyPress('VK_F');await api.sleep(900);var after=await observe();
            for(var poll=0;poll<6&&!after.hud.dialogueReady&&!after.hud.choice;poll++){api.checkStop();await api.sleep(300);after=await observe();}
            return {status:'stopped',step:name,frameId:after.frameId,reason:'Statue interaction opened; inspect offering options'};
        });
        if(name==='actTwoStatueSelectKaeya')return api.runActTwoNavigationWithPause(observation,observe,async function(field){
            var sm=field.map,sh=field.hud,sr=field.ocr||[];
            if(!sm||sm.map!=='Teyvat'||Math.hypot(sm.x+1265.917,sm.y-1928.381)>8||!sh.world||!sh.groundControls||sh.climbing||!sh.health||sh.health.max!==1363||sh.health.current<=0||sh.health.current>1363||(sh.enemyBars||[]).length||(sh.objectives||[]).length||sr.filter(r=>r.text==='Kaeya'&&r.x>=1650&&r.x<=1770&&r.y>=430&&r.y<=470).length!==1)return {status:'stopped',reason:'Living Traveler at Windrise Statue with Kaeya slot three required'};
            await api.keyPress('VK_3');await api.sleep(800);var selected=await observe();
            return {status:'stopped',step:name,fieldFrameId:selected.frameId,reason:selected.hud.health&&selected.hud.health.max===2313?'Kaeya selected; verify recovered health':'Character switch unverified; inspect before further input'};
        });
        if(name==='actTwoCooking')return api.runActTwoCooking(observation,observe);
        if(name==='actTwoChallengeStart')return api.runActTwoNavigationWithPause(observation,observe,async function(field){
            var cm=field.map,ch=field.hud,cr=field.ocr||[];
            if(!cm||cm.map!=='Teyvat'||Math.hypot(cm.x+1407.49,cm.y-2339.86)>5||!ch.world||!ch.groundControls||ch.climbing||!ch.health||ch.health.max!==2313||ch.health.current<1967||ch.enemyBars.length||(ch.objectives||[]).length||cr.filter(r=>r.text==='Start Challenge'&&r.x>=1200&&r.x<=1450&&r.y>=500&&r.y<=550).length!==1||cr.filter(r=>r.text==='F'&&r.x>=1080&&r.x<=1150&&r.y>=500&&r.y<=550).length!==1)return {status:'stopped',reason:'Fresh selected northern challenge pedestal required'};
            await api.keyPress('VK_F');await api.sleep(600);var started=await observe();
            return {status:'stopped',step:name,fieldFrameId:started.frameId,reason:'Challenge started once; inspect objective before further input'};
        });
        if(name==='actTwoCookBack'){
            var doneRows=observation.ocr||[];
            function doneText(t,x0,x1,y0,y1){return doneRows.filter(r=>String(r.text).trim()===t&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1).length===1;}
            if(observation.map||observation.hud.world||!doneText('Cook',100,300,0,80)||!doneText('Auto Cook',700,1000,970,1040)||!doneText('Cooking ingredients required',65,400,400,450)||!doneText('Amber',1650,1850,285,340))return {status:'stopped',reason:'Verified mastered cooking panel required'};
            await api.keyPress('VK_ESCAPE');await api.sleep(500);var doneAfter=await observe();
            return {status:'stopped',step:name,frameId:doneAfter.frameId,reason:'Returned from mastered recipe panel; inspect before closing'};
        }
        if(name==='actTwoCookClose'){
            var cookRows=observation.ocr||[];
            if(!cookRows.some(function(r){return r.text==='Cook'&&r.x>100&&r.x<300&&r.y<80;})||!cookRows.some(function(r){return /^Proficiency: [0-5]\/5$/.test(r.text)&&r.x>1300&&r.y>400&&r.y<470;})||!cookRows.some(function(r){return r.text==='Ingredients'&&r.x>1300&&r.y>550&&r.y<620;}))return {status:'stopped',reason:'Exact initial cooking recipe screen required'};
            await api.keyPress('VK_ESCAPE');await api.sleep(500);await observe();return api.finishActTwoDialogue(observation,observe,{status:'completed',step:name});
        }
        if(name==='actTwoJournalClose'){
            if(!observation.hud.journal||!(observation.ocr||[]).some(function(r){return ["Kaeya's Troubles",'Mystery of the Arcadian Ruins','The Art of Cooking','Shadow Over Mondstadt','License to Glide','Collector of Anemo Sigils','Not to be Missed'].indexOf(String(r.text).trim())>=0&&r.x>=850&&r.x<=1400&&r.y>=90&&r.y<=180;}))return {status:'stopped',reason:'Verified prerequisite quest journal required'};
            await api.keyPress('VK_ESCAPE');await api.sleep(500);await observe();
            return api.finishActTwoDialogue(observation,observe,{status:'completed',step:name,questComplete:false});
        }
        if(name==='actTwoWoodExit'){
            if(!(observation.ocr||[]).some(function(r){return r.text==='Wood'&&r.x>800&&r.x<1100&&r.y>830&&r.y<900;}))return {status:'stopped',reason:'Exact Wood dialogue required'};
            if(!observation.hud.choice){await api.keyPress('VK_SPACE');await api.sleep(700);observation=await observe();}
            var bye=(observation.ocr||[]).filter(function(r){return /^(Goodbye\.?|See you\.?|Bye\.?)$/.test(r.text.trim())&&r.x>1000&&r.y>430&&r.y<830;});
            if(bye.length===1)await api.chooseChoice(bye[0].text.trim());
            return api.finishActTwoDialogue(observation,observe,await runDialogue(api,observe,{maxPresses:4,deadlineMs:10000}));
        }
        if(name==='actTwoIndoorMove')return api.runActTwoIndoorMove(observation,observe);
        if(name==='actTwoHqEnter')return api.runActTwoNavigationWithPause(observation,observe,async function(field){
            var rows=field.ocr||[],prompt=rows.filter(function(r){return r.x>=1200&&r.x<=1500&&r.y>=495&&r.y<=580;}).map(function(r){return r.text;}).join(' ');
            if(!hasObjective(field,'Talk to Kaeya')||!field.map||Math.hypot(field.map.x+778.26,field.map.y-2243.68)>5||
                !/Enter/.test(prompt)||!/Favonius/.test(prompt)||!/Headquarters/.test(prompt)||
                !rows.some(function(r){return r.text==='F'&&r.x>=1080&&r.x<=1170&&r.y>=490&&r.y<=590;}))
                return {status:'stopped',reason:'Exact headquarters entrance and F prompt required',entryAttempted:false};
            await api.keyPress('VK_F');await api.sleep(900);
            var after=await observe(),polls=0;
            while(polls++<20&&!(after.hud.dialogueReady||after.hud.choice||after.hud.groundControls)){
                api.checkStop();await api.sleep(500);after=await observe();
            }
            return {status:'stopped',step:name,entryAttempted:true,frameId:after.frameId,reason:'Entrance pressed once; inspect interior before movement',questComplete:false};
        });
        if(name==='actTwoRecover'){
            if((observation.ocr||[]).some(function(r){return r.text==='Statue of The Seven'&&r.y>830&&r.y<900||r.text==='Required Anemoculus'&&r.x>1400&&r.y>820&&r.y<880||r.text==='Worship Statue'&&r.x>1300&&r.y>170&&r.y<230;}))return api.runActTwoStatue(observation,observe);
            if(api.pauseProof(observation)||observation.hud.world)return api.finishActTwoDialogue(observation,observe,{status:'completed',step:name});
            if(observation.hud.dialogueReady||observation.hud.choice||observation.hud.tutorialStep==='wagnerChoice')return api.finishActTwoDialogue(observation,observe,await runDialogue(api,observe));
            await api.closeActTwoForge(observation);return api.finishActTwoDialogue(observation,observe,await runDialogue(api,observe));
        }
        if(name==='actTwoCookOpen')return api.runActTwoNavigationWithPause(observation,observe,async function(field){
            var rows=field.ocr||[];
            var lynn=hasObjective(field,'Give the Chicken-Mushroom Skewer to Lynn')&&field.map&&Math.hypot(field.map.x+1091.7,field.map.y-2170.4)<=3;
            var goodHunter=field.map&&field.map.map==='Teyvat'&&Math.hypot(field.map.x+886.7,field.map.y-2240.3)<=8&&field.hud.health&&field.hud.health.max===2313&&field.hud.health.current>=1967;
            if(!lynn&&!goodHunter)return {status:'stopped',reason:'Known Lynn quest or Good Hunter cooking location required'};
            await api.selectActTwoCook();await api.sleep(300);field=await observe();
            var selected=rows=field.ocr||[],label=rows.filter(function(r){return r.text==='Cook'&&r.x>=1200&&r.x<=1400&&r.y>=480&&r.y<=600;}),prompt=rows.filter(function(r){return r.text==='F'&&r.x>=1080&&r.x<=1170&&r.y>=480&&r.y<=600;});
            if(label.length!==1||prompt.length!==1||Math.abs(label[0].y+label[0].height/2-prompt[0].y-prompt[0].height/2)>=25)return {status:'stopped',reason:'Selected Cook prompt required'};
            await api.keyPress('VK_F');await api.sleep(800);var after=await observe();return {status:'stopped',reason:'Cooking opened once; inspect recipe screen',cookingOpened:true,frameId:after.frameId};
        });
        if(name==='actTwoMushroom')return api.runActTwoNavigationWithPause(observation,observe,async function(field){
            var rows=field.ocr||[],labels=rows.filter(function(r){return r.text==='Mushroom'&&r.x>=1150&&r.x<=1500&&r.y>=450&&r.y<=620;}),prompts=rows.filter(function(r){return r.text==='F'&&r.x>=1080&&r.x<=1170&&r.y>=450&&r.y<=620;});
            if(!hasObjective(field,'Give the Chicken-Mushroom Skewer to Lynn')||!field.map||Math.hypot(field.map.x+1092,field.map.y-2171)>30||labels.length!==1||prompts.length!==1||Math.abs(labels[0].y+labels[0].height/2-prompts[0].y-prompts[0].height/2)>=25)return {status:'stopped',reason:'Exact selected Mushroom at Lynn camp required',pickups:0};
            await api.keyPress('VK_F');await api.sleep(500);var after=await observe();return {status:'completed',pickups:1,frameId:after.frameId,reason:'One mushroom pickup attempted; verify obtained reward'};
        });
        if(name==='actTwoForgeClose'){await api.closeActTwoForge(observation);return api.finishActTwoDialogue(observation,observe,await runDialogue(api,observe));}
        if(name==='actTwoSkewer')return api.runActTwoSkewer(observation,observe);
        if(name==='actTwoHeal'||name==='actTwoHealClose')return api.runActTwoHeal(observation,observe);
        if(name==='actTwoQuestItems')return api.runActTwoQuestItems(observation,observe);
        if(name==='actTwoInformantCombat')return api.runActTwoInformantCombat(observation,observe);
        if(name==='actTwoOre')return api.runActTwoOre(observation,observe);
        if(name==='actTwoMapClose')return api.runActTwoMapClose(observation,observe);
        if(name==='actTwoClueCamera'||name==='actTwoWindmillLookUp')return api.runActTwoClueCamera(observation,observe);
        if(name==='actTwoVisual')return api.runActTwoVisual(observation,observe);
        if(name==='actTwoNativeRoute')return api.runActTwoNativeRoute(observation,observe);
        if(name==='actTwoTownRecovery'||name==='actTwoTownClimb'||name==='actTwoTownRail')return api.runActTwoTownRecovery(observation,observe);
        if(name==='actTwoKaeyaLevel')return api.runActTwoKaeyaLevel(observation,observe);
        if(name==='actTwoTeamUi'){
            var teamAction=await api.actTwoTeamUi();await api.sleep(650);var teamFrame=await observe();
            if(teamAction==='close')return api.finishActTwoDialogue(teamFrame,observe,{status:'completed',action:teamAction,step:name});
            return {status:'completed',step:name,action:teamAction,frameId:teamFrame.frameId,questComplete:false};
        }
        if(name==='actTwoHandbookClaim'||name==='actTwoHandbookNext'||name==='actTwoHandbookPrevious'||name==='actTwoHandbookMage'||name==='actTwoHandbookDomains'||name==='actTwoHandbookExperience'){
            var handbookTarget=await api.actTwoHandbookClaim(name==='actTwoHandbookExperience'?'experience':name==='actTwoHandbookDomains'?'domains':name==='actTwoHandbookMage'?'mage':name==='actTwoHandbookPrevious'?'previous':name==='actTwoHandbookNext');await api.sleep(650);var handbookFrame=await observe();
            var handbookResult={status:'completed',step:name,action:handbookTarget.action,objective:handbookTarget.objective,frameId:handbookFrame.frameId,claimAttempted:handbookTarget.action==='claim',questComplete:false};
            if(handbookTarget.action==='close'){
                for(var closePoll=0;closePoll<5&&!handbookFrame.hud.world&&!api.pauseProof(handbookFrame);closePoll++){api.checkStop();await api.sleep(250);handbookFrame=await observe();}
                return api.finishActTwoDialogue(observation,observe,handbookResult);
            }
            return handbookResult;
        }
        if(['actTwoHandbook','actTwoCharacter','actTwoWorldMap','actTwoJournalOpen','actTwoAccountMenu'].indexOf(name)>=0)return api.runActTwoMenu(observation,observe);
        if(name==='actTwoRankReward'){
            var rewardAction=await api.actTwoRankReward();await api.sleep(650);var rewardFrame=await observe();
            if(rewardAction==='close')return api.finishActTwoDialogue(observation,observe,await runDialogue(api,observe));
            return {status:'completed',step:name,action:rewardAction,frameId:rewardFrame.frameId,claimAttempted:rewardAction==='claim',questComplete:false};
        }
        if(name==='actTwoAmberTalk'||name==='actTwoLynnTalk'||name==='actTwoVileTalk'||name==='actTwoKaeyaReport'||name==='actTwoJackTalk'||name==='actTwoCyrusTalk'||name==='actTwoGuildTalk'||name==='actTwoWagnerTalk'||name==='actTwoKaeyaTalk'||name==='actTwoWaypoint') {
            var townNpc=name==='actTwoJackTalk'?'Jack':name==='actTwoAmberTalk'?'Amber':name==='actTwoLynnTalk'?'Lynn':name==='actTwoVileTalk'?'Vile':name==='actTwoKaeyaReport'?'Kaeya':name==='actTwoCyrusTalk'?'Cyrus':name==='actTwoWaypoint'?'Teleport Waypoint':name==='actTwoKaeyaTalk'?'Kaeya':name==='actTwoWagnerTalk'?'Wagner':'Katheryne',townObjective=name==='actTwoJackTalk'?'Talk to Jack':name==='actTwoAmberTalk'?'Talk to Amber':name==='actTwoLynnTalk'?'Speak to Lynn':name==='actTwoVileTalk'?'Talk to the informant':name==='actTwoKaeyaReport'?'Report to Kaeya':name==='actTwoCyrusTalk'?"Go to the Adventurers' Guild and listen to their report":(name==='actTwoKaeyaTalk'||name==='actTwoWaypoint')?'Talk to Kaeya':name==='actTwoWagnerTalk'?'Talk to Wagner the blacksmith':'Talk to Katheryne for more details';
            if(observation.hud.dialogueReady||observation.hud.choice||observation.hud.tutorialStep==='wagnerChoice')return api.finishActTwoDialogue(observation,observe,await runDialogue(api,observe));
            return api.runActTwoNavigationWithPause(observation,observe,async function(field){
                if(name==='actTwoLynnTalk'&&hasObjective(field,'Give the Chicken-Mushroom Skewer to Lynn')&&field.map&&Math.hypot(field.map.x+1091.7,field.map.y-2170.4)<1){
                    for(var face=0;face<4;face++){
                        if(!field.hud.world||!field.hud.health||field.hud.health.current!==1700||field.hud.climbing||(field.hud.enemyBars||[]).length||!field.map||!Number.isFinite(field.map.cameraAngle))return {status:'stopped',reason:'Lynn facing evidence changed'};
                        var diff=(field.map.cameraAngle-17+540)%360-180;if(Math.abs(diff)<=8)break;
                        await api.rotate(Math.max(-750,Math.min(750,Math.round(-8*diff))));await api.sleep(250);field=await observe();
                    }
                    if(!(field.ocr||[]).some(function(r){return r.text==='Lynn'&&r.x>=1150&&r.x<=1500&&r.y>=480&&r.y<=600;})){await api.forward(100);await api.sleep(300);field=await observe();}
                }
                var rows=field.ocr||[];
                if(name==='actTwoLynnTalk'&&typeof api.selectActTwoLynn==='function'&&await api.selectActTwoLynn()){await api.sleep(300);field=await observe();rows=field.ocr||[];}
                var lynnDelivery=name==='actTwoLynnTalk'&&(hasObjective(field,'Give the Chicken-Mushroom Skewer to Lynn')||rows.some(function(r){return r.text==='Give the Chicken-Mushroom Skewer'&&r.x>=65&&r.x<=100&&r.y>=230&&r.y<=310;})&&rows.some(function(r){return r.text==='to Lynn'&&r.x>=65&&r.x<=100&&r.y>=260&&r.y<=350;}));
                var ironObjective=name==='actTwoWagnerTalk'&&rows.some(function(r){return r.text==='Collect three Iron Chunks and give'&&r.x>=65&&r.x<=100&&r.y>=230&&r.y<=310;})&&
                    rows.some(function(r){return r.text==='them to Wagner'&&r.x>=65&&r.x<=100&&r.y>=260&&r.y<=345;});
                var rankReturn=name==='actTwoGuildTalk'&&typeof api.actTwoRankReturnReady==='function'&&api.actTwoRankReturnReady();
                var jackAvailable=name==='actTwoJackTalk'&&field.map&&field.map.map==='Teyvat'&&Math.hypot(field.map.x+846.2,field.map.y-2189.2)<8&&field.hud.groundControls&&!field.hud.climbing&&field.hud.health&&field.hud.health.current===2313&&field.hud.health.max===2313&&field.hud.enemyBarDiagnostic&&Array.isArray(field.hud.enemyBars)&&!field.hud.enemyBars.length&&!(field.hud.objectives||[]).length;
                var cyrusAvailable=name==='actTwoCyrusTalk'&&field.map&&field.map.map==='Teyvat'&&Math.hypot(field.map.x+838,field.map.y-2187)<8&&field.hud.groundControls&&!field.hud.climbing&&field.hud.health&&field.hud.health.current===2313&&field.hud.health.max===2313&&field.hud.enemyBarDiagnostic&&Array.isArray(field.hud.enemyBars)&&!field.hud.enemyBars.length&&!(field.hud.objectives||[]).length;
                if(!field.hud.interact||!(hasObjective(field,townObjective)||ironObjective||lynnDelivery||rankReturn||jackAvailable||cyrusAvailable)||
                    rows.filter(function(r){return r.text===townNpc&&r.x>=1150&&r.x<=1500&&r.y>=480&&r.y<=600;}).length!==1||
                    rows.filter(function(r){return r.text==='F'&&r.x>=1080&&r.x<=1170&&r.y>=480&&r.y<=600;}).length!==1)
                    return {status:'stopped',reason:'Exact '+townNpc+' interaction required'};
                if(name==='actTwoAmberTalk'||name==='actTwoLynnTalk'||name==='actTwoVileTalk'||name==='actTwoJackTalk'||name==='actTwoCyrusTalk'||name==='actTwoKaeyaReport'){
                    var label=rows.filter(function(r){return r.text===townNpc&&r.x>=1150&&r.x<=1500&&r.y>=480&&r.y<=600;})[0],prompt=rows.filter(function(r){return r.text==='F'&&r.x>=1080&&r.x<=1170&&r.y>=480&&r.y<=600;})[0];
                    if(!(Math.abs((label.y+label.height/2)-(prompt.y+prompt.height/2))<25))return {status:'stopped',reason:townNpc+' interaction must be selected'};
                }
                await api.keyPress('VK_F');await api.sleep(900);
                return runDialogue(api,observe);
            });
        }
        if(name==='actTwoDaytime')return api.runActTwoDaytime(observation,observe);
        if(name==='actTwoMap') {
            api.checkStop();api.requireInputReady();var mapAction=await api.actTwoMap();await api.sleep(600);
            var mapAfter=await observe(),pause=false,polls=0;
            if(mapAction==='teleport'){
                var deadline=api.now()+25000;
                while(api.now()<deadline&&polls++<24){
                    api.checkStop();
                    if(mapAfter.hud.world&&await api.pauseWorldInventory()){
                        await api.sleep(600);mapAfter=await observe();pause=!!api.pauseProof(mapAfter);break;
                    }
                    await api.sleep(350);mapAfter=await observe();
                }
            }
            return {status:'stopped',step:name,action:mapAction,frameId:mapAfter.frameId,pauseVerified:pause,polls:polls,reason:'Map action attempted once; verify destination',questComplete:false};
        }
        if(name==='actTwoJournal') {
            api.checkStop();api.requireInputReady();await api.actTwoJournal();await api.sleep(500);
            var journalAfter=await observe();
            if(journalAfter.hud.world)return api.finishActTwoDialogue(observation,observe,{status:'completed',step:name,questComplete:false});
            return {status:'stopped',step:name,frameId:journalAfter.frameId,reason:'Authorized quest journal action completed; inspect selected objective',questComplete:false};
        }
        if(name==='accountSavedUi') {
            api.checkStop();api.requireInputReady();await api.accountSavedUi();await api.sleep(600);
            var savedAccountScreen=await observe();
            return {status:'stopped',step:name,frameId:savedAccountScreen.frameId,reason:'Saved-account UI action sent once; verify next screen',accountVerified:false};
        }
        if(name==='accountSwitchTitle'||name==='accountSwitchConfirm') {
            api.checkStop();api.requireInputReady();
            if(name==='accountSwitchTitle')api.accountSwitchTitle();else await api.accountSwitchConfirm();
            await api.sleep(600);
            var accountScreen=await observe();
            return {status:'stopped',step:name,frameId:accountScreen.frameId,reason:'Account-switch control clicked once; inspect next screen',accountVerified:false};
        }
        if(name==='accountSwitchClose') {
            api.checkStop();api.requireInputReady();await api.accountSwitchClose();
            await api.sleep(500);
            return {status:'stopped',step:name,reason:'Normal game-close chord sent once for account switching; verify process and title before continuing',accountVerified:false};
        }
        if(name==='reconnectGame') {
            api.checkStop();
            if(!actOneReconnectTarget(observation,api.now()))return {status:'stopped',step:name,clicks:0,reason:'Exact connection-timeout dialog not verified'};
            api.requireInputReady();api.reconnectGame();
            await api.sleep(800);api.checkStop();
            var next=await observe();
            return {status:'stopped',step:name,clicks:1,frameId:next.frameId,
                reason:'Connection-timeout confirmation sent once; inspect fresh state before further input',reconnectionVerified:false};
        }
        if(name==='lisaClimb')return api.runLisaClimb(observation,observe);
        if(name==='lisaTravelAmber')return api.runLisaTravelAmber(observation,observe);
        if(name==='lisaTravelTraveler')return api.runLisaTravelAmber(observation,observe);
        if(name==='lisaCloseThreat')return api.runLisaCloseThreat(observation,observe);
        if(name==='lisaLookDown')return api.runLisaCloseThreat(observation,observe);
        if(name==='lisaGlide')return api.runLisaGlide(observation,observe);
        if(name==='lisaVisualMove')return api.runLisaVisualMove(observation,observe);
        if(name==='lisaTeamClose')return api.runLisaTeamClose(observation,observe);
        if(name==='lisaKaeyaLevel')return api.runLisaKaeyaLevel(observation,observe);
        if(name==='lisaTeamReview')return api.runLisaTeamReview(observation,observe);
        if(name==='lisaWeaponSwitch')return api.runLisaWeaponSwitch(observation,observe);
        if(name==='lisaWeaponChoice')return api.runLisaWeaponChoice(observation,observe);
        if(name==='lisaTeamInspect')return api.runLisaTeamInspect(observation,observe);
        if(name==='lisaWindriseTeleport'||name==='actTwoGateTeleport'||name==='actTwoCityTeleport'||name==='actTwoWindriseTeleport'||name==='actTwoLionTeleport'||name==='actTwoNorthTeleport')return api.runLisaWindriseTeleport(observation,observe);
        if(name==='lisaTempleMapInspect')return api.runLisaTempleMapInspect(observation,observe);
        if(name==='lisaTempleTeleport')return api.runLisaTempleTeleport(observation,observe);
        if(name==='lisaStatueRecovery')return api.runLisaStatueRecovery(observation,observe);
        if(name==='lionFieldCombat'||name==='lionFieldProbe')return api.runLionFieldCombat(observation,observe);
        if(name==='windriseReveal')return api.runWindriseReveal(observation,observe);
        if(name==='lionFalconWaypoint'||name==='lisaWolfWaypoint') {
            if(typeof api.lionFalconWaypointReady!=='function'||typeof api.teleportLionFalconWaypoint!=='function'||!api.lionFalconWaypointReady(observation))
                return {status:'stopped',step:name,reason:'Fresh safe Lisa objective required for unlocked waypoint teleport',frameId:observation.frameId};
            var teleportBegan=api.now();await api.teleportLionFalconWaypoint();var teleportMs=api.now()-teleportBegan;
            var arrival=await observe(),polls=0;
            for(;polls<12&&!arrival.hud.world;polls++){api.checkStop();await api.sleep(500);arrival=await observe();}
            var destinationVerified=name==='lionFalconWaypoint'||arrival.map&&arrival.map.map==='Teyvat'&&
                Math.hypot(arrival.map.x+1642.421,arrival.map.y-2163.664)<=20;
            return {status:arrival.hud.world&&destinationVerified?'completed':'stopped',step:name,
                reason:'One unlocked '+(name==='lisaWolfWaypoint'?'Wolf temple':'Falcon waypoint')+' teleport attempted; inspect arrival',
                destinationVerified:!!destinationVerified,nativeTeleportMs:teleportMs,polls:polls,frameId:arrival.frameId};
        }
        if(name==='lionLocalPause') return api.runLionLocalPause(observation,observe);
        if(name==='lionVisualMove') return api.runLionVisualMove(observation,observe);
        if(name==='lionStart') return runLionEntryStart(name,observation,api,observe,false);
        if(name==='lionPartyStart') return runLionEntryStart(name,observation,api,observe,true);
        if(name==='wolfCharactersOpen') {
            var characterClose=api.wolfCharactersFoodCloseReady(observation),characterResume=!characterClose&&typeof api.wolfCharactersPauseContinueReady==='function'&&api.wolfCharactersPauseContinueReady(observation);
            if(!characterClose&&!characterResume)
                return {status:'stopped',step:name,reason:'Fresh Wolf food grid required; no character-menu input sent',inventoryCloseAttempts:0,characterMenuAttempts:0,characterMenuVerified:false,levelUpAttempts:0};
            if(characterClose)await api.wolfCharactersFoodClose();else await api.wolfCharactersPauseContinue();
            await api.sleep(450);
            var characterActive=await observe(),characterPolls=0;
            while(!api.wolfCharactersOpenReady(characterActive)&&characterPolls<3) {
                api.checkStop();await api.sleep(200);characterActive=await observe();characterPolls++;
            }
            if(!api.wolfCharactersOpenReady(characterActive))
                return {status:'stopped',step:name,reason:'Fresh living Wolf HUD unavailable after bounded read-only transition polls',inventoryCloseAttempts:characterClose?1:0,pauseResumeAttempts:characterResume?1:0,readOnlyPolls:characterPolls,characterMenuAttempts:0,characterMenuVerified:false,levelUpAttempts:0,frameId:characterActive&&characterActive.frameId};
            await api.wolfCharactersOpen();await api.sleep(600);
            var characterMenu=await observe(),characterVerified=api.wolfCharactersMenuVisible(characterMenu);
            for(var characterMenuPoll=0;!characterVerified&&characterMenuPoll<3;characterMenuPoll++) {
                api.checkStop();await api.sleep(200);characterMenu=await observe();characterVerified=api.wolfCharactersMenuVisible(characterMenu);
            }
            return {status:characterVerified?'completed':'stopped',step:name,reason:characterVerified?'English character menu verified; no level-up attempted':'One character-menu input sent; menu unverified',
                inventoryCloseAttempts:characterClose?1:0,pauseResumeAttempts:characterResume?1:0,readOnlyPolls:characterPolls,characterMenuAttempts:1,characterMenuVerified:!!characterVerified,levelUpAttempts:0,frameId:characterMenu&&characterMenu.frameId};
        }
        if(name==='wolfObserveBurst'||name==='wolfPlatformObserve') {
            var burst=[],burstStart=api.now(),burstSession=observation&&observation.session;
            var burstCount=name==='wolfPlatformObserve'?16:4;
            function validBurstFrame(o) {
                return !!(typeof burstSession==='string'&&burstSession.length>0&&o&&o.session===burstSession&&Number.isInteger(o.frameId)&&Number.isFinite(o.timestamp)&&
                    api.now()>=o.timestamp&&api.now()-o.timestamp<=1000);
            }
            if(!validBurstFrame(observation)) return {status:'stopped',step:name,reason:'Fresh same-session initial observation required',observationCount:0};
            burst.push({frameId:observation.frameId,elapsedMs:0,timings:observation.timings||null,surface:observation.hud&&observation.hud.wolfSpikeSurface||null});
            for(var bi=1;bi<burstCount;bi++) {
                if(name==='wolfPlatformObserve')await api.sleep(150);
                api.checkStop();var t0=api.now(),bo=await observe();api.checkStop();
                if(!validBurstFrame(bo)||burst.some(function(x){return x.frameId===bo.frameId;}))
                    return {status:'stopped',step:name,reason:'Fresh distinct same-session observation required',observationCount:burst.length,frameIds:burst.map(function(x){return x.frameId;})};
                burst.push({frameId:bo.frameId,elapsedMs:api.now()-t0,timings:bo.timings||null,surface:bo.hud&&bo.hud.wolfSpikeSurface||null});
            }
            var elapsed=burst.slice(1).map(function(x){return x.elapsedMs;}),sum=elapsed.reduce(function(a,b){return a+b;},0);
            return {status:'completed',step:name,frameId:burst[burst.length-1].frameId,observationCount:burst.length,frameIds:burst.map(function(x){return x.frameId;}),
                totalElapsedMs:api.now()-burstStart,perObservationMs:elapsed,minObservationMs:Math.min.apply(null,elapsed),
                maxObservationMs:Math.max.apply(null,elapsed),meanObservationMs:sum/elapsed.length,
                observationTimings:burst.slice(1).map(function(x){return x.timings;})};
        }
        if(name==='wolfLootInteract') {
            var lootFrame=observation,lootContinue=0,picked=[];
            if(api.wolfLootContinueReady(lootFrame)) {
                api.checkStop();api.wolfContinue();lootContinue=1;await api.sleep(450);lootFrame=await observe();
                for(var lootPoll=0;lootPoll<2&&!api.wolfLootReady(lootFrame);lootPoll++) {
                    api.checkStop();await api.sleep(200);lootFrame=await observe();
                }
            }
            if(!api.wolfLootReady(lootFrame)) return {status:'stopped',step:name,reason:'Fresh selected known chest loot not verified; no F sent',
                continueAttempts:lootContinue,lootAttempts:0,frameId:lootFrame&&lootFrame.frameId};
            var lootBaseline={current:lootFrame.hud.health.current,max:lootFrame.hud.health.max};
            for(var lootIndex=0;lootIndex<4&&api.wolfLootReady(lootFrame,lootBaseline);lootIndex++) {
                api.checkStop();picked.push(await api.wolfLootInteract(lootBaseline));await api.sleep(250);lootFrame=await observe();
            }
            return {status:'completed',step:name,reason:'Bounded known chest loot interactions observed; inspect fresh result',
                continueAttempts:lootContinue,lootAttempts:picked.length,items:picked,frameId:lootFrame&&lootFrame.frameId};
        }
        if(name==='wolfChestInteract') {
            var chestFrame=observation,continueCount=0;
            if(api.wolfChestContinueReady(chestFrame)) {
                api.checkStop();api.wolfContinue();continueCount=1;await api.sleep(450);chestFrame=await observe();
                for(var chestPoll=0;chestPoll<3&&!api.wolfChestReady(chestFrame);chestPoll++) {
                    api.checkStop();await api.sleep(250);chestFrame=await observe();
                }
            }
            if(!api.wolfChestReady(chestFrame)) return {status:'stopped',step:name,reason:'Fresh healthy Common Chest prompt not verified; no F sent',
                continueAttempts:continueCount,chestAttempts:0,frameId:chestFrame&&chestFrame.frameId};
            api.checkStop();await api.wolfChestInteract();await api.sleep(800);var chestAfter=await observe();
            return {status:'completed',step:name,reason:'One verified Common Chest interaction; inspect fresh loot or encounter',
                continueAttempts:continueCount,chestAttempts:1,frameId:chestAfter&&chestAfter.frameId};
        }
        if(name==='windowedGame') {
            if(!actOneWindowedGameReady(observation,api.now()))
                return {status:'stopped',step:name,reason:'Fresh safe world HUD with numeric health >= 60% required',frameId:observation&&observation.frameId||null,clicks:0};
            var change;
            try {api.checkStop();api.requireInputReady();change=await api.windowedGame();}
            catch(e) {return {status:'stopped',step:name,reason:String(e&&e.message||e),frameId:observation.frameId||null,clicks:0};}
            if(change&&change.action==='noop') {
                var noopInfo=change.info,noopDecision=actOneWindowModeDecision(noopInfo,noopInfo&&noopInfo.windowsSessionId);
                if(noopDecision!=='noop') return {status:'stopped',step:name,reason:'Already-windowed verification failed',frameId:observation.frameId||null,clicks:0,windowInfo:noopInfo};
                return {status:'completed',step:name,reason:'Game is already windowed; no input sent',frameId:observation.frameId||null,clicks:0,
                    clientWidth:noopInfo.gameWindow.clientWidth,clientHeight:noopInfo.gameWindow.clientHeight,fillsDesktop:noopInfo.fillsDesktop,windowInfo:noopInfo};
            }
            await api.sleep(700);var next=await observe(),info;
            try {info=api.windowInfo();}
            catch(e) {return {status:'stopped',step:name,reason:String(e&&e.message||e),frameId:next&&next.frameId||null,clicks:1,windowInfo:null};}
            var postSafe=actOneWindowedGameReady(next,api.now()),postDecision=actOneWindowModeDecision(info,info&&info.windowsSessionId);
            var verified=postDecision==='noop'&&postSafe;
            return {status:verified?'completed':'stopped',step:name,
                reason:verified?'Windowed 1920x1080 game client verified on 2560x1440 desktop':'Windowed geometry or safe world HUD not verified after Alt+Enter',
                frameId:next&&next.frameId||null,clicks:1,holdMs:change&&change.holdMs||null,
                clientWidth:info&&info.gameWindow&&info.gameWindow.clientWidth||null,
                clientHeight:info&&info.gameWindow&&info.gameWindow.clientHeight||null,
                desktopWidth:info&&info.desktop&&info.desktop.virtualBounds&&info.desktop.virtualBounds.width||null,
                desktopHeight:info&&info.desktop&&info.desktop.virtualBounds&&info.desktop.virtualBounds.height||null,
                fillsDesktop:info&&info.fillsDesktop,windowInfo:info};
        }
        if(name==='windowInfo') {
            try {api.checkStop();api.requireInputReady();return {status:'completed',step:name,reason:'Read-only game window diagnostics',info:api.windowInfo(),frameId:observation&&observation.frameId||null};}
            catch(e) {return {status:'stopped',step:name,reason:String(e&&e.message||e),frameId:observation&&observation.frameId||null};}
        }
        if(name==='enterGame') {
            var current=observation,target=null,preflightObservations=0,preflightDeadline=api.now()+5000;
            while(true) {
                api.checkStop();preflightObservations++;
                if(actOneEnterGameAuthPrompt(current&&current.ocr))
                    return {status:'stopped',step:name,reason:'Authentication or verification prompt appeared; inspect manually',clicks:0,
                        preflightObservations:preflightObservations,frameId:current&&current.frameId||null,preState:'authPrompt'};
                if(current&&current.hud&&current.hud.world===true)
                    return {status:'stopped',step:name,reason:'World HUD appeared before title entry; inspect current session',clicks:0,
                        preflightObservations:preflightObservations,frameId:current.frameId||null,preState:'worldHud'};
                if(!actOneEnterGameTitleFrame(current,api.now()))
                    return {status:'stopped',step:name,reason:'Unknown or unsafe screen before title entry',clicks:0,
                        preflightObservations:preflightObservations,frameId:current&&current.frameId||null,preState:'unknownScreen'};
                target=actOneEnterGameTarget(current,api.now());
                if(target) break;
                if(preflightObservations>=10||api.now()>=preflightDeadline)
                    return {status:'stopped',step:name,reason:'Exact title entry pair did not appear within the bounded wait',clicks:0,
                        preflightObservations:preflightObservations,frameId:current.frameId||null,preState:'titlePromptPulse'};
                await api.sleep(Math.min(300,preflightDeadline-api.now()));
                current=await observe();
            }
            var inputStarted=api.now(),clickProof;
            try {
                api.checkStop();api.requireInputReady();
                clickProof=api.startGame();
            } catch(e) {
                return {status:'stopped',step:name,reason:String(e&&e.message||e),clicks:0,preflightObservations:preflightObservations,frameId:current.frameId};
            }
            return await pollEntryWorld(current,api,observe,{step:name,began:inputStarted,deadline:api.now()+30000,titleClicked:true,
                titleProof:clickProof,preflightObservations:preflightObservations,autoDoor:true});
        }
        if(name==='enterWorld') {
            var doorTarget=actOneEnterWorldTarget(observation,api.now());
            if(!doorTarget) return {status:'stopped',step:name,reason:'Fresh exact bottom door Click to Begin prompt required',clicks:0,
                phaseClicks:{title:0,door:0},preState:actOneEnterGameAuthPrompt(observation&&observation.ocr)?'authPrompt':'unknownScreen',frameId:observation&&observation.frameId||null};
            var doorStart=api.now(),doorProof;
            try {api.checkStop();api.requireInputReady();doorProof=api.startGame('enterWorld');}
            catch(e) {return {status:'stopped',step:name,reason:String(e&&e.message||e),clicks:0,phaseClicks:{title:0,door:0},frameId:observation.frameId||null};}
            return await pollEntryWorld(observation,api,observe,{step:name,began:doorStart,deadline:api.now()+30000,doorClicked:true,doorProof:doorProof});
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
        if(name==='wolfPause') {
            await api.wolfDomainAction();
            var next=observation,paused=false,polls=0;
            // Escape is a toggle: wait for the menu rather than pressing it again.
            for(var pausePoll=0;pausePoll<3;pausePoll++) {
                await api.sleep(pausePoll===0?600:250);next=await observe();polls++;
                var rows=next.ocr||[];
                paused=rows.some(function(r){return r.text&&r.text.trim()==='Continue Challenge';})&&
                    rows.some(function(r){return r.text&&r.text.trim()==='Leave Domain?';});
                if(paused)break;
            }
            return {status:paused?'completed':'stopped',step:name,reason:paused?'Wolf pause menu verified':'Wolf pause menu not verified; inspect fresh scene',pauseVerified:paused,polls:polls,frameId:next.frameId};
        }
        if(name==='wolfReviveKaeyaPrompt') {
            var reviveSession=observation&&observation.session,continueAttempts=0,selectionAttempts=0,current=observation;
            function reviveFresh(o,previous) {
                return !!(typeof reviveSession==='string'&&reviveSession.length>0&&o&&o.session===reviveSession&&Number.isInteger(o.frameId)&&
                    (!previous||o.frameId>previous.frameId)&&Number.isFinite(o.timestamp)&&api.now()>=o.timestamp&&api.now()-o.timestamp<=1000);
            }
            function reviveResult(promptRequested,reason,frameId) {
                return {status:'stopped',step:name,reason:reason,continueAttempts:continueAttempts,selectionAttempts:selectionAttempts,
                    promptRequested:promptRequested,questComplete:false,frameId:frameId||null};
            }
            if(!reviveFresh(current)||typeof api.wolfRevivePromptContinueReady!=='function'||!api.wolfRevivePromptContinueReady(current))
                return reviveResult(false,'Fresh canonical Wolf pause, same-session entry proof, and unused revival permit required',current&&current.frameId);
            api.checkStop();continueAttempts=1;api.wolfRevivePromptContinue();
            await api.sleep(450);api.checkStop();current=await observe();api.checkStop();
            if(!reviveFresh(current,observation)||typeof api.wolfRevivePromptSelectReady!=='function'||!api.wolfRevivePromptSelectReady(current))
                return reviveResult(false,'Continue sent once; fresh unchanged living Amber ground HUD with party proof unavailable',current&&current.frameId);
            api.checkStop();selectionAttempts=1;await api.wolfRevivePromptSelect(current);
            await api.sleep(350);api.checkStop();var afterSelect=await observe();api.checkStop();
            if(!reviveFresh(afterSelect,current))
                return reviveResult(true,'One Kaeya selection sent; fresh post-selection capture unavailable, revive prompt unverified',afterSelect&&afterSelect.frameId);
            return reviveResult(true,'Continue and one Kaeya selection sent; inspect the exact revival prompt before any further action',afterSelect.frameId);
        }
        if(name==='wolfInventoryRecover') {
            if(!api.wolfInventoryContinueReady(observation))
                return {status:'stopped',step:name,reason:'Fresh exact Wolf pause menu unavailable',continueAttempts:0,inventoryAttempts:0,frameId:observation&&observation.frameId};
            await api.wolfInventoryContinue();
            // The live pause-menu fade ignored B at 150 ms; allow the transition
            // to settle without putting a full OCR capture in the active gap.
            await api.sleep(450);
            await api.wolfInventoryOpen();
            await api.sleep(450);
            var inventory=await observe(),ready=api.wolfFoodInventoryReady(inventory);
            for(var fadePoll=0;fadePoll<4&&!ready;fadePoll++) {
                api.checkStop();await api.sleep(250);inventory=await observe();ready=api.wolfFoodInventoryReady(inventory);
            }
            return {status:ready?'completed':'stopped',step:name,reason:ready?'Food inventory screen verified; healing not attempted':'Food inventory screen not verified after one open attempt',continueAttempts:1,inventoryAttempts:1,
                inventoryVerified:!!ready,healingAttempted:false,readOnlyPolls:fadePoll+1,frameId:inventory&&inventory.frameId};
        }
        if(name==='wolfSelectKaeyaFood') {
            if(!api.wolfKaeyaFoodReady(observation))
                return {status:'stopped',step:name,reason:'Fresh known Sweet Madame and Traveler food modal unavailable',selectionAttempts:0,selectionVerified:false,foodConsumed:false,frameId:observation&&observation.frameId};
            await api.wolfSelectKaeyaFood();
            await api.sleep(300);
            var selected=await observe(),verified=!!api.wolfKaeyaFoodSelected(selected);
            return {status:verified?'completed':'stopped',step:name,reason:verified?'Kaeya selection verified; no food used':'Kaeya selection not verified after one click',selectionAttempts:1,selectionVerified:verified,foodConsumed:false,frameId:selected&&selected.frameId};
        }
        if(name==='wolfFeedKaeya') {
            if(!api.wolfFeedKaeyaReady(observation))
                return {status:'stopped',step:name,reason:'Fresh exact Kaeya Sweet Madame modal and quantity-one crop unavailable',foodUseAttempts:0,foodUseAttempted:false,healingVerified:false,frameId:observation&&observation.frameId};
            await api.wolfFeedKaeya();await api.sleep(500);
            var afterFeed=await observe();
            return {status:'stopped',step:name,reason:'One food-use attempt recorded; healing must be verified from active HUD',foodUseAttempts:1,foodUseAttempted:true,healingVerified:false,frameId:afterFeed&&afterFeed.frameId};
        }
        if(['wolfForward','wolfForwardFine','wolfLeft','wolfRight','wolfLookLeft','wolfLookRight','wolfLookDown','wolfLookUp'].indexOf(name)>=0) {await api.wolfDomainAction();await api.sleep(180);var next=await observe();return {status:'completed',step:name,reason:'Bounded Wolf domain action; inspect fresh scene',frameId:next.frameId};}
        if(name==='wolfAdvance') {
            var current=observation,moves=0,inputMs=0,baseline=null,lastFrame=current&&current.frameId;
            function state(o) {
                if(!o||!o.hud||!api.wolfDomainHud(o)) return {ok:false,reason:'Fresh valid Wolf trial HUD unavailable'};
                var h=o.hud,hp=h.health;
                if(!hp||!Number.isFinite(hp.current)||!Number.isFinite(hp.max)||hp.max<=0||hp.current<0||hp.current>hp.max) return {ok:false,reason:'Wolf health unavailable or nonnumeric'};
                var healthFloor=typeof api.wolfRecoveryTravelReady==='function'&&api.wolfRecoveryTravelReady(o)?0.3:0.6;
                if(hp.current/hp.max<healthFloor) return {ok:false,reason:'Wolf health below '+Math.round(healthFloor*100)+'%'};
                if(baseline&&baseline.current-hp.current>baseline.max*0.05) return {ok:false,reason:'Wolf health dropped more than 5%'};
                if(h.interact) return {ok:false,reason:'Wolf interaction available'};
                if(h.enemyBars&&h.enemyBars.length) return {ok:false,reason:'Wolf enemy bars detected'};
                if(h.dialogueReady||h.choice) return {ok:false,reason:'Wolf dialogue or choice detected'};
                if(h.tutorialStep||h.objectiveChanged||h.auto||h.unknownHud) return {ok:false,reason:'Wolf tutorial or unknown HUD state'};
                if(h.groundControls!==true||h.climbing) return {ok:false,reason:'Wolf character is not confirmed grounded'};
                return {ok:true,hp:hp};
            }
            // This bounded walking step has no wall or position-change detector; a cap never proves arrival.
            function result(status,reason){return {status:status,step:name,reason:reason,moves:moves,inputMs:inputMs,frameId:lastFrame,capReached:moves===4,limitation:'No wall or geometry detection; inspect the fresh scene before another action'};}
            for(var wi=0;wi<4;wi++) {
                api.checkStop();var check=state(current);if(!check.ok)return result('stopped',check.reason);
                if(!baseline)baseline={current:check.hp.current,max:check.hp.max};
                var started=api.now();await api.wolfDomainAction();inputMs+=Math.max(0,api.now()-started);moves++;
                await api.sleep(180);current=await observe();lastFrame=current&&current.frameId;
            }
            var finalCheck=state(current);if(!finalCheck.ok)return result('stopped',finalCheck.reason);
            return result('completed','Four bounded forward moves completed; target not verified');
        }
        if(name==='wolfApproachEnemy') {
            var approachStart=api.now(),continueMs=0,inputMs=0;
            if(typeof api.wolfApproachEnemyReady!=='function'||!api.wolfApproachEnemyReady(observation))
                return {status:'stopped',step:name,reason:'Fresh canonical Wolf pause and unused Hydro tutorial checkpoint required',continueAttempts:0,moveAttempts:0,
                    approachVerified:false,questComplete:false,frameId:observation&&observation.frameId};
            var approachContinueStart=api.now();await api.wolfApproachEnemyContinue();continueMs=api.now()-approachContinueStart;
            api.checkStop();await api.sleep(450);api.checkStop();var approachCurrent=await observe();api.checkStop();
            var target=typeof api.wolfApproachEnemyTarget==='function'?api.wolfApproachEnemyTarget(approachCurrent):null;
            if(!target) return {status:'stopped',step:name,reason:'Continue sent once; fresh safe Trial Kaeya and one anchored enemy bar not verified',
                continueAttempts:1,moveAttempts:0,approachVerified:false,questComplete:false,polls:1,
                phaseTiming:{continueMs:continueMs,totalMs:api.now()-approachStart},frameId:approachCurrent&&approachCurrent.frameId};
            api.checkStop();var approachMoveStart=api.now();await api.wolfApproachEnemyMove(approachCurrent);inputMs=api.now()-approachMoveStart;
            api.checkStop();await api.sleep(180);api.checkStop();var approachAfter=await observe();api.checkStop();
            return {status:'stopped',step:name,reason:'One bounded forward approach attempted; enemy distance and arrival remain unverified',
                continueAttempts:1,moveAttempts:1,inputMs:inputMs,moveMs:500,approachVerified:false,questComplete:false,polls:2,
                phaseTiming:{continueMs:continueMs,moveMs:inputMs,totalMs:api.now()-approachStart},frameId:approachAfter&&approachAfter.frameId};
        }
        if(name==='wolfKaeyaSkill') {
            var initialHp=observation&&observation.hud&&observation.hud.health;
            if(!observation||!api.wolfDomainHud(observation)||!initialHp||!Number.isFinite(initialHp.current)||!Number.isFinite(initialHp.max)||initialHp.max<=0||initialHp.current/initialHp.max<0.6)
                return {status:'stopped',step:name,reason:'Fresh healthy Wolf trial HUD unavailable before Kaeya selection',skillAttempts:0,frameId:observation&&observation.frameId};
            await api.wolfKaeyaSkillSelect();
            await api.sleep(500);
            var selected=await observe();
            if(!api.wolfKaeyaSkillReady(selected))
                return {status:'stopped',step:name,reason:'Fresh Trial Kaeya HUD with captured max HP 1427 not verified after selection',skillAttempts:0,characterSelectionAttempts:1,frameId:selected&&selected.frameId};
            await api.wolfKaeyaSkillCast();
            await api.sleep(500);
            var afterSkill=await observe();
            return {status:'completed',step:name,reason:'One bounded Kaeya skill input attempted; target effect unverified',characterSelectionAttempts:1,skillAttempts:1,targetEffectVerified:false,frameId:afterSkill&&afterSkill.frameId};
        }
        if(name==='wolfDefensiveCryo') {
            if(!api.wolfDefensiveCryoReady(observation))
                return {status:'stopped',step:name,reason:'Fresh living Kaeya Trial HUD unavailable for defensive Cryo',skillAttempts:0,targetEffectVerified:false,frameId:observation&&observation.frameId};
            await api.wolfDefensiveCryo();await api.sleep(500);
            var defensiveAfter=await observe();
            return {status:'stopped',step:name,reason:'One defensive Cryo attempt observed; target effect unverified',skillAttempts:1,targetEffectVerified:false,frameId:defensiveAfter&&defensiveAfter.frameId};
        }
        if(name==='wolfSpikeCrossFirst')return api.runWolfSpike(observation,observe);
        if(name==='wolfSpikeCrossSecond')return api.runWolfSecondSpike(observation,observe);
        if(name==='wolfWitnessAction')return api.runWolfWitnessAction(observation,observe);
        if(name==='wolfCryoWait') {
            var cryoStart=api.now(),cryoSession=observation&&observation.session,continueAttempts=0,skillAttempts=0,pauseAttempts=0,
                inputMs=0,waitMs=0,captureCount=0,captureMs=0,cooldownWaitMs=0,cooldownSource=null,capturedRemainingSeconds=null,cooldownStartedAt=null,cooldownFinishedAt=null,
                reason='Bounded Cryo attempt observed; target effect remains unverified',
                pauseVerified=false,current=observation,lastFrame=observation&&observation.frameId;
            function addCapture(o){captureCount++;captureMs+=Math.max(0,Number(o&&o.timings&&o.timings.captureMs)||0);}
            function validFrame(o,previous){
                return !!(typeof cryoSession==='string'&&cryoSession.length>0&&o&&o.session===cryoSession&&Number.isInteger(o.frameId)&&
                    (!previous||o.frameId>previous.frameId)&&Number.isFinite(o.timestamp)&&api.now()>=o.timestamp&&api.now()-o.timestamp<=1000);
            }
            function result(){return {status:'stopped',step:name,reason:reason,continueAttempts:continueAttempts,skillAttempted:skillAttempts===1,
                skillAttempts:skillAttempts,pauseAttempts:pauseAttempts,inputMs:inputMs,waitMs:waitMs,cooldownSource:cooldownSource,
                capturedRemainingSeconds:capturedRemainingSeconds,cooldownWaitMs:cooldownWaitMs,
                cooldownElapsedMs:cooldownStartedAt===null?0:Math.max(0,(cooldownFinishedAt===null?api.now():cooldownFinishedAt)-cooldownStartedAt),captureCount:captureCount,captureMs:captureMs,
                targetEffectVerified:false,questComplete:false,pauseVerified:pauseVerified,elapsedMs:Math.max(0,api.now()-cryoStart),frameId:lastFrame||null};}
            async function pauseSafeActive(){
                if(cooldownStartedAt!==null&&cooldownFinishedAt===null)cooldownFinishedAt=api.now();
                if(typeof api.wolfCryoWaitPauseReady!=='function'||!api.wolfCryoWaitPauseReady(current))return false;
                api.checkStop();var t=api.now();pauseAttempts=1;await api.wolfCryoWaitEscape();inputMs+=Math.max(0,api.now()-t);
                api.checkStop();await api.sleep(600);waitMs+=600;api.checkStop();var paused=await observe();addCapture(paused);
                if(validFrame(paused,current)&&api.wolfCryoWaitPauseVerified(paused)){pauseVerified=true;lastFrame=paused.frameId;return true;}
                return false;
            }
            try {
                if(!validFrame(observation)||typeof api.wolfCryoWaitContinueReady!=='function'||!api.wolfCryoWaitContinueReady(observation)){
                    reason='Fresh exact same-session Wolf pause and entry proof required';return result();
                }
                api.checkStop();var t=api.now();api.wolfCryoWaitContinue();continueAttempts=1;inputMs+=Math.max(0,api.now()-t);
                api.checkStop();await api.sleep(450);waitMs+=450;api.checkStop();current=await observe();addCapture(current);
                if(!validFrame(current,observation)){reason='Fresh same-session active observation unavailable after one Continue';return result();}
                lastFrame=current.frameId;
                var resumeDeadline=api.now()+3000,retries=0;
                while(!api.wolfCryoWaitActiveReady(current)&&retries<12&&api.now()<resumeDeadline){
                    api.checkStop();var gap=Math.min(250,resumeDeadline-api.now());if(gap<=0)break;await api.sleep(gap);waitMs+=gap;api.checkStop();
                    var retry=await observe();addCapture(retry);if(!validFrame(retry,current)){reason='Stale, duplicate, or wrong-session HUD during bounded resume check';return result();}
                    current=retry;lastFrame=current.frameId;retries++;
                }
                if(!api.wolfCryoWaitActiveReady(current)){
                    reason='Strict safe grounded Trial Kaeya HUD unavailable within three seconds after Continue';await pauseSafeActive();return result();
                }
                var plan=typeof api.wolfCryoWaitCooldownPlan==='function'?api.wolfCryoWaitCooldownPlan(current):null;
                if(!plan||!Number.isInteger(plan.waitMs)||plan.waitMs<1||plan.waitMs>6500){
                    reason='Fresh verified resume state unavailable for bounded cooldown wait';await pauseSafeActive();return result();
                }
                cooldownSource=plan.source;capturedRemainingSeconds=plan.capturedRemainingSeconds;cooldownWaitMs=plan.waitMs;
                cooldownStartedAt=api.now();var cooldownDeadline=cooldownStartedAt+cooldownWaitMs;
                while(api.now()<cooldownDeadline&&api.now()-cryoStart<20000){
                    api.checkStop();var hold=Math.min(500,cooldownDeadline-api.now());await api.sleep(hold);waitMs+=hold;api.checkStop();
                    var fresh=await observe();addCapture(fresh);if(!validFrame(fresh,current)){reason='Stale, duplicate, or wrong-session HUD during local cooldown wait';return result();}
                    current=fresh;lastFrame=current.frameId;
                    if(!api.wolfCryoWaitActiveReady(current)){reason='Strict safe HUD lost or health fell more than five percent during cooldown';await pauseSafeActive();return result();}
                }
                cooldownFinishedAt=api.now();
                if(api.now()-cryoStart>=20000){reason='Twenty-second bounded recovery deadline reached before Cryo';await pauseSafeActive();return result();}
                api.checkStop();t=api.now();skillAttempts=1;await api.wolfCryoWaitCast();inputMs+=Math.max(0,api.now()-t);
                api.checkStop();await api.sleep(250);waitMs+=250;api.checkStop();var after=await observe();addCapture(after);
                if(!validFrame(after,current)){reason='One E attempt sent; fresh same-session observation unavailable';return result();}
                current=after;lastFrame=current.frameId;
                if(!api.wolfCryoWaitPauseReady(current)){reason='One E attempt observed; safe active HUD unavailable for explicit pause';return result();}
                api.checkStop();t=api.now();pauseAttempts=1;await api.wolfCryoWaitEscape();inputMs+=Math.max(0,api.now()-t);
                api.checkStop();await api.sleep(600);waitMs+=600;api.checkStop();var paused=await observe();addCapture(paused);
                if(validFrame(paused,current)&&api.wolfCryoWaitPauseVerified(paused)){pauseVerified=true;reason='One E attempt observed; fresh canonical Wolf pause verified; effect and quest completion remain unverified';lastFrame=paused.frameId;}
                else reason='One E attempt and one Escape sent; canonical Wolf pause not verified';
                return result();
            } catch(e) {
                reason=String(e&&e.message||e);
                if(skillAttempts===1&&pauseAttempts===0)try{
                    api.checkStop();var failureFrame=await observe();addCapture(failureFrame);
                    if(validFrame(failureFrame,current)){
                        current=failureFrame;lastFrame=current.frameId;await pauseSafeActive();
                    }
                }catch(ignorePauseError){}
                return result();
            }
        }
        if(name==='wolfAimCryo') {
            if(!api.wolfAimCryoReady(observation))
                return {status:'stopped',step:name,reason:'Fresh healthy Trial Kaeya HUD with same-session Wolf entry required',orientationAttempts:0,skillAttempts:0,targetEffectVerified:false,frameId:observation&&observation.frameId};
            await api.wolfAimCryo();await api.sleep(100);
            var aimAfter=await observe();
            return {status:'stopped',step:name,reason:'One bounded aim and Cryo sequence observed; turret effect unverified',orientationAttempts:2,skillAttempts:1,targetEffectVerified:false,frameId:aimAfter&&aimAfter.frameId};
        }
        if(name==='wolfCloseFoodCryo') {
            if(!api.wolfCloseFoodCryoReady(observation))
                return {status:'stopped',step:name,reason:'Fresh exact Wolf food grid unavailable',foodCloseAttempts:0,skillAttempts:0,frameId:observation&&observation.frameId};
            await api.wolfCloseFoodCryoAction('close');await api.sleep(450);
            var active=await observe(),hp=active&&active.hud&&active.hud.health;
            if(!api.wolfDefensiveCryoReady(active))
                return {status:'stopped',step:name,reason:'Fresh living grounded Kaeya Trial HUD unavailable after closing inventory',foodCloseAttempts:1,skillAttempts:0,frameId:active&&active.frameId};
            var oriented=false;
            if(hp.current/hp.max>=0.6) {
                await api.wolfCloseFoodCryoAction('look');await api.wolfCloseFoodCryoAction('forward');oriented=true;
            }
            await api.wolfCloseFoodCryoAction('skill');await api.sleep(100);
            var after=await observe();
            return {status:'stopped',step:name,reason:'Inventory closed and one defensive Cryo attempt observed; target effect unverified',foodCloseAttempts:1,
                orientationAttempts:oriented?2:0,skillAttempts:1,targetEffectVerified:false,frameId:after&&after.frameId};
        }
        if(name==='wolfTurretPass') {
            var turretState=api.wolfTurretPassReady(observation,null);
            if(!turretState||!turretState.ok) return {status:'stopped',step:name,reason:turretState&&turretState.reason||'Fresh safe Wolf HUD required',skillAttempts:0,forwardAttempts:0,targetEffectVerified:false,frameId:observation&&observation.frameId};
            await api.wolfTurretPassCast();await api.sleep(100);var turretAfter=await observe();
            return {status:'stopped',step:name,reason:'One Cryo attempt observed; turret shutdown unverified, no passage movement allowed',skillAttempts:1,forwardAttempts:0,targetEffectVerified:false,frameId:turretAfter&&turretAfter.frameId};
        }
        if(name==='wolfExitFlame') {
            if(typeof api.wolfExitFlameReady!=='function'||!api.wolfExitFlameReady(observation))
                return {status:'stopped',step:name,reason:'Fresh pause and latest safe Wolf forward/pause proof required',continueAttempts:0,forwardAttempts:0,frameId:observation&&observation.frameId};
            await api.wolfExitFlame();await api.sleep(150);
            var exitFlameAfter=await observe();
            return {status:'stopped',step:name,reason:'One bounded Continue and forward attempt observed; inspect the fresh scene before another action',
                continueAttempts:1,forwardAttempts:1,forwardMs:300,targetCleared:false,frameId:exitFlameAfter&&exitFlameAfter.frameId};
        }
        if(name==='wolfWindTakeoff') {
            if(typeof api.wolfWindTakeoffReady!=='function'||!api.wolfWindTakeoffReady(observation))
                return {status:'stopped',step:name,reason:'Fresh pause and uninterrupted exact wind-current checkpoint proof required',continueAttempts:0,spacePulses:0,takeoffVerified:false,frameId:observation&&observation.frameId};
            await api.wolfWindTakeoffContinue();await api.sleep(450);var windActive=await observe();
            if(typeof api.wolfWindTakeoffActiveReady!=='function'||!api.wolfWindTakeoffActiveReady(windActive))
                return {status:'stopped',step:name,reason:'Continue sent once; fresh grounded safe Wolf HUD not verified',continueAttempts:1,spacePulses:0,takeoffVerified:false,frameId:windActive&&windActive.frameId};
            await api.wolfWindTakeoffPulses(windActive);await api.sleep(800);var windAfter=await observe();
            return {status:'stopped',step:name,reason:'Two bounded wind-current Space pulses observed; ascent and landing remain unverified',
                continueAttempts:1,spacePulses:2,takeoffVerified:false,glideAttempts:0,frameId:windAfter&&windAfter.frameId};
        }
        if(name==='wolfWindRide') {
            var rideStart=api.now();
            if(typeof api.wolfWindRideReady!=='function'||!api.wolfWindRideReady(observation))
                return {status:'stopped',step:name,reason:'Fresh canonical Wolf pause and latest verified grounded wind-base state required',continueAttempts:0,spacePulses:0,takeoffVerified:false,frameId:observation&&observation.frameId};
            var continueStart=api.now();await api.wolfWindRideContinue();var continueMs=api.now()-continueStart;
            api.checkStop();await api.sleep(450);api.checkStop();var current=await observe(),polls=1,jumpMs=0;api.checkStop();
            if(typeof api.wolfWindRideActiveReady!=='function'||!api.wolfWindRideActiveReady(current))
                return {status:'stopped',step:name,reason:'One Continue sent; fresh grounded safe Trial Kaeya not verified',continueAttempts:1,spacePulses:0,takeoffVerified:false,
                    phaseTiming:{continueMs:continueMs,firstActiveObservationMs:api.now()-rideStart},polls:polls,frameId:current&&current.frameId};
            var jumpStart=api.now();await api.wolfWindRideJump(current);jumpMs=api.now()-jumpStart;
            api.checkStop();await api.sleep(400);api.checkStop();current=await observe();api.checkStop();polls++;
            var airborne=!!api.wolfWindRideAirborne(current),deadline=api.now()+8000;
            while(!airborne&&api.now()<deadline) {
                if(!api.wolfWindRideActiveReady(current)) break;
                api.checkStop();await api.sleep(Math.min(600,deadline-api.now()));api.checkStop();current=await observe();api.checkStop();polls++;
                airborne=!!api.wolfWindRideAirborne(current);
            }
            var state=airborne?'fresh airborne Space cue verified':'bounded wait ended without fresh airborne cue';
            return {status:'stopped',step:name,reason:'Double Space attempted at verified wind base; '+state+'. No glide or landing claimed.',
                continueAttempts:1,spacePulses:2,takeoffVerified:airborne,airborneCueVerified:airborne,glideAttempts:0,landingVerified:false,
                polls:polls,phaseTiming:{continueMs:continueMs,jumpMs:jumpMs,totalMs:api.now()-rideStart},frameId:current&&current.frameId};
        }
        if(name==='wolfGlideForward') {
            var glideStart=api.now(),continueMs=0,moves=0,inputMs=0,polls=0,landed=false;
            if(typeof api.wolfGlideForwardReady!=='function'||!api.wolfGlideForwardReady(observation))
                return {status:'stopped',step:name,reason:'Fresh exact Wolf pause and same-session entry required',continueAttempts:0,moveAttempts:0,inputMs:0,landingVerified:false,frameId:observation&&observation.frameId};
            var continueStart=api.now();await api.wolfGlideForwardContinue();continueMs=api.now()-continueStart;
            api.checkStop();await api.sleep(450);api.checkStop();var current=await observe();api.checkStop();polls++;
            var state=api.wolfGlideState(current);
            if(state==='grounded')return {status:'stopped',step:name,reason:'Already grounded after Continue; no flight or landing verified',
                continueAttempts:1,moveAttempts:0,inputMs:0,groundedBeforeGlide:true,landingVerified:false,questComplete:false,polls:polls,
                phaseTiming:{continueMs:continueMs,totalMs:api.now()-glideStart},frameId:current&&current.frameId};
            if(state!=='airborne')return {status:'stopped',step:name,reason:'Continue sent once; fresh healthy airborne or grounded Trial Kaeya HUD not verified',
                continueAttempts:1,moveAttempts:0,inputMs:0,landingVerified:false,polls:polls,phaseTiming:{continueMs:continueMs,totalMs:api.now()-glideStart},frameId:current&&current.frameId};
            var deadline=api.now()+8000;
            while(state==='airborne'&&moves<4&&api.now()<deadline) {
                api.checkStop();var moveStart=api.now();await api.wolfGlideForwardMove(current);inputMs+=api.now()-moveStart;moves++;
                api.checkStop();await api.sleep(180);api.checkStop();current=await observe();api.checkStop();polls++;
                state=api.wolfGlideState(current);
                if(state==='grounded')landed=true;
                if(state!=='airborne')break;
            }
            var stopReason=landed?'Fresh grounded HUD verified after bounded forward glide':state==='airborne'?
                (moves>=4?'Four observed forward holds used; inspect the wind current':'Eight-second glide deadline reached; inspect scene'):
                'Fresh safe airborne or grounded HUD lost; stopped without another forward hold';
            return {status:'stopped',step:name,reason:stopReason,continueAttempts:1,moveAttempts:moves,inputMs:inputMs,
                perMoveMs:moves?Array(moves).fill(400):[],landingVerified:landed,questComplete:false,polls:polls,
                phaseTiming:{continueMs:continueMs,glideMs:inputMs,totalMs:api.now()-glideStart},frameId:current&&current.frameId};
        }
        if(name==='wolfConsoleInteract') {
            var consoleStart=api.now();
            if(typeof api.wolfConsoleContinueReady!=='function'||!api.wolfConsoleContinueReady(observation))
                return {status:'stopped',step:name,reason:'Fresh exact Wolf pause menu and same-session entry required',continueAttempts:0,interactionAttempts:0,doorOpenVerified:false,frameId:observation&&observation.frameId};
            var consoleContinueStart=api.now();await api.wolfConsoleContinue();var consoleContinueMs=api.now()-consoleContinueStart;
            api.checkStop();await api.sleep(450);api.checkStop();var consoleCurrent=await observe();api.checkStop();
            if(typeof api.wolfConsoleInteractReady!=='function'||!api.wolfConsoleInteractReady(consoleCurrent))
                return {status:'stopped',step:name,reason:'Continue sent once; fresh aligned Open Door and F prompt not verified',continueAttempts:1,interactionAttempts:0,
                    promptLabel:'Open Door',doorOpenVerified:false,polls:1,phaseTiming:{continueMs:consoleContinueMs,totalMs:api.now()-consoleStart},frameId:consoleCurrent&&consoleCurrent.frameId};
            var consoleTarget=api.wolfConsoleInteractTarget?api.wolfConsoleInteractTarget(consoleCurrent):null;
            await api.wolfConsolePressF(consoleCurrent);api.checkStop();await api.sleep(300);api.checkStop();var consoleAfter=await observe();api.checkStop();
            return {status:'stopped',step:name,reason:'One Open Door interaction sent; door state requires visual verification',continueAttempts:1,interactionAttempts:1,
                promptLabel:consoleTarget&&consoleTarget.label||'Open Door',doorOpenVerified:false,polls:2,
                phaseTiming:{continueMs:consoleContinueMs,totalMs:api.now()-consoleStart},frameId:consoleAfter&&consoleAfter.frameId};
        }
        if(name==='wolfContinue') {api.wolfContinue();await api.sleep(450);return {status:'completed',step:name,reason:'Wolf challenge resumed; inspect scene'};}
        if(name==='wolfResume') {
            try { api.checkStop();var proof=api.wolfResume(),resumeResult={status:'completed',step:name,verified:true,fromSession:proof.fromSession,toSession:proof.toSession,
                priorEntryId:proof.priorEntryId,priorPauseId:proof.priorPauseId,betterGiProcessId:proof.betterGiProcessId,rdpSessionId:proof.rdpSessionId,
                gameProcessId:proof.gameProcessId,verifiedAt:proof.verifiedAt,reason:'Read-only Wolf restart handoff verified; no game input sent'};
                if(proof.priorBetterGiProcessId!==undefined)resumeResult.priorBetterGiProcessId=proof.priorBetterGiProcessId;
                return resumeResult; }
            catch(e) { return {status:'stopped',step:name,verified:false,reason:String(e&&e.message||e),inputMs:0}; }
        }
        if(name==='wolfBurstRecovery') {
            var burstStart=api.now(),burstSession=observation&&observation.session,continueAttempts=0,burstAttempts=0,
                pauseAttempts=0,inputMs=0,partyReadRetries=0,hpBefore=null,hpAfter=null,pauseVerified=false;
            function burstResult(reason,frameId) {
                return {status:'stopped',step:name,reason:reason,continueAttempts:continueAttempts,burstAttempted:burstAttempts===1,
                    burstAttempts:burstAttempts,pauseAttempts:pauseAttempts,pauseVerified:pauseVerified,inputMs:inputMs,
                    elapsedMs:Math.max(0,api.now()-burstStart),partyReadRetries:partyReadRetries,hpBefore:hpBefore,hpAfter:hpAfter,
                    burstEffectVerified:false,combatComplete:false,questComplete:false,frameId:frameId||null};
            }
            function validBurstObservation(o,previous) {
                return !!(typeof burstSession==='string'&&burstSession.length>0&&o&&o.session===burstSession&&Number.isInteger(o.frameId)&&
                    (!previous||o.frameId!==previous.frameId)&&Number.isFinite(o.timestamp)&&api.now()>=o.timestamp&&api.now()-o.timestamp<=1000);
            }
            if(!validBurstObservation(observation)||typeof api.wolfBurstContinueReady!=='function'||
               !api.wolfBurstContinueReady(observation)) return burstResult('Fresh exact same-session Wolf pause and entry proof required',observation&&observation.frameId);
            var continueAt=api.now();
            try {
                api.checkStop();continueAttempts=1;api.wolfBurstRecoveryContinue();inputMs+=Math.max(0,api.now()-continueAt);
            } catch(e) {inputMs+=Math.max(0,api.now()-continueAt);return burstResult(String(e&&e.message||e),observation.frameId);}
            await api.sleep(450);
            var current=await observe();
            if(!validBurstObservation(current,observation)) return burstResult('Fresh same-session domain observation unavailable after Continue',current&&current.frameId);
            if(api.now()-burstStart>5000) return burstResult('Five-second pre-burst deadline reached',current.frameId);
            while(!api.wolfBurstRecoveryQReady(current)&&partyReadRetries<2&&api.now()-burstStart<5000&&
                  api.wolfBurstRecoveryRetrySafe(current)) {
                api.checkStop();partyReadRetries++;await api.sleep(250);
                var retry=await observe();
                if(!validBurstObservation(retry,current)) return burstResult('Fresh same-session party OCR retry unavailable',retry&&retry.frameId);
                current=retry;
                if(api.now()-burstStart>5000) return burstResult('Five-second pre-burst deadline reached',current.frameId);
            }
            if(!api.wolfBurstRecoveryQReady(current)) return burstResult('Fresh grounded Trial Kaeya HUD with bottom-row Q unavailable',current.frameId);
            if(api.now()-burstStart>=5000) return burstResult('Five-second pre-burst deadline reached',current.frameId);
            hpBefore=Number(current.hud.health.current);
            var qAt=api.now();
            try {
                api.checkStop();burstAttempts=1;await api.wolfBurstRecoveryQ();inputMs+=Math.max(0,api.now()-qAt);
            } catch(e) {inputMs+=Math.max(0,api.now()-qAt);return burstResult(String(e&&e.message||e),current.frameId);}
            await api.sleep(250);
            var afterQ=await observe();
            if(afterQ&&afterQ.session===burstSession&&afterQ.hud&&afterQ.hud.health&&Number.isFinite(Number(afterQ.hud.health.current))) hpAfter=Number(afterQ.hud.health.current);
            if(!validBurstObservation(afterQ,current)||!api.wolfBurstRecoveryPauseReady(afterQ))
                return burstResult('Active Wolf HUD became stale or ambiguous after the one Q attempt; no further input sent',afterQ&&afterQ.frameId);
            if(api.now()-burstStart>=8000) return burstResult('Eight-second recovery deadline reached before explicit pause',afterQ.frameId);
            var escapeAt=api.now();
            try {
                api.checkStop();pauseAttempts=1;await api.wolfBurstRecoveryEscape();inputMs+=Math.max(0,api.now()-escapeAt);
            } catch(e) {inputMs+=Math.max(0,api.now()-escapeAt);return burstResult(String(e&&e.message||e),afterQ.frameId);}
            await api.sleep(600);
            var paused=await observe();
            if(validBurstObservation(paused,afterQ)&&api.wolfBurstRecoveryPauseVerified(paused)) pauseVerified=true;
            return burstResult(pauseVerified?'One Q attempt made; fresh canonical Wolf pause verified; burst effect and combat completion remain unverified':
                'One Q attempt made; canonical Wolf pause not verified after explicit Escape',paused&&paused.frameId);
        }
        if(name==='wolfCombat')return ActOneCombat.runWolf(observation,api,observe);
        if(name==='wolfRecoveryCombat') {
            var recoveryStart=api.now(),session=observation&&observation.session,continueAttempts=0,lastObserved=observation;
            function validRecoveryFrame(value,previous) {
                return !!(value&&typeof session==='string'&&session.length>0&&value.session===session&&Number.isInteger(value.frameId)&&
                    (!previous||value.frameId!==previous.frameId)&&Number.isFinite(Number(value.timestamp))&&api.now()>=value.timestamp&&api.now()-value.timestamp<=1000);
            }
            async function pauseAfterResumeIfSafe(value) {
                if(!validRecoveryFrame(value,observation)||!api.wolfRecoveryCombatPauseReady||!api.wolfRecoveryCombatPauseReady(value)) return false;
                try {var at=api.now();await api.wolfRecoveryCombatEscape();escapeMs+=Math.max(0,api.now()-at);}
                catch(e) {return false;}
                await api.sleep(600);var paused=await observe();lastObserved=paused;
                return !!(validRecoveryFrame(paused,value)&&api.wolfRecoveryCombatPauseVerified&&api.wolfRecoveryCombatPauseVerified(paused));
            }
            var resultBase={status:'stopped',step:name,reason:'Fresh exact same-session Wolf pause required',continueAttempts:0,
                pauseVerified:false,combatComplete:false,questComplete:false,healthFloorRatio:0.3,damageBudgetRatio:0.2};
            if(!validRecoveryFrame(observation)||!api.wolfRecoveryCombatContinueReady||!api.wolfRecoveryCombatContinueReady(observation)) return resultBase;
            var continueMs=0,escapeMs=0;
            try {api.checkStop();continueAttempts=1;var continueAt=api.now();api.wolfRecoveryCombatContinue();continueMs=Math.max(0,api.now()-continueAt);}
            catch(e) {resultBase.reason=String(e&&e.message||e);resultBase.continueAttempts=continueAttempts;return resultBase;}
            resultBase.continueAttempts=continueAttempts;
            await api.sleep(450);
            var active=await observe();lastObserved=active;
            if(!validRecoveryFrame(active,observation)) {
                resultBase.reason='Fresh active Trial Kaeya HUD unavailable after the one Continue';resultBase.continueAttempts=continueAttempts;
                resultBase.elapsedMs=Math.max(0,api.now()-recoveryStart);resultBase.afterResumeFrame=active&&active.frameId||null;return resultBase;
            }
            resultBase.hpInitial=active.hud&&active.hud.health?Number(active.hud.health.current):null;
            resultBase.maxHp=active.hud&&active.hud.health?Number(active.hud.health.max):null;
            if(resultBase.hpInitial/resultBase.maxHp<0.3) {
                resultBase.reason='Fresh Trial Kaeya health below the 30% recovery floor; no combat input sent';
                resultBase.pauseVerified=await pauseAfterResumeIfSafe(active);resultBase.pauseInputMs=escapeMs;
                resultBase.continueInputMs=continueMs;resultBase.totalInputMs=continueMs+escapeMs;
                resultBase.afterResumeFrame=active.frameId;resultBase.pauseFrame=resultBase.pauseVerified&&lastObserved.frameId||null;
                resultBase.elapsedMs=Math.max(0,api.now()-recoveryStart);return resultBase;
            }
            if(!api.wolfRecoveryCombatActiveReady(active)) {
                resultBase.reason='Fresh active Trial Kaeya HUD unavailable after the one Continue';resultBase.continueAttempts=continueAttempts;
                resultBase.elapsedMs=Math.max(0,api.now()-recoveryStart);resultBase.afterResumeFrame=active.frameId;return resultBase;
            }
            try {api.wolfRecoveryCombatBegin(active);}
            catch(e) {resultBase.reason=String(e&&e.message||e);resultBase.pauseVerified=await pauseAfterResumeIfSafe(active);
                resultBase.continueInputMs=continueMs;resultBase.pauseInputMs=escapeMs;resultBase.totalInputMs=continueMs+escapeMs;
                resultBase.pauseFrame=resultBase.pauseVerified&&lastObserved.frameId||null;resultBase.continueAttempts=continueAttempts;return resultBase;}
            var recoveryApi={now:api.now,sleep:api.sleep,checkStop:api.checkStop,wolfRecoverySelected:true,
                wolfRecoveryCombatKey:function(key){return api.wolfRecoveryCombatKey(key);},wolfRecoveryCombatEscape:async function(){var at=api.now();try{return await api.wolfRecoveryCombatEscape();}finally{escapeMs+=Math.max(0,api.now()-at);}},
                wolfRecoveryCombatStats:api.wolfRecoveryCombatStats};
            var wrappedObserve=async function(){var value=await observe();lastObserved=value;return value;};
            var recoveryResult=await ActOneCombat.runWolfRecovery(active,recoveryApi,wrappedObserve);
            recoveryResult.continueAttempts=continueAttempts;recoveryResult.elapsedMs=Math.max(0,api.now()-recoveryStart);
            recoveryResult.pauseVerified=!!(lastObserved&&api.wolfRecoveryCombatPauseVerified&&api.wolfRecoveryCombatPauseVerified(lastObserved));
            recoveryResult.continueInputMs=continueMs;recoveryResult.pauseInputMs=escapeMs;
            recoveryResult.totalInputMs=(recoveryResult.inputMs||0)+continueMs+escapeMs;
            var finalStats=api.wolfRecoveryCombatStats?api.wolfRecoveryCombatStats():{};
            if(recoveryResult.pauseVerified) recoveryResult.pauseFrame=finalStats.pauseFrame||lastObserved.frameId;
            if(finalStats.hpLast!=null) recoveryResult.hpLast=finalStats.hpLast;
            recoveryResult.combatComplete=false;recoveryResult.questComplete=false;
            return recoveryResult;
        }
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
        if(name==='wolfInfo') {
            if(!observation||!observation.hud||observation.hud.tutorialStep!=='wolfInfo') return {status:'stopped',step:name,reason:'Known Wolf tutorial not present',clicks:0,frameId:observation&&observation.frameId};
            api.wolfDismissInfo();await api.sleep(500);var next=await observe();
            return {status:'completed',step:name,reason:'Known Wolf tutorial clicked once; inspect next slide',clicks:1,frameId:next.frameId};
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
        if(name==='wolfReturnToEntrance') return runWolfReturnToEntrance(observation,api,observe);
        if(name==='fieldRetreatToStatue') {await api.fieldRetreatToStatue();var next=await observe();return {status:'completed',step:name,reason:'Native teleport to unlocked Statue returned; inspect world and healing',frameId:next.frameId};}
        if(name==='worldInventoryClose') {
            if(typeof api.worldInventoryCloseReady!=='function'||typeof api.closeWorldInventory!=='function'||!api.worldInventoryCloseReady(observation))
                return {status:'stopped',step:name,reason:'Fresh exact ordinary inventory required; no Escape sent',inputMs:0,frameId:observation.frameId};
            var closeBegan=api.now();await api.closeWorldInventory();var closeMs=api.now()-closeBegan;
            await api.sleep(350);var closeAfter=await observe();
            return {status:'completed',step:name,reason:'One inventory Escape sent; inspect fresh world state',inputMs:closeMs,worldVisible:closeAfter.hud.world===true,frameId:closeAfter.frameId};
        }
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
    async function runLionEntryStart(name,initial,api,observe,party) {
        var label='Deep Within the Temple of the Lion',readyHook=party?'lionPartyReady':'lionStartReady',startHook=party?'startLionParty':'startLionDomain';
        function result(status,reason,current,clicks,inputMs) {
            return {status:status,step:name,label:label,reason:reason,clicks:clicks,inputMs:inputMs,frameId:current&&current.frameId||initial&&initial.frameId||null};
        }
        if(typeof api[readyHook]!=='function'||typeof api[startHook]!=='function')
            return result('stopped','Lion entry adapter hooks unavailable; no input sent',initial,0,0);
        if(!api[readyHook](initial))
            return result('stopped',party?'Fresh verified Lion party setup required; no input sent':'Fresh exact Lion entrance selection required; no input sent',initial,0,0);
        var started=api.now(),clicks=0;
        try { api.checkStop();api[startHook]();clicks=1; }
        catch(e) { return result('stopped',String(e&&e.message||e),initial,clicks,Math.max(0,api.now()-started)); }
        var inputMs=Math.max(0,api.now()-started);
        await api.sleep(800);api.checkStop();
        var current=await observe();
        return result('completed',party?'Lion party Start clicked; inspect loading or domain':'Lion entrance Start clicked; inspect party setup',current,clicks,inputMs);
    }
    async function runWolfReturnToEntrance(initial,api,observe) {
        var step='wolfReturnToEntrance',target={x:-1642.421,y:2163.664},teleported=false,polls=0,current=initial;
        function result(status,reason) { return {status:status,step:step,reason:reason,teleported:teleported,polls:polls,frameId:current&&current.frameId||null}; }
        if(!api.wolfReturnToEntranceReady(initial)) return result('stopped','Fresh safe starter-party world state and Enter the temple objective required');
        try { api.checkStop();await api.wolfReturnToEntrance();teleported=true; }
        catch(e) { return result('stopped',String(e&&e.message||e)); }
        for(var i=0;i<12;i++) {
            api.checkStop();await api.sleep(500);api.checkStop();current=await observe();polls++;
            var h=current&&current.hud,p=current&&current.map;
            if(h&&(h.journal||h.bigMap||h.dialogueReady||h.choice||h.climbing||h.tutorialStep||h.objectiveChanged||h.auto))
                return result('stopped','Unexpected UI or state during Wolf return teleport');
            if(h&&h.world===true&&p&&p.map==='Teyvat'&&Number.isFinite(p.x)&&Number.isFinite(p.y)) {
                if(!api.wolfReturnToEntranceReady(current)) return result('stopped','Wolf return arrived at an unsafe or ambiguous world state');
                if(Math.hypot(p.x-target.x,p.y-target.y)<=20) return result('completed','Wolf entrance arrival verified within 20 map units');
            }
        }
        return result('stopped','Wolf return loading or arrival verification timed out; no retry');
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
