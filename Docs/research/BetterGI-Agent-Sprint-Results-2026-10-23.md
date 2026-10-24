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

## Sustained navigation findings and next corrections

The release-r7 navigation trial used the explicit street goal and was stopped
after a false readiness hold was identified. It recorded 2,332 frames without
frame, event, or receipt loss. Of 915 proposals, 870 were accepted and 868 applied;
783 proposals (85.57%) were raw no-ops. Applied movement keys covered 5.73 seconds
of an 85.09-second execution span. Separate ready-world no-op runs lasted 23.53
and 24.72 seconds, so detector pauses alone do not explain the policy's idling.
This trial does not establish navigation success.

After excluding only the initial graph preparation, policy execution was
52.19/62.62 ms median/p95. Capture-request-to-first-applied-input latency was
123.34/151.90 ms. The estimated observation age had mean contributions of 29.10 ms
on the server, 1.22 ms conservative full round trip, 36.50 ms from client receipt
to prediction start, and 53.75 ms of policy execution. The client waiting component
was 33.30/66.37 ms median/p95. These component percentiles must not be added.

A 17.13-second hold reported a modal overlay while the recorded city scene showed
ordinary gameplay. Later native captures remained valid world frames. A separately
labeled one-pixel translation replay reproduced the suspected resampling issue:
two of 78 translated city cases exceeded the reduced ModalStar threshold, while
all 26 actual captures and all 78 translations remained world frames at native
resolution. This demonstrates an aliasing mechanism, not an exact reconstruction
of the missing native image from that live hold. The corrective candidate requires
native confirmation of reduced ModalStar positives with unchanged thresholds.
Optional bounded native transition snapshots will preserve exact future evidence.

The native-confirmation candidate passed 75 focused C# checks, including wire
authentication and snapshot ownership, quotas, and failure handling. All 104 city
cases now match the native world classification. A separate 62-case matrix retains
real world/journal/transition outcomes and synthetic real-template blockers at
both ROI edges, in BGR/BGRA, and at three aspect ratios. Warm ordinary-world
recognition medians remain 7.36–8.04 ms; synthetic star overlays take 15.29–16.64 ms
with confirmation and remain blocked. These fixtures do not measure the full
range of real modal screens.

The client now has a tested decision-time frame refresh and a cadence that resumes
immediately after an overrun. Resident goal requests release the previous input
lease, reject predictions from a superseded control generation, and replace the
P2P goal without reloading weights or recapturing its CUDA graph. All 81 Python
checks passed, including goal changes during prediction and named-pipe/FFmpeg
integration. The combined release-r8 live validation is recorded below.

The local source audit found no RGB, normalization, text-tokenization, or sampling
temperature mismatch in P2P. Remaining differences include image resizing,
FP16/SDPA versus upstream BF16/FlexAttention, and the control/history timing.
GameScaling's tested greedy/history-zero configuration also differs from its
official temperature-one/history-five defaults. These are evaluation variables;
the current results do not prove which causes poor instruction following.

Evidence: `navigation-goal-r7.json`, its recording's `trial-analysis.json`,
`recognition-city-phase-diagnostics.json`, and `p2p-quality-contract-audit.json`.

## Release-r8 navigation and live goal changes

The 315.48-second RDP trial recorded 8,878 frames (28.14 Hz) without recording
or receipt loss. It proposed 4,793 actions, accepted 4,613, and applied 4,611.
The actual proposal rate was 15.19 Hz against the configured 20 Hz target under
the shared machine workload. Steady policy execution was 57.45/77.06 ms
median/p95; estimated capture-request age was 92.04/127.06 ms, and measured
capture-request-to-first-applied-input latency was 94.04/123.84 ms. These clocks
start at the host capture request and do not yet measure compositor or photon age.

Client receipt-to-prediction waiting measured 2.10/27.48 ms median/p95, compared
with 33.30/66.37 ms in r7. Different scenes, goals, cadence, and machine load
prevent treating this as a matched causal benchmark. Native recognition measured
8.19/12.19 ms and inclusive capture 14.51/25.12 ms.

| Goal | Proposals | Raw no-ops | Applied movement-key time | Longest ready/no-op span |
| --- | ---: | ---: | ---: | ---: |
| Descend the stairs, then follow the street | 868 | 48.96% | 24.01 s | 7.10 s |
| Stand still | 868 | 69.01% | 4.67 s | 17.29 s |
| Keep walking along the street; avoid obstacles | 3,057 | 17.86% | 134.70 s | 3.45 s |

The two requested goal IDs were acknowledged as applied. Each handoff held input
for about 100 ms. The policy loaded once in 12.17 seconds; only the first decision
prepared a graph (2.12 seconds), with no graph recapture for either goal change.
Visual supervision saw the character climb rather than descend the initial
stairs, stand beside a tower, then walk through the area around Timaeus into the
central plaza. Movement-key time is not distance or task success; the nonzero
movement under the stand-still goal also limits instruction-following claims.

Nineteen world-readiness holds totaled 3.10 seconds, with a maximum of 898 ms.
The bounded diagnostic writer retained 28 native snapshots and reported five
queue drops, with no write failures. Thirteen captured BlockingUi cases were
ordinary world views: native grayscale matching still confused stone edges and
foliage with the small gold modal star (scores 0.80023–0.81475 against 0.8).
Native confirmation fixed the earlier reduced-image aliasing mechanism but does
not eliminate this separate appearance ambiguity. Color confirmation is being
validated against these exact captures; real modal coverage remains incomplete.

A separate offline diagnostic controlled image bytes, empty temporal history,
and random uniforms across three saved views and 32 paired seeds per view.
Changing stand-still to walking changed sampled action tokens in 25/32, 28/32,
and 24/32 pairs. Movement-key frequency changed from 24 to 31, 22 to 30, and
11 to 25 cases respectively. One retained graph, unchanged goal-tensor storage,
expected FP16 embedding contents, and three exact repeat cases were verified.
This establishes immediate text-conditioning effects in those fixed states;
stand-still still emitted movement in 57 of 96 cases. It is not a gameplay
success test, and the reused seeds are not independent navigation trials.

Evidence: `navigation-goals-r8.json`, its segment report and recording's
`trial-analysis.json`/`trial-notes.json`, `recognition-r8-blocker-scores.json`,
and `p2p-goal-sensitivity-r8/results.json`. The reusable offline scripts are
`analyze_agent_trial.py` and `diagnose_p2p_goal_sensitivity.py` in the dated
research artifact directory. The RDP host stayed minimized and the game session
remained open throughout the trial and model-only diagnostics.

## Release-r9 recognition correction and source-clock discovery

The modal-star recognizer now checks every native grayscale candidate above 0.8
against the shipped template's RGB appearance, requiring RMS error at most 32/255.
All 28 retained r8 world captures and 84 phase-shift variants remain WorldHud;
224 synthetic modal overlays remain BlockingUi. The focused suite passed 67
tests, including two real journal/transition captures, candidate competition,
and bounded candidate enumeration. There is still no verified real modal-positive
capture. This offline evidence is not a live navigation success claim.

Release-r9 built from clean commit `0e3b8f94` and replaced the RDP child while
preserving the root, game process, session 3, and minimized host. Two 30-second
input-disabled recordings tested WGC v1 and v2 respectively. They retained 806
and 808 distinct source frames at approximately 27 Hz, without recording loss.
Recognition medians were 7.224 and 7.533 ms. Every reported WGC timestamp was later
than its immutable first acquisition, by median 29.403 and 29.364 ms; some were
also later than completed client receipt. Raw timestamps used 31.25 ms increments.
The strict r9 ordering check therefore rejected every frame as invalid source
timing. No policy actions were attempted in these runs.

Independent inspection found no added offset, unit-conversion error, or mismatch
between pixels and timestamps. Microsoft's documented [WGC SystemRelativeTime](https://learn.microsoft.com/en-us/uwp/api/windows.graphics.capture.direct3d11captureframe.systemrelativetime)
describes compositor QPC time; these measurements do not establish why it leads
delivery on this RDP configuration. A presentation-slot interpretation remains
an inference, not verified platform behavior.

The r10 protocol makes this limitation explicit. Source identity and the raw
reported clock remain unchanged. Its freshness anchor is the earlier of reported
time and immutable first acquisition, with the selected clock named on each frame.
Repeated cached frames retain that anchor and expire; changed timestamps on an
unchanged identity, regressions, invalid clocks, and acquisition after response
remain invalid. The 150 ms readiness limit and two-distinct-frame recovery remain.
There is no learned timestamp correction. This bounds capture freshness but does
not establish actual game-render age. Signed reported-clock age remains diagnostic;
compositor-to-acquisition delay is unknown when reported time leads acquisition.

Evidence: `recognition-r8-appearance-replay.json`,
`recognition-r8-appearance-tests.log`, `r9-build.log`, `r9-hot-replace.json`,
the `source-timing-r9-wgc1`/`source-timing-r9-wgc2` reports and recordings,
and `source-timing-r9-v1.json`/`source-timing-r9-v2.json` analyses. The r10 live
validation below passed before input was resumed.

## Release-r10 source freshness and launch validation

The input-disabled RDP3 check recorded 810 usable, world-ready frames over
30.84 seconds, at 27.46 Hz during the capture interval. All source-freshness
checks passed, with no duplicate-identity violations, clock-order violations,
epoch changes, or recording loss. First acquisition supplied the conservative
anchor for 809 frames; one frame used the earlier reported compositor time.
The original future-leading timestamps remain available as diagnostics.

First-acquisition-to-client-receipt age was 43.84/63.76 ms median/p95, with a
94.97 ms maximum. Host polling followed acquisition by 15.06/28.61 ms
median/p95, and inclusive capture plus recognition took 12.44/17.87 ms.
These measurements bound capture freshness, not game-render or photon age.
There were no policy proposals or input receipts in this validation.

The required Debug solution build and isolated release-r10 publish passed
from clean commit `329ee632`. The Python suite passed 96 tests, including real
named-pipe and FFmpeg coverage; 94 focused C# freshness, controller, snapshot,
and wire tests also passed. Child hot replacement preserved the existing game,
RDP session, minimized host, and saved sign-in state.

The existing approved launch task and protected helper hashes/permissions were
audited. Its earlier failed-registration report came from an obsolete principal
name-versus-SID comparison; current verification passes. Both approved Host and
Game launch commands successfully reused the running setup. Cold startup and a
root-host upgrade remain untested to preserve the active game session.

Evidence: `source-timing-r10-wgc2.json`, `source-timing-r10-v2.json`,
`source-timing-r10-wgc2-gpu.csv` and its metadata, `r10-build.log`,
`r10-python-tests.log`, `acquisition-freshness-tests.log`,
`acquisition-freshness-wire-tests.log`, `r10-hot-replace.json`,
`approved-launcher-audit-r10.json`, `r10-approved-host-reuse.json`, and
`r10-approved-game-reuse.json`.

## GameScaling sampled-action diagnostic

An explicit sampling mode now preserves the greedy default while supporting
temperature, top-k, and top-p outside captured decode. Each benchmark arm checked
its first two complete outputs against eager generation with matched CUDA RNG.
The two exact parity checks passed in each arm. Independent-sample mode resets
history and cycles exact image bytes with seed plus round.

Three retained r8 views and seeds 42–44 produced nine cases per arm, using history
zero, width 384, no thinking, and a 64-token cap. Greedy decoding returned nine
no-ops. Sampling at temperature 1, top-k 0, top-p 1 returned three no-ops, two
movement chunks, one interaction, and three mouse-only chunks. Six paired actions
changed; all 18 parsed and satisfied the protocol. No generated action was executed.
Sampling changes behavior here; it does not yet establish better instruction quality.

