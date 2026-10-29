"""Choose a single successor from accepted plans and a positive native gameplay witness."""
from itertools import product

from hybrid_routes import PATROL_SEGMENTS, itinerary_legs


STATIONS = ('stair-front','sidewalk-junction','west-lamp')
BALANCED = 'balanced-native-visits-v1'


def least_visited(start,requested,verified,approaches,remaining,witness_frame):
    """Prefer balanced requested/verified goals and approach directions, then longer legal routes."""
    shift = witness_frame % len(STATIONS)
    order = STATIONS[shift:]+STATIONS[:shift]
    for size in (4,3,2):
        options = []
        for seq in product(order,repeat=size):
            if any(a==b for a,b in zip((start,*seq),seq)):
                continue
            legs = itinerary_legs(start,list(seq))
            if len(legs)>remaining:
                continue
            arrivals = dict(approaches)
            for ordinal,dest in enumerate(seq,1):
                origin,last,_ = next(leg for leg in reversed(legs) if leg[2]==ordinal)
                arrivals[origin+'>'+last] += 1
            rank = (sum((requested[s]+seq.count(s))**2 for s in STATIONS),
                    sum((verified[s]+seq.count(s))**2 for s in STATIONS), sum(v*v for v in arrivals.values()),
                    -len(legs), tuple(order.index(s) for s in seq))
            options.append((rank,seq))
        if options:
            return list(min(options)[1])
    return []


def choose(policy,plans,status,witness,slot,destinations,finish):
    """Describe the observed inputs and exact stopping rule separately from the immutable wire command."""
    if policy['mode']==BALANCED and (finish or destinations is not None):
        raise ValueError('Automatic open queue owns its successor selection')
    clock = status['gameplayClock']
    if (set(clock)!={'frequencyHz','firstAppliedTicks','witnessAppliedTicks','firstNativeRequestId','firstFrameId'}
            or any(type(clock[k]) is not int or clock[k]<=0 for k in ('frequencyHz','firstFrameId','firstAppliedTicks','witnessAppliedTicks'))
            or clock['firstAppliedTicks']>clock['witnessAppliedTicks'] or clock['firstFrameId']>witness['frameId']
            or not isinstance(clock['firstNativeRequestId'],str) or len(clock['firstNativeRequestId'])!=32
            or any(c not in '0123456789abcdef' for c in clock['firstNativeRequestId'])
            or (clock['firstNativeRequestId']==witness['nativeRequestId']) != (
                clock['firstFrameId']==witness['frameId'] and clock['firstAppliedTicks']==clock['witnessAppliedTicks'])):
        raise ValueError('Unverified native gameplay clock')
    goals = [r for plan in plans for r in plan['requests']]
    index = status['activeOrdinal']-1
    if not 0<=index<len(goals) or goals[index]['id']!=witness['requestId']:
        raise ValueError('Active native witness does not address the admitted request prefix')
    requested = {s:sum(r['destination']==s for r in goals) for s in STATIONS}
    verified = {s:sum(r['destination']==s for r in goals[:index]) for s in STATIONS}
    approaches = {a+'>'+b:0 for a,b in PATROL_SEGMENTS}
    used = 0
    for plan in plans:
        start = plan['start']
        for request in plan['requests']:
            legs = itinerary_legs(start,[request['destination']])
            origin,start,_ = legs[-1]
            approaches[origin+'>'+start] += 1
            used += len(legs)
    remaining = policy['maxLegs']-used
    target = policy['targetGameplaySeconds']
    if remaining<0 or slot>policy['maxBatches']+1:
        raise ValueError('Admitted destinations exceed queue caps')
    selected = []
    if finish:
        reason = 'operatorFinish'
    elif target is not None and clock['witnessAppliedTicks']-clock['firstAppliedTicks']>=target*clock['frequencyHz']:
        reason = 'gameplayTargetReached'
    elif slot>policy['maxBatches']:
        reason = 'batchLimitReached'
    elif remaining<2:
        reason = 'legLimitReached'
    elif destinations is not None:
        reason,selected = 'manualDestinations',[s for _,s in destinations]
    elif policy['mode']==BALANCED:
        selected = least_visited(start,requested,verified,approaches,remaining,witness['frameId'])
        reason = 'balancedVisits' if selected else 'legLimitReached'
    else:
        raise ValueError('Manual open queue requires explicit destinations or finish')
    if destinations is not None and reason!='manualDestinations':
        raise ValueError('Cannot publish walking destinations beyond the current open-queue cap')
    return dict(gameplayClock=clock,activeOrdinal=index+1,completedRequestIds=[r['id'] for r in goals[:index]],
                requestedCounts=requested,verifiedCounts=verified,approachCounts=approaches,usedLegs=used,predecessorEnd=start,
                selectedStations=selected,reason=reason)
