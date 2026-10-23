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
`observationAgeClock: "source_render_when_known; host_capture_request_fallback"`
use WGC compositor time when source metadata is present. Their
`observationTimestampMs` can be subtracted from a receipt's first `startedAtMs`
to measure compositor-to-issued-input latency. Older reports use the host capture
request, which can hide time already spent in a capture cache. Keep host and source
measurements separate; unknown-source fallback does not establish compositor age.

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

| Measurement | Existing source and meaning |
| --- | --- |
| Complete inference time | Live `decisions[].policyWallMs`; adapter `fullActionMs` also retained when present. Offline samples expose `fullActionMs`. |
| Freshness | Live `estimatedObservationAgeMs` is the client's conservative estimate at proposal time. `withinDeclaredFreshnessLimit` compares it with the saved strict threshold. Offline `observationToActionMs` is replay age, not live transport/capture latency. |
| Submission/rejection | `acceptance.type` distinguishes accepted, server-rejected, and client-not-submitted proposals. Counts retain reasons such as stale observations, missed model budgets, or observation-only mode. |
| Actual input | Receipts' `appliedSteps` count intervals issued to the input backend. Cancelled/replaced chunks can contain applied steps. Accepted requests alone are not execution proof; input issuance is not proof the game responded. |
| Controller timing | `startedAtMs - acceptedAtMs` measures acceptance-to-first-issued-step. With a matching proposal, `startedAtMs - observationTimestampMs` uses the declared observation clock; `startedAtMs - capturedAtMs` remains host-request-to-first-issued-step. Neither is photon-to-display latency. |
| Missing data | Receipt coverage reports matched IDs; recorder loss/error and server receipt loss remain visible. Episode-only proposal events lack parser flags; unavailable metrics are `null` with zero known samples. |

Use `frames.jsonl` to map video indices to server capture time, and `events.jsonl` to align proposals and applied inputs. The full report is preferred where it duplicates events, so receipts are not counted twice. Review recordings with dropped frames or receipt errors before using them for outcome labels or training. The utility does not infer gameplay success, goal-conditioned competence, an action-quality score, or a statistical winner.
