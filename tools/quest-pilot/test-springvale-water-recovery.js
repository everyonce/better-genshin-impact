const fs = require('fs');
const assert = require('assert');
const path = require('path');
const crypto = require('crypto');

const runtime = process.env.BETTERGI_PILOT_APP_DIR;
const guardFiles = ['BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'];
if (runtime) guardFiles.push(path.join(runtime, 'User/JsScript/ActOnePilot/bgi.js'));
const fixture = 'tools/quest-pilot/fixtures/act-two-springvale-swim-2162';
const recorded = JSON.parse(fs.readFileSync(`${fixture}.json`));
assert.strictEqual(crypto.createHash('sha256').update(fs.readFileSync(`${fixture}.png`)).digest('hex'),
  recorded.screenshotSha256, 'Recorded frame image changed');
for (const file of guardFiles) {
  const source = fs.readFileSync(file, 'utf8');
  const match = source.match(/function springvaleSwimMapEscape\(o\)\{[^\n]+\}/);
  assert(match, `Missing swim map recovery guard in ${file}`);
  const request = {step: 'actTwoWorldMap', session: recorded.session};
  const guard = new Function('request', `${match[0]}; return springvaleSwimMapEscape;`)(request);
  const good = structuredClone(recorded);
  good.timestamp = Date.now();
  assert(guard(good), 'Recorded swimming state should allow a safe map escape');
  const reject = (edit) => {
    const state = structuredClone(good);
    edit(state);
    assert(!guard(state), `Unsafe recovery accepted in ${file}`);
  };
  reject(s => {s.session = 'another-session';});
  reject(s => {s.hud.starfellSwim.confirmed = false;});
  reject(s => {s.hud.groundControls = true;});
  reject(s => {s.hud.health.current = 3000;});
  reject(s => {s.hud.enemyBars = [{x: 900}];});
  reject(s => {s.map.cameraAngle = 100;});
  reject(s => {s.map.x = -900;});
  reject(s => {s.timestamp = Date.now() - 2000;});
}
console.log(`Springvale recorded swim recovery: ${guardFiles.length} positive, ${8*guardFiles.length} negative checks passed`);
