# Verified-source relay startup

This correction is source-only. It does not activate the relay, rewrite private configuration, change a journal, install software, or qualify a live Windows owner. The existing CLI modes and durable caller protocol remain unchanged.

## Trust boundary

`relay_driver.py` is now a stdlib-only bootstrap. Its execution, the Python interpreter and standard library/import environment, trusted private configuration, and native binaries remain trust roots. The bootstrap cannot verify itself before executing. This is exact reviewed-source loading, not a Python sandbox or a claim that compromised configuration/interpreter/native code is safe. Use an owner-controlled interpreter and source directory; isolated Python mode (`python -I -B .../relay_driver.py ...`) avoids ordinary environment/search-path injection where the owner's deployment supports it. No runtime code changes `sys.path` or removes/replaces unrelated module-cache entries.

All eight required source files are read into bounded byte strings and checked before any project module executes. Python source is compiled directly from those captured byte strings, never from a loader that can reread files or use bytecode caches. Core imports are explicitly wired to one private module graph, giving a single `Held` and `OwnerContext` identity. Private module names are registered solely for Python dataclass compatibility and cleaned up by object identity.

File and parent paths are inspected with `lstat` without resolving away link/reparse evidence. Regular files, limits, opened-file identity, and read stability are checked. SHA-256 authenticates the captured bytes. These portable checks are not a claim of a fully atomic Windows directory-handle traversal. Linux symlink fixtures and mocked Windows reparse attributes are test coverage, not real Windows junction/symlink qualification. The previously blocked Windows privilege-1314 test remains unverified.

## Owner-controlled configuration update

Schema remains 1. `sourceHashes` retains the existing absolute-path-to-lowercase-SHA-256 map syntax. It must now have exactly these keys, each located in the same lexical absolute directory as `relay_driver.py`:

- `relay_reliability.py`
- `relay_prepared.py`
- `owner_adapter.py`
- `relay_runtime.py`
- `act-one-command.py`
- `controller-control.py`
- `receipt_archive.py`
- `run-game-bound.js`

Do not reuse an old map unchanged: add the runtime and controller roles, update modified command/archive hashes, and exclude the bootstrap's `relay_driver.py` entry from this executable-source map. The bootstrap hash belongs in the owner's external artifact qualification/manifest, not a self-verification claim. Unexpected, omitted, empty, substituted, or malformed entries hold startup. `commandPath` must equal the exact command role path. Paths are intentionally exact, not case/alias-normalized. Hashes must describe the reviewed installed bytes (including line endings), not a mutable moving branch or this document's examples.

The owner must review the correction against its current tree, preserve concurrent changes, and explicitly update private source bindings. This package performs no private-config migration. Keep the original owner pin, allowed steps, app/root directories, shared durable journal and pending requests. Never clear or recreate a journal to make a new source version start. Rollback is journal-preserving: restore the reviewed code/config together; retain all request, intent, prepared, claim, response, recovery and uncertainty/hold evidence.

## Scope and metadata

Every mode verifies all required files. `consume` loads only reliability/prepared/owner/runtime and performs historical validation: it does not load command/controller/archive helpers, query native state, dispatch input, or grant a lease. A subsequent action still needs ordinary fresh admission. The three other modes load the command plus exact verified controller/archive objects. Their injection hooks preserve standalone CLI loading behavior when the CLI runs outside this bootstrap; standalone use is not covered by the relay's verified-byte guarantee.

The controller object is used only for existing authenticated `status` queries in this graph. Restart/start/stop functions in that module and their auxiliary scripts are outside the invoked relay path. Archive behavior itself is unchanged, including active-session receipt exclusion; loading its module does not enable archival.

Successful readiness, owner/recovery qualification and consume responses include `sourceVerification`. Each role records actual path, expected digest, captured/verified digest, executed digest, load method and scope. Loaded Python roles have `state=loaded` and an executed digest. Unexecuted helpers in consume and the external JavaScript caller have `state=verified-not-executed` with a null executed digest. The JS bytes are checked, but this process does not attest which bytes a separate JS host actually ran. Metadata does not replace trust in the bootstrap and external artifact qualification.

## Source and test compatibility

The former implementation lives in `relay_runtime.py`. Its admission, journal, exact request identity, immutable original heartbeat, replay/uncertainty and read-only recovery behavior is unchanged. Direct Python consumers/tests importing `ControllerRelay` or `consume` from `relay_driver` must import `relay_runtime` instead. Such direct imports are injection/test APIs, not the verified production entrypoint. Always enter the production relay through `relay_driver.py`.

Run from `tools/quest-pilot` in an isolated checkout:

    python -B -m unittest -v test_relay_prepared test_relay_reliability test_owner_adapter test_relay_driver test_verified_sources
    node test-bound-consumer.cjs

Tests use injected native responses/dispatch and local scratch fixtures only. They include an actual subprocess consume through the bootstrap, with command/controller/archive sources configured to throw if executed, and prove durable journal bytes remain unchanged. Existing 68 protocol, 21 adapter/driver and 20 caller scenarios remain required. These results are not Windows live qualification, game testing, or a latency improvement claim.
