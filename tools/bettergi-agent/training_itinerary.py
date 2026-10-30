"""Recover queued steering targets only from an independently qualified, immutable episode."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def qualified_edges(folder,*,repo=ROOT):
    """Bind every directed target to the original plans and their whole-run photo/receipt audit."""
    from audit_hybrid_run import batch_edges
    from destination_batch_sender import admitted_plans
    from destination_queue_limits import queue_limits
    from experience_manifest import digest_file,photo_inputs,qualify
    folder,repo=Path(folder).resolve(),Path(repo).resolve()
    if not folder.is_relative_to(repo/'artifacts/live'):
        raise ValueError('Directed training needs a retained live episode')
    owner=json.loads((folder/'warm-launcher.json').read_bytes())
    if owner.get('status')!='completed':
        raise ValueError('Directed training needs a completed owner manifest')
    observer=photo_inputs(folder,repo)
    plans=admitted_plans(folder) if owner.get('batchCount') else [json.loads((folder/'photo-requests.json').read_bytes())]
    edges=batch_edges(plans,max_batches=queue_limits(owner.get('queueLimitsProfile')).batches)
    paths={folder/'photo-requests.json',folder/'warm-launcher.json',folder/'handoff-audit.json',*observer}
    paths.update((folder/'batches').glob('*.json'))
    paths.update((folder/'jobs').glob('*.job.json'))
    for name in ('queue-policy.json','required-owner.json','scene-photo-claim.json'):
        if (folder/name).is_file():paths.add(folder/name)
    before={path:digest_file(path) for path in paths}
    proof=qualify(folder,repo,observer=observer)
    if (proof.get('passed') is not True or proof.get('verifiedLegs')!=len(edges)
            or proof!=json.loads((folder/'handoff-audit.json').read_bytes())):
        raise ValueError('Directed training plan differs from independent whole-run qualification')
    if before!={path:digest_file(path) for path in paths}:
        raise ValueError('Directed training evidence changed during qualification')
    return edges,dict(scope='Positive native steering receipts on the externally declared itinerary',
        humanExpertDemonstration=False,verifiedLegs=len(edges),
        files=[dict(path=str(path.relative_to(repo)),sha256=before[path]) for path in sorted(paths)])
