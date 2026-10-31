"""Immutable, explicitly reviewed two-point scout geometry; never a global route registration."""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

from navigation_profiles import SCOUT_PROFILE,SCOUT_PROFILES,scout_scope


def reviewed_route_policy(profile=SCOUT_PROFILE):
    """Return a fresh declaration of the bounded geometry authority granted at worker startup."""
    scout_scope(profile)
    return dict(version=1,profileId=profile,maximumLength=40,maximumLegs=1)


@dataclass(frozen=True)
class ReviewedScoutRoute:
    """Own exactly two immutable finite endpoints inside the existing scout localization bounds."""
    points: tuple
    profile_id: str = SCOUT_PROFILE

    def __post_init__(self):
        """Normalize both direct construction and JSON input without retaining mutable caller lists."""
        bounds,_=scout_scope(self.profile_id)
        if not isinstance(self.points,(tuple,list)) or len(self.points)!=2:
            raise ValueError('A reviewed scout route requires exactly two endpoints')
        points=[]
        for point in self.points:
            if (not isinstance(point,(tuple,list)) or len(point)!=2
                    or any(type(value) not in (int,float) or type(value) is float and not math.isfinite(value) for value in point)):
                raise ValueError('Reviewed scout coordinates must be finite numeric pairs')
            x,y=point
            if not (bounds['minX']<=x<=bounds['maxX'] and bounds['minY']<=y<=bounds['maxY']):
                raise ValueError('Reviewed scout geometry escaped the existing scope')
            points.append((float(x),float(y)))
        if not 0<math.dist(*points)<=40:
            raise ValueError('A reviewed scout leg must have positive length no greater than 40')
        object.__setattr__(self,'points',tuple(points))

    @classmethod
    def from_document(cls, document):
        """Accept only the versioned scout geometry schema, with no hidden destinations or options."""
        if (not isinstance(document,dict) or set(document)!={'version','profileId','points'}
                or type(document['version']) is not int or document['version']!=1 or document['profileId'] not in SCOUT_PROFILES):
            raise ValueError('Unexpected reviewed scout route schema or profile')
        return cls(document['points'],document['profileId'])

    def document(self):
        """Return detached canonical geometry for request, controller and audit evidence."""
        return dict(version=1,profileId=self.profile_id,points=[list(point) for point in self.points])

    @property
    def sha256(self):
        """Bind normalized geometry and its exact profile independently of JSON whitespace."""
        raw=json.dumps(self.document(),sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def route_id(self):
        """Derive identity from the complete geometry, rather than a mutable registry entry."""
        return 'reviewed-scout-v1-'+self.sha256


def load_reviewed_route(path):
    """Load one bounded explicit specification once; later file edits cannot mutate the route object."""
    path=Path(path).absolute()
    if path.resolve(strict=True)!=path or path.stat().st_size>4096:
        raise ValueError('Reviewed scout specification must be a small unlinked local file')
    return ReviewedScoutRoute.from_document(json.loads(path.read_bytes()))


def validate_reviewed_options(args):
    """Keep this optional route seam confined to one bounded ordinary resident scout lease."""
    route=getattr(args,'reviewed_scout_route',None)
    if route is None:return None
    executed_history=getattr(args,'p2p_executed_history',False)
    # A shorter hold belongs only to the separately reviewed, receipt-verified history mode.
    holds=(50,60) if executed_history is True else (100,)
    if (type(route) is not ReviewedScoutRoute or args.hybrid_route!=route.route_id
            or args.navigation_profile!=route.profile_id or not args.resident or not args.enable_input
            or args.model!='open-p2p' or not args.hybrid_navigation or args.hybrid_legs!=1
            or type(executed_history) is not bool or type(args.action_hold_ms) is not int
            or not 0<args.seconds<=35 or args.max_observation_age_ms!=150 or args.action_hold_ms not in holds
            or executed_history and (getattr(args,'navigation_climb_recovery',False)
                                     or getattr(args,'allow_inspected_obstacle_recovery',False))
            or args.patrol_series_binding is None or getattr(args,'remember_hybrid_bypass',False)):
        raise ValueError('Reviewed geometry requires one pinned 35-second Open P2P scout leg with 150 ms freshness '
                         'and 100 ms holds, or explicit executed history with 50/60 ms holds and no recovery')
    return route
