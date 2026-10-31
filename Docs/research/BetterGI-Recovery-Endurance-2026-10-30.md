# Recovery and endurance qualification — October 30, 2026

The bounded ten-minute continuous photo-queue milestone **passed** in the original R59 RDP pair: 124 verified photos and 167 navigation legs over 649.49 seconds, on one model load and one controller lease. Independent replay matched the sealed audit. Earlier publication failures and the natural G4 stair-recognition failure remain intact. G4 remains the ordinary/default observer; the frozen CNN has separately bounded experimental photo authority. Natural-miss recovery and general-world navigation remain unqualified.

## Qualification gates

1. Intentionally leave the successor queue slot empty after the lamp and junction requests. Preserve the resulting failed run. Require the independent failure audit to prove the released endpoint, no pending actions, no proposals after the boundary and the actual `missing-successor` outcome.
2. Re-observe the same pinned RDP pair without input. Require current world readiness and fresh native positions at the junction. Classifications replayed from retained H.264 are identified as decoded evidence, not original RGB. An operator STOP, unknown action, changed owner, thermal trip or missing telemetry is not an automatic recovery permission.
3. Start a new, explicitly addressed lease and qualify the endurance profile on a short automatic run. Keep the failed lease, passive re-observation and successful successor separate.
4. Target at least 600 seconds between positively witnessed native gameplay dispatches in one GPU-loaded lease, ending through an explicit finish at a verified photograph. The whole run must pass independent receipt, photo, route, owner and timing audits. A capacity closure or a timeout does not satisfy this milestone.

The opt-in `endurance-v1` profile caps one lease at 900 seconds wall time, 40 batches, 256 physical legs and 384 MiB of recording. Ordinary runs retain their original 600-second, 12-batch, 96-leg and 160-MiB limits. Endurance requires an automatic open queue and a sealed owner receipt; the profile is bound into the launch policy, supervisor, RDP worker arguments and native recordings. The independent auditors check those bindings.

Both profiles retain the 78°C thermal stop and telemetry watchdog, 150 ms native source-age limit, 100 ms action holds at 10 Hz, 35-second per-leg limit, strictly sub-second walking handoffs, and original STOP/owner/readiness controls. Source age refers to the declared native compositor clock; it is not a measurement of game-render latency. No C# hot replacement is needed for this Python supervisor change.

## Original evidence

All paths are relative to `artifacts/live/2026-10-30-endurance`.

| Evidence | Meaning |
| --- | --- |
| `initial-probe` | Five-second input-disabled observation on the original idle pair. |
| `recovery-drill/batches-20261030T163222Z-3e6ef5e26e88` | Deliberately unfilled second queue slot. The original launcher remains stopped and the resident remains failed. |
| `recovery-drill/batches-20261030T163222Z-3e6ef5e26e88/failure-audit.json` | Independent `missing-successor` proof, 79 applied actions, zero proposals after the released boundary, peak GPU temperature 66°C. |
| `after-drill-probe/junction-replay.json` | Replay of decoded H.264 frames: 58/58 junction classifications, zero inputs, maximum native distance 0.172507. |
| `endurance-regressions.log` | 489 CPU-only regressions passed before live endurance qualification. |
| `recovery-resume/batches-20261030T164400Z-3533b041e7a8` | Separate successful short queue: 14 photos, 18 legs, 581 applied actions. This is a new lease, not autonomous recovery of the induced failure. |
| `endurance/batches-20261030T164837Z-ac448072299e` | Original deadline refusal retained. The first successor action now uses the earlier of source freshness and the predecessor's original walking-handoff deadline. Neither bound is extended. |
| `deadline-validation/batches-20261030T170626Z-75e8e8fcc080` | Successful short validation: 14 photos, 18 legs, 591 actions. No tighter deadline was actually exercised in this run. |
| `endurance-fixed/batches-20261030T170929Z-ee175840aaed` | Supervisor publication stop in batch 14 after 254.096 seconds of witnessed gameplay; 2,171 applied actions. The original stopped result is unchanged. |
| `publisher-failure-reproduction.json` | Frozen old reader returned 13 plans when 14 had been admitted. The corrected reader uses the explicit bounded profile. Tests cover ordinary limits, all 40 endurance batches, finish slot 41, duplicates and missing predecessors. |
| `publisher-stopped-prefix-audit.json` | Independently verified prefix: 66 legs, 50 photos, 1,722 native-navigation and 449 P2P actions, peak 69°C. This is explicitly not a completed endurance run. |
| `endurance-publisher-fixed/batches-20261030T172810Z-be586a93956a` | Natural G4 photo failure at stair goal 7 after 280 actions. Arrival and three stationary retries remained unverified; input was released. |
| `natural-photo-failure-audit.json` | Independent failed-prefix proof. The four original stair images are frames 962, 976, 984 and 993; there were no inputs or proposals after the final boundary. |
| `g9-paired-prospective/episode-audit.json` | Twenty circuits and 80 verified legs on a new lease. G4 and G9 both scored 80/81 on the original images, missing the same stair view. G9 was not promoted. |
| `cnn-control-regressions.log` | 524 control, evidence, export and observer regressions passed before the CNN prospective trial. |
| `debug-build-configured-sources.log` | Required .NET 10 Debug solution build passed with the configured cached dependencies. No new C# release was made. |

