var ActOnePilot = (function () {
    var keys = ['VK_J', 'VK_ESCAPE', 'VK_F', 'VK_SPACE', 'VK_M'];
    function combatObjective(value) { return ['Defeat the nearby hilichurls','Clear out the nearby hilichurl camp'].indexOf(value)>=0; }
    function integer(n, lo, hi) { return typeof n === 'number' && Number.isInteger(n) && n >= lo && n <= hi; }
    function wolfContinueSeed(o,now) {
        var h=o&&o.hud,rows=o&&o.ocr||[];
        if(!o||!Number.isFinite(o.timestamp)||!Number.isFinite(now)||now<o.timestamp||now-o.timestamp>1000||o.map!==null||!h||h.world!==false||
           h.auto!==false||h.dialogueReady||h.choice||h.climbing||h.loading||h.unknownHud||h.objectiveChanged) return false;
        var continues=rows.filter(function(r){return r&&String(r.text||'').trim()==='Continue Challenge'&&r.x>750&&r.x<1000&&r.y>380&&r.y<460;}),
            leaves=rows.filter(function(r){return r&&String(r.text||'').trim()==='Leave Domain?'&&r.x>750&&r.x<1000&&r.y>620&&r.y<700;});
        return continues.length===1&&leaves.length===1;
    }
    function validate(r, session, frame, seen, now) {
        if (!r || typeof r !== 'object' || Array.isArray(r)) return 'Request must be an object';
        if (typeof r.id !== 'string' || !/^[A-Za-z0-9_-]{1,80}$/.test(r.id)) return 'Invalid id';
        if (seen[r.id]) return 'Duplicate id';
        if (r.session !== session) return 'Wrong session';
        if (r.expectedFrameId !== frame) return 'Stale frame';
        if (!integer(r.createdAt, now - 30000, now)) return 'Expired or future request';
        if (typeof r.mission !== 'string' || ['observe', 'stop', 'keyPress', 'look', 'navigation', 'dialogue', 'combat', 'recover', 'questStep'].indexOf(r.mission) < 0) return 'Unknown mission';
        var allowed = ['id', 'session', 'expectedFrameId', 'createdAt', 'mission'];
        if (r.mission === 'keyPress') { allowed.push('key'); if (keys.indexOf(r.key) < 0) return 'Key is not allowed'; }
        if (r.mission === 'look') { allowed.push('dx'); if (!integer(r.dx, -250, 250) || r.dx === 0) return 'Invalid look delta'; }
        if (r.mission === 'questStep') {
            allowed.push('step');
            if (typeof r.step !== 'string' || !/^[a-z][A-Za-z0-9]{0,39}$/.test(r.step)) return 'Invalid quest step';
            if (Object.prototype.hasOwnProperty.call(r,'lookAmount')) {
                if (['wolfLookRight','wolfLookLeft','wolfLookDown','wolfLookUp'].indexOf(r.step)<0) return 'lookAmount is allowed only for Wolf look steps';
                allowed.push('lookAmount');
                if (!integer(r.lookAmount,16,250)) return 'Invalid lookAmount';
            }
        }
        if (r.mission === 'combat') {
            allowed.push('objective','deadlineMs');
            if (!combatObjective(r.objective) && r.objective !== 'Stormterror aerial encounter') return 'Unsupported combat objective';
            if (!integer(r.deadlineMs,1000,60000)) return 'Invalid combat deadline';
        }
        if (r.mission === 'navigation') {
            allowed.push('waypoints', 'deadlineMs', 'objective');
            if (typeof r.objective !== 'string' || !r.objective.trim() || r.objective.length > 160) return 'Expected objective required';
            if (!Array.isArray(r.waypoints) || r.waypoints.length < 1 || r.waypoints.length > 10) return 'Invalid waypoints';
            if (!integer(r.deadlineMs, 1000, 90000)) return 'Invalid navigation deadline';
            for (var i = 0; i < r.waypoints.length; i++) {
                var p = r.waypoints[i];
                if (!p || typeof p !== 'object' || !Number.isFinite(p.x) || !Number.isFinite(p.y) || p.map !== 'Teyvat' || Object.keys(p).some(function (k) { return ['x', 'y', 'map'].indexOf(k) < 0; })) return 'Invalid waypoint';
            }
        }
        if (Object.keys(r).some(function (k) { return allowed.indexOf(k) < 0; })) return 'Unknown request field';
        return null;
    }
    function create(api, options) {
        var session = options.session, enabled = options.enableInput === true, frame = 0, lastObservedFrame = 0, lastObservedAt = null, seen = Object.create(null), seenOrder = [], stopped = false, busy = false, reports = [], milestones = Object.create(null), activeRequestId = null;
        // The listener has no elapsed-time or idle shutdown. Only an explicit
        // stop or the host cancellation ends it; each input mission stays bounded.
        function state() { return {state:stopped?'stopped':busy?'running':'idle',frameId:frame,activeRequestId:activeRequestId}; }
        function pulse(force) { if(typeof api.heartbeat==='function')api.heartbeat(state(),force===true); }
        function report(req, state, details) {
            var row = { session: session, id: req && req.id || null, mission: req && req.mission || null, status: state, timestamp: api.now(), frameId: frame, details: details || null };
            if(typeof api.append==='function')api.append('reports/'+session+'.jsonl',JSON.stringify(row)+'\n');
            reports.push(row);if(reports.length>200)reports.shift();
            var step=details&&details.result&&details.result.step;
            if(state==='completed'&&['falconStart','falconPartyStart','falconResume','falconFireAim','falconPause','wolfStart','wolfPartyStart','wolfResume','lionStart','lionPartyStart','lionResume'].indexOf(step)>=0)milestones[step]=row;
            var snapshot=Object.keys(milestones).map(function(k){return milestones[k];}).filter(function(r){return reports.indexOf(r)<0;}).concat(reports);
            api.write('reports/' + session + '.json', JSON.stringify(snapshot, null, 2));
            if(state!=='rejected'&&req&&req.session===session&&seen[req.id])api.write('receipts/'+session+'/'+req.id+'.json',JSON.stringify(row));
            api.write('receipt.json', JSON.stringify(row, null, 2));pulse();return row;
        }
        async function observe() {
            var data = await api.observe(session, frame + 1); frame++;
            lastObservedFrame=frame;lastObservedAt=Number(data.timestamp);
            var immutable = JSON.parse(JSON.stringify({ session: session, frameId: frame, timestamp: data.timestamp, screenshotPath: data.screenshotPath, ocr: data.ocr || [], map: data.map || null, hud: data.hud || null, timings: data.timings || {} }));
            api.write('observations/' + session + '/frame-' + String(frame).padStart(4, '0') + '.json', JSON.stringify(immutable, null, 2));
            api.write('observation.json', JSON.stringify(immutable, null, 2));
            pulse();
            return immutable;
        }
        async function process(req, missionFactory, seedObservation) {
            if (busy) return 'busy';
            if (stopped) return 'stopped';
            var reason = validate(req, session, frame, seen, api.now());
            if(!reason&&seedObservation!==undefined) {
                var seededHealth=seedObservation&&seedObservation.hud&&seedObservation.hud.health;
                var continueSeed=req&&req.mission==='questStep'&&req.step==='wolfContinue';
                if(!req||req.mission!=='questStep'||typeof req.step!=='string'||req.step.indexOf('wolf')!==0||
                   !seedObservation||seedObservation.session!==session||seedObservation.frameId!==frame||req.expectedFrameId!==frame||
                   !Number.isFinite(seedObservation.timestamp)||api.now()<seedObservation.timestamp||api.now()-seedObservation.timestamp>1000||
                   (continueSeed?!wolfContinueSeed(seedObservation,api.now()):!seededHealth||!Number.isFinite(seededHealth.current)||
                     !Number.isFinite(seededHealth.max)||seededHealth.max<=0||seededHealth.current<=0||seededHealth.current>seededHealth.max))
                    reason='Invalid or stale seeded Wolf observation';
            }
            if(!reason&&typeof api.wasSeen==='function'&&api.wasSeen(session,req.id))reason='Duplicate id';
            if (reason) { report(req, 'rejected', { reason: reason }); return 'rejected'; }
            seen[req.id] = true;seenOrder.push(req.id);if(seenOrder.length>4096)delete seen[seenOrder.shift()];
            busy = true;activeRequestId=req.id;var inputStarted = 0, routeResult = null, missionStarted = api.now();
            try {
                pulse(true);
                api.beginMission(req);
                if(seedObservation!==undefined) {
                    if(typeof api.seedObservation!=='function') throw new Error('Adapter cannot bind a seeded Wolf observation');
                    api.seedObservation(seedObservation);
                }
                report(req, 'started');
                if (req.mission === 'stop') { stopped = true; }
                else if (req.mission === 'keyPress') {
                    if (!enabled) throw new Error('Input is disabled');
                    var before = await observe();
                    var h = before.hud;
                    var permitted = (req.key === 'VK_ESCAPE' && (h.journal || h.bigMap)) ||
                        ((req.key === 'VK_J' || req.key === 'VK_M') && h.world) ||
                        (req.key === 'VK_SPACE' && h.dialogueReady) || (req.key === 'VK_F' && h.world && h.interact);
                    if (!permitted) throw new Error('Key not valid in the recognized screen');
                    api.requireInputReady(); inputStarted = api.now(); await api.keyPress(req.key);
                    await api.sleep(900);
                } else if (req.mission === 'look') {
                    if (!enabled) throw new Error('Input is disabled');
                    function safeLookState(observation) {
                        var h=observation&&observation.hud, hp=h&&h.health;
                        return !!(h&&h.world===true&&!h.journal&&!h.bigMap&&!h.tutorialStep&&!h.climbing&&
                            !h.dialogueReady&&!h.choice&&!h.lowHealth&&hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&
                            hp.max>0&&hp.current>=0&&hp.current<=hp.max&&hp.current/hp.max>=0.6);
                    }
                    var lookFresh=await observe();
                    if (!safeLookState(lookFresh)) throw new Error('Look requires fresh safe world HUD and numeric HP >= 60%');
                    api.requireInputReady(); inputStarted=api.now(); await api.rotate(req.dx);
                    await api.sleep(180);
                    routeResult=await observe();
                    if (!safeLookState(routeResult)) throw new Error('Look ended without safe world HUD and numeric HP >= 60%');
                } else if (req.mission === 'recover') {
                    if (!enabled) throw new Error('Input is disabled');
                    var recoveryFresh = await observe();
                    routeResult = await missionFactory().recover(recoveryFresh, api, observe);
                    if (routeResult.status !== 'completed') throw new Error(routeResult.reason);
                } else if (req.mission === 'questStep') {
                    if (!enabled) throw new Error('Input is disabled');
                    var questFresh=seedObservation===undefined?await observe():JSON.parse(JSON.stringify(seedObservation));
                    if(seedObservation!==undefined){lastObservedFrame=frame;lastObservedAt=Number(seedObservation.timestamp);}
                    api.requireInputReady();
                    var questPolicy=missionFactory();
                    routeResult=typeof questPolicy.runQuestStep==='function'?
                        await questPolicy.runQuestStep(req.step,questFresh,api,observe):
                        {status:'stopped',reason:'Unsupported quest step: '+req.step};
                } else if (req.mission === 'navigation') {
                    if (!enabled) throw new Error('Input is disabled');
                    var fresh = await resumeCombatJournal(req, await observe());
                    routeResult = await missionFactory().runNavigation(req, fresh, api, observe);
                    if (combatObjective(req.objective) && routeResult.reason === 'Enemy acquired') {
                        var navigationResult = routeResult;
                        var handoff = await observe();
                        routeResult = await missionFactory().run({ objective: req.objective, deadlineMs: 20000 }, handoff, api, observe);
                        routeResult.navigation = navigationResult;
                        routeResult.localHandoff = true;
                        if (routeResult.status !== 'completed') throw new Error(routeResult.reason);
                    } else if (combatObjective(req.objective) && api.pauseCombat) {
                        await observe(); await api.pauseCombat(); await observe();
                    }
                    if (routeResult.status !== 'arrived' && routeResult.status !== 'completed') throw new Error(routeResult.reason || 'Navigation policy stopped');
                } else if (req.mission === 'combat') {
                    if (!enabled) throw new Error('Input is disabled');
                    var combatFresh = await resumeCombatJournal(req, await observe());
                    routeResult = await missionFactory().run(req, combatFresh, api, observe);
                    if (req.objective !== 'Stormterror aerial encounter' && routeResult.status !== 'completed') throw new Error(routeResult.reason);
                } else if (req.mission === 'dialogue') {
                    if (!enabled) throw new Error('Input is disabled');
                    routeResult = await missionFactory().runDialogue(api, observe);
                    if (routeResult.status !== 'completed') throw new Error(routeResult.reason);
                }
                if (req.mission !== 'stop') {
                    var observedFrame=routeResult&&Number.isInteger(routeResult.frameId)&&routeResult.frameId===frame;
                    var latestInputAt=-Infinity;
                    (api.events()||[]).forEach(function(event){if(event){var at=Number.isFinite(event.finishedAt)?event.finishedAt:event.startedAt;if(Number.isFinite(at)&&at>latestInputAt)latestInputAt=at;}});
                    var observedAfterInput=observedFrame&&lastObservedFrame===frame&&Number.isFinite(lastObservedAt)&&lastObservedAt>latestInputAt;
                    if(!(req.mission==='questStep'&&req.step&&req.step.indexOf('wolf')===0&&observedAfterInput)) {
                        var terminalObservation=await observe();
                        if(req.mission==='questStep'&&req.step==='wolfContinue'&&routeResult)routeResult.frameId=terminalObservation.frameId;
                    }
                }
                var details = { elapsedMs: api.now() - missionStarted, result: routeResult, inputEvents: api.events() };
                var terminalState=req.mission==='stop'||routeResult&&routeResult.status==='stopped'?'stopped':'completed';
                report(req, terminalState, details);
                return terminalState;
            } catch (e) { report(req, 'failed', { reason: String(e && e.message || e), elapsedMs: api.now() - missionStarted, result: routeResult, inputEvents: api.events() }); throw e; }
            finally { try {api.release();} finally {busy=false;activeRequestId=null;pulse(true);} }
        }
        async function resumeCombatJournal(req, current) {
            if (combatObjective(req.objective) && current.hud.journal &&
                current.ocr.some(function(r){return r.text.trim()==='Going Upon the Breeze';})) {
                api.checkStop(); await api.keyPress('VK_ESCAPE'); await api.sleep(350);
                return await observe();
            }
            return current;
        }
        return { observe: observe, process: process, stopped: function () { return stopped; }, report: report, getFrame: function () { return frame; },getState:state };
    }
    return { create: create, validate: validate };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = ActOnePilot;
