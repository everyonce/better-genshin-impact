'use strict';

var ActOnePausedNavigationAnchor = (function () {
    var OBJECTIVE = 'meetlisaatthetemple';
    var MAX_MARKER_AGE_MS = 120000;

    function finite(v) { return typeof v === 'number' && Number.isFinite(v); }
    function compact(v) {
        var s = String(v || '');
        if (typeof s.normalize === 'function') s = s.normalize('NFD');
        return s.replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');
    }
    function exactKaeya(v) {
        var s = String(v || '');
        if (typeof s.normalize === 'function') s = s.normalize('NFD');
        return s.replace(/[\u0300-\u036f]/g, '').trim() === 'Kaeya';
    }
    function sameHealth(a, b) {
        return !!(a && b && finite(a.current) && finite(a.max) && a.current === b.current && a.max === b.max);
    }
    function localFoodPause(o, now, session) {
        if (!o || o.session !== session || !Number.isInteger(o.frameId) || !finite(o.timestamp) ||
            now < o.timestamp || !o.hud || !Array.isArray(o.ocr)) return null;
        // Prefer the canonical adapter validator when this file is evaluated in bgi.js.
        if (typeof actOneLocalPauseProof === 'function') {
            var canonical = actOneLocalPauseProof(o, o.timestamp, session);
            return canonical && canonical.kind === 'inventory' && Array.isArray(canonical.evidence) &&
                canonical.evidence.some(function (e) { return e && String(e.text || '').trim() === 'Food'; }) ? canonical : null;
        }
        var headers = o.ocr.filter(function (r) {
            return String(r.text || '').trim() === 'Food' &&
                finite(r.x) && finite(r.y) && r.x >= 100 && r.x <= 250 && r.y >= 15 && r.y <= 70;
        });
        var capacity = o.ocr.filter(function (r) {
            return /^Inventory capacity\s+\d+\/\d+$/i.test(String(r.text || '').trim()) && finite(r.x) && finite(r.y) &&
                r.x >= 1450 && r.x <= 1810 && r.y >= 15 && r.y <= 75;
        });
        return headers.length === 1 && capacity.length === 1 && o.hud.auto !== true && o.hud.dialogueReady !== true ?
            { kind: 'inventory', evidence: [headers[0], capacity[0]] } : null;
    }
    function validHistoricField(field, session, result) {
        if (!field || field.session !== session || !Number.isInteger(field.frameId) || !finite(field.timestamp) ||
            !field.map || field.map.map !== 'Teyvat' || !finite(field.map.x) || !finite(field.map.y) || !finite(field.map.cameraAngle) ||
            Math.hypot(field.map.x + 1265.917, field.map.y - 1928.381) > 500) return false;
        var h = field.hud || {}, hp = h.health;
        if (h.world !== true || h.groundControls !== true || h.climbing !== false || h.auto !== false ||
            h.journal !== false || h.bigMap !== false || h.dialogueReady !== false || h.choice !== false ||
            h.tutorialStep || h.objectiveChanged || h.unknownHud || !Array.isArray(h.enemyBars) || h.enemyBars.length !== 0 ||
            !hp || !sameHealth(hp, result.fieldHealth) ||
            hp.max <= 0 || hp.current <= 0 || hp.current > hp.max || hp.current / hp.max < 0.6 || !Array.isArray(h.objectives) ||
            h.objectives.filter(function (s) { return compact(s) === OBJECTIVE; }).length !== 1 || !Array.isArray(field.ocr)) return false;
        if (field.ocr.some(function (r) { return String(r.text || '').trim() === 'Trial'; })) return false;
        var kaeya = field.ocr.filter(function (r) {
            return exactKaeya(r.text) && finite(r.x) && finite(r.y) && r.x >= 1600 && r.x <= 1800 && r.y >= 460 && r.y <= 540;
        });
        var slot = field.ocr.filter(function (r) {
            return String(r.text || '').trim() === '3' && finite(r.x) && finite(r.y) && r.x >= 1850 && r.x <= 1890 && r.y >= 460 && r.y <= 540;
        });
        return kaeya.length === 1 && slot.length === 1;
    }

    function seed(request, marker, receipt, field, paused, now) {
        try {
            if (!request || request.mission !== 'questStep' || request.step !== 'lionFieldProbe' ||
                typeof request.session !== 'string' || !request.session || !Number.isInteger(request.expectedFrameId) ||
                !finite(now)) return null;
            var session = request.session;
            if (!marker || marker.kind !== 'pausedLisaPositionProbe' || marker.session !== session ||
                marker.frameId !== request.expectedFrameId || marker.witnessVerified !== true ||
                typeof marker.receiptId !== 'string' || !marker.receiptId || !finite(marker.createdAt) ||
                marker.createdAt > now || now - marker.createdAt > MAX_MARKER_AGE_MS || marker.usedAt) return null;
            if (!receipt || receipt.id !== marker.receiptId || receipt.mission !== 'navigation' ||
                receipt.status !== 'completed' || receipt.session !== session || !finite(receipt.timestamp) ||
                !receipt.details || !receipt.details.result) return null;
            var result = receipt.details.result;
            if (result.step !== 'lisaNavigation' || result.status !== 'completed' || result.pauseVerified !== true ||
                result.questComplete !== false || !Number.isInteger(result.fieldFrameId) ||
                !result.fieldPosition || result.fieldPosition.map !== 'Teyvat' ||
                !finite(result.fieldPosition.x) || !finite(result.fieldPosition.y) || !result.fieldHealth ||
                !Number.isInteger(field && field.frameId) || result.fieldFrameId !== field.frameId ||
                field.map.map !== result.fieldPosition.map || field.map.x !== result.fieldPosition.x ||
                field.map.y !== result.fieldPosition.y || !sameHealth(field.hud && field.hud.health, result.fieldHealth) ||
                !validHistoricField(field, session, result)) return null;

            var proof = result.pauseProof;
            if (!proof || proof.verified !== true || proof.session !== session || proof.kind !== 'inventory' ||
                !Number.isInteger(proof.sourceFrameId) || proof.sourceFrameId <= field.frameId ||
                !Number.isInteger(proof.pauseFrameId) || proof.pauseFrameId <= proof.sourceFrameId || !finite(proof.timestamp) ||
                !paused || paused.frameId !== proof.pauseFrameId || paused.session !== session ||
                paused.timestamp !== proof.timestamp || proof.timestamp > marker.createdAt) return null;
            var visible = localFoodPause(paused, now, session);
            if (!visible || visible.kind !== 'inventory' || field.frameId >= proof.pauseFrameId ||
                proof.pauseFrameId >= request.expectedFrameId || field.timestamp > receipt.timestamp ||
                receipt.timestamp > marker.createdAt || paused.timestamp < field.timestamp || proof.timestamp > receipt.timestamp ||
                !Array.isArray(proof.evidence) || proof.evidence.length !== 2 ||
                proof.evidence.some(function (e) { return !e || typeof e.text !== 'string'; }) ||
                proof.evidence.filter(function (e) { return /^Inventory capacity[ ]+[0-9]+\/[0-9]+$/i.test(e.text.trim()); }).length !== 1 ||
                proof.evidence.filter(function (e) { return e.text.trim() === 'Food'; }).length !== 1 ||
                proof.evidence.some(function (e) {
                    return !['x', 'y', 'width', 'height'].every(function (k) { return finite(e[k]); }) ||
                        !paused.ocr.some(function (r) {
                            return r.text === e.text && r.x === e.x && r.y === e.y && r.width === e.width && r.height === e.height;
                        });
                })) return null;
            return { x: field.map.x, y: field.map.y, maxDistance: 25, witnessFrameId: field.frameId };
        } catch (_) { return null; }
    }

    return { seed: seed };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = ActOnePausedNavigationAnchor;
