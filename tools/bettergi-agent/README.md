# BetterGI local agent prototype

The installed CUDA environment is `D:\work\genshin-auto\artifacts\agent\envs\gamescaling\Scripts\python.exe`. The original system Python remains separate. No environment installer is supplied. Exact installed versions and model/source revisions are saved under `artifacts/agent` by setup and benchmark commands.

This prototype uses real downloaded checkpoints. It does not claim trained Genshin competence. Historical frame replay establishes inference speed and parsing; live gameplay, resource limits, task success, and adaptation require separate evaluation.

## Start the local stream

### Run the Mondstadt street patrol on SIREN

Start at the stair-front station with the existing BetterGI RDP child in the game world and the host minimized. Run this command from the repository root.

```powershell
& 'C:/Programs/Python/Python311/python.exe' -B tools/bettergi-agent/run_rdp_patrol.py `
    --circuits 24 --seconds 540 `
    --steering-shadow=artifacts/agent/steering/gen-01.json `
    --landmark-shadow=artifacts/agent/landmarks/gen-04.json
```

Each circuit visits the sidewalk junction, the west lamp, the junction again and the foot of the stairs. The launcher locates the authenticated child and starts one resident CUDA policy there. BetterGI steers from its native pose and accepts compatible Open P2P actions. The two optional observers score steering decisions and station images. The launcher checks the first GPU every two seconds, stops at 78 °C or on missing telemetry, and releases input when the target or deadline is reached. Each launch creates a separate evidence directory. See the [patrol measurements](../../Docs/research/BetterGI-Patrol-Learning-2026-10-29.md) and [training instructions](STEERING-HEAD.md).

### Compare a station observer on the original game images

For a bounded fixed patrol on SIREN, add `--retain-station-rgb` and a frozen `--landmark-shadow`. The recorder retains the exact native RGB from every settled start and endpoint, including wrong predictions. After a complete run, `station-rgb-audit.json` verifies the original bytes, native station, timestamps, RDP identity and prediction. With `run_patrol_series.py`, add `--owner-from` with a previous `warm-launcher.json` or `series.json` to require the same authenticated RDP pair. The original-image collector requires a fixed patrol without photo objectives.

`audit_landmark_episode.py` compares two frozen observers on the same lossless originals and separately on independently decoded video. `audit_landmark_panel.py` checks older whole leases. Experimental G6 and G7 are confined to observation. See the [stair recognition experiments](../../Docs/research/BetterGI-Stair-Recognition-2026-10-29.md) for their source evidence and limits.

For a sealed directed-photo lease, `report_stationary_photo_recovery.py --run <patrol.json> --checkpoint <checkpoint.json> --qualification <qualification.json>` checks whether a natural missed photo was recovered with no intervening input and a verified handoff within one second. It also reports planned confirmations and exhausted retries.

### Repeat a qualified photo task

For separate named photo requests on one model load, use the warm launcher on SIREN. Each request specifies its name, circuit count and target stations. This command captures a lamp photo first, then obtains fresh photos of the stairs and junction.

```powershell
& 'C:/Programs/Python/Python311/python.exe' -B tools/bettergi-agent/run_warm_photo_requests.py `
    --request lamp-survey 2 west-lamp `
    --request stairs-survey 2 stair-front sidewalk-junction `
    --seconds 165 --evidence-root artifacts/live/warm-photo `
    --steering-shadow=artifacts/agent/steering/gen-01.json `
    --landmark-shadow=artifacts/agent/landmarks/gen-04.json `
    --photo-qualification=artifacts/agent/landmarks/qualify-g4-fresh-10.json
```

Declare two to four requests ahead of time. Use different names and distinct sets of target stations, up to 32 circuits in total. At a verified return to the stairs, the previous request must have all its photos, an acknowledged release and terminal receipts for every accepted action. The next request takes fresh observations and starts a fresh policy history on the loaded walking model. Each request has a dedicated photo directory. Create the printed `STOP` file to cancel. To exercise the stop path, add `--stop-drill` to a separate two-request launch. The supervisor waits for an applied input from request two, creates the STOP file, and audits the addressed cancellation. The [warm handoff report](../../Docs/research/BetterGI-Warm-Requests-2026-10-29.md) gives the timing and evidence requirements.

### Walk to requested destinations

On SIREN, a destination request selects the next surveyed leg. This example starts at the stairs, walks to the junction, turns directly back to the stairs, then reaches the west lamp via the junction. BetterGI verifies the character's pose and releases input at each intermediate station. Only a fresh, independently verified photo at the requested destination finishes that request.

```powershell
& 'C:/Programs/Python/Python311/python.exe' -B tools/bettergi-agent/run_warm_photo_requests.py `
    --destination junction-check sidewalk-junction `
    --destination stairs-check stair-front `
    --destination lamp-check west-lamp `
    --seconds 110 --evidence-root artifacts/live/destination-requests `
    --steering-shadow=artifacts/agent/steering/gen-01.json `
    --landmark-shadow=artifacts/agent/landmarks/gen-04.json `
    --photo-qualification=artifacts/agent/landmarks/qualify-g4-fresh-10.json
```

Declare two to four named requests. To admit a new run at a previous destination, pass `--start-station west-lamp`, `sidewalk-junction`, or `stair-front` (the default). The controller requires three fresh, stable native pose samples at that station before moving. Each request must involve at least one surveyed leg. A later request may return to a station and must collect its own photo. The same `STOP` file and two-request `--stop-drill` apply.

When the image classifier disagrees at a requested destination, the controller holds the existing input release and checks up to three new sets of stable frames within 1.5 seconds. An unresolved photo ends the run. To exercise this hold deliberately, add `--confirm-first-arrival` to require two matching views at the first destination. The photo journal records whether a second view was requested or the classifier actually missed.

### Send more destinations to the loaded model

On SIREN, `run_destination_batches.py` keeps the GPU model and input lease active across batches. Supply only the first two to four goals at launch. This example authorizes two batches and four surveyed legs in total.

