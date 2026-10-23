# Continuous client and recordings

`stream_client.py` defaults to observation only. Its capture reader polls at 30 Hz,
keeps one latest image for the policy, and sends frames to a bounded recorder queue.
The model clock is independent: Open P2P defaults to 20 Hz (its 50 ms action cadence),
and GameScaling to 5 Hz. `--decision-hz` and `--policy-fps` are aliases. Missed decision
ticks are skipped; the client never replays a backlog of stale images.

Capture and policy waits use absolute deadlines with short high-resolution sleeps.
On this Windows machine, `Event.wait(1/30)` took about 47 ms and reduced a requested
30 Hz capture poll to roughly 22 Hz. The bounded sleep slices retain prompt
cancellation without accumulating that timer-rounding delay.

`--cuda-graph` opts into the selected model's validated graph implementation.
Open P2P's real history must fill before graph capture. Slow eager warmup remains observation only even when input
was enabled: a prediction must finish within its decision period before submission.
This checks measured latency, not task competence. Graph latency benchmarks do not
establish gameplay success. Input also requires explicit opt-in in both BetterGI
and the client, valid allowed keys, a fresh frame, and the server's RDP/focus checks.
Action horizons and server expiry remain bounded.

For a bounded navigation trial, use `--input-keys W,A,S,D,SPACE,LSHIFT,SHIFT`
with `--enable-input`. The subset must use keys advertised by the server. A proposal
containing any other key is rejected in full; its action is never silently edited.
Relative camera movement remains supported. `--max-input-actions 40` ends the
trial after 40 server-accepted proposals and collects final stop receipts. Rejected
proposals do not consume that limit, and acceptance still does not prove execution.
The default stream has no client-side trial subset or accepted-action limit.

On this RTX 2080 SUPER while Genshin also renders, the verified bounded trial used
`--decision-hz 15 --max-observation-age-ms 150 --input-keys W,A,S,D,SPACE,LSHIFT,SHIFT
--max-input-actions 40 --enable-input`. It executed all 40 accepted proposals and
stopped; actual capture-request-to-input p50/p95 was 111/133 ms. The observation
benchmark's steady policy p50/p95 was 55/74 ms, with roughly 68 seconds of initial
history/graph startup. These measurements do not qualify the default 20 Hz target
or a 50 ms full feedback loop. See the [live results](../../Docs/research/BetterGI-Agent-Sprint-Results-2026-10-23.md)
for startup, capture, inference, execution, and task-quality limits.

The client also rejects observations older than `--max-observation-age-ms`
(100 ms by default for Open P2P, 200 ms otherwise). This is a separate freshness
check from model compute time; the server's 500 ms rejection ceiling is not a
latency target. Reports distinguish stale observations, slow inference, unsupported
keys, and unsupported scrolling without silently changing the proposed action.

Wholly black or white RGB frames are retained as evidence but skipped for policy
inference. An in-flight prediction is also withheld if the newest frame is blank.
Valid frames resume processing after a loading transition. An episode containing
no usable frames fails explicitly. Reports and frame sidecars retain capture-quality
counts; passing this narrow check does not establish that the image shows the game
or that a compositor image is fresh, so inspect representative recordings too.

## Resident gameplay and fast restart

`--p2p-fast-start --cuda-graph` starts with empty fixed-capacity K/V storage and a
GPU validity mask. Padding is never exposed as past experience. The original
rolling update, real rotary positions, policy weights, and action decoder remain
in use. Scratch graph capture does not advance episode history. `reset()` clears
history in place and retains the validated graph and its tensor pointers.

The saved-frame validation selected identical sampled actions for 205 steps,
including the first full-history rollover. Fixed/growing FP16 matrix shapes are
not bitwise identical internally: the validator requires normalized K/V RMS error
below 0.002 and normalized maximum error below 0.005. It also compares the captured
graph with same-shape eager execution. The initial elementwise checks caught
near-zero rounding differences; their failed artifacts are retained. Run
`validate_p2p_fast_start.py` for the full comparison or add `--feedback-only` for
graph/reset and accepted/rejected transaction checks. These use saved frames and
never connect to game input.

Run the following **inside the actual RDP Windows session**, after starting its
game runtime, with the installed GPU environment. Use a new output/control path
for each run. The example is a bounded navigation experiment, not a claim of
general quest competence:

```powershell
python tools/bettergi-agent/stream_client.py --resident --rdp-session-id 3 `
  --model open-p2p --source artifacts/agent/sources/open-p2p `
  --checkpoint artifacts/agent/models/open-p2p-150M/150M/checkpoint-step=00500000.ckpt `
  --cuda-graph --p2p-fast-start --decision-hz 15 --max-observation-age-ms 150 `
  --input-keys W,A,S,D,SPACE,LSHIFT,SHIFT --action-hold-ms 100 --enable-input `
  --seconds 180 --segment-seconds 180 `
  --record-dir artifacts/agent/recordings/resident-example --ffmpeg C:/programs/ffmpeg.exe `
  --output artifacts/agent/benchmarks/resident-example.json
