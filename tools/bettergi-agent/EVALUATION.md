# Comparing gameplay quality

Use actual task outcomes to compare the policies once both can meet their controller budgets while Genshin is rendering. The current GameScaling graph is about 494 ms median in offline replay against a 200 ms action horizon; its existing input gate will withhold those predictions. A fast parser, accepted request, or no-op chunk is not evidence of useful play.

## Matched live trials

1. Pick a short, repeatable goal with a visible finish and measurable partial progress: reach three marked landmarks, approach an NPC and open the intended dialogue, or finish a fixed encounter. Define the time limit, success evidence, progress unit, and intervention rule before either model runs. Start with five trials per configuration; report counts, not a universal competence claim.
2. Restore the same location, facing direction, character/party, health, quest/menu state, enemies, camera sensitivity, key bindings, resolution, frame cap, and network conditions as closely as possible. Save a starting screenshot/video segment and note resets that cannot reproduce the state. Give changed states distinct `startStateId` values. Alternate model order across repetitions.
3. Use one policy process at a time on the same GPU as the game. Record the BetterGI build, checkpoint/source hashes, adapter settings, history, prompt, seed if applicable, graph mode, controller cadence, freshness threshold, and other GPU workloads. Give changed policy settings a new `configurationId`; use `gpuContext: "game-shared"`. Keep the model's native action horizon: P2P 50 ms, GameScaling 200 ms. Do not extend actions or relax freshness gates to improve a score.
4. Record the full run with `stream_client.py --record-dir ... --output ...`. Count startup, history fill, graph checks, stalls, and resets in operational trial time. This aggregator includes all recorded decisions; it does not silently discard warmup. A separate steady-state experiment needs a separately identified artifact and declared interval. Use the same operational time limit for both models.
5. A human reviews video plus execution receipts and labels success, completed/total progress, elapsed time, and interventions. An intervention is one human takeover or corrective input episode; record its time and reason. A configured hard stop is the trial endpoint, not itself an intervention. Reviewers should use the same rubric, preferably without the model name. Keep failures and timeouts; leave unavailable labels `null` rather than guessing.

The original live benchmarks used GameScaling's generic exploration prompt and
P2P's no-text embedding. Their results do not establish equal instruction following.
For new trials, GameScaling accepts `--instruction "..."`; P2P accepts a
`--goal-embedding` file produced from the same text by `encode_goal.py`. Record
the exact instruction and use a new configuration with `mode: "trial-text"`.
GameScaling records its complete rules in policy metadata; its action-only mode
still produces controller actions, not a natural-language plan. Without these
options, retain `fixed-generic-text` for GameScaling and `none` for P2P.

Resident navigation with `--action-hold-ms 100` is a separate controller
configuration: it extends P2P's requested 50 ms hold while retaining the original
proposal in the evidence. Do not pool it with the native-horizon comparison above.

Record the observation clock as part of the configuration. Reports with
`observationAgeClock: "source_freshness_anchor_when_known; host_capture_request_fallback"`
use the declared immutable source freshness anchor when metadata is present. Their
`observationTimestampMs` can be subtracted from a receipt's first `startedAtMs`
to measure anchor-to-issued-input latency. WGC contract version 2 uses the earlier
of reported compositor time and first acquisition, labeling that choice per frame;
some RDP timestamps are future-dated. This does not establish absolute render age.
Older reports use the host capture request, which can hide capture-cache time.
Keep host, reported-compositor, and first-acquisition measurements separately labeled.

When the bridge advertises `supportsStartBeforeMs: true`, every submitted action
also carries `startBeforeMs = observationTimestampMs + maxObservationAgeMs`.
The server checks that deadline on submission and again before issuing the first
input step, covering transport and executor delays after the client age check.
An accepted action can therefore end with `start_deadline_expired` and zero
applied steps. Once its first step starts, the existing chunk hold and expiration
rules continue unchanged. The wire identity `observedAtMs` still uses the host
capture request; it is not replaced with the source anchor.

`firstInputDeadlinePolicy` records the advertised capability, whether server
enforcement was requested, and the configured clock/limit; each submitted
deadline appears on its decision and proposal event. Older bridges omit that
capability and receive no new request field. Their `client-proposal-only` label
means the strict configured age was checked before submission, but is not
guaranteed at first issued input. Capability metadata describes the protocol
contract; use actual execution receipts to establish what was applied.

For action quality, review whether the executed movement, interaction, camera change, and timing advance the visible objective. Record concrete examples and timestamps in `actionReview`. An idle chunk may be appropriate during a transition; movement may be wrong. Do not convert action frequency or inactivity into a competence score.

## Offline action comparison

