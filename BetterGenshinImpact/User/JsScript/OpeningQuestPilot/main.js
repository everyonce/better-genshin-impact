// Only these fixed, trusted package sources are loaded. Command JSON is never code.
eval(file.readTextSync('engine.js'));
eval(file.readTextSync('bgi.js'));
(async function () {
    var api = createOpeningQuestAdapter(), runner = null, previous = null;
    try {
        dispatcher.clearAllTriggers();
        previous = getGameMetrics();
        if (genshin.isRemoteDesktopSession !== true || genshin.width / genshin.height !== 16 / 9) {
            throw new Error('Opening Quest Pilot requires a 16:9 game in a Remote Desktop session.');
        }
        setGameMetrics(1920, 1080, 1);
        var session = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2) + '-' + Math.random().toString(36).slice(2);
        runner = OpeningQuestPilot.create(api, { session: session, enableInput: settings.enableInput === true });
        await runner.observe();
        log.info('Opening Quest Pilot: supervised local bridge started. Session: ' + session);
        var previousCommand = null;
        while (!runner.expired()) {
            await sleep(100);
            if (!file.isExists('command.json')) continue;
            var raw = file.readTextSync('command.json');
            if (raw === previousCommand) continue;
            previousCommand = raw;
            if (raw.length > 4096) throw new Error('command.json exceeds 4096 characters.');
            await runner.process(JSON.parse(raw));
        }
        log.info('Opening Quest Pilot stopped (stop command or session/idle limit).');
    } finally {
        try { if (runner) runner.release(); }
        finally {
            try { if (previous) setGameMetrics(previous[0], previous[1], previous[2]); }
            finally { dispatcher.clearAllTriggers(); }
        }
    }
})();
