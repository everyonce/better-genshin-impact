ENGLISH COMMISSION PILOTS 0.1.0

Requirements
  - English BetterGI r6 or newer from everyonce/english-interface. The standard
    upstream build does not yet have the required runForQuest route API.
  - English in-game text and a 1920 x 1080 game client, windowed or fullscreen.
    Your RDP desktop can stay 2560 x 1440. Configure capture and OCR normally.
  - The selected daily commission must currently be available on this account.
    These scripts cannot create a commission or unlock a quest chain.

Run a pilot
  1. In BetterGI, open JS Script. Add English Commission Pilots to a Scheduler
     group, then open that entry's custom script settings.
  2. Choose A Returning Customer, Adventurer Exam: Battle Tactics, or Question
     and Answer. All package settings, selector labels and status logs are English.
  3. Open Genshin's quest journal (J), select the matching active commission so
     its English title is visible, and close the menu. Start from normal gameplay.
  4. Run this script entry in the Scheduler. The pilot checks the journal before
     travelling. Keep the BetterGI Stop Current Task hotkey available.

Pilot behavior
  A Returning Customer: travels to Siegfria and handles recognized dialogue.
    Have Jade Parcels prepared. Submit the requested item manually when the
    hand-in window appears. No automatic cooking or inventory selection.
  Adventurer Exam: Battle Tactics: introduction with Anna/Anthony, travel and
    combat using the unchanged upstream route, then Anna's final dialogue.
    Configure a working party/combat strategy in the Scheduler group's map-
    tracking settings. This pilot does not generate a combat strategy.
  Question and Answer: travels to Swan and selects verified English answers
    in the order Librarian, Cavalry Captain, Outrider. This commission also has
    the label Basic Knowledge of the Knights; either journal label is recognized.
    If a handbook page opens, close it manually; the pilot will wait.

Settings
  Commission to run: selects one pilot, not an automatic scan of all commissions.
  Dialogue timeout: 30-300 seconds per interaction; default 120 seconds.
  Let me choose every dialogue answer: leaves all choices to you while ordinary
    dialogue still advances. Normally, only verified choices are clicked.
  Validate the package only: reads the local data, validates all three pilots,
    and reports problems without sending game input.

Unknown choices wait for your input until the dialogue timeout. Timeouts and
missing NPCs stop execution; they do not continue into the next route. A matched
English Commission Complete/Completed banner is required to report completion.
If the banner was missed, the result is explicitly UNCONFIRMED; check J yourself.
The game must use the default J journal binding. Stop the script before changing
menus or moving the game window. Use BetterGI's Stop Current Task hotkey.

Status and limitations
  This is an experimental source-tested adaptation, not a gameplay-certified
  release. Automated tests use fake OCR and input APIs; no game session was run
  during development. Actual captures and one supervised run per available pilot
  are still needed to validate OCR, NPC interaction positions, route timing and
  completion banners. The route runner may stop on a different quest stage.
  Start from the initial commission stage; automatic resumption is not implemented.
  This package does not change game settings, cooking inventories, daily region
  preferences, or the user's original Chinese script packages. No network calls.

Implementation and provenance
  Seven original upstream process/route JSON files are preserved byte-for-byte,
  along with the neutral Paimon HUD icon. Only the four route files are executed;
  the Chinese process files are retained as source evidence, not evaluated.
  The English engine uses its own plans, settings and exact normalized OCR matches.
  Waypoints, movement modes and combat actions are unchanged. Route display names
  are replaced in memory so the native pathing log uses English pilot names.
  Internal source paths remain Chinese to preserve references and attribution.
  Original route authors include 云闲vsv and 11; consult each route's info object.
  Source: babalae/bettergi-scripts-list, commit
    af12cfab667f85b857e1fe69f4ca5f52aa542ca8, repo/js/AutoCommission.
  English quest/NPC/choice evidence and pinned data hashes are in pilots.json.
  Text references use Dimbreath/AnimeGameData revision
    433284d22ef1a704e9d49ae22fb96cf7a245828e with quest transcript cross-checks.
  Review third-party source terms before redistributing this pilot package.

The native r6 quest-route API prevents path tracking's private AutoSkip handler
from selecting arbitrary answers and prevents its generic Escape handler from
closing quest screens. The script uses an explicit dialogue config that disables
default/custom-priority choices, automatic submission, rewards and expeditions.
It clears its temporary trigger configuration when execution ends.
