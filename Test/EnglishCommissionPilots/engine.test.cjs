const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const packageRoot = path.join(__dirname, '..', '..', 'BetterGenshinImpact', 'User', 'JsScript', 'AutoCommissionEnglishPilots');
const pilotsEngine = require(path.join(packageRoot, 'engine.js'));

const routePath = 'assets/test/route.json';
const routeJson = JSON.stringify({ info: { name: 'Original', description: 'Original' }, positions: [{ x: 1, y: 2 }] });

function fixture({ stages, choices, manualChoices = false } = {}) {
  const plan = {
    id: 'pilot-a',
    title: 'A Proper Commission',
    stages: stages || [{ route: 0, talks: 1, npcs: ['Mara'], choices: choices || ['Tell me more'] }],
  };
  if (manualChoices) plan.manualChoices = true;
  const plans = [plan];
  const catalog = { pilots: [
    { id: 'pilot-a', title: plan.title, routes: [routePath, 'assets/test/route2.json'] },
    { id: 'pilot-b', title: 'Second Commission', routes: [routePath] },
    { id: 'pilot-c', title: 'Third Commission', routes: [routePath] },
  ] };
  return { plan, plans, catalog };
}

function makeApi({ capture, metrics = [1920, 1080], journalFound = true, sleep } = {}) {
  const log = { keys: [], interactions: [], clicks: [], paths: [], enabled: 0, cleared: 0, infos: [], reads: [] };
  let time = 0;
  let captures = 0;
  const api = {
    sleep: async (ms) => {
      if (sleep) await sleep(ms, { log, time: () => time, captures: () => captures });
      time += ms;
    },
    capture: () => {
      captures++;
      return capture ? capture(captures, log) : { hud: true, interactions: [], options: [], completion: [] };
    },
    key: (key) => log.keys.push(key),
    journal: () => journalFound ? [{ text: 'A Proper Commission', x: 10, y: 10, width: 100, height: 20 }] : [],
    metrics: () => metrics,
    interact: (match) => log.interactions.push(match),
    now: () => time,
    click: (match) => log.clicks.push(match),
    info: (message) => log.infos.push(message),
    enableDialogue: () => { log.enabled++; },
    clearDialogue: () => { log.cleared++; },
    path: async (json) => log.paths.push(JSON.parse(json)),
    read: (path) => { log.reads.push(path); return routeJson; },
  };
  return { api, log };
}

const opts = { pilot: 'A Proper Commission', dialogueTimeoutSeconds: 30 };
function hud(interactions = []) { return { hud: true, interactions, options: [], completion: [] }; }
function dialog(options = []) { return { hud: false, interactions: [], options, completion: [] }; }

test('OCR matching handles wrapped lines, case, and punctuation but rejects substrings and ambiguity', () => {
  const wrapped = [
    { text: 'Madam', x: 10, y: 10, width: 45, height: 12 },
    { text: 'Ping', x: 10, y: 24, width: 35, height: 12 },
  ];
  assert.equal(pilotsEngine.uniqueMatch(wrapped, ['Madam Ping']).text, 'MadamPing');
  assert.equal(pilotsEngine.uniqueMatch([{ text: '  COMMISSION—COMPLETE! ', x: 0, y: 0, width: 100, height: 20 }], ['Commission Complete']).text.trim(), 'COMMISSION—COMPLETE!');
  assert.equal(pilotsEngine.uniqueMatch([{ text: 'Not the Librarian', x: 0, y: 0, width: 100, height: 20 }], ['Librarian']), null);
  assert.equal(pilotsEngine.uniqueMatch([
    { text: 'Mara', x: 0, y: 0, width: 20, height: 10 },
    { text: 'Mara', x: 0, y: 20, width: 20, height: 10 },
  ], ['Mara']), null);
});

