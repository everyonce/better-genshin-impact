# Bounded flight observation and witness refresh

Finite reviewed flight segments now use the same fresh account, exam timer, health and Space-control crops as course tracking. They sample locally while holding one direction, release on proof loss, and pause before writing the last image. Stationary segments emit no horizontal key. Left movement is allowed only as an explicit flight plan and cannot combine with backward or stationary movement.

Inspection can refresh an expired historical exam witness, but it requires zero camera offsets and zero movement holds. The current frame must still satisfy the complete exam state guard. Gameplay plans retain the ten-minute witness age limit. This avoids weakening input authorization to recover from an old checkpoint.

Live session `mv9t341i-eft9p4aj9rk` evidence:

- `31190e99`: flight changed to ground during the bounded approach; input released after 425 ms, inventory pause verified, HP 3953/4015 unchanged.
- `1395ee71`: no-movement inspection refreshed expired witness 9611 to fresh field 9635, airborne and healthy; verified pause returned in 9.569 s.
- `0453f05a` and `04ad5ea6`: left gliding moved toward the visible column, measured 1572 ms and 920 ms, with unchanged health and verified pauses. Subsequent stationary inspection did not prove lift; this is input validation, not route success.
- `5decd049`: stationary segment sent no horizontal input. Descent remained visible; no ascent claim.
- Course receipts at 9714/9718 preserved a 3 m to 80 m passage candidate and subsequent 80 m to 73 m approach. Neither proves exam completion.

No native build or application/RDP restart was needed. No new death, item spending or resin spending occurred during this change. Entire-exam completion remains unvalidated. The experimental route chain and unrelated navigation/combat changes are excluded from this publication.