```

Resident mode authenticates the lifecycle and streaming pipes to one enabled
BetterGI child in its own RDP session. It never falls back to the console or stops
an unrelated busy task. Weights load once. Reconnection and a replaced child get
fresh bridge ownership and empty temporal history while retaining GPU graph
storage. Each segment has its own report and optional recording; segment rollover
currently releases/reopens the stream, so use a segment as long as the desired
uninterrupted trial. The recording budget is shared across segments; capture and
inference can continue after recording is exhausted. This does not promise a
training-complete recording after the budget or any recording failure.

The new bridge requires two fresh positive world-HUD checks, detects blocking
modal templates, and releases input on focus loss, missing world evidence, or
150 ms without a checked capture. `worldReadiness` describes the current gate;
`frameWorldReadiness` describes the exact payload. Both carry source frame/time,
recognition cost and an interruption `epoch`. Old-generation proposals cannot
survive a pause-and-resume that occurs during inference. This is a conservative
HUD/template check, not comprehensive scene understanding. `release` clears held
inputs and old observations without ending capture or transport.

The resident process writes `<output>.control.json` and `<output>.status.json`.
Control polling/report IO run off the inference thread. Commands are bound to a
unique run ID; malformed/missing commands pause and stop is terminal:

```powershell
python tools/bettergi-agent/control_resident.py --file artifacts/agent/benchmarks/resident-example.json.control.json --command pause
python tools/bettergi-agent/control_resident.py --file artifacts/agent/benchmarks/resident-example.json.control.json --command run
python tools/bettergi-agent/control_resident.py --file artifacts/agent/benchmarks/resident-example.json.control.json --command stop
```

Resident input automatically enables `--p2p-execution-feedback`: rejected
predictions restore the previous K/V state exactly instead of inserting an action
that was withheld. Receipt-confirmed unapplied acceptances and interruptions clear
history. Accepted history still uses the model's sampled actions; timing is not
reconstructed into a full 20 Hz executed-action training sequence. Benchmark and
ordinary observation modes retain their original all-prediction history.

Resident mode also enables `--soft-cadence`: a missed nominal compute period is
reported but a still-fresh action may execute. The freshness ceiling is unchanged,
and missed ticks are skipped, never queued. `--action-hold-ms 100` explicitly
resamples P2P's one 50 ms key-hold interval to at most 100 ms to bridge modest jitter;
the original steps are stored as `rawPolicySteps`, keys are unchanged, and relative
mouse movement is still applied once. A fresh proposal can replace the hold early.

`--navigation-progress` compares the minimap surroundings, excluding the center
heading marker, with actual movement intervals from execution receipts. It is
enabled in resident mode and records `moving`, `stalled`, or insufficient-evidence
metrics. The current heuristic assumes the default 16:9 HUD and does not issue
recovery inputs or establish path/task success. Compare it with recordings before
using it as an autonomous recovery trigger.

## Recorder behavior

Use `--record-dir <new-directory> --ffmpeg <ffmpeg.exe>`. The directory must not
already exist. `--record-max-mib` defaults to 1024. FFmpeg encodes RGB24 with CPU
libx264 using two threads, leaving the GPU for inference.

The capture thread performs no recording JSON serialization, metadata flush, or
image encoding. The worker owns all recording file and encoder IO. There are eight
pending frame slots and 256 event slots. A full frame queue drops the incoming
recording frame and emits `recordingDrop`; inference continues using its latest
image slot. Losing an event is a recording error because execution labels would
be incomplete. Encoder failures, server receipt loss, byte-budget exhaustion, and
shutdown timeouts are also reported explicitly in stderr and the final report;
the client exits with a nonzero status after cleanup.

Files in each episode:

- `frames.mp4`: constant-rate presentation of the frames successfully encoded.
- `frames.jsonl`: one row per encoded frame, including `videoFrameIndex`,
  `videoPtsSeconds`, the original `frameId`, and server `capturedAtMs`.
- `events.jsonl`: episode metadata, proposals, recording drops, and server
  execution receipts, including final receipts collected during stop.
- `recording.json`: counts, errors, completion status, and clock-alignment notes.
- `ffmpeg.log`: encoder diagnostics.

Align observations to actual `appliedSteps[].startedAtMs` in execution receipts
using the same server clock as `capturedAtMs`. A proposal or acceptance is not proof
that an input was executed. Video presentation time is only an encoded-frame index;
it does not reconstruct wall time when frames were dropped or capture was irregular.
Exclude affected training spans across dropped frames, missing receipts, invalid
recordings, and capture gaps. `complete: true` means orderly recording completion;
it does not mean a gap-free or training-ready episode. Byte budgets are checked
between frames and at close; encoder/muxer buffering can cause a small overshoot.

This recorder does **not** capture human keyboard/mouse demonstrations yet. It
records the bridge's automated execution receipts. A human demonstration collector,
episode validation, task labels, and training/evaluation pipelines remain separate
work.

## CPU-only checks

Run `python -m unittest discover -s tools/bettergi-agent -p "test*.py" -v` from the
repository root. The Windows integration fixture creates a unique local named pipe,
serves explicitly synthetic RGB and receipts, and invokes the actual observe CLI
and FFmpeg. It never sends input or changes the production RDP guard. These tests
validate transport and recording, not a live RDP/game session or model performance.
