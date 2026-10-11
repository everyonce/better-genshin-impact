function actOneObjectiveRows(rows, expected) {
    // Close crystal approach also requires the cropped height/distance reading.
    if (!expected || expected === 'Investigate what Paimon has found') return null;
    var candidates = rows.filter(function (r) { return r.x >= 65 && r.x < 695 && r.y >= 230 && r.y < 315; });
    function normalized(s) { return String(s).toLowerCase().replace(/\s+/g, ''); }
    return candidates.some(function (r) { return normalized(r.text) === normalized(expected); }) ? candidates : null;
}
if (typeof module !== 'undefined' && module.exports) module.exports = { objectiveRows: actOneObjectiveRows };

function createActOneAdapter(sessionId) {
    var expectedSession = Number(sessionId), held = null, request = null, events = [], lastObservation = null;
    function dispose(v) { if (v && typeof v.dispose === 'function') v.dispose(); }
    function sessionReady() {
        if (genshin.isRemoteDesktopSession !== true || Number(genshin.windowsSessionId) !== expectedSession || expectedSession !== 5) throw new Error('RDP session 5 required');
    }
    function ready() { sessionReady(); if (genshin.isGameForeground !== true) throw new Error('Game lost foreground focus'); }
    function release() { if (held) { var k = held; held = null; keyUp(k); } }
    function checkStop() {
        ready();
        if (request && file.isExists('stop.json')) {
            var stop = JSON.parse(file.readTextSync('stop.json'));
            if (stop.session === request.session && stop.createdAt >= request.createdAt) { release(); throw new Error('Stop requested'); }
        }
    }
    async function boundedKey(key, ms) {
        checkStop(); held = key;
        var event = { type: 'key', key: key, durationMs: ms, startedAt: Date.now() }; events.push(event);
        try {
            keyDown(key);
            var deadline = Date.now() + ms;
            while (Date.now() < deadline) { await sleep(Math.min(50, deadline - Date.now())); checkStop(); }
        } finally { release(); event.finishedAt = Date.now(); }
    }
    function readRows(img, x, y, w, h) {
        var found = img.findMulti(RecognitionObject.Ocr(x, y, w, h)), rows = [];
        try {
            for (var i = 0; i < found.count; i++) {
                var r = found[i]; rows.push({ text: String(r.text), x: Number(r.x), y: Number(r.y), width: Number(r.width), height: Number(r.height) });
            }
        } finally { for (var j = 0; j < found.count; j++) dispose(found[j]); dispose(found); }
        return rows;
    }
    function scaledRows(img, x, y, w, h) {
        var crop = img.deriveCrop(x, y, w, h), scaled = null;
        try {
            var mat = crop.srcMat.resize(new OpenCvSharp.OpenCvSharp.Size(w * 3, h * 3));
            scaled = new ImageRegion(mat, 0, 0);
            return readRows(scaled, 0, 0, w * 3, h * 3);
        } finally { dispose(scaled); dispose(crop); }
    }
    function readHealth(img) {
        var result = scaledRows(img, 900, 990, 125, 40);
        if (result.some(function (r) { return /\d+\s*\/\s*\d+/.test(r.text); })) return result;
        // Read both numeric halves independently when OCR mistakes the slash for 1.
        var left = scaledRows(img, 893, 998, 65, 25).filter(function (r) { return /^\d{1,5}$/.test(r.text.trim()); });
        var right = scaledRows(img, 967, 998, 65, 25).filter(function (r) { return /^\d{1,5}$/.test(r.text.trim()); });
        if (left.length === 1 && right.length === 1) return [{ text: left[0].text.trim() + '/' + right[0].text.trim() }];
        return result;
    }
    function readMarker(img) {
        var templates = ['assets/quest-marker.png', 'assets/quest-marker-near.png'], matches = [];
        for (var t = 0; t < templates.length; t++) {
            var mat = file.readImageMatSync(templates[t]), ro = null, found = null;
            try {
                ro = RecognitionObject.TemplateMatch(mat, 320, 150, 1400, 630); ro.threshold = 0.82; ro.use3Channels = true;
                found = img.findMulti(ro);
                for (var j = 0; j < found.count; j++) {
                    var point = { x: Number(found[j].x) + Number(found[j].width) / 2, y: Number(found[j].y) + Number(found[j].height) / 2 };
                    if (!matches.some(function (m) { return Math.hypot(m.x-point.x,m.y-point.y) < 30; })) matches.push(point);
                }
            } finally {
                if (found) { for (var i = 0; i < found.count; i++) dispose(found[i]); dispose(found); }
                if (ro) dispose(ro.templateImageGreyMat); dispose(mat);
            }
        }
        return matches.length === 1 ? matches[0] : null;
    }
    function readSlime(img) {
        var crop=img.deriveCrop(400,250,1150,600),hsv=null,mask=null;
        try {
            hsv=crop.srcMat.cvtColor(OpenCvSharp.OpenCvSharp.ColorConversionCodes.BGR2HSV,0);
            mask=hsv.inRange(new OpenCvSharp.OpenCvSharp.Scalar(65,35,140),new OpenCvSharp.OpenCvSharp.Scalar(100,160,255));
            var contours=mask.findContoursAsArray(OpenCvSharp.OpenCvSharp.RetrievalModes.External,OpenCvSharp.OpenCvSharp.ContourApproximationModes.ApproxSimple),matches=[];
            for(var i=0;i<contours.length;i++) {
                var box=OpenCvSharp.OpenCvSharp.Cv2.boundingRect(contours[i]),area=Number(OpenCvSharp.OpenCvSharp.Cv2.contourArea(contours[i],false));
                var w=Number(box.width),h=Number(box.height);
                if(w>=40&&w<=160&&h>=35&&h<=140&&area>1500&&area/(w*h)>0.5) matches.push({x:400+Number(box.x)+w/2,y:250+Number(box.y)+h/2,width:w,height:h,area:area});
            }
            return matches.length===1?matches[0]:null;
        } finally {dispose(mask);dispose(hsv);dispose(crop);}
    }
    return {
        now: function () { return Date.now(); }, sleep: function (ms) { return sleep(ms); }, checkStop: checkStop,
        beginMission: function (value) {
            request = value; events = [];
            var revision = {}, names = ['main.js','engine.js','bgi.js','mission.js'];
            for(var i=0;i<names.length;i++) {
                var source=file.readTextSync(names[i]), hash=2166136261;
                for(var c=0;c<source.length;c++) hash=Math.imul(hash^source.charCodeAt(c),16777619)>>>0;
                revision[names[i]]=hash.toString(16);
                var path='revisions/'+revision[names[i]]+'/'+names[i]+'.txt';
                if(!file.isExists(path) && !file.writeTextSync(path,source)) throw new Error('Cannot preserve controller revision');
            }
            events.push({type:'controllerRevision',files:revision,startedAt:Date.now()});
        }, events: function () { return events; },
        focusGame: async function () { sessionReady(); await genshin.focusGame(); ready(); },
        requireInputReady: ready, keyPress: function (key) { return boundedKey(key, 60); }, release: release,
        advanceTutorial: async function () {
            checkStop();
            if (!lastObservation || Date.now()-lastObservation.timestamp > 1000 || ['switchAmber','enterAim','exitAim','aimSlime'].indexOf(lastObservation.hud.tutorialStep) < 0) throw new Error('Fresh Amber switch tutorial required');
            if (lastObservation.hud.tutorialStep === 'aimSlime') {
                var target = lastObservation.hud.slimeTarget;
                if (!target) throw new Error('Unique airborne slime unavailable');
                var ex=target.x-960,ey=target.y-540;
                if (Math.abs(ex)<=18 && Math.abs(ey)<=18) { await boundedKey('VK_LBUTTON',60); return 'shot'; }
                var dx=Math.max(-150,Math.min(150,Math.round(ex*0.5))),dy=Math.max(-150,Math.min(150,Math.round(ey*0.9)));
                events.push({type:'aim',dx:dx,dy:dy,target:target,frameId:lastObservation.frameId,startedAt:Date.now()});
                moveMouseBy(dx,dy); return;
            }
            return boundedKey(lastObservation.hud.tutorialStep === 'switchAmber' ? 'VK_2' : 'VK_R',60);
        },
        continueCharacter: function () {
            checkStop();
            if (!lastObservation || Date.now()-lastObservation.timestamp > 1000 || !lastObservation.hud.characterAcquired) throw new Error('Fresh character acquisition screen required');
            events.push({type:'characterAcquiredContinue',character:lastObservation.hud.characterAcquired,frameId:lastObservation.frameId,startedAt:Date.now()});
            click(1700,900);
        },
        chooseChoice: function (label) {
            checkStop();
            if (!lastObservation || Date.now() - lastObservation.timestamp > 1000 || !lastObservation.hud.choice) throw new Error('Fresh dialogue choice required');
            var matches = lastObservation.ocr.filter(function (r) { return r.text.trim() === label && r.x > 1000 && r.y > 430 && r.y < 830; });
            if (matches.length !== 1) throw new Error('Dialogue option is ambiguous');
            var row = matches[0]; events.push({ type: 'dialogueChoice', label: label, frameId: lastObservation.frameId, startedAt: Date.now() });
            click(Math.round(row.x + row.width / 2), Math.round(row.y + row.height / 2));
        },
        rotate: function (dx) {
            checkStop(); if (!Number.isInteger(dx) || Math.abs(dx) > 250) throw new Error('Invalid rotation');
            events.push({ type: 'rotate', dx: dx, startedAt: Date.now() }); moveMouseBy(dx, 0);
        },
        forward: function (ms) { if (!Number.isInteger(ms) || ms < 1 || ms > 800) throw new Error('Invalid movement duration'); return boundedKey('VK_W', ms); },
        write: function (p, t) { if (!file.writeTextSync(p, t)) throw new Error('Cannot write ' + p); },
        observe: async function (session, frame) {
            ready();
            var t0 = Date.now(), img = captureGameRegion(), captureMs = Date.now() - t0;
            try {
                if (Number(img.width) !== 1920 || Number(img.height) !== 1080) throw new Error('1920x1080 capture required');
                var o0 = Date.now(), rows = readRows(img, 0, 0, 1920, 1080);
                var fullOcrMs = Date.now() - o0, health0 = Date.now(), healthRows = readHealth(img);
                var healthOcrMs = Date.now() - health0, objective0 = Date.now();
                var reusedObjectiveRows = actOneObjectiveRows(rows, request && request.objective);
                var objectiveRows = reusedObjectiveRows || readRows(img, 65, 230, 630, 85);
                var objectiveOcrMs = Date.now() - objective0;
                var ocrMs = Date.now() - o0;
                var p0 = Date.now(), png = 'observations/' + session + '/frame-' + String(frame).padStart(4, '0') + '.png';
                if (!file.writeImageSync(png, img.srcMat)) throw new Error('PNG write failed');
                var pngMs = Date.now() - p0, map0 = Date.now(), pos = null;
                try {
                    var mp = genshin.getPositionFromMap('Teyvat', 0);
                    if (mp && Number.isFinite(Number(mp.x)) && Number.isFinite(Number(mp.y))) pos = { x: Number(mp.x), y: Number(mp.y), map: 'Teyvat', cameraAngle: Number(genshin.getCameraOrientation()) };
                } catch (_) { }
                var mapMs = Date.now() - map0, text = rows.map(function (r) { return r.text; }).join(' ');
                var hpMatch = healthRows.map(function (r) { return r.text; }).join(' ').match(/\b(\d{1,5})\s*\/\s*(\d{1,5})\b/);
                var hp = hpMatch ? { current: Number(hpMatch[1]), max: Number(hpMatch[2]) } : null;
                if (hp && (hp.current > hp.max || hp.max <= 0)) hp = null;
                var auto = rows.some(function (r) { return /^Auto$/i.test(r.text.trim()) && r.x < 350 && r.y < 150; });
                var subtitle = rows.some(function (r) { return r.x > 200 && r.x < 1550 && r.y > 790 && r.y < 990 && r.text.trim().length > 8; });
                var choice = rows.some(function (r) { return r.x > 1000 && r.y > 430 && r.y < 790 && r.text.trim().length > 6; });
                var journal = rows.some(function (r) { return /^In Progress$/i.test(r.text.trim()) && r.y < 100; });
                var bigMap = /Exploration Progress|Starfell Valley/.test(text) && !pos;
                var acquired = /Obtained New Character/.test(text) && /Click anywhere in the blank area to continue/.test(text) ? rows.filter(function(r) { return ['Amber','Kaeya','Lisa'].indexOf(r.text.trim()) >= 0 && r.x < 500 && r.y > 500 && r.y < 700; }) : [];
                var tutorialStep = /Press 2 to switch to Amber/i.test(text) && /Use Amber to defeat the airborne/i.test(text) ? 'switchAmber' : null;
                if (/Press R to enter\/exit aiming mode/i.test(text) && /Use Amber to defeat the airborne/i.test(text)) tutorialStep = 'enterAim';
                if (/Move cursor to aim. Try attacking the floating Anemo Slime/i.test(text) && /Use Amber to defeat the airborne/i.test(text)) tutorialStep = 'aimSlime';
                if (/Press R again to exit aiming mode/i.test(text) && /Go to the location designated by Amber/i.test(text)) tutorialStep = 'exitAim';
                var hud = { slimeTarget: tutorialStep === 'aimSlime' ? readSlime(img) : null, tutorialStep: tutorialStep, characterAcquired: acquired.length === 1 ? acquired[0].text.trim() : null, dialogueReady: auto && subtitle && !choice, choice: auto && choice, journal: journal, bigMap: bigMap,
                    objectiveChanged: /objective updated|quest completed/i.test(text), health: hp, healthOcr: healthRows.map(function (r) { return r.text; }),
                    healthPct: hp && hp.max > 0 ? hp.current / hp.max : null,
                    lowHealth: !hp || hp.max <= 0 || hp.current > hp.max || hp.current / hp.max < 0.6,
                    world: !!pos && !!hp && !auto && !journal && !bigMap,
                    interact: rows.some(function (r) { return /^F$/.test(r.text.trim()) && r.x > 850 && r.y > 300 && r.y < 800; }),
                    objectives: objectiveRows.map(function (r) { return r.text; }) };
                if (pos && request && request.objective === 'Investigate what Paimon has found') hud.worldMarker = readMarker(img);
                ready();
                lastObservation = { frameId: frame, timestamp: Date.now(), capturedAt: t0, screenshotPath: png, ocr: rows, map: pos, hud: hud,
                    timings: { captureMs: captureMs, ocrMs: ocrMs, fullOcrMs: fullOcrMs, healthOcrMs: healthOcrMs, objectiveOcrMs: objectiveOcrMs, objectiveSource: reusedObjectiveRows ? 'fullFrame' : 'crop', pngWriteMs: pngMs, mapMs: mapMs, totalMs: Date.now() - t0 } };
                return lastObservation;
            } finally { dispose(img); }
        }
    };
}

