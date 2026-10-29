"""Focused pre-input map admission tests with no access to a running game."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from hybrid_routes import PATROL_STATIONS
from map_inspection_client import collect_junction, junction_sample, stationary, warm_recovery_capture
from run_warm_photo_requests import options


def frame(fid=3, stamp=300, station='sidewalk-junction'):
    """Make one synthetic native navigation observation with independently chosen coordinate and photo."""
    x,y=PATROL_STATIONS[station]
    row = dict(type='frame',frameId=fid,sourceWidth=1920,sourceHeight=1080,width=192,height=192,pixelFormat='rgb24',
                observationProfile='p2p-native-hamming-192-v1',capturedAtMs=stamp,serverNowMs=stamp+12,
                sourceFrame=dict(capturedAtMs=stamp,acquiredAtMs=stamp,captureEpoch='original',timestamp100ns=stamp*10000),
                navigationPose=dict(x=x,y=y,yawDegrees=85,layerId='City_102',frameId=fid,state='valid',positionConfidence=1,yawConfidence=.9),
                motionEvidence=dict(status='normal',spaceKeyMatched=False),frameWorldReadiness=dict(ready=True,epoch=17),
                worldReadiness=dict(ready=True,epoch=17),inputAvailable=True)
    row['frameWorldReadiness'].update(sourceFrameId=fid,sourceFrame=dict(row['sourceFrame']))
    return row


class MapClientTests(unittest.TestCase):
    def setUp(self):
        self.head=Mock()
        self.head.predict.return_value={'station':'sidewalk-junction'}

    def test_visual_junction_at_native_stairs_is_refused(self):
        self.assertFalse(junction_sample(frame(station='stair-front'),b'',self.head,0,None,17))
        self.assertTrue(junction_sample(frame(),b'',self.head,0,'original',17))

    def test_stale_world_or_missing_return_barrier_cannot_authorize(self):
        original=frame()
        for key,update in [('worldReadiness',dict(ready=False)),('frameWorldReadiness',dict(epoch=20)),
                           ('motionEvidence',dict(spaceKeyMatched=True)),('navigationPose',dict(frameId=1)),
                           ('navigationPose',dict(yawDegrees=float('nan'))),('sourceFrame',dict(captureEpoch='new'))]:
            case=copy.deepcopy(original)
            case[key].update(update)
            self.assertFalse(junction_sample(case,b'',self.head,0,'original',17))
        self.assertFalse(junction_sample(original,b'',self.head,250,'original',17))
        self.assertFalse(junction_sample(dict(original,serverNowMs=500),b'',self.head,0,'original',17))
        self.head.predict.return_value={'station':'west-lamp'}
        self.assertFalse(junction_sample(original,b'',self.head,0,'original',17))

    def test_three_separated_observations_keep_original_photo(self):
        rgb=bytes(192*192*3)
        bridge=Mock()
        bridge.request.side_effect=[(frame(i,t),rgb) for i,t in enumerate([100,120,190,290],1)]
        with tempfile.TemporaryDirectory() as tmp:
            result=collect_junction(bridge,Path(tmp),'before',self.head,{'profile':frame()['observationProfile'],'serverAdvertised':True},
                                    0,None,17,lambda:None,float('inf'))
            self.assertEqual([f['frameId'] for f in result['samples']],[1,3,4])
            self.assertTrue((Path(tmp)/result['png']).is_file())
        case=frame(5,410)
        case['navigationPose']['yawDegrees']=100
        self.assertFalse(stationary(case,frame(4,290)))

    def test_launcher_only_accepts_fixed_map_route_with_a_sealed_owner(self):
        argv=['--inspect-junction-map','--map-owner-from','warm.json','--start-station','sidewalk-junction',
              '--destination','lamp','west-lamp','--destination','return','sidewalk-junction',
              '--landmark-shadow','g4.json','--photo-qualification','qualification.json']
        self.assertTrue(options(argv).inspect_junction_map)
        with self.assertRaises(SystemExit):
            options(argv[:1]+argv[3:])
        with self.assertRaises(SystemExit):
            options([w if w!='west-lamp' else 'stair-front' for w in argv])

    def test_recovery_timer_waits_for_distinct_current_native_navigation_frames(self):
        rgb = bytes(192*192*3)
        rows = [frame(i,t) for i,t in [(1,100),(2,180),(2,180),(3,240)]]
        for row in rows[1:]:
            row['navigationPose'] = dict(frameId=row['frameId'],state='unavailable',reason='world_not_ready')
            row['frameWorldReadiness'].update(ready=False,reason='world_hud_missing')
        bridge = Mock()
        bridge.request.side_effect = [(row,rgb) for row in rows]
        result = warm_recovery_capture(bridge,{'profile':rows[0]['observationProfile'],'serverAdvertised':True},0,lambda:None,float('inf'))
        self.assertEqual([row['frameId'] for row in result],[2,3])
        self.assertTrue(all(call.args==('frame',) for call in bridge.request.call_args_list))
