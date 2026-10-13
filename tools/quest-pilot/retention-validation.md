# Bounded capture storage and verified runtime retirement

Stalled pause recovery previously kept writing screenshots indefinitely. Capture admission,
bounded evidence retention and a pause watchdog now stop that growth without inventing a
successful pause result.

## Runtime limits

- Reserve storage before **every** capture. Keep at most 256 ordinary frames within
  512 MiB and 24 hours, plus 32 recent failure/transition frames within 64 MiB.
  Total PNG admission is capped at **288 files / 576 MiB**, including locked,
  changed and unregistered images. The newest two ordinary frames remain available.
- Evidence priority rotates. Older priority frames return to ordinary retention;
  a transition or failure does not grant a permanent exemption.
- Delete only registered, unchanged PNG/JSON pairs while holding exclusive handles.
  Preserve unknown, changed, locked and historical files; stop capture if these
  prevent staying within the cap. Reject filesystem links and image overwrites.
- Identical consecutive PNGs use NTFS hard links when available. Their distinct
  frame paths and metadata remain valid. Unsupported links fall back to ordinary
  writes inside the same logical budget.
- Observation trees have an additional 1 GiB / 4,096-file guard, including metadata.
  Images are limited to 16 MiB, with 128 KiB reserved for companion JSON.
- Require 2 GiB free space plus the pending payload and metadata reserve.
  Reports and replay receipts each have a 64 MiB / 4,096-file guard and are not
  automatically pruned.
- Runtime logs roll daily or at 8 MiB, retaining eight segments for seven days.
  Shared writers use Serilog's file sink. A single oversized event can exceed a
  segment threshold, and operating-system locks can prevent removal.
- Pause recovery ends after 60 seconds or 120 observations, backing off polling
  from 250 ms to 1 second and then 5 seconds. Exhaustion and storage failures
  propagate through the outer protector, release held keys and terminate the
  listener with an explicit unverified-pause/storage fault.

The listener requires native `captureStorageVersion=1` before focusing or capturing.
A JavaScript-only update into an older application is not a valid deployment.

## Cleanup and replacement workflow

1. Inventory exact duplicate build files with `storage-cleanup.py`. For historical
   captures, `plan-historical-captures.py` proposes the same bounded tail plus a
   small representative evidence set. It preserves observation JSON, reports,
   settings and concrete validation references. Indispensable images exceeding
   the evidence cap stop planning instead of enlarging the cap.
2. Obtain action-time approval for exact candidate paths and hashes. Use
   `apply-storage-cleanup.ps1` for initial cleanup and subsequent retirement.
   It rechecks hashes, containment, links, locks and preserved witnesses.
   Historical mode additionally requires verified stopped writers; it removes
   only approved PNGs and preserves metadata/reports. Never bypass an owner or
   permission denial, or copy large screenshot trees onto a nearly-full drive.
3. Run source tests and `check-storage-headroom.ps1`. Publishing requires at least
   4 GiB free and no more than 4 GiB of managed portable build files.
   Preserve the active host and one known rollback.
4. Stage one runtime. `stage-tested-runtime.ps1` can reuse a compatible portable
   runtime only when every tested package/version exists in its dependency graph.
   It installs the exact tested project assemblies, preserves settings, copies
   tracked controller code, excludes historical captures and disables supervised
   gameplay input for validation. Otherwise perform a fresh portable publish.
5. Use the supported pinned-PID/session restart endpoint. Every managed portable
   application's startup writes a directory/DLL-bound retirement checkpoint.
   A new build or copied version needs fresh verification; the next publish is
   blocked until the checkpoint completes.
6. Run `validate-installed-retention.py` with input disabled and the Food inventory
   already open. It submits only bounded observation requests, checks the PNG cap
   after each one, rejects gameplay input and reports retained file identities and
   bytes. A fresh image is required; a heartbeat alone is insufficient.
7. Run `verify-runtime-installation.py` against the exact tested DLL hash and live
   pinned endpoint, declaring every active/rollback directory with `--protect`.
   This records installed identity and produces the retirement manifest.
   `--cleanup-manifest` reuses a reviewed manifest only if its complete candidate
   paths, sizes and hashes match the fresh inventory.
8. Apply the approved retirement with `-CompleteRuntimeCheckpoint` pointing to
   the installed `User/ExternalControl/retention-checkpoint.json`. The same cleanup
   routine completes the checkpoint only after the approved batch succeeds.
   Superseded builds cannot be retired without this verification checkpoint.
9. Verify cleanup/headroom before push and merge. Stop the validation controller,
   verify ownership release, and coordinate the gameplay handoff separately.

## Validation

Native cases cover disk-low admission, immutable images, identical/changed frames,
restart quotas, path safety, changed/locked/historical preservation, continuous
priority pinning, per-write count/byte caps, log rotation and replacement checkpoints.
PowerShell fixtures cover rejected unsafe deletions, checkpoint-gated retirement,
historical metadata preservation and the publish gate. Python fixtures cover exact
duplicate planning and bounded historical evidence. JavaScript tests cover long
stalls, frozen clocks, storage failure, outer-watchdog propagation and native-version
startup enforcement.

Operational manifests, local paths, process identities, measured cleanup totals and
installed validation reports belong in ignored `artifacts/`, not public source.
