'use strict';

// Dependency-injected orchestration only. Route segments and all game I/O are
// supplied by the caller; this module never invents controls or coordinates.
var BirdsEyeRunner = (function () {
  const TARGET = "Bird's Eye View";
  const NEXT_QUEST = 'Unexpected Power';

  async function run(options) {
    const api = options && options.api;
    const routes = options && options.routes || {};
    const started = Date.now();
    // This budget is checked between awaited calls. A hung native input or
    // observation promise cannot be preempted by this pure JS orchestration.
    const maxDurationMs = positive(options && options.maxDurationMs, 15 * 60 * 1000);
    const maxNoProgress = positive(options && options.maxNoProgress, 3);
    const maxUnknown = positive(options && options.maxUnknownObservations, 30);
    let targetConfirmed = false;
    let unknownCount = 0;
    let noProgress = 0;
    let lastStage = null;
    let dialogueAdvanceCount = 0;
    let lastDialogueSignature = null;
    let sameSignatureAdvances = 0;
    const usedSegments = new Set();
    const status = (state) => { if (api && api.saveStatus) return api.saveStatus(state); };
    const result = (state, reason, extra) => ({ state, reason, ...(extra || {}) });

    try {
      if (!api || typeof api.assertRdp !== 'function' || typeof api.observe !== 'function') {
        return result('blocked', 'invalid_api');
      }
      await api.assertRdp();
      while (Date.now() - started < maxDurationMs) {
        const observation = await api.observe();
        if (!observation || typeof observation !== 'object') {
          unknownCount++;
          if (unknownCount >= maxUnknown) return result('blocked', 'unknown_state');
          await api.wait(1000);
          continue;
        }
        const quest = observation.quest;
        const screen = observation.screen;
        const stage = observation.stage;
        if (observation.completed === true && quest === TARGET) return result('completed', 'target_quest_completed');
        if (quest === NEXT_QUEST) {
          return targetConfirmed
            ? result('completed', 'verified_next_quest_transition')
            : result('blocked', 'next_quest_reached');
        }
        if (quest === TARGET) targetConfirmed = true;

        if (screen === 'unknown' || !screen) {
          unknownCount++;
          if (unknownCount >= maxUnknown) return result('blocked', 'unknown_state');
          await api.wait(1000);
          continue;
        }
        unknownCount = 0;

        if (stage && stage !== lastStage) {
          noProgress = 0;
          lastStage = stage;
        }
        if (screen === 'journal' && quest === TARGET && stage) {
          const route = routes[stage];
          const segment = Array.isArray(route) ? route.find(item => item !== undefined && !usedSegments.has(item)) : route;
          if (segment === undefined || segment === null) return result('blocked', 'no_route_for_stage', { stage });
          if (usedSegments.has(segment)) return result('blocked', 'route_segment_already_used', { stage });
          usedSegments.add(segment);
          await api.assertRdp();
          await api.navigate(segment);
        } else if (screen === 'dialogue') {
          if (!targetConfirmed) return result('blocked', 'dialogue_without_target_confirmation');
          if (typeof observation.signature !== 'string' || observation.signature.length === 0) {
            return result('blocked', 'dialogue_signature_missing');
          }
          if (dialogueAdvanceCount >= 30) return result('blocked', 'dialogue_advance_limit');
          if (observation.signature === lastDialogueSignature) {
            sameSignatureAdvances++;
            if (sameSignatureAdvances > 2) return result('blocked', 'dialogue_signature_stalled');
          } else {
            lastDialogueSignature = observation.signature;
            sameSignatureAdvances = 1;
            noProgress = 0;
          }
          if (typeof api.advanceDialogue !== 'function') return result('blocked', 'dialogue_advance_unavailable');
          await api.assertRdp();
          await api.advanceDialogue();
          dialogueAdvanceCount++;
          await api.wait(1000);
          noProgress++;
          if (noProgress >= maxNoProgress) return result('blocked', 'no_progress', { stage: stage || null });
          await status({ state: 'running', stage: stage || null, usedSegments: [...usedSegments] });
          continue;
        } else {
          return result('blocked', 'unactionable_observation', { screen, stage: stage || null });
        }

        await status({ state: 'running', stage: stage || null, usedSegments: [...usedSegments] });
        await api.wait(1000);
        noProgress++;
        if (noProgress >= maxNoProgress) return result('blocked', 'no_progress', { stage: stage || null });
      }
      return result('blocked', 'duration_limit');
    } catch (error) {
      return result('blocked', 'runner_error', { error: String(error && error.message || error) });
    } finally {
      if (api && typeof api.release === 'function') {
        try { await api.release(); } catch (_) { /* preserve the primary outcome */ }
      }
    }
  }

  function positive(value, fallback) {
    return Number.isFinite(value) && value > 0 ? value : fallback;
  }

  return { run };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = BirdsEyeRunner;
