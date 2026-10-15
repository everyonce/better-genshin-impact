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
