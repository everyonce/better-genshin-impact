var ActOneWolfWitnessAction = (function () {
    var RUN_LIMIT_MS = 15000, FRESH_MS = 1000, CONTINUE_SETTLE_MS = 450;
    var ACTION_SETTLE_MS = 150, PAUSE_SETTLE_MS = 600, MAX_POLLS = 8;
    var ACTIONS = ['forwardFine', 'forwardBounded', 'leftFine', 'rightFine', 'lookLeft', 'lookRight', 'jumpForward', 'strike'];

    function healthOf(o) {
        var h = o && o.hud && o.hud.health;
        return h && Number.isFinite(h.current) && Number.isFinite(h.max) && h.current > 0 &&
            h.max > 0 && h.current <= h.max ? h : null;
    }
    function validHealth(h) {
        return !!h && Number.isFinite(h.current) && Number.isFinite(h.max) && h.current > 0 &&
            h.max > 0 && h.current <= h.max;
    }
    function unsafePoll(o, baseline) {
        var raw = o && o.hud && o.hud.health;
        if (raw && Number.isFinite(raw.current) && raw.current <= 0) return 'Health changed during active readiness polling';
        if (raw && Number.isFinite(raw.current) && Number.isFinite(raw.max) &&
            (raw.current !== baseline.current || raw.max !== baseline.max)) return 'Health changed during active readiness polling';
        var bars = o && o.enemyBars;
        if (bars === true || Array.isArray(bars) && bars.length > 0 || bars && typeof bars === 'object' && Object.keys(bars).length > 0)
            return 'Enemy bars appeared during active readiness polling';
        return null;
    }
    function distinctFresh(o, previous, session, api) {
        var now = api.now();
        return !!o && !!session && o.session === session && Number.isInteger(o.frameId) && o.frameId >= 0 &&
            Number.isFinite(o.timestamp) && now >= o.timestamp && now - o.timestamp <= FRESH_MS &&
            (!previous || o.frameId > previous.frameId && o.timestamp > previous.timestamp);
    }
    async function run(initial, api, observe) {
        var startedAt = api.now(), current = initial, session = initial && initial.session;
        var healthBefore = healthOf(initial), healthAfter = healthBefore;
        var counts = { continue: 0, action: 0, pause: 0, polls: 0 }, pauseVerified = false;
        var action = null, reason = 'One bounded wolf witness action stopped';
        function deadline(extra) {
            if (api.now() - startedAt + (extra || 0) > RUN_LIMIT_MS) throw new Error('15-second wolf witness deadline reached');
        }
        function checkStop() { if (typeof api.checkStop === 'function') api.checkStop(); }
        async function fresh(previous) {
            checkStop(); var next = await observe(); checkStop();
            if (!distinctFresh(next, previous, session, api)) throw new Error('Fresh distinct same-session frame required');
            current = next; healthAfter = healthOf(next); return next;
        }
        async function cleanupPause() {
            // Always take a new cleanup observation. It must be fresh, distinct and in the original session.
            var before = current, next;
            try { next = await fresh(before); } catch (_) { return false; }
            if (typeof api.wolfWitnessPauseReady !== 'function' || api.wolfWitnessPauseReady(next) !== true) return false;
            // Cleanup is best-effort, but must never initiate another input beyond the run deadline.
            try { deadline(2500); } catch (_) { return false; }
            counts.pause++;
            await api.wolfWitnessEscape();
            await api.sleep(PAUSE_SETTLE_MS);
            var after = await observe();
            if (distinctFresh(after, current, session, api) && typeof api.wolfWitnessPauseVerified === 'function' &&
                api.wolfWitnessPauseVerified(after) === true) {
                current = after; healthAfter = healthOf(after); pauseVerified = true;
            }
            return pauseVerified;
        }
        try {
            if (!session || !distinctFresh(initial, null, session, api) ||
                typeof api.wolfWitnessContinueReady !== 'function' || api.wolfWitnessContinueReady(initial) !== true)
                throw new Error('Canonical paused entry proof required before Continue');
            if (!healthBefore && typeof api.wolfWitnessBaselineHealth === 'function') {
                var baseline = api.wolfWitnessBaselineHealth();
                if (validHealth(baseline)) healthBefore = { current: baseline.current, max: baseline.max };
            }
            if (!validHealth(healthBefore)) throw new Error('Valid positive health baseline required before Continue');
            if (typeof api.wolfWitnessContinue !== 'function') throw new Error('Continue action unavailable');
            deadline(); counts.continue++;
            await api.wolfWitnessContinue();
            await api.sleep(CONTINUE_SETTLE_MS);
            var ready = false;
            for (var i = 0; i <= MAX_POLLS; i++) {
                if (i > 0) { deadline(2700); await api.sleep(200); }
                var next = await fresh(current);
                var unsafe = unsafePoll(next, healthBefore);
                if (unsafe) throw new Error(unsafe);
                if (typeof api.wolfWitnessActiveReady === 'function' && api.wolfWitnessActiveReady(next) === true) {
                    ready = true; break;
                }
                // An explicit identity/freshness failure throws above; only a valid same-session frame is pollable.
                if (i === MAX_POLLS) break;
                counts.polls++;
            }
            if (!ready) throw new Error('Active session and focus guard did not become ready within eight read-only polls');
            if (!healthBefore || !healthOf(current) || healthOf(current).current !== healthBefore.current || healthOf(current).max !== healthBefore.max)
                throw new Error('Health changed before the witness action');
            if (typeof api.wolfWitnessActionName !== 'function' || typeof api.wolfWitnessAction !== 'function')
                throw new Error('Witness action adapter unavailable');
            action = api.wolfWitnessActionName();
            if (ACTIONS.indexOf(action) < 0) throw new Error('Unknown wolf witness action name');
            deadline(4000); counts.action++;
            await api.wolfWitnessAction();
            await api.sleep(ACTION_SETTLE_MS);
            var afterAction = await fresh(current);
            if (!healthBefore || !healthOf(afterAction) || healthOf(afterAction).current !== healthBefore.current ||
                healthOf(afterAction).max !== healthBefore.max) throw new Error('Health changed after the witness action');
            if (typeof api.wolfWitnessActiveReady !== 'function' || api.wolfWitnessActiveReady(afterAction) !== true)
                throw new Error('Active session or focus guard failed after the witness action');
            reason = 'One root-directed witness action attempted; no route or quest completion claim';
        } catch (e) {
            reason = String(e && e.message || e || 'Wolf witness action stopped');
        } finally {
            try { await cleanupPause(); } catch (e) { if (reason === 'One root-directed witness action attempted; no route or quest completion claim') reason = String(e && e.message || e); }
            try { if (typeof api.release === 'function') await api.release(); } catch (_) { /* Release is best effort and always attempted. */ }
        }
        healthAfter = healthOf(current);
        return {
            status: 'stopped', step: 'wolfWitnessAction', reason: reason, action: action,
            continueAttempts: counts.continue, actionAttempts: counts.action, pauseAttempts: counts.pause,
            readOnlyPolls: counts.polls, healthBefore: healthBefore ? { current: healthBefore.current, max: healthBefore.max } : null,
            healthAfter: healthAfter ? { current: healthAfter.current, max: healthAfter.max } : null,
            pauseVerified: pauseVerified, frameId: current && current.frameId,
            elapsedMs: Math.max(0, api.now() - startedAt), rootDirected: true, questComplete: false, routeComplete: false
        };
    }
    return { run: run };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = ActOneWolfWitnessAction;
