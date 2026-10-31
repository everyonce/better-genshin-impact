# Native scouting and combat observation

R61 built successfully at 02:28:54 UTC on October 31 with .NET 10.0.402: the required Debug solution validation followed by a self-contained Release publish. After Windows consent, the pinned handoff verified at 04:22 UTC. R61 child PID 28988 remains in RDP session 3, with R56 root PID 10124 and the original Genshin PID 26240/start FILETIME preserved. No enemy identity, attack outcome, or kill has been qualified.

## Scope and signal contract

`mondstadt-combat-scout-v1` is a separately selected local navigation profile. It accepts `City_102` or `MapBack_2` within X [-1350, -980], Y [2050, 2480], using the fixed search center (-1165, 2265). It keeps the original 0.99 position and 0.2 yaw confidence thresholds and the original courtyard heading anchors. There is no global-search fallback. The city and R60 surface profiles retain their existing scopes. Route admission, controller construction and replay auditing require the exact profile assigned to each route.

`enableCombatObservation` optionally analyzes the same native Mat used for the published policy image. Ordinary streams do not execute this extra analysis. The result carries its frame ID, full WGC source identity and native dimensions. It reports:

- Green, red or unknown player-health color and a visible fill-extent estimate.
- Native-coordinate red horizontal components, bounded by ROI, color, shape and count.
- Explicit unavailable or overloaded states, with no carried-over candidate values.

The estimator supports 16:9 captures from 1280 through 1920 pixels wide; synthetic tests cover 1280×720 and 1920×1080 in BGR and BGRA layouts. It uses no second capture, OCR, menu probing, input, or sleep. Component labeling is cropped to the nonzero mask. Colors do not establish enemy identity, exact numeric HP, attack authority, or a kill. All three authority/identity flags remain false.

The Python client validates the negotiated capability, exact source/frame join, freshness-anchor consistency, geometry and negative states. It preserves native metadata in recordings and decisions. `--native-combat-observation` also passes through the monitored patrol launcher. It can accompany input-disabled `--combat-shadow` for comparison with RGB192 vision and GPU decisions.

## CPU measurements

The measurements below are warm CPU recognition times, excluding capture, GPU policy evaluation, transport and controller dispatch. Each retained-image sample used an original native PNG from one of the seven verified outdoor endpoints. The positive cases are synthetic bars, not live enemies.

| Input | Samples | Median | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Seven retained outdoor images | 140 | 1.3026 ms | 1.8783 ms | 2.2469 ms |
| One synthetic red bar | 20 | 1.6382 ms | 2.0168 ms | 2.1465 ms |
| Eight synthetic red bars | 20 | 2.2792 ms | 2.8781 ms | 2.9510 ms |
| Sixteen synthetic red bars | 20 | 3.3316 ms | 4.0270 ms | 4.6893 ms |

The retained HUDs show 2488/2764 HP. The color-derived fraction is only a bar-fill estimate; it does not replace that separately inspected numerical value.

## Verification and deployment evidence

- 38 focused native tests passed, including source-buffer ownership, unavailable-state clearing, overload handling, both capture layouts, all scope boundaries and original heading-anchor preservation.
- The final 612-test Python regression cohort passed in 33.795 seconds, including the actual stream/recording path with a synthetic bridge, zero actions and recording rotation. Native observation counts are segment deltas whose sum matches the lease total. Earlier failed cohort logs remain preserved.
- The R61 lineage extension admits only the next R60→R61 handoff. It additionally requires the exact Genshin lifetime sealed by R60; later, skipped and circular transitions remain rejected.
- A fresh ordinary-token probe again returned access denied for the protected game handle. The prepared UAC helper is pinned to R56 root PID 10124, R60 child PID 24816, Genshin PID 26240 and game start FILETIME 134375822866128716. It preserves the minimized session and does not start a gameplay controller.
- Automatic retention now keeps R1/R55/R56/R60/R61. The retired R59 runtime has an exact executable/DLL/manifest witness; recordings and test results remain preserved.

