# Native combat integration checkpoint

The quest pilot now has an `actTwoNativeCombat` entry point around BetterGI's
`Dispatcher.RunCombatScript`. Its initial strategy is one Kaeya skill followed
by one second of normal attacks. Quest code handles encounter entry and the
existing verified inventory pause. It does not add another bespoke attack loop.

Entry requires fresh original-account evidence, the pinned RDP session and
foreground game, grounded Kaeya with at least 85% HP, a bounded field location,
and one substantial rectangular enemy health segment near the center of view.
Exact enemy-level OCR is unnecessary. Missing, ambiguous or menu evidence
refuses combat. A four-second cooperative cancellation monitor checks focus and
stop requests, awaits native unwind, releases the rotation's inputs and disposes
its linked cancellation source. Health is captured before and after the chunk.

Validation: 1,432 JavaScript tests passed, including 19 new guard/cancellation
cases. Syntax checks passed. The live empty-field refusal restored a verified
inventory pause. The positive live test then executed the native Kaeya rotation
in 1,756 ms against an ordinary Pyro Slime. The game displayed Character EXP x10
and, on the following reward check, Mora x16. These independent rewards confirm
the defeat; disappearance of the health bar was not used as proof. Total wall
time for the successful combat request, including observation and verified
pause, was 9,705 ms. HP was unchanged during the native rotation and subsequently
increased when energy rewards were absorbed. No food or resin was spent.

Two bounded entry fixes were needed: English party-name OCR occasionally missed
Kaeya, so native canonical party recognition now resolves the actor; an inventory
transition and jumping slime changed the apparent bar geometry, so entry polls
for complete encounter evidence and accepts the observed four-pixel bar while
retaining width, rectangularity, health, account and session checks. The native
log independently confirmed all four starter characters. No application restart
or native build was required.

The first target-acquisition continuation was denied by automatic review. The
parent clarified that the short-test budget was an efficiency target rather than
a restriction on authorized gameplay; one permitted retry acquired the target.
The denial is resolved. The waypoint detour remains stopped. This validates one
ordinary slime encounter, not sustained multi-enemy combat or party rotations.
The old exact-level diagnostic is not the selected continuation path.

Native task return alone is not success: the underlying executor can log and
swallow execution exceptions. Inspect native logs and independent damage frames;
completion additionally needs loot/reward/quest evidence. The timeout is
cooperative and can outlive four seconds if native code does not unwind.

## Cyrus camp and owned-resource upgrade

The separate guarded small-group entry cleared the first Cyrus camp. The game
changed its objective counter from 0/3 to 1/3 after three native rotations
(1,690 + 1,476 + 1,756 ms). Their complete request time was 29,920 ms. This is
combat execution timing, not whole-session throughput. The lowest observed HP
was 2,242/2,313; energy absorption restored full HP. No food or resin was spent.
The quest has not awarded Adventure EXP yet; two camps remain.

The final rotation used a one-use continuation bound to the previous successful
native receipt, its fresh-position witness, unchanged quest area and high HP.
This handles a nearly defeated enemy whose tiny remaining red segment falls
below the entry detector. It cannot chain arbitrary empty-field attacks.
Generic receipt flags remain conservative; the independently captured quest
counter is the completion evidence.

Kaeya was then upgraded from level 16 to 20 using the reviewed in-game preview:
2 Hero's Wit, 1 Adventurer's Experience, 2 Wanderer's Advice, and 9,400 Mora.
The remaining Mora balance independently confirmed the cost. HP increased from
2,313 to 2,635, ATK from 168 to 175, and DEF from 182 to 207. This EXP came from
owned books, not combat. The native entry guard now accepts the verified new
HP maximum while retaining the prior validated level-16 baseline. The upgraded
character has not yet completed the next fight.

The current complete JavaScript suite passed 1,438 tests in 35.630 seconds.
The native rotation itself is unchanged. Journal scrolling, character-menu
recognition and the exact upgrade preview have been exercised live. No native
build or application/script/RDP restart was needed. The second camp approach
is in progress with bounded navigation and stall protection.


## Second Cyrus camp and bounded local sequence

The upgraded Kaeya cleared the eastern remaining camp. The game independently
changed its counter from 1/3 to 2/3. Five native rotations at that camp totalled
8,463 ms; the eight associated combat, healing and camera requests totalled
81,522 ms. Navigation and pauses are excluded, so these totals are not overall
throughput. One owned Delicious Chicken-Mushroom Skewer was consumed, leaving
two; healing to 2,635 HP was verified. Final combat HP was 2,554/2,635. Resin spent
remains zero. Act II is still locked at the last verified Adventure Rank 9.

The first approach wandered against cliffs and was abandoned after distance
regression. Fresh map inspection confirmed the quest marker; teleporting to the
known Starsnatch waypoint and descending the grass reached the actual camp.
The saved eastern route produced 144m, 96m, 65m and then Quest area reached.
Distance checks were operator observations, not a new automatic distance guard.

