const test = require('node:test');
const assert = require('node:assert/strict');
const bgi = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');

const request = { mission: 'navigation', waypoints: [{ map: 'Teyvat', x: -1122.173, y: 2197.455 }] };

test('first navigation map match is locally seeded from the first approved waypoint and capped at 150m', () => {
  assert.deepEqual(bgi.navigationMapAnchor(request, null), {
    x: -1122.173, y: 2197.455, maxDistance: 150, source: 'firstWaypoint',
  });
  assert.deepEqual(bgi.acceptNavigationPosition(request, null, { x: -1000, y: 2200 }), {
    x: -1000, y: 2200, map: 'Teyvat',
  });
  assert.equal(bgi.acceptNavigationPosition(request, null, { x: 4918.1777, y: 4129 }), null);
  assert.equal(bgi.acceptNavigationPosition(request, null, { x: -1122.173, y: Infinity }), null);
});

test('later local map matches anchor to the last accepted position and reject jumps over 25m', () => {
  const accepted = { x: -1120, y: 2195 };
  assert.deepEqual(bgi.navigationMapAnchor(request, accepted), {
    x: -1120, y: 2195, maxDistance: 25, source: 'lastAccepted',
  });
  assert.deepEqual(bgi.acceptNavigationPosition(request, accepted, { x: -1140, y: 2200 }), {
    x: -1140, y: 2200, map: 'Teyvat',
  });
  assert.equal(bgi.acceptNavigationPosition(request, accepted, { x: -1120, y: 2220.01 }), null);
  assert.equal(bgi.acceptNavigationPosition(request, accepted, { x: 4918.1777, y: 4129 }), null);
});

test('non-navigation missions do not acquire a local map anchor', () => {
  assert.equal(bgi.navigationMapAnchor({ mission: 'questStep', waypoints: request.waypoints }, null), null);
  assert.equal(bgi.acceptNavigationPosition({ mission: 'questStep', waypoints: request.waypoints }, null, { x: 0, y: 0 }), null);
});
