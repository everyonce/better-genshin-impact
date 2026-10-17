# Stormbearer terrain assessment and recovery

The target remains the inactive Stormbearer Mountains waypoint, tp.json id59 at(-1271.522,2722.775). No waypoint reward or Adventure EXP was obtained in this assessment. Last verified rank remains AR9,955/1300. Act II remains locked; Act III was not started.

The eastern road/arch detour reached safe intermediate points but increased final-target distance from about108to119 map units. Its obstacle was a continuous cliff north of the road, with no confirmed walkable turn. A westward base probe also contacted that cliff; existing incidental-climb recovery returned to settled full-health ground535/536. Intermediate arrivals are not objective completion.

A bounded climbing attempt then recorded stamina arc heights62,58,54,49,45,41,39,35,31 pixels at559,567,575,583,591,599,607,615,622. Every batch ended in a verified Inventory pause. No resting ledge was established by the cutoff, so ascent stopped. Kaeya remained4015/4015; no fall, death, food, resin or currency spend. This tall eastern-cliff approach is retired.

The map recovery uses a general state rule within the existing starter-region bounds: fresh same-session full-health Kaeya, world climbing controls positively recognized by X/Space, no ground controls, no enemies or tracked objective, and original UID. It permits only opening the world map. It does not authorize climb release, movement, combat or other menus. The surrounding controller retains input/session/focus guards and bounded pause recovery.

Live mission9d26dd72d75a4e908da27b014abb6a07 opened map628 from the paused climb. Existing native teleport missionb32465396b3c45a2a697f0fd466a8d55 then verified Starfell Statue ground631 and Inventory634/controller635 with full4015HP. Map-only recovery and healthy ground arrival are live verified. All1932tests passed,0failed,43816.9603ms. No native build, application/RDP restart or permanent cleanup.

Commit4ebbfee522550da8250792c8fee567b0d0090f9d separately reserves6500ms plus the next hold before exploration movement when incidental-climb recovery is available. All1930tests passed. Its new early-stop branch remains tested-only; no live activation claim.

Compact receipts/observations are preserved in artifacts/act-two-stormbearer-climb-evidence.json and the durable event ledger. Model-selected route and camera requests remain manual interventions. No overall speedup or productive-gameplay-time claim is made.

The second shore attempt bedced241a80458fa17c2b6bd6f900b7 stopped at644 on UNKNOWN stamina evidence (pixels0,boxes[],height null), not a measured low value. The elevated-camera frame contains no visible stamina arc and does not establish whether stamina was full or low. No threshold was relaxed. Map-only swimming recovery2abe42e44b334f01bf98b1cb1c476af6 opened654; native teleport e226cf9c8fc641d1990156c7c4152b7b verified dry ground657/full4015 and pause660. The diagnostic now distinguishes unknown evidence from a finite measured value below the threshold, preserving the same safe stop. Recorded regression passes; all1933tests pass,0fail,45926.0907ms. New diagnostic wording itself is not separately live exercised. Do not start another crossing until map and terrain establish a traversable western approach and a clear turning point.
