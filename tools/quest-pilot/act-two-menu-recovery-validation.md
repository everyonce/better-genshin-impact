# Act II menu recovery validation

The map Back action can return to the Adventurer Handbook. Previously the pause protector did not recognize that menu and exhausted its 60-second budget. An exact, fresh Handbook close handler now sends one Escape, then independently verifies an inventory pause. It never treats the Handbook itself as proof of pause. The same handler serves supported fault recovery and map-close cleanup.

The fog-map region icon can join the OCR label as `CGalesong Hill`. The map proof accepts this recorded variant while retaining fresh session, map HUD, no active world/health, region position and exploration-label requirements. Map and explicit recovery operations now use a 12-second watchdog budget, release keys on exhaustion and request fresh recovery rather than implying user intervention is mandatory.

Live evidence, session mv9t341i-eft9p4aj9rk:
- Handbook failure5775f60d, frame8634; recovery4894b140 completed in7806ms, inventory8639.
- Icon-merged map failureaad1f146, frame8689/8691; recovery037303b9 verified map8693 in3750ms.
- Full map to Handbook to inventory transition638254c5 completed in10080ms, inventory8700, idle8701. No script, application, game or RDP restart.
- The 12-second exhaustion bound is automated-test validated; no artificial live timeout was induced.

Validation:1581 JavaScript tests passed,0failed,36.967seconds, including recorded failure fixtures and bounded-timeout/no-input regressions. No native code changed or rebuild required. Flight experiments, native-route experiments and unrelated drafts are excluded.

Read-only resin inspection is reusable: Forsaken Rift map8598 explicitly requiresAR25; Thorny Crown of the Mountain Wind8657 requiresAR30; Handbook8648 shows visible ordinary bossesLv36 and current BlossomLv12. These do not establish that every possible boss is impossible or every domain is locked. Resin200/200,spent0. No ActII completion or new AdventureEXP claimed. Mission remains active atAR9 200/1300.