## Frozen visual encoder experiment

G9 added one original missed arrival to the old RGB-grid template bank and excluded that whole lease from evaluation. Its fresh 80/81 tie did not justify replacing G4. The subsequent experiment explicitly admitted the natural-failure lease and the former G9 trial as training data for a different model; it does not reuse that trial as an independent CNN holdout.

The CNN uses only the installed P2P checkpoint's 851,808-parameter EfficientNet component. A 128-by-128 central crop excludes the minimap and side HUD. Frozen convolutional features are pooled into 1,008 values; 88 native-labeled original images from two whole leases supply nearest prototypes. No policy weights are fine-tuned, no new model is downloaded, and native positions or desired destinations are never classification inputs.

On 148 held-out original images from 11 other leases, the frozen model scored 147/148 versus G4's 146/148, with no new error. This is retained-data evidence, not a recovered live goal. The first implementation missed its predeclared 10 ms p95 budget at 13.26 ms. CUDA graph execution then preserved every feature exactly across all 236 training and held-out images, with p95 3.85 ms, maximum 5.83 ms, 5.70 MiB peak tensor allocation and 63°C peak temperature. This second pass is execution-parity evidence, not another independent accuracy trial.

The model, original failed timing result, graph comparison and source hashes remain under `cnn-comparison`. `prospective-plan.json` predeclares two fresh ten-circuit leases: no new original-image errors or per-class regression in either lease, exact original/live replay, 10 ms p95 and 25 ms maximum integrated observer time, unchanged control guards, one policy load and one observer load per lease. The new loader refuses photo authority and prewarms before input ownership. Qualification must finish before any promotion decision.

That prospective gate passed in `cnn-prospective/series-20261030T184020Z-42ec3b2d4f19`. Both observers scored 82/82 originals across two independent leases; this is a fresh tie, not another accuracy gain. All 80 legs and 2,684 applied actions passed the native audits. Observer p95 was 4.91 and 4.62 ms, maximum 6.29 and 5.46 ms. Each observer added 1.83 MiB allocated CUDA tensors and 618–633 ms prewarm beside the resident P2P policy. Peak temperatures were 64°C and 66°C. Source-to-dispatch maxima were 149.9443 and 140.7828 ms, both within the unchanged 150 ms limit. The original runtime sources were saved in `cnn-comparison/shadow-qualified-sources.zip` before adding the experimental photo admission.

## Controlled photo-authority gate

The controlled experiment is narrower than promotion: four fixed goals, lamp → stairs → lamp → stairs, from the stairs. It has exactly eight physical legs and a 90-second wall cap. `run_scene_photo_trial.py` uses the existing warm supervisor, records a fresh permit after writing its exact request file, and pins the same qualified RDP owner. G4 remains the default and rollback observer.

The permit is accepted only with the exact G10 checkpoint and pinned historical, graph-parity and two-lease prospective artifacts. It binds the original owner nonces, output directory, request-file bytes, walking-instruction bytes and deadline. Startup consumes it exclusively for the addressed run before policy loading or input ownership. It cannot authorize another folder, another run, an open queue, endurance, map inspection or wider timing/action limits. Offline photo replay checks the saved claim and original worker arguments; replay after the old deadline does not issue a new permission. A four-goal permit cannot authorize the separate endurance experiment.

