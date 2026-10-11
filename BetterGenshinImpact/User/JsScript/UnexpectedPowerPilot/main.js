eval(file.readTextSync('policy.js'));
eval(file.readTextSync('adapter.js'));
(async function () {
    var adapter = null, previous = null;
    var session = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
    var status = { session: session, startedAt: Date.now(), state: 'starting', observations: [],
        inputEvents: [], manualInterventions: [], windowsSessionId: Number(genshin.windowsSessionId) };
    function save(patch) {
        if (patch.observation) status.observations.push(patch.observation);
        if (patch.runner) status.runner = patch.runner;
        if (patch.inputEvents) status.inputEvents = patch.inputEvents;
        status.updatedAt = Date.now();
        var data = JSON.stringify(status, null, 2);
        if (!file.writeTextSync('runs/' + session + '.json', data) || !file.writeTextSync('status.json', data))
            throw new Error('status_write_failed');
    }
    try {
        dispatcher.clearAllTriggers();
        if (genshin.isRemoteDesktopSession !== true || !Number.isInteger(Number(genshin.windowsSessionId)))
            throw new Error('Unexpected Power Pilot requires BetterGI r8+ inside RDP.');
        if (genshin.width / genshin.height !== 16 / 9) throw new Error('A 16:9 game is required.');
        if (!file.createDirectory('observations/' + session) || !file.createDirectory('runs'))
            throw new Error('output_directory_failed');
        previous = getGameMetrics(); setGameMetrics(1920, 1080, 1);
        await genshin.focusGame();
        adapter = createUnexpectedPowerAdapter(UnexpectedPowerPolicy, session, save);
        adapter.assertReady();
        save({});
        if (settings.enableInput !== true) {
            await adapter.observe();
            status.state = 'observed';
        } else {
            status.state = 'running'; save({});
            // Opening the journal is the only permitted bootstrap action, and
            // only when an actual world HUD is positively observed.
            var initial = await adapter.observe();
            if (UnexpectedPowerPolicy.classify(initial.rows).kind !== 'targetJournal' && initial.mode === 'verifiedWorld')
                await adapter.openJournal();
            var result = await UnexpectedPowerPolicy.run(adapter);
            status.result = result;
            status.state = result.status;
        }
    } catch (error) {
        status.state = 'stopped'; status.error = String(error && error.message || error);
    } finally {
        try { if (adapter) adapter.release(); }
        finally {
            if (previous) setGameMetrics(previous[0], previous[1], previous[2]);
            dispatcher.clearAllTriggers();
            status.finishedAt = Date.now(); status.elapsedMs = status.finishedAt - status.startedAt;
            try { save({}); } catch (error) { log.info('Could not save pilot result: ' + String(error)); }
            log.info('Unexpected Power Pilot stopped: ' + status.state + ' ' + (status.error || (status.result && status.result.stoppedReason) || ''));
        }
    }
})();
