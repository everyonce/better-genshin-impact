var ActOneWindriseReveal = (function () {
    var LIMIT_MS = 35000, MAX_FORWARD_HOLDS = 24, FRESH_MS = 1000;

    function healthOf(o) {
        var h = o && o.hud && o.hud.health;
        return h && Number.isFinite(h.current) && Number.isFinite(h.max) && h.current > 0 && h.max > 0 && h.current <= h.max ? h : null;
    }
    function norm(s) { return String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().replace(/\s+/g, ' '); }
    function dimsOkay(o) {
        var d = o && (o.capture || o.image || o.screen || o);
        return !(d && (d.width !== undefined || d.height !== undefined)) || Number(d.width) === 1920 && Number(d.height) === 1080;
    }
    function objectiveOkay(o) {
        var rows = o && o.hud && o.hud.objectives;
        if (!Array.isArray(rows)) return false;
        var matches = rows.map(function (x) { return typeof x === 'string' ? x : x && x.text; })
            .filter(function (x) { return norm(x).replace(/\s+/g,'') === 'meetlisaatthetemple'; });
        return matches.length === 1;
    }
    function rosterEvidence(o) {
        var rows = o && Array.isArray(o.ocr) ? o.ocr : [];
        function unique(name) {
            var found = rows.filter(function (r) { return r && typeof r.text === 'string' && r.text.trim() === name &&
                Number(r.x) >= 1550 && Number(r.x) <= 1800 && Number(r.y) >= 300 && Number(r.y) <= 600; });
            return found.length === 1;
        }
        return unique('Amber') && unique('Kaeya');
    }
    function safeField(o, now, session, expectedMax, minHp, allowEnemies) {
        var h = o && o.hud, hp = healthOf(o), bars = h && h.enemyBars, rows = o && Array.isArray(o.ocr) ? o.ocr : [];
        var p = o && o.map;
        var hasTrial = rows.some(function (r) { return r && typeof r.text === 'string' && r.text.trim() === 'Trial'; });
        return !!(o && h && Number.isFinite(now) && Number.isFinite(o.timestamp) && now >= o.timestamp && now - o.timestamp <= FRESH_MS &&
            (!session || o.session === session) && Number.isInteger(o.frameId) && dimsOkay(o) && hp && hp.max === expectedMax &&
            hp.current >= minHp && h.groundControls === true && h.climbing === false && h.auto === false &&
            h.dialogueReady === false && h.choice === false && h.journal === false && h.bigMap === false && !h.tutorialStep && !h.objectiveChanged &&
            !hasTrial && (Array.isArray(bars) && (allowEnemies || bars.length === 0)) && objectiveOkay(o) && rosterEvidence(o) &&
            (!p || p.map === 'Teyvat' && Number.isFinite(p.x) && Number.isFinite(p.y)));
    }
    function fieldReady(o, now, session, expectedMax) { return safeField(o, now, session, expectedMax === undefined ? 1186 : expectedMax, 0.6 * (expectedMax === undefined ? 1186 : expectedMax)); }
    function fieldPauseReady(o, now, session, expectedMax) { return safeField(o, now, session, expectedMax === undefined ? 1186 : expectedMax, Number.MIN_VALUE, true); }
    function retreatReady(o, now, session, expectedMax) { return safeField(o, now, session, expectedMax === undefined ? 1186 : expectedMax, 0.6 * (expectedMax === undefined ? 1186 : expectedMax), true); }
    function statueInteractReady(o, now, session, expectedMax) {
        if (!fieldReady(o, now, session, expectedMax)) return false;
        var rows = o && Array.isArray(o.ocr) ? o.ocr : [];
        function unique(predicate) { return rows.filter(predicate).length === 1; }
        return unique(function (r) {
            return r && typeof r.text === 'string' && r.text.trim().replace(/\s+/g, ' ') === 'Statue of The Seven' &&
                Number(r.x) >= 1180 && Number(r.x) <= 1250 && Number(r.y) >= 490 && Number(r.y) <= 545 &&
                Number(r.width) >= 240 && Number(r.width) <= 310 && Number(r.height) >= 20 && Number(r.height) <= 38;
        }) && unique(function (r) {
            return r && typeof r.text === 'string' && r.text.trim() === 'F' && Number(r.x) >= 1080 && Number(r.x) <= 1170 &&
                Number(r.y) >= 490 && Number(r.y) <= 590 && Number(r.width) > 0 && Number(r.width) <= 60 &&
                Number(r.height) > 0 && Number(r.height) <= 60;
        });
    }
    async function run(initial, api, observe) {
        api = api || {}; var started = api.now(), current = initial, session = initial && initial.session;
        var baseline = healthOf(initial), moves = 0, retreats = 0, turns = 0, interactions = 0, inputMs = 0, permitConsumed = false,
            pausedInventory = false, interactionAttempted = false, interactionPostFrameValid = false;
        var reason = 'Windrise reveal stopped';
        function check() { if (typeof api.checkStop === 'function') api.checkStop(); }
        function elapsed() { return Math.max(0, api.now() - started); }
        function deadline() { if (elapsed() >= LIMIT_MS) throw new Error('35-second reveal deadline reached'); }
        function validFresh(o, previous) {
            var n = api.now();
            return !!o && !!session && o.session === session && Number.isInteger(o.frameId) && o.frameId >= 0 &&
                Number.isFinite(o.timestamp) && n >= o.timestamp && n - o.timestamp <= FRESH_MS &&
                (!previous || o.frameId > previous.frameId && o.timestamp > previous.timestamp);
        }
        async function fresh(previous) {
            check(); var next = await observe(); check();
            if (!validFresh(next, previous)) throw new Error('Fresh distinct same-session frame required');
            current = next;
            var h = healthOf(next);
            if (!h || !baseline || h.max !== baseline.max || baseline.current - h.current > baseline.max * 0.05)
                throw new Error('Health dropped more than 5% or became unavailable');
            return next;
        }
        async function freshForPause(previous) {
            check(); var next = await observe(); check();
            if (!validFresh(next, previous)) throw new Error('Fresh distinct same-session frame required for pause');
            current = next; return next;
        }
        async function freshAfterInteraction(previous) {
            check(); var next = await observe(); check();
            if (!validFresh(next, previous)) throw new Error('Fresh distinct same-session post-interaction frame required');
            current = next; interactionPostFrameValid = true; return next;
        }
        function ready(o) {
            return typeof api.windriseRevealReady === 'function' && api.windriseRevealReady(o) === true;
        }
        async function recordInput(fn) {
            var at = api.now(); try { await fn(); } finally { inputMs += Math.max(0, api.now() - at); }
        }
        async function tryPause() {
            // A cleanup pause is allowed only from a new frame explicitly accepted by the adapter.
            try {
                if (elapsed() >= LIMIT_MS) return false;
                if (interactionAttempted && (!interactionPostFrameValid || !fieldPauseReady(current, api.now(), session))) return false;
                if (!fieldPauseReady(current, api.now(), session)) return false;
                var before = current, next = await freshForPause(before);
                if (!fieldPauseReady(next, api.now(), session)) return false;
                if (typeof api.windriseRevealPause !== 'function') return false;
                if (elapsed() >= LIMIT_MS) return false;
                var at = api.now(), result;
                try { result = await api.windriseRevealPause(next); }
                finally { inputMs += Math.max(0, api.now() - at); }
                if (result === true) { pausedInventory = true; return true; }
            } catch (_) { /* pause is best effort; preserve the original stop reason */ }
            return false;
        }
        try {
            if (!validFresh(initial, null) || !baseline) throw new Error('Fresh safe outdoor English scene required');
            if (!ready(initial)) {
                // An otherwise valid field frame may be pause-only when an enemy blocks all movement readiness.
                // The adapter consumes only the original root witness permit and independently gates the pause.
                if (fieldPauseReady(initial, api.now(), session) && typeof api.windriseRevealConsumePausePermit === 'function') {
                    try { if (api.windriseRevealConsumePausePermit(initial) === true) permitConsumed = true; }
                    catch (_) { /* a failed permit write is final; never retry through the movement permit */ }
                }
                throw new Error('Fresh safe outdoor English scene required');
            }
            if (typeof api.windriseRevealPlan !== 'function' || typeof api.windriseRevealAction !== 'function' ||
                typeof api.windriseRevealConsumePermit !== 'function') throw new Error('Reveal adapter unavailable');
            var plan = api.windriseRevealPlan(current);
            if (!plan || (plan.action !== 'forward' && plan.action !== 'retreat' && plan.action !== 'look' && plan.action !== 'interact')) throw new Error('Invalid reveal plan');
            if ((plan.action === 'forward' || plan.action === 'retreat') && (!Number.isInteger(plan.holds) || plan.holds < 1 || plan.holds > MAX_FORWARD_HOLDS))
                throw new Error('Forward or retreat plan must contain 1 to 24 fixed 500ms holds');
            if (plan.action === 'retreat' && !retreatReady(current, api.now(), session)) throw new Error('Fresh safe retreat field evidence required');
            if (plan.action === 'look' && (!Number.isInteger(plan.dx) || Math.abs(plan.dx) > 250)) throw new Error('Look turn exceeds 250');
            if (plan.action === 'interact' && (!statueInteractReady(current, api.now(), session) ||
                typeof api.windriseRevealStatueReady !== 'function' || api.windriseRevealStatueReady(current) !== true))
                throw new Error('Fresh unique Statue of The Seven and F prompt required');
            check(); deadline();
            if (api.windriseRevealConsumePermit(current) !== true) throw new Error('One-use root permit was not consumed');
            permitConsumed = true;
            if (plan.action === 'forward' || plan.action === 'retreat') {
                for (var i = 0; i < plan.holds; i++) {
                    check(); deadline();
                    if(LIMIT_MS-elapsed()<500)throw new Error('Insufficient reveal budget for another bounded hold');
                    if (!ready(current) || plan.action === 'retreat' && !retreatReady(current, api.now(), session))
                        throw new Error('Outdoor scene or input focus guard failed');
                    await recordInput(function () { return api.windriseRevealAction(plan.action, 500); });
                    if (plan.action === 'forward') moves++; else retreats++;
                    current = await fresh(current);
                    if (!ready(current) || plan.action === 'retreat' && !retreatReady(current, api.now(), session))
                        throw new Error('Outdoor scene or input focus guard failed after movement');
                }
            } else if (plan.action === 'look') {
                check(); deadline();
                await recordInput(function () { return api.windriseRevealAction('look', plan.dx); }); turns++;
                current = await fresh(current);
                if (!ready(current)) throw new Error('Outdoor scene or input focus guard failed after look');
            } else {
                check(); deadline();
                if (!statueInteractReady(current, api.now(), session) || api.windriseRevealStatueReady(current) !== true)
                    throw new Error('Statue interaction evidence expired before input');
                interactionAttempted = true;
                interactions++;
                await recordInput(function () { return api.windriseRevealAction('interact', 60); });
                current = await freshAfterInteraction(current);
                reason = 'Single Statue F interaction attempted; unlock animation observed for root inspection; quest completion not verified';
            }
            if (plan.action !== 'interact') reason = 'Bounded reveal step completed; Windrise and quest completion not verified';
        } catch (e) { reason = String(e && e.message || e || 'Windrise reveal stopped'); }
        finally {
            // Always release held inputs, including on cancellation, focus loss, or adapter failure.
            try { if (typeof api.release === 'function') await api.release(); } catch (_) { /* best effort */ }
            // Pause only from a fresh field scene accepted by the adapter. This remains valid below HP threshold.
            if (permitConsumed && !pausedInventory && (!interactionAttempted || interactionPostFrameValid && fieldPauseReady(current, api.now(), session))) {
                await tryPause();
                if (!pausedInventory && (!interactionAttempted || interactionPostFrameValid && fieldPauseReady(current, api.now(), session))) reason += '; inventory pause was not verified';
            }
        }
        return { status: 'stopped', step: 'windriseReveal', rootDirected: true, moves: moves, retreats: retreats, turns: turns, interactions: interactions,
            pausedInventory: pausedInventory, reason: reason, frameId: current && current.frameId,
            inputMs: inputMs, elapsedMs: elapsed(), questComplete: false };
    }
    return { run: run, fieldReady: fieldReady, fieldPauseReady: fieldPauseReady,
        retreatReady: retreatReady, statueInteractReady: statueInteractReady };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = ActOneWindriseReveal;
