Bird's Eye View Pilot - experimental observe-first package

Current state: unfinished. The package records BetterGI captures, OCR, and
conservative quest-stage classification. Navigation is disabled by default.
routes.json is intentionally empty. No route is included or inferred here.
Do not enable navigation until you have supplied and independently validated
BetterGI route data for the exact objective stage(s) you intend to run.

Requirements
  * English BetterGI r8 or newer, exposing genshin.isRemoteDesktopSession,
    genshin.windowsSessionId, genshin.isGameForeground and genshin.focusGame().
  * captureGameRegion() normalized to 1920x1080. The remote desktop itself may
    be 2560x1440; setGameMetrics(1920, 1080, 1) is used for capture/input scale.
  * Run the package from its BetterGI script directory. Screenshots are stored
    under observations/<session>/frame-NNNNN.png; status.json contains the
    immutable per-frame OCR, screenshot path, classification, and Windows RDP
    session identity. Screenshots are retained; the package does not prune them.

Default operation is observation-only. It captures one frame every five
seconds for at most 30 minutes, then writes state=observation_limit. Cancel the
BetterGI script to stop sooner. This mode sends no game input.

Autonomous navigation is an experimental opt-in. It first requires the RDP
session identity to remain stable and rechecks foreground ownership before
each input. The journal is opened only after getPositionFromMap() succeeds as
a positive world-HUD signal. If the early tutorial/locked minimap makes that
API throw or return no position, the package leaves the state unknown and does
not open the journal. A recognized journal stage can use only route data
already supplied under the exact stage key in routes.json. Each route must be
a BetterGI route object with info and a nonempty positions array of finite x/y
points; no coordinates or paths are created by this package. Before starting
such a route, it sends Escape, captures again, and requires the world-HUD
position check to succeed.

Known limitation: the tutorial's locked minimap cannot provide native path
tracking. The package cannot safely navigate those objectives with the current
adapter. Unknown OCR, an unavailable minimap, an absent route, a changed RDP
session, or lost game focus stops navigation. Dialogue advancement is limited
to a recognized Paimon speaker plus subtitle in the expected region and an
English Auto label at the top left, excluding ambient world dialogue. Before
one VK_SPACE press, it captures again and requires the recognized dialogue
signature to remain unchanged. It does not choose dialogue options.

The runner's elapsed-time budget is checked between awaited calls. A hung
BetterGI/native capture, OCR, input, or route task cannot be preempted by this
JavaScript wrapper. Do not treat a started route call or an ended pilot state
as proof that the quest completed; verify the in-game journal yourself.

This standalone package has not been validated through a live game run.
Bird's Eye View was completed in English on 2026-10-10 using the separate
OpeningQuestPilot bridge and supervised controllers in tools/quest-pilot.
The journal confirmed Unexpected Power before the controller stopped; its
combat tutorial was not performed. That run validates the supervised controls,
not this package's unfinished route adapter. Review route data and all status
records before any opt-in navigation.
