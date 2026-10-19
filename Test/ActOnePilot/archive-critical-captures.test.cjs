const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');

test('critical capture archive is hashed, idempotent and refuses changed evidence', () => {
  const temp = fs.mkdtempSync(path.join(path.resolve('artifacts'), 'critical-capture-test-'));
    const app = path.join(temp, 'app');
    const source = path.join(app, 'User', 'JsScript', 'ActOnePilot', 'observations', 'session1');
    fs.mkdirSync(source, {recursive: true});
    fs.writeFileSync(path.join(source, 'frame-0001.png'), Buffer.from([1, 2, 3]));
    fs.writeFileSync(path.join(source, 'frame-0001.json'), '{"frameId":1}');
    const script = path.resolve(__dirname, '../../tools/quest-pilot/archive-critical-captures.cjs');
    const run = () => spawnSync(process.execPath, [script, 'session1', '1'], {
      cwd: temp, env: {...process.env, BETTERGI_PILOT_APP_DIR: app}, encoding: 'utf8'
    });
    const first = run();
    assert.equal(first.status, 0, first.stderr);
    const manifestPath = path.join(temp, 'artifacts', 'act-two-critical-captures-20261019', 'manifest.json');
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    assert.equal(Object.keys(manifest.entries).length, 2);
    assert.match(manifest.entries['session1/frame-0001.png'].sha256, /^[0-9a-f]{64}$/);
    assert.equal(run().status, 0);
    assert.deepEqual(JSON.parse(fs.readFileSync(manifestPath, 'utf8')), manifest);
    fs.writeFileSync(path.join(source, 'frame-0001.png'), Buffer.from([4, 5, 6]));
    const refused = run();
    assert.notEqual(refused.status, 0);
    assert.match(refused.stderr, /Evidence changed/);
    assert.deepEqual(fs.readFileSync(path.join(temp, 'artifacts', 'act-two-critical-captures-20261019', 'session1', 'frame-0001.png')), Buffer.from([1, 2, 3]));
});
