# Hideout airborne control evidence

Act II remains locked at AR9,955/1300. No Outrider reward or Original Resin has been collected.

The lower broken-floor current launch is visually verified: two60ms Space presses with a measured389-390ms release gap deployed wings and gained altitude. The airborne HUD moves Space to x1680 and enables E. Exact account digits, session, freshness, special-domain state and modal guards remain mandatory. Unknown controls never authorize a bomb.

## Live launch and first bomb

Request e47b325a23ae40a3b05e000fe5518d72 performed jump, deploy, D600,W800, oneE60, immediate result capture and Inventory pause locally. The flight/bomb sequence measured3269ms; the whole guarded request took14503ms. Fast samples retained2659/2764HP throughout that sequence. Before/after images250024935/250024936 show wings, a visible explosive projectile, and E cooldown. Five visible enemy bars remain full: the shot landed short, so no hit, kill or quest progress is claimed. The compact local evidence is artifacts/act-two-hideout-first-bomb-evidence.json. The successful launch baseline remains available for rollback.

The exact two-page tutorial handoff is now live-validated by491b082261e544b2b294e2674606c821:22 dialogue presses,2 exact tutorial clicks,47203ms total, field2434 and verified Inventory2437 at full2764HP. It never uses generic Space for either tutorial.

## Already-airborne cycle

The flightBomb mode reuses the same local directional movement, fresh flight/health samples, oneE, immediate result capture, guaranteed release and pause. It never jumps or redeploys wings. Plans require separately reviewed visible wings and targets, zero camera offsets, at most3directional holds, each at most800ms, and at most1600ms total. The input deadline remains3500ms, result budget5000ms, and minimum health2488. No threshold or game difficulty was changed.

Live request2074660b66194af4a9ea34b292b456eb used twoW800 from verified airborne2501. After the second hold, the fresh sample showed jump controls and the saved image250025042 showed landing beside the archers. The guard sent noE and verified Inventory pause2508. Health was2578 throughout its fast samples. This validates landing rejection, not a successful already-airborne bomb. A later boundedS800 retreat ended2519 at2496HP; Inventory2520 is held. No healing food is available, no kill or cleared encounter is being abandoned, and the90percent threshold is unchanged.

The landing failure exposed reporting problems: the partial action result omitted stopped status, completed movement count and failure timing. The candidate now reports stopped, counts already-executed movements, and records elapsed time/reason on rejection. Those reporting fixes are regression-tested, not yet live-exercised. All1979 canonical tests pass in41029.5231ms. No native build or application restart was needed.

Input-free inspection accepts an older same-session special-domain witness only with zero movement/camera/action offsets; every actual input still requires fresh local state. Terrain return evidence is in act-two-hideout-entrance-route.md. Next: recover health through the supported Statue route, then compare one changed positioning variable against this preserved miss baseline. Do not repeat launch while airborne, equate a fired bomb with a hit, or replay old terrain timings blindly.

## Approach exposure repair

The third attempt fired no bomb. The recorded post-deployment sample reported flying=true and jumping=false at2473/2764HP; the unchanged2488 minimum invalidated the sample. The old report incorrectly called this "No flight" and omitted the two Space inputs. The candidate separates control detection from sample safety, reports the health rejection, and counts partial launch/setup inputs. The recorded failed samples replay successfully against the fix.

The measured tutorial-exit-to-launch-terminal interval was281217ms. Nine guarded requests consumed80286ms, with180040ms in verified pause gaps between them. Their measured Inventory-close-to-pause-key spans totaled36863ms; those spans approximate exposure, not exclusive productive time. Total damage through supported exit was373HP, with no death, bomb, hit, or cleared encounter lost. The profile is preserved locally in artifacts/act-two-hideout-third-attempt-profile.json.

The reviewed final setup starts on continuous lower-chamber floor at the position represented by2905, facing the broken-tile current. Its two forward holds are W800 then W600, with intermediate2911 and placement2917. A new optional groundSetup executes those short holds, fresh health/control checks, the unchanged launch, and the preserved D600,W800,E60 baseline within one local request. It requires a named reviewed ground landmark, zero camera offset, at most3forward holds of800ms each, no flight/climb ambiguity, and the same2488 minimum. Each setup/attack phase retains its3500ms input deadline. Every rejection releases keys and pauses. Original launch and already-airborne modes remain available without setup.

All1986 canonical tests pass in48345.4759ms. The combined setup is tested but NOT live-validated; simulated savings are not claimed as measured gameplay gains. Statue healing3419e8d7cebd464781501fee58666262 restored2764HP at2980. Before retry, verify the reviewed floor/current geometry afresh. After a successful baseline bomb, use only oneW800 in the already-airborne follow-up; do not redeploy while airborne.

## Subsequent live validation, 2026-10-18 04:42 UTC

The combined setup has now succeeded in-game (703bda736ca14290b8fc846afe1ec9b7). The prescribed oneW800 airborne follow-up (b174fe87c9f0408f9dd0a43f027759b3) produced three369 damage numbers and a reduced enemy bar. The next attempt correctly refused all inputs after detecting landing. Solo Traveler healing was subsequently validated with exactly one skewer, stock2→1 and observedHP2601→2720. Current measurements, limitations and continuation are in [the validated return and bomb report](act-two-hideout-validated-return-and-bomb.md). This supersedes the earlier untested status; the domain and Act II are not complete.
