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

## Automatic release retention

`Build/release-retention.json` pins **R1, R55 and R56** and keeps the two newest
successful numbered releases in addition to those pins. `publish-english.ps1`
and `stage-tested-runtime.ps1` run `Build/Scripts/manage-release-retention.ps1`
before and after producing a runtime. Staging protects its source until copying
finishes. An executable that is in use or inaccessible preserves its whole release.
Incomplete/unregistered builds are also preserved and remain visible to the
storage gate instead of silently displacing successful builds.

The retention script supports `-Action Plan`, `Apply`, `Register` and `Status`.
It only retires immediate `artifacts/release-rN` directories. New publishes record
generated files in `Portable-File-Manifest.json`; retirement removes entries only
when their size and modification time still match. Historical releases without
that manifest use recognized root binaries and generated paths also present in a
retained build. Unknown files are preserved. This is metadata inspection, not a
bulk content-hash or duplicate scan.

All `User`, cache, log, recording, screenshot, report and test-result trees are
preserved, along with source snapshots and build manifests. After generated files
are removed, the remaining release moves on the same volume to
`artifacts/release-evidence/release-rN`. Each archive contains
`release-retirement.json`, recording its original path, archive path and removed
program files. Existing receipts are not rewritten: when reading an old absolute
path, replace its recorded `originalPath` prefix with `archivePath`. Relative
paths within a release remain unchanged. The latest batch summary is
`artifacts/release-evidence/latest-retention-run.json`.

Containment is checked before mutation; linked paths are not traversed. Existing
archives are never overwritten. A partial operation stops the batch and writes an
audit in the original or archived release, preserving remaining data for recovery.
Pins and data archives are never automatically pruned.

`check-storage-headroom.ps1` requires at least **4 GiB free** and at most **6 GiB**
of managed portable program files, as configured in the policy. Historical gameplay
verification checkpoints remain evidence and do not block release retirement or
publishing. Runtime qualification and any gameplay handoff remain separate from
storage admission; cleanup does not launch, stop or reconnect an application.

## Historical capture cleanup and runtime qualification

Historical screenshots are not deleted by automatic release retention. If a
separate capture cleanup is requested, `plan-historical-captures.py` proposes a
bounded tail and representative evidence, preserving metadata and validation
references. `apply-storage-cleanup.ps1` retains its exact manifest-hash approval,
stopped-writer, containment, lock and preservation checks for that separate action.

For an authorized live replacement, `stage-tested-runtime.ps1` checks package
compatibility, installs tested assemblies, preserves settings, excludes historical
captures and disables supervised gameplay input. The existing installed-retention
and runtime-identity validators remain available for qualification. Their results
do not substitute for source tests or authorize starting the elevated application.

## Validation

Native cases cover disk-low admission, immutable images, identical/changed frames,
restart quotas, path safety, changed/locked/historical preservation, continuous
priority pinning, per-write count/byte caps, log rotation and replacement checkpoints.
PowerShell fixtures cover release pins, recent successful builds, changed and
locked files, evidence preservation, rejected paths, archive collisions and the
storage gate. The legacy cleanup fixtures still cover approved manifest deletion,
checkpoint completion and historical metadata preservation. Python fixtures cover exact
duplicate planning and bounded historical evidence. JavaScript tests cover long
stalls, frozen clocks, storage failure, outer-watchdog propagation and native-version
startup enforcement.

Operational manifests, local paths, process identities, measured cleanup totals and
installed validation reports belong in ignored `artifacts/`, not public source.
