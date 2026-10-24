# Following-acquisition replay preparation, version 1

`prepare_replay_forward.py` is a separate CPU-only preparation command. It leaves
`prepare_replay.py`, its defaults, existing plans and replay experiments unchanged.
It does not decode video, load a model, send input or prepare training data.
Explicit reviewed probes are required; it does not choose scenes automatically.

```powershell
& artifacts/agent/envs/gamescaling/Scripts/python.exe tools/bettergi-agent/prepare_replay_forward.py `
  --report artifacts/agent/benchmarks/navigation-r14-native-01-segments/00001.json `
  --recording-dir artifacts/agent/recordings/navigation-r14-native-01/00001 `
  --probe-frame-id 2392 --history-frames 40 `
  --output artifacts/research/2026-10-23/r14-native-probe-2392-forward-v1.json
```

Use one complete, closed old-style episode and all six matching evidence files
required by [REPLAY.md](REPLAY.md). Arbitrary rollover parts are unsupported.
The output must be new: the command refuses to overwrite any existing file.
`--probe-frame-id` is repeatable; `--max-windows` defaults to 6 and
`--max-source-gap-ms` to 100. No nominal 20 Hz grid, interpolation or repeated
frames are introduced. Exit 0 means at least one candidate was prepared, not
that inference or gameplay succeeded; exit 2 means no eligible candidate or
rejected evidence. Every input and both preparation modules are hashed.

The distinct output contract is `kind: p2p-offline-forward-history-candidates`,
`schemaVersion: 1`, `comparisonMode: same-frames-forward-acquisition-v1`.
It is deliberately separate from the frozen current-acquisition GPU experiments;
those runners have not been updated or validated for this schema.

Every window retains the same images, probe and goal provenance in three arms:

| Arm | Labels for history image j |
| --- | --- |
| `accepted_proxy` | Original decoded accepted proposal proxy, unchanged. Acceptance is not proof of physical execution. |
| `receipt_same_frames` | Original **preceding** interval `(previous acquisition, current acquisition]`, unchanged. |
| `receipt_next_acquisition_v1` | Complete held state at the **next selected acquisition**, plus relative mouse events in `(current acquisition, next acquisition]`. |

For the last history image, the following endpoint is the probe's immutable
`sourceFrame.acquiredAtMs`. Only that clock is used as a label endpoint. The probe
image stays outside history; its predicted action and events after the cutoff
cannot contribute to labels. Labels name their interval, endpoint role, initial
and final state evidence, all transitions and individual mouse events. The old
anchor is retained for validation, not used as the first following-label endpoint.

Receipts reconstruct **backend-dispatch intent**, not measured OS/game input.
Replacement preserves the old held state until the next applied step; completion
or cancellation releases it. Mouse events occur once in each arm and are never
repeated across a hold. Events elsewhere in the complete recording may naturally
occur after the probe, but no new label may reference them or a probe-owned action.
Exact input/acquisition boundary ties are rejected because their ordering across
clock sources is not established. Unknown initial state and all original receipt,
clock, video-join, distinct-source, readiness, epoch, geometry, observation-gap,
reset, goal and probe-exclusion guards remain. Per-window goal metadata binds to
the actual applied version/request, including changed-goal provenance.

This mirrors only the **index direction** found in pinned Open P2P
`a329d98cbe62119679a254d71bea6446773541bc`: `video_proto_dataset.py:217–240,248–275`
pairs image j with annotation j+1. Pinned Recap
`70ee48d5f4cd0f6bb19810a55b7ec1c3f36e226f` takes a buffer callback, snapshots held
state and drains asynchronously processed mouse deltas (`record_window.rs:371–382`,
`input_manager/mod.rs:255–315`). Callback time differs from immutable first
acquisition QPC; skipped selected frames also enlarge intervals. Consequently
`publishedCallbackAlignmentEstablished` remains false. This is a versioned timing
convention comparison, **not exact training alignment**.

All evidence remains explicitly model/system provenance, with
`trainingEligible: false`, `humanDemonstrations: false` and
`expertDemonstrations: false`. Native system demonstrations must never be relabelled
human: published `stage3_finetune.py:1051–1054` masks behavior-cloning labels to
user-action frames. H.264/yuv420p compression, indexed rather than wall-time video
PTS, decoded-action token proxies, cold finite histories and unverified physical
input remain limitations. No claim of Genshin training coverage, improved quality
or suitability for fine-tuning follows from preparation or label differences.

CPU checks:

```powershell
& artifacts/agent/envs/gamescaling/Scripts/python.exe -m unittest discover `
  -s tools/bettergi-agent -p 'test_prepare_replay*.py' -v
```
