# Local agent sprint: measured results

Updated October 24, 2026. Start with the [current status](BetterGI-Agent-Status.md) for a concise overview. This report distinguishes the implemented prototype from the live-game and learning milestones in the [original backlog](BetterGI-Agent-First-Sprint.md). Follow-up entries below preserve the progression of builds and measurements; earlier snapshots are historical.

Current live checkpoint: R45 previously completed four consecutive courtyard legs inside minimized RDP, with all four retrospective full-route audits accepted and no reset between legs. The new reusable command's first live attempt at 22:17:53 UTC completed one return, then stopped during the forward leg's endpoint closure with `forward_lease_expired`. Inputs were released; saved postflight reports the same root/child/game, task false, pilot idle and stream input off. Its worker and broker were independently absent at 22:19:36 UTC. The latest native owner is failed, so the older accepted predecessor must not be reused. This remains a bounded route prototype with a newly isolated endpoint-finalization bug; sustained learned-model gameplay, general task success and training remain unestablished.

Current source checkpoint: the managed checkout now contains source11: 1,748 pinned .NET files, including the upstream merge, image-header optimization and reviewed endpoint-closure repair. Its expected selected C# cohort is 1,834 cases, including 49 newly declared endpoint cases. The launchers and all current source pins have been reviewed; no source11 restore, tests, build or deployment have run. The pending exact-endpoint NuGet approval still blocks compilation. Source manifest SHA-256: `30ed822a55eb30c703678f6cc67c77667ddb63ced136df5f7aa07ef18f0ddcea`; root readiness: `6ebe48042109683df91633c904721b9352086d7a49bfe64eb54d4a598ef72124`. R45 remains deployed.

Latest validated runtime checkpoint: R45 source09 is applied and passed 1,770/1,770 selected C# cases, with all 1,744 .NET source/resource/project pins unchanged through verification. Full Debug/Release publication passed at 20:53:03 UTC, and all owned SDK processes retired. The reviewed continuation client passed 96/96 Python cases before application. The preceding R44 release passed 1,702 cases and has a verified 543-file Python snapshot. Its host-only response wait precedes capture and preserves movement, freshness and recovery limits. Builds retain the truthful dirty-worktree base revision 5aee805bc774d6b0329c992ada4b049e9b5ed714. V7 passed its two-step eager GPU comparison and independent byte-level audit. V8 then completed 41 resident eager calls and all 20,542 numerical gates, with zero reported numerical error. The independently corrected closed-file audit accepts 369 saved-original decoder comparisons, 102 historical anchors, 82 reconstructed pass states and all 20 final cache hashes. Both V8 workers retired. The original head-width audit failure and a later output-publication failure remain recorded. V8 fills history41. V9 now passes two actual full-cache evictions, eager/graph comparisons and the production copyback path: all 1,125 gates report zero error, and the closed reader independently accepts the retained arrays and final cache hashes. Its launcher/interpreter retired. V12 now has accepted complete production-predict timing for its instrumented historical history41 replay. Uninstrumented/live latency for that new path, default-history200 parity, execution feedback and learned gameplay remain unverified. The original GameScaling decoder remains in use after its exponential substitution failed parity.

Published prototype and pending C# update: the reusable courtyard command is published on `main` at `d12541e513745a4468e1e13709cbfc16744625d3`, after 78 CPU/mock cases passed. Author and committer both use `4991891+everyonce@users.noreply.github.com`; the normal push and remote readback succeeded. The earlier verified R45 runtime/tool changes and results are published on the fork's `main` at `4d8137b9229a4f78cedfad723cb498ef614c5c73`, with all three new commits using `4991891+everyonce@users.noreply.github.com` for author and committer. The normal push and remote readback completed at 21:51:59 UTC. After V10 run002 closed and its 14 pinned primary tool files were preserved byte-exact, the clean primary checkout fast-forwarded to that verified commit at 22:23:02 UTC. The original V10 seal remains unchanged and would reject changed original paths; future diagnostics must explicitly derive from the preserved sources. Separately, the managed branch merged upstream through `205f0303185b1f721327c6b721f5ba05e662d726` at merge `3e1b87b7050fba21dc1f2a0c671f490b76dec0d3`. That merge, the applied R46 image-header optimization and endpoint repair are not yet published or built. Source10's first verification stopped at NuGet restore with six NU1100 errors for the newly required Map 1.0.25, Model 1.0.39 and Other 1.0.28 packages; zero C# tests ran. The 1,745 source pins were unchanged. An exact-endpoint approval request for a one-time official NuGet restore remains pending; no global package-source configuration was changed. R45 remains the running build.

## October 24: closed P2P kernel trace and unused decoder work

V13 retained V12's model, precision, history41 seed, image, goal and no-input boundary. It completed one preparation and one recorded warm public prediction, with six underlying forward/capture/replay accounting events. The unchanged closed reader accepted the result. The warm API took **169.4868 ms**; the 3,807.3145 ms preparation and later profiler stop/export are outside that warm interval. This single instrumented sample is not a latency distribution or a new numerical parity test.

The exported graph launch has correlation 216022. Its linked records contain **5,438 kernels and 37 device-to-device copies**, with all 104 full kernel-name groups preserved in the analysis. Forty-seven memory-efficient attention kernels confirm that fused attention is already in use. The recorded activity union is 82.326153 ms, with 75.523047 ms uncovered inside the 157.849200 ms envelope. Eleven activity records over 1 ms contribute 51.931709 ms; eleven uncovered spans over 1 ms total 54.712293 ms. These are recorded intervals and gaps, not exclusive device-busy/idle measurements, module assignments, causal diagnoses or recoverable speedup estimates. The accepted reader's tiny binary-floating-point differences are preserved and reconciled by the later decimal analysis.

Source review identified a smaller, concrete candidate: after sampling the eighth action component, the decoder performs another three-layer forward and discards its output and local cache. The candidate will preserve that final sample, embedding and shape assertion, then skip only the unused successor computation in the qualified inference/eval path. This reduces source-level decoder evaluations from nine to eight; it does not predict a proportional latency improvement. The persistent temporal cache is updated separately from the sampled actions. Training, custom hooks and changed module state require explicit handling.

The isolated candidate is being prepared for fresh original-eager, candidate-eager and candidate-graph comparisons over two full-cache evictions. All eight conditional heads, raw action IDs, random-number state and complete returned temporal state must retain the established gates. V13's shape/finite metadata is not a numerical oracle. No candidate speedup, gameplay quality or training result is established at this checkpoint.

The owner, launcher and interpreter were independently absent at 23:50:20 UTC; the original closed audit then completed successfully. Root verified the final 61-file analysis/review closure without rerunning the original reader or inherited runtime scan. A host process-table observation at 00:03:23 UTC on October 25 confirmed the same BetterGI root, R45 child and Genshin process creation/session identities.

Evidence under `artifacts/research/2026-10-24/`: accepted `native-p2p-v13-closed-audit-01/audit.json`, SHA-256 `860030fbea7b2097a0ab925b8c8ceae84e994e78d920d23d445c7d3231b5f554`; reviewed analysis `native-p2p-v13-trace-analysis-01/manifest-01.json`, `cdba85d127bcad9da871811ef383545c17deb98d18762fe33e8a2e65e7cd52cd`; source review `native-p2p-unused-action-decoder-tail-review-01/review.json`, `bfe02d206d46aa015109bc5518197b0e4985195b43e4335caced2a7311f16a5b`; root closure `native-p2p-v13-root-closure-01.json`, `89be8acf352580d2cd4addc6e04931b679e60fe317966eaf453b66a6132252bb`.

## October 24: complete P2P GPU-event diagnostic under shared load

V12 completed one preparation and all **40 measured predictions**. The original closed reader accepted the report, final input/state/source checks and all stream-event records. The unchanged 50 ms synthetic schedule skipped 116 elapsed release slots; none of the measured calls met 50 ms. Its measured window lasted 7,923.9189 ms within the ten-second admission window. The one-time preparation call took 3,800.1824 ms and is excluded from these percentiles.

| Recorded interval | Nearest-rank median | 95th percentile |
|---|---:|---:|
| Complete production predict API | 172.6898 ms | 183.3514 ms |
| GPU event: static input and sampling uniform | 0.7251 ms | 7.6980 ms |
| GPU event: graph replay | 165.2306 ms | 177.6285 ms |
| GPU event: recurrent state copyback | 1.7322 ms | 11.0713 ms |
| GPU event: full three-region span | 171.3755 ms | 182.2078 ms |
| Host bracket: post-forward synchronization | 164.6264 ms | 176.2693 ms |
| Host bracket: native action decoding | 0.5883 ms | 0.7973 ms |

The API minimum/maximum were 147.8096/187.9268 ms. The host synchronization bracket accounts for 94.45344% of summed API wall time. Separately, graph intervals account for 96.53379% of the summed independent GPU event totals. These are different clocks and scopes; no host/event subtraction is used to claim scheduling cost. Events retain intervening stream work and timing resolution limits, and cannot identify exclusive kernel execution or another process. All 41 calls passed the declared float-sum consistency check. The four reusable events produced 168 successful record returns including setup and 164 elapsed-time queries; returned record calls do not themselves timestamp GPU completion.

This is a fixed retained-image, history41, instrumented diagnostic. It does not establish current scene freshness, uninstrumented speed, default-history200 parity, model instruction quality, input execution or training eligibility. Earlier faster measurements used different paths and conditions. The collector retained 81 exact rows; only four of the 40 measured call envelopes contain complete-row receipts, reporting 96%, 97%, 97% and 98% device-wide utilization. Sampling windows and physical CUDA/NVML UUID correspondence remain unproven. All six known model, collector and utility process identities were independently absent at 23:12:56 UTC; no game input was issued.

A separate read-only driver query at 23:15:42 UTC, after the model worker exited, reported active software thermal clock limiting, 88 C, 990 MHz core clock and 96% device utilization. Power-cap, hardware-thermal and hardware-power-brake reasons were inactive in that sample. This point observation does not prove the cause of earlier calls; no hardware settings changed.

Evidence: `native-p2p-production-predict-cuda-events-v12/run-001/report.json`, SHA-256 `6105c3a3228262b448aa1c2ce6a6eb46b557a8636faaf5088462bc43d02db95f`; accepted `native-p2p-v12-closed-audit-01/audit.json`, `741d8b7c391c731f40c7e84af36f363a2c2cfc07b1f1a6c34230162b8ed1ba7f`; independent arithmetic `native-p2p-v12-independent-timing-check-01.json`, `1606b20ef668ffec246d79877ad51750e9dd4589351b007e4c317d006a00a3d7`; separate post-run clock sample `native-p2p-v12-post-run-clock-status-01.json`, `5f0f739409f96e3b80eccc5434a79208c3c41b5d2b79d10ed079c44e5c72b61b`. The joined analysis is in `native-p2p-v12-run001-telemetry-analysis-01/`.

The isolated endpoint CLI adapter also passed all 96 offline cases and independent source review. Its 78 inherited cases and legacy control flow remain intact; its 18 additional cases cover the new adapter boundaries. Source11 and the new endpoint journal format remain explicitly unbound and rejected until actual test/build/startup/runtime evidence is available. The candidate remains unapplied. Checkpoint SHA-256: `c0b1b0ec71bd1c7b7340c0e1a281985757685e57f27d0eca02a4a1f44ce32903`; review: `courtyard-endpoint-cli-adapter-independent-review-01.json`, `77e425bce022252b42763022e94dc1c06cb4d97061300413bbeee32cbcd2889b`. The original 21 alias-collision errors and the corrected 96-pass result remain preserved.

## October 24: P2P host-phase diagnostic and applied endpoint source

V11 returned one preparation and **17 of 40 required measured predictions**, then failed `measurement_admission_window_incomplete`. The unchanged complete reader rejected `closed_worker`, so this is a failed, partial diagnostic. The last call was admitted at synthetic origin +8.8502624 seconds and returned at +18.1454978 seconds: the ten-second rule limits admission, while the separate owner limit bounds an already-running call. The schedule skipped 161 intervening slots without a catch-up queue.

| Observed interval | Partial host result |
|---|---:|
| Complete API: minimum / nearest-rank median / maximum | 41.4494 / 112.6118 / 9,295.2354 ms |
| Calls within 50 ms | 1 of 17 |
| Sum of complete API intervals | 17,665.8195 ms |
| Existing post-forward synchronization bracket | 17,431.2080 ms; 98.6719467% of summed API intervals |
| Submission/replay/copyback bracket | 206.6881 ms; 1.1699887% |
| Native decoder bracket | 12.9931 ms; 0.0735494% |
| Last call: submission / synchronization / decoding | 10.0803 / 9,283.6735 / 0.7950 ms |

All 18 returned calls retained their six ordered markers: 54 phase rows and 108 markers. Preparation was excluded from the measured statistics. These are instrumented host intervals, with unmeasured tracing overhead, not isolated GPU execution time. The process CPU clock advances in 15.625 ms increments here; a zero short-phase CPU delta does not establish zero CPU work. The final input/goal/state/pointer gates were unreached after the incomplete-count failure; false default completion flags do not themselves prove mutation. Cleanup drain completed. No complete-run p95, sustained-control result or new numerical parity claim is available.

The separate collector retained 86 exact CSV/sample rows and cleanly stopped on the matching root request. Only five measured calls contain any complete-row receipts; twelve contain none. Four receipts inside the last synchronization bracket reported 98% device-wide utilization. Sampling windows, buffering and physical CUDA/NVML UUID correspondence remain unproven, so this does not identify a cause or another process. All five owned model/collector/utility PIDs were independently absent at 22:42:57 UTC.

The closed analysis and independent review recomputed every phase difference, external residual, setup interval and all 79 receipt classifications. Review: `native-p2p-v11-closed-independent-review-01.json`, SHA-256 `79a62e8f843dc77c442a9fbc9beb22250ac18db92a9bcb4e2c626bbef359702e`; closed packet: `native-p2p-v11-run001-telemetry-analysis-01/final-closure-01.json`, SHA-256 `5dec3a138e1fbdac389f212088b97b1b50203e5f919d2c0258f76a49c704f19a`. The first file-only analysis attempt failed on a text-decoder alias; its source and error log are preserved. Correcting that alias produced the closed packet.

