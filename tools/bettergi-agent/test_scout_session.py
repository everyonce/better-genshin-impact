"""Synthetic session, reuse and terminal-stop tests; no model, native process or gameplay is started."""
from contextlib import ExitStack, redirect_stderr
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import resident_runtime as runtime
import scout_session as scout
from episode_split import read_split,reserve_split


def write_json(path, value):
    """Write a named synthetic artifact without touching live runtime evidence."""
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value),encoding='utf-8')


class IdleChildTests(unittest.TestCase):
    """A stopped menu pilot is idle only after its service has released ownership."""
    def test_terminal_pilot_states_require_explicitly_released_ownership(self):
        """Cover the live stopped-pilot handoff and refuse ambiguous or still-owned states."""
        for state in ('idle','completed','failed','cancelled','stopped'):
            child=dict(taskRunning=False,agentStreamRunning=False,pilotState=state,serviceOwnsPilot=False)
            self.assertTrue(scout.idle_child(child),state)
            for ownership in (True,None,0):
                self.assertFalse(scout.idle_child(dict(child,serviceOwnsPilot=ownership)),(state,ownership))
            del child['serviceOwnsPilot']
            self.assertFalse(scout.idle_child(child),state)

    def test_busy_or_unknown_child_cannot_start_another_lease(self):
        """The new stopped state does not bypass active tasks, streams, or a stopping pilot."""
        child=dict(taskRunning=False,agentStreamRunning=False,pilotState='stopped',serviceOwnsPilot=False)
        for patch_value in (dict(taskRunning=True),dict(agentStreamRunning=True),
                            dict(pilotState='stopping'),dict(pilotState='running'),dict(pilotState=None)):
            self.assertFalse(scout.idle_child(dict(child,**patch_value)),patch_value)


class FakePolicy:
    """Keep a visible immutable weights/graph identity and resettable action history."""
    def __init__(self):
        self.weights,self.graph=object(),object()
        self.metadata={}
        self.history=[]
        self.goals=[]
        self._pending_feedback=False

    def reset(self):
        """Reset history without replacing either expensive resource."""
        self.history.clear()
        self._pending_feedback=False

    def set_goal(self, path):
        """Mirror the adapter's existing goal/history reset seam."""
        self.goals.append(path)
        self.reset()


class FakeWatch:
    """Drive explicit test submissions at admission boundaries without native monitoring."""
    def __init__(self, folder, settings, owner, lifecycle):
        self.folder,self.owner=folder,owner
        self.reason=None
        self.active=None
        self.closed=False
        self.deadline=time.monotonic_ns()+60_000_000_000
        self.drive=lambda _:None

    def start(self):
        """The real thermal monitor is tested separately with synthetic telemetry."""

    def check(self):
        """Deliver the test's next explicit operator action, or a latched stop."""
        self.drive(self)
        if self.reason:raise RuntimeError(self.reason)

    def activate(self, folder):
        """Observe the lease boundary without opening a bridge."""
        self.active=folder

    def deactivate(self):
        """Return the synthetic worker to its bridge-free state."""
        self.active=None

    def binding(self):
        """Use the same exact owner and non-extending deadline on both runs."""
        root,child=self.owner['root'],self.owner['child']
        return f"{root['processId']}:{root['instanceNonce']}:{child['processId']}:{child['instanceNonce']}:{self.deadline}"

    def close(self):
        """Record terminal retirement for assertions."""
        self.closed=True


