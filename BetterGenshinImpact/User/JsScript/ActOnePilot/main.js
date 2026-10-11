// Only fixed package files are evaluated. Request JSON is always parsed as data.
eval(file.readTextSync('engine.js'));
eval(file.readTextSync('bgi.js'));
(async function () {
    var prior = null, adapter = null, runner = null, metrics = null, session = null, lastHeartbeat = 0, failure = null,
        safetyFault = null, safetyFaultAt = 0, wolfExposureArmed = false, internalWolfSequence = 0;
    function heartbeat(force,override) {
        var now=Date.now();if(!force&&now-lastHeartbeat<1000)return;
        var state=runner?runner.getState():{state:'starting',frameId:0,activeRequestId:null};
        var value={version:1,processId:Number(genshin.betterGiProcessId),windowsSessionId:Number(genshin.windowsSessionId),remoteDesktop:genshin.isRemoteDesktopSession===true,session:session,
            state:override||(safetyFault?'faulted':state.state),heartbeatAt:now,frameId:state.frameId,activeRequestId:state.activeRequestId,error:failure||safetyFault};
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
    function readObservation() {
        try {
            if (!file.isExists('observation.json')) return null;
            var value=JSON.parse(file.readTextSync('observation.json'));
            return value&&value.session===session&&value.frameId===runner.getFrame()?value:null;
        } catch (_) { return null; }
    }
    function wolfHistory() {
        try {
            var path='reports/'+session+'.jsonl';
            if (!file.isExists(path)) return [];
            return file.readTextSync(path).split(/\r?\n/).filter(function(line){return line.trim().length>0;})
                .map(function(line){try{return JSON.parse(line);}catch(_){return null;}})
                .filter(function(row){return row&&row.session===session;});
        } catch (_) { return []; }
    }
    function wolfEntryProven(history) {
        return history.some(function(row) {
            if(row.mission!=='questStep'||row.status!=='completed'||!row.details||!row.details.result) return false;
            if(row.details.result.step==='wolfPartyStart'&&Array.isArray(row.details.inputEvents)&&
                row.details.inputEvents.some(function(event){return event&&event.type==='wolfPartyStart'&&Number.isFinite(event.startedAt);})) return true;
            return wolfResumeProof(row);
        });
    }
    function wolfReceiptMatches(row) {
        if(!row||typeof row.id!=='string'||row.session!==session||!file.isExists('receipts/'+session+'/'+row.id+'.json')) return false;
        try {
            var receipt=JSON.parse(file.readTextSync('receipts/'+session+'/'+row.id+'.json'));
            return receipt&&receipt.id===row.id&&receipt.session===row.session&&receipt.mission===row.mission&&
                receipt.status===row.status&&receipt.frameId===row.frameId&&receipt.details&&row.details&&
                receipt.timestamp===row.timestamp&&JSON.stringify(receipt.details)===JSON.stringify(row.details);
        } catch (_) { return false; }
    }
    function wolfResumeProof(row) {
        var result=row&&row.details&&row.details.result,events=row&&row.details&&row.details.inputEvents;
        if(row.mission!=='questStep'||row.status!=='completed'||!result||result.step!=='wolfResume'||
            result.verified!==true||result.toSession!==row.session||!Array.isArray(events)||!wolfReceiptMatches(row)) return false;
        return events.some(function(event) {
            return event&&event.type==='wolfResumeProof'&&event.verified===true&&
                event.fromSession===result.fromSession&&event.toSession===result.toSession&&
                event.toSession===row.session&&event.priorEntryId===result.priorEntryId&&
                event.priorPauseId===result.priorPauseId&&
                event.betterGiProcessId===result.betterGiProcessId&&
                event.rdpSessionId===result.rdpSessionId&&event.gameProcessId===result.gameProcessId&&
                event.verifiedAt===result.verifiedAt&&typeof event.fromSession==='string'&&
                typeof event.priorEntryId==='string'&&typeof event.priorPauseId==='string'&&
                Number.isInteger(event.betterGiProcessId)&&event.betterGiProcessId>0&&
                event.betterGiProcessId===Number(genshin.betterGiProcessId)&&
                Number.isInteger(event.rdpSessionId)&&event.rdpSessionId>1&&
                event.rdpSessionId===Number(genshin.windowsSessionId)&&
                Number.isInteger(event.gameProcessId)&&event.gameProcessId>0&&Number.isFinite(event.verifiedAt);
        });
    }
    function wolfPauseProven(history, observation, expectedId, afterTime) {
        if(!Array.isArray(history)) return false;
        var latestInputAt=latestWolfInputAt(history,null);
        return history.some(function(row) {
            var result=row&&row.details&&row.details.result,events=row&&row.details&&row.details.inputEvents;
            if(row.mission!=='questStep'||row.status!=='completed'&&row.status!=='stopped'||!result||
                Number.isFinite(afterTime)&&row.timestamp<afterTime||!wolfReceiptMatches(row)) return false;
            if(wolfResumeProof(row)) return !!(observation&&observation.session===session&&hasWolfPauseMenu(observation));
            var combatPause=result.step==='wolfCombat'&&row.status==='stopped'&&result.pauseVerified===true;
            if(result.step!=='wolfPause'&&!combatPause||!Array.isArray(events)||
                expectedId&&row.id!==expectedId||typeof row.id!=='string') return false;
            var escapes=events.filter(function(event){
                if(event&&event.type==='key'&&event.key==='VK_ESCAPE'&&Number.isFinite(event.startedAt)) {
                    return true;
                }
                return false;
            });
            if(escapes.length!==1) return false;
            var escapeAt=escapes[0].startedAt;
            var internalId=row.id.indexOf('idle-safety-wolfPause-'+session+'-')===0;
            if(combatPause&&(!Number.isFinite(row.timestamp)||row.timestamp<escapeAt)) return false;
            if(row.status==='completed'&&result.pauseVerified===true&&latestInputAt===escapeAt&&
                hasWolfPauseMenu(observation)&&observation&&observation.session===session&&
                Number.isFinite(observation.timestamp)&&observation.timestamp>escapeAt) return true;
            return (row.status==='stopped'||row.status==='completed')&&(combatPause||internalId||expectedId===row.id)&&
                hasWolfPauseMenu(observation)&&observation&&observation.session===session&&
                Number.isFinite(observation.timestamp)&&observation.timestamp>escapeAt&&latestInputAt===escapeAt;
        });
    }
    function wolfActiveInputProven(history) {
        var steps=['wolfAdvance','wolfForward','wolfForwardFine','wolfLeft','wolfRight','wolfLookLeft','wolfLookRight',
            'wolfLookDown','wolfLookUp','wolfKaeyaSkill','wolfDefensiveCryo','wolfAimCryo','wolfCloseFoodCryo','wolfTurretPass','wolfInventoryRecover','wolfCombat','wolfOpeningDialogue','wolfContinue','wolfPause'];
        return history.some(function(row) {
            if (row.mission!=='questStep'||steps.indexOf(row.details&&row.details.result&&row.details.result.step)<0||
                !Array.isArray(row.details&&row.details.inputEvents)) return false;
            return row.details.inputEvents.some(function(event) {
                return event&&(event.type==='wolfContinue'||event.type==='rotate'&&(row.details.result.step==='wolfCloseFoodCryo'||row.details.result.step==='wolfAimCryo')||
                    event.type==='key'&&['VK_W','VK_A','VK_D','VK_ESCAPE','VK_B','VK_3','VK_E','VK_LBUTTON','VK_SPACE'].indexOf(event.key)>=0);
            });
        });
    }
    function wolfRequestInputProven(history, request) {
        if (!request||request.mission!=='questStep') return false;
        var keys={wolfAdvance:['VK_W'],wolfForward:['VK_W'],wolfForwardFine:['VK_W'],wolfLeft:['VK_A'],wolfRight:['VK_D'],wolfKaeyaSkill:['VK_3','VK_E'],wolfDefensiveCryo:['VK_E'],wolfAimCryo:['VK_W','VK_E'],wolfCloseFoodCryo:['VK_ESCAPE','VK_W','VK_E'],wolfTurretPass:['VK_E','VK_W'],
            wolfLookLeft:[],wolfLookRight:[],wolfLookDown:[],wolfLookUp:[],wolfCombat:['VK_3','VK_E','VK_LBUTTON'],
            wolfInventoryRecover:['VK_B'],wolfOpeningDialogue:['VK_SPACE'],wolfContinue:[],wolfPause:['VK_ESCAPE']};
        if (!Object.prototype.hasOwnProperty.call(keys,request.step)) return false;
        var rows=history.filter(function(row){return row.id===request.id&&row.mission==='questStep'&&row.details&&Array.isArray(row.details.inputEvents);});
        return rows.some(function(row){return row.details.inputEvents.some(function(event){
            return event&&((request.step==='wolfContinue'||request.step==='wolfInventoryRecover')&&event.type==='wolfContinue'||
                (request.step.indexOf('wolfLook')===0||request.step==='wolfCloseFoodCryo'||request.step==='wolfAimCryo')&&event.type==='rotate'||
                event.type==='key'&&keys[request.step].indexOf(event.key)>=0);
        });});
    }
    function latestWolfInputAt(history, request) {
        var steps=['wolfAdvance','wolfForward','wolfForwardFine','wolfLeft','wolfRight','wolfLookLeft','wolfLookRight',
            'wolfLookDown','wolfLookUp','wolfKaeyaSkill','wolfDefensiveCryo','wolfAimCryo','wolfCloseFoodCryo','wolfTurretPass','wolfInventoryRecover','wolfCombat','wolfOpeningDialogue','wolfContinue','wolfPause'];
        var times=[];
        history.forEach(function(row) {
            var step=row.details&&row.details.result&&row.details.result.step;
            if (request&&row.id===request.id&&request.mission==='questStep') step=request.step;
            if (row.mission!=='questStep'||steps.indexOf(step)<0||!Array.isArray(row.details&&row.details.inputEvents)) return;
            row.details.inputEvents.forEach(function(event) {
                if (!event||!Number.isFinite(event.startedAt)) return;
                var valid=event.type==='wolfContinue'||(step.indexOf('wolfLook')===0||step==='wolfCloseFoodCryo'||step==='wolfAimCryo')&&event.type==='rotate'||
                    event.type==='key'&&['VK_W','VK_A','VK_D','VK_ESCAPE','VK_3','VK_E','VK_LBUTTON','VK_SPACE','VK_B'].indexOf(event.key)>=0;
                if (valid) times.push(event.startedAt);
            });
        });
        return times.length?Math.max.apply(Math,times):null;
    }
    function hasWolfPauseMenu(observation) {
        var rows=observation&&observation.ocr||[];
        return rows.some(function(row){return row.text&&row.text.trim()==='Continue Challenge';})&&
            rows.some(function(row){return row.text&&row.text.trim()==='Leave Domain?';});
    }
    function positiveWolfDomain(observation) {
        var hp=observation&&observation.hud&&observation.hud.health;
        return typeof actOneWolfDomainHud==='function'&&actOneWolfDomainHud(observation,Date.now(),0)&&
            hp&&Number.isFinite(Number(hp.current))&&Number(hp.current)>0&&
            Number.isFinite(Number(hp.max))&&Number(hp.max)>0&&Number(hp.current)<=Number(hp.max);
    }
    function pauseOnlyWolfDomain(observation) {
        return typeof actOneWolfPauseOnlyHud==='function'&&actOneWolfPauseOnlyHud(observation,Date.now());
    }
    function knownSafeWolfBoundary(observation) {
        if (!observation) return false;
        var h=observation.hud||{},rows=observation.ocr||[];
        if (hasWolfPauseMenu(observation)||h.world===true&&observation.map!==null||
            h.dialogueReady===true||h.choice===true||h.tutorialStep||h.journal===true||h.bigMap===true||h.loading===true) return true;
        if (typeof actOneEnterGameLoading==='function'&&actOneEnterGameLoading(rows)) return true;
        if (typeof actOneWolfFoodInventoryReady==='function'&&actOneWolfFoodInventoryReady(observation,Date.now())) return true;
        if (typeof actOneKnownSafeFoodBoundary==='function'&&actOneKnownSafeFoodBoundary(observation,Date.now())) return true;
        return rows.some(function(row){return row.text&&(/^(Party Setup|Domain Entrance)$/.test(row.text.trim())||/\b(loading|entering|connecting)\b/i.test(row.text.trim()));});
    }
    function setWolfSafetyFault(reason) {
        safetyFault='Wolf domain safety needs human attention: '+reason;
        safetyFaultAt=Date.now();
        try { heartbeat(true,'faulted'); } catch (e) { log.info('Wolf safety fault could not be written to controller status: '+String(e&&e.message||e)); }
        log.info(safetyFault);
    }
    function clearWolfSafetyFault(history, observation, expectedId) {
        if (safetyFault&&wolfPauseProven(history,observation,expectedId,safetyFaultAt)) {
            safetyFault=null; safetyFaultAt=0; failure=null; heartbeat(true);
        }
    }
    async function internalWolfStep(step, frameId, observation) {
        var requestId='idle-safety-'+step+'-'+session+'-'+(++internalWolfSequence).toString(36);
        var request={id:requestId,session:session,createdAt:Date.now(),expectedFrameId:frameId,mission:'questStep',step:step};
        return {id:requestId,status:await runner.process(request,function(){return {runQuestStep:ActOneMission.runQuestStep};},observation)};
    }
    function autoResumeAllowed(request) {
        if (!request||request.mission!=='questStep'||['wolfAdvance','wolfForward','wolfForwardFine','wolfLeft','wolfRight',
            'wolfLookLeft','wolfLookRight','wolfLookDown','wolfLookUp','wolfKaeyaSkill','wolfDefensiveCryo','wolfAimCryo','wolfTurretPass','wolfCombat','wolfOpeningDialogue'].indexOf(request.step)<0) return false;
        if (ActOnePilot.validate(request,session,runner.getFrame(),Object.create(null),Date.now())) return false;
        return !file.isExists('receipts/'+session+'/'+request.id+'.json');
    }
    function validPendingRequest(request) {
        return !!request&&!ActOnePilot.validate(request,session,runner.getFrame(),Object.create(null),Date.now())&&
            !file.isExists('receipts/'+session+'/'+request.id+'.json');
    }
    async function resumeWolfBeforeAuthorizedStep(request) {
        if (safetyFault||!autoResumeAllowed(request)) return {applicable:false,ready:false};
        var current=readObservation(),history=wolfHistory();
        if (!current||!wolfEntryProven(history)||!hasWolfPauseMenu(current)) return {applicable:false,ready:false};
        // A verified pause can sit idle for minutes. Re-capture only while the
        // exact menu is still present, then bind Continue to that fresh frame.
        // The post-Continue path still uses its single terminal active capture.
        if(!Number.isFinite(current.timestamp)||Date.now()<current.timestamp||Date.now()-current.timestamp>1000) {
            try { current=await runner.observe(); }
            catch(e) {
                runner.report(request,'rejected',{reason:'Fresh paused Wolf menu could not be captured before resume'});
                return {applicable:true,ready:false};
            }
            history=wolfHistory();
        }
        if(!current||!wolfEntryProven(history)||!hasWolfPauseMenu(current)) {
            runner.report(request,'rejected',{reason:'Fresh exact Wolf pause menu and entry proof required before resume'});
            return {applicable:true,ready:false};
        }
        if (!wolfPauseProven(history,current)) {
            runner.report(request,'rejected',{reason:'Wolf menu has no verified same-session pause provenance; use an explicit safe recovery step'});
            return {applicable:true,ready:false};
        }
        var result=await internalWolfStep('wolfContinue',current.frameId,current);
        if (result.status!=='completed') {
            runner.report(request,'rejected',{reason:'Verified Wolf resume did not complete; requested action was not dispatched'});
            return {applicable:true,ready:false};
        }
        var after=readObservation();
        var continueInputAt=latestWolfInputAt(wolfHistory(),null);
        if (!positiveWolfDomain(after)||!Number.isFinite(after.timestamp)||!Number.isFinite(continueInputAt)||after.timestamp<=continueInputAt) {
            runner.report(request,'rejected',{reason:'Fresh positive-HP Wolf trial HUD was not verified after resume; requested action was not dispatched'});
            return {applicable:true,ready:false};
        }
        // The internal Continue step necessarily advances the observation frame.
        // Bind the original authorized step to that fresh post-resume frame without
        // editing request.json or changing its operation, session, or expiry.
        request.expectedFrameId=after.frameId;
        wolfExposureArmed=true;
        return {applicable:true,ready:true,observation:after};
    }
    async function protectWolfIdleBoundary(request) {
        if (!settings||settings.enableInput!==true||!runner||runner.stopped()||request&&request.mission==='stop') return;
        var current=readObservation(),history=wolfHistory();
        if (!current||!wolfEntryProven(history)) return;
        if (wolfActiveInputProven(history)||wolfRequestInputProven(history,request)) wolfExposureArmed=true;
        var lastWolfInputAt=latestWolfInputAt(history,request);
        if (lastWolfInputAt!==null&&(!Number.isFinite(current.timestamp)||current.timestamp<=lastWolfInputAt)) {
            setWolfSafetyFault('the latest Wolf input has no fresh observation after it; no follow-up input was sent');
            return;
        }
        var activeWolfHud=positiveWolfDomain(current),pauseOnlyHud=!activeWolfHud&&pauseOnlyWolfDomain(current);
        if (activeWolfHud||pauseOnlyHud) {
            wolfExposureArmed=true;
            if (activeWolfHud&&request&&request.mission==='questStep'&&request.step==='wolfContinue') return;
            if (request&&request.mission==='questStep'&&request.step==='wolfPause') {
                setWolfSafetyFault('an explicit pause request did not produce the verified pause menu');
                return;
            }
            if (safetyFault&&request&&request.mission!=='recover'&&!(request.mission==='questStep'&&request.step==='wolfPause')) return;
            if (hasWolfPauseMenu(current)) return;
            var pauseAttempt=await internalWolfStep('wolfPause',current.frameId,current);
            var after=readObservation(),updatedHistory=wolfHistory();
            if (wolfPauseProven(updatedHistory,after,pauseAttempt.id)) { clearWolfSafetyFault(updatedHistory,after,pauseAttempt.id); return; }
            setWolfSafetyFault('a fresh Wolf domain was seen, but the automatic pause menu could not be verified');
            return;
        }
        if (hasWolfPauseMenu(current)) {
            wolfExposureArmed=true;
            var pauseRequestId=request&&request.mission==='questStep'&&request.step==='wolfPause'?request.id:undefined;
            clearWolfSafetyFault(history,current,pauseRequestId);
            return;
        }
        if (wolfExposureArmed&&!knownSafeWolfBoundary(current))
            setWolfSafetyFault('the previously verified active trial changed to an ambiguous scene; no input was sent');
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
                if (safetyFault&&request.mission!=='observe'&&request.mission!=='stop'&&request.mission!=='recover'&&
                    !(request.mission==='questStep'&&request.step==='wolfPause')) {
                    runner.report(request,'rejected',{reason:safetyFault+'; only observation, stop, and safe recovery are accepted'});
                } else {
                    if (validPendingRequest(request)&&request.mission==='questStep'&&/^wolf/.test(request.step)) {
                        var beforeWolfStep=readObservation(),beforeWolfHistory=wolfHistory();
                        if (wolfEntryProven(beforeWolfHistory)&&(positiveWolfDomain(beforeWolfStep)||hasWolfPauseMenu(beforeWolfStep))) wolfExposureArmed=true;
                    }
                    var resume=await resumeWolfBeforeAuthorizedStep(request);
                    if (!resume.applicable||resume.ready)
                        await runner.process(request, function () { return { runNavigation: ActOneMission.runNavigation, runDialogue: ActOneMission.runDialogue, runQuestStep:ActOneMission.runQuestStep, run: ActOneCombat.run, recover: ActOneRecovery.run }; },resume.ready?resume.observation:undefined);
                }
            } catch (e) { log.info('Act One Pilot request failed: ' + String(e && e.message || e)); }
            finally { try { await protectWolfIdleBoundary(request); } catch (e) { setWolfSafetyFault('automatic pause handling failed: '+String(e&&e.message||e)); } }
        }
    } catch(e) {
        failure=String(e&&e.message||e);throw e;
    } finally {
        try { if (adapter) adapter.release(); }
        finally {try {heartbeat(true,failure?'faulted':'stopped');}catch(e){log.info('Controller heartbeat unavailable: '+String(e&&e.message||e));}
            try { if (metrics) setGameMetrics(metrics[0], metrics[1], metrics[2]); } finally { dispatcher.clearAllTriggers(); } }
    }
})();