Acceptance requires all four original PNG photos, eight native verified legs, all three request handoffs strictly below one second, no unknown input outcomes, complete receipts and release proof, and safe recorded telemetry. A classification miss still receives at most the existing three stationary retries, then fails with input released. Passing this controlled trial does not by itself demonstrate recovery from a naturally occurring miss. No timeout, retry limit, source-freshness threshold or stop behavior is relaxed.

The trial passed in `cnn-photo-trial/trial-20261030T191429Z-d72c08e8f021`, run `d86a5813188a471698b5246ac2c8c65b`: four verified original PNGs, eight legs, 261 applied actions and 30.199 seconds of verified route time. The three handoffs took 607.03, 602.79 and 606.99 ms. One policy load and one controller lease served all four requests; the GPU peaked at 62°C. There were no photo misses or stationary retries, and G4 also recognized all four originals. Independent replay reproduced the complete saved audit exactly and confirmed the original minimized RDP pair idle afterward. The earlier empty attempt at 19:13 refused spaced request names before worker launch; its folder is preserved.

## Separate bounded endurance experiment

`cnn-comparison/promotion-review.json` binds the original four-goal evidence and records an independent replay and source review. Its decision permits only one bounded endurance experiment. The new `run_scene_endurance_trial.py` reuses the existing adaptive publisher and owner supervisor, with a separate permit format bound to that exact review. It requires 600 seconds of positively witnessed gameplay, a 900-second wall cap, at most 40 batches and 256 legs, and the unchanged 78°C stop, 150 ms source freshness, 100 ms action holds and subsecond handoffs. The model remains warm throughout the single lease. The queue finishes at a verified photo boundary; it cannot automatically restart after an operator or thermal stop.

Both the publisher policy and original owner manifest are hashed into this permit. The request controller rechecks the consumed initial plan and queue artifacts after model warm-up, before sending its first action. A bare CNN shadow checkpoint, a copied permit, a four-goal permit or changed bounds are rejected. Ordinary queued runs still use G4 unless they carry this separate reviewed experiment admission. Passing the experiment would establish bounded route endurance, not general-world gameplay or recovery from a natural miss that did not occur.

The experiment passed in `cnn-endurance/batches-20261030T194020Z-bb39df115553`, run `7c658d3edecd4c66be3e3b3c83f438d9`. The queue crossed the positive-dispatch target at 623.955 seconds, completed its accepted batch and finished at the sidewalk junction. `cnn-comparison/endurance-review.json` records a separate-process replay, paired original-photo comparison and the final idle/minimized owner check. The runtime source archive is `cnn-comparison/endurance-qualified-sources.zip`, SHA-256 `eb3054967e37c756aeb97454c7ec8a939ac96d15c1b81c58333e9de92211745e`.

| Measurement | Verified result |
| --- | --- |
| Gameplay / queue | 649.494 seconds; 31 accepted batches; automatic photographed finish |
| Goals / navigation | 124 original goal photos; 167 verified legs |
| Inputs | 5,543 applied; one lease; one policy load; no unknown outcomes |
| Policy GPU evaluation | Median 27.504 ms; p95 32.736 ms |
| Image to native dispatch | Median 79.762 ms; maximum 147.775 ms |
| Longest request handoff | 806.762 ms, below the unchanged 1,000 ms bound |
| CNN observer | p95 5.312 ms; maximum 6.215 ms |
| Fresh original goal photos | CNN 124/124; G4 123/124; no new CNN error |
| Temperature / recording | Peak 69°C on RTX 2080 SUPER; 185,815,798 recorded bytes |
| Recovery events | No stationary photo retry, stall passage or climb passage occurred |

G4's fresh error was the stair photo at frame 8746; the CNN classified that same original PNG correctly. This is a fresh accuracy gain and a completed route, not evidence that G4 would have failed every retry or that a recovery occurred. The 168 live station decisions were also checked against native poses and retained video. Only the 124 requested goal PNGs preserve exact pixels in this queue: intermediate views are lossy H.264. The first supplementary comparison script stopped on an incorrect assumption that warm queues also produced the fixed-circuit raw-RGB journal; its original script is retained. The completed comparison uses only the actual original PNGs.

## Natural photo-recovery probe

