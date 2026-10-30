"""Reject ownership, timing, release and stop substitutions in the warm photo audit."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from audit_photo_handoff import (attribute_actions, bridge_clock, check_plan, check_release, directed_broker,
                                directed_controls, lifecycle, terminal_release, validate_stop)


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

    def test_directed_job_cannot_substitute_session_process_plan_or_stop_target(self):
        jid='a'*8+'-'+'b'*4+'-'+'c'*4+'-'+'d'*4+'-'+'e'*12
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            jobs=folder/'jobs'
            jobs.mkdir()
            supervisor=dict(rootPid=100,childPid=200,wallTimeLimitSeconds=110)
            run=dict(runId='run',endReason='userStop',windowsSessionId=3,
                     segments=[dict(processId=200,instanceNonce='b'*32)])
            argv=['--rdp-session-id','3','--hybrid-legs','2','--seconds','110',
                  '--patrol-series-binding=100:'+'a'*32+':200:'+'b'*32+':90000000',
                  '--warm-photo-plan='+str(folder/'photo-requests.json'),
                  '--landmark-shadow='+str(folder/'head.json'),'--photo-qualification='+str(folder/'qual.json'),
                  '--record-max-mib=160']
            result=dict(jobId=jid,remoteDesktop=True,success=True,timedOut=False,returnCode=0,windowsSessionId=3,
                        runnerProcessId=300,startedAtUtc='2026-10-29T16:12:00Z',endedAtUtc='2026-10-29T16:12:40Z')
            for mutation in ('none','mainDesktop','newProcess','wrongPlan','extraEdges','wrongStop','resultSubstitution'):
                with self.subTest(mutation=mutation):
                    args=list(argv)
                    job=dict(jobId=jid,windowsSessionId=3,argv=args)
                    b=dict(result)
                    control=dict(runId='run',command='stop')
                    if mutation=='mainDesktop':
                        job['windowsSessionId']=1
                    elif mutation=='newProcess':
                        args[6]=args[6].replace('b'*32,'c'*32)
                    elif mutation=='wrongPlan':
                        args[7]+='.old'
                    elif mutation=='extraEdges':
                        args[3]='4'
                    elif mutation=='wrongStop':
                        control['runId']='other'
                    elif mutation=='resultSubstitution':
                        b['runnerProcessId']=50
                    for path,doc in ((folder/'broker.json',b),(jobs/f'{jid}.result.json',result),
                                     (jobs/f'{jid}.job.json',job),(folder/'patrol.json.control.json',control)):
                        path.write_text(json.dumps(doc))
                    def check():
                        return directed_broker(folder,run,supervisor,[None,None],folder/'head.json',folder/'qual.json')
                    if mutation=='none':
                        self.assertEqual(check()[0]['runnerPid'],300)
                    else:
                        with self.assertRaises(ValueError):
                            check()

    def test_directed_budget_replay_binds_actual_mouse_keys_gpu_and_all_qpc_anchors(self):
        a,b='stair-front','sidewalk-junction'
        step=dict(keys=['W'],mouseDx=0,mouseDy=0,durationMs=100)
        for mutation in ('none','wrongStep','unobservedClock','wrongOwner','earlyInput','nonGpuInput','overBudget'):
            with self.subTest(mutation=mutation):
                frames={i:self.frame(i*100) for i in (1,2,3)}
                for i,f in frames.items():
                    f.update(navigationPose=dict(frameId=i,state='valid',layerId='City_102',positionConfidence=1,
                                                 yawConfidence=.8,yawDegrees=32),
                             motionEvidence=dict(status='normal',spaceKeyMatched=False),inputAvailable=True,
                             frameWorldReadiness=dict(ready=True,sourceFrameId=i,sourceFrame=f['sourceFrame']))
                nav=dict(navigationMode='itinerary',completedLegs=0,segmentIndex=0,destinationOrdinal=1,
                         requestedDestination=b,fromStation=a,toStation=b,target=b,step=step,owner='open-p2p',
                         reason='modelRouteCompatible',pose=frames[2]['navigationPose'])
                row=dict(frameId=2,warmRequestId='goal',hybridNavigation=nav,acceptance=dict(type='accepted',requestId='x'),
                         rawPolicySteps=[step.copy()],steps=[step],startBeforeMs=350)
                run=dict(mode='resident-rdp',observationProfile='p2p-native-hamming-192-v1',recordedBytes=123,
                         recordingBudgetExhausted=False,segments=[dict(processId=200,exitCode=0)])
                part=dict(recording=dict(recordedBytes=123),decisionHz=10,actionHoldMs=100,maxObservationAgeMs=150,
                          firstInputDeadlinePolicy=dict(serverEnforcementRequested=True),effectiveInputKeys=list('WASD'))
                actual=dict(index=0,startedAtMs=220,**step)
                start=dict(type='hybridStartVerified',frameId=1,samples=[dict(frameId=1)])
                if mutation=='wrongStep':
                    actual['mouseDx']=20
                elif mutation=='unobservedClock':
                    frames[3]['sourceFrame']['timestamp100ns']+=9000
                elif mutation=='wrongOwner':
                    nav['destinationOrdinal']=2
                elif mutation=='earlyInput':
                    start['frameId']=3
                elif mutation=='nonGpuInput':
                    row['rawPolicySteps'][0]['keys']=[]
                elif mutation=='overBudget':
                    part['maxObservationAgeMs']=500
                def checked():
                    return directed_controls(run,dict(wallTimeLimitSeconds=110,childPid=200),[part],[start],
                            [row],[],dict(x=dict(appliedSteps=[actual])),frames,[(a,b,1,b)],self.clock)
                if mutation=='none':
                    self.assertEqual(checked()['sourceSpanSeconds'],.2)
                else:
                    with self.assertRaises(ValueError):
                        checked()

    def test_partial_second_destination_must_follow_first_goals_released_endpoint(self):
        a,b,c='stair-front','sidewalk-junction','west-lamp'
        specs=[dict(id=str(i)*32,name='go-'+s,destination=s,targets=[s]) for i,s in enumerate((b,c),1)]
        clock=dict(sessionId='session',ownerEpoch='owner')
        with tempfile.TemporaryDirectory() as d:
            embed=Path(d)/'goal'
            embed.write_bytes(b'ground')
            digest=hashlib.sha256(embed.read_bytes()).hexdigest()
            def marker(kind,index,fid,legs,**detail):
                spec=specs[index]
                return dict(type=kind,warmRequestId=spec['id'],ordinal=index+1,name=spec['name'],targets=spec['targets'],
                        destination=spec['destination'],planSha256='plan',runId='run',sourceEpoch='epoch',
                        goalEmbeddingSha256=digest,frameId=fid,completedLegs=legs,**clock,**detail)
            release=dict(type='released',arrivalFrameId=8,readinessEpoch=2,captureEpoch='epoch',serverNowMs=500,
                         readinessReason='client_release',readinessReady=False,policyHistoryReset=True)
            held=dict(state='held',reason='hybridEndpoint',frameId=8,warmRelease=release,warmRequestId=specs[0]['id'])
            part=dict(policyMetadata=dict(goal=dict(file=str(embed))),controlTransitions=[held])
            native=dict(type='hybridStartVerified',frameId=3,sourceEpoch='epoch',
                        samples=[dict(frameId=3)],warmRequestId=specs[0]['id'])
            end=dict(type='hybridEndpointVerified',samples=[dict(frameId=11)],sourceEpoch='epoch',completedLegs=1,
                     arrivalFrameId=8,releaseAtMs=500,releaseEpoch=2,warmRequestId=specs[0]['id'])
            milestone=dict(type='hybridDestinationVerified',frameId=11,station=b,requestedDestination=b,
                           warmRequestId=specs[0]['id'])
            detail=dict(release=release,pendingActionIds=[],lastAcceptedRequestId='old-final')
            valid=[native,marker('warmPhotoRequestStarted',0,3,0),end,milestone,
                   marker('warmPhotoRequestCompleted',0,11,1,**detail),
                   marker('warmPhotoHandoff',0,11,1,nextRequestId=specs[1]['id'],**detail),
                   marker('warmPhotoRequestStarted',1,11,1,previousRequestId=specs[0]['id'])]
            for mutation in ('none','unreleased','wrongGoal','earlySwitch','surplusEnd','phantomFinish','epochChange',
                             'retry','confirmed','badRetryFrame','forgedConfirm'):
                with self.subTest(mutation=mutation):
                    rows=copy.deepcopy(valid)
                    if mutation=='unreleased':
                        rows[4]['pendingActionIds']=['active']
                    elif mutation=='wrongGoal':
                        rows[3]['requestedDestination']=c
                    elif mutation=='earlySwitch':
                        rows[5]['frameId']=10
                    elif mutation=='surplusEnd':
                        rows.append(end)
                    elif mutation=='phantomFinish':
                        rows.append(marker('warmPhotoRequestCompleted',1,19,2,**detail))
                    elif mutation=='epochChange':
                        rows[6]['sourceEpoch']='another capture'
                    elif mutation in ('retry','confirmed','badRetryFrame','forgedConfirm'):
                        confirm=mutation in ('confirmed','forgedConfirm')
                        rows[2]['photoSurveyVisit']=dict(outcome='confirmationPending' if confirm else 'classificationMiss')
                        rows.insert(4,dict(type='hybridDestinationPhotoRetry',initialEndpointFrameId=11,frameId=14,
                                           samples=[dict(frameId=12),dict(frameId=13),dict(frameId=14)],
                                           warmRequestId=specs[0]['id']))
                        for m in rows[5:7]:
                            m.update(initialEndpointFrameId=11,retryOrdinal=1)
                            if confirm:
                                m['firstConfirmedFrameId']=11
                        for m in rows[5:]:
                            m['frameId']=14
                        if mutation=='badRetryFrame':
                            rows[5]['frameId']=11
                        elif mutation=='forgedConfirm':
                            rows[5]['firstConfirmedFrameId']=12
                    def check():
                        return lifecycle(rows,[part],specs,'run','plan',clock,True,[(a,b,1,b),(b,c,2,c)],
                                         mutation in ('confirmed','forgedConfirm'))
                    if mutation in ('none','retry','confirmed'):
                        self.assertEqual(check()[0],[11 if mutation=='none' else 14])
                    else:
                        with self.assertRaises(ValueError):
                            check()

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
