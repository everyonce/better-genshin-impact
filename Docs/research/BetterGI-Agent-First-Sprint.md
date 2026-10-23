# BetterGI learning agent: first implementation sprint

Prepared October 23, 2026 against source revision `eb3270862ed2f99aea4abc637b7e555c863c27df`. This is a proposed implementation backlog. No items below have been implemented by the research task.

The subsequent implementation task is tracked in [the measured sprint results](BetterGI-Agent-Sprint-Results-2026-10-23.md). That report distinguishes completed code and benchmarks from outstanding live-game and learning validation.

Read the [research and evidence report](D:/work/genshin-auto/Docs/research/BetterGI-Agent-Research-2026-10-23.md) for hardware limits, model sources, and rationale.

## Sprint outcome

A local, supervised vertical slice that records synchronized gameplay, executes expiring action chunks through one BetterGI input owner, and measures a small policy without blocking on recording or full-screen OCR. It should establish whether the RTX 2080 SUPER can run the intended model alongside Genshin before substantial data collection or training.

A rough planning allowance is one to two engineering weeks for the instrumentation and first comparisons, subject to model compatibility and access to repeatable game scenarios. This is an estimate, not a training or delivery guarantee. Curated demonstration collection adds actual gameplay time.

## 1. Establish a fresh performance baseline

- Record source revision, game resolution, frame-rate limit, capture backend, runtime type, and active recognition settings.
- Measure capture, quick HUD recognition, full OCR, encoding/writing, observation age, and input issue-to-acknowledgment latency separately.
- Compare four paths on the same scene: current pilot, capture alone, capture plus selected recognition, and capture plus independent recording.
- Report p50/p95 values and frame-rate/VRAM effects. Keep historical pilot results separate from this benchmark.

Acceptance: a reproducible benchmark report and evidence identifying which work can leave the control path. Do not begin by removing existing pilot checks globally.

## 2. Add a synchronized recorder

Proposed ownership: BetterGI owns game capture and executed inputs; an independent writer owns video encoding and dataset files. Python consumes recorded episodes for training.

- Use one monotonic time base with an explicit mapping to video presentation timestamps.
- Record actual human and automated input events, distinguishing their sources and avoiding duplicate labels.
- Include viewport, DPI, mouse calibration, task instruction, frame IDs, and execution receipts.
- Separate relative camera movement from absolute menu clicks and encode held-key transitions explicitly.
- Bound recording queues, report dropped frames, and mark invalid segments. Stop dataset recording cleanly when its storage budget is exhausted.
- Preserve existing proof artifacts. Store new recordings and model caches under an ignored workspace artifact directory initially.

Acceptance: inspect a short demonstration and verify that visible movement and labeled key/mouse intervals align within one captured-frame interval where the recording supports that precision. Missing frames and unaligned intervals must be detectable and excluded from training. Recheck alignment across a longer recording for drift.

## 3. Add the smallest useful agent bridge

Proposed code boundaries:

| Area | Responsibility |
|---|---|
| C# agent contracts | Versioned observation, proposal, and receipt data. |
| BetterGI runtime service | Capture publication, session lifecycle, local transport, and recorder coordination. |
| One agent game task | Own the existing task scope, select skills, and schedule accepted actions. |
| InputHub | Perform actual keyboard/mouse operations and release held input. |
| Python tool directory | Policy inference, dataset conversion, training, and offline evaluation. |

Keep the first transport local: named pipe or loopback endpoint with a per-session capability. Send image references through bounded shared memory or another measured local mechanism. Avoid synchronous base64 screenshots and disk PNGs on every action decision.

Minimum proposal envelope:

- Protocol version, runtime/session ID, input-owner epoch, request ID, and goal version.
- Originating frame ID and monotonic observation time.
- Explicit expiration and bounded execution horizon.
- Allowed held keys/buttons and typed mouse coordinates/deltas for each action step.
- Model/checkpoint identifier and action source.