```powershell
& 'C:/Programs/Python/Python311/python.exe' -B tools/bettergi-agent/run_destination_batches.py launch `
    --manual --batches 2 --leg-limit 4 --seconds 110 --start-station stair-front `
    --destination initial-junction sidewalk-junction --destination initial-lamp west-lamp `
    --evidence-root artifacts/live/manual-destination-batches `
    --steering-shadow artifacts/agent/steering/gen-01.json `
    --landmark-shadow artifacts/agent/landmarks/gen-04.json `
    --photo-qualification artifacts/agent/landmarks/qualify-g4-fresh-10.json
```

In another PowerShell process, pass the exact evidence folder printed by that launch. The sender checks the live RDP pair and waits for an applied input from the preceding batch before publishing. Submit while the first batch is moving so the following goals are ready at its final destination.

```powershell
$runFolder = Read-Host 'Paste the evidence folder printed by the running launcher'
& 'C:/Programs/Python/Python311/python.exe' -B tools/bettergi-agent/run_destination_batches.py submit `
    --folder $runFolder --batch 2 --destination return-junction sidewalk-junction `
    --destination return-stairs stair-front --wait-seconds 55
```

The resident admits the new list only at the released, photographed endpoint of the previous list. Each request gets fresh policy history and its own photo directory. A missing successor expires after one second at that boundary with input released. The printed `STOP` file cancels the entire lease. The built-in qualification sender can issue four goals per batch during gameplay. Use `launch` without `--manual` or `--destination` and allow seven legs per batch. For a separate cancellation trial, `--stop-in-batch 2` stops after an applied input in the second batch.

### Run an open destination queue

Run these PowerShell commands from the repository root on SIREN with BetterGI RDP connected and minimized. For each new lease, supply a sealed `warm-launcher.json` or `series.json` from a completed or stop-verified run on the same live RDP pair. The launcher copies that manifest and checks both Windows sessions, process IDs and instance nonces before issuing input. After a process restart, obtain a fresh sealed owner manifest. Choose the station where the character is currently standing. BetterGI verifies it before moving.

```powershell
$queueOwner = (Resolve-Path (Read-Host 'Path to the sealed manifest for the current RDP pair')).Path
$queueStart = Read-Host 'Current station (stair-front, sidewalk-junction or west-lamp)'
$queueArgs = @(
    '--open-queue', '--owner-from', $queueOwner, '--start-station', $queueStart,
    '--batches', '12', '--leg-limit', '96', '--seconds', '400',
    '--evidence-root', 'artifacts/live/open-destination-queues',
    '--steering-shadow', 'artifacts/agent/steering/gen-01.json',
    '--landmark-shadow', 'artifacts/agent/landmarks/gen-04.json',
    '--photo-qualification', 'artifacts/agent/landmarks/qualify-g4-fresh-10.json'
)
& 'C:/Programs/Python/Python311/python.exe' -B tools/bettergi-agent/run_destination_batches.py launch @queueArgs --target-gameplay-seconds 210
```

The automatic sender chooses one batch after observing an applied action in its predecessor. It uses the requested and already photographed destinations to balance visits and approach directions across the three stations. The 210-second target starts at the first native input dispatch and is checked at a later positively witnessed dispatch. Once that span reaches the target, the sender requests a finish at the current batch's final photographed, released endpoint. Model loading is outside that span. The 12-batch and 96-leg caps can close the queue earlier (`capacity-closed`). The 400-second wall limit, recording budget and thermal watchdog still apply. The launcher records the verified closure reason in `warm-launcher.json`.

For manual control, run the setup above with the current owner and station, then use this launch line in place of the automatic one. The launcher prints the new evidence folder.

```powershell
& 'C:/Programs/Python/Python311/python.exe' -B tools/bettergi-agent/run_destination_batches.py launch @queueArgs --manual
```

In a second PowerShell at the repository root, run the following while the initial batch is walking. Slot 2 is the decision after batch 1. After any later walking batch, pass its ordinal plus one. Both `submit` and `finish` claim this same slot exclusively. The sender can wait for its predecessor's applied action.

```powershell
$runFolder = Read-Host 'Paste the exact evidence folder printed by the manual launch'
& 'C:/Programs/Python/Python311/python.exe' -B tools/bettergi-agent/run_destination_batches.py finish `
    --folder $runFolder --batch 2 --wait-seconds 60
```

A graceful finish completes the accepted batch and seals its final station photo before closing. To cancel during movement, create the launcher’s printed `STOP` file with `New-Item -ItemType File -Path (Join-Path $runFolder 'STOP')`. This requests an immediate addressed input release. An empty manual slot at a photographed boundary has a one-second deadline. On expiry the resident keeps input released and reports queue starvation. Publish the next batch or finish while the predecessor is still walking.

### Qualify the frozen GPU scene observer

The experimental scene observer reuses the installed P2P visual encoder with a small frozen prototype bank. It reads only the central image crop. BetterGI still owns localization and route verification; P2P still supplies live visual action proposals. The new observer does not turn native controller experience into human demonstrations or establish general-world navigation.

The October 30 gate progressed through retained-image comparison, exact CUDA graph parity, two fresh shadow leases and a four-photo controlled trial. Each stage has separately retained evidence. G4 remains the ordinary/default observer. The scene checkpoint alone has no photograph authority: `run_scene_photo_trial.py` issues only an exact four-goal permission, and `run_scene_endurance_trial.py` requires the separate reviewed endurance permission. The latter uses the existing automatic publisher, targets 600 seconds of positively witnessed gameplay and stops at a photographed boundary within a 900-second cap. It preserves the 78°C thermal stop, 150 ms freshness limit, 100 ms holds, original owner and subsecond handoffs.

These workstation-specific experiments require the retained comparison artifacts and the original verified RDP pair, idle at the stairs. They reject changed owners and do not create an RDP session or reposition the character automatically. Their printed `STOP` path cancels movement. See [the qualification results, exact scope and failed attempts](../../Docs/research/BetterGI-Recovery-Endurance-2026-10-30.md).

### Export recorded controller experience

`experience_manifest.py` audits one explicitly selected, sealed warm episode and writes a new `manifest.json` plus receipt-backed `actions.jsonl`. It obtains the actual photo observer and qualification from the original saved worker command, including experimental scene permissions. It checks video decodability, source/frame alignment, complete input receipts and retained-file hashes. Native control, learned-policy proposals and recovery actions keep separate provenance. Failed or incomplete evidence remains diagnostic; it is never silently relabeled as successful gameplay.

```powershell
& 'artifacts/agent/envs/gamescaling/Scripts/python.exe' -B tools/bettergi-agent/experience_manifest.py `
    --folder PATH_TO_ONE_RETAINED_EPISODE `
    --output PATH_TO_A_NEW_EXPERIENCE_DIRECTORY --split holdout
