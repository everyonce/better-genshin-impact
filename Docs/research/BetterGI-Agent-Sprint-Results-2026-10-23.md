# Local agent sprint: measured results

Updated October 23, 2026. This report distinguishes the implemented prototype from the live-game and learning milestones in the [original backlog](BetterGI-Agent-First-Sprint.md).

## Offline GPU and model results

The RTX 2080 SUPER (8 GiB, SM 7.5) runs both real checkpoints using the isolated Python environment at `artifacts/agent/envs/gamescaling`. PyTorch 2.7.1+cu128 and FP16 CUDA execution are verified. The installed environment is preserved; no installer is supplied, as requested. Exact versions are in `artifacts/agent/gpu-environment.lock.txt`. Model downloads are pinned, with hashes and revisions in each model's `provenance.json`.

These results replay two historical Genshin screenshots through a latest-frame producer at 30 Hz. They exclude live capture, transport, game rendering, input delivery, and competition with the game for GPU resources. A parsed action is not evidence of useful gameplay.

| Configuration | Responses | Complete inference p50 / p95 | Replay observation-to-action p95 | Peak PyTorch allocation |
|---|---:|---:|---:|---:|
| Open P2P 150M, FP16, 200-frame history, CUDA graph, corrected FP32 positions | 250 | 27.32 / 28.14 ms | 54.99 ms | 836 MiB |
| GameScaling 0.8B S3, FP16 native Transformers baseline, thinking disabled | 20 | 2012.31 / 2443.05 ms | 2444.51 ms | 2371 MiB |
| GameScaling 0.8B S3, whole-token CUDA graph and static hybrid cache | 20 | 494.48 / 531.37 ms | 543.83 ms | 2371 MiB |

All runs parsed every measured response. GameScaling returned no-op chunks on these two screenshots. It generated 30 tokens per response. CUDA graph decoding reduced its median complete response time by 4.07 times: about 207 ms to the first token, then 9.92 ms per additional token, compared with about 62 ms per additional token in the baseline. Captured logits and all cache tensors were checked against eager execution; the first two complete generated token sequences also matched Transformers generation exactly. Its p95 still exceeds its 200 ms action horizon, so the live client rejects it for direct control at that cadence.

P2P meets its 50 ms model-compute budget; the longer replay does **not** pass a strict 50 ms observation-to-action p95 gate. Its initial model load took 6.1 seconds and filling the real 200-frame history plus graph warmup took 39.1 seconds. The client suppresses over-budget warmup actions. CUDA graph capture compares action outputs and temporal state with eager execution before use. FP32 rotary-position computation removes FP16 position rounding and the former periodic cold reset.

Evidence: `artifacts/agent/benchmarks/open-p2p-fp32rope-graph200.json`, `artifacts/agent/benchmarks/gamescaling-20.json`, and `artifacts/agent/benchmarks/gamescaling-graph20.json`. Reproduction commands and compatibility details are in [the agent README](../../tools/bettergi-agent/README.md).

## Implemented control and recording path

BetterGI owns capture and input through its existing task scope. A local named pipe publishes bounded, latest-only RGB frames independently of OCR, inference, and file writes. An independent controller applies expiring actions and releases input on cancellation, focus loss, resizing, disconnection, or missed deadlines. It requires both an actual RDP session and BetterGI's explicit child-session role. Inputs require opt-in on both sides.

The existing pilot's PNG proof writes now run on a bounded background writer and overlap OCR. Proof durability is still awaited before the observation returns; failed storage still blocks the supervised pilot. A new live speedup measurement remains outstanding.

The recorder writes video and execution metadata on a worker with bounded queues, explicit drop/error reporting, and a storage budget. A 60-frame synthetic recording encoded all frames with no loss; enqueue p95 was 0.037 ms. A separate real Windows named-pipe integration exercised the actual observation client and FFmpeg, preserving all nine frames and final stop receipts. These are synthetic transport/recording tests, not live game demonstrations.

The recorder currently captures automated input receipts, not human demonstration events. Capture timestamps describe host capture requests; visual action alignment, human hooks, task labels, training, and held-out gameplay evaluation remain necessary before claiming a learned Genshin skill.

## Verification and remaining live work

