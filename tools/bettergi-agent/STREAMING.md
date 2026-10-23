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