```

Split by whole episode before fitting. The exporter reserves that split in an `experience-split.json` record bound to the original resident manifest. It refuses conflicting exports, and the steering fitter rejects holdout and diagnostic reservations before optimization. The steering reader independently audits directed destination plans before deriving native weak labels. Continuous H.264 recordings contain lossy decoded pixels; archived station RGB and PNG photos retain exact policy pixels. The exporter creates data and qualification evidence only; it does not train or deploy a policy.

Completed map inspections additionally require the original `map-owner-source.json` lineage binding and an exact independent replay of `map-audit.json`. Their M/Escape pulses are retained in `ui-actions.jsonl`, with the real native operation ID, pulse ordinal, software execution evidence and original full-resolution PNGs. They remain separate from ordinary stream requests and lossy video observations. The export rejects unqualified, recovery or unaccounted UI operations. The October 30 `map-visit-training` episode contains 86 ordinary actions and two UI pulses; it is reserved for training, while the endurance and recovery-resume holdouts remain excluded from fitting.

Map admission requires three stable G4 views separated by at least 80 ms on both the freshness clock and the original capture clock. Acquisition delays cannot substitute for source-frame spacing. The rejected October 30 trial and its 62.5 ms capture gap remain diagnostic; the corrected fresh trial passed with 93.75 ms gaps throughout.

### Inspect the junction world map on SIREN

The map runner uses the existing minimized BetterGI RDP child, one resident GPU model and the qualified G4 observer. Its fixed itinerary starts at the sidewalk junction, visits the west lamp and returns to the junction. The verified R59 receipt binds host PID 10124 to child PID 5520 in RDP session 3 and protects Genshin PID 26240. The launcher checks the live owner and native game binding before walking. In the verified runs, the game window handle was 197360. The same receipt can be used while that exact pair and game are still present. [R59 ownership and deployment evidence](../rdp-automation/README.md#verified-r59-map-test-child-on-siren)

**Inspect from the world HUD.** Start only when the character is at the junction in the playable world. BetterGI verifies the junction pose and G4 photo, opens the configured world map, recognizes the map and close control on fresh frames, and closes it once. It requires a fresh world HUD, settled junction pose and matching photo before handing walking back to the controller. Normal walking proposals are fenced during the UI operation. The standard thermal, stale-frame, owner and operator STOP gates remain active throughout the run.

```powershell
$py = 'C:/Programs/Python/Python311/python.exe'
$runner = 'tools/bettergi-agent/run_warm_photo_requests.py'
$mapRoot = 'artifacts/live/2026-10-29-map-inspection'
$mapOwner = (Resolve-Path "$mapRoot/lineage59-admin/map-owner-lineage.json").Path
$route = @('--map-owner-from', $mapOwner, '--start-station', 'sidewalk-junction',
    '--destination', 'photograph-lamp', 'west-lamp', '--destination', 'return-junction', 'sidewalk-junction',
    '--seconds', '120', '--steering-shadow', 'artifacts/agent/steering/gen-01.json',
    '--landmark-shadow', 'artifacts/agent/landmarks/gen-04.json',
    '--photo-qualification', 'artifacts/agent/landmarks/qualify-g4-fresh-10.json')
& $py -B -X utf8 $runner @route --inspect-junction-map --evidence-root "$mapRoot/r59-live"
```

R59 completed the fresh inspection and both walking legs in `r59-live/warm-20261029T191756Z-b633a0566524`. The audit verified the world-map visit, return to the junction and the first west-lamp frame. [Inspection audit](../../artifacts/live/2026-10-29-map-inspection/r59-live/warm-20261029T191756Z-b633a0566524/map-audit.json) · [Completed route](../../artifacts/live/2026-10-29-map-inspection/r59-live/warm-20261029T191756Z-b633a0566524/warm-launcher.json)

**Recover an already-open map.** R58 opened the map but refused a stale frame before closing. A separate input-disabled observation recorded the map still open. R59 used both original records in a separate lease, recognized the open map on fresh native frames, closed it once, verified the world HUD and junction, then completed both walking legs. The arguments below document that completed recovery. A new interruption needs its own failed inspection and independent passive observation.

```powershell
# Recorded R59 recovery, using the shared variables and route above.
& $py -B -X utf8 $runner @route --recover-junction-map `
    --map-failure "$mapRoot/live/warm-20261029T180711Z-9e347a5c89dc" `
    --map-passive "$mapRoot/r58-after-attempt" --evidence-root "$mapRoot/recovery"
```

The recovery audit records zero map opens, one close, software input release and two route legs. Both run modes print a run-specific `STOP` path. [Recovery audit](../../artifacts/live/2026-10-29-map-inspection/recovery/warm-20261029T191651Z-9d5b3c8f7c36/map-audit.json) · [Completed recovery route](../../artifacts/live/2026-10-29-map-inspection/recovery/warm-20261029T191651Z-9d5b3c8f7c36/warm-launcher.json)

**Continue walking after the map.** From a world-ready junction, the automatic queue can start with this same map inspection. Its first two destinations are the west lamp and the junction. It chooses subsequent goals only after an applied action in the preceding batch. Supply a completed run on the current process pair along with the protected map-owner receipt. The 210-second gameplay clock begins with the walking dispatches. The 400-second deadline covers the whole invocation.

```powershell
$mapRoot = 'artifacts/live/2026-10-29-map-inspection'
& 'C:/Programs/Python/Python311/python.exe' -B -X utf8 tools/bettergi-agent/run_destination_batches.py launch `
    --open-queue --inspect-junction-map --map-owner-from "$mapRoot/lineage59-admin/map-owner-lineage.json" `
    --owner-from "$mapRoot/r59-repeat/warm-20261029T191916Z-189862af5a80/warm-launcher.json" `
    --start-station sidewalk-junction --destination first-lamp west-lamp --destination first-return sidewalk-junction `
    --batches 12 --leg-limit 96 --seconds 400 --target-gameplay-seconds 210 --evidence-root "$mapRoot/r59-sustained" `
    --steering-shadow artifacts/agent/steering/gen-01.json --landmark-shadow artifacts/agent/landmarks/gen-04.json `
    --photo-qualification artifacts/agent/landmarks/qualify-g4-fresh-10.json