test('preferred OCR choice follows configured priority while duplicate OCR of that choice abstains', () => {
  const rows = [
    { text: 'Cavalry Captain', x: 20, y: 80, width: 110, height: 20 },
    { text: 'Librarian', x: 20, y: 40, width: 80, height: 20 },
  ];
  assert.equal(pilotsEngine.preferredMatch(rows, ['Librarian', 'Cavalry Captain']).text, 'Librarian');
  assert.equal(pilotsEngine.preferredMatch(rows, ['Cavalry Captain', 'Librarian']).text, 'Cavalry Captain');
  assert.equal(pilotsEngine.preferredMatch([
    { text: 'Librarian', x: 20, y: 40, width: 80, height: 20 },
    { text: 'Librarian', x: 20, y: 80, width: 80, height: 20 },
    { text: 'Cavalry Captain', x: 20, y: 120, width: 110, height: 20 },
  ], ['Librarian', 'Cavalry Captain']), null);
});

test('real catalog, plans, settings, and referenced route files remain consistent', () => {
  const catalog = JSON.parse(fs.readFileSync(path.join(packageRoot, 'pilots.json'), 'utf8'));
  const plans = JSON.parse(fs.readFileSync(path.join(packageRoot, 'plans.json'), 'utf8'));
  const settings = JSON.parse(fs.readFileSync(path.join(packageRoot, 'settings.json'), 'utf8'));
  const reads = [];
  pilotsEngine.validate(catalog, plans, (route) => {
    reads.push(route);
    // The host's text reader consumes UTF-8 BOMs; Node's raw UTF-8 decoder leaves one.
    return fs.readFileSync(path.join(packageRoot, route.replaceAll('/', path.sep)), 'utf8').replace(/^\uFEFF/, '');
  });
  const pilotSetting = settings.find((setting) => setting.name === 'pilot');
  assert.ok(pilotSetting, 'settings must provide a pilot selector');
  assert.deepEqual(pilotSetting.options, plans.map((plan) => plan.title));
  assert.equal(pilotSetting.default, plans[0].title);
  assert.equal(new Set(plans.map((plan) => plan.id)).size, plans.length);
  assert.equal(plans.length, 3);
  assert.ok(reads.length > 0);
  for (const plan of plans) {
    const selected = pilotsEngine.settingsFor({ pilot: plan.title, dialogueTimeoutSeconds: 120 }, plans);
    assert.equal(selected.plan.id, plan.id);
    const definition = catalog.pilots.find((pilot) => pilot.id === plan.id);
    assert.ok(definition, `catalog definition missing for ${plan.id}`);
    for (const stage of plan.stages) {
      const routes = definition.routes.filter((route) => !route.endsWith('/process.json'));
      assert.ok(routes[stage.route], `stage ${stage.route} missing route for ${plan.id}`);
    }
  }
});

test('catalog validation accepts valid route data and rejects traversal or malformed waypoints', () => {
  const f = fixture();
  const reads = [];
  pilotsEngine.validate(f.catalog, f.plans, (path) => { reads.push(path); return routeJson; });
  assert.deepEqual(reads, [routePath]);
  const unsafe = fixture();
  unsafe.catalog.pilots[0].routes[0] = 'assets/../outside.json';
  assert.throws(() => pilotsEngine.validate(unsafe.catalog, unsafe.plans, () => routeJson), /Invalid route reference/);
  assert.throws(() => pilotsEngine.validate(f.catalog, f.plans, () => JSON.stringify({ info: {}, positions: [{ x: NaN, y: 2 }] })), /Invalid waypoint/);
});

test('settings resolve the selected plan and enforce bounded whole-second timeouts', () => {
  const f = fixture();
  const configured = pilotsEngine.settingsFor({ pilot: f.plan.title, dialogueTimeoutSeconds: 45, checkOnly: true, manualChoices: true }, f.plans);
  assert.equal(configured.plan, f.plan);
  assert.equal(configured.timeoutMs, 45000);
  assert.equal(configured.checkOnly, true);
  assert.equal(configured.manualChoices, true);
  assert.throws(() => pilotsEngine.settingsFor({ pilot: 'Unknown', dialogueTimeoutSeconds: 45 }, f.plans), /Choose one/);
  for (const invalid of [29, 301, 30.5, 'not a number']) {
    assert.throws(() => pilotsEngine.settingsFor({ pilot: f.plan.title, dialogueTimeoutSeconds: invalid }, f.plans), /whole number from 30 to 300/);
  }
});

