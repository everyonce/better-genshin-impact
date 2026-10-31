"""Inert northern-scope regressions; fake policies and native evidence never open a live bridge."""
import copy
from contextlib import redirect_stderr
from dataclasses import FrozenInstanceError
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import audit_hybrid_run as audit
import audit_scout_obstacle as obstacle
import navigation_profiles as profiles
import resident_runtime as runtime
import scout_session as scout
from hybrid_navigation import END, START, HybridNavigation
from hybrid_routes import ROUTE_IDS, SCOUT_GRASS_ROUTE, route_heading
from reviewed_scout_route import ReviewedScoutRoute, reviewed_route_policy
from scout_encounter_guard import binding_from_review, guard_policy
import test_audit_hybrid_run as audit_fixtures
import test_audit_scout_obstacle as obstacle_fixtures
from test_hybrid_navigation import frame, proposal
from test_navigation_profiles import route_capability
import test_scout_session as session_fixtures


NORTH = profiles.NORTH_SCOUT_PROFILE


def north_capability():
    """Mirror the separately named native contract without changing the old capability fixture."""
    value = route_capability(SCOUT_GRASS_ROUTE)
    value.update(profileId=NORTH, bounds=dict(profiles.NORTH_SCOUT_BOUNDS),
                 searchAnchor=dict(profiles.NORTH_SCOUT_ANCHOR))
    return value


def north_route():
    """Use a short directed route at the verified northern Statue, outside the old scout rectangle."""
    return ReviewedScoutRoute(((-1323.474, 2566.115), (-1326, 2572)), NORTH)


def observation(index, route, point=None):
    """Keep the real original-anchor bearings and exact same-frame pose identity."""
    point = point or route.points[0]
    position = dict(x=point[0], y=point[1])
    value = frame(index, index * 100, point=point, yaw=route_heading(position, route.points[1]))
    value['navigationPose'].update(layerId='MapBack_2',
        headingToStartDegrees=int(route_heading(position, START)),
        headingToEndDegrees=int(route_heading(position, END)))
    return value


