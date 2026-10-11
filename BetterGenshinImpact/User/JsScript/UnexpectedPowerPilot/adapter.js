// All capture/input remains inside the BetterGI process in the RDP session.
function createUnexpectedPowerAdapter(policy, session, save) {
    var frame = 0, held = null, expectedSession = Number(genshin.windowsSessionId);
    var last = null, events = [];
    function dispose(value) { if (value && typeof value.dispose === 'function') value.dispose(); }
    function assertReady() {
        if (genshin.isRemoteDesktopSession !== true || Number(genshin.windowsSessionId) !== expectedSession)
            throw new Error('rdp_session_changed');
        if (genshin.isGameForeground !== true) throw new Error('game_focus_lost');
    }
    function release() { if (held) { var key = held; held = null; keyUp(key); } }
    async function boundedKey(key, ms) {
        assertReady();
        held = key;
        try {
            keyDown(key);
            for (var elapsed = 0; elapsed < ms; elapsed += 50) {
                await sleep(Math.min(50, ms - elapsed));
                assertReady();
            }
        } finally { release(); }
    }
    function readRows(image, recognition) {
        var found = image.findMulti(recognition), rows = [];
        try {
            for (var i = 0; i < found.count; i++) {
                var r = found[i];
                rows.push({ text: String(r.text), x: Number(r.x), y: Number(r.y),
                    width: Number(r.width), height: Number(r.height) });
            }
        } finally {
            for (var j = 0; j < found.count; j++) dispose(found[j]);
            dispose(found);
        }
        return rows;
    }
    async function observe() {
        assertReady();
        var image = captureGameRegion();
        try {
            if (Number(image.width) !== 1920 || Number(image.height) !== 1080)
                throw new Error('normalized_capture_unavailable');
            var rows = readRows(image, RecognitionObject.Ocr(0, 0, 1920, 1080));
            var healthRows = readRows(image, RecognitionObject.Ocr(800, 985, 320, 50));
            var partyRows = readRows(image, RecognitionObject.Ocr(1620, 375, 155, 70));
            var health = healthRows.some(function (r) { return /^\s*\d+\s*\/\s*\d+\s*$/.test(r.text); });
            var party = rows.concat(partyRows).some(function (r) { return r.text.normalize('NFD').replace(/[\u0300-\u036f]/g, '') === 'Lumina' && r.x > 1500 && r.y > 300 && r.y < 600; });
            var tutorial = policy.classify(rows).kind === 'tutorialAction';
            var menu = rows.some(function (r) { return /^(Auto|In Progress|Settings)$/i.test(r.text.trim()); });
            var path = 'observations/' + session + '/frame-' + String(++frame).padStart(4, '0') + '.png';
            if (!file.writeImageSync(path, image.srcMat)) throw new Error('screenshot_write_failed');
            last = { frameId: frame, timestamp: Date.now(), screenshotPath: path, rows: rows,
                healthRows: healthRows, partyRows: partyRows, mode: health && (party || tutorial) && !menu ? 'verifiedWorld' : null,
                remoteDesktop: true, windowsSessionId: expectedSession };
            save({ observation: last });
            assertReady();
            return last;
        } finally { dispose(image); }
    }
    async function menuKey(key, expectedKind) {
        var fresh = await observe();
        var state = policy.classify(fresh.rows);
        if (expectedKind === 'verifiedWorld' ? fresh.mode !== expectedKind : state.kind !== expectedKind)
            throw new Error('menu_state_changed_before_input');
        events.push({ type: key === 'VK_J' ? 'openJournal' : 'closeJournal', frameId: fresh.frameId, startedAt: Date.now() });
        save({ inputEvents: events });
        await boundedKey(key, 60);
        await sleep(1000);
        assertReady();
    }
    return {
        now: function () { return Date.now(); },
        assertReady: assertReady,
        observe: observe,
        wait: async function (ms) { await sleep(ms); assertReady(); },
        saveStatus: function (record) { save({ runner: record }); },
        closeJournal: function () { return menuKey('VK_ESCAPE', 'targetJournal'); },
        openJournal: function () { return menuKey('VK_J', 'verifiedWorld'); },
        hold: async function (key, ms) {
            var fresh = await observe(), state = policy.classify(fresh.rows);
            var candidate = { type: state.action && state.action.type, key: key, ms: ms };
            if (!policy.validateAction(candidate, state).ok) throw new Error('tutorial_prompt_changed_before_input');
            if (fresh.mode !== 'verifiedWorld') throw new Error('world_hud_unavailable_before_input');
            var event = { type: candidate.type, key: key, ms: ms, frameId: fresh.frameId, startedAt: Date.now() };
            events.push(event); save({ inputEvents: events });
            try {
                await boundedKey('VK_' + key, ms);
                event.completedAt = Date.now();
            } catch (error) { event.error = String(error); throw error; }
            finally { release(); save({ inputEvents: events }); }
            await sleep(800);
            assertReady();
        },
        release: release
    };
}
