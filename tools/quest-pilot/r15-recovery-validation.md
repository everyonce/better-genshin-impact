# r15 recovery validation

## Verified live results

The prior public snapshot, commit `fa38127`, was published on both `main` and `english-interface`. This report also records later witnessed live actions and source changes.

The already-open revival modal used one Confirm and no character key in a 3,104 ms receipt. A number-band crop from the same image correctly read eight available eggs, adding 68 ms to a 910 ms observation. The next first-pit route selected Kaeya and reached verified solid-floor landing at 100/1,427 HP after two W800 holds; its receipt took 19,457 ms.

Earlier bounded second-pit approach receipts used two W200 inputs and returned to verified pause in 6,649 ms and 6,686 ms. Later runner validation included two single-W200 approaches (4,217 ms and 4,471 ms), plus two no-jump attempts (6,545 ms and 6,754 ms) that used at most three read-only polls, sent no action, and verified pause.

An earlier second-pit crossing attempt took 29,153 ms total (28,713 ms routine). It used one E and two W600 holds; a third movement was rejected before key-down. It stopped at verified pause with Kaeya at 100/1,427 HP. This earlier failure was followed by additional witnessed runner validation below.

The ice-refresh attempt took 8,824 ms total (8,388 ms routine), used one E and no movement, and stopped because positive ice proof was unavailable. This was a false negative: the cooldown-text height measured 17.333 pixels against an 18-pixel threshold; the minimum is now 16 pixels. The strongest recorded image had ice-mask pixel fractions of 0.855/0.839 ahead and 0.977/0.928 at the feet, plus a 4.8-second cooldown. An offline regression accepts that immutable image and rejects short text, weak ice, and changed HP. The original failed receipt remains unchanged; this does not prove a crossing.

Subsequent floor-guard rejections stopped before movement while the moving platform shifted the observed geometry. All verified pause and preserved the 100 HP state. A later image showed Kaeya clearly standing on bright blue paving: its stone fraction was only 0.581, while the union of stone and ice masks covered 0.996 of the same underfoot area. The platform-only centering guard now uses three support probes and the exact mask union, subtracting the overlap. Other floor guards remain unchanged.

The corrected live attempt sent one D200 hold and no character-selection, skill, or forward key. It stopped before a second hold when destination probes changed. The receipt took 4,554 ms total (4,099 ms routine), returned to verified pause, and an image showed Kaeya centered on the moving platform with 100/1,427 HP. That verifies one guarded centering input, not the proposed two-hold sequence or a pit crossing. Opening the food inventory then took 2,791 ms and found seven revival eggs but no healing food.

A root-directed character recovery upgraded Amber from level 5 to 6. The witnessed changes were max HP 1,055→1,121, ATK 48→50, and DEF 67→71, consuming one 3-star EXP book (5,000 XP) and 1,000 Mora (16,466→15,466). The subsequent actual HP value is not yet verified; the max-HP increase must not be reported as healing.

The witnessed one-use character-recovery flow applied backpressure and sent no input when OCR reported `Wéapons` or `Falents`. Known OCR noise was handled while retaining exact unique menu zones. Reading the amount, stock, and cost from the same capture added 338 ms to a 1,280 ms observation. Recorded menu action times were: select Amber 4,130 ms; open Level 2,454 ms; add one EXP book 2,572 ms; confirm 2,198 ms; close Level 2,813 ms; close the remaining menu 2,390 ms. These are root-directed UI actions, not autonomous quest progress.

After the second pit, the bounded runner walked the stairs and corridors to the final crystal. Kaeya remained at 100/1,427 HP through the witnessed movement. Two early LMB60 strikes followed by 150 ms settles still left the attack mid-swing. Source now waits 900 ms after a strike, with a pre-input reserve plus 750 ms, but this change is not a claim of successful crystal activation.

A third strike was followed by a black HUD transition and Kaeya closing the Bravo dialogue. Health was unavailable during the transition, so no damage outcome is confirmed. The legacy main loop latched an ambiguity fault. A narrow source fix accepts a matching strike-closing transition observed within 15 seconds, while the separately witnessed recovery handles a dialogue held longer by that fault. The persistent listener was subsequently reloaded at a verified world boundary.

The hotloaded recovery path validated an unused root-witness permit, a real receipt, and the expected entry before sending five Space60 presses. It took 6,565 ms and stopped at a choice screen. A first continuation attempt correctly sent no input and stopped in 566 ms because legacy key records lacked a frame association. The comparison now uses paired semantic frame/time values and tags future key records with their frame; it does not alter historical receipts.

A subsequent local generic dialogue-closing pass sent nine presses, totaling 712 ms of input time over 19 seconds, then stopped on unrecognized state during an automatic movie. It did not claim quest completion. A read-only poll after the movie showed the authoritative `Obtained New Character Kaeya` overlay outside the Wolf temple. One guarded acquisition click took 13,229 ms including the outdoor observations. The reward HUD showed Amber at level 7 and 1,186/1,186 HP, and the journal subsequently showed only `Sparks Amongst the Pages — Meet Lisa at the temple` under Prologue: Act I. Wolf/Crash Course is complete; Act I is not. These actions were root-directed interventions; no user gameplay action occurred in this continuation.

## Current recovery work

The root-witnessed bounded runner has been exercised live. With readiness expanded to at most eight additional read-only polls under a 15-second budget and cleanup time reserved, a second-pit crossing completed in 6,430 ms total (5,852 ms routine): two read-only polls, one W600 hold, and one Space60 jump. Guaranteed key-up handling was used. A far-bank image was visually verified and preserved; Kaeya remained at 100/1,427 HP. A subsequent single W800 hold on the far bank took 4,370 ms total (3,933 ms routine), again preserved 100/1,427 HP, and returned to verified pause. Later witnessed movement reached the final crystal, followed by the closing scene, Kaeya acquisition, rewards, and verified next journal objective.

The final full JavaScript suite passed 881/881 tests in 17,521.6179 ms, including the acquisition-dismiss extension and excluding the unintegrated Lion preparation. Focused source counts are 14 witness core, 10 witness adapter, 20 character-recovery, 33 engine, 61 main-idle, and 11 closing-recovery tests. Source tests and these bounded live runs do not establish uninterrupted autonomy. The supervised endpoint stopped and restarted only the script on the same RDP child; the new listener was verified idle, without a fault, with the game still open.

## Limits

Wolf/Crash Course is complete and the next quest is verified as `Sparks Amongst the Pages`. Act I remains incomplete. No end-to-end quest speedup has been measured, so no comparative speedup claim is supported. Root-directed actions, source hotloads, restarts, and recovery choices are interventions, not uninterrupted autonomous progress.

The report is suitable for shared public source: it excludes account identifiers, session credentials, process/request identifiers, and raw player OCR.

A cleanup request was rejected by automatic policy before the removal command executed; no files were deleted. An independent audit verified 197 preserved r13 entries. That preservation is not a completed cleanup.
