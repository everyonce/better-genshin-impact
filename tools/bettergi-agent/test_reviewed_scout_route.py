"""CPU-only reviewed geometry admission and controller tests; no bridge, GPU or game input."""
import copy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from hybrid_navigation import END,START,HybridNavigation
from hybrid_routes import SCOUT_GRASS_ROUTE,route_heading
from navigation_profiles import SCOUT_PROFILE
from reviewed_scout_route import (CURRENT_SCENE_INSPECTION,ReviewedScoutRoute,load_reviewed_route,
                                  require_navigation_review_scene,validate_reviewed_options)
from test_hybrid_navigation import frame,proposal
from test_navigation_profiles import route_capability


class ReviewedScoutRouteTests(unittest.TestCase):
    """Reject destination/scope substitutions while preserving the original native controller guards."""
    def route(self):
        """Use an explicit short southeast candidate entirely within the existing scout scope."""
        return ReviewedScoutRoute(((-1135,2267),(-1142,2255)))

    def test_current_scene_markers_cannot_be_reused_for_navigation(self):
        """Either retained document rejects inspection authority, including a backfilled anchor."""
        historical=dict(owner={},enableInput=False,modelLoaded=False)
        require_navigation_review_scene(historical,{})
        anchored=dict(historical,captureHelperSha256='a'*64,anchor=[-1135,2267])
        require_navigation_review_scene(anchored,{})
        for marker in (dict(inspectionMode=CURRENT_SCENE_INSPECTION),dict(navigationReviewAllowed=False),
                       dict(inspectionMode=None),dict(navigationReviewAllowed=1)):
            for document in ('plan','result'):
                plan,result=copy.deepcopy(anchored),{}
                (plan if document=='plan' else result).update(marker)
                with self.subTest(document=document,marker=marker),self.assertRaisesRegex(ValueError,'cannot authorize'):
                    require_navigation_review_scene(plan,result)

    def test_stripped_inspection_markers_still_need_a_modern_capture_anchor(self):
        """A current helper's remaining source-hash declaration cannot masquerade as an old anchorless plan."""
        for anchor in (None,[],[0],[-1135,float('nan')],[True,2267],['-1135',2267]):
            with self.subTest(anchor=anchor),self.assertRaisesRegex(ValueError,'fixed anchor'):
                require_navigation_review_scene(dict(captureHelperSha256='a'*64,anchor=anchor),{})

    def observation(self,index,point=None):
        """Supply native headings to original anchors, as the real SCOUT capability requires."""
        route=self.route()
        point=point or route.points[0]
        pose=dict(x=point[0],y=point[1])
        row=frame(index,index*100,point=point,yaw=route_heading(pose,route.points[1]))
        row['navigationPose'].update(layerId='MapBack_2',headingToStartDegrees=int(route_heading(pose,START)),
                                     headingToEndDegrees=int(route_heading(pose,END)))
        return row

    def controller(self,**changes):
        """Construct a local controller with exactly the same native SCOUT capability."""
        route=self.route()
        return HybridNavigation(route_capability(SCOUT_GRASS_ROUTE),route.route_id,
                                navigation_profile=SCOUT_PROFILE,reviewed_scout_route=route,**changes)

    def test_geometry_is_deeply_immutable_and_its_identity_covers_direction(self):
        """Caller lists or detached output documents cannot silently redirect a loaded worker."""
        points=[[-1135,2267],[-1142,2255]]
        route=ReviewedScoutRoute(points)
        points[1][0]=-1140
        document=route.document()
        document['points'][1][0]=-1140
        self.assertEqual(route,self.route())
        self.assertEqual(ReviewedScoutRoute.from_document(route.document()).sha256,route.sha256)
        with self.assertRaises(FrozenInstanceError):route.points=tuple(reversed(route.points))
        self.assertNotEqual(ReviewedScoutRoute(tuple(reversed(route.points))).route_id,route.route_id)

    def test_only_two_finite_endpoints_in_scope_and_within_forty_units_are_accepted(self):
        """Reject extra destinations, zero-length legs, oversized legs and nonnumeric coordinates."""
        bad=[[],[(-1135,2267)],list(self.route().points)+[(-1140,2250)],
             [(-1135,2267),(-1135,2267)],[(-1135,2267),(-1135,2307.01)],
             [(-1351,2267),(-1340,2267)],[(-1135,2049),(-1135,2055)],
             [(-1135,2267),(float('nan'),2255)],[(-1135,2267),(-1142,float('inf'))],
             [(-1135,2267),(True,2255)],[(-1135,2267),('-1142',2255)],[(-1135,2267),(10**400,2255)]]
        for points in bad:
            with self.subTest(points=points),self.assertRaises(ValueError):ReviewedScoutRoute(points)
        self.assertEqual(ReviewedScoutRoute(((-1135,2267),(-1135,2307))).points[1],(-1135.0,2307.0))
        for update in (dict(profileId='mondstadt-city-v1'),dict(version=True),dict(extraDestination=[0,0])):
            with self.subTest(update=update),self.assertRaises(ValueError):
                ReviewedScoutRoute.from_document(self.route().document()|update)

    def test_file_changes_cannot_mutate_an_already_parsed_geometry(self):
        """The CLI receives an immutable value, never a live reference to editable JSON."""
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder).resolve()/'route.json'
            path.write_text(json.dumps(self.route().document()),encoding='utf-8')
            spec=load_reviewed_route(path)
            path.write_text(json.dumps(ReviewedScoutRoute(tuple(reversed(spec.points))).document()),encoding='utf-8')
            self.assertEqual(spec,self.route())
            self.assertNotEqual(load_reviewed_route(path),spec)

    def test_controller_binds_geometry_and_requires_its_directed_start(self):
        """Unlike a reversible fixed route, a fresh review authorizes only start-to-end travel."""
        nav=self.controller()
        for index in (1,2,3):nav.prepare(self.observation(index))
        self.assertEqual(nav.phase,'walking')
        self.assertEqual((nav.start,nav.end),self.route().points)
        self.assertEqual(nav.snapshot()['routeSpecSha256'],self.route().sha256)
        event=nav.drain_events()[0]
        self.assertEqual(event['routeSpec'],self.route().document())
        self.assertEqual(nav.choose(self.observation(3),proposal(['W']))['step']['keys'],['W'])
        with self.assertRaises(RuntimeError):self.controller().prepare(self.observation(1,self.route().points[1]))
        with self.assertRaises(ValueError):self.controller(remember_bypass=True)

    def test_obstacle_requires_new_inspection_instead_of_generating_another_destination(self):
        """Explicit scout geometry inherits the fixed scout route's terminal obstacle behavior."""
        nav=self.controller()
        for index in (1,2,3):nav.prepare(self.observation(index))
        row=self.observation(4)
        with self.assertRaisesRegex(RuntimeError,'survey_obstacle_requires_inspection'):
            nav._begin_recovery(row)

    def test_geometry_options_cannot_change_model_scope_deadline_or_input_limits(self):
        """The optional CLI does not enlarge the established worker's non-leg authority."""
        route=self.route()
        args=SimpleNamespace(reviewed_scout_route=route,hybrid_route=route.route_id,navigation_profile=SCOUT_PROFILE,
            resident=True,enable_input=True,model='open-p2p',hybrid_navigation=True,hybrid_legs=1,seconds=35,
            max_observation_age_ms=150,action_hold_ms=100,patrol_series_binding=('exact','owner'),remember_hybrid_bypass=False)
        self.assertEqual(validate_reviewed_options(args),route)
        for key,value in dict(resident=False,model='gamescaling',hybrid_legs=2,seconds=35.01,
                              max_observation_age_ms=151,action_hold_ms=101,patrol_series_binding=None,
                              hybrid_route=SCOUT_GRASS_ROUTE,navigation_profile='other').items():
            changed=copy.copy(args)
            setattr(changed,key,value)
            with self.subTest(key=key),self.assertRaises(ValueError):validate_reviewed_options(changed)

    def test_short_holds_require_explicit_executed_history_and_exclude_recovery(self):
        """The opt-in history contract cannot shorten ordinary holds or retain obstacle/climb authority."""
        route=self.route()
        args=SimpleNamespace(reviewed_scout_route=route,hybrid_route=route.route_id,navigation_profile=SCOUT_PROFILE,
            resident=True,enable_input=True,model='open-p2p',hybrid_navigation=True,hybrid_legs=1,seconds=35,
            max_observation_age_ms=150,action_hold_ms=100,patrol_series_binding=('exact','owner'))
        self.assertEqual(validate_reviewed_options(args),route)
        for hold in (50,60):
            changed=copy.copy(args)
            changed.action_hold_ms=hold
            with self.subTest(ordinary_hold=hold),self.assertRaises(ValueError):validate_reviewed_options(changed)
            changed.p2p_executed_history=True
            self.assertEqual(validate_reviewed_options(changed),route)
            for key in ('navigation_climb_recovery','allow_inspected_obstacle_recovery','remember_hybrid_bypass'):
                forbidden=copy.copy(changed)
                setattr(forbidden,key,True)
                with self.subTest(hold=hold,forbidden=key),self.assertRaises(ValueError):validate_reviewed_options(forbidden)
        for mode,hold in ((True,100),(True,49),(True,61),(True,50.0),(1,50),('true',50),(None,100)):
            changed=copy.copy(args)
            changed.p2p_executed_history=mode
            changed.action_hold_ms=hold
            with self.subTest(mode=mode,hold=hold),self.assertRaises(ValueError):validate_reviewed_options(changed)




