"""Verify and decode continuous saved replay windows on CPU; never run a policy."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import p2p_replay_sensitivity as decoder
import prepare_replay_session as session


def require_prepared_plan(plan):
    """Reject unsupported or failed plans before any source video is inspected."""
    session.base.require(isinstance(plan, dict) and plan.get('schemaVersion') == 1
                         and plan.get('joinVersion') == 1
                         and plan.get('kind') == 'p2p-offline-continuous-history-candidates',
                         'continuous_plan_required')
    session.base.require(plan.get('status') == 'prepared', 'continuous_plan_not_prepared')


def validate_document(plan, segments):
    """Rebuild every window, label and original video address from the source sidecars."""
    require_prepared_plan(plan)
    parameters = plan['parameters']
    rebuilt = session.prepare_session(segments, history_frames=parameters['historyFrames'],
        max_windows=parameters['maxWindows'], max_source_gap_ms=parameters['maxSourceGapMs'],
        probe_frame_ids=parameters['requestedProbeFrameIds'], comparison_mode='same-frames-only')
    expected = {key: value for key, value in plan.items() if key != 'inputEvidence'}
    session.base.require(decoder.canonical(rebuilt) == decoder.canonical(expected), 'continuous_plan_rebuild_mismatch')
    return rebuilt


def load_plan(path):
    """Read bounded metadata and verify all original files before reconstruction."""
    session.base.require(path.stat().st_size <= session.MAX_JSON_BYTES, 'plan_too_large')
    plan = session._read_json(path)
    require_prepared_plan(plan)
    sources = plan['sourceSegments']
    session.base.require(1 <= len(sources) <= session.MAX_SEGMENTS, 'segment_count_out_of_range')
    segments, evidence, metadata_bytes = [], {}, 0
    for source in sources:
        number = session.base.integer(source['number'], 'segment.number')
        report = Path(source['report'])
        directory = Path(source['recordingDirectory'])
        files = {'report': report, **{name: directory / name for name in
                 ('recording.json', 'observations.jsonl', 'frames.jsonl', 'events.jsonl', 'frames.mp4')}}
        for name, file in files.items():
            if name != 'frames.mp4':
                metadata_bytes += file.stat().st_size
                session.base.require(metadata_bytes <= session.MAX_JSON_BYTES, 'metadata_memory_bound_exceeded')
            evidence[f'{number:05d}/{name}'] = session.base._file_evidence(file)
        segments.append(session.RecordedSegment(report, directory, session._read_json(report),
            session._read_json(files['observations.jsonl'], True), session._read_json(files['frames.jsonl'], True),
            session._read_json(files['events.jsonl'], True), session._read_json(files['recording.json'])))
    session.base.require(evidence == plan['inputEvidence'], 'continuous_input_evidence_mismatch')
    validate_document(plan, segments)
    return plan, segments


def window_references(window):
    """Keep the probe, anchors and real observation samples from both comparison arms."""
    references = [window['probe']]
    for arm in window['arms'].values():
        references.append(arm['anchor'])
        references.extend(sample['frame'] for sample in arm['samples'])
    return references


def collect_references(plan):
    """Deduplicate shared observations only when every source-address field agrees."""
    references = {}
    for window in plan['windows']:
        for row in window_references(window):
            identity = session.base.integer(row['frameId'], 'frameId')
            if identity in references:
                session.base.require(decoder.canonical(references[identity]) == decoder.canonical(row),
                                     'conflicting_frame_reference')
            references[identity] = row
    session.base.require(references, 'no_selected_frames')
    return references


def export_pixels(plan_path, output, ffmpeg, ffprobe):
    """Decode original local indexes and retain explicit lossy-pixel provenance."""
    plan_path, output = plan_path.resolve(), output.resolve()
    session.base.require(not output.exists(), 'output_already_exists')
    plan_pin = decoder.digest(plan_path)
    plan, segments = load_plan(plan_path)
    roots = {Path(pin['path']).resolve().parent for pin in plan['inputEvidence'].values()}
    session.base.require(not any(output.is_relative_to(root) for root in roots), 'output_would_modify_source')
    references = collect_references(plan)
    tools = []
    for command in (ffmpeg, ffprobe):
        resolved = shutil.which(str(command))
        session.base.require(resolved is not None, 'decoder_executable_missing')
        tools.append(str(Path(resolved).resolve()))
    tool_pins = [decoder.digest(Path(path)) for path in tools]
    source_paths = [Path(__file__), Path(session.__file__), Path(session.base.__file__), Path(decoder.__file__)]
    source_pins = [decoder.digest(path) for path in source_paths]
    output.mkdir(parents=True)
    report = dict(schemaVersion=1, kind='continuous-replay-decoded-pixels', status='decoding',
                  sourcePlan=plan_pin, decoderTools=tool_pins, sourcePins=source_pins,
                  frames=[], videos=[], windows=[],
                  originalPixelParityVerified=False, inferenceExecuted=False, trainingEligible=False,
                  expertDemonstrations=False, liveCapture=False, gameInput=False,
                  limitations=['H.264/yuv420p decoding does not recover the original live RGB bytes.',
                               'Video PTS identifies a stored frame; action labels retain their original software clock.',
                               'Structural alignment does not establish physical input timing or gameplay success.'])
    try:
        from PIL import Image
        for segment in segments:
            number = segment.report['segment']['number']
            selected = [row for row in references.values() if row['recordingSegment'] == number]
            if not selected:
                continue
            video = (segment.recording_dir / 'frames.mp4').resolve()
            session.base.require(all(Path(row['videoFile']).resolve() == video for row in selected),
                                 'video_segment_address_mismatch')
            info = dict(segment=number, video=decoder.digest(video))
            pixels = decoder.decode_indexed(video, selected, segment.recording['encodedFrames'],
                                             tools[0], tools[1], info)
            report['videos'].append(info)
            for reference in sorted(selected, key=lambda row: row['videoFrameIndex']):
                rgb = pixels[reference['videoFrameIndex']]
                destination = output / ('frame-%010d.png' % reference['frameId'])
                Image.fromarray(rgb).save(destination, format='PNG', compress_level=3)
                with Image.open(destination) as saved:
                    session.base.require(saved.mode == 'RGB' and saved.tobytes() == rgb.tobytes(),
                                         'decoded_png_roundtrip_mismatch')
                report['frames'].append(dict(reference=reference, image=decoder.digest(destination),
                    rgbSha256=hashlib.sha256(rgb.tobytes()).hexdigest()))
        session.base.require(len(report['frames']) == len(references), 'not_all_selected_frames_decoded')
        for window in plan['windows']:
            report['windows'].append(dict(windowId=window['windowId'], probeFrameId=window['probe']['frameId'],
                segments=sorted({row['recordingSegment'] for row in window_references(window)}),
                arms={name: dict(anchorFrameId=arm['anchor']['frameId'],
                      sampleFrameIds=[sample['frame']['frameId'] for sample in arm['samples']])
                      for name, arm in window['arms'].items()}))
        session.base.require(decoder.digest(plan_path) == plan_pin, 'plan_changed_during_decode')
        session.base.require(plan['inputEvidence'] == {name: session.base._file_evidence(Path(pin['path']))
            for name, pin in plan['inputEvidence'].items()}, 'source_changed_during_decode')
        session.base.require([decoder.digest(Path(path)) for path in tools] == tool_pins, 'decoder_changed')
        session.base.require([decoder.digest(path) for path in source_paths] == source_pins, 'reader_source_changed')
        session.base.require(not any(name in sys.modules for name in ('torch', 'transformers')),
                             'unexpected_model_runtime_import')
        report.update(status='verified', sourceFilesUnchanged=True, modelRuntimeImported=False)
    except Exception as error:
        report.update(status='rejected', errorType=type(error).__name__, error=str(error))
        raise
    finally:
        report['finishedUtc'] = datetime.now(timezone.utc).isoformat()
        with (output / 'manifest.json').open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write('\n')
    return report


def main(argv=None):
    """Expose CPU decoding separately from model inference or a running bridge."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--ffprobe', default='ffprobe')
    args = parser.parse_args(argv)
    try:
        result = export_pixels(args.plan, args.output, args.ffmpeg, args.ffprobe)
    except (session.base.EvidenceError, decoder.GateFailure, subprocess.SubprocessError,
            OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps(dict(status='rejected', errorType=type(error).__name__, error=str(error))))
        return 2
    print(json.dumps(dict(status=result['status'], frames=len(result['frames']),
                         windows=len(result['windows']), output=str(args.output.resolve()))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
