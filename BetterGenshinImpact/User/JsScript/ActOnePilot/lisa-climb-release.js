'use strict';

var ActOneLisaClimbRelease = (function () {
    var OBJECTIVE = 'meetlisaatthetemple';
    var MAX_FRAME_AGE_MS = 1000;
    var SENSITIVE = /\b(?:password|passcode|captcha|verification|verify|login|log in|sign in|account|authentication|auth|confirm|confirmation|purchase|payment|wish|redeem|security code|two.factor|2fa|revive|revival|disconnected|disconnect|connection timed out|connection timeout)\b/i;

    function finite(v) { return typeof v === 'number' && Number.isFinite(v); }
    function normalized(v) {
        var s = String(v == null ? '' : v);
        if (typeof s.normalize === 'function') s = s.normalize('NFD');
        return s.replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z]/g, '');
    }
    function exactKaeya(v) {
        var s = String(v == null ? '' : v);
        if (typeof s.normalize === 'function') s = s.normalize('NFD');
        return s.replace(/[\u0300-\u036f]/g, '').trim() === 'Kaeya';
    }
    function inside(r, x1, x2, y1, y2) {
        return finite(r.x) && finite(r.y) && finite(r.width) && finite(r.height) &&
            r.width > 0 && r.height > 0 && r.x >= x1 && r.x <= x2 && r.y >= y1 && r.y <= y2;
    }
    function hasFlag(o, names) {
        return names.some(function (name) { return o && o[name] === true; });
    }

    function ready(o, now, session, state) {
        try {
            if (!o || !finite(now) || !state || state.armed !== true || state.releaseAttempted !== false ||
                !Number.isInteger(state.lastInputFrame) || o.session !== session || !session ||
                !Number.isInteger(o.frameId) || o.frameId <= state.lastInputFrame || !finite(o.timestamp) ||
                o.timestamp > now || now - o.timestamp > MAX_FRAME_AGE_MS || !o.hud || !Array.isArray(o.ocr)) return false;

            var h = o.hud, hp = h.health;
            if (h.world !== true || h.climbing !== true || h.groundControls !== false ||
                h.auto !== false || h.choice !== false || h.dialogueReady !== false || h.journal !== false ||
                h.bigMap !== false || h.objectiveChanged !== false ||
                h.deathUI === true || h.dead === true ||
                hasFlag(h, ['loading', 'unknown', 'unknownHud', 'tutorial', 'tutorialStep', 'auth', 'authentication', 'confirmation']) ||
                (h.tutorialStep !== false && h.tutorialStep !== undefined && h.tutorialStep !== null && h.tutorialStep !== '') ||
                (h.loading !== false && h.loading !== undefined) ||
                !hp || !finite(hp.current) || !finite(hp.max) || hp.current <= 0 || hp.max <= 0 || hp.current > hp.max ||
                hp.current / hp.max < 0.6 || !Array.isArray(h.enemyBars) || (h.enemyBars.length !== 0 && state.allowEnemyEscape !== true) ||
                !Array.isArray(h.objectives) || h.objectives.filter(function (x) { return normalized(x) === OBJECTIVE; }).length !== 1) return false;

            if (o.ocr.some(function (r) { return !r || typeof r.text !== 'string' ||
                !finite(r.x) || !finite(r.y) || !finite(r.width) || !finite(r.height) ||
                r.width <= 0 || r.height <= 0 || SENSITIVE.test(r.text); })) return false;

            var kaeya = o.ocr.filter(function (r) { return exactKaeya(r.text) && inside(r, 1600, 1800, 460, 540); });
            var slot = o.ocr.filter(function (r) { return r.text.trim() === '3' && inside(r, 1850, 1895, 460, 540); });
            var trial = o.ocr.filter(function (r) { return normalized(r.text) === 'trial'; });
            var x = o.ocr.filter(function (r) { return r.text.trim() === 'X' && inside(r, 1580, 1635, 1010, 1060); });
            var space = o.ocr.filter(function (r) { return normalized(r.text) === 'space' && inside(r, 1660, 1780, 1010, 1060); });
            var ownedTraveler = kaeya.length === 0 && hp.max === 1288 &&
                o.ocr.filter(function (r) { return r.text.trim() === 'Lumina' && inside(r, 1600, 1800, 280, 350); }).length === 1 &&
                o.ocr.filter(function (r) { return r.text.trim() === 'Amber' && inside(r, 1600, 1800, 350, 460); }).length === 1 &&
                o.ocr.filter(function (r) { return r.text.trim() === '2' && inside(r, 1850, 1895, 350, 460); }).length === 1;
            return (kaeya.length === 1 || ownedTraveler) && slot.length === 1 && trial.length === 0 && x.length === 1 && space.length === 1;
        } catch (_) { return false; }
    }

    return { ready: ready };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = ActOneLisaClimbRelease;
