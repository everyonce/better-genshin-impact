"""Reviewed local routes in BetterGI's City_102 world-coordinate plane."""
import math


COURTYARD_ROUTE = 'mondstadt-courtyard-hybrid-v1'
LAMPPOST_ROUTE = 'mondstadt-lamppost-v1'
PLANTER_ROUTE = 'mondstadt-planter-v1'
STAIR_POST_ROUTE = 'mondstadt-stair-post-v1'
ROUTE_IDS = (COURTYARD_ROUTE, LAMPPOST_ROUTE, PLANTER_ROUTE, STAIR_POST_ROUTE)

# The default segment is also advertised as the bridge's native heading anchors.
_POINTS = {
    COURTYARD_ROUTE: ((-867.7041015625, 2281.378173828125), (-874.3662109375, 2274.179931640625)),
    # Surveyed level road on either side of the fixed pavement lamp and planter.
    LAMPPOST_ROUTE: ((-858.70, 2263.65), (-846.30078125, 2261.13671875)),
    # Sidewalk by the stone stairs, with a flower box between the two ends.
    PLANTER_ROUTE: ((-844.625, 2260.4599609375), (-840.55, 2252.43)),
    # The stone end post blocks the direct line. Its left side opens onto the street.
    STAIR_POST_ROUTE: ((-844.93, 2255.29), (-844.30, 2245.50)),
}


def route_points(route_id):
    """Return fixed start and end pairs. Reject arbitrary coordinates or unknown IDs."""
    if route_id not in _POINTS:
        raise ValueError(f'Unknown hybrid route {route_id!r}')
    return _POINTS[route_id]


def route_heading(pose, goal):
    """Compute the image-plane bearing using both reversed world-coordinate axes."""
    return math.degrees(math.atan2(pose['y'] - goal[1], pose['x'] - goal[0])) % 360


def camera_correction(yaw, heading):
    """Choose a bounded horizontal pulse, using fresh measured yaw for every step."""
    delta = (heading - yaw + 180) % 360 - 180
    gain = 3 if abs(delta) > 30 else 2
    return max(-250, min(250, round(delta * gain)))
