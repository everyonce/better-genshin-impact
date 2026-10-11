// Only fixed package files are evaluated. Request JSON is always parsed as data.
eval(file.readTextSync('engine.js'));
eval(file.readTextSync('bgi.js'));
(async function () {
    var prior = null, adapter = null, runner = null, metrics = null;
    try {
        dispatcher.clearAllTriggers();
        if (genshin.isRemoteDesktopSession !== true || Number(genshin.windowsSessionId) !== 5) throw new Error('Act One Pilot requires RDP session 5.');
        if (genshin.width / genshin.height !== 16 / 9) throw new Error('A 16:9 game is required.');
        if (!file.createDirectory('observations') || !file.createDirectory('reports')) throw new Error('Output directories unavailable.');
        metrics = getGameMetrics(); setGameMetrics(1920, 1080, 1);
        var session = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
        adapter = createActOneAdapter(genshin.windowsSessionId);
        await adapter.focusGame();
        runner = ActOnePilot.create(adapter, { session: session, enableInput: settings.enableInput === true });
        if (!file.createDirectory('observations/' + session)) throw new Error('Session output directory unavailable.');
        await runner.observe();
        while (!runner.stopped()) {
            await sleep(100);
            if (!file.isExists('request.json')) continue;
            var raw = file.readTextSync('request.json');
            if (raw === prior) continue;
            prior = raw;
            if (raw.length > 8192) { runner.report(null, 'rejected', { reason: 'request.json exceeds 8192 characters' }); continue; }
            try {
                var request = JSON.parse(raw);
                // Between completed missions there are no held keys. Refresh only
                // trusted package code, preserving the runner's session and nonce state.
                eval(file.readTextSync('bgi.js'));
                var refreshed = createActOneAdapter(genshin.windowsSessionId);
                Object.keys(refreshed).forEach(function (key) { adapter[key] = refreshed[key]; });
                if (request.mission === 'navigation' || request.mission === 'dialogue') eval(file.readTextSync('mission.js'));
                await runner.process(request, function () { return ActOneMission; });
            } catch (e) { log.info('Act One Pilot request failed: ' + String(e && e.message || e)); }
        }
    } finally {
        try { if (adapter) adapter.release(); }
        finally { try { if (metrics) setGameMetrics(metrics[0], metrics[1], metrics[2]); } finally { dispatcher.clearAllTriggers(); } }
    }
})();
