"""Run only the reviewed four-photo G10 experiment on the original minimized RDP pair."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import uuid

import run_warm_photo_requests as warm
from scene_photo_trial import DESTINATIONS,issue,prerequisites


def run(comparison,evidence_root):
    """Reserve separate evidence and let the existing warm supervisor own all input, STOP and release behavior."""
    comparison,evidence_root=Path(comparison).resolve(),Path(evidence_root).resolve()
    identity=prerequisites(comparison)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder=evidence_root/f'trial-{stamp}-{uuid.uuid4().hex[:12]}'
    folder.mkdir(parents=True,exist_ok=False)
    arguments=['--start-station','stair-front','--seconds','90','--landmark-shadow',str(comparison/'g10-shadow.json'),
        '--photo-qualification',str(folder/'scene-photo-permit.json'),
        '--steering-shadow',str(warm.patrol.ROOT/'artifacts/agent/steering/gen-01.json')]
    for index,station in enumerate(DESTINATIONS,1):
        arguments+=['--destination',f'scene-{index}',station]
    args=warm.options(arguments)

    class TrialGuard(warm.WarmGuard):
        """Restrict the existing supervisor to the audited owner and issue its exact short plan once."""
        def __init__(self,directory,options):
            """Prepare a permit after the supervisor has exclusively written the immutable request file."""
            super().__init__(directory,options)
            self.required_identity=identity
            issue(options.photo_qualification,comparison,directory/'photo-requests.json',identity,self.deadline_ns,options.goal_embedding)

    result=warm.run(args,folder,guard_type=TrialGuard)
    print(json.dumps(dict(folder=str(folder),status=result['status'],reason=result.get('reason'))))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison',type=Path,required=True)
    parser.add_argument('--evidence-root',type=Path,required=True)
    args=parser.parse_args()
    raise SystemExit(0 if run(args.comparison,args.evidence_root)['status']=='completed' else 1)
