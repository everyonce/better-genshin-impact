# Raptor completion and hideout approach

`They Call Him Raptor` completed on 2026-10-17 at frames15443/15444. The reward screen confirms275AdventureEXP,6175Mora,3Adventurer'sExperience and7FineEnhancementOre. Rank9 is925/1300, leaving375EXP toAR10. This is a prerequisite completion, not ActII completion. Durable OCR/state and terminal receipts are in `artifacts/act-two-raptor-completion-evidence.json`.

Fresh journal15450 identifies `Outrider Style` and `Enter Raptor's Hideout`,13m away. The first ground approach reached7m at15474 with3644/4015HP. Its listed rewards remain prospective. Do not replay the completed ambush or look for the obsolete License to Glide suggestion.

The preceding native ambush work was independently published as `a1b83586b8c788e30f3fd2064b72c9cdc6c2adcd` on both english-interface and main, verified by git ls-remote. Its1750-test suite passed. This subsequent change adds exact post-ambush and hideout regional travel, one reviewed low-rock release, Outrider journal closing, recorded regressions, and durable checkpoint/retention tooling. It does not widen combat authorization.

Live validation: guarded marks travel reached a new Paimon/Amber conversation15431; the existing dialogue handler returned the completed quest and reward. One accidental low-rock cling stopped the travel batch; a single60msX release succeeded15408 with unchanged health. Hideout journal closing and13m-to7m ground approach succeeded. There were no deaths, resource expenditures, or application/game/RDP restarts during this cycle. All inputs and capture remained inside BetterGI RDP7.

The marks/rock change passed1752tests; the final suite additionally covers the Outrider journal and approach. `artifacts/raptor-marks-full-tests.log` records the final count and duration. Original PNGs remain under bounded capture retention; embedded OCR evidence is durable. The ledger now includes regional world observations even when unreliable minimap coordinates are intentionally omitted. A separate read-only retention audit prevents accidentally running an old checkpoint-writing audit helper.

Latest retention audit:256recent images503044791bytes,32pinned images66689288bytes,8496963584bytes free; within policy. No permanent cleanup occurred.
