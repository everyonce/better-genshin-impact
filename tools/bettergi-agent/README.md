# BetterGI local agent prototype

The installed CUDA environment is `D:\work\genshin-auto\artifacts\agent\envs\gamescaling\Scripts\python.exe`. The original system Python remains separate. No environment installer is supplied. Exact installed versions and model/source revisions are saved under `artifacts/agent` by setup and benchmark commands.

This prototype uses real downloaded checkpoints. It does not claim trained Genshin competence. Historical frame replay establishes inference speed and parsing; live gameplay, resource limits, task success, and adaptation require separate evaluation.

## Start the local stream

1. Use the approved **Start Genshin in RDP** launcher to start or reuse the minimized RDP host and child game runtime. The [RDP automation guide](../rdp-automation/README.md) covers the stable shortcuts, saved Windows sign-in, commands inside the child session and child-only hot replacement.
2. Launch `stream_client.py --resident` inside that actual RDP Windows session, using the installed GPU Python. From the main desktop, use the guide's `rdp_control.py exec` command to dispatch it into RDP. Resident mode authenticates the child and starts its stream; it never falls back to console input. Both the server and client must enable input before a model action is submitted.

For the already configured session 3, this bounded observation-only command requires no model loading or game input. Use unique recording/output paths for each run:

```powershell
& D:/work/genshin-auto/artifacts/agent/envs/gamescaling/Scripts/python.exe `
  tools/bettergi-agent/stream_client.py --resident --rdp-session-id 3 `
  --model observe --observation-profile p2p-native-hamming-192-v1 `
  --seconds 30 --segment-seconds 30 --preview `
  --record-dir artifacts/agent/recordings/first-observation --ffmpeg C:/programs/ffmpeg.exe `
  --output artifacts/agent/benchmarks/first-observation.json
```

The [streaming guide](STREAMING.md) documents input opt-in, text goals, pause/resume, idle recovery, observation profiles and recording limits. Manual/nonresident streams remain available through the [headless bridge commands](../../Docs/design/agent-stream.md#headless-launch).

An observation session sends a bounded queue of RGB frames to FFmpeg independently of capture and inference. The resulting H.264 video is lossy, with synthetic fixed-rate playback timestamps. `frames.jsonl` maps actual encoded indices to source metadata; `observations.jsonl` separately retains received headers even when the video queue drops an image. Use native source clocks and execution receipts for analysis, and reject affected training windows after metadata, receipt or video loss. Model-generated trajectories are not expert demonstrations, and these recordings do not establish physical-input or game-render timing.

For pretrained Open P2P inference, replace `--model observe` with:

```text
--model open-p2p --source artifacts/agent/sources/open-p2p --checkpoint artifacts/agent/models/open-p2p-150M/150M/checkpoint-step=00500000.ckpt --history 200 --cuda-graph --p2p-fast-start
```

The producer consumes fresh frames independently of inference through one replaceable slot. Slow models skip old frames rather than build a backlog. The controller rejects stale/expired actions and releases held inputs when the action horizon expires. Open P2P predicts a held-key state and relative mouse event; this adapter assigns a 50 ms interval, rather than predicting duration. An explicit `--action-hold-ms 100` selects the bounded hold used in the live trials. Replacement preserves common held keys. GameScaling predicts six steps totaling 200 ms. The first-input freshness deadline is separate from the hold horizon.

In the r14 Release comparison, native-Hamming P2P directional input started at 94.57 ms median / 126.38 ms p95; all 1840 input starts respected the 150 ms deadline. The model still climbed or stalled at obstacles. The same-seed legacy trial was slower at the median but had fewer no-op proposals, so this single pair does not establish a navigation-quality winner. See the [live results and limitations](../../Docs/research/BetterGI-Agent-Sprint-Results-2026-10-23.md#r14-release-live-verification--2026-10-24-utc).

## Reproduce offline benchmarks

For CPU-only preparation of receipt-grounded history comparisons, see [Offline replay preparation](REPLAY.md). It checks recorded evidence and prepares real-frame windows; it does not run inference or produce expert training labels.
The separate [following-acquisition comparison](REPLAY_FORWARD.md) preserves
those plans and tests a next-frame action association on the same history images.

Run one GPU benchmark process at a time. These commands use actual saved Genshin frames and do not send game inputs.

```powershell
& artifacts/agent/envs/gamescaling/Scripts/python.exe tools/bettergi-agent/benchmark.py --model open-p2p --source artifacts/agent/sources/open-p2p --checkpoint artifacts/agent/models/open-p2p-150M/150M/checkpoint-step=00500000.ckpt --images artifacts/act-two-upper-contact-regression-20261019/frame-0672.png artifacts/act-two-upper-contact-regression-20261019/frame-0690.png --history 200 --cuda-graph --warmup 203 --samples 250 --output artifacts/agent/benchmarks/open-p2p-fp32rope-graph200.json

