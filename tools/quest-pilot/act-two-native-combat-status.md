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

Validation: 1,430 JavaScript tests passed, including 17 new guard/cancellation
cases. Syntax checks passed. A live empty-field test refused combat and restored
a verified inventory pause. Source changes were hotloaded without an application
restart or native build.

**Positive native execution and enemy damage remain unverified.** The nearby
potential target never produced a confirmed enemy bar. Four short approach
batches preserved HP; automatic approval review rejected a further approach.
No native rotation was invoked, no enemy defeat or reward was claimed, and the
character was left paused. Further movement on that approach requires explicit
approval. The old exact-level diagnostic is not the selected continuation path.

Native task return alone is not success: the underlying executor can log and
swallow execution exceptions. Inspect native logs and independent damage frames;
completion additionally needs loot/reward/quest evidence. The timeout is
cooperative and can outlive four seconds if native code does not unwind.
