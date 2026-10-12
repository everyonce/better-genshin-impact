var ActOneCombat = (function () {
    var OBJECTIVE = 'Defeat the nearby hilichurls';
    var CAMP_OBJECTIVE = 'Clear out the nearby hilichurl camp';
    var AERIAL_OBJECTIVE = 'Stormterror aerial encounter';
    var OBJECTIVES = [OBJECTIVE, CAMP_OBJECTIVE];
    var MAX_RUN_MS = 60000;
    var MAX_ACTIONS = 40;
    var MIN_HEALTH_RATIO = 0.6;
    var MAX_HEALTH_LOSS_RATIO = 0.2;
    var CHARACTER_SWITCH_DELAY_MS = 500;
    var OBSERVE_DELAY_MS = 350;
    var EVIDENCE_RETRY_DELAY_MS = 200;
    var MAX_EVIDENCE_RETRIES = 2;
    var BURST_OBSERVE_DELAY_MS = 700;
    var APPROACH_OBSERVE_DELAY_MS = 150;
    var SKILL_INTERVAL_MS = 8000;
    var MAX_CAMERA_SCANS = 4;
    var MAX_CAMERA_CORRECTIONS = 4;
    var MAX_APPROACH_STEPS = 6;
    var MAX_APPROACH_STALLS = 2;
    var MAX_AERIAL_BURSTS = 60;
    var AERIAL_MIN_HEALTH_RATIO = 0.6;
    var AERIAL_MAX_HEALTH_LOSS_RATIO = 0.1;
    var WOLF_MAX_ACTIONS = 30;
    var WOLF_MAX_RUN_MS = 20000;
    var WOLF_SKILL_COOLDOWN_MS = 6500;
    var WOLF_ATTACK_INTERVAL_MS = 250;
    var WOLF_BAR_REACQUIRE_MS = 4000;
    var WOLF_SEEK_FORWARD_LIMIT = 4;
    var WOLF_SEEK_TURN_LIMIT = 2;
    var WOLF_SEEK_FORWARD_MS = 250;
    var WOLF_SEEK_CENTER_MIN = 850;
    var WOLF_SEEK_CENTER_MAX = 1070;
    // Contour width moves by 1–2 px on stable targets; require a larger
    // change before treating it as damage progress or a restored bar.
    var WOLF_BAR_PROGRESS_TOLERANCE = 3;

    function wolfStateError(observation, api, baseline) {
        if (!observation || !observation.hud) return 'Wolf combat HUD unavailable';
        var h=observation.hud, hp=h.health, rows=observation.ocr||[];
        if (observation.map!==null || h.world!==false || h.groundControls!==true || h.journal===true ||
            h.bigMap===true || h.climbing===true || h.dialogueReady===true || h.choice===true || h.tutorialStep ||
            h.loading===true || h.unknownHud===true || h.objectiveChanged===true || h.auto===true ||
            rows.some(function(r){return r.text&&(/^(Party Setup|Domain Entrance)$/.test(r.text.trim())||
                /\b(loading|entering|connecting|preparing)\b/i.test(r.text.trim()));}))
            return 'Wolf domain or no-UI state changed';
        if (!rows.some(function(r){return r.text&&r.text.trim()==='Kaeya'&&r.x>1550&&r.y>300&&r.y<600;}) ||
            !rows.some(function(r){return r.text&&r.text.trim()==='Trial'&&r.x>1700&&r.y>300&&r.y<600;}))
            return 'Trial Kaeya HUD evidence unavailable';
        if (!hp || !Number.isFinite(Number(hp.current)) || !Number.isFinite(Number(hp.max)) ||
            Number(hp.max)<=0 || Number(hp.current)<0 || Number(hp.current)>Number(hp.max))
            return 'Wolf player health unavailable';
        if (Number(hp.current)/Number(hp.max)<MIN_HEALTH_RATIO) return 'Wolf player health below 60%';
        if (baseline && baseline.current-Number(hp.current)>baseline.max*MAX_HEALTH_LOSS_RATIO)
            return 'Wolf player health dropped more than 20% of maximum';
        if (!Number.isFinite(Number(observation.timestamp)) || api.now()<Number(observation.timestamp) ||
            api.now()-Number(observation.timestamp)>1000) return 'Wolf observation is stale';
        return null;
    }

    async function runWolf(initial, api, observe) {
        var began=api&&typeof api.now==='function'?api.now():0, presses=0,inputMs=0,lastE=-Infinity,lastAttack=-Infinity;
        var baseline=null,bestWidth=null,noDamage=0,lastSeekNoDamage=0,seekForward=0,seekTurns=0,lastFrameId=null;
        lastFrameId=initial&&initial.frameId;
        function stopped(reason) {
            return {status:'stopped',step:'wolfCombat',reason:reason,presses:presses,inputMs:inputMs,
                seekForward:seekForward,seekTurns:seekTurns,frameId:lastFrameId,
                elapsedMs:api&&typeof api.now==='function'?Math.max(0,api.now()-began):0,combatComplete:false};
        }
        if (!api || typeof observe!=='function' || typeof api.now!=='function' || typeof api.sleep!=='function' ||
            typeof api.checkStop!=='function' || typeof api.wolfCombatKey!=='function' ||
            typeof api.wolfPauseCombat!=='function') return stopped('Wolf combat API unavailable');
        var reason=wolfStateError(initial,api,null);
        if (reason) return stopped(reason);
        var initialBars=initial.hud.enemyBars;
        var hp=initial.hud.health;
        baseline={current:Number(hp.current),max:Number(hp.max)};
        lastFrameId=initial.frameId;
        async function fresh() {
            api.checkStop();
            var value=await observe(); api.checkStop(); lastFrameId=value&&value.frameId;
            return value;
        }
        async function ensureFresh(observation) {
            var timestamp=observation&&Number(observation.timestamp),now=api.now();
            if(Number.isFinite(timestamp)&&now>=timestamp&&now-timestamp<=1000) return observation;
            return await fresh();
        }
        async function checkedFresh(observation) {
            var checked=wolfStateError(observation,api,baseline),retries=0;
            function safeForPartyRetry(value) {
                if (!value||!value.hud) return false;
                var h=value.hud,hp=h.health,rows=value.ocr||[];
                if (value.map!==null||h.world!==false||h.groundControls!==true||h.climbing===true||
                    h.journal===true||h.bigMap===true||h.dialogueReady===true||h.choice===true||h.tutorialStep||
                    h.loading===true||h.unknownHud===true||h.objectiveChanged===true||h.auto===true) return false;
                if (rows.some(function(r){return r.text&&(/^(Party Setup|Domain Entrance)$/.test(r.text.trim())||
                    /\b(loading|entering|connecting|preparing)\b/i.test(r.text.trim()));})) return false;
                if (!hp||!Number.isFinite(Number(hp.current))||!Number.isFinite(Number(hp.max))||Number(hp.max)<=0||
                    Number(hp.current)<=Number(hp.max)*MIN_HEALTH_RATIO||Number(hp.current)>Number(hp.max)) return false;
                if (baseline&&baseline.current-Number(hp.current)>baseline.max*MAX_HEALTH_LOSS_RATIO) return false;
                return Number.isFinite(Number(value.timestamp))&&api.now()>=Number(value.timestamp)&&
                    api.now()-Number(value.timestamp)<=1000;
            }
            while (checked==='Trial Kaeya HUD evidence unavailable'&&retries<2&&safeForPartyRetry(observation)) {
                api.checkStop(); await api.sleep(EVIDENCE_RETRY_DELAY_MS); observation=await fresh(); retries++;
                checked=wolfStateError(observation,api,baseline);
            }
            return {observation:observation,reason:checked};
        }
        function wolfPauseGuard(observation) {
            if (!observation||!observation.hud) return false;
            var h=observation.hud,hp=h.health,rows=observation.ocr||[];
            return observation.map===null&&h.world===false&&h.groundControls===true&&h.climbing!==true&&
                h.journal!==true&&h.bigMap!==true&&h.dialogueReady!==true&&h.choice!==true&&!h.tutorialStep&&
                hp&&Number.isFinite(Number(hp.current))&&Number.isFinite(Number(hp.max))&&Number(hp.max)>0&&
                Number(hp.current)>0&&Number(hp.current)<=Number(hp.max)&&
                Number.isFinite(Number(observation.timestamp))&&api.now()>=Number(observation.timestamp)&&
                api.now()-Number(observation.timestamp)<=1000&&
                rows.some(function(r){return r.text&&r.text.trim()==='Kaeya'&&r.x>1550&&r.y>300&&r.y<600;})&&
                rows.some(function(r){return r.text&&r.text.trim()==='Trial'&&r.x>1700&&r.y>300&&r.y<600;});
        }
        async function pauseIfSafe() {
            var current=await fresh();
            if (!wolfPauseGuard(current)) return false;
            await api.wolfPauseCombat();
            await api.sleep(600);
            var paused=await fresh(), rows=paused&&paused.ocr||[];
            return rows.some(function(r){return r.text&&r.text.trim()==='Continue Challenge';}) &&
                rows.some(function(r){return r.text&&r.text.trim()==='Leave Domain?';});
        }
        async function finish(reason) {
            var pauseVerified=false;
            if (reason!=='Wolf combat API unavailable') pauseVerified=await pauseIfSafe();
            var result=stopped(reason); result.pauseVerified=pauseVerified; return result;
        }
        function validInitialEnemyBar(bars) {
            return Array.isArray(bars)&&bars.length>0&&Number.isFinite(Number(bars[0].width))&&Number(bars[0].width)>0;
        }
        var initialBarRetries=0;
        while (!validInitialEnemyBar(initialBars)&&initialBarRetries<2) {
            if (api.now()-began>=WOLF_MAX_RUN_MS) return finish('Wolf combat time limit reached');
            api.checkStop(); await api.sleep(EVIDENCE_RETRY_DELAY_MS); api.checkStop();
            if (api.now()-began>=WOLF_MAX_RUN_MS) return finish('Wolf combat time limit reached');
            initial=await fresh(); initialBarRetries++;
            reason=wolfStateError(initial,api,baseline);
            if (reason) return finish(reason);
            if (api.now()-began>=WOLF_MAX_RUN_MS) return finish('Wolf combat time limit reached');
            initialBars=initial.hud.enemyBars;
        }
        if (!validInitialEnemyBar(initialBars))
            return finish('Wolf enemy bar evidence unavailable before character selection');
        // The guarded trial-domain HUD is the only context in which selecting Kaeya is allowed.
        api.checkStop();
        var selectStarted=api.now(); await api.wolfCombatKey('VK_3'); presses++;
        inputMs+=Math.max(0,api.now()-selectStarted);
        await api.sleep(500);
        var selected=await fresh(),selectedEvidence=await checkedFresh(selected); selected=selectedEvidence.observation; reason=selectedEvidence.reason;
        if (reason) return finish(reason);
        baseline={current:Number(selected.hud.health.current),max:Number(selected.hud.health.max)};
        initial=selected;
        // Keep the original post-selection observation out of the combat
        // decision sequence; the first decision gets its own fresh capture.
        // Thereafter each post-action checked frame is reused by the next loop.
        var current=null;
        while (true) {
            api.checkStop();
            if (api.now()-began>=WOLF_MAX_RUN_MS) return finish('Wolf combat time limit reached');
            if (presses>=WOLF_MAX_ACTIONS) return finish('Wolf combat action limit reached');
            current=await ensureFresh(current);
            var currentEvidence=await checkedFresh(current); current=currentEvidence.observation; reason=currentEvidence.reason;
            if (reason) return finish(reason);
            if (api.now()-began>=WOLF_MAX_RUN_MS) return finish('Wolf combat time limit reached');
            var bars=current.hud.enemyBars;
            if (!Array.isArray(bars)||bars.length===0) {
                // Skills can hide enemy labels/bars under Wet/Frozen effects.
                // Do not send input while reacquiring; keep checking the same HUD,
                // health-loss and freshness guards, bounded by both deadlines.
                var reacquireUntil=Math.min(api.now()+WOLF_BAR_REACQUIRE_MS,began+WOLF_MAX_RUN_MS);
                while (api.now()<reacquireUntil) {
                    await api.sleep(Math.min(WOLF_ATTACK_INTERVAL_MS,reacquireUntil-api.now()));
                    if (api.now()-began>=WOLF_MAX_RUN_MS) return finish('Wolf combat time limit reached');
                    current=await fresh(); currentEvidence=await checkedFresh(current); current=currentEvidence.observation; reason=currentEvidence.reason;
                    if (reason) return finish(reason);
                    if (api.now()-began>=WOLF_MAX_RUN_MS) return finish('Wolf combat time limit reached');
                    bars=current.hud.enemyBars;
                    if (Array.isArray(bars)&&bars.length) break;
                }
                if (!Array.isArray(bars)||bars.length===0) return finish('Enemy bars did not return within the bounded reacquisition window');
            }
            var bar=bars[0],width=Number(bar.width);
            if (!Number.isFinite(width)||width<=0) return finish('Wolf enemy bar width unavailable');
            if (bars.length!==1) {bestWidth=null;noDamage=0;lastSeekNoDamage=0;}
            else if (bestWidth===null || width<bestWidth-WOLF_BAR_PROGRESS_TOLERANCE) {bestWidth=width;noDamage=0;lastSeekNoDamage=0;}
            else if (width>bestWidth+WOLF_BAR_PROGRESS_TOLERANCE) {bestWidth=width;noDamage=0;lastSeekNoDamage=0;}
            if (bars.length===1&&noDamage>=2&&noDamage-lastSeekNoDamage>=2&&typeof api.wolfCombatSeek==='function') {
                if (presses>=WOLF_MAX_ACTIONS) return finish('Wolf combat action limit reached before bounded approach');
                var targetX=Number(bar.x),targetY=Number(bar.y),seekKind=null,dx=0;
                if (!Number.isFinite(targetX)||!Number.isFinite(targetY)) return finish('Wolf enemy bar position unavailable for bounded approach');
                if (targetY<250||targetY>650||targetX<600||targetX>1350)
                    return finish('Wolf enemy bar outside bounded approach corridor');
                if (targetX>=WOLF_SEEK_CENTER_MIN&&targetX<=WOLF_SEEK_CENTER_MAX) {
                    if (seekForward>=WOLF_SEEK_FORWARD_LIMIT) return finish('Wolf bounded approach pulse limit reached');
                    seekKind='forward';
                } else {
                    if (seekTurns>=WOLF_SEEK_TURN_LIMIT) return finish('Wolf bounded camera correction limit reached');
                    // Match the controller's established aim convention: a target
                    // right of center gets a positive mouse delta, and vice versa.
                    seekKind='turn';dx=Math.max(-32,Math.min(32,targetX-960));
                }
                api.checkStop();
                var seekStarted=api.now();
                await api.wolfCombatSeek(seekKind,current.frameId,dx,seekKind==='forward'?WOLF_SEEK_FORWARD_MS:0);
                presses++;inputMs+=Math.max(0,api.now()-seekStarted);
                if (seekKind==='forward') seekForward++; else seekTurns++;
                lastSeekNoDamage=noDamage;
                if (api.now()-began>=WOLF_MAX_RUN_MS) return finish('Wolf combat time limit reached after bounded approach');
                if (seekKind==='forward') await api.sleep(WOLF_SEEK_FORWARD_MS);
                current=await fresh();currentEvidence=await checkedFresh(current);current=currentEvidence.observation;reason=currentEvidence.reason;
                if (reason) return finish(reason);
                if (api.now()-began>=WOLF_MAX_RUN_MS) return finish('Wolf combat time limit reached after bounded approach');
                continue;
            }
            var key=null,now=api.now();
            if (now-lastE>=WOLF_SKILL_COOLDOWN_MS) key='VK_E';
            else if (now-lastAttack>=WOLF_ATTACK_INTERVAL_MS) key='VK_LBUTTON';
            else { await api.sleep(Math.max(1,WOLF_ATTACK_INTERVAL_MS-(now-lastAttack))); continue; }
            api.checkStop();
            var started=api.now(); await api.wolfCombatKey(key); presses++;
            inputMs+=Math.max(0,api.now()-started);
            if (key==='VK_E') lastE=api.now(); else lastAttack=api.now();
            await api.sleep(WOLF_ATTACK_INTERVAL_MS);
            current=await fresh(); currentEvidence=await checkedFresh(current); current=currentEvidence.observation; reason=currentEvidence.reason;
            if (reason) return finish(reason);
            if (Array.isArray(current.hud.enemyBars)&&current.hud.enemyBars.length===1) {
                var nextWidth=Number(current.hud.enemyBars[0].width);
                if (!Number.isFinite(nextWidth)||nextWidth<=0) return finish('Wolf enemy bar width unavailable');
                if (nextWidth<bestWidth-WOLF_BAR_PROGRESS_TOLERANCE) {bestWidth=nextWidth;noDamage=0;lastSeekNoDamage=0;}
                else if (nextWidth>bestWidth+WOLF_BAR_PROGRESS_TOLERANCE) {bestWidth=nextWidth;noDamage=0;lastSeekNoDamage=0;}
                else if (key==='VK_LBUTTON') noDamage++;
                if (noDamage>=6&&typeof api.wolfCombatSeek!=='function')
                    return finish('Enemy bar showed no damage progress across six attacks');
            } else if (Array.isArray(current.hud.enemyBars)&&current.hud.enemyBars.length>1) {
                bestWidth=null;noDamage=0;lastSeekNoDamage=0;
            }
            // The checked post-action observation is also the next decision frame.
            // The next loop reuses it unless its one-second safety window expires.
        }
    }

    async function runWolfTurretPass(options) {
        options=options||{};
        var current=options.observation,now=options.now,observe=options.observe,sleep=options.sleep,checkStop=options.checkStop;
        var wolfReady=options.wolfReady,wolfAdvanceState=options.wolfAdvanceState,wolfCast=options.wolfCast;
        var skillAttempts=0,forwardAttempts=0;
        function result(status,reason,frame) {
            return {status:status,step:'wolfTurretPass',reason:reason,skillAttempts:skillAttempts,forwardAttempts:forwardAttempts,
                targetEffectVerified:false,passageVerified:false,frameId:frame&&frame.frameId||null};
        }
        if(typeof now!=='function'||typeof observe!=='function'||typeof sleep!=='function'||typeof checkStop!=='function'||
            typeof wolfReady!=='function'||typeof wolfAdvanceState!=='function'||typeof wolfCast!=='function')
            return result('stopped','Wolf turret-pass API unavailable',current);
        function stateError(observation,baseline) {
            if(!observation||!observation.hud||!wolfReady(observation,now())) return 'Fresh Trial Kaeya Wolf HUD unavailable';
            var h=observation.hud,hp=h.health;
            if(!hp||!Number.isFinite(Number(hp.current))||!Number.isFinite(Number(hp.max))||Number(hp.max)!==1427||
                Number(hp.current)<Number(hp.max)*MIN_HEALTH_RATIO||Number(hp.current)>Number(hp.max)) return 'Wolf health or Kaeya max-HP evidence unsafe';
            var safe=wolfAdvanceState(observation,baseline);
            if(!safe||safe.ok!==true) return safe&&safe.reason||'Wolf grounded action state unsafe';
            return null;
        }
        var hp=current&&current.hud&&current.hud.health;
        var baseline=hp&&Number.isFinite(Number(hp.current))&&Number.isFinite(Number(hp.max))?
            {current:Number(hp.current),max:Number(hp.max)}:null;
        var reason=stateError(current,baseline);
        if(reason) return result('stopped',reason,current);
        checkStop();
        await wolfCast();skillAttempts=1;
        await sleep(100);checkStop();
        current=await observe();checkStop();
        return result('stopped','One Kaeya skill attempt observed; turret shutdown unverified, no passage movement allowed',current);
    }

    function aerialEvidenceError(observation, initialHealth) {
        if (!observation || !observation.hud) return 'Aerial HUD evidence unavailable';
        var h=observation.hud;
        if (observation.map !== null || h.journal || h.bigMap || h.dialogueReady || h.choice || h.world===true)
            return 'Aerial encounter screen changed';
        var hp=h.health;
        if (!hp || !Number.isFinite(Number(hp.current)) || !Number.isFinite(Number(hp.max)) || Number(hp.max)<=0 ||
            Number(hp.current)<0 || Number(hp.current)>Number(hp.max)) return 'Aerial player health unavailable';
        var current=Number(hp.current),max=Number(hp.max);
        if (h.lowHealth===true || current/max<AERIAL_MIN_HEALTH_RATIO) return 'Aerial player health below 60%';
        if (initialHealth && initialHealth.current-current > initialHealth.max*AERIAL_MAX_HEALTH_LOSS_RATIO)
            return 'Aerial player health dropped more than 10% of maximum';
        if (h.aerialBossVisible!==true) return 'Encounter transition: Stormterror indicators disappeared';
        if (!h.aerialBoss) return 'Aerial boss health bar evidence unavailable';
        var fraction=Number(h.aerialBoss.barFraction);
        if (!Number.isFinite(fraction) || fraction<=0 || fraction>1) return 'Aerial boss health bar evidence unavailable';
        return null;
    }

    async function runAerial(request, observation, api, observe) {
        var began=api.now(),actions=0,bursts=0,inputMs=0,noProgress=0;
        var runLimit=typeof request.deadlineMs==='number'&&Number.isFinite(request.deadlineMs)&&request.deadlineMs>0?
            Math.min(request.deadlineMs,60000):60000;
        function stopped(reason) {
            return {status:'stopped',reason:reason,elapsedMs:Math.max(0,api.now()-began),actions:actions,
                attacks:0,skills:0,bursts:bursts,inputMs:inputMs,mode:'aerial',questCompleted:false};
        }
        async function resolveAerialEvidence(candidate, healthBaseline) {
            var reason=aerialEvidenceError(candidate,healthBaseline),retries=0;
            function missingBossEvidence(value) {
                return value==='Encounter transition: Stormterror indicators disappeared' ||
                    value==='Aerial boss health bar evidence unavailable';
            }
            while(missingBossEvidence(reason)&&retries<2) {
                api.checkStop();await api.sleep(180);api.checkStop();candidate=await observe();api.checkStop();retries++;
                reason=aerialEvidenceError(candidate,healthBaseline);
            }
            return {observation:candidate,reason:reason};
        }
        if (!request || request.objective!==AERIAL_OBJECTIVE) return stopped('Unsupported combat objective');
        if (typeof observe!=='function'||typeof api.now!=='function'||typeof api.sleep!=='function'||
            typeof api.checkStop!=='function'||typeof api.fireAerial!=='function') return stopped('Aerial combat API unavailable');
        var evidence=await resolveAerialEvidence(observation,null);
        observation=evidence.observation;
        if(evidence.reason) return stopped(evidence.reason);
        var initialHealth={current:Number(observation.hud.health.current),max:Number(observation.hud.health.max)};
        var bestBar=Number(observation.hud.aerialBoss.barFraction);
        while(true) {
            api.checkStop();
            if(api.now()-began>=runLimit) return stopped('Aerial encounter deadline reached');
            if(bursts>=MAX_AERIAL_BURSTS) return stopped('Aerial burst limit reached');
            var fireStarted=api.now();
            await api.fireAerial(800);actions++;bursts++;inputMs+=Math.max(0,api.now()-fireStarted);
            await api.sleep(60);
            var current=await observe();api.checkStop();
            evidence=await resolveAerialEvidence(current,initialHealth);
            current=evidence.observation;reason=evidence.reason;
            if(reason) return stopped(reason);
            var bar=Number(current.hud.aerialBoss.barFraction);
            if(bar<bestBar-0.005) {bestBar=bar;noProgress=0;} else noProgress++;
            if(noProgress>=8) return stopped('Aerial boss bar made no progress after eight bursts; inspect aim');
        }
    }

    function stop(reason, began, api, actions, attacks, skills, bursts, character, ranged, paused) {
        return {
            status: 'stopped', reason: reason,
            elapsedMs: Math.max(0, api.now() - began),
            actions: actions, attacks: attacks, skills: skills, bursts: bursts,
            character: character, ranged: ranged === true, paused: paused === true
        };
    }

    function evidenceError(observation, initialHealth, expectedObjective) {
        if (observation && observation.hud &&
            (observation.hud.objectiveCompleted === true || observation.hud.questCompleted === true))
            return 'Objective completion verified';
        if (!observation || !observation.hud || observation.hud.world !== true)
            return 'World HUD unavailable';
        var hud = observation.hud;
        if (hud.objectiveChanged === true) return 'Objective changed';
        if (!Array.isArray(hud.objectives) || hud.objectives.indexOf(expectedObjective) < 0)
            return 'Expected objective missing or changed';
        var health = hud.health;
        if (!health || !Number.isFinite(Number(health.current)) || !Number.isFinite(Number(health.max)) || Number(health.max) <= 0)
            return 'Health evidence unavailable';
        var current = Number(health.current), max = Number(health.max);
        if (current / max < MIN_HEALTH_RATIO) return 'Health below 60%';
        if (initialHealth && initialHealth.current - current >= initialHealth.max * MAX_HEALTH_LOSS_RATIO)
            return 'Health dropped 20% or more of maximum';
        return null;
    }

    function isSupportedObjective(value) { return OBJECTIVES.indexOf(value) >= 0; }

    async function run(request, observation, api, observe) {
        if(request&&request.objective===AERIAL_OBJECTIVE) return runAerial(request,observation,api,observe);
        var began = api.now(), actions = 0, attacks = 0, skills = 0, bursts = 0;
        var runLimitMs = typeof request.deadlineMs === 'number' && Number.isFinite(request.deadlineMs) && request.deadlineMs > 0
            ? Math.min(request.deadlineMs, MAX_RUN_MS) : MAX_RUN_MS;
        var initialHealth = null, lastSkillAt = null, scans = 0, cameraCorrections = 0;
        var approachSteps = 0, approachStalls = 0;
        var character = 'Traveler', ranged = false, amberSwitches = 0;
        async function result(reason) {
            var paused = false, completionVerified = reason === 'Objective completion verified';
            if (reason !== 'Combat API unavailable' && reason !== 'Unsupported combat objective' &&
                request && isSupportedObjective(request.objective) && typeof api.pauseCombat === 'function' &&
                typeof api.checkStop === 'function' && typeof observe === 'function') {
                // Exceptions from stop/readiness checks intentionally escape without attempting a pause.
                api.checkStop();
                var fresh = await observe();
                api.checkStop();
                completionVerified = completionVerified || !!(fresh && fresh.hud &&
                    (fresh.hud.objectiveCompleted === true || fresh.hud.questCompleted === true));
                if (fresh && fresh.hud && fresh.hud.world === true) {
                    var pauseRequested = await api.pauseCombat();
                    if (pauseRequested) {
                        var afterPause = await observe();
                        api.checkStop();
                        paused = !!(afterPause && afterPause.hud && afterPause.hud.journal === true);
                    }
                }
            }
            var stopped = stop(completionVerified ? 'Objective completion verified' : reason,
                began, api, actions, attacks, skills, bursts, character, ranged, paused);
            stopped.status = completionVerified ? 'completed' : 'stopped';
            stopped.outcome = completionVerified ? 'objective_completed' : 'combat_stopped';
            return stopped;
        }
        async function retryTransientEvidence(candidate, healthBaseline) {
            var reason = evidenceError(candidate, healthBaseline, request.objective), retries = 0;
            function transientEvidence() {
                if (reason === 'World HUD unavailable' || reason === 'Health evidence unavailable') return true;
                return reason === 'Expected objective missing or changed' &&
                    !(candidate && candidate.hud && candidate.hud.objectiveChanged === true);
            }
            while (transientEvidence() && retries < MAX_EVIDENCE_RETRIES) {
                api.checkStop();
                await api.sleep(EVIDENCE_RETRY_DELAY_MS);
                api.checkStop();
                candidate = await observe();
                api.checkStop();
                retries++;
                reason = evidenceError(candidate, healthBaseline, request.objective);
            }
            return { observation: candidate, reason: reason };
        }
        async function switchToAmberIfPossible() {
            if (api.now() - began >= runLimitMs) return { reason: 'Combat deadline reached' };
            if (actions >= MAX_ACTIONS) return { reason: 'Combat action limit reached' };
            if (ranged || amberSwitches > 0 || typeof api.selectAmber !== 'function') return false;
            api.checkStop();
            await api.selectAmber();
            actions++; amberSwitches++; character = 'Amber'; ranged = true;
            await api.sleep(500);
            current = await observe();
            var amberEvidence = await retryTransientEvidence(current, null);
            current = amberEvidence.observation;
            if (amberEvidence.reason) return { reason: amberEvidence.reason };
            initialHealth = { current: Number(current.hud.health.current), max: Number(current.hud.health.max) };
            lastSkillAt = null;
            approachSteps = 0; approachStalls = 0; cameraCorrections = 0; scans = 0;
            return true;
        }
        if (!request || !isSupportedObjective(request.objective)) return result('Unsupported combat objective');
        if (typeof observe !== 'function' || typeof api.now !== 'function' || typeof api.sleep !== 'function' ||
            typeof api.checkStop !== 'function' || typeof api.selectTraveler !== 'function' ||
            typeof api.combatAttack !== 'function') return result('Combat API unavailable');

        var initialEvidence = await retryTransientEvidence(observation, null);
        observation = initialEvidence.observation;
        var reason = initialEvidence.reason;
        if (reason) return result(reason);
        initialHealth = { current: Number(observation.hud.health.current), max: Number(observation.hud.health.max) };

        api.checkStop();
        await api.selectTraveler();
        actions++;
        await api.sleep(CHARACTER_SWITCH_DELAY_MS);
        var current = await observe();
        var switchedEvidence = await retryTransientEvidence(current, null);
        current = switchedEvidence.observation;
        reason = switchedEvidence.reason;
        if (reason) return result(reason);
        initialHealth = { current: Number(current.hud.health.current), max: Number(current.hud.health.max) };

        if (typeof api.prepareCombatView === 'function' && await api.prepareCombatView()) {
            actions++;
            await api.sleep(250); current = await observe();
            var preparedEvidence = await retryTransientEvidence(current, initialHealth);
            current = preparedEvidence.observation;
            if (preparedEvidence.reason) return result(preparedEvidence.reason);
        }
        while (true) {
            api.checkStop();
            if (api.now() - began >= runLimitMs) return result('Combat deadline reached');
            if (actions >= MAX_ACTIONS) return result('Combat action limit reached');
            var loopEvidence = await retryTransientEvidence(current, initialHealth);
            current = loopEvidence.observation;
            reason = loopEvidence.reason;
            if (reason) return result(reason);

            var bars = current.hud.enemyBars || [], enemy = null;
            var closeEnemy = false, centeredEnemy = false;
            if (typeof api.combatLook === 'function') {
                if (!bars.length) {
                    cameraCorrections = 0;
                    if (scans >= MAX_CAMERA_SCANS) return result('No enemy health bar found after four bounded camera scans');
                    scans++;
                    await api.combatLook(250); actions++; await api.sleep(250);current=await observe();continue;
                }
                scans = 0;
                enemy=bars.slice().sort(function(a,b){
                    return Number(b.height)-Number(a.height) || Math.abs(a.x-960)-Math.abs(b.x-960);
                })[0];
                closeEnemy = Number(enemy.height) >= 6;
                centeredEnemy = Math.abs(enemy.x - 960) <= (ranged ? 220 : 140);
                if (closeEnemy && !ranged) {
                    // Prioritize the strongest visible bar; preserve native auto-targeting.
                    cameraCorrections = 0;
                } else if (!centeredEnemy) {
                    if (cameraCorrections >= MAX_CAMERA_CORRECTIONS)
                        return result('Enemy camera alignment exceeded four corrections');
                    cameraCorrections++;
                    await api.combatLook(Math.max(-250,Math.min(250,Math.round((enemy.x-960)*0.5))));actions++;
                    await api.sleep(250);current=await observe();continue;
                } else {
                    cameraCorrections = 0;
                    if (!ranged && typeof api.combatAdvance === 'function') {
                        if (approachSteps >= MAX_APPROACH_STEPS)
                            return result('Combat approach reached six steps without a close enemy');
                        var beforeMap = current.map;
                        api.checkStop();
                        await api.combatAdvance(); actions++; approachSteps++;
                        await api.sleep(APPROACH_OBSERVE_DELAY_MS);
                        current = await observe();
                        var approachEvidence = await retryTransientEvidence(current, initialHealth);
                        current = approachEvidence.observation;
                        if (approachEvidence.reason) return result(approachEvidence.reason);
                        var afterMap = current.map;
                        var mapMoved = beforeMap && afterMap && Number.isFinite(Number(beforeMap.x)) &&
                            Number.isFinite(Number(beforeMap.y)) && Number.isFinite(Number(afterMap.x)) &&
                            Number.isFinite(Number(afterMap.y)) &&
                            Math.hypot(Number(afterMap.x) - Number(beforeMap.x), Number(afterMap.y) - Number(beforeMap.y)) >= 0.3;
                        approachStalls = mapMoved ? 0 : approachStalls + 1;
                        var closeAfterApproach = (current.hud.enemyBars || []).some(function (bar) { return Number(bar.height) >= 6; });
                        if (approachStalls >= MAX_APPROACH_STALLS && !closeAfterApproach) {
                            var stallSwitch = await switchToAmberIfPossible();
                            if (stallSwitch === true) continue;
                            if (stallSwitch && stallSwitch.reason) return result(stallSwitch.reason);
                            return result('Combat approach stalled for two observed steps');
                        }
                        if (approachSteps >= MAX_APPROACH_STEPS && !closeAfterApproach) {
                            var rangeSwitch = await switchToAmberIfPossible();
                            if (rangeSwitch === true) continue;
                            if (rangeSwitch && rangeSwitch.reason) return result(rangeSwitch.reason);
                            return result('Combat approach reached six steps without a close enemy');
                        }
                        continue;
                    }
                }
            }
            if (bursts === 0 && typeof api.combatBurst === 'function' && actions < MAX_ACTIONS &&
                bars.length > 0 && (closeEnemy || centeredEnemy)) {
                api.checkStop();
                await api.combatBurst();
                actions++; bursts++;
                await api.sleep(BURST_OBSERVE_DELAY_MS);
                current = await observe();
                var burstEvidence = await retryTransientEvidence(current, initialHealth);
                current = burstEvidence.observation;
                if (burstEvidence.reason) return result(burstEvidence.reason);
                continue;
            }
            if (typeof api.combatSkill === 'function'  &&
                (lastSkillAt === null || api.now() - lastSkillAt >= SKILL_INTERVAL_MS)) {
                await api.combatSkill();
                actions++; skills++; lastSkillAt = api.now();
                await api.sleep(OBSERVE_DELAY_MS);
                current = await observe();
            } else {
                var currentHealthRatio = Number(current.hud.health.current) / Number(current.hud.health.max);
                var nearRecognizedEnemy = enemy && Number(enemy.height) >= 6 && Math.abs(enemy.x - 960) <= 260;
                var canBurst = nearRecognizedEnemy && currentHealthRatio >= 0.8 && actions + 2 <= MAX_ACTIONS;
                await api.combatAttack();
                actions++; attacks++;
                if (canBurst) {
                    // Separate clicks so the game's normal-attack animation can advance between presses.
                    await api.sleep(200);
                    api.checkStop();
                    await api.combatAttack();
                    actions++; attacks++;
                    await api.sleep(200);
                } else {
                    await api.sleep(OBSERVE_DELAY_MS);
                }
                current = await observe();
            }
            var actionEvidence = await retryTransientEvidence(current, initialHealth);
            current = actionEvidence.observation;
            reason = actionEvidence.reason;
            if (reason) return result(reason);
        }
    }

    return { run: run, runWolf:runWolf, runWolfTurretPass:runWolfTurretPass, runAerial:runAerial, aerialObjective:AERIAL_OBJECTIVE, objective: OBJECTIVE, objectives: OBJECTIVES.slice() };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = ActOneCombat;
