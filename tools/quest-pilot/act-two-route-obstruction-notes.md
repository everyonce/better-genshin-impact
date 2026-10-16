# Cyrus approach inspection

The west-side approach reached the ridge face at full health but did not provide a walkable entrance to the final ambush. A direct northern segment collided with a tree; the local stall watchdog stopped it. The west bypass advanced normally. Subsequent backtracking was an intentional response to the ridge obstruction, not a coordinate inversion or restarted completed waypoints.

Recorded route audit: the two reverse batches covered 33.27 m and 40.42 m, and the southern-base segment covered 32.93 m. These are measured map-path distances, not quest progress. The southern base still has large boulders blocking the eastward line. The next landmark is open ground at the southern end of that ridge. The retired rock-side combat entry remains unsuitable.

A camera-only inspection was initially rejected because the field helper recognized the final ambush only within 35 m of its center. The new travel-camera scope permits inspection within the bounded approach region, only for that exact objective, full upgraded Kaeya health, grounded controls, no visible enemy bars, the original account and the current session. It does not permit movement or combat through this exception. A single camera turn then succeeded live at unchanged full health and independently verified Inventory afterward. Source and installed module hashes matched; no application rebuild or restart was needed.

Validation: 31 focused field tests passed, including refusals for movement plans, low health, threats, changed objective, wrong account/session, stale observations and out-of-region coordinates. Combat alignment remains unvalidated; no attack or quest completion is claimed.

An oversized five-waypoint request was refused before any input by the existing four-waypoint limit. It was split into bounded requests, retaining the finite-navigation/pause wrapper. Persisted local route cursors and receipts identify completed waypoints and intentional replans.

Request construction now rejects exploration routes longer than four waypoints or deadlines outside 1..45 seconds before writing a request. Field-plan construction requires a retained matching witness with enemy-scan diagnostics (except the established regional-map flow); a post-teleport frame without those diagnostics produces a local explanation. Five Python preflight/controller-gate tests passed. These are construction checks; the runtime still independently verifies ownership, freshness, health, target and pause conditions.
