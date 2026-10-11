Act One Pilot

Purpose and limits
-----------------
Persistent local BetterGI controller for supervised development of the English
Prologue Act I route. It is not a campaign runner and a successful navigation
receipt means only that the supplied waypoint was reached. Requires BetterGI
r8+, Windows RDP session 5, a 16:9 game, and a normalized 1920x1080 capture.
Input is disabled by default; enableInput is an explicit script-group setting.

The controller
--------------
main.js starts one controller instance and keeps it alive while it polls
request.json every 100 ms. Its session ID, frame counter, consumed request IDs,
and timeout state persist between missions. Requests are JSON data; they never
execute code. IDs are consumed before mission work, so reusing a request is
rejected even if its client timed out.

Between new requests, the running main.js reloads trusted bgi.js into the
existing adapter. It reloads mission.js for navigation and dialogue requests.
This preserves the engine's session, frame, and replay-protection state. Edits
to bgi.js or mission.js take effect on the next new request. Edits to main.js
or engine.js require stopping and relaunching the controller. A client poll
timeout does not stop a mission and must not cause blind request replay.

Requests and input
------------------
Requests have the form {session,id,createdAt,expectedFrameId,mission}. Session
and frame come from observation.json; createdAt is Unix milliseconds, no more
than 30 seconds old. Use tools/quest-pilot/act-one-command.py to submit a request
atomically. Supported missions:

  observe: publish a fresh screenshot, OCR, position, HUD state and timings.
  stop: release keys and end the persistent controller.
  keyPress: VK_J/VK_M in the recognized world, VK_ESCAPE in the journal/map,
    VK_SPACE in recognized dialogue, or VK_F only when the world HUD and an
    interaction prompt are both detected.
  navigation: objective text, waypoints [{map:'Teyvat',x,y}], and deadlineMs
    (1000..90000). At most 10 waypoints, each within 150 map units. Uses the
    supplied route points; it does not plan around terrain.
  dialogue: at most 40 advances or 60 seconds. It stops at unknown screens,
    ambiguous choices, and the recognized world HUD. For Amber, Paimon, Jean,
    Lisa, Kaeya, and Venti it selects the first visible ordinary story response
    (preserving two explicit Forest responses), and rejects transaction words.
    Recognized Amber/Kaeya/Lisa acquisition banners are acknowledged only when
    both acquisition title and click-to-continue instructions are visible.

Amber's airborne-slime tutorial is handled as three exact English OCR steps,
before the generic world-return check: “Press 2 to switch to Amber” sends VK_2;
“Press R to enter/exit aiming mode” sends VK_R; “Move cursor to aim. Try
attacking the floating Anemo Slime” enters bounded aiming. For aiming, the
adapter examines a 1150x600 region starting at (400,250), thresholds a cyan
HSV range, and accepts only one contour with the configured size/area limits.
It then moves the cursor toward that fresh target by 50% of horizontal and 90%
of vertical center offset, each clamped to ±150 pixels. If both offsets are
within 18 pixels, it fires one 60 ms left-button click and reports a shot.
After each correction it waits 250 ms; after a shot it waits 1 second. Both
paths observe again before any further action. An unchanged switch, aim-entry,
or aim-exit prompt is acted on once; an unchanged aiming prompt is limited to
12 corrections/shots, then stops. “Press R again to exit aiming mode” together
with “Go to the location designated by Amber” sends one VK_R press, then
reobserves. Missing or ambiguous slime detection fails closed. Unknown screens
get observation-only retries and stop without game input when still
unrecognized.

Navigation verifies the map, camera, current objective, world HUD, and health
before each bounded input. It reobserves after turning and uses W for at most
800 ms per movement. World-coordinate X/Y axes are inverted relative to the
screen; camera conversion follows Navigation.cs and SceneBaseMap.cs. It stops
for missing HUD, changed objective, HP below 60%, a loss above 10% of initial
maximum HP, three stalled movements, a position jump above 25 map units,
nonconverging camera, deadline, session change, or lost focus. Held keys release
in finally. Two observation-only retries tolerate transient OCR misses.