Complete inference median/p95 was 1618/2023 ms greedy and 1664/1845 ms sampled.
The arms ran sequentially under shared foreground/game/build load, so these are
descriptive measurements, not isolated comparative timing. The earlier goal-8
benchmark's six steady cases had median 580 ms after excluding its two validation
warmups. Model weights, packages, 84 visual tokens, and static-cache length 1024
matched. The newer prompts had 834 tokens versus 842; no accidental input-size
increase explains the slowdown. Both prefill and per-token decode were slower.
The opt-in invariant text-prefix experiment now fails its strict checkpoint
numerical parity gate and remains disabled by default. Its diagnostic status is
described below; no validated prefix speedup has been established.

Evidence: `gamescaling-sampling-audit.json`, `gamescaling-greedy-r8-matched.json`,
`gamescaling-sampled-r8-matched.json`, and `gamescaling-sampling-r8-comparison.json`.

## Release-r10 ten-minute navigation trial

The resident P2P policy completed a 600-second RDP3 trial with the goal
"Keep walking forward along the open street. Avoid obstacles." It loaded once
in 10.92 seconds and produced 9,524 valid proposals, of which 9,129 were accepted.
There were 393 client suppressions (323 old observations, 62 disallowed trial
keys, and eight world changes during inference) and two server rejections
(`stale_frame` and `unknown_frame`). Every accepted proposal had a receipt;
9,128 started and one was cancelled before starting. The host remained minimized.

Steady policy execution was 54.96/73.34/140.28 ms median/p95/p99. The slowest
steady decision took 711.63 ms; it is retained rather than removed as an outlier.
The first graph preparation took 1,671.68 ms and the first complete decision
1,755.35 ms. Native recognition took 8.32/12.17 ms median/p95, and inclusive
capture plus recognition 14.88/24.88 ms. These are measurements under shared
foreground and game load, not isolated GPU throughput.

The recording retained 16,174 of 16,270 received frames (96 video-frame drops),
with no event drops and a clean close. There were no source-clock or repeated
identity violations. All but 21 recorded source frames used first acquisition
as the freshness anchor. World readiness held the controller 16 times for a
combined 2.83 seconds, with a 468.60 ms maximum. No modal-overlay false positive
was reported during this run.

Behavior remains the larger limitation: 4,290 proposals were no-ops (45.04%).
One all-ready no-op sequence lasted 50.04 seconds across 861 decisions, 846 of
which were accepted. Executed movement-key time was 236.54 seconds, or 39.42%
of the recorded trial interval, accounting for held-key continuity across
replacement actions. This is not distance or task success. Selected recorded
views show street movement interspersed with repeated building climbs. The
character at the end differs from the initial character; the trial does not
establish why that change occurred. Navigation quality is not yet reliable.

Freshness-anchor-to-first-recorded-input timing joined 9,115 receipts to recorded
frames: 110.83/140.92/153.10 ms median/p95/p99 and 241.49 ms maximum. Thirteen
started receipts lacked a recorded frame because of video loss. Of the joined
starts, 154 exceeded the client's 150 ms observation budget. r10 checked that
budget before submission but did not enforce it across transport and scheduling;
these are descriptive legacy results, not a passed server deadline check.
The receipt timestamp marks server dispatch, not physical game receipt or photon
response. Capture freshness also remains distinct from actual game-render age.

Evidence: `navigation-r10.json`, its completed segment and recording,
`navigation-r10-source-analysis.json`, `navigation-r10-first-input-baseline.json`,
`navigation-r10-trial-analysis.json`, `navigation-r10-gpu.csv` and metadata,
and the timestamp-selected `navigation-r10-visual-review` images/manifest.
The older trial analyzer's reconstructed host-clock latency is not used for
these freshness-anchor measurements.

## First-input enforcement and upstream capture integration

The new optional `startBeforeMs` request deadline uses the frame's explicit
freshness anchor plus the client's observation budget. Capability negotiation
requires the server's boolean `supportsStartBeforeMs`; legacy peers retain their
existing behavior and are labeled unenforced. The server checks the deadline at
admission and immediately before the first input, refreshing the common QPC
clock under the controller lock after focus validation. This closes the queued
tick and transport gap without shortening an action that has already started.
Rejection and cancellation reasons remain observable in acknowledgements and
receipts, and accepted responses now include `acceptedAtMs`.

The focused deadline suite passed 28 tests, including queued-tick ordering,
invalid clocks, expired pending actions, key release on cancellation, and legacy
and already-started action behavior. Thirteen wire tests passed, as did four
Python deadline/reporting tests and seven observation-timing tests. Independent
review found no remaining deadline issue. The r11 live verification below
passed the first-input checks and separately exposed a readiness snapshot race.

Upstream `14537eae` was merged with the fork's source-identity protections.
WGC V2 now uses the upstream on-demand acquisition design with per-session
capture-pump ownership, generation-bound callbacks and serialized cleanup after
timed-out operations. Old published metadata is invalidated before GPU mutation;
first acquisition and source high-water marks survive transient render failure.
The focused capture/controller suite passed 104 tests, including ten new pump
and lifecycle tests; 18 Telegram/xxtui tests also passed. The pre-existing native
GPU readback can still wait indefinitely if a driver map never returns.

The upstream acquisition point moves later in the capture path. A lower measured
first-acquisition age in the next release would therefore not, by itself, prove
that game content became newer or end-to-end render latency improved. Raw source
identity, acquisition clocks and the selected freshness clock remain explicit.

Evidence: commits `ae6e95ed` and `7d4d0929`, `wgc-v2-merge-tests.log`,
`first-input-deadline-tests.log`, `first-input-deadline-wire-tests.log`, and
`first-input-deadline-ordering-tests.log`.

## GameScaling prefix-cache parity investigation

The experimental flag remains off by default and retains strict floating-cache
and logit checks plus exact complete generated-token comparison. The first real
checkpoint smoke failed the numerical gate: maximum absolute logit difference
was 0.03809. Across three fixed images, both the 740-token prefix and an aligned
704-token prefix failed; repeated original full-prefill controls were bitwise
exact. All six selected complete greedy/sampled token comparisons nevertheless
matched. That limited behavioral agreement does not validate the approximation.

A layer-zero trace found identical input, rotary positions, QKV projection and
convolution. The earliest difference appeared in the FP16 Z linear projection
when sequence geometry changed; the first strict-tolerance failure within that
layer appeared after attention normalization. Temporarily disabling reduced-
precision reductions improved some recurrent differences but still failed final
logit checks. The process setting was restored. No cache-layout or position bug
was identified by these diagnostics.

A separately labeled offline diagnostic completed five arms with nine cases
each. Baseline A1/A2 median action times were 1609/1074 ms; prefix B1/B2 and
sampled-prefix medians were 868/879/887 ms. All 45 complete-token comparisons
matched, but no action met 200 ms and the numerical gate still failed. The
floating-value mismatch bypass exists only in ignored research code. GPU clocks
and shared load drifted substantially between arms, and reference-copy overhead
was not identical in every arm; the observed difference is not a controlled
causal speedup. This experiment remains ineligible for production.

Evidence: `gamescaling-prefix-validation` smoke reports, `diagnostic-summary.json`,
`layer0-summary.json`, raw comparisons and GPU telemetry. The tracked protocol,
constraints and failed-validation status are documented in
`tools/bettergi-agent/EVALUATION.md`.

## r11 live deadline verification and readiness race

r11 was built from clean commit `6cd5d6cb` and replaced only the RDP child.
The console host stayed minimized and Genshin remained running. An immutable
archive of that commit's controller tools was used while later code was edited.
The initial input-disabled check recorded 801 distinct, usable world frames
without source-clock violations or recording loss.

The following three-minute P2P run produced 2833 proposals, 2745 acceptances,
and 2745 receipts. All 2717 recorded first input starts met the requested 150 ms
deadline. Two proposals were rejected at admission; 27 accepted proposals were
cancelled before starting because their deadline expired, and one was cancelled
for scheduler lateness. No accepted receipt or recording event was missing.
Freshness-anchor-to-first-dispatch time was 100.00/132.98/140.53 ms at
p50/p95/p99, with maximum 149.79 ms. These are server dispatch timestamps, not
physical game input or render-latency measurements.

The source audit separately failed one current-readiness clock check. Frame 61
was returned with response time 2115.2839 ms, but its current-readiness object
described frame 62, acquired at 2122.894 ms and checked at 2135.8878 ms. Its own
RGB/source metadata was correctly attributed. The handler had sampled response
time before waiting for the controller lock, allowing a newer registration to
appear in the subsequent readiness read. The next build samples clock and
readiness together under that lock, after the focus check.

Release acknowledgements now sample time after key release completes. The
server also advances its observation cutoff to that completion time without
adding another interruption epoch. A capture acquired during a delayed release
cannot count toward either of the two fresh confirmations needed to resume.
The focused C# suite passed 112 tests, including the exact r11 timestamp replay,
delayed focus, delayed release, real pipe acknowledgements, motion recognition,
source freshness and first-input deadlines. These fixes still need the next
live verification.

P2P steady policy time was 55.75/72.86/111.60 ms at p50/p95/p99. The run still
had 1126 no-op proposals (39.75%); its longest stretch contained 240 accepted and
actually applied no-ops across 13.53 seconds. All 380 recorded frames during that
stretch were usable and world-ready, and temporal history stayed populated.
This establishes policy idling rather than a transport or readiness pause.
The character also remained caught around a cart/wall; movement input alone
does not establish successful navigation. All 4895 frames were recorded with
no frame/event loss. Different scenes and run lengths prevent a controlled
quality comparison with r10.

Evidence: `r11-build.log`, `source-timing-r11-v2.json`,
`navigation-r11-first-input-analysis.json`, `navigation-r11-trial-analysis.json`,
the `navigation-r11-deadlines` report/recording/GPU telemetry, and
`r12-motion-snapshot-tests.log` under the local research/artifact directories.

## Motion evidence and bounded navigation recovery

The bridge now reports same-frame native Space/X template evidence as Normal,
Climb, Fly or Unknown. It uses the existing BetterGI key-tip assets, preserves
the world-readiness gate and does not infer grounded footing from Normal.
Unavailable, blocked or superseded evidence reports Unknown. The 25 motion tests
passed with two hash-pinned real climbing captures, five normal captures and two
blocked captures. Both climbing images correctly matched Space and X without
modifying the borrowed pixels. A genuine native flying example remains unverified.
The native replay took 0.58–0.83 ms per world image in this CPU test; this is not
a live capture benchmark. Evidence is in `native-motion-positive-replay.json`
and `native-motion-positive-tests.log`.

An optional eight-second navigation-idle reset is now implemented. It requires
explicit versioned ground-navigation intent, fresh world-ready frames and
Normal/Climb evidence. The transaction acknowledges release, discards old frames,
resets only P2P temporal history and waits behind a fresh-source barrier. Model
weights and CUDA graph stay loaded. Pause/stop/new-goal control wins; another
reset requires a matched receipt proving later directional input was dispatched.
This does not prove the character moved. Fourteen new tests, 29 scoped tests
and 70 combined regression tests passed, with independent review. The feature
remains disabled unless requested with `--navigation-idle-reset-seconds 8` and `--goal-intent ground-navigation`.

The P2P audit also found that live mouse decoding hardcoded mean bin centers
although the downloaded checkpoint specifies `truncated_normal`. For the wide
bins observed in r11, 1024 seeded upstream samples averaged roughly 186–189
horizontal units versus the fixed 322, and 35.8–36.1 vertical units versus 87.
The correction restores the checkpoint decoder and retains an explicit mean
override for older comparisons. This is a credible camera-control difference,
but does not explain the sustained exact-zero action sequence by itself.
Resize and temporal-cadence differences remain separately documented research
questions; they were not silently changed with this decoder correction.