`natural-recovery/probe-plan.json` predeclares one G4 diagnostic lease from the verified junction, with a 180-second gameplay target and 300-second wall cap. It retains the existing three stationary retries, 1.5-second retry window, subsecond walking handoff bound, thermal stop and native source freshness limits. No miss is injected and no model or threshold is changed. Success requires an actual `classificationMiss`, a qualified later original photo and positive continuation in the same run and lease. A completed run without a miss does not qualify recovery. An unresolved miss preserves the failure and exact retry PNGs and ends the probe without automatic restart.

The probe completed in `natural-recovery/batches-20261030T201430Z-78f31e9b6c6d`, run `7124a715c18642e5a1464c8180dc79d8`: 40 photos, 54 legs, 1,778 applied actions and 208.573 seconds. It contained no classification miss or stationary retry, so `natural-recovery/probe-result.json` records `naturalRecoveryQualified: false`. Independent export replay matched the saved audit. Its peak was 76°C; the unchanged stop was 78°C. A subsequent read-only check at 20:27 UTC confirmed the original pair idle, minimized and game-ready, with current GPU temperature 58°C. The probe was not automatically repeated to force a miss. Its separately reserved export is diagnostic-only.

## Execution context

Initial discovery from the restricted workspace runner returned Windows error 5 for the existing primary and child control pipes. The same documented discovery succeeded when `prepare-cnn-prospective.py` ran through the normal approval-reviewed `require_escalated` execution route. That script only read the existing endpoints and sealed the plan; it did not request Windows UAC, change an ACL, replace a process or modify the RDP connection. Both calls addressed primary PID 10124/session 1 and child PID 5520/session 3; the successful call verified the original nonces, minimized window and idle input state. The subsequent bounded patrol command went through the same approval review.

## Learning provenance

These recordings are automated controller experience. BetterGI navigation, P2P action proposals, native software input receipts and weak labels derived from surveyed native positions must remain separately attributable. They are not human expert demonstrations. The queue failure was deliberately induced; it must not be reported as a naturally occurring navigation failure.

Retain source/clock metadata, actual native action receipts, endpoint outcomes, interruptions, recorder-loss counters and source hashes. Station archives and photo PNGs preserve exact original RGB; the continuous video is lossy H.264. A missing encoded source image is a loss and is excluded from image/action training pairs. Native dispatch is evidence that software sent an input; world pose and original photos supply separate outcome evidence.

`experience_manifest.py` independently audits a whole lease and binds each action to its actual proposal, native receipt, source observation and indexed encoded video frame. It records controller provenance and does not label these as human expert demonstrations. The successful 581-action short run was exported as an untouched holdout; the natural 280-action photo failure was exported as diagnostic-only and is ineligible for training. Video dimensions, presentation timestamps, frame counts and decodability are checked with the already installed FFmpeg tools.

Subsequent candidate training and evaluation must split by whole run before fitting, preserve a held-out baseline, and keep the deployed checkpoint until its own independent qualification passes. This milestone establishes recovery/endurance evidence; it does not establish general-world navigation or learned-policy competence beyond the recorded actions.

The successful CNN endurance episode is exported to `artifacts/agent/experience/2026-10-30/cnn-endurance-holdout`. All 5,543 actions have paired source images and terminal receipts: 4,478 native-controller actions and 1,065 learned-policy actions. Recorded frame/event/observation/receipt losses are zero. Its image/action eligibility describes evidence completeness; its **holdout split excludes it from fitting**. No policy was fitted on this episode.

The steering reader now independently qualifies the whole directed episode and supplies its externally declared itinerary to label extraction. It previously omitted that itinerary and silently skipped every directed steering target. The corrected reader recovered 4,347 weak native labels from this holdout (2,046 forward, 1,374 right, 927 left) as a loader validation only. The original plans, observer qualification and byte hashes accompany the labels. The remaining native actions do not meet the narrower steering-label admission rule and are not relabeled.

`experience-split.json` now binds a whole-run split to the original resident-manifest hash. Conflicting exports are refused, and the steering fitter rejects holdout and diagnostic inputs before optimization. The earlier recovery-resume holdout and the CNN endurance holdout both have explicit reservations; neither was fitted. `split-guard-regressions.log` records all 556 selected tests passing. The two source files checked by the frozen CNN loader also use explicit LF Git attributes, preserving their qualification bytes across checkouts.

## Separate map-transition training episode