class NorthScopeTests(unittest.TestCase):
    """Explicit scope changes neither original geometry nor native admission requirements."""

    def test_exact_translation_detached_contracts_and_old_scope_isolation(self):
        """The camp overlaps both scopes; the northern Statue requires the new profile explicitly."""
        bounds, anchor = profiles.scout_scope(NORTH)
        self.assertEqual(bounds, dict(minX=-1500, maxX=-1130, minY=2430, maxY=2860))
        self.assertEqual(anchor, dict(x=-1315, y=2645))
        old_bounds, old_anchor = profiles.scout_scope(profiles.SCOUT_PROFILE)
        for key in bounds:
            self.assertEqual(bounds[key] - old_bounds[key], -150 if key.endswith('X') else 380)
        self.assertEqual((anchor['x']-old_anchor['x'], anchor['y']-old_anchor['y']), (-150, 380))
        bounds['minX'] = -9999
        anchor['x'] = 0
        self.assertEqual(profiles.scout_scope(NORTH)[0]['minX'], -1500)
        self.assertEqual(profiles.scout_scope(NORTH)[1]['x'], -1315)
        for x, y, north, old in ((-1261.02734375, 2444.220703125, True, True),
                                (-1323.474, 2566.115, True, False), (-1165, 2265, False, True)):
            pose = dict(x=x, y=y, layerId='MapBack_2')
            self.assertEqual(profiles.allows_pose_scope(pose, NORTH), north)
            self.assertEqual(profiles.allows_pose_scope(pose, profiles.SCOUT_PROFILE), old)
            self.assertFalse(profiles.allows_pose_scope(pose, profiles.SURFACE_PROFILE))
            self.assertFalse(profiles.allows_pose_scope(pose, profiles.COURTYARD_PROFILE))

    def test_north_corners_layers_and_nonfinite_coordinates_remain_bounded(self):
        """Both allowed layers accept exact corners and refuse every just-outside edge."""
        for x in (-1500, -1130):
            for y in (2430, 2860):
                for layer in profiles.SURFACE_LAYERS:
                    self.assertTrue(profiles.allows_pose_scope(dict(x=x, y=y, layerId=layer), NORTH))
        for change in (dict(x=-1500.01), dict(x=-1129.99), dict(y=2429.99), dict(y=2860.01),
                       dict(x=float('nan')), dict(y=float('inf')), dict(x=True), dict(y='2645'),
                       dict(layerId='MapBack_1'), dict(layerId='City_103'), dict(layerId=None)):
            with self.subTest(change=change):
                self.assertFalse(profiles.allows_pose_scope(dict(x=-1315, y=2645, layerId='MapBack_2') | change, NORTH))

    def test_native_capability_requires_exact_profile_bounds_anchor_and_thresholds(self):
        """A label alone cannot substitute an older anchor or weaker recognition contract."""
        profiles.validate_capability(north_capability(), NORTH)
        for change in (dict(profileId=profiles.SCOUT_PROFILE), dict(bounds=dict(profiles.SCOUT_BOUNDS)),
                       dict(searchAnchor=dict(profiles.SCOUT_ANCHOR)), dict(localOnly=False),
                       dict(bounds=dict(profiles.NORTH_SCOUT_BOUNDS, maxY=2861)),
                       dict(minimumPositionConfidence=.98), dict(minimumYawConfidence=.19),
                       dict(allowedLayerIds=['MapBack_2']), dict(readOnly=False), dict(sameFrame=False),
                       dict(start=dict(x=-1315, y=2645))):
            with self.subTest(change=change), self.assertRaises(ValueError):
                profiles.validate_capability(north_capability() | change, NORTH)
        with self.assertRaises(ValueError):
            profiles.validate_capability(north_capability(), profiles.SCOUT_PROFILE)

    def test_no_fixed_route_can_implicitly_select_northern_localization(self):
        """The existing route registry remains untouched and cannot use the new scope as an upgrade."""
        for route_id in ROUTE_IDS:
            self.assertNotEqual(profiles.required_profile(route_id), NORTH)
            with self.subTest(route_id=route_id), self.assertRaises(ValueError):
                HybridNavigation(north_capability(), route_id, navigation_profile=NORTH)

    def test_review_hash_binds_profile_direction_and_immutable_geometry(self):
        """Identical overlapping coordinates still produce different identities under different scopes."""
        points = [[-1261, 2444], [-1267, 2448]]
        route = ReviewedScoutRoute(points, NORTH)
        old = ReviewedScoutRoute(points, profiles.SCOUT_PROFILE)
        expected = hashlib.sha256(json.dumps(route.document(), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(route.sha256, expected)
        self.assertEqual(ReviewedScoutRoute.from_document(route.document()), route)
        self.assertNotEqual(route.sha256, old.sha256)
        self.assertNotEqual(route.route_id, old.route_id)
        self.assertNotEqual(ReviewedScoutRoute(tuple(reversed(route.points)), NORTH).sha256, route.sha256)
        points[1][0] = -1280
        detached = route.document()
        detached['points'][1][0] = -1280
        self.assertEqual(route.points[1], (-1267, 2448))
        with self.assertRaises(FrozenInstanceError):
            route.profile_id = profiles.SCOUT_PROFILE
        for invalid in (dict(route.document(), profileId='unknown'), dict(route.document(), version=True),
                        dict(route.document(), extraDestination=[-1270, 2448])):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                ReviewedScoutRoute.from_document(invalid)

    def test_northern_review_is_two_points_with_the_unchanged_forty_unit_limit(self):
        """The new rectangle does not grant longer legs or rescue old-scope coordinates."""
        self.assertEqual(ReviewedScoutRoute(((-1315, 2645), (-1315, 2685)), NORTH).points[1], (-1315, 2685))
        for points in (((-1315, 2645), (-1315, 2685.01)), ((-1315, 2645), (-1315, 2645)),
                       ((-1500.01, 2645), (-1499, 2645)), ((-1131, 2645), (-1129.99, 2645)),
                       ((-1315, 2429.99), (-1315, 2431)), ((-1315, 2859), (-1315, 2860.01)),
                       ((-1165, 2265), (-1166, 2265)), ((-1315, 2645), (float('nan'), 2646))):
            with self.subTest(points=points), self.assertRaises(ValueError):
                ReviewedScoutRoute(points, NORTH)
        with self.assertRaises(ValueError):
            ReviewedScoutRoute(north_route().points)

    def test_controller_requires_matching_review_and_fresh_directed_start(self):
        """Only the reviewed northern start can arm the unchanged native navigation controller."""
        route = north_route()
        nav = HybridNavigation(north_capability(), route.route_id, navigation_profile=NORTH, reviewed_scout_route=route)
        for index in (1, 2, 3):
            nav.prepare(observation(index, route))
        self.assertEqual(nav.phase, 'walking')
        self.assertEqual(nav.snapshot()['routeSpecSha256'], route.sha256)
        self.assertEqual(nav.choose(observation(3, route), proposal(['W']))['step']['keys'], ['W'])
        wrong_start = HybridNavigation(north_capability(), route.route_id, navigation_profile=NORTH, reviewed_scout_route=route)
        with self.assertRaises(RuntimeError):
            wrong_start.prepare(observation(1, route, route.points[1]))
        old = ReviewedScoutRoute(((-1261, 2444), (-1267, 2448)))
        with self.assertRaises(ValueError):
            HybridNavigation(north_capability(), old.route_id, navigation_profile=NORTH, reviewed_scout_route=old)
        for change in (dict(remember_bypass=True), dict(itinerary_destinations=['unreviewed'])):
            with self.subTest(change=change), self.assertRaises(ValueError):
                HybridNavigation(north_capability(), route.route_id, navigation_profile=NORTH, reviewed_scout_route=route, **change)

    def test_cli_requires_explicit_reviewed_only_north_worker_selection(self):
        """Selecting north never silently enables inherited fixed routes or changes time/storage limits."""
        base = ['run', '--directory', 'unused', '--owner-from', 'owner.json', '--navigation-profile', NORTH]
        for extra in ([], ['--allow-reviewed-routes', '--route', SCOUT_GRASS_ROUTE]):
            with redirect_stderr(io.StringIO()), self.subTest(extra=extra), self.assertRaises(SystemExit):
                scout.options(base + extra)
        args = scout.options(base + ['--allow-reviewed-routes'])
        self.assertEqual((args.navigation_profile, args.routes, args.seconds, args.record_max_mib), (NORTH, None, 600, 160))
        self.assertFalse(args.allow_inspected_obstacle_recovery)


class NorthWorkerTests(unittest.TestCase):
    """Exercise real resident/session admission with only existing GPU and native boundaries replaced."""

    def setUp(self):
        """Reuse the inert session harness without importing its test cases into this module's suite."""
        self.fixture = fixture = session_fixtures.ScoutSessionTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.settings.navigation_profile = NORTH
        fixture.settings.allow_reviewed_routes = True
        fixture.reviewed_routes = [north_route(), ReviewedScoutRoute((north_route().points[1], (-1333, 2577)), NORTH)]
        original = fixture.make_review

        def reviewed_scene(route_id, spec=None):
            """Declare the actual selected native scope in the otherwise unchanged source fixture."""
            path = original(route_id, spec)
            review = json.loads(path.read_bytes())
            plan_path = Path(review['nativeEndpoint']) / 'plan.json'
            plan = json.loads(plan_path.read_bytes())
            plan['navigationProfile'] = NORTH
            session_fixtures.write_json(plan_path, plan)
            return path

        fixture.make_review = reviewed_scene

    def manifest(self):
        """Construct the minimal immutable north review authority, with no registered fixed route."""
        return dict(owner=self.fixture.owner, routes={}, navigationProfile=NORTH,
                    reviewedScoutRoutePolicy=reviewed_route_policy(NORTH),
                    sessionId='c'*32, modelConfigurationSha256='f'*64)

    def test_idle_bootstrap_loads_once_without_a_request_or_native_lease(self):
        """Loader-only startup must not require live request authority or submit its bootstrap geometry."""
        fixture = self.fixture
        fixture.target = 0
        state = fixture.run_worker()
        manifest = json.loads((fixture.settings.directory / 'manifest.json').read_bytes())
        self.assertEqual((state['state'], state['modelLoads'], state['legs'], state['seenRequestIds']), ('stopped', 1, [], []))
        self.assertEqual((fixture.starts, fixture.episodes), ([], []))
        self.assertEqual(manifest['routes'], {})
        self.assertEqual(manifest['navigationProfile'], NORTH)
        self.assertEqual(manifest['reviewedScoutRoutePolicy'], reviewed_route_policy(NORTH))
        self.assertEqual(fixture.loads[0].navigation_profile, NORTH)
        self.assertNotIn(fixture.loads[0].hybrid_route, ROUTE_IDS)
        self.assertEqual((manifest['legDeadlineSeconds'], manifest['sourceFreshnessMs'], manifest['actionHoldMs'],
                          manifest['stopTemperatureC']), (35, 150, 100, 78))
        self.assertTrue(fixture.watch.closed)

    def test_bootstrap_failures_retire_the_created_watch_without_loading_or_leasing(self):
        """Parser exits and configuration failures cannot leave the original identity monitor running."""
        fixture = self.fixture
        for stage, error in (('leg_arguments', SystemExit(2)), ('model_contract', RuntimeError('synthetic configuration failure'))):
            fixture.settings.directory = fixture.live / ('bootstrap-failure-' + stage)
            fixture.watch = None
            with self.subTest(stage=stage), patch.object(scout, stage, side_effect=error) as fault:
                try:
                    code = scout.run_session(fixture.settings, lifecycle=fixture.lifecycle, loader=fixture.load,
                        watch_factory=fixture.make_watch, auditor=fixture.audit)
                    self.assertNotEqual(code, 0)
                except (SystemExit, RuntimeError) as actual:
                    self.assertIs(actual, error)
                fault.assert_called_once()
            self.assertIsNotNone(fixture.watch)
            self.assertTrue(fixture.watch.closed)
            self.assertIsNone(fixture.watch.active)
            self.assertEqual((fixture.loads, fixture.starts, fixture.episodes), ([], [], []))

    def test_two_explicit_north_reviews_reuse_weights_with_fresh_guards_and_leases(self):
        """A bootstrap is never counted as a leg; every actual resident binds the consumed north review."""
        fixture = self.fixture
        controls = []
        fixture.after_episode = lambda number, control: controls.append(control)
        state = fixture.run_worker()
        self.assertEqual([row['state'] for row in state['legs']], ['verified', 'verified'])
        self.assertEqual((len(fixture.loads), len(fixture.starts), len(fixture.audits)), (1, 2, 2))
        self.assertEqual(len({episode[3] for episode in fixture.episodes}), 2)
        self.assertIsNot(controls[0].scout_encounter_guard, controls[1].scout_encounter_guard)
        for episode, report, spec in zip(fixture.episodes, fixture.audits, fixture.reviewed_routes):
            args = episode[0]
            self.assertEqual(args.navigation_profile, NORTH)
            self.assertEqual(args.reviewed_scout_route, spec)
            self.assertEqual(report['policyReuse']['navigationProfile'], NORTH)
            self.assertEqual(report['policyReuse']['routeSpecSha256'], spec.sha256)
            self.assertEqual((report['modelLoads'], report['modelLoadSeconds']), (0, 0))
        self.assertEqual(len(state['seenRequestIds']), 2)
        self.assertTrue(fixture.watch.closed)

    def test_north_review_cannot_borrow_old_manifest_policy_or_fixed_routes(self):
        """Absence or partial alteration of explicit northern startup authority fails closed."""
        manifest = self.manifest()
        self.assertEqual(scout.session_profile(manifest), NORTH)
        for change in (dict(reviewedScoutRoutePolicy=reviewed_route_policy()),
                       dict(reviewedScoutRoutePolicy=None), dict(routes={SCOUT_GRASS_ROUTE: [[0, 0], [1, 1]]})):
            with self.subTest(change=change), self.assertRaises(ValueError):
                scout.session_profile(manifest | change)

    def test_review_request_and_native_source_must_all_keep_the_north_scope(self):
        """Scope substitutions are rejected even when the request, geometry and owner otherwise match."""
        fixture = self.fixture
        spec = north_route()
        path = fixture.make_review(spec.route_id, spec)
        manifest = self.manifest()
        evidence = scout.review_evidence(path, manifest, 0)
        request = dict(version=1, sessionId=manifest['sessionId'], requestId='d'*32, afterRequestId=None,
            modelConfigurationSha256='f'*64, navigationProfile=NORTH, maximumLegs=1, reviewFile=str(path), **evidence)
        request_path = fixture.live / ('d'*32 + '.json')
        session_fixtures.write_json(request_path, request)
        self.assertEqual(scout.validate_request(request_path, manifest, None, 0)[0], request)
        for change in (dict(navigationProfile=profiles.SCOUT_PROFILE), dict(routeSpecSha256='0'*64),
                       dict(routeId=SCOUT_GRASS_ROUTE), dict(maximumLegs=2)):
            session_fixtures.write_json(request_path, request | change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                scout.validate_request(request_path, manifest, None, 0)
        review = json.loads(path.read_bytes())
        plan_path = Path(review['nativeEndpoint']) / 'plan.json'
        plan = json.loads(plan_path.read_bytes())
        session_fixtures.write_json(plan_path, plan | dict(navigationProfile=profiles.SCOUT_PROFILE))
        with self.assertRaisesRegex(ValueError, 'another owner or input scope'):
            scout.review_evidence(path, manifest, 0)

    def test_standalone_north_geometry_cannot_load_or_open_a_lease(self):
        """The new scope preserves the cached-request requirement at the actual resident boundary."""
        fixture = self.fixture
        spec = north_route()
        folder = fixture.live / 'standalone'
        watch = session_fixtures.FakeWatch(folder, fixture.settings, fixture.owner, fixture.lifecycle)
        args = scout.leg_arguments(fixture.settings, fixture.owner, spec.route_id, folder, watch.binding(), 160, spec)
        with self.assertRaisesRegex(ValueError, 'cached-session request'):
            runtime.run_resident(args, fixture.load, fixture.episode)
        self.assertEqual((fixture.loads, fixture.starts, fixture.episodes), ([], [], []))

    def test_one_inspected_north_obstacle_keeps_failed_leg_and_creates_new_guard(self):
        """Only lifecycle proof is substituted; scope, fresh review and real resident controls remain enforced."""
        fixture = self.fixture
        fixture.prepare_obstacle_worker()
        fixture.driver = lambda watch: self.recovery_driver(watch)
        controls = []
        fixture.after_episode = lambda number, control: controls.append(control)
        state = fixture.run_worker(prefix_auditor=fixture.synthetic_prefix_audit)
        self.assertEqual([row['state'] for row in state['legs']], ['failed', 'verified'])
        self.assertEqual((len(fixture.loads), len(fixture.starts), state['inspectedObstacleRecoveriesUsed']), (1, 2, 1))
        self.assertIsNot(controls[0].scout_encounter_guard, controls[1].scout_encounter_guard)
        self.assertFalse(state['legs'][0]['evidenceComplete'])
        self.assertEqual(state['legs'][0]['failedLeases'], 1)
        self.assertIsNone(state['pendingObstacleRecovery'])
        reuse = fixture.audits[0]['policyReuse']
        self.assertEqual(reuse['navigationProfile'], NORTH)
        self.assertEqual(reuse['obstacleRecovery']['failedRequestId'], state['legs'][0]['requestId'])

    def recovery_driver(self, watch):
        """Submit a wholly new explicit north review only after the retained failed boundary is published."""
        fixture = self.fixture
        state = json.loads((watch.folder / 'session.json').read_bytes())
        if state['state'] != 'awaitingReview':
            return
        if len(state['legs']) >= fixture.target:
            watch.reason = 'operatorStop'
            return
        if any(path.stem not in state['seenRequestIds'] for path in (watch.folder / 'requests').glob('*.json')):
            return
        number = len(state['legs'])
        fixture.episode_error = scout.OBSTACLE_ERROR if number == 0 else None
        spec = fixture.reviewed_routes[number]
        scout.submit(watch.folder, fixture.make_review(spec.route_id, spec))


class NorthAuditTests(unittest.TestCase):
    """Independent replay reopens original native scope and cached-session declarations."""

    def setUp(self):
        """Own only synthetic JSON/image artifacts in a temporary directory."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def proof(self, name):
        """Adapt the historical proof fixture to an explicitly northern reviewed-only worker."""
        write = audit_fixtures.CachedPolicyAuditTests.write
        run_path = self.root / name / 'session/legs' / ('e'*32) / 'patrol.json'
        run = {}
        proof_path, reuse = audit_fixtures.CachedPolicyAuditTests.proof(run_path, run,
            settings_changes=dict(native_combat_observation=True), reviewed_scout_route=north_route())
        for path in (Path(reuse['sessionProof']), Path(reuse['sessionProof']).parent / 'manifest.json'):
            document = json.loads(path.read_bytes())
            document.update(navigationProfile=NORTH, routes={}, reviewedScoutRoutePolicy=reviewed_route_policy(NORTH),
                            scoutEncounterGuardPolicy=guard_policy())
            write(path, document)
        request_path = Path(reuse['requestFile'])
        request = json.loads(request_path.read_bytes())
        review = json.loads(Path(request['reviewFile']).read_bytes())
        plan_path = Path(review['nativeEndpoint']) / 'plan.json'
        plan = json.loads(plan_path.read_bytes())
        binding = binding_from_review(review, request['reviewSha256'])
        request.update(navigationProfile=NORTH, nativePlanSha256=write(plan_path, plan | dict(navigationProfile=NORTH)),
                       scoutEncounterGuard=binding)
        reuse.update(navigationProfile=NORTH, scoutEncounterGuard=binding, requestSha256=write(request_path, request),
                     sessionProofSha256=hashlib.sha256(Path(reuse['sessionProof']).read_bytes()).hexdigest())
        run.update(policyReuse=copy.deepcopy(reuse), policyReuseSha256=write(proof_path, reuse), scoutEncounterGuard=binding)
        return run_path, run, proof_path, reuse, request

    def test_cached_north_proof_binds_original_manifest_and_native_review_scope(self):
        """Rehashing a substitution cannot silently restore old-scope or fixed-route semantics."""
        write = audit_fixtures.CachedPolicyAuditTests.write
        run_path, run, proof_path, reuse, _ = self.proof('valid')
        self.assertEqual(audit.verify_policy_reuse(run, run_path, proof_path)['navigationProfile'], NORTH)
        for name in ('manifest_profile', 'manifest_routes', 'manifest_policy', 'session_profile', 'request_profile',
                     'native_profile', 'native_source'):
            run_path, run, proof_path, reuse, request = self.proof(name)
            if name.startswith('manifest'):
                path = Path(reuse['sessionProof']).parent / 'manifest.json'
                document = json.loads(path.read_bytes())
                if name == 'manifest_profile':
                    document['navigationProfile'] = profiles.SCOUT_PROFILE
                elif name == 'manifest_routes':
                    document['routes'] = {SCOUT_GRASS_ROUTE: [[0, 0], [1, 1]]}
                else:
                    document.pop('reviewedScoutRoutePolicy')
                write(path, document)
            elif name == 'session_profile':
                path = Path(reuse['sessionProof'])
                document = json.loads(path.read_bytes())
                document.pop('navigationProfile')
                reuse['sessionProofSha256'] = write(path, document)
            elif name == 'request_profile':
                request['navigationProfile'] = profiles.SCOUT_PROFILE
                reuse['requestSha256'] = write(Path(reuse['requestFile']), request)
            elif name == 'native_profile':
                review = json.loads(Path(request['reviewFile']).read_bytes())
                path = Path(review['nativeEndpoint']) / 'plan.json'
                document = json.loads(path.read_bytes())
                document['navigationProfile'] = profiles.SCOUT_PROFILE
                request['nativePlanSha256'] = write(path, document)
                reuse['requestSha256'] = write(Path(reuse['requestFile']), request)
            else:
                review = json.loads(Path(request['reviewFile']).read_bytes())
                path = Path(review['nativeEndpoint']) / Path(review['imageName']).with_suffix('.json')
                document = json.loads(path.read_bytes())
                document['sourceFrame']['timestamp100ns'] += 1
                request['imageMetadataSha256'] = write(path, document)
                reuse['requestSha256'] = write(Path(reuse['requestFile']), request)
            run.update(policyReuse=copy.deepcopy(reuse), policyReuseSha256=write(proof_path, reuse))
            with self.subTest(name=name), self.assertRaises(ValueError):
                audit.verify_policy_reuse(run, run_path, proof_path)

    def test_new_north_scope_cannot_claim_historical_unguarded_semantics(self):
        """Removing every derived guard marker cannot turn a newly introduced scope into an old recording."""
        write = audit_fixtures.CachedPolicyAuditTests.write
        run_path, run, proof_path, reuse, request = self.proof('guard-downgrade')
        for path in (Path(reuse['sessionProof']), Path(reuse['sessionProof']).parent / 'manifest.json'):
            document = json.loads(path.read_bytes())
            document.pop('scoutEncounterGuardPolicy')
            write(path, document)
        request.pop('scoutEncounterGuard')
        reuse.pop('scoutEncounterGuard')
        run.pop('scoutEncounterGuard')
        reuse['requestSha256'] = write(Path(reuse['requestFile']), request)
        reuse['sessionProofSha256'] = hashlib.sha256(Path(reuse['sessionProof']).read_bytes()).hexdigest()
        run.update(policyReuse=copy.deepcopy(reuse), policyReuseSha256=write(proof_path, reuse))
        with self.assertRaisesRegex(ValueError, 'Northern cached scouting'):
            audit.verify_policy_reuse(run, run_path, proof_path)

    def test_retained_original_worker_cannot_switch_scope_in_its_successor_review(self):
        """A complete original-prefix proof does not authorize a differently scoped recovery request."""
        write = obstacle_fixtures.write
        folder, original, run, _, _, _ = obstacle_fixtures.fixture(self.root)
        prefix = obstacle.audit_failed_prefix(folder, original)
        audit_path = folder / 'failed-prefix-audit.json'
        prefix_sha = write(audit_path, prefix)
        owner = run['policyReuse']['owner']
        spec = north_route()
        evidence = audit_fixtures.CachedPolicyAuditTests.reviewed_scene(folder.parent.parent / 'successor',
            owner, spec.route_id, spec.points, spec)
        review = json.loads(Path(evidence['reviewFile']).read_bytes())
        plan_path = Path(review['nativeEndpoint']) / 'plan.json'
        plan = json.loads(plan_path.read_bytes())
        evidence['nativePlanSha256'] = write(plan_path, plan | dict(navigationProfile=NORTH))
        witness = dict(failedRequestId=original['requestId'], failedRunId=run['runId'], failedRouteId=original['routeId'],
            failedReviewSha256=original['reviewSha256'], failedManifestSha256=prefix['residentManifestSha256'],
            failedRoutePoints=[list(point) for point in scout.route_points(original['routeId'])],
            prefixAuditFile=str(audit_path), prefixAuditSha256=prefix_sha, cleanupAtUnixNs=1,
            cleanupAtMonotonicNs=90_000_000, owner=owner, originalOwnerIdleMinimizedAfter=True,
            residentControlRetired=True, newPythonThreadsAlive=[], retainedState='policy-weights-and-immutable-configuration-only')
        request = dict(original, **evidence, requestId='f'*32, afterRequestId=original['requestId'], routeId=spec.route_id,
            navigationProfile=NORTH, routeSpec=spec.document(), routeSpecSha256=spec.sha256, obstacleRecovery=witness)
        request['scoutEncounterGuard'] = binding_from_review(review, request['reviewSha256'])
        with self.assertRaisesRegex(ValueError, 'scope|profile'):
            obstacle.verify_recovery_request(request, witness, owner)


if __name__ == '__main__':
    unittest.main()
