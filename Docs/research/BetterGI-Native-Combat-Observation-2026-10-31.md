# Native scouting and combat observation

R61 built successfully at 02:28:54 UTC on October 31 with .NET 10.0.402: the required Debug solution validation followed by a self-contained Release publish. Deployment is pending the normal Windows consent prompt. R60 remains active until the sealed R61 handoff verifies. No enemy identity, attack outcome, or kill has been qualified.

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

The prepared passive live probe compares the default, surface and scouting profiles in separate input-disabled leases. It checks profile locking, source freshness, stationary position, original-anchor bearings, unchanged health, zero input history, and minimized-owner recovery. Native snapshots are preserved on failure. Positive hostile recognition and sustained combat remain the next in-game work; offline color tests do not qualify them.
