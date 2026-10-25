# BetterGI agent status

Updated October 24, 2026. See the [measured sprint results](BetterGI-Agent-Sprint-Results-2026-10-23.md) for evidence and historical checkpoints.

The local prototype supports launching BetterGI and Genshin inside minimized RDP, issuing commands in that session, and replacing the child BetterGI build. It has demonstrated automatic continuation along a fixed courtyard route. General autonomous gameplay and learned-model task completion remain unverified.

| Area | Latest verified state |
|---|---|
| Deployed application | R45; 1,770 selected C# tests and full Debug/Release validation passed before deployment. |
| Native navigation | Four consecutive courtyard legs passed their full retrospective audits. A later reusable-command trial completed one return and then stopped on an endpoint lease-expiry failure. |
| Reusable command | Published on the fork at `d12541e513745a4468e1e13709cbfc16744625d3`; 78 CPU/mock tests passed. It stops after a failed or unknown outcome. |
| Endpoint repair | Applied and reviewed in the separate source11 checkout. Its expected 1,834-case C# cohort, build and deployment are still pending. |
| Future endpoint adapter | 96 offline tests and source review passed. It remains unapplied and unbound until the new application and its result format are validated. |
| GPU runtime | Existing PyTorch 2.7.1 + CUDA 12.8 environment on the RTX 2080 SUPER. |
| Action acknowledgment | A matching request ID is required before settling policy history. Unknown outcomes preserve the pending action and stop the runner. The focused candidate and caller cohorts passed 55 distinct mocked tests. |
| Execution-aware decisions | Opt-in client snapshots and GameScaling prompt conditioning are implemented; 121 distinct inert tests passed. The bounded live receipt-to-decision check is pending. |
| Ongoing input telemetry | Four-file C# candidate passed source review. Its 26 prepared cases remain uncompiled and unexecuted; R45 still exposes terminal receipts rather than ongoing call state. |
| Native history rollback | Offline CUDA validation and its closed-result audit passed: 44 reference calls, 48 candidate attempts, 44 acceptances, four rejections and 960 consistency checks. Live controller integration remains unverified. |
| Growing-history graphs | Two native startup prefixes passed capture, replay and 192 independently recomputed consistency checks. All 41 prefixes, feedback composition and startup latency remain unqualified. |
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

The current milestone joins each image with the controller evidence known before
the next decision. The client now records proposals, admissions and terminal
receipts separately, retains their originating goal, and excludes evidence that
arrives during inference. Optional GameScaling text is bounded to 2,048 bytes and
records the exact consumed text hash. The integrated cohort passed 121 distinct
tests (134 executions, including 13 repeated imported fixture cases). Local
evidence is `artifacts/research/2026-10-24/execution-context-primary-integration-01/tests-01/receipt.json`
(SHA256 `6f377f57b910ab4ad8cd0815ed65609594f4f648d33b013a95083d5878a2cb1a`).
Next, collect one bounded attack and compare GameScaling decisions on its identical
pre-attack image with the actual before/after receipt contexts. Those model outputs
will be recorded without being executed. Passing the unit checks establishes the
wiring, not learned instruction-following quality or constant gameplay.

The build needs three upstream asset packages that are missing locally: `BetterGI.Assets.Map` 1.0.25, `BetterGI.Assets.Model` 1.0.39 and `BetterGI.Assets.Other` 1.0.28. The one-time restore approval for the [official NuGet source](https://api.nuget.org/v3/index.json) remains pending after automatic approval review blocked the source change.

Once restore is authorized, run the complete source11 test/build checks, replace only the RDP child, and establish a fresh navigation seed before testing the repair. The latest failed owner cannot resume from an older successful proof. The separate ongoing-input telemetry candidate also needs build/test validation before deployment and client integration. Further graph/startup work and training decisions follow execution-context and actual-scene quality checks; the accepted offline numerical results alone do not qualify the new controller for live use.

Controls and launch instructions: [RDP automation](../../tools/rdp-automation/README.md). Research scope: [first sprint](BetterGI-Agent-First-Sprint.md) and [original research](BetterGI-Agent-Research-2026-10-23.md).
