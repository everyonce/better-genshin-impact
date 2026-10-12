'use strict';

var ActOneLionFieldCombat = (function () {
    var OBJECTIVE = 'Meet Lisa at the temple';
    var MAX_AGE_MS = 1000;
    var MIN_HP_RATIO = 0.6;
    var MAX_FIELD_POLLS = 6;
    var MAX_CLEANUP_POLLS = 3;

    function compact(value) {
        var text = String(value || '');
        if (typeof text.normalize === 'function') text = text.normalize('NFD');
        return text.replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '');
    }

    function fresh(o, now, session, previous) {
        return !!(o && typeof session === 'string' && session.length > 0 && o.session === session &&
            Number.isInteger(o.frameId) && (!previous || o.frameId > previous.frameId) &&
            Number.isFinite(o.timestamp) && Number.isFinite(now) && now >= o.timestamp && now - o.timestamp <= MAX_AGE_MS);
    }

    function safeWorld(o, now, session, previous, requireLisaObjective) {
        if (!fresh(o, now, session, previous)) return false;
        var h = o.hud || {}, hp = h.health;
        if (h.world !== true || h.groundControls !== true || h.climbing !== false || h.journal !== false ||
            h.bigMap !== false || h.dialogueReady !== false || h.choice !== false || h.auto !== false ||
            h.unknownHud === true || h.objectiveChanged === true || h.tutorialStep || !Array.isArray(h.objectives)) return false;
        if (requireLisaObjective && !h.objectives.some(function (s) { return compact(s) === 'meetlisaatthetemple'; })) return false;
        return !!(hp && Number.isFinite(hp.current) && Number.isFinite(hp.max) && hp.max > 0 &&
            hp.current > 0 && hp.current <= hp.max && hp.current / hp.max >= MIN_HP_RATIO);
    }

    function knownWorld(o, now, session, previous) {
        if (!fresh(o, now, session, previous)) return false;
        var h = o.hud || {}, hp = h.health;
        return h.world === true && h.groundControls === true && h.climbing === false && h.journal === false &&
            h.bigMap === false && h.dialogueReady === false && h.choice === false && h.auto === false &&
            h.unknownHud !== true && h.objectiveChanged !== true && !h.tutorialStep && hp && Number.isFinite(hp.current) &&
            Number.isFinite(hp.max) && hp.max > 0 && hp.current > 0 && hp.current <= hp.max &&
            Array.isArray(h.objectives) && h.objectives.some(function (s) { return compact(s) === 'meetlisaatthetemple'; });
    }

    async function run(initial, api, observe) {
        var session = initial && initial.session;
        var current = initial;
        var prepared = false, kaeyaSelectAttempted = false, amberReturnAttempted = false, fightStarted = false;
        var nativeFightMs = null, inputMs = 0, polls = 0, postSelectionPolls = 0, pauseVerified = false, releaseError = null;
        var reason = 'Fresh Lisa Hydro Slime field fight not completed';
        var resultStep = 'lionFieldCombat', fieldProbe = null;
        var output = null;
        function now() { return api.now(); }
        function result() {
            if (!output) output = {};
            Object.assign(output, { status: 'stopped', step: resultStep, reason: reason, frameId: current && current.frameId || null,
                inputMs: inputMs, nativeFightMs: nativeFightMs, fieldPolls: polls, kaeyaSelectAttempted: kaeyaSelectAttempted,
                postSelectionPolls: postSelectionPolls,
                amberReturnAttempted: amberReturnAttempted, fightStarted: fightStarted, enemyClearVerified: false, pauseVerified: pauseVerified,
                releaseError: releaseError });
            if (fieldProbe) output.fieldProbe = fieldProbe;
            return output;
        }
        if (!api || typeof observe !== 'function' || typeof api.now !== 'function' || typeof api.checkStop !== 'function' ||
            typeof api.sleep !== 'function' || typeof api.release !== 'function' || typeof api.lionFieldInventoryReady !== 'function' ||
            typeof api.lionFieldCloseInventory !== 'function' || typeof api.lionFieldReady !== 'function' ||
            typeof api.lionFieldSelectKaeya !== 'function' || typeof api.lionFieldReturnAmber !== 'function' ||
            typeof api.lionFieldFight !== 'function' ||
            typeof api.lionFieldPause !== 'function') {
            return { status: 'stopped', step: 'lionFieldCombat', reason: 'Lion field combat adapter is incomplete', enemyClearVerified: false };
        }
        if (!fresh(initial, now(), session, null) || !api.lionFieldInventoryReady(initial, now())) {
            reason = 'Fresh recognized safe Food inventory required';
            return result();
        }
        try {
            api.checkStop();
            var closeAt = now();
            prepared = true;
            await api.lionFieldCloseInventory(initial);
            inputMs += Math.max(0, now() - closeAt);

            // Inventory dismissal can take several frames; observe only, with no blind movement.
            var lastObserved = initial;
            for (var i = 0; i < MAX_FIELD_POLLS; i++) {
                api.checkStop();
                current = await observe();
                polls++;
                if (!fresh(current, now(), session, lastObserved)) { reason = 'Fresh distinct same-session field frame unavailable after inventory close'; return result(); }
                lastObserved = current;
                if (!safeWorld(current, now(), session, null, true)) {
                    await api.sleep(150);
                    continue;
                }
                if (api.lionFieldReady(current, now()) !== true) { reason = 'Owned Kaeya slot 3 and exact Lisa encounter HUD not verified'; return result(); }
                break;
            }
            if (!safeWorld(current, now(), session, null, true) || api.lionFieldReady(current, now()) !== true) {
                reason = 'Lisa encounter field did not become safe and ready within six observations';
                return result();
            }

            if (typeof api.lionFieldProbeOnly === 'function' && api.lionFieldProbeOnly() === true) {
                resultStep = 'lionFieldProbe';
                var probeHud = current.hud || {}, probeHp = probeHud.health || {}, probeMap = current.map || {};
                fieldProbe = { frameId: current.frameId, health: { current: probeHp.current, max: probeHp.max },
                    objectives: probeHud.objectives.slice(),
                    enemyBars: Array.isArray(probeHud.enemyBars) ? probeHud.enemyBars.map(function (bar) {
                        return { x: bar && bar.x, y: bar && bar.y, width: bar && bar.width, height: bar && bar.height };
                    }) : [],
                    compassAngle: Number.isFinite(probeHud.compassAngle) ? probeHud.compassAngle :
                        Number.isFinite(probeMap.cameraAngle) ? probeMap.cameraAngle : null };
                reason = 'Read-only Lisa field probe captured; no party selection or combat input sent';
                return result();
            }

            api.checkStop();
            var selectAt = now();
            kaeyaSelectAttempted = true;
            await api.lionFieldSelectKaeya(current);
            inputMs += Math.max(0, now() - selectAt);
            var selected = null, selectedReady = false, selectPrevious = current;
            await api.sleep(250);
            for (var si = 0; si < MAX_FIELD_POLLS; si++) {
                api.checkStop();
                selected = await observe();
                postSelectionPolls++;
                if (!fresh(selected, now(), session, selectPrevious)) {
                    reason = 'Fresh distinct same-session frame unavailable after Kaeya selection attempt';
                    return result();
                }
                selectPrevious = selected;
                current = selected;
                if (safeWorld(selected, now(), session, null, true) && api.lionFieldReady(selected, now()) === true) {
                    selectedReady = true;
                    break;
                }
                if (si + 1 < MAX_FIELD_POLLS) await api.sleep(150);
            }
            if (!selectedReady) {
                reason = 'Owned Kaeya slot 3 and fresh safe Lisa encounter HUD not verified within six observations';
                return result();
            }
            current = selected;
            if (!Array.isArray(current.hud.enemyBars) || current.hud.enemyBars.length === 0) {
                reason = 'No fresh detected red enemy bar; native fight not started';
                return result();
            }
            api.checkStop();
            fightStarted = true;
            var fightAt = now();
            try { await api.lionFieldFight(current); }
            finally { nativeFightMs = Math.max(0, now() - fightAt); }
            reason = 'One bounded native fight returned; inspect enemies and quest objective';
            return result();
        } catch (e) {
            reason = String(e && e.message || e);
            return result();
        } finally {
            try { await api.release(); }
            catch (e) { releaseError = String(e && e.message || e); }
            // Never send B from an unknown screen. The adapter must verify the exact safe Food pause.
            if (prepared) {
                var pauseSource = null;
                try {
                    var cleanupPrevious = current;
                    var known = null;
                    async function captureKnownWorld() {
                        for (var ci = 0; ci < MAX_CLEANUP_POLLS; ci++) {
                            try {
                                var frame = await observe();
                                if (knownWorld(frame, now(), session, cleanupPrevious)) {
                                    cleanupPrevious = frame;
                                    current = frame;
                                    return frame;
                                }
                                if (fresh(frame, now(), session, cleanupPrevious)) cleanupPrevious = frame;
                            } catch (captureError) {
                                if (!releaseError) releaseError = 'Cleanup capture: ' + String(captureError && captureError.message || captureError);
                            }
                            if (ci + 1 < MAX_CLEANUP_POLLS) await api.sleep(150);
                        }
                        return null;
                    }
                    known = await captureKnownWorld();
                    if (known && kaeyaSelectAttempted) {
                        amberReturnAttempted = true;
                        try {
                            await api.lionFieldReturnAmber(known);
                            await api.sleep(250);
                        } catch (e) {
                            if (!releaseError) releaseError = 'Amber return: ' + String(e && e.message || e);
                        }
                        known = await captureKnownWorld();
                    }
                    if (known) pauseVerified = await api.lionFieldPause(known) === true;
                } catch (e) {
                    if (!releaseError) releaseError = 'Pause verification: ' + String(e && e.message || e);
                }
            }
            result();
        }
    }

    return { run: run, fresh: fresh, safeWorld: safeWorld, knownWorld: knownWorld, compact: compact,
        objective: OBJECTIVE, minHpRatio: MIN_HP_RATIO, maxFieldPolls: MAX_FIELD_POLLS, maxCleanupPolls: MAX_CLEANUP_POLLS };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = ActOneLionFieldCombat;
