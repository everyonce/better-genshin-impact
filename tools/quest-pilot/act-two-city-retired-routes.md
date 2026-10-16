# Cathedral navigation: retired attempts, 2026-10-16

Do not replay these sequences for the cathedral objective. Preserve their files as diagnostic history.

| Route | Observed failure |
|---|---|
| act-two-upper-stair-clear-road | First point intersects retaining wall9922. |
| act-two-north-tavern-chest | First point intersects building corner9986. |
| act-two-cathedral-north-stairs | Drifts over exterior stair railing10048; grassy landing10050. |
| act-two-cathedral-outer-lawn | Previously reached water7550; remains retired. |
| act-two-cathedral-central-stair-entry | First east-to-west crossing hits rail10091. |
| act-two-cathedral-raymond-stairs | Crosses stair side wall10121. |
| act-two-upper-stair-return | Starting from the wrong terrace hits house10150. |
| act-two-cathedral-house-street-bypass | Northward leg crosses retaining-wall corner10179. |
| act-two-cathedral-visible-wall-corner | First three points succeeded; final west crossing hits building10222. |
| act-two-cathedral-building-north-opening | Reaches actual staircase but collides with bench10254. |
| act-two-cathedral-bench-stair-center | Clears bench and ascends; west turn is too early and hits corner10280. |
| act-two-cathedral-cleared-stair-landing | Northern landing reached, but final west leg hits building10334. |
| act-two-cathedral-upper-corridor-south-turn | Follows wrong side of stair mouth and hits retaining wall10354. |

## Measured diagnosis and verified correction

At 20:18 UTC, clear-ground displacement10377→10378 was(+4.383,+1.068) at camera192.5°, actual bearing193.699°.10386→10387 was(+0.363,-2.952) at camera97.5°, actual97.015°. Errors1.20° and0.48° support correct heading/localization in this sample. The failure was route geometry, not an axis reversal. Compact measurements: artifacts/act-two-city-heading-diagnostic.json.

Fresh10354 showed the staircase immediately right of the retaining wall. After a single X release onto visible pavement, act-two-cathedral-visible-stair-right succeeded10393 via(-825,2321),(-814,2321),(-814,2303), no climbing or damage. Fountain-stair-mouth reached10408(-803.92,2298.46); main-stair-centerline reached10432(-766.24,2275.44). These are verified sequential starts and endpoints, not interchangeable starting terraces. Health3953 throughout. No new quest reward or EXP from these navigation segments.

The controller steers on two-dimensional map coordinates. It cannot infer which terrace a coordinate belongs to, obstacle footprint, or stair/railing clearance. A route marked arrived proves only the sampled position and guard state, not the next segment. Do not infer ground-only reachability from a sparse historical waypoint list.

The retained ledger verifies that the old successful5084 approach included climbs4942 and4969 in session mv8bs5vw-4lgvs6stzly. Its actual trajectory is preserved in artifacts/act-two-old-city-trajectory.json. It must not be described as a previously verified ground-only corridor.

Latest useful geometry:10254 shows an open stair left of the bench at(-845.84,2311.92), camera261.10280 shows the character reached the stair corner(-838.08,2319.66), with visible steps and open landing to the right. A new route must clear that corner before turning west, and must be checked against fresh imagery. Health3953/4015 throughout these attempts. One exterior-stair fall10050; no death, food or resin spending.
