# BetterGI local agent prototype

The installed CUDA environment is `D:\work\genshin-auto\artifacts\agent\envs\gamescaling\Scripts\python.exe`. The original system Python remains separate. No environment installer is supplied. Exact installed versions and model/source revisions are saved under `artifacts/agent` by setup and benchmark commands.

This prototype uses real downloaded checkpoints. It does not claim trained Genshin competence. Historical frame replay establishes inference speed and parsing; live gameplay, resource limits, task success, and adaptation require separate evaluation.

## Start the local stream

1. Run the updated BetterGI build in its verified RDP child game session. Start the **Local Agent Stream** JavaScript project. Leave its input checkbox disabled for initial observation and model evaluation.
2. Use the installed Python to run `stream_client.py`. The default pipe is `BetterGI.Agent.local`; only the same Windows user can connect. Both sides must explicitly enable input before any model action is submitted.

The staged portable package includes `User/ScriptGroup/AgentStream.json`. Inside the verified RDP child session, this command selects that observation-only group:

```powershell
& D:/work/genshin-auto/artifacts/agent/runtime/BetterGI.exe --instance childsession --startGroups AgentStream
```

Run it only after the game's RDP session is ready; the bridge deliberately refuses an unrelated desktop session. An already-running BetterGI instance may require selecting the group through its UI instead of starting a second process.

```powershell
& artifacts/agent/envs/gamescaling/Scripts/python.exe tools/bettergi-agent/stream_client.py --pipe BetterGI.Agent.local --model observe --seconds 60 --record-dir artifacts/agent/episodes/first-observation --ffmpeg C:/programs/ffmpeg.exe --output artifacts/agent/live-observation.json
```

An observation session records a bounded queue of raw RGB frames to FFmpeg independently of capture and inference. Its video sidecar maps every encoded frame index to the server's monotonic capture clock. Use the sidecar and actual execution receipts to align demonstrations; MP4 playback time alone does not establish wall-clock alignment. Recording loss and receipt loss must invalidate affected training segments.

For pretrained Open P2P inference, replace `--model observe` with:

```text
--model open-p2p --source artifacts/agent/sources/open-p2p --checkpoint artifacts/agent/models/open-p2p-150M/150M/checkpoint-step=00500000.ckpt --history 200 --cuda-graph
```

The producer consumes fresh frames independently of inference through one replaceable slot. Slow models skip old frames rather than build a backlog. The controller rejects stale/expired actions and releases held inputs when the action horizon expires. Open P2P predicts one 50 ms interval; GameScaling predicts six steps totaling 200 ms. Neither adapter extends a stale prediction to hide inference delay.

## Reproduce offline benchmarks

Run one GPU benchmark process at a time. These commands use actual saved Genshin frames and do not send game inputs.

```powershell
& artifacts/agent/envs/gamescaling/Scripts/python.exe tools/bettergi-agent/benchmark.py --model open-p2p --source artifacts/agent/sources/open-p2p --checkpoint artifacts/agent/models/open-p2p-150M/150M/checkpoint-step=00500000.ckpt --images artifacts/act-two-upper-contact-regression-20261019/frame-0672.png artifacts/act-two-upper-contact-regression-20261019/frame-0690.png --history 200 --cuda-graph --warmup 203 --samples 250 --output artifacts/agent/benchmarks/open-p2p-fp32rope-graph200.json

& artifacts/agent/envs/gamescaling/Scripts/python.exe tools/bettergi-agent/benchmark.py --model gamescaling --source artifacts/agent/sources/GameScaling --checkpoint artifacts/agent/models/GameScaling-0.8B-S3 --images artifacts/act-two-upper-contact-regression-20261019/frame-0672.png artifacts/act-two-upper-contact-regression-20261019/frame-0690.png --warmup 2 --samples 20 --max-new-tokens 48 --output artifacts/agent/benchmarks/gamescaling-20.json

& artifacts/agent/envs/gamescaling/Scripts/python.exe tools/bettergi-agent/benchmark.py --model gamescaling --source artifacts/agent/sources/GameScaling --checkpoint artifacts/agent/models/GameScaling-0.8B-S3 --images artifacts/act-two-upper-contact-regression-20261019/frame-0672.png artifacts/act-two-upper-contact-regression-20261019/frame-0690.png --cuda-graph --warmup 2 --samples 20 --max-new-tokens 48 --output artifacts/agent/benchmarks/gamescaling-graph20.json
```

