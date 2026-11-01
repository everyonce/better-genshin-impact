"""Inert Windrise perception scope checks; no model, operating-system bridge or game is started."""
from contextlib import redirect_stderr
import copy
import io
import time
from types import SimpleNamespace
import unittest

from hybrid_navigation import HybridNavigation
from hybrid_routes import ROUTE_IDS
import navigation_profiles as profiles
from probe_camera_response import Experiment,qualified
from reviewed_scout_route import ReviewedScoutRoute,reviewed_route_policy
from run_rdp_patrol import options as patrol_options
from scout_session import options as scout_options
from stream_client import validate_navigation_scope_options
from survey_surface_camera import turn_to
from test_navigation_profiles import surface_capability
from test_probe_camera_response import CameraBridge


PROFILE=profiles.WINDRISE_RECOVERY_PROFILE
SPAWN=(-1266.435546875,1934.080078125)


def windrise_capability():
    """Mirror the exact native read-only capability while retaining the old courtyard bearing anchors."""
    return dict(surface_capability(),profileId=PROFILE,allowedLayerIds=['MapBack_2'],
                bounds=dict(profiles.WINDRISE_BOUNDS),searchAnchor=dict(profiles.WINDRISE_ANCHOR),localOnly=True)


class WindriseScopeTests(unittest.TestCase):
    """A new geofence can qualify camera perception without silently adding route or model authority."""
    def test_exact_native_capability_and_each_immutable_field(self):
        """Refuse broader bounds/layers, shifted anchors, weak thresholds or another profile."""
        expected=windrise_capability();profiles.validate_capability(expected,PROFILE)
        self.assertEqual(PROFILE,'windrise-statue-recovery-v1')
        self.assertEqual(expected['bounds'],dict(minX=-1272,maxX=-1260,minY=1922,maxY=1940))
        self.assertEqual(expected['searchAnchor'],dict(x=-1266,y=1931))
        for mutation in (dict(profileId=profiles.SCOUT_PROFILE),dict(profileId=PROFILE+' '),
                dict(bounds=dict(profiles.WINDRISE_BOUNDS,maxY=1941)),
                dict(searchAnchor=dict(x=-1266,y=1932)),dict(localOnly=False),
                dict(allowedLayerIds=['City_102','MapBack_2']),dict(allowedLayerIds=['City_102']),
                dict(minimumPositionConfidence=.98),dict(minimumYawConfidence=.19),
                dict(maxWidth=3840),dict(maxHeight=2160),dict(normalIsGroundedProof=True),
                dict(readOnly=False),dict(sameFrame=False),dict(start=dict(x=-1266,y=1931))):
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                profiles.validate_capability(expected|mutation,PROFILE)
        for field in ('bounds','searchAnchor','localOnly','allowedLayerIds'):
            changed=copy.deepcopy(expected);changed.pop(field)
            with self.subTest(missing=field),self.assertRaises(ValueError):profiles.validate_capability(changed,PROFILE)

    def test_bounds_layers_and_finite_coordinates(self):
        """Only the exact small outdoor rectangle qualifies; city and arbitrary world maps stay excluded."""
        for x in (-1272,-1260):
            for y in (1922,1940):self.assertTrue(profiles.allows_pose_scope(dict(x=x,y=y,layerId='MapBack_2'),PROFILE))
        pose=dict(x=SPAWN[0],y=SPAWN[1],layerId='MapBack_2')
        self.assertTrue(profiles.allows_pose_scope(pose,PROFILE))
        for change in (dict(x=-1272.001),dict(x=-1259.999),dict(y=1921.999),dict(y=1940.001),
                dict(x=float('nan')),dict(y=float('inf')),dict(x=True),dict(y='1931'),
                dict(layerId='City_102'),dict(layerId='MapBack_1'),dict(layerId=None)):
            with self.subTest(change=change):self.assertFalse(profiles.allows_pose_scope(pose|change,PROFILE))
        for old in profiles.NAVIGATION_PROFILES:self.assertFalse(profiles.allows_pose_scope(pose,old))

    def test_scout_and_generic_model_admission_remain_unchanged(self):
        """No existing route/model worker may opt into the perception-only scope as an implicit upgrade."""
        self.assertEqual(profiles.NAVIGATION_PROFILES,(profiles.COURTYARD_PROFILE,profiles.SURFACE_PROFILE,
            profiles.SCOUT_PROFILE,profiles.NORTH_SCOUT_PROFILE))
        self.assertNotIn(PROFILE,profiles.SCOUT_PROFILES)
        self.assertIn(PROFILE,profiles.LOCALIZATION_PROFILES)
        for check in (lambda:profiles.scout_scope(PROFILE),lambda:reviewed_route_policy(PROFILE),
                      lambda:ReviewedScoutRoute((SPAWN,(-1266,1932)),PROFILE),
                      lambda:validate_navigation_scope_options(SimpleNamespace(navigation_profile=PROFILE,
                          navigation_guidance=True,hybrid_navigation=False))):
            with self.assertRaises(ValueError):check()
        for route in ROUTE_IDS:
            self.assertNotEqual(profiles.required_profile(route),PROFILE)
            with self.subTest(route=route),self.assertRaises(ValueError):
                HybridNavigation(windrise_capability(),route,navigation_profile=PROFILE)
        with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            patrol_options(['--navigation-profile',PROFILE])
        with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            scout_options(['run','--directory','unused','--owner-from','unused','--navigation-profile',PROFILE])

    def test_existing_camera_controller_uses_real_receipts_and_no_keys(self):
        """The established signed feedback loop can operate at the new geofence without a model or movement."""
        bridge=CameraBridge();bridge.yaw=269.5
        bridge.alter=lambda frame:frame['navigationPose'].update(x=SPAWN[0],y=SPAWN[1],layerId='MapBack_2')
        report=dict(observations=[],actions=[],receipts=[])
        trial=Experiment(bridge,report,station=SPAWN,profile=PROFILE,seconds=35)
        turn_to(trial,95.43226074135671)
        self.assertLessEqual(abs(report['finalYawDegrees']-95.43226074135671),3)
        self.assertEqual(len(bridge.issued),len(report['receipts']))
        self.assertGreater(len(bridge.issued),0)
        for request in bridge.issued:
            step=request['steps'][0]
            self.assertEqual(len(request['steps']),1)
            self.assertEqual(step['keys'],[])
            self.assertEqual((step['mouseDy'],step['durationMs']),(0,100))
            self.assertLessEqual(abs(step['mouseDx']),250)
        self.assertIsNone(trial.pending)

    def test_camera_freshness_and_position_guards_are_not_weakened(self):
        """New scope still requires same-frame readiness, strict source age and stable body position."""
        bridge=CameraBridge()
        bridge.alter=lambda frame:frame['navigationPose'].update(x=SPAWN[0],y=SPAWN[1],layerId='MapBack_2')
        frame,_=bridge.request('frame')
        frame.update(clientReceivedNs=time.perf_counter_ns(),transportRoundTripMs=0,frameQuality='usable')
        self.assertTrue(qualified(frame,PROFILE))
        for mutate in (lambda row:row.update(serverNowMs=row['sourceFrame']['freshnessAtMs']+151),
                       lambda row:row['navigationPose'].update(positionConfidence=.989),
                       lambda row:row['navigationPose'].update(yawConfidence=.199),
                       lambda row:row['frameWorldReadiness'].update(ready=False),
                       lambda row:row['motionEvidence'].update(status='climb'),
                       lambda row:row['navigationPose'].update(frameId=999)):
            row=copy.deepcopy(frame);mutate(row)
            with self.subTest(mutate=mutate):self.assertFalse(qualified(row,PROFILE))
        report=dict(observations=[],actions=[],receipts=[])
        trial=Experiment(bridge,report,station=SPAWN,profile=PROFILE,seconds=35)
        trial.pulse(-75)
        count=len(bridge.issued)
        bridge.alter=lambda row:row['navigationPose'].update(x=SPAWN[0]+.36,y=SPAWN[1],layerId='MapBack_2')
        with self.assertRaisesRegex(ValueError,'body position changed'):trial.pulse(-75)
        self.assertEqual(len(bridge.issued),count)


if __name__=='__main__':unittest.main()
