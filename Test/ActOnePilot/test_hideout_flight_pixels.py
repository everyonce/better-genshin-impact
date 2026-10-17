"""Recorded-image regression: Space text alone must not prove special-domain flight."""
import json,unittest
from pathlib import Path
from PIL import Image
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
ROOT=Path(__file__).resolve().parents[2]
class FlightPixels(unittest.TestCase):
 def test_actual_positive_and_ground_jump_negatives(self):
  t=np.array(Image.open(ROOT/'BetterGenshinImpact/User/JsScript/ActOnePilot/assets/hideout-flight-control.png').convert('L'),dtype=float);z=t-t.mean()
  cases=json.loads((ROOT/'Test/ActOnePilot/fixtures/hideout-flight/manifest.json').read_text())
  for case in cases:
   with self.subTest(frame=case['label']):
    a=np.array(Image.open(ROOT/case['fixture']).convert('L'),dtype=float);w=sliding_window_view(a,t.shape);m=w-w.mean(axis=(-2,-1),keepdims=True)
    scores=(m*z).sum(axis=(-2,-1))/np.sqrt((m*m).sum(axis=(-2,-1))*(z*z).sum());peak=float(scores.max())
    self.assertEqual(peak>=.85,case['flightVisible']);print(case['label'],round(peak,3),case['flightVisible'])
if __name__=='__main__':unittest.main()
