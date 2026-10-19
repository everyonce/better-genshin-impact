# Windmill riddle route research (2026-10-19)

Scope: read-only route and controller selection. No gameplay input, capture, process restart, or quest progress in this research pass. Last verified state remains `artifacts/act-two-latest-checkpoint.json` (session `mvf7ifnp-30yiczwdy7v`, Inventory frame 16, controller idle; Kaeya grounded at approximately `(-842.43, 2210.26)`, full HP, `Higher 27m`; AR9 955/1300, Act II locked).

## Selected route

Use the nearby **blue-roofed house** as the initial elevation, then jump/glide to the windmill's wooden balcony. The firsthand Gamers Heroes walkthrough explicitly describes this approach and the subsequent wooden platforms for stamina recovery: https://www.gamersheroes.com/game-guides/where-to-find-secret-pirate-treasure-in-genshin-impact/ . The chest is near the windmill top. This is public geometry, not proof of the current account's position or of a successful current-session route.

A separate BetterGI script-library path (`artifacts/act-two-windmill-house-glide-reference.json`, authored by Tool_tingsu, BGI 0.45.0) agrees on the geometry: house approach near `(-820.02,2222.8)`, roof climb near `(-817.59,2224.26)`, glide via `(-833.11,2216.95)` to the windmill balcony near `(-845.77,2217.93)`, and walk to `(-846.75,2217.17)`. Treat these as approximate navigation anchors; the library route is a collection script, not a validated quest path. Do **not** replay its later blind `keydown(W)`/repeated-jump action.

The account previously reached the lower wooden balcony around `(-846.9512,2217.3613)` with full HP (`artifacts/act-two-upper-windmill-evidence.json`, frame 20162), so that surface is a plausible landing target. Its subsequent upper-wall ascent stalled at `Higher 4m` against an overhang/diagonal support. A separate W150 ladder-contact request from that balcony was denied before input by automatic review because the position overlapped a retired fall/crossing area. That denial remains a constraint; this research does not justify retrying the same crossing.

## Controller assessment

The stock `PathExecutor.MoveTo` climb mode is **not a conservative final-ascent controller**. It holds forward continuously, suppresses its horizontal stuck detector in climb mode, and only has a 240-second waypoint timeout (`BetterGenshinImpact/GameTask/AutoPathing/PathExecutor.cs`, around lines 811–1103). The enclosing `finally` releases W, but a prolonged wall hold can exhaust stamina well before timeout. `SkillBoostHelper.DetectStamina` (around lines 1338–1404) substitutes 0 or 240 from history when no valid pixels are found; that 240 cannot establish current climbing reserve. Current-account W642 and W600+W200 attachment/ascent trials returned zero yellow pixels in climbing frames, so no fresh reserve estimate exists.

For roof and windmill ascent, use short, individually bounded inputs only after a fresh field/pose/height observation. Require an explicit stable roof or wooden-platform landing and visual proof of rest before another climbing phase. Limit each hold to a small fraction of a full stamina bar and stop on unchanged height, uncertain attachment, absent reserve evidence, lost focus, or unverified landing. Never substitute the stock 240-second climb waypoint or a full-stamina blind hold. Existing `act-two-lower-climb.js` needs a positive same-frame stamina arc at its historical lower-wall starting pose and therefore is inapplicable at the current wall.

## Smallest safe validation before traversal

While Inventory remains open and inputs are stopped, review the saved windmill balcony frame 20162 and the guide's house-location image, then bind the house approach anchors to a current **ground-level** map/position witness. The first resumed action should be a separately guarded, bounded ground waypoint toward `(-820.02,2222.8)` that stops before any roof climb or jump and verifies safe pavement, full health, and objective. Only then inspect the house wall/roof and design one short attachment test. This route has not been live-validated in the current session; no claim of gameplay resumption or quest progress follows from the research.
