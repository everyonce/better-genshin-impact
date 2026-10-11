const test = require('node:test');
const assert = require('node:assert/strict');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

function row(text, x, y, width = 100, height = 30) { return { text, x, y, width, height }; }
function wolfEntrance(patch = {}) {
  return {
    timestamp: 1000, frameId: 1519, map: null,
    ocr: [
      row('Domain Entrance', 137, 30),
      row('Deep Within the Temple of the Wolf', 52, 157, 390, 30),
      row('Recommended Party Level: 5', 56, 206, 290, 30),
      row('Deep Within the Temple of the Wolf', 1274, 149, 469, 29),
      row('Start', 1688, 999, 85, 36),
    ],
    hud: { world: false, journal: false, bigMap: false, dialogueReady: false, choice: false, tutorialStep: null },
    ...patch,
  };
}

test('Wolf entrance target accepts only exact selected Wolf level-5 screen', () => {
  assert.deepEqual(bgi.templeStartTarget(wolfEntrance(), 1500, 'Wolf'), {
    x: 1731, y: 1017, label: 'Deep Within the Temple of the Wolf',
  });
  const base = wolfEntrance();
  const wrongTitle = base.ocr.map(r => r.x === 1274 ? { ...r, text: 'Deep Within the Temple of the Falcon' } : r);
  const wrongLevel = base.ocr.map(r => r.text === 'Recommended Party Level: 5' ? { ...r, text: 'Recommended Party Level: 25' } : r);
  const badScreens = [
    { ...base, timestamp: 499 },
    { ...base, timestamp: 1501 },
    { ...base, map: { map: 'Teyvat', x: 0, y: 0 } },
    { ...base, hud: { ...base.hud, journal: true } },
    { ...base, hud: { ...base.hud, bigMap: true } },
    { ...base, hud: { ...base.hud, dialogueReady: true } },
    { ...base, ocr: wrongTitle },
    { ...base, ocr: wrongLevel },
    { ...base, ocr: [...base.ocr, row('Start', 1700, 1000)] },
  ];
  for (const bad of badScreens) assert.equal(bgi.templeStartTarget(bad, 1500, 'Wolf'), null);
  assert.equal(bgi.templeStartTarget(base, 1500, 'Falcon'), null);
  assert.equal(bgi.templeStartTarget(base, 1500, 'Lion'), null);
});

test('wolfStart clicks once, waits, then captures a new frame', async () => {
  let now = 1000, clicks = 0, observes = 0;
  const calls = [];
  const api = {
    now: () => now,
    startWolfDomain: () => { clicks++; calls.push('click'); return 'Deep Within the Temple of the Wolf'; },
    sleep: async ms => { calls.push(['sleep', ms]); now += ms; },
  };
  const result = await mission.runQuestStep('wolfStart', wolfEntrance(), api, async () => {
    observes++; calls.push('observe'); return { frameId: 1520 };
  });
  assert.equal(result.status, 'completed');
  assert.equal(result.step, 'wolfStart');
  assert.equal(result.label, 'Deep Within the Temple of the Wolf');
  assert.equal(clicks, 1);
  assert.equal(observes, 1);
  assert.deepEqual(calls, ['click', ['sleep', 800], 'observe']);
});

function doorFrame(frameId, aligned) {
  const fY = aligned ? 520 : 450;
  return {
    timestamp: 1000 + frameId, frameId, map: { map: 'Teyvat', x: -1642.421, y: 2163.664 },
    ocr: [row('Kaeya', 1200, fY), row('F', 1095, fY), row('Temple of the Wolf', 1200, aligned ? 520 : 540)],
    hud: { world: true, objectives: ['Enter the temple'], dialogueReady: false, choice: false, climbing: false },
  };
}

test('wolfDoorInteract observes after scrolling before F interaction and stays within two attempts', async () => {
  let now = 1000, index = 0;
  const calls = [], actions = [];
  const frames = [doorFrame(1, false), doorFrame(2, true)];
  const api = {
    now: () => now,
    wolfDoorAction: async () => { const action = actions.length === 0 ? 'scroll' : 'interact'; actions.push(action); calls.push(action); return action; },
    sleep: async ms => { calls.push(['sleep', ms]); now += ms; },
  };
  const result = await mission.runQuestStep('wolfDoorInteract', frames[0], api, async () => {
    const next = frames[Math.min(index++, frames.length - 1)]; calls.push(`observe-${next.frameId}`); return next;
  });
  assert.equal(result.status, 'completed');
  assert.equal(result.step, 'wolfDoorInteract');
  assert.equal(result.frameId, 2);
  assert.deepEqual(calls, ['scroll', ['sleep', 400], 'observe-1', 'interact', ['sleep', 1000], 'observe-2']);
  assert.equal(actions.length, 2);
});

test('wolfDoorInteract stops after two unresolved attempts and after an action exception', async () => {
  let now = 1000, attempts = 0, observations = 0;
  const noSettle = await mission.runQuestStep('wolfDoorInteract', doorFrame(1, false), {
    now: () => now,
    wolfDoorAction: async () => { attempts++; return 'scroll'; },
    sleep: async ms => { now += ms; },
  }, async () => { observations++; return doorFrame(observations + 1, false); });
  assert.equal(noSettle.status, 'stopped');
  assert.equal(attempts, 2);
  assert.equal(observations, 2);

  attempts = 0;
  await assert.rejects(() => mission.runQuestStep('wolfDoorInteract', doorFrame(1, false), {
    now: () => now,
    wolfDoorAction: async () => { attempts++; throw new Error('Unsafe/ambiguous row'); },
    sleep: async () => {},
  }, async () => { throw new Error('must not observe after failed action'); }), /Unsafe\/ambiguous row/);
  assert.equal(attempts, 1);
});