The next bounded objective was a fresh G4 world-map inspection followed by the west-lamp and junction photos, with a 120-second wall cap and the same original minimized R59 RDP owner. The ordinary M/Escape map pulses live in a separate native journal rather than the stream action-receipt list. `map_experience.py` now independently replays the map audit and emits `ui-actions.jsonl` with the real native operation ID, pulse ordinal, software execution evidence and exact original 1920×1080 PNG. Ordinary actions retain their receipt-to-video pairing. The launcher preserves the original lineage path and SHA-256 in `map-owner-source.json`; the exporter rejects missing, changed, recovery or unqualified map evidence. UI pulses are separate native-controller experience, not human demonstrations or P2P actions.

The initial trial, `map-training/live/warm-20261030T204404Z-17ea753e9743`, run `5c1c4fdb9fb34e5396d92232cf45b378`, completed two walking legs and two photos with 76 applied actions. Its map audit failed: the first two G4 sources were **distinct**, but their capture timestamps advanced only 62.5 ms while their freshness timestamps advanced 82.7854 ms. The existing audit requires at least 80 ms of source separation. This was a collection-clock mismatch, not literal frame reuse. `capture-spacing-diagnosis.json` preserves the original intervals, completed walking evidence, terminal release and 63°C peak. That whole episode is explicitly reserved as diagnostic and blocked from fitting.

`collect_junction` now requires both freshness separation and original capture separation before admitting a source. The 80 ms audit gate is unchanged. A regression reproduces the divergent clocks and proves the closer source is skipped. The first exporter regression run exposed four old mocked-lineage fixture errors; those fixtures now retain and check the actual owner bytes. All 564 selected tests passed after the spacing correction (`map-capture-spacing-regressions.log`). No native application build or replacement was needed.

After the failure was diagnosed and the original idle owner was verified, `trial-plan-v3.json` declared a separate corrected trial and froze its source archive. `map-training/live-fixed/warm-20261030T205030Z-b2530879e65f`, run `b702f29a05b04aed950c543b9d91edc7`, passed both independent audits:

| Evidence | Result |
| --- | --- |
| Map inputs | One M pulse and one Escape pulse, with original PNG sources and native execution journal |
| G4 source spacing | 93.75 ms for every before/returned interval |
| Walking | Two verified legs and two photos; 9.702 seconds |
| Ordinary actions | 86 paired actions: 79 native controller, 7 learned policy |
| Handoff / ownership | 609.586 ms; one model load and one controller lease |
| Recording / temperature | Zero recorded losses; 69°C peak with the unchanged 78°C stop |
| Final release | 13,789.341 ms on the original native lease clock |

The `artifacts/agent/experience/2026-10-30/map-visit-training` export is reserved as **train**, separate from both existing holdouts. `qualified-map-review.json` verifies all 30 retained original-file hashes, both independent audits, ordinary and UI action-file hashes, and the original UI source PNGs. The directed reader recovered 77 native steering weak labels (40 forward, 19 right, 18 left) without fitting. At 20:54 UTC the same host and child were idle, minimized and game-ready; the GPU was 56°C. Both holdout reservations still rejected fitting. This qualifies a bounded map transition and its training provenance, not an independently trained general-purpose policy.

## Varied starts and rejected steering candidates

`varied-starts/series-20261030T210501Z-c98f5e7fe592` collected two independently leased, preassigned episodes. Junction-to-lamp training completed seven legs/four photos in 25.01 seconds with 214 actions and 155 native steering labels. Lamp-to-junction holdout completed five legs/four photos in 20.30 seconds with 177 actions and 149 labels. Both had zero recording losses; maximum handoffs were 705.75/700.55 ms and GPU peaks 63/61°C. The exports retain their distinct train/holdout reservations. Frozen scalar generations 1 and 2 each agreed with 143/149 new holdout labels; the native five-degree teacher rule agreed with all its own labels.

`steering-candidate-01` used one fixed, one-thread CPU fit: 822 native weak labels from six permitted training runs, 24 coefficients, 0.260 seconds. Its candidate SHA-256 is `7dd9a0581136605527980b5bef0c57713af35dabc1dbf563339eaea60bfb2aee`. It reached 145/149 on the new holdout, 432/444 on recovery-resume, and 4,260/4,347 on the endurance holdout, with at most 28.6 µs p95. It nevertheless failed the predeclared zero-paired-regression/native-rule gate. The original heads, failures and holdout reservations remain unchanged; the candidate was not deployed.

