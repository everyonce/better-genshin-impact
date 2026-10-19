// Append-only archive for small, unresolved BetterGI image/JSON evidence sets.
// Does not alter rolling runtime retention or delete files.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = process.env.BETTERGI_PILOT_APP_DIR
  ? path.join(process.env.BETTERGI_PILOT_APP_DIR, 'User', 'JsScript', 'ActOnePilot')
  : path.resolve('artifacts/release-r18/BetterGI-English-win-x64/User/JsScript/ActOnePilot');
const destination = path.resolve('artifacts/act-two-critical-captures-20261019');
const session = process.argv[2], frames = process.argv.slice(3).map(Number);
if (!/^[A-Za-z0-9_-]+$/.test(session || '') || !frames.length || frames.some(n => !Number.isInteger(n) || n < 0 || n > 9999)) {
  throw Error('Usage: node archive-critical-captures.cjs SESSION FRAME [FRAME...]');
}
const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
fs.mkdirSync(destination, {recursive: true});
const manifestPath = path.join(destination, 'manifest.json');
const manifest = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) : {schemaVersion: 1, entries: {}};
const entries = manifest.entries, proposed = new Map();
for (const frame of frames) for (const ext of ['png', 'json']) {
  const name = `frame-${String(frame).padStart(4, '0')}.${ext}`;
  const key = `${session}/${name}`, source = path.join(root, 'observations', session, name);
  if (!fs.statSync(source).isFile()) throw Error(`Missing capture: ${source}`);
  proposed.set(key, {source, sha256: hash(source), bytes: fs.statSync(source).size});
}
const imageKeys = new Set([...Object.keys(entries), ...proposed.keys()].filter(k => k.endsWith('.png')));
const imageBytes = [...imageKeys].reduce((n, k) => n + (proposed.get(k) || entries[k]).bytes, 0);
if (imageKeys.size > 24 || imageBytes > 80 * 1024 * 1024) throw Error('Critical capture archive budget exceeded');
const newBytes = [...proposed].reduce((n, [k, v]) => n + (entries[k] ? 0 : v.bytes), 0);
const space = fs.statfsSync(destination);
if (space.bavail * space.bsize - newBytes < 2 * 1024 ** 3) throw Error('Critical archive would violate free-space floor');
for (const [key, value] of proposed) {
  const target = path.join(destination, ...key.split('/'));
  if (entries[key] && (entries[key].sha256 !== value.sha256 || entries[key].bytes !== value.bytes)) throw Error(`Evidence changed: ${key}`);
  if (fs.existsSync(target)) {
    if (hash(target) !== value.sha256) throw Error(`Archive changed: ${key}`);
  } else {
    fs.mkdirSync(path.dirname(target), {recursive: true});
    fs.copyFileSync(value.source, target, fs.constants.COPYFILE_EXCL);
    if (hash(target) !== value.sha256) throw Error(`Archive verification failed: ${key}`);
  }
  if (!entries[key]) entries[key] = {...value, archivedUtc: new Date().toISOString()};
}
const temporary = `${manifestPath}.tmp`;
fs.writeFileSync(temporary, JSON.stringify(manifest, null, 2));
fs.renameSync(temporary, manifestPath);
console.log(JSON.stringify({manifest: manifestPath, images: imageKeys.size, imageBytes, entries: Object.keys(entries).length}));
