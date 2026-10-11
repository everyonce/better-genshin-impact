// Conservative, OCR-only policy for the English Unexpected Power tutorial.
var UnexpectedPowerPolicy = (function () {
    var MAX_RUN_MS = 120000;
    var UNKNOWN_OBSERVATIONS = 3;
    var MAX_ATTEMPTS = 3;
    var RETRY_DELAY_MS = 3000;

    function norm(value) {
        return String(value == null ? '' : value).toLowerCase()
            .replace(/[^a-z0-9]+/g, ' ').trim().replace(/\s+/g, ' ');
    }
    function inBox(row, x1, y1, x2, y2) {
        return typeof row.x === 'number' && typeof row.y === 'number' &&
            row.x >= x1 && row.x <= x2 && row.y >= y1 && row.y <= y2;
    }
    function promptNorm(text) {
        return norm(text).replace(/^e (?=(press|hold) e )/, '').replace(/^q (?=press q )/, '');
    }
    function classify(rows) {
        if (!Array.isArray(rows)) return { kind: 'unknown', reason: 'invalid_ocr' };
        var texts = rows.map(function (r) { return norm(r && r.text); });
        // Completion requires the exact quest name and completion label in one nearby group.
        for (var i = 0; i < rows.length; i++) {
            for (var j = 0; j < rows.length; j++) {
                if (texts[i] === 'unexpected power' && texts[j] === 'quest completed' &&
                    i !== j && Math.abs((rows[i].y || 0) - (rows[j].y || 0)) <= 100) {
                    return { kind: 'completed', reason: 'quest_completed' };
                }
            }
        }
        var headings = rows.filter(function (r) {
            var t = norm(r && r.text);
            return inBox(r || {}, 800, 80, 1800, 200) &&
                (t === 'unexpected power' || t === 'forest rendezvous');
        });
        var statuses = rows.filter(function (r) { return norm(r && r.text) === 'in progress'; });
        if (headings.length || statuses.length) {
            if (headings.length !== 1 || statuses.length !== 1 ||
                Math.abs((headings[0].y || 0) - (statuses[0].y || 0)) > 220)
                return { kind: 'unknown', reason: 'ambiguous_journal' };
            var heading = norm(headings[0].text);
            if (heading === 'unexpected power') return { kind: 'targetJournal' };
            if (heading === 'forest rendezvous') return { kind: 'nextJournal', title: 'Forest Rendezvous' };
        }
        var prompts = [
            ['press e to unleash elemental skill', 'tap_skill', 'E', 60],
            ['hold e to unleash elemental skill', 'hold_skill', 'E', 1200],
            ['hold e to charge skills for increased power', 'hold_skill', 'E', 1200],
            ['press q to unleash elemental burst', 'burst', 'Q', 60]
        ];
        var found = [];
        rows.forEach(function (r) {
            if (!r || !inBox(r, 400, 100, 1400, 350)) return;
            var t = promptNorm(r.text);
            prompts.forEach(function (p) { if (t === p[0]) found.push({
                kind: 'tutorialAction', prompt: t,
                action: { type: p[1], key: p[2], ms: p[3] }
            }); });
        });
        // The observed English hold tutorial wraps onto two adjacent lines.
        // Join only that exact pair; never combine arbitrary screen text.
        rows.forEach(function (first) {
            if (!first || !inBox(first, 400, 100, 1400, 300) ||
                promptNorm(first.text) !== 'hold e to charge skills for increased') return;
            rows.forEach(function (second) {
                if (second && norm(second.text) === 'power' &&
                    second.y > first.y && second.y - first.y < 65 &&
                    Math.abs(second.x - first.x) < 400) found.push({ kind: 'tutorialAction',
                        prompt: 'hold e to charge skills for increased power',
                        action: { type: 'hold_skill', key: 'E', ms: 1200 } });
            });
        });
        if (found.length === 1) return found[0];
        return { kind: 'unknown', reason: found.length > 1 ? 'ambiguous_prompt' : 'unrecognized_state' };
    }
    function validateAction(action, observedState) {
        if (!action || !observedState || observedState.kind !== 'tutorialAction' || !observedState.action)
            return { ok: false, reason: 'action_requires_observed_tutorial_prompt' };
        var expected = observedState.action;
        if (action.type !== expected.type || action.key !== expected.key || action.ms !== expected.ms)
            return { ok: false, reason: 'action_does_not_match_prompt' };
        if (!((action.type === 'tap_skill' && action.key === 'E' && action.ms === 60) ||
            (action.type === 'hold_skill' && action.key === 'E' && action.ms === 1200) ||
            (action.type === 'burst' && action.key === 'Q' && action.ms === 60)))
            return { ok: false, reason: 'action_outside_allowlist' };
        return { ok: true, reason: null };
    }
    async function run(api) {
        var started = api.now(), actions = [], transitions = [], interventions = [], observations = [], stoppedReason = null;
        var previousPrompt = null, unchangedPromptAttempts = 0, unknownCount = 0, openedJournal = false;
        function snapshot(phase) {
            api.saveStatus({ phase: phase, actions: actions.slice(), transitions: transitions.slice(),
                interventions: interventions.slice(), observations: observations.slice(), stoppedReason: stoppedReason,
                elapsedMs: Math.max(0, api.now() - started) });
        }
        function checkTime() { if (api.now() - started >= MAX_RUN_MS) throw new Error('duration_limit'); }
        async function observe() {
            checkTime();
            var raw = await api.observe();
            var state = raw && raw.kind ? raw : classify(Array.isArray(raw) ? raw : raw && raw.rows);
            var item = { at: api.now(), mode: raw && raw.mode || null, kind: state.kind };
            observations.push(item); snapshot('observed');
            return { raw: raw, state: state };
        }
        async function beforeInput(type, detail) {
            checkTime();
            await api.assertReady();
            checkTime();
            actions.push({ type: type, detail: detail || null, phase: 'started', at: api.now() });
            snapshot('action_started');
        }
        function afterInput(type) {
            var entry = actions[actions.length - 1];
            if (entry && entry.type === type && entry.phase === 'started') entry.phase = 'completed';
            if (entry) entry.finishedAt = api.now();
            snapshot('action_completed');
        }
        async function pauseAndObserve(ms) {
            await api.wait(ms);
            checkTime();
            await api.assertReady();
            return await observe();
        }
        function transition(from, to) {
            transitions.push({ from: from, to: to, at: api.now() }); snapshot('transition');
        }
        try {
            var current = await observe(), state = current.state;
            if (state.kind !== 'targetJournal') {
                stoppedReason = state.kind === 'nextJournal' ? 'next_quest_requires_target_confirmation' : 'target_journal_not_confirmed';
                return { status: 'stopped', stoppedReason: stoppedReason, actions: actions, transitions: transitions, interventions: interventions };
            }
            if (state.kind === 'targetJournal') {
                transition('start', 'targetJournal');
                await beforeInput('closeJournal');
                await api.closeJournal(); afterInput('closeJournal');
                current = await observe(); state = current.state;
            }
            while (true) {
                if (state.kind === 'completed') { transition('targetQuest', 'completed'); stoppedReason = 'quest_completed'; break; }
                if (state.kind === 'nextJournal') { transition('targetQuest', 'nextJournal'); stoppedReason = 'next_quest_reached_after_target'; break; }
                if (state.kind === 'tutorialAction') {
                    unknownCount = 0;
                    var prompt = state.prompt;
                    if (previousPrompt !== null && prompt !== previousPrompt) unchangedPromptAttempts = 0;
                    if (unchangedPromptAttempts >= MAX_ATTEMPTS) { stoppedReason = 'prompt_stalled'; break; }
                    if (previousPrompt !== null && prompt === previousPrompt && unchangedPromptAttempts > 0) {
                        current = await pauseAndObserve(RETRY_DELAY_MS);
                        state = current.state;
                        if (state.kind !== 'tutorialAction') continue;
                        // Retry only from this newly captured OCR; never reuse the stale prompt.
                        if (state.prompt !== previousPrompt) { unchangedPromptAttempts = 0; continue; }
                        prompt = state.prompt;
                    }
                    var valid = validateAction(state.action, state);
                    if (!valid.ok) { stoppedReason = valid.reason; break; }
                    var priorKind = actions.filter(function (a) { return a.type === 'tutorialAction' && a.phase === 'completed'; });
                    var lastTutorial = priorKind.length ? priorKind[priorKind.length - 1].detail : null;
                    if (lastTutorial && lastTutorial !== state.action.type && prompt === previousPrompt) {
                        stoppedReason = 'prompt_did_not_change_between_actions'; break;
                    }
                    await beforeInput('tutorialAction', state.action.type);
                    try { await api.hold(state.action.key, state.action.ms); }
                    finally { api.release(); }
                    afterInput('tutorialAction');
                    unchangedPromptAttempts++;
                    previousPrompt = prompt;
                    transition('tutorialAction', state.action.type);
                    current = await pauseAndObserve(250); state = current.state;
                    if (state.kind === 'tutorialAction' && state.prompt !== prompt) unchangedPromptAttempts = 0;
                    continue;
                }
                // verifiedWorld is adapter evidence, not an OCR classification. Wait for
                // three fresh frames before opening the journal, and never send combat input.
                if (current.raw && current.raw.mode === 'verifiedWorld' && !openedJournal) {
                    unknownCount++;
                    if (unknownCount < UNKNOWN_OBSERVATIONS) {
                        current = await pauseAndObserve(250); state = current.state; continue;
                    }
                    openedJournal = true;
                    await beforeInput('openJournal');
                    await api.openJournal(); afterInput('openJournal');
                    current = await pauseAndObserve(250); state = current.state;
                    if (state.kind === 'targetJournal') {
                        transition('verifiedWorld', 'targetJournal');
                        stoppedReason = 'target_journal_reconfirmed'; break;
                    }
                    if (state.kind === 'nextJournal') { transition('targetQuest', 'nextJournal'); stoppedReason = 'next_quest_reached_after_target'; break; }
                    continue;
                }
                if (state.kind === 'unknown') {
                    unknownCount++;
                    if (unknownCount >= UNKNOWN_OBSERVATIONS) { stoppedReason = 'unknown_state'; break; }
                    current = await pauseAndObserve(250); state = current.state; continue;
                }
                stoppedReason = 'unexpected_state'; break;
            }
        } catch (error) { stoppedReason = String(error && error.message || error); }
        finally {
            try { api.release(); } catch (_) { /* Preserve the primary stop reason. */ }
            snapshot('stopped');
        }
        return { status: stoppedReason === 'quest_completed' || stoppedReason === 'next_quest_reached_after_target' ? 'completed' : 'stopped',
            stoppedReason: stoppedReason, actions: actions, transitions: transitions, interventions: interventions };
    }
    return { classify: classify, validateAction: validateAction, run: run };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = UnexpectedPowerPolicy;
