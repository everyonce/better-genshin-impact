"""Validate receipt-committed P2P history on retained RGB without opening a game bridge."""
import argparse
from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path
import time
from types import SimpleNamespace

from PIL import Image
import torch

from benchmark import file_hash, stats, write_report
from model_adapters import OpenP2PAdapter
from observation_profiles import P2P_NATIVE
from p2p_executed_history import KEYBOARD, encode_controller_step
from p2p_startup import prepare_startup_graph
from policy_rgb_archive import verify_policy_rgb
from run_rdp_patrol import sample_gpu


def snapshot(policy):
    """Retain an independent pre-step reference, including validity and episode counters."""
    return dict(state=[type(part)(part.k_cache.clone(),part.v_cache.clone()) for part in policy.state],
                index=policy.idx.clone(),valid=policy.temporal_cache.valid_tokens.clone(),steps=policy.steps_seen)


def assert_restored(policy, saved):
    """Require byte-exact rollback rather than a reset that discards committed context."""
    torch.testing.assert_close(policy.idx,saved['index'],rtol=0,atol=0)
    torch.testing.assert_close(policy.temporal_cache.valid_tokens,saved['valid'],rtol=0,atol=0)
    if policy.steps_seen!=saved['steps'] or policy._pending_feedback:
        raise AssertionError('Rejected candidate changed committed history')
    for actual,expected in zip(policy.state,saved['state']):
        torch.testing.assert_close(actual.k_cache,expected.k_cache,rtol=0,atol=0)
        torch.testing.assert_close(actual.v_cache,expected.v_cache,rtol=0,atol=0)


def upstream_reference(policy, selected, saved):
    """Run the installed complete two-pass path with its decoder returning the actual selected action."""
    model=policy.model
    action=model.action_mapping.action_to_tensor(
        [KEYBOARD[key][0] for key in selected['keys'] if key in KEYBOARD],
        [str({'LBUTTON':0,'RBUTTON':1,'MBUTTON':2}[key]) for key in selected['keys'] if key not in KEYBOARD],
        SimpleNamespace(x=torch.tensor(selected['mouseDx'],device=model.action_mapping._mouse_delta_x_edges.device),
                        y=torch.tensor(selected['mouseDy'],device=model.action_mapping._mouse_delta_y_edges.device)))
    action=type(action)(action.keys.to('cuda'),action.mouse_buttons.to('cuda'),
                        action.mouse_delta_x.to('cuda').reshape(1,1),action.mouse_delta_y.to('cuda').reshape(1,1))
    decoder=model.bc_transformer.action_decoder
    original=decoder.autogressive_sample
    decoder.autogressive_sample=lambda *args,**kwargs:action
    try:
        with torch.inference_mode(),torch.device('cuda'),torch.autocast('cuda',dtype=policy.dtype):
            _,index,state=model.bc_transformer.online_forward(
                model._normalize_frames(policy.static_frame).unsqueeze(0).unsqueeze(0),policy.text,
                saved['index'],saved['state'],should_grow_cache=False,action_sampler=None,
                empty_sampled_action_fn=model.action_mapping.make_empty_action,
                action_in_to_tokens_fn=model.action_in_to_tokens)
        return index,state
    finally:
        decoder.autogressive_sample=original


def synthetic_receipt(index, selected, owner):
    """Create explicitly simulated software evidence; this never asserts hardware delivery."""
    accepted_at=index*1000.+30
    request=dict(requestId=f'offline-{index}',frameId=index+1,modelId=owner,steps=[deepcopy(selected)],
                 observedAtMs=accepted_at-20,startBeforeMs=accepted_at+130,expiresAtMs=accepted_at+750)
    acceptance=dict(type='accepted',requestId=request['requestId'],acceptedAtMs=accepted_at)
    receipt=dict(requestId=request['requestId'],frameId=request['frameId'],modelId=owner,
        acceptedAtMs=accepted_at,endedAtMs=accepted_at+selected['durationMs'],
        status='completed',reason='horizon_complete',appliedSteps=[dict(index=0,startedAtMs=accepted_at+.1,
            keys=selected['keys'][:],mouseDx=selected['mouseDx'],mouseDy=selected['mouseDy'])])
    return request,acceptance,receipt


def compare_upstream(policy, selected, saved):
    """Compare the complete candidate and ensure reconstruction left the saved prior untouched."""
    reference_index,reference_state=upstream_reference(policy,selected,saved)
    torch.cuda.synchronize()
    torch.testing.assert_close(policy.idx,reference_index,rtol=0,atol=0)
    maximum_error=0.
    for actual,expected,backup,prior in zip(policy.state,reference_state,policy._history_backup,saved['state']):
        for value,reference in ((actual.k_cache,expected.k_cache),(actual.v_cache,expected.v_cache)):
            torch.testing.assert_close(value,reference,rtol=1e-3,atol=1e-3)
            maximum_error=max(maximum_error,(value-reference).abs().max().item())
        torch.testing.assert_close(backup.k_cache,prior.k_cache,rtol=0,atol=0)
        torch.testing.assert_close(backup.v_cache,prior.v_cache,rtol=0,atol=0)
    return maximum_error


def main():
    """Check fill, rollover, numerical equivalence, timing and rollback using the installed GPU."""
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','checkpoint','goal-embedding','recording','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--cache-root',type=Path,default=Path('artifacts/agent/compatibility'))
    parser.add_argument('--nvidia-smi',type=Path,default=Path('C:/Windows/System32/nvidia-smi.exe'))
    parser.add_argument('--steps',type=int,default=45)
    args=parser.parse_args()
    if not 43<=args.steps<=80:parser.error('Use 43-80 steps to cover H41 fill and rollover')
    if args.output.exists():parser.error('Use a new report path to preserve previous results')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    report=dict(status='starting',scope='Offline exact-RGB numerical replay with synthetic receipts; no bridge or game input',
                historyFrames=41,actionHoldMs=50,steps=[],thermal=[],rollbackChecks=[])
    started=time.monotonic()
    def thermal():
        """Bound the diagnostic independently of model speed and foreground machine load."""
        reading=sample_gpu(args.nvidia_smi)
        report['thermal'].append(dict(elapsedSeconds=time.monotonic()-started,**reading))
        if reading['temperatureC']>=78 or time.monotonic()-started>180:
            raise RuntimeError('Offline validation exceeded its thermal or wall-time bound')
    try:
        thermal()
        rows=[json.loads(line) for line in (args.recording/'frames.jsonl').read_text(encoding='utf-8').splitlines() if line]
        rows=[row for row in rows if row.get('observationProfile')==P2P_NATIVE and row.get('policyRgb')
              and (row.get('frameWorldReadiness') or {}).get('ready') is True]
        if len(rows)<args.steps:raise ValueError('Retained recording has too few independently identified source frames')
        rows=rows[:args.steps]
        images=[Image.frombytes('RGB',(192,192),verify_policy_rgb(args.recording,row['policyRgb']).read_bytes()) for row in rows]
        archive=args.output.with_suffix('.sources')
        archive.mkdir(exist_ok=False)
        code_hashes={}
        for source in sorted(Path(__file__).parent.glob('*.py')):
            raw=source.read_bytes()
            (archive/source.name).write_bytes(raw)
            code_hashes[source.name]=hashlib.sha256(raw).hexdigest()
        report.update(recording=str(args.recording.resolve()),framesJournalSha256=file_hash(args.recording/'frames.jsonl'),
            sourceFrames=[dict(frameId=row['frameId'],sourceFrame=row['sourceFrame'],policyRgb=row['policyRgb']) for row in rows],
            checkpointSha256=file_hash(args.checkpoint),goalSha256=file_hash(args.goal_embedding),
            sourceArchive=str(archive.resolve()),codeHashes=code_hashes)
        torch.manual_seed(724)
        load_started=time.perf_counter()
        policy=OpenP2PAdapter(str(args.checkpoint),str(args.source),str(args.cache_root),history=41,
            cuda_graph=True,fast_start=True,execution_feedback=True,executed_history=True,
            goal_embedding=str(args.goal_embedding),observation_profile=P2P_NATIVE)
        report['loadSeconds']=time.perf_counter()-load_started
        reference_source=Path(inspect.getsourcefile(policy.model.bc_transformer.__class__))
        reference_bytes=reference_source.read_bytes()
        (archive/'upstream-policy-transformer.py').write_bytes(reference_bytes)
        report['upstreamReference']=dict(path=str(reference_source),sha256=hashlib.sha256(reference_bytes).hexdigest())
        warmup=prepare_startup_graph(policy)
        if policy._pending_feedback or policy.steps_seen or policy._history_backup is not None:
            raise AssertionError('Startup preparation invented a history transaction')
        graph=policy.graph
        executed_graph=policy.executed_graph
        pointers=[policy.idx.data_ptr(),policy.text.data_ptr(),policy.temporal_cache.valid_tokens.data_ptr()]
        pointers += [tensor.data_ptr() for part in policy.state for tensor in (part.k_cache,part.v_cache)]
        report.update(adapter=policy.metadata,startup=warmup,status='validating')
        print(json.dumps(dict(phase='loaded',loadSeconds=report['loadSeconds'],startup=warmup)),flush=True)
        thermal()
        for index,image in enumerate(images):
            saved=snapshot(policy)
            torch.cuda.synchronize()
            tick=time.perf_counter()
            prediction=policy.predict(image,observation_profile=P2P_NATIVE)
            torch.cuda.synchronize()
            prediction_ms=(time.perf_counter()-tick)*1000
            selected=dict(durationMs=50,keys=['W'],mouseDx=0,mouseDy=0)
            kind='native-forward'
            if index%3==1:
                selected.update(keys=[],mouseDx=35 if index%2 else -35)
                kind='native-yaw'
            elif index%3==2 and prediction['parseValid'] and len(prediction['steps'])==1:
                try:
                    encode_controller_step(prediction['steps'][0])
                    selected=deepcopy(prediction['steps'][0]);kind='model-rounded'
                except ValueError:kind='unrepresentable-model-native-forward'
            tick=time.perf_counter()
            encoded=policy.prepare_executed_action(selected)
            torch.cuda.synchronize()
            recompute_ms=(time.perf_counter()-tick)*1000
            # The independent saved state predates both sampled and corrected candidates.
            maximum_error=compare_upstream(policy,selected,saved)
            request,acceptance,receipt=synthetic_receipt(index,selected,kind)
            policy.finish_executed_action(receipt,request,acceptance)
            counters=policy.executed_history_counters()
            if counters['afterFrames']!=index+1 or counters['validFrames']!=min(index+1,41):
                raise AssertionError('Completed action did not advance exactly one history frame')
            report['steps'].append(dict(step=index+1,selection=kind,selected=selected,encodedAction=encoded,
                predictionMs=prediction_ms,recomputeMs=recompute_ms,totalModelMs=prediction_ms+recompute_ms,
                maximumCacheAbsoluteError=maximum_error,**counters))
            if index in (0,42):
                committed=snapshot(policy)
                policy.predict(image,observation_profile=P2P_NATIVE)
                policy.prepare_executed_action(dict(durationMs=50,keys=['A'],mouseDx=-17,mouseDy=0))
                policy.finish_action(False)
                assert_restored(policy,committed)
                report['rollbackChecks'].append(dict(afterStep=index+1,bitwiseExact=True))
            if index%8==0 or index==len(images)-1:
                thermal();write_report(args.output,report)
                print(json.dumps(report['steps'][-1]),flush=True)
        # A new leg must overwrite the graph's private prior-cache inputs after a
        # goal/history reset, even though both graph objects remain loaded.
        policy.set_goal(str(args.goal_embedding))
        empty=snapshot(policy)
        if empty['steps'] or empty['index'].item() or empty['valid'].item():
            raise AssertionError('Goal reset retained previous episode history')
        policy.predict(images[0],observation_profile=P2P_NATIVE)
        reset_step=dict(durationMs=50,keys=['W'],mouseDx=2,mouseDy=0)
        policy.prepare_executed_action(reset_step)
        reset_error=compare_upstream(policy,reset_step,empty)
        policy.finish_action(False)
        assert_restored(policy,empty)
        report['resetAfterRollover']=dict(historyFrames=0,rollbackBitwiseExact=True,maximumCacheAbsoluteError=reset_error)
        current=[policy.idx.data_ptr(),policy.text.data_ptr(),policy.temporal_cache.valid_tokens.data_ptr()]
        current += [tensor.data_ptr() for part in policy.state for tensor in (part.k_cache,part.v_cache)]
        if graph is not policy.graph or executed_graph is not policy.executed_graph or pointers!=current:
            raise AssertionError('Graph or history storage changed')
        if any(file_hash(Path(__file__).with_name(name))!=digest for name,digest in code_hashes.items()):
            raise AssertionError('Source changed during the frozen GPU validation')
        report['sourceFilesUnchanged']=True
        report.update(status='passed',stableStorage=True,predictionMs=stats([row['predictionMs'] for row in report['steps']]),
            recomputeMs=stats([row['recomputeMs'] for row in report['steps']]),
            totalModelMs=stats([row['totalModelMs'] for row in report['steps']]))
    except BaseException as error:
        report.update(status='failed',error=str(error))
        raise
    finally:
        report['elapsedSeconds']=time.monotonic()-started
        write_report(args.output,report)
    print(json.dumps({key:report[key] for key in ('status','predictionMs','recomputeMs','totalModelMs','elapsedSeconds')}),flush=True)


if __name__=='__main__':
    main()
