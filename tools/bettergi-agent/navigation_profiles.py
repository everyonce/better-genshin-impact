"""Explicit native localization scopes; profile selection never grants input authority."""
import math
from hybrid_routes import COURTYARD_ROUTE,route_points

COURTYARD_PROFILE='mondstadt-courtyard-hybrid-v1'
SURFACE_PROFILE='mondstadt-surface-hybrid-v1'
NAVIGATION_PROFILES=(COURTYARD_PROFILE,SURFACE_PROFILE)
SURFACE_BOUNDS=dict(minX=-1100,maxX=-820,minY=2100,maxY=2350)
SURFACE_LAYERS=('City_102','MapBack_2')


def validate_capability(capability,profile):
    """Refuse implicit upgrades, changed thresholds, or broader advertised surface bounds."""
    expected=dict(version=1,profileId=profile,sameFrame=True,readOnly=True)
    if profile not in NAVIGATION_PROFILES or any(capability.get(key)!=value for key,value in expected.items()):
        raise ValueError('The bridge does not advertise the requested same-frame navigation profile')
    start,end=route_points(COURTYARD_ROUTE)
    if (tuple(capability.get('start',{}).get(key) for key in ('x','y'))!=start
            or tuple(capability.get('end',{}).get(key) for key in ('x','y'))!=end):
        raise ValueError('The fixed courtyard geometry differs')
    if profile==SURFACE_PROFILE and (capability.get('allowedLayerIds')!=list(SURFACE_LAYERS)
            or capability.get('bounds')!=SURFACE_BOUNDS or capability.get('minimumPositionConfidence')!=.99
            or capability.get('minimumYawConfidence')!=.2 or capability.get('maxWidth')!=1920
            or capability.get('maxHeight')!=1080 or capability.get('normalIsGroundedProof') is not False):
        raise ValueError('The bounded surface navigation contract differs')


def allows_pose_scope(pose,profile):
    """Check layer and finite world coordinates independently of route and confidence checks."""
    if any(type(pose.get(key)) not in (int,float) or not math.isfinite(pose[key]) for key in ('x','y')):
        return False
    if profile==COURTYARD_PROFILE:return pose.get('layerId')=='City_102'
    return (profile==SURFACE_PROFILE and pose.get('layerId') in SURFACE_LAYERS
            and SURFACE_BOUNDS['minX']<=pose['x']<=SURFACE_BOUNDS['maxX']
            and SURFACE_BOUNDS['minY']<=pose['y']<=SURFACE_BOUNDS['maxY'])