# Batch tests deliberately reuse the existing inert session and stream boundaries.
# They never import a GPU runtime, create a native connection or read live evidence.
from contextlib import ExitStack, redirect_stdout
import io
import time
from unittest.mock import patch
import audit_hybrid_run as audit_module
import native_ground_control as ground_module
import scout_session as scout_module
import stream_client as client_module
import test_scout_session as session_tests
import test_p2p_executed_history_stream as stream_tests
from reviewed_scout_route import (ReviewedScoutBatch, parse_reviewed_route, reviewed_leg_count,
                                  reviewed_batch_policy, batch_policy_matches, require_batch_review)
from scout_encounter_guard import ScoutEncounterGuard
from test_native_ground_control import attach_ground, binding as ground_binding
from test_resident_goals import dormant_control
from test_scout_encounter_guard import sample as guard_sample


BATCH = ReviewedScoutBatch(((-1135,2267),(-1142,2255),(-1142,2243)))


def batch_arguments(folder, *, seconds=4.):
    """Declare one inert two-leg lease with the same explicit private admission as the resident."""
    args = stream_tests.inert_arguments(folder, seconds=seconds)
    args.reviewed_scout_route, args.hybrid_route = BATCH, BATCH.route_id
    args.reviewed_scout_batch, args.hybrid_legs = True, reviewed_leg_count(BATCH)
    args.require_ground_control_layout, args.segment_seconds = True, 90
    return args