Observation and recognition
---------------------------
Each observation captures the 1920x1080 game region, performs full-frame OCR,
writes a PNG and queries map coordinates. Health uses a 3x-scaled crop around
the health bar; if that result lacks a number/number pair, two separately
scaled numeric crops try to recover the left and right values around a missed
slash. Missing or invalid health is treated as unsafe for navigation.

For navigation objectives other than the Forest crystal objective, the adapter
can reuse full-frame OCR rows inside the objective box only when one row exactly
matches the requested objective after case/whitespace normalization. Otherwise
it performs OCR on the objective crop. This conditional reuse preserves the
requested objective text when the full-frame OCR is confident; it does not
promise the crop's every secondary row (for example, a distance label) will be
present in the full-frame result. The Forest crystal objective always uses the
objective crop because its adjacent “Higher Xm” reading is part of the scoped
approach/recovery logic.

At the Forest crystal approach, both assets/quest-marker.png and
assets/quest-marker-near.png are template-matched in the central screen region
with threshold 0.82 and three-channel matching. Overlapping detections within
30 pixels are treated as one physical marker. Marker guidance is accepted only
when exactly one unique marker remains. It is used only when the current
request objective is exactly “Investigate what Paimon has found” and map
coordinates are available. Within 15 map units, the controller steers toward
the marker and uses short movement pulses; it stops when the interaction prompt
appears. A single jump recovery is allowed only when position stalls near the
crystal and “Higher 1m” through “Higher 9m” is visible. It will not repeatedly
jump or continue after an ambiguous marker, missing evidence, or available
interaction.

Recorded Forest crystal interaction
------------------------------------
Saved release-r8 observations show “Investigate what Paimon has found” changing
from “Higher 4m” to “Higher 2m” and “Higher 1m”. Frames 198–199 show the world
interaction prompt. The navigation receipt stopped at “Interaction available”; a
separate VK_F request then completed. The subsequent dialogue mission returned
to the world HUD after seven advances. Saved frames 209–210 show “Quest
Completed”; the next objective was “Keep heading towards Mondstadt”. The later
saved journal observation shows “Wind-Riding Knight”. This is evidence for that
recorded interaction and quest transition only, not completion of the wider
campaign. The stop reason “Interaction available” is an intentional handoff to
the separately supervised VK_F request, not a reason to keep navigating.

Recorded Amber tutorial state
-----------------------------
Saved observations show frame 291 detecting one cyan target at (1134.5,369),
91x84 pixels. By frame 305 a fresh target at (953.5,528.5), 93x79 pixels was
within the 18-pixel center tolerance. The mission receipt records one 60 ms
VK_LBUTTON input at 1791683297826. Frame 307 then showed the “Go to the location
designated by Amber” objective and exit-aim prompt; the following dialogue
receipt records one VK_R and world return by frame 310. This confirms the shot
input and an objective transition in the saved run. The shot mission stopped
when its next frame had no unique slime target, so the records do not prove a
hit or the slime's health. They also do not establish completion of the larger
quest.

Safety and lifetime
-------------------
The controller requires RDP session 5 and game foreground focus. Input remains
disabled unless enableInput is explicitly set. Idle limit is 10 minutes and
total session limit is 60 minutes. To cancel an active mission, write stop.json
with its session and a createdAt at least as new as the active request, or use
the client cancel. A stopped/failed mission leaves the bridge available; the
stop mission ends it. Native capture/OCR calls cannot be interrupted mid-call
by a JS deadline.

Evidence and timing report
-------------------------
Observations are immutable JSON/PNG pairs. observation.json is the latest
observation; receipt.json is the latest request state; reports/<session>.json
preserves mission receipts and timed input events. Each observation records
capture, full-frame OCR, health OCR, objective OCR source/time, PNG writing,
map lookup and total time. The privacy-filtered summary aggregates the combined
OCR stage and reports median/p95 timings; it omits OCR text, screenshots, and
account IDs. Run it with the configured Python runtime:

  & 'C:\Users\daniel\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' tools/quest-pilot/report-act-one.py

The report's elapsed interval includes idle time; it is not mission duration.
Its terminal objective is the last recorded OCR evidence, not a completion
claim. To cancel or resume safely, inspect receipt.json and the child process
before submitting a new request.
