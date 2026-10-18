(function (root) {
    'use strict';
    // Gauge costs from KQM's Abyss Mage data, restricted to the verified starter
    // party elements. These are planning rules, not a live-validated detector.
    const barrierCosts = {
        Cryo: { Pyro: 6, Electro: 12, Anemo: 24 },
        Hydro: { Cryo: 12, Electro: 15, Pyro: 24, Anemo: 24 },
        Pyro: { Electro: 12, Cryo: 24, Anemo: 24 },
        Electro: { Cryo: 8, Pyro: 8, Anemo: 16 }
    };
    function fresh(value, context) {
        return !!(value && value.session === context.session &&
            Number.isFinite(value.timestamp) && context.now >= value.timestamp &&
            context.now - value.timestamp <= 800 && value.frameId === context.frameId);
    }
    function classify(target, context) {
        if (!fresh(target, context) || !target.visible || !target.tracked ||
            !target.id || !(target.confidence >= .9)) return 'unknown';
        if (target.kind === 'material' && target.material === 'wood' && target.shieldVisible)
            return 'wood';
        if (target.kind === 'barrier' && target.family === 'AbyssMage' &&
            target.shieldVisible && barrierCosts[target.element]) return target.element;
        return 'unknown';
    }
    function decide(context, history) {
        history = history || {};
        const stop = reason => ({ action: 'retreat', reason, attackAllowed: false });
        if (!context.focusVerified || !context.sessionVerified || context.interrupted ||
            !Number.isFinite(context.healthRatio) || context.healthRatio < .95 ||
            !Number.isFinite(context.healthLossRatio) || context.healthLossRatio > .05)
            return stop('Focus, interruption or health guard');
        const kind = classify(context.target, context);
        if (kind === 'unknown') return stop('Unknown or stale shield identity');
        if ((history.attempts || 0) >= 2 || history.lastOutcome === 'no-effect')
            return stop('Bounded attempts exhausted or previous application ineffective');
        const costs = kind === 'wood' ? { Pyro: 1 } : barrierCosts[kind];
        const usable = (context.capabilities || []).filter(cap =>
            fresh(cap, context) && cap.partyVerified && cap.primitiveTested &&
            cap.ready === true && cap.cooldownReady === true &&
            (cap.energyRequired === false || cap.energyReady === true) &&
            cap.rangeVerified && cap.facingVerified && cap.targetId === context.target.id &&
            costs[cap.element] && Number.isFinite(cap.exposureMs) &&
            cap.exposureMs > 0 && cap.exposureMs <= context.remainingActionMs);
        usable.sort((a, b) => costs[a.element] - costs[b.element] || a.exposureMs - b.exposureMs);
        if (!usable.length) return stop('No fresh ready and in-range tested elemental primitive');
        return { action: 'apply-element', capability: usable[0].id,
            targetId: context.target.id, element: usable[0].element,
            maximumInputs: 1, verify: kind === 'wood' ? 'burning-then-shield-state' : 'barrier-gauge',
            damageRotationAllowed: false };
    }
    function verify(before, after, context) {
        const unknown = reason => ({ state: 'unknown', damageRotationAllowed: false, reason });
        if (!before || before.session !== context.session || !before.visible || !before.tracked ||
            !(before.confidence >= .9) || !['material', 'barrier'].includes(before.kind) || !fresh(after, context) || after.id !== before.id ||
            !after.visible || !after.tracked || !(after.confidence >= .9) ||
            after.timestamp <= before.timestamp) return unknown('Target continuity not verified');
        // A missing bar, disappeared target or damage number is never break proof.
        if (after.shieldVisible === false && after.bodyVisible && after.breakAnimationVerified &&
            after.unshieldedPoseVerified) return { state: 'removed', damageRotationAllowed: true };
        if (before.kind === 'material' && before.material === 'wood') {
            if (after.burningOnShieldVerified) return { state: 'burning', damageRotationAllowed: false };
        } else if (before.kind === 'barrier' && after.kind === 'barrier' &&
            before.element === after.element && after.gaugeTracked && before.gaugeTracked &&
            Number.isFinite(before.shieldFraction) && Number.isFinite(after.shieldFraction) &&
            after.shieldFraction >= 0 && before.shieldFraction <= 1 &&
            before.shieldFraction - after.shieldFraction >= .05)
            return { state: 'reduced', damageRotationAllowed: false };
        return unknown('No target-linked shield effect established');
    }
    root.ShieldResponse = { classify, decide, verify };
    if (typeof module !== 'undefined' && module.exports) module.exports = root.ShieldResponse;
})(typeof globalThis !== 'undefined' ? globalThis : this);
