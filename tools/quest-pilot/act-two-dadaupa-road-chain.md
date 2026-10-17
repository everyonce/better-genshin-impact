# Dadaupa road encounter and bounded route chain

The reviewed road encounter at(-1409.45,1587.87) contains two visually identified Lv6 Hydro Slimes. `act-two-field.js` permits the existing Cryo/normal-attack loop only with a nearby recent encounter witness, known full-size Kaeya health at least85%, original session/account checks, grounded field state and at most two detected targets. The encounter loop is limited to six cycles/eight seconds and releases keys before its verified inventory pause. This scope is not a general enemy classifier.

Live receipt `mission-335d7ca5baea40099d8da12af3950edb` used one Cryo skill and three normal attacks. Frame282 verified both slimes gone, two Character EXP×10 notifications and Mora23+20, with4015/4015HP. Adventure EXP gained was0. Total request12358ms. A missing OCR space in the tracked quest ended that cycle safely; whitespace normalization is now regression-tested but has not been separately re-exercised live.

`act-two-road-chain.py` runs at most three finite navigation segments. It preserves the cursor after a verified deadline stop. At the reviewed enemy contact it may issue the existing guarded defense and resume only after clear, healthy ground. Unknown outcomes, unfamiliar enemies, failed preflights, unsupported stops and failed footing checks terminate the chain. A recovered climb requires an alternate route and is never blindly retried.

The chain's deadline continuation was exercised live in receipts168f2ea1/e0cc31e1, ending at(-1410.40,1466.23). The combined navigation-to-combat-to-navigation branch is tested and pending live exercise; its combat and navigation components were exercised separately. No waypoint unlock is implied by route arrival.

The final waypoint approach also supports camera-only inspection in the reviewed southern road corridor, one W600 mount at the recorded low rock, and one W600 stamina probe there. Further climbing requires same-frame substantial yellow-arc stamina and full health. Map recovery is available for a fresh full-health enemy-free climb within18map units of the waypoint. The mount418 and probe423 ran successfully without damage;423 regained ground controls. Continuous climbing and map escape are not yet live-validated.

Generic incidental-climb recovery was additionally exercised at the waypoint approach in receipt `mission-c068c8a8d38e4f438c135db767d08231`, with settled406/407 and full health. The route chain stopped rather than repeating that face.

Validation:1902 scoped JavaScript tests passed,0failed,49949.4273ms; the Python recorded-encounter selection test passed. An initially overbroad camera predicate caused four existing negative tests to fail; it was restricted to the reviewed corridor/current quest and all passed. No build or application/RDP restart. Compact encounter evidence is in `artifacts/act-two-dadaupa-defense-evidence.json`.