`visual-steering-01` froze the existing 1,008-dimensional center-scene CNN and fitted a nearest-cosine prototype bank within each exact planned waypoint. It excluded current pose, heading, bearing error, raw P2P actions and future frames. The bank used 232 training images; the untouched 149-image validation episode scored 110/149 (73.83%) at 3.27 ms p95, excluding capture/decode/transport. CUDA graph/eager features matched exactly on all 381 images and the GPU peaked at 61°C. The 95% accuracy gate failed, so no fresh final test or input authority was granted. The bank SHA-256 is `0c21f0371002307cba4758d3228241a555edec28bc6eb66721976fd3475b8c69`.

## Exact-pixel recording and paired fidelity diagnostic

Ten original goal PNGs could be joined to precisely the same encoded source frames. Their average pixel error was 4.17/255 and minimum frozen-CNN feature cosine 0.9582; all ten scene labels were unchanged. Those station images did not establish the cause of steering errors. The original steering frames had only lossy video, so the Python recorder gained optional bounded raw RGB192 retention; no native application was rebuilt or replaced.

The standard-budget diagnostic episode `exact-pixel-collection/series-20261030T220204Z-40d00a1d6f90/exact-pixel-diagnostic-01`, run `06d0a1f2431747c4925fc45e29ac2e23`, then passed independent route and handoff audits on the original R56/R59 owner:

| Evidence | Result |
| --- | --- |
| Route | Four legs, four photos, 19.6875 seconds |
| Applied inputs | 175: 132 native controller, 43 learned policy |
| Exact pixels | 405 RGB192 files, with SHA-256 and original encoded indices |
| Recording | 49,992,792 bytes of 167,772,160; all loss counters zero |
| Handoff / thermal | 797.1383 ms maximum; 61°C peak; original 78°C stop unchanged |
| Terminal release | 20,720.8149 ms on the native lease clock |

`exact-pixel-comparison/result.json` rechecked all 429 referenced original files and paired 129 native steering sources with both their raw RGB and decoded H.264 pixels. With the same frozen rejected prototype, raw pixels scored 87/129 (67.44%) and encoded pixels 84/129 (65.12%). Eleven predictions changed: seven raw-pixel wins and four losses. Average pixel error was 4.66/255; minimum feature cosine was 0.8742. Restoring only the input pixels did not repair the model's accuracy. This single correlated episode does not isolate the effects of compression during fitting. It is explicitly **diagnostic**, excluded from fitting, and confers no promotion or control authority.

The focused recorder tests passed. The first broad run encountered sandbox-denied Windows hard links in existing evidence-publication tests; the unchanged suite then passed all 569 tests on the host in 29.51 seconds. Failed logs remain preserved. The raw files are written off the capture path and share the existing total recording budget, including retiring segments; truncation, changed hashes, redirected paths and incomplete coverage are rejected.

## Combat prerequisites

The user selected combat at 21:55 UTC. The native bridge accepts bounded mouse-button proposals, but the initial surveyed navigation graph stayed inside the city and the map transaction grants only its fixed M/Escape visit. The input-disabled native image in `resource-prerequisites/01-frame-000000000016.png` showed the planter wall, no collectible prompt and no enemy. The initial manual-positioning request was withdrawn. Autonomous short route trials now extend toward the gate and an observed enemy. No combat inputs have been sent.

`combat-isolated-enemy-v1.json` was encoded with the installed local EmbeddingGemma model, one CPU thread, exact token parity and zero upstream embedding error. `combat_observer.py` is deliberately read-only: red horizontal shapes are candidates, health colors are coarse visual evidence, and temporal confirmation never grants input or proves a kill. Five synthetic refusal/clock tests passed. `combat-negative-observer.json` found zero enemy candidates on all 405 original city frames, with green health-color evidence throughout and 0.456 ms p95 processing. Positive recognition and live combat outcomes remain unqualified.

## Autonomous city extension

The original R59 owner remained minimized. `run_rdp_patrol.py` now accepts an explicit one-to-four-leg bound on declared local routes while preserving resident owner binding, 150 ms source freshness, 100 ms holds, the 35-second leg deadline and 78°C thermal stop. Candidate survey routes stop for inspection before any retreat or sidestep. The existing stair-post route retains its separately tested recovery behavior. The ordinary G4 street patrol is unchanged.

