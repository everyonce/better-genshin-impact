var ActOnePilot = (function () {
    var keys = ['VK_J', 'VK_ESCAPE', 'VK_F', 'VK_SPACE', 'VK_M'];
    function integer(n, lo, hi) { return typeof n === 'number' && Number.isInteger(n) && n >= lo && n <= hi; }
    function validate(r, session, frame, seen, now) {
        if (!r || typeof r !== 'object' || Array.isArray(r)) return 'Request must be an object';
        if (typeof r.id !== 'string' || !/^[A-Za-z0-9_-]{1,80}$/.test(r.id)) return 'Invalid id';
        if (seen[r.id]) return 'Duplicate id';
        if (r.session !== session) return 'Wrong session';
        if (r.expectedFrameId !== frame) return 'Stale frame';
        if (!integer(r.createdAt, now - 30000, now)) return 'Expired or future request';
        if (typeof r.mission !== 'string' || ['observe', 'stop', 'keyPress', 'navigation', 'dialogue'].indexOf(r.mission) < 0) return 'Unknown mission';
        var allowed = ['id', 'session', 'expectedFrameId', 'createdAt', 'mission'];
        if (r.mission === 'keyPress') { allowed.push('key'); if (keys.indexOf(r.key) < 0) return 'Key is not allowed'; }
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
        var session = options.session, enabled = options.enableInput === true, frame = 0, seen = Object.create(null), stopped = false, started = api.now(), activity = started, busy = false, reports = [];
        function expired() { return api.now() - started >= 3600000 || api.now() - activity >= 600000; }
        function report(req, state, details) {
            var row = { session: session, id: req && req.id || null, mission: req && req.mission || null, status: state, timestamp: api.now(), frameId: frame, details: details || null };
            reports.push(row); api.write('reports/' + session + '.json', JSON.stringify(reports, null, 2)); api.write('receipt.json', JSON.stringify(row, null, 2)); return row;
        }
        async function observe() {
            var data = await api.observe(session, frame + 1); frame++;
            var immutable = JSON.parse(JSON.stringify({ session: session, frameId: frame, timestamp: data.timestamp, screenshotPath: data.screenshotPath, ocr: data.ocr || [], map: data.map || null, hud: data.hud || null, timings: data.timings || {} }));
            api.write('observations/' + session + '/frame-' + String(frame).padStart(4, '0') + '.json', JSON.stringify(immutable, null, 2));
            api.write('observation.json', JSON.stringify(immutable, null, 2));
            return immutable;
        }
        async function process(req, missionFactory) {
            if (busy) return 'busy';
            if (stopped || expired()) { stopped = true; return 'stopped'; }
            var reason = validate(req, session, frame, seen, api.now());
            if (reason) { report(req, 'rejected', { reason: reason }); return 'rejected'; }
            seen[req.id] = true; busy = true; var inputStarted = 0, routeResult = null, missionStarted = api.now();
            try {
                api.beginMission(req);
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
                } else if (req.mission === 'navigation') {
                    if (!enabled) throw new Error('Input is disabled');
                    var fresh = await observe();
                    routeResult = await missionFactory().runNavigation(req, fresh, api, observe);
                    if (routeResult.status !== 'arrived') throw new Error(routeResult.reason || 'Navigation policy stopped');
                } else if (req.mission === 'dialogue') {
                    if (!enabled) throw new Error('Input is disabled');
                    routeResult = await missionFactory().runDialogue(api, observe);
                    if (routeResult.status !== 'completed') throw new Error(routeResult.reason);
                }
                if (req.mission !== 'stop') await observe();
                activity = api.now();
                var details = { elapsedMs: api.now() - missionStarted, result: routeResult, inputEvents: api.events() };
                report(req, req.mission === 'stop' ? 'stopped' : 'completed', details);
                return req.mission === 'stop' ? 'stopped' : 'completed';
            } catch (e) { activity = api.now(); report(req, 'failed', { reason: String(e && e.message || e), elapsedMs: api.now() - missionStarted, result: routeResult, inputEvents: api.events() }); throw e; }
            finally { busy = false; api.release(); }
        }
        return { observe: observe, process: process, expired: expired, stopped: function () { return stopped || expired(); }, report: report, getFrame: function () { return frame; } };
    }
    return { create: create, validate: validate };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = ActOnePilot;
