# Prepared relay owner adapter and durable caller

This source-only addition supplies the Windows owner adapter, a guarded CLI line loop, a pure historical result consumer and a caller whose completion authority is the exact durable result. It requires the reviewed prepared-recovery-v3 protocol and CLI hook already installed in tools/quest-pilot. It does not install or start a controller.

The caller persists one exact outer request and dispatches it once. After dispatch it reads the durable result even when terminal output is missing, wrapped, malformed, interleaved, split, closed or throws. A valid result must match the original request, pinned owner and prepared claim. Missing or mismatched evidence retains that original request as held; there is no fallback redispatch. Waiting permits at most24 consume attempts and checks a120second deadline between calls. An in-flight tool call can finish after that deadline.

owner_adapter.py queries native identity only through the existing PID/WTS/SID-authenticated status client supplied by the guarded CLI. Its v1 lifetime digest uses ordered ASCII fields, including a normalized absolute Windows drive path and a private nonce; only the digest leaves the provider. A fresh current_admission check additionally requires the native idle/frame/no-active-request state to match the fresh file heartbeat. Historical identity-only reads do not require the original frame to remain current.

relay_driver.py has four modes. consume reads and validates the persisted exact result without native queries or an input lease. serve is the live single-writer line loop. verify-owner and qualify-recovery are owner-only native-read qualification operations. Recovery is disabled unless private configuration explicitly enables it after producer qualification. qualify-recovery validates two actual owner-bracketed samples, not a cached settled journal return. A historical result preserves original timestamps; the next action still uses the guarded CLI's normal admission checks.

The trusted owner supplies private configuration with schema, owner, allowed steps, commandPath, pilotRoot, appDirectory, journalDirectory, legacyResponses, requestsDirectory, recoveryEnabled and exact sourceHashes. The owner includes every adapter/protocol/CLI/helper/caller dependency in those hash bindings and keeps one shared durable journal. No real configuration, identity, nonce, account information or runtime evidence is included here. Native path support is intentionally limited to ordinary ASCII absolute drive paths; UNC/device namespaces and ambiguous paths are rejected.

run-game-bound.js is an async function for the existing orchestrator tool context. The owner supplies its tools/load/store/text/image bindings and the archonBoundRuntime/archonRelaySession values; importing these files does not configure or launch it. Pending and held memory must survive until the exact original request is reconciled. Resetting those flags or deleting the journal is not recovery.

Run the injected tests from tools/quest-pilot after the prepared-v3 dependency is present:

    python -B -m unittest -v test_owner_adapter test_relay_driver
    node test-bound-consumer.cjs

The Python scenarios use synthetic native responses, local temporary fixtures and fake dispatch. The JavaScript scenarios inject every tool call. The ConPTY fixture in this package is synthetic; the original private capture is excluded. Production adapter/driver/caller bytes and the two Python tests were copied unchanged from the qualified owner revision. The JavaScript test's fixture ID and the fixture itself were sanitized, so the whole package is a separately tested source version and is not claimed byte-identical to the live evidence bundle.

Keep the existing source-age, current-frame, recovery, character-selection and one-writer guards. This package does not enable receipt archival, rollover or capture cleanup. The native active-session archival contract remains separate. Source test success alone does not establish a gameplay latency improvement.

Verified-source correction: see verified-source-loading.md for the stdlib-only bootstrap, exact required source bindings, helper injection, metadata, direct-import test change, and owner-controlled journal-preserving qualification. The original package provenance above describes the input packet; modified files in this correction are a new source candidate and are not byte-identical to a deployed owner.
