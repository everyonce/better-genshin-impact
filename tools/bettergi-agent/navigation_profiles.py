"""Explicit native localization scopes; profile selection never grants input authority."""
import math
from hybrid_routes import COURTYARD_ROUTE,ROUTE_IDS,SURFACE_ROUTES,SCOUT_ROUTES,route_points

COURTYARD_PROFILE='mondstadt-courtyard-hybrid-v1'
SURFACE_PROFILE='mondstadt-surface-hybrid-v1'
SCOUT_PROFILE='mondstadt-combat-scout-v1'
NAVIGATION_PROFILES=(COURTYARD_PROFILE,SURFACE_PROFILE,SCOUT_PROFILE)
SURFACE_BOUNDS=dict(minX=-1100,maxX=-820,minY=2100,maxY=2350)
SCOUT_BOUNDS=dict(minX=-1350,maxX=-980,minY=2050,maxY=2480)
SCOUT_ANCHOR=dict(x=-1165,y=2265)
SURFACE_LAYERS=('City_102','MapBack_2')


def required_profile(route_id):
    """A fixed route selects exactly one scope; a broader profile is never an implicit substitute."""
    if route_id not in ROUTE_IDS:raise ValueError('Unknown fixed navigation route')
    if route_id in SURFACE_ROUTES:return SURFACE_PROFILE
    if route_id in SCOUT_ROUTES:return SCOUT_PROFILE
    return COURTYARD_PROFILE


def validate_capability(capability,profile):
    """Refuse implicit upgrades, changed thresholds, or broader advertised surface bounds."""
    expected=dict(version=1,profileId=profile,sameFrame=True,readOnly=True)
    if profile not in NAVIGATION_PROFILES or any(capability.get(key)!=value for key,value in expected.items()):
        raise ValueError('The bridge does not advertise the requested same-frame navigation profile')
    start,end=route_points(COURTYARD_ROUTE)
    if (tuple(capability.get('start',{}).get(key) for key in ('x','y'))!=start
            or tuple(capability.get('end',{}).get(key) for key in ('x','y'))!=end):
        raise ValueError('The fixed courtyard geometry differs')
    bounds=SCOUT_BOUNDS if profile==SCOUT_PROFILE else SURFACE_BOUNDS
    if profile in (SURFACE_PROFILE,SCOUT_PROFILE) and (capability.get('allowedLayerIds')!=list(SURFACE_LAYERS)
            or capability.get('bounds')!=bounds or capability.get('minimumPositionConfidence')!=.99
            or capability.get('minimumYawConfidence')!=.2 or capability.get('maxWidth')!=1920
            or capability.get('maxHeight')!=1080 or capability.get('normalIsGroundedProof') is not False):
        raise ValueError('The bounded surface navigation contract differs')
    if profile==SCOUT_PROFILE and (capability.get('searchAnchor')!=SCOUT_ANCHOR or capability.get('localOnly') is not True):
        raise ValueError('The fixed local scouting anchor differs')


def allows_pose_scope(pose,profile):
    """Check layer and finite world coordinates independently of route and confidence checks."""
    if any(type(pose.get(key)) not in (int,float) or not math.isfinite(pose[key]) for key in ('x','y')):
        return False
    if profile==COURTYARD_PROFILE:return pose.get('layerId')=='City_102'
    bounds=SCOUT_BOUNDS if profile==SCOUT_PROFILE else SURFACE_BOUNDS
    return (profile in (SURFACE_PROFILE,SCOUT_PROFILE) and pose.get('layerId') in SURFACE_LAYERS
            and bounds['minX']<=pose['x']<=bounds['maxX']
            and bounds['minY']<=pose['y']<=bounds['maxY'])
