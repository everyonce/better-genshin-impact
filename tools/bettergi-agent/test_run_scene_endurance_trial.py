"""Exercise the production queue CLI and guard wiring without a native endpoint or model."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_scene_endurance_trial as trial


class SceneEnduranceLauncherTests(unittest.TestCase):
    """The experimental runner must preserve the existing publisher and predeclared queue caps."""
    def test_exact_profile_and_owner_reach_the_existing_batch_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            identity=dict(root=dict(processId=10,instanceNonce='a'*32,windowsSessionId=1),
                          child=dict(processId=20,instanceNonce='b'*32,windowsSessionId=3))
            def original_admit(guard,lifecycle,root,child):
                """Stand in for an already verified owner without starting background threads."""
                guard.identity=identity
            def supervise(args,folder,*,guard_type):
                """Inspect the real parsed CLI and emit no job or control message."""
                self.assertEqual((args.batches,args.destination_legs,args.seconds,args.target_gameplay_seconds),(40,256,900,600))
                self.assertTrue(args.open_queue and args.endurance)
                self.assertFalse(args.manual)
                guard=guard_type(folder,args)
                guard.admit(None,identity['root'],identity['child'])
                return dict(status='completed')
            with (patch.object(trial,'reviewed_owner',return_value=(identity,Path(temp)/'previous.json')),
                  patch.object(trial,'issue') as issued,
                  patch.object(trial.batches.BatchGuard,'admit',original_admit),
                  patch.object(trial.batches.warm,'run',side_effect=supervise) as runner):
                self.assertEqual(trial.run(Path(temp)/'comparison',Path(temp)/'evidence')['status'],'completed')
            self.assertEqual(runner.call_count,1)
            self.assertEqual(issued.call_count,1)


if __name__=='__main__':
    unittest.main()
