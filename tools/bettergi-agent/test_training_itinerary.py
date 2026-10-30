"""Do not learn queued targets from self-reported action hints or unqualified route files."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from destination_batch_sender import create_plan,encode
from training_itinerary import qualified_edges


class TrainingItineraryTests(unittest.TestCase):
    """Keep the native audit mocked while exercising actual independent plan expansion and file bindings."""
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo=Path(temp.name).resolve()
        self.folder=self.repo/'artifacts/live/episode'
        (self.folder/'batches').mkdir(parents=True)
        self.first=create_plan('stair-front',[('first','sidewalk-junction'),('lamp','west-lamp')])
        self.second=create_plan('west-lamp',[('stairs','stair-front'),('junction','sidewalk-junction')])
        (self.folder/'photo-requests.json').write_bytes(encode(self.first))
        (self.folder/'batches/00002.intent.json').write_bytes(encode(dict(plan=self.second)))
        (self.folder/'warm-launcher.json').write_bytes(encode(dict(status='completed',batchCount=2)))
        self.proof=dict(passed=True,verifiedLegs=5)
        (self.folder/'handoff-audit.json').write_bytes(encode(self.proof))
        self.checkpoint=self.repo/'artifacts/model.json'
        self.permission=self.folder/'qualification.json'
        self.checkpoint.write_text('{}')
        self.permission.write_text('{}')
        inputs=patch('experience_manifest.photo_inputs',return_value=(self.checkpoint,self.permission))
        inputs.start()
        self.addCleanup(inputs.stop)
        audit=patch('experience_manifest.qualify',return_value=self.proof)
        self.audit=audit.start()
        self.addCleanup(audit.stop)

    def test_preserves_direction_and_global_request_numbers_across_batches(self):
        edges,proof=qualified_edges(self.folder,repo=self.repo)
        self.assertEqual(edges,[('stair-front','sidewalk-junction',1,'sidewalk-junction'),
            ('sidewalk-junction','west-lamp',2,'west-lamp'),('west-lamp','sidewalk-junction',3,'stair-front'),
            ('sidewalk-junction','stair-front',3,'stair-front'),('stair-front','sidewalk-junction',4,'sidewalk-junction')])
        self.assertFalse(proof['humanExpertDemonstration'])
        self.assertTrue(any(row['path'].endswith('00002.intent.json') for row in proof['files']))

    def test_failed_owner_or_different_saved_audit_is_rejected(self):
        (self.folder/'warm-launcher.json').write_bytes(encode(dict(status='failed',batchCount=2)))
        with self.assertRaisesRegex(ValueError,'completed owner'):qualified_edges(self.folder,repo=self.repo)
        self.audit.assert_not_called()
        (self.folder/'warm-launcher.json').write_bytes(encode(dict(status='completed',batchCount=2)))
        (self.folder/'handoff-audit.json').write_bytes(encode(dict(self.proof,passed=False)))
        with self.assertRaisesRegex(ValueError,'whole-run qualification'):qualified_edges(self.folder,repo=self.repo)

    def test_changed_plan_during_audit_is_rejected(self):
        def mutate(*args,**kwargs):
            path=self.folder/'photo-requests.json'
            path.write_bytes(path.read_bytes()+b' ')
            return self.proof
        self.audit.side_effect=mutate
        with self.assertRaisesRegex(ValueError,'changed during qualification'):qualified_edges(self.folder,repo=self.repo)

    def test_declared_leg_count_must_match_actual_qualified_route(self):
        self.proof['verifiedLegs']=6
        (self.folder/'handoff-audit.json').write_bytes(encode(self.proof))
        with self.assertRaisesRegex(ValueError,'whole-run qualification'):qualified_edges(self.folder,repo=self.repo)
