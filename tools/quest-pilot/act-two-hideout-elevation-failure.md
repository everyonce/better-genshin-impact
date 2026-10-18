# Hideout return elevation failure, 2026-10-18

This return did not reconnect to the known entrance approach. No sixth domain entry occurred. Kaeya stayed at4015/4015; five purchased skewers remain unused. No EXP, resin, falls, deaths or runtime restart occurred during this return.

The lower-road helper diverged at4571 (140m rather than133–139m). Subsequent reviewed corrections reached the low shelf, but the upper path differed from the successful entrance geometry. At4724 the character stood in a dead-end grass alcove, Higher30m. Retire that alcove approach.

After backing out, a different wall was mounted at4793 Higher31m. Probe4799 exposed sufficient stamina. Two four-hold climbs reached a narrow rock shelf at4821 Higher29m. **This was not the known upper grass landing.** Instead of following the prior successful ground corridor, another wall was mounted at4845 Higher28m. A probe and four holds reached4866 at27m without Higher; another four holds reached4874 **Lower27m**. This is the exact elevation overshoot transition and a failed route condition, not entrance progress. Further ascent must stop when the hideout marker reads Lower.

The four-hold sideways batch e2a4559f reached4896 Lower26m. A tested lateral-progress guard subsequently admitted three D600 holds in c7d92ee7 before the unchanged stamina floor stopped the fourth;4921 readLower27m. Thus sideways continuation also failed to converge. No safe drop landing was established. Supported map inspection b9d8f579 selected the exact Springvale waypoint; teleport8e8a0836 recovered to4935 at168m, full4015, Inventory4936/controller4937.

The prior successful route crested onto broad upper grass (2334/2773/1660), then followed a grounded slope toward14–20m and the visible golden entrance marker. A narrow shelf in front of a second high wall does not match that landing. Fogged minimap coordinates and similar distance values cannot establish route identity.

Code: field-progress.js adds a reviewed sideways-only continuation for a completed same-direction batch with decreased exact hideout distance, unchanged endpoint on stationary reobservation, and <=8degree camera difference. It cannot authorize upward or reversed movement. Existing field stamina, health, focus, session and pause checks remain unchanged. This lateral branch was exercised live in c7d92ee7; it did not solve the route. The new Lower-ascent stop is regression-tested, not live-triggered.

The first broad test invocation included unrelated untracked WIP tests and reported11failures. Canonical tracked tests plus the new focused file are the publication suite. No unrelated WIP was changed or staged.

## Lower-wall seam retired, 2026-10-18 08:10 UTC

The next return reached the low shelf but diverged before the climb. The successful fifth route hopped at heading37 and approached at96. The new hop5084 used approximately71 and approached at130. It contacted a seam at5102 Higher30m. A single probe revealed stamina; three subsequent W600 holds5109->5116 produced no useful ascent. The repeated30m state is a failed route anchor, not progress. Two short releases onto freshly visible lower grass preserved full4015HP. Ground recovery backed out to35m. Reorientation to99 exposed a broad wall face5178 Higher34m, but oneW600 failed to mount5183; this approach is also retired. No sixth domain entry occurred.

Reference checkpoint6 identifies the low shelf, while checkpoint7 is the final entrance, not the upper landing. No image of the successful upper landing3548 remains. Its recorded grounded state and headings cannot prove a visual match. Future return work must validate the actual shelf position and turn, not just restore a heading or distance. Compact failure regressions and exact observations are in artifacts/act-two-hideout-seam-failure-evidence.json and artifacts/hideout-seam-failure.

Outrider navigation was canceled with e8eafadb; Springvale teleport683577e8 recovered fullKaeya5216. Current alternative is a bounded Ley Line assessment for the remaining345EXP and unused Original Resin. The former party-OCR blocker has an actual saved-image regression that recovers17767/17768; the live runtime includes that repair. It still needs fresh combat validation. This interval earned no AdventureEXP and spent no food or resin. No falls, deaths, app/pilot/RDP restarts or irreversible cleanup occurred.

## Narrow saved-image diagnosis, 08:18 UTC

Parent requested a hold at Springvale before another approach. Controller5220 remains idle, Inventory5219 verified. No gameplay input occurred during this diagnosis.

- Available successful image: `Test/ActOnePilot/fixtures/hideout-return/checkpoint-6.jpg`, frame3486, shelf entry at37degrees. `artifacts/climb-contact-review.jpg` preserves only bottom-left crops of successful wall contact3509/3516. Neither is the upper landing.
- Missing successful landing: no retained PNG/JPG was found for1660,2334,2773,3548. Frame3548 is grounded31m in the durable ledger; that is not image evidence. Checkpoint7 is final entrance3617, not the upper landing.
- Available failures: private compact5116 shows the stalled seam,4821 shows the narrow upper shelf. Earlier alcove4724 image has expired. These limitations prevent claiming an exact image match to that older alcove.
- Earliest clear local divergence: before hopping, failed5079 was37m at71degrees versus successful3486 at39m and37degrees. The failed view is oblique to the shelf and its wall junction; matching approximate distance did not justify continuing. The subsequent manual approach130 rather than96 compounded that mismatch.

`compare-route-anchor.ps1` performs offline terrain ORB matching and a homography, excluding HUD and the character. It reports alignment and heading disagreement, always `gameplayAuthorized:false`. It never captures or sends input and is not hotloaded. Eight recorded/synthetic regression cases passed in8203ms: exposure/JPEG variation of the real shelf reference, mismatched heading, unrelated entrance, blank terrain, missing landing reference, actual failed pre-hop5079, actual stalled seam5116, and narrow shelf4821. Actual5079 yielded one descriptor match and zero geometric inliers. These are negative-anchor checks; there is no positive cross-return or live route validation. Detailed results: `artifacts/act-two-route-anchor-regression-results.json`.

The hideout approach remains retired. Repeating it requires a verified shelf entry and a new positively verified upper landing, which must be retained before claiming reconnection. A separate Ley Line attempt would differ because it bypasses this climb and uses the already-recorded party-OCR repair; its combat/reward outcome remains unverified.