The complete Python regression suite passed 136 tests after updating the
diagnostics setup fixture to include the protocol's required session identity.
No runtime validation was loosened. The successful run is recorded in
`r12-python-regression-rerun.log`.

## Current GameScaling graph decode attribution

A bounded prefix-disabled diagnostic preserved the original 834-token prompt,
production generation/stopping logic, graph/cache identity and complete output
tokens across three cases, with eager references and one CPU/CUDA trace. Across
87 instrumented decode steps, graph stream intervals had p50/p95 of 32.55/81.80 ms;
host graph calls were 3.24/4.98 ms. These intervals accounted for 93–96% of the
measured decode remainder and include GPU scheduling gaps.

The apparent token-copy wait is mostly earlier GPU work: all 192 GPU copies in
the trace totaled 0.748 ms. The 29 traced graph launches contained 59,653 kernels
and 710.44 ms of summed kernel durations: 374.77 ms GEMV, 289.52 ms other operations,
44.32 ms full attention and 1.83 ms convolution. Missing causal-convolution
acceleration alone is therefore a poor target. Projection cost and unfused
recurrent/normalization operations warrant further study. Profiling greatly
inflated prefill and the game/foreground workload was shared; these numbers are
diagnostic attribution, not a clean performance benchmark or an inherent floor.

Evidence: `gamescaling-decode-attribution/report.json`, `summary.json`, its
single trace and telemetry; `p2p-mouse-decoding-audit.json`; and
`p2p-resize-audit.json` (CPU mathematical reconstruction, not Rust bit parity).

## Release r12 live verification

Release r12 was built and published from clean revision `93f57a10` with .NET
10.0.402 after the required full solution build. Its assembly SHA256 is
`68bdb9f64e71adaacfe5b94ad5af8c6b9fc0b22df724824cc15463a90da87664`.
The immutable snapshot includes all 500 tracked tool files. Hot replacement
changed only the RDP child (32528 to 29704); host 28072 and game 27728 remained
running. The tested changes through this revision were pushed to the fork.

A 30-second input-disabled check recorded 804 distinct sources with no drops,
duplicates or known-source/freshness clock violations. All frames were usable,
world-ready and classified Normal. Native motion recognition measured
0.588/0.891 ms at p50/p95. Normal is still not proof of grounded footing.

The three-minute checkpoint-mouse trial used `truncated_normal`, with recovery
disabled. Of 2764 proposals, 2657 were accepted and every one of 2623 first
input starts met its 150 ms deadline. The remaining 34 accepted requests were
cancelled before starting. Both source-clock checks passed without violations.
Freshness-anchor-to-first-dispatch latency was 102.77/134.19/141.12 ms at
p50/p95/p99, with a maximum of 149.967 ms. Steady policy latency was
58.81/75.65/105.54 ms. There were 753 no-op proposals (27.24%); the longest
accepted no-op sequence spanned 5.30 seconds. All 4919 frames were recorded.
The character left the workshop area, but climbed structures and glided;
this did not establish reliable street navigation. The scene, route and load
differed from r11, so the apparent improvement is not a controlled decoder
quality comparison.

A subsequent five-minute run used the instruction “Walk along the open street.
Stay on the ground and turn away from walls,” ground-navigation intent and the
eight-second recovery threshold. It accepted 4135 of 4407 proposals. All 4100
first input starts respected their requested deadlines; 35 accepted requests
were cancelled before starting. Source timing reconstruction covered 4093 of
those starts, with p50/p95/p99/max of 102.58/132.80/141.61/149.60 ms. Both
source-clock checks passed on recorded observations. These are server dispatch
times relative to the declared freshness anchor, not physical input receipt
or game-render age.

Recovery triggered once after 127 consecutive accepted no-ops and 8.026 seconds.
It acknowledged release, reset temporal history and waited for a fresh source.
A matched W-input receipt rearmed recovery 156.35 ms after release. No graph
preparation occurred after the initial startup, confirming that this recovery
retained the loaded model and CUDA graph. Directional dispatch alone does not
prove displacement. The final preview independently showed the character on
the bridge outside Mondstadt; health had fallen from 2764 to 2488, and the run
was not a defined route-completion test.

Steady policy latency in the five-minute run was 57.85/78.57/147.34 ms at
p50/p95/p99, with a 903.98 ms maximum under shared machine load. Stale proposals
were withheld or rejected. No-op proposals were 26.68%. Recording encoded 7884
frames and dropped 53 video/frame-metadata entries, with no event loss or
missing accepted-action receipts. The recorder's `complete` flag means it
closed without an error; it does not mean there were no frame drops. The
movement analysis found 23 decision source frames missing from the sidecar,
including seven applied actions without independently reconstructable source
latency. This motivates retaining observation metadata separately from video
backpressure.

Evidence: `r12-build.log`, `r12-hot-replace.json`, `source-timing-r12-v2.json`,
`navigation-r12-first-input-analysis.json`, `navigation-r12-trial-analysis.json`,
`navigation-r12-idle-first-input-analysis.json` and
`navigation-r12-idle-trial-analysis.json`, plus their immutable runtime manifests,
segment reports, recordings and GPU telemetry under the local artifact folders.

## Game rendering cost and resize reference

Read-only Windows GPU-engine counters for game PID 27728/session 3 showed mean
3D utilization of 40.26% with policy stopped and 39.78% during active P2P, from
16 samples per observation window. These counters are not FPS or render latency,
and the scene/foreground workload was uncontrolled; similar means neither prove
nor rule out contention. Saved graphics settings include 1920x1080 windowed,
high shadows/effects/environment, extreme global illumination and SMAA. Saved
render-scale fields disagree (1.1 modern, 1.0 legacy), and runtime FPS/scale
remain unconfirmed. No graphics settings were changed.

The pinned fast_image_resize 5.1.4 Hamming interpolation was reconstructed in
independent C++ and Python integer references. Coefficients and output bytes
matched across 78 synthetic cases, padded/channel tests and three native images.
Cached-plan C++ resize plus ctypes measured roughly 1.12–1.18 ms p50 and
1.48–1.63 ms p95; this excludes capture, transport and inference. Actual Rust
execution subsequently established exact bytes for all 81 synthetic/native
fixtures, 21 quantized coefficient sets and 324 C++ layout/stride comparisons.
Unmodified fast_image_resize 5.1.4 AVX2 and scalar outputs agreed. The official
Rust 1.87 toolchain and 12 dependencies were checksum verified and kept under
workspace artifacts; all 199 original registry-source files remained unchanged.
This is fixture parity, not proof for every possible image/geometry. Production
preprocessing remains unchanged pending bridge integration and gameplay tests.

Evidence: `game-render-settings-audit-r12.json`, `game-gpu-p2p-comparison-r12.json`
and `p2p-resize-reference/` under `artifacts/research/2026-10-23/`.

## Next runtime changes awaiting live verification

The fixed `reset-navigation` command has passed independent review and 36
focused C# tests, with 56 Python reset/control tests. It owns one RDP-only task
through cleanup, teleports to reviewed Mondstadt waypoint ID10, and verifies
three fresh, distinct local-map/yaw observations. Its process identity handle
requests only query-limited/synchronize rights. The cooperative 75-second
deadline, source-freshness limits and 2D position/yaw tolerances are documented
in the RDP automation README. This is not a pitch, health, elevation or full
scene reset, and live repeatability has not yet been established.

The recorder now retains headers in a separate bounded `observations.jsonl`
queue, while `frames.jsonl` continues to index only encoded images. Observation
loss explicitly fails recording; video queue admission is not reported as
encoding success. Independent review and 43 focused tests passed, followed by
the full 142-test Python agent suite. Updated local analyzers prefer the new
sidecar, retain the old format, and pass 13 source-clock, 22 deadline and three
sidecar fixtures. The original r12 analyzer versions are preserved locally.

## r13 live verification — 2026-10-24 UTC

The full Debug solution build and isolated Debug publish passed at 00:11 UTC
with SDK 10.0.402, clean source `89ebac0b4b6800bfc1585618141f418a9f8ea763`,
and DLL SHA256 `e106a0b2d8302f5be0a1892a1d0d832b66c5787dc99f250b69f4f9e9d23c8f88`.
The release also retains 502 committed tool files and their hashes. Child-only
replacement changed PID 29704 to 12828 in RDP 3; root 28072 and game 27728 remained
running, with the host minimized.

The first fixed waypoint reset completed in 27.17 seconds. Three distinct native
observations measured `(-867.68359375, 2281.37890625)`, yaw 1.5 degrees,
position confidence about 0.996786 and yaw confidence about 0.586 on `City_102`.
The second reset-only repetition failed closed in 5.55 seconds during orientation
with `local_position_unrecognized`. No third repetition was dispatched. A
subsequent input-disabled 30-second recording showed the character at the
Mondstadt waypoint, retaining all 803 received headers and 803 encoded frames;
both source-clock checks passed with no violations. This establishes one
verified reset, not repeatable reset success. A bounded settling retry and
measured-yaw dispatch correction are prepared for the next runtime.

A separate 120-second P2P run then exercised the new recorder under actual
inference and input. It used the existing ground-street goal, checkpoint mouse
sampling, the 8-second idle-history recovery option and a 150 ms first-input
deadline. Its start was not a successfully repeated controlled reset, so it is
not a matched gameplay-quality comparison.

| Evidence | r13 result |
|---|---:|
| Proposals / accepted / rejected / not submitted | 1752 / 1651 / 4 / 97 |
| Input starts / accepted actions cancelled before first start | 1632 / 19 |
| First-input deadline violations / missing accepted receipts | 0 / 0 |
| Freshness anchor → first input, median / p95 / p99 / max | 107.09 / 138.38 / 144.85 / 149.66 ms |
| Steady policy wall time, median / p95 / p99 | 59.18 / 80.60 / 147.06 ms |
| Received observation headers / encoded frames | 3260 / 3260 |
| Dropped observation headers / video frames / receipt events | 0 / 0 / 0 |
| Proposed no-ops / applied no-ops / movement-key steps | 783 / 726 / 735 |
| Normal / climb / unknown motion frames | 2613 / 634 / 13 |

All 1632 started actions have their observation headers, receipts and valid
first-input deadline checks. Both source-clock checks pass. The new sidecar
also preserves the original r12 analysis results apart from provenance and the
metadata-source label. Video-drop retention is covered by deterministic tests;
this live run itself had no drops.

Navigation quality remains limited: the final preview places the character
beside a wall/stairs, and 44.69% of proposals were no-ops. The longest policy
no-op span was 8.55 seconds, including 107 accepted decisions out of 114, but the
strict recovery eligibility sequence did not trigger. This is being diagnosed
separately; timely input and complete recordings are not route completion.

Evidence: `r13-build.log`, `r13-hot-replace.json`,
`r13-navigation-reset-01.json`, `r13-navigation-reset-02.json`,
`source-timing-r13-reset.json`, `navigation-r13-recorder-first-input-analysis.json`
and `navigation-r13-recorder-trial-analysis.json` under
`artifacts/research/2026-10-23/`; the immutable runtime and tools are in
`artifacts/release-r13/`.

A receipt-based latency breakdown separately covers all 735 directional-key starts: freshness-to-dispatch p50 107.1527 ms, p95 136.9248 ms, p99 143.166088 ms and maximum 149.6194 ms. The remaining starts comprise 726 no-ops, 165 camera-only actions and six other key actions. All 1,632 started receipts join to retained observation headers; 19 accepted receipts have no applied steps. These are action-step timings, not game-render age or proof of navigation success. Evidence: `artifacts/research/2026-10-23/r13-action-latency-breakdown.json`.

