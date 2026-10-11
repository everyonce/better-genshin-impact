var ActOneCombat = (function () {
    var OBJECTIVE = 'Defeat the nearby hilichurls';
    var CAMP_OBJECTIVE = 'Clear out the nearby hilichurl camp';
    var OBJECTIVES = [OBJECTIVE, CAMP_OBJECTIVE];
    var MAX_RUN_MS = 60000;
    var MAX_ACTIONS = 40;
    var MIN_HEALTH_RATIO = 0.6;
    var MAX_HEALTH_LOSS_RATIO = 0.2;
    var CHARACTER_SWITCH_DELAY_MS = 500;
    var OBSERVE_DELAY_MS = 350;
    var EVIDENCE_RETRY_DELAY_MS = 200;
    var MAX_EVIDENCE_RETRIES = 2;
    var BURST_OBSERVE_DELAY_MS = 700;
    var APPROACH_OBSERVE_DELAY_MS = 150;
    var SKILL_INTERVAL_MS = 8000;
    var MAX_CAMERA_SCANS = 4;
    var MAX_CAMERA_CORRECTIONS = 4;
    var MAX_APPROACH_STEPS = 6;
    var MAX_APPROACH_STALLS = 2;

    function stop(reason, began, api, actions, attacks, skills, bursts, paused) {
        return {
            status: 'stopped', reason: reason,
            elapsedMs: Math.max(0, api.now() - began),
            actions: actions, attacks: attacks, skills: skills, bursts: bursts, paused: paused === true
        };
    }

    function evidenceError(observation, initialHealth, expectedObjective) {
        if (observation && observation.hud &&
            (observation.hud.objectiveCompleted === true || observation.hud.questCompleted === true))
            return 'Objective completion verified';
        if (!observation || !observation.hud || observation.hud.world !== true)
            return 'World HUD unavailable';
        var hud = observation.hud;
        if (hud.objectiveChanged === true) return 'Objective changed';
        if (!Array.isArray(hud.objectives) || hud.objectives.indexOf(expectedObjective) < 0)
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

    function isSupportedObjective(value) { return OBJECTIVES.indexOf(value) >= 0; }

    async function run(request, observation, api, observe) {
        var began = api.now(), actions = 0, attacks = 0, skills = 0, bursts = 0;
        var runLimitMs = typeof request.deadlineMs === 'number' && Number.isFinite(request.deadlineMs) && request.deadlineMs > 0
            ? Math.min(request.deadlineMs, MAX_RUN_MS) : MAX_RUN_MS;
        var initialHealth = null, lastSkillAt = null, scans = 0, cameraCorrections = 0;
        var approachSteps = 0, approachStalls = 0;
        async function result(reason) {
            var paused = false, completionVerified = reason === 'Objective completion verified';
            if (reason !== 'Combat API unavailable' && reason !== 'Unsupported combat objective' &&
                request && isSupportedObjective(request.objective) && typeof api.pauseCombat === 'function' &&
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
                began, api, actions, attacks, skills, bursts, paused);
            stopped.status = completionVerified ? 'completed' : 'stopped';
            stopped.outcome = completionVerified ? 'objective_completed' : 'combat_stopped';
            return stopped;
        }
        async function retryTransientEvidence(candidate, healthBaseline) {
            var reason = evidenceError(candidate, healthBaseline, request.objective), retries = 0;
            function transientEvidence() {
                if (reason === 'World HUD unavailable' || reason === 'Health evidence unavailable') return true;
                return reason === 'Expected objective missing or changed' &&
                    !(candidate && candidate.hud && candidate.hud.objectiveChanged === true);
            }
            while (transientEvidence() && retries < MAX_EVIDENCE_RETRIES) {
                api.checkStop();
                await api.sleep(EVIDENCE_RETRY_DELAY_MS);
                api.checkStop();
                candidate = await observe();
                api.checkStop();
                retries++;
                reason = evidenceError(candidate, healthBaseline, request.objective);
            }
            return { observation: candidate, reason: reason };
        }
        if (!request || !isSupportedObjective(request.objective)) return result('Unsupported combat objective');
        if (typeof observe !== 'function' || typeof api.now !== 'function' || typeof api.sleep !== 'function' ||
            typeof api.checkStop !== 'function' || typeof api.selectTraveler !== 'function' ||
            typeof api.combatAttack !== 'function') return result('Combat API unavailable');

        var initialEvidence = await retryTransientEvidence(observation, null);
        observation = initialEvidence.observation;
        var reason = initialEvidence.reason;
        if (reason) return result(reason);
        initialHealth = { current: Number(observation.hud.health.current), max: Number(observation.hud.health.max) };

        api.checkStop();
        await api.selectTraveler();
        actions++;
        await api.sleep(CHARACTER_SWITCH_DELAY_MS);
        var current = await observe();
        var switchedEvidence = await retryTransientEvidence(current, null);
        current = switchedEvidence.observation;
        reason = switchedEvidence.reason;
        if (reason) return result(reason);
        initialHealth = { current: Number(current.hud.health.current), max: Number(current.hud.health.max) };

        if (typeof api.prepareCombatView === 'function' && await api.prepareCombatView()) {
            actions++;
            await api.sleep(250); current = await observe();
            var preparedEvidence = await retryTransientEvidence(current, initialHealth);
            current = preparedEvidence.observation;
            if (preparedEvidence.reason) return result(preparedEvidence.reason);
        }
        while (true) {
            api.checkStop();
            if (api.now() - began >= runLimitMs) return result('Combat deadline reached');
            if (actions >= MAX_ACTIONS) return result('Combat action limit reached');
            var loopEvidence = await retryTransientEvidence(current, initialHealth);
            current = loopEvidence.observation;
            reason = loopEvidence.reason;
            if (reason) return result(reason);

            var bars = current.hud.enemyBars || [], enemy = null;
            var closeEnemy = false, centeredEnemy = false;
            if (typeof api.combatLook === 'function') {
                if (!bars.length) {
                    cameraCorrections = 0;
                    if (scans >= MAX_CAMERA_SCANS) return result('No enemy health bar found after four bounded camera scans');
                    scans++;
                    await api.combatLook(250); actions++; await api.sleep(250);current=await observe();continue;
                }
                scans = 0;
                enemy=bars.slice().sort(function(a,b){
                    return Number(b.height)-Number(a.height) || Math.abs(a.x-960)-Math.abs(b.x-960);
                })[0];
                closeEnemy = Number(enemy.height) >= 6;
                centeredEnemy = Math.abs(enemy.x - 960) <= 140;
                if (closeEnemy) {
                    // Prioritize the strongest visible bar; preserve native auto-targeting.
                    cameraCorrections = 0;
                } else if (!centeredEnemy) {
                    if (cameraCorrections >= MAX_CAMERA_CORRECTIONS)
                        return result('Enemy camera alignment exceeded four corrections');
                    cameraCorrections++;
                    await api.combatLook(Math.max(-250,Math.min(250,Math.round((enemy.x-960)*0.5))));actions++;
                    await api.sleep(250);current=await observe();continue;
                } else {
                    cameraCorrections = 0;
                    if (typeof api.combatAdvance === 'function') {
                        if (approachSteps >= MAX_APPROACH_STEPS)
                            return result('Combat approach reached six steps without a close enemy');
                        var beforeMap = current.map;
                        api.checkStop();
                        await api.combatAdvance(); actions++; approachSteps++;
                        await api.sleep(APPROACH_OBSERVE_DELAY_MS);
                        current = await observe();
                        var approachEvidence = await retryTransientEvidence(current, initialHealth);
                        current = approachEvidence.observation;
                        if (approachEvidence.reason) return result(approachEvidence.reason);
                        var afterMap = current.map;
                        var mapMoved = beforeMap && afterMap && Number.isFinite(Number(beforeMap.x)) &&
                            Number.isFinite(Number(beforeMap.y)) && Number.isFinite(Number(afterMap.x)) &&
                            Number.isFinite(Number(afterMap.y)) &&
                            Math.hypot(Number(afterMap.x) - Number(beforeMap.x), Number(afterMap.y) - Number(beforeMap.y)) >= 0.3;
                        approachStalls = mapMoved ? 0 : approachStalls + 1;
                        var closeAfterApproach = (current.hud.enemyBars || []).some(function (bar) { return Number(bar.height) >= 6; });
                        if (approachStalls >= MAX_APPROACH_STALLS && !closeAfterApproach)
                            return result('Combat approach stalled for two observed steps');
                        if (approachSteps >= MAX_APPROACH_STEPS && !closeAfterApproach)
                            return result('Combat approach reached six steps without a close enemy');
                        continue;
                    }
                }
            }
            if (bursts === 0 && typeof api.combatBurst === 'function' && actions < MAX_ACTIONS &&
                bars.length > 0 && (closeEnemy || centeredEnemy)) {
                api.checkStop();
                await api.combatBurst();
                actions++; bursts++;
                await api.sleep(BURST_OBSERVE_DELAY_MS);
                current = await observe();
                var burstEvidence = await retryTransientEvidence(current, initialHealth);
                current = burstEvidence.observation;
                if (burstEvidence.reason) return result(burstEvidence.reason);
                continue;
            }
            if (typeof api.combatSkill === 'function'  &&
                (lastSkillAt === null || api.now() - lastSkillAt >= SKILL_INTERVAL_MS)) {
                await api.combatSkill();
                actions++; skills++; lastSkillAt = api.now();
                await api.sleep(OBSERVE_DELAY_MS);
                current = await observe();
            } else {
                var currentHealthRatio = Number(current.hud.health.current) / Number(current.hud.health.max);
                var nearRecognizedEnemy = enemy && Number(enemy.height) >= 6 && Math.abs(enemy.x - 960) <= 260;
                var canBurst = nearRecognizedEnemy && currentHealthRatio >= 0.8 && actions + 2 <= MAX_ACTIONS;
                await api.combatAttack();
                actions++; attacks++;
                if (canBurst) {
                    // Separate clicks so the game's normal-attack animation can advance between presses.
                    await api.sleep(200);
                    api.checkStop();
                    await api.combatAttack();
                    actions++; attacks++;
                    await api.sleep(200);
                } else {
                    await api.sleep(OBSERVE_DELAY_MS);
                }
                current = await observe();
            }
            var actionEvidence = await retryTransientEvidence(current, initialHealth);
            current = actionEvidence.observation;
            reason = actionEvidence.reason;
            if (reason) return result(reason);
        }
    }

    return { run: run, objective: OBJECTIVE, objectives: OBJECTIVES.slice() };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = ActOneCombat;
