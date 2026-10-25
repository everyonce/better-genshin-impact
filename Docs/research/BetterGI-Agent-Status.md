# BetterGI agent status

Updated October 25, 2026. See the [measured sprint results](BetterGI-Agent-Sprint-Results-2026-10-23.md) for evidence and historical checkpoints.

The local prototype supports launching BetterGI and Genshin inside minimized RDP, issuing commands in that session, and replacing the child BetterGI build. It has demonstrated automatic continuation along a fixed courtyard route. General autonomous gameplay and learned-model task completion remain unverified.

| Area | Latest verified state |
|---|---|
| Deployed application | R45; 1,770 selected C# tests and full Debug/Release validation passed before deployment. |
| Native navigation | Four consecutive courtyard legs passed their full retrospective audits. A later reusable-command trial completed one return and then stopped on an endpoint lease-expiry failure. |
| Reusable command | Published on the fork at `d12541e513745a4468e1e13709cbfc16744625d3`; 78 CPU/mock tests passed. It stops after a failed or unknown outcome. |
| Endpoint repair | Applied and reviewed in the separate source11 checkout. Its expected 1,834-case C# cohort, build and deployment are still pending. |
| Future endpoint adapter | 96 offline tests and source review passed. It remains unapplied and unbound until the new application and its result format are validated. |
| GPU runtime | Existing PyTorch 2.7.1 + CUDA 12.8 environment on the RTX 2080 SUPER. |
| P2P key compatibility | The primary source now admits the official Right Shift command through the existing input implementation. Independent source review passed; compilation and deployment remain pending. |
| Action acknowledgment | A matching request ID is required before settling policy history. Unknown outcomes preserve the pending action and stop the runner. The focused candidate and caller cohorts passed 55 distinct mocked tests. |
| Execution-aware decisions | Opt-in client snapshots and GameScaling prompt conditioning are implemented; 121 distinct inert tests passed. One live attack command returned a completed software receipt. The closed context and graph comparisons produced neutral input in both contexts and did not establish receipt-dependent behavior. |
| Ongoing input telemetry | The corrected Python client passed independent review and 103 tests against the integrated primary files. It preserves receipt timing qualifications and prioritizes the latest reported input call. The four-file C# producer passed source review; its 26 cases remain uncompiled. R45 still exposes terminal receipts rather than ongoing call state. |
| P2P execution-history commit | Offline CUDA comparison passed 860 byte-exact cache comparisons across 44 reference calls, 48 proposals and 43 scripted commits. A bounded RDP trial then verified live image intake, rejected-proposal rollback and cleanup; its first proposal missed the latency limit, so no action was submitted. Live receipt-authorized history commit remains unverified. |
| Native history rollback | Offline CUDA validation and its closed-result audit passed: 44 reference calls, 48 candidate attempts, 44 acceptances, four rejections and 960 consistency checks. Live controller integration remains unverified. |
| Growing-history graphs | Two native startup prefixes passed capture, replay and 192 independently recomputed consistency checks. Full coverage of all 41 prefixes and startup latency remain unqualified. |
| Receipt-bound startup graphs | Three consecutive native prefixes passed all 534 numerical gates with zero recorded error, including all 60 committed K/V leaves, actions, RNG and rejected proposals. The two continuation handoffs took about 4.08 and 5.09 seconds. Preloading, longer continuation and live use remain unqualified. |
| Pending tensor transfer | A four-pair public-path comparison passed 1,368 numerical checks with zero recorded error. Packed transfer averaged about 185.73 ms versus 184.06 ms for the original path, and all four receipt calls were slower. No speedup is established; the optimization is not promoted. |
| Preloaded history graphs | Two preloaded prefixes passed all 356 numerical gates with zero recorded error, including 40 committed K/V leaves. Preloading took 6.91 seconds and the observed handoff took 329.92 ms. Longer continuation and continuous gameplay remain unqualified. |
| Paired Q/K arithmetic | All 47 actual operand samples passed 188 numerical checks. Sixteen checks recorded nonzero error, with a maximum of 0.001953125. Full-model parity and speed remain unqualified. |
| Continuous input handoff | The separate step-application contract passed design review. Its protocol/ledger has 53 original and 24 focused inert cases; both review findings are corrected and independently reviewed. BetterGI bridge integration is under development; native history integration remains pending. |
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

The receipt-bound native owner currently serializes terminal completion, history
commit and the next prediction. The controller calls `ReleaseAll` before queuing
the terminal receipt, whereas its valid replacement path can retain common held
keys. Preloading graphs alone cannot remove this sequencing boundary. This is a
source finding about software call order, not proof of physical key release or a
measured gap. The independent review is
`artifacts/research/2026-10-24/controller-continuity-source-independent-review-01/review-01.json`
(SHA256 `fabe3a163e43ae8be53abc5b6d689ae427aad197782ea919c33513e0740ed622`).

The proposed follow-on separates complete software step-application evidence
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
The existing 60 ms post-input delay also exceeds the native 50 ms interval before
inference begins, so the initial protocol prototype is a correctness step;
continuous timing still needs an explicit scheduling/resampling solution.
The design review is
`artifacts/research/2026-10-24/continuous-step-application-contract-independent-review-01/review-01.json`
(SHA256 `d9ad5d41c3db8514b1671012adc1451184d67c378606a34fabb62c915f68cde3`).

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
The C# producer is still uncompiled and unpublished, so these client tests do not
establish deployed ongoing telemetry or physical input state.

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
The qualification worker and complete fixtures are under construction. Actual
CUDA mask values, graph lifetime, numerical parity and latency still require
qualification; no measured mask-reuse saving is established.

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

The build needs three upstream asset packages that are missing locally: `BetterGI.Assets.Map` 1.0.25, `BetterGI.Assets.Model` 1.0.39 and `BetterGI.Assets.Other` 1.0.28. The one-time restore approval for the [official NuGet source](https://api.nuget.org/v3/index.json) remains pending after automatic approval review blocked the source change.

Upstream was checked again at 08:21 UTC on 2026-10-25. Its new commit
`f154b69649fcd828a517af03d4230f6693e6832d` changes only the project version to
`0.66.3-alpha.1`; it adds no functional changes after the upstream merge already
staged in the build worktree. That version update has been fetched but is not
part of the frozen source11 build packet or the running R45 application.

Once restore is authorized, include the reviewed Right Shift change in a fresh build packet and run the complete test/build checks, replace only the RDP child, and establish a fresh navigation seed before testing the repair. The latest failed owner cannot resume from an older successful proof. The separate ongoing-input telemetry candidate also needs build/test validation before deployment and live validation. Further graph/startup work and training decisions follow execution-context and actual-scene quality checks; the accepted offline numerical results alone do not qualify the new controller for live use.

Controls and launch instructions: [RDP automation](../../tools/rdp-automation/README.md). Research scope: [first sprint](BetterGI-Agent-First-Sprint.md) and [original research](BetterGI-Agent-Research-2026-10-23.md).