### Prepared r14 controls and image profile

The opt-in `p2p-native-hamming-192-v1` profile resizes native BGR/BGRA capture directly into a pooled RGB192 payload. Its production C# implementation matches the unmodified `fast_image_resize` 5.1.4 Rust reference for 81 fixtures across four layouts (324 byte comparisons) and 21 coefficient-axis checks in both Debug and Release. The existing `legacy-area-640x360-v1` profile remains the default. Client startup and every received frame verify the declared profile and dimensions; P2P skips its Pillow resize only for a verified native payload. The existing minimap progress heuristic reports `unsupportedHudAspectRatio` on square frames, so that metric cannot compare these profiles. Native world-readiness and motion recognition still use the original capture.

Navigation reset now allows a bounded three-second settling window, with at most 25 probes and 120 ms between misses, for transient post-teleport pose recognition. Identity, world, target and wrong-position failures still stop immediately. Camera adjustment uses the yaw already measured from the validated frame and rechecks cancellation/source freshness before input. This has not yet established repeated live-reset reliability.

Idle recovery preserves context across brief timing-only no-op gaps when independent, fresh, eligible observations continue and accepted no-ops remain no more than 0.5 seconds apart. Only a fresh accepted no-op can trigger recovery. World readiness/epoch, native capture generation, motion-state and control/goal changes interrupt the window. A sanitized 215-decision r13 replay triggers once during the second 8.552-second idle interval; the intervening blocked attack still separates the windows. This replay does not establish that another history reset will solve a wall-navigation stall. The 150 ms input-start deadline, release acknowledgment, fresh-source barrier and receipt-rearmed latch are unchanged.

The combined C# batch passed 143 focused tests, and the final Python agent suite passed 162 tests in the installed model environment without model/GPU work. Launcher recovery tests separately cover valid-child reuse, one-shot missing-child dispatch, ambiguous/unavailable child discovery and default minimization. The original r1 host remains running; its cold/latest-host lifecycle has not been revalidated.

`build-runtime.ps1 -PublishConfiguration Release` selects an optimized publication while retaining the required full Debug solution validation first. The manifest records both configurations. The default remains Debug. Planned live comparisons use the same Release runtime, goal and process-local Torch seed, with verified teleport position/yaw before each run; rendering, scheduling and camera pitch remain uncontrolled.

## r14 Release live verification — 2026-10-24 UTC

The required full Debug solution build and self-contained Release publication
passed with SDK 10.0.402 from clean source
`9a1f7204d88339649ff36d0df1550378553718f2`. The published DLL SHA256 is
`df864cb455acae22c8918d1120091181163c788c79bcb47f0bf545edc3205760`;
507 committed tool files were preserved in its immutable source snapshot.
Replacement changed only the RDP child, from PID 12828 to 12284. Host 28072 and
game 27728 remained running, with RDP session 3 minimized.

Three initial reset repetitions passed in 20.66, 8.56 and 8.55 seconds. All nine
final observations measured `(-867.68359375, 2281.37890625)`, yaw 2 degrees and
layer `City_102`, with distinct increasing native sources. A 30-second native
input-disabled stream retained all 794 observations and video frames, passed
both clock checks, and measured server resize p50/p95 of 0.669/0.995 ms.

The first attempted legacy gameplay trial stopped before policy startup: its
reset failed during orientation with `world_not_ready`. The failed-frame pixels
and precise world classification were not retained. A subsequent 10-second
input-disabled run retained 277 world-ready observations. The legacy retry and
the later native trial each completed their own position/yaw reset before input.
Thus r14 improves repeated pose acquisition but does not eliminate reset failures.

Both 120-second trials used the same Release runtime, checkpoint, ground-street
instruction, Torch seed `20261024`, 20 Hz decision target, 30 Hz capture target,
100 ms action hold and 150 ms first-input deadline. The process-local CPU/CUDA
seed was recorded at startup and exit. This does not make game rendering,
scheduling, camera pitch or full game state deterministic.

| Measurement | Legacy area/Pillow path | Native Hamming192 path |
|---|---:|---:|
| Proposals / accepted | 1879 / 1808 | 1917 / 1851 |
| First input starts / accepted without a start | 1800 / 8 | 1840 / 11 |
| Missing accepted receipts / deadline violations | 0 / 0 | 0 / 0 |
| Directional-key starts | 1513 | 1133 |
| Directional freshness → dispatch, p50 / p95 | 100.58 / 128.93 ms | 94.57 / 126.38 ms |
| All first starts, p50 / p95 / maximum | 101.38 / 132.24 / 149.53 ms | 94.99 / 125.72 / 147.87 ms |
| Server observation resize, p50 / p95 | 2.030 / 3.860 ms | 0.821 / 1.097 ms |
| Client preprocessing, p50 / p95 | 4.154 / 10.073 ms | 1.918 / 9.232 ms |
| Steady policy wall time, p50 / p95 | 55.84 / 73.94 ms | 55.68 / 71.62 ms |
| Retained observation headers / encoded frames | 3296 / 3296 | 3325 / 3325 |
| Dropped observations / frames / receipt events | 0 / 0 / 0 | 0 / 0 / 0 |
| Proposed no-ops | 238 (12.67%) | 426 (22.22%) |
| Native normal / climb / unknown frames | 2347 / 948 / 1 | 1952 / 1369 / 4 |

Every started action joins to a retained observation header and passes the
server deadline check; both source/freshness clock checks pass in both runs.
The native run's 11 accepted actions without a start comprise nine deadline
expirations, one scheduler-late cancellation and one stop cancellation.
Directional keys here exclude opposing W/S or A/D pairs; they measure dispatched
intent, not displacement. Latencies describe the server's first action-step
dispatch relative to its conservative freshness anchor, not game-render age or
physical input acknowledgment.

Both final previews show climbing or obstruction. Neither trial establishes
successful street navigation, and the native profile is not a demonstrated
quality winner. Its original-resolution motion recognizer remains available;
the old client minimap heuristic explicitly reports `unsupportedHudAspectRatio`
for its square payload. Recovery preserved brief timing-only gaps in both runs,
but the maximum eligible idle windows were only 5.65 and 5.72 seconds, below the
eight-second threshold. Neither run exercised an actual idle-reset trigger.

Whole-run GPU telemetry, including startup, had median utilization 90%/92%,
median SM clock 1635/1605 MHz and median temperature 88°C in legacy/native order.
This is shared GPU context, without per-process attribution. Different scenes,
camera pitch, load and a single trial per profile limit causal performance and
quality conclusions. Native preprocessing is faithful to the upstream resize
reference and reduced image preparation cost in this pair; inference still
dominates policy wall time.

The installed protected launcher helpers and task definition match current
source. Both existing shortcut targets were then invoked in warm mode: Host
reported `primary_control_endpoint`, Game reported `game_runtime`, and both
preserved the same root/child identities and minimized RDP window. Cold startup
and saved-sign-in were not exercised. A cold package selection resolves r14,
but the currently running r1 host still launches its own older package if its
child disappears; warm shortcut validation does not upgrade that host.

Evidence under `artifacts/research/2026-10-23/`: `r14-build.log`,
`r14-hot-replace.json`, `r14-navigation-reset-01.json` through `-03.json`,
`native-observe-r14-01-source-analysis.json`,
`navigation-r14-legacy-01-reset.json`, the reset/source/trial analyses for
`navigation-r14-legacy-02` and `navigation-r14-native-01`,
`r14-profile-comparison.json`, `r14-profile-gpu-context.json`,
`approved-launcher-audit-r14.json` and `r14-warm-launchers-live.json`.

## r15 recording continuity and reset evidence — 2026-10-24 UTC

Full Debug solution validation and self-contained Release publication passed
from clean source `e5f423af99dbbe6f4d8427b7f26652fc105bc7d8`. The r15 DLL SHA256 is
`fca044340d9366bc58411aee9bdf4f003793ba02232c4613c1fa954fa6a9b5f9`, with 512
committed tool files in the immutable snapshot. The final Python suite passed
202 tests without initializing CUDA; the bounded initial HUD-settling change
also passed 48 focused navigation-reset tests. Upstream main
`14537eae67c1070776a6be2fa9cf87be53d8386e` was already an ancestor of this build.
Child-only replacement changed PID 12284 to 52240 while retaining host 28072,
game 27728 and minimized RDP session 3.

Recording rotation now occurs inside a healthy bridge lease. Active and
retiring writers share bounded recording budgets, preserve pending-action and
source-header context, and publish explicit incomplete-evidence failures.
Actual disconnection still releases control and starts a new lease. The live
45-second observation-only check rotated through five files under one session,
retaining all 1,193 source headers and encoded frames with no dropped frames,
events or observations. Every writer retired cleanly. Boundary acquisition gaps
were 39.73, 35.48, 80.79 and 15.32 ms; no capture epoch changed. Source joins and
clock checks passed. With no model or input enabled, this check does not yet
validate model history, action receipts or input cadence across rotation.

The first r15 reset failed after 26.15 seconds with `pose_not_settled` during
final verification. It released task ownership and sent no subsequent policy
input. Its intermediate verification poses were not retained, so the exact
failed yaw, spatial-spread or sample-spacing condition cannot be recovered.
The three planned reset repetitions stopped after that failure. Later
input-disabled previews show the character at the city spawn, which does not
establish the required settled position/yaw contract. The next diagnostic
change must retain those samples without weakening reset acceptance.

The committed CPU-only replay preparer validates source/video/action/goal joins
and creates explicit unlabelled probes. In selected late-idle windows, probe
2392 has identical accepted-proposal and execution-receipt action histories;
probes 711 and 3079 differ in 7 and 15 of their 40 history labels. These are
system input-intent labels from unsuccessful gameplay, not expert training data.
An ignored offline sensitivity prototype passed nine CPU tests and validated
243 supplied/boundary labels against the upstream action codec. Its first GPU
run passed exact probe-placeholder invariance but failed batched-full versus
original-incremental context parity: maximum absolute difference 0.046875,
17,059 of 41,984 values outside the existing `rtol=atol=1e-3` bound. It retained
the arrays and published no history-effect comparisons. This is an invalidated
offline reference comparison, not evidence of better or worse gameplay.

Evidence: `r15-build.log`, `r15-hot-replace.json`,
`r15-final-python-tests.log`, `r15-navigation-reset-01.json`,
`native-observe-r15-continuity-01-analysis.json`,
`p2p-replay-sensitivity-cpu-preflight-03/report.json` and
`p2p-replay-sensitivity-run-001/report.json` under the local research directory.

The subsequent diagnostic-only reset patch retains each returned verification
pose, its rolling-window size and the exact shared gate reason, up to the
existing 15-attempt bound. Successful output remains three verified poses;
acceptance thresholds, delays and input behavior are unchanged. A separate
run/instance-pinned read returns complete terminal evidence within 32 KiB while
ordinary responses and incoming requests retain their 8 KiB limits. The Python
client preserves full failed results in `NavigationResetError.status` and CLI
error JSON. Focused reset/status C# validation passed 66 tests; all 107 RDP
Python tests passed. This source validation does not yet establish a live cause
or a successful reset retry.

## r16 reset diagnostics and published P2P timing — 2026-10-24 UTC

