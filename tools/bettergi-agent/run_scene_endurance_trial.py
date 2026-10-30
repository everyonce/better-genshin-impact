"""Execute the independently reviewed, single-use scene-observer endurance qualification on SIREN."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import uuid

import run_destination_batches as batches
from scene_endurance_trial import issue,reviewed_owner


def run(comparison,evidence_root):
    """Reuse the existing adaptive publisher and supervisor with a separate explicit experimental permission."""
    comparison,evidence_root=Path(comparison).resolve(),Path(evidence_root).resolve()
    identity,predecessor=reviewed_owner(comparison)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder=evidence_root/f'batches-{stamp}-{uuid.uuid4().hex[:12]}'
    (folder/'batches').mkdir(parents=True,exist_ok=False)
    args=batches.launch_options(['--batches','40','--leg-limit','256','--start-station','stair-front',
        '--open-queue','--endurance','--target-gameplay-seconds','600','--seconds','900','--owner-from',str(predecessor),
        '--landmark-shadow',str(comparison/'g10-shadow.json'),'--photo-qualification',str(folder/'scene-endurance-permit.json'),
        '--steering-shadow',str(batches.patrol.ROOT/'artifacts/agent/steering/gen-01.json')])

    class SceneQueueGuard(batches.BatchGuard):
        """Issue only after ordinary owner admission and after its immutable publisher policy exists."""
        def admit(self,lifecycle,root,child):
            """Keep the original monitors and sender; add no input or recovery mechanism."""
            super().admit(lifecycle,root,child)
            if self.identity!=identity:
                raise ValueError('Scene endurance owner differs from the reviewed predecessor')
            issue(args.photo_qualification,comparison,self.identity,self.deadline_ns,args.goal_embedding)

    result=batches.warm.run(args,folder,guard_type=SceneQueueGuard)
    print(json.dumps(dict(folder=str(folder),status=result['status'],reason=result.get('reason'))))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison',type=Path,required=True)
    parser.add_argument('--evidence-root',type=Path,required=True)
    args=parser.parse_args()
    raise SystemExit(0 if run(args.comparison,args.evidence_root)['status']=='completed' else 1)