- Full solution restore/build and self-contained portable publish passed with the RDP lifecycle hooks. The latest package verified through live child replacement is `artifacts/release-r4/BetterGI-English-win-x64`, built from clean revision `b5dc287e`; its build manifest records the binary hashes.
- 27 controller/wire tests passed, including 11,000 successive actions without a lifetime restart and real pipe access checks.
- 36 external-control tests and 10 RDP lifecycle tests passed.
- Five background image-writer tests and 16 targeted pilot JavaScript tests passed.
- The final agent Python suite passed 45 tests, including actual Windows named-pipe/video integration, final-receipt draining, deadline timing, bounded trial limits, key semantics, freshness/compute budgets, and evaluation aggregation.
- The current RDP/launcher Python suite passed 63 tests, including native command cleanup, Unicode console output, Windows PowerShell 5.1 launcher checks, authenticated parent checks across hot replacement, approved-task identity validation, and capture-mode selection.
- The r4 capture/lifecycle follow-up passed 102 focused C# tests and the full solution build. These counts overlap the earlier controller and lifecycle suites.

The [RDP automation CLI](../../tools/rdp-automation/README.md) implements discovery, status, bounded connection and game startup, minimized hosting, standard-token child commands, configuration staging, and verified child replacement. Its launcher verifies package hashes and follows BetterGI's normal self-elevation to the correct process ID. Explicit automation startup suppresses informational banners. Windows authentication remains user-managed.

Live deployment reached the real RDP desktop after the user completed Windows sign-in. The user has now confirmed that Windows sign-in is saved and Genshin's game world is open. The primary runs in console session 2 (PID 28072), with Genshin (PID 27728) in RDP session 3. The host can be minimized and shown through the control endpoint. A hidden child command completed successfully with `remoteDesktop:true`, `elevated:false`, and medium integrity; the installed CUDA Python environment also detected the RTX 2080 SUPER from that same standard-token runner. Evidence is in `artifacts/rdp-automation/jobs/4d92880c-7827-4eb4-916f-33145bbcf086.result.json` and `1f35a1f0-a4a7-4e75-8ff8-2c0057ab4d4b.result.json`.

The hardcoded session-1 assumption in registered-root reporting and recovery is fixed: the authenticated endpoint's actual session now determines root identity. Live hot replacement succeeded twice, from the r1 child (PID 35832) to r3 (PID 21988), then r4 (PID 30308), retaining root PID 28072 in session 2 and game PID 27728 in session 3. The replacement attached to the existing game without replacing the primary host or game process. The CLI now waits for full game-ready state, not merely process discovery. Saved Windows sign-in uses BetterGI's Desktop Clone > Control Center > More > Remember Windows sign-in entry; its Windows Credential Manager target is stable across portable release directories.

The follow-up also adds `start-agent`/`stop-agent` for the fixed TaskRunner-owned bridge, with input disabled by default. The approved scheduled task is installed and verified. Windows returned its principal as an account name rather than the supplied SID; verification now resolves the name to the exact approved SID and still rejects unknown or different accounts. Both Host and Game shortcuts succeeded with the existing host. The protected task selects the newest verified BetterGI package for a cold start; the ordinary wrapper reuses an already verified older host and directs Genshin only into its actual RDP child. These warm shortcut checks do not establish a cold-start task launch result.

Live BitBlt capture produced invalid, all-white images in both window states:

| RDP host state | Recorded frames | Run duration | Recorded rate | Image validity |
|---|---:|---:|---:|---|
| Minimized | 259 | 11.94 s | 21.61 fps | All white; unusable game observations |
| Visible | 129 | Not reported | Not reported | All white; unusable game observations |

The transport and recorders delivered frames, but the images do not show the game and cannot support gameplay or model-quality conclusions. The initial P2P observation trial was aborted and is **not a live model benchmark result**. Automation startup had skipped the existing enabled Win11 BitBlt prerequisite; that initialization now runs before automated game launch. This corrects future startup ordering without claiming it repairs a game already launched with the old surface settings.

The new `set-capture-mode` command switched the running r4 child (PID 30308) to Windows Graphics Capture without restarting root PID 28072 or Genshin PID 27728. Visible-host recording delivered 130 usable frames. Minimized-host recording delivered 258 usable frames over 11.96 seconds, with no recorder drops; all 258 decoded images were nonblank and consecutive decoded frames changed. Representative images were visually inspected and show Kaeya in Mondstadt. The minimized run's capture work was 5.87 ms median / 11.58 ms p95; pipe round trips were 1.57 / 3.85 ms. These initial checks used the older Python polling wait and received about 21.5 fps.

The polling deficit was traced to Windows timer rounding: requesting a 33.33 ms `Event.wait` yielded 46.69 ms median / 47.77 ms p95. Absolute-deadline, bounded `time.sleep` slices measured 29.97 Hz in a 30-tick CPU test. Capture and policy scheduling now use that path. The RGB guard also correctly marked a real 44-frame all-white episode as failed, with zero model decisions; loading fades may recover when usable frames return.

