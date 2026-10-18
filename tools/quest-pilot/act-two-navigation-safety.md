# Navigation safety and fog localization, 2026-10-18

Act II remains locked at AR9,955/1300; no EXP or resin reward was earned in this investigation. Current supporting objective is the unopened Windwail Highland Statue of The Seven (tp.json id3), not a retired shield, chest or waypoint59 target.

## Zero-motion hazard regression

`navigation-hazard-noop.fixture.json` preserves the actual stationary aftermath request08f58878165240e08a35a632afc626af: arrived,0movement,171HP lost. It was unsafe observation, never a retreat. The client and live adapter now bind a one-use navigation safety file to the exact request/route/session/frame and a recent ground witness before Escape. A hazard-side route entirely inside3units is refused before unpause. The recorded8759GPS outlier is also refused. Missing coordinates do not qualify.

An optional route `escape` object defines a reviewed stationary hazard location, minimumMovement>=4 and minimumSeparationGain>=6. The planned endpoint must exceed both bounds plus arrival tolerance. Final arrival requires actual movement and increased distance from that location. This proves geographic separation, not clearance from a moving enemy. No live escape with this new mechanism has run; the actual adapter's pre-unpause rejection is exercised in regression tests.

## Localization diagnosis and bounded recovery

Normal Springvale teleport returned an impossible global GPS x8759; anchored navigation095a70af refused before movement. The short regional visual fallback was explicitly allowed only with a named start/end landmark, fresh safe ground, finite movement and independently checked arrival. The cart/sign-to-lamp segment stopped short of its end landmark. It was not reported as arrival; recoveryefe0057b teleported back to the known Springvale north waypoint, fullHP4015. No further unmeasured heading advance is permitted.

Stationary probe2ae2a3da seeded the native matcher at tp5, then tried SIFT once: null after6014ms,0movement, fullHP, verified Inventory. It did not establish localization. Two stable/plausible API positions would still be candidate evidence only, without automatic navigation authority.

`audit-springvale-localization.ps1` replays actual OpenCvSharp SIFT on saved captures and installed training assets. The minimap crop matches the source's62,19,212,212 at1920x1080. The correct3x3Springvale feature region contains24221points. At known teleport7277:15ratio matches,12inliers, position(-867.3535,1992.4053), about0.48units from the native anchor. At7333:8matches/6inliers and unstable extrapolation across scale. Farther into fog7357:only1–4matches across the tested masks/scales, below the unchanged7match minimum. Coverage and crop exist; insufficient visible terrain features in fog is supported by these examples. Exact live-query differences remain a limitation. No confidence threshold was lowered.

A full-map fallback uses the existing256scale training asset and quarter-size screenshots. Saved positive controls: Windrise7263,51inliers, about1.51units from the Statue position; Springvale7292,41inliers, about0.17units from the exact teleport anchor. Fresh recovered-anchor7377 independently gives(-867.3789,1992.9307),40/40inliers across0.51/0.84of the query width/height, about0.16units from the anchor. Native matching took102–115ms, asset loading about100ms, excluding shell startup/compilation. Source7363 measures the road endpoint(-824.83594,1978.8994),36inliers; the previously sampled position7323 was(-857.7246,1993.8516), about36.1units apart. This is measured ground travel, not EXP or a proved lamp arrival.

`full_map_position.py` is read-only and verifies the exact screenshot hash, same-session full-map/account evidence, centered player marker, >=20inliers, >=70%inlier ratio, spatial coverage and starter-region plausibility. It reports the position of that capture and explicitly grants no navigation, elevation, hazard-clearance or current-state authority. Consumers must establish no intervening movement and independently verify safe route/landmarks. Four recorded Python tests cover the real fresh anchor, marker, stale/account/hash failures and sparse/clustered/outlier matches.

One offline diagnostic initially flattened a PowerShell trial argument into an invalid scale and failed an allocation before producing evidence. A fixed scale whitelist and structured trial objects now prevent that mistake. This did not rebuild or restart BetterGI or send game input. Analysis results are not represented as live movement validation.

## Current continuation

Sessionmvcuzen8-drrh7eb3gqe/RDP7, child11256. Recovered Springvale north anchor, fullKaeya4015, Inventory7383/controller7384 idle. Fresh map7377 is the full-map anchor control. Keep coordinate navigation blocked while minimap GPS is unresolved. Continue toward the same Statue only using a fresh measured position plus a named, bounded visible ground segment and verified arrival. No new difficulty change, premium currency, Fragile Resin, food or Original Resin was spent. See target-switch-review and compact accounting reports; there is no measured objective-efficiency gain.