Local evidence is under `artifacts/live/2026-10-30-endurance`: `r61-native-hud-test-results`, `r61-scout-combat-regressions-v4.log`, `r61-build.log`, `r61-deploy-plan.json`, and `r61-native-source-snapshot`. The snapshot preserves the new native sources and patch because the build manifest correctly records a dirty working tree. The package DLL SHA-256 is `03f75e29b73a2fb3161600c75a37976f9789522076546374da5d13d74e9c736e`.

The passive live probe compares the default, surface and scouting profiles in separate input-disabled leases. It checks profile locking, source freshness, stationary position, original-anchor bearings, unchanged health, zero input history, and minimized-owner recovery. Native snapshots are preserved on failure. Positive hostile recognition and sustained combat remain the next in-game work; offline color tests do not qualify them.

## First live R61 results

The original passive probe stopped with zero inputs because its last R60 endpoint and HP assumptions no longer matched the current scene. The retained native image showed the Traveler on grass at approximately (-1095.24, 2203.18), with 2354/2764 HP. The cause of that intervening movement/health change is not established. The failed evidence remains in `r61-scout-combat-qualification`.

After reviewing the new scene, `r61-scout-combat-current-qualification` passed all three input-disabled profiles. Surface and scout positions agreed within 0.35 units; original-anchor headings, profile locking, source identity, unchanged approximate health and zero input history passed. Native recognition was 1.6701 ms median and 1.9289 ms maximum across the six selected positive-health samples; peak GPU temperature was 56°C.

| Scout leg | Run ID | Motion | Accepted actions | Maximum dispatch age | GPU peak |
| --- | --- | ---: | ---: | ---: | ---: |
| Grass | `5e3148c756874f97ba3b572a6f50864a` | 4.3276 s | 31 | 145.89 ms | 63°C |
| Grove | `57b7b8115fc045c6a6f2970c08bf3da4` | 5.0938 s | 47 | 118.18 ms | 64°C |

Both legs used the GPU policy, explicit scout localization and optional native HUD metadata. The independent audits verified 195 exact RGB hashes and all 79 decision/native-metadata joins. Native analysis was available on 185 frames; the remaining startup frames explicitly reported unavailable evidence. All available health observations were green with an estimated fill of 0.8553, matching the separately inspected 2354/2764 HUD. Native recognition medians were 1.4929/1.4830 ms (p95 1.9034/1.9128 ms); GPU policy medians were 23.3187/26.5191 ms (p95 28.9661/31.5031 ms). Neither leg produced enemy candidates, stalls or climb recovery. These are separate diagnostic navigation legs, not continuous combat qualification.

Evidence is under `combat-scout-survey/leg-20261031T043334Z-eaff38ed27d7` and `combat-scout-survey/leg-20261031T043900Z-95783fa0bf79`, including independent native endpoints and `native-observation-audit.json`. Pixel hashes and metadata joins were verified; native color analysis was not replayed from downsampled policy pixels. A subsequent stationary camera survey reached 273° for a 270° request in three pulses (`camera-scout-grove-north`), with its native view retained in `combat-scout-survey/grove-north-scene`.

## Warm scouting worker

`scout_session.py` retains the installed Open P2P weights and validated CUDA graph while closing each completed native stream. A fresh reviewed native endpoint is required before each separately requested registered route. Three stationary source observations, exact profile/start position, image/hash/source joins, the original owner, 150 ms freshness, 100 ms holds and 35-second leg deadline remain required. The session retains 78°C, telemetry-loss, ownership and operator-stop supervision while loading, moving and waiting. It neither submits destinations nor restarts after a failure.

The first live worker (`warm-scout-qualification-01`) loaded once in 11.219 seconds and completed two independently audited legs:

| Route | Run ID | Motion | Accepted actions | Maximum dispatch age | Per-leg model loads |
| --- | --- | ---: | ---: | ---: | ---: |
| North apron | `85b4decaaad24b24a8acb5b4bca5038e` | 3.6912 s | 33 | 124.80 ms | 0 |
| North meadow | `bdff7e893d27496f95e14e4c7e9c02af` | 5.2890 s | 49 | 144.35 ms | 0 |

