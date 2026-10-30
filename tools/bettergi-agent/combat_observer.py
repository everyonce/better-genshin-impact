"""Read-only RGB192 combat candidates. These heuristics never grant input authority or prove a kill."""
import math
import numpy as np


def inspect_pixels(pixels):
    """Find compact red horizontal candidates outside the HUD and retain explicit health-color uncertainty."""
    if type(pixels) is not bytes or len(pixels) != 192*192*3:
        raise ValueError('Combat observation requires exact RGB192 bytes')
    image=np.frombuffer(pixels,dtype=np.uint8).reshape(192,192,3).astype(np.int16)
    red,green,blue=image[:,:,0],image[:,:,1],image[:,:,2]
    # BetterGI's native fight recognition uses red health bars. At RGB192 this is only a coarse candidate.
    redness=(red>=180)&(red-green>=70)&(np.abs(green-blue)<=25)&(green>=35)&(green<=160)
    allowed=np.zeros((192,192),dtype=bool)
    allowed[27:145,24:166]=True
    points=set(zip(*np.nonzero(redness&allowed)))
    bars=[]
    overloaded=len(points)>512
    if not overloaded:
        while points:
            start=points.pop()
            pending=[start]
            component=[start]
            while pending:
                y,x=pending.pop()
                for neighbor in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
                    if neighbor in points:
                        points.remove(neighbor)
                        pending.append(neighbor)
                        component.append(neighbor)
            ys,xs=zip(*component)
            width,height=max(xs)-min(xs)+1,max(ys)-min(ys)+1
            if 6<=width<=48 and 1<=height<=4 and width>=4*height and len(component)>=.7*width*height:
                bars.append(dict(x=min(xs),y=min(ys),width=width,height=height,pixels=len(component)))
    health=(green[178:184,76:117]>=100)&(green[178:184,76:117]-red[178:184,76:117]>=18)&(green[178:184,76:117]-blue[178:184,76:117]>=25)
    green_count=int(health.sum())
    red_count=int(redness[178:184,76:117].sum())
    color='green-visible' if green_count>=6 and red_count<=2 else 'red-visible' if red_count>=3 else 'unknown'
    return dict(enemyBarCandidates=sorted(bars,key=lambda row:(row['y'],row['x'])),redMaskOverloaded=overloaded,
                playerHealthColor=color,playerHealthGreenPixels=green_count,playerHealthRedPixels=red_count,
                authorizesInput=False,enemyIdentityVerified=False,killVerified=False)


class CombatObserver:
    """Confirm only stable candidate geometry on distinct source clocks; this remains observation-only."""
    def __init__(self):
        self.previous=None

    def observe(self,frame,pixels):
        """Refuse temporal confirmation after source changes, ambiguity, stale spacing or missing HUD health color."""
        result=inspect_pixels(pixels)
        source=frame.get('sourceFrame') or {}
        stamp,epoch=source.get('timestamp100ns'),source.get('captureEpoch')
        candidates=result['enemyBarCandidates']
        current=None
        if (len(candidates)==1 and result['playerHealthColor']=='green-visible'
                and isinstance(epoch,str) and epoch and type(stamp) is int and stamp>0
                and type(frame.get('frameId')) is int and frame['frameId']>0):
            current=dict(frameId=frame['frameId'],epoch=epoch,stamp=stamp,box=candidates[0])
        result['temporalCandidateConfirmed']=False
        before=self.previous
        if current and before and current['epoch']==before['epoch'] and current['frameId']>before['frameId']:
            gap=(current['stamp']-before['stamp'])/10000
            a,b=before['box'],current['box']
            if 80<=gap<=250 and math.hypot(a['x']-b['x'],a['y']-b['y'])<=3 and .6<=b['width']/a['width']<=1.3:
                result['temporalCandidateConfirmed']=True
                result['confirmationFrameIds']=[before['frameId'],current['frameId']]
        # Preserve the first source until sufficient separation; repeated sources cannot refresh it.
        if (current is None or before is None or current['epoch']!=before['epoch']
                or current['stamp']-before['stamp']>=800000 or current['stamp']<before['stamp']):
            self.previous=current
        return result
