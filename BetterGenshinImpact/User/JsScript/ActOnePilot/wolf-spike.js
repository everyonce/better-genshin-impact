var ActOneWolfSpike = (function () {
    var RUN_LIMIT_MS = 25000;
    var AFTER_SKILL_LIMIT_MS = 10000;
    var MOVE_SETTLE_MS = 180;
    var FRESH_MS = 1000;
    var MAX_HEALTH_LOSS = 0.05;
    var CONTINUE_SETTLE_MS = 450;
    var SELECT_SETTLE_MS = 350;
    var SKILL_SETTLE_MS = 700;
    var ESCAPE_SETTLE_MS = 600;
    var MAX_BANK_RETRIES = 8;
    var BANK_POLL_MS = 500;
    var MAX_ICE_RETRIES = 3;
    var ICE_POLL_MS = 100;
    var JUMP_SETTLE_MS = 300;
    var LANDING_POLL_MS = 100;
    var MAX_LANDING_RETRIES = 2;

    function healthOf(o) {
        var h = o && o.hud && o.hud.health;
        return h && Number.isFinite(h.current) && Number.isFinite(h.max) && h.max > 0 ? h : null;
    }

    function sameFreshFrame(o, previous, session, api) {
        if (!o || !Number.isFinite(o.timestamp) || !Number.isInteger(o.frameId) || o.frameId < 0 ||
            o.session !== session || !session || api.now() < o.timestamp || api.now() - o.timestamp > FRESH_MS) return false;
        if (previous && (o.frameId <= previous.frameId || o.timestamp <= previous.timestamp)) return false;
        return true;
    }

    function result(status, reason, current, counts, startedAt, api, extras) {
        var hp = healthOf(current);
        var out = {
            status: status,
            step: 'wolfSpikeCrossFirst',
            frameId: current && current.frameId,
            reason: reason,
            continueAttempts: counts.continue,
            characterSelectionAttempts: counts.select,
            skillAttempts: counts.skill,
            movementAttempts: counts.move,
            jumpAttempts: counts.jump,
            landingObserveRetries: counts.landingObserveRetries,
            pauseAttempts: counts.pause,
            bankObserveRetries: counts.bankObserveRetries,
            iceObserveRetries: counts.iceObserveRetries,
            observeCount: counts.observe,
            sleepMs: counts.sleep,
            waitMs: counts.waitMs,
            inputTimingsMs: counts.inputTimingsMs,
            captureTimingsMs: counts.captureTimingsMs,
            elapsedMs: Math.max(0, api.now() - startedAt),
            initialHealth: counts.initialHealth,
            amberHealth: counts.amberHealth,
            finalHealth: hp ? { current: hp.current, max: hp.max } : null,
            lastFrameId: current && current.frameId,
            lastTimestamp: current && current.timestamp,
            iceEffectVerified: false,
            questProgressVerified: false,
            questComplete: false,
            landingVerified: false,
            pauseVerified: false
        };
        if (extras) Object.keys(extras).forEach(function (k) { out[k] = extras[k]; });
        return out;
    }

    async function runWolfSpike(initial, api, observe) {
        var startedAt = api.now();
        var counts = { continue: 0, select: 0, skill: 0, move: 0, jump: 0, landingObserveRetries: 0, pause: 0, observe: 0, sleep: 0,
            waitMs: 0, inputTimingsMs: [], captureTimingsMs: [], bankObserveRetries: 0, iceObserveRetries: 0,
            initialHealth: null, amberHealth: null };
        var current = initial;
        var session = initial && initial.session;
        var reason = 'Spike pit attempt stopped at its bounded action limit';
        var iceVerified = false, landingVerified = false, paused = false;
        var existingIceOnFresh = false, existingIceReused = false, afterSkillAt = null;
        var cooldownWaitMs = 0, cooldownSource = 'existing-ice';
        var crossingCharacter = 'amber', crossingHealth = null;
        var landingContinuation = false;
        var crossingPlan = { character: 'amber', minRatio: 0.6, moveMs: 500, maxMoves: 3 };

        async function sleep(ms, allowOverrun) {
            api.checkStop();
            if (!allowOverrun && api.now() - startedAt + ms > RUN_LIMIT_MS) throw new Error('25-second spike phase deadline reached');
            await api.sleep(ms);
            counts.sleep += ms;
            counts.waitMs += ms;
            api.checkStop();
        }

        function enforceDeadlines(afterSkillAt) {
            if (api.now() - startedAt >= RUN_LIMIT_MS) throw new Error('25-second spike phase deadline reached');
            if (afterSkillAt !== null && api.now() - afterSkillAt >= AFTER_SKILL_LIMIT_MS)
                throw new Error('10-second post-skill deadline reached');
        }

        async function input(name, fn) {
            api.checkStop();
            var t = api.now();
            try { await fn(); }
            finally { counts.inputTimingsMs.push({ input: name, durationMs: Math.max(0, api.now() - t) }); }
        }

        async function fresh(previous, body, minRatio, allowBankWait, allowExistingIce) {
            api.checkStop();
            var captureStarted = api.now();
            var next;
            try { next = await observe(); }
            finally {
                counts.captureTimingsMs.push(Math.max(0, api.now() - captureStarted));
                counts.observe++;
            }
            api.checkStop();
            if (!sameFreshFrame(next, previous, session, api)) throw new Error('Fresh distinct same-session observation required');
            var activeReady = typeof api.wolfSpikeActiveReady === 'function' &&
                api.wolfSpikeActiveReady(next, body || 'any', minRatio || 0) === true;
            var bankWaitReady = allowBankWait === true && typeof api.wolfSpikeBankWaitReady === 'function' &&
                api.wolfSpikeBankWaitReady(next) === true;
            var existingIceReady = allowExistingIce === true && typeof api.wolfSpikeExistingIceReady === 'function' &&
                api.wolfSpikeExistingIceReady(next) === true;
            if (!activeReady && !bankWaitReady && !existingIceReady) throw new Error('Wolf spike HUD is unsafe or ambiguous');
            current = next;
            existingIceOnFresh = existingIceReady;
            return next;
        }

        async function pauseIfAllowed(trigger) {
            if (!current || !sameFreshFrame(current, null, session, api) ||
                typeof api.wolfSpikePauseReady !== 'function' || !api.wolfSpikePauseReady(current)) return false;
            api.checkStop();
            counts.pause++;
            await input('escape', api.wolfSpikeEscape);
            await sleep(ESCAPE_SETTLE_MS, true);
            var captureStarted = api.now();
            var after;
            try { after = await observe(); }
            finally {
                counts.captureTimingsMs.push(Math.max(0, api.now() - captureStarted));
                counts.observe++;
            }
            if (sameFreshFrame(after, current, session, api) && api.wolfSpikePauseVerified(after)) {
                current = after;
                paused = true;
                return true;
            }
            return false;
        }

        try {
            var beforeHp = healthOf(initial);
            if (!session || !Number.isInteger(initial && initial.frameId) || initial.frameId < 0 ||
                typeof api.wolfSpikeContinueReady !== 'function' || !api.wolfSpikeContinueReady(initial))
                return result('stopped', 'Fresh paused-bank entry proof and starter-party health required', initial, counts, startedAt, api);
            counts.initialHealth = beforeHp ? { current: beforeHp.current, max: beforeHp.max } : null;

            enforceDeadlines(null); api.checkStop(); counts.continue++;
            await input('continue', api.wolfSpikeContinue);
            await sleep(CONTINUE_SETTLE_MS);
            current = await fresh(initial, 'any', 0, true, true);

            existingIceReused = existingIceOnFresh;
            if (existingIceReused) {
                var existingKaeyaHp = healthOf(current);
                if (!existingKaeyaHp || existingKaeyaHp.max !== 1427 || existingKaeyaHp.current <= 0)
                    throw new Error('Existing ice proof requires living Kaeya 1427 HP');
                iceVerified = true;
                afterSkillAt = api.now();
            } else {
                var bankActive = api.wolfSpikeActiveReady(current, 'any', 0) === true;
                for (var bankPoll = 0; !bankActive && bankPoll < MAX_BANK_RETRIES; bankPoll++) {
                    await sleep(BANK_POLL_MS);
                    current = await fresh(current, 'any', 0, true);
                    counts.bankObserveRetries++;
                    bankActive = api.wolfSpikeActiveReady(current, 'any', 0) === true;
                }
                if (!bankActive) throw new Error('Safe first-bank reacquisition did not reach the active Wolf HUD');

                enforceDeadlines(null);
                counts.select++;
                await input('select-kaeya', api.wolfSpikeSelectKaeya);
                await sleep(SELECT_SETTLE_MS);
                current = await fresh(current, 'kaeya', 0);

                var plan = typeof api.wolfSpikeCooldownPlan === 'function' ? api.wolfSpikeCooldownPlan(current) : null;
                cooldownSource = Number.isInteger(plan) && plan >= 0 && plan <= 6500 ? 'adapter' : '6500ms-fallback';
                cooldownWaitMs = cooldownSource === 'adapter' ? plan : 6500;
                var cooldownDeadline = api.now() + cooldownWaitMs;
                while (api.now() < cooldownDeadline) {
                    var slice = Math.min(1000, cooldownDeadline - api.now());
                    await sleep(slice);
                    current = await fresh(current, 'kaeya', 0);
                }

                var kaeyaBeforeSkill = healthOf(current);
                if (!kaeyaBeforeSkill || kaeyaBeforeSkill.max !== 1427 || kaeyaBeforeSkill.current <= 0)
                    throw new Error('Living Kaeya 1427 HP required before the first-spike skill');
                enforceDeadlines(null); api.checkStop(); counts.skill++;
                await input('cast-e', api.wolfSpikeCast);
                afterSkillAt = api.now();
                await sleep(SKILL_SETTLE_MS);
                current = await fresh(current, 'kaeya', 0);
                enforceDeadlines(afterSkillAt);
                var kaeyaHp = healthOf(current);
                if (!kaeyaHp || kaeyaHp.max !== 1427 || kaeyaHp.current <= 0 || kaeyaHp.current < kaeyaBeforeSkill.current)
                    throw new Error('Fresh living Kaeya 1427 HP required while waiting for first-spike ice evidence');
                iceVerified = typeof api.wolfSpikeIceReady === 'function' && api.wolfSpikeIceReady(current) === true;
                while (!iceVerified && counts.iceObserveRetries < MAX_ICE_RETRIES) {
                    enforceDeadlines(afterSkillAt);
                    await sleep(ICE_POLL_MS);
                    enforceDeadlines(afterSkillAt);
                    counts.iceObserveRetries++;
                    current = await fresh(current, 'kaeya', 0);
                    enforceDeadlines(afterSkillAt);
                    var pollingHp = healthOf(current);
                    if (!pollingHp || pollingHp.max !== kaeyaHp.max || pollingHp.current <= 0 || pollingHp.current < kaeyaHp.current)
                        throw new Error('Kaeya HP or strict active HUD changed during spike ice polling');
                    iceVerified = typeof api.wolfSpikeIceReady === 'function' && api.wolfSpikeIceReady(current) === true;
                }
                if (!iceVerified) throw new Error('Positive first-spike ice evidence required before selecting Amber or moving');
            }

            enforceDeadlines(afterSkillAt);
            var requestedPlan = typeof api.wolfSpikeCrossingPlan === 'function' ? api.wolfSpikeCrossingPlan() : null;
            if (requestedPlan !== null && requestedPlan !== undefined) {
                if (requestedPlan.character === 'kaeya' && requestedPlan.minRatio === 0.01 && requestedPlan.moveMs === 200 &&
                    requestedPlan.maxMoves === 1 && requestedPlan.landingContinuation === true && existingIceReused) {
                    crossingPlan = requestedPlan;
                    crossingCharacter = 'kaeya';
                    landingContinuation = true;
                } else if (requestedPlan.character === 'kaeya' && requestedPlan.minRatio === 0.01 && requestedPlan.moveMs === 800 &&
                    requestedPlan.maxMoves === 2 && requestedPlan.landingContinuation !== true) {
                    crossingPlan = requestedPlan;
                    crossingCharacter = 'kaeya';
                } else if (requestedPlan.character === 'amber' && requestedPlan.minRatio === 0.6 && requestedPlan.moveMs === 500 &&
                    requestedPlan.maxMoves === 3 && requestedPlan.landingContinuation !== true) {
                    crossingPlan = requestedPlan;
                } else throw new Error('Crossing plan was not an approved bounded Kaeya or Amber route');
            }

            if (crossingCharacter === 'amber') {
                counts.select++;
                await input('select-amber', api.wolfSpikeSelectAmber);
                await sleep(SELECT_SETTLE_MS);
                current = await fresh(current, 'amber', crossingPlan.minRatio);
            } else if (!sameFreshFrame(current, null, session, api) ||
                (!landingContinuation && api.wolfSpikeActiveReady(current, 'kaeya', crossingPlan.minRatio) !== true)) {
                throw new Error('Fresh safe Kaeya frame required for the approved Kaeya crossing plan');
            }
            var crossingHp = healthOf(current);
            if (!crossingHp || crossingHp.current / crossingHp.max < crossingPlan.minRatio ||
                (crossingCharacter === 'kaeya' && (crossingHp.max !== 1427 || crossingHp.current <= 0)))
                throw new Error('Crossing character health is below its approved route threshold');
            crossingHealth = { current: crossingHp.current, max: crossingHp.max };
            if (crossingCharacter === 'amber') counts.amberHealth = crossingHealth;

            if (landingContinuation && typeof api.wolfSpikeLandingReady === 'function' && api.wolfSpikeLandingReady(current) === true) {
                landingVerified = true;
                reason = 'Native adapter confirmed the existing first-platform landing';
            }

            for (var i = 0; !landingVerified && i < crossingPlan.maxMoves; i++) {
                enforceDeadlines(afterSkillAt);
                api.checkStop(); counts.move++;
                await input('move-w', function () { return api.wolfSpikeMove(crossingPlan.moveMs); });
                await sleep(MOVE_SETTLE_MS);
                current = await fresh(current, crossingCharacter, crossingPlan.minRatio);
                var hp = healthOf(current);
                if (!hp || hp.max !== crossingHp.max || (crossingHp.current - hp.current) / crossingHp.max > MAX_HEALTH_LOSS)
                    throw new Error(crossingCharacter + ' lost more than 5% health; stopping movement');
                if (typeof api.wolfSpikeLandingReady === 'function' && api.wolfSpikeLandingReady(current) === true) {
                    landingVerified = true;
                    reason = 'Adapter confirmed the first spike-pit landing state';
                    break;
                }
                if (crossingCharacter === 'amber' && counts.move >= crossingPlan.maxMoves) {
                    var lipReady = typeof api.wolfSpikeLipReady === 'function' && api.wolfSpikeLipReady(current) === true;
                    if (!lipReady) {
                        reason = 'First-pit lip was not positively verified after three bounded W inputs; stopped before further movement';
                        break;
                    }
                    enforceDeadlines(afterSkillAt);
                    api.checkStop(); counts.jump++;
                    await input('landing-jump', api.wolfSpikeLandingJump);
                    await sleep(JUMP_SETTLE_MS);
                    current = await fresh(current, 'amber', crossingPlan.minRatio);
                    hp = healthOf(current);
                    if (!hp || hp.max !== crossingHp.max || (crossingHp.current - hp.current) / crossingHp.max > MAX_HEALTH_LOSS)
                        throw new Error('Amber lost more than 5% health after the lip jump; stopping');
                    if (typeof api.wolfSpikeLandingReady === 'function' && api.wolfSpikeLandingReady(current) === true) {
                        landingVerified = true;
                        reason = 'Adapter confirmed the first spike-pit landing after the lip jump';
                        break;
                    }
                    for (var landingPoll = 0; landingPoll < MAX_LANDING_RETRIES && !landingVerified; landingPoll++) {
                        enforceDeadlines(afterSkillAt);
                        await sleep(LANDING_POLL_MS);
                        enforceDeadlines(afterSkillAt);
                        current = await fresh(current, 'amber', crossingPlan.minRatio);
                        counts.landingObserveRetries++;
                        hp = healthOf(current);
                        if (!hp || hp.max !== crossingHp.max || (crossingHp.current - hp.current) / crossingHp.max > MAX_HEALTH_LOSS)
                            throw new Error('Amber lost more than 5% health while verifying the lip jump landing');
                        if (typeof api.wolfSpikeLandingReady === 'function' && api.wolfSpikeLandingReady(current) === true) {
                            landingVerified = true;
                            reason = 'Adapter confirmed the first spike-pit landing after the lip jump';
                        }
                    }
                    if (!landingVerified) reason = 'Lip jump completed but positive landing evidence did not arrive within two polls';
                    break;
                }
            }
            await pauseIfAllowed(landingVerified ? 'landing' : 'bounded-stop');
            return result('stopped', paused ? reason + '; pause verified' : reason + '; pause not verified', current,
                counts, startedAt, api, { iceEffectVerified: iceVerified, landingVerified: landingVerified, pauseVerified: paused,
                    existingIceReused: existingIceReused, crossingCharacter: crossingCharacter, crossingHealth: crossingHealth,
                    landingContinuation: landingContinuation,
                    cooldownWaitMs: cooldownWaitMs, cooldownSource: cooldownSource });
        } catch (e) {
            reason = String(e && e.message || e || 'Spike phase stopped');
            // On an input exception, observe current state before considering Escape cleanup.
            try {
                var captureStarted = api.now();
                var cleanup;
                try { cleanup = await observe(); }
                finally {
                    counts.captureTimingsMs.push(Math.max(0, api.now() - captureStarted));
                    counts.observe++;
                }
                if (sameFreshFrame(cleanup, current, session, api)) {
                    current = cleanup;
                    await pauseIfAllowed('exception');
                }
            } catch (_) { /* retain the original stop reason */ }
            return result('stopped', reason + (paused ? '; pause verified' : ''), current, counts, startedAt, api,
                { iceEffectVerified: iceVerified, landingVerified: landingVerified, pauseVerified: paused, existingIceReused: existingIceReused,
                    crossingCharacter: crossingCharacter, crossingHealth: crossingHealth, landingContinuation: landingContinuation });
        }
    }

    return { runWolfSpike: runWolfSpike };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = ActOneWolfSpike;
