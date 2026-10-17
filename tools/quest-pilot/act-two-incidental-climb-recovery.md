# Local navigation recovery and journal dispatch

Exploration now handles a newly observed low climb after its own grounded movement with one existing `releaseClimb` call (X60, short wait, S250). It requires unchanged full Kaeya health, no visible enemy, a same-session ground witness no more than five seconds old and within two map units. It then observes twice, at least700ms apart, and reports `groundRecovered` only for stable, enemy-free footing with full health. It stops for an alternate route instead of walking back into the obstacle.

The recorded low Lion entrance contact at(-1435.70,1652.47) also permits this recovery when resuming from inventory. Its adapter entry is restricted to that small location, fresh same-session full-health climbing and the original account. Other initial climbing states remain stopped. The existing bounded-key and pause wrapper retain focus/session checks and key release.

Live receipt `mission-42f4e7d4598d4bf3a4279fc5941eb61e` on2026-10-17 recovered footing at225/226, full4015HP, then verified inventory229. It took11925ms and one release. The terminal is classified failed because navigation intentionally stopped short of its target; `groundRecovered:true` records the successful recovery. Generic incidental contact elsewhere is regression-tested, not yet live-validated.

`actTwoRecover` now routes a recognized journal through the existing guarded journal-close handler after specialized journal recovery checks. Unknown journals remain stopped without falling through to Forge. Recorded Outrider journal117 covers the original failure. This dispatch is hotloaded; its live exercise is pending.

Validation:1892 tracked and newly added JavaScript tests passed,0failed,61214.5641ms. An earlier indiscriminate glob also included unrelated untracked draft tests and failed three; those drafts were preserved and excluded from this scoped publication. No application build or restart was needed. The separately published seven-phase lower-climb mission remains not deployed.
