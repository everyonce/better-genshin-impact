'use strict';

// Pure OCR classifier. It deliberately requires exact recognized labels and
// abstains when OCR suggests more than one incompatible state.
var BirdsEyeStages = (function () {
  const objectives = new Map([
    ['follow the path', { quest: "Bird's Eye View", stage: 'follow_path' }],
    ['go to paimon', { quest: "Bird's Eye View", stage: 'go_to_paimon' }],
    ['talk to paimon', { quest: "Bird's Eye View", stage: 'talk_to_paimon' }],
    ['follow paimon', { quest: "Bird's Eye View", stage: 'follow_paimon' }],
    ['swim to the island in starfell lake', { quest: "Bird's Eye View", stage: 'swim_to_island' }],
  ]);

  function normalize(value) {
    return String(value || '')
      .normalize('NFKC')
      .replace(/[’‘`´]/g, "'")
      .toLowerCase()
      .replace(/[^a-z0-9']/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function classify(rows) {
    const validRows = Array.isArray(rows) ? rows.filter(row => row && typeof row.text === 'string') : [];
    const matching = value => validRows.filter(row => normalize(row.text) === normalize(value));
    const has = value => matching(value).length > 0;
    const inProgress = has('In Progress');
    const titleInHeading = title => matching(title).filter(inHeading);
    const birdHeadings = titleInHeading("Bird's Eye View");
    const nextHeadings = titleInHeading('Unexpected Power');
    const birdRows = birdHeadings.length ? birdHeadings : matching("Bird's Eye View");
    const nextRows = nextHeadings.length ? nextHeadings : matching('Unexpected Power');
    const target = birdRows.length > 0;
    const nextQuest = nextRows.length > 0;
    const completionRows = [...matching('Quest Completed'), ...matching('Quest Complete')];
    const found = [...objectives.entries()].filter(([label]) => has(label)).map(([, result]) => result);
    const distinctStages = [...new Set(found.map(item => item.stage))];
    const bothTitles = target && nextQuest;

    if (target && !bothTitles && completionRows.some(banner => birdRows.some(title => plausiblyGrouped(title, banner)))) {
      return result('completion', "Bird's Eye View", null, true, 'target_and_completion_banner');
    }
    if (bothTitles) {
      return result('unknown', null, null, false, 'conflicting_quest_titles');
    }
    if (target && inProgress && distinctStages.length === 1 && found.every(item => item.quest === "Bird's Eye View")) {
      return result('journal', "Bird's Eye View", distinctStages[0], false, 'exact_journal_objective');
    }
    if (nextQuest && inProgress && nextRows.some(inHeading)) {
      return result('journal', 'Unexpected Power', null, false, 'selected_next_quest_in_journal');
    }
    if (distinctStages.length > 0 || (target && inProgress) || (target && completionRows.length > 0)) {
      return result('unknown', null, null, false, 'conflicting_or_incomplete_evidence');
    }
    const speakerIndexes = validRows.map((row, index) => ({ row, index }))
      .filter(({ row }) => normalize(row.text) === 'paimon' && inBottomCenter(row));
    const hasSubtitle = speakerIndexes.some(({ index }) => validRows.some((row, otherIndex) =>
      otherIndex !== index && normalize(row.text).length > 0 && inBottomArea(row)));
    const hasAutoPrompt = matching('Auto').some(inTopLeft);
    if (hasSubtitle && hasAutoPrompt) return result('dialogue', null, null, false, 'speaker_subtitle_and_auto_prompt');
    return result('unknown', null, null, false, 'no_confirmed_quest_state');
  }

  function hasCoordinates(row) {
    return Number.isFinite(row.x) && Number.isFinite(row.y);
  }

  function inHeading(row) {
    return !hasCoordinates(row) || (row.x >= 800 && row.x <= 1800 && row.y >= 80 && row.y <= 200);
  }

  function inBottomArea(row) {
    return hasCoordinates(row) && row.x >= 600 && row.x <= 1200 && row.y >= 700 && row.y <= 1000;
  }

  function inBottomCenter(row) {
    return inBottomArea(row);
  }

  function inTopLeft(row) {
    return hasCoordinates(row) && row.x >= 0 && row.x < 200 && row.y >= 0 && row.y < 100;
  }

  function plausiblyGrouped(a, b) {
    if (!hasCoordinates(a) || !hasCoordinates(b)) return true;
    const ax = a.x + (Number.isFinite(a.width) ? a.width / 2 : 0);
    const bx = b.x + (Number.isFinite(b.width) ? b.width / 2 : 0);
    return Math.abs(ax - bx) <= 700 && Math.abs(a.y - b.y) <= 400;
  }

  function result(screen, quest, stage, completed, reason) {
    return { screen, quest, stage, completed, reason };
  }

  return { classify };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = BirdsEyeStages;