Compare both policies on the same saved frames and explicitly declared histories, without controlling the game. Record frame hashes, order, preprocessing, history cadence, and reset/warmup behavior. Judge proposed chunks against the pictured situation with human notes. This tests action plausibility; only a live trial can establish what happens after an action.

The default `benchmark.py` mode is latest-frame replay: different model speeds can skip different frames. These runs are not automatically a matched same-frame sequence. Align individual comparisons by image hash (for cyclic reports, `frames[sample.frameId % len(frames)]`) and inspect history differences before claiming a paired comparison.

GameScaling's `--sample-mode independent` instead cycles the supplied images,
clears chat history before each case, retains its validated graph, and uses
`seed + round` for each image cycle. It records `sourceImageIndex` and `sampleSeed`.
This supports matched static-image comparisons, not a temporal or gameplay trial.
Both benchmark and stream clients accept `--sampling sample --temperature 1
--top-k 0 --top-p 1`; greedy selection remains the default. These values match
upstream's sampling choices, while history, preprocessing, reasoning, dtype, and
token limits remain independently specified. The graph checks its first two full
sampled outputs against eager generation with restored CUDA random state.

GameScaling also exposes an experimental `--gamescaling-prefix-cache` option in
both clients. It requires `--cuda-graph` and `--history 0`; it is disabled by
default and rejects P2P, padded batches, unsupported caches, and image histories.
It snapshots the text strictly before `vision_start`, including every hybrid
cache tensor and Python initialization/state flag, and restores existing storage
before processing the fresh image. Each suffix uses the complete prompt's
original multimodal positions. Image processing and sampling settings stay the
same. A changed text prefix or cache allocation rebuilds the snapshot.

Every new snapshot requires two prefill comparisons against the original full
prompt, with cache/logit `rtol=1e-3, atol=1e-3`, exact non-floating state, and two
exact complete-token comparisons against original `model.generate`. Sampling
checks use paired CUDA random state and restore the caller's subsequent state.
The local validation counters reset on rebuild even after earlier graph checks
passed. Any failed check aborts the prediction; there is no silent fallback.
Numerical closeness does not mean bitwise floating-point equivalence.

Record offline `adapter.cudaGraph.prefixCache`, live
`finalPolicyMetadata.cudaGraph.prefixCache`, and each decision/sample's
`prefixCache`. Live `policyMetadata` remains the immutable episode-start snapshot.
They expose prefix/suffix lengths, snapshot bytes, rebuild reason/generation,
setup, snapshot-copy, restore, suffix, inspection, position, prefill validation,
and full-action validation times, plus actual maximum cache/logit differences.
`snapshotCopyMs` is included in `setupMs`; `totalPrefillMs` includes prefill
validation but excludes full-action validation. `fullActionMs` includes all of
these costs and complete decoding. Report startup/rebuild separately from steady
reuse without removing it from operational trial duration.

This integration has CPU tests with tiny random Qwen3.5 modules, including
original-generation comparisons under simulated CPU replay. Those checks do not
establish real-checkpoint parity, CUDA graph performance, or gameplay quality.
The 2026-10-23 FP16 check on the real GameScaling-0.8B-S3 checkpoint **failed**
the unchanged numerical gate before returning an action. On three saved r8
images, repeated full-prefill controls were bitwise identical, but splitting at
740 tokens or a 64-token-aligned 704 tokens failed cache/logit closeness. Maximum
observed differences were 0.0390625 in cache state and 0.0380859375 in logits.
Six bounded complete-token diagnostics on one image matched original greedy and
paired-seed sampled outputs; these matches do not supersede the failed gate.
The option remains **default-off and unvalidated**. The production qualification
comparison stopped at the failed smoke check. Local numerical evidence is in
`artifacts/research/2026-10-23/gamescaling-prefix-validation/diagnostic-summary.json`.

An additional, explicitly authorized **offline performance diagnostic** bypassed
only the known floating-point numerical failures inside an ignored wrapper.
Tracked tolerances and production behavior were unchanged. Every diagnostic
report records `numericGatePassed: false` and `productionEligible: false`, and
preserves failed tensor checks and arrays. There was no controller input.

The counterbalanced order was baseline A1, prefix B1, prefix B2, baseline A2,
then sampled prefix. Each arm used two validation warmups and nine measured
independent cases: the same three saved r8 images and seeds, 384-pixel input
width, history 0, full 834-token prompt, and 64-token output cap. The prefix was
740 text tokens. Timings below are milliseconds; p95 uses linear interpolation.

| Arm | Full action p50 / p95 | Prefill plus first selection p50 | Remaining decode p50 |
| --- | --- | --- | --- |
| A1 baseline, greedy | 1608.7 / 1871.5 | 526.9 | 876.0 |
| B1 prefix, greedy | 868.0 / 899.5 | 178.4 | 678.9 |
| B2 prefix, greedy | 879.1 / 985.8 | 188.7 | 672.2 |
| A2 baseline, greedy | 1073.7 / 1415.3 | 384.4 | 680.6 |
| Prefix, sampled | 886.7 / 960.8 | 189.3 | 669.5 |

