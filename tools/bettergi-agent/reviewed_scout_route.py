"""Immutable, explicitly reviewed two-point scout geometry; never a global route registration."""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

from navigation_profiles import SCOUT_BOUNDS,SCOUT_PROFILE


def reviewed_route_policy():
    """Return a fresh declaration of the bounded geometry authority granted at worker startup."""
    return dict(version=1,profileId=SCOUT_PROFILE,maximumLength=40,maximumLegs=1)


@dataclass(frozen=True)
class ReviewedScoutRoute:
    """Own exactly two immutable finite endpoints inside the existing scout localization bounds."""
    points: tuple

    def __post_init__(self):
        """Normalize both direct construction and JSON input without retaining mutable caller lists."""
        if not isinstance(self.points,(tuple,list)) or len(self.points)!=2:
            raise ValueError('A reviewed scout route requires exactly two endpoints')
        points=[]
        for point in self.points:
            if (not isinstance(point,(tuple,list)) or len(point)!=2
                    or any(type(value) not in (int,float) or type(value) is float and not math.isfinite(value) for value in point)):
                raise ValueError('Reviewed scout coordinates must be finite numeric pairs')
            x,y=point
            if not (SCOUT_BOUNDS['minX']<=x<=SCOUT_BOUNDS['maxX'] and SCOUT_BOUNDS['minY']<=y<=SCOUT_BOUNDS['maxY']):
                raise ValueError('Reviewed scout geometry escaped the existing scope')
            points.append((float(x),float(y)))
        if not 0<math.dist(*points)<=40:
            raise ValueError('A reviewed scout leg must have positive length no greater than 40')
        object.__setattr__(self,'points',tuple(points))

    @classmethod
    def from_document(cls, document):
        """Accept only the versioned scout geometry schema, with no hidden destinations or options."""
        if (not isinstance(document,dict) or set(document)!={'version','profileId','points'}
                or type(document['version']) is not int or document['version']!=1 or document['profileId']!=SCOUT_PROFILE):
            raise ValueError('Unexpected reviewed scout route schema or profile')
        return cls(document['points'])

    def document(self):
        """Return detached canonical geometry for request, controller and audit evidence."""
        return dict(version=1,profileId=SCOUT_PROFILE,points=[list(point) for point in self.points])

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
    if (type(route) is not ReviewedScoutRoute or args.hybrid_route!=route.route_id
            or args.navigation_profile!=SCOUT_PROFILE or not args.resident or not args.enable_input
            or args.model!='open-p2p' or not args.hybrid_navigation or args.hybrid_legs!=1
            or not 0<args.seconds<=35 or args.max_observation_age_ms!=150 or args.action_hold_ms!=100
            or args.patrol_series_binding is None or getattr(args,'remember_hybrid_bypass',False)):
        raise ValueError('Reviewed geometry requires one pinned 35-second Open P2P scout leg with 150/100 ms limits')
    return route
