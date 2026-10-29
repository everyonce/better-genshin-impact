# BetterGI agent status

Updated October 29, 2026. The latest work adds a three-station street patrol, a steering observer and an image-only station recognizer. See the [patrol learning report](BetterGI-Patrol-Learning-2026-10-29.md). Earlier trials cover [physical obstacle recovery](BetterGI-Obstacle-Gameplay-2026-10-29.md), [courtyard navigation](BetterGI-Hybrid-Gameplay-2026-10-27.md) and [model latency](BetterGI-Agent-Sprint-Results-2026-10-23.md).

R57 and the resident Open P2P GPU model completed 24 crossings of the Mondstadt stair post in 210.98 seconds inside minimized RDP on October 29. The first climb escape taught a detour. All 23 subsequent crossings reused it, including four that paused for stale images and resumed. Median model evaluation was 30.38 ms and median image-to-first-input dispatch was 81.14 ms. A separate 5 Hz run verified four ground-stall escapes. The October 27 courtyard run completed 60 legs in 259.80 seconds. The evidence covers fixed local navigation courses. Combat, quests and independent learned-model task completion still need in-game qualification.

R57 is the current child package at `artifacts/release-r57/BetterGI-English-win-x64/BetterGI.exe`; the existing R56 primary host was retained. The October 27 evidence is under `artifacts/live/2026-10-27-hybrid`. The current reproduction profile uses H41, 10 Hz decisions, native RGB192 and the 150 ms first-input deadline. Release retention preserves pinned R1/R55/R56 and useful recordings/test results. The following October 26 details are historical, including process identities and the temporary GPU-testing deferral.

## Historical October 26 checkpoint

New GPU experiments were temporarily deferred while investigating reported
desktop lag. At 19:03:49 UTC, `nvidia-smi` showed 43% GPU use, 87°C and active software
thermal slowdown, with 4,615 MiB free. No model or gameplay-controller worker from
this task was running. Three aggregate CPU intervals at 19:05:43–46 UTC measured
22.60–25.52% busy, with about 12,071–12,121 MiB physical memory available. These
brief device-wide samples do not identify a responsible process or measure disk
latency. At 19:23 UTC, CPU intervals were 16.46–24.61% with about 12.6 GiB of
physical memory available; GPU thermal slowdown remained active. A single-worker,
below-normal-priority Debug build started at 19:24 UTC and passed in 279 seconds.
The focused recorder/resampler/wire suite then passed all 97 cases (14 seconds of
test execution). The current RDP session and game remain open.
Evidence: `host-lag-aggregate-readonly-01.json` and `host-lag-summary-01.json`.

Daniel explicitly resumed live testing through BetterGI RDP at 14:18 UTC on
October 26. R56 now runs in session 3 while preserving Genshin and the minimized
RDP session. The console root remains R1. Live tests include four 30-second P2P
trials, four 90-second walk/stand/walk goal-switch trials, a GameScaling shadow trial,
five WGC capture shadow trials, a 45-second H41 monitoring trial, a
30-second H200 climb-recovery trial, an H41 trial stopped by its recovery budget,
a successful 45-second H41 trial with shorter retry and a 20-second positive-goal trial,
and a successful native seed route followed by four connected courtyard legs.
The model/control pipeline works, but the learned policies do not yet reliably
follow Genshin instructions. R54 removed first-dispatch expirations in the latest
trials. Blocking WGC capture now supports about 28 captured frames and 19 model
decisions per second in the latest live run; repeatable task quality remains
under investigation.
Evidence is under `artifacts/live/2026-10-26-r52`. The earlier offline-only
transition remains historical evidence, not a current restriction.

| Area | Latest verified state |
|---|---|
| Upstream integration | The default branch `refactor/20260930` is integrated through `ae4f785c`. The latest merge adds explicit inactive-affix recognition and corrects capitalization matching; the required Debug build and 10 scripted OCR cases passed. Earlier integration cohorts recorded 539 distinct UnitTest cases and 527 Agent cases across their source trees. Live feature validation remains deferred. |
| Prepared local builds | R56 is a self-contained `win-x64` Release package from `1d501ac5`, with dirty-tree provenance recording the concurrent documentation/Python work. Its compiled native source matches R55. Required Debug build, Release publish and launcher validation passed. R55's focused readback/freshness/controller cohort passed 147 cases, including 17 new retry cases. R54's earlier controller/capture cohort passed 731 distinct cases. Older packages remain intact. |
| Root upgrade staging | Commit `5f9ad00e` adds opt-in, byte-preserving Pulonia staging for a quiescent source and inactive, exclusive target. Twenty new tests and three existing regressions passed; independent source review found no actionable issue. Live use remains deferred. |
| Coordinated root/child upgrade | The explicit transaction uses the approved launcher and a one-shot startup binding, preserves the game/session, and ends with scheduling held. Earlier validation passed the Debug build, 129 C# cases and 91 Python cases. The approved task/helper now pass actual launcher preflight after a process-local PowerShell utility-module fix. A verified-package exception handles R1's omitted stream-status field; 17 new admission cases and 14 existing fake transaction cases pass on primary, and the actual R1 read-only admission passes. Cold launch, handoff and explicit resume remain untested. Host access to child/game query/synchronize handles remains blocked; no root retirement was attempted. |
| Deployed application | R56 child PID 58188 in RDP session 3, instance `dcc56e3913414257a64479af4a08926e`, assembly SHA256 `0bd78a568fe314a8d97312f0d5c7a2375e93e4325e288ac50d4953946b26ec62`. Root PID 28072 and Genshin PID 27728 were preserved. The selected capture path is blocking WGC with source retention and CPU conversion. R54's H41 WGC run applied all 1,707 accepted actions; R55's H200 run applied all 1,584 but remained climbing for most of the trial. H200 is not promoted. |
| Resident child replacement | An observation-only R55→R56 probe retained worker PID 35228, its native birth, resident run ID and one model load. Saved frame/readiness joins independently reconstructed 17 fresh predictions before and 14 after replacement. The replacement command took 17.872 seconds. The original lease's disconnect, failed aggregate and exit code 1 remain preserved; recording bytes were complete with zero drops. This verifies weight/process continuity with history resets, not seamless input or root cold launch. The worker retired; a separate process check found only the original game in session 3. Evidence: `continuity-run-002` and `continuity-run-002-audit-01`. The first attempt's artifact-sharing failure remains in `continuity-run-001`; a bounded logger correction passed nine distinct inert cases before the fresh run. |
| Native navigation | A fresh R52 seed and four immediately linked courtyard legs completed with 254 position observations and no recorded recovery, recognition, release or execution faults. All 15 journal/screenshot hashes and 140 listed evidence checks passed. This is exploratory native route acceptance, not general autonomous gameplay or a rebinding of the frozen R47 proof. |
| Native WGC image reference | R56 completed a v4 short route with passive same-source RGB capture: 5.139 seconds, 56 poses and 128 intact RGB images. The archive is complete and retired with zero loss. The 945-check file/contract audit passed, including journal/manifest/image hashes and source joins. Recognized displacement was 8.889 coordinate units; endpoint distance fell from 9.823 to 0.972. Scripted controller intent remains explicitly ineligible as expert training data. |
| Reusable command | Bounded continuation and the reviewed schema3 envelope checker are in primary. Explicit v5 client support passed 279 Python tests. The separate H03 reader package remains bound to R47. Current live runs use fresh instance and predecessor identities; the direct CLI successfully validated the R52 cycle. |
| Endpoint repair | Deployed in R46 with input telemetry and Right Shift support. Both R47 routes and the return's endpoint/continuation evidence pass their full audits. Physical input acknowledgment and training eligibility remain false. |
| Native timing v5 | The fresh R52 cycle used `task_owned_timer` and the supported single-leg seed/advertised courtyard continuations. The four continuation legs took 24.83 seconds wall time, including approximately 0.28–0.31 second handoffs. Recorded source ages had median 62.17 ms, p95 74.83 ms and maximum 84.96 ms. |
| Offline recognition replay | Eleven saved captures passed scoped CPU replay: five exploration frames, two climbing frames, the journal, one swimming-controls frame and two map screens. Eleven additional swimming-derived rows are explicitly synthetic. Five recorded positions match the production coordinate conversion; the other checks do not establish localization or current readiness. |
| GPU runtime | Existing PyTorch 2.7.1 + CUDA 12.8 environment on the RTX 2080 SUPER. Bounded loaded-model latency runs and paired scene/goal probes completed on October 26; their fresh results are below. No environment installation was needed. |
| P2P temperature candidate | Explicit `--p2p-temperature 0.2` is available for replay and shadow runs. Its walk/stand improvement on bilinear pixels did not transfer to native Hamming pixels: walking stayed idle across 54 consecutive predictions. Landmark probes also mostly became idle. Forty actual API predictions matched the reference; the public CUDA graph command and 100 CPU checks passed. Default sampling remains unchanged; this is not a qualified gameplay setting. |
| P2P key compatibility | The official Right Shift command is included in deployed R46 through the existing input implementation. Separate live key-delivery qualification remains pending. |
| Action acknowledgment | A matching request ID is required before settling policy history. Unknown outcomes preserve the pending action and stop the runner. The focused candidate and caller cohorts passed 55 distinct mocked tests. |
| Execution-aware decisions | Opt-in client snapshots and GameScaling prompt conditioning are implemented; 121 distinct inert tests passed. One live attack command returned a completed software receipt. The closed context and graph comparisons produced neutral input in both contexts and did not establish receipt-dependent behavior. |
| Ongoing input telemetry | The Python client passed independent review and 103 tests; the C# producer's 26 cases passed within R46's 1,860-test validation. The producer is deployed, but a controlled live ongoing-call test remains pending. |
| Continuous recording replay | A separate offline preparer verifies one complete lease across resident segments and preserves original video-file/local-index addresses. One six-segment archive passed, including four windows crossing video boundaries. Forty-eight Python checks passed; these remain automated trajectories with training eligibility false. |
| Terminal receipt timing | A saved shutdown receipt exposed a timestamp sampled before the input lock. Terminal releases now refresh a valid session clock under that lock; replacement retains its exact successor-acceptance boundary. The Debug build and 160 selected C# cases passed, including six new cases. This source change is included in the deployed R54/R55 builds. |
| P2P execution-history commit | Offline CUDA comparison passed 860 byte-exact cache comparisons across 44 reference calls, 48 proposals and 43 scripted commits. A bounded RDP trial then verified live image intake, rejected-proposal rollback and cleanup; its first proposal missed the latency limit, so no action was submitted. Live receipt-authorized history commit remains unverified. |
| Native history rollback | Offline CUDA validation and its closed-result audit passed: 44 reference calls, 48 candidate attempts, 44 acceptances, four rejections and 960 consistency checks. Live controller integration remains unverified. |
| Growing-history graphs | Two native startup prefixes passed capture, replay and 192 independently recomputed consistency checks. Full coverage of all 41 prefixes and startup latency remain unqualified. |
| Receipt-bound startup graphs | Three consecutive native prefixes passed all 534 numerical gates with zero recorded error, including all 60 committed K/V leaves, actions, RNG and rejected proposals. The two continuation handoffs took about 4.08 and 5.09 seconds. Preloading, longer continuation and live use remain unqualified. |
| Pending tensor transfer | A four-pair public-path comparison passed 1,368 numerical checks with zero recorded error. Packed transfer averaged about 185.73 ms versus 184.06 ms for the original path, and all four receipt calls were slower. No speedup is established; the optimization is not promoted. |
| Preloaded history graphs | Conditional graph cleanup passed all 356 numerical gates with zero recorded error across two preloaded prefixes and 40 committed K/V leaves. First/final retirement took 10.49/19.76 ms and handoff took 173.11 ms in this diagnostic run. Longer continuation and continuous gameplay remain unqualified. |
| Paired Q/K arithmetic | Rejected by the full native four-call comparison: 33 of 224 gates failed (25 cache and eight logit/score comparisons). All 136 exact gates passed, but that does not establish numerical equivalence or permit promotion. |
| Shared rotary values | The numerical qualification source and complete host fixture passed review: 28 archives, 817 arrays and 412 checks are represented. A separate ordinary-call timing harness and its exception-restoration correction also passed source review. Actual CUDA numerical equivalence and latency remain untested. |
| Fixed attention masks | One actual G12 graph-pair qualification passed 267 numerical checks with zero observed differences. Both captured graphs and all ten masks retired; other prefixes, latency benefit and live use remain unqualified. |
| Continuous input handoff | Queued-successor v2 remains off by default. The per-session server negotiation passed the Debug solution build and all 527 selected C# Agent tests. The installed experimental start CLI passed 19 fake-transport tests, and the installed Python handshake/transport cohort passed all 194 cases. The unchanged checkpoint scope has 43 previously passing cases; five harness checks and standalone capacity cleanup also passed earlier. Runtime activation, actual numerical qualification and observation/dispatch timing remain pending. |
| Checkpoint qualification entry | The complete single-load P/Q composition passed 104 guarded CPU cases, including the earlier scope and entry cases. Its real producer and reader validated 17 containers, 197 arrays and 120 checks using fake numerical operands. The assembled worker also passed all 30 guarded wrapper cases, including retained-state admission and failure cleanup. Actual model loading, numerical equivalence and controller timing remain unqualified. |
| GameScaling device-greedy decoding | A loaded-model run completed four setup calls and four balanced pairs. Saved records pass exact token/action checks and 236 exact recorded common-state comparisons; both graphs fit with 2,580 MiB peak PyTorch reservation. The candidate saved only 8.66–53.04 ms (0.19–1.42%) under heavy GPU load. Independent process verification was blocked, so full qualification and promotion remain withheld. |
| Model optimization | Skipping unused final decoder work passed 1,733 correctness checks across two history41 evictions. A separate 40-pair experiment reduced median prediction time from 165.30 ms to 155.07 ms; paired actions/random states and final cache checks passed. |
| Training | Not started. The pinned public P2P metadata has no Genshin labels; local demonstrations remain needed. The current recorder captures automated receipts, not human input. Model proposals and incomplete recordings are not expert action labels. |

## Latest WGC recorder load check

`r56-native-shadow-cycle-v4-01` completed four verified native legs: seed,
return, forward and return. Durations were 5.127, 5.516, 5.369 and 5.889 seconds.
The exact predecessor chain, endpoint continuity and software input cleanup
passed 3,571 saved-evidence checks. All 445 retained RGB hashes matched.

The first three image archives were complete (126, 144 and 137 frames). The
fourth retained 38 images but stopped admission with `shadow_buffer_exhausted`:
one rejected offer and 288 subsequent ignored offers. Its journal contains 112
distinct sources without archived RGB, so `framesLost=1` is not a complete
coverage-loss count. The native route still completed and the archive worker
retired; the overall command correctly failed and never started the fifth leg.
Evidence: `r56-native-shadow-cycle-v4-01-independent-audit-01/audit-02.json`.

The source fix passes the required Debug build and 97 focused tests. It returns a raw
slot immediately after resizing and partitions the existing 66,355,200-byte
reserve into eight 1080p BGRA slots or two 4K BGRA slots. There is still one
writer, a fixed two-second retirement bound, and truthful failure on overflow.
New timing and high-water fields separate queued, resizing and writing work.
All 14 recorder cases passed, alongside 83 related resampler/wire cases, with no
failures or skips. Release packaging and live qualification are pending. R56
continues running the previous binary. Evidence:
`recorder-buffer-primary-validation-01.json`.

A separate read-only process-access matrix confirmed that the ordinary host
can retain the root lifetime but cannot even query the child/game. The ordinary
RDP worker can retain child/game lifetimes but cannot query the root. Thus the
current child-side root-retirement implementation also needs an architectural
correction; relaxing the Python preflight would not make it work. No root
retirement or permission change was attempted. Evidence:
`r56-process-access-matrix-01-host.json` and `r56-process-access-matrix-01-rdp.json`.
An additional ordinary-host probe obtained termination/query/synchronize rights on
the exact existing R1 lifetime and closed the handle without using those rights.
This supports retiring R1 from the host while an independent RDP sentinel retains
the child/game lifetimes; the coordinated transaction still needs implementation.
Evidence: `r1-host-termination-rights-readonly-01.json`.

The training preparation identifies 52 causal image-to-scripted-intent pairs
in the earlier short-route archive, not fixed-duration expert demonstrations.
All existing training-eligibility flags remain false. An isolated synthetic
head-gradient smoke is being prepared for the original four P2P output heads
(65,600 parameters). Its file-only preflight verified 20 source pins; no gradient
update or model deployment has run.

## Live climb-recovery prototype

The composed transport-origin, opt-in climb-recovery and shorter retry changes
passed 199 inert tests together. The required Debug build passed with the
installed .NET 10 SDK; the later timing correction changes only Python.
Recovery requests use a separate origin and X authorization. They do
not become model proposals or model history. Unknown action outcomes and
unfinished recovery are terminal; ordinary pipe reconnect cannot re-arm them.

R56's 45-second H41 run (`p2p-r56-climb-03`) completed with 1,250 captured
frames, 849 predictions and 824 accepted/applied model actions. Saved motion
hints were 1,246 normal and four unknown, with no climb, so this checks normal
monitoring rather than recovery efficacy. Model medians across the three
segments were 38.80–39.81 ms; first-dispatch source-age medians were
74.27–76.54 ms. Four stale predictions were refused. Recording completed
without drops and final tracked held keys were empty.

After a fresh waypoint/heading reset, the 30-second H200 diagnostic
(`p2p-r56-climb-04`) completed with 408 accepted model actions and two separately
recorded X attempts. This was **one recovery episode**, not two successful
recoveries: the first X receipt completed but subsequent hints remained climb.
The second attempt began after the five-second cooldown; fresh normal hints
then allowed model control to resume. X software intervals were
22,133.0428–22,246.0151 ms and 27,200.4370–27,314.7402 ms. The first resumed model
action began at 27,644.8927 ms. The saved audit passed 35 joins, including
terminal receipts, cleanup/history resets, exit frames and the resumed model
request; all 28 pinned inputs remained unchanged. Complete recording and empty
tracked held keys were retained. These are software receipts and absence of
climb hints, not physical-input acknowledgment or proof of groundedness.

