const test = require('node:test');
const assert = require('node:assert/strict');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

const now = 2000000;
function row(text, x, y, width = 55, height = 24) { return { text, x, y, width, height }; }
function airborne(patch = {}) {
  return {
    session: 'wolf-session', timestamp: now, frameId: 228, map: null,
    ocr: [row('Kaeya', 1665, 489), row('Trial', 1802, 463), row('Space', 1680, 1024, 52, 24)],
    hud: { world: false, groundControls: false, climbing: false, health: { current: 626, max: 1427 },
      auto: false, dialogueReady: false, choice: false, journal: false, bigMap: false, tutorialStep: null,
      objectiveChanged: false },
    ...patch,
  };
}

test('airborne pause proof accepts only a fresh exact Wolf party frame with a lower-right Space cue', () => {
  const frame = airborne();
  assert.equal(bgi.wolfAirPauseOnlyHud(frame, now), true);
  assert.equal(bgi.wolfPauseOnlyHud(frame, now), true, 'existing pause-only dispatcher can reuse the airborne proof');
  assert.equal(bgi.wolfAirPauseOnlyHud(airborne({ hud: { ...frame.hud, health: { current: 1, max: 1427 } } }), now), true,
    'any positive captured HP permits Escape-only recovery');
});

test('airborne pause proof rejects stale, future, mapped, world, grounded, or climbing frames', () => {
  const good = airborne();
  for (const bad of [
    airborne({ timestamp: now - 1001 }), airborne({ timestamp: now + 1 }),
    airborne({ map: { map: 'Teyvat', x: 0, y: 0 } }),
    airborne({ ocr: null }),
    airborne({ hud: { ...good.hud, world: true } }),
    airborne({ hud: { ...good.hud, groundControls: true } }),
    airborne({ hud: { ...good.hud, climbing: true } }),
  ]) assert.equal(bgi.wolfAirPauseOnlyHud(bad, now), false);
});

test('airborne pause proof rejects ambiguous, misplaced, or absent party and Space cues', () => {
  const good = airborne();
  for (const patch of [
    { ocr: [...good.ocr, row('Space', 1700, 1010)] },
    { ocr: good.ocr.map(r => r.text === 'Space' ? { ...r, x: 1500 } : r) },
    { ocr: good.ocr.filter(r => r.text !== 'Space') },
    { ocr: [...good.ocr, row('Kaeya', 1660, 480)] },
    { ocr: good.ocr.map(r => r.text === 'Kaeya' ? { ...r, x: 1450 } : r) },
    { ocr: good.ocr.map(r => r.text === 'Trial' ? { ...r, y: 700 } : r) },
    { ocr: good.ocr.filter(r => r.text !== 'Trial') },
  ]) assert.equal(bgi.wolfAirPauseOnlyHud(airborne(patch), now), false);
});

test('airborne pause proof rejects dead, malformed, or wrong-max health and any conflicting UI state', () => {
  const good = airborne();
  for (const bad of [
    airborne({ hud: { ...good.hud, health: { current: 0, max: 1427 } } }),
    airborne({ hud: { ...good.hud, health: { current: 1428, max: 1427 } } }),
    airborne({ hud: { ...good.hud, health: { current: 600, max: 1055 } } }),
    ...['auto', 'loading', 'unknownHud', 'objectiveChanged', 'dialogueReady', 'choice', 'journal', 'bigMap']
      .map(flag => airborne({ hud: { ...good.hud, [flag]: true } })),
    airborne({ hud: { ...good.hud, tutorialStep: 'glideOpen' } }),
  ]) assert.equal(bgi.wolfAirPauseOnlyHud(bad, now), false);
});

test('grounded pause-only behavior still works without the airborne Space cue', () => {
  const frame = airborne({ hud: { ...airborne().hud, groundControls: true }, ocr: [row('Kaeya', 1665, 489), row('Trial', 1802, 463)] });
  assert.equal(bgi.wolfAirPauseOnlyHud(frame, now), false);
  assert.equal(bgi.wolfPauseOnlyHud(frame, now), true);
});