test('check-only mode validates and returns without game input', async () => {
  const f = fixture();
  const { api, log } = makeApi();
  assert.equal(await pilotsEngine.makeRunner(api).run(f.catalog, f.plans, { ...opts, checkOnly: true }), 'checked');
  assert.deepEqual(log.keys, []);
  assert.deepEqual(log.paths, []);
  assert.equal(log.enabled, 0);
});

test('wrong resolution sends no input and starts no route', async () => {
  const f = fixture();
  const { api, log } = makeApi({ metrics: [1920, 1200] });
  await assert.rejects(pilotsEngine.makeRunner(api).run(f.catalog, f.plans, opts), /1920 x 1080/);
  assert.deepEqual(log.keys, []);
  assert.deepEqual(log.paths, []);
});

test('a stale startup completion banner cannot complete the run before route progress', async () => {
  const f = fixture({ stages: [{ route: 0, talks: 0, npcs: ['Mara'], choices: [] }] });
  const stale = [{ text: 'Commission Complete', x: 1, y: 1, width: 100, height: 15 }];
  const { api, log } = makeApi({ capture: (n) => ({
    ...hud(),
    completion: n <= 2 ? stale : n >= 4 ? stale : [],
  }) });
  assert.equal(await pilotsEngine.makeRunner(api).run(f.catalog, f.plans, opts), 'completed');
  assert.equal(log.paths.length, 1, 'the route must run before any fresh completion is accepted');
  assert.equal(log.cleared, 1);
});

test('a route exception propagates and prevents all later interaction input', async () => {
  const f = fixture();
  const { api, log } = makeApi({ capture: () => hud() });
  const routeError = new Error('route failed');
  const path = api.path;
  api.path = async (json) => { await path(json); throw routeError; };
  await assert.rejects(pilotsEngine.makeRunner(api).run(f.catalog, f.plans, opts), (error) => error === routeError);
  assert.equal(log.paths.length, 1, 'the route was attempted exactly once');
  assert.deepEqual(log.interactions, []);
  assert.deepEqual(log.clicks, []);
  assert.deepEqual(log.keys, ['VK_J', 'VK_ESCAPE']);
  assert.equal(log.cleared, 1);
});

test('wrong or unreadable active quest never starts a route', async () => {
  const f = fixture();
  const { api, log } = makeApi({ journalFound: false, capture: () => hud() });
  await assert.rejects(pilotsEngine.makeRunner(api).run(f.catalog, f.plans, opts), /No route was started/);
  assert.deepEqual(log.paths, []);
  assert.deepEqual(log.keys, ['VK_J', 'VK_ESCAPE']);
});

test('unexpected NPC prevents interaction and route progression', async () => {
  const f = fixture();
  const { api, log } = makeApi({ capture: (n) => n <= 2 ? hud() : hud([{ text: 'Unrelated person', x: 1, y: 1, width: 80, height: 15 }]) });
  await assert.rejects(pilotsEngine.makeRunner(api).run(f.catalog, f.plans, opts), /Expected NPC not visible/);
  assert.deepEqual(log.interactions, []);
  assert.equal(log.paths.length, 1);
  assert.equal(log.cleared, 1);
});

test('unrecognized dialogue choice times out without clicking or starting a later route', async () => {
  const f = fixture({ stages: [
    { route: 0, talks: 1, npcs: ['Mara'], choices: ['Tell me more'] },
    { route: 1, talks: 1, npcs: ['Mara'], choices: [] },
  ] });
  const { api, log } = makeApi({ capture: (n) => n <= 2 ? hud() : n === 3 ? hud([{ text: 'Mara', x: 1, y: 1, width: 40, height: 12 }]) : dialog([{ text: 'A different answer', x: 10, y: 50, width: 120, height: 20 }]) });
  await assert.rejects(pilotsEngine.makeRunner(api).run(f.catalog, f.plans, opts), /No later route was started/);
  assert.deepEqual(log.clicks, []);
  assert.equal(log.paths.length, 1);
  assert.equal(log.cleared, 1);
});

