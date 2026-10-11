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
    async function runNavigation(request, observation, api, observe) {
        var began = api.now(), initialHealth = observation.hud.health, totalInputMs = 0, turns = 0, movements = 0;
        var current = observation, afterForward = null, stalled = 0, turnAttempts = 0, jumpRecoveries = 0;
        function stop(reason) { return { status: 'stopped', reason: reason, inputMs: totalInputMs, turns: turns, movements: movements, jumpRecoveries: jumpRecoveries }; }
        for (var w = 0; w < request.waypoints.length; w++) {
            var target = request.waypoints[w];
            while (true) {
                api.checkStop();
                if (api.now() - began >= request.deadlineMs) return stop('Navigation deadline reached');
                for (var retry = 0; retry < 2 && current.map && (!current.hud.health || !current.hud.objectives.some(function (s) { return objectiveMatches(s, request.objective); })); retry++) {
                    await api.sleep(180); current = await observe(); api.checkStop();
                }
                if (!current.map || !current.hud.world || current.hud.objectiveChanged || current.hud.lowHealth) return stop('Dialogue, objective, low-health, or missing navigation evidence');
                if (!current.hud.objectives.some(function (s) { return objectiveMatches(s, request.objective); })) return stop('Expected objective not visible');
                if (!initialHealth) initialHealth = current.hud.health;
                if (initialHealth.current - current.hud.health.current > initialHealth.max * 0.1) return stop('Health dropped more than 10% of maximum during mission');
                if (current.map.map !== target.map) return stop('Waypoint map does not match current map');
                var distance = Math.hypot(target.x - current.map.x, target.y - current.map.y);
                var investigating = clean(request.objective) === clean('Investigate what Paimon has found');
                if (investigating && current.hud.interact) return stop('Interaction available');
                if (!investigating && distance <= 5) break;
                if (distance > 150) return stop('Waypoint farther than the allowed local segment');
                if (afterForward) {
                    var moved = Math.hypot(current.map.x - afterForward.x, current.map.y - afterForward.y);
                    if (moved > 25) return stop('Map position jumped');
                    stalled = moved < 0.5 ? stalled + 1 : 0; afterForward = null;
                    if (stalled >= 3) {
                        var crystalStep = clean(request.objective) === clean('Investigate what Paimon has found') && distance < 12 &&
                            current.hud.objectives.some(function (s) { return /Higher\s+[1-9]m/i.test(s); });
                        if (!crystalStep || jumpRecoveries >= 1) return stop('Map coordinates stalled');
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
                    var rotateStart = api.now(); await api.rotate(Math.max(-250, Math.min(250, Math.round(-ratio * diff))));
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
        return { status: 'arrived', inputMs: totalInputMs, turns: turns, movements: movements, jumpRecoveries: jumpRecoveries };
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
            if (current.hud.tutorialStep) {
                if ((tutorialSteps[current.hud.tutorialStep] || 0) >= (current.hud.tutorialStep === 'aimSlime' ? 12 : 1)) return {status:'stopped',reason:'tutorial_did_not_advance',presses:presses,inputMs:inputMs};
                tutorialSteps[current.hud.tutorialStep] = (tutorialSteps[current.hud.tutorialStep] || 0) + 1;
                var tutorialStart = api.now(); var tutorialAction = await api.advanceTutorial(); inputMs += api.now()-tutorialStart; presses++;
                await api.sleep(current.hud.tutorialStep === 'aimSlime' && tutorialAction !== 'shot' ? 250 : 1000); current = await observe(); continue;
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
    return { runNavigation: runNavigation, runDialogue: runDialogue, bearing: bearing, objectiveMatches: objectiveMatches, selectDialogueChoice: selectDialogueChoice };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = ActOneMission;