The full Debug solution and self-contained Release build passed from clean
source `0416abdc41417594c4de8b70cd39521e46e67f84`. The r16 DLL SHA256 is
`528fc4de11137878a9ac2c67292aa976380573e6a0d59cb3dcedc0b357dc9d60`, with 512
committed tool files in the immutable snapshot. Child-only replacement changed
PID 52240 to 20092 while retaining host 28072, game 27728 and minimized RDP
session 3. Those commits were pushed to the fork's `main` branch.

The first reset passed in 22.14 seconds, with three distinct source frames at
position (-867.68359375, 2281.37890625), yaw 2 degrees and zero measured spatial
or yaw spread. The second reset failed in 10.56 seconds. All 15 retained poses
had the same position and yaw 3.0000038146972656 degrees; every rejection was
`target_yaw_out_of_tolerance`. This identifies that run's exact failed gate.
Both orientation and final verification used the same 3-degree threshold; the
orientation sample was not retained, so near-boundary settling remains a
plausible cause rather than a measured transition. The final threshold must
remain strict. A separate reset before the continuity trial passed at yaw
2 degrees. Evidence: `r16-build.log`, `r16-hot-replace.json`,
`r16-navigation-reset-01.json`, `r16-navigation-reset-02.json` and
`navigation-r16-continuity-01-reset.json` in the local research directory.