The prefill column subtracts preprocessing from first-token wall time and includes
first-token selection; it is not isolated GPU kernel time. **0 of 45 actions
finished within 200 ms**; the fastest prefix case was 831.5 ms. All 36 greedy
outputs were 30-token no-ops. Sampled outputs used 30–35 tokens, with three no-ops
out of nine. Parsing and protocol compatibility passed for all 45 cases; these
are static-image results, not gameplay outcome measurements.

Complete generated IDs matched for all cases: nine A1 and nine sampled cases
passed post-timing original eager generation (paired CUDA RNG for sampling);
the other 27 cases matched their corresponding A1 IDs. This bounded token
agreement does not override the failed numerical gate. Each prefix arm retained
80 failed cache/logit comparisons across its two numerical validations, with
maximum cache/logit absolute differences of 0.0390625 / 0.0380859375.

The snapshot retained 54 tensors totaling 32,342,064 bytes (30.84 MiB). Prefix
setup took 723–797 ms, including 10.7–13.7 ms to copy the snapshot; median restore
cost was 1.8–2.6 ms. Two numerical comparisons took 1.44–1.55 seconds per prefix
arm, including diagnostic copies of failed arrays. Two complete-action checks
took 5.61–6.32 seconds. Model loading took 10.4–15.6 seconds, and the two warmups
took 10.7–11.8 seconds; they are excluded from the measured-action table, not
from operational startup. Peak Torch allocation was about 2371 MiB in every arm
and may have been dominated by loading.

Treat differences between arms as diagnostic observations, not a clean speedup
estimate. A1 to A2 baseline median drifted from 1609 to 1074 ms. Genshin rendered
on the same GPU throughout, and a CPU-only .NET build ran concurrently. Bounded
whole-GPU telemetry showed changing clocks (approximately 1305–1583 MHz median
across timed windows) and cannot attribute work to this model alone. A1 and the
sampled arm also retained CUDA RNG and copied the full prompt/output inside the
timed call for later validation; other arms copied only generated IDs. That
instrumentation difference was not measured separately. The finalized summary,
per-case IDs, telemetry, costs, and limits are saved under
`artifacts/research/2026-10-23/gamescaling-prefix-validation/performance-diagnostic/summary.json`.

Until a separately recorded GPU validation passes, treat this option as a failing
experiment. For a future bounded matched saved-image comparison, keep the same images,
seeds, history, sampling, and game/GPU load in both arms; add only this flag to
the second arm. Preserve all validation measurements and report actual generated
tokens and outputs alongside steady latency.

Keep offline latency separate from live latency under game/GPU contention. Label GPU context accurately, including `unknown` when it was not recorded. Never run two benchmark models concurrently for the headline latency comparison. GameScaling's previous no-op replay output establishes neither failure at every task nor successful gameplay.

## Aggregate saved trials

`evaluate_trials.py` uses only the Python standard library. It reads finalized `stream_client.py` reports, optional recorder directories, and offline benchmark reports. All artifact paths below are relative to the manifest file. This example is a template with **unlabeled outcomes**, not a measured result:

```json
{
  "version": 1,
  "trials": [
    {
      "id": "landmarks-p2p-01",
      "kind": "live-control",
      "model": "open-p2p",
      "configurationId": "p2p150m-history200-graph-v1",
      "goalId": "reach-three-landmarks-120s",
      "startStateId": "bridge-facing-east-v1",
      "gpuContext": "game-shared",
      "conditioning": {"mode": "none"},
      "report": "landmarks-p2p-01.json",
      "episodeDirectory": "episodes/landmarks-p2p-01",
      "evidence": "episodes/landmarks-p2p-01/frames.mp4; use frames.jsonl for timestamps",
      "actionReview": null,
      "outcome": null
    }
  ]
}
```

After human review, replace `outcome` with an object containing `source: "human"`, `rater`, and optional `success` (boolean/null), `elapsedSeconds`, `interventions` (integer), and `progress: {"completed": ..., "total": ..., "unit": "landmarks"}`. `completed` means progress achieved during this trial, excluding progress already present at the start. Include concrete notes/evidence. Missing values stay missing. An unsuccessful completed trial is `success: false`; an unreviewed trial is `null`. Observation-only and offline trials cannot receive gameplay outcome labels through this utility.

```powershell
& artifacts/agent/envs/gamescaling/Scripts/python.exe tools/bettergi-agent/evaluate_trials.py artifacts/agent/trials.json --output artifacts/agent/trial-summary.json
& artifacts/agent/envs/gamescaling/Scripts/python.exe -m unittest discover -s tools/bettergi-agent -p test_evaluate_trials.py -v
```