class ScoutSessionTests(unittest.TestCase):
    """Exercise the actual resident reuse seam while substituting only native and GPU boundaries."""
    def setUp(self):
        """Create a completely isolated workspace and fixed original ownership."""
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.live=self.root/'artifacts/live'
        self.live.mkdir(parents=True)
        self.owner=dict(root=dict(processId=11,windowsSessionId=1,instanceNonce='a'*32),
                        child=dict(processId=22,windowsSessionId=3,instanceNonce='b'*32))
        self.primary=dict(self.owner['root'],instanceType='Primary',uiStatus='current',childWindowMinimized=True)
        self.child=dict(self.owner['child'],instanceType='ChildSession',remoteDesktop=True,automationEnabled=True,
            runtimeRunning=True,automationState='game_ready',taskRunning=False,agentStreamRunning=False,
            pilotState='idle',serviceOwnsPilot=False,agentPipeName='BetterGI.Agent.synthetic')
        self.starts=[]
        self.lifecycle=SimpleNamespace(discover=lambda:dict(instances=[self.primary,self.child],unavailable=[]),
            require_role=lambda *args:None,_require_connected_root=lambda *args:None,
            start_agent=lambda entry,*args,**kwargs:self.starts.append(entry.copy()) or entry)
        self.checkpoint=self.root/'synthetic.ckpt'
        self.checkpoint.write_bytes(b'fixed synthetic checkpoint')
        self.goal=self.root/'goal.json'
        write_json(self.goal,dict(goal='synthetic fixed instruction'))
        self.settings=SimpleNamespace(directory=self.live/'session',owner_from=self.live/'owner.json',
            routes=None,seconds=60,checkpoint=self.checkpoint,source=self.root/'source',goal_embedding=self.goal,
            ffmpeg=self.root/'ffmpeg.exe',nvidia_smi=self.root/'nvidia-smi.exe',record_max_mib=160)
        for module,name,value in ((scout,'LIVE',self.live),(scout,'ROOT',self.root),
            (scout,'OPEN_P2P_SHA256',hashlib.sha256(self.checkpoint.read_bytes()).hexdigest()),
            (scout,'load_map_owner',lambda _:copy.deepcopy(self.owner)),(scout,'require_ordinary',lambda _:None),
            (runtime,'require_current_rdp',lambda _:None),(runtime,'control_module',lambda:self.lifecycle)):
            self.stack.enter_context(patch.object(module,name,value))
        self.stack.enter_context(patch.object(runtime.socket,'gethostname',return_value='SIREN'))
        self.policy=FakePolicy()
        self.loads=[]
        self.episodes=[]
        self.reviews=0
        self.target=2
        self.before_submit=lambda number:None
        self.after_episode=lambda number,control:None
        self.episode_code=0
        self.episode_error=None
        self.recording_payload=b''
        self.admit_guard=True
        self.audits=[]
        self.watch=None
        self.stack.enter_context(patch.object(scout.client,'run_episode',self.episode))

    def make_review(self, route, spec=None):
        """Join one explicit review to fresh immutable native-plan, image and observation fixtures."""
        self.reviews+=1
        folder=self.live/f'review-{self.reviews}'
        folder.mkdir()
        image=folder/'01-frame-000000000001.png'
        image.write_bytes(b'synthetic-image-'+str(self.reviews).encode())
        image_sha=scout.file_sha(image)
        points=spec.points if spec is not None else scout.route_points(route)
        frames=[]
        for number in (1,2,3):
            stamp=(time.perf_counter_ns()//100 if getattr(self.settings,'allow_inspected_obstacle_recovery',False) else 0)
            source=dict(captureEpoch='synthetic',timestamp100ns=stamp+number*1_000_000,freshnessAtMs=number*100)
            pose=dict(state='valid',frameId=number,x=points[0][0],y=points[0][1],
                      layerId='MapBack_2',positionConfidence=.999,yawConfidence=.8,yawDegrees=270)
            frames.append(dict(frameId=number,sourceFrame=source,navigationPose=pose,sourceFrameAgeMs=40,
                frameWorldReadiness=dict(ready=True,sourceFrameId=number,sourceFrame=source,epoch=1),
                worldReadiness=dict(ready=True),motionEvidence=dict(status='normal',spaceKeyMatched=False),
                executionContext=dict(lastSequence=0)))
        write_json(folder/'plan.json',dict(owner=self.owner,enableInput=False,modelLoaded=False,
                                         navigationProfile=scout.SCOUT_PROFILE))
        write_json(folder/'result.json',dict(status='completed',inputEnabled=False,modelLoaded=False,
            ownerIdleMinimizedAfter=True,stableSamples=frames,observations=frames))
        write_json(image.with_suffix('.json'),dict(frames[0],imageSha256=image_sha))
        path=folder/'review.json'
        write_json(path,dict(routeId=route,points=[list(point) for point in points],
            nativeEndpoint=str(folder),imageName=image.name,imageSha256=image_sha,attacksAllowed=False,
            maximumLegs=1,inspectedHealth=2000,inspectedMaximumHealth=2700,visualReview='Synthetic clear ground',
            **(dict(routeSpec=spec.document(),routeSpecSha256=spec.sha256) if spec is not None else {})))
        return path

    def driver(self, watch):
        """Simulate separately supplied requests only after each prior leg has fully returned."""
        state=json.loads((watch.folder/'session.json').read_text())
        if state['state']!='awaitingReview':return
        self.assertIsNone(watch.active)
        completed=sum(row['state']=='verified' for row in state['legs'])
        if completed>=self.target:
            watch.reason='operatorStop'
            return
        if any(path.stem not in state['seenRequestIds'] for path in (watch.folder/'requests').glob('*.json')):return
        self.before_submit(completed)
        spec=self.reviewed_routes[completed] if getattr(self,'reviewed_routes',None) else None
        route=spec.route_id if spec is not None else (scout.SCOUT_GRASS_ROUTE,scout.SCOUT_GROVE_ROUTE)[completed%2]
        scout.submit(watch.folder,self.make_review(route,spec))

    def make_watch(self, *args):
        """Inject deterministic commands while retaining the real resident lifetime."""
        self.watch=FakeWatch(*args)
        self.watch.drive=self.driver
        return self.watch

    def load(self, args):
        """Record the only heavyweight load boundary without importing GPU libraries."""
        self.loads.append(args)
        return self.policy

    def episode(self, args, policy, control):
        """Complete one synthetic lease with the real resident's unique run/control identity."""
        self.assertIs(policy,self.policy)
        self.assertEqual(policy.history,[])
        self.assertEqual((args.action_hold_ms,args.max_observation_age_ms,args.hybrid_legs),(100,150,1))
        self.assertLessEqual(args.seconds,35)
        self.episodes.append((args,policy.weights,policy.graph,control.run_id))
        if self.admit_guard:
            from test_scout_encounter_guard import sample
            frame=sample(health=args.scout_encounter_guard['baselineHealthFraction'])
            control.scout_encounter_guard.observe(frame,1)
            control.scout_encounter_guard.check_dispatch(frame,2)
        policy.history.append('prior-leg-history')
        runtime.atomic_json(args.output,dict(endReason='hybridLegLimit' if self.episode_code==0 else 'error',
            framesReceived=30,acceptedInputActions=10))
        if self.recording_payload:
            Path(args.record_dir).mkdir(parents=True,exist_ok=True)
            (Path(args.record_dir)/'synthetic-recording.bin').write_bytes(self.recording_payload)
        self.after_episode(len(self.episodes),control)
        if self.episode_error:raise RuntimeError(self.episode_error)
        return self.episode_code

    def audit(self, folder, request):
        """Check reuse evidence independently while avoiding fabricated gameplay qualification."""
        from audit_hybrid_run import verify_policy_reuse
        report=json.loads((folder/'patrol.json').read_text())
        with patch.object(runtime,'OPEN_P2P_SHA256',scout.OPEN_P2P_SHA256):
            proof=verify_policy_reuse(report,folder/'patrol.json',Path(str(folder/'patrol.json')+'.reuse.json'))
        self.assertEqual(proof['requestId'],request['requestId'])
        self.audits.append(report)

    def run_worker(self, **kwargs):
        """Run a bounded CPU-only session and return its terminal evidence."""
        code=scout.run_session(self.settings,lifecycle=self.lifecycle,loader=self.load,
            watch_factory=self.make_watch,auditor=self.audit,**kwargs)
        self.assertEqual(code,1)  # An explicit terminal stop ends this worker, never restarts it.
        return json.loads((self.settings.directory/'session.json').read_text())

    def test_two_reviewed_routes_load_once_reset_history_and_retire_each_lease(self):
        """Actual resident controls and manifests prove zero-load reuse with distinct fresh run IDs."""
        result=self.run_worker()
        self.assertEqual((result['state'],result['reason']),('stopped','operatorStop'))
        self.assertEqual((len(self.loads),len(self.episodes),len(self.starts),len(self.audits)),(1,2,2,2))
        self.assertEqual([row['state'] for row in result['legs']],['verified','verified'])
        self.assertEqual(len(self.policy.goals),2)
        self.assertEqual(self.episodes[0][1:3],self.episodes[1][1:3])
        self.assertNotEqual(self.episodes[0][3],self.episodes[1][3])
        self.assertEqual([r['modelLoads'] for r in self.audits],[0,0])
        self.assertEqual([r['modelLoadSeconds'] for r in self.audits],[0.0,0.0])
        self.assertEqual(result['modelLoads'],1)
        self.assertTrue(self.watch.closed)
        for row in result['legs']:
            self.assertEqual(row['datasetSplit'],'diagnostic')
            self.assertEqual(read_split(Path(row['directory']),row['runId'])['split'],'diagnostic')

    def test_two_different_explicit_geometries_reuse_actual_resident_without_route_table_edits(self):
        """Two fresh reviews select different local immutable routes across real resident lifetimes."""
        # Longer idle retention must never extend the per-leg limits asserted by episode().
        self.settings.seconds=1800
        self.settings.allow_reviewed_routes=True
        self.reviewed_routes=[scout.ReviewedScoutRoute(((-1135,2267),(-1135,2280))),
                              scout.ReviewedScoutRoute(((-1135,2280),(-1150,2280)))]
        self.test_two_reviewed_routes_load_once_reset_history_and_retire_each_lease()
        self.assertEqual([episode[0].reviewed_scout_route for episode in self.episodes],self.reviewed_routes)
        for report,spec in zip(self.audits,self.reviewed_routes):
            self.assertEqual(report['policyReuse']['routeSpec'],spec.document())
            self.assertEqual(report['policyReuse']['routeSpecSha256'],spec.sha256)
            self.assertEqual(report['policyReuse']['routeId'],spec.route_id)
            self.assertNotIn(spec.route_id,scout.SCOUT_ROUTES)

    def test_explicit_geometry_requires_startup_authority_and_a_fresh_matching_start(self):
        """Geometry never grants a worker new scope or substitutes another reviewed starting location."""
        spec=scout.ReviewedScoutRoute(((-1135,2267),(-1135,2280)))
        review=self.make_review(spec.route_id,spec)
        manifest=dict(owner=self.owner,routes={})
        with self.assertRaisesRegex(ValueError,'did not authorize'):scout.review_evidence(review,manifest,0)
        manifest['reviewedScoutRoutePolicy']=scout.reviewed_route_policy()
        self.assertEqual(scout.review_evidence(review,manifest,0)['routeSpecSha256'],spec.sha256)
        with self.assertRaisesRegex(ValueError,'fresh native scene'):scout.review_evidence(review,manifest,time.time_ns()+1)
        value=json.loads(review.read_text())
        moved=scout.ReviewedScoutRoute(((-1145,2267),(-1145,2280)))
        value.update(routeId=moved.route_id,points=moved.document()['points'],routeSpec=moved.document(),routeSpecSha256=moved.sha256)
        write_json(review,value)
        with self.assertRaisesRegex(ValueError,'route start'):scout.review_evidence(review,manifest,0)

    def test_standalone_reviewed_geometry_cannot_load_or_open_a_lease_without_cached_request(self):
        """The optional CLI seam cannot skip explicit worker admission even with valid geometry."""
        spec=scout.ReviewedScoutRoute(((-1135,2267),(-1135,2280)))
        folder=self.live/'standalone'
        watch=FakeWatch(folder,self.settings,self.owner,self.lifecycle)
        args=scout.leg_arguments(self.settings,self.owner,spec.route_id,folder,watch.binding(),160,spec)
        with self.assertRaisesRegex(ValueError,'cached-session request'):
            runtime.run_resident(args,self.load,self.episode)
        self.assertEqual((self.loads,self.starts,self.episodes),([],[],[]))

    def test_explicit_request_cannot_change_reviewed_geometry_hash_profile_or_leg_count(self):
        """Validate the actual worker request boundary before cached acquisition or native input."""
        spec=scout.ReviewedScoutRoute(((-1135,2267),(-1142,2255)))
        other=scout.ReviewedScoutRoute(((-1135,2267),(-1140,2253)))
        review=self.make_review(spec.route_id,spec)
        manifest=dict(owner=self.owner,routes={},reviewedScoutRoutePolicy=scout.reviewed_route_policy(),
                      sessionId='c'*32,modelConfigurationSha256='f'*64)
        request=dict(version=1,sessionId=manifest['sessionId'],requestId='d'*32,afterRequestId=None,
            modelConfigurationSha256='f'*64,navigationProfile=scout.SCOUT_PROFILE,maximumLegs=1,
            reviewFile=str(review),**scout.review_evidence(review,manifest,0))
        path=self.live/('d'*32+'.json')
        write_json(path,request)
        self.assertEqual(scout.validate_request(path,manifest,None,0)[0],request)
        for changed in (dict(routeSpec=other.document()),dict(routeSpecSha256=other.sha256),dict(routeId=other.route_id),
                        dict(navigationProfile='other'),dict(maximumLegs=2),dict(afterRequestId='e'*32)):
            write_json(path,request|changed)
            with self.subTest(changed=changed),self.assertRaises(ValueError):scout.validate_request(path,manifest,None,0)

    def test_busy_passive_observer_refuses_one_request_without_automatic_retry(self):
        """Finishing passive inspection alone cannot cause the refused request to start."""
        original=self.driver
        phases=[]
        self.target=1
        def busy_driver(watch):
            """Explicitly submit again only after observing the recorded refusal and an idle child."""
            state=json.loads((watch.folder/'session.json').read_text())
            if state['state']=='awaitingReview' and not phases:
                phases.append('busy')
                self.child['taskRunning']=True
            elif state.get('lastRefusal') and phases==['busy']:
                self.assertEqual(len(self.starts),0)
                self.child['taskRunning']=False
                phases.append('idle-without-request')
                return
            elif phases==['busy','idle-without-request']:
                self.assertEqual(len(self.starts),0)
                phases.append('fresh-explicit-request')
            original(watch)
        self.driver=busy_driver
        result=self.run_worker()
        self.assertEqual(result['lastRefusal']['reason'],'childBusy')
        self.assertEqual((len(result['seenRequestIds']),len(self.starts)),(2,1))
        self.assertEqual(result['legs'][0]['state'],'verified')

    def test_changed_owner_goal_or_checkpoint_stops_before_a_second_lease(self):
        """Immutable policy/owner checks prevent weight reuse under a different contract."""
        def change_after_first(number):
            """Mutate goal bytes after a fully audited first leg."""
            if number==1:write_json(self.goal,dict(goal='changed'))
        self.before_submit=change_after_first
        result=self.run_worker()
        self.assertEqual(len(self.starts),1)
        self.assertEqual(result['state'],'failed')
        self.assertIn('instruction bytes changed',result['reason'])

    def test_owner_replacement_is_terminal_before_the_first_lease(self):
        """A valid reviewed scene cannot authorize another child process or nonce."""
        self.before_submit=lambda _:self.child.update(instanceNonce='c'*32)
        result=self.run_worker()
        self.assertIn('owner changed',result['reason'])
        self.assertFalse(self.starts)

    def test_failed_leg_and_unresolved_cleanup_never_start_a_following_leg(self):
        """The outer worker cannot turn a failed resident into an automatic retry."""
        self.episode_code=1
        result=self.run_worker()
        self.assertEqual(len(self.starts),1)
        self.assertEqual(result['state'],'failed')
        self.assertEqual(len(result['legs']),1)
        self.assertEqual(result['legs'][0]['state'],'failed')
        self.assertEqual(result['legs'][0]['residentStatus'],'failed')
        self.assertEqual(result['legs'][0]['runId'],self.episodes[0][3])

    def test_unadmitted_guard_cannot_convert_a_zero_episode_code_into_route_success(self):
        """Missing native health admission stays terminal even if an episode seam incorrectly returns zero."""
        self.admit_guard=False
        result=self.run_worker()
        self.assertEqual((result['state'],result['legs'][0]['state']),('failed','failed'))
        self.assertEqual((len(self.starts),len(self.episodes),len(self.audits)),(1,1,0))
        report=json.loads((Path(result['legs'][0]['directory'])/'patrol.json').read_bytes())
        self.assertEqual(report['failedLeases'],1)
        self.assertFalse(report['scoutEncounterGuardState']['admitted'])

    def test_guard_trip_keeps_terminal_accounting_and_cannot_retry_or_verify_route(self):
        """The retained hazard and failed archive remain bound to the one original native lease."""
        from test_scout_encounter_guard import sample
        self.recording_payload=b'hazard evidence bytes'
        self.after_episode=lambda number,control:control.scout_encounter_guard.observe(sample(2,health=.5),3)
        result=self.run_worker()
        self.assertEqual((result['state'],len(self.starts),len(self.episodes),len(self.audits)),('failed',1,1,0))
        self.assertEqual(result['recordedBytes'],len(self.recording_payload))
        self.assertTrue(result['recordedBytesComplete'])
        report=json.loads((Path(result['legs'][0]['directory'])/'patrol.json').read_bytes())
        self.assertEqual(report['failedLeases'],1)
        self.assertEqual(report['scoutEncounterGuardState']['trip']['reason'],'reviewedHealthFractionDrop')

    def test_resealed_guard_baseline_cannot_replace_original_review_health_in_audit(self):
        """Resealing derived request/reuse files never changes the original manually inspected HP values."""
        from audit_hybrid_run import verify_policy_reuse
        from scout_encounter_guard import binding_from_review
        self.target=1;result=self.run_worker()
        output=Path(result['legs'][0]['directory'])/'patrol.json'
        report=json.loads(output.read_bytes());reuse=report['policyReuse']
        request_path=Path(reuse['requestFile']);request=json.loads(request_path.read_bytes())
        changed=binding_from_review(dict(inspectedHealth=1000,inspectedMaximumHealth=2700),request['reviewSha256'])
        request['scoutEncounterGuard']=changed;write_json(request_path,request)
        reuse.update(scoutEncounterGuard=changed,requestSha256=hashlib.sha256(request_path.read_bytes()).hexdigest())
        proof=Path(str(output)+'.reuse.json');write_json(proof,reuse)
        report.update(scoutEncounterGuard=changed,policyReuseSha256=hashlib.sha256(proof.read_bytes()).hexdigest())
        with patch.object(runtime,'OPEN_P2P_SHA256',scout.OPEN_P2P_SHA256):
            with self.assertRaisesRegex(ValueError,'baseline differs from the original review'):
                verify_policy_reuse(report,output,proof)

    def test_raised_failed_resident_keeps_original_run_bytes_and_terminal_state(self):
        """Mirror a real obstacle exception after the resident archive has been written and closed."""
        self.episode_error='hybrid_navigation:survey_obstacle_requires_inspection'
        self.recording_payload=b'preserved failed recording'*137
        result=self.run_worker()
        row=result['legs'][0]
        self.assertEqual((result['state'],row['state'],row['residentStatus']),('failed','failed','failed'))
        self.assertEqual((row['runId'],row['residentError']),(self.episodes[0][3],self.episode_error))
        self.assertEqual((row['recordedBytes'],result['recordedBytes']),(len(self.recording_payload),)*2)
        self.assertTrue(result['recordedBytesComplete'])
        self.assertTrue(row['modelReused'])
        self.assertEqual((len(self.loads),len(self.starts),len(self.episodes),len(self.audits)),(1,1,1,0))
        self.assertEqual((Path(self.episodes[0][0].record_dir)/'synthetic-recording.bin').read_bytes(),self.recording_payload)
        self.assertEqual(row['datasetSplit'],'diagnostic')
        self.assertEqual(read_split(Path(row['directory']),row['runId'])['split'],'diagnostic')

    def obstacle_driver(self, watch):
        """Supply each recovery request explicitly only after observing the retained failed boundary."""
        state=json.loads((watch.folder/'session.json').read_bytes())
        if state['state']!='awaitingReview':return
        if len(state['legs'])>=self.target:
            watch.reason='operatorStop'
            return
        if any(path.stem not in state['seenRequestIds'] for path in (watch.folder/'requests').glob('*.json')):return
        number=len(state['legs'])
        self.episode_error=scout.OBSTACLE_ERROR if number in self.obstacle_failures else None
        self.before_submit(number)
        route=(scout.SCOUT_GRASS_ROUTE,scout.SCOUT_GROVE_ROUTE)[number%2]
        review=self.make_review(route)
        self.recovery_review_mutation(number,review,state)
        scout.submit(watch.folder,review)

    def synthetic_prefix_audit(self, folder, request):
        """Isolate worker lifecycle tests; the separate prefix suite replays complete native/RGB evidence."""
        report,digest=scout.read_json(Path(folder)/'patrol.json')
        self.assertEqual(report['status'],'failed')
        return dict(prefixVerified=True,passed=False,routeCompleted=False,runId=report['runId'],
            requestId=request['requestId'],residentManifestSha256=digest)

    def prepare_obstacle_worker(self):
        """Keep the actual resident control/guard lifetimes while substituting only the inert prefix fixture."""
        import audit_scout_obstacle
        self.settings.allow_inspected_obstacle_recovery=True
        self.obstacle_failures={0}
        self.recording_payload=b'closed failed-or-successful diagnostic recording'
        self.recovery_review_mutation=lambda *args:None
        self.driver=self.obstacle_driver
        self.stack.enter_context(patch.object(audit_scout_obstacle,'audit_failed_prefix',self.synthetic_prefix_audit))

    def test_opt_in_one_failed_prefix_retains_only_policy_and_uses_a_new_guard(self):
        """The real resident creates a different guard/run while the original failed evidence stays failed."""
        self.prepare_obstacle_worker()
        guards=[]
        self.after_episode=lambda number,control:guards.append(control.scout_encounter_guard)
        result=self.run_worker(prefix_auditor=self.synthetic_prefix_audit)
        self.assertEqual([row['state'] for row in result['legs']],['failed','verified'])
        self.assertEqual((len(self.loads),len(self.starts),result['inspectedObstacleRecoveriesUsed']),(1,2,1))
        self.assertIsNot(guards[0],guards[1])
        self.assertTrue(guards[0].snapshot()['armed'])
        self.assertEqual([guard.snapshot()['observations'] for guard in guards],[1,1])
        self.assertEqual(result['legs'][0]['reason'],scout.OBSTACLE_ERROR)
        self.assertFalse(result['legs'][0]['evidenceComplete'])
        self.assertEqual(result['legs'][0]['failedLeases'],1)
        self.assertEqual(result['recordedBytes'],2*len(self.recording_payload))
        self.assertEqual([row['datasetSplit'] for row in result['legs']],['diagnostic','diagnostic'])
        self.assertIsNone(result['pendingObstacleRecovery'])
        requests=[json.loads(path.read_bytes()) for path in (self.settings.directory/'requests').glob('*.json')]
        successor=next(row for row in requests if 'obstacleRecovery' in row)
        self.assertEqual(successor['afterRequestId'],result['legs'][0]['requestId'])
        self.assertEqual(self.audits[0]['policyReuse']['obstacleRecovery'],successor['obstacleRecovery'])

    def test_second_obstacle_exhausts_allowance_without_a_third_lease(self):
        """One reviewed successor cannot make the recovery option an unlimited restart loop."""
        self.prepare_obstacle_worker();self.obstacle_failures={0,1};self.target=3
        result=self.run_worker(prefix_auditor=self.synthetic_prefix_audit)
        self.assertEqual((result['state'],len(self.starts),len(result['legs'])),('failed',2,2))
        self.assertEqual([row['state'] for row in result['legs']],['failed','failed'])
        self.assertEqual(result['inspectedObstacleRecoveriesUsed'],1)

    def test_proven_unsubmitted_obstacle_prediction_is_discarded_without_weight_reload(self):
        """The known choose() exception follows predict(), leaving a non-transmitted history transaction."""
        self.prepare_obstacle_worker()
        self.after_episode=lambda number,control:setattr(self.policy,'_pending_feedback',number==1)
        result=self.run_worker(prefix_auditor=self.synthetic_prefix_audit)
        self.assertEqual([row['state'] for row in result['legs']],['failed','verified'])
        self.assertEqual(len(self.loads),1)
        self.assertFalse(self.policy._pending_feedback)

    def test_stale_or_same_route_recovery_review_is_refused_before_second_lease(self):
        """Fresh bytes alone cannot recycle old native source timestamps or the blocked destination."""
        self.prepare_obstacle_worker()
        def stale(number, review, state):
            """Rewrite the new native source as an old capture while preserving matching file joins."""
            if number!=1:return
            value=json.loads(review.read_bytes());endpoint=Path(value['nativeEndpoint'])
            native=json.loads((endpoint/'result.json').read_bytes())
            for frame in native['observations']+native['stableSamples']:
                frame['sourceFrame']['timestamp100ns']=frame['frameId']*1_000_000
                frame['frameWorldReadiness']['sourceFrame']['timestamp100ns']=frame['frameId']*1_000_000
            write_json(endpoint/'result.json',native)
            metadata_path=endpoint/Path(value['imageName']).with_suffix('.json')
            metadata=json.loads(metadata_path.read_bytes());metadata['sourceFrame']['timestamp100ns']=1_000_000
            write_json(metadata_path,metadata)
        self.recovery_review_mutation=stale
        result=self.run_worker(prefix_auditor=self.synthetic_prefix_audit)
        self.assertEqual(len(self.starts),1)
        self.assertIn('predates completed cleanup',result['reason'])

    def test_same_blocked_geometry_is_not_reissued_after_inspection(self):
        """A newly captured review cannot silently retry the original blocked route."""
        self.prepare_obstacle_worker()
        def same_route(number, review, state):
            """Replace only the synthetic review with a freshly captured original geometry."""
            if number==1:
                replacement=self.make_review(scout.SCOUT_GRASS_ROUTE)
                review.write_bytes(replacement.read_bytes())
        self.recovery_review_mutation=same_route
        result=self.run_worker(prefix_auditor=self.synthetic_prefix_audit)
        self.assertEqual(len(self.starts),1)
        self.assertIn('different route',result['reason'])

    def test_operator_stop_after_failure_never_retains_policy_for_a_successor(self):
        """A simultaneous STOP takes precedence over an otherwise eligible geometric failure."""
        self.prepare_obstacle_worker()
        self.after_episode=lambda number,control:(self.settings.directory/'STOP').write_text('stop')
        result=self.run_worker(prefix_auditor=self.synthetic_prefix_audit)
        self.assertEqual(len(self.starts),1)
        self.assertEqual(result['inspectedObstacleRecoveriesUsed'],0)
        self.assertNotIn('policyRetainedForInspection',result['legs'][0])

    def test_changed_owner_or_goal_after_inspected_stop_cannot_open_the_new_lease(self):
        """Holding weights during inspection never relaxes original native owner or goal identity."""
        self.prepare_obstacle_worker()
        self.before_submit=lambda number:self.child.update(instanceNonce='c'*32) if number==1 else None
        result=self.run_worker(prefix_auditor=self.synthetic_prefix_audit)
        self.assertEqual(len(self.starts),1)
        self.assertIn('owner changed',result['reason'])

    def test_changed_goal_after_inspected_stop_cannot_reuse_loaded_policy(self):
        """Fresh review authority cannot substitute instruction bytes in a retained model."""
        self.prepare_obstacle_worker()
        self.before_submit=lambda number:write_json(self.goal,dict(goal='changed')) if number==1 else None
        result=self.run_worker(prefix_auditor=self.synthetic_prefix_audit)
        self.assertEqual(len(self.starts),1)
        self.assertIn('instruction bytes changed',result['reason'])

    def test_source_changes_and_thermal_stop_remain_terminal_at_the_recovery_boundary(self):
        """Keeping weights does not waive source pinning or the existing thermal supervisor."""
        self.prepare_obstacle_worker()
        original=scout.source_contract();changed=[False]
        self.stack.enter_context(patch.object(scout,'source_contract',lambda:dict(original,changed='yes') if changed[0] else original))
        self.before_submit=lambda number:changed.__setitem__(0,True) if number==1 else None
        result=self.run_worker(prefix_auditor=self.synthetic_prefix_audit)
        self.assertEqual(len(self.starts),1)
        self.assertIn('runtime source changed',result['reason'])

    def test_thermal_stop_during_failed_prefix_cleanup_has_no_recovery_allowance(self):
        """Supervision wins before any policy retention publication or successor submission."""
        self.prepare_obstacle_worker()
        self.after_episode=lambda number,control:setattr(self.watch,'reason','seriesTemperatureStop')
        result=self.run_worker(prefix_auditor=self.synthetic_prefix_audit)
        self.assertEqual((result['state'],result['reason']),('stopped','seriesTemperatureStop'))
        self.assertEqual((len(self.starts),result['inspectedObstacleRecoveriesUsed']),(1,0))

    def test_live_capture_thread_prevents_policy_retention(self):
        """A published failed manifest cannot hide a still-running reader or recorder worker."""
        self.prepare_obstacle_worker()
        finish=threading.Event();threads=[]
        def leak(number, control):
            """Start only an inert local thread whose lifecycle is independently checked."""
            worker=threading.Thread(target=finish.wait,name='synthetic-capture-reader',daemon=True)
            worker.start();threads.append(worker)
        self.after_episode=leak
        try:
            result=self.run_worker(prefix_auditor=self.synthetic_prefix_audit)
            self.assertEqual(len(self.starts),1)
            self.assertIn('threads did not retire',result['reason'])
        finally:
            finish.set()
            for worker in threads:worker.join(2)

    def test_terminal_accounting_preserves_a_conflicting_existing_split(self):
        """A prior reservation cannot be silently overwritten to make a scout result admissible."""
        folder=self.live/'conflicting-reservation'
        report=dict(runId='a'*32,status='completed',recordedBytes=123)
        write_json(folder/'patrol.json',report)
        original=(folder/'patrol.json').read_bytes()
        reserve_split(folder,report['runId'],'holdout')
        row=dict(directory=str(folder),requestId='b'*32,state='verified')
        scout.account_leg(row)
        self.assertEqual(row['state'],'failed')
        self.assertIn('different reserved split',row['accountingError'])
        self.assertEqual(read_split(folder,report['runId'])['split'],'holdout')
        self.assertEqual((folder/'patrol.json').read_bytes(),original)

    def test_success_then_failure_counts_both_archives_once_without_a_third_leg(self):
        """Finalization must neither omit the failed suffix nor double-count an earlier verified leg."""
        self.target=3
        self.recording_payload=b'synthetic bytes'
        self.before_submit=lambda completed:setattr(self,'episode_error','obstacle' if completed==1 else None)
        result=self.run_worker()
        self.assertEqual([row['state'] for row in result['legs']],['verified','failed'])
        self.assertEqual(result['recordedBytes'],2*len(self.recording_payload))
        self.assertTrue(result['recordedBytesComplete'])
        self.assertEqual((len(self.episodes),len(self.audits)),(2,1))

    def test_failure_before_manifest_publication_is_unknown_accounting_not_a_running_leg(self):
        """No original run ID or recording total is invented when the runner never publishes one."""
        def fail(*args,**kwargs):
            """Represent a runner failure before resident initialization."""
            raise RuntimeError('runner initialization failed')
        result=self.run_worker(runner=fail)
        row=result['legs'][0]
        self.assertEqual((result['state'],row['state']),('failed','failed'))
        self.assertIsNone(row['recordedBytes'])
        self.assertNotIn('runId',row)
        self.assertFalse(result['recordedBytesComplete'])
        self.assertTrue(row['accountingError'])
        self.assertEqual((self.starts,self.episodes),([],[]))
        self.assertFalse((Path(row['directory'])/'experience-split.json').exists())

    def test_busy_child_after_success_is_unresolved_cleanup(self):
        """A successful model result does not excuse a still-owned native lease."""
        self.after_episode=lambda *_:self.child.update(taskRunning=True)
        result=self.run_worker()
        self.assertEqual((result['state'],len(self.starts)),('failed',1))
        self.assertIn('cleanup did not release',result['reason'])

    def test_operator_pause_at_leg_end_is_terminal(self):
        """An operator intervention cannot be hidden by a coincidentally successful endpoint."""
        self.after_episode=lambda _,control:runtime.atomic_json(control.path,
            dict(version=1,runId=control.run_id,command='pause'))
        result=self.run_worker()
        self.assertEqual((result['state'],len(self.starts)),('failed',1))
        self.assertIn('Operator stop, pause or goal request',result['reason'])

    def test_cached_goal_queued_during_acquisition_cannot_open_a_native_lease(self):
        """The actual resident must reject a new instruction before starting its first bridge."""
        original_control=runtime.ResidentControl
        controls=[]
        def create_control(*args,**kwargs):
            """Retain the actual control solely to inject a deterministic loading-time request."""
            control=original_control(*args,**kwargs)
            controls.append(control)
            return control
        def queued(args,loader,episode,**kwargs):
            """Deliver the external goal after cached acquisition but before the resident loop."""
            def acquire(current):
                """Keep the real cache validation and inject no new policy or native behavior."""
                policy=loader(current)
                control=controls[-1]
                request=dict(version=1,runId=control.run_id,command='run',goalRequestId='f'*32,
                    goalEmbedding=str(self.root/'replacement.json'),goalIntent='ground-navigation')
                runtime.atomic_json(control.path,request)
                control._observe(request,None)
                return policy
            with patch.object(runtime,'ResidentControl',side_effect=create_control):
                return runtime.run_resident(args,acquire,episode,**kwargs)
        result=self.run_worker(runner=queued)
        self.assertEqual(result['state'],'failed')
        self.assertFalse(self.starts)
        self.assertFalse(self.episodes)
        self.assertEqual(len(self.policy.goals),1)
        self.assertIn('frozen scout request',result['legs'][0]['residentError'])

    def test_unobserved_goal_at_leg_end_cannot_pass_completion_or_start_another_leg(self):
        """A late raw control request is rejected even when no monitor poll has observed it yet."""
        self.after_episode=lambda _,control:runtime.atomic_json(control.path,
            dict(version=1,runId=control.run_id,command='run',goalRequestId='f'*32,
                 goalEmbedding=str(self.root/'replacement.json'),goalIntent='ground-navigation'))
        with patch.object(runtime.ResidentControl,'_monitor',return_value=None):
            result=self.run_worker()
        self.assertEqual((result['state'],len(self.starts),len(self.episodes)),('failed',1,1))
        self.assertFalse(self.audits)
        self.assertEqual(len(self.policy.goals),1)
        self.assertIn('goal request',result['reason'])
        report=json.loads((Path(result['legs'][0]['directory'])/'patrol.json').read_bytes())
        self.assertIsNone(report['goalRequestId'])
        self.assertEqual(report['policyGoalVersion'],0)

    def test_loader_seam_rejects_changed_sampling_before_start(self):
        """Even an internal caller cannot acquire cached weights using altered action settings."""
        def changed(args,loader,episode,**kwargs):
            """Tamper after the worker's argument validation but before the injected loader runs."""
            args.action_hold_ms=101
            return runtime.run_resident(args,loader,episode,**kwargs)
        result=self.run_worker(runner=changed)
        self.assertEqual(result['state'],'failed')
        self.assertFalse(self.starts)

    def test_wrong_start_scope_stale_or_unstable_review_is_rejected(self):
        """A retained PNG and a count of samples cannot bypass native scene admission."""
        manifest=dict(owner=self.owner,routes={scout.SCOUT_GRASS_ROUTE:[list(p) for p in scout.route_points(scout.SCOUT_GRASS_ROUTE)]})
        changes={
            'wrong-start':lambda frame:frame['navigationPose'].update(x=frame['navigationPose']['x']+5),
            'outside-scope':lambda frame:frame['navigationPose'].update(layerId='Unknown'),
            'stale':lambda frame:frame.update(sourceFrameAgeMs=151),
            'wrong-source':lambda frame:frame['frameWorldReadiness']['sourceFrame'].update(captureEpoch='other'),
            'space':lambda frame:frame['motionEvidence'].update(spaceKeyMatched=True),
            'moving':lambda frame:frame['navigationPose'].update(x=frame['navigationPose']['x']+frame['frameId']*.4),
        }
        for name,change in changes.items():
            with self.subTest(name=name):
                path=self.make_review(scout.SCOUT_GRASS_ROUTE)
                result_path=path.parent/'result.json'
                result=json.loads(result_path.read_text())
                for frame in result['stableSamples']+result['observations']:change(frame)
                write_json(result_path,result)
                with self.assertRaises(ValueError):scout.review_evidence(path,manifest,0)

    def test_selected_image_must_be_qualified_and_review_must_be_fresh(self):
        """An initial pre-ready image cannot borrow the later stable observations' authority."""
        manifest=dict(owner=self.owner,routes={scout.SCOUT_GRASS_ROUTE:[list(p) for p in scout.route_points(scout.SCOUT_GRASS_ROUTE)]})
        path=self.make_review(scout.SCOUT_GRASS_ROUTE)
        scout.review_evidence(path,manifest,0)
        with self.assertRaisesRegex(ValueError,'fresh native scene'):
            scout.review_evidence(path,manifest,time.time_ns()+1_000_000)
        result_path=path.parent/'result.json'
        result=json.loads(result_path.read_text())
        pre_ready=copy.deepcopy(result['observations'][0])
        pre_ready['frameId']=pre_ready['navigationPose']['frameId']=0
        pre_ready['frameWorldReadiness'].update(ready=False,sourceFrameId=0)
        result['observations'].insert(0,pre_ready)
        write_json(result_path,result)
        image=json.loads((path.parent/'01-frame-000000000001.json').read_text())
        image.update(frameId=0,sourceFrame=pre_ready['sourceFrame'])
        write_json(path.parent/'01-frame-000000000001.json',image)
        with self.assertRaisesRegex(ValueError,'world-readiness'):
            scout.review_evidence(path,manifest,0)

    def test_checkpoint_replacement_or_pending_history_blocks_next_lease(self):
        """An altered checkpoint cannot be hidden behind an already cached policy object."""
        self.before_submit=lambda number:self.checkpoint.write_bytes(b'replaced checkpoint') if number==1 else None
        result=self.run_worker()
        self.assertEqual(len(self.starts),1)
        self.assertIn('checkpoint or instruction bytes changed',result['reason'])

    def test_repeated_image_polls_keep_raw_evidence_and_require_consistent_provenance(self):
        """A later stale poll can share qualified pixels; conflicting pose/source data cannot."""
        manifest=dict(owner=self.owner,routes={scout.SCOUT_GRASS_ROUTE:[list(p) for p in scout.route_points(scout.SCOUT_GRASS_ROUTE)]})
        path=self.make_review(scout.SCOUT_GRASS_ROUTE)
        result_path=path.parent/'result.json'
        result=json.loads(result_path.read_text())
        repeat=copy.deepcopy(result['observations'][0])
        repeat['sourceFrameAgeMs']=200
        result['observations'].insert(1,repeat)
        write_json(result_path,result)
        scout.review_evidence(path,manifest,0)
        self.assertEqual(len(json.loads(result_path.read_text())['observations']),4)
        for field in ('navigationPose','sourceFrame'):
            with self.subTest(field=field):
                changed=copy.deepcopy(result)
                if field=='navigationPose':changed['observations'][1][field]['yawDegrees']=271
                else:changed['observations'][1][field]['captureEpoch']='different'
                write_json(result_path,changed)
                with self.assertRaises(ValueError):scout.review_evidence(path,manifest,0)


class PolicyIdentityTests(unittest.TestCase):
    """Keep the real policy pin outside the synthetic checkpoint fixture's patched constants."""
    def test_installed_open_p2p_pin_is_distinct_from_landmark_g4(self):
        """The 2,198,488,343-byte policy checkpoint must never inherit the landmark model identity."""
        from landmark_recognizer import G4_SHA256
        self.assertEqual(scout.OPEN_P2P_SHA256,
            '2a3b43121144ca2d9c2b8aa605e313184c98ac5ef6d2c3b530c2d353d886c5bc')
        self.assertEqual(runtime.OPEN_P2P_SHA256,scout.OPEN_P2P_SHA256)
        self.assertNotEqual(scout.OPEN_P2P_SHA256,G4_SHA256)


class SessionLifetimeOptionsTests(unittest.TestCase):
    """Longer idle model retention keeps an explicit hard limit and the existing data cap."""

    def test_default_and_explicit_extended_lifetime(self):
        """The established default remains ten minutes; thirty minutes needs an explicit option."""
        argv=['run','--directory','unused-session','--owner-from','unused-owner.json']
        self.assertEqual(scout.options(argv).seconds,600)
        extended=scout.options(argv+['--seconds','1800'])
        self.assertEqual(extended.seconds,1800)
        self.assertEqual(extended.record_max_mib,160)

    def test_time_and_recording_bounds_remain_required(self):
        """Neither an unbounded service nor a larger recording budget is admitted by this extension."""
        argv=['run','--directory','unused-session','--owner-from','unused-owner.json']
        for extra in (['--seconds','29'],['--seconds','1801'],['--record-max-mib','161']):
            with self.subTest(extra=extra),redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                scout.options(argv+extra)


class SessionWatchTests(unittest.TestCase):
    """Exercise real idle/active thermal and STOP supervision using a fake owner guard."""
    def setUp(self):
        """Replace only endpoint discovery and GPU telemetry; use actual monitor threads."""
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        self.folder=Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.series=SimpleNamespace(required_identity=None,admit=lambda *args:None,finished=threading.Event(),
            stop_reason=lambda:'operatorStop' if (self.folder/'STOP').exists() else None,binding=lambda:'synthetic')
        self.stack.enter_context(patch.object(scout,'SeriesGuard',return_value=self.series))
        self.stack.enter_context(patch.object(scout,'owner_pair',return_value=({},{})))
        self.stack.enter_context(patch.object(scout.patrol,'POLL_SECONDS',.01))
        self.stack.enter_context(patch.object(scout.patrol,'CONTROL_POLL_SECONDS',.005))
        self.watch=scout.SessionWatch(self.folder,SimpleNamespace(seconds=30,nvidia_smi='synthetic'),{},None)
        self.addCleanup(self.watch.close)

    def test_hot_or_unavailable_initial_telemetry_blocks_loading(self):
        """No GPU policy may load when the first thermal sample is unsafe or absent."""
        with patch.object(scout.patrol,'log_sample',return_value=dict(temperatureC=78)):
            with self.assertRaisesRegex(RuntimeError,'temperatureLimit'):self.watch.start()
        with patch.object(scout.patrol,'log_sample',return_value=dict(temperatureC=40)):
            self.watch._sample()
        with self.assertRaisesRegex(RuntimeError,'temperatureLimit'):self.watch.check()

    def test_idle_telemetry_loss_is_terminal_even_after_recovery(self):
        """A later good sample cannot re-enable an idle worker after telemetry loss."""
        with patch.object(scout.patrol,'log_sample',return_value=dict(error='synthetic unavailable')):
            self.watch._sample()
        with self.assertRaisesRegex(RuntimeError,'telemetryLost'):self.watch.check()

    def test_idle_stop_is_latched_and_never_opens_a_lease(self):
        """Removing a STOP sentinel cannot turn a stopped worker back into a request listener."""
        (self.folder/'STOP').touch()
        with self.assertRaisesRegex(RuntimeError,'operatorStop'):self.watch.check()
        (self.folder/'STOP').unlink()
        with self.assertRaisesRegex(RuntimeError,'operatorStop'):self.watch.check()
        self.assertIsNone(self.watch.active)

    def test_stop_reaches_active_run_while_thermal_sample_is_blocked(self):
        """The independent control thread keeps STOP responsive during a slow GPU query."""
        blocked,release=threading.Event(),threading.Event()
        samples=[]
        def sample(*args):
            """Block the second synthetic query until the assertion releases it."""
            samples.append(1)
            if len(samples)>1:
                blocked.set()
                release.wait(1)
            return dict(temperatureC=55)
        leg=self.folder/'leg'
        leg.mkdir()
        run_id='d'*32
        write_json(leg/'patrol.json.status.json',dict(version=1,runId=run_id))
        write_json(leg/'patrol.json.control.json',dict(version=1,runId=run_id,command='run'))
        with patch.object(scout.patrol,'log_sample',side_effect=sample):
            try:
                self.watch.activate(leg)
                self.watch.start()
                self.assertTrue(blocked.wait(.5))
                (self.folder/'STOP').touch()
                deadline=time.monotonic()+.5
                while time.monotonic()<deadline:
                    if scout.patrol.addressed_control(leg/'patrol.json.control.json',run_id)['command']=='stop':break
                    time.sleep(.005)
                self.assertEqual(scout.patrol.addressed_control(leg/'patrol.json.control.json',run_id)['command'],'stop')
            finally:
                release.set()
                self.watch.close()


if __name__=='__main__':
    unittest.main()
