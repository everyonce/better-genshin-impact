"""Explicit native localization scopes; profile selection never grants input authority."""
import math
from hybrid_routes import COURTYARD_ROUTE,ROUTE_IDS,SURFACE_ROUTES,SCOUT_ROUTES,route_points

COURTYARD_PROFILE='mondstadt-courtyard-hybrid-v1'
SURFACE_PROFILE='mondstadt-surface-hybrid-v1'
SCOUT_PROFILE='mondstadt-combat-scout-v1'
NORTH_SCOUT_PROFILE='mondstadt-north-combat-scout-v1'
WINDRISE_RECOVERY_PROFILE='windrise-statue-recovery-v1'
SCOUT_PROFILES=(SCOUT_PROFILE,NORTH_SCOUT_PROFILE)
# Generic model/route admission remains restricted to its existing four profiles.
NAVIGATION_PROFILES=(COURTYARD_PROFILE,SURFACE_PROFILE,*SCOUT_PROFILES)
LOCALIZATION_PROFILES=(*NAVIGATION_PROFILES,WINDRISE_RECOVERY_PROFILE)
SURFACE_BOUNDS=dict(minX=-1100,maxX=-820,minY=2100,maxY=2350)
SCOUT_BOUNDS=dict(minX=-1350,maxX=-980,minY=2050,maxY=2480)
SCOUT_ANCHOR=dict(x=-1165,y=2265)
NORTH_SCOUT_BOUNDS=dict(minX=-1500,maxX=-1130,minY=2430,maxY=2860)
NORTH_SCOUT_ANCHOR=dict(x=-1315,y=2645)
WINDRISE_BOUNDS=dict(minX=-1272,maxX=-1260,minY=1922,maxY=1940)
WINDRISE_ANCHOR=dict(x=-1266,y=1931)
SURFACE_LAYERS=('City_102','MapBack_2')


def scout_scope(profile):
    """Return detached bounds and anchor for one explicitly selected local scouting scope."""
    if profile==SCOUT_PROFILE:return dict(SCOUT_BOUNDS),dict(SCOUT_ANCHOR)
    if profile==NORTH_SCOUT_PROFILE:return dict(NORTH_SCOUT_BOUNDS),dict(NORTH_SCOUT_ANCHOR)
    raise ValueError('Unknown local scouting profile')


def required_profile(route_id):
    """A fixed route selects exactly one scope; a broader profile is never an implicit substitute."""
    if route_id not in ROUTE_IDS:raise ValueError('Unknown fixed navigation route')
    if route_id in SURFACE_ROUTES:return SURFACE_PROFILE
    if route_id in SCOUT_ROUTES:return SCOUT_PROFILE
    return COURTYARD_PROFILE


def validate_capability(capability,profile):
    """Refuse implicit upgrades, changed thresholds, or broader advertised surface bounds."""
    expected=dict(version=1,profileId=profile,sameFrame=True,readOnly=True)
    if profile not in LOCALIZATION_PROFILES or any(capability.get(key)!=value for key,value in expected.items()):
        raise ValueError('The bridge does not advertise the requested same-frame navigation profile')
    start,end=route_points(COURTYARD_ROUTE)
    if (tuple(capability.get('start',{}).get(key) for key in ('x','y'))!=start
            or tuple(capability.get('end',{}).get(key) for key in ('x','y'))!=end):
        raise ValueError('The fixed courtyard geometry differs')
    # Windrise is perception-only here: it never joins the scout route registry or grants input.
    bounds,anchor=(WINDRISE_BOUNDS,WINDRISE_ANCHOR) if profile==WINDRISE_RECOVERY_PROFILE else (
        scout_scope(profile) if profile in SCOUT_PROFILES else (SURFACE_BOUNDS,None))
    layers=['MapBack_2'] if profile==WINDRISE_RECOVERY_PROFILE else list(SURFACE_LAYERS)
    if profile in (SURFACE_PROFILE,*SCOUT_PROFILES,WINDRISE_RECOVERY_PROFILE) and (capability.get('allowedLayerIds')!=layers
            or capability.get('bounds')!=bounds or capability.get('minimumPositionConfidence')!=.99
            or capability.get('minimumYawConfidence')!=.2 or capability.get('maxWidth')!=1920
            or capability.get('maxHeight')!=1080 or capability.get('normalIsGroundedProof') is not False):
        raise ValueError('The bounded surface navigation contract differs')
    if profile in (*SCOUT_PROFILES,WINDRISE_RECOVERY_PROFILE) and (capability.get('searchAnchor')!=anchor or capability.get('localOnly') is not True):
        raise ValueError('The fixed local scouting anchor differs')


def allows_pose_scope(pose,profile):
    """Check layer and finite world coordinates independently of route and confidence checks."""
    if any(type(pose.get(key)) not in (int,float) or not math.isfinite(pose[key]) for key in ('x','y')):
        return False
    if profile==COURTYARD_PROFILE:return pose.get('layerId')=='City_102'
    bounds=WINDRISE_BOUNDS if profile==WINDRISE_RECOVERY_PROFILE else (
        scout_scope(profile)[0] if profile in SCOUT_PROFILES else SURFACE_BOUNDS)
    layers=('MapBack_2',) if profile==WINDRISE_RECOVERY_PROFILE else SURFACE_LAYERS
    return (profile in (SURFACE_PROFILE,*SCOUT_PROFILES,WINDRISE_RECOVERY_PROFILE) and pose.get('layerId') in layers
            and bounds['minX']<=pose['x']<=bounds['maxX']
            and bounds['minY']<=pose['y']<=bounds['maxY'])