& artifacts/agent/envs/gamescaling/Scripts/python.exe tools/bettergi-agent/benchmark.py --model gamescaling --source artifacts/agent/sources/GameScaling --checkpoint artifacts/agent/models/GameScaling-0.8B-S3 --images artifacts/act-two-upper-contact-regression-20261019/frame-0672.png artifacts/act-two-upper-contact-regression-20261019/frame-0690.png --warmup 2 --samples 20 --max-new-tokens 48 --output artifacts/agent/benchmarks/gamescaling-20.json

& artifacts/agent/envs/gamescaling/Scripts/python.exe tools/bettergi-agent/benchmark.py --model gamescaling --source artifacts/agent/sources/GameScaling --checkpoint artifacts/agent/models/GameScaling-0.8B-S3 --images artifacts/act-two-upper-contact-regression-20261019/frame-0672.png artifacts/act-two-upper-contact-regression-20261019/frame-0690.png --cuda-graph --warmup 2 --samples 20 --max-new-tokens 48 --output artifacts/agent/benchmarks/gamescaling-graph20.json
```

Reports include source revision, weight hashes, installed packages, image hashes, seed, warmup, per-frame timings, first-token versus complete-action latency, parsing, overwritten frames, and peak PyTorch VRAM. Pixels are predecoded, so offline latency excludes live capture, transport, game rendering, and input-to-display delay. Replay is open loop and may use a different frame cadence from training. It is not a task-completion benchmark. GPU memory allocated by the game is not included in PyTorch's peak-memory counter.

In the original offline benchmark on this RTX 2080 SUPER, the corrected 200-frame P2P graph ran 250 measured actions at 27.32ms median / 28.14ms p95; its 30Hz replay frame-age-inclusive p95 was 54.99ms. The matched steady eager run was 209.71ms / 244.02ms. That growing-history benchmark spent about 39 seconds filling and validating its context. Current resident mode requires masked fast startup instead; it starts with empty history and keeps unused cache capacity masked. The position diagnostic passed beyond the old 9000-step reset boundary without a reset.

GameScaling's 20-action median improved from 2012.31ms to 494.48ms using its whole-token graph; p95 improved from 2443.05ms to 531.37ms. It still misses its 200ms action horizon. All GameScaling replay outputs were no-op chunks. Parsing and static protocol compatibility therefore establish neither useful behavior nor actual execution. See `Docs/research/BetterGI-Agent-Sprint-Results-2026-10-23.md` for the combined sprint results and remaining live qualification.

## Native compatibility changes

- **GameScaling:** Uses its official prompt, original checkpoint chat template, special action tokens, and action-only prefix. Native Transformers SDPA runs in FP16 on Turing. Qwen3.5's linear-attention/convolution reference kernels work without native Linux extensions but are slow. Only complete, finite action chunks are accepted. Mouse deltas are per-mille of source dimensions and are applied once per chunk. Number-key and function-key capitalization stays distinct. Scrolling is recognized but not submitted because the first bridge does not support it.
- **Open P2P:** Uses its original image encoder, transformer, action heads, KV state and action mapping. Tensor-only checkpoint loading is strict. A generated source copy under `artifacts/agent/compatibility` removes training/Unix transport imports, selects FP16, and evaluates the original attention mask using native SDPA. The upstream repository stays unchanged, and a manifest records source modifications and hashes. The default no-text path uses the learned no-text embedding. Optional text goals use a separately prepared official encoder embedding, loaded once outside the frame loop. Mouse decoding follows the checkpoint's `truncated_normal` setting by default; `--p2p-mouse-sampling` records explicit alternatives. Resident input rolls back rejected proposal history and resets after accepted-but-unapplied receipts; accepted history still contains sampled actions rather than a reconstruction of actual execution timing.
- **Image profiles:** The legacy default uses native→640×360 OpenCV Area→192×192 Pillow Bilinear. The opt-in `p2p-native-hamming-192-v1` profile performs direct native→RGB192 interpolation matching the pinned upstream Rust Hamming reference and skips the second resize. Profile/dimension checks precede inference. Native world/motion checks still inspect the original capture; the old 16:9 client minimap heuristic is unavailable for square payloads.
- **CUDA graphs:** Open P2P graph capture verifies actions and cached state against eager inference with identical input and sampling values. `--p2p-fast-start` uses fixed-capacity storage with a validity mask, so unused entries are not treated as gameplay history; a history reset retains the validated graph. The older growing-history path and offline benchmarks retain their declared warmup context. A short `--history 32` configuration changes temporal context with unverified effects on gameplay quality; the released configuration uses 200.

## Verification

The experimental step-application bridge, queued successor, native history owner
and checkpoint load scope have 192 portable, CPU-only checks. From the repository root, run them
with Python 3.11; no model, GPU or running BetterGI instance is required:

```powershell
python -B -X utf8 -m unittest discover -s tools/bettergi-agent -p "test_step_application_*.py" -v
python -B -X utf8 -m unittest discover -s tools/bettergi-agent -p "test_checkpoint_load_scope.py" -v
```

The first command contains 149 checks and the second contains 43. They exercise
the actual Bridge with in-memory transport, partial writes, strict parsing,
application/terminal ordering, bounded packets, native history/RNG ownership and
checkpoint-load cleanup using fake numerical objects. The guarded candidate
validation passed these 192 cases plus five harness checks. The installed files
match those qualified bytes. The capacity test creates and removes its own
temporary evidence when run normally; our research runner can instead retain it.
That standalone cleanup path also passed under the existing guards. These checks
did not import a model runtime or exercise a real checkpoint.

The owner may publish history after a complete software application, retain the
unresolved terminal and prepare one successor. It preserves uncertain outcomes
and forbids publishing that successor until its predecessor reconciles. Explicit
v2 supports one active 50 ms action and one immutable queued successor. A valid
handoff retains shared held keys and records the successor's actual software
calls before retiring its predecessor. Missing, expired or uncertain successors
close the chain; the fixed boundary and original frame deadlines are not renewed.
The capability and checkpoint scope remain disabled. Actual numerical
qualification, runtime activation and observation/dispatch timing remain pending.
A software application record does not confirm physical input delivery or
completion of the action's hold interval. The qualified adapter and loader files
use explicit LF Git attributes because their admission guards check exact bytes.

`--cuda-graph` also supports GameScaling. Original multimodal prefill feeds Transformers' static hybrid cache, followed by one captured whole-token decode step. The adapter validates logits and every mutated cache tensor against eager execution, and checks its first two complete greedy outputs token-for-token against original `generate()`. These checks increase startup cost and are included in warmup time. A changed prompt capacity triggers graph recapture; the live gate keeps slow startup/capture actions from reaching the controller.

P2P evaluates the original FP32 rotary-position formula directly on the GPU. This prevents FP16 position overflow and removes the finite-cache reset/pause; temporal K/V history still rolls at 200 frames. Tests compare exact values against the original FP32 cache, including positions beyond 65504. `--position-offset` exercises large positions in an offline diagnostic; it does not create prior gameplay experience.

```powershell
& artifacts/agent/envs/gamescaling/Scripts/python.exe -m unittest discover -s tools/bettergi-agent -p "test_*.py" -v
```

The model tests compare the original causal mask and decode offsets against explicit masked-softmax attention, and check per-mille conversion, complete-action validation and key naming. Successful inference does not prove visual understanding or Genshin task completion. Preserve the initial eager and optimized JSON reports for comparison.

Official upstreams: [GameScaling](https://github.com/THUSI-Lab/GameScaling), [Open P2P](https://github.com/elefant-ai/open-p2p). The generated Open P2P source copy includes its upstream MIT license. Models are stored under ignored workspace artifacts; no `BetterGenshinImpact/Assets` directory is introduced.