class BatchBridge(stream_tests.HistoryBridge):
    """Publish a second endpoint only after three further acknowledged in-memory actions."""
    def __init__(self, *, transform=None, **kwargs):
        """Keep the existing one-native-clock transport and add the required ground contract."""
        super().__init__(**kwargs)
        self.hello['groundControlObservation'] = copy.deepcopy(ground_module.CAPABILITY)
        self.batch_transform, self.last_source = transform, None

    def request(self, command, **arguments):
        """Retain the real request/receipt envelope while providing only synthetic source pixels."""
        if command == 'requireGroundControlLayout':
            self.commands.append(command)
            return dict(type='groundControlLayout', requiredForInput=True,
                        capability=copy.deepcopy(ground_module.CAPABILITY)), b''
        row, pixels = super().request(command, **arguments)
        if command == 'release':
            row['worldReadiness'].update(reason='client_release', sourceFrame=copy.deepcopy(self.last_source))
        if command == 'frame':
            index = min(len(self.completed)//3, len(BATCH.points)-1)
            point = BATCH.points[index]
            target = BATCH.points[min(index+1, len(BATCH.points)-1)]
            pose = row['navigationPose']
            pose.update(x=point[0], y=point[1],
                        yawDegrees=route_heading(dict(zip(('x','y'),point)), target) if point != target else 30.,
                        headingToStartDegrees=int(route_heading(dict(zip(('x','y'),point)), START)),
                        headingToEndDegrees=int(route_heading(dict(zip(('x','y'),point)), END)))
            row = attach_ground(row)
            self.last_source = copy.deepcopy(row['sourceFrame'])
            if self.batch_transform:row = self.batch_transform(row)
        return row, pixels


def run_batch_fixture(folder, *, bridge=None, policy=None, recorder=None, control=None, args=None):
    """Run production intake, guard, controller, receipts and cleanup through inert external boundaries."""
    bridge = bridge or BatchBridge()
    policy, recorder = policy or stream_tests.HistoryPolicy(), recorder or stream_tests.HistoryRecorder()
    args = args or batch_arguments(folder)
    control = control or dormant_control(folder, frozen_goal=True)
    control.set_initial_goal(dict(instruction='fixed reviewed batch'), 'ground-navigation')
    control.scout_encounter_guard = ScoutEncounterGuard(ground_binding())
    control.scout_batch_policy = reviewed_batch_policy(BATCH.profile_id)
    control.scout_batch_route_sha256 = BATCH.sha256
    with ExitStack() as stack:
        stack.enter_context(patch.dict(stream_tests.sys.modules, {'PIL': SimpleNamespace(
            Image=SimpleNamespace(frombytes=lambda mode,shape,pixels:pixels))}))
        stack.enter_context(patch.object(client_module, 'Bridge', return_value=bridge))
        stack.enter_context(patch.object(client_module, 'AsyncVideoRecorder', return_value=recorder))
        stack.enter_context(redirect_stdout(io.StringIO()))
        result = client_module.run_episode(args, policy, control)
    report_path = Path(args.output).parent/'00001.json' if getattr(args,'lease_output',None) else Path(args.output)
    report = json.loads(report_path.read_text(encoding='utf-8'))
    return result, report, recorder, bridge, policy


class ReviewedScoutBatchAuthorityTests(unittest.TestCase):
    """Prove that opt-in whole-polyline review adds no unbounded or legacy authority."""
    def test_geometry_preserves_v1_and_requires_one_to_eight_bounded_legs(self):
        """A separate exact schema/hash covers every ordered point, including later waypoints."""
        self.assertEqual(parse_reviewed_route(BATCH.document()), BATCH)
        self.assertEqual(reviewed_leg_count(BATCH), 2)
        with self.assertRaises(ValueError):ReviewedScoutRoute.from_document(BATCH.document())
        points = [(-1135,2267+i) for i in range(9)]
        self.assertEqual(reviewed_leg_count(ReviewedScoutBatch(points)), 8)
        for value in (points+[(-1135,2276)], points[:1], [points[0],points[0]],
                      [points[0],(-1135,2307.01)], [points[0],(-1351,2267)]):
            with self.subTest(points=value), self.assertRaises(ValueError):ReviewedScoutBatch(value)
        for change in (dict(version=True), dict(version=1), dict(profileId='City_102'), dict(extra=1)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                ReviewedScoutBatch.from_document(BATCH.document()|change)
        other = ReviewedScoutBatch(BATCH.points[:-1]+((-1143,2243),))
        self.assertNotEqual(other.sha256, BATCH.sha256)

    def test_batch_requires_exact_review_and_type_strict_descriptor(self):
        """A current start image alone cannot authorize unreviewed later points or resealed flags."""
        review = dict(wholePolylineReviewed=True, polylineReview='All two original segments inspected', routeSpecSha256=BATCH.sha256)
        require_batch_review(review, BATCH)
        for change in (dict(wholePolylineReviewed=1), dict(wholePolylineReviewed=False),
                       dict(polylineReview=''), dict(routeSpecSha256='0'*64)):
            with self.subTest(change=change), self.assertRaises(ValueError):require_batch_review(review|change, BATCH)
        with self.assertRaises(ValueError):require_batch_review(review, ReviewedScoutRoute(BATCH.points[:2]))
        descriptor = reviewed_batch_policy()
        self.assertTrue(batch_policy_matches(descriptor))
        for change in (dict(version=True), dict(maximumLegs=9), dict(maximumSeconds=61),
                       dict(actionHoldMs=60), dict(automaticRecovery=0), dict(extra=False)):
            self.assertFalse(batch_policy_matches(descriptor|change))

    def test_every_expanded_limit_requires_the_explicit_batch_mode(self):
        """The stream accepts neither an unstamped batch nor recovery, stale sources or larger clocks."""
        with tempfile.TemporaryDirectory() as folder:
            args = batch_arguments(folder, seconds=60)
            self.assertEqual(validate_reviewed_options(args), BATCH)
            for key,value in dict(reviewed_scout_batch=False, hybrid_legs=1, seconds=60.001,
                    action_hold_ms=60, max_observation_age_ms=151, p2p_executed_history=False, segment_seconds=60,
                    navigation_climb_recovery=True, allow_inspected_source_gap_recovery=True,
                    allow_inspected_obstacle_recovery=True, remember_hybrid_bypass=True).items():
                changed = copy.copy(args);setattr(changed,key,value)
                with self.subTest(key=key), self.assertRaises(ValueError):validate_reviewed_options(changed)
            control = dormant_control(folder, frozen_goal=True)
            control.scout_encounter_guard = ScoutEncounterGuard(ground_binding())
            policy = stream_tests.HistoryPolicy()
            for descriptor,digest in ((None,BATCH.sha256),(reviewed_batch_policy(),'0'*64)):
                control.scout_batch_policy, control.scout_batch_route_sha256 = descriptor,digest
                with self.assertRaisesRegex(ValueError,'[Bb]atch'):
                    stream_tests.validate_executed_history_options(args,policy,control,require_bound=True)

    def test_cli_default_stays_one_leg_and_batch_refuses_automatic_recovery(self):
        """The worker's separate admission flag requires reviewed geometry and the unchanged H41/50ms mode."""
        with tempfile.TemporaryDirectory() as folder:
            base = ['run','--directory',folder,'--owner-from',str(Path(folder)/'owner.json')]
            self.assertNotIn('allow_reviewed_batches', vars(scout_module.options(base)))
            selected = base+['--allow-reviewed-routes','--p2p-executed-history','--allow-reviewed-batches']
            self.assertTrue(scout_module.options(selected).allow_reviewed_batches)
            for extra in (['--action-hold-ms','60'],['--allow-inspected-source-gap-recovery'],
                          ['--allow-inspected-obstacle-recovery'],['--route',SCOUT_GRASS_ROUTE]):
                with self.subTest(extra=extra), redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                    scout_module.options(selected+extra)
            with self.assertRaises(SystemExit):scout_module.options(base+['--allow-reviewed-batches'])


class ReviewedScoutBatchSessionTests(unittest.TestCase):
    """Use the actual worker/request/resident lifecycle, substituting only its existing GPU and pipe doubles."""
    def setUp(self):
        """Compose the existing isolated fixture without rerunning its inherited legacy test methods."""
        self.fixture = fixture = session_tests.ScoutSessionTests(methodName='runTest')
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.prepare_executed_history_worker()
        fixture.settings.allow_reviewed_batches = True
        fixture.reviewed_routes, fixture.target = [BATCH], 1
        original_review = fixture.make_review

        def reviewed(route, spec=None):
            """Add only the new explicit whole-polyline review to the existing current-scene fixture."""
            path = original_review(route,spec)
            document = json.loads(path.read_bytes())
            document.update(maximumLegs=reviewed_leg_count(spec),wholePolylineReviewed=True,
                            polylineReview='Both exact synthetic ground segments inspected')
            session_tests.write_json(path,document)
            return path

        def episode(args, policy, control):
            """Keep real resident admission/retirement while avoiding any inference or native call."""
            self.assertIs(policy,fixture.policy)
            self.assertEqual((args.hybrid_legs,args.action_hold_ms,args.max_observation_age_ms),(2,50,150))
            self.assertLessEqual(args.seconds,60)
            self.assertEqual(args.segment_seconds,90)
            self.assertEqual(control.scout_batch_policy,reviewed_batch_policy())
            self.assertEqual(control.scout_batch_route_sha256,BATCH.sha256)
            fixture.episodes.append((args,policy.weights,policy.graph,control.run_id))
            source = attach_ground(guard_sample(health=args.scout_encounter_guard['baselineHealthFraction']))
            control.scout_encounter_guard.observe(source,1)
            control.scout_encounter_guard.check_dispatch(source,2)
            session_tests.runtime.atomic_json(args.output,dict(endReason='hybridLegLimit' if fixture.episode_code==0 else 'error',
                framesReceived=30,acceptedInputActions=6))
            fixture.after_episode(len(fixture.episodes),control)
            if fixture.episode_error:raise RuntimeError(fixture.episode_error)
            return fixture.episode_code

        fixture.make_review = reviewed
        fixture.stack.enter_context(patch.object(scout_module.client,'run_episode',episode))

    def test_one_review_one_load_one_native_lease_for_two_exact_legs(self):
        """Actual generated proof/request/session joins independently replay with no extra model load."""
        fixture = self.fixture
        result = fixture.run_worker()
        self.assertEqual((result['state'],result['reason']),('stopped','operatorStop'))
        self.assertEqual((len(fixture.loads),len(fixture.starts),len(fixture.episodes),len(fixture.audits)),(1,1,1,1))
        self.assertEqual(result['modelLoads'],1)
        self.assertTrue(fixture.watch.closed)
        request = json.loads(next((fixture.settings.directory/'requests').glob('*.json')).read_bytes())
        self.assertEqual(request['maximumLegs'],2)
        self.assertEqual(request['routeSpecSha256'],BATCH.sha256)
        self.assertEqual(fixture.audits[0]['modelLoads'],0)
        self.assertEqual(fixture.audits[0]['reviewedScoutBatchPolicy'],reviewed_batch_policy())

    def test_failed_batch_retires_without_failed_goal_or_source_gap_retry(self):
        """The whole reviewed batch is consumed once; a failed lease never becomes another leg request."""
        fixture = self.fixture
        fixture.episode_code, fixture.episode_error = 1,'synthetic non-endpoint source interruption'
        result = fixture.run_worker()
        self.assertEqual(len(fixture.starts),1)
        self.assertEqual(len(fixture.episodes),1)
        self.assertNotEqual(result['reason'],'operatorStop')
        self.assertTrue(fixture.watch.closed)
        self.assertEqual(len(list((fixture.settings.directory/'requests').glob('*.json'))),1)
        self.assertFalse(any(row.get('state')=='verified' for row in result['legs']))

    def test_mutable_polyline_review_cannot_expand_an_already_loaded_worker(self):
        """A hash-consistent request still needs the explicit complete review and exact count."""
        fixture = self.fixture
        original = fixture.make_review

        def incomplete(route,spec=None):
            """Keep the native/image evidence intact while withholding whole-route approval."""
            path = original(route,spec)
            document = json.loads(path.read_bytes());document.pop('wholePolylineReviewed')
            session_tests.write_json(path,document)
            return path

        fixture.make_review = incomplete
        result = fixture.run_worker()
        self.assertEqual((len(fixture.starts),len(fixture.episodes)),(0,0))
        self.assertNotEqual(result['reason'],'operatorStop')
        self.assertTrue(fixture.watch.closed)


class ReviewedScoutBatchStreamTests(unittest.TestCase):
    """Exercise two or more endpoints with real serialized history, guards, release and cleanup code."""
    def test_two_endpoints_keep_one_lease_and_reset_only_at_acknowledged_release(self):
        """The selected-action receipt chain survives both resets, with the same policy object throughout."""
        with tempfile.TemporaryDirectory() as folder:
            code,report,recorder,bridge,policy = run_batch_fixture(folder)
            self.assertEqual((code,report['status'],report['endReason']),(0,'completed','hybridLegLimit'))
            self.assertEqual((len(bridge.actions),len(bridge.completed),len(policy.commits)),(6,6,6))
            endpoints = [row for row in report['hybridNavigationEvents'] if row['type']=='hybridEndpointVerified']
            resets = [row for row in report['controlTransitions'] if 'executedHistoryReset' in row]
            self.assertEqual([row['endpoint'] for row in endpoints],['waypoint-1','waypoint-2'])
            self.assertEqual([row['history']['afterFrames'] for row in report['executedHistoryEvents']],[1,2,3,1,2,3])
            self.assertEqual(len(resets),2)
            for index,row in enumerate(resets):
                marker = row['executedHistoryReset']
                self.assertEqual(marker['previousReceipt']['requestId'],policy.commits[(index+1)*3-1])
                self.assertEqual(marker['release']['serverNowMs'],endpoints[index]['releaseAtMs'])
                self.assertEqual(marker['after']['afterFrames'],0)
            self.assertEqual(bridge.commands[-1],'stop')
            self.assertTrue(recorder.closed)
            self.assertTrue(bridge.handle.close.called)
            self.assertFalse(policy.pending)

    def test_eight_ordered_endpoints_complete_without_weight_reload_or_ninth_leg(self):
        """The upper count is exercised in the real loop, with one original request and24 receipts."""
        points = [(-1135,2267)]
        for index in range(8):
            x,y = points[-1]
            points.append((x-12,y) if index%2 else (x,y-12))
        batch = ReviewedScoutBatch(points)
        with patch(__name__+'.BATCH',batch), tempfile.TemporaryDirectory() as folder:
            code,report,recorder,bridge,policy = run_batch_fixture(folder,args=batch_arguments(folder,seconds=8))
            self.assertEqual((code,report['hybridNavigation']['completedLegs']),(0,8))
            self.assertEqual((len(bridge.actions),len(bridge.completed),len(policy.commits)),(24,24,24))
            self.assertEqual([row['history']['afterFrames'] for row in report['executedHistoryEvents']],[1,2,3]*8)
            self.assertEqual(len([row for row in report['controlTransitions'] if 'executedHistoryReset' in row]),8)
            self.assertTrue(recorder.closed)
            self.assertEqual(bridge.commands[-1],'stop')

    def test_missing_or_foreign_second_leg_receipt_cannot_be_hidden_by_first_reset(self):
        """One prior confirmed endpoint is retained, but a lost or foreign next receipt forbids continuation."""
        for foreign in (False,True):
            with self.subTest(foreign=foreign), tempfile.TemporaryDirectory() as folder:
                bridge,policy,recorder = BatchBridge(),stream_tests.HistoryPolicy(),stream_tests.HistoryRecorder()

                def changed(rows):
                    """Mutate only the first action of the second leg after its native terminal simulation."""
                    return ([dict(rows[0],requestId='foreign-request')] if foreign else []) if len(bridge.completed)==4 else rows

                bridge.bad_receipt = changed
                with self.assertRaises((ValueError,RuntimeError)):
                    run_batch_fixture(folder,bridge=bridge,policy=policy,recorder=recorder)
                report = json.loads((Path(folder)/'run.json').read_bytes())
                self.assertEqual((len(bridge.actions),len(policy.commits)),(4,3))
                self.assertEqual(len([row for row in report['controlTransitions'] if 'executedHistoryReset' in row]),1)
                self.assertEqual(report['status'],'failed')
                self.assertEqual(bridge.commands[-1],'stop')
                self.assertTrue(recorder.closed)

    def test_non_endpoint_enemy_health_source_and_ground_interruptions_are_terminal(self):
        """No later waypoint can turn a known hazard or stale/missing source into an automatic retry."""
        for kind in ('enemy','health','source','ground'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                bridge = BatchBridge()

                def interrupt(row):
                    """Deliver the interruption after one acknowledged second-leg action, not during own release."""
                    if len(bridge.completed)<4 or 'combatEvidence' not in row:return row
                    if kind=='enemy':row['combatEvidence']['enemyBarCandidates']=guard_sample(candidates=True)['combatEvidence']['enemyBarCandidates']
                    elif kind=='health':row['combatEvidence']['playerHealthFractionEstimate']=.7
                    elif kind=='source':row['sourceFrameAgeMs']=151
                    else:row=attach_ground(row,water=True)
                    return row

                bridge.batch_transform = interrupt
                with self.assertRaises((ValueError,RuntimeError)):run_batch_fixture(folder,bridge=bridge)
                report = json.loads((Path(folder)/'run.json').read_bytes())
                self.assertEqual(len(bridge.actions),4)
                self.assertEqual(report['status'],'failed')
                self.assertEqual(bridge.commands[-1],'stop')

    def test_original_lease_expiry_does_not_restart_or_extend_a_batch(self):
        """A pending action at the original deadline ends the lease without another action or endpoint reset."""
        with tempfile.TemporaryDirectory() as folder:
            bridge = BatchBridge(hold_terminal=True)
            args = batch_arguments(folder,seconds=.25)
            began = time.monotonic()
            with self.assertRaisesRegex(RuntimeError,'lease ended'):
                run_batch_fixture(folder,bridge=bridge,args=args)
            self.assertEqual(len(bridge.actions),1)
            self.assertLess(time.monotonic()-began,2)
            report = json.loads((Path(folder)/'run.json').read_bytes())
            self.assertFalse([row for row in report['controlTransitions'] if 'executedHistoryReset' in row])
            self.assertEqual(bridge.commands[-1],'stop')

    def test_stop_and_recording_loss_after_endpoint_do_not_enable_another_leg(self):
        """The existing STOP and fail-closed recorder still retire a batch with its prior endpoint retained."""
        for kind in ('stop','recording'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                control = dormant_control(folder,frozen_goal=True)
                bridge = BatchBridge()

                class StoppingRecorder(stream_tests.HistoryRecorder):
                    """Inject a local interruption after the first exact endpoint event is retained."""
                    def event(self,event):
                        """Refuse only subsequent recording or latch STOP; never replace native input evidence."""
                        result = super().event(event)
                        if event.get('type')=='hybridEndpointVerified' and event['completedLegs']==1:
                            if kind=='stop':
                                with control._lock:control._command,control._epoch='stop',control._epoch+1
                            else:self.dropped_events=1
                        return result

                recorder = StoppingRecorder()
                if kind=='stop':run_batch_fixture(folder,bridge=bridge,control=control,recorder=recorder)
                else:
                    with self.assertRaises((ValueError,RuntimeError)):run_batch_fixture(folder,bridge=bridge,control=control,recorder=recorder)
                self.assertEqual(len(bridge.actions),3)
                self.assertEqual(bridge.commands[-1],'stop')
                self.assertTrue(recorder.closed)


class ReviewedScoutBatchAuditTests(unittest.TestCase):
    """Replay one real inert two-endpoint journal, then corrupt exact joins without rerunning the model double."""
    @classmethod
    def setUpClass(cls):
        """Retain one synthetic original trace for independent reset and endpoint mutations."""
        with tempfile.TemporaryDirectory() as folder:
            code,part,recorder,_,_ = run_batch_fixture(folder)
            if code != 0:raise AssertionError(part)
            cls.trace = (part,{metadata['frameId']:metadata for metadata,_ in recorder.frames},recorder.events)

    def replay(self, part, frames, rows):
        """Use the original JSONL reader, exact receipt checker and batch endpoint verifier."""
        starts = [row for row in part['hybridNavigationEvents'] if row['type']=='hybridStartVerified']
        endpoints = [row for row in part['hybridNavigationEvents'] if row['type']=='hybridEndpointVerified']
        audit_module.verify_reviewed_batch(BATCH,starts,endpoints,part['decisions'],frames)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'00001';path.mkdir()
            (path/'events.jsonl').write_text('\n'.join(json.dumps(row) for row in rows),encoding='utf-8')
            return audit_module.verify_executed_history(part,[part],frames,[dict(number=1)],path.parent,
                dict(historyCommitMode=stream_tests.MODE,actionHoldMs=50,routeSpec=BATCH.document(),
                     reviewedScoutBatchPolicy=reviewed_batch_policy()))

    def test_actual_two_endpoint_trace_replays_zeroed_counters_without_losing_prior_receipts(self):
        """All six admissions/terminals remain in the audit even though the final temporal cache is empty."""
        result = self.replay(*copy.deepcopy(self.trace))
        self.assertEqual((result['committedActions'],result['finalHistoryFrames']),(6,0))
        self.assertFalse(result['physicalInputDeliveryVerified'])

    def test_complete_audit_replays_batch_sources_guard_receipts_and_endpoints(self):
        """Only the separately tested file-proof admission is injected; every original stream record replays."""
        part,frames,rows = copy.deepcopy(self.trace)
        # The resident wrapper retains this same initial state before invoking the
        # stream. Its actual generation/proof path is tested in the session cases.
        part['leaseInitialGoalState'] = copy.deepcopy(part['initialGoalState'])
        reuse = dict(routeId=BATCH.route_id,navigationProfile=BATCH.profile_id,
            routeSpec=BATCH.document(),routeSpecSha256=BATCH.sha256,
            historyCommitMode=stream_tests.MODE,actionHoldMs=50,
            reviewedScoutBatchPolicy=reviewed_batch_policy(),scoutEncounterGuard=copy.deepcopy(part['scoutEncounterGuard']))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);recording = root/'recording'/'00001';recording.mkdir(parents=True)
            (recording/'events.jsonl').write_text('\n'.join(json.dumps(row) for row in rows),encoding='utf-8')
            (recording/'observations.jsonl').write_text('\n'.join(json.dumps(row) for row in frames.values()),encoding='utf-8')
            (root/'part.json').write_text(json.dumps(part),encoding='utf-8')
            run = dict(part,evidenceComplete=True,modelLoads=0,segments=[dict(number=1,report='part.json')])
            (root/'run.json').write_text(json.dumps(run),encoding='utf-8')
            with patch.object(audit_module,'verify_policy_reuse',return_value=reuse):
                result = audit_module.audit(root/'run.json',recording.parent,repository=root,
                    minimum_legs=2,reviewed_scout_route=BATCH,policy_reuse_proof=root/'inert-proof.json')
            self.assertEqual((result['verifiedLegs'],result['controllerLeases'],result['acceptedActions']),(2,1,6))
            self.assertEqual(result['executedHistory']['finalHistoryFrames'],0)
            self.assertFalse(result['physicalInputDeliveryVerified'])

    def test_complete_audit_requires_terminal_before_endpoint_release(self):
        """Coherently reseal every terminal/predecessor copy; the native ordering must still hold."""
        for offset in (0,1):
            with self.subTest(millisecondsAfterRelease=offset):
                altered=copy.deepcopy(self.trace)
                marker=next(row['executedHistoryReset'] for row in altered[0]['controlTransitions']
                            if 'executedHistoryReset' in row)
                request=marker['previousReceipt']['requestId']
                changed_end=marker['release']['serverNowMs']+offset
                count=[0]

                def change(value):
                    """Change only the exact receipt's end clock in all retained original copies."""
                    if isinstance(value,dict):
                        if value.get('requestId')==request and 'endedAtMs' in value:
                            value['endedAtMs']=changed_end;count[0]+=1
                        for child in value.values():change(child)
                    elif isinstance(value,(list,tuple)):
                        for child in value:change(child)

                change(altered)
                self.assertGreaterEqual(count[0],4)
                with patch.object(self,'trace',altered):
                    if offset:
                        with self.assertRaisesRegex(ValueError,'settled receipt'):
                            self.test_complete_audit_replays_batch_sources_guard_receipts_and_endpoints()
                    else:self.test_complete_audit_replays_batch_sources_guard_receipts_and_endpoints()

    def test_each_batch_edge_keeps_the_original35_second_deadline(self):
        """The longer total authority cannot renew a stalled edge or a no-frame wait."""
        part,frames,_ = copy.deepcopy(self.trace)
        start = next(row for row in part['hybridNavigationEvents'] if row['type']=='hybridStartVerified')
        nav = HybridNavigation(route_capability(SCOUT_GRASS_ROUTE),BATCH.route_id,
            navigation_profile=BATCH.profile_id,reviewed_scout_route=BATCH,
            action_hold_ms=50,require_ground_controls=True)
        with patch('hybrid_navigation.time.perf_counter_ns',return_value=0):
            for sample in start['samples']:nav.prepare(frames[sample['frameId']])
        self.assertEqual(nav.phase,'walking')
        with patch('hybrid_navigation.time.perf_counter_ns',return_value=35_000_000_001):
            with self.assertRaisesRegex(RuntimeError,'leg_progress_deadline'):nav.check_leg_deadline()

    def test_missing_foreign_or_relabelled_reset_cannot_conceal_a_receipt(self):
        """Mutate every retained copy coherently so refusal depends on the independent semantic joins."""
        for kind in ('missing-receipt','foreign-receipt','missing-reset','foreign-release','reset-counters','reason','ordinal'):
            with self.subTest(kind=kind):
                part,frames,rows = copy.deepcopy(self.trace)
                if kind=='missing-receipt':
                    request = part['receipts'][2]['requestId']
                    rows[:] = [row for row in rows if not ('appliedSteps' in row and row.get('requestId')==request)]
                else:
                    for values in (part['controlTransitions'],rows):
                        index = next(index for index,row in enumerate(values) if 'executedHistoryReset' in row)
                        if kind=='missing-reset':values[index].pop('executedHistoryReset');continue
                        marker = values[index]['executedHistoryReset']
                        if kind=='foreign-receipt':marker['previousReceipt']['requestId']='foreign'
                        elif kind=='foreign-release':marker['release']['serverNowMs']+=1
                        elif kind=='reset-counters':marker['before']['afterFrames']=0
                        elif kind=='reason':values[index]['reason']='unrelated-source-gap'
                        else:marker['endpointOrdinal']=2
                with self.assertRaises(ValueError):self.replay(part,frames,rows)

    def test_later_waypoint_and_post_release_source_cannot_be_substituted(self):
        """A released first leg is not authority to skip, reverse or refresh the next leg's deadline."""
        for kind in ('order','epoch','arrival','leg-clock','active-target','extra-action'):
            with self.subTest(kind=kind):
                part,frames,rows = copy.deepcopy(self.trace)
                endpoints = [row for row in part['hybridNavigationEvents'] if row['type']=='hybridEndpointVerified']
                endpoint = endpoints[1]
                if kind=='order':endpoint['endpoint']='waypoint-1'
                elif kind=='epoch':frames[endpoint['samples'][0]['frameId']]['frameWorldReadiness']['epoch']+=1
                elif kind=='arrival':endpoint['arrivalFrameId']=part['decisions'][0]['frameId']
                elif kind=='leg-clock':endpoint['legElapsedMs']=35001
                elif kind=='active-target':part['decisions'][-1]['hybridNavigation']['target']='waypoint-1'
                else:part['decisions'][-1]['observationTimestampMs']=endpoint['samples'][-1]['atMs']+1
                with self.assertRaises(ValueError):self.replay(part,frames,rows)



class ReviewedScoutBatchRecordingTests(unittest.TestCase):
    """Keep the existing bounded archive alive once, including teardown after its nominal interval."""
    def test_real_segment_path_and_delayed_teardown_keep_one_archive_and_original_input_limits(self):
        """Advance only the recording clock after stop; cleanup must close rather than rotate or infer."""
        import stream_segments as segment_module
        with tempfile.TemporaryDirectory() as folder:
            args = batch_arguments(folder)
            args.lease_output = str(Path(folder)/'lease.json')
            args.record_dir = str(Path(folder)/'recording'/'00001')
            args.lease_deadline = time.monotonic()+args.seconds
            created, offset = [], [0]
            original_class = segment_module.StreamSegments
            clock = SimpleNamespace(perf_counter=lambda:time.perf_counter()+offset[0],
                                    monotonic=time.monotonic,sleep=time.sleep)

            def create(*values,**keywords):
                """Observe the real segment manager without replacing any of its lifecycle methods."""
                archive = original_class(*values,**keywords)
                created.append(archive)
                return archive

            class RetainedRecorder(stream_tests.HistoryRecorder):
                """Supply synchronous retained bytes in place of FFmpeg, preserving the real segment owner."""
                def begin_close(self):
                    """The real manager stops admission before the finalizer closes this owned recorder."""
                    self.closing = True

                def fail(self,reason):
                    """Retain a real manager failure instead of pretending evidence is complete."""
                    self.error = str(reason)

                def close(self,timeout=None):
                    """Retain the original source/journal bytes and count them against the shared budget."""
                    result = super().close()
                    root = Path(args.record_dir);root.mkdir(parents=True,exist_ok=True)
                    observations = '\n'.join(json.dumps(row) for row,_ in self.frames).encode()
                    events = '\n'.join(json.dumps(row) for row in self.events).encode()
                    (root/'observations.jsonl').write_bytes(observations)
                    (root/'events.jsonl').write_bytes(events)
                    used = created[0].budget.update(str(root),len(observations)+len(events)+sum(len(pixels) for _,pixels in self.frames))
                    if used>=created[0].budget.maximum:result.update(complete=False,error='synthetic storage exhaustion')
                    return result

            class LateStopBridge(BatchBridge):
                """Move only the archive teardown clock after the final native stop acknowledgement."""
                def request(self,command,**arguments):
                    """No input or source clock is advanced by this delayed-finalization simulation."""
                    result = super().request(command,**arguments)
                    if command=='stop':offset[0]=91
                    return result

            with patch.object(segment_module,'time',clock), patch.object(segment_module,'StreamSegments',side_effect=create):
                code,part,recorder,bridge,policy = run_batch_fixture(folder,bridge=LateStopBridge(),recorder=RetainedRecorder(),args=args)
            lease = json.loads(Path(args.lease_output).read_bytes())
            self.assertEqual((code,len(created),len(lease['segments'])),(0,1,1))
            self.assertEqual((created[0].budget.maximum,args.seconds,args.segment_seconds),(160*2**20,4.,90))
            self.assertGreater(part['segment']['endedAtClientNs']-part['segment']['startedAtClientNs'],90_000_000_000)
            self.assertEqual((lease['endReason'],lease['acceptedInputActions']),('hybridLegLimit',6))
            self.assertEqual((len(bridge.actions),len(policy.commits)),(6,6))
            self.assertEqual(bridge.commands[-1],'stop')
            self.assertTrue(recorder.closed)
            self.assertFalse(created[0].worker.is_alive())

    def test_batch_storage_ceiling_and_recording_interval_cannot_be_changed(self):
        """A longer observation file never permits more bytes, input time, queues or side inputs."""
        with tempfile.TemporaryDirectory() as folder:
            args = batch_arguments(folder,seconds=60)
            stream_tests.validate_executed_history_options(args)
            for key,value in (('record_max_mib',160.001),('record_max_mib',0),('segment_seconds',30),
                              ('segment_seconds',60),('segment_seconds',91),('seconds',60.001)):
                changed = copy.copy(args);setattr(changed,key,value)
                with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                    stream_tests.validate_executed_history_options(changed)


if __name__=='__main__':unittest.main()
