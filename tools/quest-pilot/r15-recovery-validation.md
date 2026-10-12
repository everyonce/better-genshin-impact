# r15 recovery validation

## Verified live results

The prior public snapshot, commit `3683d6b79e0f1a4dbbfdfc47e21dbb6a9c90e670`, was published on both `main` and `english-interface`. This report also records later witnessed live actions and source changes.

The already-open revival modal used one Confirm and no character key in a 3,104 ms receipt. A number-band crop from the same image correctly read eight available eggs, adding 68 ms to a 910 ms observation. The next first-pit route selected Kaeya and reached verified solid-floor landing at 100/1,427 HP after two W800 holds; its receipt took 19,457 ms.

Earlier bounded second-pit approach receipts used two W200 inputs and returned to verified pause in 6,649 ms and 6,686 ms. Later runner validation included two single-W200 approaches (4,217 ms and 4,471 ms), plus two no-jump attempts (6,545 ms and 6,754 ms) that used at most three read-only polls, sent no action, and verified pause.

An earlier second-pit crossing attempt took 29,153 ms total (28,713 ms routine). It used one E and two W600 holds; a third movement was rejected before key-down. It stopped at verified pause with Kaeya at 100/1,427 HP. This earlier failure was followed by additional witnessed runner validation below.

The ice-refresh attempt took 8,824 ms total (8,388 ms routine), used one E and no movement, and stopped because positive ice proof was unavailable. This was a false negative: the cooldown-text height measured 17.333 pixels against an 18-pixel threshold; the minimum is now 16 pixels. The strongest recorded image had ice-mask pixel fractions of 0.855/0.839 ahead and 0.977/0.928 at the feet, plus a 4.8-second cooldown. An offline regression accepts that immutable image and rejects short text, weak ice, and changed HP. The original failed receipt remains unchanged; this does not prove a crossing.

Subsequent floor-guard rejections stopped before movement while the moving platform shifted the observed geometry. All verified pause and preserved the 100 HP state. A later image showed Kaeya clearly standing on bright blue paving: its stone fraction was only 0.581, while the union of stone and ice masks covered 0.996 of the same underfoot area. The platform-only centering guard now uses three support probes and the exact mask union, subtracting the overlap. Other floor guards remain unchanged.

The corrected live attempt sent one D200 hold and no character-selection, skill, or forward key. It stopped before a second hold when destination probes changed. The receipt took 4,554 ms total (4,099 ms routine), returned to verified pause, and an image showed Kaeya centered on the moving platform with 100/1,427 HP. That verifies one guarded centering input, not the proposed two-hold sequence or a pit crossing. Opening the food inventory then took 2,791 ms and found seven revival eggs but no healing food.

A root-directed character recovery upgraded Amber from level 5 to 6. The witnessed changes were max HP 1,055→1,121, ATK 48→50, and DEF 67→71, consuming one 3-star EXP book (5,000 XP) and 1,000 Mora (16,466→15,466). The subsequent actual HP value is not yet verified; the max-HP increase must not be reported as healing.

The witnessed one-use character-recovery flow applied backpressure and sent no input when OCR reported `Wéapons` or `Falents`. Known OCR noise was handled while retaining exact unique menu zones. Reading the amount, stock, and cost from the same capture added 338 ms to a 1,280 ms observation. Recorded menu action times were: select Amber 4,130 ms; open Level 2,454 ms; add one EXP book 2,572 ms; confirm 2,198 ms; close Level 2,813 ms; close the remaining menu 2,390 ms. These are root-directed UI actions, not autonomous quest progress.

The latest canonical Wolf state was verified pause with no fault; the preceding witness showed Kaeya at 100/1,427 HP. Legacy-loaded engine labels marked UI actions failed. A source engine fix has been validated, but the persistent listener has not yet been reloaded, so the live labels remain uncorrected evidence.

## Current recovery work

The root-witnessed bounded runner has now been exercised live. With readiness expanded to at most eight additional read-only polls under a 15-second budget and cleanup time reserved, a second-pit crossing completed in 6,430 ms total (5,852 ms routine): two read-only polls, one W600 hold, and one Space60 jump. Guaranteed key-up handling was used. A far-bank image was visually verified and preserved; Kaeya remained at 100/1,427 HP. A subsequent single W800 hold on the far bank took 4,370 ms total (3,933 ms routine), again preserved 100/1,427 HP, and returned to verified pause. This establishes the second-pit crossing and safe far-bank movement for these witnessed runs.

The final full JavaScript suite passed 851/851 tests in 15,195.9565 ms, including the W800 addition and excluding the unintegrated Lion preparation file. Current focused source counts are 12 core, 9 adapter, 20 character-recovery, 33 engine, and 45 main-idle tests. Source tests and these bounded live runs do not establish uninterrupted autonomy.

## Limits

The second pit is crossed. The Wolf domain, Crash Course, and Act I remain incomplete. No end-to-end quest speedup has been measured, so no comparative speedup claim is supported. Root-directed actions, source hotloads, restarts, and recovery choices are interventions, not uninterrupted autonomous progress.

The report is suitable for shared public source: it excludes account identifiers, session credentials, process/request identifiers, and raw player OCR.

A cleanup request was rejected by automatic policy before the removal command executed; no files were deleted. An independent audit verified 197 preserved r13 entries. That preservation is not a completed cleanup.
