# Raptor return travel checkpoint

The Springvale southern village/pond detour did not reconnect to the ambush and is retired. Safe teleport reset and the recorded original westward approach reduced the objective from141m to40m with Kaeya4015/4015, no attacks, damage, consumables or quest completion. Do not present this as Act II completion: AR9 remains650/1300, Act II locked, resin200 and spent0.

The scoped controller changes allow enemy-free remote ambush return travel, one reviewed low-climb release, whitespace-only map-label OCR normalization, and opt-in converging travel. The latter logs every forward-step distance and stops when distance increases by more than2m or fails to decrease for two steps. A single250ms stationary reread recovers quest-text fade only with a prior exact quest/distance witness, full health and no enemies. Fresh session, controller, account, map, health and input-release checks remain enforced.

Live evidence: mission-b97ee83f4c674f72b5824fb139ef63dd141->126m; mission-9f8691e467e946b5b15b6f1a7ce4ec3d125->96m; mission-bcc45172456841c1828295f9e267a32895->65m; mission-440a6e10d93f49b793c076c47cfd2a4964->40m. Quest-text rereads succeeded live in these runs. The stop-on-stall and stop-on-increase branches have automated coverage but no positive live trigger yet. Map refresh helper verified same-session map and final inventory pause, and leaves an unrecognized map open without retry.

Focused regressions:27 passed. Full isolated tracked suite result is recorded in artifacts/raptor-travel-full-tests.log. Publication excludes unrelated source drafts and the uninstalled native-route experiment. No native rebuild or application/RDP restart was needed.

Continue the original mission through authoritative Prologue Act II completion and stop before Act III. Next: fresh enemy type/facing/range, a short native rotation, and actual damage/kill verification. No repeat of out-of-range rotations.
