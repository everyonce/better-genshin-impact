# Optional first-current ascent test

The successful bomb followed by a grounded resume suggests the initial glide did not retain enough altitude. This remains a hypothesis. Saved3699 shows the verified current;250037023 shows the bomb hit near floor height and250037070 shows landing. The later second-current jumps were short of the visible vent and must not be replayed.

An optional `--ascent-hold-ms` (200–1200) on `currentProbe` leaves all direction keys released after verified deployment. Every200ms of requested wait it samples flight and health again, stops immediately if either changes, and enforces a2500ms cooperative observation deadline. It issues no extra Space or attack. Only afterward may the existing separately reviewed bomb follow-up run. All original floor2488, session, freshness, one-use plan, input release and pause guards remain. Synchronous host calls retain the documented cooperative-deadline limitation.

2002 canonical tests passed in53622.2981ms, including five measured ascent samples, invalid plan rejection, health loss and landing stops. Hotloaded into r18 without restart.

Fifth attempt live result: the1000ms requested hold produced five positive flight samples across1753ms, with unchanged2683HP. Visible wings persisted through the following two bomb cycles. This verifies sustained flight and successful follow-ups, not a quantitative altitude gain. The broken-floor footprint and floor tiles appear farther below after the hold, but automatic camera motion prevents a controlled height comparison. The first bomb landed short; the next bomb showed three369hits on the first group, then a rightward cycle showed two369hits on the lower archers. No whole-room clear or precise kill count is claimed.

The second-current double-Space attempt was interrupted by Superconduct:2607->2510HP, unknown controls and knockback. No subsequent exposed probe was issued with only22HP above2488. Supported exit and free Windrise healing restored2764.

Optional `--adaptive-deploy` now samples after the first Space. Positive flight omits the second press; a positive jump control retains the existing300-550ms deployment window. Unknown controls, low health or a late sample refuse another input and pause. This addresses the possibility that a highlighted updraft jump control already opens the glider, but that hypothesis remains **not live-validated**. Existing two-press behavior is unchanged unless explicitly selected. The full canonical suite passed2006tests in52862.5638ms. No new difficulty or health-floor change.
