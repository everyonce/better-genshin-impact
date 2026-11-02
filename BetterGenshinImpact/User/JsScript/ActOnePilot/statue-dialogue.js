(function (root, factory) {
  var api = factory();
  root.ActOneStatueDialogue = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var FRESH_MS = 1000;
  var SPEAKER = 'Statue of The Seven';
  var OPENING = 'The world opens itself before those with noble hearts.';
  var BLESSINGS = ["Statue’s Blessing", "Statue's Blessing"];
  var HAZARD_TEXT = /\b(?:loading|log\s*in|authentication|auth|verification|verify|confirm(?:ation)?|are you sure|purchase|offering|offer)\b/i;

  function normalized(value) {
    return String(value == null ? '' : value).replace(/\s+/g, ' ').trim().replace(/[.]$/, '');
  }

  function rowText(row) { return normalized(row && row.text); }

  function validRow(row) {
    return !!row && Number.isFinite(row.x) && Number.isFinite(row.y) &&
      Number.isFinite(row.width) && Number.isFinite(row.height) && row.width > 0 && row.height > 0;
  }

  function inChoiceBox(row) {
    return validRow(row) && row.x > 1000 && row.x < 1800 && row.y >= 430 && row.y <= 830 &&
      row.width >= 25 && row.width <= 650 && row.height >= 14 && row.height <= 100 &&
      row.x + row.width < 1900 && row.y + row.height < 900;
  }

  function unsafeHud(hud) {
    // The observer clears dialogueReady while the choice list is visible.
    // Exact Auto, speaker, opening subtitle and both choices still identify this UI.
    if (!hud || hud.auto !== true || (hud.dialogueReady !== true && !(hud.choice === true && hud.dialogueReady === false)) || hud.world !== false ||
        hud.journal !== false || hud.bigMap !== false || (hud.choice !== false && hud.choice !== true) || hud.climbing !== false ||
        hud.objectiveChanged !== false || hud.tutorialStep != null || hud.loading === true || hud.unknownHud === true)
      return true;
    // Dialogue has hidden health/party/objective HUD. A visible health reading means this is another screen.
    if (hud.health != null || hud.party === true || hud.objectiveVisible === true || hud.menu === true || hud.confirm === true)
      return true;
    return false;
  }

  function exactDialogueRows(o, allowSilentOpening) {
    var rows = Array.isArray(o && o.ocr) ? o.ocr : [];
    var autoAnchors = rows.filter(function (r) { return rowText(r) === 'Auto'; });
    var speakers = rows.filter(function (r) { return rowText(r) === SPEAKER; });
    var bodies = rows.filter(function (r) { return rowText(r) === normalized(OPENING); });
    var silent = allowSilentOpening === true && bodies.length === 0 &&
      rows.filter(function (r) { return validRow(r) && r.y >= 895 && r.y <= 980 && r.x > 200 && r.x < 1550; })
        .every(function (r) { return /^[.\u2026\u22ef\s]*$/.test(String(r.text || '')); });
    if (autoAnchors.length !== 1 || speakers.length !== 1 || (bodies.length !== 1 && !silent) ||
        !validRow(autoAnchors[0]) || !validRow(speakers[0]) || (!silent && !validRow(bodies[0]))) return null;
    var auto = autoAnchors[0], speaker = speakers[0], body = bodies[0] || null;
    // Bound this allowlist to the observed Windrise subtitle layout; unrelated UI cannot satisfy it.
    if (auto.x < 90 || auto.x > 190 || auto.y < 10 || auto.y > 60 || auto.width < 45 || auto.width > 110 ||
        auto.height < 20 || auto.height > 45 ||
        speaker.x < 650 || speaker.x > 1000 || speaker.y < 820 || speaker.y > 900 ||
        speaker.width < 280 || speaker.width > 450 || speaker.height < 20 || speaker.height > 55 ||
        body && (body.x < 400 || body.x > 1000 || body.y < 875 || body.y > 960 ||
        body.width < 700 || body.width > 1050 || body.height < 20 || body.height > 50 ||
        speaker.y >= body.y + body.height)) return null;
    if (rows.some(function (r) { return HAZARD_TEXT.test(String(r && r.text || '')); })) return null;
    return { speaker: speaker, body: body, rows: rows };
  }

  function validObservation(o, now, session, state) {
    return !!o && typeof session === 'string' && session.length > 0 && state && state.session === session &&
      state.armed === true && state.interactionAttempted === true &&
      Number.isInteger(state.lastInputFrame) && state.lastInputFrame >= 0 &&
      typeof state.advanceAttempted === 'boolean' && typeof state.leaveAttempted === 'boolean' &&
      Number.isFinite(now) && Number.isFinite(o.timestamp) && now >= o.timestamp && now - o.timestamp <= FRESH_MS &&
      o.session === session && Number.isInteger(o.frameId) && o.frameId > state.lastInputFrame &&
      Number.isFinite(o.frameId) && !unsafeHud(o.hud);
  }

  function leaveTarget(rows) {
    var candidates = rows.filter(inChoiceBox);
    var leaves = candidates.filter(function (r) { return rowText(r) === 'Leave'; });
    var blessings = candidates.filter(function (r) { return BLESSINGS.indexOf(rowText(r)) >= 0; });
    if (leaves.length !== 1 || blessings.length !== 1) return null;
    // Recorded Starfell choice screens include a small F prompt left of Blessing.
    // It is a key hint, not an additional actionable choice. Reject duplicates
    // and any F row outside that narrow, vertically aligned geometry.
    var hints = candidates.filter(function (r) { return rowText(r) === 'F'; });
    if (hints.length > 1) return null;
    if (hints.length === 1) {
      var hint = hints[0], blessing = blessings[0];
      if (hint.x < 1180 || hint.x > 1260 || hint.width > 55 || hint.height > 55 ||
          Math.abs(hint.y - blessing.y) > 20 || hint.x + hint.width >= blessing.x) return null;
      candidates = candidates.filter(function (r) { return r !== hint; });
    }
    // Extra actionable text could be an offering or confirmation panel and stays untouched.
    var labels = candidates.map(rowText).filter(function (text) { return text.length > 0; });
    if (labels.length !== 2 || labels.indexOf('Leave') < 0 ||
        labels.filter(function (text) { return BLESSINGS.indexOf(text) >= 0; }).length !== 1) return null;
    return leaves[0];
  }

  function action(o, now, session, state) {
    if (!validObservation(o, now, session, state)) return null;
    var found = exactDialogueRows(o, state.allowSilentOpening);
    if (!found) return null;
    if (o.hud.choice === true) {
      if (state.leaveAttempted !== false) return null;
      var leave = leaveTarget(found.rows);
      if (!leave) return null;
      return { kind: 'leave', x: leave.x + leave.width / 2, y: leave.y + leave.height / 2 };
    }
    if (state.advanceAttempted !== false || o.hud.choice !== false) return null;
    return { kind: 'advance', key: 'VK_SPACE', durationMs: 60 };
  }

  // Close only the positively observed empty Lv.3 Worship panel; never offer or infer hidden health.
  function worshipCloseAction(o, now, session, state) {
    var h = o && o.hud, stamp = h && h.captureStamp;
    if (!state || state.session !== session || state.purpose !== 'inventory-protection' ||
        state.worshipCloseAttempted !== false || typeof state.advanceAttempted !== 'boolean' ||
        typeof state.leaveAttempted !== 'boolean' || !Number.isInteger(state.lastInputFrame) || state.lastInputFrame < -1 ||
        !(state.afterInputAt === null || Number.isFinite(state.afterInputAt)) ||
        !o || o.session !== session || !Number.isInteger(o.frameId) || o.frameId <= 0 || o.frameId <= state.lastInputFrame ||
        !Number.isFinite(now) || !Number.isFinite(o.timestamp) || o.timestamp > now ||
        !stamp || stamp.session !== session || stamp.frameId !== o.frameId || stamp.source !== 'game-capture-start' ||
        !Number.isFinite(stamp.capturedAt) || stamp.capturedAt <= 0 || stamp.capturedAt > o.timestamp ||
        now < stamp.capturedAt || now - stamp.capturedAt > FRESH_MS ||
        state.afterInputAt !== null && stamp.capturedAt <= state.afterInputAt || o.map !== null ||
        h.world !== false || h.groundControls !== false || h.auto !== false || h.dialogueReady !== false ||
        h.choice !== false || h.journal !== false || h.bigMap !== false || h.climbing !== false ||
        h.objectiveChanged !== false || h.tutorialStep != null || h.health != null || h.party === true ||
        h.objectiveVisible === true || h.menu === true || h.confirm === true ||
        h.loading !== undefined && h.loading !== false || h.unknownHud !== undefined && h.unknownHud !== false ||
        !Array.isArray(h.enemyBars) || h.enemyBars.length ||
        !Array.isArray(o.ocr)) return null;
    // Generic observations may omit loading/unknownHud; the complete positive panel evidence is mandatory.
    var rows = o.ocr, ids = rows.filter(function (r) {
      var text = r && String(r.text || '').trim();
      return r && (/^UID\s*:?\s*\d{9}$/i.test(text) ||
        Number.isFinite(r.x) && Number.isFinite(r.y) && r.x >= 1600 && r.y >= 1030 &&
        (/^UID\b/i.test(text) || /^\d{9}$/.test(text)));
    }), uid = ids[0];
    if (ids.length !== 1 || !/^(?:UID\s*:?\s*)?693306810$/.test(String(uid.text || '').trim()) ||
        !validRow(uid) || uid.x < 1600 || uid.y < 1030 || uid.x + uid.width > 1920 || uid.y + uid.height > 1080)
      return null;
    function one(text, x1, x2, y1, y2) {
      var matches = rows.filter(function (r) { return r && String(r.text || '').trim() === text; });
      if (matches.length !== 1) return false;
      var r = matches[0];
      return validRow(r) && r.x >= x1 && r.x <= x2 && r.y >= y1 && r.y <= y2 &&
        r.x + r.width <= 1920 && r.y + r.height <= 1080;
    }
    if (!one('Lv.', 1550, 1660, 50, 100) || !one('3', 1550, 1660, 95, 150) ||
        !one('Worship Statue', 1300, 1500, 170, 230) || !one('Anemoculus 0/4', 1700, 1900, 170, 230) ||
        !one("Statue's Rewards", 1450, 1750, 230, 290) ||
        !one('Current Stamina Limit: 114/240', 1400, 1800, 320, 370) ||
        !one('Required Anemoculus', 1450, 1750, 820, 880) || !one('Owned', 1400, 1530, 870, 910) ||
        !one('x 0', 1400, 1530, 900, 950) || !one('Offer', 1380, 1530, 980, 1040) ||
        !one('Offer All', 1650, 1800, 980, 1040) ||
        rows.some(function (r) { return /\b(?:loading|log\s*in|authentication|auth|verification|verify|confirm(?:ation)?|purchase|cancel|blessing|leave|auto)\b/i.test(String(r && r.text || '')); }))
      return null;
    return { kind: 'worship-close', key: 'VK_ESCAPE', durationMs: 60 };
  }

  // Current-party recovery has its own source/account contract; entry cleanup never pretends to have pressed F.
  function recoveryAction(o, now, session, state) {
    var worship = worshipCloseAction(o, now, session, state);
    if (worship) return worship;
    var stamp = o && o.hud && o.hud.captureStamp;
    if (!state || state.session !== session ||
        (state.purpose !== 'healer-intro' && state.purpose !== 'inventory-protection') ||
        !Number.isInteger(state.lastInputFrame) || state.lastInputFrame < -1 ||
        typeof state.advanceAttempted !== 'boolean' || typeof state.leaveAttempted !== 'boolean' ||
        !(state.afterInputAt === null || Number.isFinite(state.afterInputAt)) ||
        !o || o.session !== session || !Number.isInteger(o.frameId) || o.frameId <= 0 || o.frameId <= state.lastInputFrame ||
        !Number.isFinite(now) || !Number.isFinite(o.timestamp) || o.timestamp > now ||
        !stamp || stamp.session !== session || stamp.frameId !== o.frameId || stamp.source !== 'game-capture-start' ||
        !Number.isFinite(stamp.capturedAt) || stamp.capturedAt <= 0 || stamp.capturedAt > o.timestamp ||
        now < stamp.capturedAt || now - stamp.capturedAt > FRESH_MS ||
        state.afterInputAt !== null && stamp.capturedAt <= state.afterInputAt ||
        o.map !== null || unsafeHud(o.hud) || o.hud.groundControls !== false ||
        o.hud.loading !== false || o.hud.unknownHud !== false) return null;
    // A complete conflicting UID anywhere, or an ambiguous account strip, rejects the source.
    var ids = (Array.isArray(o.ocr) ? o.ocr : []).filter(function (r) {
      var text = r && String(r.text || '').trim();
      return r && (/^UID\s*:?\s*\d{9}$/i.test(text) ||
        Number.isFinite(r.x) && Number.isFinite(r.y) && r.x >= 1600 && r.y >= 1030 &&
        (/^UID\b/i.test(text) || /^\d{9}$/.test(text)));
    });
    var uid = ids[0];
    if (ids.length !== 1 || !/^(?:UID\s*:?\s*)?693306810$/.test(String(uid.text || '').trim()) ||
        !validRow(uid) || uid.x < 1600 || uid.y < 1030 || uid.x + uid.width > 1920 || uid.y + uid.height > 1080)
      return null;
    var found = exactDialogueRows(o, true);
    if (!found) return null;
    if (o.hud.choice === true) {
      if (state.purpose !== 'inventory-protection' || state.leaveAttempted) return null;
      var leave = leaveTarget(found.rows);
      return leave ? { kind: 'leave', x: leave.x + leave.width / 2, y: leave.y + leave.height / 2 } : null;
    }
    if (found.rows.some(inChoiceBox)) return null;
    return state.advanceAttempted || o.hud.choice !== false ? null : { kind: 'advance', key: 'VK_SPACE', durationMs: 60 };
  }

  return Object.freeze({ action: action, recoveryAction: recoveryAction });
});
