# Act I: English Lion approach validation

Wolf / Crash Course is complete. The journal now lists Sparks Amongst the Pages,
with Meet Lisa at the temple, as the only remaining Prologue: Act I quest.
This report does not claim Act I or the Lion domain is complete.

## Validated changes

- Added a one-shot ordinary-inventory Escape using the real English category,
  capacity and selected-item panel anchors. It rejects modal confirmations,
  stale/cross-session frames and duplicate anchors. A live close used 80 ms of
  input. The first post-close capture was still transitioning; the terminal
  capture confirmed the world. A subsequent navigation attempt stopped on HP loss.
- Statue recovery accepts the captured whitespace-only OCR variant
  `Statue of TheSeven`, while requiring exactly one nearby interaction label.
  The next live recovery restored active Amber from 719/1186 to 1186/1186 HP
  in 25,568 ms, then verified the paused journal. Two preceding healing passes
  stopped without restoring HP; these were failures, not successful recovery.
- Added a Lisa-objective-specific, one-shot teleport to the already unlocked
  Falcon waypoint, retaining existing Falcon/Wolf guards. Native teleport took
  6,735 ms; the whole request took 9,966 ms and returned a world capture with
  Amber at 1186/1186 HP. No party switches or walking occur in this helper.
- Added fail-closed English Lion entrance and party Start hooks. Their UI
  geometry remains provisional until a live Lion entrance is inspected.
  Tests establish click/provenance bounds, not live domain entry or completion.

## Travel and downtime evidence

Two supervised road segments arrived in 40,056 ms and 31,432 ms with no HP loss.
Their latest full observations took 325 ms and 538 ms respectively, including
capture, OCR, map lookup and PNG persistence. These are individual frame samples,
not a quest-wide latency benchmark or a before/after speedup claim.

A southward shortcut entered Cryo slimes and hit a stone obstruction. The first
stop occurred after 148 HP loss in 34,153 ms; a westward bypass stopped after
further damage, before walking. Inventory pauses prevented continued unattended
exposure. The controller then retreated to the unlocked Starfell statue and
healed. This route is unsuitable for unattended reuse.

Root-directed route submissions, inventory recovery, code hotloads, failed
healing attempts and the waypoint change are interventions. They are not an
uninterrupted autonomous run. No user clicks, native BetterGI restarts or RDP
restarts were required for these changes.

## Tests and limits

The full JavaScript suite passed 898/898 tests in 14,172.8779 ms before publication.
An unintegrated Lion trial guard under preparation was excluded from this run.
No native source changed; no additional portable build was required.

Completion will require live Lisa dialogue/entry, safe Lion trial traversal and
authoritative final journal evidence. Act II and unrelated world quests remain
outside the gameplay objective.