At 23:17 UTC, `city-exit-survey/summary-20261030T231701Z.json` independently joins 15 completed **separate trials**, 62.62 seconds of verified route motion and 532 applied actions. This is not a continuous city-exit qualification. Maximum software dispatch age was 141.745 ms and peak GPU temperature was 63°C. One stair-post climb passage was verified. Every completed leg retained exact policy RGB evidence and a fresh native endpoint image. These episodes are diagnostic, excluded from fitting, and confer no general model or combat promotion.

The direct gate line (`mondstadt-street-extension-12-v1`, run `ce7bb48aca524bc3af97ae874f375d38`) encountered the right pillar, performed the existing climb drop and stopped at `survey_obstacle_requires_inspection`. Its original 39 accepted actions and failed evidence remain intact; both launchers now refuse that route. The terminal software record reported `release:client_stop`, `returned_unverified`, no active input and an empty tracked key list. This is not physical release proof. Before a new clearance plan, `gate-obstacle-inspection` observed normal motion and a ready world; frames 15 and 18 had the identical position (-934.7949, 2222.0059), one capture epoch and 125 ms source separation. The original owner was independently idle/minimized afterward. The new clearance and gate-center legs passed, with the bridge visible in the latter native image.

The first two launcher attempts failed before an agent stream: a keyword-only argument error and a conservative street-only binding check. Their evidence is preserved. The repaired bounded-route binding passed its refusal tests. A broad 577-test suite passed before subsequent route additions; focused route, launcher and client regressions continued to pass as the survey grew.

## Outdoor transition and bounded timeout

The October 31 00:25 summary, `city-exit-survey/summary-20261031T002508Z.json`, extends the diagnostic total to 16 separate verified legs, 64.933154 seconds and 551 accepted actions. The dispatch-age and temperature maxima remain 141.745 ms and 63°C. Route 15 subsequently hit the arch's inner corner; its failure is preserved and blocked. Route 16 cleared it in 2.3125 seconds with 19 accepted actions. Its post-release frames 87, 90 and 93 localized identically at (-939.84375, 2224.61328125), yaw 115.5°, about 94 ms apart.

Route 17 (`092b107d12fa41f5a170311a1b9c6435`) accepted 27 actions before outdoor localization stopped qualifying. Movement stayed held, but the missing-pose wait bypassed the old source-clock deadline. The operator stop and original failed evidence remain intact; this route is blocked. The subsequent native inspection had a ready normal world but no valid pose, so it does not prove stationary localized coordinates.

The retained gate image independently matched the existing map assets on `MapBack_2`, confidence 0.992757, at (-947.53906, 2222.0996), yaw 15°. The city-only layer check rejected an otherwise qualified outdoor match. The one replay's 51.7691 ms timing is a diagnostic measurement, not a latency benchmark.

The controller now checks a monotonic 35-second admission/leg deadline before all wait paths. Pauses and pose loss do not renew it. `gate-deadline-live-disabled/result.json` verifies a live admission-controller stop at 35.0527344 seconds. The full resident GPU loop in `gate-deadline-resident-disabled`, run `1704cbb3418146d0959cecc3077015d1`, stopped at 35.0061574 seconds with 685 frames, zero accepted inputs, native input disabled and 61°C peak. Its original wrapper result remains failed because it selected a lease receipt as a numeric segment; `independent-audit.json` validates the expected timeout from the preserved raw evidence. Neither diagnostic is a successful navigation run.

R60 adds an explicit surface profile with only `City_102` and `MapBack_2`, X [-1100, -820], Y [2100, 2350], position confidence at least .99 and yaw confidence at least .2. The default city profile remains unchanged and a stream cannot switch profiles after enabling navigation. The bridge approach is a declared candidate, not yet a qualified route. Movement remains held until live coordinate, bearing and visual-route checks pass.

Verification: 17 focused native localization tests, 29 focused Python scope/controller tests, 11 lineage tests and the final 587-test Python suite passed. The required Debug solution validation and R60 Release publishing passed. Earlier failed test logs remain preserved. New managed builds save exact executable/DLL/manifest identity witnesses before normal cleanup, allowing retired packages to disappear while their original handoff evidence remains verifiable. R58's obsolete runtime was retired; recordings and test results were preserved.