test('cancellation during dialogue propagates, clears dialogue mode, and sends no later input', async () => {
  const f = fixture();
  const cancellation = new Error('cancelled by user');
  let cancelled = false;
  const { api, log } = makeApi({
    capture: (n) => n <= 2 ? hud() : n === 3 ? hud([{ text: 'Mara', x: 1, y: 1, width: 40, height: 12 }]) : dialog(),
    sleep: async (ms, state) => {
      if (ms === 400 && state.captures() >= 4 && !cancelled) { cancelled = true; throw cancellation; }
    },
  });
  await assert.rejects(pilotsEngine.makeRunner(api).run(f.catalog, f.plans, opts), (e) => e === cancellation);
  assert.equal(log.enabled, 1);
  assert.equal(log.cleared, 1);
  assert.deepEqual(log.clicks, []);
  assert.equal(log.interactions.length, 1);
  assert.equal(log.paths.length, 1);
});

test('manual choice configuration never auto-selects an OCR option', async () => {
  const f = fixture();
  const raw = { ...opts, manualChoices: true };
  const { api, log } = makeApi({ capture: (n) => n <= 2 ? hud() : n === 3 ? hud([{ text: 'Mara', x: 1, y: 1, width: 40, height: 12 }]) : dialog([{ text: 'Tell me more', x: 10, y: 50, width: 120, height: 20 }]) });
  await assert.rejects(pilotsEngine.makeRunner(api).run(f.catalog, f.plans, raw), /No later route was started/);
  assert.deepEqual(log.clicks, []);
  assert.ok(log.infos.some((s) => s.includes('Waiting for a recognized answer')));
  assert.equal(log.paths.length, 1);
});

test('a complete run returns completed only after observing the completion banner', async () => {
  const f = fixture();
  let clicked = false;
  let interactionSeen = false;
  const { api, log } = makeApi({ capture: (n) => {
    if (n <= 2) return hud();
    if (n === 3) return hud([{ text: 'Mara', x: 1, y: 1, width: 40, height: 12 }]);
    if (!clicked) return dialog([{ text: 'Tell me more', x: 10, y: 50, width: 120, height: 20 }]);
    // Three stable HUD observations end the conversation; the next frame is the final banner check.
    if (n >= 8) return { ...hud(), completion: [{ text: 'Commission Complete', x: 1, y: 1, width: 100, height: 15 }] };
    return hud();
  } });
  const click = api.click;
  api.click = (match) => { clicked = true; click(match); };
  api.interact = (match) => { interactionSeen = true; log.interactions.push(match); };
  assert.equal(await pilotsEngine.makeRunner(api).run(f.catalog, f.plans, opts), 'completed');
  assert.equal(interactionSeen, true);
  assert.equal(log.clicks.length, 1);
  assert.equal(log.paths.length, 1);
  assert.equal(log.cleared, 1);
  assert.ok(log.infos.some((s) => s.includes('completion banner detected')));
});

test('route steps without a completion banner end unconfirmed', async () => {
  const f = fixture();
  let clicked = false;
  const { api, log } = makeApi({ capture: (n) => {
    if (n <= 2) return hud();
    if (n === 3) return hud([{ text: 'Mara', x: 1, y: 1, width: 40, height: 12 }]);
    if (!clicked) return dialog([{ text: 'Tell me more', x: 10, y: 50, width: 120, height: 20 }]);
    return hud();
  } });
  const click = api.click;
  api.click = (match) => { clicked = true; click(match); };
  await assert.rejects(pilotsEngine.makeRunner(api).run(f.catalog, f.plans, opts), /UNCONFIRMED/);
  assert.equal(log.cleared, 1);
  assert.equal(log.paths.length, 1);
});

test('vendored source assets retain their pinned byte hashes', () => {
  const crypto = require('node:crypto');
  const manifest = JSON.parse(fs.readFileSync(path.join(packageRoot, 'source-hashes.json'), 'utf8').replace(/^\uFEFF/, ''));
  assert.equal(manifest.files.length, 8);
  for (const entry of manifest.files) {
    const bytes = fs.readFileSync(path.join(packageRoot, entry.path));
    assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), entry.sha256, entry.path);
  }
});