Source tracing places the wait after asynchronous graph replay and index/key/value copyback, before native decoding reads tensor values. [PyTorch 2.7.1 launches graph replay on the current CUDA stream](https://github.com/pytorch/pytorch/blob/v2.7.1/aten/src/ATen/cuda/CUDAGraph.cpp#L175). Removing the explicit synchronization has not been shown to remove the underlying dependency. The subsequent V12 run described above used four reusable timing events around input setup, graph replay and state copyback, initialized through an existing setup synchronization. Event durations must retain the [CUDA 12.8 limitations on intervening stream work and finite resolution](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-runtime-api/group__CUDART__EVENT.html). Root source note: `native-p2p-v11-root-synchronization-note-01.md`, SHA-256 `bee7a203ed97c9db3c6ea12a4a67476951b6cd7ed97158c5b2d951c042a7ef71`.

The endpoint repair's separate evidence-reader overlay passed 22 offline cases and independent review after correcting host-age and wire-type checks. Its original preparation and all prior source bytes remain preserved. The new full route entry deliberately remains unbound until actual source11 test, build, startup and runtime records exist. Overlay review SHA-256: `734bb01dc90abd30f4090a7a670f34ae83eea5d1bfcb51f62b318d3752388899`. The current reusable CLI retains its R45-compatible schema guard; this overlay does not retroactively accept the failed forward.

## October 24: reusable-command endpoint closure failure

The reusable `courtyard_sequence.py` and pure-file evidence validator are applied in the managed checkout with their focused fixtures. The reviewed candidate passed 59/59 CPU/mock cases, and its installed default preview passed against the actual latest accepted predecessor. One documentation-only string was added during application; its function AST was otherwise unchanged. The four-leg live request attempted exactly two legs: return `b0e7410dee6f439dbf773bfe3e69c0c4` completed according to the native client, then forward `9bdf2a8a5fc944a0b7e7bb2db8f45119` failed. The worker did not replay or start either remaining leg. The separate full-route audit accepted the first return at 22:25:38 UTC: `courtyard-sequence-live-01-return-audit-01.json`, SHA-256 `9a6879f8705cd5cdbeaa90e9797bc8563680073e609c9524b7d29ad70c54aba5`. That historical acceptance cannot replace the failed forward as the current latest owner.

The final renewal allowed 100 ms. The next capture call took 61.5070 ms and recognition 37.7640 ms. Recognition finished 0.6037 ms before expiry, but the read and endpoint close reached the lease check 1.3114 ms after expiry. W-up then completed without a reported error. A renewed response wait did not cause this final interval: only a physical W-down establishes the 60 ms response cutoff, and this capture started 167.4251 ms beyond that cutoff. The source-relative 250 ms cap did not shorten this grant.

The saved `releasing` phase proves through the frozen Task's control flow that its endpoint-distance branch had been entered. The exact last numerical pose was not retained because closure threw before the endpoint decision was appended. The preceding pose, 1.7334377918 units from the target, belongs to a different read and cannot fill that gap. There were 43 completed/admitted reads, 42 decisions, no recovery pauses and no final-verification samples or final image. A separate read-only screenshot at 22:22:30 UTC shows the normal English HUD and upright Traveler beside the fountain; it does not replace final pose verification.

The reviewed repair was applied to nine managed source/test files at 22:42:23 UTC and is now frozen in source11. It retains the accepted endpoint decision before closure, joins the actual expiry pause and original movement budget, confirms release, permanently closes movement and requires fresh final verification within the original pause/task deadline. Ordinary closure and the movement/source limits remain unchanged. The 49 new C# cases are declared but unexecuted. The applied-source receipt is `courtyard-endpoint-expiry-candidate-v1/apply-result-01.json`, SHA-256 `a0aea9c3eab73b3c05ef3809688887168a6978ecd2c2bb4d09aef6ece4e97625`. The historical source10 manifest and deployed R45 binaries are unchanged. The closed failure analysis is `courtyard-sequence-live-01-failure-analysis/report-01.json`, SHA-256 `26fd6d1a851fa245706fcac7be0e337d79bd9349977673f9d1202fd351feee84`.

The parent failure-reporting fix is now applied in the managed checkout. Its 19 focused mock cases exercise the actual parent function, including native failure versus broker timeout, malformed or contradictory success records, partial admission cutoff and zero-leg completion uncertainty. A file-only projection against the saved failed run correctly retains `forward_lease_expired`, two attempted legs and one successful leg, without replay or changes to the original summary. Broker facts, reported native terminal state and independent OS retirement remain distinct. Projection SHA-256: `58eee020e695c24b40989872f1bc37c282813f3533bc11fa7f06d39df04560c5`; application receipt: `f3a699cd95b7436383e5cc012ca8788799e6049fefc2271fcb087cc210b2b986`. The worker loop and all other pre-existing production functions are AST-identical. This patch improves reporting; the separate applied C# repair still requires compilation and live verification.

Publication validation combined all 78 CPU/mock cases against exact copies of the published primary dependencies: 28 evidence, 31 sequence and 19 parent-reporting cases, with zero failures, errors or skips. The first combined attempt exposed an obsolete minimal worker fixture; a fixture-only correction then needed a name-reference fix. Both failed attempts remain preserved. The final fixture matches the current worker producer, while both production modules remain byte-identical to the reviewed versions. Frozen publication manifest: `courtyard-cli-publication-candidate-v1/source03/manifest-03.json`, SHA-256 `7dd4104924417f4537bfe6576bacc7847b326bd489b4dbc22fe666baa574f2a4`; passing receipt: `0cdbceff782412073cdf1fe2400049eafa1af1f2d51315eb8a55cfa35b7da2de`. These tests do not compile C# or operate the game.

## October 24: P2P run002 with concurrent device telemetry

The unchanged V10 production-predict experiment returned one preparation and **27 of 40 requested measured calls**, then rejected further admission after its fixed ten-second window. It remains failed/inconclusive; no full-benchmark p95 or sustained-control claim is available. The admitted last call returned at synthetic origin +10.4852426 seconds. The original 50 ms absolute schedule skipped 169 slots between calls and created no catch-up queue.

| Observed interval or subset | Saved host duration |
|---|---:|
| Runtime admission phase | 41,581.9594 ms |
| Model construction and goal | 11,908.2536 ms |
| Preparation public predict | 11,994.2204 ms |
| 27 returned calls: minimum / median / maximum | 49.2437 / 121.3498 / 3,284.6152 ms |
| Measured preprocessing: minimum / median / maximum | 0.5534 / 0.9905 / 2.7135 ms |

Only one returned call was at most 50 ms. These partial-call statistics describe the admission-limited observations, not the requested complete sample. Graph preparation reported 11,901.8614 ms in the preparation call and zero in the measured calls. Existing evidence places most time after preprocessing, but does not distinguish graph/copyback, synchronization, native decoding, scheduling or driver waits. A watchdog stack is a sampled location, not a subcall timer.

The separate collector retained 165 complete two-second rows, no unparsed tail or stderr, and cleanly retired its owned utility/readers after root stop. Twenty-one complete receipts inside runtime admission reported 98% device utilization. The longest measured call contained two receipts reporting 97% and 98%; only five measured calls contain any receipts, while 22 contain none. Receipt timing is not driver sampling time, and neither a GPU-only duration nor a cause is established. Missing receipts are not zero utilization. Device-wide values, unknown averaging/buffering and unproven CUDA/NVML UUID correspondence remain explicit limitations.

The file-only join passed 14 focused cases. Independent review rehashed 140 named files, reparsed all 165 CSV rows and recomputed 35 interval joins. Both model processes, both collector Python processes and the utility were independently absent at 22:15:29 UTC. The final input/goal/state/pointer gates were unreached after the incomplete-count failure; false completion flags do not themselves establish mutation. All original failures, seals and archives are preserved. The later V11 trace-only derivative around graph/copyback, synchronization and decoder boundaries is documented above; the original V10 sources and failure remain unchanged. Review record: `native-p2p-v10-run002-telemetry-independent-review-01.json`, SHA-256 `dab9a423f78cf897db500dda31fadb0c2178422b0b50f52d62ddae2799c23400`.

## October 24: measured walking intervals and small-heading pauses

The four accepted R45 legs also contain adjacent midpoint observations taken within one continuous held-W interval. Their source gaps are 59.0809 / 59.3504 / 61.7942 / 67.8425 ms. This describes behavior already present in R45; no new midpoint profile or improvement was executed. Return03 did pause during its wider approach: W was released outside the 1.5-unit midpoint disk, followed by already-released camera observations inside it. Its later adjacent crossing is the narrower verified result.

| Accepted leg | Recorded held-W total, ms | Returned task interval, ms | Held-W / returned task interval |
|---|---:|---:|---:|
| Return02 | 1867.5988 | 4489.6814 | 41.5976% |
| Forward02 | 2037.0693 | 5743.1077 | 35.4698% |
| Return03 | 1819.2803 | 4949.6398 | 36.7558% |
| Forward03 | 1803.2549 | 5370.9180 | 33.5744% |

The numerator sums native W-down-to-W-up software call-completion intervals. The denominator is the returned `navigationBaseline.result.elapsedMs`: task start through evidence publication, excluding enclosing owner/TaskRunner cleanup and client/broker lifetime. These are software dispatch proxies, not measured game velocity or physical acknowledgments. Return02 includes a late release after lease expiry; the separate authority-clipped analysis excludes that excess. Pre-publication `journal.workflowResult.elapsedMs` and first-input-to-input-close intervals are different denominators and are not substituted here.

Five resumed heading corrections began with only 5.5-6.5 degrees of measured yaw error and produced 618.7717-787.3516 ms release-to-next-press gaps. A sixth such release preceded endpoint acceptance and had no later press. The current rule realigns whenever error exceeds five degrees, including while W is held. A modest separate tolerance while already walking is a future experiment; new W-down alignment, corridor limits, source age, input leases and response waits must remain separately checked. No heading threshold or mouse gain has changed. Individual camera-command/next-pose pairs vary too much to infer a fixed gain from these traces.

The descriptive analysis is `r45-courtyard-midpoint-retrospective-01/report-01.json`, SHA256 `30f8b01a3a935cb52f62d60e62afe53d8d00a73f70e6039da28ed36b2986087d`. Its denominator clarification and exact field joins are `DUTY-DENOMINATORS-02.md` and `DUTY-FIELD-JOINS-03.md`. Independent source/evidence review `r45-courtyard-midpoint-independent-review-01.json` is clear, SHA256 `cdf81b893c2d676d057f3738d93e96bf6fe074bb7da6acd7a90b9fa3f21e0c4e`.

## October 24: incomplete native P2P production-predict timing

V10 run001 invoked the actual complete production `predict` method under the normal CPU-default caller context. It used the accepted V8 full history41 seed, native sampling, FP16 graph replay, unchanged production preprocessing/copyback/decode, and a repeated historical RGB192 image and goal. No action was sent to the game. One preparation call returned in 139,316.2077 ms, including 136,737.8066 ms reported graph preparation. That preparation aggregate includes eager warmups, capture, verification, synchronization and comparisons; it is not kernel timing.

Only three of the required forty measured calls returned:

| Measured call | Complete predict, ms | Internal preprocessing, ms | Synthetic schedule slot |
|---|---:|---:|---:|
| 0 | 61.0943 | 0.4410 | 0 |
| 1 | 195.8981 | 0.5724 | 2 |
| 2 | 35640.4891 | 0.4538 | 6 |

The third call began 300.1499 ms into the ten-second admission window and returned about 35.94 seconds into that window. The next admission correctly rejected the incomplete schedule. The worker exited 1 on its own with `measurement_admission_window_incomplete`; the 600-second ownership timeout was not reached. This failed, incomplete sample provides no forty-call median/p95 or sustained-throughput result. All four returned proposals, including preparation, were valid neutral actions on the repeated historical input; they do not establish gameplay quality.

The long measured interval falls after preprocessing. Two existing watchdog samples locate the host at the production post-replay/copyback `torch.cuda.synchronize()` call. The dumps lack exact UTC/call-ordinal anchors and do not identify a native CUDA cause. A separate 98% GPU-utilization sample began at 21:44:29 UTC, after the worker finished at 21:43:59 UTC and its owner at 21:44:00 UTC. It is not concurrent telemetry and cannot attribute the stall to GPU contention, temperature or memory pressure. Initial CUDA admission reported 7,450,132,480 free bytes; that earlier API result is distinct from the later device-wide sample.

Cleanup drained CUDA successfully, and launcher 37400/interpreter 55720 were independently absent at 21:46:57 UTC. Post-measurement input/state/storage and final source checks were not reached. Their false/unset completion flags are not accepted checks; the no-override implementation also does not turn an unreached restoration flag into evidence of a leaked override. The unchanged closed reader verified all 7,078 sealed files, then rejected the failed worker with `closed_worker`; no accepted audit file was produced. The separate failure analysis verified its 31 frozen local source files and retained all failed evidence. A proposed later identical run would add a separately bounded read-only device collector; it has not run at this checkpoint.

Evidence: `native-p2p-production-predict-latency-v10/run-001/report.json`, SHA256 `86ace1c095417ab47b03db3855bdf90dbf03f6fffb1d67bc503531a9fe5db004`; failure-analysis manifest `native-p2p-v10-failure-analysis-01/manifest-01.json`, SHA256 `8afef56ed817317d51260ac2b56a22793a06bc3948812cc73abf84c6edf4069e`; preserved reader attempt `native-p2p-v10-closed-audit-01/attempt-01.json`, SHA256 `12a8a99ffb52c141258c5a40972383772fc0594c6c222f6e411104b978c955c9`. The fork publication is recorded in `r45-stable-push-01.json`. R46 source10 is `desktop-dc-precompile-source-10.json`, SHA256 `1e4877348fe62a6f42288c4097093a58b2bf24435aaa3a599d62f9137609c847`; its failed verification is `desktop-dc-csharp-10-validation.json`. The image-header change and upstream package/OCR changes require fresh build/live verification, and a future R45-to-R46 timing comparison would include both changes.

## October 24: automatic route continuation and native P2P cache acceptance

The frozen R45 supervisor ran one standard-token, windowless command worker in RDP session 3. It called the unchanged native client for return02, forward02, return03 and forward03, with no reset, replay, process replacement or foreground refocus. The fixed four-leg bound ended the batch normally. All returned native owners were completed and verified, with clean reported input release. The original capture epoch, child/build, game identity and immediate predecessor chain remained bound throughout.

The native workflow intervals were 4,489.681 / 5,743.108 / 4,949.640 / 5,370.918 ms. The complete broker interval was 23,219 ms. The 63/62/78 ms inter-leg values describe a previous client terminal return through the next mutation delegation, including envelope publication/checks. A separately saved post-run clock inspection identifies Python 3.11 monotonic time as `GetTickCount64()` with 15.625 ms resolution; the worker did not record that clock metadata itself. These values neither resolve sub-millisecond behavior nor measure key-release-to-next-key-down or rendered response. The native trace uses the same child-process QPC domain for the control intervals below. Full audits occurred after the batch; admission during the batch used the unchanged native/client gates and each completed leg's immediate saved artifact envelope.

The closed trace analysis finds 185 returned reads, 184 accepted observations, 12 final normal poses and one `LeaseExpired` recovery. That recovery followed a 41.6142 ms W-down software call, a 60.8688 ms read-entry-to-capture-request interval, 27.6872 ms acquisition and 26.8796 ms recognition. The original 150 ms grant expired before admission of the resulting pose. Recorded release completion to the next W-down completion took 154.8406 ms. The underlying cause of the unusually slow input call is unmeasured; the 90.155 ms maximum recognition sample belongs to a different read.

The three inter-leg gaps use native software call-completion timestamps. They do not establish physical input acknowledgement or a rendered response. All values below are milliseconds; the first component accounts for any remaining input closure after forward-key release.

| Transition | W-up to next W-down | Remaining input closure | Final verification | Final-read end to next leg start | Initial readiness | Camera alignment through next W-down |
|---|---:|---:|---:|---:|---:|---:|
| Return02 to forward02 | 2498.9253 | 0 | 534.3355 | 500.3098 | 66.2369 | 1398.0431 |
| Forward02 to return03 | 1941.6212 | 0 | 540.3264 | 536.0612 | 85.2970 | 779.9366 |
| Return03 to forward03 | 3279.2642 | 152.0692 | 539.8290 | 637.7507 | 80.3610 | 1869.2543 |

The 500-638 ms publication/startup intervals cannot be attributed solely to PNG writing from these traces. Camera realignment includes 9, 5 and 12 calls before the corresponding first forward-key press. The current route therefore continues automatically, while movement still pauses between legs. Reducing a redundant image copy is a separate prepared optimization whose live cost and effect remain unmeasured; it does not justify relaxing freshness, release or final-verification checks.

The metric report is `r45-courtyard-batch-01-metrics-01/report-01.json`, SHA256 `c941bbcec060cce609ca0acfccfd332f7095e099c909ff0afa8f774d469b19ea`; the concise note is `SUMMARY.md`, SHA256 `e525acef1896fb4f82924bfd13e57ab18da89cca2b76444707c27e3bba39657c`. All 60 selected evidence pins matched. The separate clock inspection is `r45-courtyard-supervisor-clock-info-01.json`, SHA256 `44f04d068044e085d6359c33df8d7b3532460b53e7da806fd428728c4752abc4`. Root visual inspection of the final forward03 image shows the upright character, normal game HUD and the courtyard near the fountain; the NPC interaction prompt is visible, with no BetterGI overlay.

Evidence: `artifacts/research/2026-10-24/r45-courtyard-supervisor/runs/r45-courtyard-batch-01` and `r45-courtyard-batch-01-closed-audits/outputs`. The closed four-leg chain summary SHA256 is `25b3e265b05820a33e6534ef2712d22a8bf8d23fb97957b123b2eec3bee933d2`. The external retirement record is `r45-courtyard-batch-retirement-01.json`: supervisor 54168 and broker 14240 were absent at 21:26:45 UTC; the separately saved native postflight was idle/input off with the host minimized. The latest native run was `0930d950e4914536b4748320d963764e`.

The separate V9 GPU diagnostic reconstructed V8's actual full 492-token cache and advanced absolute indices 492 to 504 to 516. It exercised two eager calls and two graph calls, including two real 12-token evictions, native sampling, full cache update/preservation checks and the byte-bound production replay/copyback statements. All 1,125 ordered gates passed with maximum reported absolute error 0. The eager and graph compact archives were byte-identical at each step. The closed reader independently reconstructed the seed and both returned cache trajectories, matching 20 seed hashes and 40 named final hashes, with all saved decoder comparisons accepted.

V9 used the retained real RGB192 image and goal as explicitly synthetic continuation inputs. It issued zero controller calls and did not execute the complete production `predict` method. Its 77.078 seconds include preflight, instrumentation, file validation and cleanup; this is not a model latency result. Peak PyTorch allocation was 802,265,600 bytes and reserved memory was 950,009,856 bytes. Four compact archives total 3,539,118 bytes. Both final CUDA drains and temporary-hook restoration completed, the owned process returned 0, and launcher 1244/interpreter 32760 were independently absent at 21:21:27 UTC.

V9 evidence is under `native-p2p-full-cache-graph-eviction-v9/run-001`: report SHA256 `ae150d87d343bbd1ccbf289ea412bf65c72f9a3b1f4a4b21e902bb786acbbd76`. The accepted closed audit is `native-p2p-v9-closed-audit-01/audit.json`, SHA256 `fe0d3824bb8234aee399ce79eb8df48b47b0b37d08a727876fe29f2d2415ea6e`. The subsequent V10 experiment attempted complete production `predict` timing under the actual CPU-default caller context; its incomplete result is recorded above. It includes preprocessing, transfer, sampling, graph replay/copyback, synchronization and action decoding. The historical timing table below is not a measurement of that new native-history41 path. No default-history200, feedback, live quality or training claim follows from V9.

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

- Full solution restore/build and self-contained portable publish passed with the initial RDP lifecycle hooks. The package verified at that stage was `artifacts/release-r4/BetterGI-English-win-x64`, built from clean revision `b5dc287e`; its build manifest records the binary hashes.
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


## r25 live reset recovery and walking readback - 2026-10-24 UTC

The full Debug build, Release publish and normal manifest path passed from clean
commit `15a3f90f4574003ca824d76855ef97275a87b52e` in 183.58 seconds. DLL SHA256 is
`bc87da26990625c37686ad4209d621e1b199aa4217f0ac4f5fa23c8611914288`.
The 530-file tools snapshot is immutable. The saved Game shortcut replaced only
child 40720 with 36680; root 28072 remained minimized, RDP session 3 connected,
and Genshin PID 27728 retained its creation time.

Reset `9bdcfce6b57c436c8c633b2a5e4b211f` completed in 29.08 seconds with all
three verification samples. Its first retained transient was pose probe 6,
phase orienting, initial-HUD allowance false: source age 647.57 ms after capture,
including a 579.06 ms Map. That frame was discarded and the reset continued to
fresh verification. No terminal source diagnostic was logged. This directly
exercises the new later-orientation readiness path; it is one reset, not a
reliability rate or a complete game-state reset.

The separately reset v3/task-owned walking run
`9c26028c442e455e8b275d805dede083` advanced 4.063 map units through 25 accepted
observations before `native_source_unavailable_or_stale`. Accepted capture
median/max was 7.02/11.66 ms, recognition 28.01/53.86 ms, and conservative source
age 34.96/62.73 ms. All 25 same-frame chat checks were Closed. The earlier r24
diagnostic had median age 105.05 ms; this is a descriptive comparison under
uncontrolled foreground load, not a controlled causal performance estimate.

The final observation blocked in capture for 965.33 ms, including 963.08 ms Map,
then rejected its 966.27 ms-old source before recognition. The selected capture
had two pool pulls, one nonnull source and no discarded candidate. The immediate
capture-gate contention probe was false and recorded GC pause delta zero. Thus
this failure is not explained by waiting on the capture gate or by the recorded
GC pause counter; the wall-time interval alone does not attribute GPU busy time.
The walking key had already been explicitly released for realignment, 60.99 ms
before its logical expiry, with no release error. One physical hold lasted
931.33 ms; no repeated physical start was exercised. Last accepted pose remained
5.77 units from the endpoint. Owner time was 3,279.63 ms and evidence was complete;
this is a failed segment with no final verification image.

Journal SHA256 is
`bbe7aca5bff65bbc8f828709dc38fcfc094e9fc38bcf05c136bf149a9f65fed2`.
The owner, source diagnostics, image/journal hash audit and postflight are retained
in `r25-live-summary.json` and the `native-baseline-r25-01-*` records. Postflight
confirmed idle child, released input, unchanged game identity and minimized host.
The next candidate adds explicit bounded no-input recovery for timing overruns;
blocking readback remains a separate open issue. Training eligibility remains false.


## Bounded navigation timing recovery (r26, 24 October 2026)

The r25 walk exposed a timing interruption after W had already been released for camera alignment. The opt-in `timingContract=v4` now handles that sole-source-age case and known forward-lease expiry with the same persistent input watchdog. Recovery is armed only after the initial anchor and disabled before final verification. Defaults and the v1–v3 contracts retain their prior behavior.

A recovery first latches a pause and confirms release. It then reacquires fresh, increasing, same-epoch evidence with both source clocks beyond release completion plus 80 ms, including same-frame closed-chat, world, motion and route checks. Resume itself sends no input. New physical W starts retain the 150 ms allowance, renewals remain 100 ms, and the conservative source-plus-250 ms ceiling still applies. Hard target, clock, geometry, world, chat, motion and route errors remain terminal.

Each run permits at most two recovery windows, each bounded by two seconds and 32 actual capture polls and clipped to the original owner deadline. The journal retains pause tickets, distinct original pause and observed trigger causes, release timing/errors, capture/observation ranges, resumed source and failure outcomes. A resumed frame enters ordinary decision observations once; it is not double-counted by a synthetic recovery decision. Existing low-level trace completeness and training eligibility remain false. Synchronous native calls and scheduling can exceed cooperative deadlines; input authority is not extended to cover them.

Source review corrected delayed expiry release before a potentially slow target check, loss of the recovery timeout code through exception unwrapping, and duplicate observation counting. Validation passed **251 C# tests** (234 navigation/source-freshness and 17 external-control protocol) and **227 Python automation tests**, with zero skipped C# cases and unchanged source hashes. The new tests include an active watchdog surviving a pause and draining on disposal, blocked keyup with competing close/resume, hard-fault precedence, and recovery while W is already released. The maximum-count v4 journal fixture is **4,969,509 bytes**, below the **6,291,456-byte** limit. These are offline managed/synthetic and mocked transport results; live recovery remains to be measured after the full build.

Local evidence is retained in `r26-candidate-apply.json`, `r26-validation-summary.json`, the `r26-v4-focused-01` and `r26-v4-protocol-01` test logs/TRX/manifests, and `r26-python-validation.json` under `artifacts/research/2026-10-23/`.


### Live r26 recovery and remaining preparation failure

The full Debug build, Release publish and manifest succeeded from clean source `3fd75ca54511b5bf83077de4c0d26d77c829419f` in **187.953 seconds**. The approved saved Game shortcut replaced child PID 36680 with **50516** in session 3, preserving root PID 28072, Genshin PID 27728 and its creation time, and the minimized RDP window. The immutable tools snapshot contains 531 files. Upstream main was still `14537eae67c1070776a6be2fa9cf87be53d8386e` at 05:47 UTC and is already included.

| Attempt | Reset | Native v4 walk |
| --- | --- | --- |
| r26-01 | Completed with three verification poses; retained orientation probe 45 had a 930.08 ms old source and 850.60 ms Map interval, then readiness recovered | Verified in 4,847.61 ms; 50 unique decisions; 9.480 map units; final distance 0.398; no recovery pause |
| r26-02 | Failed in preparation before teleport, owner `75fb3facd6734f9bbdeb79ce9f40a484` | Not started |
| r26-03 | Completed with three verification poses; no retained source diagnostic | Verified in 5,056.02 ms; 52 unique decisions; 9.706 map units; final distance 0.202; one expiry pause/resume |

The r26-03 watchdog pause retained `LeaseExpired` as both the original and observed trigger. W release completed **5.845 ms after its expiry**, with no reported release error. The same watchdog remained active and the recovery window resumed **128.598 ms after pause start**. The new acquisition clock crossed release completion by **96.715 ms**; both source clocks passed the required 80 ms barrier. One recovery observation used four capture polls. There were four physical W starts and 32 forward grants across the whole run. All three final verification poses passed. This demonstrates one live release/reacquisition/resume sequence followed by route completion; source-age recovery during walking has not yet been observed live.

Accepted-decision source age was **35.90 ms median / 128.64 ms maximum** in r26-01 and **33.17 / 128.82 ms** in r26-03. Their capture medians were 5.95 and 6.38 ms; recognition medians were 27.64 and 26.15 ms. These are short, uncontrolled runs under concurrent foreground load, not reliability estimates or a controlled comparison with r25. The r26-01 final image was inspected and shows a normal Mondstadt world view with Traveler near the waypoint/NPCs; the menu and chat dialog are closed.

The separate r26-02 preparation failure is retained: source age **1,043.21 ms**, capture-gate wait **395.00 ms**, Map **128.34 ms**, and source already **905.49 ms** old at acquisition. The capture selected the newer of two available pool frames and showed no process GC counter increase during that call. The exact gate holder and GPU scheduling cause are not identified. Preparation still fails immediately on this age-only condition; bounded preparation readiness is the next isolated change.

Evidence is in `r26-build-outcome.json`, `r26-hot-replace.json`, `r26-live-summary.json`, and each named trial's owner, analysis, image and journal files. The r26-03 journal SHA-256 is `5e7588e3235b970ae5157b74aafcfc5876de0745df2f60486b0cc171608e1ffb`. The v4 analyzer passed 24 CPU fixtures and independent review, preserving r21-03/r25-01 analysis fields. Absolute owner-deadline clipping and per-check OS target identity are explicitly unmeasured in the journal; input call completion does not prove OS/game acknowledgment. Training eligibility remains false.


### R27 bounded preparation readiness

The r26-02 failure occurred before teleport, outside the existing post-teleport pose wait. R27 adds a separate **3-second / 25-probe preparation window with 120 ms spacing** after the one-time waypoint/map warmup. It remains inside the original 75-second reset owner. Each synchronous probe checks the pinned target, source metadata and geometry, then the existing strict world recognizer. Only the typed sole-age outcome can wait again; the freshness threshold stays **500 ms**. A provisional capture epoch is pinned from the first valid header, and actual source regressions, changed geometry/generation, malformed/future acquisition clocks, hard world errors and cancellation remain terminal. Identical cached old sources may be discarded without receiving new timestamps. The epoch is committed only after fresh readiness and the final monotonic deadline check.

The helper owns no detached capture task. A slow native call can return after its cooperative window, but cannot admit late success or authorize teleport. Only cancellation carrying the exact expired window token is translated into the preparation timeout; owner cancellation and unrelated native exceptions keep their original behavior. Existing pose acquisition and the timer's preparation chat guard are unchanged; this patch adds no direct same-frame chat recognizer to preparation. Diagnostics remain bounded to one transient and one terminal source record, with the nullable v2 `PreparationAcquisitionOrdinal` distinct from pose ordinal/HUD settling.

**199 focused C# tests passed with no skips**, including 23 preparation cases, reset workflow/source/capture-policy coverage and shared source freshness. Source hashes remained unchanged during validation. Cases cover stale→fresh admission, finite failure with no teleport, caller/native cancellation, misleading exception text, changed geometry/epoch/clocks, late synchronous readiness and mandatory cleanup. Seven disposable apply-guard fixtures passed. The ignored reset analyzer passed 14 CPU tests; seven historical r23–r26 runs retain exactly equal outputs under its old and updated helpers. The analyzer's producer/schema hashes still match the applied candidate; its recorded helper hash predates the final exact-token cancellation refinement, which does not change that schema. Subsequent packaging and live observations are recorded below.


### R27 package and live check

Full Debug build and Release packaging succeeded from `907a160997035b3969c5ef54941f4ac22ba0e022` in **184.781 seconds**. The approved shortcut replaced child PID 50516 with **30852**, retaining the root, original Genshin process and minimized session. Reset `c68c075be2a240eb88fa9e977d736e4b` completed with three verification poses and no retained age diagnostic. This validates the deployed normal preparation path; its retry branch was not exercised live in this run.

Walk `26186aae58bf4a8180fcfd45c5528e2a` ended **unverified** after 4,805.84 ms, 48 accepted observations and 29 forward grants over three W holds. All W releases completed before expiry without reported errors. It reached a measured endpoint distance of **1.136 map units**, released input and collected two valid final poses. The third final read then reached **152.616 ms source age**, exceeding the unchanged 150 ms limit after a 17.04 ms capture and 45.37 ms recognition phase. Final verification currently permits no age-only waiting, and the movement lease is already terminally closed there; no recovery pause occurred. A separate bounded read-only final-verification wait is under design and must never reopen input. This result is not a completed route or a regression attribution to the preparation patch.

Evidence: `r27-build-outcome.json`, `r27-hot-replace.json`, `r27-live-summary.json` and the named trial artifacts. Journal SHA-256: `b0daa4a0104984fe33a36a7cad59f88707942896cf49c7f51a4c899bd263cf5f`. The required third pose was not inferred from the two available samples. Training eligibility remains false.


### R28 dispatcher collection and captured-frame ownership

Removed the dispatcher's unconditional full `GC.Collect()` every two seconds. Its old `finally` block ran even when a tick skipped its lock, inference was paused or a task suppressed timer capture, and collection time fell outside the processing metric. Automatic .NET collection remains enabled. The selected long WGC Map calls showed zero collections, so this is removal of an avoidable process-wide pause source, not an explanation or promised cure for those capture stalls.

The acquired `GameCaptureFrame` now enters a `using` scope immediately, covering exceptions in preview or region construction before `CaptureContent` takes ownership. Existing native and resized Mat ownership remains intact. **76 focused C# tests passed, with zero skipped and unchanged source hashes**, including eight new actual OpenCV/WGC ownership cases and the real inert dispatcher regression. Candidate-application guards previously passed seven disposable CPU tests. No capture backend, trigger, input timing gate, other explicit collection call or GPU setting changed.

Full Debug build, Release package and matched five-minute input-disabled capture/memory observations are pending. Memory evaluation will report private-byte/workingset trends and capture-source timing with process/session/build identities. Managed heap/GC counters are unavailable through the current read-only endpoint; process memory is not an exact native/GPU allocation measure. Bounded reusable pixel pools and live image queues must not be mislabeled as leaks. Source audit and candidate/test evidence are under `artifacts/research/2026-10-23/dispatcher-gc-ownership-audit-r27.md`, `r28-dispatcher-gc-candidate/`, and `r28-dispatcher-focused-01-validation.json`.

### GameScaling cached-block parity probe

One offline GPU probe used the installed environment, fixed inputs and strict `rtol=atol=0.001` gates. The original 30-token eager response matched the established sequential graph response exactly. Repeated full prefill, state restoration, repeated sequential graph and single-token eager/graph controls were bitwise exact. The first **two-token cached block failed**: logits differed by up to **0.029296875**, and 29 cache tensors also exceeded tolerance. Matching next-token IDs in those two positions do not establish equivalent actions or future cache behavior. The run stopped before four-token blocks or later images; production decoding remains unchanged.

No OOM occurred; peak PyTorch reserved memory was 2,688 MiB. The run included initialization, controls, comparisons and evidence compression, so elapsed wall time is not inference latency. Report SHA-256 is `d93c30bedef6f8e986aa3d3bd800c7722aab23ba33958969dd5e5dc1dd41b3a0`; failure NPZ SHA-256 is `041c83104224246a1595664117ab2623b60b1642e6c21cb35f5060b4fbe0ad01`. Evidence and CPU analysis are in `gamescaling-draft-parity/run-001/`. A source-only audit of fewer host synchronizations while preserving single-token numerical geometry is the next investigation; no speedup is established.


### R28 package, overloaded capture and measurement limits

Full Debug build and Release packaging succeeded from `6055bb11aa37ce3f484bc4ab4a88127c3997d0ce` in **185.953 seconds**. The approved shortcut replaced only the child with **PID 37960**, preserving root PID 28072, Genshin PID 27728 and the minimized RDP session.

The planned matched memory comparison could not start. Its fresh r27 warmup reset (`a07bfe9ed4854082bee47564f2cf1990`) saw 2,100/3,507 ms source ages and exhausted the new preparation window after two synchronous calls. This exercised the typed preparation retry/timeout without teleporting; a native call returned after the cooperative three-second budget and was rejected. Capture-gate waits were 408/2,547 ms and Map waits 472/843 ms. Concurrent process-wide GC pause deltas were 24.409/24.754 ms, which do not account for those multi-second intervals or identify a collecting caller. A separate ten-second input-disabled observer received two usable frames. Neither paired memory arm ran.

After replacement, r28 reset `f1fd19369c7e462a91ce616a9e6a838a` completed with three poses despite one retained 774.517 ms orientation-source transient. Walk `bc56da01030f4a0ea4730f061d9f2f92` ended **unverified** after 10,040.66 ms and 42 accepted observations, last observed 2.222 world-coordinate units from the endpoint. All three W releases completed 31.9–37.0 ms before expiry, without errors. W was already released when a 3,482.77 ms capture caused a typed source-age pause; the next two captures took 1,684.64 and 997.19 ms, and the two-second recovery budget expired without resuming input. The final native call returned 718 ms after that cooperative recovery deadline. This is live evidence of the no-W source-age pause/failure path, not a successful recovery or a route completion. The evidence journal and initial image hashes were verified; no final-verification image exists because the run failed before that phase.

The first standalone r28 capture/memory attempt then failed **before sampling**: the ordinary RDP worker could not open the cross-session root process even with query-limited access. An exact three-process read-only probe confirmed child/game handles and memory counters work; only the root handle was denied. The next harness revision will retain root identity/liveness through its already-authenticated PID/session/nonce/assembly API checks while keeping native handles for child/game. It will preserve all original failed evidence and create a new versioned plan. No memory trend, paired speedup or leak-freedom result exists yet.

Evidence: `r28-live-summary.json`, the named trial artifacts, `r28-memory-comparison-precondition.json`, `capture-memory-r28-01/` and `r28-process-query-probe.json`. The root, game and foreground-desktop separation remained intact. Current results support further capture/recovery work; they do not support unattended quest completion or training-data eligibility.


### R29: fresh final evidence after permanent input closure

The r27 trial reached the endpoint with two acceptable final poses but rejected its third image at 152.616 ms. The v4 controller now permits one separate final collection window after successful permanent input close: at most two seconds from that close, clipped to the original 30-second task deadline, and at most 32 native reads/32 capture admissions. A validated age-only rejection may wait for another source; the 150 ms source limit, fixed close-plus-80 ms barrier and every known non-age source/pose gate remain unchanged. Three accepted samples retain their existing endpoint, spread, yaw, distinct-source and acquisition-spacing gates. The window sends no input, cannot reopen the lease, and does not consume or reset movement recovery tickets.

The native path holds candidate image ownership locally while preparing private sample/decision rows. It rechecks target, permanent closure, cancellation, prefix, source age and deadline before committing those rows and the matching image identity. A rejected image is disposed without replacing earlier accepted evidence. File-only policy version1 and one bounded window record join accepted/discarded reads to the original observation/poll arrays; no pipe framing, CLI option or default timing contract changes. A failed run may retain a valid partial prefix. V1–V3 and the initial v4 anchor remain unchanged.

Independent source review and **257 focused C# tests passed**, including 46 new deterministic cases and the existing maximum-capacity 6 MiB journal test. The new fixtures replay the 152.616 ms third-read rejection followed by a fresh fourth read; cover hard-error priority, permanently closed input, callback delay, cancelled/late work, image/row admission and bounded failure; and preserve legacy branches. Test sources stayed hash-identical during execution. These are offline tests, not live recovery evidence. The required full Debug solution build, Release package and live evaluation are still pending at this entry.

R28's selected slow-capture diagnostics further locate 3,480.572/1,682.176/993.757 ms inside the readback Map interval, with no capture-gate contention and process-wide GC pause deltas 4.703/0/0 ms. These are wall intervals, including possible scheduling/driver delays, rather than GPU-kernel attribution. A default-off nonblocking readback design is the next capture investigation; it does not justify increasing freshness thresholds.

### R29 package and verified live route

The full Debug solution build and Release package succeeded from clean source `39ee3f13efcf480986001098de1630982013d6e3` in **207.016 seconds**. The saved Game shortcut replaced only the RDP child with PID **53176**, preserving the root, minimized session and original Genshin process/creation time. The immutable tool snapshot contains 531 files; the deployed DLL SHA-256 is `01ec84e50e59c64b0e0d4dd95192c74d126c4ca555bb9cd4fdc8e1c94252a142`.

Reset `bfc5433f72d9424db27c9c021e1196d2` completed with three poses after a retained **911.666 ms** preparation-source transient; its Map interval was 592.690 ms. This supplies live evidence that the preparation wait can discard stale evidence and subsequently complete. The independently reset v4 walk `51bd192e730a441dbd7aec0c5b8bbf98` then **verified in 4,825.562 ms**, using 51 unique accepted observations, 31 forward grants and three physical W starts. All releases completed 29.176–46.497 ms before expiry without reported release errors. No movement recovery pause occurred.

The final window completed 452.552 ms after permanent input closure, with three accepted reads and eight actual capture polls. There were **zero final age discards**: this run validates the deployed normal final-admission path, not the new age-retry branch. All three required poses were retained, with final endpoint distance **0.783 map units**. The final image was inspected and shows Traveler in the normal Mondstadt world view near the waypoint/NPCs with chat and menus closed. Postflight confirmed idle child, unchanged game identity and minimized host.

The frozen r29 analyzer passed 50 CPU fixtures and preserved eight historical analyses. The live owner/journal/image hashes and source/closure joins passed its represented checks. Evidence is in `r29-build-outcome.json`, `r29-hot-replace.json`, and `native-baseline-r29-01-*`; journal SHA-256 is `2b82a6b3bda634fe1ca38a98578ddf3582ea89aab8239e16c48ad4eb8a436a59`. Absolute owner-deadline clipping, physical OS/game input acknowledgment and independent pixel-to-source correspondence remain outside the journal's proof. This short uncontrolled success is not a sustained reliability result; training eligibility remains false.

### Shortened r28 capture/memory observation

The revised input-disabled observer used native handles only for the child/game and the authenticated status endpoint for the cross-session root. It retired after **224.500 seconds**, before the planned 330-second warmup-plus-measurement window, because recorded source age reached the 2,000 ms stall bound. It made zero input proposals. The warmup-excluded data contain 194 memory samples, 5,835 frame replies and 4,466 unique sources. The child stream finished with input disabled and no running stream; the worker retains its non-null error and repeated after-retirement observer error.

Private bytes spanned **6.934 MiB** over the observed measured samples, with descriptive slope +0.753 MiB/minute. This is **inconclusive**: no paired r27 arm ran, the intended observation duration was incomplete, and process memory does not distinguish pools, trimming or leaks. Unique-source first-receipt age p95 was 57.924 ms, while **all-reply age p95 was 686.861 ms** and maximum 2,031.601 ms. Repeated pixels continued aging; first receipts alone understate that stall.

The preserved original `last120Seconds` field actually selects the planned final window beginning at 210 seconds and contains only 14 samples. A separately versioned derived report labels that scope explicitly and adds the observed trailing window `(104.469,224.469]`, containing 120 samples. It passed 15 CPU fixtures, reproduces the old numerical fields and preserves eight original input files byte-for-byte. Evidence: `capture-memory-v2-r28-01/`, `capture-memory-v2-r28-01-analysis.json`, and `r28-memory-observed-window-analysis-01/`. No memory-pass or leak-free conclusion is assigned.

### GameScaling single-token feedback correctness

The alternative feedback scheduler preserves the original single-token graph shape. It checkpoints state, overlaps an unchanged next replay with the host's token decision, and restores the exact checkpoint when the token ends the response. One frozen three-image GPU probe completed all **33 strict parity gates**, including complete output IDs, parsed action, full terminal cache/logit/scalar state, repeated execution and captured storage preservation. All six candidate passes were bitwise exact to their controls. The earlier failed block/prefix variants remain preserved and disabled.

Every case produced a 30-token no-op response. This establishes correctness only for those fixed inputs; it provides no gameplay-quality result. The instrumented full-action intervals were 24.44–85.07 seconds under concurrent foreground rendering and partial CPU-build overlap. They include checkpoint/copy/extra-forward/drain costs and have no matched original timing arm, so they establish **no speedup**. A separately prepared matched comparison is required before any production decoding change. Evidence: `gamescaling-single-token-feedback/run-001/`; report SHA-256 `959ce6b283243f9b054b4e30e302edab00170d8b0fff13ee7a10b654ddf94734`. Production defaults remain unchanged.


### R30 explicit single-slot GPU readback

WindowsGraphicsCaptureV2 now has an explicit `poll_single_v1` mode alongside the default `blocking` mode. The polling path owns one existing staging resource, performs one nonblocking Map check per busy poll, and returns typed Pending metadata without inventing pixels or a new source identity. A completed readback may submit one successor after publishing its own pixels. Generation, geometry, stop/drain, exception and native-resource ownership rules remain explicit; other GPU/driver calls can still block. No live latency improvement is claimed before measurement.

The stream, dispatcher, native reset and native baseline now distinguish Pending from unavailable capture. Pending cannot refresh an input lease, create a pose or advance accepted-source authority. Existing source-age, cancellation, recovery, final-verification and total-task bounds remain in force. Control capability version 1 advertises the exact supported values, and mode selection checks persisted configuration separately from the actual attached backend. Omitted control options select blocking with the legacy request shape; explicit readback selection requires V2 and an idle child.

All **511 focused C# tests passed**, with zero skipped and all 38 measured source-file hashes unchanged during the run. The initial integrated suite exposed two test import errors, a mixed real/synthetic source-clock fixture, and a real journal-capacity regression. The fixture now uses one clock domain. Journal serialization preserves the four original signed RECT edges while omitting redundant Vanara aliases; the fully populated polling fixture is **5,868,475 bytes**, below the unchanged **6,291,456-byte** ceiling. Pending and Ready-refill geometry are asserted in the actual serialized journal. Forty-eight CLI checks also passed against the exact production client; earlier failed evidence remains retained.

Evidence: `r30-combined-candidate/`, `r30-integrated-source-01.json`, `r30-readback-focused-05-validation.json`, `r30-readback-focused-results/r30-readback-focused-05.trx`, and `r30-readback-control-candidate/cli-validation-02.json`. Full Debug/Release packaging, isolated child replacement, input-disabled blocking/poll observations and independently reset live routes are the next validation stages. The root RDP host and game process remain pinned throughout those operations.

### R30 package and standalone polling observation

The full Debug solution build and Release package succeeded from clean source `9db4294568036e7ba428b12d854ed4c1769881e8` in **192.187 seconds**. The approved Game shortcut replaced only the child, from PID 53176 to **37068**, retaining root PID 28072, Genshin PID 27728 with its original creation time, and the minimized RDP session. All 532 archived tool files and the deployed binaries were verified; DLL SHA-256 is `27e42a95df9e1bf5703e52cc8bc4930fd8907043ebeffdfd93823e7a867c28f5`. Source was pushed to the fork.

The input-disabled blocking observation stopped during warmup when source age reached **2,010.445 ms**. Its first published capture took **2,080.200 ms**, including processing rather than an isolated Map interval. The complete 35-row journal contains zero measured samples; producer retirement and parent idle cleanup completed. The retained after-retirement error repeats that observer failure and does not indicate an unretired thread. This is an incomplete blocking arm, so it cannot support a paired speed comparison.

After an explicit idle mode switch, the separate polling observer completed five seconds of warmup plus **30 measured seconds**, with zero input proposals. Of 900 measured frame replies, **326 carried newly observed sources** and 574 repeated retained sources: about **10.87 distinct updates/s** at a 30-request/s observation cadence. New-source first-receipt conservative age was median **75.631 ms**, p95 **92.841 ms**, maximum **94.616 ms**. Across all replies, age was median **107.094 ms**, p95 **183.287 ms**, maximum **246.835 ms**; repeated pixels continue aging. Successful unique-source capture calls were median **6.048 ms**, p95 **7.431 ms**. These are source/host timing proxies, not rendered-frame latency or isolated GPU-kernel measurements. Pending telemetry did not create new pixels or renew input authority. The final child was idle with input disabled, and the root remained minimized.

Between those observations, poll-mode reset `ed71b18d41e342808ac920d8d4b37ad0` failed during teleport preparation; no navigation baseline began. Logs identify three `Screenshot failed after multiple attempts!` errors in the legacy map/layer capture path. That helper projects typed Pending to null and makes only four capture attempts with three 30 ms sleeps. Roughly 11.7 seconds of the 16.1-second reset were map-feature loading, so the reset duration must not be attributed entirely to readback stalls. The legacy logs do not distinguish Pending from actual Unavailable on each failing call. A subsequent input-disabled image confirms the game remained on its **big map**; the completed polling observation therefore measures this map scene, not world-view movement. A bounded, cancellable teleport-only Pending integration is the next fix; controller freshness limits remain unchanged.

The standalone observer was separately versioned and independently reviewed, with **37 CPU/file checks** and unchanged original evidence. It admits only the proved terminal blocking freshness failure and explicitly marks paired comparison ineligible. Evidence: `r30-build-outcome.json`, `r30-hot-replace.json`, `r30-readback-blocking-observe-01/`, `r30-readback-poll-standalone-observe-01/`, `native-baseline-r30-01-*`, `r30-poll-scene-01.*`, and `r30-live-evidence-01.json`. Poll journal SHA-256 is `ef032e53347e28c19864559b74f800fb15fe56f95c144c9b2fb8ff5feb0b3a38`. This is capture integration evidence, not a completed poll-mode route or training-ready gameplay.

### GameScaling matched feedback timing

The frozen matched test completed **12 measured calls**, six per arm, in balanced ABBA/BAAB/ABBA order across three saved images. Both paths used the same installed GPU environment, FP16 model, 384-wide image processing, full 834-token prompt, zero history and unchanged greedy/EOS limits. Timings include preprocessing, prefill, decoding, action parsing and a symmetric final GPU drain; the feedback arm also includes all checkpoint, speculative replay and restoration work. All complete token IDs, parsed actions, terminal state and captured-storage gates passed.

The existing decoder's full usable-action latency was median **728.24 ms**, p95 **752.51 ms**. Strict feedback was median **781.38 ms**, p95 **809.32 ms**, slower in each paired image mean and **52.32 ms / 7.15% slower overall**. First-token host-available medians were 247.43 and 255.99 ms respectively. This variant remains disabled; the measured overhead does not justify promotion. All responses were the same 30-token no-op, so this test establishes no instruction-following or gameplay-quality advantage. Six samples per arm and uncontrolled background load limit generalization. Evidence: `gamescaling-feedback-latency/run-001/`; report SHA-256 `5369f4e7556e9dfa7d02c9e5466338a566092888b45dbb74934e4011a80997d1`. Production eligibility remains false.


### R31 bounded teleport polling and two-leg integration

The reset teleport path now explicitly consumes typed Pending results on an already selected `poll_single_v1` backend. One acquisition has a two-second/200-call bound with cancellation, target, capture-state and mode checks before and after native work. Actual Unavailable outcomes retain the existing four-call allowance; malformed Pending metadata and terminal context/deadline failures propagate through map and loading-screen helpers. Ordinary legacy captures and the controller's 150 ms source-age limit are unchanged. Synchronous native calls remain cooperative: late results are rejected after return, rather than claimed preemptible.

The new explicit `mondstadt-city-two-legs-v1` route uses the first three pinned shipped points, with v4 and `task_owned_timer` required. Both legs keep one owner, input lease/watchdog, source history and global 30-second/read/poll/input/recovery budgets. At the midpoint, a nonterminal release holds input off while three fresh stable checkpoint poses and a fourth distinct next-leg anchor are verified. This read-only window is bounded by two seconds/32 reads/32 captures and the original workflow deadline. It cannot reopen failed input or create movement recovery. Only the second endpoint uses the existing permanent closure and final verification. Partial first-leg completion never means overall success.

All **566 focused C# tests passed**, with zero skipped and all **46 pinned source/dependency files** unchanged during the final run. Coverage includes 33 teleport cases, 36 waypoint-lease cases and the two-leg workflow/wire cases. The actual maximum-count two-leg polling journal is **5,901,334 bytes**, below the unchanged **6,291,456-byte** bound. Compact status is **1,770 bytes** and the dedicated full result is **12,599 bytes**, within the unchanged 8 KiB/32 KiB limits. Integration found and fixed a real full-response nesting failure: only outgoing response serialization now permits depth ten; request parsing and replay fingerprints retain depth eight. The test verifies that checkpoint motion evidence survives serialization. Earlier constructor/test-type/GUID fixture failures and raw outputs are retained.

The frozen CLI candidate passed 42 CPU checks; its file-apply guard passed five. The separate two-leg live helper passed 20 mocked checks and requires an exact successful same-build/same-child single-leg proof before its one reset and one route attempt. The independently reviewed two-leg file analyzer passed 37 synthetic fixtures and three synthetic CLI checks; it accepts only the new route and does not infer OS/game acknowledgment or training eligibility. Evidence: `r30-teleport-pending-candidate/`, `r31-two-leg-candidate/`, `r31-integrated-source-04.json`, `r31-navigation-focused-04-validation.json`, `r31-navigation-focused-results/r31-navigation-focused-04.trx`, `r31-two-leg-helper-validation-01.json`, and `r31-two-leg-analysis/validation-01.json`. Packaging and live results follow below.

### R31 deployment and R32 map recovery

The full Debug and Release r31 build passed in **163.875 seconds** from clean revision `aa5f660a663c9bb6ce713145b7eee11545a265a7`, which was pushed to the fork. The approved Game shortcut replaced only the RDP child, from PID 37068 to 18688. Root PID 28072, the original Genshin PID 27728 and its creation time, minimized RDP hosting, and selected `poll_single_v1` capture were preserved.

Reset `7e9ad790f255412889506c7f6ca69560` then failed during **preparing**, before teleport or walking, with `world_not_ready; evidence=HudMissing`. Most of its 11.76 seconds were map-feature warmup. A later input-disabled screenshot showed the big map still open; it is not the unretained failing frame. No pose samples or source diagnostics were retained, so the run cannot establish whether Pending captures occurred. Cleanup left the child idle, with its stream stopped and input disabled. The reset analyzer passed four checks and eleven historical byte comparisons. Consolidated evidence is `r31-live-evidence-01.json`, SHA-256 `68f603fd6851e06347a16d43f3382279b550a3885c4676981705ca9b9e948a6b`.

The r32 change adds one map-close attempt inside the existing post-warmup **three-second/25-probe** preparation window. Positive map markers and the close button, directly closed chat, no recognized modal, valid source metadata, and the unchanged **500 ms** source-age bound are required before Escape. Explicit key-up runs after an attempted dispatch, including failure. Completion requires a distinct same-epoch source beyond the existing **80 ms dual-clock** input-response barrier and a recognized world HUD. Missing HUD alone never authorizes Escape; post-Escape settling still rejects chat and modal evidence. The 75-second reset owner and 150 ms controller freshness limit remain unchanged.

All **601 focused C# tests passed**, including 35 new recovery cases, with zero skipped and **57 pinned source/dependency files** unchanged. The candidate also passed independent source review and four isolated file-guard checks. Evidence: `r32-reset-map-recovery-candidate/`, `r32-integrated-source-01.json`, and `r32-navigation-focused-01-validation.json`. Full r32 packaging and actual map-template/live recovery acceptance remain unverified at this stage.

### GameScaling stateless feedback result

A separate finite experiment removed checkpoint/restore work from successful history-zero, prefix-disabled calls, while retaining the original decoder as the control. All processed inputs, complete token IDs, parsed actions, next-prefill reset state, termination controls, and cache-rebuild controls passed: **40 adapter calls plus four eager controls**, including 12 timed calls. Terminal-state parity was intentionally not established; errors quarantine the candidate instance.

The original full usable-action latency was median **736.33 ms**, p95 **743.34 ms**. Stateless feedback was median **753.01 ms**, p95 **770.03 ms**, with a **21.43 ms / 2.92% mean regression** and slower means for all three paired images. All timed responses were 30-token no-ops, so this does not establish gameplay quality. This run is separate from the checkpoint/restore experiment above; their samples are not pooled. The production decoder remains unchanged. Evidence: `gamescaling-stateless-feedback/run-001/report.json`, SHA-256 `b1eeb2f940da45c3505342b7d292ccf977269d8a2b9326890e6f3633670ee215`, and its `analysis-01.json`.

### R32 live recovery, verified short route, and reset failure

The full Debug and Release build passed in **169.375 seconds** from revision `788123ba2935f3de951e3d8c1918443663872462`, now pushed to the fork. The approved Game shortcut replaced only the RDP child, from PID18688 to PID16792. Both saved postflights retain root PID28072/session2, the original game PID27728/session3 and its creation time, the minimized host, and configured/effective `poll_single_v1` capture. Streams were stopped and agent input disabled after each attempt.

Reset `d057f2619675430f82c82d73aacec3cf` completed, and its bounded map-close diagnostic recorded `WorldVerified:true` with no dispatch or release error. This is visual world-readiness evidence; `InputAcknowledgment` remains false. The following single-leg run `368ad1423fec46dfab4b9fd106d8453f` completed and verified in **6217.80 ms**, with **50 observations**, complete image/journal evidence, and a final endpoint distance of **0.48794 map units**. Its final image shows the character near Mikhail with the dialogue prompt visible. The saved image is the verified endpoint of this trial, not a claim about the later current game state.

The single-leg result unlocked one same-build two-leg attempt. Its reset `c02a22b8876a43cfa1ac7df13dc42665` failed during final verification: `pose_acquisition_timeout; attempts=22; elapsedMs=3005; last=pose_source_stale; stage=after_recognition`. The two-leg route was **never started**. In this path, that stale-source result means the conservative source clock exceeded the unchanged **500 ms** age ceiling; duplicates and the 80 ms post-input barrier fail earlier with different outcomes. The last failed probe's capture/recognition/check timing was not retained, so this result cannot identify whether capture delay, recognition, scheduling, or their combination caused the overrun. A narrow diagnostic change is being reviewed before another live attempt; freshness, polling cadence and input authority remain unchanged.

The consolidation verified the 601-test TRX, both postflights, original process identities, and exact PNG/journal hashes. Evidence: `r32-live-evidence-01.json`, SHA-256 `502a2096a269eece37e96378b42e9237670647c9910f7d18f9a5cfada25ef394`. These are bounded native-controller trials, not human demonstrations, complete low-level input acknowledgments, or training-ready data.

### Instruction-quality and isolated GPU-kernel execution checkpoints

All three exact quality goals were encoded offline on CPU with the original cached EmbeddingGemma encoder; upstream token and embedding parity passed. The frozen quality plan uses the same two native screenshots and instructions for P2P sampled, GameScaling sampled, and GameScaling greedy, with complete unfiltered action scoring and independent eager/repeat controls. The first P2P arm completed six warmups and 96 scored calls, then failed at its first eager control: the harness called temporal-cache rollback outside `torch.inference_mode()`. The process exited and the instance was quarantined. **No instruction-quality comparison is eligible from that run.** Its unmodified report is `instruction-quality-native-execution/p2p-sampled-001/report.json`, SHA-256 `2ea37c8e4ec5bc994b54662122f61cc977c2daa54e7bd343b85bff484c9b79d2`. A separate v2 harness fixes the scope and adds rollback regression checks; the evaluation plan, thresholds and goals are unchanged.

The independently reviewed recurrent-GDN synthetic probe also ran once. The exact pinned Triton Windows3.2 wheel was downloaded and extracted into a separate workspace directory; the working Python environment was not installed into or modified. Torch2.7.1+cu128, Triton3.2.0 and SM75 were detected, but compilation stopped because Triton's bundled-compiler and CUDA discovery used the environment's installation directory instead of the isolated extraction. No candidate kernel returned, and zero numerical/graph rows completed. The owned worker/job retired. This establishes neither kernel parity nor a speed improvement. Original evidence is retained under `gamescaling-recurrent-gdn-triton/runs/run-001`; a child-process-only toolchain-path fix is under review, with the kernel and numerical gates unchanged.

The separate reviewed v2 launcher supplied the verified bundle's `CC` and `CUDA_PATH` only to its owned child. Run002 then **passed all 104 numerical and input-preservation rows, including 96 CUDA-graph rows**, at the original `atol=1e-3, rtol=1e-3` gates. Every output element and full FP32 recurrent state was checked; graph pointers remained stable and graph replay matched candidate eager execution exactly. The original oracle, kernel, workloads and thresholds were unchanged. The worker/job retired successfully, with no stderr output. This establishes finite synthetic compatibility on this machine, not full-model parity or an inference speedup. Report: `gamescaling-recurrent-gdn-triton/runs/run-002/report.json`, SHA-256 `d71c5c32d615fb2cc9b8b6c4c14c4d86cf14993220f92e86879a8c865f76b70f`. A separate full-model parity experiment is being prepared.

### R33 timeout evidence implementation

The reset now retains bounded metadata for the current pose probe and, when that probe is interrupted, the last fully returned probe. Capture completion, recognition, actual source-age checking and timeout emission have separate clocks. Pending metadata cannot be mistaken for returned pixels, and an earlier probe cannot supply the interrupted probe's source. Completion is recorded after native frame disposal; a returned sample does not imply the acquisition deadline accepted it. Any pose-acquisition timeout can use the existing terminal log slot, even if the transient slot was consumed during preparation.

This change preserves the one-transient/one-terminal log budget, original capture/source predicates, recognition/input ordering, 500 ms reset freshness, 80 ms response barrier, three-second/25-probe/120 ms acquisition policy, and 75-second reset owner. It adds no retry, input authority or pixel storage. Both source reviews were clear. All **614 focused C# tests passed**, including 13 new cases, with zero skipped and **69 source/dependency hashes unchanged**. Evidence is `r33-navigation-focused-01-validation.json` and the matching TRX. Full r33 packaging and live diagnostic acceptance remain outstanding at this checkpoint.

### Completed matched instruction-quality comparison

The separate v2 execution completed all **252 scheduled calls**, including **198 scored outputs** and **36 eager/repeat comparisons**. All three processes exited successfully, all control comparisons passed, and an independent file-only review confirmed the schedules, seed pairing, source/goal pins and report hashes. The comparison is eligible as this finite offline test. It is not a live-game or training-data result.

Whole-chunk compatibility with the unchanged strict rubric:

| Saved scene / instruction | P2P sampled | GameScaling sampled | GameScaling greedy |
|---|---:|---:|---:|
| Initial / stand still | 6/16 | 7/16 | 1/1 |
| Initial / interact only if F is visible | 4/16 | 7/16 | 1/1 |
| Initial / step backward | 2/16 | 0/16 | 0/1 |
| Final / stand still | 7/16 | 9/16 | 1/1 |
| Final / interact only if F is visible | 0/16 | 0/16 | 0/1 |
| Final / step backward | 1/16 | 0/16 | 0/1 |
| **Total** | **20/96** | **23/96** | **3/6** |

An always-no-op policy scores **50%** on these six equally weighted cells: it satisfies both stand-still cells and the initial scene's absent-prompt instruction. Greedy GameScaling emitted six no-ops and exactly matched that baseline. On the three cells requiring an action, P2P scored **3/48** and sampled GameScaling **0/48**. Neither sampled arm emitted F for the visible-prompt instruction. All 198 scored outputs were structurally compatible, with no incomplete/invalid output; structural validity alone does not establish instruction correctness or controller admission.

These are two cold-history scenes with 16 paired seeds per sampled cell, different native preprocessing/conditioning, and 50 ms versus 200 ms action horizons. The small F cue and cold history limit generalization. The instrumented call durations are not latency benchmarks. The comparison's inherited planning-limitations list still describes some processor/runtime evidence as deferred; the actual v2 execution supplies those processor tensors, geometry and runtime/weight pins.

A subsequent read-only contract audit found no dropped goal or missing F vocabulary: P2P's actual goal tensors match the encoded artifacts, F remains available, and it even appeared once under a stationary instruction. All 138 GameScaling prompts match the official template with the intended goal and F binding. Its outputs completed in 30–34 tokens, below the 64-token cap. History zero, reduced image resolution and disabled reasoning remain plausible factors rather than established causes. A literal F command and a separately collected genuine history sequence are the next separating tests; no fabricated history or training claim is made.

Evidence: `instruction-quality-native-comparison-v2-01.json`, SHA-256 `db8fce339ac33740030a600220d89bbbcf5445f2b94855359ee7326b0539e3df`; `instruction-quality-native-v2-contract-diagnosis.json`, SHA-256 `05feae71b7b9af7638b0d643a69f46790cc25ca0a01bd5556f9da360f7399bfb`. The original failed v1 run remains preserved.

### R33 package, verified short route and final polling exhaustion

Full Debug validation and self-contained Release publication passed in **207.282 seconds** from clean source `9a1757abacf1a8cb7c2d38f3ac768123aa0ae120`, which was pushed to the fork. The build manifest hash is `a1335e6fa2cb8c7d83d7a18ce86448e2e226f5d812b891b1ad270f28014ebbdf`; the published DLL hash is `5e4aab5e9e1da92eba050231d3ba503b51813bcefa360b455cab56e0094d0f0d`. The 533-file tool snapshot has manifest hash `817b3fe03d3218ad9c5b6a325634836e020277eb5ae00fb1e00504a76ca6dc4c`.

The approved saved launcher replaced the RDP child with PID **35412**, nonce `eed1621a9b69466798ec9bbfd15cd7e4`. Root PID28072/session2, Genshin PID27728/session3 with its original creation time, the minimized RDP host, and configured/effective `poll_single_v1` were preserved. Both recorded postflights completed without error.

Reset `1b6700b889874311bfda441580d318eb` completed with three verified samples. Single-leg run `a4e02f3f541f4bdca57ddfd540a4e7be` then **completed and verified in 5807.26 ms**, with 49 observations and complete evidence. Reset `de10849499fd427f94d9143d08a2855b` also completed with three verified samples. Both resets retained one preparation Pending diagnostic and no terminal source/timeout diagnostic; the new timeout-specific diagnostic was therefore not exercised by a live failure in these two resets.

Two-leg run `b3e86356d1b94a2faca0d58a471ded64` executed leg1, its verified three-plus-one midpoint hold, and leg2. It failed after **12520.91 ms**, with 110 observations and complete evidence, at `final_verification_capture_limit_exceeded`. It remains **unverified**. One accepted final pose was **0.92447 map units** from the endpoint at yaw40 degrees, with **62.82 ms** source age; the required three-pose cluster was incomplete.

The final window consumed all 32 capture calls after **624.80 ms**, leaving **1375.04 ms** before its original deadline. Read118 used ten calls: five Pending, four response-barrier rejects and one accepted pose. Read119 used two calls: one Pending and one returned frame discarded at **172.47 ms** source age. That frame had been prefetched before a **123.15 ms** inter-read gap. Read120 spent its remaining 20 calls polling the same Pending reservation1399, at median **15.25 ms** start spacing. The last retained call took **0.0301 ms**, including **0.0132 ms** Map time returning StillDrawing; it had no gate contention or GC delta. This demonstrates polling-budget exhaustion, not a blocking Map call. No freshness threshold or retry policy was relaxed during the run.

The narrow next change separates validated Pending polls from completed capture attempts within the same bounded final window. Prefetch aging remains a separate observation. Evidence: `native-baseline-r33-01-result.json`, `native-two-leg-r33-01-result.json`, both `*-reset-capture-analysis-r33.json` files, and `native-two-leg-r33-01-route-analysis.json` (SHA-256 `38809945276929c16d8d54f674b2ed1402eaa53865fc73743830277bd7726771`). The detailed final-window breakdown is `native-two-leg-r33-01-final-capture-breakdown.json`, SHA-256 `f8ad693933f6d9723db39d4e45207b18132f6fb351d530385f7d1aafa91f3eff`. These records remain ineligible as human demonstrations or complete low-level input acknowledgments.

### R34 final-window Pending accounting

Final-readiness version 2 reserves one poll and one conservative capture charge before native work. Only a structurally valid typed Pending result, after the existing source/epoch/geometry validation, refunds that call's capture charge and consumes the separate Pending allowance. Ready (including a simultaneous refill), null, invalid Pending and exceptions remain charged. Each serial reservation settles once; disposal retains an unsettled call's charge. Thus `PollCount = CaptureCount + PendingPollCount`, including failure paths, while raw native rows retain a nullable per-call charge marker. PollCount counts reservations, so a setup failure can consume a unit before a native row exists; it is not presented as successful returned pixels.

The window retains its two-second deadline, 32 completed/error capture charges, 32 reads, 150 ms source freshness, 80 ms response barriers, three-pose cluster, permanent input closure and independent 4096 global poll ceiling. The additional Pending allowance is 400, derived from 2000/5 ms, with a conservative 432 total-reservation ceiling. The actual deadline can stop much sooner. Movement, waypoint and prefetch behavior are unchanged; historical final-readiness v1 retains its prior all-call capture meaning.

Both source review and the 50 mocked operational-helper checks passed. All **638 focused C# cases passed**, with zero skipped and all **71 source/dependency hashes unchanged** across the run. This includes 24 new cases for prolonged Pending, independent budget exhaustion, one-time settlement, invalid/error outcomes, clipped deadlines, global capacity and eventual three-pose verification. The maximum-count serialization fixture passed the unchanged 6 MiB limit. Evidence: `r34-navigation-focused-01-validation.json`, SHA-256 `97fd5c52987b02964995848df84d9ea28b1fba06274354c930b94b75e1ae25a9`. Full packaging and live acceptance remain pending at this implementation checkpoint.

### Full-model recurrent-kernel check stopped on numerical mismatch

The first bounded full-model attempt used the separately extracted Triton 3.2 wheel and unchanged candidate kernel; the working GPU environment was not modified. Original repeat IDs/terminal state, unchanged original prefill, 18 per-layer input-preservation checks, and each arm's own eager-versus-graph full state/logits checks passed. At case 0's first decoded step, the independent cumulative logit comparison failed the predefined `atol=rtol=1e-3` gate: **124405/248320** values differed beyond tolerance, with maximum absolute difference **0.021484375**. No case completed, and no performance or production-eligibility claim follows.

The worker restored its bindings, drained CUDA and retired. Peak allocated/reserved CUDA memory was 2486401536/2904555520 bytes. Its 297.938-second instrumented worker duration is explicitly not inference latency. Report: `gamescaling-recurrent-gdn-full-model/runs/run-001/report.json`, SHA-256 `72f5ef0b78b30b74471d9419fad7803c7786f30b1ab38528ca2f13c6289c792c`; launcher result SHA-256 `d850540c811915e8e12f7443008213ab59479cbd2d8c51da3439fc32cbebb44f`.

A CPU-only diagnosis verified all 302 saved arrays (165749464 bytes). Before-state tensors and metadata were exact. The earliest recurrent-state difference was layer 0, maximum **5.96e-8**; saved convolution inputs through layer 9 and attention states at layers 3/7 remained exact, with later activation differences growing. The next argmax and top-five IDs still matched. This locates the first observed divergence but does not establish its cause or full-sequence equivalence. Real per-layer q/k/v/g/beta inputs were not retained at this failure site. The next isolated diagnostic will retain those exact inputs and replay both functions against them, preserving the original tolerance and failed result. Diagnosis evidence: `full-model-gdn-run001-cpu-analysis-02.json`, SHA-256 `8fee96a246af945ecd19d7a73305eb2c36506e0d0b12a263148a24d2a61b750d`.

### R34 deployment and two bounded short-route failures

Full Debug validation and self-contained Release publication passed in **201.515 seconds** from clean revision `65f99a010abb0665aec64f479aac1bd6b7d10aac`, pushed to the fork with the requested noreply identity. The package DLL hash is `059213e7ae45cd40f6a0a2a45ff3e3a4858023b05621f24f2bbe90b264ccf186`; build manifest hash is `58ee4a437a3d50df3a72a67c40507dc1f61ed55a91cddea6e6b205b57eeea1ca`. The approved saved launcher replaced only the child, now PID25904/session3, while preserving root PID28072, Genshin PID27728 and its original creation time, the minimized RDP connection, and configured/effective `poll_single_v1`.

Reset `36448f107fed47dc9a152c726a04353d` completed with three verified point-1 samples. Baseline `63dd6ac0ebf645f79103a5076fd66e9b` then failed in **146.308 ms**, before recognition or navigation input, with `native_source_unavailable_or_stale`. Its first read polled reservation293 six times as Pending and then received the same reservation's pixels. The source was already **670.096 ms** old at read entry and **752.464 ms** old at capture return. Its staging submission preceded the read by **624.977 ms**. The Ready call also queued reservation294 from a newer source; that refill was not the returned frame. The evidence establishes inherited submitted work, but does not identify its submitting caller or the cause of the delay. The sole retained native call trace took **2.168 ms**, including **0.0082 ms** Map time; it cannot characterize earlier native calls.

A separate reviewed helper used that exact successful reset and terminal zero-navigation-command failure as prerequisites for one direct start, `native-baseline-r34-02`. It sent no new reset and retained explicit historical-reset provenance. Twelve CPU/mocked checks passed. It rechecked the same child/package/game/mode, current idle/input-disabled state and retained owners; existing native freshness and start-region gates still authorized any movement. These checks establish the recorded identities and procedural continuity, not a complete OS-input trace or an independently exposed runtime-generation identity.

Direct-start run `ebd5763a337e46f6b46a063c6fc7b79c` passed its initial point-1 observation at **136.352 ms** source age, issued camera turns and three bounded W holds, and failed after **2603.864 ms** with **12 observations** at `recovery_limit_exceeded`. Both permitted lease-expiry recoveries obtained a fresh pose and resumed. The third expiry ended the run. The first renewal missed its 150 ms grant by about **0.49 ms**; subsequent releases began about **7.79 ms** and **6.75 ms** after their grant deadlines. Those are recorded host timings, not physical key-release acknowledgment. Both trials retained complete hashed evidence, no native release error, and clean read-only postflights. Neither reached final verification, so the r34 final-readiness change has no live acceptance result yet. The two-leg prerequisite remains unmet.

Evidence: `r34-build-outcome.json`, `r34-hot-replace.json`, `native-baseline-r34-01-*`, and `native-baseline-r34-02-*`. The initial-failure journal hash is `cb3f9b46f566641368a6534d8c185fee655da3483b05fdf916c785cf6d0ab10f`. The direct-start helper hash is `8ea77a8578f7cb8063c5fdd6afb99b98824d52299aa667e6dfdb0b5323a32fe2`; its validation hash is `b5d0ca77845d4236c03c635a7367e4c0cebb8779ba9a5138e3190ecc0734f6d8`. Capture waits and recognition/scheduling costs are being compared with the completed r33 route before changing controller timing.

The file-only comparison found that requested 5 ms Pending waits actually took median **15.175 ms** in r34 (57 samples), versus **15.255 ms** in the completed r33 run (117 samples). This is existing overhead, not a new r34 timing regression. Warm recognition was slower in r34: median **32.016 ms** versus **26.860 ms**. Its first post-W read spent **105.844 ms waiting**, **10.260 ms in capture calls**, **30.680 ms recognizing**, and **1.640 ms elsewhere**. The later two reads also followed deliberate cadence waits of **55.205 / 58.212 ms**. These recorded components explain the observed deadline misses; they do not prove an optimized wait will complete the route. Evidence: `native-baseline-r34-02-vs-r33-wait-audit-02.json`, SHA-256 `33c35869213035c78f4560a02c191ff64a2dcde2cda5322e365edb13c97c3ba7`.

Microsoft documents approximately 15 ms resolution for short [Task.Delay waits on Windows](https://learn.microsoft.com/en-us/dotnet/api/system.threading.tasks.task.delay?view=net-10.0), and provides [high-resolution waitable timers](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createwaitabletimerexw) on supported Windows versions. A separate finite microbenchmark is being prepared to measure an owned asynchronous timer, including worker/continuation overhead and cancellation/retirement behavior. Global timer settings, power policy, priority, controller freshness and movement permissions remain unchanged.

### Real-input kernel diagnostic interrupted by progress publication

The first isolated real-input collection passed its exact original-prefill controls and reached recurrent layer5 during the single original decode. Windows then returned `WinError 5` while atomically replacing `progress.json`. No candidate kernel was attempted. The precise holder of any conflicting file handle was not observed. The worker restored bindings, drained CUDA and retired; **102 tensors / 43406456 bytes** of partial failure evidence were retained. Its **23.281-second** instrumented duration is not inference latency.

The failed run remains unchanged under `gamescaling-recurrent-gdn-real-input/runs/run-001`. A separate v2 diagnostic is adding bounded retries for transient Windows replacement/sharing errors, while keeping atomic publication, terminal failure on exhausted retries, numerical gates and owned-worker/compiler deadlines. This infrastructure failure supplies no new candidate-parity result and does not change the earlier failed full-model decision.

### Completed local timer measurement

The isolated BCL-only timer probe compiled successfully and passed all **nine native lifecycle checks**, including cancellation/reuse, concurrent disposal and worker retirement. Its fixed cohort retained 16 warmup pairs and all 64 measured AB/BA pairs. Full call-to-await latency for a requested 5 ms delay was **15.690 ms median / 20.327 ms p95** for `Task.Delay`, versus **5.476 ms median / 5.594 ms p95 / 5.750 ms maximum** for the owned high-resolution timer. The paired median difference was **10.298 ms**. Timings include worker admission, arming, observed wake, cleanup and asynchronous continuation; the actual kernel signal time is unobserved.

The probe changed no global timer setting, process priority, affinity, power policy, foreground or game setting. SDK compilation, lifecycle checks and measurement were sequential, with no root GPU or live operation overlapping the measurement. External desktop/game load was not measured or controlled. These are results for one finite timer cohort, not a promised gameplay improvement or permission to extend movement grants. Raw clocks, summaries and source/binary/report hashes were independently checked and recorded in `native-local-wait-benchmark/execution-01.json`, SHA-256 `0978403fe26d7852c8ea2c24355ba961de5006c5337ebddd4ce4aff6124d0f73`.

### Real-input recurrent-kernel replay completed

The separate v2 run completed all 18 original-input layer comparisons with the unchanged `atol=rtol=1e-3` gates. Exact original prefill/first-decode controls, input-preservation checks, binding restoration, CUDA drain and worker retirement passed. Ten progress publications each needed one bounded replacement retry, exercising the Windows file-sharing fix. Report: `gamescaling-recurrent-gdn-real-input-v2/runs/run-001/report.json`, SHA-256 `3c106cfefa38977cb686cae99429166ef80cc841c217df026e6a4c48ce1ddbc9`.

A separate file-only audit verified **216 finite arrays / 75941568 bytes**, 36 exact original collection/replay joins and 36 exact historical recurrent-state joins. Only **3 / 36864 FP16 output values** differed (layers 9, 12 and 17), with maximum absolute difference **4.768e-7**. All 18 FP32 state arrays had some differences: **1294093 / 4718592 coordinates**, maximum absolute difference **4.768e-7**. All fixed tolerance comparisons passed. Whole-model success controls and input preservation are recorded in-process checks; the audit does not reconstruct post-call input snapshots that were not retained. Audit SHA-256: `16b8c29f9ff2eca17ce35ce7fb2f08b8e86c57b778c3224b9ec508d74dde5783`.

Each layer replay starts from the original layer inputs; candidate changes do not propagate through the model in this diagnostic. The historical full-model mismatch therefore remains unresolved. The candidate already used `enable_fp_fusion=False`, confirmed by sealed source, executed compiler metadata and retained PTX; repeating that setting would not test a new variant. A separate saved-input comparison is being prepared for the exponential implementation. No tolerance was widened, and the **23.531-second** load/copy/compile/file-inclusive worker duration is not inference latency.

### Literal instruction diagnostic

The fixed follow-on instruction was **“Press F. Keep the camera still. Do not move, attack, jump, or sprint.”** The official CPU encoder produced a finite 768-value vector with exact upstream token IDs and zero maximum embedding difference; its vector-file SHA-256 is `27e0cc2e1b921f2fb60929ace682ac642e33929e8fba5db9821ab45348df873e`. Existing goal artifacts were preserved.

Both sampled arms completed their fixed 38 calls: two warmups, 32 scored calls over the same two saved views and 16 paired seeds, two original eager controls and two repeat controls. All **eight controls passed**, both workers retired, and all 64 scored proposals were structurally valid. Strict whole-chunk instruction success required at least one F press and prohibited every other key/button, camera movement and scroll; an entirely neutral chunk failed.

| Saved view | P2P sampled | GameScaling sampled |
|---|---:|---:|
| Initial | 0 / 16 | 0 / 16 |
| Final | 2 / 16 | 1 / 16 |
| Total | **2 / 32** | **1 / 32** |

P2P produced 11 entirely neutral chunks and GameScaling 13. Their native action horizons differ (50 ms and 200 ms), and every sample starts with cold history. This small saved-view diagnostic neither ranks live gameplay quality nor measures steady-stream latency. The paired historical contrast applies a common F-presence/F-only measure while preserving the original conditional instruction scores; it does not pretend that the two instructions have identical requirements. Merely making the instruction literal did not establish reliable goal following.

Aggregate: `instruction-quality-literal-f-v1/summary-001.json`, SHA-256 `fdb233fa99bd920542f928e73965368eef20aeadc05d589926f9337f9c1b3e85`. P2P report SHA-256: `34c173b1b1ca9855edd2110a285ddc27b6bc4387ad30b3ec7fa935d4a92b02cb`; GameScaling: `e30a81a856561f670f9174e45795f0338b9166e1a94f224dd495cefc0d8959fe`. No generated action was dispatched to the game or admitted as training data.

### Exponential substitution: saved-input result

The separately sealed kernel changes only `tl.exp(decay)` to `libdevice.exp(decay)`, leaving fusion disabled and the other arithmetic/launch settings unchanged. All 18 exact original/default layer controls completed before any variant call. All 18 variant output/state pairs passed the unchanged `atol=rtol=1e-3` gates. The file-only audit matched all 72 control arrays against retained originals/defaults and checked all 180 variant arrays/masks, including independent scalar tolerance classification.

Against the original fallback, FP16 output differences decreased **3 → 2**: layer 9 became exact, while layers 12 and 17 retained differences. FP32 state differences decreased **1294093 → 491305 coordinates**; bit counts and RMS improved in all 18 layers. This identifies a useful numerical intervention without proving full-model parity or a latency benefit. Eight bounded publication retries completed, CUDA drained, and the worker retired. Its **9.078-second** total includes compilation and evidence handling.

Report SHA-256: `061d519becc0a9df7bd10906c9a6b9689c0c5f36898f6c434bb0d529f3ce1461`; separate audit: `gdn-libdevice-exp-run001-file-audit-01.json`, SHA-256 `50dc2b368ca01e77aecaead25e78a60f0d43fb57a899839eddb7a6819486a71d`. The earlier failed full-model run remains unchanged. A separate full-model test of this variant is being prepared.

### R35 controller implementation and focused validation

The v4 initial pose read now has one no-input readiness window bounded by **entry + 2 seconds and the original workflow deadline**, including preparation time. Only a typed, valid own-window source rejected for positive age after capture can retry. The 150 ms freshness requirement, hard metadata/geometry/target failures, recognition failures and input prohibitions remain intact. The window permits at most 32 reads, 32 charged captures and 400 validated pending polls (432 total reservations); validated pending polls refund their capture charge, as in the final window. Stale source headers pin the window's metadata floor without advancing the last fresh admitted source. The window cannot reopen later in the route, and its records are file-only diagnostics.

V4 waits now use a lazily created, reusable high-resolution timer with one dedicated normal-priority worker. Requested slices remain 1–5 ms and availability/cancellation checks bracket each wait. The worker owns timer arming, cancellation and handle closure; request cancellation registrations retire before their events are disposed or reused. Cleanup drains the input lease and performs global release before retiring the timer, while remaining image/native cleanup runs even if retirement fails. There is no fallback to a different timing policy after native failure. V1–v3 retain their prior delay path, and the independent input watchdog is unchanged.

The fixed focused suite passed **719/719**, with zero failed or skipped cases: the prior 638 plus 66 initial-readiness/workflow cases and 15 timer cases. Source/dependency hashes for all **1604 files** were unchanged during the run. Four expanded maximum-count journal fixtures measured **5907596, 4963694, 5940343 and 5029317 bytes**, each below the unchanged **6291456-byte** file limit; these are representation tests rather than claims that a live workflow reaches every maximum simultaneously. Validation manifest: `r35-navigation-focused-01-validation.json`, SHA-256 `30260a7df5614024affbfd06f391b86803ba5fe8d2526fdde9bccbccb1e305b7`. No GPU/model or live operation overlapped the SDK run. Full solution Debug validation, Release packaging and gameplay verification remain pending at this checkpoint.

### R35 full build and successful short route

The required full Debug build and self-contained Release package subsequently passed. Both were produced from clean commit `43f8f2c1ee8860375180a6646dd9c5710c8d2459`; the build manifest SHA-256 is `00f7023dc8d6c377fb4e5c5cec0971d0f7e8b1b721afe57612669f354ac51608`, and the packaged application DLL is `a75a6ce1814fb10653024769f4222737c9d596876bb455d81490838942b58032`. The immutable snapshot contains 533 committed tool files. Deployment replaced only the RDP child, verified the minimized host, and preserved Genshin PID27728/session3 with its original creation time. Commit `43f8f2c1` was pushed using the requested noreply author and committer identity.

`native-baseline-r35-01` performed a fresh reset and completed run `6aa1cf2a2a90472499a684ab60ca9521`. Owner elapsed time was **4617.1505 ms**; the recorded workflow took **4319.6471 ms**. All 51 observation attempts completed. There were 34 forward grants, two physical key-down dispatches, two corresponding releases, and no recovery windows or release errors. Both releases completed approximately 50 ms before their recorded expiry. Three distinct final sources verified the fixed endpoint; the final window used 27 reservations, comprising nine charged captures and 18 validated pending refunds. These are controller records rather than physical input acknowledgments.

The initial window admitted its first read, with one charged capture, one pending refund and no age discard. Its source was **125.8588 ms** old at read return. This run exercises successful admission, not the stale-frame retry branch. The separate initial-audit v2 adds a necessary return-age consistency check; 41 CPU cases pass and prior actual analysis fields remain identical. Its actual-output SHA-256 is `dac6f29e80a14957f7cce282fc81c5b9ad93ac8dc9b32bff27f5e7ea0230e275`.

Across 323 requested 5 ms waits, measured durations were **5.4863 ms median / 5.7495 ms p95 / 10.1258 ms maximum**. The retained r34 failed run's same requested-duration cohort had 97 waits at 13.5311/15.9856/18.1914 ms. Workloads, outcomes and foreground contention differ, so this is an observed comparison rather than a controlled gameplay speedup claim.

The independent single-route, source/readback, recovery and final-v2 checks also passed. The adapted final analyzer retains the original fixed point2 endpoint, rejects other profiles and reproduces the retained r33 analysis byte for byte. Deliberately inconsistent pose copies, a consistently substituted point3 endpoint and a foreign profile are rejected. Its package is `r35-single-route-analysis-v2`, validation SHA-256 `119b04e9c7a5f25aa2132d28a08299f0acacb35c352e87b98977d7cd38c1dd9b`; failed preparation/fixture attempts are preserved separately. The actual controller journal SHA-256 is `040e33e260a7e0d50bfa96b24a2095dbb0120ebc1920041c342304aedbaa1345`.

### R35 two-leg attempt: reset stopped before navigation

`native-two-leg-r35-01` stopped in reset run `e2274024838f41bba3e5d7474a3f212a`. No baseline start was attempted. The three-second pose-acquisition window timed out after 22 probes; the terminal source was rejected after recognition at **511.1791 ms**, beyond the unchanged 500 ms reset limit.

The retained terminal call began with the source already **482.7797 ms** old. Capture took **2.2703 ms**, including a **0.0101 ms** Map, and recognition took **26.0465 ms**. There was no recorded capture-gate contention or process GC-pause delta. The source timestamp preceded first acquisition by **204.3384 ms**, and its staging submission preceded this poll by **277.9571 ms**. Earlier probe history, GPU-ready time and individual retry-wait durations are not retained, so this cannot assign the entire delay to the 120 ms retry interval.

The current reset helper applies that interval even to validated metadata-only Pending responses and charges those polls against its frame-attempt budget. A scoped implementation is being prepared to poll Pending promptly while retaining the three-second window, 25 actual-frame limit, 500 ms freshness and 80 ms input-response barrier. Reset diagnosis: `native-two-leg-r35-01-reset-timing-diagnosis-01.json`, SHA-256 `faef929991c099298f88f822a6f38d90869266a6596eccce25717d2f8d7227bf`.

### Exponential substitution: full-model gate still fails

The separately reviewed full-model derivative used the exact saved-input exponential kernel and bounded JSON publisher. The fixed numerical, cache, generation, timeout and worker-ownership gates were unchanged. Original repeat checks, exact prefill, all 18 input-preservation checks, and each arm's eager/graph comparisons passed. The first cumulative decoded step then failed the unchanged `atol=rtol=1e-3` logit gate: **123245/248320** CUDA-classified mismatches, with maximum absolute error **0.021728515625**. No candidate case or complete generation passed. Bindings were restored, CUDA drained and the worker retired. Its 55.047-second worker duration includes instrumentation and is not inference latency.

The file-only comparison verified 635 sealed pins and both 302-array failure archives. Original inputs, states, logits and IDs were byte-identical across the two experiments. Logit RMS decreased **0.004309624 → 0.004196356**, but maximum error increased slightly; the original next-token argmax27 remained unchanged. The first changed stored convolution buffer moved from layer10 to layer13, while recurrent FP32 state already differed at layer0 in both experiments. This does not identify a causal arithmetic operation or establish downstream instruction quality. CPU float64 mismatch counts differ slightly from the saved CUDA classifications and are reported separately.

Report: `gamescaling-recurrent-gdn-full-model-libdevice-exp/runs/run-001/report.json`, SHA-256 `3fc9103c0843e9dc760bcfcd84efcb68f5fba3acb379eb788c8181e81c9d51a6`. File audit: `gdn-full-model-exp-run001-cpu-audit-01.json`, SHA-256 `363b0d8c3c04e86c3e7aebf1914801c1ba386ba887a40bd5001dc10d67822a8d`; seven focused CPU fixtures pass. No tolerance was widened or production decoder changed. Further kernel variants are deferred in favor of practical policy-quality evaluation on continuous game observations.

## Reset pending-capture polling integration (R36)

The reviewed R36 source is integrated locally and the focused tests pass; full packaging and live validation are pending at this checkpoint. Only the already selected `poll_single_v1` reset path uses it. Typed, native-validated Pending responses now request a 5 ms owned high-resolution wait and receive a separate finite metadata allowance. Ready frames, recognition misses and failures retain their charges. The original three-second window, 25 charged observations, 500 ms reset freshness, 80 ms input-response barrier and outer owner deadline remain. Ordinary observation retries still request 120 ms. A monotonic deadline check also runs at the existing camera and recognized-map-close input boundaries.

The existing baseline timer was moved mechanically into `Core/Infrastructure/OwnedHighResolutionWaitTimer`; reset and navigation own separate instances. Final log summaries distinguish actual observation and Pending wait counts, sums and maxima, including successful windows. These are host intervals, not GPU-ready times or input acknowledgments. Source diagnostic version3 explicitly identifies the new accounting; legacy default behavior and version2 log shape remain unchanged.

The candidate manifest SHA-256 is `d837dc13b8f195e654d60947ed3a5005b4bae3cad4bb975f26f773b0bddeb54b`. It contains ten payloads and one guarded old-timer deletion. All **756 focused tests passed**, including 37 new reset cases and the 15 existing timer lifecycle cases, with zero failures or skips. All 1,607 pinned source/dependency files stayed byte-identical during validation and the old timer remained absent. Four representation-only journal fixtures stayed within 6 MiB; the largest was 5,940,407 bytes. Validation manifest: `r36-navigation-focused-01-validation.json`, SHA-256 `f44190c8c1f1399d545668dcb47eb351c5c8fe79e3da4e6c0024f18ed3c5dc7d`. Operational helper preparation separately passed 64 CPU/mock checks, with exact source and runtime bindings required before publication and deployment. These tests do not establish live acceptance.

## Native-frame cadence for temporal policy evaluation

A file-only audit of the successful R35 short route found **374 polls: 214 Pending, 51 admitted poses and 109 response-barrier returns**. The 160 pixel-bearing returns contain **109 distinct sources**, with acquisition-gap median/p95/maximum **33.301/52.388/168.789 ms**. The longest sequence with gaps at most 100 ms contains 107 sources. Recording only the 51 admitted poses would yield a longest qualifying sequence of 26, insufficient for the proposed 40-frame history plus a probe.

The proposed capture-only recorder therefore taps already returned, validated fresh frames before response-barrier disposal. It preserves their original source clocks and distinguishes them from admitted pose/world evidence. It introduces no second Capture caller or input controller. Those temporal pixels were not retained in the historical run, and source cadence alone does not establish complete action joins, model quality or live throughput. The cadence audit is `p2p-native-shadow-cadence-r35.json`, SHA-256 `2128d6c221d4472024c16cd7b0ce000e5349ec8e9ddde9a8bc10e3bc95172b71`; capture-only implementation is being prepared separately.

## R36 build, deployment and live outcomes

R36 is committed and pushed as `da84198a767ce62d068869b88749a90dd7ccf9d0`, with the requested noreply address for author and committer. Its 756 focused tests passed, followed by the required full Debug validation and self-contained Release publication in 204.906 seconds. The package DLL hash is `68cb23ac92d7ff6a9aae21ee917512843683767f7e13b0b24290d64cbbd30fb7`; the build manifest hash is `ae6b1028477feebcc269813017337c7a195c77b206333c6855dd01956d08e94f`. A 533-file tool snapshot and separate runtime binding pin the deployed package.

Child-only replacement reached PID 44652 in session 3, nonce `a22b6e48011d464792f2c6839de5f77e`, while preserving root PID 28072 in session 2, the minimized host, and game PID 27728 in session 3 with its original creation time. The three subsequent trials used fresh resets and explicit `poll_single_v1`, `v4`, and `task_owned_timer` selections.

| Trial | Reset | Native route outcome |
|---|---|---|
| `native-baseline-r36-01` | Completed in 36.303 s | Failed before input: a frame fresh at capture aged during recognition. |
| `native-baseline-r36-02` | Completed in 17.379 s | Completed in 4.990 s, 56 observations, 57 read attempts. |
| `native-two-leg-r36-01` | Completed in 18.086 s | Failed during first-leg recovery in 2.446 s, 12 observations. |

The short success (`adc70200e2374d2295b4b53104de9ccd`) has 36 forward grants, 3 physical W holds and 3 successful releases, completed 46.275/46.745/50.374 ms before their leases expired. Final pose was (-874.18359375, 2274.6904296875), 0.542178 map units from point 2. Its three final samples have distinct source identities and recorded ages 50.0072/136.1900/136.9608 ms. One final-after-capture age rejection was discarded successfully. No movement recovery or hard-fault event occurred. Journal SHA256: `4d209d3d5acc3d72b3d04cab4ad1c6169709344a98a2cef87bc52e26d454cce3`.

Short 01 (`dfebd12177fd4da6ba93a98b24d13cac`) exposes a narrower initial-admission gap: the only frame passed its capture check at 120.404 ms, spent 35.8783 ms in recognition, then failed the unchanged 150 ms gate. Its age at read exit was 160.3999 ms; the exact failing check timestamp is unlogged. The initial collector currently retries only age failures at capture. It issued no input. Journal SHA256: `b58977183e5d4504f528b4334c0656978f1d41098a7fa79a91e9b7887500daad`.

Two-leg 01 (`ded94485f45d4778a27398dec5a21cec`) preserved two initial-after-capture age discards, then entered a lease-expiry recovery. The recorded release completed 8.379 ms after expiry, with no release error; this is retained as observed scheduling lateness. Recovery exhausted its 32 raw-poll allowance on 32 Pending returns over 673.4445 ms, with no recognition, before its existing two-second deadline. It did not reach the midpoint. Journal SHA256: `9b56de61660a37274cc9a4697d9b6966147c20a4651adca410a906e0fb6b41dd`.

The first reset's independently recomputed ledger has 37 completed windows: 1 preparation, 33 orientation and 3 verification. Its 512 reservations equal 107 charged observations plus 405 validated Pending refunds. No window reached its limit. The 405 requested 5 ms waits averaged 5.493702 ms, maximum 12.3038 ms; 70 ordinary 120 ms waits averaged 130.443077 ms. These are one run's host timings, not a controlled load comparison or a complete GPU/OS trace.

The saved full-route and initial/timing analyzers validate both successful and failed outcome records without promoting a failure to route acceptance. R37 is being prepared to address the two observed no-input readiness gaps while retaining 150 ms controller freshness, original owner/window deadlines, finite budgets and hard-error rejection. Reverse continuation and capture-only temporal archives remain deferred. Continuous useful gameplay, learned action quality and training eligibility are not established.

An entry-point inspection subsequently found that the earlier `analyze-reset-capture-r36-v2.py` still imported the original v1 ledger module. Its reports are preserved, but they did not exercise the corrected preparation-ordinal gate. The new R37 entry explicitly imports the corrected v2 module, with an entry-binding regression test, and revalidated all three R36 ledgers. Only `pollingEvidence.method` changes; source events, joins, counts, timings and outcomes remain identical. The corrected short 02 and two-leg 01 reports retain respectively 29 and 30 completed visible windows, 240 and 285 reservations, 159 and 199 Pending refunds, and mean requested-5-ms waits of 5.479 and 5.448 ms. Their new report hashes are `c393d8e8882159c00dbca51c494c60debc2697bee35ad30bdef75054b4b85d72` and `e6672c09aac78962d4b63625d1b96e970f4abc03eb9468e693c3347754377143`. This aggregate evidence does not establish a complete per-poll trace.

## Initial-frame and recovery readiness integration (R37)

The separately reviewed initial and recovery changes are applied in that order. Initial admission can discard an exact recorded age-only failure after capture, after recognition, before or after retaining its image, or when the completed read returns. Hard source, geometry, world, chat and pose errors remain terminal. Discarded initial images are detached and disposed, and the consumed-source floor remains intact. A completed read can still fail the enclosing initial window; the evidence records both facts.

Recovery separates its 32 charged captures from up to 400 validated Pending refunds and 432 total reservations. Pending alone requests a 5 ms wait; ordinary recovery retries retain 20 ms. Neither policy widens the existing 150 ms freshness gate, two-second window, original workflow deadline, release barrier or input lease. Recovery source high-water includes valid returned headers that age out, while Pending cannot advance it. File-only initial and recovery evidence both become version 2; other policies and request fields are unchanged.

Initial manifest SHA-256: `f47cb63c9f428f1d4503f28bf3c17a6a012086a973b901ecbe2cb2039eb0aff2`. Recovery overlay manifest SHA-256: `0a1cb9c613508e38cd0b8c251f3b8b6de07f0acb71a0dd80db31b2863a812973`. All **813 focused tests passed**, including the 34 new initial and 23 new recovery cases, with no failures or skips. All 1,612 pinned inputs stayed unchanged during the run. The four representation-only journal fixtures measured 5,956,794, 4,963,694, 5,989,541 and 5,078,515 bytes, each within 6 MiB. Validation manifest: `r37-navigation-focused-01-validation.json`, SHA-256 `b06b6e6647bedc30ba535b16de7e094814e6919b40dac2aa73e01595c08ecb72`. The subsequent build and live checks are recorded below. Reverse continuation and capture-only recording remain unapplied.

## R37 build, deployment and live outcomes

R37 was built from clean revision `a53c49b849d280ebbfbdc7eed48621ba1306ce2e`. The required full Debug validation and self-contained Release publication passed in 205.938 seconds. Package: `artifacts/release-r37/BetterGI-English-win-x64`; DLL SHA-256 `24e2af97ee805c36ed25649b68fe2338111f17ffb94cbe0a2debcb21331ad4e7`. The build manifest and 533-file frozen tool snapshot were verified before child-only replacement.

The new child is PID 11364 in session 3, nonce `4950e907cbcb4f498c11d26b19ecdb9b`. Root PID 28072, the minimized host and game PID 27728 with its original creation time were preserved. The deployment and all trials explicitly required `poll_single_v1`; a stale helper README sentence claiming a blocking-mode prerequisite is corrected in a separate pinned note without rewriting that historical helper seal. All routes used `v4` and `task_owned_timer`, with a fresh reset for every attempt.

| Trial | Reset | Native route outcome |
|---|---|---|
| `native-baseline-r37-01` | Completed in 31.630 s | Completed in 6.537 s; 54 observations, 58 reads. |
| `native-two-leg-r37-01` | Completed in 18.018 s | Verified midpoint, then failed at the shared recovery limit in 7.355 s; 56 observations. |
| `native-two-leg-r37-02` | Completed in 16.899 s | Completed both legs in 12.098 s; 141 observations, 142 reads. |

The short route discarded two old initial frames before accepting its third read. Its initial window recorded 121 reservations, 3 charged captures and 118 validated Pending refunds. A later SourceAge recovery while W was not held resumed in 154.935 ms. All three physical W releases completed 45.510–47.137 ms before expiry. The final position was 1.211323 map units from point 2, within the existing gate. Journal SHA-256: `461dea497840db538d5fac706a77e94372c8ffd1e34f097e2035189ed68fe0df`.

Two-leg 01 recovered twice: a stationary SourceAge wait in 153.027 ms, then a held-W lease-expiry recovery in 737.596 ms. The latter used 123 reservations, only 3 charged captures and 120 valid Pending refunds, demonstrating that R37 no longer exhausts recovery on 32 metadata-only polls. Its W release completed 2.587 ms after expiry, with no release error; this lateness remains explicit. Three midpoint samples plus a fresh second-leg anchor passed. A subsequent old frame at the second-leg start triggered the global two-recovery cap while W was already up. Journal SHA-256: `738ddbca2e998e0d4b6cbdca1b004902d43587238a87abb0504c14fde7e4d1f3`.

Two-leg 02 completed with 104 forward grants and 7 physical W holds. All releases completed 44.458–59.392 ms before their leases expired. Its single recovery was a stationary SourceAge wait, resuming in 146.734 ms. Final pose was (-885.974609375, 2263.2490234375), **0.178068 map units from point 3**; the three final samples had distinct source identities and ages 40.4577/116.4719/127.5044 ms. Journal SHA-256: `8ece997066b12f84f7babac893d85f973c5686e90947c78900ae6ca71952d716`.

All three saved outcomes passed the new initial/full-route/reset consistency checks, including the failed outcome as a failure. The analyzer package passed 128 CPU fixtures and retained eight historical full-route outputs byte-for-byte; its manifest SHA-256 is `c6c5985a488a10319c43d6e29e6924cfb8bab8d2b23af8905d8f623f42530827`. The successful two-leg outcome audit is `native-two-leg-r37-02-outcome-audit-r37.json`, SHA-256 `2541b0f487038d777926b5bb00ad27a74989e9cd7a8b7eb1526818e8946b8b2f`. The three-run summary is `r37-live-outcome-summary-01.json`, SHA-256 `82b7091cb47af081dfe59820d571b857e5e4f169f23c1bd1b0c6dba1a0ed6044`.

These results establish bounded forward navigation under the observed load, not uninterrupted gameplay or learned policy quality. The failed attempt motivates separate finite stationary readiness accounting while retaining two movement recoveries, fresh-source checks, bounded release/rearm and the original workflow deadline. Reverse continuation and temporal capture are the next integration work; no model-controlled or training-eligible episode is claimed.

## R38 continuation, capture recording and stationary readiness

R38 was built from clean revision `77ef4761172695a719a87198456f7732a11c1904`, using `4991891+everyonce@users.noreply.github.com` for both author and committer. The required full Debug validation and self-contained Windows Release publication passed in **209.297 seconds**. The build manifest SHA-256 is `cb94697b86b8b62d7d0023a00da02b5a38314f611fe9223ffc549179b99126ee`; the application DLL is `244c337bfc87f2a88a4d452ac37c22d58839dc2cce0a7ae4ffd4f0fde54bf7e5`. The package contains a verified snapshot of 536 committed tool files. Child-only deployment reached PID 32568/session 3, nonce `69fcbf34945b48829a79080364baa0bc`, while preserving root PID 28072, its minimized host and game PID 27728 with its original creation time.

The integrated changes add an explicit fixed 3→2→1 return from the latest verified forward two-leg result, optional `rgb192-capture-only-v1` recording, and separate stationary readiness accounting. Continuation checks the retained owner, runtime, game creation, backend, mode, cleanup completion and source floor before new route authority. Recovery schema 3 permits two movement recoveries and two SourceAge windows entered with W already up, four windows total. Classification is fixed at pause entry. The original 150 ms freshness, two-second recovery window, 30-second workflow deadline, response barriers and bounded input leases remain.

The recorder copies already returned fresh frames into two owned buffers, then performs the pinned Hamming resize to RGB192 on its worker. It records native source/poll identity, copy timing, duplicate suppression and byte hashes, with explicit completion and worker retirement. The limits remain 1024 frames, 108 MiB of RGB and an 8 MiB sidecar. Capture admission is recorded separately from subsequent pose admission; archived pixels and logical controller events do not grant training eligibility or physical-input acknowledgment.

All **915 focused C# tests** and **287 Python command tests** passed. The C# run verified 1,634 unchanged inputs and four representation-only maximum-count journals below 6 MiB. Earlier failures are retained: one production namespace import, two test imports/fixtures, and a Python test's staging-only path needed correction. The first full Python attempt encountered sandbox filesystem restrictions; the unchanged suite then passed under normal Windows permissions with a private workspace temporary directory. Focused validation SHA-256: `ba52271d99ea498f5c7451cf680cdde1cdfcf9279f0c0c3d41959d95aa11d539`; Python validation: `b3649eedcd1073470247b7ae0dd4403924d9a16b5a9083eccbed54293b58fc1c`.

All four trials used `poll_single_v1`, `v4` and `task_owned_timer`. The first three used fresh resets; the return used the actual endpoint and exact evidence of forward 02 without a reset.

| Trial | Native outcome | Observations | Recorded unique frames |
|---|---|---:|---:|
| `native-baseline-r38-01` | Short route completed in 5.354 s | 56 | Recording unselected |
| `native-two-leg-r38-01` | Recovery deadline exceeded in 6.186 s | 46 | 104 |
| `native-two-leg-r38-02` | Both legs completed in 11.367 s | 137 | 275 |
| `native-reverse-r38-01` | Climbing detected in 7.440 s | 90 | 196 |

Every selected archive completed and its worker retired with zero rejected or lost frames. Forward 02's controller journal SHA-256 is `63c89ba8821f296366575d72b8c682dc72c17d0b0b1aa47104d96aa0e606b486`; its archive manifest is `22460ed54f2e5e9f6409f9249c03e3153e45c8382af6e72a2002c21fba3e6497`. The independently accepted v3 outcome audit is `native-two-leg-r38-02-outcome-audit-r38.json`, SHA-256 `ad0fafc1c1a40c381934296c045c49d52e4dfd07c49436950aad971bebd96f97`.

Forward 01's recovery used 355 validated Pending polls and one charged capture. One staging submission remained Pending for 1.926 seconds after submission despite a completed 0.1374 ms Flush; its final uncontended Map probe returned `still_drawing` in 0.0097 ms. The last shadow copy preceded this submission by 231.012 ms. The three WGC source files are identical to R37, which also retained shorter 746–832 ms Pending intervals. These unpaired runs do not identify a GPU/driver cause or isolate recorder overhead. Its W release completed 30.9368 ms after the recorded lease expiry, with no release error. Diagnosis: `r38-shadow-readback-stall-01/report.json`, SHA-256 `d39a3120b4580d2abbe02d4ede3e20030e124781472d65b6539ec85946f3df3e`.

The return passed its same-runtime predecessor and strictly newer same-epoch source checks, then stopped on the first reverse leg. Its last normal pose was (-876.09375, 2271.779296875), 2.957607 map units before point 2. The retained last image shows the character climbing the stone wall below the upper courtyard. Key-up completed 62.8378 ms before expiry. This exposes a physical route limitation: reversing the forward coordinates encounters an elevation barrier. The next continuity test uses the level P1↔P2 courtyard segment, retaining the climb guard and preserving this encounter for obstacle evaluation. A completed out-and-back cycle and learned-policy quality remain unestablished at this checkpoint.

The separately sealed analyzer v4 subsequently checked all four actual outcomes, preserving the two native failures. Its 174 CPU/file cases pass, with 11 historical route and three reset comparisons unchanged. It corrects two wrapper compatibility issues: strict SHA-256 comparison accepts hexadecimal case differences, and the exact pinned short helper reports artifact errors through its existing top-level error rather than a separate absent field. Prior reports and the failed reverse-analysis log remain unchanged. Package SHA-256: `c4f1e4bb8500b75d8795b4200e553740d4d63ffa3935b519eb402bdc5eda7e9a`; consolidated results: `r38-closed-trial-audits-02.json`, SHA-256 `546c89bc2af5fca33dad1b7b849ff94df85fa586d15e18f3a9b3c18f9f55e5ec`.

The first actual temporal-context reader run verified forward 02's 275 images and selected the earliest eligible 40-frame history plus one probe: frames 1–40 and 41. The 40 acquisition intervals span **1280.7148 ms**, with maximum reported-source/acquisition/copy-availability gaps **62.5/55.2411/61.2032 ms**. Their recorded controller history contains seven camera calls, one W-down and three renewals. The earlier candidate was excluded because it began outside the controller lease lifetime. This establishes a recorded-intent association for a subsequent replay experiment; native cadence is irregular, other physical controls are unknown, and no model inference or training occurred. The v3-bound reader remains valid for this accepted forward outcome; 28 reader CPU checks passed. Report: `native-context-feasibility-r38/forward02-001.json`, SHA-256 `b46b2e0f67229eb2676a1eb2b19e96faf544e0a2ad871632ab84e73a73c1abdf`.

Across all 275 archived frames, the synchronous owned-buffer copy interval measured **0.8988 ms median / 1.4463 ms nearest-rank p95 / 2.1155 ms maximum**. This interval excludes capture, initial recorder setup, worker resizing/writing and queue lifetime; it is not a controlled end-to-end overhead comparison. Timing report SHA-256: `454978d0b27168b9d37623dfaf143d177877ecc5f0deb463751fe7f2c6d1c82b`.

R38 revision `77ef4761172695a719a87198456f7732a11c1904` was pushed to the fork's `main` branch on 2026-10-24 after its recorded validation and live checks. The R39 integration below remains a separate source change.

## R39 fixed courtyard continuation and compact status

The new `mondstadt-city-courtyard-return-v1` uses only P2→P1, and `mondstadt-city-courtyard-forward-v1` uses P1→P2. A return requires the exact latest successful ordinary short or courtyard-forward owner; courtyard-forward requires courtyard-return. Ordinary short runs using `v4` and `task_owned_timer` now retain the same runtime/game/capture/input binding needed for continuation. Each courtyard request still authorizes one fixed leg, without a reset fallback or automatic loop. The original source, geometry, motion, lease, cleanup and shadow-retirement gates remain.

Integrated validation exposed a real compact-response regression: adding the two route capabilities made six failed-with-shadow representation fixtures exceed the existing 8 KiB status limit, reaching 8,232 bytes. Status now advertises `endpointContinuationVersion: 2` and carries only the versioned predecessor run/profile reference. The dedicated result and controller journal retain the complete version-1 runtime/source/artifact proof. The client supports exact legacy version 1 and new version 2, checks the same latest owner, preserves visible game/capture/readback checks while polling, and validates the full proof after terminal retrieval. Old clients reject the new continuation capability before mutation. The 8 KiB ordinary and 32 KiB dedicated-response limits are unchanged.

All **980 focused C# tests** and **322 Python command tests** pass, with no failures or skips. The C# run retained 1,640 unchanged input files. Across 24 bounded long-path wire fixtures, the largest compact response is **2,752 bytes** and the largest dedicated result is **22,906 bytes**; these are representation fixtures, not universal bounds on arbitrary strings. The four maximum-count journals remain below 6 MiB. C# validation SHA-256: `929f41a2a8926a61f999b0318b5ce913d49d34d13115c7381f241db3580e5dae`; Python validation: `197683545e4b1bf22b9bac92f70717390f7852e21f4fff415ce035a976dde9dd`.

Earlier R39 attempts are preserved. The first compile stopped on missing required fields in a new test fixture. The next run had 12 test comparisons treating cloned arrays as record identities and the six genuine wire-size failures; the corrected comparisons cover every serialized snapshot field. A complete-Python wrapper initially expected ten new cases instead of the actual eighteen and stopped during discovery, before executing tests. Only that wrapper's count changed before the successful 322-case run. Courtyard candidate SHA-256: `f8cafda7b18c921832fd718988671a188a3eb2efcafc99dece18942befd40fe1`; compact-status candidate: `581d3394baa0fb4f1289a7a8290f1e7aad19963abff075c2674b358fa92d3fb0`.

## First fixed-rate replay context from native recording

A separate CPU adapter selected the earliest eligible absolute-QPC 50 ms grid containing 40 history steps plus one unlabeled probe from R38 forward 02. It uses original RGB bytes from source frames 144–189, with two explicit image holds and a maximum conservative source age of 103.8903 ms. The 40 supplied history labels contain 34 software-W end states and one camera-call interval. Other controls are explicit synthetic neutral fills. The raw-copy completion time is only an availability lower bound: worker preprocessing/transport latency was not measured and is assumed zero for this offline projection.

The prepared context SHA-256 is `251c047502c7e9d3207493180709c3ccc35c767639c16283ee24a4dd3ee86bc7`, with 17 CPU preparation checks passing. A separately reviewed execution helper passed 19 CPU/mock checks and pins the installed runtime and unchanged original sequential P2P functions. It specifies two history arms, four fresh 41-step replays, and 128 paired sampling calls, including exact alternate-placeholder controls. Execution seal SHA-256: `3b778f8073e083835194ba8c07e3d892e2f7841ead3d35f8bb3c9af94965eccd`. This experiment measures sensitivity to projected history on one real probe; it does not establish gameplay quality, physical action delivery or training eligibility. Numerical execution results are recorded separately after process retirement.

## R39 runtime and capture diagnosis on 24 October

R39 was built from clean revision `ab4f1ea8c56ac06ccbbfc303683dfd9f0bbd78f3` and pushed to the fork. Full Debug validation and self-contained Release publication passed in 185.625 seconds after the 980 C# and 322 Python checks above. The published DLL SHA-256 is `b8aca3d14bfd1879c712289f7c3f8bdace40e3e2b6a6c15815d5f5027f81dc12`. Child-only replacement reached PID 45140 in session 3, preserving root PID 28072, the minimized RDP host and the original game PID 27728. The 538-file tool snapshot and configured/effective `poll_single_v1` selection were verified. Deployment proof: `r39-hot-replace.json`, SHA-256 `8b940aead4aea7d4832c73f13c812f85f1b4c0f73099bb243112f46b3decbe30`.

The first R39 seed failed before teleport or navigation. After 12.445 seconds of map-template warmup, reset readiness exhausted 400 validated Pending polls in 2245.0966 ms, with no charged observation and 755.6149 ms still left before its three-second deadline. This was a polling-cap failure, not 400 captured images. Reattaching the same backend did not restore usable capture. A later unchanged live probe returned two images, but their source ages were approximately 4.27 and 3.79 seconds and the world/freshness guards rejected them. R39 has completed no navigation leg. [Reset diagnosis](D:/work/genshin-auto/artifacts/research/2026-10-23/r39-reset-pending-diagnosis-01/report.json); [later live-capture audit](D:/work/genshin-auto/artifacts/research/2026-10-23/r39-cadence-and-live-closed-audit-01/audit.json).

Initial isolated polling workers returned no frames in eight seconds. Blocking GPU readback exceeded its 30-second owned-process limit; blocking CPU readback returned one stale frame after a 24.488-second call, including 24.395 seconds around Map. Later polling observations returned frames with both the original library and experimental source retention; the original library's 16-frame result disproves a stable zero-frame baseline. These serial observations occurred under varying external load and do not identify a driver cause or isolate retention's effect. The isolated retention library holds the selected WGC frame and surface through successful Map, CPU copy and Unmap, and quarantines the generation on faults. It was not installed into R39. [Initial diagnostic audit](D:/work/genshin-auto/artifacts/research/2026-10-23/r39-blocking-retirement-closed-audit-01/audit.json); [later three-arm audit](D:/work/genshin-auto/artifacts/research/2026-10-23/r39-retention-poll-closed-audit-01/audit.json).

The final cadence-v3 diagnostic used the same isolated retention library, a 5 ms high-resolution wait after Pending, a 50 ms wait after other outcomes, and an eight-second admission window. Three independent image copies were retained during measurement and encoded afterward. Raising the call cap from 160 to 1600 allowed the full window; the earlier cap had stopped the GPU and CPU observations after only 2.127 and 1.005 seconds. Both full-window workers reached the time deadline and retired, with root/game/child identities, minimized state and disabled input preserved.

| Full eight-second arm | Ready / Pending / Unavailable | Median / p95 reported source age at return | Both source and acquisition ages at most 150 ms |
|---|---:|---:|---:|
| Retention, GPU conversion | 8 / 1299 / 1 | 124.4004 / 3976.9714 ms | 5 of 8 |
| Retention, CPU conversion | 110 / 273 / 1 | 82.2968 / 97.4239 ms | 108 of 110 |

CPU conversion's favorable p95 hides a real mid-run interruption. One reservation took 974.0386 ms from submission to the successful Map attempt; the following source was already 945.8390 ms old when acquired. These produced two approximately one-second-old returns and a **1111.4289 ms gap** between replies meeting both 150 ms age limits. The final CPU reservation was never polled before the window ended, so its censored lifetime is not a proven busy-Map stall. The GPU arm ended with 590 busy Map attempts on one reservation over 3353.1603 ms. All six saved PNGs showed plausible game content without visible black/white or channel corruption. These capture-only ages exclude recognition and controller feedback, and the comparisons do not isolate conversion from changing machine load. The CPU path warrants a guarded explicit prototype; sustained control reliability remains unestablished. Evidence: `r39-wgc-retention-cadence-v3/runs/{gpu-001,cpu-001}`; published build binding SHA-256 `7135b3a72f093d120d6e48ced581296a154de527c5fd0252a2ffa662c1be6330`.

## R40 capture controls validated on 24 October

R40 adds explicit `sourceRetention` and `conversion` controls for WGC V2, with configured and effective selections reported through the automation endpoint. Retention remains disabled by default and conversion remains GPU by default. The changes are committed and pushed as `5aee805bc774d6b0329c992ada4b049e9b5ed714`. Freshness limits, input leases and navigation gates are unchanged.

All 1,098 focused C# tests and 341 Python tests passed with zero skips and unchanged source hashes. The four retention implementation files, shared generation/source inputs and managed fixture are byte-identical to the previously completed ownership test, so that fixture was not rerun. Evidence: [C# validation](D:/work/genshin-auto/artifacts/research/2026-10-23/r40-navigation-focused-01-validation.json), [Python validation](D:/work/genshin-auto/artifacts/research/2026-10-23/r40-rdp-command-tests-01.json), and [ownership reuse proof](D:/work/genshin-auto/artifacts/research/2026-10-23/r40-managed-ownership-reuse-01.json). Full Debug validation and self-contained Release publication subsequently passed in 219.609 seconds. Child-only replacement reached PID 23148 in session 3, with DLL SHA-256 `12d79fe77313dfd1880735deb2102afd2f0570b63e66629dddc0a2e4fd920b2e`; the minimized root host and original Genshin process remained intact. The first capture trial returned 53 distinct changed images, but source age reached 1245 ms and the fresh-frame gap reached 1449 ms. Two native seed attempts then returned no usable observations and issued no input. R40 therefore did not establish a continuous gameplay loop.

## Completed original sequential P2P comparison

The instrumented launcher-v3 `run-001` remains a preserved 600-second timeout. It completed two 41-step replays and 27 sample pairs, with a 437.500-second host interval in the first online call. A separate first-call diagnostic then completed all 41 calls, with the first taking 5.516 seconds. Neither observation identifies the cause of the earlier delay. The unchanged full comparison was subsequently run once more as `run-002` and completed within its original 600-second limit. The worker reported 467.907 seconds including preflight and cleanup; its owned process tree retired and an independent process check was clear.

The completed run contains four fresh 41-step replays and 128 sampling calls. An independent file-only audit verified all 134 saved NPZs and reproduced 532 exact saved-array comparisons. Within each history arm, changing the final probe placeholder preserved all pre-action contexts, the first 40 steps' teacher-forced heads, the first probe head, and every paired sampled proposal and conditional head. Later teacher-forced probe heads were intentionally excluded because they may depend on the supplied placeholder prefix. Original image bytes and goal inputs were preserved. This establishes an original sequential reference for this context; it does not establish resident-cache, CUDA-graph, full-context or next-call parity.

Both arms used the same 41 images, text goal, probe and 32 paired seeds. Only the supplied action history changed:

| Supplied history | No-op proposals | Camera-only proposals | W-only proposals |
|---|---:|---:|---:|
| Recorded-intent projection | 27 | 4 | 1 |
| Synthetic neutral history | 30 | 2 | 0 |

Five paired seeds differed across histories. This demonstrates history sensitivity on one probe, not improved instruction following or gameplay quality. The 50 ms projection, repeated images, synthetic neutral fills and software-intent labels remain experimental conventions rather than acknowledged physical actions or training data. The instrumented original path's host timings are not a latency benchmark for the resident GPU implementation. The next model gate is a same-context resident-cache/graph comparison against this saved original reference. [Closed comparison](D:/work/genshin-auto/artifacts/research/2026-10-23/P2P-V3-RUN002-CLOSED-COMPARISON.md); audit SHA-256 `e5eb480af02e2c4c9c1b8149e1a8dd764854a2d2abdb403d5a99d3255bc1ee0a`; worker report SHA-256 `7d738ce2d1c1a82841c1bd6cc44d840427bdda9db3528c98732215f162323d0d`.


## Desktop capture investigation on 24 October

The later isolated WGC experiments remained inconsistent with dependable controller input. Default-release polling returned no ready frames during its eight-second windows, and the blocking-copy worker exceeded its 30-second process limit without returning its first call. A window-client DC (`GetDC(game HWND)`) returned quickly, but all three saved images were entirely white. These workers retired; none of those outcomes was accepted as useful capture.

Cropping the desktop DC (`GetDC(NULL)`) to the exact game client rectangle succeeded while the RDP host stayed minimized. The eight-second `desktop-dc-001` run returned 84 images with no unavailable result or capture exception. All three saved images were independently inspected as recognizable Genshin content; they were distinct and nonuniform. The remaining 81 images were not saved or visually verified. BetterGI's own log overlay was visible and must be suppressed in the application integration.

Median/p95 capture-call duration was **35.4784/43.5717 ms**, including median/p95 BitBlt intervals of 34.5951/42.5494 ms. The requested 50 ms waits actually had a 57.2948 ms median and occurred after calls, so this diagnostic did not demonstrate a 20 Hz end-to-end loop. The last admitted call returned 24.9918 ms after the eight-second cutoff; no later clone or call was admitted. The worker retired, and the existing root, child, game, minimized state and disabled input were preserved. Closed audit SHA-256: `dcb6123873b8d9880660753e4cb72e49f739e7568864c77251a63a8f487bb9a0`.

This is host acquisition evidence, without a compositor/render timestamp. The production implementation is being developed separately with per-call GDI ownership, immutable capture-start/end metadata, synchronous own-overlay suppression, and an explicit `host-acquisition-v1` controller policy. Its default is observation only. The existing source-age, lease and response-delay bounds remain; capture return time cannot make an old acquisition appear fresh. Production capture and controller behavior still require build and live validation.

## P2P resident attention mismatch localized

The closed two-step v5 diagnostic returned from all four model calls and reported the existing strict numerical failure at resident step 1, pass 1, layer 2's query. The worker reported 560.438 seconds including its preflight and cleanup; process retirement was subsequently confirmed. Of the 1,040 gates actually reached, 1,039 passed. The failing tensor had 28 elements outside the unchanged absolute/relative 0.001 bounds, with maximum absolute difference 0.0078125. It was not accepted for gameplay or graph equivalence. Worker report SHA-256: `f2c8667233300fd5cf93e4157a0192b53d4184637365e52cdd549e733a22dfd1`.

Independent saved-array analysis found all 242 common step-0 boundaries byte-identical. At step 1, image/goal inputs, pre-call active state, layer-0 queries, active keys/values and masks were also exact. The first retained difference was one FP16 ULP in layer-0 attention output: -0.145751953125 versus -0.1456298828125. Original attention used a physical 24-token history; resident attention used a padded physical length of 492 even though its active values and mask matched. This supports testing identical active operand geometry; it does not identify a GPU kernel or driver fault.

The v6 candidate packs only the active key/value and already evaluated mask suffix contiguously for the first two steps. It retains the full cache, position/mask formulas, supplied actions, two-pass order, original oracle comparisons and numerical thresholds. All 64 CPU/mock checks passed and independent source review was clear before the bounded GPU test began. The owned GPU run then reached its 600-second deadline during resident-step-0 post-return validation, before resident step 1. Its worker and Job retired; there was no final numerical report or successful in-process cleanup proof. Independent closed-file analysis verified the three returned archives and found all 242 same-shape original/resident step-0 boundaries byte-identical. Twenty stored-mask active suffixes also matched, and all 180 saved prefix-count scalars were zero. This partial result does not establish second-step equivalence. Closed partial audit SHA-256: `eb029849091b11f828ac10c70d9f4aa062922fd59120da69fcd53d8a95e0cff6`. A separately disclosed brief local Python/Job test episode overlapped this run; its relationship to the timeout is unknown. The separate scalar-packet GPU probe has now compared 14 recorded tensor pairs and five synthetic cases. All **19 outcome objects matched**, including nine passes, eight numerical gate failures, one strict-JSON failure and the existing empty-input exception. Its helper preserves the FP32 calculations and transfers five losslessly widened scalars together; the test does not establish model-policy latency. The owned worker retired and the closed audit is `7cee37b9e2cb81c5dbf28a08d13028bea979f0fd2b0ace13aaa9cf6880b44dc5`. V7 uses that helper only for diagnostic result validation. Its 74 CPU/mock tests passed, all 6,820 file pins were checked, and independent source and seal reviews were clear. The immutable V7 preflight seal is `4de0917e9a5265007ec6c2f4a1ca419250587f072094e9c6f1d27b7f71d54402`; its GPU run has not started. Later rolling-history behavior, sampling and CUDA-graph equivalence remain separate gates. The instrumented diagnostic timings are not resident-policy latency measurements.


## R41 production capture build and deployment — October 24, 18:35 UTC

The final source04 cohort passed all 1,613 C# cases. Earlier compilation and fixture failures remain in their own attempt records; the final fixture corrections unwrap the typed WGC evidence without relaxing identity, timing, input or disposal assertions. The full Debug solution check and Release publish then exited successfully. No SDK process remained before the child replacement.

R41's application DLL is `664764b33bc413a0233994b813e86c37518b1826ada05dd48a6ddef8238e41e9`; its capture DLL is `779a17582976efc7518d8e8c014e4c7a80a134f3d155dc8027a807aec620c0f0`. The child-only replacement reported ready at 18:34:59 UTC, creating PID31552 in session3. Root PID28072 stayed minimized, and Genshin PID27728 retained its exact CIM creation identity. The new child reported runtime ready, no task/Agent stream, input disabled and desktop-DC policy `observe-only`; its selected capture backend was still WGC pending the separate live validation stage.

Evidence is retained under `artifacts/research/2026-10-24`: `desktop-dc-csharp-04-validation.json`, `r41-build-outcome.json`, `r41-build.log`, `r41-sdk-retirement-01.json` and `r41-hot-replace.json`. The actual package manifest is `artifacts/release-r41/build-manifest.json`. The replacement record preserves the build/source/client provenance and before/after game identity. Failed preparatory wrappers are separate: CIM timestamps have microsecond precision, direct root-desktop process handles are denied for this game, and the existing control client requires string paths. None of those failed preparations dispatched a restart.

Live admission still requires an input-disabled capture recording, inspection of all three spaced images for recognizable game content and absence of BetterGI's overlay, and a separately selected host-acquisition policy before one reset/ordinary short. The validation helper must use the actual status DTO and established protected-game CIM query; synthetic fixture fields and denied native queries cannot authorize a run. These checks establish a usable prototype path, not constant gameplay or training eligibility.


## R41 live startup failure and R42 correction — October 24, 18:54 UTC

The single R41 `select-observe` request failed at 18:43:42 UTC with `Desktop capture requires the calling thread's PerMonitorV2 context.` Source inspection confirmed that the existing comparison already used `AreDpiAwarenessContextsEqual`; the missing step was establishing that thread-local context. The failed selection left runtime stopped, task/stream/input disabled, and root/game identities unchanged. The passive worker was never started. The original binding, tool snapshot, failed run and closed evidence record are retained; the request was not replayed.

The six-file R42 DPI delta enters a caller-local scope around Start target validation and each Capture transaction. GDI/borrowed-pixel cleanup and restoration of the original thread context precede publication; the host acquisition interval includes both. Uncertain restoration retains the primary error, releases rejected owned pixels and quarantines the backend. It changes no process-wide or WPF DPI setting. Production and complementary fixture reviews are clear, and all 1,631 C# cases passed at 18:54:26 UTC with unchanged source pins.

A separate two-file client correction removes the nonexistent top-level game-process field assumption. Host reset pins the positive integer game process ID from its admitted owner and requires it through every poll; baseline retains its prior owner pin. It preserves source policy, age, lease and no-replay checks. All 241 selected CPU/mock cases passed. The R41 frozen client remains preserved; the corrected client belongs to the forthcoming R42 snapshot.

Evidence: `artifacts/research/2026-10-24/r41-capture-selection-closed-01.json`, `desktop-dc-precompile-source-05.json`, `desktop-dc-csharp-05-validation.json`, `desktop-dc-dpi-scope-r42/manifest-01.json`, and `desktop-dc-client-status-correction-01/manifest.json`. The 1,742 .NET pins and the separately reviewed Python tools are distinct source sets. Native capture, image inspection and reset/short validation remain pending the fresh binary.


## R42 package and explicit startup recovery — October 24, 19:01 UTC

Full Debug validation and Release publication succeeded at 18:56:53 UTC; all 1,742 .NET source pins and the build script remained unchanged. SDK/compiler retirement was observed at 18:58:31 UTC. The published BetterGI DLL is `46015140c157029ddb21c86f0e3ee52277445ad5b7befcf0f76586ce4096ce04`, and the capture DLL is `73760154fdbd0c72ad29fc593b762e7e0ae3940404d400099e4554af9c864e46`.

One child-only replacement was acknowledged. Old child 31552 exited and new child 31608/session 3 loaded the exact package. Automatic runtime attachment then failed with `desktop_capture_target_not_foreground`; the wrapper exited 1 at 18:59:14 UTC and retained that failure. Read-only status/CIM checks confirmed root 28072 remained minimized and the same game 27728/session 3 retained its original creation identity. The new child has no task, stream or input enabled.

The provider intentionally neither activates nor launches a game for DesktopDc. Opening the replacement application's UI therefore requires a separate, explicit focus handoff before attachment. That handoff is being prepared through the existing authenticated RDP command runner; it must verify the exact game foreground, then perform a new explicit start action. It is not a second replacement attempt, and native capture will retain terminal focus-loss checks. Passive images and route validation remain pending.


## R42 one-shot focus recovery closed — October 24, 19:09 UTC

The reviewed ordinary-token RDP worker made exactly one `SetForegroundWindow` call at 19:08:06 UTC. Windows returned false. The game remained visible and nonminimized at HWND 196990; foreground remained the exact BetterGI child 31608 at HWND 3932762. The worker and broker returned exit 1 without timeout, truncation or incomplete output. The wrapper did not call runtime start and did not replay replacement. Root remained minimized, the same game creation identity was preserved, and task/stream/input remained off. SDK/model/focus worker retirement was observed at 19:09:39 UTC. No capture/DPI native success is claimed.

The next change moves a single explicit startup focus opportunity into the RDP child's existing lifecycle, under the task semaphore and runtime start/stop lock. It will use the existing endpoint-only replacement capability before explicit start. Ordinary provider attachment, captures and active controller tasks retain terminal focus-loss behavior. This is a separate R43 source change; R42 evidence remains immutable. The latest GPU sample had 3,581 MiB free at 97% utilization, below V7's unchanged 3,584 MiB admission threshold.

Evidence: `artifacts/research/2026-10-24/r42-focus-recovery-closed-01.json`, the retained `r42-focus-recovery/runs/activate-01` results, and `desktop-dc-automated-startup-plan-01/PLAN.md`.


## R43 startup handoff: corrected compile, October 24

The explicit automated DesktopDc start can yield the foreground from BetterGI to its same-session Genshin window once. It does not refocus an existing runtime. Task ownership, cancellation and stop/restart guards enclose acquisition and cleanup; active capture retains terminal focus-loss behavior. Source07 contains the five-file startup change, including one helper and one test class, plus the import correction.

C#06 stopped during compilation with CS0103 at `GameRuntimeService.cs`; no tests or R43 runtime ran. Its source and failure records remain intact. The single missing `BetterGenshinImpact.GameTask.Common` import was independently checked, and C#07 passed all 1,678 cases with zero failures, errors or skips. Exact evidence is retained in `artifacts/research/2026-10-24/r43-initial-compile-closed-01.json`. Publication and actual RDP startup/capture remain separate pending checks.

## R43 live capture and bounded controller result — October 24

The full build finished at 19:27:32 UTC. One endpoint-only replacement and one explicit startup loaded child 40476 in session 3; the original minimized host and game process were retained. The eight-second passive run completed at 19:33:25 with 123 ordered host snapshots, no input, and clean recorder retirement. Acquisition median/p95 was 30.9796/52.9322 ms; host-start age at server sampling was 64.0646/96.1970 ms. Three saved PNGs were inspected directly and joined to their raw RGB hashes. These are host-acquisition measurements, not render-freshness measurements.

After one explicit host-policy selection, reset completed with three accepted poses at P1. The ordinary short ran for 2.54 seconds, retained 11 observations and 19 input transitions, and failed recovery_limit_exceeded. All three forward grants were 150 ms; the 250 ms source cap did not shorten them. Recognition finished 8.3941, 35.4279, and 5.9663 ms after their deadlines. W-up completed 1.8582, 25.1459, and 8.0807 ms late with no reported release error. Those timings are retained rather than treated as exact physical acknowledgments.

The native trace includes 24 pre-barrier polls and 14 admitted polls, with no Pending or source-age recovery. Ordinary W-down retains a 60 ms response boundary; camera, W-up, and recovery retain 80 ms. The next proposed change waits before synchronous host capture when the response boundary has not arrived. It does not extend leases, source-age limits, recovery budgets, or deadlines, and does not guarantee the remaining capture plus recognition will always fit under contention.

Evidence: r43-binding-passive-independent-audit-01.json (13a43283…), r43-live-validation/r43-passive-visual-decision-01.json (525ded5b…), native result c46f4696…, journal 9e99d531…, and r43-short-failure-diagnosis-01/diagnosis.json (8e38d5ea…). The success-only route auditor retained its expected rejection of this failed route. Its separate schedule-wait field-name mismatch must be corrected in a new parser version before future successful-route acceptance. No continuation was admitted.

## V7 closed numerical audit - October 24

The active-contiguous eager comparison completed all four calls: two original and two resident. All 1,273 ordered gates passed (867 exact, including 160 empty-state checks; 406 unchanged tolerance checks). Every nonempty maximum absolute and relative error was zero. The separate stdlib ZIP/NPY audit decoded all 1,408 boundary arrays, verified 524 cross-arm logical array pairs, 280 state joins and 36 direct saved run002 decoder joins. The 40 documented mask projections remove only unused fixed-storage prefixes. No NumPy, Torch or candidate module was imported by that saved-file audit.

All 80 attention records retain 492-token resident storage and show matching original/resident active geometry at 12 and 24 tokens. Only the first two of the 41 prepared observations were evaluated. Input preservation, hook restoration, source verification, final drains and ownership closure passed; independent status records show both launcher PID 48048 and interpreter PID 40264 absent. The worker's 53.641 seconds includes instrumentation and is not an inference-latency result.

This supports active-extent packing for the tested early eager path. It does not establish a specific kernel cause, graph correctness, later occupancy, rollover, default 200-frame history, sampling, execution feedback or useful gameplay. The next correctness check is the same eager comparison across all 41 saved oracle observations, which can cover empty-to-full occupancy but not the first eviction at observation 42.

Evidence: `artifacts/research/2026-10-24/native-p2p-v7-closed-audit-01/ASSESSMENT.md`, `report-01.json` (SHA-256 `330b9cc83a6c3b7e2320ac29c737fff42886a49d5ab052ccd5dfd243068be4aa`), its five-test `validation-01.json`, and `native-p2p-v7-gate-scope-review-01/review.json`. The earlier verifier-only isolated-source path error and its corrected audit remain recorded; no GPU run or candidate file changed.

## R44 response scheduling and first live route - October 24

Source08 moves the existing response wait ahead of a DesktopDc task-owned capture. The three-file change added 24 C# cases; all 1,702 selected cases passed, and full Debug/Release publication succeeded with unchanged source. R44 replaced only child 40476 with child 48316/session 3. The root remained minimized and game 27728 kept its creation identity. Detached staging changed only the new package's persisted DesktopDc policy to observe-only before startup; explicit host selection followed visual inspection.

The eight-second passive run recorded 122 distinct host snapshots. Acquisition median/p95 was 31.7108/52.5433 ms; host-start age at server snapshot was 76.2678/88.8449 ms. Three RGB images were inspected. These are host-acquisition intervals, not render timestamps or input acknowledgments.

Reset a94c10beaafd452b984af69a4c72835b completed, followed by short ebbcee6079224f8597542b9ea5493598. The short reported verified completion, 49 observations and 5,523.0096000134945 ms terminal elapsed. Three final poses agreed at (-873.875, 2275.076171875), 1.0220 units from P2, with normal motion. The initial and final images visibly show movement from the street to the waypoint-side grass; input release and wrapper cleanup had no reported errors.

The independent timing join found 49 polls and 49 admitted captures, no pre-barrier discards, no Pending states, and no lease expiries or recoveries. Three physical W-downs retained the 150 ms lease; 25 distinct-source renewals retained 100 ms. Minimum renewal headroom was 22.4803 ms. Capture median/p95 was 34.7969/48.7602 ms, recognition 27.0826/31.3819 ms, and all recorded source ages were below 100 ms. R43 had 24 discarded early captures and three expired grants. These separate live runs do not isolate workload effects or establish long-run reliability; no dedicated prewait-duration telemetry was added.

The full route auditor's first rejected report is preserved. Pinned NavigationBaselineTask first samples elapsed after closing input, publishes evidence, then resamples elapsed and enforces its deadline. Here the journal has 5,218.472400009632 ms and the terminal result 5,523.0096000134945 ms. Their 304.5372000038624 ms increment spans publication and surrounding phase/clock overhead. The independently reviewed v3 correction preserves all other semantic joins, requires finite monotonic elapsed values below the existing 30,000 ms deadline, and binds read/final-window completion to the earlier workflow end. Its 64 retained and 12 focused cases passed across two preserved test runs. Root reran only closed-artifact analysis: native-baseline-r44-01-audit-02.json accepted the route, SHA-256 facfee8d1ff62d9465733c761f853607f8e73d765dea6aa76e3501f528ec65be. The sealed analyzer manifest is 2cb3ef6977b2a1a2766b76400e927510935baa2131cca6f89e39539fe4c86bd5. This establishes the ordinary short result; typed courtyard continuation remains an isolated, unapplied candidate.

Evidence: `artifacts/research/2026-10-24/desktop-dc-precompile-source-08.json`, `desktop-dc-csharp-08-validation.json`, `r44-build-outcome.json`, `r44-hot-replace.json`, `r44-live-validation/`, `r44-runtime-binding-independent-review-01.json`, `r44-short-timing-audit-01/report-01.json`, and the preserved rejected `r44-route-audit-bindings/native-baseline-r44-01-audit.json`.


## P2P V8 full-history eager diagnostic on 24 October

The one reviewed V8 run completed 41 resident eager calls, with no original-model rerun. All 20,542 runtime gates passed with zero reported maximum absolute error. The 369 direct saved-reference comparisons cover every frame's context and eight decoder heads. The run fills the 492-token storage for history41; it does not evict a real observation or validate a CUDA graph, sampled actions, default history200, controller latency or gameplay quality.

The run saved 41 compact step archives plus three canonical-hash files: 40,998,688 raw tensor bytes and 36,523,770 serialized bytes. Peak allocated/reserved GPU memory was 480,851,456/534,773,760 bytes. Its 221.578-second instrumented interval includes preflight, detailed comparison and cleanup; it is not inference latency. Owned launcher 17400 and interpreter 27804 both exited, independently confirmed through CIM at 20:40:03 UTC.

Report: `artifacts/research/2026-10-24/native-p2p-oracle-eager-41-v8/run-001/report.json`, SHA-256 `6857b5860f731c5adf86921506120af7adf57f361d17742111865062df4d1428`. Ownership report SHA-256: `99bd3bcdb59dfe6cec624e06ed1fc18f537295469ad16720dfecd17200323b9c`.

The first separate closed audit exited 1 at its expected-layout check. Its table expected 20/20 categories for decoder heads 6/7, while the saved arrays contain 23/17. The original action mapping, original saved reference and all 41 V8 headers agree on 23/17. No numerical comparison failed in the GPU report. A separately sealed correction changes only those two expected widths; its audit implementation is byte-identical. Root verified all 73 dependency pins and the exact reverse diff, and all 10 focused tests passed. The original failed attempt is preserved in `native-p2p-v8-closed-audit-01-attempt.json`, SHA-256 `c9bc94492a39dbb9899cd29000fd3bc438c05b0b5dec4f951824989a97e64807`.

The corrected reader completed every audit check on its first execution, then rejected publication because its output directory already exceeded the inherited JSON capacity. That failed publication is preserved in `native-p2p-v8-closed-audit-02-attempt.json`, SHA-256 `6edc32ebad5a2b44c2b8c2474818ad0f29b2a78a25840e7a4005d4ca802a4ce4`. The same frozen reader, source seal and evidence succeeded when directed to a fresh isolated output directory. No model execution was repeated.

The accepted closed audit is `native-p2p-v8-closed-audit-03/audit.json`, SHA-256 `5ad57cde70ea8204b1f23c41bdfc6871445b10f97b53970a5ba0d72dd798cd42`. It accepts all 369 saved-original decoder comparisons and 102 historical first-two-step anchors, reconstructs 82 expected pass states, and matches all 20 actual final state hashes. The correction manifest is `e48022ceac68683180b07b5295dd6379bb6b35b90487d5d3f6a1c79cae7fa9f7`; the independent correction review is `54867d469a0cd1184ab9cf371b0c3a0073f63caba1fdf7d839cc35581209b59a`. Original later KV arrays are unavailable, and full intermediate states were not archived. The result supports the tested eager reconstruction only; input authority, training eligibility, graph correctness, eviction and gameplay quality remain false or unestablished.

## R45 continuation integration and verification on 24 October

Root applied the reviewed 16 C# and five Python payloads after verifying the previous source and tool snapshots. Source09 adds typed host continuation from the successful P1-to-P2 seed, followed by explicitly requested P2-to-P1 and P1-to-P2 legs. Each leg retains capture but acquires and releases its own input ownership. The latest successful predecessor, build, process, session, capture epoch and fresh endpoint pose must match. The new child requires a new seed after replacement. Existing deadlines, response waits, freshness and lease bounds remain unchanged.

The C# run finished at 20:50:23 UTC with all 1,770 cases passed, no failures, skips or source changes. Its validation SHA-256 is `bb6311c363304867c20cd52d39c778b5c2b467b03bdf789f48c528fef84ac46c`; source09 is `63b144fb337a0236cb2b142364baae65341ea1e4c469c4f945233a9c95b858eb`. SDK process 31212 was independently confirmed retired before full R45 Debug/Release publication started at 20:51:13 UTC. Live continuation and sustained cycling remain to be tested.

The full build outcome is `70832d73230d54f638dbd4f8ce2e8992c55840de6a88aed44724da89c8d95375`; release manifest `feab44267563fce58b6b95acfa3bce21f638204379862837968a75e8ab2a7d98` records the new DLL `e32be549a59da13e8d577427463b5f7b1dbb5a2b7f6a1321c37bdbbb811af1be`. The live helper passed 123/123 CPU/mock cases and independent source/seal reviews. Root verified its 599 distinct preparation/tool pins before the single replacement. Helper manifest: `6c4d309ab4d61774723d227bdbee26e01ec96b58bc361009e8fc6806dbbb3f14`.

Endpoint-only replacement and one explicit startup completed at 20:57:05 UTC. The composite proof is `55bad29d03eab451abc36c3292471e095c667acec15c6bed2ae006c0f106c6cb`; its endpoint/start records are `ccd03a6419791da126fc661944bebfdbf6b7d9ba245d6bb2bcadf1557c0b0a82` and `cd1c783885213b8f1b02806547b1696c786314d412910d737a95086af18ab9bc`. Detached staging changed only the new package policy to observe-only. The child is PID 20928, session 3, nonce 167fdaf9aa12423cae61678a476fad50. The copied 543-file/9,633,955-byte tool snapshot manifest is `ca1b27427f0acf02b1cba2572a1b9adcb3e61e214306e591289b1e264eed28c5`. A separate CIM check at 21:02:02 confirms old child 48316 absent, new child present, and original root/game creation identities intact. No native R45 route has been requested at this checkpoint.


## R45 fresh capture and three accepted route legs on 24 October

The final live binding was fixed before capture: `r45-live-validation/r45-validation-binding.json`, SHA-256 `98f383526b4840b54f42078b22c61756621f22f63bd9ef5194650390de11f186`. The separate closed-route binding is `r45-route-audit-bindings/runtime-binding-01.json`, SHA-256 `f5715edee0d14b8620e8d646a020ba50ea88c471687f56edb30c1c6886389550`. The R45 auditor passed 109/109 cases and independently verified its 592-file closure; package SHA-256 `30620ef76dedb11d0a43f694d9bd4d39a4c24ff0a2e78f0ed2da33fa08122878`.

The eight-second passive check recorded 126 distinct snapshots. Acquisition median/p95/max was 31.5261/51.5064/58.8200 ms; host-start age at server snapshot was 66.8817/91.8474/114.3106 ms. Root inspected all three spaced RGB images: normal game view, standing character, no BetterGI overlay or open dialog. The first visual decision included file pins but omitted the complete per-image capture records, so the launcher rejected it before importing the client or querying/mutating the live app. The preserved correction adds exactly those unchanged records. Accepted visual decision SHA-256: `6491388149480f0bef547afd43926ed8033637e0f469385dea2572317d6934bb`. Host timestamps do not establish rendered-frame age.

| Actual route | Run ID | Reads | Terminal ms | Workflow ms | Recorded W-downs / forward grants | Admitted recoveries |
|---|---|---:|---:|---:|---:|---:|
| Fresh P1 to P2 seed | `4ab9072ba2a04f28980e21a791b23dd7` | 49 | 5778.344 | 5466.838 | 4 / 27 | 0 |
| P2 to P1 return | `74487169dd094dbfa4988791214f7ef1` | 48 | 6114.806 | 5813.177 | 5 / 23 | 1 |
| P1 to P2 forward | `339ed37667834c3ea229dcc2f3b7e0f1` | 48 | 5740.891 | 5434.512 | 4 / 25 | 0 |

The seed used one authorized navigation reset. The return and forward did not reset or teleport. All three reported verified completion and null inputReleaseError, and their wrappers completed cleanup without error. Three final normal-motion poses agreed at each endpoint, respectively 0.6947, 0.9441 and 0.7056 map units from the target. Both continuations retained epoch `a0d8bbc3-0073-4a43-988e-e4332fa93a93`, exact build/child/game identity, strict newer-source admission and the actual predecessor endpoint. Each leg acquired and closed its own input owner. These are software/capture evidence joins, not physical input acknowledgments.

The accepted audits are `native-baseline-r45-01-audit-01.json` (`be2890a88a1e6ac3e0d3cadc24687257fde72830407c8a8d311696958c225ccc`), `native-courtyard-return-r45-01-audit-01.json` (`2505f69e3047242314573e5bc57d9b57e0468bf994643200910b1f2f6bd484d0`) and `native-courtyard-forward-r45-01-audit-01.json` (`abba58e965a88a3031ce8e928e1926e747972ee6122af6045b5ede669902d11c`), all in `r45-route-audit-bindings/`. Their exact predecessor proofs are retained beside them. The final forward proof is `174790fbb55581e2faae7c136957c63feac1305c6331d8cca073dbf42daff0fe`.

The return's single recovery was a lease expiry. Read 21 acquired eligible snapshot 2140 after the 60 ms response barrier. Capture took 59.9460 ms and recognition 38.3531 ms; recognition completed 10.356 ms after the 150 ms deadline. Recorded W-up completion to the next W-down completion was 143.7937 ms, including the 80 ms release barrier, a 31.572 ms recovery capture and 26.052 ms recognition. There were no Pending states, stale-source rejections, duplicate captures or early-barrier discards. The already-overdue 50 ms schedule check consumed 0.055 ms. This identifies the measured stages, not a hardware cause. The exact diagnosis is `r45-return-recovery-diagnosis-01/report.json`, SHA-256 `5965179aec37b224d3107309fa121864f5f856f31ffa5ff402ef84bea920b1a2`.

The next live experiment is a separately reviewed four-leg supervisor with a bounded admission window, immediate terminal/envelope recording, unchanged client/server checks per leg and retrospective full audits. Root/game process checks belong to the batch boundary. The existing individually audited-predecessor helper is not represented as the batch admission path. A lost response or an old completed predecessor cannot establish that a new owner has retired.

## Direction toward broader SIREN gameplay

Use the Lumine comparison to suggest experiments while preserving the distinct pretrained starting points of Open P2P and GameScaling. P2P latency does not establish instruction-following quality. GameScaling's complete language-conditioned action latency must be judged against the action horizon, with original preprocessing and action semantics retained. Cache and graph parity precede attributing behavioral changes to learning. V9 has now passed the two actual full-cache eviction comparisons and closed-file audit recorded above. V10 run001 did not complete its required production-predict timing sample; no sustained latency or learned-gameplay conclusion follows from that attempt.

Expand from successful narrow skills using temporally aligned frames and execution evidence, including recoveries and takeover examples. Keep proposals, acceptance, software execution intent and physical-action uncertainty distinct. Damaged intervals and projected/synthetic labels are not expert training targets. Hold out sessions, routes and tasks, and compare completion, interventions, recovery, latency and stale-action rejection against scripted and unchanged pretrained baselines. Test fast control with occasional planning only where measured task quality supports it. Training has not begun; the current live success belongs to the native navigation controller.
