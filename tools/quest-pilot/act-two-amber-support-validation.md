# Amber support upgrade, 2026-10-18

Verified live at Windrise after the northern Ley Line retreat. Amber increased from level7,1186HP,51ATK to level10,1733HP,125ATK,88DEF (frame6297). Owned artifacts were equipped; Hunter's Bow1/baseATK23 was replaced by owned Recurve Bow, then enhanced1->16/baseATK38->76/HP10.2%->16.0%.

Actual costs:3Adventurer's Experience(15000EXP),16FineEnhancementOre(32000weaponEXP),6200Mora total. Mora108203->105203->102003;45FineOre->29. No premium resources, resin, food, wishes or weapon fodder. Character EXP was from books, not combat. Upgrade and equipment receipts are in artifacts/act-two-amber-support-evidence.json. Inventory pause6302/idle6303 verified; all input remained in BetterGI RDP7.

The team UI validates Amber's character identity separately from Kaeya, preserves fresh account/session/frame and one-use checks, and requires exact resource/cost previews before spending. Recorded OCR whitespace and weapon-label accent variations are normalized only in the relevant character menu. Native combat policy was not changed by this publication.34focused team tests pass; upgrade/equipment/weapon paths exercised live. Several menu actions stopped with zero input on unmatched stock, whitespace, tooltip state or an already changed screen; these are recorded failures, not successful gameplay.

Act II remains locked at AR9,955/1300. The northern Ley Line remains4/9. The normal-only2second Kaeya candidate has tests but no live validation; the close shielded target was unsuitable, so no candidate native window was run. Initial safe return GPS contour completed, but finalbankleg lost395HP before pause. Emergency map recovery770ms, followed by Statue healing. No newAdventureEXP or resin spending.

Next test is one bounded Amber charged Pyro arrow against a freshly identified wooden shield from the previously safe northern bank, with immediate shield/health assessment and pause/retreat within budget. The shield action is not implemented or validated yet; prepare/test it before returning. After shield removal, validate an actual defeat with the appropriate damage dealer. Do not equate a safe timeout or preview with progress.
