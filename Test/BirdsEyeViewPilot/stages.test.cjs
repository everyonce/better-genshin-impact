'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { classify } = require('../../BetterGenshinImpact/User/JsScript/BirdsEyeViewPilot/stages.js');

test('recognizes the selected next quest from the completed RDP run', () => {
  const fixture = require('./completed-run-journal.json');
  const observed = classify(fixture.ocr);
  assert.equal(observed.quest, 'Unexpected Power');
  assert.equal(observed.screen, 'journal');
  assert.equal(observed.completed, false); // The runner requires prior target evidence.
});

const row = (text, x = 900, y = 130) => ({ text, x, y, width: 300, height: 24 });
const journal = objective => [row('In Progress', 140, 40), row("Bird’s Eye View!", 875, 130), row(objective, 930, 267)];

test('recognizes all exact journal objectives despite case and punctuation differences', () => {
  const cases = [
    ['Follow the path', 'follow_path'],
    ['Go to Paimon', 'go_to_paimon'],
    ['Talk to Paimon', 'talk_to_paimon'],
    ['Follow Paimon', 'follow_paimon'],
    ['Swim to the island in Starfell Lake', 'swim_to_island'],
  ];
  for (const [label, stage] of cases) {
    assert.deepEqual(classify(journal(label.toUpperCase() + '!')), {
      screen: 'journal', quest: "Bird's Eye View", stage, completed: false, reason: 'exact_journal_objective',
    });
  }
});

test('does not accept objective phrases embedded in narrative descriptions', () => {
  assert.equal(classify([row('In Progress'), row("Bird's Eye View"), row('The note says: Follow the path, then find the marker.')]).screen, 'unknown');
});

test('recognizes the selected next quest in its journal heading region without inventing a stage', () => {
  assert.deepEqual(classify([row('In Progress', 140, 40), row('Unexpected Power', 875, 130), row('Left entry', 192, 286)]), {
    screen: 'journal', quest: 'Unexpected Power', stage: null, completed: false, reason: 'selected_next_quest_in_journal',
  });
  assert.equal(classify([row("Bird's Eye View"), row('Unexpected Power')]).completed, false);
});

test('requires the target and a spatially plausible same-screen completion banner', () => {
  assert.equal(classify([row("Bird's Eye View"), row('Quest Completed!', 950, 300)]).completed, true);
  assert.equal(classify([row("Bird's Eye View"), row('Quest Completed!', 150, 800)]).completed, false);
  assert.equal(classify([row("Bird's Eye View"), row('In Progress'), row('Unexpected Power')]).completed, false);
  assert.equal(classify([row('Quest Completed!')]).completed, false);
  assert.equal(classify([row("Bird's Eye View"), row('Unexpected Power'), row('Quest Completed!', 950, 300)]).completed, false);
});

test('ambient Paimon subtitles remain unknown without the top-left Auto prompt', () => {
  assert.equal(classify([row('Paimon', 900, 800)]).screen, 'unknown');
  assert.equal(classify([row('Paimon', 900, 800), row('Hey, traveler!', 300, 800)]).screen, 'unknown');
  assert.equal(classify([row('Paimon', 900, 800), row('Hey, traveler!', 900, 900)]).screen, 'unknown');
});

test('interactive Paimon dialogue requires the exact Auto label in the top-left region', () => {
  assert.deepEqual(classify([row('Paimon', 900, 800), row('Hey, traveler!', 900, 900), row('Auto', 100, 50)]), {
    screen: 'dialogue', quest: null, stage: null, completed: false, reason: 'speaker_subtitle_and_auto_prompt',
  });
  assert.equal(classify([row('Paimon', 900, 800), row('Hey, traveler!', 900, 900), row('Auto', 250, 50)]).screen, 'unknown');
});

test('abstains on conflicting objectives and on split or missing journal labels', () => {
  assert.equal(classify([...journal('Follow the path'), row('Talk to Paimon')]).screen, 'unknown');
  assert.equal(classify([row('In Progress'), row("Bird's Eye View"), row('Follow'), row('the path')]).screen, 'unknown');
  assert.equal(classify([row("Bird's Eye View"), row('Follow the path')]).screen, 'unknown');
});
