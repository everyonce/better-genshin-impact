"""Validate the exact launcher-to-existing-supervisor contract without opening a control pipe."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_scene_photo_trial as trial


class SceneTrialLauncherTests(unittest.TestCase):
    """Construct the real four-request CLI and guard while replacing all external execution."""
    def test_names_bounds_owner_and_guard_use_the_existing_launcher(self):
        with tempfile.TemporaryDirectory() as temp:
            identity=dict(root=dict(processId=10,instanceNonce='a'*32,windowsSessionId=1),
                          child=dict(processId=20,instanceNonce='b'*32,windowsSessionId=3))
            def supervise(args,folder,*,guard_type):
                """Inspect the real parsed plan and create no native job or model."""
                self.assertEqual([r['destination'] for r in args.plan['requests']],trial.DESTINATIONS)
                self.assertEqual((args.plan['start'],args.destination_legs,args.seconds),('stair-front',8,90))
                self.assertEqual([r['name'] for r in args.plan['requests']],['scene-1','scene-2','scene-3','scene-4'])
                guard=guard_type(folder,args)
                self.assertEqual(guard.required_identity,identity)
                return dict(status='completed')
            with (patch.object(trial,'prerequisites',return_value=identity),patch.object(trial,'issue') as issued,
                    patch.object(trial.warm,'run',side_effect=supervise) as runner):
                result=trial.run(Path(temp)/'comparison',Path(temp)/'evidence')
            self.assertEqual(result['status'],'completed')
            self.assertEqual(runner.call_count,1)
            self.assertEqual(issued.call_count,1)


if __name__=='__main__':
    unittest.main()