An intended 90-second H41 run (`p2p-r56-climb-05`) subsequently stopped after
about 24.4 seconds with `attempt_budget_exhausted`. It retained 680 frames and
341 accepted model actions. The first episode again required two X attempts;
only the second was followed by model resumption. A later climb exhausted the
two-attempt lifetime budget. The aggregate remains failed with
`evidenceComplete=false`; final tracked held keys were empty. The worker exited,
and a separate native-handle check inside RDP confirmed the original child and
game births. The original root was also confirmed. This separate check was
needed because the initial worker wrapper skipped its final lifetime check on
an exception; the wrapper now performs that check in cleanup on either outcome.

A fresh 45-second H41 trial (`p2p-r56-climb-06`) qualified the shorter retry in
one observed climb episode. It completed with 1,256 frames, 812 predictions and
788 accepted/applied model actions; all accepted requests had exactly one matching
receipt. The second initial release followed the first cleanup/history reset by
794.19 ms. The two X starts were 1,050.12 ms apart, and model control resumed only
after the second attempt and two fresh normal hints. Both X receipts completed;
this again establishes one recovered episode, not two successful recoveries.
Model evaluation was 42.71 ms median / 55.20 ms p95. First-dispatch source age
was 79.39 / 104.51 ms, with a 127.79 ms maximum. All recording segments completed
without drops; final tracked keys were empty and the original root, child and
game lifetimes were preserved. The independent audit is
`p2p-r56-climb-06-independent-audit-01/audit-02.json`.

The policy waits at least 750 ms after successful terminal cleanup/history reset
within one unresolved incident. Separate incidents retain a five-second
release-based cooldown and the resident's two-attempt lifetime limit. H41 remains
preferred. This shorter retry does not solve repeated-wall behavior. Source
inspection found the X key in the native release path, including its key-up and
fallback check; the software telemetry does not establish physical key release
or explain why the first attempt left the climb hint active.

A subsequent 20-second H41 run (`p2p-r56-left-01`) used the independently encoded
positive instruction “Turn left and walk along the street.” All 555 captured
frames had normal motion hints; 373 of 374 predictions were accepted/applied,
with no detected climb or recovery. Model evaluation was 38.47 ms median /
48.29 ms p95; first-dispatch source age was 72.65 / 94.74 ms. Recording and cleanup
completed and original process lifetimes were preserved. This demonstrates short
movement, not reliable left-turn instruction following: decoded horizontal mouse
movement summed positive, and the trajectories are not a controlled paired
comparison. Quality requires independent visual/position evidence.

The progress monitor previously rejected every native square image despite
receiving its original widescreen dimensions. It now restores only its diagnostic
HUD coordinate plane from the verified native profile; model pixels are unchanged.
The 199 composed tests and 15 synthetic progress tests pass on the final primary
source. Legacy headers without original dimensions remain supported.

The subsequent 30-second live run (`p2p-r56-progress-01`) completed with 827 frames,
553 predictions and 538 accepted/applied model actions, all with unique matching
receipts. Every motion hint was normal. It retained 127 progress events—five
collecting and 122 moving—with no geometry rejection, all explicitly labeled
`low-detail-hud-difference`. This confirms metric availability, not physical
displacement or reliable wall detection. Model median/p95 was 41.88/52.52 ms;
first-dispatch source age was 77.59/100.77 ms, maximum 134.31 ms. Recording,
empty-key cleanup and original process lifetimes were preserved. Shared load
and trajectories were not controlled, so this does not isolate metric overhead.

## Native image reference and GameScaling decoding probe

R56's v4 native short route completed under blocking WGC with passive Hamming
RGB192 recording (`r56-native-shadow-v4-02`). The published 5.139 seconds includes
about 308 ms after the journal's 4.831-second workflow. Its 128 unique frames
were selected from 316 capture polls; the other 188 offers were duplicates,
not lost images. The archive writer retired with zero losses or rejected frames.
The independent audit verified 945 file/scalar joins, all RGB/PNG/journal/manifest
hashes, pose/source joins and v4 expiry arithmetic. It retained 56 pose samples,
52 controller intents and 23 input transitions. Observation source age was
33.48 ms median / 52.30 ms p95; active-input intent source age was 34.55/43.43 ms.
These are software/recognition measurements and scripted intent, not physical
input acknowledgment or expert training labels. Audit:
`r56-native-shadow-v4-02-independent-audit-01/audit-01.json`.

The first attempt remains separately failed at `measuring_start` with
`route_corridor_exceeded`, zero pose/input rows and one passive image. A baseline
does not teleport implicitly; the successful attempt used an explicit reset first.

The successful route's initial and final PNGs then supplied four offline
GameScaling calls: greedy and unfiltered temperature-1 sampling on the same two
images, FP16/eager, history zero and no thinking. Both greedy outputs and sampled
initial output were neutral. Sampled final output pressed F for its first 33 ms
step, then became neutral. The image visibly contains an F/Mikhail prompt, which
contextualizes the output without proving causality. All four complete 30-token
outputs parsed, but **none obeyed the W-only instruction**: zero W keys in 24 steps.
The local path can emit controls; changing decoding alone did not fix this task.

Both separately supervised workers retired successfully, source hashes were
unchanged, and peak reserved GPU memory was 2,420/2,442 MiB within the 3,072 MiB
limit. No game input was sent. These four cold eager calls are a behavior probe,
not a latency comparison with the graph-enabled live run or official BF16/vLLM
deployment. Audit: `gamescaling-native-route-probe-audit-01/audit.json`.

## Resumed live testing in BetterGI RDP

Four 30-second trials used the live R52/R53 children, native Hamming RGB192 images,
P2P history41, cached ground-navigation text, CUDA graph prewarming, one CPU
thread and a 3 GiB PyTorch allocator limit. Both retained the 150 ms first-input
freshness bound, 100 ms action hold and restricted movement-key list. Each trial
started after a verified reset to the same Mondstadt waypoint. Shared-machine
load and in-game trajectories were not controlled, so these are diagnostic runs.

| Live setting | Model median / p95 | Predicted actions | Accepted / applied | Too-old predictions | Recorded data |
|---|---|---:|---:|---:|---:|
| Detailed execution context | 45.04 / 59.29 ms | 367 | 217 / 190 | 104 | 89.91 MiB |
| Context off, native snapshots off | 43.29 / 54.07 ms | 404 | 371 / 361 | 18 | 45.35 MiB |
| R53 exclusive capture, context/snapshots off | 38.53 / 45.88 ms | 467 | 397 / 368 | 34 | 53.96 MiB |
| R53, decision rate reduced to 15 Hz | 39.07 / 47.69 ms | 439 | 317 / 284 | 95 | 54.22 MiB |

The first trial prepared its graph during loading in 2,071.82 ms and evaluated
its first real image in 30.97 ms, without graph preparation in the input loop.
These recordings completed without frame/event/observation drops and
returned stopped controllers with empty tracked held-key sets. These are
software dispatch receipts, not physical-input acknowledgments or task-success
labels. The owned live-model workers were independently confirmed retired
after the GameScaling trial. Recordings and reports are under
`artifacts/live/2026-10-26-r52`.

Source inspection found that the normal trigger timer still captured while the
agent ran its independent capture loop. `RunAgentWithResultAsync` now acquires
the existing task-owned timer pause, preserving window/liveness housekeeping
and the existing cancellation/cleanup scope. This change is deployed in R53.
Across all recorded frames, median capture-request-to-authoritative-start time
fell from 21.305 ms to 0.002 ms. The complete capture/preprocessing interval was
62.35 versus 61.04 ms; the inner host acquisition interval rose from 32.02 to
51.78 ms. These are distinct boundaries, and uncontrolled load prevents a
causal interpretation of the inner-interval change. Hamming conversion is
below 1 ms. Reducing decisions to 15 Hz increased receipt-to-prediction waiting
and deadline rejection, so 20 Hz remains the current diagnostic setting.

The 90-second R53 goal-switch run recorded 1,593 frames without drops and made
1,501 predictions, with 1,315 accepted and 1,239 applied actions. One model load
served walk/stand/walk goals. The status observer saw matching goal-application
acknowledgments 188 and 140 ms after the corresponding control CLI returned
(50 ms observation polling). Tracked held keys were empty after stop.
During the stationary phase, 206 of 415 applied proposals contained movement
keys, versus 202/392 and 283/432 in the two walking phases. The saved video also
shows movement during the stationary phase. Correct command acknowledgment
therefore does not establish instruction compliance. A separate H41 diagnostic
ran six graph/eager pairs using two saved 192-pixel video frames in an A/B/A
goal sequence. Its NumPy-only readback passed 374 checks over the retained
arrays, including copied goal values, cache resets, stable graph addresses,
paired sampling and full cache comparisons at the existing tolerances.
Both paths chose S in all six predictions, including the stationary phase.
This excludes the tested graph/goal-buffer mismatch on these inputs; it does
not establish general instruction compliance. All diagnostic workers were
confirmed retired at 15:32 UTC, preserving the same Genshin process in RDP.
Evidence: `p2p-distinct-goal-parity/independent-summary-001.json` under the live
artifact directory.

All 76 accepted-but-unapplied actions in that run expired before their first
dispatch. Their remaining deadline slack at acceptance had median 3.84 ms;
applied actions waited median 4.51 ms and p95 14.30 ms from acceptance to first
software dispatch. R54 immediately dispatches the first eligible
standard step after acceptance, through the existing guarded controller path.
A shared failure latch prevents retrying partially failed input. The 150 ms
limit and experimental queued scheduler are unchanged. Additive DesktopDc
phase timings retain the exact captured snapshot identity and authoritative
clock boundaries, making capture costs measurable without changing input
eligibility. These changes are deployed and live-tested in R54.

The combined controller/capture cohort has 731 distinct passing tests across
the initial run and a permissions-aware rerun. The initial sandbox blocked
three named-pipe label cases and one atomic snapshot write; all four passed
with normal Windows permissions, along with all 18 immediate-dispatch cases.
The scalar recorder-only microbenchmark averaged 0.854 microseconds and 312
allocated bytes per call over 10,000 samples; this excludes GDI and pixels.

R54 repeated the same 90-second walk/stand/walk configuration with 1,561 frames,
1,461 predictions and 1,361 accepted/applied actions. There were zero
first-dispatch expirations. Acceptance-to-first-software-dispatch time had
median 0.0163 ms, p95 0.0252 ms and maximum 1.256 ms; the corresponding R53
median/p95 were 4.512/14.304 ms. Every applied start remained within the
150 ms host-source-age limit. One later receipt ended for stale world
observation; all tracked keys were released at shutdown. The recording
completed without dropped frames, events or observations.

Movement keys occurred in 394/436, 42/508 and 294/417 applied actions across
the three goal phases. Saved frames show street movement, standing beside a
wall, and a final view pressed against that wall. This is not successful
goal-directed navigation. The source fidelity check found no text-template,
RGB channel, W/S mapping or mouse-scaling mismatch. Official inference uses
BF16, H200 and 50 ms holds; this local setting uses FP16, H41 and 100 ms holds.
The official README states most paper experiments used no text, and Genshin
is absent from its listed tested games. Those differences remain quality
considerations rather than established causes of the observed behavior.

All 1,561 R54 frames retained matching diagnostic/snapshot identity. Median
DesktopDc total was 51.356 ms: BitBlt alone was 45.640 ms, clone 3.103 ms,
pre/post target checks 0.708/0.741 ms, cleanup 0.676 ms and allocation 0.098 ms.
Gate waiting was 0.0004 ms. Complete capture/preprocessing remained 60.183 ms.
This localizes the dominant cost to desktop pixel acquisition; weakening
target/session checks would not address it.

WGC V2 comparisons used retained source surfaces and CPU color conversion.
The initial 30-second `poll_single_v1` shadow run had 447 frames, 134 predictions
and 453 pending readbacks. Capture/preprocessing median was 9.66 ms, but reported
source age at response was 110.50 ms and estimated age after prediction was
147.14 ms. Pending already avoids direct readiness invalidation; the stream
waited a full capture cadence before polling again, while the client's hold
path could release and invalidate older in-flight sources. A bounded retry
candidate now yields 2 ms for at most eight retries within the original
33.33 ms turn. Genuine failures, timestamps and freshness guards are unchanged.
Its focused cohort passed all 147 tests, including 17 new retry cases. The clean
R55 build is deployed. Its 30-second polling shadow run delivered 841 frames and
579 predictions, with all recorded frames world-ready. Capture/preprocessing
median was 27.34 ms; reported source age at response was 56.23 ms. Estimated age
after prediction was 99.70 ms median, 124.51 ms p95 and 141.66 ms maximum. The
recording completed without drops, and no model input was enabled. This improves
the observed polling outcome; blocking remains the lower-age candidate pending
the fresh configuration comparison. R55's following H41 blocking shadow trial
delivered 843 frames and 576 predictions, all recorded frames world-ready.
Capture/preprocessing median was 16.46 ms, source age at response 29.30 ms and
estimated age after prediction 75.65 ms median / 100.23 ms p95 / 127.85 ms max.
Both R55 shadow recordings completed without drops. Blocking remains selected
for live use; these sequential runs are diagnostic, not load-controlled pairs.

The released P2P H200 temporal configuration was then tested without input,
using the same R55 blocking/native192/FP16 settings and 3 GiB allocator cap.
It produced 847 frames and 555 predictions in 30 seconds. Model evaluation
was 50.60 ms median / 58.84 ms p95; estimated age after inference was
85.25 ms median / 107.47 ms p95 / 122.85 ms maximum. Readiness was positive
on 846 frames after one confirming frame, and recording completed without
drops. Shadow history includes unexecuted predictions and omits the live
rollback backup, so a live comparison is still necessary. Full-history cache
storage increases by approximately 223.59 MiB for graph input/output and the
live backup, excluding graph pools and scratch; this is source-derived, not
a measured process-memory delta.

The existing resident navigation-progress heuristic rejects the square native
model image as `unsupportedHudAspectRatio`; its output does not measure movement
for this profile. Live quality therefore relies on recorded visual evidence,
separate from software movement intent. The model profile is preserved.

The H200 live walk/stand/walk comparison completed with 2,536 frames, 1,610
predictions and all 1,584 accepted actions applied. There were no first-dispatch
expirations; median/p95 model evaluation was 46.29/61.12 ms and reported source
age at first software dispatch was 83.29/108.56 ms, maximum 146.85 ms. Eleven
predictions were too old, thirteen requested excluded keys, and two crossed
goal-control epochs. Recording completed without drops and shutdown held keys
were empty. Its worker was independently confirmed retired at 16:29 UTC.

This did not improve behavior. Applied movement-key counts were 312/550,
102/504 and 8/530. The character began climbing a building at 7.896 seconds and
never returned to a detected normal state during the remaining 82.07 seconds.
All three saved phase images visibly show climbing/hanging. The existing
same-frame native motion detector reported 2,307 climb, 223 normal and six
unknown frames; its median/p95 recognition cost was 0.641/0.849 ms. Execution
context being off does not disable this detector. Ground-navigation intent
currently labels recovery context; it does not gate climbing inputs or provide
a drop/reposition action. Existing idle-history reset does not drop the character.

H41 also encountered climbing in the earlier blocking WGC run: 894 of 2,542
frames were climb, across three episodes that each returned to a detected normal
state (approximately 14.72, 15.28 and 1.31 seconds). Thus H41 is the better current
latency/behavior setting, but neither configuration reliably follows the ground
constraint. Normal detection only establishes absence of the Space hint, not
proof of standing on the ground. The native reset successfully recovered the
H200 run to the verified waypoint at 16:30:56 UTC. Evidence:
`motion-comparison.json`, `p2p-r55-h200-goal-switch-segments/00001.json`,
`post-r55-h200-live-process-check.json`, and `r55-reset-after-h200.json`.

The same WGC backend in blocking mode produced 853 frames and 591 predictions
in a separate 30-second shadow run. Capture/preprocessing median was 13.27 ms,
estimated source age after prediction was 63.31 ms, and readiness was positive
on 852 frames after one confirming frame. Every prediction's estimated age was
under 150 ms. Both shadow recordings completed without drops and used no model
input. Neither observation-only admission nor reported compositor timestamps
establish physical-input or true game-render latency.

The subsequent 90-second blocking WGC live walk/stand/walk run captured 2,542
frames and made 1,728 predictions. All 1,707 accepted actions were applied,
with zero first-dispatch expirations. Median/p95 model evaluation was
38.70/47.48 ms; capture/preprocessing was 14.18/22.41 ms. Reported compositor
source age at first software dispatch was 74.16/96.45 ms, maximum 112.81 ms.
Acceptance-to-first-dispatch median was 0.0162 ms. Five predictions were too
old, fourteen requested excluded keys, and two crossed goal-control epochs.
The applied movement-key counts were 561/582, 36/568 and 428/557 across the
three phases. Saved frames show the character at a wall, beside a building,
and on stairs; movement-key counts do not establish route completion.
The recording retained all frames/events/observations, used 352,776,510 counted
bytes and closed completely. Shutdown held keys were empty. The worker was
independently absent at 16:05 UTC, preserving Genshin's original session-3
process. Shared load and trajectories differ across trials; DesktopDc host
acquisition and WGC compositor-age measurements also have different boundaries.
Evidence: `p2p-r54-wgc-goal-switch-segments/00001.json`,
`dispatch-capture-comparison.json`, and `post-r54-wgc-live-process-check.json`.

GameScaling's live observation-only trial used the validated greedy graph,
history0 and image width384. It recorded 337 frames and generated 14 valid but
entirely neutral action chunks for an explicit six-step W-only instruction.
Full-action median was 940.28 ms; the first action took 5,018.97 ms including
setup. Both required graph validation actions passed. No model input was
enabled, accepted or applied. `observeMode` is not a freshness pass, and these
results do not support using this path as the real-time controller.

The approved `StartHost` task and protected helper installation passed read-only
validation at 14:26 UTC. No registration was needed. The coordinated root
upgrade and cold launch remain separate, untested operations.

## Latest upstream merge and R52 package

