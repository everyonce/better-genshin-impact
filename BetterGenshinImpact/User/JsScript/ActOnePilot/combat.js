var ActOneCombat = (function () {
    var OBJECTIVE = 'Defeat the nearby hilichurls';
    var MAX_RUN_MS = 60000;
    var MAX_ACTIONS = 40;
    var MIN_HEALTH_RATIO = 0.6;
    var MAX_HEALTH_LOSS_RATIO = 0.2;
    var CHARACTER_SWITCH_DELAY_MS = 500;
    var OBSERVE_DELAY_MS = 350;
    var SKILL_INTERVAL_MS = 8000;

    function stop(reason, began, api, actions, attacks, skills, paused) {
        return {
            status: 'stopped', reason: reason,
            elapsedMs: Math.max(0, api.now() - began),
            actions: actions, attacks: attacks, skills: skills, paused: paused === true
        };
    }

    function evidenceError(observation, initialHealth) {
        if (observation && observation.hud &&
            (observation.hud.objectiveCompleted === true || observation.hud.questCompleted === true))
            return 'Objective completion verified';
        if (!observation || !observation.hud || observation.hud.world !== true)
            return 'World HUD unavailable';
        var hud = observation.hud;
        if (hud.objectiveChanged === true) return 'Objective changed';
        if (!Array.isArray(hud.objectives) || hud.objectives.indexOf(OBJECTIVE) < 0)
            return 'Expected objective missing or changed';
        var health = hud.health;
        if (!health || !Number.isFinite(Number(health.current)) || !Number.isFinite(Number(health.max)) || Number(health.max) <= 0)
            return 'Health evidence unavailable';
        var current = Number(health.current), max = Number(health.max);
        if (current / max < MIN_HEALTH_RATIO) return 'Health below 60%';
        if (initialHealth && initialHealth.current - current >= initialHealth.max * MAX_HEALTH_LOSS_RATIO)
            return 'Health dropped 20% or more of maximum';
        return null;
    }

    async function run(request, observation, api, observe) {
        var began = api.now(), actions = 0, attacks = 0, skills = 0;
        var runLimitMs = typeof request.deadlineMs === 'number' && Number.isFinite(request.deadlineMs) && request.deadlineMs > 0
            ? Math.min(request.deadlineMs, MAX_RUN_MS) : MAX_RUN_MS;
        var initialHealth = null, lastSkillAt = null, scans = 0;
        async function result(reason) {
            var paused = false, completionVerified = reason === 'Objective completion verified';
            if (reason !== 'Combat API unavailable' && reason !== 'Unsupported combat objective' &&
                request && request.objective === OBJECTIVE && typeof api.pauseCombat === 'function' &&
                typeof api.checkStop === 'function' && typeof observe === 'function') {
                // Exceptions from stop/readiness checks intentionally escape without attempting a pause.
                api.checkStop();
                var fresh = await observe();
                api.checkStop();
                completionVerified = completionVerified || !!(fresh && fresh.hud &&
                    (fresh.hud.objectiveCompleted === true || fresh.hud.questCompleted === true));
                if (fresh && fresh.hud && fresh.hud.world === true) {
                    var pauseRequested = await api.pauseCombat();
                    if (pauseRequested) {
                        var afterPause = await observe();
                        api.checkStop();
                        paused = !!(afterPause && afterPause.hud && afterPause.hud.journal === true);
                    }
                }
            }
            var stopped = stop(completionVerified ? 'Objective completion verified' : reason,
                began, api, actions, attacks, skills, paused);
            stopped.status = completionVerified ? 'completed' : 'stopped';
            stopped.outcome = completionVerified ? 'objective_completed' : 'combat_stopped';
            return stopped;
        }
        if (!request || request.objective !== OBJECTIVE) return result('Unsupported combat objective');
        if (typeof observe !== 'function' || typeof api.now !== 'function' || typeof api.sleep !== 'function' ||
            typeof api.checkStop !== 'function' || typeof api.selectTraveler !== 'function' ||
            typeof api.combatAttack !== 'function') return result('Combat API unavailable');

        var reason = evidenceError(observation, null);
        if (reason) return result(reason);
        initialHealth = { current: Number(observation.hud.health.current), max: Number(observation.hud.health.max) };

        api.checkStop();
        await api.selectTraveler();
        actions++;
        await api.sleep(CHARACTER_SWITCH_DELAY_MS);
        var current = await observe();
        reason = evidenceError(current, null);
        if (reason) return result(reason);
        initialHealth = { current: Number(current.hud.health.current), max: Number(current.hud.health.max) };

        if (typeof api.prepareCombatView === 'function' && await api.prepareCombatView()) {
            actions++;
            await api.sleep(250); current = await observe();
        }
        while (true) {
            api.checkStop();
            if (api.now() - began >= runLimitMs) return result('Combat deadline reached');
            if (actions >= MAX_ACTIONS) return result('Combat action limit reached');
            reason = evidenceError(current, initialHealth);
            if (reason) return result(reason);

            if (typeof api.combatLook === 'function') {
                var bars=current.hud.enemyBars || [];
                if (!bars.length) {
                    if(++scans>12) return result('No enemy health bar found in bounded camera scan');
                    await api.combatLook(250); actions++; await api.sleep(250);current=await observe();continue;
                }
                scans = 0;
                var enemy=bars.slice().sort(function(a,b){return Math.abs(a.x-960)-Math.abs(b.x-960);})[0];
                var centerTolerance = Number(enemy.height) >= 6 ? 260 : 140;
                if(Math.abs(enemy.x-960)>centerTolerance) {
                    await api.combatLook(Math.max(-250,Math.min(250,Math.round((enemy.x-960)*0.5))));actions++;
                    await api.sleep(250);current=await observe();continue;
                }
            }
            if (typeof api.combatSkill === 'function'  &&
                (lastSkillAt === null || api.now() - lastSkillAt >= SKILL_INTERVAL_MS)) {
                await api.combatSkill();
                actions++; skills++; lastSkillAt = api.now();
            } else {
                await api.combatAttack();
                actions++; attacks++;
            }
            await api.sleep(OBSERVE_DELAY_MS);
            current = await observe();
            reason = evidenceError(current, initialHealth);
            if (reason) return result(reason);
        }
    }

    return { run: run, objective: OBJECTIVE };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = ActOneCombat;