Execution receipts must report acceptance or rejection reason, actual start/end times, applied actions, cancellation, and the originating proposal. Convert model-specific coordinate units at a tested adapter boundary. GameScaling's mouse units require a per-mille conversion; do not pass them directly as pixel deltas. Its mouse movement applies once per chunk, so duplicating it across all six steps would multiply the movement. Preserve its case-sensitive number-key versus function-key mapping. [GameScaling action format](https://github.com/THUSI-Lab/GameScaling)

Acceptance: cancellation, loss of focus, model crash/disconnect, obsolete goal, expired frame, invalid coordinates, and competing controller attempts are handled deterministically. A provisional input-release target is within 250 ms of a detected stop condition. Test held-key release directly rather than inferring it from a log message. Skills must reuse the current task scope because nested TaskRunner sessions are rejected.

## 4. Run the model comparison before live control

Use saved game frames first. Start with GameScaling-0.8B-S3, then attempt Open P2P 150M in a separate environment if its dependencies are practical. If either fails to load or fit, preserve the exact failure and evaluate the smaller fallback instead of repeatedly changing unrelated packages.

| Variable | Initial experiment |
|---|---|
| Precision | Supported FP16/FP32 paths first; optional quantization only after a working baseline. |
| Visual history | Short contexts, such as one, two, and five frames where the model interface permits. |
| Image size | Compare a small supported image budget against a more legible setting; preserve native-resolution OCR crops separately. |
| Generation | Action-only mode and a measured small output-token budget where supported. |
| Timing | Cold start, warmed inference, p50/p95 latency, and long-session memory behavior. |
| Output quality | Parse validity, legal action rate, temporal consistency, and obvious scene/action mismatches. |
| Shared GPU | Repeat successful configurations while the game runs at the selected settings. |

Record exact package versions, source revisions, model hashes, and peak VRAM. The listed 2.2 GB checkpoint size is not an inference-memory estimate. Do not use the published 85% GPU allocation or large context defaults while sharing 8 GB with the game.

Acceptance: choose the candidate from measured results. For direct 5 Hz control, use a provisional p95 capture-to-first-action target of 200 ms with acceptable game frame rate and memory headroom. A slower but useful model can become a planner or scene interpreter. No candidate is required to pass this gate merely because its paper reports real-time performance on different hardware.

## 5. Prove the learning loop on one skill

- Choose a repeatable route-and-interaction task with observable completion and manageable recovery.
- Collect a small clean dataset first, then compare additional collection at roughly 1, 5, 10, and 20 hours as warranted by learning curves.
- Freeze a session-level evaluation split before training. Reserve different routes or task variants for generalization checks.
- Verify forward/backward numerical stability on a tiny batch before scheduling a longer run.
- Train with the game closed. Start with small adapters or a compact policy and short context.
- Compare scripted behavior, the pretrained checkpoint, and the adapted policy on the same task definitions.
- Save interventions and recoveries for the next dataset version. Keep automatic proposals separate from human corrections and actually executed actions.

Acceptance: improved held-out task completion or recovery, with no increase in input-release failures or stale-action execution. Lower training loss alone does not satisfy this milestone.

## Initial boundaries and operating policy

Begin with one bound game runtime and one input owner. Continue known valid skills during asynchronous planning; release input when execution validity expires. Detect menus, loading, focus loss, and unsupported states explicitly. Each run should have a declared objective and limits for resource-spending actions. Unknown transactions require a defined policy rather than an inferred permission.

Do not claim deterministic environment resets for live story progress. Use repeatable activities where available and report operator-required resets honestly. Do not run a second controller alongside BetterGI.

Honor repository conventions for implementation: UTF-8 without BOM for C#, comments on added members, existing MVVM boundaries, and no new `BetterGenshinImpact/Assets` directory. After code changes, run the prescribed solution build:

```powershell
dotnet msbuild BetterGenshinImpact.sln -restore -p:Configuration=Debug -nologo -tl:off -clp:ErrorsOnly
```

Use focused behavioral tests for ownership, timing, action parsing, and cancellation. Live gameplay measurements are a separate requirement; a successful build cannot establish policy quality or responsiveness.