A separate deterministic controller check ran with RDP minimized. It issued 100 ms forward and backward steps, recorded both completed execution receipts, and visibly changed the character's position/orientation. Capture-request-to-input-issue times were 29.53 and 35.42 ms; acceptance-to-issue times were 4.55 and 23.04 ms. These are two transport/controller checks, not model or photon-to-input latency measurements. Evidence is in `artifacts/agent/recordings/live-controller-smoke-r4` and its matching benchmark report.

## Live shared-GPU measurements

Both models ran against the actual minimized RDP game, one model at a time, with input disabled. The shared-GPU setup reported 3505 MiB used and 46% utilization before policy inference, with the GPU at 87°C and software thermal slowdown active. These results include game rendering, capture, recording, and GPU contention; they are not interchangeable with the offline table.

| Live configuration / phase | Decisions | Policy wall p50 / p95 | Estimated capture-request age p50 / p95 |
|---|---:|---:|---:|
| P2P eager history startup | 200 | 305.21 / 349.30 ms | 355.89 / 400.01 ms |
| P2P first graph construction | 1 | 1000.37 ms | 1051.11 ms |
| P2P steady CUDA graph | 417 | 55.10 / 73.93 ms | 101.96 / 142.42 ms |
| GameScaling full episode, including two validation warmup decisions | 11 | 1939.86 / 6070.20 ms | 1982.63 / 6133.90 ms |
| GameScaling after those validation calls | 9 | 1850.91 / 2586.24 ms | 1902.38 / 2678.11 ms |

P2P recorded 3072 usable frames at 27.92 fps over 110.02 seconds. The first graph result arrived 68.07 seconds after the first consumed frame. Steady policy work met a 50 ms budget in 17.27% of decisions and a 66.67 ms budget in 93.05%; only 42.93% stayed below 100 ms estimated observation age. A measured trial configuration therefore uses 15 Hz with a 150 ms freshness limit, rather than claiming a sustained 20 Hz controller. The initial observation run also exposed P2P's `LeftArrow`/`RightArrow`/`UpArrow`/`DownArrow` names; the adapter now translates them to the bridge's equivalent `LEFT`/`RIGHT`/`UP`/`DOWN` names without removing or changing actions.

GameScaling recorded 810 usable frames at 26.44 fps. All 11 outputs parsed but requested no movement or other action. Its first two decisions include exact-token validation against eager generation; the remaining nine still take roughly 1.85 seconds median. The current Windows/Turing path remains too slow for direct 200 ms control, even after the demonstrated offline decoder improvement. Its optional fused convolution and gated-delta kernels are unavailable in this installed environment; the correct reference kernels remain in use.

Both recordings completed without blank frames, recorder drops, or receipt loss. Latest-frame coalescing skipped published frame IDs, which is distinct from recorder queue loss. Timing values start at host capture requests and do not establish compositor freshness or photon-to-input latency. Source reports, video, phase analyses, and representative PNGs are in the matching `live-p2p-wgc-r4` and `live-gamescaling-wgc-r4` benchmark/recording directories.

## Bounded live P2P controller trial

With the RDP window minimized, P2P used a 15 Hz decision target, a 150 ms freshness ceiling, a movement-key subset, and a hard limit of 40 server-accepted proposals. The trial reached that limit and stopped normally. All 40 accepted IDs match unique execution receipts and applied steps: 24 `D+W`, 12 `W`, and four `A+W`, with no mouse movement or other keys. Thirty actions completed their horizons, nine were replaced by newer proposals, and the last was cancelled by the final client stop. The controller's normal release path ran; no independent OS key-state probe was performed.

The applied-input span was 2.803 seconds, with 2000 ms of requested action horizons. Recorded images visibly show Kaeya moving from the stair corner into the lane. Host-capture-request-to-first-input latency was **111.12 ms median / 133.11 ms p95**; server acceptance-to-input was **1.87 / 12.50 ms**. The 46 steady graph decisions in this short episode measured 54.88 / 100.50 ms policy wall time. Warmup and other over-budget proposals were withheld: 206 for compute time and one for age.

All 2105 frames were encoded and decoded, with no blank frames or recording/event/receipt loss. Actual received rate was 27.72 fps over 75.90 seconds. Eleven control/recording consistency checks passed. Evidence is in `artifacts/agent/recordings/live-p2p-control-r4/control-verification.json`, its `live-analysis.json`, and the matching benchmark report. This demonstrates a functioning vision-to-controller loop and bounded navigation; it does not meet a 50 ms full-loop response goal or establish quest/task competence.

The [gameplay evaluation protocol](../../tools/bettergi-agent/EVALUATION.md) compares matched task/start-state trials and keeps task success, progress, interventions, action execution, and timing separate. Its offline aggregator preserves missing outcomes as unscored. Those original GameScaling and P2P trials used a fixed generic prompt and no text, respectively, so they do not establish equivalent goal-conditioned instruction following. Replaying the saved benchmarks through the aggregator reproduced their measured medians without claiming gameplay success.

