// BirdsEyeViewPilot package entry point. Routes are data, never executable code.
(async function () {
    var previousMetrics = null, status = null, sessionId = null;
    var runner = null, stages = null, api = null, heldKeys = [];
    var frameId = 0, lastObservation = null, journalOpenAttempted = false;
    var enableNavigation = settings && settings.enableNavigation === true;
    var sessionStarted = Date.now();

    function release(obj) { if (obj && typeof obj.dispose === 'function') obj.dispose(); }
    function writeStatus() {
        if (!file.writeTextSync('status.json', JSON.stringify(status, null, 2))) {
            throw new Error('Could not write status.json.');
        }
    }
    function checkRdp() {
        if (typeof genshin.isRemoteDesktopSession !== 'boolean' ||
            !Number.isInteger(Number(genshin.windowsSessionId))) {
            throw new Error('This BetterGI build does not expose the RDP session identity required by this pilot.');
        }
        if (genshin.isRemoteDesktopSession !== true) {
            throw new Error('Navigation is enabled only inside a Windows Remote Desktop session.');
        }
        if (Number(genshin.windowsSessionId) !== status.windowsSessionId) {
            throw new Error('Windows session changed during the pilot; stopping before input.');
        }
    }
    function requireForeground() {
        checkRdp();
        if (genshin.isGameForeground !== true) throw new Error('Game lost foreground focus; stopping before input.');
    }
    async function focusForInput() {
        checkRdp();
        if (typeof genshin.focusGame !== 'function') throw new Error('This BetterGI build does not expose focusGame().');
        await genshin.focusGame();
        requireForeground();
    }
    function press(key) {
        requireForeground();
        keyPress(key);
    }
    function keyDownTracked(key) {
        requireForeground();
        keyDown(key);
        if (heldKeys.indexOf(key) < 0) heldKeys.push(key);
    }
    function releaseKeys() {
        var keys = heldKeys.slice();
        heldKeys = [];
        keys.forEach(function (key) { try { keyUp(key); } catch (_) { /* best effort */ } });
    }
    function normalizeRows(found) {
        var rows = [];
        try {
            for (var i = 0; i < found.count; i++) {
                var row = found[i];
                rows.push({ text: String(row.text), x: Number(row.x), y: Number(row.y),
                    width: Number(row.width), height: Number(row.height) });
            }
        } finally {
            for (var j = 0; j < found.count; j++) release(found[j]);
            release(found);
        }
        return rows;
    }
    function readOcr(image) {
        return normalizeRows(image.findMulti(RecognitionObject.Ocr(0, 0, 1920, 1080)));
    }
    function saveFrame(rows, width, height, image) {
        frameId++;
        var imagePath = 'observations/' + sessionId + '/frame-' + String(frameId).padStart(5, '0') + '.png';
        if (!file.writeImageSync(imagePath, image.srcMat)) throw new Error('Could not save immutable screenshot ' + imagePath);
        var classification = stages.classify(rows);
        var position = null;
        var worldHud = false;
        // The map-position API is also our positive world-HUD signal. It throws
        // on early tutorial/locked-map states, which must remain observation-only.
        if (classification.screen === 'unknown' && typeof genshin.getPositionFromMap === 'function') {
            try {
                position = genshin.getPositionFromMap();
                worldHud = !!position;
            } catch (_) { position = null; worldHud = false; }
        }
        var record = {
            frameId: frameId, timestamp: Date.now(), width: Number(width), height: Number(height),
            screenshotPath: imagePath, ocr: rows, screen: classification.screen,
            quest: classification.quest, stage: classification.stage,
            completed: classification.completed, classificationReason: classification.reason,
            worldHud: worldHud,
            mapPosition: position ? { x: Number(position.x !== undefined ? position.x : position.X),
                y: Number(position.y !== undefined ? position.y : position.Y) } : null,
            remoteDesktop: { isRemoteDesktopSession: genshin.isRemoteDesktopSession === true,
                windowsSessionId: Number(genshin.windowsSessionId) }
        };
        if (classification.screen === 'dialogue') {
            record.signature = rows.map(function (row) {
                return String(row.text).normalize('NFKC').trim().toLowerCase();
            }).filter(Boolean).join('|');
        }
        status.observations.push(record);
        status.updatedAt = record.timestamp;
        lastObservation = record;
        writeStatus();
        return record;
    }
    function captureObservation() {
        var image = captureGameRegion();
        try {
            if (Number(image.width) !== 1920 || Number(image.height) !== 1080) {
                throw new Error('captureGameRegion() must provide the normalized 1920x1080 frame.');
            }
            var rows = readOcr(image);
            return saveFrame(rows, image.width, image.height, image);
        } finally { release(image); }
    }
    function parseRoute(value) {
        var route = typeof value === 'string' ? JSON.parse(value) : value;
        if (!route || typeof route !== 'object' || Array.isArray(route) ||
            !route.info || !Array.isArray(route.positions) || route.positions.length === 0) {
            throw new Error('Route data must be a supplied BetterGI route object with info and positions.');
        }
        route.positions.forEach(function (point) {
            if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) {
                throw new Error('Supplied route contains a waypoint without finite x/y coordinates.');
            }
        });
        return JSON.stringify(route);
    }
    function loadSource(path, symbol) {
        // Direct eval returns the final expression from its own lexical scope;
        // this keeps the strict-mode sources' `var` bindings local to eval.
        return eval(file.readTextSync(path) + '\n' + symbol + ';');
    }

    try {
        dispatcher.clearAllTriggers();
        if (typeof genshin.windowsSessionId !== 'number' || !Number.isInteger(genshin.windowsSessionId) ||
            typeof genshin.isRemoteDesktopSession !== 'boolean') {
            throw new Error('Birds Eye View Pilot requires the RDP identity properties isRemoteDesktopSession and windowsSessionId (BetterGI r8).');
        }
        previousMetrics = getGameMetrics();
        setGameMetrics(1920, 1080, 1);
        sessionId = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
        if (!file.createDirectory('observations/' + sessionId)) throw new Error('Could not create this session observation folder.');
        status = { package: 'BirdsEyeViewPilot', session: sessionId, startedAt: sessionStarted,
            enableNavigation: enableNavigation, isRemoteDesktopSession: genshin.isRemoteDesktopSession,
            windowsSessionId: genshin.windowsSessionId, observations: [], state: 'starting' };
        writeStatus();
        runner = loadSource('engine.js', 'BirdsEyeRunner');
        stages = loadSource('stages.js', 'BirdsEyeStages');
        var routes = JSON.parse(file.readTextSync('routes.json') || '{}');
        if (!routes || Array.isArray(routes) || typeof routes !== 'object') throw new Error('routes.json must be an object keyed by exact recognized stage.');

        api = {
            assertRdp: function () { checkRdp(); },
            wait: function (ms) { return sleep(ms); },
            saveStatus: function (state) { status.runner = state; writeStatus(); },
            observe: async function () {
                var observation = captureObservation();
                if (enableNavigation && !journalOpenAttempted && observation.screen === 'unknown' && observation.worldHud) {
                    journalOpenAttempted = true;
                    await focusForInput();
                    press('VK_J');
                    await sleep(900);
                    observation = captureObservation();
                }
                return observation;
            },
            navigate: async function (segment) {
                if (!enableNavigation) throw new Error('Navigation is disabled in settings.');
                if (!lastObservation || lastObservation.screen !== 'journal' ||
                    lastObservation.quest !== "Bird's Eye View" || !lastObservation.stage) {
                    throw new Error('Route start requires a fresh journal observation confirming Bird\'s Eye View and its stage.');
                }
                var routeJson = parseRoute(segment);
                await focusForInput();
                press('VK_ESCAPE');
                await sleep(700);
                var image = captureGameRegion();
                var postClose;
                try {
                    if (Number(image.width) !== 1920 || Number(image.height) !== 1080) throw new Error('Normalized 1920x1080 capture is unavailable.');
                    postClose = saveFrame(readOcr(image), image.width, image.height, image);
                } finally { release(image); }
                if (!postClose.worldHud) throw new Error('Could not positively recognize the world HUD after closing the journal; route was not started.');
                await focusForInput();
                if (!pathingScript || typeof pathingScript.runForQuest !== 'function') {
                    throw new Error('This BetterGI build does not expose pathingScript.runForQuest().');
                }
                await pathingScript.runForQuest(routeJson);
            },
            advanceDialogue: async function () {
                if (!enableNavigation) throw new Error('Dialogue input is disabled in settings.');
                if (!lastObservation || lastObservation.screen !== 'dialogue' ||
                    typeof lastObservation.signature !== 'string' || !lastObservation.signature) {
                    throw new Error('Dialogue input requires a fresh recognized speaker and subtitle.');
                }
                var expectedSignature = lastObservation.signature;
                await focusForInput();
                var fresh = captureObservation();
                if (fresh.screen !== 'dialogue' || fresh.signature !== expectedSignature) {
                    throw new Error('Dialogue changed before the input check; no key was sent.');
                }
                await focusForInput();
                keyDownTracked('VK_SPACE');
                try { await sleep(60); }
                finally { releaseKeys(); }
            },
            release: async function () { releaseKeys(); }
        };

        if (enableNavigation) {
            status.state = 'running';
            writeStatus();
            var result = await runner.run({ api: api, routes: routes });
            status.state = result.state;
            status.reason = result.reason;
            status.result = result;
            status.finishedAt = Date.now();
            writeStatus();
            log.info('Birds Eye View Pilot ended: ' + result.state + ' (' + result.reason + ').');
        } else {
            status.state = 'observing';
            writeStatus();
            log.info('Birds Eye View Pilot is observe-only. Screenshot and OCR records are in status.json and observations/' + sessionId + '/.');
            for (var i = 0; i < 360; i++) {
                captureObservation();
                await sleep(5000);
            }
            status.state = 'observation_limit';
            status.finishedAt = Date.now();
            writeStatus();
        }
    } catch (error) {
        if (status) {
            status.state = 'blocked';
            status.error = String(error && error.message || error);
            status.finishedAt = Date.now();
            try { writeStatus(); } catch (_) { /* Preserve the original error. */ }
        }
        log.info('Birds Eye View Pilot stopped: ' + String(error && error.message || error));
    } finally {
        releaseKeys();
        try { if (previousMetrics) setGameMetrics(previousMetrics[0], previousMetrics[1], previousMetrics[2]); }
        finally { dispatcher.clearAllTriggers(); }
    }
})();