Native group combat can now run at most four short chunks locally, with fresh
health, session, encounter and progress checks between them. The sequence stops
on missing targets, insufficient health, no measured progress, a quest increment
or its time bound. Bar reduction is only a conservative continuation heuristic;
quest counters and rewards remain authoritative. Unit tests cover continuation,
no-progress stops, guard stops, deadlines and immediate objective completion.
The live final request stopped after its first chunk when the counter increased;
multi-chunk live throughput has not yet been demonstrated.

The group strategy includes the native burst command from the existing starter
rotation. Burst activation was not independently verified; normal attack damage
and objective completion were. Camera occlusion by grass and a stone pillar
required bounded camera corrections. Native task completion flags remain
conservative. No native build or application, script or RDP restart was needed.
The complete JavaScript suite passed 1,447 tests in 37.310 seconds.


## Third investigation and free recovery

The third investigation advanced directly to `Defeat the attacking monsters`; no literal 3/3 toast was captured. The newly spawned axe Mitachurls remain. A native Amber skill followed by a Kaeya switch took 10.219 seconds. Retained frames show knockback into rocks and burning grass, with targets leaving the viewport. Missing comparable bars do not prove zero damage.

Free Statue recovery restored Kaeya from 1991 to 2635/2635, verified on consecutive world observations, followed by verified inventory pause. The repair accepts the recorded third portrait label beginning at y=213 and polls boundedly when the instructional text disappears during healing effects. Missing panel evidence still refuses healing. No food was used for this recovery.

Native chunks now arm the linked .NET cancellation timer before calling the executor; cancellation after a swallowed native exception cannot be reported as successful execution. Timer-arm failure still releases inputs and disposes the token source. A no-input probe of short 50ms waits stopped after 4.086 seconds with unchanged full health and verified pause. This is cooperative cancellation, not a hard four-second bound: a single native wait(10) ignores the avatar token and ran 10.095 seconds. Mission rotations must avoid long waits or other uninterruptible commands.

The next bounded ambush experiment uses the native current-character skill and one-second attack, avoiding the blocked switch path. This recipe is unit-tested but has not yet been live-validated against the ambush. The full JavaScript suite passed 1,456 tests in 43.498 seconds. No native rebuild or runtime restart occurred.


The live short-rotation retry exposed an API detail: an explicit current-avatar name is rejected by alias validation. The supported form omits the character prefix and passes a null default avatar. That corrected invocation completed in 1.745 seconds. It did not establish effective combat: the player was knocked into a cliff and bush, health fell from 2527 to 2356/2635, and the unchanged 90% guard stopped after one chunk. No freeze, defeat or comparable-target HP reduction was confirmed. The clearer return view shows a mixed axe and wooden-shield group, correcting the earlier two-axe classification. Inputs remain safely paused pending a defensive or positioning correction; the same rotation must not be repeated to spend down healing stock.

## Native targeting and acquisition validation

The final ambush now uses the stock `AutoFightTask` continuous camera targeting with a two-second native timeout and independent four-second cooperative cancellation. Its short strategy uses a lateral dodge, skill key and normal attack clicks. Pickup, guardian, party-changing and fight-end side effects are disabled. Existing solo and earlier camp rotations are preserved. The task releases keys and buttons and joins the targeting task before returning.

The first attempt never entered native combat: repeated exposed observations lost enemy bars during knockback, and HP fell from 2635 to 2311 before the unchanged 90% guard stopped it. Entry now checks account identity and the recent local encounter witness while paused, then takes one same-image acquisition with cropped health, objective and ground-control OCR. It does not encode a PNG or perform full-screen OCR before native start. The enemy contour crop includes the upper screen area where the recorded close Mitachurl bar appeared; geometric filtering remains required. This reuses the existing OpenCV contour implementation. The stock `AvatarRecognition` API is not directly exposed to JavaScript.

Real-image replay recognized the visible ambush and rejected menu, empty-world and occluded examples in 231–405 ms. A live 300 ms menu-transition wait sampled too early and refused safely with unchanged full HP. With a 550 ms wait, fresh acquisition took 343 ms and `AutoFightTask` was invoked 957 ms after Escape release. That measures native invocation, not the exact first native input.

The native task then ran for 2.187 seconds. The retained view shows a changed camera, displacement, a normal-attack arc and an active skill cooldown; the native log corroborates skill cooldown and timeout. HP remained 2635/2635 through the verified pause. No comparable-target HP reduction, defeat, reward or quest transition was confirmed, so one chunk stopped on `no_damage_progress`. Successful task execution is not successful ambush completion.

The corrected plateau route, including the camp-post bypass, reached the ledge in a complete guarded replay without health loss or stalls. Free Statue healing was verified before the return; this validation used no food or resin. All 1,476 JavaScript tests passed in 41.535 seconds. No native build or application, script or RDP restart was needed. Act II remains locked and the Cyrus reward remains unclaimed.
