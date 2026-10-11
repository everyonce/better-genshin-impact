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
    function checkStartupStop() {
        if (!session || !file.isExists('stop.json')) return;
        var stop;
        try { stop=JSON.parse(file.readTextSync('stop.json')); } catch (_) { return; }
        if (stop && stop.session===session && Number.isFinite(stop.createdAt)) throw new Error('Stop requested during controller startup');
    }
    function startupStep(observation) {
        var now=Date.now();
        if (typeof actOneEnterGameTitleFrame==='function' && actOneEnterGameTitleFrame(observation,now)) return 'enterGame';
        if (typeof actOneEnterWorldTarget==='function' && actOneEnterWorldTarget(observation,now)) return 'enterWorld';
        return null;
    }
    function blankStartup(observation) {
        if (!observation || observation.map!==null) return false;
        var hud=observation.hud||{},rows=observation.ocr||[];
        if (hud.world===true || hud.health || hud.journal || hud.bigMap || hud.dialogueReady || hud.choice || hud.interact || hud.objectiveChanged) return false;
        if ((typeof actOneEnterGameAuthPrompt==='function' && actOneEnterGameAuthPrompt(rows)) ||
            (typeof actOneEnterGameUnknownUi==='function' && actOneEnterGameUnknownUi(rows)) ||
            (typeof actOneEnterGameLoading==='function' && actOneEnterGameLoading(rows))) return false;
        return rows.length===0 && (hud.world===false || Object.keys(hud).length===0);
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
        var focusStartedAt=Date.now(),focusDeadline=focusStartedAt+5000,focusAttempts=0,focusError=null,focused=false;
        while(focusAttempts<5 && Date.now()<focusDeadline) {
            checkStartupStop();
            heartbeat(true,'starting');
            focusAttempts++;
            try { await adapter.focusGame(); focused=true; break; }
            catch(e) {
                focusError=e;
                adapter.release();
                if(focusAttempts>=5 || Date.now()>=focusDeadline) break;
                await sleep(Math.min(350,focusDeadline-Date.now()));
                checkStartupStop();
            }
        }
        if(!focused) throw new Error('Game focus failed after '+focusAttempts+' bounded attempts: '+String(focusError&&focusError.message||focusError||'startup deadline reached'));
        runner = ActOnePilot.create(adapter, { session: session, enableInput: settings.enableInput === true });
        if (!file.createDirectory('observations/' + session)) throw new Error('Session output directory unavailable.');
        if (!file.createDirectory('receipts/' + session)) throw new Error('Session receipt directory unavailable.');
        var initialObservation = await runner.observe(),step=startupStep(initialObservation),startupObservations=1,startupDeadline=Date.now()+5000;
        heartbeat(true,'starting');
        while(!step && blankStartup(initialObservation) && startupObservations<8 && Date.now()<startupDeadline) {
            checkStartupStop();
            await sleep(Math.min(350,startupDeadline-Date.now()));
            checkStartupStop();
            heartbeat(true,'starting');
            initialObservation=await runner.observe();startupObservations++;
            heartbeat(true,'starting');
            step=startupStep(initialObservation);
        }
        if (settings.enableInput === true && step) {
            eval(file.readTextSync('mission.js'));
            await runner.process({id:'startup-'+step,session:session,createdAt:Date.now(),
                expectedFrameId:initialObservation.frameId,mission:'questStep',step:step},
                function () { return {runQuestStep:ActOneMission.runQuestStep}; });
        }
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
