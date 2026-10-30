"""Freeze a v1 landmark challenger from independently verified natural photo misses; grant no input authority."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from audit_hybrid_run import require
from audit_queue_failure import audit_failure
from freeze_landmark_candidate import encoded, original_rgb, sha, source_views
from landmark_recognizer import FORMAT, G4_SHA256, LandmarkRecognizer
from run_rdp_patrol import native_qpc_sample
from train_steering import distinct


def extend_template_bank(base, metadata, templates, missed_frame_ids):
    """Keep the ordered incumbent bank; append only distinct original arrivals and exclude the whole training lease."""
    require(base.get('format') == FORMAT, 'Only the unchanged v1 family may be extended')
    require(missed_frame_ids and len(set(missed_frame_ids)) == len(missed_frame_ids), 'Missing or repeated miss identities')
    lookup = {row['evidence']['frameId']: row for row in templates}
    require(len(lookup) == len(templates) and set(missed_frame_ids) <= lookup.keys(),
            'A selected miss is not one distinct original native arrival')
    require(all(row['runId'] == metadata['runId'] and row['evidence']['captureEpoch'] == metadata['captureEpoch']
                and metadata['sourceInterval100ns'][0] <= row['evidence']['sourceTimestamp100ns'] <= metadata['sourceInterval100ns'][1]
                for row in templates), 'Training provenance differs from the whole native lease')
    result = json.loads(json.dumps(base))
    result['trainingRuns'].append(metadata)
    distinct(result['trainingRuns'])
    result['prototypes'].extend(row for row in templates if row['evidence']['frameId'] in missed_frame_ids)
    LandmarkRecognizer(result)
    return result


def freeze(folder, base, qualification, output):
    """Recompute failure authority, retain its originals, and predeclare a separate prospective comparison."""
    folder, output = Path(folder).resolve(), Path(output).resolve()
    repo = Path(__file__).resolve().parents[2]
    require(folder.is_relative_to(repo/'artifacts/live') and not output.is_relative_to(folder),
            'Use original managed evidence and a separate new candidate directory')
    head = LandmarkRecognizer.load(base)
    require(head.checkpoint_id == G4_SHA256, 'This natural-failure trainer requires the exact qualified G4 incumbent')
    proof = audit_failure(folder, base, qualification, repo)
    require(proof['status'] == 'failed-natural-photo' and proof['verifiedPrefix'] is True,
            'Only an independently verified natural recognition failure is training material')
    metadata, templates, source = source_views(folder/'patrol.json', head, True)
    originals = [row for row in source['photos'] if row['training']]
    misses = [row['frameId'] for row in originals if row['prediction']['station'] != row['station']]
    data = extend_template_bank(head.data, metadata, templates, misses)
    candidate = LandmarkRecognizer(data)
    # Replay all original arrivals, not correlated retries; training agreement is never held-out accuracy.
    for row in originals:
        pixels = original_rgb(Path(row['pngPath']), row['pngSha256'], row['rgbSha256'])
        require(candidate.predict(pixels)['station'] == row['station'], 'The candidate does not preserve every training arrival')
    source_raw = encoded(dict(scope='whole failed lease is training, never evaluation',
        humanExpertDemonstration=False,supervision='independently audited native map pose and release',
        source=source,independentFailureAudit=proof,selectedOriginalFrameIds=misses))
    data.update(parentCheckpointSha256=head.checkpoint_id,augmentationManifestSha256=sha(source_raw))
    raw = encoded(data)
    qpc = native_qpc_sample()
    require(qpc is not None, 'Windows QPC required before prospective qualification')
    freeze_record = dict(format='bettergi-natural-photo-miss-freeze-v1',authority='shadow only',
        checkpointSha256=sha(raw),incumbentSha256=head.checkpoint_id,sourceManifestSha256=sha(source_raw),
        frozenAtUtc=datetime.now(timezone.utc).isoformat(),
        freezeQpc=dict(clock='windows-query-performance-counter',frequencyHz=qpc[0],ticks=qpc[1]),
        inheritedPrototypes=len(head.labels),addedPrototypes=len(misses),totalPrototypes=len(candidate.labels),
        excludedWholeTrainingRun=metadata,trainingOriginals=len(originals),correlatedRetriesExcluded=len(source['photos'])-len(originals),
        implementationSha256={name:sha(Path(__file__).with_name(name).read_bytes()) for name in
            ('freeze_photo_miss_candidate.py','landmark_recognizer.py','freeze_landmark_candidate.py','audit_queue_failure.py')},
        historicalGate='No new errors on the pinned original-image panel; decoded recordings reported separately',
        holdout=dict(circuits=20,predeclaredRuns=1,newLeaseAfterFreeze=True,uniquePerClassMinimum=20,
            noPerClassRegression=True,strictNetImprovement=True,strictGainAfterMovement=True,
            initialTrainingPoseMayNotBeSoleGain=True),
        promotion='All historical and prospective gates must pass; a manual restart is not autonomous recovery')
    output.mkdir(parents=True,exist_ok=False)
    for name,content in (('gen-09.json',raw),('source-manifest.json',source_raw),('freeze.json',encoded(freeze_record))):
        with (output/name).open('xb') as stream:
            stream.write(content)
    return freeze_record


def main():
    """Write one immutable candidate; this command never launches a model or acquires game input."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('folder','base','qualification','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    result = freeze(args.folder,args.base,args.qualification,args.output)
    print(json.dumps(result,allow_nan=False))


if __name__ == '__main__':
    main()
