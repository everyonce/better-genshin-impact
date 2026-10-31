"""Inert regressions for the explicit city-to-surface localization boundary."""
import copy
import io
import unittest
from contextlib import redirect_stderr

from hybrid_navigation import HybridNavigation,START,END
from hybrid_routes import BRIDGE_APPROACH_ROUTE,SCOUT_ENTRY_ROUTE,route_points,route_heading
from navigation_profiles import (COURTYARD_PROFILE,SURFACE_PROFILE,SCOUT_PROFILE,SURFACE_BOUNDS,SCOUT_BOUNDS,
                                SCOUT_ANCHOR,SURFACE_LAYERS,validate_capability,allows_pose_scope,required_profile)
from test_hybrid_navigation import capability,frame,proposal
from run_rdp_patrol import options,patrol_argv
from pathlib import Path


def surface_capability():
    """Mirror the versioned native scope contract without opening a bridge or game process."""
    result=capability()
    result.update(profileId=SURFACE_PROFILE,allowedLayerIds=list(SURFACE_LAYERS),bounds=dict(SURFACE_BOUNDS),
        minimumPositionConfidence=.99,minimumYawConfidence=.2,maxWidth=1920,maxHeight=1080,normalIsGroundedProof=False)
    return result


def route_capability(route):
    """Give fixed-route fixtures the exact scope required by the production admission boundary."""
    profile=required_profile(route)
    if profile==COURTYARD_PROFILE:return capability()
    result=surface_capability()
    if profile==SCOUT_PROFILE:
        result.update(profileId=SCOUT_PROFILE,bounds=dict(SCOUT_BOUNDS),searchAnchor=dict(SCOUT_ANCHOR),localOnly=True)
    return result


def gate_frame(index):
    """Use the retained outdoor gate location with independently derived original-anchor bearings."""
    item=frame(index,index*100,point=route_points(BRIDGE_APPROACH_ROUTE)[0],yaw=14)
    pose=item['navigationPose']
    pose.update(layerId='MapBack_2',headingToStartDegrees=int(route_heading(pose,START)),
                headingToEndDegrees=int(route_heading(pose,END)))
    return item


class NavigationProfileTests(unittest.TestCase):
    def test_outdoor_pose_requires_explicit_profile_and_can_keep_native_route_guidance(self):
        default=HybridNavigation(capability())
        self.assertEqual(default.prepare(gate_frame(1)),'poseUnqualified')
        with self.assertRaises(ValueError):HybridNavigation(capability(),BRIDGE_APPROACH_ROUTE)
        with self.assertRaises(ValueError):HybridNavigation(surface_capability(),BRIDGE_APPROACH_ROUTE)
        surface=HybridNavigation(surface_capability(),BRIDGE_APPROACH_ROUTE,navigation_profile=SURFACE_PROFILE)
        for index in (1,2,3):surface.prepare(gate_frame(index))
        self.assertEqual(surface.snapshot()['profileId'],SURFACE_PROFILE)
        self.assertEqual(surface.choose(gate_frame(3),proposal(['W']))['step']['keys'],['W'])

    def test_changed_layer_bounds_confidence_and_anchor_contracts_are_rejected(self):
        for change in (dict(bounds=dict(SURFACE_BOUNDS,minX=-1200)),dict(allowedLayerIds=['MapBack_2']),
                       dict(minimumPositionConfidence=.98),dict(start=dict(x=0,y=0))):
            contract=surface_capability()
            contract.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):validate_capability(contract,SURFACE_PROFILE)
        for change in (dict(layerId='MapBack_1'),dict(positionConfidence=.989),dict(yawConfidence=.199),dict(x=-1100.01)):
            nav=HybridNavigation(surface_capability(),BRIDGE_APPROACH_ROUTE,navigation_profile=SURFACE_PROFILE)
            item=gate_frame(1)
            item['navigationPose'].update(change)
            self.assertEqual(nav.prepare(item),'poseUnqualified')

    def test_launcher_cannot_silently_upgrade_an_existing_route(self):
        for flags in (['--route',BRIDGE_APPROACH_ROUTE,'--legs','1'],['--navigation-profile',SURFACE_PROFILE]):
            with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):options(flags)
        args=options(['--route',BRIDGE_APPROACH_ROUTE,'--legs','1','--navigation-profile',SURFACE_PROFILE])
        command=patrol_argv(args,3,Path('unused'))
        self.assertEqual(command[command.index('--navigation-profile')+1],SURFACE_PROFILE)

    def test_scouting_is_separate_from_both_existing_route_scopes(self):
        contract=surface_capability()
        contract.update(profileId=SCOUT_PROFILE,bounds=dict(SCOUT_BOUNDS),searchAnchor=dict(SCOUT_ANCHOR),localOnly=True)
        validate_capability(contract,SCOUT_PROFILE)
        self.assertEqual(required_profile(SCOUT_ENTRY_ROUTE),SCOUT_PROFILE)
        for route in (BRIDGE_APPROACH_ROUTE,'mondstadt-courtyard-hybrid-v1'):
            with self.assertRaises(ValueError):HybridNavigation(contract,route,navigation_profile=SCOUT_PROFILE)
        nav=HybridNavigation(contract,SCOUT_ENTRY_ROUTE,navigation_profile=SCOUT_PROFILE)
        self.assertEqual(nav.snapshot()['profileId'],SCOUT_PROFILE)
        for change in (dict(bounds=dict(SCOUT_BOUNDS,minX=-1351)),dict(searchAnchor=dict(x=-1164,y=2265)),dict(localOnly=False)):
            with self.subTest(change=change),self.assertRaises(ValueError):validate_capability(dict(contract,**change),SCOUT_PROFILE)
        point=dict(x=-1165,y=2265,layerId='MapBack_2')
        self.assertTrue(allows_pose_scope(point,SCOUT_PROFILE))
        self.assertFalse(allows_pose_scope(point,SURFACE_PROFILE))
        self.assertFalse(allows_pose_scope(dict(point,x=-1350.01),SCOUT_PROFILE))
        with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            options(['--route',SCOUT_ENTRY_ROUTE,'--legs','1','--navigation-profile',SURFACE_PROFILE])
        args=options(['--route',SCOUT_ENTRY_ROUTE,'--legs','1','--navigation-profile',SCOUT_PROFILE])
        self.assertEqual(args.navigation_profile,SCOUT_PROFILE)


if __name__=='__main__':unittest.main()
