# r15 recovery validation

## Verified live results

The initial recovery snapshot, commit `4d37f6bbf827665f38c51f813c9e9b4510aa9546`, was published on both `main` and `english-interface`. It contains the native RDP focus/restart repairs, portable-package preflight, resume provenance, and direct revival recovery. This report also records subsequent script changes and attempts.

The already-open revival modal used one Confirm and no character key in a 3,104 ms receipt. A number-band crop from the same image correctly read eight available eggs, adding 68 ms to a 910 ms observation. The next first-pit route selected Kaeya and reached verified solid-floor landing at 100/1,427 HP after two W800 holds; its receipt took 19,457 ms.

Two bounded second-pit approach receipts completed with Kaeya at 100 HP and returned to verified pause. Each used two W200 inputs: 6,649 ms total (6,254 ms routine) and 6,686 ms total (6,186 ms routine). These receipts establish approach behavior only; neither verifies a crossing or quest progress.

A second-pit crossing attempt took 29,153 ms total (28,713 ms routine). It used one E and two W600 holds. The third movement was rejected before key-down; the run stopped at verified pause with Kaeya at 100/1,427 HP. The pit and quest remain incomplete.

The ice-refresh attempt took 8,824 ms total (8,388 ms routine), used one E and no movement, and stopped because positive ice proof was unavailable. This was a false negative: the cooldown-text height measured 17.333 pixels against an 18-pixel threshold; the minimum is now 16 pixels. The strongest recorded image had ice-mask pixel fractions of 0.855/0.839 ahead and 0.977/0.928 at the feet, plus a 4.8-second cooldown. An offline regression accepts that immutable image and rejects short text, weak ice, and changed HP. The original failed receipt remains unchanged; this does not prove a crossing.

Subsequent floor-guard rejections stopped before movement while the moving platform shifted the observed geometry. All verified pause and preserved the 100 HP state. A later image showed Kaeya clearly standing on bright blue paving: its stone fraction was only 0.581, while the union of stone and ice masks covered 0.996 of the same underfoot area. The platform-only centering guard now uses three support probes and the exact mask union, subtracting the overlap. Other floor guards remain unchanged.

The corrected live attempt sent one D200 hold and no character-selection, skill, or forward key. It stopped before a second hold when destination probes changed. The receipt took 4,554 ms total (4,099 ms routine), returned to verified pause, and an image showed Kaeya centered on the moving platform with 100/1,427 HP. That verifies one guarded centering input, not the proposed two-hold sequence or a pit crossing. Opening the food inventory then took 2,791 ms and found seven revival eggs but no healing food.

## Current recovery work

The current obstacle is moving-platform geometry. The guard stopped input, but its earlier color assumptions rejected a visible supported position. The correction must be validated live before claiming reliable passage.

Current JavaScript validation passed 804 tests in 14,111 ms, excluding the unintegrated Lion preparation file. Recorded platform cases cover both clipped stone masks and strong mask-union support; weak or missing support, changed HP/session/focus, and extra holds are rejected. This is source-level validation only; it does not establish live completion or uninterrupted autonomy. Earlier receipt-backed recovery work remains historical evidence, not proof that Act I completed.

## Limits

The second pit, Wolf domain, Crash Course, and Act I remain incomplete. No end-to-end quest speedup has been measured, so no comparative speedup claim is supported. Root-directed actions, source hotloads, restarts, and recovery choices are interventions, not uninterrupted autonomous progress.

The report is suitable for shared public source: it excludes account identifiers, session credentials, process/request identifiers, and raw player OCR.

A cleanup request was rejected by automatic policy before the removal command executed; no files were deleted. An independent audit verified 197 preserved r13 entries. That preservation is not a completed cleanup.
