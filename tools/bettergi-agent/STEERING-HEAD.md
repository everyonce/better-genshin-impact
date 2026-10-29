# Training a shadow steering head

The head classifies the current steering decision as forward, turn left, or turn right. It uses the current native pose and steering waypoint together with the frozen visual policy's raw proposal. Only the training process imports NumPy. The saved JSON runs with the Python standard library.

Run these commands from the repository root with Python and NumPy installed. A run argument is a completed resident manifest next to its `<stem>-segments` and `<stem>-recording` directories. Give each generation and evaluation a new output path.

```powershell
$trials = 'artifacts/live/2026-10-29-obstacle'
$models = 'artifacts/agent/steering'
python tools/bettergi-agent/train_steering.py train --train-run "$trials/post-walk-31.json" --train-run "$trials/lamp-hybrid-12.json" --train-run "$trials/planter-21.json" --eval-run "$trials/post-interrupt-47.json" --checkpoint "$models/gen-01.json" --report "$models/gen-01-r47.json"
python tools/bettergi-agent/train_steering.py evaluate --checkpoint "$models/gen-01.json" --eval-run "$trials/later-sealed-patrol.json" --report "$models/gen-01-patrol.json"
```

To compare generations, train a second checkpoint with the same training arguments plus the first completed patrol as an additional `--train-run`. Evaluate both checkpoints on the same later patrol. The loader rejects repeated resident runs, leases, and overlapping windows from the same compositor capture. Each evaluation includes the source evidence digest for comparing held-out populations across generations.

Eligible training observations have a fresh, normal ground pose and a native steering decision joined to one matching, timely applied step. Recovery, cancelled steps and compatible P2P-owned steps are excluded. Raw P2P accuracy here therefore describes the subset of decisions where the native controller intervened. Read forward and turn support, precision, recall, the full confusion table and the native five-degree rule alongside accuracy. Agreement with a teacher provides no evidence of improved gameplay.

Use `--steering-shadow=CHECKPOINT` to load the head once for a live hybrid run. After the ordinary controller dispatches or rejects a proposal, the observer grades the source frame, current waypoint and original Open P2P proposal. It journals the predicted class, softmax score, time and checkpoint hash. The head has no input handle.

## Learning station appearance

The landmark recognizer predicts a station from the center of a 192 × 192 game image. Training uses independently audited arrival images and station labels. Each unique source frame contributes one template. The evaluation checks for overlap with training leases and reports per-class recall, confusion by approach, and a training-majority reference.

```powershell
python tools/bettergi-agent/landmark_recognizer.py train --train-run <first-patrol.json> --out <generation-1.json>
python tools/bettergi-agent/landmark_recognizer.py train --train-run <first-patrol.json> --train-run <second-patrol.json> --out <generation-2.json>
python tools/bettergi-agent/landmark_recognizer.py evaluate --checkpoint <generation-1.json> --checkpoint <generation-2.json> --eval-run <unseen-patrol.json> --out <paired-result.json>
```

The live launcher accepts `--landmark-shadow=CHECKPOINT`. The recognizer sees the exact RGB frame at each verified arrival before video compression. Its report records that frame's hash and ID, predicted station and processing time. The offline comparison uses the corresponding decoded video frames. A previous circuit's return and the next circuit's start share the same frame.

To select the observer for the next patrol, pass the paired result and both frozen checkpoint hashes to `qualify_landmarks.py`. It recommends the challenger only when the held-out run includes at least ten unique images per station, total correct predictions increase and recall holds or improves at every station. The recommendation is written to a new file. Repeat training with the completed lease, freeze the next checkpoint, and collect a new held-out patrol before comparing again.

```powershell
python tools/bettergi-agent/qualify_landmarks.py --evaluation <paired-result.json> --incumbent-sha <sha256> --challenger-sha <sha256> --output <selection.json>
```

## Stationary camera calibration

Fit the separate camera-response model from two completed isolated-pulse leases. Each pulse must match one horizontal-only terminal receipt and a stationary body pose before and after. The holdout uses different count magnitudes. The calibration includes observed confidence, input provenance, a conservative settling interval and absolute yaw forecast errors relative to three fixed gains.

```powershell
python tools/bettergi-agent/camera_response.py --train artifacts/live/2026-10-29-patrol/camera-train-04.json --holdout artifacts/live/2026-10-29-patrol/camera-holdout-05.json --out artifacts/agent/steering/camera-gain-01.json
```

`CameraCalibration.load(path)` recomputes eligibility. A trial requires all signed turns correct, held-out mean absolute error below two degrees, and improvement of both 0.1 degree and ten percent over 0.10°/count. The small-angle and large-angle native references use 0.50°/count and ⅓°/count. These are response forecast comparisons. Measure route time, endpoint verification and controller input counts separately in an independent patrol trial.

`calibration.suggest(error_degrees, ms_since_last_mouse=...)` returns a signed horizontal count or `None`. Use the current qualified native pose and a conservative lower bound on time since the last applied camera input. Positive infinity is valid for the first pulse. The model abstains inside the five-degree walking band and before the prior response has settled. Output is capped at the smaller of 250 and the largest observed training count.
