"""Reject ownership, timing, release and stop substitutions in the warm photo audit."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from audit_photo_handoff import attribute_actions, bridge_clock, check_plan, check_release, lifecycle, terminal_release, validate_stop


class WarmAuditTests(unittest.TestCase):
    def setUp(self):
        self.specs = [dict(id='1'*32, name='stair',targets=['stair-front'],circuits=1),
                      dict(id='2'*32, name='lamp',targets=['west-lamp'],circuits=1)]
        self.clock = dict(originTicks=200_000,frequency=10_000_000)
        self.rows, self.receipts, self.frames = [], {}, {}
        for owner,(fid,sampled,at) in enumerate(((8,100,200),(22,700,790))):
            req = str(owner+1)
            acceptance = dict(type='accepted',requestId=req,acceptedAtMs=at)
            self.rows.append(dict(frameId=fid,warmRequestId=self.specs[owner]['id'],acceptance=acceptance,
                historyCommitted=False,hybridNavigation=dict(owner='hybrid-native'),policyGoalVersion=0,
                episodeStep=1,validHistoryFrames=1))
            self.receipts[req] = dict(frameId=fid,acceptedAtMs=at,endedAtMs=at+10,status='completed',
                                      appliedSteps=[dict(startedAtMs=at+1)])
            self.frames[fid]=self.frame(sampled)
        self.frames[20] = self.frame(650)
        self.completed = dict(lastAcceptedRequestId='1',release=dict(serverNowMs=250))

    def frame(self, ms):
        return dict(capturedAtMs=ms,sourceTimestampKind='wgc_reported_compositor_qpc',
                    sourceFrame=dict(capturedAtMs=ms,acquiredAtMs=ms,freshnessAtMs=ms,
                        timestamp100ns=self.clock['originTicks']+int(ms*10000),freshnessClockKind='reported_compositor_qpc'))

    def audit_actions(self):
        groups,switches = attribute_actions(self.rows,[],self.receipts,self.frames,self.specs,[20],[self.completed],self.clock)
        return groups,switches[0]

    def test_qpc_dispatch_gap_and_disjoint_receipts(self):
        groups,result = self.audit_actions()
        self.assertEqual(result['dispatchGapMs'],590)
        self.assertEqual(result['oldLast']['firstDispatchTicks'],2210000)
        self.assertEqual(groups[1][0]['sourceAgeMs'],91)

    def test_rejects_false_owner_outstanding_action_backdated_clock_and_reused_history(self):
        cases = [(self.rows[1],'warmRequestId',self.specs[0]['id']), (self.rows[1],'validHistoryFrames',2),
                 (self.rows[0],'historyCommitted',True), (self.receipts['1'],'endedAtMs',300),
                 (self.frames[22]['sourceFrame'],'timestamp100ns',10), (self.completed,'lastAcceptedRequestId','2')]
        for row,key,bad in cases:
            with self.subTest(key=key):
                value=row[key]
                row[key]=bad
                with self.assertRaises(ValueError):
                    self.audit_actions()
                row[key]=value

    def test_endpoint_handoff_ceiling_remains_strict(self):
        self.frames[22]=self.frame(1160)
        self.rows[1]['acceptance']['acceptedAtMs'] = 1200
        self.receipts['2'].update(acceptedAtMs=1200,endedAtMs=1210,appliedSteps=[dict(startedAtMs=1201)])
        with self.assertRaisesRegex(ValueError,'one-second'):
            self.audit_actions()

    def test_three_requests_require_two_distinct_timely_switches_and_every_receipt(self):
        third = dict(id='3'*32,name='junction',targets=['sidewalk-junction'],circuits=1)
        specs = self.specs + [third]
        check_plan(dict(version=1,requests=specs))
        next_row = copy.deepcopy(self.rows[1])
        next_row.update(frameId=34,warmRequestId=third['id'])
        next_row['acceptance'].update(requestId='3',acceptedAtMs=1400)
        self.rows.append(next_row)
        self.receipts['3']=dict(frameId=34,acceptedAtMs=1400,endedAtMs=1420,status='completed',appliedSteps=[dict(startedAtMs=1401)])
        self.frames.update({32:self.frame(1250),34:self.frame(1350)})
        done = [self.completed,dict(lastAcceptedRequestId='2',release=dict(serverNowMs=840)),
                dict(lastAcceptedRequestId='3',release=dict(serverNowMs=1500))]
        def run():
            return attribute_actions(self.rows,[],self.receipts,self.frames,specs,[20,32],done,self.clock)
        groups,handoffs = run()
        self.assertEqual([len(g) for g in groups],[1,1,1])
        self.assertEqual([h['dispatchGapMs'] for h in handoffs],[590,610])
        self.assertEqual([h['newRequestId'] for h in handoffs],[specs[1]['id'],third['id']])
        next_row['warmRequestId']=specs[1]['id']
        with self.assertRaisesRegex(ValueError,'retired or future'):
            run()
        next_row['warmRequestId']=third['id']
        done[2]['lastAcceptedRequestId']='2'
        with self.assertRaisesRegex(ValueError,'wrong terminal'):
            run()
        done[2]['lastAcceptedRequestId']='3'
        self.frames[34]=self.frame(1730)
        next_row['acceptance'].update(acceptedAtMs=1790)
        self.receipts['3'].update(acceptedAtMs=1790,endedAtMs=1800,appliedSteps=[dict(startedAtMs=1791)])
        done[2]['release']['serverNowMs']=1850
        with self.assertRaisesRegex(ValueError,'one-second'):
            run()

    def test_ledger_refuses_identical_request_definitions_or_other_qpc_epochs(self):
        check_plan(dict(version=1, requests=self.specs))
        bad = copy.deepcopy(self.specs)
        bad[1]['targets']=bad[0]['targets']
        with self.assertRaises(ValueError):
            check_plan(dict(version=1,requests=bad))
        part=dict(hello=dict(sessionId='s',ownerEpoch='e',
                inputTelemetry=dict(sessionOriginAtStopwatchTicks=1,stopwatchFrequency=10_000_000)))
        other=copy.deepcopy(part)
        other['hello']['inputTelemetry']['sessionOriginAtStopwatchTicks']=2
        with self.assertRaises(ValueError):
            bridge_clock([part,other])

    def test_requires_original_release_and_empty_request(self):
        owner=self.specs[0]['id']
        proof=dict(type='released',arrivalFrameId=10,readinessEpoch=4,readinessReady=False,
                   readinessReason='client_release',captureEpoch='abc',serverNowMs=250,policyHistoryReset=True)
        completed=dict(warmRequestId=owner,frameId=20,sourceEpoch='abc',completedLegs=4,pendingActionIds=[],release=proof)
        end=dict(arrivalFrameId=10,sourceEpoch='abc',releaseEpoch=4,completedLegs=4,releaseAtMs=250,samples=[dict(frameId=20)])
        held=dict(state='held',reason='hybridEndpoint',frameId=10,warmRequestId=owner,warmRelease=copy.deepcopy(proof))
        parts=[dict(controlTransitions=[held])]
        check_release(completed,end,parts)
        held['warmRelease']['policyHistoryReset']=False
        with self.assertRaises(ValueError):
            check_release(completed,end,parts)

    def test_third_request_cannot_start_before_its_own_release_or_take_the_preceding_image(self):
        specs=self.specs+[dict(id='3'*32,name='junction',targets=['sidewalk-junction'],circuits=1)]
        clock=dict(sessionId='session',ownerEpoch='owner')
        with tempfile.TemporaryDirectory() as d:
            embed=Path(d)/'embedding.json'
            embed.write_bytes(b'fixed walking goal')
            base=dict(planSha256='plan',goalEmbeddingSha256=hashlib.sha256(embed.read_bytes()).hexdigest(),
                      sourceEpoch='epoch',runId='run',**clock)
            part=dict(controlTransitions=[],policyMetadata=dict(goal=dict(file=str(embed))))
            def marker(kind,i,leg,**extra):
                spec=specs[i]
                return dict(type=kind,warmRequestId=spec['id'],ordinal=i+1,name=spec['name'],
                            targets=spec['targets'],circuits=1,frameId=leg*10,completedLegs=leg,**base,**extra)
            events=[dict(type='hybridStartVerified',frameId=0,samples=[dict(frameId=0)],warmRequestId=specs[0]['id']),
                    marker('warmPhotoRequestStarted',0,0)]
            for leg in range(1,13):
                i=(leg-1)//4
                fid=leg*10
                endpoint=dict(type='hybridEndpointVerified',sourceEpoch='epoch',completedLegs=leg,
                              samples=[dict(frameId=fid)],releaseAtMs=fid-2,arrivalFrameId=fid-3,
                              releaseEpoch=leg,warmRequestId=specs[i]['id'])
                events.append(endpoint)
                if leg % 4:
                    continue
                proof=dict(type='released',arrivalFrameId=fid-3,serverNowMs=fid-2,readinessEpoch=leg,
                           captureEpoch='epoch',readinessReady=False,readinessReason='client_release',policyHistoryReset=True)
                part['controlTransitions'].append(dict(state='held',reason='hybridEndpoint',frameId=fid-3,
                                                      warmRelease=proof,warmRequestId=specs[i]['id']))
                detail=dict(release=proof,pendingActionIds=[],lastAcceptedRequestId=str(leg))
                events.extend([dict(type='hybridCircuitVerified',frameId=fid,warmRequestId=specs[i]['id']),
                               marker('warmPhotoRequestCompleted',i,leg,**detail)])
                if i+1<len(specs):
                    events.extend([marker('warmPhotoHandoff',i,leg,nextRequestId=specs[i+1]['id'],**detail),
                                   marker('warmPhotoRequestStarted',i+1,leg,previousRequestId=specs[i]['id'])])
            def checked():
                return lifecycle(events,[part],specs,'run','plan',clock,False)
            self.assertEqual(checked()[0],[40,80])
            boundary=next(e for e in events if e['type']=='hybridEndpointVerified' and e['completedLegs']==8)
            boundary['warmRequestId']=specs[2]['id']
            with self.assertRaisesRegex(ValueError,'belongs to another request'):
                checked()
            boundary['warmRequestId']=specs[1]['id']
            third=next(e for e in events if e['type']=='warmPhotoRequestStarted' and e['ordinal']==3)
            third['frameId']=79
            with self.assertRaisesRegex(ValueError,'released circuit endpoint'):
                checked()

    def test_cancellation_joins_external_marker_and_software_release(self):
        groups,_ = self.audit_actions()
        parts=[dict(stop=dict(type='stopped',executionContext=dict(telemetryComplete=True,active=None,
                    trackedState=dict(heldKeys=[],telemetryIncomplete=False,releaseOutcome='returned_unverified'),
                    lastInputEvent=dict(atMs=900,origin='release:client_stop',
                        call=dict(operation='releaseAll',stage='returned_unverified',error=None)))))]
        run=dict(endReason='userStop',runId='run')
        stop=dict(version=1,mode='external-stop-drill',runId='run',requestId=self.specs[1]['id'],
                  nativeRequestId='2',frameId=22,observedAtMonotonicNs=10,stopFileCreatedAtMonotonicNs=20,
                  addressedStopAtMonotonicNs=30)
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            (folder/'patrol.json.control.json').write_text(json.dumps(dict(runId='run',command='stop')))
            path=folder/'operator-stop.json'
            path.write_text(json.dumps(stop))
            (folder/'STOP').write_text(json.dumps({k:v for k,v in stop.items() if k not in (
                'stopFileCreatedAtMonotonicNs','addressedStopAtMonotonicNs')}))
            supervisor=dict(runId='run',stopReason='seriesOperatorStop',stopRequested=True,stopRequestedAtMonotonicNs=30)
            (folder/'launcher.json').write_text(json.dumps(supervisor))
            self.assertEqual(validate_stop(folder,run,parts,self.specs,groups)['terminalReleaseAtMs'],900)
            parts[0]['hello']=dict(sessionId='s',ownerEpoch='o',inputTelemetry=dict(
                sessionOriginAtStopwatchTicks=self.clock['originTicks'],stopwatchFrequency=self.clock['frequency']))
            released=self.clock['originTicks']+9_000_000
            bracket=dict(clock='windows-query-performance-counter',frequencyHz=10_000_000,
                         beforeTicks=released-20_000,afterTicks=released-10_000)
            def timing():
                (folder/'launcher.json').write_text(json.dumps(dict(supervisor,addressedStopQpc=bracket)))
                path.write_text(json.dumps(dict(stop,addressedStopQpc=bracket)))
                return validate_stop(folder,run,parts,self.specs,groups)['addressedStopToRelease']
            self.assertEqual((timing()['minimumMs'],timing()['maximumMs']),(1,2))
            bracket['afterTicks']=released+400
            self.assertEqual(timing()['minimumMs'],0)
            bracket['beforeTicks']=released+1
            with self.assertRaisesRegex(ValueError,'caused this native release'):
                timing()
            bracket.update(beforeTicks=released-20_000,frequencyHz=1_000_000)
            with self.assertRaisesRegex(ValueError,'native QPC'):
                timing()
            (folder/'launcher.json').write_text(json.dumps(supervisor))
            with self.assertRaisesRegex(ValueError,'native QPC'):
                validate_stop(folder,run,parts,self.specs,groups)
            path.write_text(json.dumps(dict(stop,nativeRequestId='1')))
            with self.assertRaises(ValueError):
                validate_stop(folder,run,parts,self.specs,groups)
            parts[0]['stop']['executionContext']['trackedState']['heldKeys']='W'
            with self.assertRaises(ValueError):
                terminal_release(parts,groups)
