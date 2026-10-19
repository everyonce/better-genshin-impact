# Windmill house approach: verified stair bypass, high-wall stop (2026-10-19)

**Outcome:** The first pillar was bypassed on grounded steps; a second stone post was bypassed onto a broad upper landing; Kaeya crossed that landing to `(-830.4004,2207.3105)`. Frame 180 shows a tall continuous stone wall directly on the line toward the library house anchor near `(-820.02,2222.8)`, with a diagonal stair structure farther right. The target house/blue roof is **not visible or reached**. Stop the direct ground approach here. Inventory pause frame 182 persisted in a no-input observation frame 184; the owned pilot is idle. Kaeya remains 4015/4015 HP, grounded, with no enemy bars and `Look for the location in the riddle / Higher 31m`. Last verified AR9 955/1300 and Act II locked; no quest or EXP change.

Fresh preflight `mission-4e48490746bf4d01be17aa8448076d1d` captured field frame 98 at `(-849.1699,2201.0693)`, UID `693306810`, 4015/4015 HP, grounded, enemy-free and `Higher 37m`. Every subsequent route used the same BetterGI R18 child PID 11256, RDP session 7 and sole owned pilot session `mvf7ifnp-30yiczwdy7v`. No application, game, script or RDP restart, user-console action, combat, item use, resin use, fall or death occurred.

Verified ground transitions (all full health, no jump or climb):

| Request | Route target | Measured endpoint | Result |
| --- | --- | --- | --- |
| `mission-218d410cd89d4703b0cd802b84116e82` | first pillar left `(-849.2,2196)` | frame 113 `(-849.25,2197.87)`, Higher 38m | Arrived; clear of the old `y2201` pillar line. |
| `mission-89aab1c25e39469e939a1c3d47385d7f` | eastbound stair `(-842,2198)` | frame 127 `(-843.68,2197.63)`, Higher 36m | Arrived on broad stair corridor. |
| `mission-1eef25cd2462461985c0bbd340baae09` | stair corridor `(-834.5,2198)` | frame 140 `(-836.26,2198.39)`, Higher 34m | Arrived on open steps. |
| `mission-62da4705214a4202a0a94934ac2da0ec` | direct upper stair `(-829,2198)` | frame 152 `(-833.71,2199.67)`, Higher 33m | Stalled on a **second** stone post; route moved outside active `routes/` to `act-two-blue-roof-upper-post-retired-20261019.json`. |
| `mission-d029714b32804d7391874c12b8ca7a59` | back/right bypass `(-836,2204.5)` | frame 167 `(-835.07,2203.09)`, Higher 31m | Arrived on broad paved upper landing. |
| `mission-83acfdffdff04f80a0894f22d5c5103b` | upper plaza `(-829,2208)` | frame 180 `(-830.40,2207.31)`, Higher 31m | Arrived on paving; **new high wall** blocks the direct house line. |

Each navigation request used bounded local observe/move cycles and a verified Inventory pause. There were zero jump recoveries, climb steps or releases during the six navigation requests. The previously approval-denied lower-balcony W150 ladder crossing remains excluded; the two stone-post stops are controller progress-guard stops, not access denials. The known lower stair descent/return remains verified (`act-two-blue-roof-stairs-result-20261019.md`). Reverse travel from the **current upper-plaza wall endpoint** has not been live exercised and must not be described as verified.

**Next route decision:** Use a fresh in-game map/field witness to identify a real opening around the tall wall or the diagonal stair on its right; do not aim another straight line through it. An alternate candidate is a city-waypoint approach from the north via the previously recorded upper street around `(-850,2237)` and `(-838,2237)`, then the library's house anchor `(-820,2223)`. That house route is reference geometry, not account-validated from this checkpoint. Keep the game paused until one of these access corridors is visually grounded. No roof climb or glide is authorized by this report.

**Measured timing:** From preflight start at 12:42:06.701 UTC to final no-input terminal at 12:52:36.221 UTC: **629,520 ms**. Eight local requests (fresh inspection, six navigation requests, final no-input observation) totaled **113,154 ms**; the remaining **516,366 ms** was between requests, including protected pause, visual review, route preparation and writing, not measured as pure model latency. Recorded W holds across the six navigation requests total **8,303 ms**. No whole-run Act II efficiency claim follows from this segment. The observed gap between requests is the main batching opportunity once a corridor has been independently validated; the unforeseen posts and high wall required route review here.
