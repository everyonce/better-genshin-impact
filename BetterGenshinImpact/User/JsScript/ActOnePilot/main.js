// Only fixed package files are evaluated. Request JSON is always parsed as data.
eval(file.readTextSync('engine.js'));
eval(file.readTextSync('bgi.js'));
(async function () {
    var prior = null, adapter = null, runner = null, metrics = null, session = null, lastHeartbeat = 0, failure = null;
    function heartbeat(force,override) {
        var now=Date.now();if(!force&&now-lastHeartbeat<1000)return;
        var state=runner?runner.getState():{state:'starting',frameId:0,activeRequestId:null};
        var value={version:1,processId:Number(genshin.betterGiProcessId),windowsSessionId:Number(genshin.windowsSessionId),remoteDesktop:genshin.isRemoteDesktopSession===true,session:session,
            state:override||state.state,heartbeatAt:now,frameId:state.frameId,activeRequestId:state.activeRequestId,error:failure};
        if(!Number.isInteger(value.processId)||value.processId<=0)throw new Error('Updated BetterGI host with controller identity is required');
        if(!file.writeTextSync('controller-status.json',JSON.stringify(value)))throw new Error('Cannot publish controller heartbeat');
        lastHeartbeat=now;
    }
    try {
        dispatcher.clearAllTriggers();
        if (genshin.isRemoteDesktopSession !== true || !Number.isInteger(Number(genshin.windowsSessionId)) || Number(genshin.windowsSessionId) <= 1) throw new Error('Act One Pilot requires a verified RDP child session above Windows session 1.');
        if (genshin.width / genshin.height !== 16 / 9) throw new Error('A 16:9 game is required.');
        if (!file.createDirectory('observations') || !file.createDirectory('reports')) throw new Error('Output directories unavailable.');
        metrics = getGameMetrics(); setGameMetrics(1920, 1080, 1);
        session = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
        heartbeat(true,'starting');
        adapter = createActOneAdapter(genshin.windowsSessionId);
        adapter.setHeartbeat(heartbeat);
        await adapter.focusGame();
        runner = ActOnePilot.create(adapter, { session: session, enableInput: settings.enableInput === true });
        if (!file.createDirectory('observations/' + session)) throw new Error('Session output directory unavailable.');
        if (!file.createDirectory('receipts/' + session)) throw new Error('Session receipt directory unavailable.');
        await runner.observe();
        heartbeat(true);
        while (!runner.stopped()) {
            await sleep(100);
            heartbeat(false);
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
                refreshed.setHeartbeat(heartbeat);
                Object.keys(refreshed).forEach(function (key) { adapter[key] = refreshed[key]; });
                eval(file.readTextSync('mission.js'));
                eval(file.readTextSync('combat.js'));
                eval(file.readTextSync('recovery.js'));
                await runner.process(request, function () { return { runNavigation: ActOneMission.runNavigation, runDialogue: ActOneMission.runDialogue, runQuestStep:ActOneMission.runQuestStep, run: ActOneCombat.run, recover: ActOneRecovery.run }; });
            } catch (e) { log.info('Act One Pilot request failed: ' + String(e && e.message || e)); }
        }
    } catch(e) {
        failure=String(e&&e.message||e);throw e;
    } finally {
        try { if (adapter) adapter.release(); }
        finally {try {heartbeat(true,failure?'faulted':'stopped');}catch(e){log.info('Controller heartbeat unavailable: '+String(e&&e.message||e));}
            try { if (metrics) setGameMetrics(metrics[0], metrics[1], metrics[2]); } finally { dispatcher.clearAllTriggers(); } }
    }
})();
