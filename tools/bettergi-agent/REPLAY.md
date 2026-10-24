# Offline replay preparation

`prepare_replay.py` is a CPU-only, standard-library evidence checker. It prepares
candidate history windows for an eventual P2P sensitivity comparison. It does not
decode video, load a model, send input, evaluate task success, or create a training
dataset. Every output and label is marked `trainingEligible: false`; recorded
model/system actions are never described as expert demonstrations.

Run from the repository root, using **one complete, closed old-style episode**:

```powershell
& artifacts/agent/envs/gamescaling/Scripts/python.exe tools/bettergi-agent/prepare_replay.py `
  --report artifacts/agent/benchmarks/navigation-r14-native-01-segments/00001.json `
  --recording-dir artifacts/agent/recordings/navigation-r14-native-01/00001 `
  --output artifacts/research/2026-10-23/r14-native-replay-candidates.json
```

The report must contain that entire episode's decisions and terminal receipts.
The recording directory must contain its matching `observations.jsonl`,
`frames.jsonl`, `events.jsonl`, `recording.json`, and nonempty `frames.mp4`.
The resident summary JSON is not the segment report. **Arbitrary r15 rollover
parts are not supported:** their action receipts and histories may cross part
boundaries. Do not concatenate parts or invent missing labels to make them pass.

Defaults select up to six candidate probes, at least five seconds apart, with
40 preceding images in each arm. For a reviewed probe, add `--probe-frame-id 131`;
the option can be repeated. Other bounded controls are `--history-frames`,
`--max-windows`, `--probe-spacing-ms`, `--max-jitter-ms`, and
`--max-source-gap-ms`. The nominal grid is fixed at 20 Hz, with at most 20 ms
selection error by default; the configured tolerance must remain below 25 ms.
Actual selected timestamps and jitter are retained. No image or time step is
duplicated, interpolated, or stretched to fill a gap.

The default `--comparison-mode three-arm` prepares:

1. `accepted_proxy`: decoded accepted proposals associated with their observation
   frames. These are proxies for re-encoding, not the original sampled token IDs
   or claims about keys held when the image was acquired.
2. `receipt_same_frames`: the same images, labelled with receipt-grounded held
   states and relative mouse events.
3. `receipt_nominal_20hz`: distinct actual images selected near a 20 Hz grid,
   labelled using the same receipt reconstruction.

Use `--comparison-mode same-frames-only` for the narrower two-arm comparison:
`accepted_proxy` versus `receipt_same_frames`. This keeps precisely the same
accepted images, timestamps and probe in both arms, and omits nominal-grid
selection and jitter requirements. All source/video, receipt, distinct-frame,
observation-gap, readiness, reset, goal and probe-exclusion checks still apply.
The output explicitly records `comparisonMode`, sets
`nominalGridRequirementsApplied: false`, and leaves nominal-rate/jitter
parameters null. It never repeats or synthesizes frames.

This mode is needed because the strict grid excluded the late probes from the
r14 native run's 100- and 58-accepted-no-op stretches. It can test sensitivity
to action-history labels on those same images; it **cannot** test whether a
nominal 20 Hz history changes behavior. Do not pool it with the three-arm timing
comparison or describe it as repaired frame cadence. Choose explicit probes
with `--probe-frame-id` after reviewing their recorded scenes.

Each arm also names a real anchor image for its first interval. The anchor and
probe are excluded from the 40 history samples; the probe has no outcome/action
label. Different arms can cover different wall-time spans despite equal image
counts. These would be bounded cold histories, not restorations of the live
200-frame cache.

## Clock and action convention

Labels use server-monotonic `sourceFrame.acquiredAtMs`, the immutable first
acquisition timestamp. Reported compositor time, the conservative freshness
anchor, host request time, source identity and video index remain available
separately. Acquisition time is **not** proven game-render time.

For consecutive selected acquisition times, a receipt label covers
`(previous acquisition, current acquisition]`. It carries the complete held
controller key/button state at the interval end. Replacement preserves the old
state until the next applied step; non-replacement receipt endings release it.
Mouse events are attributed once per arm to the interval containing their
`startedAtMs`, and their deltas are summed without repeating them during a hold.
Individual events and state transitions remain in the plan for audit.

This reconstructs **backend-dispatch intent**, not independently measured OS
input or game response. Unknown initial state, missing receipts, unknown clocks,
conflicting evidence and ambiguous event ordering cause rejection. A known
recorded release can establish an empty held state; missing evidence cannot.

## Limits and results

The tool requires closed, loss-free recording summaries and matching accepted
actions/terminal receipts. It checks source/video joins and rejects windows
crossing history resets, goal/control changes, readiness or capture interruptions,
geometry changes, or the configured observation-gap limit. It hashes all six
inputs and writes an atomic JSON plan with rejection reasons. Exit 0 means at
least one window was prepared; exit 2 means rejection or no eligible windows.
Each window resolves its exact goal version/request to `initialGoalState` or a
matching applied `policyGoalChange` event and retains that metadata separately
from the report's startup policy. Missing or contradictory goal provenance is
rejected; stored goal-file paths are provenance, not proof that the file's
contents remain unchanged or that its embedding bytes were captured live.

`frames.mp4` uses H.264 CRF20/yuv420p. Decoded pixels cannot prove equality with
the RGB tensors seen live. Encoded `videoPtsSeconds` is an image index on a
constant-rate timeline, not wall-clock capture time. This command validates the
recorder's image indexes but does not decode the video or verify every encoded
frame. Original sampled action-token IDs are also absent from these reports.
Consequently, later replay must explicitly retain compressed-image and
re-encoded-proposal limitations; exact live-cache parity needs different evidence.

Automatic probes are availability candidates biased toward complete, low-jitter
windows. Review their scenes before selecting idle, movement or obstacle cases.
Neither preparation nor a change in sampled keys establishes better gameplay,
Genshin training coverage, or suitability for fine-tuning. The recorded 150 ms
first-input deadline policy is retained as provenance; this command does not
modify any live policy or controller setting.

Focused checks:

```powershell
& artifacts/agent/envs/gamescaling/Scripts/python.exe -m unittest discover `
  -s tools/bettergi-agent -p test_prepare_replay.py -v
```
