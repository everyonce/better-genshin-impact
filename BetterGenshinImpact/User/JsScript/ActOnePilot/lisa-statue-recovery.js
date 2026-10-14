'use strict';

var ActOneLisaStatueRecovery = (function () {
    var MAX_AGE_MS = 1000;
    var MAX_SCREEN_POLLS = 6;
    var MAX_STATUE_POLLS = 12;
    var MAX_HEAL_POLLS = 12;

    function finite(n) { return typeof n === 'number' && Number.isFinite(n); }
    function positiveHealth(frame) {
        var hp = frame && frame.hud && frame.hud.health;
        return !!(hp && finite(hp.current) && finite(hp.max) && hp.current > 0 && hp.max > 0 && hp.current <= hp.max);
    }
    function fresh(frame, now, session, lastId) {
        return !!(frame && frame.session === session && Number.isInteger(frame.frameId) && frame.frameId > lastId &&
            finite(frame.timestamp) && finite(now) && frame.timestamp <= now && now - frame.timestamp <= MAX_AGE_MS);
    }
    function groundedWorld(frame, requireNoEnemies) {
        var h = frame && frame.hud;
        return !!(h && h.world === true && h.groundControls === true && h.climbing === false &&
            h.journal === false && h.bigMap === false && h.auto === false && h.choice === false &&
            h.dialogueReady === false && h.objectiveChanged === false && h.unknownHud !== true &&
            h.loading !== true && h.tutorial !== true && h.tutorialStep == null &&
            Array.isArray(h.enemyBars) && (!requireNoEnemies || h.enemyBars.length === 0) && positiveHealth(frame));
    }
    function result(recovered, frame, attempted, polls, reason) {
        var hp = frame && frame.hud && frame.hud.health;
        return { status: recovered ? 'completed' : 'stopped', step: 'lisaStatueRecovery', recovered: recovered,
            health: hp || null, frameId: frame && Number.isInteger(frame.frameId) ? frame.frameId : null,
            teleportAttempted: attempted, polls: polls, reason: reason, questComplete: false };
    }
    async function healAtStatue(current, api, observe, attempted, polls) {
        var healed = await api.lisaRecoveryHealAtStatue(current, observe);
        var hp = healed && healed.health;
        var accepted = !!(healed && healed.recovered === true && hp && finite(hp.current) && finite(hp.max) &&
            hp.current > 0 && hp.max > 0 && hp.current <= hp.max && hp.current / hp.max >= 0.95 &&
            Number.isInteger(healed.fieldFrameId) && healed.fieldFrameId >= current.frameId);
        var answer = result(accepted, current, attempted, polls, healed && healed.reason || 'Statue approach and healing were not verified');
        answer.healingAttempted = true;
        answer.moves = healed && healed.moves || 0;
        answer.turns = healed && healed.turns || 0;
        if (healed && Number.isInteger(healed.fieldFrameId) && healed.fieldFrameId >= current.frameId) {
            answer.fieldFrameId = healed.fieldFrameId; answer.fieldPosition = healed.fieldPosition || null;
        }
        if (accepted) { answer.health = hp; answer.frameId = healed.fieldFrameId; }
        return answer;
    }

    async function work(initial, api, observe) {
        var current = initial || null, attempted = false, polls = 0, outcome;
        function stop(reason) { return result(false, current, attempted, polls, reason); }
        try {
            if (!api || typeof api.now !== 'function' || typeof api.checkStop !== 'function' ||
                typeof api.sleep !== 'function' || typeof api.release !== 'function' || typeof observe !== 'function' ||
                !current || !current.session || !Number.isInteger(current.frameId) || !finite(current.timestamp))
                return stop('Initial recovery state or required runner functions are invalid');
            api.checkStop();
            var lastId = current.frameId, session = current.session, ready = false;
            var alreadyMap = typeof api.lisaRecoveryInitialMapReady === 'function' && api.lisaRecoveryInitialMapReady(current) === true;
            if (alreadyMap) {
                if (typeof api.lisaRecoveryAdoptMap !== 'function') return stop('Paused map recovery ownership adapter is missing');
                await api.lisaRecoveryAdoptMap(current);
                if (api.lisaRecoveryMapReady(current) !== true) return stop('Adopted paused map is no longer ready');
            } else {
            if (api.lisaRecoveryInventoryReady(current, api.now()) !== true)
                return stop('Exact recovery food inventory was not verified');
            await api.lisaRecoveryCloseInventory(current);
            await api.sleep(300);

            for (var i = 0; i < MAX_SCREEN_POLLS; i++) {
                api.checkStop();
                await api.sleep(250);
                current = await observe(); polls++;
                if (!fresh(current, api.now(), session, lastId)) continue;
                lastId = current.frameId;
                if (groundedWorld(current, false) && api.lisaRecoveryFieldReady(current) === true ||
                    typeof api.lisaRecoveryMapOpenReady === 'function' && api.lisaRecoveryMapOpenReady(current) === true) { ready = true; break; }
            }
            if (!ready) return stop('Fresh grounded Lisa field state was not verified after closing inventory');

            api.checkStop();
            await api.lisaRecoveryOpenMap(current);
            var mapInputs = 1;
            await api.sleep(250);
            ready = false;
            for (var m = 0; m < MAX_SCREEN_POLLS; m++) {
                api.checkStop();
                await api.sleep(250);
                current = await observe(); polls++;
                if (!fresh(current, api.now(), session, lastId)) continue;
                lastId = current.frameId;
                if (api.lisaRecoveryMapReady(current) === true) { ready = true; break; }
                // Knockback can reject M. Retry only against a new, living field
                // observation, never against a map or an unknown transition.
                if (mapInputs < 3 && groundedWorld(current, false) && api.lisaRecoveryFieldReady(current) === true) {
                    await api.lisaRecoveryOpenMap(current); mapInputs++;
                }
            }
            if (!ready) return stop('Fresh paused Teyvat map state was not verified');
            }

            api.checkStop();
            attempted = true;
            await api.lisaRecoveryTeleport(current);
            await api.sleep(500);
            ready = false;
            for (var s = 0; s < MAX_STATUE_POLLS; s++) {
                api.checkStop();
                if (s > 0) await api.sleep(500);
                current = await observe(); polls++;
                if (!fresh(current, api.now(), session, lastId)) continue;
                lastId = current.frameId;
                if (groundedWorld(current, true) && api.lisaRecoveryFieldReady(current) === true &&
                    api.lisaRecoveryAtStatue(current) === true) { ready = true; break; }
            }
            if (!ready) return stop('Fresh Lisa field state at the unlocked Starfell Statue was not verified');

            // The teleport spawn is outside the healing radius. Approach locally
            // rather than spending another twelve captures waiting for impossible healing.
            if (typeof api.lisaRecoveryHealAtStatue === 'function' && current.map && current.map.map === 'Teyvat' &&
                finite(current.map.x) && finite(current.map.y) &&
                Math.hypot(current.map.x + 1323.474, current.map.y - 2566.115) > 3 &&
                Math.hypot(current.map.x + 1323.474, current.map.y - 2566.115) < 15)
                return await healAtStatue(current, api, observe, attempted, polls);

            for (var h = 0; h < MAX_HEAL_POLLS; h++) {
                if (current.hud.health.current / current.hud.health.max >= 0.95)
                    return result(true, current, attempted, polls, 'Passive Statue healing reached at least 95% HP');
                api.checkStop();
                await api.sleep(500);
                current = await observe(); polls++;
                if (!fresh(current, api.now(), session, lastId)) return stop('Fresh same-session health frame was not verified during passive healing');
                lastId = current.frameId;
                if (!groundedWorld(current, true) || api.lisaRecoveryFieldReady(current) !== true || api.lisaRecoveryAtStatue(current) !== true)
                    return stop('Lisa field or Statue safety state changed during passive healing');
            }
            if (current.hud.health.current / current.hud.health.max >= 0.95)
                return result(true, current, attempted, polls, 'Passive Statue healing reached at least 95% HP');
            if (typeof api.lisaRecoveryHealAtStatue === 'function')
                return await healAtStatue(current, api, observe, attempted, polls);
            return stop('Passive Statue healing did not reach 95% HP within the bounded wait');
        } catch (error) {
            outcome = stop(error && error.message ? 'Recovery stopped: ' + error.message : 'Recovery stopped after an API failure');
            return outcome;
        }
    }

    async function run(initial, api, observe) {
        var answer, releaseFailed = false;
        try { answer = await work(initial, api, observe); }
        finally {
            try { if (api && typeof api.release === 'function') await api.release(); else releaseFailed = true; }
            catch (_) { releaseFailed = true; }
        }
        if (releaseFailed) answer = Object.assign({}, answer || result(false, initial, false, 0, 'Recovery stopped'),
            { recovered: false, reason: 'Recovery release failed' });
        return answer;
    }

    return { run: run };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = ActOneLisaStatueRecovery;