Logs and recording evidence are under `artifacts/research/2026-10-23` and `artifacts/agent`. RDP startup, warm shortcuts, standard-token child commands, child hot replacement, valid minimized game capture, bounded controller execution, and shared-GPU model inference have passed live checks. Precise input-to-screen response and useful goal-directed game behavior still require separate evaluation.

## Resident runtime and instruction conditioning

The policy can now remain loaded across pause/run commands, recording segments,
pipe disconnects, and verified BetterGI child replacement. The off-thread control
file is fail-closed; input still requires the same RDP session, owner, fresh frame,
foreground game, and current game-world evidence. Capture continues during pauses.
Two positive HUD checks establish readiness; missing HUD, recognized blocking UI,
stale capture, focus loss, or explicit release invalidates prior input authority.

P2P's masked fixed-capacity cache starts with empty history and retains its CUDA
graph across resets. A 205-step growing-cache comparison matched every sampled
action and index; FP16 cache differences stayed within the declared relative
tolerance. Rejected input predictions roll back temporal state exactly. Actual
unapplied receipts trigger history reset. Accepted predictions still do not
reconstruct a perfectly sampled 20 Hz history of what the game executed.

Official EmbeddingGemma access was authenticated locally. Goals are encoded once
on CPU with the upstream 128-token, raw hidden-state masked-mean representation;
no projection, normalization, or per-frame text inference is added. Both tested
instructions matched upstream token IDs and embeddings exactly. The explicit
street-navigation goal encoded in 379 ms after a 5.23-second CPU load. P2P retains
the goal across graph resets. GameScaling also accepts an explicit per-trial
instruction, so future comparisons can supply the same text to both policies.

A 300-second observation-only resident trial replaced child 30492/release-r5 with
child 39240/release-r6 while preserving root 28072, game 27728, RDP session 3, and the
minimized host. The process loaded the model once (21.78 seconds). Initial graph
preparation took 3.50 seconds; the first prediction after replacement took 53.60 ms
with zero graph preparation. The resumed 995 predictions measured 51.14/61.31 ms
median/p95 policy wall time. There were no accepted inputs. Both recordings
closed normally; the first segment recorded seven frame-queue drops, while the
second encoded all 1,633 frames without frame or event loss. The expected old-child
disconnect is retained as a stream-error boundary in the first segment.

Evidence: `resident-observe-r5-r6.json`, its segment reports/recordings,
`resident-replacement-analysis.json`, and `r6-resident-hot-replace.json` under
the artifact directories above. The new `--preview` option publishes a JPEG
from the recording worker for supervision without encoding on the control path.
The 67 Python checks passed, including real named-pipe and FFmpeg integration.

This run exposed a remaining bottleneck: in a 2,567-frame live snapshot, 1080p
readiness recognition took 36.10/66.61 ms median/p95 and accounted for 87% of median
capture time. The first exact-ROI optimization reduced a warmed 1080p world-frame
benchmark only from 25.98 to 25.18 ms. The production recognizer now preserves
aspect ratio while capping recognition at 960×540. In the final paired replay,
old/native-fast/reduced medians were 42.25/42.10/10.98 ms and 35.25/34.33/8.92 ms
on two real world frames. Reduced maxima were 22.06/11.41 ms under the shared
machine workload; this is not a hard sub-10 ms bound.

All 56 tested outcomes were preserved at 960×540. A 640×360 variant lost HUD
detection in 12 cases and was rejected. The initial matrix includes synthetic
modal overlays and HUD removal, so it does not establish a real UI error rate.
All 70 focused C# checks passed, including named-pipe ACL checks rerun under the
normal Windows token. Live recognition timing and useful goal-directed gameplay
remain separate checks.

Additional native screenshots from the current RDP game covered the visible
world, the real HUD-less journal transition, and the settled quest journal.
Old, native-fast, and production-960 paths agreed on all three; production
medians were 8.54, 1.38, and 1.64 ms respectively. Seven focused checks passed
(`recognition-live-fixture-replay.json`). An eight-second observation-only r6
bridge run recorded 80 journal frames, all with world readiness and input
availability false, without frame or event loss (`journal-guard-r6.json`).

GameScaling's explicit instruction path passed a real eight-sample saved-frame
GPU replay (`gamescaling-goal-8.json`). All outputs parsed but were no-ops. Full
action time was 583 ms median, with a 5.99-second first-call outlier (no warmup
was excluded). This verifies prompt plumbing, not successful navigation.
