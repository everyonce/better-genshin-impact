Opening Quest Pilot - experimental supervised development tool

This is a BetterGI capture/OCR/input bridge for manually supervising the first
quest of a fresh account (Wanderer's Trail). It is not a ready campaign script or a prebuilt route.
An operator must inspect each screenshot and decide the next bounded action.
Only actual on-screen quest evidence can establish completion; an action receipt
means the command executed and a new observation was saved, not quest completion.

1. Install English BetterGI r8 or newer inside Desktop Clone/RDP and use a 16:9
   game window. Capture and input coordinates are normalized to 1920x1080.
   English is preferred; this package never changes
   game language. Start the script through BetterGI. If the opening screen lacks
   the normal world HUD, its script group must explicitly allow non-main-UI start.
2. Leave enableInput unchecked for observation-only use. Check it in BetterGI
   settings only when ready for supervised game input. Read observation.json and
   its screenshotPath. Images are observations/<session>/frame-0001.png etc. OCR is
   full-screen plain text plus bounding boxes and can miss or misread text.
3. Write exactly one command to package-root command.json using an atomic file
   replacement. Copy session and frameId from the CURRENT observation; supply a
   new id and createdAt as current Unix milliseconds. Wait for receipt.json and
   the next observation before deciding and writing another command.
4. Stop with the BetterGI cancel control, or the stop command. The session ends
   after 30 minutes or 120 seconds without an accepted command. Restart creates
   a new session; commands from earlier sessions are rejected without input.

Example (replace the sample session, expectedFrameId, and timestamp):
{"id":"step-001","session":"COPY-CURRENT-SESSION","expectedFrameId":1,"createdAt":0,"action":"observe"}

Command actions and additional fields:
  observe / stop: no extra fields; permitted with input disabled.
  keyPress: key = VK_W, VK_A, VK_S, VK_D, VK_F, VK_SPACE, VK_ESCAPE, VK_J, or VK_M.
  hold: key = VK_W, VK_A, VK_S, VK_D, or VK_SPACE; ms = integer 30..1000.
  moveMouseBy: dx and dy = integers -300..300.
  click: x = integer 0..1919; y = integer 0..1079.

All commands require id, session, expectedFrameId, createdAt, and action.
Unknown fields/actions, stale frames, duplicate ids, and commands older than
30 seconds or dated in the future are rejected. No shell, HTTP, or command-code
evaluation exists. Invalid JSON/read/write/capture failures stop the session.
Before input, BetterGI focuses its bound game window and verifies foreground
ownership. Every input checks focus again; holds check focus at most 50 ms apart.
Losing focus stops the session and releases held keys even while unfocused.
Held keys are also released on errors/cancellation; prior metrics are restored and
dispatcher triggers cleared. Other automatic triggers are cleared at startup.

journal.log appends started/completed/rejected/failed action receipts; receipt.json
is the latest receipt. A started receipt without completion requires inspecting
the game before continuing. Never assume the action did not happen and replay it.
Screenshots are local and retained in a separate folder per session; observation.json
contains the latest observation and journal.log retains receipts. Do not type movement
commands while a menu or text box is open. Select commands only from fresh visual
evidence. Verify Wanderer's Trail completion after the rock-face climb from the
game's quest state, including the transition to the next quest, Bird's Eye View.
Reaching the Statue of The Seven is not the first quest's completion criterion.

Tests (from repository root): node --test Test/OpeningQuestPilot/engine.test.cjs

Live validation (2026-10-10, English game text, native 1920x1080 capture):
This bridge was used under step-by-step visual supervision to complete
Wanderer's Trail. The game displayed "Wanderer's Trail - Quest Completed",
and the journal then showed "Bird's Eye View" / "Follow the path". The pilot
was stopped at that point. No game-language change was needed. This validates
the supervised workflow; it does not make the package an unattended quest runner
or validate unattended operation.

RDP validation (2026-10-10): the r8 bridge completed Bird's Eye View using
supervised path segments, bounded visual Paimon following, and dialogue
advancement. The actual game was 2560x1440, with 1920x1080 normalized captures,
in Windows RDP session 5. The journal then selected Unexpected Power and its
Elemental Skill objective. The pilot stopped without performing that combat
tutorial. Game text stayed English. See tools/quest-pilot for the supervised
controllers and Test/BirdsEyeViewPilot/completed-run-journal.json for the final
OCR evidence. navigation.json records the remote session and optional native
map position; locked tutorial minimaps cannot supply that position.
