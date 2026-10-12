var ActOneWolfSecondSpike = (function () {
    var RUN_LIMIT_MS = 35000, AFTER_SKILL_LIMIT_MS = 10000, FRESH_MS = 1000;
    var CONTINUE_SETTLE_MS = 450, SELECT_SETTLE_MS = 350, SKILL_SETTLE_MS = 700;
    var MOVE_SETTLE_MS = 180, ESCAPE_SETTLE_MS = 600, MAX_HEALTH_LOSS = 0.05;

    function healthOf(o) {
        var h = o && o.hud && o.hud.health;
        return h && Number.isFinite(h.current) && Number.isFinite(h.max) && h.max > 0 ? h : null;
    }
    function sameFrame(o, previous, session, api) {
        return !!o && Number.isInteger(o.frameId) && o.frameId >= 0 && Number.isFinite(o.timestamp) &&
            o.session === session && !!session && api.now() >= o.timestamp && api.now() - o.timestamp <= FRESH_MS &&
            (!previous || o.frameId > previous.frameId && o.timestamp > previous.timestamp);
    }
    function makeResult(current, counts, startedAt, api, ice, floor, paused, reason, crossingCharacter) {
        var hp = healthOf(current);
        return {
            status: 'stopped', step: 'wolfSpikeCrossSecond', frameId: current && current.frameId,
            reason: reason, continueAttempts: counts.continue, characterSelectionAttempts: counts.select,
            skillAttempts: counts.skill, movementAttempts: counts.move, alignmentObserveRetries: counts.alignment,
            iceObserveRetries: counts.icePolls, pauseAttempts: counts.pause, observeCount: counts.observe,
            sleepMs: counts.sleep, waitMs: counts.sleep, inputTimingsMs: counts.inputs, captureTimingsMs: counts.captures,
            elapsedMs: Math.max(0, api.now() - startedAt), initialHealth: counts.initialHealth,
            kaeyaHealth: counts.kaeyaHealth, amberHealth: counts.amberHealth, crossingCharacter: crossingCharacter,
            finalHealth: hp ? { current: hp.current, max: hp.max } : null,
            lastFrameId: current && current.frameId, lastTimestamp: current && current.timestamp,
            iceEffectVerified: ice, solidFloorReached: floor, pauseVerified: paused,
            questProgressVerified: false, questComplete: false, secondPitComplete: false
        };
    }
    async function runWolfSecondSpike(initial, api, observe) {
        var startedAt = api.now(), current = initial, session = initial && initial.session;
        var counts = { continue: 0, select: 0, skill: 0, move: 0, alignment: 0, icePolls: 0, pause: 0,
            observe: 0, sleep: 0, inputs: [], captures: [], initialHealth: null, kaeyaHealth: null, amberHealth: null };
        var ice = false, floor = false, paused = false;
        var reason = 'Second-pit attempt stopped at its bounded action limit', afterSkillAt = null, crossingCharacter = null;

        function deadline() {
            if (api.now() - startedAt >= RUN_LIMIT_MS) throw new Error('35-second second-pit deadline reached');
            if (afterSkillAt !== null && api.now() - afterSkillAt >= AFTER_SKILL_LIMIT_MS)
                throw new Error('10-second post-skill deadline reached');
        }
        async function sleep(ms, cleanup) {
            api.checkStop();
            if (!cleanup && (api.now() - startedAt + ms > RUN_LIMIT_MS ||
                afterSkillAt !== null && api.now() - afterSkillAt + ms > AFTER_SKILL_LIMIT_MS)) deadline();
            await api.sleep(ms); counts.sleep += ms; api.checkStop();
            if (!cleanup) deadline();
        }
        async function input(name, fn) {
            api.checkStop(); var t = api.now();
            try { await fn(); } finally { counts.inputs.push({ input: name, durationMs: Math.max(0, api.now() - t) }); }
        }
        async function fresh(previous, body, ratio) {
            api.checkStop(); var t = api.now(), next;
            try { next = await observe(); } finally { counts.captures.push(Math.max(0, api.now() - t)); counts.observe++; }
            api.checkStop();
            if (!sameFrame(next, previous, session, api)) throw new Error('Fresh distinct same-session frame required');
            if (typeof api.wolfSecondActiveReady !== 'function' || api.wolfSecondActiveReady(next, body, ratio) !== true)
                throw new Error('Second-pit active HUD, focus, floor, or health guard failed');
            current = next; return next;
        }
        async function pauseIfAllowed() {
            if (!current || !sameFrame(current, null, session, api) || typeof api.wolfSecondPauseReady !== 'function' ||
                api.wolfSecondPauseReady(current) !== true) return false;
            api.checkStop(); counts.pause++;
            await input('escape', api.wolfSecondEscape);
            await sleep(ESCAPE_SETTLE_MS, true);
            var t = api.now(), after;
            try { after = await observe(); } finally { counts.captures.push(Math.max(0, api.now() - t)); counts.observe++; }
            if (sameFrame(after, current, session, api) && api.wolfSecondPauseVerified(after) === true) {
                current = after; paused = true; return true;
            }
            return false;
        }

        try {
            var initialHp = healthOf(initial);
            if (!session || !Number.isInteger(initial && initial.frameId) || initial.frameId < 0 ||
                typeof api.wolfSecondContinueReady !== 'function' || api.wolfSecondContinueReady(initial) !== true)
                throw new Error('Fresh exact second-pit paused entry proof required');
            crossingCharacter = typeof api.wolfSecondCrossingCharacter === 'function' ? api.wolfSecondCrossingCharacter() : 'amber';
            if (crossingCharacter !== 'kaeya' && crossingCharacter !== 'amber')
                throw new Error('Second-pit crossing character must be kaeya or amber');
            counts.initialHealth = initialHp && { current: initialHp.current, max: initialHp.max };
            deadline(); counts.continue++;
            await input('continue', api.wolfSecondContinue);
            await sleep(CONTINUE_SETTLE_MS);
            current = await fresh(initial, 'any', 0.01);

            deadline(); counts.select++;
            await input('select-kaeya', api.wolfSecondSelectKaeya);
            var selectionSettle = typeof api.wolfSecondSelectionSettleMs === 'function' ? api.wolfSecondSelectionSettleMs() : SELECT_SETTLE_MS;
            if(selectionSettle!==0&&selectionSettle!==SELECT_SETTLE_MS)throw new Error('Invalid Kaeya selection settle plan');
            if(selectionSettle!==0) {
                await sleep(selectionSettle);
                current = await fresh(current, 'kaeya', 0.01);
            } else if(api.wolfSecondActiveReady(current,'kaeya',0.01)!==true)throw new Error('Already selected Kaeya proof failed');
            var kaeya = healthOf(current);
            if (!kaeya || kaeya.max !== 1427 || kaeya.current <= 0) throw new Error('Living Kaeya required for second-pit ice setup');
            counts.kaeyaHealth = { current: kaeya.current, max: kaeya.max };

            var plan = typeof api.wolfSecondCooldownPlan === 'function' ? api.wolfSecondCooldownPlan(current) : null;
            var cooldownMs = Number.isInteger(plan) && plan >= 0 && plan <= 6500 ? plan : 6500;
            var cooldownDeadline = api.now() + cooldownMs;
            while (api.now() < cooldownDeadline) {
                deadline(); await sleep(Math.min(1000, cooldownDeadline - api.now()));
            }
            current = await fresh(current, 'kaeya', 0.01);
            var afterCooldownHp = healthOf(current);
            if (!afterCooldownHp || afterCooldownHp.current !== kaeya.current || afterCooldownHp.max !== kaeya.max)
                throw new Error('Kaeya health changed before second-pit alignment');

            var aligned = typeof api.wolfSecondAlignedReady === 'function' && api.wolfSecondAlignedReady(current) === true;
            var alignmentLimit = crossingCharacter === 'kaeya' ? 24 : 8;
            while (!aligned && counts.alignment < alignmentLimit) {
                deadline(); await sleep(200); deadline();
                current = await fresh(current, 'kaeya', 0.01); counts.alignment++;
                var alignHp = healthOf(current);
                if (!alignHp || alignHp.current !== kaeya.current || alignHp.max !== kaeya.max)
                    throw new Error('Kaeya health changed during read-only second-pit alignment');
                aligned = api.wolfSecondAlignedReady(current) === true;
            }
            if (!aligned) throw new Error('Bilateral moving-block alignment was not positively verified');
            deadline(); counts.skill++;
            await input('cast-e', api.wolfSecondCast);
            afterSkillAt = api.now();
            await sleep(SKILL_SETTLE_MS); current = await fresh(current, 'kaeya', 0.01); deadline();
            var iceHp = healthOf(current);
            if (!iceHp || iceHp.current !== kaeya.current || iceHp.max !== kaeya.max)
                throw new Error('Kaeya health changed after second-pit skill');
            ice = typeof api.wolfSecondIceReady === 'function' && api.wolfSecondIceReady(current) === true;
            while (!ice && counts.icePolls < 3) {
                deadline(); await sleep(100); deadline(); current = await fresh(current, 'kaeya', 0.01); counts.icePolls++;
                var pollHp = healthOf(current);
                if (!pollHp || pollHp.current !== kaeya.current || pollHp.max !== kaeya.max)
                    throw new Error('Kaeya health changed during second-pit ice verification');
                ice = api.wolfSecondIceReady(current) === true;
            }
            if (!ice) throw new Error('Positive second-pit ice proof required before crossing');

            var mover, moveBody, moveRatio, baseline;
            if (crossingCharacter === 'kaeya') {
                mover = 'kaeya'; moveBody = 'kaeya'; moveRatio = 0.01; baseline = kaeya;
            } else {
                deadline(); counts.select++;
                await input('select-amber', api.wolfSecondSelectAmber);
                await sleep(SELECT_SETTLE_MS); current = await fresh(current, 'amber', 0.6);
                var amber = healthOf(current);
                if (!amber || amber.current / amber.max < 0.6) throw new Error('Amber below 60% health before second-pit movement');
                counts.amberHealth = { current: amber.current, max: amber.max };
                mover = 'amber'; moveBody = 'amber'; moveRatio = 0.6; baseline = amber;
            }
            for (var i = 0; i < 3; i++) {
                deadline(); counts.move++;
                await input('move-w', api.wolfSecondMove);
                await sleep(MOVE_SETTLE_MS); current = await fresh(current, moveBody, moveRatio);
                var movedHp = healthOf(current);
                if (mover === 'kaeya') {
                    if (!movedHp || movedHp.current !== baseline.current || movedHp.max !== baseline.max)
                        throw new Error('Kaeya health changed during second-pit crossing; further movement stopped');
                } else if (!movedHp || movedHp.max !== baseline.max ||
                    (baseline.current - movedHp.current) / baseline.max > MAX_HEALTH_LOSS)
                    throw new Error('Amber lost more than 5% health during second-pit movement');
                floor = typeof api.wolfSecondFloorReached === 'function' && api.wolfSecondFloorReached(current) === true;
                if (floor) { reason = 'Native adapter confirmed solid floor reached; second-pit completion is unverified'; break; }
            }
            if (!floor) reason = 'Three bounded second-pit moves ended without positive solid-floor evidence';
            await pauseIfAllowed();
            return makeResult(current, counts, startedAt, api, ice, floor, paused, reason, crossingCharacter);
        } catch (e) {
            reason = String(e && e.message || e || 'Second-pit attempt stopped');
            try {
                var t = api.now(), cleanup;
                try { cleanup = await observe(); } finally { counts.captures.push(Math.max(0, api.now() - t)); counts.observe++; }
                if (sameFrame(cleanup, current, session, api)) { current = cleanup; await pauseIfAllowed(); }
            } catch (_) { /* Keep the original bounded stop reason. */ }
            return makeResult(current, counts, startedAt, api, ice, floor, paused, reason, crossingCharacter);
        }
    }
    return { runWolfSecondSpike: runWolfSecondSpike };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = ActOneWolfSecondSpike;
