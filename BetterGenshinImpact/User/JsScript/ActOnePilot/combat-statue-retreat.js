'use strict';

// Fixed current-party retreat. Arrival is not evidence that the Statue healed Lisa.
var ActOneCombatStatueRetreat = (function () {
    var SOURCE_MS = 1000, MAX_WORLD_POLLS = 6, MAX_MAP_POLLS = 6, MAX_ARRIVAL_POLLS = 12;
    var TARGET = { x: -1323.474, y: 2566.115, radius: 20 };

    // The preserved capture-start stamp, not completion time, supplies input freshness.
    function fresh(o, now, session, afterFrame) {
        var s = o && o.hud && o.hud.captureStamp;
        return !!(o && o.session === session && Number.isInteger(o.frameId) && o.frameId > 0 && o.frameId > afterFrame &&
            Number.isFinite(now) && Number.isFinite(o.timestamp) && o.timestamp <= now && s &&
            s.session === session && s.frameId === o.frameId && s.source === 'game-capture-start' &&
            Number.isFinite(s.capturedAt) && s.capturedAt > 0 && s.capturedAt <= o.timestamp && now >= s.capturedAt && now - s.capturedAt <= SOURCE_MS);
    }

    // A visible original UID is required; a hidden or contradictory identity cannot authorize input.
    function originalUid(o) {
        var rows = o && Array.isArray(o.ocr) ? o.ocr : [];
        var ids = rows.filter(function (r) {
            var text = r && String(r.text || '').trim();
            return r && (/^UID\s*:?\s*\d{9}$/i.test(text) ||
                Number.isFinite(r.x) && Number.isFinite(r.y) && r.x >= 1600 && r.y >= 1030 &&
                (/^UID\b/i.test(text) || /^\d{9}$/.test(text)));
        });
        var id = ids[0];
        return ids.length === 1 && /^(?:UID\s*:?\s*)?693306810$/.test(String(id.text || '').trim()) &&
            [id.x,id.y,id.width,id.height].every(Number.isFinite) && id.width > 0 && id.height > 0 &&
            id.x >= 1600 && id.y >= 1030 && id.x + id.width <= 1920 && id.y + id.height <= 1080;
    }

    // These four ordered names and numeric max1001 bind the reviewed current party.
    // Sidebar bars and missing slot digits never imply character health or selection.
    function party(o) {
        var rows = o && Array.isArray(o.ocr) ? o.ocr : [];
        if (rows.some(function (r) { return /^Trial$/i.test(String(r.text || '').trim()); })) return false;
        return [['Lumina',235,305],['Amber',325,395],['Kaeya',415,485],['Lisa',505,585]].every(function (slot) {
            var found = rows.filter(function (r) {
                return r && [r.x,r.y,r.width,r.height].every(Number.isFinite) && r.width > 0 && r.height > 0 &&
                    r.x >= 1550 && r.x <= 1810 && r.y >= 235 && r.y <= 650 && String(r.text || '').trim() === slot[0];
            });
            return found.length === 1 && found[0].y >= slot[1] && found[0].y <= slot[2];
        });
    }

    // Enemy candidates are read on this capture even when the quest objective is unrelated.
    function worldReady(o, now, session, noEnemies) {
        var h = o && o.hud, hp = h && h.health, diagnostic = h && h.enemyBarDiagnostic;
        if (!fresh(o, now, session, -1) || !originalUid(o) || !party(o) || !h || h.world !== true ||
            h.groundControls !== true || h.climbing !== false || h.auto !== false || h.journal !== false ||
            h.bigMap !== false || h.choice !== false || h.dialogueReady !== false || h.objectiveChanged !== false ||
            h.loading || h.unknownHud || h.tutorial || h.tutorialStep || h.characterAcquired ||
            !hp || !Number.isInteger(hp.current) || hp.max !== 1001 || hp.current <= 0 || hp.current > 1001 ||
            !Array.isArray(h.healthOcr) || !Array.isArray(h.enemyBars) || h.enemyBars.length > 4 ||
            !diagnostic || diagnostic.level !== 'any' || !Number.isInteger(diagnostic.candidates) ||
            diagnostic.candidates < 0 || diagnostic.candidates > 4) return false;
        var parsed = h.healthOcr.map(function (text) { return /^(\d+)\s*\/\s*(\d+)$/.exec(String(text).trim()); }).filter(Boolean);
        return parsed.length > 0 && parsed.every(function (m) { return Number(m[1]) === hp.current && Number(m[2]) === hp.max; }) &&
            (!noEnemies || h.enemyBars.length === 0 && diagnostic.candidates === 0);
    }

    // A successful native teleport return is insufficient: require the fixed local destination.
    function atStatue(o, now, session) {
        return worldReady(o, now, session, true) && !!o.map && o.map.map === 'Teyvat' &&
            Number.isFinite(o.map.x) && Number.isFinite(o.map.y) &&
            Math.hypot(o.map.x - TARGET.x, o.map.y - TARGET.y) <= TARGET.radius;
    }

    function result(arrived, o, attempted, polls, reason) {
        return { status: arrived ? 'completed' : 'stopped', step: 'combatStatueRetreat', arrived: arrived,
            healingVerified: false, questComplete: false, teleportAttempted: attempted, polls: polls, reason: reason,
            health: o && o.hud && o.hud.health || null, fieldPosition: arrived ? o.map : null,
            arrivalFrameId: arrived ? o.frameId : null, frameId: o && Number.isInteger(o.frameId) ? o.frameId : null };
    }

    // Only Escape, bounded new-source M attempts and one fixed tp invocation are available.
    async function work(initial, api, observe) {
        var current = initial, attempted = false, polls = 0, session = initial && initial.session;
        function stop(reason) { return result(false, current, attempted, polls, reason); }
        function check() { api.checkStop(); if (api.now() >= api.combatRetreatDeadline()) throw new Error('Original retreat deadline reached'); }
        async function next(last, delay) {
            check(); if (delay) await api.sleep(delay); check();
            var o = await observe(); polls++; check();
            // A new frame number cannot renew a reused or regressed capture clock.
            if (!fresh(o, api.now(), session, last) ||
                o.hud.captureStamp.capturedAt <= current.hud.captureStamp.capturedAt || o.timestamp <= current.timestamp)
                throw new Error('Retreat observation source/session is stale or non-advancing');
            return o;
        }
        try {
            if (!api || typeof api.now !== 'function' || typeof api.checkStop !== 'function' ||
                typeof api.sleep !== 'function' || typeof api.combatRetreatDeadline !== 'function' ||
                typeof observe !== 'function' || typeof session !== 'string' || !session ||
                !fresh(current, api.now(), session, -1)) return stop('Fresh owned initial capture required');
            check();
            if (api.combatRetreatInitialMapReady(current)) {
                await api.combatRetreatAdoptMap(current);
            } else {
                if (!api.combatRetreatInventoryReady(current)) return stop('Exact owned inventory or map required');
                await api.combatRetreatCloseInventory(current);
                var world = false;
                for (var w = 0; w < MAX_WORLD_POLLS; w++) {
                    current = await next(current.frameId, 100);
                    if (api.combatRetreatFieldReady(current)) { world = true; break; }
                }
                if (!world) return stop('Living current Lisa party was not verified after inventory close');
                check(); await api.combatRetreatOpenMap(current);
                var mapInputs = 1, map = false;
                for (var m = 0; m < MAX_MAP_POLLS; m++) {
                    current = await next(current.frameId, 150);
                    if (api.combatRetreatMapReady(current)) { map = true; break; }
                    // Knockback can ignore M. Never retry against unknown, old, menu or dead frames.
                    if (mapInputs < 3 && api.combatRetreatFieldReady(current)) {
                        check(); await api.combatRetreatOpenMap(current); mapInputs++;
                    }
                }
                if (!map) return stop('Fresh paused map was not verified');
            }
            check(); attempted = true;
            // Stock tp has its own <=3 attempts within a60s cancellation budget.
            await api.combatRetreatTeleport(current);
            for (var a = 0; a < MAX_ARRIVAL_POLLS; a++) {
                current = await next(current.frameId, 500);
                if (api.combatRetreatAtStatue(current))
                    return result(true, current, attempted, polls, 'Safe fixed Statue arrival verified; healing is unverified');
            }
            return stop('Safe current-party arrival at the fixed Statue was not verified');
        } catch (error) { return stop('Retreat stopped: ' + String(error && error.message || error)); }
    }

    // Retain an earlier failure if key release also fails; protection remains the adapter's duty.
    async function run(initial, api, observe) {
        var answer = null, releaseError = null;
        try { answer = await work(initial, api, observe); }
        finally { try { if (!api || typeof api.release !== 'function') throw new Error('Release API missing'); await api.release(); }
            catch (error) { releaseError = String(error && error.message || error); } }
        if (releaseError) {
            answer = answer || result(false, initial, false, 0, 'Retreat did not finish');
            answer.status = 'stopped'; answer.cleanupErrors = [releaseError];
        }
        return answer;
    }
    return { run: run, fresh: fresh, originalUid: originalUid, party: party, worldReady: worldReady, atStatue: atStatue };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = ActOneCombatStatueRetreat;
