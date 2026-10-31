"""Fixed local trial routes in BetterGI's shared world-coordinate plane."""
import math


COURTYARD_ROUTE = 'mondstadt-courtyard-hybrid-v1'
LAMPPOST_ROUTE = 'mondstadt-lamppost-v1'
PLANTER_ROUTE = 'mondstadt-planter-v1'
STAIR_POST_ROUTE = 'mondstadt-stair-post-v1'
STAIR_APPROACH_ROUTE = 'mondstadt-stair-approach-v1'
STREET_EXTENSION_ROUTE = 'mondstadt-street-extension-01-v1'
STREET_TURN_ROUTE = 'mondstadt-street-extension-02-v1'
STREET_CONTINUE_ROUTE = 'mondstadt-street-extension-03-v1'
STREET_JUNCTION_ROUTE = 'mondstadt-street-extension-04-v1'
STREET_STAIRS_ROUTE = 'mondstadt-street-extension-05-v1'
STREET_LOWER_LANE_ROUTE = 'mondstadt-street-extension-06-v1'
STREET_DESCENT_ROUTE = 'mondstadt-street-extension-07-v1'
STREET_LOWER_STEPS_ROUTE = 'mondstadt-street-extension-08-v1'
STREET_STEPS_EXIT_ROUTE = 'mondstadt-street-extension-09-v1'
STREET_SMITHY_ROUTE = 'mondstadt-street-extension-10-v1'
STREET_GATE_APPROACH_ROUTE = 'mondstadt-street-extension-11-v1'
STREET_GATE_ROUTE = 'mondstadt-street-extension-12-v1'
STREET_GATE_CLEARANCE_ROUTE = 'mondstadt-street-extension-13-v1'
STREET_GATE_CENTER_ROUTE = 'mondstadt-street-extension-14-v1'
STREET_BRIDGE_ENTRY_ROUTE = 'mondstadt-street-extension-15-v1'
STREET_ARCH_CLEARANCE_ROUTE = 'mondstadt-street-extension-16-v1'
STREET_ARCH_EXIT_ROUTE = 'mondstadt-street-extension-17-v1'
STREET_PATROL_ROUTE = 'mondstadt-street-patrol-v1'
BRIDGE_APPROACH_ROUTE = 'mondstadt-bridge-approach-v1'
BRIDGE_ENTRY_ROUTE = 'mondstadt-bridge-entry-v1'
BRIDGE_MIDDLE_ROUTE = 'mondstadt-bridge-middle-v1'
BRIDGE_EXIT_ROUTE = 'mondstadt-bridge-exit-v1'
FIELD_JUNCTION_ROUTE = 'mondstadt-field-junction-v1'
FIELD_NORTH_ROUTE = 'mondstadt-field-north-v1'
FIELD_EAST_ROUTE = 'mondstadt-field-east-v1'
SCOUT_ENTRY_ROUTE = 'mondstadt-combat-scout-entry-v1'
SCOUT_ROUTES = (SCOUT_ENTRY_ROUTE,)
SURFACE_ROUTES = (BRIDGE_APPROACH_ROUTE,BRIDGE_ENTRY_ROUTE,BRIDGE_MIDDLE_ROUTE,BRIDGE_EXIT_ROUTE,FIELD_JUNCTION_ROUTE,FIELD_NORTH_ROUTE,FIELD_EAST_ROUTE)
SURVEY_ROUTES = (STREET_EXTENSION_ROUTE,STREET_TURN_ROUTE,STREET_CONTINUE_ROUTE,STREET_JUNCTION_ROUTE,
                 STREET_STAIRS_ROUTE,STREET_LOWER_LANE_ROUTE,STREET_DESCENT_ROUTE,STREET_LOWER_STEPS_ROUTE,
                 STREET_STEPS_EXIT_ROUTE,STREET_SMITHY_ROUTE,STREET_GATE_APPROACH_ROUTE,STREET_GATE_ROUTE,
                 STREET_GATE_CLEARANCE_ROUTE,STREET_GATE_CENTER_ROUTE,STREET_BRIDGE_ENTRY_ROUTE,STREET_ARCH_CLEARANCE_ROUTE,
                 STREET_ARCH_EXIT_ROUTE) + SURFACE_ROUTES + SCOUT_ROUTES