```

Success requires both `handoff-audit.json` and `map-audit.json`. The latter checks the captured map, verified world return, first lamp photo, and the completed successor batches under the original owner. An explicit finish completes the current batch. Use the printed `STOP` file for immediate cancellation.

### Separate resident batches

On SIREN the series launcher can repeat a task on the same minimized RDP connection. This example requests one source photo at each named station in each batch. The collector saves the original RGB image when the native station, verified frame and qualified image prediction agree. At the end of the batch a separate verifier decodes each saved PNG, checks its raw pixels against the live hash and classifies it again. A failed objective ends the series.

```powershell
& 'C:/Programs/Python/Python311/python.exe' -B tools/bettergi-agent/run_patrol_series.py `
    --batches 2 --circuits 4 --seconds 145 --series-seconds 330 `
    --evidence-root artifacts/live/photo-series `
    --steering-shadow=artifacts/agent/steering/gen-01.json `
    --landmark-shadow=artifacts/agent/landmarks/gen-04.json `
    --photo-qualification=artifacts/agent/landmarks/qualify-g4-fresh-10.json `
    --photo-station stair-front --photo-station sidewalk-junction --photo-station west-lamp
```

To cancel, create the `STOP` file at the path printed on launch. The supervisor addresses the active resident, cancels later batches and saves `series.json`. A new batch requires the same authenticated root and child, the preceding batch's completed audit and a fresh GPU check. Each batch releases input before its audit. The next batch pays the CUDA model startup cost again.

### Start an individual stream

1. Use the approved **Start Genshin in RDP** launcher to start or reuse the minimized RDP host and child game runtime. The [RDP automation guide](../rdp-automation/README.md) covers the stable shortcuts, saved Windows sign-in, commands inside the child session and child-only hot replacement.
2. Launch `stream_client.py --resident` inside that actual RDP Windows session, using the installed GPU Python. From the main desktop, use the guide's `rdp_control.py exec` command to dispatch it into RDP. Resident mode authenticates the child and starts its stream; it never falls back to console input. Both the server and client must enable input before a model action is submitted.

For the already configured session 3, this bounded observation-only command requires no model loading or game input. Use unique recording/output paths for each run:

```powershell
& D:/work/genshin-auto/artifacts/agent/envs/gamescaling/Scripts/python.exe `
  tools/bettergi-agent/stream_client.py --resident --rdp-session-id 3 `
  --model observe --observation-profile p2p-native-hamming-192-v1 `
  --seconds 30 --segment-seconds 30 --preview `
  --record-dir artifacts/agent/recordings/first-observation --ffmpeg C:/programs/ffmpeg.exe `
  --output artifacts/agent/benchmarks/first-observation.json
```

