# BetterGI agent status

Updated October 25, 2026, 21:42 UTC. See the [measured sprint results](BetterGI-Agent-Sprint-Results-2026-10-23.md) for evidence and historical checkpoints.

The local prototype supports launching BetterGI and Genshin inside minimized RDP, issuing commands in that session, and replacing the child BetterGI build. It has demonstrated automatic continuation along a fixed courtyard route. General autonomous gameplay and learned-model task completion remain unverified.

Current work uses recorded screenshots and synthetic data until Daniel explicitly
says the machine is ready for game and model work again. At 17:45:41 UTC, two
read-only status requests confirmed an idle child, disabled input, no running
task or stream, and the minimized RDP host. No cleanup action was needed. Live
observations, game tests, application replacement and GPU qualification are
deferred; elapsed time alone does not resume them. Evidence is
`artifacts/research/2026-10-24/offline-only-transition-01/status-01.json`
(SHA256 `8d55acacc93791e365228d45b8a4046ff896c2344f7244a2309485d97fe48f39`).

| Area | Latest verified state |
|---|---|
| Upstream integration | Four upstream commits through `39bb31b5` are merged and pushed in `982d24f7`. The final Debug build and the 1,890-case C# regression cohort passed. New Training Guide, music and collection UI/game behavior still needs live validation. |
| Deployed application | Last verified at 17:45 UTC: R47 inside the existing minimized RDP session. Its 1,890 selected C# tests and Debug/Release validation passed before replacement; the same Genshin process was preserved. No new deployment or live check has occurred during the offline hold. |
| Native navigation | Both saved R47 routes now pass the full audit: seed 3.82 seconds/37 observations and return 5.07 seconds/44 observations. The return's immediate predecessor link is accepted. This does not establish sustained gameplay. |
| Reusable command | Bounded continuation and the reviewed schema3 envelope checker are in primary. Explicit v5 client support passed 279 Python tests. The separate H03 reader package and corrected return proof are accepted; future live continuation requires user readiness and fresh runtime checks. |
| Endpoint repair | Deployed in R46 with input telemetry and Right Shift support. Both R47 routes and the return's endpoint/continuation evidence pass their full audits. Physical input acknowledgment and training eligibility remain false. |
| Native timing v5 | Explicit native timing v5 is committed at `ab136e25be0467c28ca664a825eef5a79bdeefb1` and deployed in R47. Seed and return evidence are accepted; the next forward leg and four-leg qualification are deferred. |
| Offline recognition replay | Eleven saved captures passed scoped CPU replay: five exploration frames, two climbing frames, the journal, one swimming-controls frame and two map screens. Eleven additional swimming-derived rows are explicitly synthetic. Five recorded positions match the production coordinate conversion; the other checks do not establish localization or current readiness. |
| GPU runtime | Existing PyTorch 2.7.1 + CUDA 12.8 environment on the RTX 2080 SUPER. |
| P2P key compatibility | The official Right Shift command is included in deployed R46 through the existing input implementation. Separate live key-delivery qualification remains pending. |
| Action acknowledgment | A matching request ID is required before settling policy history. Unknown outcomes preserve the pending action and stop the runner. The focused candidate and caller cohorts passed 55 distinct mocked tests. |
| Execution-aware decisions | Opt-in client snapshots and GameScaling prompt conditioning are implemented; 121 distinct inert tests passed. One live attack command returned a completed software receipt. The closed context and graph comparisons produced neutral input in both contexts and did not establish receipt-dependent behavior. |
| Ongoing input telemetry | The Python client passed independent review and 103 tests; the C# producer's 26 cases passed within R46's 1,860-test validation. The producer is deployed, but a controlled live ongoing-call test remains pending. |
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
| Checkpoint qualification entry | The complete single-load P/Q composition passed 104 guarded CPU cases, including the earlier scope and entry cases. Its real producer and reader validated 17 containers, 197 arrays and 120 checks using fake numerical operands. Actual model loading, numerical equivalence and controller timing remain unqualified. |
| GameScaling device-greedy decoding | The disabled candidate passed 19 fake decoder tests. Its two-owner comparison executor passed 16 guarded CPU tests, and a further complete producer-to-reader fixture passed. The prepared experiment compares four pairs on saved images with original full-action validation; CUDA equivalence, simultaneous memory fit and speed remain untested. |
| Model optimization | Skipping unused final decoder work passed 1,733 correctness checks across two history41 evictions. A separate 40-pair experiment reduced median prediction time from 165.30 ms to 155.07 ms; paired actions/random states and final cache checks passed. |
| Training | Not started. Model proposals and incomplete recordings are not expert action labels. |

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
not measurements of model memory or GPU numerical behavior. The numerical
assembly remains disabled while its owned-worker composition is prepared.

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