ROUTE_IDS = (COURTYARD_ROUTE, LAMPPOST_ROUTE, PLANTER_ROUTE, STAIR_POST_ROUTE, STAIR_APPROACH_ROUTE, STREET_PATROL_ROUTE) + SURVEY_ROUTES
# Keep failed geometry readable for its original evidence, but refuse launching that line again.
BLOCKED_ROUTE_IDS = (STREET_GATE_ROUTE,STREET_BRIDGE_ENTRY_ROUTE,STREET_ARCH_EXIT_ROUTE)
EXECUTABLE_ROUTE_IDS = tuple(route for route in ROUTE_IDS if route not in BLOCKED_ROUTE_IDS)

# The default segment is also advertised as the bridge's native heading anchors.
_POINTS = {
    # Candidate through the grass beyond the last inspected fence end; live use still requires a fresh scene review.
    SCOUT_ENTRY_ROUTE: ((-1090,2194),(-1115,2194)),
    # Reuse the already surveyed junction/stair edge as a single reversible leg.
    STAIR_APPROACH_ROUTE: ((-844.93,2255.29),(-846.30078125,2261.13671875)),
    # Eight-unit continuation in the clear lane seen from the native stair-post endpoint.
    # This candidate stops for inspection on any obstacle; it is not a general route qualification.
    STREET_EXTENSION_ROUTE: ((-844.30,2245.50),(-840.50,2238.50)),
    # Move from the wall-side pavement into the visibly clear road on the left.
    STREET_TURN_ROUTE: ((-840.50,2238.50),(-846.00,2235.00)),
    # Continue along the road toward its visible corner, without crossing the planting bed.
    STREET_CONTINUE_ROUTE: ((-846.00,2235.00),(-840.50,2225.00)),
    # The city tile shows the gate-side branch northeast of the windmill corner.
    STREET_JUNCTION_ROUTE: ((-840.50,2225.00),(-852.00,2229.00)),
    # From the landscaped corner, take the visible stair opening toward the lower houses.
    STREET_STAIRS_ROUTE: ((-852.00,2229.00),(-865.00,2227.00)),
    # Follow the visible lower lane on the left of the low stone wall.
    STREET_LOWER_LANE_ROUTE: ((-865.00,2227.00),(-880.00,2228.00)),
    # Follow the curving descent between the houses and the low outer wall.
    STREET_DESCENT_ROUTE: ((-880.00,2228.00),(-895.00,2222.00)),
    # Leave the low landscaped shelf toward the visible descending lane by the smithy.
    STREET_LOWER_STEPS_ROUTE: ((-895.00,2222.00),(-901.00,2216.00)),
    # Finish the last visible steps before turning into the lower plaza.
    STREET_STEPS_EXIT_ROUTE: ((-901.00,2216.00),(-904.00,2213.00)),
    # Turn through the open gap on the left of the house, beside the smithy.
    STREET_SMITHY_ROUTE: ((-904.00,2213.00),(-917.00,2216.00)),
    # Keep left of the smithy's work area through the open gate-side pavement.
    STREET_GATE_APPROACH_ROUTE: ((-917.00,2216.00),(-924.00,2228.00)),
    # Approach the gate opening identified in the city tile and current minimap.
    STREET_GATE_ROUTE: ((-924.00,2228.00),(-940.00,2220.00)),
    # The direct gate trial stopped at the right pillar. This fresh normal pose backs into open paving.
    STREET_GATE_CLEARANCE_ROUTE: ((-934.80,2222.00),(-932.00,2229.00)),
    # Cross toward the opening after clearing the right pillar onto verified paving.
    STREET_GATE_CENTER_ROUTE: ((-932.00,2229.00),(-942.00,2229.00)),
    # Clear the inner arch corner diagonally onto the visible bridge approach.
    STREET_BRIDGE_ENTRY_ROUTE: ((-942.00,2229.00),(-952.00,2221.00)),
    # The diagonal met the inner corner. Back away slightly and move sideways into the opening first.
    STREET_ARCH_CLEARANCE_ROUTE: ((-941.94,2229.02),(-940.00,2225.00)),
    # Advance through the opening from its newly verified central paving point.
    STREET_ARCH_EXIT_ROUTE: ((-940.00,2225.00),(-952.00,2221.00)),
    # The start is the retained, independently matched outdoor gate frame; qualify live before movement.
    BRIDGE_APPROACH_ROUTE: ((-947.53906,2222.0996),(-960.00,2219.00)),
    # Turn into the open bridge entrance seen from the verified first outdoor endpoint.
    BRIDGE_ENTRY_ROUTE: ((-960.00,2219.00),(-976.00,2211.00)),
    # Continue down the visibly open bridge center after the entry endpoint is verified.
    BRIDGE_MIDDLE_ROUTE: ((-976.00,2211.00),(-1010.00,2194.00)),
    # Follow the remaining open roadway past the NPC to the visible far bridge exit.
    BRIDGE_EXIT_ROUTE: ((-1010.00,2194.00),(-1042.00,2178.00)),
    # Stay on the open dirt road to the junction visible beyond the far bridge exit.
    FIELD_JUNCTION_ROUTE: ((-1042.00,2178.00),(-1065.00,2166.00)),
    # The north-facing scene shows open ground across the road, clear of the right-side fence.
    FIELD_NORTH_ROUTE: ((-1065.00,2166.00),(-1065.00,2194.00)),
    # The east-facing survey clears the bush and follows visible grass away from the lake edge.
    FIELD_EAST_ROUTE: ((-1065.00,2194.00),(-1090.00,2194.00)),
    COURTYARD_ROUTE: ((-867.7041015625, 2281.378173828125), (-874.3662109375, 2274.179931640625)),
    # Surveyed level road on either side of the fixed pavement lamp and planter.
    LAMPPOST_ROUTE: ((-858.70, 2263.65), (-846.30078125, 2261.13671875)),
    # Sidewalk by the stone stairs, with a flower box between the two ends.
    PLANTER_ROUTE: ((-844.625, 2260.4599609375), (-840.55, 2252.43)),
    # The stone end post blocks the direct line. Its left side opens onto the street.
    STAIR_POST_ROUTE: ((-844.93, 2255.29), (-844.30, 2245.50)),
}

