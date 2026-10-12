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
    if (!hud || hud.auto !== true || hud.dialogueReady !== true || hud.world !== false ||
        hud.journal !== false || hud.bigMap !== false || (hud.choice !== false && hud.choice !== true) || hud.climbing !== false ||
        hud.objectiveChanged !== false || hud.tutorialStep != null || hud.loading === true || hud.unknownHud === true)
      return true;
    // Dialogue has hidden health/party/objective HUD. A visible health reading means this is another screen.
    if (hud.health != null || hud.party === true || hud.objectiveVisible === true || hud.menu === true || hud.confirm === true)
      return true;
    return false;
  }

  function exactDialogueRows(o) {
    var rows = Array.isArray(o && o.ocr) ? o.ocr : [];
    var autoAnchors = rows.filter(function (r) { return rowText(r) === 'Auto'; });
    var speakers = rows.filter(function (r) { return rowText(r) === SPEAKER; });
    var bodies = rows.filter(function (r) { return rowText(r) === normalized(OPENING); });
    if (autoAnchors.length !== 1 || speakers.length !== 1 || bodies.length !== 1 ||
        !validRow(autoAnchors[0]) || !validRow(speakers[0]) || !validRow(bodies[0])) return null;
    var auto = autoAnchors[0], speaker = speakers[0], body = bodies[0];
    // Bound this allowlist to the observed Windrise subtitle layout; unrelated UI cannot satisfy it.
    if (auto.x < 90 || auto.x > 190 || auto.y < 10 || auto.y > 60 || auto.width < 45 || auto.width > 110 ||
        auto.height < 20 || auto.height > 45 ||
        speaker.x < 650 || speaker.x > 1000 || speaker.y < 820 || speaker.y > 900 ||
        speaker.width < 280 || speaker.width > 450 || speaker.height < 20 || speaker.height > 55 ||
        body.x < 400 || body.x > 1000 || body.y < 875 || body.y > 960 ||
        body.width < 700 || body.width > 1050 || body.height < 20 || body.height > 50 ||
        speaker.y >= body.y + body.height) return null;
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
    // Leave-choice geometry below is synthetic, with no recorded or live-validated choice capture.
    // Extra actionable text could be an offering or confirmation panel and stays untouched.
    var labels = candidates.map(rowText).filter(function (text) { return text.length > 0; });
    if (labels.length !== 2 || labels.indexOf('Leave') < 0 ||
        labels.filter(function (text) { return BLESSINGS.indexOf(text) >= 0; }).length !== 1) return null;
    return leaves[0];
  }

  function action(o, now, session, state) {
    if (!validObservation(o, now, session, state)) return null;
    var found = exactDialogueRows(o);
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

  return Object.freeze({ action: action });
});
