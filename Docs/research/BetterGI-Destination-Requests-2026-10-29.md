# Destination-directed walking on SIREN

## What a request controls

The requested photograph determines the next street BetterGI walks. The three surveyed stations are the stair front, sidewalk junction and west lamp. Only the stairs–junction and junction–lamp connections have been surveyed in both directions. The controller computes the next hop from the last verified station and the active destination. A visit to the junction en route to the lamp counts as a leg. The lamp request owns both legs and needs a fresh photograph at the lamp to complete.

Each new lease declares its starting station. Three stable native pose samples in the original capture establish that the character is there before movement begins. Open P2P evaluates live 192 × 192 game images on the GPU. BetterGI supplies the route bearing, corrects the heading and selects a forward movement when the model proposal is idle or incompatible with that bearing. A destination change resets action history and keeps the model loaded. The final destination ends the lease at that location.

## How the route was checked

The subprocess ran on SIREN inside the existing minimized BetterGI RDP host. The test used the qualified G4 landmark classifier, the steering checkpoint in observation mode and the existing 78 °C cutoff. The original ground-walking goal embedding, ten decisions per second and 150 ms image-to-first-software-dispatch deadline were shared by both controllers. All run directories are retained under `artifacts/live/2026-10-29-destination`.

The verifier independently expands the named requests on the surveyed graph. For each actual leg, it joins a native forward-input receipt to a later in-corridor pose showing progress in the requested direction. At each arrival it checks the release acknowledgement and three stable poses against the original capture. The exact source image at a requested endpoint must also pass the frozen classifier and match the saved PNG pixels. The request handoff uses the native dispatch clock and is cross-checked against Windows Graphics Capture timestamps. Reported navigation time runs from the confirmed start to the final confirmed arrival, excluding model loading and offline verification.

## Matched live comparison

Both controllers began at the stairs and received the same three photo requests in the same order. The qualified destination run captured all three and ended at the requested lamp. When the second request asked for the stairs, the character reversed at the junction. When the third asked for the lamp, the character crossed that same junction in transit.

| Measured inside the game session | Fixed circuit | Destination route |
| --- | ---: | ---: |
| Verified legs per request | 4, 4, 4 | 1, 1, 2 |
| Verified navigation time | 41.90 s | 13.10 s |
| Applied actions | 358 | 110 |
| Verified original photos | 3 | 3 |
| Median GPU policy evaluation | 30.49 ms | 29.85 ms |
| Maximum image age at first software dispatch | 134.94 ms | 126.41 ms |
| Peak GPU temperature | 64 °C | 60 °C |

The destination route finished 28.81 seconds sooner in this pair. The GPU evaluated a proposal for every recorded movement decision. Of the 110 applied actions, 23 used Open P2P's proposed movement and 87 used BetterGI's navigation correction. The two request handoffs took 603.08 and 702.27 ms, including the verified station release. The model loaded once per lease, taking 20.19 seconds before the fixed run and 18.42 seconds before the directed run. Evidence is in `control/warm-20261029T161054Z-cde5d8b2bdc2` and `directed-repeat/warm-20261029T161625Z-64a96d6d0b4a`.

## Continuation and repeat visits

The continuation began at the lamp where the previous goal had ended. It walked lamp → junction → lamp → junction → stairs in 18.39 seconds, collecting three independently verified photos. For the first request, the frozen plan required two matching images at the junction. Original frame 149 matched. With the same input release in force, the controller obtained three fresh stable poses and a second matching image at frame 158, 285.27 ms later. The full handoff took 905.32 ms. The next handoff took 612.26 ms. This trial explicitly exercised confirmation. The earlier naturally occurring classification miss remains a separate failed trial. Evidence is in `stationary-confirmation/warm-20261029T162144Z-e304cd46dc7b`.

Another lease began at the stairs and requested junction, stairs, lamp and a new stairs photo. It verified six legs in 20.03 seconds. The two stair photos came from frames 193 and 570, with distinct source pixel hashes. The three handoffs ranged from 599.74 to 712.98 ms. Evidence is in `revisit/warm-20261029T162235Z-0f71cab1aa36`.

A final four-request lease visited the lamp, stairs, lamp and junction. It walked seven legs in 27.59 seconds, with 240 applied actions and independent lamp photos at frames 225 and 678. Its oldest image at first software dispatch was 119.46 ms. This lease ended at the junction. Evidence is in `longer/warm-20261029T162332Z-77db1e144e22`.

Across four fully qualified destination leases, 14 photo requests accounted for 21 verified legs, 678 applied actions and 79.11 seconds of navigation. The longest interval between any consecutive software dispatches within those leases was 905.32 ms, including the requested second view. The maximum image age at first dispatch was 128.56 ms and the GPU peaked at 64 °C. Each lease loaded the GPU model once. These measurements cover stationary photo goals on the surveyed street. The [earlier six-minute test](BetterGI-Warm-Requests-2026-10-29.md#sustained-run) measured continuous play on a fixed circuit.

## Retained refusals

The first directed trial recorded stairs → junction → stairs → junction → lamp. It saved all three requested photos, but the steering verifier attempted to reconstruct each target from the fixed four-leg circuit. At the junction it expected the west lamp when the active request called for the stairs. Replaying the original frames and weights with the corrected verifier reproduced all 118 shadow predictions. The original refusal remains in `directed/warm-20261029T161213Z-ab4951a3e7b6`.

The first lamp-start trial reached all three destinations and returned to the stairs. Its opening journal entry recorded a source mismatch because the collector expected every lease to begin at the stairs. The verifier correctly rejected that journal. The collector now binds the first observation to the plan's explicit start. The original refusal remains in `continuation/warm-20261029T161504Z-f83905c5ec99`.

The next lamp-start trial passed admission and collected the junction photo. On its return to the lamp, the character stood at (−859.10, 2263.75) facing 332.5°. G4 classified frame 312 as the junction and the controller stopped. In a separate input-disabled lease the native position and heading stayed fixed. The frozen classifier recognized the lamp in all 56 recorded views over 4.625 seconds. That observation prompted a same-release retry at the destination. The original disagreement and the subsequent observation are preserved in `continuation-repeat/warm-20261029T161710Z-694ee9a9bdad` and `lamp-hold-observation`.

## Stop drill and next milestone

The stop drill started at the previous lease's final junction. The first request reached the stairs and qualified its photo. Eight actions from the second request had been applied when the supervisor stopped the resident. The native release returned 185.71–187.27 ms after the addressed stop write, with no active action or tracked keys held. The verifier marked the second goal incomplete. The last recorded pose was within one world unit of the stair front. Final discovery found the original R56 host minimized in session 1, the original R57 child game-ready in session 3, no running task or stream, and a GPU temperature of 55 °C. Evidence is in `stop/warm-20261029T162434Z-e306a75560a4` and `final-discovery.json`.

The next milestone is to submit another bounded request batch at a verified destination without paying the 16–19 second model load between these leases. Qualify several minutes of changing requests on one resident and keep the same admission, photo, handoff, thermal and stop checks. Retain the first naturally occurring classification miss under the new retry policy and verify whether its replacement photo qualifies within the existing deadline. The [launcher instructions](../../tools/bettergi-agent/README.md#walk-to-requested-destinations) reproduce the three-goal comparison.
