# Cyrus ambush decision, 2026-10-16

Hold at Windrise after free healing: consecutive world frames 2599–2600 show Kaeya 2635/2635; Inventory proof 2602 and controller frame 2603 are idle. No return trip has begun. Cyrus remains at `Defeat the attacking monsters`; Act II remains locked at the last verified AR9, 20/1300. No food or resin was spent in this recovery.

| Sequence | Native chunks | Native time | Combat-request time | Before/after HP declines |
| --- | ---: | ---: | ---: | ---: |
| First completed camp | 3 | 4.922 s | 29.920 s | 71 HP |
| Second completed camp | 5 | 8.463 s | 53.764 s | 199 HP |
| Latest ambush probes | 4 | 9.556 s | 40.798 s | 77 HP |

These are sums of positive net declines between sampled before/after health, not gross damage or attack-only damage. The brackets include the first post-native observation. Healing gains are not used to estimate gross damage. Second-camp healing, camera and refused-entry requests add 27.758 s beyond its combat-request time. The two camps have authoritative quest-counter increments; the ambush does not.

Five additional ambush intervals with no native attack between their endpoints lost 349 HP: 2635→2589, 2582→2474, 2474→2456, 2456→2410, and 2475→2344. They bracket pause transitions, acquisition, and in some cases a camera correction. Retreat then lost another 183 HP before safe Windrise arrival. This is stronger evidence of avoidable exposure than attributing all losses to the attack recipe.

Fast acquisition is working: the four native invocations began 957–1008 ms after Escape release. The successful old camps took 1456–3859 ms. However, after native return the current path still spends 1745–2907 ms before requesting Inventory, including two world observations. Native time is only 23.4% of current combat-request wall time; the successful camps were 16.4% and 15.7%, so total overhead alone does not explain the different combat outcome.

Three factors remain distinct:

* Damage is real: frame 2474 shows white 45 enemy damage and a depleted axe-enemy bar with Cryo status. Camera/count changes correctly report unknown association, not zero damage. Requiring a single associated bar cannot support continuation in this five-enemy encounter and would also reject several successful earlier camp transitions.
* Range/facing and interruption are real: frame 2524 shows the Cryo cone pointing away after a lateral dodge. An attack-first experiment then suffered knockback, with the skill still cooling at entry. Neither proves a better rotation. A Burst-first candidate never ran because fresh HP was below 90%.
* Repeated acquisition and pause cycles cost health without adding damage. The refreshed entry floor and unknown-association stop must remain; inventing progress or lowering the combat floor would conceal this problem.

The selected next test is a smaller pause-handoff change, not another rotation or return trip: use the already-fresh post-combat world observation to request Inventory immediately, then the same 650 ms settling delay and independent Inventory proof already validated on acquisition refusal. Avoid the extra exposed world capture. Test stale/session/health/menu rejection and replay the recorded terminal observations, then exercise one no-combat pause cycle at the safe Statue. Compare native-return-to-pause-request latency before any return. Keep native AutoFight and its entry/cancellation bounds unchanged. This addresses measured exposure but does not claim to solve target association or finish combat.

The existing Statue approach exception already permits 60% HP only within eight metres of the known Statue, with no enemies, one exact waypoint and a maximum ten-second request. The initial fifteen-second invocation missed that exception; the ten-second invocation reached the interaction prompt and free healing succeeded. No health predicate was relaxed.

Published recovery/combat-evidence changes are commit `4a559990b964260d3a21769fa62949ada65320e4`, verified on both requested remote branches. All 1484 JavaScript tests passed in 35.502 s. The experimental native recipes were preserved privately and the runtime and source recipe were restored to the published version. No native build or application/script/RDP restart occurred. Raw account observations and receipts remain private.
