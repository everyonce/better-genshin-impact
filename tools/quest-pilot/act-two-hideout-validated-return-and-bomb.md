# Hideout return and first verified bomb hit

Act II remains locked at AR9,955/1300. The current supporting quest is Outrider Style. No domain completion, Adventure EXP reward, or resin spending is claimed.

## Return-route correction

The failed fourth return first diverged before the first bend:12800ms forward input replaced the successful third return's9400ms, an extra3400ms. It later turned44degrees early at107m, where the successful approach continued six800ms forward holds at about142.5degrees. Similar objective distance did not establish the same position. Old third-return screenshots had expired; this comparison uses retained action/heading evidence, not an invented visual match.

The fifth return completed the entrance at3617/3622, Higher1m with the exact F Raptor's Hideout prompt and Kaeya4015/4015. The guarded interaction receipt95ec6f395c6744a7a4d8aa5ee52c8124 opened the entrance. No damage or death occurred during this return.

`act_two_hideout_return.py` provides one reviewed ground segment per invocation. It requires a fresh grounded full-health witness, native heading, exact objective, immediate verified predecessor, and a written review of visible ground/left/right landmarks. Distance alone cannot resume a segment. A single bounded signpost correction is permitted after the first road segment stops short; repetition and overshoot are rejected. The corrected tail uses actual fifth-return actions from `routes/act-two-hideout-fifth-return.json`, including camera-only review boundaries and the rock/tent bypass. Eight compact image/metadata references total under1MiB. They are visual references, not automated landmark recognition.

The initial helper segments were exercised live; the later corrected actions were exercised individually. The complete updated wrapper has not been replayed end-to-end. Its ground route ends before the shelf hop and upper climb; neither is authorized as blind timing replay. Fresh slope, stamina and safe-landing evidence remains necessary.

## Live approach and bomb evidence

Fourth domain attempt: tutoriale719f910a5e142b19bfc0e3be4c71e5a completed22 dialogue presses and two exact tutorial clicks in47576ms at2764HP. Ground batchd6370d00ed67483bb3dc8af83ae056e6 completed threeW800 in3428ms locally, remaining full health.

Combined setup703bda736ca14290b8fc846afe1ec9b7 completed W800,W600, jump/deploy with366ms release gap, D600,W800 and oneE. Setup2130ms, bomb cycle3354ms, whole request18011ms. Wings were positively observed, but the first bomb missed: five full enemy bars remained. FinalHP2648.

Already-airborne followupb174fe87c9f0408f9dd0a43f027759b3 used oneW800 and oneE, local2525ms, whole request11220ms. Phase250037023 shows three369 damage numbers and a reduced enemy bar. The next phase250037070 shows the ground group absent/dissolving, with elevated archers remaining. No numeric kill count or encounter completion is claimed. The subsequent e90f69a6fa1b40369b27d26a388281f4 detected landing and rejected all movement/bomb inputs at2601HP. Do not redeploy wings unless a fresh grounded wind-current launch is reviewed.

The same terminal-to-terminal method measured148524ms from tutorial exit to first-bomb terminal, versus281217ms to the prior failed launch. Five requests consumed56689ms versus nine/80286ms. Inter-request verified pause gaps were75895ms versus180040ms; measured Inventory-close-to-pause-key spans were27113ms versus36863ms. These overlapping spans approximate exposure and are not exclusive productive time. The endpoints differ: this attempt includes a bomb; the previous attempt failed before firing.

## Solo Traveler healing

The verified domain food modal has exactly one centered Lv.17 Traveler card. The skewer handler now accepts that precise layout while retaining original-account, food-title, freshness, quantity-one and same-frame checks. Additional/wrong/shifted cards and stale or non-one quantity proof remain rejected. Kaeya's existing path remains supported.

Live receipt3336652912754166ba48f04fdf401309 consumed exactly one Delicious Chicken-Mushroom Skewer; stock2 became1 at3726. Subsequent world3730/3731 showed2720/2764HP versus2601 before healing, with an Electro effect visible. Full post-heal HP was not captured, so only the observed net119HP increase is claimed. No premium, resin, difficulty change or restart occurred.

Validation:1991 canonical JavaScript tests passed,0failed,43634.6832ms; nine Python return checks passed, including the recorded bend fixture. Solo-modal focused tests passed6/6. The first full-suite attempt loaded the old helper via an inherited harness; after correcting candidate isolation the complete suite passed. No native code changed or native build was required. Runtime changes were hotloaded from the tested canonical candidate, preserving unrelated source work.

Current continuation: Inventory3732/controller3733, same RDP7/sessionmvcuzen8-drrh7eb3gqe. Continue this domain from fresh observation; do not reset the cleared ground progress. Act III remains untouched.