The upstream default branch advanced by one commit, `ae4f785c`, adding localized
inactive-substat markers to artifact recognition. The fork includes it in merge
`bd552493`. A new test calls the public recognition path using scripted OCR,
synthetic card pixels and an input backend that rejects keyboard/mouse access.
The upstream implementation passed seven cases but failed three capitalization
variants. Ordinal case-insensitive marker matching passes all ten cases with no
skips, including the existing fourth-substat grayscale fallback. No OCR model,
real screenshot or salvage operation was used. The required Debug solution
build passed with the installed SDK and package cache.

R52 was then built and published from clean `bd552493`. Its 2,703 files total
925,980,125 bytes; all 154 User files match source. The production launcher's
`-ValidateOnly` path passed. Its managed assembly SHA256 is
`9adfccce383b25726799b319b51254121b0c59429cc852787c26ffec2fceea53`.
The package is at `artifacts/release-r52/BetterGI-English-win-x64`. It was
deployed to the existing RDP child after live testing resumed. The combined source,
package and launcher proof is
`artifacts/research/2026-10-24/r52-local-completion-01.json`
(SHA256 `6fa1f7c5a42ec1b326651eb0f5e9c0930c9be86fbfe1ae336e5a9cf1ca11fd27`).

## Optional startup preparation and recorded idle intervals

`stream_client.py --p2p-prewarm` prepares the existing masked P2P CUDA graph
inside `load_policy`, before a bridge is opened. A temporary zero-valued RGB192
image retains the real input's HWC-to-CHW storage layout. The existing capture
validation runs, then history and pending feedback return to empty state. No
controller action or recorded observation is emitted. Failure aborts policy
loading. The option requires Open P2P, CUDA graphs and masked fast startup, and
remains off by default. Twelve focused CPU checks passed.

Two bounded saved-image comparisons passed: history length 41, and the default
200 frames with the goal changed after preparation but before the first image.
Each comparison used two predictions per arm with simulated acceptance followed
by rejection. All four paired outputs matched exactly, as did goal, uniform,
CPU/CUDA random state and 160 recorded cache-tensor comparisons before and after
feedback. Rejection restored the previously committed history. These comparisons
repeat one archived image and one seed; they do not establish gameplay quality.

Illustrative first-prediction wall times were 3,269.25 vs 159.47 ms (41 frames)
and 3,282.42 vs 168.68 ms (200 frames), cold vs prewarmed. Preparation itself
took 2,233.72 and 2,133.44 ms during loading. Peak reservation was 572 and
1,066 MiB. Both runs used one CPU thread and a 3 GiB allocator cap. Cold ran
first, shared-machine load was uncontrolled, and these small comparisons are
not steady-state latency qualification. Tool-owned runs exited successfully;
independent process verification and live qualification remain unavailable.
The first attempt stopped on a harness assertion that confused token and frame
indices; its failed result is retained. Readback evidence is
`artifacts/research/2026-10-24/p2p-startup-prewarm-review-01.json`
(SHA256 `2c9f15b881cde5e9a7014d56d0994748c34f2ad551777a8f154e3cef9ed2a817`).

A separate audit partitions 117.30 seconds of the archived r16 software-input
timeline: directional keys account for 41.61%, explicit neutral applications
34.93%, empty held-key states following mouse-only events 17.03%, other held
inputs 0.29%, and released states awaiting another application 6.14%. Mouse
deltas are instantaneous events, not held movement. There were 1,807 accepted
receipts but 1,793 applied steps, including 648 neutral states. The 65 release
intervals form 61 continuous gaps; consecutive release events do not create
separate causal gaps. The first graph preparation took 1,945.21 ms. These are
historical timings with 200 frames of policy history, and software intent does
not prove physical delivery, character motion or task success. Evidence is
`artifacts/research/2026-10-24/r16-input-coverage-audit-03.json`
(SHA256 `dd66063a28347d9bf39cc264cdf8903433cec748d6f4932af25bdd8a6c882ab2`).

## Continuous evidence and demonstration readiness

A file-only inventory found 47 archived recording segments declaring 82,656
encoded frames. It did not decode videos or establish visual task success. The
older replay preparer rejected the newer resident format because carry-over
headers are not new observations and segment boundaries are not episode
boundaries. The new `prepare_replay_session.py` verifies a complete, single-lease
chain before applying the existing frame, receipt, reset and goal checks.
Original source files remain unchanged; every output frame points to its actual
video file and local encoded index.

The six r16 segments contain 3,328 observations and 1,807 terminal receipts.
Four explicitly selected windows cross recording boundaries and retain 40
history frames each. A fifth probe was excluded for a policy-history reset.
The initial r16 rejection was a validator defect: the saved
`navigationIdleRearmed` event was present, but the older check counted only
`navigationIdleRecovery`. Both event types must now match their report entries,
and both remain interruption boundaries.

The six r17 segments still fail the strict audit. One `client_stop` receipt ends
0.2208 ms before its last applied step. Its original timestamp has not been
rewritten. The current controller had the same race: callers could sample time
before waiting for the input lock. Normal and queued terminal releases now
refresh a valid session clock while holding that lock, before release. Failed
optional clocks cannot prevent cleanup. Replacement does not resample its
shared old-end/new-acceptance timestamp. This improves software timing evidence;
it does not establish physical key delivery or game acknowledgement.

The required Debug solution build passed using the existing repository package
cache. All 160 selected C# cases and 48 portable Python cases passed with no
skips. The Python checks imported no model runtime. Their file-link test required
ordinary filesystem access outside the sandbox and used disposable workspace
fixtures. No live status, capture, input, application replacement or GPU inference
was performed for this source validation. R49/R50 remain unchanged and do not
contain the new terminal-clock change. A clean self-contained Release build of
`f938b51e` now supplies the fix in inactive R51. Its 2,703 files total 925,979,613
bytes; all 154 shipped User files match source. The production launcher's
`-ValidateOnly` path passed without process or application checks. R51's managed
assembly SHA256 is `c54b60d6b6031f2a09951c0c6c981b24e6ccd63e2388283e583f63138668a93f`.
Live deployment and qualification remain deferred.

The CPU-only `experiments/continuous_replay_pixels.py` reader now reconstructs
the entire prepared plan from the original sidecars before decoding. It verified
2,783 video-frame records across five original r16 videos and exported 168 PNGs
for the four accepted windows. Each 40-step window retains an anchor and separate
probe, giving 42 images; both action-label variants address the same image files.
Selected video PTS/index pairs and PNG RGB round trips passed. All eight focused
checks passed, and the real rejected r17 plan stopped before any source-video
inspection or output-directory creation. The final export matches every decoded
RGB hash from the earlier reader version. No policy, Torch or Transformers runtime
loaded. H.264 compression still limits fidelity to original live RGB, and the
software action receipts remain non-expert evidence rather than training labels.

Evidence under `artifacts/research/2026-10-24`:

- `replay-session-validation-02/completion.json`: SHA256 `07b8945b0bb0d23b21f1346bd89f0b1127a0afc1dff98ddc0c692fff1b0dd6c9`.
- `replay-continuous-r16-boundaries-01.json`: SHA256 `60aed0dc597feb01b336e731c3ccd930f3cd33322cd5318c01e0815e9d5a1179`.
- `replay-continuous-r17-02.json`: SHA256 `5ddee510fef50067850a3f8efcb4544c81229db5e3b9198a7ba5f5113a2d60f8`.
- `r51-local-completion-01.json`: SHA256 `ff8a3be3c7382b2a7dc78300781a2d7cf53bef8d2fd875daa736d9d866593950`.
- `continuous-pixel-validation-01/completion.json`: SHA256 `099fe1eb5036683a093f071ebe0358dec66eb91420436b4c15d40129dc2136fe`.
- `replay-continuous-decoded-r16-02/manifest.json`: SHA256 `9bb0da0b23043f1ce017d1533e3d9b9b24b81b63e921135ccb5f5cc599f543f4`.

Human demonstrations still require a separate synchronized input ledger. The
existing macro recorder retains relative wall-clock times, merges nearby mouse
movements and omits the shared stream-clock anchor and input provenance needed
for training. Its keyboard hooks and relative-mouse monitor lifecycle are useful
building blocks. Future collection should run inside the RDP child and preserve
unmerged events, held-state transitions, source identity and loss markers on the
frame clock. No human-input recording or training has started.

## GameScaling literal-key control

A finite saved-image diagnostic completed 12 cold greedy calls: two archived
frames, two repeats and three instructions. The frames differ in whether a
contextual F prompt is visible. All 12 outputs were the same valid, complete
200 ms neutral action; all six repeated arm/frame pairs matched exactly.

| Instruction | Whole-chunk rubric passes | Cases requiring F | Cases emitting F |
|---|---:|---:|---:|
| Press F now, with no other controls | 0/4 | 4 | 0 |
| Press F only when its prompt is visible | 2/4 | 2 | 0 |
| Stand still | 4/4 | 0 | 0 |

The combined 6/12 score only matches the always-neutral baseline. Removing the
visibility condition did not elicit F in this configuration. This narrows the
next investigation but does not identify a cause: history zero, reduced image
size, disabled reasoning and model task coverage remain unresolved factors.
The original eager generation path used FP16, width 384, a 64-token limit and
no warmups. Its cold call times are not a latency comparison.

All 105 source pins, both input copies, checkpoint bytes and retained reports
passed readback. Each original tool execution returned zero. No independent
process identity or retirement check was attempted; the local watchdog is not
independent supervision. Lifetime, live-quality and training qualification
remain false. The earlier fully qualified execution plan remains unready.
The limited diagnostic receipt is
`artifacts/research/2026-10-24/offline-gamescaling-literal-f-direct-01/review.json`
(11,124 bytes, SHA256
`1aa0e40dd1d53b061ff1ea56c14160af109e7ac08968f3901c236d66e6c2175f`).

The offline benchmark now has an explicit `--gamescaling-reasoning` switch for
a controlled follow-up. Its open-thought prefill and strict parser follow the
pinned upstream implementation; the live stream CLI does not expose the switch.
All 50 focused CPU regression cases passed, including seven new cases. Actual
CPU processor checks confirm identical image tensors and prompt content except
for the assistant suffix (842 versus 840 tokens). Four actual upstream parser
checks also passed, including rejecting an action inside unfinished reasoning
and ignoring an example action inside a completed thought. No model predictions
or CUDA initialization occurred in those CPU checks. Evidence is under
`artifacts/research/2026-10-24/gamescaling-reasoning-cpu-01/` and
`artifacts/research/2026-10-24/gamescaling-reasoning-inputs-01/review.json`
(22,330 bytes, SHA256
`91ed0bf44273271538a358646efbbf352dc027b9734404ac4599a38a9dc9d282`).
The matched GPU comparison then completed one prediction per mode on the saved
frame with the visible F prompt, using the same 160-token cap. The action-only
case stopped after 30 tokens and matched the earlier 64-token result exactly.
The reasoning-enabled case emitted an empty, closed thought and stopped after
32 tokens. Both returned the same neutral action. Merely enabling reasoning did
not elicit F on this frame; this does not show whether substantive reasoning
would help. All 109 source/configuration pins passed readback. The receipt is
`artifacts/research/2026-10-24/offline-gamescaling-reasoning-direct-01/review.json`
(5,865 bytes, SHA256
`dd6ed74485edfe6f8b4835638eb7b8f1001b66b751c558e4a7d0320ea40b4fa2`).

A further single call removed manual downsampling (`--image-width 0`) while
retaining the action-only control's other settings. Actual CPU preprocessing
kept all non-image tokens identical and increased image tokens from 84 to 2,040,
with a 68x120 patch grid from the original 1920x1080 capture. The GPU call still
returned the exact same 30-token neutral output and all six action steps. Peak
PyTorch reservation was 2,644 MiB within the existing 3 GiB cap. This comparison
uses RGB input; it does not reproduce upstream's JPEG transport. Its 110 pinned
source/configuration files passed readback. Evidence is
`artifacts/research/2026-10-24/offline-gamescaling-native-size-direct-01/review.json`
(2,788 bytes, SHA256
`32cf99114b7c25925bfa1c679d6411b0c38793ca2aa8a87ecd2cbcad0985c05a`).
These follow-ups retain the same missing independent lifetime verification and
provide no live, latency or training qualification.