# The fixed patrol starts at the stairs. Destination requests can start at any verified station here.
PATROL_STATIONS = {'stair-front': _POINTS[STAIR_POST_ROUTE][0],
                   'sidewalk-junction': _POINTS[LAMPPOST_ROUTE][1], 'west-lamp': _POINTS[LAMPPOST_ROUTE][0]}
PATROL_SEGMENTS = (('stair-front', 'sidewalk-junction'), ('sidewalk-junction', 'west-lamp'),
                   ('west-lamp', 'sidewalk-junction'), ('sidewalk-junction', 'stair-front'))


def patrol_leg(completed_legs):
    """Return the directed segment that follows this many verified arrivals."""
    return PATROL_SEGMENTS[completed_legs % len(PATROL_SEGMENTS)]


def station_path(origin, destination):
    """Return the next station(s) from a named origin without inventing an unsurveyed edge."""
    if not isinstance(origin, str) or origin not in PATROL_STATIONS:
        raise ValueError('Itinerary origin must be a surveyed station')
    if not isinstance(destination, str) or destination not in PATROL_STATIONS or destination == origin:
        raise ValueError('Each destination must require movement to a surveyed station')
    if (origin, destination) in PATROL_SEGMENTS:
        return (destination,)
    # The two ends of this three-station street meet at one surveyed junction.
    for start, via in PATROL_SEGMENTS:
        if start == origin and (via, destination) in PATROL_SEGMENTS:
            return via, destination
    raise ValueError('No surveyed path between requested stations')


def itinerary_legs(start, destinations):
    """Preview the shortest surveyed path for each ordered request, with a one-based owner."""
    if not isinstance(destinations, (tuple, list)) or not 1 <= len(destinations) <= 4:
        raise ValueError('Expected one to four predeclared itinerary destinations')
    legs = []
    origin = start
    for ordinal, destination in enumerate(destinations, 1):
        for station in station_path(origin, destination):
            legs.append((origin, station, ordinal))
            origin = station
    return tuple(legs)


def route_points(route_id):
    """Return the first fixed segment. Patrol legs are advanced explicitly after release."""
    if route_id == STREET_PATROL_ROUTE:
        start, end = patrol_leg(0)
        return PATROL_STATIONS[start], PATROL_STATIONS[end]
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