An audit of the published recorder and training loader established a separate
action-association issue. [Recap's input snapshot](https://github.com/elefant-ai/recap/blob/70ee48d5f4cd0f6bb19810a55b7ec1c3f36e226f/src/input_manager/mod.rs#L253-L315)
contains held keys/buttons at the callback and mouse deltas accumulated since
the preceding snapshot. [P2P's loader](https://github.com/elefant-ai/open-p2p/blob/a329d98cbe62119679a254d71bea6446773541bc/elefant/data/video_proto_dataset.py#L217-L240)
pairs image j with annotation j+1, making that action interval follow the paired
image in callback order. The existing `receipt_same_frames` comparison instead
uses state at the current immutable acquisition and mouse events in the
preceding acquisition interval. Its original cases remain unchanged; it is an
explicit comparison convention, not established training alignment.

The published source establishes an index direction, not exact physical input
or pixel timing. Callback-to-acquisition calibration, asynchronous event-queue
outliers and the recorder versions used by historical training data remain
unverified. A new following-acquisition comparison needs its own method/version
and real next-frame boundary; its final history interval may use the probe's
acquisition clock without consuming probe pixels or a later predicted action.
The full pinned audit is retained locally as
`p2p-image-action-time-association-audit.md`. The official labelled BC
[loss mask](https://github.com/elefant-ai/open-p2p/blob/a329d98cbe62119679a254d71bea6446773541bc/elefant/policy_model/stage3_finetune.py#L1051-L1054)
currently selects user-action frames. Native-controller demonstrations require
an explicit provenance/masking policy; they must never be marked human input.

The separate CPU-only `prepare_replay_forward.py` now retains the original
accepted-proposal and preceding-acquisition arms verbatim and adds
`receipt_next_acquisition_v1` on the identical images. All 34 preparer tests
passed; independent review found no blocker. Probe 2392 remains an exact
three-arm control with 40 no-op labels. Probe 711 has seven differing mouse-only
labels between each pair of arms. Probe 3079 differs in 15 labels between
accepted and preceding histories, and 14 between accepted and following
histories. These differences establish neither policy sensitivity nor gameplay
quality. Plans and the comparison are retained as
`r14-native-probe-{2392,711,3079}-forward-v1.json` and
`r14-native-forward-v1-comparison.json`.

The orientation follow-up aims within one degree before final verification,
leaving margin inside the unchanged three-degree acceptance band. Both camera
correction and loop completion use the same predicate; the 50-attempt bound,
75-second cooperative deadline and all source/position checks remain unchanged.
The exact r16 failure angle remains rejected. Focused reset/status validation
passed 83 tests, including small-input rounding and the retained boundary case;
live validation of this follow-up is recorded in the r17 section below.

The r16 two-minute gameplay trial completed under one bridge lease and one model
load, rotating through six recording files. It retained all 3,328 distinct source
observations and encoded frames, 1,896 proposals and 1,807 accepted actions with
exact terminal receipt joins. There were 1,793 first input dispatches and 14
accepted actions cancelled before a first dispatch; two other proposals were
rejected for their deadline. All first dispatches met the 150 ms freshness
deadline: median 99.89 ms, p95 129.09 ms, p99 143.34 ms and maximum 148.44 ms.
There were no image, observation or event drops. All ten proposals/receipts
crossing file boundaries joined their originals exactly, all five boundaries
continued `episodeStep` by one, and graph preparation occurred only at the
initial prediction. Other receipt-driven history resets still occurred inside
segments; recording rotation itself did not require one.

The first offline continuity analysis failed because it required an event field
that the historical journal never serialized: all 1,896 report decisions had
`historyCommitted`, while all matching journal events omitted it. Every other
shared action/timing field matched; this was not conflicting commit evidence.
The original failed analysis is preserved. Explicit historical validation checks
the report flag against declared acceptance feedback and labels coverage
`report-only-legacy`, while keeping all other joins and deadlines exact. It does
not permit this exception for versioned journals. The subsequent six-line client
change adds a versioned capability and serializes the field after feedback;
GameScaling/no-feedback proposals carry null. The full agent Python suite passed
214 tests without initializing CUDA. The richer journal subsequently passed
strict live validation in r17, without the historical omission exception.

The behavioral pause remains material: idle recovery triggered after 8.060
seconds and 122 accepted no-ops, but another 140 accepted no-ops followed. The
first later directional dispatch occurred 10.587 seconds after release. This
establishes neither immediate recovery nor physical movement at that instant.
The final saved preview shows the character on an open street; intermediate
previews include an obstruction, and no fixed navigation endpoint was scored.
Evidence: `navigation-r16-continuity-01-analysis.json` (original failure),
`navigation-r16-continuity-01-analysis-v2.json` (explicit historical coverage),
the six segment reports/recordings, and `r17-agent-python-tests.log`.

Independent review subsequently tightened the ignored analyzer to cross-check
declared policy feedback against the journal mode, including unversioned journals
whose fields are present. Eleven analyzer contract tests passed. A new
`navigation-r16-continuity-01-analysis-v3.json` retains the same measured results
and report-only history limitation; both earlier analyses remain unchanged.

## r17 orientation margin verified live — 2026-10-24 UTC

The full Debug solution and self-contained Release publication passed from clean
source `2d62d8fd3a408c411b07f2b73a9ac60fdecee790`. The r17 DLL SHA256 is
`fe5ae5f3e43e5b7ec4b008d11490aa46a377a7e61a86016ef192f1cbe9bda2e2`, with 515
tracked tool files in the immutable snapshot. Child-only replacement changed
PID 20092 to 2616, retaining host 28072, game 27728 and minimized RDP session 3.

Three separately evidenced resets passed in 26.69, 12.07 and 14.13 seconds.
All nine final samples were at (-867.68359375, 2281.37890625), yaw exactly zero,
on layer `City_102`. Each run accepted its first three verification observations
with zero measured position/yaw spread and distinct fresh native sources. The
initial one-degree orientation goal leaves margin without widening the final
three-degree gate. These results support the bounded fix; they do not establish
unlimited reset reliability, camera pitch equality or complete game-state reset.
The offline GPU sensitivity experiment was also running during these resets,
so their durations are not isolated performance measurements.

Evidence: `r17-build.log`, `r17-hot-replace.json`,
`r17-navigation-reset-01.json` through `-03.json`,
`r17-reset-margin-tests.log` (83 focused C# tests) and
`r17-agent-python-tests.log` (214 Python tests, CUDA not initialized).

## r17 continuous gameplay and strict journal validation - 2026-10-24 UTC

`navigation-r17-continuity-01` completed 120 seconds of gameplay with the same
native Hamming profile, goal, seed, 100 ms action hold and 150 ms first-dispatch
limit. Its separate pre-run reset also passed with three yaw-zero samples. One
model load (7.937 seconds), one bridge lease and one initial graph preparation
served all six 20-second recording segments. The outer RDP job completed in
133.391 seconds, including startup. The original host stayed minimized; the
child and game runtime remained available after the policy and stream stopped.

Strict analysis passed without `--allow-legacy-history-omission`. All 1,818
proposal events contain version 2 and an explicit `historyCommitted` matching
the report and declared acceptance-feedback mode. All 1,737 accepted proposals
have unambiguous terminal receipts; 1,726 reached a recorded first dispatch and
11 were cancelled before starting. Another two proposals were rejected for an
expired deadline; 79 were not submitted. Every recorded first dispatch met the
150 ms limit: median 97.12 ms, p95 131.76 ms, p99 141.24 ms, maximum 148.02 ms.
These remain freshness-anchor-to-server-dispatch measurements, not game-render
or physical input-acceptance latency.

All 3,250 distinct source observations and encoded frames were retained, with
no image, header or event drops and all recording workers retired. Thirteen
carried context headers were excluded from received-frame counts. All eight
proposal/receipt pairs crossing file boundaries matched their originals. The
five boundary acquisition gaps were 15.90, 57.56, 33.90, 29.42 and 30.41 ms.
One boundary repeats `episodeStep` after an uncommitted proposal; the other four
advance it by one. Eleven receipt-driven history resets occurred during the
lease; file rotation did not reload the model or prepare another graph.

Behavior remains inadequate for reliable continuous navigation. Of 1,818
proposals, 1,005 (55.28%) were no-ops. Recorded first dispatches comprised 557
with directional keys, 197 with camera movement but no directional key, four
with other keys, and 968 no-ops. The longest eligible idle window was 7.651
seconds, below the configured eight-second recovery threshold, so no idle
recovery fired. The final saved preview is obstructed by a stall/counter, and
no destination or physical-displacement success was scored. Timing and complete
recording therefore do not establish successful gameplay.

Evidence: `navigation-r17-continuity-01-analysis.json`,
`navigation-r17-continuity-01-behavior-counts.json`,
`navigation-r17-continuity-01-reset.json`,
`navigation-r17-continuity-01-postflight.json`, the resident benchmark report and
its six segment reports/recordings. The analyzed lease is
`ec11d3236eee4185998cbea5c85d20cd`.

## Three-way sequential P2P replay result - 2026-10-24 UTC

The isolated `sequential-online-forward-acquisition-three-arm-v1` experiment
completed on the GPU. Each arm uses identical saved images/goals, 40 supplied
history labels, the original incremental `online_forward` path and a probe at
context length 41. It compares accepted-proposal history (A), preceding-
acquisition receipt history (P), and following-acquisition receipt history (F).
It never changes the live controller or enables a new sampler mask.

All 2,412 exact gates passed before comparisons were published. An independent
CPU audit verified 62 referenced hashes, all nine parity archives, nine input
archives, 288 repeated probe samples and all nine paired summaries. The checks
cover repeated fresh-cache contexts/teacher heads, probe-placeholder invariance,
paired sampled outputs/conditional logits and the identical-history control.
The previous full-batched-context parity failure remains unresolved and is not
superseded by these sequential-repeatability results.

| Probe | No-ops per arm, out of 32 seeds | A/P decoded differences | A/F | P/F |
|---|---:|---:|---:|---:|
| 2392, identical-history control | 32 | 0 | 0 | 0 |
| 711 | 30 | 2 | 0 | 2 |
| 3079 | 29 | 0 | 1 | 1 |

The rare differences are `e` versus `f`, or vertical mouse deltas of -1 versus
-2. No paired seed switched between no-op and action. Zero such switches in
32 seeds still permits a nominal 95% Wilson upper bound of 10.72%; it does not
establish equality of the underlying distributions. These are three selected
states with supplied short histories and the raw upstream sampler. Live key
admission can reject a whole proposal, and no game execution or quality was
evaluated here. The result shows limited history sensitivity without evidence
that this timing change fixes idling.

The live history behavior remains unchanged. The next bounded measurement is a
native fixed-leg controller with independently checked endpoint poses. Any
future native-controller data must retain system provenance and its actual
execution/evidence limits; this replay study creates no training-eligible or
human demonstrations.

Evidence: `p2p-replay-forward-sequential-run-001/report.json`, its unchanged NPZ
archives, `p2p-replay-forward-sequential-run-001-analysis.json`, and
`P2P-REPLAY-FORWARD-SEQUENTIAL-RUN-001-ANALYSIS.md`. The executed runner SHA256 is
`cb976b9ce9e0790e958f919ef01d0fdaf9f0e81ae34607a150ad75ddf8edad29`.

The reproducible source is now tracked in
[the replay experiment package](../../tools/bettergi-agent/experiments/README.md).
Its 35 CPU tests passed without skips. A source-only copied checkout, with no
ignored research scripts, reproduced all nine historical RGB/token/goal inputs
exactly during CPU preflight. The packaged entrypoint has separate provenance;
its path/decoder/goal-relocation changes do not relabel the already executed GPU
run. All retained numerical definitions and exact publication gates remain
unchanged. No GPU installer or additional model run was added.

## Native fixed-leg baseline implementation - 2026-10-24 UTC

A separate `startNavigationBaseline` command now controls the first shipped
Mondstadt street leg, with no caller-supplied route or input sequence. The reset
remains a separate, verified operation. This baseline uses native minimap/yaw
feedback, W and horizontal camera motion, a 100 ms renewable input lease, and a
30-second whole-operation deadline. Both source clocks must advance past input
response barriers; expired input cannot be renewed by a late observation.

Arrival requires three fresh, stable endpoint observations after permanent input
closure. The authenticated result query is pinned to the exact run and retains
owner/cleanup failures. Initial/final images and a bounded intent-and-pose journal
are published only after release. They are explicitly system-generated evidence,
not human demonstrations, complete low-level dispatch traces or training data.

The new `run-navigation-baseline` CLI keeps the child PID/session/nonce and run
identity pinned through cleanup and result retrieval. All 162 focused C# tests
and 72 focused Python CLI/transport/reset tests passed. The implementation has
completed independent review; live route success is still to be measured in the
next isolated release.

## r18 first native route trial - 2026-10-24 UTC

The full required Debug solution build and isolated Release publish passed from
clean commit `f5ab0b57ac0cc2ae8ae9eb4650a29f04d04ef825`. The release contains a
525-file frozen tools snapshot. Child-only replacement changed PID 2616 to 23592
in RDP session 3; root PID 28072 stayed minimized and game PID 27728 remained.
The running DLL SHA-256 is
`9d4b82acac2a270318d0e6cd6462211d4291a5837bf1d2b37c10cc3f89799875`.

The separate reset passed. Native baseline run
`c94e0dc5c26e4bfcb0780b1db6aec726` failed with `forward_lease_expired` after
1,457.55 ms. Nine camera corrections reached the admitted heading tolerance;
the first W grant then expired before a post-W observation completed. Keyup
completed 8.03 ms after the 100 ms expiry, with no reported release error.
All ten completed observations and twelve input transitions were retained;
the postflight confirmed idle tasks/stream, an attached runtime and a minimized
root. This is a failed route attempt, not an arrival result.

Median accepted-frame capture cost was 4.15 ms and recognition was 26.38 ms.
The required 60 ms W-response barrier leaves only 38.65 ms after dispatch
completion before expiry. The controller also schedules its next observation
50 ms after the current pose/input rather than counting recognition in that
cadence. The failed in-flight observation was not retained, so this evidence
does not yet isolate its final barrier, capture or recognition cost. The
next correction will address scheduling and preserve failed-attempt timings;
the original failed evidence remains unchanged in
`artifacts/research/2026-10-23/native-baseline-r18-01-*.json` and the run's
`User/NavigationBaselines` directory.

## Observation cadence and atomic child reconciliation - 2026-10-24 UTC

The next controller revision anchors each 50 ms cycle to the actual workflow
entry into pose recognition. Capture and recognition therefore consume that
cycle's budget. Each new read resets the anchor, so a delayed read cannot create
a series of catch-up deadlines. Capture polling, 60/80 ms response barriers,
the 100 ms movement lease, 150 ms source-age limit and route geometry are unchanged.

Bounded file-only diagnostics now retain interrupted reads in `finally`,
including their last stage, capture/source/recognition clocks, duplicate/barrier
counts and concurrent lease fault. Pacing waits retain the requested deadline,
actual exit and failure. The journal records QPC frequency and diagnostic schema
version 1. Capacity failures remain explicitly incomplete, even beside a
concurrent watchdog fault. All 172 focused baseline/adjacent C# cases passed,
including ten new timing/evidence cases. Live improvement remains to be measured.

The approved Host and Game shortcuts now independently pin the latest verified
child package while preserving a running primary host. A matching child is
reused; an already-ready active game receives no redundant start mutation.
Host readiness explicitly identifies the selected child control endpoint,
while Game readiness separately requires the attached game runtime.

Independent review found two races in the initial workspace-only upgrade path:
new work could begin after an idle status check, and another launcher could
overwrite the shared pending-restart manifest. The application now exposes
`idleRestartVersion:1`. Its typed restart request binds the exact target
directory and executable/assembly hashes, while a task/runtime reservation
prevents new task and manual/queued runtime-start admission through committed
shutdown. A failed launch releases both reservations. A successful launch keeps
shutdown responsibility even if later status, serialization or response work
fails. Automatic upgrades require this capability before staging configuration
or a manifest; legacy builds require the existing controlled explicit replacement
path. An uncertain mutation is not automatically replayed.

The launcher passed 99 focused Python/PowerShell checks and independent review.
The focused C# restart batch passed 65 cases, including 16 new reservation,
request-binding and response-failure cases; all 36 existing external-control
protocol regressions also passed. The protocol smoke test first caught an eager
task/logger initialization dependency in service construction. Deferring that
semaphore lookup until an actual restart fixed the dependency, and the failed
test log is preserved beside both successful rerun logs. The required full
solution build remains before deployment.

## r19 deployment, shortcuts and measured native failure - 2026-10-24 UTC

The full Debug solution build and isolated Release publish passed from clean
commit `429d53bbcd397c6041df8ec567b5f955c7a2ce1d`, now pushed to the fork.
The release retains a 527-file frozen tools snapshot and DLL SHA-256
`5f80bba4b5681ec6a5710cbd31f71d5956db99c3be6e32cb381a7330e4d0dd2a`.

The first replacement attempt lost its stop acknowledgement: the r18 server
logged its five-second I/O deadline while runtime/capture cleanup occupied
the request. Fresh status established that the same child was alive and fully
stopped. A separately recorded recovery continued from that state with one
restart request; it did not replay stop. Child PID 46148 is now running r19
in session 3. Root PID 28072 remained minimized and connected; game PID 27728
remained in session 3. Both saved `.lnk` files were actually launched and
successfully reused this same child, selected the r19 hashes and preserved the
minimized window. Host and Game reported their distinct readiness scopes.
Evidence is retained in the `r19-hot-replace*` and `r19-approved-*-shortcut-01`
JSON files under `artifacts/research/2026-10-23`.

The separate reset passed. Native run `f2fcdd4e43b14eeab9500e1fae5e4a63`
failed on the first W grant with `forward_lease_expired` after 1,423.51 ms.
All nine accepted poses, eleven input transitions and ten observation attempts
were retained. The new cadence wait before the failed read was only about
0.08 ms, but that read needed 94.88 ms through its last capture and another
28.43 ms for recognition. Six capture attempts failed the feedback barrier.
These counts do not establish six distinct frames: duplicate checks compare
against the last accepted pose, so a rejected cached frame can be polled again.

The first qualifying frame was acquired 27.20 ms after the 60 ms barrier;
capture and recognition then consumed 36.22 ms. Recognition completed 25.25 ms
after lease expiry. Keyup completed 21.72 ms after expiry with no release error;
the journal records those actual times rather than claiming a hard OS deadline.
Postflight confirmed no running task/stream, an attached runtime and a minimized
host. The cadence correction alone has not produced a successful route or a
training-eligible demonstration. Original failed evidence and the hash-verified
analysis remain in `native-baseline-r19-01-*.json` and the run directory.

## r20 same-frame recognition and launcher validation - 2026-10-24 UTC

Native recognition now prepares the yaw, processed minimap and mask once per
admitted frame, then passes the owned result to the existing rank-0 local map
matcher. Existing callers keep their original API. Synthetic checks and two
saved native screenshots matched pixels, masks, yaw, confidence and position
exactly; a failed local match also preserved the previous cache. The final
alternating-order CPU replay used four warmups and twenty measured pairs per
image. Median yaw-plus-map time changed from 13.07 to 11.70 ms on the r18 image
and from 12.48 to 11.16 ms on r19. These are local replay measurements, not proof
that the live 100 ms lease is now achievable.

File diagnostic schema 2 adds per-stage recognition clocks and flat capture
poll records. It distinguishes equality with the previous poll from duplication
of the last accepted pose, and records both response-barrier margins. Limits
remain 1,024 observation attempts and 1,024 workflow observations, with a new
4,096-poll bound and explicit failure on exhaustion. The maximum-count fixture
serialized to 4,420,417 bytes, exceeding the first proposed 4 MiB ceiling, so only
the post-release journal file ceiling increased to 6 MiB. This fixture does not
prove a bound for every possible field representation. Pipe response limits,
100 ms W lease, 150 ms source age, 60/80 ms barriers and 30-second workflow
deadline are unchanged.

Lifecycle admission now always queues UI-affine work before executing its
synchronous prefix. The request can acknowledge admission while native cleanup
runs, and the lifecycle still owns the entire cleanup task. Request timeout does
not abandon or replay cleanup. Atomic restart version 2 additionally binds
Host/Game startup intent in the authenticated request fingerprint. Host
replacement requires v2 and starts only the control endpoint; Game retains v1
compatibility and verifies an attached game runtime. Direct explicit hot-replace
keeps its existing default. Cold or missing-child startup through an older
primary remains a separate compatibility limitation.

Validation passed 179 focused native checks, one saved-image replay, 58 launcher
and lifecycle C# checks, 36 existing protocol regressions, and the full 170-case
RDP Python suite. Original compile/capacity failures and successful reruns are
preserved under `artifacts/research/2026-10-23`. Full solution build, publication
and a pinned live shortcut upgrade remain the next validation steps. Independent
reviews of both the launcher/lifecycle and minimap/diagnostic changes found no
actionable issues.

## r20 deployment and capture-delay evidence - 2026-10-24 UTC

The required Debug solution build and Release publish passed from clean commit
`785e0458f0ce2bd1718e25264c64cebb706cb4ed`. The release has a verified 527-file
tools snapshot and DLL SHA-256
`cb0fccf3b44f7f8b8bcd72e842067a547b75d3bc424ac3cf7208360a3c3aa1d4`.
Launching the actual saved Game shortcut replaced the child with r20 PID 32540,
but the wrapper reported an empty control error. No restart was repeated.
Separate read-only discovery confirmed the exact new package/nonce, attached
runtime, unchanged minimized root and unchanged game process, including its
creation time. Both the original failed proof and successful reconciliation
remain in `r20-approved-game-upgrade-01.json` and
`r20-hot-replace-recovery-01.json`.

The wrapper captured stdout while the Python client wrote its structured error
to stderr; the deployment helper then replaced that failure with an empty bare
assertion. A separate startup-readiness branch can reject a newly launched
child's temporary UI/pipe unavailability before its bounded deadline. That is a
confirmed source weakness, but the lost stderr prevents attributing this
particular upgrade result to it. The replacement itself was verified, and the
pending launcher patch must preserve uncertainty without replaying mutation.

The first separate reset failed at the entry source check of its first final
verification read, with no sample returned. The stable error code does not
distinguish stale/malformed source metadata from an epoch mismatch. A subsequent
eight-second observation-only stream received 213 distinct usable frames, all
world-ready and normal-motion, with no drops or input authorization. Source age
was 33.21 ms median, 54.04 ms at the nearest-rank 95th percentile, and 79.64 ms
maximum. This proves later recovery, not the failed
reset frame's cause. Recording and worker cleanup completed.

A newly named second reset passed. Native run
`52ee5d43c2904396b37e9d988f9a56eb` then failed after one accepted pose and one
camera transition, before W was pressed. Its second capture call took 644.79 ms
and returned a source 613.92 ms old at failure. The first-acquisition timestamp
was about 625.43 ms after capture was requested and 19.37 ms before it returned;
the compositor timestamp was already about 594.07 ms old at acquisition.
These clocks locate most of the delay before acquisition, but cannot yet
separate lock contention, native pool wait and thread scheduling. The first
accepted observation used 4.08 ms capture and 31.18 ms recognition. Recognition
phases were 8.86 ms world, 1.03 ms motion, 3.70 ms color/crop, 3.67 ms yaw/mask,
and 12.50 ms local position/geometry.

The complete schema-2 intent/pose journal is retained with SHA-256
`6c8426b62c34900c2ecc80fc7765cce4b960b7e6a3c5ec8ed043d5b0940d2203`.
Postflight showed the runtime attached, no running task/stream and the same
minimized root. This run did not test the first W lease, reach the endpoint, or
produce a training-eligible demonstration. Its measurements are preserved in
`native-baseline-r20-02-diagnostic-analysis.json`; source capture timing needs
finer instrumentation before assigning the stall to CPU, GPU or a lock.

## r21 capture and startup source validation - 2026-10-24 UTC

An optional per-call capture API records raw QPC boundaries for the capture
gate, state lock, Windows frame pool, render/disposal, submit, staging Map and
CPU copy. It retains acquired and returned source identities separately, so a
cached source acquired by another caller cannot be mistaken for this call's
acquisition stage. Ordinary capture callers retain the original path without
diagnostic allocation or clock reads. These are wall intervals, not GPU busy
times. The native baseline retains up to 63 slow/failed traces plus one terminal
trace, with explicit support, omission and incomplete-trace fields. Reset source
failures also emit one bounded diagnostic preserving the original error code.
The timer still captures while task triggers are disabled, making capture-gate
contention a source-level candidate; this change measures it without changing
producer behavior or claiming that contention caused the r20 stall.

The native baseline now accepts explicit timing contract v2. Its first W-down
attempt grants at most 150 ms, later grants 100 ms, and every grant is capped at
250 ms from the older raw-source/first-acquisition clock. Dispatch consumes the
grant; release and realignment never rearm the first-attempt allowance. This is
logical input authority, not a hard physical keyup guarantee. V1 remains the
default and retains its original behavior. Source freshness, response barriers,
geometry and cleanup requirements are unchanged. Contract identity is bound in
the request, status, result and journal.

The launcher now preserves stderr, exit and timeout evidence, and reconciles
post-acknowledgement startup transients within the existing deadline. An
uncertain restart is never replayed. New primaries bind Host/Game startup intent
to an immutable operation across direct launch and RDP login callbacks. Game
may join endpoint startup and then explicitly attach the runtime. Host rejects
incompatible or unsupported startup before mutation. The current old primary
can continue verified child reuse/replacement; cold endpoint-only startup on it
remains unsupported. Live Windows-login behavior of the new primary is unproven.

All 262 unique focused C# checks and the full 199-case RDP Python suite passed.
The initial system-SDK mismatch and sandbox-only pipe integrity-label failure
are retained with their successful corrected runs. The maximum-count journal
fixture, including 64 full capture traces, is 4,856,229 bytes under the unchanged
6 MiB file limit. Independent reviews found no actionable issues. Full Debug
solution build, Release publication and pinned child-only live validation are
the next steps; no successful route or v2 latency result is claimed yet.

## r21 live replacement and first verified native leg - 2026-10-24 UTC

The required Debug solution build and Release publish passed from clean commit
`1fb7baa55d971aaec0d5ba7649487377d464b074`. The 529-file tools snapshot and DLL
`cc9979a0d9ec48c6ae6e7cfc066d4fe5d1256b492c7153505b24315611e9f642`
were verified. The actual saved Game shortcut replaced child 32540 with 53828
and reported success. The same primary stayed minimized, RDP remained in
session 3, and Genshin PID 27728 retained its original creation time. The new
primary's cold/login path was not exercised.

The first reset failed while orienting. Its new diagnostic identified a source
661.83 ms old, within the same capture epoch. The capture call took 622.53 ms:
606.60 ms before acquiring the capture gate, 0.0013 ms acquiring the state lock,
0.0561 ms in frame retrieval, 0.6568 ms rendering/disposal, 0.0557 ms submit,
13.48 ms readback Map and 1.66 ms CPU copy/cleanup. This places the dominant
wall delay before capture admission; it does not distinguish contention from
descheduling or GC, or identify the lock holder. Exact evidence is retained in
`native-baseline-r21-01-reset-source-analysis.json`.

The next separately reset v2 trial, `90e069533d184be186aecbceab74f0f7`, advanced
5.68 map units through 32 accepted observations before its second physical W
start expired. The first 150 ms grant and subsequent renewals worked. After a
direction correction, the second start correctly retained the 100 ms v2 rule.
Its final recognition finished 0.15 ms after expiry; keyup completed 1.55 ms
after expiry without a release error. All capture calls stayed below the 50 ms
detail threshold, so the journal contains no detailed capture-stage records.
The complete read followed by input-gate failure motivates retaining the final
capture trace separately in the existing reserved slot.

A further separately reset v2 trial, `e18b9b304069481a9d1f43eba864434c`, completed
the fixed 9.81-unit leg in 4,525.65 ms with 49 accepted observations. Three fresh
post-release samples agreed at 0.88 units from the endpoint and yaw 48.5 degrees.
Observed displacement was 8.98 units; the two physical forward holds lasted
1,500.22 and 432.81 ms between recorded dispatch completions, supported by 31
accepted grants. Capture median/max were 5.70/15.98 ms and recognition median/max
24.17/39.46 ms. All recorded grants passed the v2 source-cap audit. Journal
SHA-256 is `83d1d90b1ca2a20aa97cb5347001e91e1a396f53611e18f8e97154e8aefe7359`.
Postflight was idle/attached with the same minimized root. This establishes one
successful short native leg, not general navigation reliability, a model-quality
winner or a training-eligible demonstration. All failed attempts remain retained.


## r22 timer capture isolation and stall attribution - 2026-10-24 UTC

The fixed native baseline now offers an explicit `capturePolicy` independent of
input timing. Omitted requests retain `shared`; `task_owned_timer` is an opt-in
experiment. After the task semaphore is held, TaskRunner drains the current
runtime's timer tick, finishes trigger disable callbacks, and retains the
capture pause through input cleanup. Timer window/liveness checks remain active.
A failed disable remains admission-blocking even if an ordinary tick observed
it first. Successful later disable can clear a current slot's failure; retired
failure evidence is bounded text and requires dispatcher/process recreation.
The drain wait is bounded and cancellation-aware, but synchronous callbacks are
not forcibly preempted. Other hotkey/background callers are not excluded.

While timer image checks are paused, the native task checks chat on the same
admitted frame before world recognition; open or unknown chat ends the task.
The experimental raw-frame chat path rejects dimensions above 1920x1080.
Configured task cancellation stays available through drain, execution and
cleanup. Journal chat timing is separate from world recognition timing, so its
cost can be measured rather than hidden in the capture comparison.

Optional capture diagnostics now record a nonblocking monitor probe and before/
after process-wide GC counters, with QPC bounds around their sequential reads.
These distinguish immediate contention evidence from aggregate GC activity;
they do not attribute pauses to a particular thread, stage, or lock holder.
Ordinary capture does not collect these diagnostics. The final available capture
trace is promoted after input closure, including a fast successful read followed
by an input-gate failure. The 64-trace cap and 6 MiB journal bound remain.

The first focused C# run caught six wire cases from a missing lowercase JSON
property annotation; the correction and serialization assertions passed the
same 278-case rerun. Together with 36 existing control checks, all 314 unique
C# checks passed. The control pipe integrity-label check passed under the normal
Windows token after its known sandbox-only failure. All 205 RDP Python tests
passed under the normal Windows token. The sandbox-only launcher/file-permission failures and first C# failure
artifacts remain retained. The latest full-count journal fixture is 4,948,595 bytes, including 64 complete
probe/GC traces. Independent reviews are clear; all 21 changed/new C# files are
UTF-8 without BOM. Required full Debug build, Release publication and the
same-contract live comparison follow.

## r22 live capture isolation evidence - 2026-10-24 UTC

Full Debug build and Release publication passed from clean commit
`015695653cb536679a2a0ba0e933c2756b410d75`. The 529-file tools snapshot and DLL
`b2fc870577efcced37b6a9c52aff5999045682be4440848f23037f876cd69120`
were pinned before the saved Game shortcut replaced child 53828 with 43052.
The primary remained minimized, session 3 stayed connected, and Genshin PID
27728 retained its creation time. The commit was pushed to the fork.

Three shared-capture resets failed before baseline input, while orienting or
verifying. All three immediate monitor probes reported contention. Source ages
were 574.41, 747.85 and 685.54 ms; capture-gate wall waits were 496.23, 651.27
and 638.54 ms. Their own readback Map intervals were 15.18, 13.30 and 1.23 ms.
Process-wide GC pause deltas were 0, 23.07 and 0 ms. These measurements establish
contention during the sampled calls; they do not identify the holder, and the
GC deltas cannot explain the dominant waits. The current two-buffer WGC pool
returns one next frame per call, so pending pixels can remain old after a long
competing capture. No pool-selection or GC behavior was changed for this run.

One explicitly labeled diagnostic baseline reused reset02's already teleported
state after its orientation source-age failure. It was not a fully reset
comparison pair. Baseline start/source/world/geometry gates independently passed
before movement. Run `09a11dc82295411891d98f2442819392`, v2 with
`task_owned_timer`, advanced 6.50 units through 36 accepted observations in
3,388.88 ms, then failed its second physical W start's 100 ms deadline. Accepted
captures had median/max 6.54/13.50 ms; recognition had median/max 26.98/37.30 ms.
All 37 chat checks were Closed, with median/max 4.32/5.45 ms. The endpoint was
still 3.35 units away at the last accepted pose.

The terminal observation needed seven polls and six response-barrier waits.
Its source acquisition occurred 91.10 ms after the second keydown completed;
capture then returned at 102.64 ms and recognition finished at 130.46 ms. The
watchdog keyup completed 17.39 ms after logical expiry, with no release error.
The reserved final diagnostic slot retained this fast capture: 11.56 ms total,
9.36 ms Map, immediate contention false, and no recorded GC activity. This
supports testing a separate v3 contract that allows each physical start up to
150 ms while retaining 100 ms renewals and the older-source-plus-250 ms cap.
It does not establish capture-policy reliability or a model-quality winner.

Exact reset-source records, owner identities and log-line hashes are retained
in `native-baseline-r22-01-reset-source-analysis.json`,
`native-baseline-r22-02-reset-source-analysis.json` and
`native-baseline-r22-04-reset-source-analysis.json`. Baseline journal SHA-256 is
`b6e784379597f9c78545a74456fade776da9af132b30ccbbe499bc3ba020b097`.
All terminal runs released input and left the child idle and attached under the
same minimized primary. Reset isolation after teleport and the explicit v3
timing variant are the next implementation steps; this evidence is not human
demonstration data and remains ineligible for training.

## r23 repeated walking starts and reset capture isolation - 2026-10-24 UTC

The explicit v3 native timing contract grants each new physical W-down attempt
up to 150 ms. Held-input renewals stay at 100 ms and never send another keydown.
Every v3 grant still expires no later than the older immutable source clock plus
250 ms, and dispatch time consumes the allowance. The run-first attempt marker
remains true only once. V1/default and v2 behavior are unchanged; capabilities,
request validation, owner status, result and journal retain the chosen contract.

The reset now separately offers `capturePolicy=task_owned_timer`, with `shared`
remaining the default. Teleport and its existing timer chat detection remain
shared. After awaited teleport, TaskRunner's single-use callback drains the
pinned runtime's timer capture before orientation. The reset then checks chat
on each admitted native pose frame before world recognition, with the same
1920x1080 geometry bound as the baseline. Open or unknown chat is terminal.
Position, yaw, source-age and settled-sample requirements are unchanged.

TaskRunner owns deferred activation through native disposal and final input
cleanup. Closing the task rejects later activation, cancels and awaits an
already pending drain, runs cleanup, and only then releases capture and cancel-
hotkey scopes. There is no detached timeout waiter. The existing 75-second reset
budget includes admission and cleanup; synchronous trigger callbacks remain
cooperative and cannot be forcibly preempted. The client requires advertised
support before opting in and pins the selected policy through terminal evidence.

The full RDP Python suite passed 215/215 tests. All 331 focused C# checks passed:
295 native timing/reset/capture-ownership cases and 36 external-control cases,
with zero skipped tests. The first compile caught missing imports and incorrect
xUnit overload selection in new tests; those test-only fixes and the identical
successful rerun are retained. Independent reviews of the v3 timing, deferred
ownership and reset/client integration found no actionable issues. All 20
changed/new C# files are UTF-8 without BOM. The required full Debug build,
Release publication and separately reset live trials follow; no r23 gameplay
result is claimed yet.

## r23 publication and isolated reset results - 2026-10-24 UTC

The required full Debug build and Release publish completed from clean commit
`30b7038406b5f88d8b28d7e615ac274568dbf8dc`. The packaging wrapper then exited
with an error because its nested Windows PowerShell could not resolve
`Get-FileHash`. The published files were preserved. Python SHA256 recovered the
standard manifest after checking the earlier build/publish exit-code guards;
the original failure, log hash and recovery timestamp are retained in
`r23-build-manifest-recovery.json`. This was manifest recovery, not a successful
wrapper exit. The published DLL is
`a204beee835cb6532fdfd1d9397b29447542c54724ead07c341eae4d9a8ad380`.
Its 529-file source snapshot was verified before the saved Game shortcut replaced
child 43052 with 45072. The primary remained minimized and connected to session
3; Genshin PID 27728 retained its creation time.

Two separately initiated resets selected `task_owned_timer`; both failed while
orienting before baseline execution. Their logs do not identify the orientation
acquisition ordinal. Consequently,
neither run exercises the v3 walking contract. Run02 deliberately repeated the
same policy after the first cold-child failure, as recorded in
`r23-comparison-plan-amendment-01.json`; it is not the originally planned v2 pair.

| Reset | Source age after capture | Capture-gate wait | Own readback Map | GC pause delta |
| --- | ---: | ---: | ---: | ---: |
| `2f668cadca944f1fbf54aa4dde79813c` | 530.82 ms | 0.0065 ms | 286.28 ms | 0 ms |
| `fd319c5c59f246a9abcf0e3db3ed38c1` | 906.21 ms | 0.0061 ms | 677.80 ms | 0 ms |

Both immediate capture-gate probes were uncontended. Raw source ages at initial
acquisition were approximately 240.55 and 223.56 ms. Isolation therefore removed
the measured gate-contention pattern in these two calls, but their own readback
delays still made the images unusable. These observations do not prove a GPU
workload attribution or a capture-policy reliability improvement. Selecting a
newer queued frame alone cannot make a 677.80 ms Map satisfy the 500 ms reset
limit. Exact source clocks, capture stages, owner identities and log-line hashes
are retained in `native-baseline-r23-01-reset-source-analysis.json` and
`native-baseline-r23-02-reset-source-analysis.json`. Both terminal checks found
input released, the child idle/attached, and the same minimized primary and game.

The next reset change will discard an old initial post-teleport frame within the
existing bounded readiness window and wait for independently fresh evidence
before camera input. Later source failures remain terminal. No stale image will
be accepted as a pose, and source-age limits will not increase.

The build helper now hashes published files through a streaming .NET SHA256
function without relying on module auto-loading. Six focused tests passed for
exact binary bytes, empty/large files, literal Unicode paths, released handles,
and missing/locked-file errors. The fixture deliberately makes `Get-FileHash`
unavailable. A fresh nested-shell probe currently resolves both that cmdlet and
`ConvertTo-Json`, so the historical availability failure was not naturally
reproduced and serialization was left unchanged. Independent review is clear.

## r24 initial post-teleport source readiness - 2026-10-24 UTC

Only the first post-teleport orientation acquisition may now discard an
otherwise-valid, same-epoch frame whose source age exceeds 500 ms immediately
after capture. It uses the existing three-second, 25-attempt acquisition window
and 120 ms retry interval. The rejected image does not reach recognition or
camera input and does not update the consumed source clocks, epoch or input
barrier. Preparation, later orientation, verification and post-recognition
source failures retain their terminal behavior. A changed epoch remains terminal
even when the image is also stale. The 500 ms freshness threshold and 75-second
owner budget are unchanged.

Cancellation and target identity are rechecked after capture returns. A separate
bounded transient log retains the first discarded source without consuming the
existing terminal diagnostic slot. This is readiness handling before camera
input; WGC frame selection, blocking readback and GPU configuration are unchanged.

All 120 focused NavigationReset tests passed, including 15 new cases for exact
age boundaries, scope, invalid/changed source identity, stale-to-fresh recovery,
cancellation and finite wait bounds. The log and TRX are retained as
`reset-initial-source-retry-01.log` and `reset-initial-source-retry-01.trx`.
Independent review is clear and all three changed/new C# files are UTF-8 without
BOM. Full Debug/Release validation and separately reset live trials follow.

## r24 live readiness and walking diagnostics - 2026-10-24 UTC

The complete build wrapper succeeded from clean commit
`4606614edc692c5ff754b411b0ce49917fd54a0e`: required full Debug, Release publish,
and manifest hashing all passed. DLL SHA256 is
`3dae13b8b9cf092ea5a177490e02a986b59b6746afb948aa8ad5dd2fc2ac5ba6`.
The 530-file tools snapshot was verified before the saved Game shortcut replaced
child 45072 with 40720. The primary remained minimized and session 3 connected;
Genshin PID 27728 and its creation time were preserved.

Reset `c2b4275fc4344e38b6fe84f292bb5582` failed while orienting, after a
584.10 ms readback Map. The source was 278.21 ms old at acquisition and 867.49 ms
old after capture. Immediate contention was false and recorded GC pause delta
was zero. There was no transient-source log: the exact same-epoch, after-capture,
age-only failure reached the terminal branch, which establishes that this was a
later orientation acquisition rather than the first settling acquisition. The
first-only r24 allowance therefore did not cover this failure. Earlier r23 logs
did not establish their acquisition ordinals; their description above is
corrected accordingly.

One explicitly labeled diagnostic then reused that known teleported state,
without claiming a verified reset. Native baseline source/world/start-position
gates independently passed. Run `f1e17182dffd460fa183c0bf78491f79` used v3 and
`task_owned_timer`, advanced 3.012 map units through 20 accepted observations in
1,888.68 ms, then failed source freshness. Accepted capture median/max was
8.87/15.98 ms, recognition 26.66/44.90 ms, and source age 105.05/114.09 ms.
All 20 same-frame chat checks were Closed. Only one physical W hold occurred,
so this does not establish the repeated-start benefit of v3.

The final capture took 86.44 ms, including 84.18 ms Map, after acquiring pixels
already 66.20 ms old. Source age was 153.27 ms at the failed observation's exit;
recognition did not run on that image. The capture gate was uncontended and GC
pause delta zero. Keyup completed 5.10 ms after the logical lease deadline,
without release error. The last accepted pose remained 6.82 units from the
endpoint. This is neither a completed route nor a separately reset comparison.
The retained initial image shows normal Mondstadt world view at the waypoint;
no final image was produced. Journal SHA256 is
`a71443cc2275cc4c59c15ebeccd40931f9daa83de1308b8cbda36f85168619b1`.

The two terminal checks left input released and the child idle/attached under
the same minimized host. The next work separates three issues: bounded fresh
pose waiting throughout reset, newest-of-two WGC selection to reduce queued
image age, and an explicit future continuity contract that can release input
and reacquire fresh evidence after transient lateness. Existing v1/v2/v3 timing
and training-ineligibility claims remain unchanged.


## r25 pose readiness and bounded newest-frame selection - 2026-10-24 UTC

Every orientation and verification pose acquisition may now discard a sole-age
stale source at the after-capture or after-recognition check. The exact nonempty
capture epoch must already be pinned. Preparation, malformed clocks, changed
identity, invalid geometry and hard world/pose failures remain terminal. The
existing 500 ms freshness limit, three-second/25-attempt/120 ms acquisition
window and 75-second owner budget are unchanged. The missing-HUD allowance
still applies only to the first orientation read. After-recognition discard
retains consumed source clocks and map observation, returns before camera input
or success, and does not advance the input barrier. The bounded diagnostic is
now version 2, recording preparing/orienting/verifying phase, the one-based pose
probe ordinal and initial-HUD allowance. At most one transient and one terminal
source record are logged per reset.

WGC V2 now inspects at most two pool entries and renders only the newest accepted
frame. Each accepted source advances the generation high-water mark and retains
its original first-acquisition clock, including discarded frames. An accepted
geometry change immediately stops lookahead and follows the existing iconic or
Recreate/invalidate/skip path. Pull, property and cleanup failures dispose owned
candidates before propagating; known changed bounds invalidate old publication
if selection cleanup fails. Ordinary and diagnostic capture use the same bounded
selection. Three fixed counters report pulls, nonnull frames and discarded-frame
disposal attempts; the pool interval now includes selection, property reads and
discard cleanup. A disposal attempt does not establish successful native Close.
This reduces avoidable queue age; it does not bound blocking Map or establish a
live latency improvement before measurement.

All 210 focused tests passed with zero skipped: 128 reset, 21 newest-frame
selection, 10 lifecycle/pump, 9 capture timing, 23 source freshness and 19 baseline
diagnostics. The synthetic maximum-count journal is 4,952,755 bytes, below the
6,291,456-byte cap. An initial test compile failed on an always-throw lambda
selecting an obsolete async assertion overload; an explicit Action cast fixed
only that test, and the failed attempt is preserved. Exact command/environment,
eight source-file hashes and log/TRX hashes are retained in
`r25-reset-wgc-focused-02-validation.json`; the summary is
`r25-reset-wgc-validation-summary.json`. Independent production review is clear;
all changed C# files are UTF-8 without BOM. Full Debug/Release packaging and live
validation follow. Baseline v1/v2/v3 timing and training eligibility are unchanged.