Peak GPU temperature was 63°C. Separate native endpoint images showed unchanged 2354/2764 HP; neither leg reported a stall or climb. The worker then honored an explicit qualification stop. The broker confirmed an ordinary token in RDP session 3, no timeout and complete output; the intentional stop returned code 1 with session state `stopped`, while both leg audits remained verified. The original owner was idle and minimized afterward. Cached acquisition reported 0.0 on the existing timer, which means its resolution was insufficient; it does not prove literal zero latency.

Independent replay verified all 221 archived source files, 201 exact RGB hashes, and 82 decision/native-metadata joins. Native HUD evidence was valid on 198 frames and explicitly unavailable on three startup frames; unavailable evidence did not authorize actions. P2P supplied 36 accepted actions and native navigation supplied 46. Median policy evaluation was 29.39 ms, with 35.27 ms p95 and 108.26 ms maximum. No enemy candidates were reported. The detailed result is retained as `warm-scout-qualification-01/independent-audit-20261031T054305Z-5dcb5b61.json`; both episodes are reserved as diagnostic data and excluded from fitting.

The second worker (`warm-scout-inland-02`) loaded once in 10.438 seconds, then completed the inland slope as run `dfd5a945fdce46ab94b9ab5a65d91a02`: **7.0801 seconds, 67 accepted actions, and 136.10 ms maximum source-to-dispatch age**. Replaying its archived auditor reproduced the original route audit exactly. All 141 exact RGB files and all 67 native decision joins matched. Native HUD evidence was valid on 139 frames and unavailable on two startup frames; no enemy candidates were present. P2P supplied 29 accepted actions and native navigation supplied 38. Policy evaluation was 31.2729 ms median, 34.5304 ms nearest-rank p95 and 38.6647 ms maximum.

The new `perf_counter_ns` measurement recorded cached policy acquisition at **0.4974 ms**. The endpoint image retained 2354/2764 HP but showed a rock wall along the next frozen diagonal candidate. That candidate was not submitted. The worker was explicitly retired with the original owner idle/minimized, and the successful episode remains diagnostic-only. Its replay is `warm-scout-inland-02/independent-native-audit.json`. These audits verify pixel hashes, native metadata identities and software input receipts; they do not independently establish physical input delivery, a combat outcome, or native-color replay from RGB192.

The broader regression cohort passed 642 tests before the final checkpoint-identity correction; the final focused cohort passed 59. That review corrected an accidental reference to the unrelated G4 landmark checkpoint. The policy pin is the installed 2,198,488,343-byte Open P2P checkpoint, SHA-256 `2a3b43121144ca2d9c2b8aa605e313184c98ac5ef6d2c3b530c2d353d886c5bc`. G4 landmark behavior was not changed. Repeated polls of the same native source are retained and accepted only when immutable provenance agrees; conflicting duplicates are rejected.

## Reviewed geometry and forest approach

An explicitly opted-in worker can accept one immutable two-point geometry within the existing scout bounds and a maximum length of 40 map units. `route-spec` produces canonical content and its SHA-256 identity; a fresh source-bound image review, request, per-leg file, cached-policy proof, controller and auditor must agree on that exact geometry. It never edits the shared route table or grants a standalone resident new route authority. Admission requires the directed starting point. Successful legs still close their native leases and await another review.

The first geometry trial (`warm-scout-bypass-03`, run `3ec8d23ea6114178a8b4423ec95f582d`) stopped at a tree with `survey_obstacle_requires_inspection`. It made 41 navigation actions followed by two bounded climb-release actions. Independent replay verified 145 RGB hashes, 42 decision/native joins and the terminal receipts; maximum navigation dispatch age was 114.06 ms and GPU peak was 63°C. Its 17,906,552 payload bytes remain diagnostic-only. The original session file incorrectly retained a running row and zero bytes after the exception; it was preserved unchanged, and a separate audit records the correct failed state. The worker now accounts failed resident runs and their actual files in its terminal path, marks missing accounting evidence incomplete, and never double-counts completed legs. Route reviews now use the exact observed start rather than a rounded waypoint.