The result contains per-trial records and per-model/configuration groups, separated by trial kind, goal, start state, GPU context, and conditioning. Compare matching groups across models. Success uses only explicit boolean labels and reports its denominator; progress averages each labeled trial's fraction, separated by unit. Outcome time is human-labeled wall time, not a duration inferred from MP4 playback. Group timing percentiles pool individual decisions using linear interpolation; they are not averages of trial percentiles. Report per-trial values alongside pooled values so longer runs cannot hide variation.

`progressPerSecondByUnit` divides each human-labeled trial's completed progress by its own positive `elapsedSeconds`, then summarizes those per-trial rates within each explicit unit. Trials with zero or missing elapsed time contribute no rate. This is the mean of individual trial rates, not total progress divided by total or averaged duration.

A terminal `unacknowledgedAction` remains a decision with status `unacknowledged`, even when the client exited before appending its completed decision record. Its submission and acceptance remain unknown; missing parser flags and timings stay unavailable. Exact request IDs prevent double-counting, and the unresolved latch takes precedence over any saved, unvalidated reply. `acceptedPerDecision` and `serverRejectedPerSubmitted` are `null` when any decision's admission outcome is unknown. `serverRejectedPerAcknowledgedRequest` reports the narrower ratio using only confirmed accepted/rejected replies.

`unacknowledgedRequestReceiptCoverage` separately counts matching receipts within the same trial. Applied steps in those receipts remain execution evidence without turning a lost acknowledgement into a known reply or proving that the game responded.

| Measurement | Existing source and meaning |
| --- | --- |
| Complete inference time | Live `decisions[].policyWallMs`; adapter `fullActionMs` also retained when present. Offline samples expose `fullActionMs`. |
| Freshness | Live `estimatedObservationAgeMs` is the client's conservative estimate at proposal time. `withinDeclaredFreshnessLimit` compares it with the saved strict threshold. Offline `observationToActionMs` is replay age, not live transport/capture latency. |
| Submission/rejection | `acceptance.type` distinguishes accepted, server-rejected, and client-not-submitted proposals. Counts retain reasons such as stale observations, missed model budgets, or observation-only mode. |
| Actual input | Receipts' `appliedSteps` count intervals issued to the input backend. Cancelled/replaced chunks can contain applied steps. Accepted requests alone are not execution proof; input issuance is not proof the game responded. |
| Controller timing | `startedAtMs - acceptedAtMs` measures acceptance-to-first-issued-step. With a matching proposal, `startedAtMs - observationTimestampMs` uses the declared observation clock; `startedAtMs - capturedAtMs` remains host-request-to-first-issued-step. Neither is photon-to-display latency. |
| Missing data | Receipt coverage reports matched IDs; recorder loss/error and server receipt loss remain visible. Episode-only proposal events lack parser flags; unavailable metrics are `null` with zero known samples. |

Use `frames.jsonl` to map video indices to server capture time, and `events.jsonl` to align proposals and applied inputs. The full report is preferred where it duplicates events, so receipts are not counted twice. Review recordings with dropped frames or receipt errors before using them for outcome labels or training. The utility does not infer gameplay success, goal-conditioned competence, an action-quality score, or a statistical winner.

## Current graph decode attribution

The 2026-10-23 prefix-disabled diagnostic preserved the 834-token prompt, original
generation/stopping logic, graph/cache identity and complete tokens for three
fixed cases against uninstrumented graph and eager references. One repeat also
had a CPU/CUDA timeline. No production code or numeric gate was bypassed.

Across 87 decode steps, GPU graph-stream intervals were 32.55/81.80 ms p50/p95;
host graph calls were 3.24/4.98 ms. Graph intervals covered 93–96% of event-arm
decode time, including scheduling gaps. Token-copy host calls mostly waited for
that preceding work: all 192 actual GPU copies in the trace totaled 0.748 ms.
The 29 graph launches contained 59,653 kernels with 710.44 ms summed duration:
374.77 ms GEMV, 289.52 ms other operations, 44.32 ms attention and 1.83 ms convolution.
Removing host token checks or adding causal-conv alone is unlikely to provide the
needed order-of-magnitude improvement. Fused recurrent/normalization operations
and projection efficiency remain candidates, not measured improvements.

The trace inflated prefill substantially; the shared game/foreground workload
also affects stream intervals and kernel timings. This is attribution evidence,
not an uncontended benchmark or a fixed latency floor. Local evidence is in
`artifacts/research/2026-10-23/gamescaling-decode-attribution/{report,summary}.json`
and its single trace/telemetry, reproduced by the ignored
`diagnose_gamescaling_decode_attribution.py` research wrapper.
