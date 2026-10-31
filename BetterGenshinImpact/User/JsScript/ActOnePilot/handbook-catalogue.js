// Pure admission for three explicitly requested, bounded enemy-catalogue operations.
var HandbookCatalogue = (function () {
    'use strict';
    var commands = ['handbookCatalogueScroll', 'handbookCatalogueSelect', 'handbookCatalogueTrack'];

    // Reject extra fields even when an adapter is called without the request engine.
    function requestError(r) {
        if (!r || typeof r !== 'object' || Array.isArray(r) || r.mission !== 'questStep' || commands.indexOf(r.step) < 0)
            return 'Unknown handbook catalogue command';
        var fields = ['id', 'session', 'expectedFrameId', 'createdAt', 'mission', 'step'];
        if (typeof r.id !== 'string' || !/^[A-Za-z0-9_-]{1,80}$/.test(r.id) ||
            typeof r.session !== 'string' || !r.session || r.session.length > 100 ||
            !Number.isInteger(r.expectedFrameId) || r.expectedFrameId < 0 ||
            !Number.isInteger(r.createdAt) || r.createdAt < 0) return 'Invalid catalogue request identity';
        if (r.step === 'handbookCatalogueSelect') {
            fields.push('x', 'y');
            if (!Number.isInteger(r.x) || !Number.isInteger(r.y) || r.x <= 420 || r.x >= 940 || r.y <= 265 || r.y >= 870)
                return 'Catalogue coordinates must be strictly inside the left icon grid';
        }
        if (r.step === 'handbookCatalogueTrack') {
            fields.push('enemyName');
            if (typeof r.enemyName !== 'string' || !/^[A-Za-z][A-Za-z0-9 '():-]{1,95}$/.test(r.enemyName) ||
                r.enemyName !== r.enemyName.trim() || / {2}/.test(r.enemyName)) return 'Explicit English enemy name required';
        }
        return Object.keys(r).some(function (key) { return fields.indexOf(key) < 0; }) ? 'Unknown catalogue request field' : null;
    }

    // OCR matching is exact after ordinary whitespace normalization; it never uses fuzzy names.
    function text(row) { return String(row && row.text || '').trim().replace(/\s+/g, ' '); }

    // Normalize only location comma spacing, preserving every name letter and OCR glyph.
    function locationText(row) { return text(row).replace(/\s*,\s*/g, ', '); }

    // These handbook coordinates refer to the existing 1920x1080 observation layout.
    function box(row, x0, x1, y0, y1, maxWidth, maxHeight) {
        return !!(row && Number.isFinite(row.x) && Number.isFinite(row.y) && Number.isFinite(row.width) &&
            Number.isFinite(row.height) && row.x >= x0 && row.x <= x1 && row.y >= y0 && row.y <= y1 &&
            row.width >= 10 && row.width <= maxWidth && row.height >= 10 && row.height <= maxHeight &&
            row.x + row.width <= 1920 && row.y + row.height <= 1080);
    }

    // A second occurrence is ambiguous, including an open category popup or duplicated OCR.
    function unique(rows, label, x0, x1, y0, y1, maxWidth, maxHeight) {
        var found = rows.filter(function (row) { return text(row) === label; });
        return found.length === 1 && box(found[0], x0, x1, y0, y1, maxWidth, maxHeight) ? found[0] : null;
    }

    // Date.now bounds are 1000 ms since OCR completion and 2000 ms since capture began.
    // These legacy UI clocks are separate from native AgentStream QPC/frame-age qualification.
    function screenReady(o, now, r) {
        if (requestError(r) || !o || o.session !== r.session || !Number.isInteger(o.frameId) ||
            o.frameId <= r.expectedFrameId || !Number.isFinite(now) || !Number.isFinite(o.timestamp) ||
            !Number.isFinite(o.capturedAt) || o.capturedAt < r.createdAt || o.timestamp < o.capturedAt ||
            now - o.capturedAt > 2000 ||
            o.timestamp < r.createdAt || now < o.timestamp || now - o.timestamp > 1000 ||
            now < r.createdAt || now - r.createdAt > 30000 || o.map !== null || !o.hud ||
            !Array.isArray(o.ocr) || o.ocr.length > 500) return false;
        if (['world', 'journal', 'bigMap', 'choice', 'dialogueReady', 'auto', 'climbing', 'groundControls']
            .some(function (key) { return o.hud[key] !== false; })) return false;
        var rows = o.ocr;
        if (!unique(rows, 'Experience', 220, 300, 220, 260, 180, 60) ||
            !unique(rows, 'Domains', 220, 300, 320, 370, 180, 60) ||
            !unique(rows, 'Enemies', 220, 300, 410, 470, 180, 60) ||
            !unique(rows, 'Guide', 220, 300, 510, 570, 180, 60) ||
            !unique(rows, 'X', 1630, 1670, 195, 230, 70, 70) ||
            !unique(rows, 'Easy', 390, 440, 180, 220, 100, 60)) return false;
        return !rows.some(function (row) {
            return ['Easy', 'Elite Enemies', 'Boss Enemies'].indexOf(text(row)) >= 0 &&
                box(row, 380, 700, 265, 450, 300, 60);
        });
    }

    // The selected title, selected Mondstadt location and Navigate button form one proof.
    function trackedEnemy(o, name) {
        var rows = o.ocr, locations = rows.filter(function (row) {
            return box(row, 1020, 1120, 300, 380, 600, 60) && row.x + row.width <= 1640 &&
                /^[A-Za-z][A-Za-z '()-]{1,79}, [A-Za-z][A-Za-z -]{1,39}$/.test(locationText(row));
        });
        if (locations.length !== 1 || !/, Mondstadt$/.test(locationText(locations[0]))) return null;
        var location = locations[0], title = rows.filter(function (row) {
            return box(row, 1020, 1120, 240, 330, 600, 60) && row.x + row.width <= 1640 &&
                row.y + row.height <= location.y - 4;
        }).sort(function (left, right) { return left.y - right.y || left.x - right.x; });
        if (title.length < 1 || title.length > 2 || title.map(text).join(' ') !== name) return null;
        if (title.length === 2 && (Math.abs(title[0].x - title[1].x) > 20 ||
            title[1].y < title[0].y + title[0].height || title[1].y - title[0].y > 65)) return null;
        var navigate = unique(rows, 'Navigate', 1370, 1450, 800, 850, 200, 60);
        if (!navigate || navigate.width < 80 || navigate.height < 20) return null;
        return {enemyName: name, location: locationText(location), title: title.map(text),
            x: Math.round(navigate.x + navigate.width / 2), y: Math.round(navigate.y + navigate.height / 2)};
    }

    // Return a finite operation; no operation includes a follow-on click or navigation route.
    function target(o, now, r) {
        if (!screenReady(o, now, r)) return null;
        if (r.step === 'handbookCatalogueScroll')
            return {command: r.step, action: 'scrollCatalogue', x: 680, y: 670, ticks: 8, delta: -1};
        if (r.step === 'handbookCatalogueSelect')
            return {command: r.step, action: 'selectCatalogueIcon', x: r.x, y: r.y};
        var enemy = trackedEnemy(o, r.enemyName);
        return enemy ? Object.assign({command: r.step, action: 'trackCatalogueEnemy'}, enemy) : null;
    }

    return {commands: commands.slice(), requestError: requestError, screenReady: screenReady, target: target};
})();
if (typeof module !== 'undefined' && module.exports) module.exports = HandbookCatalogue;
