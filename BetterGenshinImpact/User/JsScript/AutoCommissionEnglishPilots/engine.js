// English commission pilot runner. This module has no BetterGI or OS side effects.
var EnglishPilots = (function () {
    function normalize(text) {
        return String(text || '').normalize('NFKC').toLowerCase().replace(/[^a-z0-9]/g, '');
    }

    // Match a complete OCR line or at most three spatially adjacent wrapped lines.
    // Do not substring-match: "Not the Librarian" must never match "Librarian".
    function exactMatches(lines, texts) {
        var wanted = texts.map(normalize).filter(Boolean);
        var sorted = lines.filter(function (r) { return r.text && r.width > 0 && r.height > 0; })
            .slice().sort(function (a, b) { return a.y - b.y || a.x - b.x; });
        var hits = [];
        for (var i = 0; i < sorted.length; i++) {
            var words = '', previous = null;
            for (var j = i; j < Math.min(i + 3, sorted.length); j++) {
                var row = sorted[j];
                if (previous && (Math.abs(row.x - sorted[i].x) > 60 ||
                    row.y - previous.y < previous.height * 0.6 ||
                    row.y - (previous.y + previous.height) > 16)) break;
                words += row.text;
                if (wanted.indexOf(normalize(words)) >= 0) {
                    hits.push({ text: words, x: sorted[i].x, y: sorted[i].y,
                        width: sorted[i].width, height: sorted[i].height });
                }
                previous = row;
            }
        }
        return hits;
    }

    function uniqueMatch(lines, texts) {
        var matches = exactMatches(lines, texts);
        return matches.length === 1 ? matches[0] : null;
    }

    function preferredMatch(lines, texts) {
        for (var i = 0; i < texts.length; i++) {
            var matches = exactMatches(lines, [texts[i]]);
            if (matches.length > 1) return null;
            if (matches.length === 1) return matches[0];
        }
        return null;
    }

    function validate(pilots, plans, read) {
        if (!pilots || !Array.isArray(pilots.pilots) || pilots.pilots.length !== 3) {
            throw new Error('The three-pilot catalog is missing or invalid.');
        }
        plans.forEach(function (plan) {
            var pilot = pilots.pilots.find(function (p) { return p.id === plan.id; });
            if (!pilot) throw new Error('A pilot definition is missing. Reinstall this package.');
            plan.stages.forEach(function (stage) {
                var path = pilot.routes.filter(function (p) { return !p.endsWith('/process.json'); })[stage.route];
                if (!path || path.indexOf('..') >= 0 || path.indexOf('assets/') !== 0) {
                    throw new Error('Invalid route reference for ' + pilot.title + '.');
                }
                var route = JSON.parse(read(path));
                if (!route.info || !Array.isArray(route.positions) || !route.positions.length) {
                    throw new Error('Missing route data for ' + pilot.title + '.');
                }
                route.positions.forEach(function (point) {
                    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) {
                        throw new Error('Invalid waypoint for ' + pilot.title + '.');
                    }
                });
            });
        });
    }

    function settingsFor(raw, plans) {
        var title = String(raw.pilot || plans[0].title);
        var plan = plans.find(function (p) { return p.title === title; });
        if (!plan) throw new Error('Choose one of the three English pilot commissions in script settings.');
        var seconds = Number(raw.dialogueTimeoutSeconds || 120);
        if (!Number.isInteger(seconds) || seconds < 30 || seconds > 300) {
            throw new Error('Dialogue timeout must be a whole number from 30 to 300 seconds.');
        }
        return { plan: plan, timeoutMs: seconds * 1000, checkOnly: raw.checkOnly === true,
            manualChoices: raw.manualChoices === true };
    }

    function makeRunner(api) {
        var completed = false, completionArmed = false, progressed = false;
        function hasCompletion(frame) { return !!uniqueMatch(frame.completion, ['Commission Complete', 'Commission Completed']); }
        function observe(frame) {
            if (completionArmed && progressed && hasCompletion(frame)) completed = true;
            return frame;
        }
        async function frame() { await api.sleep(1); return observe(api.capture()); }
        async function press(key) { await api.sleep(1); api.key(key); await api.sleep(350); }

        async function verifyQuest(pilot) {
            if (!(await frame()).hud) throw new Error('Start from the normal game screen with menus closed.');
            await press('VK_J');
            await api.sleep(1000);
            var found = false;
            try {
                for (var attempt = 0; attempt < 4; attempt++) {
                    // The title can appear in both the list and detail pane; no click is made here.
                    if (exactMatches(api.journal(), [pilot.title].concat(pilot.display_aliases || [])).length > 0) { found = true; break; }
                    await api.sleep(500);
                }
            } finally {
                // A cancelled sleep throws before further input; never undo a user's manual stop.
                await press('VK_ESCAPE');
            }
            if (!found) throw new Error('Could not read "' + pilot.title + '" in the English quest journal. Select that active commission in J, close the menu, and retry. No route was started.');
            var baseline = await frame();
            if (!baseline.hud) throw new Error('The quest journal did not close to the game screen. Stop and close it manually.');
            for (var wait = 0; hasCompletion(baseline) && wait < 20; wait++) {
                await api.sleep(500);
                baseline = await frame();
            }
            if (hasCompletion(baseline)) throw new Error('A previous completion banner is still visible. Wait for it to disappear and retry. No route was started.');
            completionArmed = true;
        }

        async function conversation(stage, state, options) {
            var before = await frame();
            if (completed) return;
            var npc = preferredMatch(before.interactions, stage.npcs);
            if (!before.hud || !npc) throw new Error('Expected NPC not visible: ' + stage.npcs.join(' / ') + '. The route may have failed, or this quest is at a different stage.');
            // Select the verified interaction, not whichever unrelated F prompt is first.
            await api.interact(npc);
            var deadline = api.now() + options.timeoutMs;
            var entered = false, stableHud = 0, lastChoice = '';
            var warned = false;
            while (api.now() < deadline) {
                var current = await frame();
                if (completed) return;
                if (!current.hud) entered = true;
                if (entered && current.hud) {
                    if (++stableHud >= 3) return;
                } else stableHud = 0;
                if (entered && !current.hud) {
                    var allowed = stage.choices || [];
                    if (state.answers) allowed = allowed.concat(state.answers[state.answerIndex] || []);
                    var match = options.manualChoices ? null : preferredMatch(current.options, allowed);
                    var signature = current.options.map(function (r) { return normalize(r.text); }).join('|');
                    if (match && signature !== lastChoice) {
                        await api.sleep(1);
                        api.click(match);
                        lastChoice = signature;
                        if (state.answers && uniqueMatch([match], state.answers[state.answerIndex] || [])) state.answerIndex++;
                        api.info('Selected: ' + match.text);
                        await api.sleep(900);
                    } else if (!warned && current.options.length > 0) {
                        api.info('Waiting for a recognized answer. You may choose dialogue or submit the requested item manually; the pilot will resume.');
                        warned = true;
                    }
                }
                await api.sleep(400);
            }
            throw new Error('Dialogue did not finish within the configured timeout. No later route was started. Finish the current interaction manually before retrying.');
        }

        return {
            run: async function (catalog, plans, raw) {
                completed = false; completionArmed = false; progressed = false;
                validate(catalog, plans, api.read);
                var options = settingsFor(raw, plans), plan = options.plan;
                var pilot = catalog.pilots.find(function (p) { return p.id === plan.id; });
                api.info('English commission pilot: ' + pilot.title);
                if (options.checkOnly) { api.info('All three pilot definitions and route files passed validation. No game input was sent.'); return 'checked'; }
                var size = api.metrics();
                if (size[0] !== 1920 || size[1] !== 1080) throw new Error('These pilots require a 1920 x 1080 game client. The RDP desktop can remain 2560 x 1440.');
                if (plan.requirements) api.info(plan.requirements);
                await verifyQuest(pilot);
                var owned = false;
                var state = { answers: plan.answers || null, answerIndex: 0 };
                try {
                    owned = true;
                    api.enableDialogue();
                    var paths = pilot.routes.filter(function (p) { return !p.endsWith('/process.json'); });
                    for (var i = 0; i < plan.stages.length && !completed; i++) {
                        var stage = plan.stages[i];
                        var route = JSON.parse(api.read(paths[stage.route]));
                        // Change display metadata in memory only; all waypoints/actions stay untouched.
                        route.info.name = pilot.title + ' - route ' + (i + 1);
                        route.info.description = route.info.name;
                        api.info('Following route ' + (i + 1) + ' of ' + plan.stages.length + '.');
                        await api.path(JSON.stringify(route));
                        await api.sleep(1); // Honor cancellation before any later input.
                        progressed = true;
                        for (var pass = 0; pass < stage.talks && !completed; pass++) {
                            await conversation(stage, state, options);
                            await api.sleep(800);
                        }
                    }
                    // Allow the final dialogue/reward banner to appear.
                    for (var wait = 0; wait < 8 && !completed; wait++) { await frame(); await api.sleep(400); }
                    if (!completed) throw new Error('Pilot steps ended, but no English commission-completion banner was detected. Completion is UNCONFIRMED; check the quest journal.');
                    api.info('English commission-completion banner detected.');
                    return 'completed';
                } finally { if (owned) api.clearDialogue(); }
            }
        };
    }
    return { normalize: normalize, exactMatches: exactMatches, uniqueMatch: uniqueMatch, preferredMatch: preferredMatch,
        validate: validate, settingsFor: settingsFor, makeRunner: makeRunner };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = EnglishPilots;
