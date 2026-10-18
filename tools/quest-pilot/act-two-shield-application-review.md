# Bounded shield application review — 2026-10-18

Act II is **not complete**. AR9 remains955/1300, northern Ley Line4/9, Original Resin200/200 with zero spent. Act III has not started. The full Act II goal remains active. Later parent steering requested diagnosis and held-out validation rather than further single-frame template accumulation.

## Results

- Safety slice818a250bedc659414da2d0034b5f88be2c8ddfbc was verified on both remote branches. The earlier synthetic-frame pause failure and its129.509second exposure remain recorded separately in `act-two-shield-safety-validation.md`.
- Safe charged-shot receipt54ce3a7235eb4d7e8edcba187c0ef962 fired once. Reviewed images show the charged Pyro arrow and fiery impact. It returned full-health Kaeya and verified Inventory6520. Local5.510s; whole request15.146s. The receipt's old reason string incorrectly says no firing; its shot counter and images are authoritative, and the string was fixed.
- Two ranged inspections662838a09e104348ab90efb0f4fc3d19 andf0b695112ac84328939015ed99d5dea3 retained full health and stable aim at the earlier rock. The second clearly showed a wooden shield. No arrow was fired during either inspection.
- Field application requestb6cf556194924e6c90d38fd598ad5968 was **withheld by the target guard**, not by approval review. The Mitachurl approached, changing its scale and pose. Fresh template recognition returned unknown, so centering and firing were refused. **Zero field shots, no verified Pyro application, burning, shield reduction, shield removal or defeat.** A compact real-image regression preserves this failure.
- The fast return sample reported3845HP; final regular frame6588 showed3721HP. The adapter now reports final regular health, with the earlier fast value retained separately. Tests cover this exact reporting discrepancy. Recovery reached Windrise at3623HP:392total health lost, including98after the last field sample. No Amber health loss was recorded in this attempt.
- Emergency map8e4ca9ea76184b908deda3cf5db15060 opened in772ms from unpause. Statue healing9faef658b827453fb9f5659b8c9f7f24 restored all four party bars at6636; Kaeya4015/4015 at6639. Inventory6642 independently verified, controller6643idle, no pending input. No food, resin, premium currency, new deaths, falls or restarts in this window.

## Implementation and limits

The reusable policy distinguishes material shields from elemental barriers, selects a suitable available and ready capability, imposes health/exposure/retry limits, and separates elemental application from shield removal. Sourced starter-party Abyss Mage matchups have offline tests; **live barrier identification and automatic shield-removal detection remain unsupported**. `shield-response-mechanics.md` records sources and primitive tradeoffs.

The local shot adapter requires fresh target continuity and a reticle inside the detected wooden shield before firing. It supports reviewed synthetic aim witnesses using their normal source-frame provenance. Q readiness was positively observed locally after the switch transition, but the new burst application path has not cast Q in combat. Do not claim it live-validated. Read-only native replay recognized known wooden poses and ready-Q icons; its narrow templates did not generalize to the approaching enemy.

Focused validation:58tests passed,0failed,292.24ms. This covers pause deadlines/handoff, final-health reporting, frame/party/health gates, material/barrier planning, target continuity, reticle containment, bounded burst and charged-shot logic. No C# change, build, application restart or RDP restart was required.

## Accounting and next decision

`artifacts/act-two-shield-window-accounting.json` covers the measured28.655minute window from the fresh read-only checkpoint to final healing. There were24model-submitted missions,251.252seconds inside terminal requests, at least679.263seconds of verified Inventory gaps,66key events and14.568seconds of declared key holds. The maximum shield unpause-to-verified-pause interval was10.902seconds in this window. Capture/OCR/write timings overlap request timings; do not sum them. Adventure EXP and defeat gains were zero, so no objective-efficiency improvement is claimed.

Do not repeat the same rock approach/aim/heal loop. This rock was safe for brief inspection but did not remain outside immediate melee. A next attempt needs a concrete improvement to target tracking across approach/scale or a separately verified shorter available Pyro primitive and position. Keep the target, health and pause gates; full barrier recognition is not a prerequisite. Preserve the mission goal and continue Act II after resolving this application blocker.

Retention audit12:11UTC:10,350,567,424bytes free;238recent images/535,819,858bytes plus32pins/66,901,224bytes, within existing caps. Runtime application logs:4files/192,143bytes; pilot report logs:3files/7,644,226bytes, largest5,043,304bytes. No new permanent cleanup or runtime build. Durable ledger59,341,504bytes before this report. Compact evidence and regression assets are preserved outside the rotating runtime capture tree.


## Second return and retirement of tuning loop (12:39 UTC)
The frontal scale/pose repair passed native replay ae77e019 on ranged-positive260065782, occluded-ground260065851, and visible-front260065852 (1/0/1 matches;668/377/639ms). It did not establish generalization. Four camera inspections on a new full-health return produced zero shots; the target was initially out of view, then back/side-facing and overlapping another enemy. Camera settle increased100to300ms within the same deadline; the visual response improved but no measured speedup is claimed.

A further turned-face template passed its own source and two negatives (aef50730,449/245/389ms), but held-out fresh aim260067272 failed after the target turned and moved. This exposes pose and lighting brittleness, not a missing final example. Final requestab825783 firedzero, returned Kaeya4015 and verified Inventory6731. This loop is retired; do not add another one-frame template. Full field Pyro application remains unverified. Ready-Q observation is not a successful cast; its policy capability is explicitly marked primitiveTested=false until a safe cast validates it.

Inspectionf750e5ca skipped return because target-vision latency aged its sample. Recovery observations now omit target matching while preserving identity/health/freshness. Recovery-onlyae7f5710 switched back, but a slow final sample lost result accounting; regular6722 independently confirms4015 and Inventory6724. Final field request exercised the revised cleanup successfully.59focused tests pass. No health loss, deaths, resin, food, XP or defeat gains on this second visit. Teleportafded2db returned to Windrise Inventory6745/controller6746.

Retention12:39UTC:10,367,291,392bytes free,249recent/536,830,608bytes and32pins/57,567,042bytes, within caps. Durable event ledger59,576,923bytes. No build, app/RDP restart or permanent cleanup. Continue bounded Adventure Rank exploration; a live-safe burst/decoy alternative and a held-out multi-view detector remain future work, not prerequisites for exploration.


Held-out comparison: `artifacts/act-two-shield-held-out-scores.json` and contact sheet compare13retained success/failure anchors across ground/aim transitions, scale, facing, occlusion and charged-light tint. Two full frames rotated between contact-sheet creation and replay; their missing values are not scores. The fitted frontal source matches1.0; remaining available non-source views peak0.52-0.58 under the active color templates. Small turned shield views remain false negatives/unknown. This justifies retiring the fit-one-example loop and removing its selector. No broader recognition accuracy, field Pyro effect or objective-efficiency gain is claimed.
