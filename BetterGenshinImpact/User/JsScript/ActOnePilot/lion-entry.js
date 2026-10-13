var ActOneLionEntry = (function () {
var TITLE = 'Deep Within the Temple of the Lion';
var OUTER_LABEL = 'Temple of the Lion';

function rowsFor(observation, label) {
  return (Array.isArray(observation && observation.ocr) ? observation.ocr : []).filter(r =>
    r && typeof r.text === 'string' && r.text.trim() === label);
}
function validBox(r) {
  return Number.isFinite(r.x) && Number.isFinite(r.y) && Number.isFinite(r.width) && Number.isFinite(r.height) && r.width > 0 && r.height > 0;
}
function freshSafeDomainScreen(o, now) {
  const h = o && o.hud;
  return !!(o && Number.isFinite(o.timestamp) && Number.isFinite(now) && now >= o.timestamp && now - o.timestamp <= 1000 &&
    o.map === null && h && h.world === false && h.journal === false && h.bigMap === false &&
    h.dialogueReady === false && h.choice === false && h.climbing === false && h.auto === false && !h.tutorialStep);
}
function oneIn(rows, label, x0, x1, y0, y1) {
  const found = rowsFor({ ocr: rows }, label).filter(r => validBox(r) && r.x >= x0 && r.x < x1 && r.y >= y0 && r.y < y1);
  return found.length === 1 ? found[0] : null;
}
function startTarget(o, now) {
  if (!freshSafeDomainScreen(o, now)) return null;
  const rows = o.ocr || [];
  const header = oneIn(rows, 'Domain Entrance', 70, 300, 0, 90);
  const outer = oneIn(rows, OUTER_LABEL, 0, 600, 100, 230);
  // The live quest entrance omits the outer temple heading. Its selected
  // quest instead has an exact level recommendation and Lisa description.
  const questDetail = oneIn(rows, 'Recommended Party Level: 5', 0, 600, 190, 245) &&
    oneIn(rows, 'forth with Lisa the Librarian to the Temple of', 1200, 1900, 235, 280);
  const left = oneIn(rows, TITLE, 0, 600, 100, 230);
  const selected = oneIn(rows, TITLE, 900, 1850, 100, 230);
  const button = oneIn(rows, 'Start', 1550, 1900, 950, 1070);
  if (!header || !(outer || questDetail) || !left || !selected || !button || rowsFor(o, 'Start').length !== 1 ||
      rowsFor(o, OUTER_LABEL).length > 1 || rowsFor(o, TITLE).length !== 2 ||
      rows.some(r => r && typeof r.text === 'string' && /Temple of the (Falcon|Wolf)/.test(r.text.trim()))) return null;
  const x = Math.round(button.x + button.width / 2), y = Math.round(button.y + button.height / 2);
  if (!Number.isFinite(x) || !Number.isFinite(y) || x < 1550 || x >= 1900 || y < 950 || y >= 1070) return null;
  return { x, y, label: TITLE };
}
function safeUIParty(o, now) {
  if (!freshSafeDomainScreen(o, now)) return null;
  const rows = o.ocr || [];
  const required = [
    oneIn(rows, 'Party Setup', 50, 450, 0, 120),
    oneIn(rows, 'Lumina', 250, 650, 240, 430),
    oneIn(rows, 'Amber', 600, 1000, 240, 450),
    oneIn(rows, 'Team Standing By', 50, 500, 930, 1080),
    oneIn(rows, 'Start', 1550, 1900, 950, 1070),
  ];
  if (required.some(x => !x) || rowsFor(o, 'Start').length !== 1 ||
      rows.some(r => r && typeof r.text === 'string' && /^(Trial|Recommended Party Level:|Temple of the (Falcon|Wolf))/.test(r.text.trim()))) return null;
  const button = required[4], x = Math.round(button.x + button.width / 2), y = Math.round(button.y + button.height / 2);
  return Number.isFinite(x) && Number.isFinite(y) && x >= 1550 && x < 1900 && y >= 950 && y < 1070 ? { x, y } : null;
}
function isReadOnly(e) {
  return !!e && ['controllerRevision', 'observe', 'observation'].includes(e.type);
}
function entryProof(reports, session, observation, currentRequestId) {
  if (!Array.isArray(reports) || typeof session !== 'string' || !session || !observation ||
      !Number.isFinite(observation.timestamp) || observation.session !== session) return false;
  const entries = reports.filter(r => r && r.session === session && r.mission === 'questStep' && r.status === 'completed' &&
    r.details && r.details.result && r.details.result.step === 'lionStart');
  if (entries.length !== 1) return false;
  const entry = entries[0], events = entry.details.inputEvents;
  if (!Number.isFinite(entry.timestamp) || entry.timestamp > observation.timestamp || !Array.isArray(events) ||
      entry.details.result.label !== TITLE) return false;
  const proofEvents = events.filter(e => e && e.type === 'lionDomainStart');
  if (proofEvents.length !== 1) return false;
  const proof = proofEvents[0], startAt = proof.startedAt;
  if (proof.label !== TITLE || !Number.isFinite(startAt) || !Number.isInteger(proof.frameId) || proof.frameId < 0 ||
      !Number.isInteger(proof.x) || proof.x < 1550 || proof.x >= 1900 || !Number.isInteger(proof.y) || proof.y < 950 || proof.y >= 1070 ||
      startAt > entry.timestamp || entry.timestamp > observation.timestamp) return false;
  const proofIndex = events.indexOf(proof);
  for (let i = proofIndex + 1; i < events.length; i++) if (!isReadOnly(events[i])) return false;
  for (const report of reports) {
    if (!report || report.session !== session) continue;
    // The engine records dispatch before checking party readiness. It is
    // metadata, not a missing input log; completed attempts retain their log.
    if (report.status === 'started' && typeof report.id === 'string' &&
        (report.id === currentRequestId || reports.some(r => r && r.id === report.id && r.session === session &&
          ['completed','stopped','failed','rejected'].includes(r.status) && Array.isArray(r.details && r.details.inputEvents)))) continue;
    const otherEvents = report.details && report.details.inputEvents;
    if (!Array.isArray(otherEvents)) {
      if (report !== entry && report.timestamp >= startAt && report.timestamp <= observation.timestamp && report.mission !== 'observe') return false;
      continue;
    }
    for (const event of otherEvents) {
      if (report === entry && event === proof || isReadOnly(event)) continue;
      if (!event || typeof event.type !== 'string' || !Number.isFinite(event.startedAt)) {
        if (Number.isFinite(report.timestamp) && report.timestamp >= startAt && report.timestamp <= observation.timestamp) return false;
      } else if (event.startedAt >= startAt && event.startedAt <= observation.timestamp) return false;
    }
  }
  return true;
}
function partyTarget(o, now, reports, session, currentRequestId) {
  const target = safeUIParty(o, now);
  return target && entryProof(reports, session, o, currentRequestId) ? target : null;
}

return { startTarget: startTarget, partyTarget: partyTarget, entryProof: entryProof, safeUIParty: safeUIParty };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = ActOneLionEntry;
