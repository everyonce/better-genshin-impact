# r15 recovery validation

## Verified live results

The r15 native focus helper recovered the bound RDP child without synthetic key or mouse input. A corrected self-contained package then restarted the native child while retaining the game and outer RDP host. The restart client now rejects incomplete or framework-dependent runtime packages before dispatch. Wolf resume receipts preserve the prior BetterGI process identity across native restart.

The corrected second-pit crossing took 16,785 ms by receipt: one E, two W600 holds, then a third movement rejected before key-down. It ended at verified canonical pause frame 49 with Kaeya at 100/1427. No pit or quest completion was verified.

A later ice-refresh attempt took 7,099 ms by receipt (6,109 ms in the routine). It sent Continue only: no 3, E, or W input. A 1,409 ms capture returned stale data; a loading transition then preceded a fall/reset. Kaeya died and Amber fell from 633 to 528 HP. Repeated full captures consumed the remaining ice. This was a failed recovery, not evidence that the ice route is safe.

## Current recovery work

For an already-selected Kaeya, the proposed refresh path now skips the 3 interaction and extra selection capture, performs one fresh post-cooldown check, then attempts E immediately. This path has not been live-validated.

The revival flow distinguishes available inventory stock from the single egg consumed. A direct already-open-modal path verifies the latest expected prompt, an unused permit, the immutable receipt, and no intervening input. A confirmation marker is persisted before the click. Full OCR merged the star and stock number; a number-band crop from the same capture read eight correctly, adding 68 ms to a 910 ms observation. The live recovery sent one Confirm and no character key in a 3,104 ms receipt. Amber remained active, so the receipt did not claim active-Kaeya revival. The following guarded first-pit route selected Kaeya and verified solid-floor landing at 100/1427 after two W800 holds; its receipt took 19,457 ms.

Current validation: 790 JavaScript tests passed in 15,731 ms, excluding the unintegrated Lion preparation file; seven Python restart-preflight tests and four portable-runtime fixture cases passed. Three native focus-helper tests passed before these script-only edits. The release build had zero errors, and the self-contained package passed the installed-package preflight. The shortened second-pit ice refresh is still awaiting live validation. No end-to-end quest speedup is established.

## Limits and cleanup

The second pit, Wolf domain, Crash Course, and Act I remain incomplete. No end-to-end quest speedup is measured. Root-directed actions, source hotloads, restarts, and recovery choices are interventions, not uninterrupted autonomous progress.

A cleanup request was rejected by policy before the removal command executed; no files were deleted. An independent audit verified 197 r13 preservation entries, and prior reads verified four primary r15 native-file hashes. Do not treat those checks as a successful cleanup or as execution of the rejected command.
