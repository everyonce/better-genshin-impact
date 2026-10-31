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


if __name__=='__main__':unittest.main()
