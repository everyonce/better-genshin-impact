"""Export source-identified RDP video frames for an independently verified street patrol circuit."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from audit_hybrid_run import PATROL_ORDER, audit, require
from experiments.p2p_replay_sensitivity import decode_indexed
from hybrid_routes import STREET_PATROL_ROUTE
from prepare_replay import _frames


NAMES = {'stair-front': 'Stair-front', 'sidewalk-junction': 'Sidewalk junction', 'west-lamp': 'West lamp'}


def circuit_visits(summary, admission, circuit):
    """Use the exact admission/previous endpoint followed by the four verified terminal samples."""
    require(summary['routeId'] == STREET_PATROL_ROUTE and 1 <= circuit <= summary['verifiedCircuits'],
            'Requested circuit was not independently verified')
    circuits = summary['patrolCircuits']
    first = admission if circuit == 1 else circuits[circuit-2]['endingFrameId']
    legs = circuits[circuit-1]['legs']
    require([leg['toStation'] for leg in legs] == list(PATROL_ORDER[1:]), 'Wrong circuit station order')
    return [dict(circuit=circuit, stop=i, station=station, frameId=fid) for i, (station, fid) in
            enumerate(zip(PATROL_ORDER, [first]+[leg['verifiedFrameId'] for leg in legs]))]


def indexed_frames(directory, part):
    """Join the sealed MP4 index to original observations and check the native pose on both sidecars."""
    def rows(name):
        with (directory/name).open(encoding='utf-8') as stream:
            return [json.loads(line) for line in stream]
    originals = [f for f in rows('observations.jsonl') if not f.get('continuityContext')]
    encoded = rows('frames.jsonl')
    seal = json.loads((directory/'recording.json').read_text(encoding='utf-8'))
    require(seal.get('closed') and seal.get('complete') and not seal.get('error') and
            seal['encodedFrames'] == part['recording']['encodedFrames'] == len(encoded), 'Unsealed or missing encoded frames')
    joined = _frames(originals, encoded, part['observationProfile'], part['capturePollHz'])
    require(all(e.get('navigationPose') == joined[e['frameId']].get('navigationPose') for e in encoded),
            'Encoded sidecar references a different native pose')
    return joined, len(encoded)


def center_signature(image):
    """Coarse luminance of the center scene, excluding the screen edges occupied by the HUD."""
    w, h = image.size
    return np.asarray(image.crop((w//4, h//5, 3*w//4, 3*h//4)).convert('L').resize((16, 16),
                      Image.Resampling.BOX), dtype=np.float32)


def contact_sheet(visits, images):
    """Display the five original views, preserving their recorded aspect ratio beneath English labels."""
    sheet = Image.new('RGB', (666, 581), '#14212c')
    draw = ImageDraw.Draw(sheet)
    title, label = ImageFont.load_default(size=18), ImageFont.load_default(size=14)
    draw.text((14, 9), f"Mondstadt street patrol  |  Circuit {visits[0]['circuit']}", font=title, fill='white')
    draw.text((14, 35), 'BetterGI RDP recording  /  verified station views in travel order', font=label, fill='#b4cbd9')
    for v in visits:
        i = v['stop']
        x, y = 12 + i%3*218, 63 + i//3*258
        draw.text((x, y), f"{i+1}. {NAMES[v['station']]}", font=title, fill='white')
        image = images[v['frameId']].copy()
        image.thumbnail((197, 193), Image.Resampling.LANCZOS)
        sheet.paste(image, (x, y+29))
        draw.text((x, y+225), f"Frame {v['frameId']}   /   video {v['videoFrameIndex']}", font=label, fill='#b4cbd9')
    return sheet


def export_landmarks(run_path, recordings, output, *, repository, circuit=1, ffmpeg='ffmpeg', ffprobe='ffprobe',
                     camera_checkpoint=None):
    """Re-audit sealed source evidence, then decode only exact station frames and write their provenance."""
    run_path, recordings, output = Path(run_path), Path(recordings), Path(output)
    summary = audit(run_path, recordings, repository=repository, minimum_circuits=circuit,
                    camera_checkpoint=camera_checkpoint)
    run = json.loads(run_path.read_text(encoding='utf-8-sig'))
    parts = [(e, json.loads((Path(repository)/e['report']).read_text(encoding='utf-8-sig'))) for e in run['segments']]
    admission = next(event['frameId'] for _, p in parts for event in p['hybridNavigationEvents']
                     if event['type'] == 'hybridStartVerified')
    selected = circuit_visits(summary, admission, circuit)
    other = summary['verifiedCircuits'] if circuit == 1 else 1
    comparison = [] if other == circuit else circuit_visits(summary, admission, other)
    visits, images = selected+comparison, {}
    for entry, part in parts:
        directory = recordings/f"{entry['number']:05d}"
        frames, count = indexed_frames(directory, part)
        present = [v for v in visits if v['frameId'] in frames]
        if not present:
            continue
        video = directory/'frames.mp4'
        pixels = decode_indexed(video, [frames[v['frameId']] for v in present], count, ffmpeg, ffprobe, {})
        for v in present:
            f = frames[v['frameId']]
            pose = f['navigationPose']
            images[v['frameId']] = Image.fromarray(pixels[f['videoFrameIndex']])
            v.update(leaseSegment=entry['number'], videoFile=str(video.resolve()), videoFrameIndex=f['videoFrameIndex'],
                     videoPtsSeconds=f['videoPtsSeconds'], sourceFrame=f['sourceFrame'], nativePose={k: pose[k]
                     for k in ('frameId','x','y','yawDegrees','layerId')}, observationProfile=f['observationProfile'],
                     videoSize=[f['width'],f['height']], sourceSize=[f['sourceWidth'],f['sourceHeight']])
    require(all('videoFrameIndex' in v for v in visits), 'Verified station frame missing from encoded video')
    require(not output.exists() or not any(output.iterdir()), 'Choose an empty output directory')
    output.mkdir(parents=True, exist_ok=True)
    for v in visits:
        file = output/f"circuit-{v['circuit']:03}-stop-{v['stop']+1}-{v['station']}-frame-{v['frameId']}.png"
        images[v['frameId']].save(file)
        v.update(file=file.name, pngSha256=hashlib.sha256(file.read_bytes()).hexdigest())
    measurements = []
    for v, w in zip(selected, comparison):
        a, b = center_signature(images[v['frameId']]), center_signature(images[w['frameId']])
        yaw = (v['nativePose']['yawDegrees']-w['nativePose']['yawDegrees']+180)%360-180
        measurements.append(dict(stop=v['stop'], station=v['station'], frames=[v['frameId'],w['frameId']],
                                 yawDifferenceDegrees=abs(yaw), meanAbsoluteLumaDifference=float(np.abs(a-b).mean()/255)))
    contact_sheet(selected, images).save(output/'station-views.png')
    manifest = dict(version=1, runId=run['runId'], runFile=str(run_path.resolve()), routeId=summary['routeId'],
                    verifiedCircuits=summary['verifiedCircuits'], circuit=circuit, contactSheet='station-views.png',
                    pixelSource='Recorded RDP observation decoded from H.264 as RGB24', visits=selected,
                    comparisonVisits=comparison, centerSceneComparison=measurements,
                    comparisonNote='Diagnostic only. Normalized 16x16 center luminance difference depends on camera, lighting and animation.')
    if comparison:
        manifest['comparisonContactSheet'] = f'comparison-circuit-{other:03}-views.png'
        contact_sheet(comparison, images).save(output/manifest['comparisonContactSheet'])
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--recordings', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--repository', default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument('--circuit', type=int, default=1)
    parser.add_argument('--camera-checkpoint', help='Camera checkpoint when the archived trial applied calibrated turns')
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--ffprobe', default='ffprobe')
    args = vars(parser.parse_args())
    args['run_path'] = args.pop('run')
    print(json.dumps(export_landmarks(**args), indent=2))