Reports include source revision, weight hashes, installed packages, image hashes, seed, warmup, per-frame timings, first-token versus complete-action latency, parsing, overwritten frames, and peak PyTorch VRAM. Pixels are predecoded, so offline latency excludes live capture, transport, game rendering, and input-to-display delay. Replay is open loop and may use a different frame cadence from training. It is not a task-completion benchmark. GPU memory allocated by the game is not included in PyTorch's peak-memory counter.

On this RTX 2080 SUPER, the corrected 200-frame P2P graph ran 250 measured actions at 27.32ms median / 28.14ms p95; its 30Hz replay frame-age-inclusive p95 was 54.99ms. The matched steady eager run was 209.71ms / 244.02ms. P2P initially spends about 39 seconds filling and validating that context. This startup history has a slower cadence than steady 20Hz control; temporal behavior still needs live validation. The position diagnostic passed beyond the old 9000-step reset boundary without a reset.

GameScaling's 20-action median improved from 2012.31ms to 494.48ms using its whole-token graph; p95 improved from 2443.05ms to 531.37ms. It still misses its 200ms action horizon. All GameScaling replay outputs were no-op chunks. Parsing and static protocol compatibility therefore establish neither useful behavior nor actual execution. See `Docs/research/BetterGI-Agent-Sprint-Results-2026-10-23.md` for the combined sprint results and remaining live qualification.

## Native compatibility changes

- **GameScaling:** Uses its official prompt, original checkpoint chat template, special action tokens, and action-only prefix. Native Transformers SDPA runs in FP16 on Turing. Qwen3.5's linear-attention/convolution reference kernels work without native Linux extensions but are slow. Only complete, finite action chunks are accepted. Mouse deltas are per-mille of source dimensions and are applied once per chunk. Number-key and function-key capitalization stays distinct. Scrolling is recognized but not submitted because the first bridge does not support it.
- **Open P2P:** Uses its original image encoder, transformer, action heads, KV state and action mapping. Tensor-only checkpoint loading is strict. A generated source copy under `artifacts/agent/compatibility` removes training/Unix transport imports, selects FP16, and evaluates the original attention mask using native SDPA. The upstream repository stays unchanged, and a manifest records source modifications and hashes. The default no-text path uses the learned no-text embedding exactly as upstream; no gated text encoder is downloaded. Mouse bin centers are used for repeatable decoding instead of truncated-normal jitter.
- **CUDA graphs:** Optional Open P2P steady-state optimization replays the same operations after its temporal cache fills. Capture verifies actions and cached state against eager inference with identical input and sampling values. Actual frames populate the cache; empty or invented gameplay history is not inserted into a live episode. Startup and graph capture remain slower. Offline graph benchmarks explicitly retain the declared warmup context. A short `--history 32` configuration lowers startup/context cost, with unverified effects on gameplay quality; the released configuration uses 200.

## Verification

`--cuda-graph` also supports GameScaling. Original multimodal prefill feeds Transformers' static hybrid cache, followed by one captured whole-token decode step. The adapter validates logits and every mutated cache tensor against eager execution, and checks its first two complete greedy outputs token-for-token against original `generate()`. These checks increase startup cost and are included in warmup time. A changed prompt capacity triggers graph recapture; the live gate keeps slow startup/capture actions from reaching the controller.

P2P evaluates the original FP32 rotary-position formula directly on the GPU. This prevents FP16 position overflow and removes the finite-cache reset/pause; temporal K/V history still rolls at 200 frames. Tests compare exact values against the original FP32 cache, including positions beyond 65504. `--position-offset` exercises large positions in an offline diagnostic; it does not create prior gameplay experience.

```powershell
& artifacts/agent/envs/gamescaling/Scripts/python.exe -m unittest discover -s tools/bettergi-agent -p "test_*.py" -v
```

The model tests compare the original causal mask and decode offsets against explicit masked-softmax attention, and check per-mille conversion, complete-action validation and key naming. Successful inference does not prove visual understanding or Genshin task completion. Preserve the initial eager and optimized JSON reports for comparison.

Official upstreams: [GameScaling](https://github.com/THUSI-Lab/GameScaling), [Open P2P](https://github.com/elefant-ai/open-p2p). The generated Open P2P source copy includes its upstream MIT license. Models are stored under ignored workspace artifacts; no `BetterGenshinImpact/Assets` directory is introduced.
