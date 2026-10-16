# Act II navigation repair, 2026-10-16

Act II remains locked at AR10; last verified AR9 170/1300. Resin200/200, spent0. This is an engineering milestone, not quest completion.

The command tool previously restarted every supplied route at waypoint0, although receipts already returned nextWaypointIndex. New `--resume-route` resumes only the exact last route/session after a terminal deadline stop with a verified Inventory pause. It verifies the submitted waypoints, original route hash and cumulative cursor. Pending outcomes, intervening requests, changed routes, combat/terrain/health stops and corrupt cursors are rejected. New navigation submissions persist one compact progress record before request submission. Do not use this flag to push through terrain failures.

Ordinary exam/exploration travel now scales movement holds by distance to the arrival boundary, retaining the800ms ceiling and fresh observation after each hold. NPC/marker approaches keep their previous precision behavior. No native build or restart.

Measured baseline:971829ms wall,704093ms verified pause gaps,267736ms controller requests,32951ms recorded movement-key holds.193 observations cost170958ms, including94384ms PNG writes. Categories overlap; request time is not productive gameplay. A repeated route backtracked approximately7m. Evidence: artifacts/act-two-exam-navigation-diagnosis.json.

Live ground segment5e5f63f5738449e4a571d6a1c19d1819 reached southern terrace:92m->67m from exam,24.336m displacement,HP3637unchanged,no climbing,36088ms wall/6154ms input. The next face is a cliff and has not been climbed. Reverse route validation2544623c stopped at cursor1;33832343 resumed only remaining2points and arrived safely. Combined return used9movementholds versus16outward, but the extra deliberate deadline stop prevents claiming an overall speedup. Current pause7481/controller7482; no further route inferred from this test.

Journal inspection now supports one guarded World Quest tab click and exact return to All. Live7234 showed only Collector of Anemo Sigils with no displayed AdventureEXP. License to Glide7241 is available and displays175AdventureEXP,4375Mora,2XPbooks,5ores; reward NOT earned. Selecting Navigate opens the map: inspect result before choosing the next menu action.

Validation:1569 tracked-JS-plus-new-probe/travel tests passed0fail,35964.6ms Node/36031ms wall, using the live bgi adapter.69 navigation tests,9 journal tests,6 cursor tests and3 existing command-gate tests passed. First command-gate run hit sandbox temp permissions; rerun with workspace temp passed. Live cursor and movement timing were exercised; the Whopperflower probe remains unvalidated and excluded from this publication.

Retain source-only nativeRouteMapContext experiment and other unfinished work; never whole-copy source bgi.js to runtime. Ley Line remains parked6/7; no new return loop. Full goal: tools/quest-pilot/act-two-goal.md.
