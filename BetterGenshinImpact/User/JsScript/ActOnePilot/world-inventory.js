// Read-only gate for the one Escape used to close an open world inventory.
// Anchors match a captured Wolf inventory frame at 1920x1080: category header
// at top-left, capacity at top-right, and selected-item title on the right.
function actOneWorldInventoryClosePermission(o, now, expectedSession) {
    var h = o && o.hud;
    var rows = o && Array.isArray(o.ocr) ? o.ocr : [];
    if (!o || !Number.isFinite(o.timestamp) || !Number.isFinite(now) ||
        now < o.timestamp || now - o.timestamp > 1000 ||
        typeof expectedSession !== 'string' || !expectedSession || o.session !== expectedSession ||
        o.map !== null || !h || h.world !== false || h.dialogueReady !== false ||
        h.choice !== false || h.journal !== false || h.bigMap !== false ||
        h.climbing !== false || h.auto !== false) return null;

    function text(r) { return String(r && r.text || '').trim(); }
    var categories = ['Food', 'Weapons', 'Artifacts', 'Character Development Items',
        'Materials', 'Gadgets', 'Quest', 'Precious Items', 'Furnishings'];
    var header = rows.filter(function (r) {
        return categories.indexOf(text(r)) >= 0 && r.x >= 100 && r.x <= 250 &&
            r.y >= 15 && r.y <= 70 && r.width >= 50 && r.width <= 180 && r.height >= 20 && r.height <= 55;
    });
    var capacity = rows.filter(function (r) {
        var label=text(r),typed=header.length===1&&label.startsWith(text(header[0])+' ')&&/^\d+\/\d+$/.test(label.slice(text(header[0]).length+1));
        return (/^Inventory capacity\s+\d+\/\d+$/i.test(label)||typed) &&
            r.x >= 1450 && r.x <= 1810 && r.y >= 15 && r.y <= 75 && r.width >= 180 && r.width <= 360;
    });
    var selectedItemTitle = rows.filter(function (r) {
        var value = text(r);
        return value.length >= 5 && value.length <= 80 &&
            r.x >= 1280 && r.x <= 1810 && r.y >= 95 && r.y <= 190 &&
            r.width >= 180 && r.width <= 500 && r.height >= 25 && r.height <= 70;
    });

    // Confirm/Cancel identify an action modal. Use is intentionally allowed:
    // it is present on the captured selected-item inventory screen and Escape
    // only closes that screen.
    if (header.length !== 1 || capacity.length !== 1 || selectedItemTitle.length !== 1 ||
        rows.some(function (r) { return ['Confirm', 'Cancel', 'Amount to use'].indexOf(text(r)) >= 0; })) return null;
    return { key: 'VK_ESCAPE', durationMs: 60, frameId: o.frameId, session: o.session };
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { worldInventoryClosePermission: actOneWorldInventoryClosePermission };
}
