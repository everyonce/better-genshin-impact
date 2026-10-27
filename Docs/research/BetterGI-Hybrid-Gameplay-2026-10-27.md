# Hybrid gameplay qualification — October 27, 2026

The local R57 prototype completed **60 consecutive courtyard legs in 259.80 seconds** through minimized BetterGI RDP, using one resident Open P2P GPU model and one input owner. All 2,272 accepted actions have matching applied software receipts. No stall recovery, model reload, teleport, manual repositioning, or controller reconnect occurred during that run.

This demonstrates sustained navigation on the fixed upper courtyard segment. It does not establish general quest completion, combat competence, or successful escape from a physical obstruction.

## What changed

BetterGI publishes optional position, map layer, camera yaw and native camera corrections from the exact full-resolution image used to produce each model observation. Recognition uses the existing local map matcher and minimap processor before RGB192 downsampling. The default stream remains unchanged until the authenticated client requests navigation guidance.

The hybrid client retains route-compatible P2P walking actions. It immediately substitutes native heading or forward corrections for idle or off-route proposals, while preserving the original proposal and labeling the selected controller. Rejected or overridden model proposals are not committed to model action history. Both controllers use the existing stream owner, world gate and 150 ms first-input freshness deadline.

Every endpoint requires an acknowledged release followed by three distinct, stable source poses. The planner measures actual displacement and receipt-confirmed movement. A measured obstruction triggers bounded retreat and side-step attempts, with a two-attempt limit per leg. Corridor departure, failed endpoint verification, or a changed capture generation ends the run. The existing optional climb-drop recovery can share this owner and clears stale hybrid progress during recovery.

Ordinary recordings now omit the repeated rolling execution-context snapshot from each frame header. They retain source clocks, native poses, proposals and terminal receipts. Explicit `--execution-context record` retains the full diagnostic context. Recording growth fell from approximately 66 MB to 7 MB per 30-second segment in these trials.

## Measured runs

Evidence root: `artifacts/live/2026-10-27-hybrid`.

| Run | Result | Verified legs | Verified route time | Accepted actions | Model evaluation median / p95 | Peak GPU |
|---|---|---:|---:|---:|---:|---:|
| `hybrid-01` | Reached the far endpoint; client release-timestamp validation failed | 0 | Not qualified | 26 | 26.21 / 29.05 ms | 63°C |
| `hybrid-02` | Completed and audited | 4 | 16.69 s | 146 | 29.25 / 33.57 ms | 61°C |
| `hybrid-sustained-03` | Deliberately stopped at an endpoint to compact recording metadata | 23 | Partial planned run | 919 | 30.27 / 34.44 ms | 63°C |
| `hybrid-sustained-04` | Completed and audited | 60 | 259.80 s | 2,272 | 29.87 / 33.35 ms | 64°C |
| `hybrid-plinth-07` | Rejoined from a small plinth-edge offset, then completed and audited | 8 | 37.81 s | 332 | 29.67 / 33.30 ms | 62°C |

The first trial exposed a client integration error: the release acknowledgement uses `serverNowMs`; `releasedAtMs` belongs to saved recovery events. The client and composed fixture were corrected before subsequent runs. Its failed result is preserved.

The sustained run processed 5,597 recorded frames, including 5,525 valid native poses. Native recognition median/p95 was 11.35/14.46 ms. Source freshness to first software input had a median of 80.46 ms and maximum of 143.90 ms. Five stale proposals were withheld. The model evaluated 2,277 images; 473 accepted actions retained P2P attribution, 1,052 were native heading corrections and 747 were native replacements for idle/off-route proposals.

One model load took 18.30 seconds before gameplay. The run used nine recording segments with no dropped frames, observations or events, and retained 69,377,462 bytes. Segment rotation did not reload the model or replace the input owner. Endpoint confirmation includes short intentional release/settling intervals; the result does not imply uninterrupted forward key holds.

The plinth setup sent only three 100 ms left sidesteps through the same authenticated RDP bridge. It remained within the endpoint neighborhood and produced normal motion hints. The subsequent eight-leg run enabled climb recovery but did not need it. **Physical obstacle escape and climb-drop effectiveness remain unverified by these runs.** The bounded stall trigger, retreat/side-step sequence, exhaustion, stale-frame rejection and recovery ownership are covered by inert tests.

## Runtime and reproduction

- Child: `artifacts/release-r57/BetterGI-English-win-x64/BetterGI.exe`, RDP session 3.
- Tested DLL SHA256: `0c849ea73fc52ec236bb741044bc45919b9578856607379d8e588681bad2b1ff`.
- Primary host remained R56; the child hot replacement preserved Genshin and the minimized RDP session.
- RTX 2080 SUPER; existing CUDA environment; no package installation or driver/power changes.
- Open P2P 150M, history 41, CUDA graph, fast start and prewarm, native Hamming RGB192, 20 Hz polling and 10 Hz decision target, 100 ms holds, 150 ms freshness limit.
- Text goal: “Walk along the open street. Stay on the ground and turn away from walls.”
- A separate run-bound monitor requested stop at 78°C or its deadline. Neither successful qualification needed a thermal stop.

Run `stream_client.py` **inside the existing RDP session through `rdp_control.py exec`**, using the established source/checkpoint/goal paths and:

```text
--resident --rdp-session-id 3 --model open-p2p --history 41
--cuda-graph --p2p-fast-start --p2p-prewarm --goal-intent ground-navigation
--hybrid-navigation --hybrid-legs 60
--observation-profile p2p-native-hamming-192-v1
--fps 20 --decision-hz 10 --action-hold-ms 100 --max-observation-age-ms 150
--seconds 300 --segment-seconds 30 --enable-input --preview --record-max-mib 128
```

Use fresh output/recording paths for every run. `--navigation-guidance --model observe` performs the input-disabled pose check. `--navigation-climb-recovery` explicitly enables the existing bounded X-key drop helper; it does not expand the model's WASD allowlist.

Audit the retained completed run from the repository root:

```powershell
python -B tools/bettergi-agent/audit_hybrid_run.py `
  --run artifacts/live/2026-10-27-hybrid/hybrid-sustained-04.json `
  --recordings artifacts/live/2026-10-27-hybrid/hybrid-sustained-04-recording `
  --minimum-legs 60 `
  --output artifacts/live/2026-10-27-hybrid/hybrid-sustained-04-audit.json
```

The audit joins all 180 endpoint samples to their original recorded poses and source clocks, checks the release barriers and alternating endpoints, verifies one lease/model load, and joins accepted actions to terminal software receipts. It does not attest physical input delivery, render latency, groundedness, or expert training eligibility. `hybrid-sustained-04-results.png` plots progress and latency; video playback uses synthetic frame timestamps, so use the recorded source clocks for elapsed-time analysis.

## Validation and remaining work

The required Debug solution build and optimized Release publish passed. The Agent C# cohort passed 580 tests under the normal Windows user token; the initial restricted-token failures were limited to the test pipe integrity label and temporary-file rename. The selected Python cohort passed 123 tests, and the build hash helper passed six. Live input-disabled positioning, R57 child replacement, four-leg and 60-leg trials, offset rejoining, recording rotation and terminal cleanup were verified.

R1, R55 and R56 remain pinned. R57 is registered with the release-retention policy; `build-runtime.ps1` now invokes that policy for managed repository artifacts before and after publishing.

Next qualification should deliberately reproduce a low-risk physical obstruction and verify escape/rejoining, then extend to longer native routes with independently checked elevation transitions. Quest interaction and combat need separate success criteria. BetterGI currently supplies most route control; the pretrained model has not independently demonstrated reliable goal completion.
