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
            var spikePause=result.step==='wolfSpikeCrossFirst'&&row.status==='stopped'&&result.status==='stopped'&&
                result.pauseVerified===true&&result.questComplete===false&&result.continueAttempts===1&&result.pauseAttempts===1&&
                Number.isInteger(result.characterSelectionAttempts)&&result.characterSelectionAttempts>=0&&result.characterSelectionAttempts<=2&&
                Number.isInteger(result.skillAttempts)&&result.skillAttempts>=0&&result.skillAttempts<=1&&
                Number.isInteger(result.movementAttempts)&&result.movementAttempts>=0&&result.movementAttempts<=4;
            var secondSpikePause=result.step==='wolfSpikeCrossSecond'&&row.status==='stopped'&&result.status==='stopped'&&
                result.pauseVerified===true&&result.secondPitComplete===false&&result.questComplete===false&&
                result.continueAttempts===1&&result.pauseAttempts===1&&
                Number.isInteger(result.characterSelectionAttempts)&&result.characterSelectionAttempts>=0&&result.characterSelectionAttempts<=2&&
                Number.isInteger(result.skillAttempts)&&result.skillAttempts>=0&&result.skillAttempts<=1&&
                Number.isInteger(result.movementAttempts)&&result.movementAttempts>=0&&result.movementAttempts<=3;
            var cryoSkillAttempted=result&&result.skillAttempted===true&&result.skillAttempts===1;
            var cryoSkillSkipped=result&&result.skillAttempted===false&&result.skillAttempts===0;
            var cryoWaitPause=result.step==='wolfCryoWait'&&row.status==='stopped'&&result.pauseVerified===true&&
                result.continueAttempts===1&&(cryoSkillAttempted||cryoSkillSkipped)&&result.pauseAttempts===1&&
                result.targetEffectVerified===false&&result.questComplete===false;
            if(result.step!=='wolfPause'&&!combatPause&&!cryoWaitPause&&!spikePause&&!secondSpikePause||!Array.isArray(events)||
                expectedId&&row.id!==expectedId||typeof row.id!=='string') return false;
            if(secondSpikePause) {
                var secondContinues=events.filter(function(e){return e&&e.type==='wolfSecondContinue';});
                var secondPlans=events.filter(function(e){return e&&e.type==='wolfSecondCooldownPlan';});
                var secondKeys=events.filter(function(e){return e&&e.type==='key';});
                if(secondContinues.length!==1||secondPlans.length>1||secondKeys.length<1||
                   events.some(function(e){return !e||['controllerRevision','wolfSecondContinue','wolfSecondCooldownPlan','key'].indexOf(e.type)<0;}))return false;
                var secondContinue=secondContinues[0];
                if(!Number.isInteger(secondContinue.frameId)||secondContinue.frameId<0||!Number.isFinite(secondContinue.startedAt)||
                   !Number.isFinite(secondContinue.finishedAt)||secondContinue.finishedAt<secondContinue.startedAt)return false;
                if(secondPlans.length&&(!Number.isInteger(secondPlans[0].frameId)||secondPlans[0].frameId<=secondContinue.frameId||
                   !Number.isFinite(secondPlans[0].startedAt)||secondPlans[0].startedAt<secondContinue.finishedAt||
                   !Number.isInteger(secondPlans[0].waitMs)||secondPlans[0].waitMs<0||secondPlans[0].waitMs>6500))return false;
                var secondCounts={'VK_3':0,'VK_E':0,'VK_2':0,'VK_W':0,'VK_ESCAPE':0},lastSecondFrame=secondContinue.frameId,lastSecondTime=secondContinue.finishedAt;
                for(var q=0;q<secondKeys.length;q++) {
                    var secondKey=secondKeys[q];
                    if(!Object.prototype.hasOwnProperty.call(secondCounts,secondKey.key)||!Number.isInteger(secondKey.frameId)||
                       secondKey.frameId<=lastSecondFrame||!Number.isFinite(secondKey.startedAt)||!Number.isFinite(secondKey.finishedAt)||
                       secondKey.finishedAt<secondKey.startedAt||secondKey.startedAt<lastSecondTime)return false;
                    if(secondKey.durationMs!==(secondKey.key==='VK_W'?600:60))return false;
                    secondCounts[secondKey.key]++;lastSecondFrame=secondKey.frameId;lastSecondTime=secondKey.finishedAt;
                }
                var secondEscape=secondKeys[secondKeys.length-1];
                var secondSawSelect=false,secondSawSkill=false,secondSawAmber=false,secondSawMove=false;
                for(var a=0;a<secondKeys.length-1;a++) {
                    var actionKey=secondKeys[a].key;
                    if(actionKey==='VK_3') {if(secondSawSelect||secondSawSkill)return false;secondSawSelect=true;}
                    else if(actionKey==='VK_E') {if(!secondSawSelect||secondSawSkill)return false;secondSawSkill=true;}
                    else if(actionKey==='VK_2') {if(!secondSawSkill||secondSawAmber||secondSawMove)return false;secondSawAmber=true;}
                    else if(actionKey==='VK_W') {if(!secondSawSkill||!secondSawAmber)return false;secondSawMove=true;}
                    else return false;
                }
                if(secondPlans.length&&(secondPlans[0].frameId>=secondEscape.frameId||secondPlans[0].startedAt>secondEscape.startedAt||
                   secondSawSkill&&(!secondSawSelect||secondPlans[0].frameId<=secondKeys[0].frameId||
                   secondPlans[0].frameId>=secondKeys.filter(function(e){return e.key==='VK_E';})[0].frameId||
                   secondPlans[0].startedAt>secondKeys.filter(function(e){return e.key==='VK_E';})[0].startedAt)))return false;
                if(secondCounts.VK_ESCAPE!==1||secondEscape.key!=='VK_ESCAPE'||secondCounts.VK_3>1||secondCounts.VK_E>1||
                   secondCounts.VK_2>1||secondCounts.VK_W>3||
                   secondCounts.VK_3+secondCounts.VK_2>result.characterSelectionAttempts||
                   result.characterSelectionAttempts-secondCounts.VK_3-secondCounts.VK_2>1||
                   secondCounts.VK_E>result.skillAttempts||result.skillAttempts-secondCounts.VK_E>1||
                   secondCounts.VK_W>result.movementAttempts||result.movementAttempts-secondCounts.VK_W>1)return false;
                var secondInputAt=latestWolfInputAt(history,null);
                if(!Number.isInteger(result.lastFrameId)||result.lastFrameId<=secondEscape.frameId||
                   !Number.isFinite(result.lastTimestamp)||result.lastTimestamp<secondEscape.finishedAt||
                   !Number.isInteger(row.frameId)||row.frameId<result.lastFrameId||!Number.isFinite(row.timestamp)||row.timestamp<secondEscape.finishedAt||
                   secondInputAt!==secondEscape.startedAt||!hasWolfPauseMenu(observation)||!observation||observation.session!==session||
                   !Number.isInteger(observation.frameId)||observation.frameId<result.lastFrameId||
                   !Number.isFinite(observation.timestamp)||observation.timestamp<result.lastTimestamp||observation.timestamp<=secondEscape.finishedAt)return false;
                return true;
            }
            if(spikePause) {
                var spikeContinues=events.filter(function(e){return e&&e.type==='wolfSpikeContinue';});
                var spikeJumps=events.filter(function(e){return e&&e.type==='wolfSpikeLandingJump';});
                var spikeEscapes=events.filter(function(e){return e&&e.type==='key'&&e.key==='VK_ESCAPE';});
                var spikeKeys=events.filter(function(e){return e&&e.type==='key';});
                if(spikeContinues.length!==1||spikeEscapes.length!==1||spikeKeys.length<1||
                   spikeContinues[0].type!=='wolfSpikeContinue'||!Number.isInteger(spikeContinues[0].frameId)||
                   !Number.isFinite(spikeContinues[0].startedAt)||!Number.isFinite(spikeContinues[0].finishedAt)||
                   spikeContinues[0].finishedAt<spikeContinues[0].startedAt) return false;
                var jumpCount=Number.isInteger(result.jumpAttempts)?result.jumpAttempts:0;
                if(jumpCount<0||jumpCount>1||spikeJumps.length!==jumpCount) return false;
                var spikeEscape=spikeEscapes[0];
                if(!Number.isInteger(spikeEscape.frameId)||!Number.isFinite(spikeEscape.startedAt)||
                   !Number.isFinite(spikeEscape.finishedAt)||spikeEscape.finishedAt<spikeEscape.startedAt||
                   spikeEscape.startedAt<spikeContinues[0].finishedAt) return false;
                var spikeKeyCounts={'VK_3':0,'VK_E':0,'VK_2':0,'VK_W':0,'VK_ESCAPE':0};
                if(events.some(function(e){return !e||['controllerRevision','wolfSpikeContinue','wolfSpikeCooldownPlan','wolfSpikeLandingJump','key'].indexOf(e.type)<0;})) return false;
                var lastSpikeKeyAt=-Infinity;
                var lastSpikeKeyFrame=spikeContinues[0].frameId;
                for(var s=0;s<spikeKeys.length;s++) {
                    var keyEvent=spikeKeys[s];
                    if(!Object.prototype.hasOwnProperty.call(spikeKeyCounts,keyEvent.key)||!Number.isInteger(keyEvent.frameId)||
                       keyEvent.frameId<=lastSpikeKeyFrame||!Number.isFinite(keyEvent.startedAt)||
                       !Number.isFinite(keyEvent.finishedAt)||keyEvent.finishedAt<keyEvent.startedAt||
                       keyEvent.startedAt<spikeContinues[0].finishedAt||keyEvent.startedAt<lastSpikeKeyAt) return false;
                    spikeKeyCounts[keyEvent.key]++;lastSpikeKeyAt=keyEvent.finishedAt;lastSpikeKeyFrame=keyEvent.frameId;
                }
                if(spikeJumps.length) {
                    var jump=spikeJumps[0],forwardBeforeJump=0,lastForward=null;
                    for(var w=0;w<spikeKeys.length;w++) if(spikeKeys[w].key==='VK_W'&&spikeKeys[w].frameId<jump.frameId) {
                        forwardBeforeJump++;lastForward=spikeKeys[w];
                    }
                    if(!Array.isArray(jump.keys)||jump.keys.length!==2||jump.keys[0]!=='VK_W'||jump.keys[1]!=='VK_SPACE'||
                       jump.durationMs!==500||jump.spaceDurationMs!==60||jump.keysReleased!==true||forwardBeforeJump<3||!lastForward||
                       !Number.isInteger(jump.frameId)||jump.frameId<=lastForward.frameId||jump.frameId>=spikeEscape.frameId||
                       !Number.isFinite(jump.startedAt)||!Number.isFinite(jump.finishedAt)||jump.finishedAt<jump.startedAt||
                       jump.startedAt<lastForward.finishedAt||jump.finishedAt>spikeEscape.startedAt||
                       spikeKeys.some(function(e){return e.key==='VK_W'&&e.frameId>jump.frameId;})) return false;
                }
                if(spikeKeyCounts.VK_ESCAPE!==1||spikeKeys[spikeKeys.length-1]!==spikeEscape||
                   spikeKeyCounts.VK_3>1||spikeKeyCounts.VK_2>1||spikeKeyCounts.VK_E>1||spikeKeyCounts.VK_W>4||
                   spikeKeyCounts.VK_3>result.characterSelectionAttempts||spikeKeyCounts.VK_2>result.characterSelectionAttempts||
                   spikeKeyCounts.VK_3+spikeKeyCounts.VK_2>result.characterSelectionAttempts||
                   result.characterSelectionAttempts-spikeKeyCounts.VK_3-spikeKeyCounts.VK_2>1||
                   spikeKeyCounts.VK_E>result.skillAttempts||result.skillAttempts-spikeKeyCounts.VK_E>1||
                   spikeKeyCounts.VK_W>result.movementAttempts||result.movementAttempts-spikeKeyCounts.VK_W>1) return false;
                var spikeInputAt=latestWolfInputAt(history,null);
                if(!Number.isInteger(result.lastFrameId)||result.lastFrameId<=spikeEscape.frameId||
                   !Number.isFinite(result.lastTimestamp)||result.lastTimestamp<spikeEscape.finishedAt||
                   !Number.isInteger(row.frameId)||row.frameId<result.lastFrameId||
                   !Number.isFinite(row.timestamp)||row.timestamp<spikeEscape.finishedAt||
                   spikeInputAt!==spikeEscape.startedAt||!hasWolfPauseMenu(observation)||!observation||observation.session!==session||
                   !Number.isInteger(observation.frameId)||observation.frameId<result.lastFrameId||
                   !Number.isFinite(observation.timestamp)||observation.timestamp<result.lastTimestamp||
                   observation.timestamp<=spikeEscape.finishedAt) return false;
                return true;
            }
            if(cryoWaitPause) {
                var continueEvents=events.filter(function(e){return e&&e.type==='wolfCryoWaitContinue';});
                var skillEvents=events.filter(function(e){return e&&e.type==='wolfCryoWaitSkill';});
                var cryoEscapes=events.filter(function(e){return e&&e.type==='wolfCryoWaitEscape';});
                if(continueEvents.length!==1||skillEvents.length!==(cryoSkillAttempted?1:0)||cryoEscapes.length!==1) return false;
                var sequence=[continueEvents[0]].concat(cryoSkillAttempted?[skillEvents[0]]:[]).concat([cryoEscapes[0]]);
                for(var i=0;i<sequence.length;i++) {
                    if(!Number.isInteger(sequence[i].frameId)||sequence[i].frameId<0||!Number.isFinite(sequence[i].startedAt)||
                       !Number.isFinite(sequence[i].finishedAt)||sequence[i].finishedAt<sequence[i].startedAt||
                       i>0&&(sequence[i].frameId<=sequence[i-1].frameId||sequence[i].startedAt<sequence[i-1].finishedAt)) return false;
                }
                if(cryoSkillAttempted&&(skillEvents[0].key!=='VK_E'||skillEvents[0].finishedAt>cryoEscapes[0].startedAt)||
                   cryoEscapes[0].key!=='VK_ESCAPE') return false;
                var genericKeys=events.filter(function(e){return e&&e.type==='key';});
                var expectedKeys=cryoSkillAttempted?['VK_E','VK_ESCAPE']:['VK_ESCAPE'];
                if(genericKeys.length!==expectedKeys.length) return false;
                for(var k=0;k<genericKeys.length;k++) {
                    if(genericKeys[k].key!==expectedKeys[k]||!Number.isFinite(genericKeys[k].startedAt)||
                       !Number.isFinite(genericKeys[k].finishedAt)||genericKeys[k].finishedAt<genericKeys[k].startedAt) return false;
                }
                var continueEvent=continueEvents[0],escapeEvent=cryoEscapes[0],escapeKey=genericKeys[genericKeys.length-1];
                if(genericKeys[0].startedAt< (cryoSkillAttempted?skillEvents[0].startedAt:continueEvent.startedAt)||
                   genericKeys[genericKeys.length-1].startedAt<escapeEvent.startedAt||
                   cryoSkillAttempted&&genericKeys[0].finishedAt>escapeEvent.startedAt) return false;
                var hasUnexpectedInput=events.some(function(e){return !e||(
                    ['controllerRevision','wolfCryoWaitPlan','wolfCryoWaitContinue','wolfCryoWaitSkill','wolfCryoWaitEscape','key'].indexOf(e.type)<0||
                    e.type==='rotate'||e.type==='click'||e.type==='wolfContinue'||
                    e.key!==undefined&&e.type!=='key'&&e!==skillEvents[0]&&e!==escapeEvent||
                    (e.type==='wolfCryoWaitContinue'&&e!==continueEvent)||
                    (e.type==='wolfCryoWaitSkill'&&(!cryoSkillAttempted||e!==skillEvents[0]))||
                    (e.type==='wolfCryoWaitEscape'&&e!==escapeEvent));
                });
                if(hasUnexpectedInput) return false;
                var latestInputAtExpected=escapeKey.startedAt;
                if(!Number.isFinite(row.timestamp)||row.timestamp<escapeKey.finishedAt||latestInputAt!==latestInputAtExpected||
                   !Number.isInteger(result.frameId)||!Number.isInteger(row.frameId)||result.frameId<=escapeEvent.frameId||row.frameId<result.frameId||
                   !hasWolfPauseMenu(observation)||!observation||observation.session!==session||
                   !Number.isInteger(observation.frameId)||observation.frameId<result.frameId||
                   !Number.isFinite(observation.timestamp)||observation.timestamp<=escapeKey.finishedAt) return false;
                return true;
            }
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
            'wolfLookDown','wolfLookUp','wolfKaeyaSkill','wolfDefensiveCryo','wolfAimCryo','wolfCloseFoodCryo','wolfTurretPass','wolfInventoryRecover','wolfCombat','wolfOpeningDialogue','wolfContinue','wolfPause','wolfCryoWait','wolfSpikeCrossFirst','wolfSpikeCrossSecond'];
        steps.push('wolfCharactersOpen','wolfWitnessAction');
        return history.some(function(row) {
            if (row.mission!=='questStep'||steps.indexOf(row.details&&row.details.result&&row.details.result.step)<0||
                !Array.isArray(row.details&&row.details.inputEvents)) return false;
            return row.details.inputEvents.some(function(event) {
                var step=row.details.result.step;
                return event&&(event.type==='wolfContinue'||event.type==='wolfSpikeContinue'||event.type==='wolfSpikeLandingJump'||event.type==='wolfSecondContinue'||
                    step==='wolfCharactersOpen'&&event.type==='wolfCharactersOpen'||
                    step==='wolfWitnessAction'&&(event.type==='wolfWitnessContinue'||event.type==='wolfWitnessEscape'||validWolfWitnessActionEvent(event))||
                    step==='wolfCryoWait'&&['wolfCryoWaitContinue','wolfCryoWaitSkill','wolfCryoWaitEscape'].indexOf(event.type)>=0||
                    event.type==='rotate'&&(step==='wolfCloseFoodCryo'||step==='wolfAimCryo'||step==='wolfWitnessAction')||
                    event.type==='key'&&(['VK_W','VK_A','VK_D','VK_ESCAPE','VK_B','VK_3','VK_E','VK_LBUTTON','VK_SPACE','VK_2'].indexOf(event.key)>=0||step==='wolfCharactersOpen'&&event.key==='VK_C'));
            });
        });
    }
    function validWolfWitnessActionEvent(event) {
        return !!event&&event.type==='wolfWitnessAction'&&['forwardFine','forwardBounded','leftFine','rightFine','lookLeft','lookRight','jumpForward','strike'].indexOf(event.action)>=0;
    }
    function wolfRequestInputProven(history, request) {
        if (!request||request.mission!=='questStep') return false;
        var keys={wolfAdvance:['VK_W'],wolfForward:['VK_W'],wolfForwardFine:['VK_W'],wolfLeft:['VK_A'],wolfRight:['VK_D'],wolfKaeyaSkill:['VK_3','VK_E'],wolfDefensiveCryo:['VK_E'],wolfAimCryo:['VK_W','VK_E'],wolfCloseFoodCryo:['VK_ESCAPE','VK_W','VK_E'],wolfTurretPass:['VK_E','VK_W'],
            wolfLookLeft:[],wolfLookRight:[],wolfLookDown:[],wolfLookUp:[],wolfCombat:['VK_3','VK_E','VK_LBUTTON'],wolfCryoWait:[],
            wolfSpikeCrossFirst:['VK_3','VK_E','VK_2','VK_W','VK_ESCAPE'],wolfSpikeCrossSecond:['VK_3','VK_E','VK_2','VK_W','VK_ESCAPE'],
            wolfCharactersOpen:['VK_C'],wolfWitnessAction:['VK_W','VK_A','VK_D','VK_SPACE','VK_LBUTTON','VK_E'],
            wolfInventoryRecover:['VK_B'],wolfOpeningDialogue:['VK_SPACE'],wolfContinue:[],wolfPause:['VK_ESCAPE']};
        if (!Object.prototype.hasOwnProperty.call(keys,request.step)) return false;
        var rows=history.filter(function(row){return row.id===request.id&&row.mission==='questStep'&&row.details&&Array.isArray(row.details.inputEvents);});
        return rows.some(function(row){return row.details.inputEvents.some(function(event){
            return event&&((request.step==='wolfContinue'||request.step==='wolfInventoryRecover')&&event.type==='wolfContinue'||
                request.step==='wolfSpikeCrossFirst'&&['wolfSpikeContinue','wolfSpikeLandingJump'].indexOf(event.type)>=0||
                request.step==='wolfSpikeCrossSecond'&&event.type==='wolfSecondContinue'||
                request.step==='wolfCryoWait'&&['wolfCryoWaitContinue','wolfCryoWaitSkill','wolfCryoWaitEscape'].indexOf(event.type)>=0||
                request.step==='wolfCharactersOpen'&&event.type==='wolfCharactersOpen'||
                request.step==='wolfWitnessAction'&&(event.type==='wolfWitnessContinue'||event.type==='wolfWitnessEscape'||validWolfWitnessActionEvent(event))||
                request.step==='wolfWitnessAction'&&event.type==='rotate'||
                (request.step.indexOf('wolfLook')===0||request.step==='wolfCloseFoodCryo'||request.step==='wolfAimCryo')&&event.type==='rotate'||
                event.type==='key'&&keys[request.step].indexOf(event.key)>=0);
        });});
    }
    function latestWolfInputAt(history, request) {
        var steps=['wolfAdvance','wolfForward','wolfForwardFine','wolfLeft','wolfRight','wolfLookLeft','wolfLookRight',
            'wolfLookDown','wolfLookUp','wolfKaeyaSkill','wolfDefensiveCryo','wolfAimCryo','wolfCloseFoodCryo','wolfTurretPass','wolfInventoryRecover','wolfCombat','wolfOpeningDialogue','wolfContinue','wolfPause','wolfCryoWait','wolfSpikeCrossFirst','wolfSpikeCrossSecond'];
        steps.push('wolfCharactersOpen','wolfWitnessAction');
        var times=[];
        history.forEach(function(row) {
            var step=row.details&&row.details.result&&row.details.result.step;
            if (request&&row.id===request.id&&request.mission==='questStep') step=request.step;
            if (row.mission!=='questStep'||steps.indexOf(step)<0||!Array.isArray(row.details&&row.details.inputEvents)) return;
            row.details.inputEvents.forEach(function(event) {
                if (!event||!Number.isFinite(event.startedAt)) return;
                var valid=event.type==='wolfContinue'||step==='wolfSpikeCrossFirst'&&['wolfSpikeContinue','wolfSpikeLandingJump'].indexOf(event.type)>=0||step==='wolfSpikeCrossSecond'&&event.type==='wolfSecondContinue'||
                    step==='wolfCharactersOpen'&&event.type==='wolfCharactersOpen'||step==='wolfWitnessAction'&&(event.type==='wolfWitnessContinue'||event.type==='wolfWitnessEscape'||validWolfWitnessActionEvent(event))||
                    step==='wolfCryoWait'&&['wolfCryoWaitContinue','wolfCryoWaitSkill','wolfCryoWaitEscape'].indexOf(event.type)>=0||(step.indexOf('wolfLook')===0||step==='wolfCloseFoodCryo'||step==='wolfAimCryo'||step==='wolfWitnessAction')&&event.type==='rotate'||
                    event.type==='key'&&(['VK_W','VK_A','VK_D','VK_ESCAPE','VK_3','VK_E','VK_LBUTTON','VK_SPACE','VK_B','VK_2'].indexOf(event.key)>=0||step==='wolfCharactersOpen'&&event.key==='VK_C');
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
        if (typeof actOneWolfCharacterMenuVisible==='function'&&actOneWolfCharacterMenuVisible(observation,Date.now())) return true;
        if (typeof actOneWolfAmberLevelPanelVisible==='function'&&actOneWolfAmberLevelPanelVisible(observation,Date.now())) return true;
        return rows.some(function(row){return row.text&&(/^(Party Setup|Domain Entrance)$/.test(row.text.trim())||/\b(loading|entering|connecting)\b/i.test(row.text.trim()));});
    }
    function setWolfSafetyFault(reason) {
        safetyFault='Wolf domain safety stopped: '+reason;
        safetyFaultAt=Date.now();
        try { heartbeat(true,'faulted'); } catch (e) { log.info('Wolf safety fault could not be written to controller status: '+String(e&&e.message||e)); }
        log.info(safetyFault);
    }
    function clearWolfSafetyFault(history, observation, expectedId) {
        if (safetyFault&&wolfPauseProven(history,observation,expectedId,safetyFaultAt)) {
            safetyFault=null; safetyFaultAt=0; failure=null; heartbeat(true);
        }
    }
    function exactWolfClosingDialogue(observation) {
        if(!observation||observation.session!==session||!Number.isInteger(observation.frameId)||
            !Number.isFinite(observation.timestamp)||Date.now()<observation.timestamp||Date.now()-observation.timestamp>1000) return false;
        var h=observation.hud||{},rows=observation.ocr||[];
        if(h.world!==false||h.auto!==true||h.dialogueReady!==true||h.choice!==false||h.health!==null||
            Array.isArray(h.enemyBars)&&h.enemyBars.length>0) return false;
        return rows.some(function(row){return row&&typeof row.text==='string'&&row.text.trim()==='Auto'&&row.x<500&&row.y<200;})&&
            rows.some(function(row){return row&&typeof row.text==='string'&&row.text.trim()==='Kaeya'&&row.x>=0&&row.x<1920&&row.y>800;});
    }
    function wolfClosingStrikeProven(history, observation) {
        if(!wolfEntryProven(history)||!exactWolfClosingDialogue(observation)) return false;
        var latestInputAt=latestWolfInputAt(history,null),now=Date.now();
        return history.some(function(row) {
            var result=row&&row.details&&row.details.result,events=row&&row.details&&row.details.inputEvents;
            if(row.mission!=='questStep'||(row.status!=='completed'&&row.status!=='stopped')||!result||
                result.step!=='wolfWitnessAction'||result.action!=='strike'||result.actionAttempts!==1||
                !Array.isArray(events)||!wolfReceiptMatches(row)||!Number.isFinite(row.timestamp)||
                row.timestamp>observation.timestamp||observation.timestamp-row.timestamp>15000) return false;
            var actions=events.filter(function(e){return e&&e.type==='wolfWitnessAction'&&e.action==='strike';});
            var keys=events.filter(function(e){return e&&e.type==='key'&&e.key==='VK_LBUTTON';});
            if(actions.length!==1||keys.length!==1) return false;
            var action=actions[0],key=keys[0];
            return Number.isInteger(action.frameId)&&action.frameId>=0&&Number.isFinite(action.startedAt)&&
                Number.isFinite(action.finishedAt)&&action.finishedAt>=action.startedAt&&action.rootDirected===true&&
                Number.isInteger(key.frameId)&&key.frameId===action.frameId&&key.durationMs===60&&
                Number.isFinite(key.startedAt)&&Number.isFinite(key.finishedAt)&&key.finishedAt>=key.startedAt&&
                key.startedAt>=action.startedAt&&key.finishedAt<=action.finishedAt&&
                observation.frameId>action.frameId&&observation.timestamp>action.finishedAt&&
                row.timestamp>=action.finishedAt&&latestInputAt>=key.startedAt&&latestInputAt<=key.finishedAt&&now>=row.timestamp;
        });
    }
    function clearWolfClosingDialogueFault(history, observation) {
        var ambiguityFaults=['Wolf domain safety stopped: the previously verified active trial changed to an ambiguous scene; no input was sent',
            'Wolf domain safety needs human attention: the previously verified active trial changed to an ambiguous scene; no input was sent'];
        if(ambiguityFaults.indexOf(safetyFault)>=0&&
            wolfClosingStrikeProven(history,observation)) {
            safetyFault=null;safetyFaultAt=0;failure=null;heartbeat(true);
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
        clearWolfClosingDialogueFault(history,current);
        if(!safetyFault&&exactWolfClosingDialogue(current)) return;
        if (wolfExposureArmed&&!knownSafeWolfBoundary(current))
            setWolfSafetyFault('the previously verified active trial changed to an ambiguous scene; no input was sent');
    }
    try {
        dispatcher.clearAllTriggers();
        if (Number(file.captureStorageVersion) !== 1) throw new Error('Act One Pilot requires the bounded capture-storage runtime before starting.');
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
            } catch (e) {
                if(e&&(e.code==='PAUSE_PROTECTION_EXHAUSTED'||e.code==='CAPTURE_STORAGE_BLOCKED')) {
                    failure=String(e.message);throw e;
                }
                log.info('Act One Pilot request failed: ' + String(e && e.message || e));
            }
            finally { if(!failure)try { await protectWolfIdleBoundary(request); } catch (e) { setWolfSafetyFault('automatic pause handling failed: '+String(e&&e.message||e)); } }
        }
    } catch(e) {
        failure=String(e&&e.message||e);throw e;
    } finally {
        try { if (adapter) adapter.release(); }
        finally {try {heartbeat(true,failure?'faulted':'stopped');}catch(e){log.info('Controller heartbeat unavailable: '+String(e&&e.message||e));}
            try { if (metrics) setGameMetrics(metrics[0], metrics[1], metrics[2]); } finally { dispatcher.clearAllTriggers(); } }
    }
})();
