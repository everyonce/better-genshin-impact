'use strict';

// Current-party Statue healing is separate from the old quest and starter-party healer.
var ActOneCombatStatueHeal = (function () {
    var X = -1323.474, Y = 2566.115;

    // Retain the established bounded approach: no pathfinding, teleport or fallback dialogue.
    async function work(initial, api, observe) {
        var current = initial, moves = 0, turns = 0, interacted = false, chosen = false, reacquisitions = 0;
        var session = initial && initial.session, lastFrame = -1, lastCapture = -1, lastCompleted = -1;
        function result(reason) {
            return { status: 'stopped', step: 'combatStatueHeal', reason: reason, moves: moves, turns: turns,
                interactAttempted: interacted, blessingChoiceAttempted: chosen, healthVerified: false,
                frameId: current && current.frameId, passiveReacquisitionAttempts: reacquisitions };
        }
        function check() {
            api.checkStop();
            if (api.now() >= api.combatHealDeadline()) throw new Error('Original Statue healing deadline reached');
        }
        // Neither a new frame number nor OCR completion renews a previous capture.
        function accept(o) {
            var s = o && o.hud && o.hud.captureStamp;
            if (!o || o.session !== session || !Number.isInteger(o.frameId) || o.frameId < 1 || o.frameId <= lastFrame ||
                !s || s.session !== session || s.frameId !== o.frameId || s.source !== 'game-capture-start' ||
                !Number.isFinite(s.capturedAt) || s.capturedAt <= lastCapture || s.capturedAt <= 0 ||
                !Number.isFinite(o.timestamp) || o.timestamp <= lastCompleted || o.timestamp < s.capturedAt ||
                api.now() < o.timestamp || api.now() - s.capturedAt > 1000)
                throw new Error('Statue healing source/session is stale or non-advancing');
            lastFrame = o.frameId; lastCapture = s.capturedAt; lastCompleted = o.timestamp;
            current = o;
        }
        async function next(delay) {
            check(); if (delay) await api.sleep(delay); check();
            var o = await observe(); check(); accept(o); return o;
        }
        // Only this unresolved numeric conflict may request another input-free capture.
        // It never promotes diagnostic guesses, a prior HP value, or a protection frame.
        function mayReobserveConflict() {
            var h = current && current.hud, s = h && h.captureStamp, phase = h && h.combatHealObservation;
            var d = h && h.enemyBarDiagnostic, now = api.now(), rows = current && current.ocr;
            if (!h || !s || !Number.isFinite(now) || now < current.timestamp || now - s.capturedAt > 1000 ||
                h.health !== null || h.world !== false || current.map !== null ||
                !h.healthDiagnostic || h.healthDiagnostic.decision !== 'conflict-halves-disagree-or-missing' ||
                !Array.isArray(h.healthOcr) || h.healthOcr.length !== 0 ||
                !phase || phase.version !== 1 || phase.phase !== 'approach' || phase.session !== session ||
                phase.frameId !== current.frameId || phase.observationStartedAtUnixMs !== s.capturedAt ||
                h.groundControls !== true || h.climbing !== false || h.auto !== false || h.journal !== false ||
                h.bigMap !== false || h.choice !== false || h.dialogueReady !== false || h.objectiveChanged !== false ||
                h.loading || h.unknownHud || h.tutorial || h.tutorialStep || h.characterAcquired ||
                h.aerialBossVisible || h.aerialBoss || h.slimeTarget ||
                !Array.isArray(h.enemyBars) || h.enemyBars.length !== 0 ||
                !d || d.level !== 'any' || d.candidates !== 0 || !Array.isArray(rows)) return false;
            // Refuse visible foreign/duplicate identities and trial party evidence immediately.
            if (rows.some(function (r) { return /^Trial$/i.test(String(r && r.text || '').trim()); })) return false;
            var ids = rows.filter(function (r) {
                return r && /^(?:UID\b|\d{9}$)/i.test(String(r.text || '').trim());
            });
            var id = ids[0];
            return ids.length === 1 && /^(?:UID\s*:?\s*)?693306810$/.test(String(id.text || '').trim()) &&
                [id.x,id.y,id.width,id.height].every(Number.isFinite) && id.width > 0 && id.height > 0 &&
                id.x >= 1600 && id.y >= 1030 && id.x + id.width <= 1920 && id.y + id.height <= 1080;
        }
        // Share three passive observations across the whole request; no deadline or input budget resets.
        async function qualifiedFieldAfterGap() {
            check();
            while (!api.combatHealFieldReady(current)) {
                check();
                if (reacquisitions >= 3 || !mayReobserveConflict()) return false;
                reacquisitions++;
                await next(150);
            }
            check();
            // A blocking STOP check must not age a successful field proof into a health claim.
            var now = api.now();
            return Number.isFinite(now) && now >= current.timestamp && now - current.hud.captureStamp.capturedAt <= 1000;
        }
        function distance() { return Math.hypot(current.map.x - X, current.map.y - Y); }
        // Only a freshly qualified world source can end the approach without more input.
        function sufficientHealth() {
            if (current.hud.health.current / current.hud.health.max < 0.95) return null;
            var answer = result('Current Lisa numeric HP already at or above95%');
            answer.status = 'completed'; answer.healthVerified = true; answer.health = current.hud.health;
            return answer;
        }
        try {
            if (!api || ['now','checkStop','sleep','release','combatHealDeadline','combatHealInventoryReady',
                'combatHealPrepareNavigation','combatHealCloseInventory','combatHealFieldReady',
                'combatHealRotate','combatHealForward','combatHealInteractReady','combatHealInteract',
                'combatHealBlessingReady','combatHealChooseBlessing','combatHealPanelReady','combatHealRunPanel']
                .some(function (name) { return typeof api[name] !== 'function'; }) || typeof observe !== 'function')
                return result('Required owned Statue healing adapter is missing');
            check(); accept(initial);
            if (!api.combatHealInventoryReady(current)) return result('Fresh original-account inventory required');
            // Heavy map assets load while the recognized inventory remains open, before a new source is acquired.
            await api.combatHealPrepareNavigation(current); check();
            await next(20);
            if (!api.combatHealInventoryReady(current)) return result('Inventory changed during navigation preparation');
            await api.combatHealCloseInventory(current);
            var field = false;
            for (var poll = 0; poll < 6; poll++) {
                await next(150);
                if (api.combatHealFieldReady(current)) { field = true; break; }
            }
            if (!field) return result('Living threat-free Lisa within15 units of Starfell Statue required');
            var sufficient = sufficientHealth();
            if (sufficient) return sufficient;
            while (distance() > 3 && moves < 4 && turns < 12) {
                check();
                if (!api.combatHealFieldReady(current)) return result('Current owned Statue approach source refused');
                var angle = current.map.cameraAngle;
                if (!Number.isFinite(angle)) return result('Fresh local camera orientation required for Statue approach');
                var dx = X - current.map.x, dy = Y - current.map.y;
                var target = (Math.atan2(-dy, -dx) * 180 / Math.PI + 360) % 360;
                var diff = (angle - target + 540) % 360 - 180;
                if (Math.abs(diff) > 8) {
                    turns++; await api.combatHealRotate(current, Math.max(-250, Math.min(250, Math.round(-8 * diff))));
                    await next(180);
                } else {
                    moves++; await api.combatHealForward(current, 500); await next(150);
                }
                if (!await qualifiedFieldAfterGap()) return result('Statue approach lost fresh living grounded evidence');
                sufficient = sufficientHealth();
                if (sufficient) return sufficient;
            }
            if (distance() > 3) return result('Bounded Statue approach did not reach the interaction radius');
            for (var settle = 0; settle < 4 && !api.combatHealInteractReady(current); settle++) {
                await next(250);
                if (!await qualifiedFieldAfterGap()) return result('Statue interaction world became unsafe');
                sufficient = sufficientHealth();
                if (sufficient) return sufficient;
            }
            if (!api.combatHealInteractReady(current)) return result('Unique exact Statue interaction prompt required');
            check(); interacted = true; await api.combatHealInteract(current);
            var choice = false;
            for (var dialoguePoll = 0; dialoguePoll < 6; dialoguePoll++) {
                await next(350);
                if (api.combatHealBlessingReady(current)) { choice = true; break; }
            }
            if (!choice) return result('Exact owned Statue dialogue and unique Blessing choice required; no fallback');
            check(); chosen = true; await api.combatHealChooseBlessing(current);
            for (var panelPoll = 0; panelPoll < 6; panelPoll++) {
                await next(350);
                if (api.combatHealPanelReady(current)) {
                    var answer = await api.combatHealRunPanel(current, observe); check();
                    answer.passiveReacquisitionAttempts = reacquisitions;
                    answer.approach = { moves: moves, turns: turns, interactAttempted: interacted,
                        blessingChoiceAttempted: chosen, worldToPanelOwned: true };
                    return answer;
                }
            }
            return result('Owned fourth-card Statue panel was not verified');
        } catch (error) { return result('Statue healing stopped: ' + String(error && error.message || error)); }
    }

    // Release remains mandatory and its failure cannot erase the known operation result.
    async function run(initial, api, observe) {
        var answer = await work(initial, api, observe);
        try { if (api && typeof api.release === 'function') await api.release(); }
        catch (error) {
            answer.status = 'stopped'; answer.cleanupErrors = [String(error && error.message || error)];
        }
        return answer;
    }
    return { run: run };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = ActOneCombatStatueHeal;
