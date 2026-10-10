// Pure command policy and injected BetterGI adapter. Never evaluate command contents.
var OpeningQuestPilot = (function () {
    var keys = ['VK_W', 'VK_A', 'VK_S', 'VK_D', 'VK_F', 'VK_SPACE', 'VK_ESCAPE', 'VK_J', 'VK_M'];
    function integer(n, lo, hi) { return typeof n === 'number' && Number.isInteger(n) && n >= lo && n <= hi; }
    function validate(c, session, frame, seen, now, enabled) {
        if (!c || typeof c !== 'object' || Array.isArray(c)) return 'Command must be an object';
        if (typeof c.id !== 'string' || !/^[A-Za-z0-9_-]{1,80}$/.test(c.id)) return 'Invalid id';
        if (seen[c.id]) return 'Duplicate id';
        if (c.session !== session) return 'Wrong session';
        if (c.expectedFrameId !== frame) return 'Stale frame';
        if (!integer(c.createdAt, now - 30000, now)) return 'Expired or future command';
        var fields = ['id', 'session', 'expectedFrameId', 'createdAt', 'action'];
        if (c.action === 'keyPress') {
            fields.push('key');
            if (keys.indexOf(c.key) < 0) return 'Key is not allowed';
        } else if (c.action === 'hold') {
            fields.push('key', 'ms');
            if (['VK_W', 'VK_A', 'VK_S', 'VK_D', 'VK_SPACE'].indexOf(c.key) < 0 || !integer(c.ms, 30, 1000)) return 'Invalid hold';
        } else if (c.action === 'moveMouseBy') {
            fields.push('dx', 'dy');
            if (!integer(c.dx, -300, 300) || !integer(c.dy, -300, 300)) return 'Invalid mouse delta';
        } else if (c.action === 'click') {
            fields.push('x', 'y');
            if (!integer(c.x, 0, 1919) || !integer(c.y, 0, 1079)) return 'Invalid click coordinates';
        } else if (c.action !== 'observe' && c.action !== 'stop') return 'Unknown action';
        if (Object.keys(c).some(function (k) { return fields.indexOf(k) < 0; })) return 'Unknown command field';
        if (!enabled && c.action !== 'observe' && c.action !== 'stop') return 'Input is disabled';
        return null;
    }
    function create(api, options) {
        var session = options.session, enabled = options.enableInput === true;
        var frame = 0, seen = Object.create(null), held = null, stopped = false, busy = false;
        var started = api.now(), lastActivity = started;
        function timedOut() { return api.now() - started >= 1800000 || api.now() - lastActivity >= 120000; }
        function receipt(c, status, reason) {
            var value = { session: session, id: c && c.id || null, action: c && c.action || null,
                status: status, reason: reason || null, frameId: frame, timestamp: api.now() };
            api.write('journal.log', JSON.stringify(value) + '\n', true);
            api.write('receipt.json', JSON.stringify(value, null, 2));
        }
        async function observe() {
            var next = frame + 1, path = 'observations/' + session + '/frame-' + String(next).padStart(4, '0') + '.png';
            var captured = await api.capture(path);
            var observation = { session: session, frameId: next, timestamp: captured.timestamp,
                width: captured.width, height: captured.height, screenshotPath: path,
                enableInput: enabled, ocr: captured.ocr };
            api.write('observation.json', JSON.stringify(observation, null, 2));
            frame = next;
            return observation;
        }
        function release() {
            if (held) { api.keyUp(held); held = null; }
        }
        async function process(c) {
            if (busy) return 'busy';
            if (stopped || timedOut()) { stopped = true; return 'stopped'; }
            var reason = validate(c, session, frame, seen, api.now(), enabled);
            if (reason) { receipt(c, 'rejected', reason); return 'rejected'; }
            busy = true;
            seen[c.id] = true; // Consumed before any write/input: errors cannot replay it.
            try {
                receipt(c, 'started');
                if (c.action !== 'observe' && c.action !== 'stop') await api.focusGame();
                await api.sleep(1); // BetterGI cancellation checkpoint before every input.
                reason = validate(c, session, frame, Object.create(null), api.now(), enabled);
                if (timedOut() || reason) throw new Error(reason || 'Session time limit reached');
                if (c.action === 'stop') stopped = true;
                else if (c.action === 'keyPress') api.keyPress(c.key);
                else if (c.action === 'hold') {
                    held = c.key;
                    try {
                        api.keyDown(c.key);
                        for (var remaining = c.ms; remaining > 0; remaining -= 50) {
                            await api.sleep(Math.min(50, remaining));
                            api.requireInputReady();
                        }
                    } finally { release(); }
                } else if (c.action === 'moveMouseBy') api.moveMouseBy(c.dx, c.dy);
                else if (c.action === 'click') api.click(c.x, c.y);
                await api.sleep(250); // Input and capture pipelines need time to settle.
                await observe();
                receipt(c, 'completed');
                lastActivity = api.now();
                return stopped ? 'stopped' : 'completed';
            } catch (error) {
                stopped = true;
                try { receipt(c, 'failed', String(error)); } catch (_) { /* Preserve original error. */ }
                throw error;
            } finally { busy = false; release(); }
        }
        return { observe: observe, process: process, release: release,
            expired: function () { return stopped || timedOut(); } };
    }
    return { validate: validate, create: create };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = OpeningQuestPilot;