After inspecting the tree, a new four-leg session (`warm-scout-tree-detour-04`) retraced to clear ground, reached the lower path, and followed two inspected bends. Its four runs are `6dbeffb0dd764d3d8fec082248c13a17`, `5897a7d17f984fdfb42425db4896eb1b`, `8b10cd67c9ba41968590eef6dce7efe1`, and `a596e30bf4c54f41b011639ec4a54867`. Independent replay verified **382 exact RGB hashes, 155 decision/native joins and 153 input receipts** over **17.60 seconds**. Recorded payload totaled 47,189,438 bytes. Maximum software dispatch age was 131.73 ms; accepted policy inference was 29.77 ms median / 35.22 ms p95. One 10.453-second model load served all four legs, with cached acquisitions below 0.65 ms. Peak GPU temperature was 63°C, no enemy candidates appeared, and the native endpoint retained 2354/2764 HP.

The worker and broker retired at the configured 600-second limit with the original owner idle and minimized. The full audit is `warm-scout-tree-detour-04/independent-retired-session-audit-20261031T064458Z-515cb6af.json`; all four episodes are reserved diagnostic. These separate reviewed legs do not establish continuous handoff or combat qualification.

To reduce model reloads between inspections, an explicit `--seconds` can now retain the worker for up to 1800 seconds. The default remains 600 seconds and the data cap remains 160 MiB. The 35-second leg deadline, 150 ms source freshness, 100 ms hold, owner checks and all terminal-stop supervision are unchanged. The full geometry baseline passed 655 Python tests and the required .NET 10 Debug build. The terminal-accounting cohort passed 131 tests; the final lifetime/reuse/route/audit cohort passed 75. The initial broad Python run was unable to create local hard links under restricted tool filesystem access; the authorized rerun passed without code changes, and both logs remain preserved.

## Forest replay and review fixes

The explicitly extended worker (`warm-scout-forest-05`) loaded once in 10.938 seconds and completed two more reviewed legs: `222b53949aab438f9ab5a518d3dd6129` and `dd0bfdf94c334de397666140204f003d`. Independent replay verified **173 RGB hashes, 69 decision/native joins and 68 accepted actions** over **7.7764 seconds**. Native evidence was valid on 165 frames, unavailable on six startup frames and absent on two pre-admission frames; no enemy candidates appeared. Maximum dispatch age was 116.06 ms and peak GPU temperature was 64°C. Accepted policy evaluations measured 28.10 ms median / 33.86 ms p95 / 63.44 ms maximum. One 181.00 ms initial evaluation was discarded as too old and produced no input. The separately inspected endpoint retained 2354/2764 HP.

Both episodes are reserved diagnostic. The worker was explicitly stopped while idle before changing source; the ordinary RDP broker completed without timeout or lost output, and both recorded worker/broker process IDs were subsequently absent. The original owner remained idle/minimized. Evidence is `warm-scout-forest-05/independent-native-audit.json`, `accepted-timing-retirement-supplement.json`, and `strengthened-replay.json`. Proposal-owner counts include the discarded evaluation and must not be substituted for accepted-action counts.

Independent code review found that ordinary resident goal controls could replace a cached scout's frozen instruction, and that reuse auditing did not reopen every original visual-source artifact. The runtime now freezes the goal before starting its control monitor. A queued goal during acquisition or inference releases input and fails before changing the tensor; a late unobserved goal in the terminal control file also prevents successful completion or another leg. Ordinary resident goal updates remain supported, and a plain scout pause followed by an explicit run remains bounded by the original 35-second deadline.

Reuse replay now independently checks the original review, native plan/result, PNG and metadata hashes for registered and custom routes; it rechecks the source joins and stable directed start. Resident summaries, all three segment goal snapshots, journals and decisions must retain the original ground-navigation goal with no pending/applied replacement. The focused runtime tests passed 27 cases and the auditor passed 26. Replaying the two original warm legs, all four tree-detour legs and both forest legs with the strengthened auditor exactly reproduced their historical reports. The final combined cohort passed **670 tests in 43.114 seconds** (`r61-frozen-scout-regressions-v3.log`). No native application source changed after the verified R61 build.
