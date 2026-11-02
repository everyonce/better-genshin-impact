// A separate, bounded Lisa portrait operation. The legacy starter-party healer is unchanged.
var ActOneCombatStatuePanel = (function () {
    var UID = '693306810', MAX_HP = 1001, MAX_AGE_MS = 1000;

    // Require the capture-start stamp, not merely completion of a slow OCR observation.
    function fresh(o, now, session, afterFrame) {
        var stamp = o && o.hud && o.hud.captureStamp;
        return !!(o && o.session === session && typeof session === 'string' && session &&
            Number.isInteger(o.frameId) && o.frameId >= 1 && o.frameId > afterFrame && Number.isFinite(o.timestamp) &&
            Number.isFinite(now) && now >= o.timestamp && stamp && stamp.source === 'game-capture-start' &&
            stamp.session === session && stamp.frameId === o.frameId && Number.isFinite(stamp.capturedAt) &&
            stamp.capturedAt <= o.timestamp && now >= stamp.capturedAt && now - stamp.capturedAt <= MAX_AGE_MS);
    }

    // Match one recognized label within the retained 1920x1080 panel geometry.
    function one(rows, match, x0, x1, y0, y1) {
        return rows.filter(function (r) {
            return r && match.test(String(r.text || '').trim()) &&
                [r.x, r.y, r.width, r.height].every(Number.isFinite) && r.width > 0 && r.height > 0 &&
                r.x >= x0 && r.x <= x1 && r.y >= y0 && r.y <= y1;
        }).length === 1;
    }

    // The original account must be visibly present; a background panel under a modal is inadmissible.
    function account(rows) {
        if (!Array.isArray(rows)) return false;
        // Complete UID tokens are exclusive, even if an overlay puts a second one outside the expected corner.
        var ids = rows.filter(function (r) { return /^(?:UID)?[: ]*[0-9]{9}$/.test(String(r && r.text || '').trim()); });
        return ids.length === 1 && one(ids, /^(?:UID)?[: ]*693306810$/, 1600, 1890, 1030, 1080) &&
            !rows.some(function (r) {
                return /^(?:Confirm|Cancel|Revive|Sign In|Log In|Purchase|Use)$/i.test(String(r.text || '').trim());
            });
    }

    // Return only the fourth reviewed card. Never infer another card from a missing label.
    function permission(o, now, session, afterFrame) {
        var h = o && o.hud, rows = o && o.ocr;
        if (!fresh(o, now, session, afterFrame) || !account(rows) || !h ||
            h.world !== false || h.bigMap !== false || h.journal !== false || h.auto !== false ||
            h.choice !== false || h.dialogueReady !== false || h.climbing !== false ||
            !Array.isArray(h.enemyBars) || h.enemyBars.length !== 0 || h.health !== null) return null;
        if (!one(rows, /^Click on the character portrait to restore HP$/, 190, 240, 15, 70) ||
            !one(rows, /^Statue['’]s Blessing$/, 1490, 1550, 10, 70) ||
            !one(rows, /^Lv\.?\s*17$/, 60, 170, 210, 255) ||
            !one(rows, /^Lv\.?\s*11$/, 240, 350, 210, 255) ||
            !one(rows, /^Lv\.?\s*20$/, 420, 530, 210, 255) ||
            !one(rows, /^Lv\.?\s*4$/, 600, 710, 210, 255)) return null;
        var powerRows = rows.filter(function (r) { return /^Restorative Power:/.test(String(r.text || '').trim()); });
        if (powerRows.length !== 1) return null;
        // The retained panel also has this exact slash-to-seven OCR substitution; geometry and fixed denominator remain mandatory.
        var row = powerRows[0], text = String(row.text || '').trim();
        var match = /^Restorative Power:\s*([0-9]{1,5})\s*\/\s*10000$/.exec(text) ||
            /^Restorative Power:\s*([0-9]{1,5})\s*7\s*10000$/.exec(text);
        if (!match || ![row.x, row.y, row.width, row.height].every(Number.isFinite) ||
            row.x < 1380 || row.x > 1420 || row.y < 580 || row.y > 630 ||
            row.width < 450 || row.width > 530 || row.height < 20 || row.height > 50 ||
            Number(match[1]) <= 0 || Number(match[1]) > 10000) return null;
        return { uid: UID, slot: 4, x: 658, y: 160, frameId: o.frameId,
            capturedAt: h.captureStamp.capturedAt, restorativePower: Number(match[1]) };
    }

    // Numeric health after closing the panel must belong to the reviewed living Lisa roster.
    function worldHealth(o, now, session, afterFrame) {
        var h = o && o.hud, hp = h && h.health, rows = o && o.ocr;
        if (!fresh(o, now, session, afterFrame) || !account(rows) || !h || h.world !== true ||
            h.groundControls !== true || h.climbing !== false || h.bigMap !== false || h.journal !== false ||
            h.auto !== false || h.choice !== false || h.dialogueReady !== false ||
            !Array.isArray(h.enemyBars) || h.enemyBars.length || !hp ||
            !Number.isFinite(hp.current) || hp.current <= 0 || hp.current > MAX_HP || hp.max !== MAX_HP) return null;
        if (!one(rows, /^Lumina$/, 1600, 1800, 240, 300) ||
            !one(rows, /^Amber$/, 1600, 1800, 330, 390) ||
            !one(rows, /^Kaeya$/, 1600, 1800, 420, 490) ||
            !one(rows, /^Lisa$/, 1600, 1800, 515, 580)) return null;
        return { current: hp.current, max: MAX_HP };
    }

    // Three source-bound portrait clicks are sufficient for the reviewed ~80% Lisa case; no retry after uncertainty.
    async function run(initial, api, observe) {
        var current = initial, heals = 0, closed = false, answer = null, lastFrame = -1;
        var lastCapture = -1, lastCompleted = -1;
        var session = initial && initial.session;
        // A new frame number cannot renew either timestamp of the preceding accepted source.
        function newer(o) {
            return fresh(o, api.now(), session, lastFrame) &&
                o.hud.captureStamp.capturedAt > lastCapture && o.timestamp > lastCompleted;
        }
        // Record only a source that passed the complete clock and mode gate.
        function remember(o) {
            lastFrame = o.frameId; lastCapture = o.hud.captureStamp.capturedAt; lastCompleted = o.timestamp;
        }
        function stopped(reason) {
            return { status: 'stopped', step: 'combatStatuePanelHeal', reason: reason,
                portraitClickAttempts: heals, panelCloseAttempted: closed, healthVerified: false, frameId: current && current.frameId };
        }
        try {
            if (!api || ['now', 'checkStop', 'sleep', 'release', 'panelSourceReady', 'clickLisaPortrait', 'closeStatuePanel'].some(function (name) {
                return typeof api[name] !== 'function';
            }) || typeof observe !== 'function') return stopped('Required owned panel adapter is missing');
            for (var i = 0; i < 3; i++) {
                api.checkStop();
                var permit = permission(current, api.now(), session, lastFrame);
                // The native adapter also binds the roster from its owned world-to-panel transition.
                if (!permit || !newer(current) || api.panelSourceReady(current) !== true)
                    return stopped('Fresh original-account fourth Lisa card, owned roster and positive Statue reserve required');
                remember(current);
                heals++;
                await api.clickLisaPortrait(current, permit);
                await api.sleep(700);
                api.checkStop();
                current = await observe();
            }
            api.checkStop();
            if (!permission(current, api.now(), session, lastFrame) || !newer(current) || api.panelSourceReady(current) !== true)
                return stopped('Fresh owned panel required before one close');
            remember(current);
            closed = true;
            await api.closeStatuePanel(current);
            await api.sleep(350);
            for (var poll = 0; poll < 6; poll++) {
                api.checkStop();
                current = await observe();
                if (!newer(current)) return stopped('Post-panel capture is stale or not newer');
                var hp = worldHealth(current, api.now(), session, lastFrame);
                remember(current);
                if (hp) {
                    answer = stopped(hp.current / hp.max >= 0.95 ? 'Lisa health verified at or above 95%' : 'Lisa remains below 95%');
                    answer.health = hp;
                    answer.healthVerified = hp.current / hp.max >= 0.95;
                    answer.status = answer.healthVerified ? 'completed' : 'stopped';
                    return answer;
                }
                if (!account(current.ocr)) return stopped('Original-account evidence disappeared after panel close');
                if (poll < 5) await api.sleep(250);
            }
            return stopped('Fresh grounded Lisa health was not verified after panel close');
        } catch (error) {
            return stopped('Panel recovery stopped: ' + String(error && error.message || error));
        } finally {
            if (api && typeof api.release === 'function') await api.release();
        }
    }

    return { permission: permission, worldHealth: worldHealth, run: run };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = ActOneCombatStatuePanel;
