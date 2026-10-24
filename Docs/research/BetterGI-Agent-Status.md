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
| Training | Not started. Model proposals and incomplete recordings are not expert action labels. |

## Latency evidence

Each row describes its own workload. Input history, execution backend, capture, instrumentation and machine load differ; controlled task-quality comparisons are still pending.

| Measurement | Median | 95th percentile |
|---|---:|---:|
| P2P earlier offline CUDA graph, history200 | 27.32 ms | 28.14 ms |
| P2P earlier live shared-GPU graph phase | 55.10 ms | 73.93 ms |
| P2P latest instrumented retained-frame run, history41 | 172.69 ms | 183.35 ms |
| GameScaling optimized offline graph, 30-token action | 494.48 ms | 531.37 ms |
| GameScaling earlier live shared-GPU run, after validation calls | 1,850.91 ms | 2,586.24 ms |

The latest P2P run completed all 40 measured predictions and passed its closed-report audit. None met the 50 ms target; the scheduler skipped 116 elapsed release slots. GPU event timing places most of the measured stream interval around model graph execution. These event intervals include scheduling effects and do not establish exclusive kernel time.

A separate read-only sample at 23:15:42 UTC reported active software thermal clock limiting, 88 C, a 990 MHz core clock and 96% device utilization after the model worker exited. This observation describes that sample; it does not isolate the cause of earlier prediction latency.

## Next steps

The build needs three upstream asset packages that are missing locally: `BetterGI.Assets.Map` 1.0.25, `BetterGI.Assets.Model` 1.0.39 and `BetterGI.Assets.Other` 1.0.28. The one-time restore approval for the [official NuGet source](https://api.nuget.org/v3/index.json) remains pending after automatic approval review blocked the source change.

Once restore is authorized, run the complete source11 test/build checks, replace only the RDP child, and establish a fresh navigation seed before testing the repair. The latest failed owner cannot resume from an older successful proof. In parallel, use the model timing evidence to select a bounded kernel/scheduling diagnostic, then compare task success and interventions on actual game scenes before selecting a training approach.

Controls and launch instructions: [RDP automation](../../tools/rdp-automation/README.md). Research scope: [first sprint](BetterGI-Agent-First-Sprint.md) and [original research](BetterGI-Agent-Research-2026-10-23.md).
