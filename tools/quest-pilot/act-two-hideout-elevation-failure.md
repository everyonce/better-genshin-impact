# Hideout return elevation failure, 2026-10-18

This return did not reconnect to the known entrance approach. No sixth domain entry occurred. Kaeya stayed at4015/4015; five purchased skewers remain unused. No EXP, resin, falls, deaths or runtime restart occurred during this return.

The lower-road helper diverged at4571 (140m rather than133–139m). Subsequent reviewed corrections reached the low shelf, but the upper path differed from the successful entrance geometry. At4724 the character stood in a dead-end grass alcove, Higher30m. Retire that alcove approach.

After backing out, a different wall was mounted at4793 Higher31m. Probe4799 exposed sufficient stamina. Two four-hold climbs reached a narrow rock shelf at4821 Higher29m. **This was not the known upper grass landing.** Instead of following the prior successful ground corridor, another wall was mounted at4845 Higher28m. A probe and four holds reached4866 at27m without Higher; another four holds reached4874 **Lower27m**. This is the exact elevation overshoot transition and a failed route condition, not entrance progress. Further ascent must stop when the hideout marker reads Lower.

The four-hold sideways batch e2a4559f reached4896 Lower26m. A tested lateral-progress guard subsequently admitted three D600 holds in c7d92ee7 before the unchanged stamina floor stopped the fourth;4921 readLower27m. Thus sideways continuation also failed to converge. No safe drop landing was established. Supported map inspection b9d8f579 selected the exact Springvale waypoint; teleport8e8a0836 recovered to4935 at168m, full4015, Inventory4936/controller4937.

The prior successful route crested onto broad upper grass (2334/2773/1660), then followed a grounded slope toward14–20m and the visible golden entrance marker. A narrow shelf in front of a second high wall does not match that landing. Fogged minimap coordinates and similar distance values cannot establish route identity.

Code: field-progress.js adds a reviewed sideways-only continuation for a completed same-direction batch with decreased exact hideout distance, unchanged endpoint on stationary reobservation, and <=8degree camera difference. It cannot authorize upward or reversed movement. Existing field stamina, health, focus, session and pause checks remain unchanged. This lateral branch was exercised live in c7d92ee7; it did not solve the route. The new Lower-ascent stop is regression-tested, not live-triggered.

The first broad test invocation included unrelated untracked WIP tests and reported11failures. Canonical tracked tests plus the new focused file are the publication suite. No unrelated WIP was changed or staged.
