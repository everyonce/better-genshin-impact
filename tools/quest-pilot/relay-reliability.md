# Inactive relay reliability contract

This module and matching result reader are inert library code. They are not imported by the production relay, wired into its line loop or close branch, or connected to a game/controller. Publishing these files does not activate them.

## Contract

An outer request ID binds the exact accepted payload, script session, process ID, Windows session and an explicitly supplied verified owner/process-lifetime fingerprint. PID alone is insufficient; a digest is a comparison fingerprint, not authentication. All IDs, PIDs and bindings in the tests are synthetic fixtures.

The journal flushes a global active intent and immutable per-ID intent before dispatch. One OS file lock covers admission through response persistence. A matching settled request returns its saved response without dispatch. A changed payload or identity, corrupt/partial evidence, or a legacy unbound response is held. An unknown active request blocks every new ID in the entire journal, including after restart. Missing responses, errors, timeouts and restarts do not prove non-submission.

Cached outcomes are historical evidence. They never grant a fresh visual decision or extend original evidence timestamps. Preserve existing task-specific freshness, provenance, ownership, nonce, character and quiescence checks at their actual admission boundaries.

## Required integration, all currently inactive

1. The controller owner must supply a trusted current owner/lifetime adapter and enforce that exact identity at the existing guarded CLI admission boundary. The library does not query or authenticate processes, native status, pipes or game state. A post-dispatch identity check is insufficient.
2. Use one persistent journal across all relay writers and restarts. Supply the previous response directory as a read-only collision guard. Preserve its original bytes. Establish that the previous relay has relinquished dispatch before replacing it. Never evade an unknown by deleting evidence, selecting a fresh journal or inventing a new outer ID.
3. Wire the original relay line loop and close branch explicitly, retaining its allowed steps and guarded CLI. Parse with `parse_request`, then call `RelayJournal.execute(request, context, guarded_dispatch)`. The callback must return the trusted existing response fields `id`, `code`, `error`, `result`, `output`. Settlement requires matched inner IDs/session/frame plus verified quiescence, or the explicitly recognized V4 archived/deferred non-submission result. The library does not infer non-submission from absent output.
4. Replace an ID-only result consumer at the same time. Validate the bound envelope with `validate_result(envelope, exact_original_request, exact_verified_context, allowed_steps)` or `journal.read_result(...)` after a lost response. Never fall back to a bare legacy ID result file. Held and unknown results are not completion. Settled includes failed/stopped/rejected terminal outcomes and deferral: consumers must still inspect the original code and terminal status. `replayed: true` identifies a historical cached result.
5. Automatic recovery from an original inner request and authoritative receipt is not implemented. A matching durable settled response can be reconciled without dispatch; other unknown outcomes remain held. Final controller-owner review, safe live adoption, and evidence of gameplay benefit remain outstanding.

## Durability and retention

Ordering is active-intent flush, per-ID-intent flush, one dispatch, response flush, then retirement of the active marker after validating settlement. A crash between the two intent writes conservatively holds the journal even if dispatch had not happened. A crash after a durable settled response allows read-only result reconciliation; a later admitted request may retire that already-settled marker. A crash before a durable response never causes automatic replay.

Qualification covers process restart, abrupt process exit, lost responses and local write failures. Power-loss/filesystem-corruption durability is not qualified. Keep the journal protected from external deletion/modification and shared by every writer. Hashes do not authenticate a hostile writer. There is no automatic journal-retention cleanup policy. Active, unknown, legacy and authoritative evidence must be preserved.

The tests use isolated temporary fixtures, synthetic dispatch functions and two bounded child Python processes for OS-lock and abrupt-exit checks. They never import the production relay/CLI or reach a game interface. The same 23 cases passed on Windows and independently on macOS/POSIX; this is 23 distinct cases, not 46. The documentation correction changed no reviewed code/test bytes and caused no redundant retest. Test durations are not gameplay latency measurements.

## Rollback

Before activation, reverting the additive source integration commit removes only these three source/test/doc files. Keep journals, response evidence, review receipts and frozen artifacts outside that source-only revert.

If a future owner activates an adapter, rollback must be coordinated by that owner at a verified safe boundary: quiesce the old relay, preserve all journals/proofs, account for existing in-flight or unknown requests, and establish one verified writer before restoring prior wiring. Never delete/reset a journal, clear an unknown marker, or replay an uncertain request as a rollback step. This package supplies no live rollback or activation command.