The [streaming guide](STREAMING.md) documents input opt-in, text goals, pause/resume, idle recovery, observation profiles and recording limits. Manual/nonresident streams remain available through the [headless bridge commands](../../Docs/design/agent-stream.md#headless-launch).

An observation session sends a bounded queue of RGB frames to FFmpeg independently of capture and inference. The resulting H.264 video is lossy, with synthetic fixed-rate playback timestamps. `frames.jsonl` maps actual encoded indices to source metadata; `observations.jsonl` separately retains received headers even when the video queue drops an image. Use native source clocks and execution receipts for analysis, and reject affected training windows after metadata, receipt or video loss. Model-generated trajectories are not expert demonstrations, and these recordings do not establish physical-input or game-render timing.

For bounded data collection, `--retain-policy-rgb` preserves the exact immutable RGB192 payload beside each encoded frame, on the recording worker. It requires the native Hamming192 profile and a recording cap of at most 160 MiB. Raw files share that existing budget, including retiring segments; retention stops before admitting a raw file that would exceed it. `frames.jsonl` carries each file's shape, size and SHA-256. The experience exporter independently checks those bytes, source/action alignment and complete raw coverage against the recording seal, while retaining the H.264 references separately. This option does not expand input authority or make automated trajectories human demonstrations. It is available on the standard patrol/warm-photo launchers, but not the larger endurance profile.

`combat_observer.py` is a read-only preparation tool. Its compact red-bar and health-color heuristics return candidates and temporal consistency only. They explicitly do not identify an enemy, grant input authority, estimate a health percentage, or verify a kill. The current negative-route check is not positive combat qualification.

`prepare_replay_session.py` prepares offline P2P comparisons from one **complete,
closed bridge lease** split across resident recording segments. It verifies the
session/owner, contiguous report chain, original carry-over frames, pending
proposals, terminal receipts, local video indices and loss counters before using
the existing replay-window checks. No model, GPU, encoder or game connection is
started. For example, from the repository root:

```powershell
python tools/bettergi-agent/prepare_replay_session.py `
  --reports-dir artifacts/agent/benchmarks/navigation-r16-continuity-01-segments `
  --recordings-dir artifacts/agent/recordings/navigation-r16-continuity-01 `
  --history-frames 40 --max-windows 6 `
  --output artifacts/agent/replays/continuous-session.json
```

Use `--first-segment` and `--last-segment` together when a directory contains
multiple leases; the selected range must contain one whole lease. Optional
`--probe-frame-id` values select specific recorded decisions. The command limits
one preparation to 128 segments and 128 MiB of JSON metadata. It hashes every
input, including video, and rejects changes observed during preparation.

The distinct output kind is `p2p-offline-continuous-history-candidates`. Every
image reference includes its original `videoFile`, `recordingSegment`, local
`videoFrameIndex` and local `videoPtsSeconds`; consumers must understand those
multiple-video addresses. Videos are neither concatenated nor decoded, and
carry-over headers do not create extra images. `trainingEligible` and
`expertDemonstrations` remain false. The existing macro recorder also lacks the
shared frame-clock anchor and unmerged input ledger needed for human training
demonstrations.

To decode a prepared continuous plan with the existing Python environment and
installed FFmpeg/FFprobe, run:

```powershell
.\artifacts\agent\envs\gamescaling\Scripts\python.exe tools/bettergi-agent/experiments/continuous_replay_pixels.py `
  --plan artifacts/agent/replays/continuous-session.json `
  --output artifacts/agent/replays/continuous-decoded
```

The output directory must be new. Use `--ffmpeg` and `--ffprobe` to select existing
decoder binaries explicitly when they are not on PATH. This CPU-only reader
reconstructs the full plan and action labels from pinned source files, verifies
each video's frame count and selected PTS/index pairs, and exports PNGs with a
`manifest.json`. A 40-step window includes 42 images: its anchor, 40 history
samples and separate probe. Shared references use one exported image. The PNGs
preserve decoded RGB values; the source video's lossy compression limits fidelity
to the original observations. A verified manifest remains non-expert and
ineligible for training, and the command never loads a policy or connects to a
running application.

For pretrained Open P2P inference, replace `--model observe` with:

```text
--model open-p2p --source artifacts/agent/sources/open-p2p --checkpoint artifacts/agent/models/open-p2p-150M/150M/checkpoint-step=00500000.ckpt --history 200 --cuda-graph --p2p-fast-start
```

The current local live candidate uses `--history 41 --p2p-prewarm
--action-hold-ms 100 --fps 30 --decision-hz 20 --max-observation-age-ms 150`
with the native Hamming RGB192 profile and blocking Windows Graphics Capture.
The shorter history changes temporal context. In the latest 90-second H41 run,
median/p95 model evaluation was 38.70/47.48 ms and reported source age at first
software dispatch was 74.16/96.45 ms. All 1,707 accepted actions were applied.
The H200 comparison also met the input deadline but remained climbing a wall
for most of its run; neither result establishes reliable Genshin navigation.
See the [current live evidence and limitations](../../Docs/research/BetterGI-Agent-Status.md).

The optional `--p2p-prewarm` flag prepares the masked CUDA graph during policy
loading, before the bridge connects. It uses a temporary zero-valued RGB192
image with the normal prediction layout, then restores empty history. It emits
no controller input. Preparation time is recorded separately in
`policyMetadata.startupGraphPreparation`; the work moves into loading rather
than disappearing. The flag requires Open P2P, `--cuda-graph` and
`--p2p-fast-start`, and remains opt-in. Both history configurations have now
completed live RDP trials with prewarming enabled.
Saved-image checks matched actions, cached state and random-generator state at
41 and 200 history frames, including a goal change and rejected-action rollback.

The producer consumes fresh frames independently of inference through one replaceable slot. Slow models skip old frames rather than build a backlog. The controller rejects stale/expired actions and releases held inputs when the action horizon expires. Open P2P predicts a held-key state and relative mouse event; this adapter assigns a 50 ms interval, rather than predicting duration. An explicit `--action-hold-ms 100` selects the bounded hold used in the live trials. Replacement preserves common held keys. GameScaling predicts six steps totaling 200 ms. The first-input freshness deadline is separate from the hold horizon.

In the r14 Release comparison, native-Hamming P2P directional input started at 94.57 ms median / 126.38 ms p95; all 1840 input starts respected the 150 ms deadline. The model still climbed or stalled at obstacles. The same-seed legacy trial was slower at the median but had fewer no-op proposals, so this single pair does not establish a navigation-quality winner. See the [live results and limitations](../../Docs/research/BetterGI-Agent-Sprint-Results-2026-10-23.md#r14-release-live-verification--2026-10-24-utc).

## Reproduce offline benchmarks

For CPU-only preparation of receipt-grounded history comparisons, see [Offline replay preparation](REPLAY.md). It checks recorded evidence and prepares real-frame windows; it does not run inference or produce expert training labels.
The separate [following-acquisition comparison](REPLAY_FORWARD.md) preserves
those plans and tests a next-frame action association on the same history images.

Run one GPU benchmark process at a time. These commands use actual saved Genshin frames and do not send game inputs.

```powershell
& artifacts/agent/envs/gamescaling/Scripts/python.exe tools/bettergi-agent/benchmark.py --model open-p2p --source artifacts/agent/sources/open-p2p --checkpoint artifacts/agent/models/open-p2p-150M/150M/checkpoint-step=00500000.ckpt --images artifacts/act-two-upper-contact-regression-20261019/frame-0672.png artifacts/act-two-upper-contact-regression-20261019/frame-0690.png --history 200 --cuda-graph --warmup 203 --samples 250 --output artifacts/agent/benchmarks/open-p2p-fp32rope-graph200.json

& artifacts/agent/envs/gamescaling/Scripts/python.exe tools/bettergi-agent/benchmark.py --model gamescaling --source artifacts/agent/sources/GameScaling --checkpoint artifacts/agent/models/GameScaling-0.8B-S3 --images artifacts/act-two-upper-contact-regression-20261019/frame-0672.png artifacts/act-two-upper-contact-regression-20261019/frame-0690.png --warmup 2 --samples 20 --max-new-tokens 48 --output artifacts/agent/benchmarks/gamescaling-20.json

& artifacts/agent/envs/gamescaling/Scripts/python.exe tools/bettergi-agent/benchmark.py --model gamescaling --source artifacts/agent/sources/GameScaling --checkpoint artifacts/agent/models/GameScaling-0.8B-S3 --images artifacts/act-two-upper-contact-regression-20261019/frame-0672.png artifacts/act-two-upper-contact-regression-20261019/frame-0690.png --cuda-graph --warmup 2 --samples 20 --max-new-tokens 48 --output artifacts/agent/benchmarks/gamescaling-graph20.json
```

Reports include source revision, weight hashes, installed packages, image hashes, seed, warmup, per-frame timings, first-token versus complete-action latency, parsing, overwritten frames, and peak PyTorch VRAM. Pixels are predecoded, so offline latency excludes live capture, transport, game rendering, and input-to-display delay. Replay is open loop and may use a different frame cadence from training. It is not a task-completion benchmark. GPU memory allocated by the game is not included in PyTorch's peak-memory counter.

In the original offline benchmark on this RTX 2080 SUPER, the corrected 200-frame P2P graph ran 250 measured actions at 27.32ms median / 28.14ms p95; its 30Hz replay frame-age-inclusive p95 was 54.99ms. The matched steady eager run was 209.71ms / 244.02ms. That growing-history benchmark spent about 39 seconds filling and validating its context. Current resident mode requires masked fast startup instead; it starts with empty history and keeps unused cache capacity masked. The position diagnostic passed beyond the old 9000-step reset boundary without a reset.

GameScaling's 20-action median improved from 2012.31ms to 494.48ms using its whole-token graph; p95 improved from 2443.05ms to 531.37ms. It still misses its 200ms action horizon. All GameScaling replay outputs were no-op chunks. Parsing and static protocol compatibility therefore establish neither useful behavior nor actual execution. See `Docs/research/BetterGI-Agent-Sprint-Results-2026-10-23.md` for the combined sprint results and remaining live qualification.

P2P replay and shadow runs also accept `--p2p-temperature 0.2`. The default `1`
uses the original adapter. An override selects a separate experimental adapter
and records its temperature in the result metadata; the value stays fixed for
that adapter and its CUDA graphs. `--temperature` remains GameScaling's option.
The current P2P candidate was tested with history 41 and cached text goals on
retained screenshots. Lower temperature helped the narrow walk/stand comparison
with bilinear pixels, but walking stayed idle for all 54 predictions with native
Hamming pixels, even after filling history. Landmark goals also mostly became
idle on that image path. This is not a qualified gameplay setting.
See the [current evidence](../../Docs/research/BetterGI-Agent-Status.md).
Overrides are refused with `--enable-input` and cannot enter the existing native
checkpoint qualification profile. They currently support offline comparison
and shadow observation only.

## Native compatibility changes

- **GameScaling:** Uses its official prompt, original checkpoint chat template, special action tokens, and action-only prefix. Native Transformers SDPA runs in FP16 on Turing. Qwen3.5's linear-attention/convolution reference kernels work without native Linux extensions but are slow. Only complete, finite action chunks are accepted. Mouse deltas are per-mille of source dimensions and are applied once per chunk. Number-key and function-key capitalization stays distinct. Scrolling is recognized but not submitted because the first bridge does not support it.
- **Open P2P:** Uses its original image encoder, transformer, action heads, KV state and action mapping. Tensor-only checkpoint loading is strict. A generated source copy under `artifacts/agent/compatibility` removes training/Unix transport imports, selects FP16, and evaluates the original attention mask using native SDPA. The upstream repository stays unchanged, and a manifest records source modifications and hashes. The default no-text path uses the learned no-text embedding. Optional text goals use a separately prepared official encoder embedding, loaded once outside the frame loop. Mouse decoding follows the checkpoint's `truncated_normal` setting by default; `--p2p-mouse-sampling` records explicit alternatives. Resident input rolls back rejected proposal history and resets after accepted-but-unapplied receipts; accepted history still contains sampled actions rather than a reconstruction of actual execution timing.
- **Image profiles:** The legacy default uses native→640×360 OpenCV Area→192×192 Pillow Bilinear. The opt-in `p2p-native-hamming-192-v1` profile performs direct native→RGB192 interpolation matching the pinned upstream Rust Hamming reference and skips the second resize. Profile/dimension checks precede inference. Native world/motion checks still inspect the original capture; the old 16:9 client minimap heuristic is unavailable for square payloads.
- **CUDA graphs:** Open P2P graph capture verifies actions and cached state against eager inference with identical input and sampling values. `--p2p-fast-start` uses fixed-capacity storage with a validity mask, so unused entries are not treated as gameplay history; a history reset retains the validated graph. The older growing-history path and offline benchmarks retain their declared warmup context. A short `--history 32` configuration changes temporal context with unverified effects on gameplay quality; the released configuration uses 200.

P2P's generated FP16 copy also normalizes RGB bytes in FP16. It preserves the
cast from uint8 and divide-by-255 formula, but changes upstream BF16 rounding. Pixel
resize parity and CUDA graph parity within this port do not establish full-model
BF16/FP16 equivalence.

## Verification

### Native navigation with GPU feedback

`stream_client.py --resident --model open-p2p --hybrid-navigation
--goal-intent ground-navigation --hybrid-legs 2` opts into the fixed
Mondstadt courtyard qualification route. Supply the usual checkpoint, source,
CUDA graph, fast-start, RDP session, input and output arguments. Omitting
`--hybrid-legs` uses the existing finite run duration. `--navigation-guidance`
alone exposes read-only native poses and is suitable for an observation-only
check before enabling movement.

Choose a surveyed segment with `--hybrid-route`. The default is
`mondstadt-courtyard-hybrid-v1`. The streetlamp, flower box and stone stair post
use `mondstadt-lamppost-v1`, `mondstadt-planter-v1` and
`mondstadt-stair-post-v1`. Begin within two map units of either endpoint.
The street routes check their coordinate orientation against BetterGI's two
native bearings on each usable frame before steering.

BetterGI recognizes position and camera yaw from the exact native image that
produces each policy observation. The GPU still evaluates the image stream;
route-compatible forward proposals retain `open-p2p` attribution. Native
heading corrections and replacements for idle/off-route proposals are labeled
`hybrid-native`, with the original model proposal retained. An overridden model
proposal is not committed to its action history. Both sources share the same
input owner, freshness limits and world-readiness gate.

Three distinct stable observations admit the starting endpoint. Every completed
leg requires an acknowledged release followed by three fresh stable endpoint
poses. The stall detector requires two seconds of distinct, aligned observations
within half a map unit and at least 600 ms of confirmed forward input.
Retreat requires 200 ms of confirmed backward input. Turning back toward the
route requires both a confirmed sidestep and 1.5 map units of lateral clearance.
Input and time budgets bound each attempt. The planner stops on exhausted
recovery attempts or departure from its corridor.

For the stair post, add `--navigation-climb-recovery --remember-hybrid-bypass`.
If Genshin begins climbing, BetterGI confirms the drop command completed and
waits for two new normal-motion frames before the controller backs away.
After a successful detour, the controller can retain three measured positions
for that RDP stream and follow them in reverse on the return leg. Saving a path
requires forward progress past contact and a confirmed endpoint.
A late image releases input. During an established detour, three fresh stable
positions in the same capture and the acknowledged readiness epoch can confirm
the current waypoint again. A change in location or motion discards the detour.

Run `audit_hybrid_run.py` on the saved report and recordings to check a trial.
`--minimum-obstacle-passages` checks stationary forward attempts followed by
passage. `--minimum-climb-passages` checks a drop followed by passage.
`--minimum-bypass-replays` checks completed traversals of the taught path.
`--minimum-bypass-rebinds` requires a recorded stale-frame release and
reconfirmation during a completed replay.
The evidence includes endpoint samples, recovery attempts and controller
selection counts. Ordinary recordings omit the repeated rolling
`executionContext` snapshot from each image header, while retaining source
clocks, poses, proposal events and all terminal receipts. Use
`--execution-context record` to retain the full snapshots for diagnostics.
These checks qualify this route only; normal motion hints
are not proof of grounded movement, and software input receipts are not proof
of physical input delivery.

The experimental step-application bridge, queued successor, native history owner
and checkpoint load scope have 237 portable, CPU-only checks. From the repository root, run them
with Python 3.11; no model, GPU or running BetterGI instance is required:

```powershell
python -B -X utf8 -m unittest discover -s tools/bettergi-agent -p "test_step_application_*.py" -v
python -B -X utf8 -m unittest discover -s tools/bettergi-agent -p "test_checkpoint_load_scope.py" -v
```

The first command contains 194 checks and the second contains 43. They exercise
the actual Bridge with in-memory transport, partial writes, strict parsing,
application/terminal ordering, bounded packets, native history/RNG ownership and
checkpoint-load cleanup using fake numerical objects. All 194 transport checks
passed against the installed sources under the guarded runner. The unchanged
43 checkpoint cases and five harness checks passed in the preceding candidate
validation. The capacity test creates and removes its own
temporary evidence when run normally; our research runner can instead retain it.
That standalone cleanup path also passed under the existing guards. These checks
did not import a model runtime or exercise a real checkpoint.

The owner may publish history after a complete software application, retain the
unresolved terminal and prepare one successor. It preserves uncertain outcomes
and forbids publishing that successor until its predecessor reconciles. Explicit
v2 supports one active 50 ms action and one immutable queued successor. A valid
handoff retains shared held keys and records the successor's actual software
calls before retiring its predecessor. Missing, expired or uncertain successors
close the chain; the fixed boundary and original frame deadlines are not renewed.
The server supports an explicit per-session queued-v2 startup handshake; ordinary
sessions keep the capability disabled. Model-owner installation and the normal
checkpoint scope remain disabled. Actual numerical qualification, runtime
activation and observation/dispatch timing remain pending.

For transport development, start a fresh input-enabled stream with
`rdp_control.py start-agent --enable-input --experimental-queued-step-applications`
as described in the [RDP guide](../rdp-automation/README.md). Before sending actions,
the connected `Bridge` must separately call
`enable_experimental_step_applications(reviewed_producer_build_sha256=...)` with
the reviewed `BetterGenshinImpact.dll` SHA256. The client validates the producer,
session, owner epoch, clock, keys and initial empty state. It binds subsequent
requests to that original connection; replacement or failed negotiation retires
the original handle once and preserves the first failure. A listening stream
alone does not establish this handshake, and the ordinary resident loop does not
enable it automatically.

A software application record does not confirm physical input delivery or
completion of the action's hold interval. The qualified adapter and loader files
use explicit LF Git attributes because their admission guards check exact bytes.

`--cuda-graph` also supports GameScaling. Original multimodal prefill feeds Transformers' static hybrid cache, followed by one captured whole-token decode step. The adapter validates logits and every mutated cache tensor against eager execution, and checks its first two complete greedy outputs token-for-token against original `generate()`. These checks increase startup cost and are included in warmup time. A changed prompt capacity triggers graph recapture; the live gate keeps slow startup/capture actions from reaching the controller.

For saved-image quality diagnostics, `benchmark.py --model gamescaling` accepts
`--gamescaling-reasoning`. It uses upstream's open `<think>` prefill; the default
uses `<think>\n\n</think>`. Thinking and action tokens share `--max-new-tokens`.
An unfinished thought or incomplete action produces no accepted steps. Compare
the same images, goal, sampling and token budget in both modes. The live stream
CLI does not expose this experimental switch, and offline results do not qualify
gameplay quality or controller latency.

P2P evaluates the original FP32 rotary-position formula directly on the GPU. This prevents FP16 position overflow and removes the finite-cache reset/pause; temporal K/V history still rolls at 200 frames. Tests compare exact values against the original FP32 cache, including positions beyond 65504. `--position-offset` exercises large positions in an offline diagnostic; it does not create prior gameplay experience.

```powershell
& artifacts/agent/envs/gamescaling/Scripts/python.exe -m unittest discover -s tools/bettergi-agent -p "test_*.py" -v
```

The model tests compare the original causal mask and decode offsets against explicit masked-softmax attention, and check per-mille conversion, complete-action validation and key naming. Successful inference does not prove visual understanding or Genshin task completion. Preserve the initial eager and optimized JSON reports for comparison.

Official upstreams: [GameScaling](https://github.com/THUSI-Lab/GameScaling), [Open P2P](https://github.com/elefant-ai/open-p2p). The generated Open P2P source copy includes its upstream MIT license. Models are stored under ignored workspace artifacts; no `BetterGenshinImpact/Assets` directory is introduced.

## Bounded navigation qualification

R61 adds `--navigation-profile mondstadt-combat-scout-v1` for the separate local area X [-1350, -980], Y [2050, 2480], centered at (-1165, 2265). It retains the existing confidence thresholds and heading anchors. A fixed route must use its exact assigned profile; this does not widen the old patrol or surface scopes. `survey_surface_camera.py` accepts the same explicit profile for camera-only observation in that area.

`--native-combat-observation` negotiates optional native health-color, fill-estimate and red-bar metadata on the existing authenticated stream. It is available directly in `stream_client.py` and through `run_rdp_patrol.py`, and can accompany input-disabled `--combat-shadow`. It does not enable input. Each `combatEvidence` block is bound to the exact source frame; malformed joins stop the client. A pending first capture may have no block. Unknown health and overloaded candidate sets remain explicit. Color components do not verify a hostile or a kill. See the [contract and measured CPU cost](../../Docs/research/BetterGI-Native-Combat-Observation-2026-10-31.md).

`--hybrid-observe` runs the full resident navigation loop with both client and native input disabled. It rejects an input-enabled native lease. Admission and each walking leg have a 35-second wall-clock deadline checked before wait paths, including missing frames, unqualified poses and pauses. A terminal timeout remains a failed gameplay run even when it is the expected outcome of a stop qualification.

`--navigation-profile mondstadt-surface-hybrid-v1` requires R60's explicitly advertised capability. It permits only `City_102` and `MapBack_2`, within world X [-1100, -820] and Y [2100, 2350], retaining the 0.99 position and 0.2 yaw thresholds. The city-only profile remains the default. Surface routes require this profile; old patrols cannot silently inherit it. The coordinator must qualify fresh live coordinates and route consistency before enabling movement, and retain its original owner binding and stop/thermal limits.

`--combat-shadow` records same-frame vision candidates alongside P2P predictions with input disabled. Candidates do not verify enemy identity, authorize attacks, or prove a kill. Exact policy RGB capture is required. Survey extensions stop on obstacles for inspection; failed geometry remains available for evidence replay while being excluded from launch choices.

`survey_surface_camera.py` inspects one compass heading from a verified stationary surface position. Supply the sealed owner lineage, a completed input-disabled native scene from that owner, and a new evidence directory under `artifacts/live`:

```powershell
python tools/bettergi-agent/survey_surface_camera.py `
  --owner-lineage $lineage --anchor-scene $nativeScene `
  --heading 330 --output $newEvidenceDirectory
```

The hook retains original source/receipt evidence and allows only horizontal mouse pulses with empty key lists. It measures each settled response, stops within three degrees of the requested heading, and refuses absent, reversed or excessive responses. The whole survey is bounded to 35 seconds and twelve corrections, with the established 150 ms freshness, 100 ms holds, 78°C stop, telemetry-loss stop and exact minimized RDP identity. Creating `STOP` in its evidence directory cancels it. It does not restart on failure. Capture a fresh input-disabled native scene afterward before declaring another movement leg. Camera surveys are diagnostic and do not load or train a policy model.

## Keep a scout policy loaded between reviewed legs

`scout_session.py` keeps the installed Open P2P weights and CUDA graph in one ordinary-token RDP worker. Each explicit request gets a fresh resident run and one controller lease; the bridge closes before the next passive inspection. Pass this worker command to the existing RDP command broker, with workspace TEMP/TMP, a new evidence directory, and the sealed original owner lineage:

```powershell
& $gpuPython -B -X utf8 tools/bettergi-agent/scout_session.py run `
  --directory $newSession --owner-from $lineage --seconds 600 `
  --route mondstadt-combat-scout-north-meadow-v1 --allow-reviewed-routes
```

The worker requires the original minimized owner and an ordinary token in its RDP session. It submits no destinations itself. The default lifetime is 600 seconds; an explicit `--seconds` may retain the policy for up to 1800 seconds. The recording cap remains 160 MiB. Thermal, telemetry-loss, ownership and operator stops remain active while loading and waiting. A failed leg stops the worker. Each movement leg retains the 35-second deadline, 150 ms source freshness and 100 ms hold limit.

The scout's text goal stays fixed for the session. An external goal request releases input and fails the leg before changing the model; a late goal request also prevents another leg. Start a new session to select another instruction. A plain pause followed by an explicit run remains within the original 35-second deadline. Independent replay checks the original review/native/image files as well as unchanged goal state throughout the recorded run.

After startup or the preceding completed leg, capture and inspect a fresh input-disabled native scene. A review names its `nativeEndpoint`, `imageName`, `imageSha256`, inspected health/max health, and `visualReview`; it must declare `attacksAllowed: false` and `maximumLegs: 1`. The source must contain three stationary, same-epoch observations and a matching full native PNG. Repeated polls are allowed only when their immutable source evidence agrees.

For a registered route, include its `routeId` and exact `points`. To choose a different short path, generate the four geometry fields and include them in that same visual review:

```powershell
python tools/bettergi-agent/scout_session.py route-spec `
  --start $startX $startY --end $endX $endY
python tools/bettergi-agent/scout_session.py submit `
  --session $newSession --review $freshReview
python tools/bettergi-agent/scout_session.py stop --session $newSession
```

Explicit geometry is immutable, directed, limited to two points and 40 units, and confined to the existing scout bounds. Its complete hash is bound through the original review, request, cached-policy proof and controller evidence. It does not register a global route or authorize an automatic obstacle detour. The independent auditor requires both `--policy-reuse-proof <patrol.json.reuse.json>` and `--reviewed-scout-route <leg/reviewed-route.json>` for these legs. Ordinary audits retain their one-model-load requirement.

An intentional stop produces terminal session state `stopped` and process code 1; assess its reason separately from completed leg audits. Keep failed trials and native recordings as diagnostics, and reserve diagnostic or holdout episodes before export so they cannot enter fitting. See the [live measurements and limitations](../../Docs/research/BetterGI-Native-Combat-Observation-2026-10-31.md).