The same 0.8B checkpoint then processed upstream's saved Doom example at native
1280x720 size with its supplied system prompt. One greedy call and three sampled
calls (temperature 1, seeds 42–44) produced four valid, compatible, non-neutral
chunks. Two contained keyboard/mouse-button input; one fired, and one used
movement keys. The other two changed only the camera. This establishes that the
local generation path can emit active controls, without establishing correct
aiming or gameplay competence. The
[upstream reference](https://github.com/THUSI-Lab/GameScaling/blob/6764efabfbb4121d6e5d3cfcbc54dedf1469bf5a/examples/run_example.py)
used a 9B model with five prior frames, so it is not an exact answer target for
these cold 0.8B calls. The reference answer was excluded from model input.
All 116 pinned files and retained responses passed readback; peak PyTorch
reservation was 2,402 MiB. The receipt is
`artifacts/research/2026-10-24/gamescaling-doom-sanity-01/review.json`
(7,121 bytes, SHA256
`d9f657557a609cb4b58ee7c0efd5a520a4087ba8008bde74c3161b8bbb45a411`).
The independent lifetime, latency, live-quality and training limitations also
apply to this diagnostic.

Published real-time 0.8B results use BF16 and vLLM on one H200 per instance.
That deployment is documented in the paper's
[serving configuration, Appendix B.4](https://arxiv.org/html/2610.28698v1).
The current cold eager diagnostics are behavioral probes; the earlier local
CUDA-graph latency measurements remain the applicable optimized references.

## Coordinated application upgrade

The new `upgrade-root-child` command retires only the verified original root
and idle bootstrap child, then stages the root's settings and opaque Pulonia
files into a separate final package. It preflights conflicting destination data
and the existing fixed launcher before retirement. The final root and child use
the same build, reconnect to the protected game/session, and keep scheduling
paused. A separate `resume-upgrade` command initializes saved state, retains
existing compatibility checks, rechecks admission and identity, then completes
the startup record and releases queued work. The transaction never resumes work
automatically.

The final source passed the required Debug solution build. Its 51 passing C#
cases include 34 new startup/upgrade cases and 17 existing recovery cases; all
91 Python cases passed, including 14 new transaction cases. An earlier test
invocation selected an old x64 assembly and is explicitly excluded. The accepted
C# receipt uses the newly built `bin/Debug` assembly. Independent readback
verified all 25 changed source files against their retained copies and checked
63 evidence files; review found no remaining actionable source issue.

The clean managed checkout then passed another required Debug build and a
self-contained Release publish. R49 contains 2,703 files totaling 925,975,225
bytes; all 154 User files match clean source. R50 is an exact separate copy of
those application files, with its own manifest identifying its final directory.
The production launcher's file validator accepts both packages. A further 78
existing state-compatibility, trigger, shutdown and remote-ownership cases passed
against the clean checkout's new Debug assembly, bringing the distinct C# total
to 129. Neither package has been launched or deployed.

The package and regression receipt is
`artifacts/research/2026-10-24/root-child-upgrade-local-completion-01.json`
(2,621 bytes, SHA256
`97a8c9738b1ed64f7808bbe5926a9d2a611cef531a2515845a860b38f149ddd8`).

This is source and offline validation, not a live deployment. The existing
approved task must still pass its actual preflight. Root absence permits opaque
copying but does not prove historical multi-file coherence. Failed or uncertain
handoffs retain their evidence and startup markers without automatic retry,
rollback or scheduling release. Operational details are in
[the RDP command guide](../../tools/rdp-automation/README.md#coordinated-root-and-child-upgrade-explicit-scheduling-held).

Evidence: `artifacts/research/2026-10-24/root-child-upgrade-root-review-01/review.json`
(17,391 bytes, SHA256
`deb1ca9853d94cb33c6516bc48c93d7cf44de1c92a720ade33804899c4ab9d0e`).
The frozen source handoff is
`artifacts/research/2026-10-24/root-child-upgrade-candidate-01/source-handoff-01.json`
(4,859 bytes, SHA256
`8d3ae670b34556aedfbc3f7205fe7881aa7ef1e9a847117d0cde67144cb67cc8`).

## GameScaling token-selection comparison

At 03:17–03:19 UTC on October 26, the existing experimental device-greedy
decoder ran beside the original decoder, sharing one model while retaining
separate graph/cache owners. Four setup calls exercised the original complete
action validation, followed by four pairs in alternating baseline/candidate order.
The input was the earlier retained 640x360 frame, with either image-only input
or the same frozen execution-receipt context. No game or controller was accessed.

| Saved workload / order | Baseline public call | Candidate public call | Candidate reduction |
|---|---:|---:|---:|
| Image-only, baseline then candidate | 3,723.70 ms | 3,670.66 ms | 53.04 ms / 1.42% |
| Image-only, candidate then baseline | 3,677.24 ms | 3,645.88 ms | 31.36 ms / 0.85% |
| Receipt context, baseline then candidate | 4,500.80 ms | 4,485.66 ms | 15.14 ms / 0.34% |
| Receipt context, candidate then baseline | 4,531.69 ms | 4,523.03 ms | 8.66 ms / 0.19% |

The saved-record reader verified matching complete tokens and public actions,
unchanged RNG, and all 59 common state entries per pair. All 236 recorded
comparisons were exact. Float arrays were not retained, so their numerical
deltas cannot be independently recomputed. Both graphs and their caches passed
the worker's cleanup checks; peak PyTorch reserved memory was 2,580 MiB within
the 3,072 MiB cap. Every output was the same 30-token neutral action, including
the image-only calls whose instruction requested one attack.

These four pairs show only a small reduction for this workload. The GPU was
96–98% busy at 88°C with active thermal slowdown, and graphics clocks ranged
from 975 to 1,350 MHz. These measurements neither estimate idle-machine speed
nor replace the earlier, different-workload benchmark. Reference gated-delta-rule
and causal-conv1d fallbacks remained active.

The numerical worker and its supervisor reported completion, and the outer
owned job closed. However, Windows denied the independent observer's CIM query.
Automatic approval review then rejected a narrowly scoped self-process query
because the active hold includes process/status checks. Permission for only
offline benchmark-worker checks has been requested separately; no workaround
or further process query was attempted. The full lifetime audit is incomplete,
and the candidate remains disabled and outside production.

Evidence: `artifacts/research/2026-10-24/offline-gamescaling-device-greedy-01/review.json`
(10,488 bytes, SHA256
`4a70361107be01e6b5d25d0c4da912c165c0b8995f34e34cad211ec0404f64c3`).
The new packet preserves the original numerical helper bytes. Its only runtime
source changes rename the earlier mistaken offline-hold authorization field and
enforce one intra-op/inter-op CPU thread; the user's live-game hold remains in force.

## Fresh saved-image model runs

Three actual loaded-model runs completed between 00:52 and 01:01 UTC on
October 26. Each owned worker exited successfully and its job was closed.
The closure independently recomputed the summaries, joined the CUDA and NVML
device identities, and verified all 185 unique source/input pins. These are
ordinary adapter measurements; the separate execution-aware native qualification
and disabled optimization candidates remain unqualified.

| Model path | Measured calls | Full action median / p95 | Replay publication to action median / p95 | Peak PyTorch allocated memory |
|---|---:|---:|---:|---:|
| P2P eager, history 41 | 12 | 205.00 / 235.90 ms | 218.89 / 266.02 ms | 416.85 MiB |
| P2P CUDA graph, history 41 | 12 | 35.82 / 46.21 ms | 54.03 / 68.86 ms | 463.52 MiB |
| GameScaling CUDA graph, history 0, width 384 | 8 | 938.59 / 1,018.31 ms | 951.48 / 1,046.64 ms | 2,369.09 MiB |

All 12 measured P2P graph calls used an already prepared graph and finished
their full-action calculation below 50 ms. Replay queue age still pushed its
publication-to-action p95 above 50 ms. P2P's eager and graph runs used different
warmup/capture work and independently initialized random state; this is not a
matched numerical-equivalence experiment or a controlled speedup estimate.

All actions parsed and passed the software protocol checks. All eight
GameScaling outputs were the same complete 30-token neutral action despite the
walking instruction. That observation is a behavior gap on this test image,
not a task-quality score. GameScaling's median first-token latency was 330.85 ms.

The retained street image was captured on October 25 at 17:13:29 UTC. P2P
directly resized its 1920x1080 pixels to 192x192 using PIL bilinear resampling;
the adapter's legacy profile name does not imply that a 640x360 stream resize
occurred. The cached goal embedding was loaded without timing the encoder.
P2P's accumulated actions are synthetic proposals, not executed-action or
expert labels. Repeating one frozen image cannot establish navigation ability,
live capture/input latency, or continuous gameplay.

Each worker used one CPU thread, a 3,072 MiB PyTorch allocator cap and a 180-second
worker limit. Admission required 3,584 MiB free GPU memory and 6,144 MiB available
RAM. Device-wide thermal slowdown was active; telemetry covers loading, warmup
and inference together and does not attribute work to another process. The
allocator cap excludes CUDA context and other driver allocations.

GameScaling reported reference fallbacks for gated-delta-rule and causal-conv1d
kernels. The current [FLA CUDA dependencies](https://github.com/fla-org/flash-linear-attention/blob/main/pyproject.toml)
require Triton 3.3 or newer, while the standard [Triton Windows support table](https://github.com/triton-lang/triton-windows)
lists this Turing GPU under Triton 3.2. A separately mentioned Turing fork has not
been installed or qualified here. The existing environment remains unchanged.

Evidence: `artifacts/research/2026-10-24/offline-model-reference-closure-01.json`
(13,028 bytes, SHA256
`c595ffcfbae6f67d8b2f9ddcd887bca691a27d78784fb2fcb749f9cba44f6094`).
It pins all three plans, benchmark reports, worker supervision and logs.

## Saved-image goal response

The next probes used the same two retained courtyard route endpoints and cached
walking/standing goals. P2P ran 160 predictions: four image/goal cases plus a
duplicate-image control, each across 32 paired seeds. Every call reset to empty
history; the original temperature-1 sampling and mouse decoder were retained.
All 32 duplicate controls matched in tokens, raw actions, controller steps,
cache contents and random state. Changing the image altered 10/32 walking
actions; changing the goal altered 18/32 actions on the initial image and 19/32
on the final image. These are proposal differences, not successful navigation.

| Model / instruction | Movement proposals on initial image | Movement proposals on final image |
|---|---:|---:|
| P2P / walk forward | 27/32 | 27/32 |
| P2P / stand still | 17/32 | 15/32 |
| GameScaling sampled / walk forward | 1/8 | 1/8 |
| GameScaling sampled / stand still | 1/8 | 1/8 |

Movement here means a proposed W/A/S/D key, not measured displacement. P2P
therefore responds to the image and goal, but the standing instruction still
produces movement in roughly half these cold-history samples. Its instrumented
probe is not a latency benchmark. The first recorder attempt failed while
flattening structured action fields; its failed worker and logs are retained,
and the corrected second attempt completed with unchanged model/source bytes.
Independent closure: `artifacts/research/2026-10-24/offline-p2p-scene-goal-02/closure.json`
(4,547 bytes, SHA256
`52569c3414dd6213a64fea87c6e87243f02838a17b68102003f09baa07aa33dd`).

GameScaling ran 48 measured sampled predictions, including 16 exact duplicate
controls, with temperature 1, no top-k/top-p filtering, history 0, width 384 and
at most 64 new tokens. Changing the image altered 3/8 raw actions for either
goal. Changing the goal altered none of the eight paired actions on either
image. The production CPU prompt path was reconstructed with model construction
mocked and stopped before CUDA: both instructions survived tokenization, text
inputs differed (835 versus 826 tokens), and image tensors matched. The original
benchmark did not record prompt or full RNG/cache traces, so this reconstruction
and the duplicate controls do not imply the stronger state proof of the P2P run.

All 48 GameScaling outputs parsed and passed protocol checks. The initial image
produced no input in 5/8 unique-seed trials, and the final image in 3/8, for both
goals. Full-action median/p95 was 936.76/1,149.65 ms for walking and
929.70/1,080.44 ms for standing; peak allocated memory was 2,371.22 MiB.
Both workers closed successfully, and original whole-action generation validated
the first two warmup actions in each run. Independent closure recomputed the
summaries, compared all paired outputs and verified 117 unique source/input pins:
`artifacts/research/2026-10-24/offline-gamescaling-scene-goal-closure-01.json`
(9,259 bytes, SHA256
`56a401973be3c36275edd9f7cf20f775b5f8053c78913135fee20be4a9247bb8`).

These small samples expose instruction-response limitations; they do not rank
gameplay quality, prove text-independent logits, qualify live control or create
expert training labels. No actions were sent to the game.

## P2P temperature candidate

A second 160-call cold-history probe changed only the original P2P model's
explicit sampling temperature from 1 to 0.2. All paired calls started with the
same image, goal tensor, cache and random state. The original mouse decoder was
retained, and all 32 duplicate-image controls matched exactly.

| Instruction / retained image | Movement at temperature 1 | Movement at temperature 0.2 |
|---|---:|---:|
| Walk / initial | 27/32 | 32/32 |
| Walk / final | 27/32 | 31/32 |
| Stand still / initial | 17/32 | 0/32 |
| Stand still / final | 15/32 | 1/32 |

Movement means a proposed W/A/S/D key. This is evidence for a useful sampling
setting on these two images, not a general instruction-following or navigation
score. It does not require training a new model.

Five completed full-history episodes then used seed 9001, 42 warmup calls and
12 measured CUDA graph calls each. Walking produced movement on all 12 measured
calls for either image; standing produced no input on all 12 for either image.
The repeated initial-image walking episode matched all 54 token/raw/controller
actions and its terminal cache/random state exactly. There were 270 predictions
in total, including 60 measured graph calls; 12 measured calls belong to the
repeat control. History was filled with unexecuted proposals on an unchanged
image, so these correlated sequences do not establish real gameplay quality.

Two earlier workers reached their 180-second limits and closed their own jobs;
their failed supervision and logs remain retained and are excluded from passing
results. A preparation failure and a free-memory refusal also remain recorded.
The successful single-episode probes used a 768 MiB PyTorch allocator cap,
required 2,048 MiB free GPU memory and 6,144 MiB available RAM, and used one CPU
thread. CUDA context/driver allocations are outside that allocator cap.

The reusable implementation lives in `tools/bettergi-agent/p2p_sampling.py`.
The default temperature 1 delegates to the original factory without extra
arguments; explicit overrides select a separate class and record the scalar in
metadata. The original `model_adapters.py` bytes remain unchanged. Overrides are
accepted by the benchmark and shadow client, refused with `--enable-input`, and
excluded from the existing native checkpoint qualification profile. The scalar
stays fixed for the adapter's lifetime, including captured CUDA graphs.

The actual new API then ran 40 cold-history predictions across eight paired
seeds and five conditions. Every token, raw action, controller step, before/after
cache and random-state hash matched the retained temperature-0.2 reference.
The public benchmark command separately completed 42 warmup and 12 measured
calls using `--p2p-temperature 0.2 --cuda-graph --history 41`. Its graph capture
passed the original action-exact/cache-tolerance checks, and every measured call
used the prepared graph and proposed movement. Full-action median/p95 was
174.72/184.36 ms; replay publication-to-action was 192.84/219.76 ms. Peak allocated
memory was 463.52 MiB. Device-wide utilization was 97–98% during that worker,
with a median graphics clock of 1,095 MHz. These shared-device samples do not
attribute competing work, and this run is not a controlled comparison with the
earlier 35.82 ms median. The full-history diagnostic episodes likewise had
variable latency.

The final CPU cohort passed all 100 tests with no skips and no CUDA
initialization. It covers original factory behavior, the upstream sampling
argument, CLI routing, invalid settings, direct programmatic loading, the live
input boundary, actual native class admission, and existing stream/action/
GameScaling regressions. Retained source copies match the tested bytes.

Independently closed evidence:

- Cold temperature comparison: `artifacts/research/2026-10-24/offline-p2p-temperature-020-01/closure.json`
  (5,760 bytes, SHA256 `18f7c7579ef9e12b6ffea8f5b60063ea6a486f3efa6991778c7f6e6a56f95077`).
- Full-history episodes and repeat: `artifacts/research/2026-10-24/offline-p2p-temperature-history-closure-01.json`
  (19,260 bytes, SHA256 `dabcbd4bfae6a93a0e4fe8ca85fcc5eed9c1935d117a058fe99522b9f26f7bc3`); 178 unique source/input pins were verified, including the frozen original source archive.
- New API parity: `artifacts/research/2026-10-24/offline-p2p-temperature-api-01/closure.json`
  (4,914 bytes, SHA256 `3e2f3617da757cbdb575a64028207857766cce31e4d5114640fe1d95753942ac`).
- Public CUDA graph command: `artifacts/research/2026-10-24/offline-p2p-temperature-cli-01/graph-01/closure.json`
  (3,707 bytes, SHA256 `41ca9af6d84c3cf6ec6d818f821d64854a31ae785849466be236bed152fce44e`).
- Final CPU validation: `artifacts/research/2026-10-24/p2p-temperature-option-validation-02/result.json`
  (2,757 bytes, SHA256 `ade07a05ae2c9837678aa82369c8ceaa772622c34d4b7a1b375a3e5dc5244a72`).

## Directional instruction probes

The temperature option and its initial evidence are pushed in `a601adef`.
Its 11 tested source files match the committed blobs after line-ending
normalization; author and committer use the requested GitHub noreply address.
The local handoff is `artifacts/research/2026-10-24/p2p-temperature-feature-handoff-01.json`.

A broader probe added four instructions: walk left, walk right, walk backward
and jump. Each new cached vector was generated once on CPU with the same local
encoder/tokenizer weights and matched the upstream tokenization and embedding
methods exactly. Both temperature arms ran 56 measured cold-history predictions
on the initial saved image: seven conditions across eight seeds, including walk,
stand and an exact duplicate control. All 56 pairs had identical initial
cache/random state, goal tensor and pixels. All 48 historical control calls also
matched their earlier token/action/cache/random-state outputs exactly.

At temperature 0.2, the complete first-prediction outputs were:

| Instruction | Outputs across eight paired seeds |
|---|---|
| Walk forward | W in 8/8 |
| Stand still | No input in 8/8 |
| Walk left | No input in 8/8 |
| Walk right | W in 5/8; no input in 3/8 |
| Walk backward | W in 3/8; no input in 5/8 |
| Jump | No input in 8/8 |

All mouse deltas were zero in this temperature-0.2 arm. Temperature 1 produced
more varied proposals, but the left/right/backward/jump probes respectively
included A in 0/8, D in 1/8, S in 1/8 and SPACE in 0/8 calls. These are observed
keys, not unique correct-action labels or task-success scores; camera motion and
multi-step behavior matter too.

Separate left and jump episodes then ran 54 consecutive predictions each at
temperature 0.2. Both remained entirely idle, including all 12 measured calls
after filling history 41. Their initial predictions exactly matched the cold
controls; each CUDA graph passed capture checks and both workers closed with
unchanged sources/inputs. Filled history therefore did not resolve this
particular fixed-image behavior. The proposed actions were never executed, and
the scene never changed, so this still does not establish closed-loop failure.

The [P2P paper](https://arxiv.org/html/2601.04575v1) describes training annotations
as extended goals, deliberately avoiding instant directional commands. That
makes these primitive-command probes a limited stress test. Scene-landmark goals
need separate evaluation before interpreting them as general task capability.
The local official inference code also retains the latest text across frames,
so the adapter's persistent cached goal matches that aspect of upstream usage.

Evidence:

- CPU goal encoding: `artifacts/research/2026-10-24/offline-p2p-direction-goals-01/closure.json`
  (3,989 bytes, SHA256 `eeda6c6f164e51c360fb821656f3839a479b7ef449c077d54e5514562082c051`).
- Paired cold predictions: `artifacts/research/2026-10-24/offline-p2p-directions-closure-01.json`
  (12,676 bytes, SHA256 `9b1e080d0947dae58e6df1d1fcc3d7d39389fc6fb7b855abc6f268c8e18bdbcb`); 112 measured predictions, two additional warmups and 178 unique source/input pins verified.
- Continuous left/jump histories: `artifacts/research/2026-10-24/offline-p2p-direction-history-closure-01.json`
  (6,365 bytes, SHA256 `f469c0701f37bee1d9b1a0a95e28174ba78ddcb2d0ac5168924f16454efccdf7`); 108 predictions, 24 measured graph calls and 178 unique source/input pins verified.

## Landmark goal probes

Four scene-based goals were then tested: approach the doorway on the left,
approach the blue waypoint on the right, reach the cobblestone road, and stay
near the waypoint while keeping it in view. Their cached embeddings were
generated on CPU and matched the upstream encoder methods exactly. Each
temperature arm ran 56 cold-history predictions: four new goals plus the same
walking, standing and duplicate controls, across eight seeds on one saved image.

| Goal | Controller outputs different from walking, temperature 1 | Different from walking, temperature 0.2 | No input, temperature 0.2 |
|---|---:|---:|---:|
| Approach doorway | 1/8 | 4/8 | 3/8 |
| Approach waypoint | 2/8 | 5/8 | 2/8 |
| Reach road | 2/8 | 4/8 | 0/8 |
| Stay near waypoint | 3/8 | 5/8 | 2/8 |

All 56 cross-temperature pairs started with identical pixels, goal tensors,
cache and random state. All 48 historical control calls exactly matched their
earlier actions and state, and all 16 within-run duplicate controls matched.
Both workers finished successfully with unchanged sources and inputs.

These differences establish some goal sensitivity on this image. They do not
show progress toward the requested landmark or rank the temperatures by task
quality. At temperature 0.2 every mouse delta was zero, and both waypoint goals
produced W in 6/8 trials and D in 3/8; key counts can overlap in one action.
An initial forward step may be compatible with several destinations. Changing
observations and measured progress are required to evaluate navigation.
No game input, live capture or training labels were produced.

Evidence:

- CPU goal encoding: `artifacts/research/2026-10-24/offline-p2p-landmark-goals-01/closure.json`
  (4,304 bytes, SHA256 `313361103fe9eb6c6f5aa9ca1e4b8139a367501e6d3a0f4e7c1cb58d2e23c1a2`).
- Paired predictions: `artifacts/research/2026-10-24/offline-p2p-landmarks-closure-01.json`
  (13,514 bytes, SHA256 `0215a8066890af19c2f8e057c392add550e2b17543e8a8d678037281f6225503`); 112 measured predictions, two warmups and 178 unique source/input pins verified.

## Native Hamming preprocessing comparison

The preceding goal probes used the ordinary adapter's bilinear resize. A second
comparison used the unchanged production `AgentHamming192Plan` on the same
saved native image. A standalone converter matched both coefficient axes and the
1920x1080 analytical ramp against retained upstream Rust results. It produced
packed RGB192 pixels without loading BetterGI or accessing a live capture.
The native-profile adapter consumed those verified pixels without another resize.

An October 26 source recheck confirmed that the pinned reference uses
[`fast_image_resize` Hamming interpolation with RGB bytes](https://github.com/elefant-ai/open-p2p/blob/a329d98cbe62119679a254d71bea6446773541bc/elefant_rust/src/resize.rs).
The native adapter leaves normalization inside the generated compatibility model.
Its loader replaces upstream BF16 with the selected runtime precision, FP16 here,
while retaining the cast from uint8 and divide-by-255 formula.
The default 20 policy decisions per second and raw 50 ms actions agree with the
reference rescaling path's nominal 20 FPS; explicit controller overrides and
missed deadlines still require measurement. No extra native resize or channel
mismatch was identified. This does not qualify gameplay or justify replacing
Hamming with bilinear based on frozen-image outputs. The first file-only review is
`artifacts/research/2026-10-24/p2p-preprocessing-source-check-01/review.json`
(3,949 bytes, SHA256 `c9fdfff44242ce3e0c71b12af5138775123c8674c043750751223445b3715738`).

**Correction:** that first review omitted the loader's dtype rewrite when calling
normalization unchanged. A CPU check of all 256 byte values through the extracted
source arithmetic found 224 differing normalized values, with maximum absolute
difference 0.001953125; zero and one remain exact. This does not establish a cause
for idle outputs or full-model BF16/FP16 equivalence. The superseding review is
`artifacts/research/2026-10-24/p2p-normalization-source-correction-01/review.json`
(3,148 bytes, SHA256 `b217715edb4559d344c2a122b605554858fe72237ae48392c779356dfc1e3ca5`).
Preprocessing metadata now names the runtime dtype explicitly in its formula;
all eight existing profile tests passed. Runtime precision, pixels and sampling
behavior were not changed, and the CPU diagnostic did not initialize CUDA.

A later controlled comparison retained the upstream BF16 pixel rounding and
cast those values to FP16 before the unchanged FP16 model. All 256 byte values
matched the upstream arithmetic exactly on both CPU and GPU. The same saved
Hamming-resized scene, cached backward/still goals and reset random seeds then
produced 20 predictions: all ten matched pairs had identical decoded and
controller outputs, and all four duplicate controls matched. Among four unique
seeds per arm, the backward goal produced two forward actions, one diagonal
backward-left action and one neutral action. The still goal produced two neutral
outputs, one camera-only output and one attack/camera output. These are token
observations, not game task scores. Changing input rounding alone did not improve
this small comparison; it does not identify the cause of poor instruction following.

The run completed in 34.52 seconds including setup, using 402 MiB peak PyTorch
reservation. This is not a latency benchmark or full-model BF16 comparison.
It used a single interpreter and local watchdog without independent process
lifetime verification; training and live qualification remain false. Production
normalization and sampling were unchanged. Evidence is
`artifacts/research/2026-10-24/offline-p2p-normalization-pair-direct-01/review.json`
(4,781 bytes, SHA256 `1c8474f8aa1554dbb5e11df036450a6c187ee612f598790bc666234615a2ea56`).

In the earlier temperature comparison, each arm ran 56 cold-history predictions. All 112 comparisons with
the bilinear runs began with identical cache/random state and goal tensors;
the prepared pixels differed. Both native temperature arms shared the same
pixels and passed all 16 duplicate controls. The workers closed successfully
with unchanged sources and inputs; 186 unique source/input pins were verified.

| Instruction | No input with bilinear pixels, temperature 0.2 | No input with native Hamming pixels, temperature 0.2 |
|---|---:|---:|
| Walk forward | 0/8 | 8/8 |
| Stand still | 8/8 | 8/8 |
| Approach doorway | 3/8 | 7/8 |
| Approach waypoint | 2/8 | 8/8 |
| Reach road | 0/8 | 7/8 |
| Stay near waypoint | 2/8 | 8/8 |

A continuous native-Hamming walking episode then stayed idle for all 54
predictions, including 12 measured calls after filling history 41. Its initial
prediction exactly matched the cold control and its CUDA graph validated.
The earlier temperature benefit therefore does not transfer even to this other
supported pixel path. Temperature 0.2 remains experimental and the default is
unchanged. These fixed-image proposals do not establish gameplay quality for
either preprocessing method; future comparisons need changing observations and
actual task progress using the exact deployed image path.

Evidence:

- Saved-image conversion: `artifacts/research/2026-10-24/offline-p2p-native-pixels-01/closure.json`
  (2,833 bytes, SHA256 `3d5ea1e6b6a3a5dbcfe72f35e41afeb8ab34214a0ee1ce3bc5c5b0807da33e32`).
- Paired native/bilinear predictions: `artifacts/research/2026-10-24/offline-p2p-native-landmarks-closure-01.json`
  (16,650 bytes, SHA256 `5a012d6ce498960a79754aad161281661be6a4ceee5a8a66dea8b9ca772db3f9`).
- Continuous native walking history: `artifacts/research/2026-10-24/offline-p2p-native-history-walk-closure-01.json`
  (3,696 bytes, SHA256 `3a0806751b7b0b2ab1142cb245991df1cca25ff068512a212cdb56d8b02989bd`); 178 unique source/input pins verified.

## Public training data check

On October 26, the official P2P metadata index at revision
`1553d6b8190d270dcd256528ffa2066098225dba` contained 108,851 distinct recording
paths. A case-insensitive search of both `env_name` and the actual
`env_sub_type` column found no `genshin`, `yuanshen`, or `原神` labels.
This establishes only this index's labels, not a checkpoint's training history
or the absence of mislabeled gameplay. [Pinned upstream metadata](https://huggingface.co/datasets/elefantai/p2p-full-data/blob/1553d6b8190d270dcd256528ffa2066098225dba/data_metadata.parquet)

Only the 6,049,853-byte index was downloaded. Its SHA256 matched the published
file hash, `5fb7ce5ba3f5ec22ce4c084bc1640bc8c1546ff6beaab0f7e8b836cddcf43ed9`.
An existing PyArrow 20.0.0 installation read it using one CPU thread; no model,
video archive, credentials or live capture was involved. The retained inventory
is `artifacts/research/2026-10-24/p2p-dataset-inventory-01/inventory.json`
(66,168 bytes, SHA256
`c8182ceb34bb50ecea964c1e77239b954d0830c9040623e59eceaf42951feb06`).

The next data milestone remains aligned Genshin demonstrations with task outcomes.
The existing stream recorder retains automated execution receipts; human input
collection and verified training alignment remain separate work. Saved-image
predictions must not be promoted into successful demonstration labels.

## Default-branch integration

The upstream default branch adds shared resin settings and result handling,
material collection targets, a unified combat-strategy browser, additional music
formats, multi-instance task execution and cloud-web instance previews. The fork
retains English UI, session-bound input, RDP controls and restart ownership checks.

Compatibility preserves original plan and account evidence before conversion.
Only an exactly empty legacy task state migrates automatically. Populated or
unknown legacy state keeps scheduling blocked; its old records are available in
a separate **Legacy records (read only)** tab with bounded previews and exact
record lookup. This view cannot resume or schedule old work. Legacy resin
policies that cannot retain their original meaning produce an explicit error.

Validation covers 523 distinct core UnitTest cases and 527 Agent cases on the
core merge, then 15 history view-model cases and one offscreen history layout
case on the later UI revisions. The layout case uses the real theme at normal
and narrow widths. These are scoped runs, not a claim that every test reran on
the final source tree. The final Debug solution build passed. Evidence is
`artifacts/research/2026-10-24/upstream-refactor-validation-final-01/validation-summary.json`
(SHA256 `a607a96ae7d8cb0f56a1a55f675b3967e5ebcc9a23d3ecd2be77e6f62a6ff2df`).

The initial parser test run exposed an indirect application-bootstrap dependency
in preview logging. Pure parser defaults now use a null logger; gameplay callers
supply their logger explicitly, and the affected tests pass. The aborted run,
compiler correction and earlier layout-fixture failures remain recorded and are
excluded from the passing totals. The live runtime has not been rechecked during
the machine hold. This integration establishes no new model latency, instruction
quality or sustained-gameplay result.

The integration is pushed in merge `4c99cad1d99406cc60636b3a37998896b54f192a`.
The R48 self-contained Release publish completed at 00:19:55 UTC on October 26,
then all 925,945,021 packaged bytes were inventoried without loading the app or
models. Its build manifest is `artifacts/release-r48/build-manifest.json`
(SHA256 `48d7d5725be1e27ad6b33772727993220836319efd16045a5ebea4fb365bfbeb`).
Package verification and the full file inventory are recorded in
`artifacts/research/2026-10-24/upstream-r48-package-verification-01/verification.json`
(SHA256 `d1346623b9d0c24d8bf5cb3167e7e0841e5595a2419bcafc7ea0b32484b0bd28`).
RDP replacement and fresh runtime checks await explicit machine readiness.

The source comparison with the R47 checkpoint preserves IPC version 2, five
instance contract files and eight child-replacement helper functions. It does
not establish compatibility with the running binaries: the archived R1 host and
R47 child manifests both record dirty source checkouts, and no live check was
performed. R48's new `pulonia.node.*` commands require a compatible root
coordinator as well as the child. At assessment time, the configuration stager
did not copy `User/Pulonia`. Commit `5f9ad00e` now supplies explicit
`--preserve-pulonia --source-quiescent` staging while retaining the default
child-only behavior. All store writers must be quiescent and prevented from
resuming, and the target must remain inactive and exclusive. Inventory/hash
stability alone cannot prove a coherent snapshot of an actively written store.
The helper preserves opaque bytes and legacy scheduling holds; it does not
perform coordinated root replacement or establish runtime migration continuity.
The tested/reviewed source handoff is
`artifacts/research/2026-10-24/root-pulonia-staging-01/source-handoff-01.json`
(6,635 bytes, SHA256
`4429b5d75ec88d0351285d6e1189211182c4d5737ae3bf7c82d7bd4e10a4d374`).
Original source assessment:
`artifacts/research/2026-10-24/upstream-r48-host-compatibility-01/assessment.json`
(SHA256 `9de82008d96770a346b701e66d1b9e0dc58c8901e129ff60706c92b82c35b744`).

## Latency evidence

Each row describes its own workload. Input history, execution backend, capture, instrumentation and machine load differ; controlled task-quality comparisons are still pending.

| Measurement | Median | 95th percentile |
|---|---:|---:|
| P2P earlier offline CUDA graph, history200 | 27.32 ms | 28.14 ms |
| P2P earlier live shared-GPU graph phase | 55.10 ms | 73.93 ms |
| P2P completed 40-call instrumented replay, history41 | 172.69 ms | 183.35 ms |
| P2P paired original, history41, 40 measured calls | 165.30 ms | 183.39 ms |
| P2P paired decoder-tail candidate, same experiment | 155.07 ms | 173.13 ms |
| GameScaling optimized offline graph, 30-token action | 494.48 ms | 531.37 ms |
| GameScaling earlier live shared-GPU run, after validation calls | 1,850.91 ms | 2,586.24 ms |

The old 27.32 ms value is the report's `fullAction` measurement. All 14 adapted
model-source hash rows match the later history41 report, but the exact historical
caller and loader bytes were not recorded. The earliest retained caller uses
192×192 P2P input; its `image_width=384` option applies to GameScaling. History,
goal contents, mouse sampling, preprocessing, RNG seeds and instrumentation
differ between these runs, so their elapsed-time gap has no established cause.
The source comparison is recorded in
`artifacts/research/2026-10-24/native-p2p-historical-latency-source-supplement-01.json`
(SHA256 `57fde1644e801da4942ceb63fdff5996eeeb38c76573b5827ba01e4424244f25`).

The later four-call execution-context diagnostic used ordinary generation, with
CUDA graphs and text-prefix reuse disabled. Its complete 30-token actions took
12,044.73–13,241.64 ms. This is a different workload from the earlier graph
measurements, with no controlled attribution of foreground load, prompt length or
generation backend. It is unsuitable for continuous control in that configuration.

A subsequent controlled comparison used one resident model, the same retained
image and receipt contexts, and alternating call order. Setup and complete-action
validation finished before these four measured pairs:

| Context | Call order | Ordinary generation | Graph generation |
|---|---|---:|---:|
| Before receipt | Ordinary, graph | 11,438.44 ms | 4,778.34 ms |
| After receipt | Graph, ordinary | 12,716.01 ms | 5,099.09 ms |
| After receipt | Ordinary, graph | 12,692.05 ms | 5,272.53 ms |
| Before receipt | Graph, ordinary | 12,863.73 ms | 4,323.55 ms |

Every pair returned identical complete 30-token neutral actions. One graph and
cache allocation served all measured graph calls; no reference generation occurred
inside those calls. The three setup calls included two reference generations.
The closed reader accepted the latency comparison, with no population percentile
or instruction-quality claim. The experiment stayed within its time and allocator
limits, and all three observed processes retired. No generated output was sent to
the game. Local evidence is
`artifacts/research/2026-10-24/execution-context-gamescaling-graph-comparison-assembly-02/closed-audit-01/audit.json`
(SHA256 `ac6ada10eef2f2a633195fb73b425cab181bbd0c5ef9532611e2c4bbe63831bb`).

A read-only sample after retirement, at 06:20:09 UTC, reported 88 C, 94% GPU
utilization, a 1,080 MHz graphics clock and active software thermal clock limiting.
It is a separate observation, not concurrent per-call evidence or an explanation
of the measured differences. Graph generation helps this workload substantially,
but its 4.32-5.27 second actions remain too slow for continuous control.

The 40-call P2P diagnostic passed its closed-report audit. None met the 50 ms target; the scheduler skipped 116 elapsed release slots. GPU event timing places most of the measured stream interval around model graph execution. These event intervals include scheduling effects and do not establish exclusive kernel time.

The later paired experiment kept both models resident and repeatedly used a retained historical frame. The candidate was faster in 29 of 40 pairs, with a 6.19% reduction in the two arms' medians. The median paired difference was -11.79 ms, but call order mattered: -19.53 ms when the original ran first versus -3.34 ms when the candidate ran first. All 80 measured calls exceeded 50 ms and the scheduler skipped 232 release slots. The accepted result establishes a modest improvement for this offline workload; live latency and 20 Hz remain unproven. Local closed evidence is `artifacts/research/2026-10-24/native-p2p-v15-namespace-routing-v5-closed-audit-01/audit.json` (SHA256 `9c6db6bf07514b1565eaf3d67411d8cdf7de314d2f549e0e8ab14ad66eafdba8`).

A later single profiled warm prediction took 169.49 ms. Its accepted trace contains 5,438 graph-linked kernels and 37 device copies; fused memory-efficient attention is already active. A few long recorded events and gaps dominate the totals, so they cannot be treated as proven optimization savings or attributed to a specific cause. The model processes exited and their retirement was independently confirmed.

A separate read-only sample at 23:15:42 UTC reported active software thermal clock limiting, 88 C, a 990 MHz core clock and 96% device utilization after the model worker exited. This observation describes that sample; it does not isolate the cause of earlier prediction latency.

## Startup validation

The native-history feedback validation used the original sampler, history41 and the retained images/goal. It checked rejection and retry at empty history, the last growing-history step, the first full-history graph and an existing graph, followed by reset. The accepted audit joins actions, CPU/CUDA random states, indices, retained state evidence, cleanup and the three independently observed worker identities. This establishes offline model-state behavior; it does not establish live input delivery, task quality, startup speed or bridge integration. Local evidence is in `artifacts/research/2026-10-24/native-p2p-native-history-feedback-execution-v2-closed-audit-01/audit.json` (SHA256 `84f4770eacf95b2ac32be2acbe4af6124d469a7319ec76c7924c4ed0afb6fcbd`).

A separate two-prefix experiment captured graphs that grow native history from 0 to 12 and from 12 to 24 tokens while preserving the native sampler. Its closed reader independently recomputed 192 checks over four public calls, eight state records and 58 CPU/CUDA RNG arrays, with zero maximum recorded numerical difference. The scoped capture correction was restored and all three experiment processes retired. This qualifies the two tested prefixes; it does not establish all 41 startup positions, rejection handling with these graphs, or a latency distribution. Local evidence is `artifacts/research/2026-10-24/native-p2p-two-prefix-v3-run001-closed-audit-01.json` (SHA256 `5d9f73c7d449b9f69d846100a3d296ff1fbbeeee3201871561a1a7c128e22abe`).

The earlier history200 control run used 15 Hz and a 150 ms observation-age limit. All 200 eager predictions were withheld as `modelMissedDecisionBudget`; its subsequent graph phase accepted 40 actions. That runner advanced model history through withheld predictions. The new native-history candidate rolls back known rejected proposals, so repeated slow startup calls can prevent it from reaching graph-ready history. Preparing a full-history graph in advance does not accelerate the preceding 41 growing-history steps. The exact current candidate's startup cost is still unmeasured.

The existing masked fast-start cache stores explicit empty-history validity, but its historical 205-step comparison used different, tensor-wide error metrics. A later strict history41 comparison failed when padded attention used a different physical width from the original. Packing the active data contiguously passed the tested eager comparisons; it does not establish a single fixed graph for every growing prefix. The eager and graph paths also use different sampling methods, so comparisons with shared supplied uniforms do not prove equivalent native public prediction and RNG behavior.

The dormant-graph candidate now runs the same model and history checks after a failed capture as after a successful capture. Replacing committed history before a capture error poisons the owner. The corrected source passed 38 isolated tests and independent review; it has not been enabled for live control.

## Next steps

The integrated queued-successor v2 separates software application from final
terminal reconciliation. It can publish the first history and prepare one
successor while retaining the unresolved predecessor; the successor cannot
publish until that predecessor reconciles. The controller admits one immutable
successor at the original 50 ms boundary, and a healthy handoff retains common
held keys. Missing, expired or uncertain successors close the chain without
renewing frame or action deadlines. The current bounded experiment retains at
most 32 records; sustained operation and rearming are not qualified. The
checkpoint scope remains optional, and all activation flags remain false.

The initial v1 port passed one guarded CPU execution: 51 owner, 43 checkpoint-scope, 11 source
admission, 33 Bridge, seven prewrite and five harness cases, with no failures or
errors. The tests used fake numerical operands, retained their capacity evidence
and left all selected input pins unchanged. They do not establish real checkpoint
loading, CUDA equivalence or model/controller latency. The 24 changed payloads
were installed byte for byte; explicit LF attributes preserve the adapter/loader
source guards across checkout. Local evidence is
`artifacts/research/2026-10-24/native-p2p-step-application-primary-port-candidate-03/checks/cpu01/receipt.json`
(SHA256 `a59cda68d122786d3522cdfd585532d63072ab0414beabf074c183e82e198ce7`)
and the installation record
`artifacts/research/2026-10-24/native-p2p-step-application-primary-port-root-01/application-01.json`
(SHA256 `35700e6c2218edf986750aa29cfc0a9d8675e191f239248de621d1f93fc5534a`).

The earlier receipt-bound native owner serializes terminal completion, history
commit and the next prediction. The controller calls `ReleaseAll` before queuing
the terminal receipt, whereas its valid replacement path can retain common held
keys. Preloading graphs alone cannot remove this sequencing boundary. This is a
source finding about software call order, not proof of physical key release or a
measured gap. The independent review is
`artifacts/research/2026-10-24/controller-continuity-source-independent-review-01/review-01.json`
(SHA256 `fabe3a163e43ae8be53abc5b6d689ae427aad197782ea919c33513e0740ed622`).

The protocol separates complete software step-application evidence
from ongoing call telemetry and terminal receipts. Any earlier history commit
needs its own ownership, duplicate, failure and late-receipt rules. The present
native owner still requires an unchanged 50 ms step. The existing client hold
option permits 33–100 ms, and the server permits one to six such intervals with a
250 ms total horizon; a single 250 ms interval is not supported. Longer held input
would require an explicit resampling contract and game-quality evaluation, with
the native action and mouse delta preserved in the evidence. These are design
requirements, not enabled behavior or a demonstrated latency solution.

The reviewed design gives complete software input-call coverage a separate,
versioned acknowledgment. It requires exact decision/step identities, a reserved
immutable result queue, contiguous acknowledgments, whole-batch validation and
separate history publication. Terminal contradictions stop the owner. These
receipts describe software calls, without claiming OS delivery or game effects.
The design selected 60 ms as a conservative initial post-input observation-delay
target. It is not an implemented delay in the current stream or native binding.
If enforced before successor inference, it would already exceed the native 50 ms
interval at zero compute. Current capture runs independently at 30 Hz; a new
frame ID and a maximum-age check do not prove acquisition after an application.
The prototype therefore still needs an explicit observation/dispatch timing
contract and measurement before any continuous-feedback claim.
The design review is
`artifacts/research/2026-10-24/continuous-step-application-contract-independent-review-01/review-01.json`
(SHA256 `d9ad5d41c3db8514b1671012adc1451184d67c378606a34fabb62c915f68cde3`).
Its earlier existing-delay wording is corrected by the source-bound clarification
`artifacts/research/2026-10-24/step-application-observation-delay-clarification-01/clarification-01.json`
(SHA256 `627e4c81f4931cc8638c64939b7f5c7094c9bad4bdf8dc297e26b734e78a85da`).

The protocol correction rejects DEL before reserving reply bytes and requires
the exact completed-record prefix before any client mutation. Both old failure
cases were reproduced against the prior bodies; 24 focused methods have passing
evidence. The unchanged 53-case evidence remains source-bound. The correction
review is
`artifacts/research/2026-10-24/step-application-protocol-ledger-correction-independent-review-02/review-01.json`
(SHA256 `06f494035500e726a9317a1a37188547ee7eed2894a49248d0272802b8f92e02`).
Controller instrumentation, reliable transport acknowledgment and native-owner
commit integration are not yet deployed.

The current milestone joins each image with the controller evidence known before
the next decision. The client now records proposals, admissions and terminal
receipts separately, retains their originating goal, and excludes evidence that
arrives during inference. Optional GameScaling text is bounded to 2,048 bytes and
records the exact consumed text hash. The integrated cohort passed 121 distinct
tests (134 executions, including 13 repeated imported fixture cases). Local
evidence is `artifacts/research/2026-10-24/execution-context-primary-integration-01/tests-01/receipt.json`
(SHA256 `6f377f57b910ab4ad8cd0815ed65609594f4f648d33b013a95083d5878a2cb1a`).
The capability-gated ongoing-input client is also integrated. It retains reported
call starts, returns and failures separately from active intentions and software
tracked keys. Its bounded projection preserves the latest reported call before
older calls or verbose intention data, while keeping the existing receipt and
clock qualifications. A portable legacy fixture checks exact snapshot and text
bytes for the retained capability-absent case. All 103 focused tests passed
against the actual primary modules under model, native, process and network
guards. Local evidence is
`artifacts/research/2026-10-24/ongoing-input-context-primary-validation-01/receipt.json`
(SHA256 `16e7f9e058f6249850adc26409ba7afacd2cb5f0fb639dbfe9f4c1f03d73d036`).
At that client-only checkpoint the C# producer was uncompiled. It subsequently
passed the R46 validation and was deployed as described below; these client tests
alone do not establish physical input state.

The live collector now has one completed software-reported LBUTTON step, a frozen
640x360 pre-command image, and exact before/after receipt contexts. Every published
file was checked; release/stop and idle input-off were reported, and an independent
Windows process snapshot confirmed the collector subtree was gone. Public-ledger
replay reproduced both context files byte for byte. Local closed evidence is
`artifacts/research/2026-10-24/execution-context-live-probe-02/run-002-root-audit/audit-01.json`
(SHA256 `5942e5e5ef1a0cb012215c7388bf049542c97dc64e2c1bd52a738b0a4ea7d2a7`).

Two earlier traces remain explicit negative cases: one stopped before dispatch on
source age, and one was admitted but cancelled before its first step. Buffering
bulk evidence until cleanup reduced the measured intake-to-context span from
47.64 ms in the first collector to 2.22 and 3.11 ms in the later runs. These are
individual observations, not a controlled latency distribution. The unchanged
second collector's server receipt-to-acceptance timestamp interval was 32.39 ms
in its cancelled run and 0.26 ms in its successful run. The acceptance timestamp
precedes the final availability check and queue installation; the evidence does
not attribute the variation to a particular operation.

Source review confirms LBUTTON uses Windows mouse events with an insertion-count
check. The completed receipt still does not establish game consumption, ongoing
holds or successful per-key release. Both retained images show the normal game
world; the later capture began only 14.49 ms after the terminal timestamp and does
not independently confirm an attack effect.

The first offline model attempt stopped during runtime import when its subprocess
guard raised an error. It loaded no model, produced no predictions and reached no
CUDA capacity reading. The owned job retired and an independent Windows query
confirmed all three process identities were absent. Local failure closure is
`artifacts/research/2026-10-24/execution-context-model-probe-03/root-launch-01/failure-closure-01.json`
(SHA256 `e9d69e868ec0dc359717226c4788a792701ae8f551a23304449ecabd41c3e866`).
The corrected guard still denied every child process, but gave the three exact,
source-pinned Windows version probes an error type handled by Python's existing
native-version fallback. Its 21 focused tests passed. The next run recorded those
three denials, no unexpected subprocess denial and no diagnostic failure.

The closed GameScaling comparison used the identical pre-command image in
before/after/after/before context order. All four outputs were complete, valid
neutral actions, so the requested attack-before / neutral-after behavior was not
demonstrated. Both context text hashes were verified at model consumption; context
delivery alone does not establish that the model used the receipt correctly.
The run stayed within its unchanged allocator and time limits, drained CUDA work,
and retired all three independently observed process identities. None of its
outputs was executed. Local closed evidence is
`artifacts/research/2026-10-24/execution-context-model-probe-04/closed-audit-01/audit.json`
(SHA256 `47dd5d0d0cc6e6b2fb31fc532a1e5a39833030385e6bc2989dfb37d2db770fa7`).

A simpler control used the same image and the unconditional instruction "Attack
once using LB, then stay still. Do not move or turn the camera." It made exactly
two ordinary public calls, first without execution context and then with the
retained empty-before context. Both returned the identical complete 30-token
neutral action. Their prompts contained 840 and 1,105 tokens respectively; the
actual messages, input/output IDs and restored observation bindings were retained.
The closed reader accepted both observations, and all three processes retired.
Receipt JSON alone therefore does not explain the neutral response on this frame.
This single-image control does not establish general task quality. Instrumented
call durations were 14,792.67 and 15,785.81 ms; this was not a latency comparison.
No output was executed. Local evidence is
`artifacts/research/2026-10-24/execution-context-gamescaling-quality-control-01/closed-audit-01/audit.json`
(SHA256 `9c09e49b891d0930838bcf5bc5642ea31734eef316e705eb7b0c4b83f64a1641`).

The GameScaling decoder now resets its complete-action validation count whenever
it creates a new cache. Previously, a larger cache inherited earlier successful
checks. Eight guarded orchestration cases passed against the exact primary file,
covering growth, reuse, mismatches and reference failures without loading a model.
Local evidence is `artifacts/research/2026-10-24/gamescaling-primary-validation-01/receipt.json`
(SHA256 `0464ec3baeb4fa215918f85d19f2ad440f938c50c3676d3d8a8d8695c5364997`).

A separate grouped-decoding candidate transfers up to four greedy token IDs per
GPU-to-CPU synchronization. Its original 27 guarded cases passed. Review found
that a later prefill failure could retain the previous successful attempt's
receipt; the correction passed 10 focused cases and source review. The numerical
token loop is unchanged by that correction. The assembly then passed 28 guarded
cases and independent review before a bounded seven-call GPU comparison.

The comparison used one model/cache owner, three excluded setup calls and two
balanced pairs. Both arms returned the exact same complete 30-token neutral
action, with unchanged CPU/CUDA generator bytes. Measured full public-call times
on this shared machine were:

| Context | Original graph decoder | Grouped decoder | Grouped minus original |
| --- | ---: | ---: | ---: |
| Before receipt | 4,787.04 ms | 4,965.98 ms | +178.93 ms |
| After receipt | 5,281.69 ms | 5,522.95 ms | +241.26 ms |

Grouping was slower in both observations and is not being integrated. Each
grouped call performed 32 decode replays versus 29 for the original, including
three discarded steps after EOS. This does not isolate the cost of those steps
or establish a general speed difference. Numerical reset checks were limited to
excluded setup; measured calls retained actual reset/pointer evidence and exact
returned-ID comparisons. All three owned processes retired, and no output was
executed. Local closed evidence is
`artifacts/research/2026-10-24/execution-context-gamescaling-grouped-comparison-assembly-01/closed-audit-01/audit.json`
(SHA256 `355e7bc4c4af245d2703d22501f511782dfd323151f1e8a52f6d370e286ff649`).

P2P's corrected receipt owner now uses the actual string `ownerEpoch` and keeps
wire identity separate from local control, goal and readiness epochs. Its 46
focused tests and renewed source review passed; the earlier clearance remains
withdrawn. The reviewed numerical plan uses one original-first model, compares
43 receipt commits against complete original predictions, tests known rejection
and local cancellation rollback, and ends with an unresolved proposal that must
remain quarantined. The completed harness passed an additional 46 guarded cases,
including its complete 95-archive reader and maximum-capacity fixture, then passed
independent source review. Its owned runtime assembly passed 23 new guarded
cases. A correction to bind the loader's actual detached method namespace passed
23 focused cases and independent review before the completed numerical run.

That run used one eager FP16 model with history 41, the unchanged native sampler
and mouse decoder, and no input authority. It completed 44 original reference
calls, 48 candidate proposals and 43 commits from scripted completion receipts.
Two rejections and two local cancellations restored the predecessor and generator
state; the final unresolved proposal remained quarantined without a commit.
The independent reader reconstructed all 860 full cache-state comparisons from
the saved evidence: every comparison was byte-exact, with zero absolute error.
All three owned processes retired, and the final runtime audit accepted the
source, numerical and retirement evidence. This establishes offline receipt
semantics; live response time, physical input and game effects remain unverified.
Local closed evidence is
`artifacts/research/2026-10-24/native-p2p-receipt-commit-execution-02-closed-audit/audit.json`
(SHA256 `711637467dad8a6b4c2aa0ef9c65fda51bc666b32c8377b044b4b078db76583b`).

The bounded R45 runner passed 36 isolated worker, cleanup and publication cases.
Review then found two errors in its saved-results checker: a prior receipt could
be associated with a later proposal, and a cyclic process-parent chain could be
accepted. A harmless RDP diagnostic also exposed two launch integration issues:
the broker requires path strings, and the ordinary RDP worker cannot query the
desktop host's native process creation time across Windows logon sessions.
The correction verifies the host process in the desktop parent and verifies
BetterGI and Genshin locally in the RDP worker, while retaining authenticated
host status checks. All four corrections passed 32 focused cases and independent
source review. The model, native sampler, receipt owner and consumer sources
remain unchanged. Local review is
`artifacts/research/2026-10-24/native-p2p-r45-receipt-worker-independent-review-02/review-02.json`
(SHA256 `cee4916d4210bf26a6d30a5cfed4bc65e1d6a1544cf4171ad32473cf3029a120`).

A separate input-free probe confirmed that the desktop can read the exact native
identities of the ordinary RDP broker, launcher and interpreter, despite the
protected app-process restrictions. All three probe processes retired. The
independent trial observer passed 20 isolated cases and four reviewer checks;
it joins exact commands and parent IDs to native creation ticks, confirms the
same identities, then checks late absence of only those captured PIDs. Its
source review is
`artifacts/research/2026-10-24/native-p2p-r45-os-observer-independent-review-01/review-01.json`
(SHA256 `46154e65e93d98d9bc9e95baa001b392ac0d91a6d69f708396006a273d773cd6`).
The corrected runtime assembly then passed its full 8,626-file dependency check
and ran once in the existing minimized RDP session. The first actual RGB192
observation showed the game world. Its complete public proposal took 1,825.44 ms
(1,801.45 ms inside preparation), producing a neutral 50 ms proposal. The unchanged
50 ms compute limit rejected it before submission; observation age at that check
was 1,895.48 ms. There were zero admissions, zero software-completed actions and
no committed policy history. Release/stop returned, all three independently
observed worker processes exited, and the final runtime audit passed. This single
first-call diagnostic establishes the live integration and rejection path, not
steady latency or gameplay quality. Local closed evidence is
`artifacts/research/2026-10-24/native-p2p-r45-receipt-worker-execution-02/closed-audit-01/audit.json`
(SHA256 `8664517b6c4645965c4eb0d4a7c8aaf1ae8ef11893c153589df4a631f620fc30`).

A subsequent 640x360 observation showed the normal game world and HUD. Its first
frame still reported `world_confirming`, so it was retained as diagnostic imagery
with input disabled. Stream shutdown and independent process retirement were
confirmed. Local image evidence is
`artifacts/research/2026-10-24/r45-clean-observation-helper-02/run-001/frame.png`
(SHA256 `e12a534d80b265dc880446bf27e896d4bc8465e12f88cca4a361dfcd52b6dfe0`).

The input-contract audit found that official P2P keyboard ID19 decodes to
`RSHIFT`, which BetterGI's allowed-key list omitted. Its existing input parser
already supports `VK_RSHIFT`. The primary C# source now adds exactly that key;
the hello capability and request validator use the same list. Trial-key and
reserved-key restrictions remain effective. The ten-byte change passed
independent source review and exact byte comparison, but is not compiled or
deployed. It does not explain the earlier neutral proposal, whose raw key IDs
were all zero. Local review is
`artifacts/research/2026-10-24/agent-rshift-capability-independent-review-01/review-01.json`
(SHA256 `524afd518a1ee47d6a9478e3c6831743d3a8349e244f3d3bc562a59d374a0f4f`).

Saved timing intervals from the accepted eager correctness run give proposal
wall median 829.20 ms across 48 calls and receipt-commit median 325.79 ms across
43 calls. These include native computation, decoding and transaction checks;
they are not GPU kernel timings or a balanced performance comparison. Numerical
archive writes occur outside those intervals. Removing report writing therefore
does not directly subtract its duration from the recorded proposal interval.
The source-boundary analysis is
`artifacts/research/2026-10-24/native-p2p-receipt-commit-eager-timing-analysis-01/ASSESSMENT.md`
(SHA256 `6fa8db84964f1b0d39e29b2d2a12c7216ecced63e0ab4ef50cfc8a0c6903aa14`).

A private first-step G12 prepare/commit graph pair passed 42 distinct isolated
cases and independent source review. It retains the original native sampler,
CPU mouse decoder and receipt authority, uses separate private graph pools,
restores generators after setup and rejection, and copies committed state before
retiring graph storage. This covers the genuine empty-history first step only.
The numerical worker, complete report fixture and independent numerical reader
are now source-reviewed. A cleanup correction preserves pending, poisoned and
partially constructed graph owners until process retirement, while healthy
cleanup uses the inherited lifecycle guard; 33 focused cases passed. The corrected
qualification source passed independent review. Its runtime assembly passed the
full 8,763-file check and ran once in RDP. The first attempt stopped during the
second warmup at `observed_operand_layout`, before graph capture or proposals.
The inventory expected FP32 for text, thinking and output-token tensors, whereas
all 48 retained eager pending records identify those three tensors as FP16;
the image prefix is FP32. A fresh correction preserves those actual formats.
Parent and worker final source checks passed, and an independent query confirmed
all three ordinary RDP processes had exited. The standalone numerical reader
rejected the incomplete runtime envelope. That attempt supplies no split-graph
numerical or latency acceptance. The failed attempt and closure remain preserved:
`artifacts/research/2026-10-24/native-p2p-g12-execution-01-failure-summary-01.json`
(SHA256 `daa162fe74250d883ad2daccca72b8d9dcc3e1dfe2fdbaade07d2cb8e0a035d6`).
Local source review is
`artifacts/research/2026-10-24/native-p2p-g12-receipt-graph-independent-review-01/review-01.json`
(SHA256 `e945f4f103c640d9c080308248ea750fc9fc496aa18d075be0f1b1db96e26f7b`).

The corrected execution02 then passed its full 8,788-file preflight and ran once
in minimized RDP. The independent closed reader accepted all 157 actual-array
gates, each with zero recorded absolute error, together with generator, public
action and committed-history checks. Three same-prefix proposals exercised local
discard, known rejection and one scripted completed receipt. Both graphs retired
cleanly, and all three independently observed processes exited. No game input
was sent. Complete proposal wall times were 196.77, 210.49 and 212.82 ms; the
receipt path took 95.76 ms. These descriptive correctness-run timings exceed
the 50 ms decision budget and do not establish a controlled speedup or steady
performance. Local closed evidence is
`artifacts/research/2026-10-24/native-p2p-g12-receipt-graph-execution-02/closed-audit-01/audit.json`
(SHA256 `e9ce0e054b121c7e62deb8fbc2c4aecd084026c55bff33ff7706bbc4a3378c10`).

The subsequent G24 experiment passed all 356 independently recomputed numerical
gates with zero recorded absolute error. The second graph starts from the first
graph's actual committed objects and completion-time RNG checkpoint. Six
proposals cover local discard, known
rejection and one synthetic completed receipt at each prefix. All 40 committed
K/V leaves, raw actions, public output, generator states and retained first-step
objects passed their checks. All four graphs retired and the three independently
observed processes exited. This remains an offline test with no game input.
Local closed evidence is
`artifacts/research/2026-10-24/native-p2p-g24-receipt-graph-execution-01/closed-audit-01/audit.json`
(SHA256 `cce78a6f6b8afb9ac8e633871a0c80453be4845582b8beeced50511587dbbd15`).

In that correctness run, complete first-step proposals took 176.49–190.59 ms;
second-step proposals took 223.49–252.51 ms. Receipt calls took 98.96 and 96.77 ms.
The first setup interval was 3,007.88 ms and the continuation handoff, including
the second graph setup, took 3,981.18 ms. The setup pause remains a concrete
obstacle to continuous control. These are descriptive intervals from one
correctness run, not a controlled speedup or steady-state distribution.

The following G36 experiment extended this to three consecutive prefixes. It
passed all 534 independently recomputed numerical gates with zero recorded
absolute error, including all 60 committed K/V leaves and actual C0/C1 predecessor
provenance. Nine proposals cover one local discard, one known rejection and one
synthetic completed receipt at each prefix. All six graphs and the three
independently observed model processes retired; the final artifact census also
passed. No output was sent to the game. Local closed evidence is
`artifacts/research/2026-10-24/native-p2p-g36-receipt-graph-execution-02/closed-audit-01/audit.json`
(SHA256 `8dd6842f2afc6e5e35607effe0777e076fd4227acb8a5dd22b108e3365de53f1`),
with mandatory final closure
`artifacts/research/2026-10-24/native-p2p-g36-receipt-graph-execution-02/root-orchestration-01/json-reserve-closure.json`
(SHA256 `175fd48917847feeda3cdc36185fbcfff011bf17eda1d1590be960f1bf402223`).

That run's initial graph setup took 3,301.52 ms. The two continuation handoffs
took 4,082.36 and 5,088.75 ms. Proposal ranges were 162.23–190.39 ms at G12,
206.08–523.99 ms at G24 and 207.90–239.98 ms at G36. Every measured proposal
exceeded 50 ms. These are descriptive correctness-run intervals under shared
machine load; the result qualifies the tested history transitions, not steady
speed or live action quality. Preparing graphs before they are needed remains
the next change for the multi-second handoff pauses.

The separate pending-tensor batching optimization also passed its actual CUDA
byte checks: five batches, 155 tensor occurrences, 42,118 reference bytes and
20 unchanged CPU/CUDA RNG arrays. The first-prefix inventory has 13 nonempty
occurrences totaling 10,464 bytes; the earlier all-FP32 fixture's 16,608 bytes
are not an observed native inventory. The first outer reader rejected the run
because it compared the proposals' actual empty predecessor objects with setup
scratch objects. A reviewed correction retains full object, pointer, storage and
byte checks while joining those entries to their actual predecessor. Sixteen
focused cases passed, including the saved run and altered-identity negatives.
A fresh CPU re-audit then repeated the full original 9,127-file verification,
all 157 original numerical gates and independent process-closure checks. It
accepted the same immutable GPU run; the initial failure remains preserved.
Local corrected evidence is
`artifacts/research/2026-10-24/native-p2p-pending-materialization-execution-02-corrected-audit-01/audit.json`
(SHA256 `f600d2bad738ebf98e2c85958fcb44f5e35d676f67373eba666444088c6eed44`).

The transfer comparison then completed eight fresh graph-pair lifetimes in two
order-reversed blocks. Its closed reader accepted 1,368 actual-array checks with
zero recorded error across 24 public proposals and eight synthetic receipts.
All observed model processes exited, all four orchestration commands retained
certain and complete outcomes, and the final artifact census passed. No game
input was sent.

| Call order | Original proposal mean | Packed proposal mean | Packed minus original |
| --- | ---: | ---: | ---: |
| B0, P0 | 166.35 ms | 194.52 ms | +28.17 ms |
| P1, B1 | 185.31 ms | 176.17 ms | -9.15 ms |
| P2, B2 | 195.56 ms | 194.13 ms | -1.43 ms |
| B3, P3 | 189.03 ms | 178.10 ms | -10.93 ms |

Each mean contains three repeated calls within one lifetime; there are four
matched lifetime pairs. Packed transfer won three pairs, but its overall proposal
mean was about 185.73 ms versus 184.06 ms, and all four receipt calls were slower.
Receipt medians were 100.89 ms packed versus 91.46 ms original. This does not
establish a reliable speed improvement, so the existing transfer path remains
the basis for continuation work. No percentile, continuous gameplay rate or
action-quality claim follows from this comparison. Local accepted evidence is
`artifacts/research/2026-10-24/native-p2p-pending-materialization-latency-execution-03/closed-audit-01/audit.json`
(SHA256 `2c7febcbc7132e4df5410b13aa3b39668f1b2b56724878efc57afaf248882e19`),
with mandatory final closure
`artifacts/research/2026-10-24/native-p2p-pending-materialization-latency-execution-03/root-orchestration-01/json-reserve-closure.json`
(SHA256 `ca6ce358b90a9b9adbebbac74a3da520ebb56fb584966c33c675f71378f2c5be`).
The separate descriptive summary retains all 16 paired intervals and excluded
setup/reset/close/archive times:
`artifacts/research/2026-10-24/native-p2p-pending-materialization-latency-execution-03-summary-01/summary.json`
(SHA256 `fbfe116ea5ccf8af55542e4eec97920a56ddcae8018f1a02f91121ac586b11c2`).

Coverage beyond the first two preloaded prefixes and rolling eviction remain
unqualified. The dormant two-prefix reader's initial-state identity join was
corrected before execution. Its first actual run produced all 21 expected
archives, then failed report validation because graph-pool identities retained
tuples where the schema requires lists. No numerical report was published or
accepted. All three observed worker identities retired; backend cleanup was not
published. The failed run and finalizer refusal are retained at
`artifacts/research/2026-10-24/native-p2p-dormant-two-prefix-execution-01-failure-closure-01/failure-closure.json`
(SHA256 `2f756b07b5587ed9566611adc33875b46f6cacf409d749277a2896a4032524e6`).

The recorder now uses the same detached pool-list representation as the existing
setup recorder. Ten focused inert cases passed, including reproduction with the
old producer and acceptance of the corrected producer through the unchanged
complete 21-archive, 356-gate fixture reader. The independent source review is
`artifacts/research/2026-10-24/native-p2p-dormant-bank-identity-serialization-independent-review-01/review-01.json`
(SHA256 `bf863047c4879c894fe9f82b23dad03159a172d52582e815afd25e1d0b46afc8`).
The corrected second run passed all 356 numerical checks with zero recorded
error, including 40 committed K/V leaves, six proposals, two local discards, two
known rejections and two synthetic receipt commits. All four private graphs were
prepared before the first candidate image. Activation added no capture/replay,
decoding or RNG restore in the retained counters. Worker cleanup, independent
three-role process retirement and the final output-capacity closure passed.

This instrumented run recorded 6,906.60 ms of preloading and a 329.92 ms handoff.
First-graph retirement occupied 169.39 ms and activation binding 139.46 ms.
The six public proposals took 193.29–248.09 ms; the two receipt calls took 130.40
and 151.18 ms. These are single-run diagnostics, not a controlled speed
comparison. The two-prefix bank does not establish all 41 prefixes, rolling
eviction or continuous live gameplay. The accepted audit is
`artifacts/research/2026-10-24/native-p2p-dormant-two-prefix-execution-02/closed-audit-01/audit.json`
(SHA256 `0b4969c2748f6dac7631a8acf3e02f78b7c008f741a2f68d11a3aedf5a2cbdc0`).

A third run changed only graph retirement's unconditional garbage collection:
collection now runs when an original graph weak reference remains alive, while
the existing synchronization and final retirement checks stay in place. All
356 numerical gates again passed with zero recorded error, including all 40
committed K/V leaves. Preloading took 7,309.44 ms, first/final graph retirement
took 10.49/19.76 ms, and handoff took 173.11 ms. These separate instrumented runs
had uncontrolled machine load; they do not establish a controlled speedup or
end-to-end gameplay latency.

The four required commands, closed audit and finalizer passed, and all three
worker identities retired. The retained summary also records an initial invalid
root CLI mode and the corrected observer starting after the parent; no numerical
worker was repeated. The accepted audit is
`artifacts/research/2026-10-24/native-p2p-dormant-two-prefix-execution-03/closed-audit-01/audit.json`
(SHA256 `f74ddc258276c64367cc36ea3e9c87335ac3946f322e28a242b90b62a362e450`).
The checked two-run summary is
`artifacts/research/2026-10-24/native-p2p-retirement-fastpath-results-01/summary-01.json`
(SHA256 `4396caea3dc2375bd6738e229a010108ff7cbd8a93b63c075bb498bf44d1cce3`).

The first paired Q/K qualification run stopped before its first prediction:
compiling only a class produced different Python bytecode from compiling its
complete module. The worker's cleanup completed and all three observed worker
identities retired. The actual parent and audit commands exited with code 1;
the mandatory finalizer also failed because no accepted audit existed. This
remains a failed numerical run, preserved at
`artifacts/research/2026-10-24/native-p2p-paired-qk-qualification-execution-01-failure-closure-01/failure-closure.json`
(SHA256 `df3bb2a4104f06d2b66f13cd421b6fef6ff4d5548727010a4f8bb68cd442e3c7`).

The correction changes only the compilation input to the complete module AST;
it executes none of that module and retains the exact method-code comparison.
Fifteen distinct focused inert cases passed, including independent full-module
fixtures and code-drift rejection. The independent source review is
`artifacts/research/2026-10-24/native-p2p-paired-qk-qualification-independent-review-02/review-01.json`
(SHA256 `f0e40c5d6197e8c901690296f52e3609e8ba25d32c44b1c42a2207cbf3f7d983`).
The second Q/K run passed that code qualification but stopped at the context
observer: native `torch.device('cuda')` scopes push a `DeviceContext` directly,
without updating the Python marker the observer used. The worker reported
complete cleanup and all three observed worker identities retired. There were
no completed comparison cases or archives. This failed run is preserved at
`artifacts/research/2026-10-24/native-p2p-paired-qk-qualification-execution-02-failure-closure-01/failure-closure.json`
(SHA256 `e2bd5be45aa35312a9d20ff77f3591a2f29b50e9fe2d4fd9b202cf64f40e6c38`).

The corrected observer reads the effective stock native device mode while
retaining the inference, autocast and device requirements. Twenty-four focused
inert cases and independent source review passed. The review is
`artifacts/research/2026-10-24/native-p2p-paired-qk-context-observation-correction-independent-review-01/review-01.json`
(SHA256 `8a360dbcb2c0e69ca4a10dc3eb8869587be7a31f05779c5dba31cdc8aa91589f`).
The third Q/K run passed 188 numerical gates across all 47 actual operand
samples, with 50 retained archives and 97 RNG checkpoints. Sixteen gates had
nonzero error; maximum absolute error was 0.001953125 and the largest fraction
of the declared tolerance was 0.7100. This is a local component pass rather than
bitwise equality. The original reference used one public prediction; the
candidate helper was exercised separately. Full native prediction, accumulated
history/action parity, kernel reduction and latency remain unverified.
Both source scopes and profiler were restored, cleanup completed, all three
observed worker identities retired and the final output-capacity closure passed.
The accepted audit is
`artifacts/research/2026-10-24/native-p2p-paired-qk-qualification-execution-03/closed-audit-01/audit.json`
(SHA256 `fcf285992bd6a21a54d867a8848b939c4d9e953b3695b7dd6fb0d72b9ac7f603`).

The combined numerical/timing summary, including both final closure pins, is
`artifacts/research/2026-10-24/native-p2p-qk-and-dormant-results-01/summary-01.json`
(SHA256 `f4023abdb7d11e76ec4d7364ec8f6de78fae9c30108a28eaf824ee3a5ab5fc9f`).

Fixed attention-mask reuse now has a source-only integration with the actual G12
graph pair and receipt owner. Both graphs are registered before capture, and
their retirement precedes releasing the mask storage. Review found the same
kind of device-observation defect in its global-default getter. The narrow
correction passed 24 focused inert cases and independent source review at
`artifacts/research/2026-10-24/native-p2p-fixed-mask-native-context-correction-independent-review-01/review-01.json`
(SHA256 `2b4ad78221d3ad7b81cab7cdceacc478de4f6d3d0b36e95531528bba9bbcabb3`).
Its numerical plan now distinguishes actual constructor-return bytes from scalar
expectations and compares storage aliases only across overlapping lifetimes.
The corrected plan passed review at
`artifacts/research/2026-10-24/native-p2p-fixed-mask-qualification-plan-independent-review-02/review-01.json`
(SHA256 `4ea4f34500a38a6dc2bea18958fad1ab667dddd733f7281a20dcf30878e40dcd`).
The qualification source and complete fixtures passed independent review:
47 distinct inert cases, 12 retained archive fixtures, 440 arrays and 267
numerical gates. The first runtime assembly review found a missing required
preimage file; a fresh corrected assembly passed review. The actual GPU run then
passed all 267 numerical checks with zero observed differences, retaining 12
archives, 440 arrays and 46 CPU/CUDA RNG arrays. It exercised three proposals,
one local discard, one rejection and one synthetic software-receipt commit.
Both captured graphs and all ten fixed masks retired, all three observed worker
identities retired, and all four orchestration commands plus final capacity
closure completed successfully. This qualifies the tested G12 case; other
prefixes, latency benefit and live control remain unqualified. The source review is
`artifacts/research/2026-10-24/native-p2p-fixed-mask-qualification-independent-review-01/review-01.json`
(SHA256 `ca7c513a482ebdeb2cc5de1add7ef6c2c31038aba6836e8190fd2dbb0e70326f`).
The accepted result summary is
`artifacts/research/2026-10-24/native-p2p-fixed-mask-results-01/summary-01.json`
(SHA256 `4d66201ea5c76ab7400104f9aaec6f590c80c2b5c9ce2a6501f451d40214f814`).
Its 61 read-only GPU samples reported 87–88 C, 92–97% utilization,
795–1,215 MHz SM clocks and active software thermal limiting. The samples cover
only part of the parent process window and do not establish per-call causes or
a controlled speed comparison.

During the transfer trial, all 78 read-only GPU queries succeeded. They reported
88 C, 91–97% device utilization, 1,035–1,305 MHz SM clocks and active software
thermal clock limiting. The samples overlap only three of the eight short
lifetime call spans and do not establish per-call causes or unloaded latency.
P2P remains the main path
toward continuous gameplay while GameScaling's speed and instruction response
are evaluated separately. Source research also found
no verified supported FLA installation for this unchanged Windows, SM7.5 and
Torch 2.7.1 stack; no package change has been made. Learned task quality, constant
gameplay and expert training labels remain unqualified.

The newly approved one-time restore from the [official NuGet source](https://api.nuget.org/v3/index.json) passed normal approval review and completed with SDK exit code 0 at 14:32:33 UTC on October 25. `BetterGI.Assets.Map` 1.0.25, `BetterGI.Assets.Model` 1.0.39 and `BetterGI.Assets.Other` 1.0.28 are now present. Persistent NuGet configuration and all source11 pins remained unchanged.

An extra wrapper check initially compared the raw signed archive SHA512 to NuGet's signature-excluded content hash. That was a verifier error: the [NuGet metadata format](https://github.com/NuGet/Home/wiki/Nupkg-Metadata-File) defines different hashes. A separate read-only correction verified all three raw archive hashes, package identities, official source metadata and content-hash joins to the restored project libraries. The original outcome remains preserved; no second restore or download occurred. Corrected verification is
`artifacts/research/2026-10-24/official-nuget-restore-20261025-01/verification-02.json`
(SHA256 `519527206a9da686cfc723fdb7bb8a6843223c89b67005663f4b7f1d12c90fe1`).

The fresh source12 packet then passed all 1,860 selected C# tests, including the
26 new ongoing-input telemetry cases, and both the required Debug solution build
and isolated self-contained Release publish. Its 1,749 source files remained
unchanged through validation. The completed test evidence is
`artifacts/research/2026-10-24/desktop-dc-csharp-12-validation.json`
(SHA256 `3b03e6b8c6ab097fa1dd5bcd2805f7e13b0debd3dfeea238571f2aa86881e36b`).
The R46 publish is at `artifacts/release-r46/BetterGI-English-win-x64`; its
manifest SHA256 is `b428eb603216fe8d453abfcd62f0037659ced6ac743c3c37d1998e0838da9623`.
The R46 child replacement completed at 16:02:50 UTC on October 25. The same
Genshin process and RDP session remained alive, the host remained minimized, and
the old child and all four deployment probe chains retired. Root acceptance is
`artifacts/research/2026-10-24/r46-child-deployment-root-acceptance-03/acceptance-01.json`
(SHA256 `6ac357ef587b586d3df22a73109490b5589e79a58f5a3d612dd4842b69ebb4c3`).
A subsequent clean observation acquired the actual Mondstadt scene without
submitting input. The native reset then succeeded, but the fresh short seed
stopped at `recovery_limit_exceeded` after two movement recoveries. Its latest
owner remains ineligible; no older successful owner was substituted.

The approved graphics adjustment remains pending. Both attempts to activate the
existing RDP window failed with `GetCursorPos failed: Access is denied
(0x80070005)`. No graphics settings were changed. A subsequent read-only check
confirmed the RDP window remained minimized. The user subsequently clarified
that the main desktop is locked; that does not establish the RDP session's lock
state. A source-only assessment found that current interfaces do not provide a
complete settings read/change/verify/restore workflow. A dedicated settings
operation would need original-value recording, recognized menu transitions and
independent apply/restoration checks. The planning artifact is
`artifacts/research/2026-10-24/genshin-graphics-fps-workflow-planning-01/assessment-01.json`
(SHA256 `99f8aeebe9041fc118051fd8fd202a1659a8871af8a88015ef52fbce48d409d6`).
No settings route has been implemented or used.

A fresh upstream fetch at 16:41 UTC reached
`39bb31b5c61a10a3474f1a53b2f1bf4807853b4f`. Its four new commits add the
0.66.3-alpha.1 version, elemental collection configuration, guided music, and
Training Guide domain/resin planning. These 52 changed paths were ported to the
fork's scoped runtime, preserving ownership/cancellation, English translations
and the existing RDP controls. The source review is
`artifacts/research/2026-10-24/upstream-39bb31b5-integration-review-01/review-01.json`.
Merge `982d24f743a9ce26720e5f26f6403a5a185bba9f` is pushed to the fork. Both author
and committer use `4991891+everyonce@users.noreply.github.com`. The final Debug
build passed, and the regression run passed all 1,890 cases; only whitespace
cleanup followed that test run. Completion evidence is
`artifacts/research/2026-10-24/upstream-39bb31b5-port-root-review-01/completion-01.json`
(SHA256 `00d890d2ad3b979fb8576038a03c1ba3ae4848e65410147192aa79f8e72f1115`).
R47 remains deployed. New WPF feature behavior and upstream game-text locale
assumptions have not been validated in the game during this offline period.

The already reviewed upstream work and R46 implementation are now integrated in
primary commit `c9ad4d0f4299ab4a50054e35a735b915db846c15`. The primary Debug build
and 1,860-test cohort passed. Its 15 implementation payloads match the reviewed
source12 bytes; across the full source set, 183 other files differ only in line
endings, so the entire primary tree is not claimed to be byte-identical.

The R46 seed timing analysis found that capture, recognition and the initial
response delay outlasted the old 150 ms first grant or 100 ms renewal. The fresh
observations still had room inside the existing source-relative 250 ms horizon.
The explicit v5 contract now grants only that remaining horizon, preserving the
150 ms source freshness check, identity/order checks, endpoint handling, recovery
limits and release requirements. The model's separate 50 ms decision budget is
unchanged. All 1,890 selected C# cases passed with 1,750 source files unchanged;
evidence is in
`artifacts/research/2026-10-24/native-navigation-timing-v5-root-application-01`.
R47 was published successfully at 16:56:24 UTC and replaced the child inside the
same minimized RDP session. Deployment closure
`artifacts/research/2026-10-24/r47-child-deployment-run-001/closure.json`
retains child PID 42000, its actual native birth and the unchanged game PID 27728.
A fresh observation stream closed cleanly. The reset then completed, followed by
v5 seed `ed35382ef54a4078a5bc61f3e8f07f67` in 3,824.52 ms with 37 observations and
zero movement recoveries. The controller returned idle, the host stayed minimized,
and both worker/broker chains retired. Its full audit subsequently passed.
The accepted audit is
`artifacts/research/2026-10-24/r47-navigation-v5-file-binding-01/seed-audit.json`
(SHA256 `c92ae01669ada21d4624483be9ea43d9cf9304566b4ce61c617d7dba935f90be`).
Original collection evidence is in
`artifacts/research/2026-10-24/r47-native-navigation-01`.

Return `97c0d0450701468291fab3bbe35afeb1` then completed in 5,069.66 ms with 44
observations, clean input release and retired worker/broker processes. Its full
audit failed at an inherited assertion requiring v4 for linked routes. That
failure is preserved. The H03 correction handles explicit v5 and constrains the
selected local reader before importing it. It passed independent review, followed
by all five root-issued file-only binding/audit/proof stages with unchanged inputs.
The corrected return audit accepts the immediate predecessor link and both route
records. It retains the original H01 collection identity separately from the H03
reader. No forward or four-leg run has started.
The diagnosis is
`artifacts/research/2026-10-24/r47-return-audit-diagnosis-01/diagnosis-01.json`
(SHA256 `042e88128ffe070c949f6ecade0f240fba691693bf6bb508896ac89d2a370229`).
The corrected return audit is
`artifacts/research/2026-10-24/r47-navigation-v5-file-reader-correction-03/return-audit.json`
(SHA256 `f4bf7da903127abf3c99c7ea8a62539e9ef95fa5f7a79b9bce6c00e66671bf40`),
and its predecessor proof is `return-proof.json` in the same directory
(SHA256 `8ff6f41e2336caa1d2d550b796f10c0a451a46338db29bcdc63f6e06c13bc632`).

The explicit v5 Python client passed all 279 affected regression cases with no
source changes during the run. Two older fixtures were updated to use unknown
`v6` instead of newly supported `v5`; disposable test files were moved into the
workspace after the sandbox redirected temporary directory rejected atomic file
replacement. Both earlier attempts are preserved in
`artifacts/research/2026-10-24/native-navigation-timing-v5-client-root-application-01`.
Existing defaults remain v1 for a single baseline and v4 for courtyard continuation.

The completed full-native paired Q/K experiment retained all four calls, 22
archives and 535 arrays, but failed 33 of 224 numerical gates. It remains
rejected, with all worker identities retired. The failure closure is
`artifacts/research/2026-10-24/native-p2p-full-qk-results-01/failure-closure-01.json`.
The next candidate shares only duplicate FP32 rotary values while preserving the
original normalization, positional-module calls and rotation arithmetic. Its
source, reversible installer/observer and complete host fixture passed review.
The allocator's separately pinned current-identity derivative also passed source
review, while preserving historical evidence. Actual allocation, GPU equivalence
and latency still require qualification; fixture results are not model results.
The unchanged GPU admission floor is 3,584 MiB free. The 17:32:45 UTC sample
reported 3,283 MiB free, 98% utilization and 88 C; it is historical evidence, not
a fresh admission or attribution of another application's workload.

Five retained 1920x1080 PNGs from three native runs are now joined to their exact
journal image sources, pose measurements and timing records. The R46 failed
seed's final image is explicitly absent. The existing saved-file minimap and
world/motion tests each passed once, processing all five exact image hashes.
All 106 bound inputs remained unchanged. The test reports match recorded world,
motion, map layer and position-confidence fields; the producer's FP32 coordinate
conversion reproduces all five recorded positions exactly. The test asserts
original/prepared yaw equality but does not publish yaw, so direct equality to
historical yaw is not established. These are reference measurements, not
independent ground truth; five endpoints cannot establish continuous recognition
or gameplay. The immutable input manifest is
`artifacts/research/2026-10-24/native-navigation-offline-screenshot-replay-plan-01/recorded-frames.json`
(SHA256 `0cc723d06e56f62f8cc6ec44bd8aafd52beba90c29115eb4cd0588fbdf6740d7`).
The replay closure is
`artifacts/research/2026-10-24/native-navigation-offline-screenshot-replay-run-01/closure-01.json`
(SHA256 `990c9e406abee5d4eae3ec0365adef3fb57b8c12cd9a6f0f55acb4800870edf2`).
Its 100 retained CPU timing pairs have medians of 12.40 ms for the original path
and 10.90 ms for shared preprocessing. They are repeated saved-image diagnostics,
not a live-loop latency measurement or an attribution of foreground load.

Two additional saved climbing frames and a saved journal image passed the existing
world/motion replay method once. Both climbing frames returned WorldHud/Climb with
the expected Space and X hints; the journal returned HudMissing and the supplied
not-ready motion gate returned Unknown. The first climbing recording's historical
invalidated readiness remains false. Closure is
`artifacts/research/2026-10-24/native-navigation-offline-negative-climb-replay-run-01/closure-01.json`
(SHA256 `9e22705b6818ca4f8fb489eb9a5d96bd6b929db4ab7972f26801c2b95bb89d98`).
The saved swimming-controls image then passed the existing modal appearance test:
one captured WorldHud row, three synthetic translated WorldHud rows and eight
synthetic BlockingUi overlays. It does not classify swimming motion or validate
the historical coordinates. Its closure is
`artifacts/research/2026-10-24/native-navigation-offline-swimming-replay-run-01/closure-01.json`
(SHA256 `b2545db2f521882d164f91b96dd769da95e3be75ad9540d28e59571083874091`).
These runs preserved their bound inputs and prior replay evidence. The nine real
captures are distinct from the eleven generated test rows.

Two saved 640x360 map screens then passed one existing world/motion test with no
synthetic additions. Both returned HudMissing, while the explicitly false
world-ready motion gate returned Unknown/world_not_ready with null key hints.
All 90 bound inputs stayed unchanged, and the earlier nine-image closures were
preserved. A path-separator
comparison in the file-only closer was corrected using the saved after-hash;
the SDK test ran once. Closure is
`artifacts/research/2026-10-24/native-navigation-offline-map-replay-run-01/closure-01.json`
(SHA256 `0f921f4f02831e0df00cb4335f2cb371eff28c7807ac952771065ca11dfbf33f`).
Coverage now includes eleven real captures and eleven separately synthetic rows.
The finite inventory of 19 directly saved images supplied no reviewed dialogue,
loading, defeat/revival or combat example; those categories remain coverage gaps.
Historical map timestamps and labels are retained without inferring current
readiness, movement or localization.

The ordinary-call shared-rotary timing harness now preserves the original
prediction or entry exception when restoration also fails. Uncertain restoration
retains ownership and prevents lease release. Eight focused inert correction
cases passed, and the independent H02 source review closed the original finding:
`artifacts/research/2026-10-24/native-p2p-shared-rotary-timing-independent-review-02/review-01.json`
(SHA256 `df90a88dcb3a3645b9cec9780e7d92f4cb73ab0b9b091db2d244888be9740c2b`).
This harness still requires the actual 412-check CUDA qualification and separately
qualified runtime composition. No timing run or model allocation has occurred.

A tiny Windows file-sharing fixture also completed: five disposable 33-byte files
rejected conflicting writes/deletes while the read lease was open, and allowed
the operations after closure. This qualifies those fixture operations only. The
corrected checkpoint-load provenance candidate has passed source review, but its
actual checkpoint loading and numerical integration remain unqualified.

The separate eager native-history/application owner passed source review, with
51 current methods joined to saved passing executions. Its review is
`artifacts/research/2026-10-24/native-p2p-step-application-owner-integration-independent-review-01/review-01.json`
(SHA256 `24ceb6d09034095f9a128f7941bc21ea75cbb7d383a307238f0c14ad75a18aaa`).
The C# step-application producer and strict Python bridge are now integrated with
availability disabled. The required Debug solution build passed, followed by all
425 selected Agent tests: 381 retained cases, 38 application cases and six actual
telemetry-composition cases. The initial 397/407 run exposed one real explicit-null
handling bug and nine fixtures with invalid capture epochs; that failed evidence
is retained. The correction preserves omission versus explicit null through
deserialization and cloning, while keeping unsupported extensions rejected.
The completed validation is
`artifacts/research/2026-10-24/step-application-bridge-null-presence-root-review-01/completion.json`
(SHA256 `8de46fd9b3113c6ebf34711486686a76b0439ddcab2737927c9907bfba6a4fcb`).
All 40 Python bridge cases subsequently passed from portable repository tests,
using the actual Bridge class with in-memory transport and no live constructor.
Their receipt is
`artifacts/research/2026-10-24/step-application-bridge-portable-tests-root-review-01/test-result.json`
(SHA256 `fb6c66c1bf2645e87ccd72e49b1f62f9d9f81e3947c7d04b548c3ce17099df18`).

The initial queued-successor v2 implementation addressed those controller boundaries in disabled source.
The corrected Debug build and 491-case Agent cohort passed, including 65 queued
cases and one new regression for explicit JSON null in mouse-call evidence.
The earlier compiler failure and 487/490 test run remain preserved; the latter
exposed that real producer bug and two test-fixture mistakes. Final C# evidence is
`artifacts/research/2026-10-24/step-application-queued-v2-integration-03/tests-01/result.json`,
with TRX SHA256 `0a72245b38a74292055492775a101ccdf238530047bf4b0302b0d1c2d36aac44`.

The corresponding Python candidate passed all 197 guarded cases (192 portable
plus five harness checks), with all selected source pins unchanged. The 34
payloads were installed exactly, and all 62 selected primary paths match the
qualified sources. The same capacity method also passed without injected output,
removing its temporary files. Main receipt is
`artifacts/research/2026-10-24/native-p2p-step-application-queued-v2-python-candidate-04/checks/cpu01/receipt.json`
(SHA256 `2bfec32d959bbe6fbdab6efdc992ed7e7ea5d17e90db3a1ce5a8781502caf675`);
the separate cleanup receipt is
`artifacts/research/2026-10-24/native-p2p-queued-v2-standalone-capacity-recipe-01/checks/cpu01/receipt.json`
(SHA256 `d9f70fcf4472a850e2a3044c72a43ff7f911f5dbe2543ff425131cbffe4da1da`).
These fake-operand checks do not establish numerical behavior or physical input.

The separate session opt-in and producer handshake are now implemented in the
working tree. The required Debug build passed, followed by all 527 selected Agent
cases, including 36 negotiation cases. The initial test compilation failure was
a missing `System.IO` import in the new fixture; its evidence is retained and the
corrected cohort passed. The final result is
`artifacts/research/2026-10-24/step-application-queued-v2-negotiation-integration-02/tests-01/result.json`
(SHA256 `acd44e45c4c0472dd588f3c534cdd9833659f612711189bacfb4bda593291092`).
The installed CLI opt-in also passed all 19 fake startup cases:
`artifacts/research/2026-10-24/step-application-queued-v2-cli-portable-root-01/receipt.json`
(SHA256 `a7ee2474d320e7f60dc7d3d485ab2672026d7f9372062c61f86fa98541ea49fe`).
Neither change enables the model owner or deploys a new application.

The corrected client handshake passed 46 focused fake cases. It binds both
negotiation and subsequent requests to the original connection and validated
hello. Connection replacement retires the original connection once, preserves
its first failure and makes repeated enable attempts inert. Its review and
receipt are under
`artifacts/research/2026-10-24/step-application-queued-v2-handshake-root-03/`.
All five portable payloads were then installed, and the complete 194-case
transport cohort passed in 8.41 seconds externally measured. All 152 selected
source pins stayed unchanged, and no forbidden operation occurred. Retained
output plus retired temporary files totaled 7,428,630 bytes within the 8 MiB
limit. The installed receipt is
`artifacts/research/2026-10-24/step-application-queued-v2-handshake-portable-root-01/receipt.json`
(SHA256 `6e26627a369842724103ae46b7a8232a2922a67f0c632e461ef43c239593ba81`).
One root installer metadata-field error was corrected before any primary write
or test execution; that failed preflight is retained separately.

The checkpoint qualification entry passed 63 fake cases, with the ordinary
runtime entry still blocked. That receipt is
`artifacts/research/2026-10-24/native-p2p-checkpoint-offline-qualification-root-01/receipt.json`
(SHA256 `467f6492e54277d7e27203e45c1b0cf3ab3c0d282750cfb7b8b640979e685ede`).
The complete single-load P/Q composition subsequently passed all 104 guarded
CPU cases after correcting phase timing coverage, public-duration containment
and a test-only guarded-import conflict. The real producer and independent reader
processed fake operands through 17 STORED containers, 197 arrays and all 120
comparison checks. The 12 operation spans include load, public calls, dispatch,
receipt ingestion and cleanup; synthetic test clocks establish no live deadline.
The run took 6.39 seconds externally measured, retained 5,066,454 bytes within its
8 MiB limit, preserved all 307 selected source pins and three Job helper pins,
and left its temporary directory empty. No numerical runtime was imported.
Its receipt is
`artifacts/research/2026-10-24/native-p2p-scoped-queued-v2-qualification-root-03/receipt.json`
(SHA256 `6ea40dab5536ea5e2e0f5f31994a94d1903dbed43fc4e56288f36d566f434495`).
The retained containers total 4,054,514 bytes; the report is 154,637 bytes within
the reserved report allowance. These are complete fixture capacity checks,
not measurements of model memory or GPU numerical behavior.

The assembled worker subsequently passed all 30 guarded CPU wrapper cases.
They cover completed producer/reader integration, retained-owner identity,
admission before report detachment and preservation of the first failure.
The first attempt stopped two cases because the test helper placed fake binding
files inside the reserved worker output directories. A one-line fixture correction
moved them to distinct siblings within the owned attempt; production guards and
all 30 test-method bodies remained unchanged. Both attempts are retained.
The passing run took 3.33 seconds externally measured, retained 5,115,048 bytes
within its 8 MiB limit, preserved 186 selected pins and three Job helper pins,
matched all 20 expected phase messages and left its temporary directory empty.
Its receipt is
`artifacts/research/2026-10-24/native-p2p-scoped-queued-v2-execution-root-03/receipt.json`
(SHA256 `42ce9829e296e0404c22bd90dad12230037761e3f9aea2d1a7bae7ebf4d1e997`).
The reviewed logical diagnostic bound is 32,999,666 bytes within 32 MiB; it
excludes model/runtime storage and GPU memory. No numerical runtime was imported,
no checkpoint was read, and the full inherited input scan was not performed.
The assembly remains disabled for numerical execution and live input.

The GameScaling device-greedy candidate and two-owner executor remain outside
the primary runtime. Their 19 decoder and 16 executor CPU cases passed; the latter
receipt is
`artifacts/research/2026-10-24/gamescaling-device-greedy-comparison-executor-01/checks/cpu01/receipt.json`
(SHA256 `a348eb33e63b349c509c16811fb042d86635039f5acce5e76b2b99b7164c2fb3`).
The prepared experiment preserves the original full-action checks and separates
public prediction time from later cache inspection. Stored float summaries
cannot independently reproduce the comparisons. Its GPU binding remains false.
One complete fake producer-to-reader case also passed, exercising all 12 fake
calls and the full report serialization rather than a partial reader fixture:
`artifacts/research/2026-10-24/gamescaling-device-greedy-reader-success-root-01/receipt.json`
(SHA256 `8d677b776281ea0f0f7953bcf0f2e765e6620bca1db33d619c9b88eed8eb7d6c`).
These are CPU behavior checks; no new GameScaling GPU latency result exists.

Actual native history publication and live integration remain pending. The source
preserves the native 50 ms action, proposal under 50 ms and consumed-frame start
under 100 ms. Controller transition evidence and actual timing qualification are
required before claiming continuous dispatch. Further graph/startup work and
training decisions depend on execution-context and scene-quality checks.

Controls and launch instructions: [RDP automation](../../tools/rdp-automation/README.md). Research scope: [first sprint](BetterGI-Agent-First-Sprint.md) and [original research](BetterGI-Agent-Research-2026-10-23.md).
